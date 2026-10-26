import json
import sqlite3
import unittest

from broditech_odoo_migrations import avant_jobs


def job(**updates):
    row = {
        'uuid': 'legacy-uuid', 'model_name': 'res.partner',
        'method_name': '_job_sync_partner_to_am', 'state': 'pending',
        'records': json.dumps({'_type': 'odoo_recordset', 'model': 'res.partner', 'ids': [42], 'uid': 7}),
        'args': '[]', 'kwargs': '{}', 'user_id': 7, 'company_id': 2,
        'name': 'Sync company to Avant Manager', 'exc_info': 'original traceback',
        'date_created': '2026-01-02 03:04:05',
    }
    row.update(updates)
    return row


class Cursor:
    """Execute metadata and transfer SQL against real SQLite rows."""
    def __init__(self, rows=None):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript('''
            CREATE TABLE res_users (id INTEGER PRIMARY KEY, company_id INTEGER);
            CREATE TABLE res_company (id INTEGER PRIMARY KEY);
            INSERT INTO res_users VALUES (7,2);
            INSERT INTO res_company VALUES (2);
            CREATE TABLE ir_model_data (module TEXT, name TEXT, model TEXT, res_id INTEGER,
                                       noupdate BOOLEAN, UNIQUE(module,name));
        ''')
        if rows is not None:
            self.db.execute('CREATE TABLE queue_job (id INTEGER PRIMARY KEY, payload TEXT)')
            self.db.executemany('INSERT INTO queue_job (payload) VALUES (?)', [(json.dumps(row),) for row in rows])

    def execute(self, query, params=()):
        self.regclass = "to_regclass('queue_job')" in query
        if self.regclass:
            self.result = self.db.execute("SELECT name FROM sqlite_master WHERE name='queue_job'")
            return
        if 'to_jsonb(job)' in query:
            query = "SELECT payload FROM queue_job WHERE json_extract(payload,'$.method_name') IN (?,?) ORDER BY id"
            params = params[0]
        query = query.replace('id SERIAL PRIMARY KEY', 'id INTEGER PRIMARY KEY')
        query = query.replace('%s::timestamp', '?').replace('%s', '?').replace('NOW()', 'CURRENT_TIMESTAMP')
        self.result = self.db.execute(query, params)

    def fetchone(self):
        result = self.result.fetchone()
        return (None,) if self.regclass and result is None else result

    def fetchall(self):
        return self.result.fetchall()


class AvantJobTests(unittest.TestCase):
    def test_all_states_preserve_history_without_replaying_terminal_or_running_jobs(self):
        for source, target in avant_jobs._STATES.items():
            with self.subTest(source=source):
                values = avant_jobs.job_values(job(state=source))
                self.assertEqual(values['state'], target)
                self.assertEqual((values['res_id'], values['user_id']), (42, 7))
                for text in ('legacy-uuid', 'original traceback', source):
                    self.assertIn(text, values['error'])

    def test_jsonb_project_and_uid_fallback(self):
        values = avant_jobs.job_values(job(model_name='project.project', method_name='_job_sync_project_to_am', user_id=None,
            records={'_type': 'odoo_recordset', 'model': 'project.project', 'ids': [55], 'uid': 7}, args=[], kwargs={}))
        self.assertEqual((values['model_name'], values['res_id'], values['user_id']), ('project.project', 55, 7))

    def test_invalid_payloads_abort_instead_of_losing_jobs(self):
        for updates in ({'records': 'bad JSON'}, {'records': '{}'}, {'args': '[1]'}, {'kwargs': '{"x":1}'},
                        {'state': 'unknown'}, {'model_name': 'other'},
                        {'records': {'_type': 'odoo_recordset', 'model': 'res.partner', 'ids': [1, 2]}},
                        {'records': {'_type': 'odoo_recordset', 'model': 'res.partner', 'ids': [True]}}):
            with self.subTest(updates=updates), self.assertRaises((RuntimeError, ValueError)):
                avant_jobs.job_values(job(**updates))

    def test_unsupported_scheduling_requires_review(self):
        for updates in ({'eta': '2030-01-01'}, {'graph_uuid': 'dependency-graph'}):
            values = avant_jobs.job_values(job(**updates))
            self.assertEqual(values['state'], 'failed')
            self.assertIn('review', values['error'])

    def test_transfer_preserves_dates_company_history_and_is_idempotent(self):
        cr = Cursor([job(), job(uuid='done-job', state='done', company_id=None), job(uuid='unrelated', method_name='other')])
        avant_jobs.migrate(cr, None)
        avant_jobs.migrate(cr, None)
        rows = cr.db.execute('SELECT res_id, user_id, company_id, state, create_date FROM am_sync_job ORDER BY id').fetchall()
        self.assertEqual(rows, [(42, 7, 2, 'pending', '2026-01-02 03:04:05'), (42, 7, 2, 'done', '2026-01-02 03:04:05')])
        self.assertEqual(cr.db.execute("SELECT count(*) FROM ir_model_data WHERE module='am_integration'").fetchone()[0], 2)
        self.assertEqual(cr.db.execute('SELECT count(*) FROM queue_job').fetchone()[0], 3)

    def test_validation_precedes_any_transfer(self):
        cr = Cursor([job(), job(uuid='invalid', args='[1]')])
        with self.assertRaises(RuntimeError):
            avant_jobs.migrate(cr, None)
        self.assertIsNone(cr.db.execute("SELECT name FROM sqlite_master WHERE name='am_sync_job'").fetchone())

    def test_missing_user_or_company_aborts(self):
        for updates in ({'user_id': 999}, {'company_id': 999}):
            with self.subTest(updates=updates), self.assertRaisesRegex(RuntimeError, 'missing user/company'):
                avant_jobs.migrate(Cursor([job(**updates)]), None)

    def test_missing_source_or_no_avant_jobs_skips_destination_creation(self):
        for rows in (None, [], [job(method_name='unrelated')]):
            cr = Cursor(rows)
            avant_jobs.migrate(cr, None)
            self.assertIsNone(cr.db.execute("SELECT name FROM sqlite_master WHERE name='am_sync_job'").fetchone())

    def test_dangling_marker_aborts(self):
        cr = Cursor([job()])
        avant_jobs.migrate(cr, None)
        cr.db.execute('DELETE FROM am_sync_job')
        with self.assertRaisesRegex(RuntimeError, 'Missing previously migrated'):
            avant_jobs.migrate(cr, None)
