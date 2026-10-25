"""Verify automatic startup after a real wheel install, without an Odoo import.

Usage: python3 tools/verify_wheel.py dist/package.whl
Uses an isolated temporary virtualenv and never downloads dependencies.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import zipfile


def main():
    wheel = Path(sys.argv[1]).resolve()
    hook = "broditech_odoo_migrations_autoload.pth"
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        assert hook in names, "Startup hook is missing from wheel"
        assert "broditech_odoo_migrations/cleanup.py" in names, "Cleanup is missing from wheel"
        assert "odoo/__init__.py" not in names
        assert "odoo/upgrade/__init__.py" not in names
        assert len([p for p in names if p.startswith("odoo/upgrade/") and "/pre-" in p]) == 3

    with tempfile.TemporaryDirectory(prefix="broditech-startup-") as temp:
        venv.EnvBuilder(with_pip=True).create(temp)
        python = str(Path(temp) / "bin" / "python")
        env = dict(os.environ)
        for key in ("PYTHONPATH", "ODOO_VERSION", "ODOO_PRE_UPGRADE_SCRIPTS"):
            env.pop(key, None)
        subprocess.run(
            [python, "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
            env=env, check=True,
        )
        probe = """
import json, os, sys
print(json.dumps({
    'scripts': os.environ.get('ODOO_PRE_UPGRADE_SCRIPTS'),
    'odoo_imported': any(n == 'odoo' or n.startswith('odoo.') for n in sys.modules),
}))
"""
        for version in (None, "17.0", "19.0"):
            scenario = dict(env)
            if version:
                scenario["ODOO_VERSION"] = version
            output = subprocess.check_output([python, "-c", probe], env=scenario, text=True)
            result = json.loads(output)
            assert not result["odoo_imported"], "Startup imported Odoo too early"
            if version == "19.0":
                script = Path(result["scripts"])
                assert script.is_file() and script.name == "pre_upgrade.py"
            else:
                assert result["scripts"] is None

        scenario = dict(env, ODOO_VERSION="19.0", ODOO_PRE_UPGRADE_SCRIPTS="/existing.py")
        output = subprocess.check_output([python, "-c", probe], env=scenario, text=True)
        scripts = json.loads(output)["scripts"].split(",")
        assert len(scripts) == 2 and scripts[1] == "/existing.py"
        print("Fresh-interpreter startup checks passed; no manual import or Odoo dependency required.")


if __name__ == "__main__":
    main()
