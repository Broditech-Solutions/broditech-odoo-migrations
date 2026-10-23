"""Preserve the global Modelo 347 exclusion flag for every existing company."""

import json
import logging


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Use SQL only: the registry cannot initialize until this column is converted.
    cr.execute(
        """
        SELECT attribute.atttypid::regtype::text
          FROM pg_attribute AS attribute
         WHERE attribute.attrelid = to_regclass('res_partner')
           AND attribute.attname = 'not_in_mod347'
           AND NOT attribute.attisdropped
        """
    )
    column = cr.fetchone()
    if not column:
        _logger.info("No res_partner.not_in_mod347 column to migrate")
        return

    column_type = column[0]
    if column_type not in ("boolean", "jsonb"):
        raise RuntimeError(
            "Expected res_partner.not_in_mod347 to be boolean or jsonb, "
            f"found {column_type!r}"
        )

    if column_type == "boolean":
        # Include inactive companies. The old flag applied globally, including
        # shared contacts whose company_id is NULL.
        cr.execute("SELECT id FROM res_company ORDER BY id")
        company_ids = [str(row[0]) for row in cr.fetchall()]
        if not company_ids:
            raise RuntimeError("Cannot migrate the Modelo 347 flag without companies")

        true_values = json.dumps(dict.fromkeys(company_ids, True))
        false_values = json.dumps(dict.fromkeys(company_ids, False))
        # A legacy SQL Boolean default cannot be cast to JSONB either. Odoo's
        # field default supplies False after the conversion.
        cr.execute("ALTER TABLE res_partner ALTER COLUMN not_in_mod347 DROP DEFAULT")
        cr.execute(
            """
            ALTER TABLE res_partner
            ALTER COLUMN not_in_mod347 TYPE jsonb
            USING CASE
                WHEN not_in_mod347 IS NULL THEN NULL
                WHEN not_in_mod347 THEN %s::jsonb
                ELSE %s::jsonb
            END
            """,
            (true_values, false_values),
        )
        _logger.info(
            "Converted res_partner.not_in_mod347 to JSONB for %s companies",
            len(company_ids),
        )
    else:
        _logger.info("res_partner.not_in_mod347 is already JSONB; preserving values")

    cr.execute(
        """
        UPDATE ir_model_fields
           SET company_dependent = TRUE
         WHERE model = 'res.partner' AND name = 'not_in_mod347'
           AND company_dependent IS DISTINCT FROM TRUE
        """
    )
