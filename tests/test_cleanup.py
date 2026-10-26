import runpy
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import broditech_odoo_migrations as package


class CleanupCursor:
    def __init__(self, states, dependencies=(), configuration=()):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(
            "CREATE TABLE ir_module_module (id INTEGER PRIMARY KEY, name TEXT, state TEXT);"
            "CREATE TABLE ir_module_module_dependency (module_id INTEGER, name TEXT);"
            "CREATE TABLE ir_model_data (module TEXT, name TEXT, model TEXT);"
            "CREATE TABLE ir_model (model TEXT);"
        )
        for name, state in states.items():
            self.db.execute("INSERT INTO ir_module_module (name,state) VALUES (?,?)", (name, state))
        for name, dependency in dependencies:
            self.db.execute(
                "INSERT INTO ir_module_module_dependency SELECT id,? FROM ir_module_module WHERE name=?",
                (dependency, name),
            )
        self.db.executemany("INSERT INTO ir_model_data VALUES (?,?,?)", configuration)
        self.db.execute("INSERT INTO ir_model VALUES ('legacy_model')")
        self.dbname = "test"

    def execute(self, query, params=()):
        # Adapt PostgreSQL tuple parameters for SQLite metadata queries.
        for param in params:
            if isinstance(param, tuple):
                query = query.replace("%s", "(" + ",".join("?" for _ in param) + ")", 1)
            else:
                query = query.replace("%s", "?", 1)
        flat = [value for param in params for value in (param if isinstance(param, tuple) else (param,))]
        # SQLite does not use PostgreSQL's default backslash LIKE escape.
        if "SELECT model FROM ir_model" in query:
            query, flat = "SELECT model FROM ir_model", []
        self.result = self.db.execute(query, flat)

    def fetchall(self):
        return self.result.fetchall()


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name in ("base", "web", "project"):
            addon = root / name
            addon.mkdir()
            (addon / "__manifest__.py").write_text("{}")
        self.manifests = {
            "base": {"name": "Base"}, "web": {"depends": ["base"]},
            "project": {"depends": ["base"]},
            "am_integration": {"depends": ["project"]},
            "am_project": {"depends": ["am_integration"]},
            "disable_vat_check": {"depends": ["base"]},
        }
        self.util = types.SimpleNamespace(uninstall_module=Mock(), delete_unused=Mock())
        self.helpers = types.SimpleNamespace(_VALID_MODELS={"res.partner"})
        module = types.ModuleType("odoo.modules.module")
        module.get_manifest = self.manifests.get
        module.get_module_path = lambda name, **kwargs: str(root / name) if name in ("base", "web") else None
        registry = types.ModuleType("odoo.modules.registry")
        registry.Registry = Mock(return_value=types.SimpleNamespace(_init_modules=set()))
        self.registry = registry.Registry
        upgrade = types.ModuleType("odoo.upgrade")
        upgrade.util = self.util
        util_module = types.ModuleType("odoo.upgrade.util")
        util_module.helpers = self.helpers
        with patch.dict(sys.modules, {
            "odoo.modules.module": module, "odoo.modules.registry": registry,
            "odoo.upgrade": upgrade, "odoo.upgrade.util": util_module,
        }):
            self.script = runpy.run_path(str(Path(package.__file__).with_name("cleanup.py")))

    def test_removes_am_update_and_retired_dependents_first_without_sources(self):
        cr = CleanupCursor(
            {"base": "installed", "am_update": "to upgrade", "old_dependency": "installed", "old_child": "to remove"},
            [("old_child", "old_dependency"), ("am_update", "am_project")],
        )
        keep, order = self.script["cleanup_plan"](cr)
        self.assertNotIn("am_update", keep)
        self.assertIn("am_project", keep)
        self.assertLess(order.index("old_child"), order.index("old_dependency"))
        self.assertEqual(set(order), {"am_update", "old_dependency", "old_child"})

    def test_preserves_current_transitive_dependencies_instead_of_stale_ones(self):
        self.manifests["am_project"]["depends"].append("retained_oca")
        self.manifests["retained_oca"] = {"depends": ["base"]}
        cr = CleanupCursor(
            {"base": "installed", "retained_oca": "installed", "stale_oca": "installed"},
            [("am_project", "stale_oca")],
        )
        keep, order = self.script["cleanup_plan"](cr)
        self.assertIn("retained_oca", keep)
        self.assertEqual(order, ["stale_oca"])

    def test_rejects_retained_dependency_on_am_update(self):
        self.manifests["am_project"]["depends"].append("am_update")
        self.manifests["am_update"] = {"name": "Update"}
        with self.assertRaisesRegex(RuntimeError, "must not depend"):
            self.script["migrate"](CleanupCursor({"am_update": "installed"}), None)
        self.util.uninstall_module.assert_not_called()

    def test_preserves_database_only_studio_and_its_dependencies(self):
        self.manifests["web_studio"] = {"depends": ["web", "studio_support"]}
        self.manifests["studio_support"] = {"depends": ["base"]}
        self.manifests["custom_studio_dependency"] = {"depends": ["base"]}
        cr = CleanupCursor(
            {"studio_customization": "installed", "web_studio": "installed",
             "studio_support": "installed", "custom_studio_dependency": "installed",
             "am_update": "to upgrade"},
            [("studio_customization", "custom_studio_dependency")],
        )
        keep, order = self.script["cleanup_plan"](cr)
        self.assertTrue({"studio_customization", "web_studio", "studio_support",
                         "custom_studio_dependency"}.issubset(keep))
        self.assertEqual(order, ["am_update"])

    def test_absent_or_uninstalled_studio_does_not_require_its_runtime(self):
        for states in ({}, {"studio_customization": "uninstalled"}):
            keep, order = self.script["cleanup_plan"](CleanupCursor(states))
            self.assertNotIn("studio_customization", keep)
            self.assertNotIn("web_studio", keep)
            self.assertEqual(order, [])

    def test_exported_studio_uses_current_manifest_dependencies(self):
        self.manifests["studio_customization"] = {"depends": ["project"]}
        self.manifests["web_studio"] = {"depends": ["web"]}
        cr = CleanupCursor(
            {"studio_customization": "installed", "stale_oca": "installed"},
            [("studio_customization", "stale_oca")],
        )
        keep, order = self.script["cleanup_plan"](cr)
        self.assertIn("web_studio", keep)
        self.assertIn("project", keep)
        self.assertEqual(order, ["stale_oca"])

    def test_studio_exception_does_not_hide_missing_runtime_or_removal(self):
        with self.assertRaisesRegex(RuntimeError, "Cannot locate retained addon web_studio"):
            self.script["cleanup_plan"](CleanupCursor({"studio_customization": "installed"}))
        self.manifests["web_studio"] = {"depends": ["web"]}
        with self.assertRaisesRegex(RuntimeError, "Required addons marked for removal.*studio_customization"):
            self.script["cleanup_plan"](CleanupCursor({"studio_customization": "to remove"}))

    def test_rejects_cycles_missing_retained_sources_and_required_removals(self):
        cr = CleanupCursor({"a": "installed", "b": "to upgrade"}, [("a", "b"), ("b", "a")])
        with self.assertRaisesRegex(RuntimeError, "Cyclic"):
            self.script["migrate"](cr, None)
        with self.assertRaisesRegex(RuntimeError, "marked for removal"):
            self.script["migrate"](CleanupCursor({"base": "to remove"}), None)
        del self.manifests["am_project"]
        with self.assertRaisesRegex(RuntimeError, "Cannot locate retained"):
            self.script["migrate"](CleanupCursor({}), None)
        self.util.uninstall_module.assert_not_called()

    def test_uninstalls_all_pending_states_preserves_configuration_and_repeats(self):
        cr = CleanupCursor(
            {"base": "installed", "am_update": "to upgrade", "retired": "installed",
             "pending": "to install", "removing": "to remove"},
            configuration=[("retired", "partner", "res.partner"), ("retired", "rule", "ir.rule")],
        )
        original = self.helpers._VALID_MODELS

        def uninstall(cr, name):
            self.assertIn("legacy_model", self.helpers._VALID_MODELS)
            cr.execute("UPDATE ir_module_module SET state='uninstalled' WHERE name=%s", (name,))

        self.util.uninstall_module.side_effect = uninstall
        self.script["migrate"](cr, None)
        self.assertEqual({call.args[1] for call in self.util.uninstall_module.call_args_list},
                         {"am_update", "retired", "pending", "removing"})
        self.util.delete_unused.assert_called_once_with(cr, "retired.partner", keep_xmlids=False)
        self.assertIs(self.helpers._VALID_MODELS, original)
        self.util.uninstall_module.reset_mock()
        self.script["migrate"](cr, None)
        self.util.uninstall_module.assert_not_called()

    def test_uninstall_failure_restores_model_guard(self):
        original = self.helpers._VALID_MODELS
        self.util.uninstall_module.side_effect = ValueError("uninstall failed")
        with self.assertRaisesRegex(ValueError, "uninstall failed"):
            self.script["migrate"](CleanupCursor({"am_update": "installed"}), None)
        self.assertIs(self.helpers._VALID_MODELS, original)

    def test_aborts_if_uninstall_leaves_an_active_module(self):
        with self.assertRaisesRegex(RuntimeError, "Cleanup did not uninstall.*am_update"):
            self.script["migrate"](CleanupCursor({"am_update": "to upgrade"}), None)

    def test_refuses_schema_cleanup_after_base_loaded(self):
        self.registry.return_value._init_modules.add("base")
        with self.assertRaisesRegex(RuntimeError, "pre-upgrade-scripts"):
            self.script["migrate"](CleanupCursor({"am_update": "installed"}), None)
        self.util.uninstall_module.assert_not_called()
