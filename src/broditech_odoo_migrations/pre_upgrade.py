# License AGPL-3.0-or-later
"""Explicit pre-upgrade entry point: rename modules, then convert JSONB fields."""

import logging


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo.release import version_info

    from broditech_odoo_migrations import commission, mod347, queue_job

    if version_info[0] != 19:
        raise RuntimeError("These project migrations must run under Odoo 19")

    cr.execute(
        """
        SELECT name FROM ir_module_module
         WHERE state IN ('installed', 'to upgrade', 'to remove')
        """
    )
    installed = {row[0] for row in cr.fetchall()}
    _logger.info("Running Broditech Odoo 19 migrations for installed modules")
    # Module operations must precede the loading of base and the addon graph.
    commission.migrate(cr, version)
    if "l10n_es_aeat_mod347" in installed:
        mod347.migrate(cr, version)
    if "queue_job" in installed:
        queue_job.migrate(cr, version)
    _logger.info("Broditech Odoo 19 pre-upgrade migrations completed")
    # Odoo owns the transaction. Never commit or create a registry here.
