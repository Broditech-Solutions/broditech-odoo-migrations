"""Register an Odoo 19 pre-upgrade script before Odoo parses its configuration.

Called by a site-packages .pth file at Python startup. Do not import Odoo,
connect to PostgreSQL, or perform migrations from this module.
"""

import os
from pathlib import Path


def register():
    # ODOO_VERSION is supplied by Odoo.sh. Leave unrelated Python/Odoo
    # environments untouched, including source-version upgrade processes.
    if os.environ.get("ODOO_VERSION", "").split(".", 1)[0] != "19":
        return
    script = str(Path(__file__).resolve().with_name("pre_upgrade.py"))
    setting = "ODOO_PRE_UPGRADE_SCRIPTS"
    existing = [path.strip() for path in os.environ.get(setting, "").split(",")]
    paths = [script]
    for path in existing:
        if path and path not in paths:
            paths.append(path)
    os.environ[setting] = ",".join(paths)
