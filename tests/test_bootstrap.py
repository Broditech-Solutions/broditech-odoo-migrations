import os
import unittest
from pathlib import Path
from unittest.mock import patch

from broditech_odoo_migrations.bootstrap import register


class BootstrapTests(unittest.TestCase):
    def test_odoo19_registers_existing_packaged_entrypoint(self):
        with patch.dict(os.environ, {"ODOO_VERSION": "19.0"}, clear=True):
            register()
            path = Path(os.environ["ODOO_PRE_UPGRADE_SCRIPTS"])
            self.assertTrue(path.is_absolute())
            self.assertTrue(path.is_file())
            self.assertEqual(path.name, "pre_upgrade.py")

    def test_preserves_other_scripts_and_registers_only_once(self):
        with patch.dict(os.environ, {
            "ODOO_VERSION": "19.0",
            "ODOO_PRE_UPGRADE_SCRIPTS": " /existing.py, /another.py, /existing.py ",
        }, clear=True):
            register()
            first = os.environ["ODOO_PRE_UPGRADE_SCRIPTS"]
            register()
            self.assertEqual(first, os.environ["ODOO_PRE_UPGRADE_SCRIPTS"])
            paths = first.split(",")
            self.assertEqual(len(paths), 3)
            self.assertEqual(paths[1:], ["/existing.py", "/another.py"])

    def test_other_versions_and_unrelated_interpreters_unchanged(self):
        for version in (None, "17.0", "18.0", "20.0", ""):
            environment = {"ODOO_PRE_UPGRADE_SCRIPTS": "/existing.py"}
            if version is not None:
                environment["ODOO_VERSION"] = version
            with self.subTest(version=version), patch.dict(os.environ, environment, clear=True):
                register()
                self.assertEqual(dict(os.environ), environment)


if __name__ == "__main__":
    unittest.main()
