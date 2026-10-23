"""Convert legacy queue payloads to the JSONB storage used by Odoo 19."""

import logging


_logger = logging.getLogger(__name__)

# These are PostgreSQL table names, not dotted Odoo model names.
_COLUMNS = {
    "queue_job": ("records", "args", "kwargs"),
    "queue_job_function": ("retry_pattern", "related_action"),
}


def migrate(cr, version):
    for table, columns in _COLUMNS.items():
        for column in columns:
            cr.execute(
                """
                SELECT attribute.atttypid::regtype::text
                  FROM pg_attribute AS attribute
                 WHERE attribute.attrelid = to_regclass(%s)
                   AND attribute.attname = %s
                   AND NOT attribute.attisdropped
                """,
                (table, column),
            )
            result = cr.fetchone()
            if not result or result[0] == "jsonb":
                continue
            if result[0] not in ("text", "character varying", "json"):
                raise RuntimeError(
                    f"Expected {table}.{column} to contain JSON text or JSONB, "
                    f"found {result[0]!r}"
                )

            # Identifiers come exclusively from the fixed mapping above.
            # Parse the serialized JSON rather than wrapping it as a string.
            # Invalid JSON aborts the transaction instead of discarding jobs.
            cr.execute(
                f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
                f'TYPE jsonb USING "{column}"::jsonb'
            )
            _logger.info("Converted %s.%s to JSONB", table, column)
