import importlib
import json
import runpy
import sqlite3
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import broditech_odoo_migrations as package
from broditech_odoo_migrations import mod347, pre_upgrade, queue_job


class FieldCursor:
    def __init__(self, column_type, companies=((1,), (7,))):
        self.column_type = column_type
        self.companies = companies
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchone(self):
        return (self.column_type,) if self.column_type else None

    def fetchall(self):
        return self.companies


class FieldTests(unittest.TestCase):
    def test_mod347_preserves_both_values_for_all_companies(self):
        cr = FieldCursor("boolean")
        mod347.migrate(cr, "17.0.1.3.0")
        conversions = [(q, p) for q, p in cr.calls if "TYPE jsonb" in q]
        self.assertEqual(len(conversions), 1)
        query, params = conversions[0]
        self.assertEqual(json.loads(params[0]), {"1": True, "7": True})
        self.assertEqual(json.loads(params[1]), {"1": False, "7": False})
        self.assertIn("WHEN not_in_mod347 IS NULL THEN NULL", query)
        self.assertIn("DROP DEFAULT", cr.calls[2][0])

    def test_mod347_skips_already_converted_and_missing_columns(self):
        for kind in ("jsonb", None):
            with self.subTest(kind=kind):
                cr = FieldCursor(kind)
                mod347.migrate(cr, "17.0.1.3.0")
                self.assertFalse(any("ALTER TABLE" in q for q, p in cr.calls))

    def test_mod347_rejects_unexpected_type_and_missing_companies(self):
        for cr in (FieldCursor("text"), FieldCursor("boolean", companies=())):
            with self.assertRaises(RuntimeError):
                mod347.migrate(cr, "17.0.1.3.0")
            self.assertFalse(any("ALTER TABLE" in q for q, p in cr.calls))

    def test_queue_converts_all_five_columns_and_skips_converted_ones(self):
        for kind in ("text", "character varying", "json", "jsonb", None):
            with self.subTest(kind=kind):
                cr = FieldCursor(kind)
                queue_job.migrate(cr, "17.0.1.1.1")
                queries = [q for q, p in cr.calls if "ALTER TABLE" in q]
                self.assertEqual(len(queries), 0 if kind in ("jsonb", None) else 5)
                for query in queries:
                    self.assertIn('::jsonb', query)
                    self.assertNotIn('"queue.job"', query)

    def test_queue_rejects_unexpected_type(self):
        with self.assertRaises(RuntimeError):
            queue_job.migrate(FieldCursor("integer"), "17.0.1.1.1")


class MetadataCursor:
    """Execute the migration's metadata queries using real SQLite rows."""

    def __init__(self, rows, xmlids=()):
        self.db = sqlite3.connect(":memory:")
        self.operations = []
        self.db.executescript(
            "CREATE TABLE ir_module_module "
            "(name TEXT UNIQUE,state TEXT,latest_version TEXT,id INTEGER PRIMARY KEY);"
            "CREATE TABLE ir_model_data (module TEXT,name TEXT,model TEXT,res_id INTEGER);"
            "CREATE TABLE ir_model_constraint (module INTEGER);"
            "CREATE TABLE ir_model_relation (module INTEGER);"
        )
        self.db.executemany("INSERT INTO ir_module_module VALUES (?,?,?,?)", rows)
        self.db.executemany("INSERT INTO ir_model_data VALUES (?,?,?,?)", xmlids)

    def execute(self, query, params):
        if "WHERE name IN %s" in query:
            query = query.replace(
                "WHERE name IN %s",
                "WHERE name IN (" + ",".join("?" for _ in params[0]) + ")",
            )
            params = params[0]
        else:
            query = query.replace("%s", "?")
        self.result = self.db.execute(query, params)

    def fetchall(self):
        return self.result.fetchall()

    def fetchone(self):
        return self.result.fetchone()


def fake_rename(cr, old, new):
    cr.operations.append(("rename", old, new))
    cr.db.execute("UPDATE ir_module_module SET name=? WHERE name=?", (new, old))


def fake_merge(cr, old, new):
    cr.operations.append(("merge", old, new))
    cr.db.execute("DELETE FROM ir_module_module WHERE name=?", (old,))


class CommissionTests(unittest.TestCase):
    legacy = ("commission", "to upgrade", "17.0.1.1.0", 10)

    def setUp(self):
        upgrade = types.ModuleType("odoo.upgrade")
        upgrade.util = types.SimpleNamespace(rename_module=fake_rename, merge_module=fake_merge)
        parser = types.ModuleType("odoo.tools.parse_version")
        parser.parse_version = lambda v: tuple(int(x) for x in v.split("."))
        with patch.dict(sys.modules, {"odoo.upgrade": upgrade, "odoo.tools.parse_version": parser}):
            path = Path(package.__file__).parent / "commission.py"
            self.migrate = runpy.run_path(str(path))["migrate"]

    def test_active_target_merge_preserves_id_and_earliest_version(self):
        for state in ("installed", "to upgrade", "to install", "to remove"):
            with self.subTest(state=state):
                cr = MetadataCursor([self.legacy, ("commission_oca", state, "19.0.2.0.0", 20)])
                self.migrate(cr, "17.0.1.0.1")
                self.assertEqual(cr.operations, [("merge", "commission", "commission_oca")])
                expected = "to remove" if state == "to remove" else "to upgrade"
                self.assertEqual(
                    cr.db.execute("SELECT * FROM ir_module_module").fetchall(),
                    [("commission_oca", expected, "17.0.1.1.0", 20)],
                )
                cr.operations.clear()
                self.migrate(cr, "17.0.1.0.1")
                self.assertEqual(cr.operations, [])

    def test_placeholder_preserves_legacy_identity(self):
        cr = MetadataCursor([self.legacy, ("commission_oca", "uninstalled", None, 20)])
        self.migrate(cr, "17.0.1.0.1")
        self.assertEqual(cr.operations, [
            ("merge", "commission_oca", "commission"),
            ("rename", "commission", "commission_oca"),
        ])
        self.assertEqual(cr.db.execute("SELECT id FROM ir_module_module").fetchone(), (10,))

    def test_standard_current_names_and_uninstalled_modules_are_untouched(self):
        cr = MetadataCursor([
            ("commission", "installed", "19.0.1.0.0", 10),
            ("commission_oca", "installed", "19.0.2.0.0", 20),
            ("sale_commission", "installed", "18.0.1.0.0", 30),
            ("hr_commission", "uninstalled", None, 40),
        ])
        self.migrate(cr, "17.0.1.0.1")
        self.assertEqual(cr.operations, [])

    def test_xmlid_conflicts_abort_before_merge(self):
        rows = [self.legacy, ("commission_oca", "installed", "19.0.2.0.0", 20)]
        for target_id in (5, 6):
            cr = MetadataCursor(rows, [
                ("commission", "rule", "ir.rule", 5),
                ("commission_oca", "rule", "ir.rule", target_id),
            ])
            if target_id == 5:
                self.migrate(cr, "17.0.1.0.1")
                self.assertEqual(len(cr.operations), 1)
            else:
                with self.assertRaisesRegex(RuntimeError, "rule"):
                    self.migrate(cr, "17.0.1.0.1")
                self.assertEqual(cr.operations, [])


class EntryPointTests(unittest.TestCase):
    def test_namespace_contains_all_external_scripts(self):
        namespace = importlib.import_module("odoo.upgrade")
        root = Path(package.__file__).parent.parent / "odoo" / "upgrade"
        self.assertIn(root, [Path(p) for p in namespace.__path__])
        self.assertFalse((root / "__init__.py").exists())
        self.assertEqual(len(list(root.glob("*/*/pre-*.py"))), 3)
        for path in root.glob("*/*/pre-*.py"):
            self.assertTrue(callable(runpy.run_path(str(path))["migrate"]))

    def test_coordinator_order_and_installed_module_filtering(self):
        release = types.ModuleType("odoo.release")
        release.version_info = (19, 0)
        for installed in ((), (("queue_job",),), (("l10n_es_aeat_mod347",), ("queue_job",))):
            calls = []
            mocks = {
                name: types.SimpleNamespace(migrate=lambda cr, version, name=name: calls.append(name))
                for name in ("commission", "mod347", "queue_job")
            }
            cr = Mock()
            cr.fetchall.return_value = installed
            with patch.dict(sys.modules, {"odoo.release": release}), patch.multiple(package, create=True, **mocks):
                pre_upgrade.migrate(cr, "19.0.1.0.0")
            expected = ["commission"]
            names = {row[0] for row in installed}
            if "l10n_es_aeat_mod347" in names:
                expected.append("mod347")
            if "queue_job" in names:
                expected.append("queue_job")
            self.assertEqual(calls, expected)


if __name__ == "__main__":
    unittest.main()
