# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Run via --pre-upgrade-scripts before the Odoo module graph is loaded."""

import logging

from odoo.upgrade import util
from odoo.tools.parse_version import parse_version


_logger = logging.getLogger(__name__)

COMMISSION_MODULE_RENAMES = (
    ("commission", "commission_oca"),
    ("account_commission", "account_commission_oca"),
    ("hr_commission", "hr_commission_oca"),
    ("sale_commission", "sale_commission_oca"),
    ("sale_commission_pricelist", "sale_commission_pricelist_oca"),
)


def migrate(cr, version):
    # Query SQL directly: module renames must precede registry initialization.
    names = tuple(name for pair in COMMISSION_MODULE_RENAMES for name in pair)
    cr.execute(
        """
        SELECT name, state, latest_version, id
          FROM ir_module_module
         WHERE name IN %s
        """,
        (names,),
    )
    modules = {
        name: (state, installed_version, module_id)
        for name, state, installed_version, module_id in cr.fetchall()
    }
    pending = []
    for old, new in COMMISSION_MODULE_RENAMES:
        state, installed_version, _module_id = modules.get(old, (None, None, None))
        if state not in ("installed", "to upgrade", "to remove"):
            continue
        # A name shared by a legacy OCA addon and a current standard addon is
        # not sufficient evidence for a rename. Check the installed version.
        try:
            installed_major = int((installed_version or "").split(".")[0])
        except ValueError:
            raise RuntimeError(
                f"Cannot identify {old} as a legacy OCA installation: "
                f"invalid installed version {installed_version!r}"
            ) from None
        cutoff = 18 if old == "sale_commission" else 19
        if installed_major >= cutoff:
            _logger.info("Leaving current module %s unchanged", old)
            continue
        if new in modules:
            target_state, target_version, target_id = modules[new]
            if target_state not in ("uninstalled", "uninstallable"):
                # The upgrade may already have installed the renamed addon.
                # Merge ownership only if no XML ID would replace a different
                # record: merge_module otherwise resolves such collisions by
                # deleting or replacing records, which is unsuitable here.
                cr.execute(
                    """
                    SELECT source.name
                      FROM ir_model_data AS source
                      JOIN ir_model_data AS target ON target.name = source.name
                     WHERE source.module = %s AND target.module = %s
                       AND (source.model IS DISTINCT FROM target.model
                            OR source.res_id IS DISTINCT FROM target.res_id)
                     ORDER BY source.name
                     LIMIT 10
                    """,
                    (old, new),
                )
                conflicts = [row[0] for row in cr.fetchall()]
                if conflicts:
                    raise RuntimeError(
                        f"Cannot merge {old} into {new}: these XML IDs point "
                        f"to different records: {', '.join(conflicts)}"
                    )
                versions = [installed_version]
                if target_version:
                    versions.append(target_version)
                merge_version = min(versions, key=parse_version)
                merge_state = (
                    "to remove"
                    if "to remove" in (state, target_state)
                    else "to upgrade"
                )
                pending.append((old, new, "merge", merge_state, merge_version))
                continue
            cr.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM ir_model_data WHERE module = %s
                    UNION ALL
                    SELECT 1 FROM ir_model_constraint WHERE module = %s
                    UNION ALL
                    SELECT 1 FROM ir_model_relation WHERE module = %s
                )
                """,
                (new, target_id, target_id),
            )
            if cr.fetchone()[0]:
                raise RuntimeError(
                    f"Cannot replace the uninstalled {new} entry: it still "
                    "owns data or schema objects. Resolve those records first."
                )
        operation = "placeholder" if new in modules else "rename"
        pending.append((old, new, operation, None, None))

    # Validate all pairs before making any changes.
    for old, new, operation, merge_state, merge_version in pending:
        if operation == "merge":
            util.merge_module(cr, old, new)
            # Retain the earliest installed version so the legacy OCA data
            # receives the full set of module migrations on the next update.
            cr.execute(
                """
                UPDATE ir_module_module
                   SET state = %s, latest_version = %s
                 WHERE name = %s
                """,
                (merge_state, merge_version, new),
            )
            _logger.info("Merged legacy OCA module %s into %s", old, new)
            continue
        if operation == "placeholder":
            # Merge the empty catalog entry INTO the installed legacy entry,
            # then rename it. This preserves the installed module's ID, state,
            # and version so its own upgrade scripts remain eligible.
            util.merge_module(cr, new, old)
        util.rename_module(cr, old, new)
        _logger.info("Renamed OCA commission module %s to %s", old, new)
