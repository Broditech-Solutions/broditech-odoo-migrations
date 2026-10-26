"""Preserve Avant queue jobs before queue_job's SQL uninstall drops its table."""

import json
import logging

_logger = logging.getLogger(__name__)
_METHODS = {
    "res.partner": "_job_sync_partner_to_am",
    "project.project": "_job_sync_project_to_am",
}
_STATES = {
    "pending": "pending", "enqueued": "pending", "done": "done",
    "failed": "failed", "cancelled": "failed", "started": "failed",
    "wait_dependencies": "failed",
}


def _json(value, default):
    return json.loads(value) if isinstance(value, str) else (default if value is None else value)


def job_values(row):
    """Decode OCA's JSON recordset without importing its retired addon."""
    records = _json(row["records"], {})
    model = row["model_name"]
    ids = records.get("ids") if isinstance(records, dict) else None
    if (not isinstance(records, dict) or records.get("_type") != "odoo_recordset"
            or records.get("model") != model or row["method_name"] != _METHODS.get(model)
            or not isinstance(ids, list) or len(ids) != 1
            or type(ids[0]) is not int or ids[0] <= 0):
        raise RuntimeError(f"Cannot migrate Avant queue job {row['uuid']}: invalid target recordset")
    if _json(row["args"], []) != [] or _json(row["kwargs"], {}) != {}:
        raise RuntimeError(f"Cannot migrate Avant queue job {row['uuid']}: unexpected arguments")
    if row["state"] not in _STATES:
        raise RuntimeError(f"Cannot migrate Avant queue job {row['uuid']}: unknown state {row['state']}")
    state = _STATES[row["state"]]
    # The replacement has no ETA, graph dependencies, or running state. Never
    # replay work with unsupported scheduling or an uncertain remote outcome.
    if state == "pending" and (row.get("eta") or row.get("graph_uuid")):
        state = "failed"
    detail = "Migrated from queue.job. Original job metadata:\n" + json.dumps(row, default=str, sort_keys=True)
    if row["state"] == "started":
        detail += "\nInterrupted execution: reconcile the remote result before retrying."
    if state == "failed" and row["state"] in ("pending", "enqueued", "wait_dependencies"):
        detail += "\nLegacy scheduling/dependencies require review before retrying."
    return {
        "name": row.get("name") or f"Avant sync {row['uuid']}",
        "model_name": model, "res_id": ids[0], "state": state, "error": detail,
        "user_id": row.get("user_id") or records.get("uid"),
    }


def migrate(cr, version):
    cr.execute("SELECT to_regclass('queue_job')")
    if not cr.fetchone()[0]:
        _logger.info("No legacy queue_job table; skipping Avant job transfer")
        return
    cr.execute("SELECT to_jsonb(job) FROM queue_job job WHERE method_name IN %s ORDER BY id",
               (tuple(_METHODS.values()),))
    rows = [_json(result[0], {}) for result in cr.fetchall()]
    # Decode every job before creating records or allowing destructive cleanup.
    prepared = [(row, job_values(row)) for row in rows]
    if not prepared:
        return
    # am_integration has not initialized its new model yet. Create its normal
    # stored columns; Odoo will register the model and add constraints/indexes.
    cr.execute("""
        CREATE TABLE IF NOT EXISTS am_sync_job (
            id SERIAL PRIMARY KEY, name VARCHAR NOT NULL, model_name VARCHAR NOT NULL,
            res_id INTEGER NOT NULL, user_id INTEGER NOT NULL, company_id INTEGER NOT NULL,
            state VARCHAR NOT NULL, error TEXT, create_uid INTEGER, write_uid INTEGER,
            create_date TIMESTAMP WITHOUT TIME ZONE, write_date TIMESTAMP WITHOUT TIME ZONE
        )
    """)
    migrated = 0
    for row, values in prepared:
        xml_name = "legacy_queue_job_" + row["uuid"]
        cr.execute("SELECT res_id FROM ir_model_data WHERE module='am_integration' AND name=%s AND model='am.sync.job'",
                   (xml_name,))
        existing = cr.fetchone()
        if existing:
            cr.execute("SELECT id FROM am_sync_job WHERE id=%s", (existing[0],))
            if not cr.fetchone():
                raise RuntimeError(f"Missing previously migrated Avant job {row['uuid']}")
            continue
        cr.execute("""
            SELECT u.id, COALESCE(%s, u.company_id)
              FROM res_users u JOIN res_company c ON c.id=COALESCE(%s, u.company_id)
             WHERE u.id=%s
        """, (row.get("company_id"), row.get("company_id"), values["user_id"]))
        owner = cr.fetchone()
        if not owner:
            raise RuntimeError(f"Cannot migrate Avant queue job {row['uuid']}: missing user/company")
        cr.execute("""
            INSERT INTO am_sync_job
                (name, model_name, res_id, user_id, company_id, state, error,
                 create_uid, write_uid, create_date, write_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s::timestamp, NOW()),COALESCE(%s::timestamp, NOW()))
            RETURNING id
        """, (values["name"], values["model_name"], values["res_id"], owner[0], owner[1],
              values["state"], values["error"], owner[0], owner[0],
              row.get("date_created") or row.get("create_date"), row.get("write_date") or row.get("date_created")))
        target_id = cr.fetchone()[0]
        # Ownership belongs to the retained addon, never queue_job. UUID-based
        # XML IDs prevent duplicate imports if queue_job is retained or rerun.
        cr.execute("""
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES ('am_integration', %s, 'am.sync.job', %s, TRUE)
        """, (xml_name, target_id))
        migrated += 1
    _logger.info("Transferred %d Avant queue jobs to am.sync.job (%d already migrated)",
                 migrated, len(prepared) - migrated)
    # No ORM, commits, or execution of sync methods during migration.
