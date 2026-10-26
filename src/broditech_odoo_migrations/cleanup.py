# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Run with --pre-upgrade-scripts, before the module graph is loaded.

Use SQL upgrade helpers: legacy addons may have no loadable Odoo 19 source.
"""

import logging
from pathlib import Path

from odoo.modules.module import get_manifest, get_module_path
from odoo.modules.registry import Registry
from odoo.upgrade import util
from odoo.upgrade.util import helpers


_logger = logging.getLogger(__name__)
KEEP_MODULES = {"am_integration", "am_project", "disable_vat_check"}
ACTIVE_STATES = ("installed", "to upgrade", "to install", "to remove")


def _standard_addon_roots():
    roots = set()
    for name in ("base", "web", "web_enterprise"):
        path = get_module_path(name, display_warning=False)
        if path:
            roots.add(Path(path).resolve().parent)
        elif name != "web_enterprise":
            raise RuntimeError("Cannot locate standard Odoo addon %s" % name)
    return roots


def cleanup_plan(cr):
    cr.execute("SELECT name, state FROM ir_module_module WHERE state IN %s",
               (ACTIVE_STATES,))
    states = dict(cr.fetchall())
    roots = _standard_addon_roots()
    standard = {
        addon.name for root in roots for addon in root.iterdir()
        if (addon / "__manifest__.py").is_file()
    }
    cr.execute("""
        SELECT m.name, d.name
          FROM ir_module_module_dependency d
          JOIN ir_module_module m ON m.id = d.module_id
    """)
    dependencies = {}
    for name, dependency in cr.fetchall():
        dependencies.setdefault(name, set()).add(dependency)
    # Use current manifests for retained addons: the database may still contain
    # obsolete dependencies from before the major upgrade.
    keep = set()
    studio = {"studio_customization"} & states.keys()
    pending = list(KEEP_MODULES | (standard & states.keys()) | studio)
    while pending:
        name = pending.pop()
        if name in keep:
            continue
        manifest = get_manifest(name)
        if name in studio:
            # Studio creates an imported database module with no addon folder.
            # Use its database dependencies only when no exported manifest is
            # available, and always retain the Studio runtime itself.
            required = set(manifest.get("depends", ()) if manifest else dependencies.get(name, ()))
            required.add("web_studio")
        elif not manifest:
            raise RuntimeError("Cannot locate retained addon %s" % name)
        else:
            required = manifest.get("depends", ())
        keep.add(name)
        pending.extend(required)
    if "am_update" in keep:
        raise RuntimeError("Retained addons must not depend on retired addon am_update")
    removing = keep & {name for name, state in states.items() if state == "to remove"}
    if removing:
        raise RuntimeError("Required addons marked for removal: %s" % sorted(removing))
    candidates = states.keys() - keep
    # Include pending installations: they must not reach the Odoo 19 graph.
    # The SQL uninstall helper also cleans up any partially installed data.

    # Remove dependents before their dependencies, even without addon sources.
    order = []
    remaining = set(candidates)
    while remaining:
        depended_on = set().union(*(dependencies.get(name, set()) for name in remaining))
        leaves = remaining - depended_on
        if not leaves:
            raise RuntimeError("Cyclic addon dependencies: %s" % sorted(remaining))
        order.extend(sorted(leaves))
        remaining -= leaves
    return keep, order


def migrate(cr, version):
    keep, candidates = cleanup_plan(cr)
    if candidates and "base" in Registry(cr.dbname)._init_modules:
        raise RuntimeError(
            "Run this cleanup through --pre-upgrade-scripts before loading addons."
        )
    _logger.info("Retaining %d standard/required addons; exceptions: %s",
                 len(keep), ", ".join(sorted(KEEP_MODULES)))
    _logger.info("Non-standard addon cleanup plan (%d): %s",
                 len(candidates), ", ".join(candidates))
    for name in candidates:
        _logger.info("Uninstalling non-standard addon %s", name)
        # Preserve configuration and contacts still used by business records.
        # Removing its XML IDs lets the addon uninstall without deleting
        # business records that reference those methods or stages.
        cr.execute("""
            SELECT module || '.' || name FROM ir_model_data
             WHERE module = %s AND model IN ('account.payment.method', 'project.task.type', 'res.partner')
        """, (name,))
        configuration = [row[0] for row in cr.fetchall()]
        if configuration:
            util.delete_unused(cr, *configuration, keep_xmlids=False)
        # Some legacy addons registered real model names containing only
        # underscores. Upgrade-util mistakes those for SQL table names. Allow
        # only names verified in ir_model, and restore its guard afterwards.
        cr.execute("SELECT model FROM ir_model WHERE model LIKE %s AND model NOT LIKE %s",
                   ("%\\_%", "%.%"))
        valid_models = helpers._VALID_MODELS
        helpers._VALID_MODELS = valid_models | {row[0] for row in cr.fetchall()}
        try:
            util.uninstall_module(cr, name)
        finally:
            helpers._VALID_MODELS = valid_models
    cr.execute("SELECT name FROM ir_module_module WHERE name IN %s AND state != 'uninstalled'",
               (tuple(candidates) or ("",),))
    remaining = [row[0] for row in cr.fetchall()]
    if remaining:
        raise RuntimeError("Cleanup did not uninstall: %s" % remaining)
    _logger.info("Cleanup successfully uninstalled %d non-standard addons", len(candidates))
