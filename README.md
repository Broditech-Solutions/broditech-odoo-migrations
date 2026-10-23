# Broditech Odoo migrations

Installable, project-specific migrations for an OCA database upgraded from
Odoo 17 to Odoo 19. This repository contains only migration code and tests.
It does not contain database dumps, filestores, credentials, or OCA addon code.

## Included changes

| Migration | Behavior |
| --- | --- |
| Modelo 347 | Convert `res_partner.not_in_mod347` from Boolean to JSONB, preserving its value for every existing company. |
| Queue jobs | Convert the five serialized queue payload columns from JSON text to JSONB. |
| Commission module names | Rename legacy OCA modules to their `_oca` names and handle existing target entries after checking XML ID conflicts. |

The explicit entry point applies field conversions only to modules marked
installed, pending upgrade, or pending removal. Current standard module names
are preserved using the installed-version checks from the locally tested
commission migration. Unsupported legacy commission modules are not guessed or
renamed. The scripts are safe to repeat and leave transactions to Odoo.

**The existing `am_update` uninstall cleanup is excluded.** That script remains
in the addon repository and may still run when that addon is upgraded.

## Upload to GitHub

Create an empty repository named `broditech-odoo-migrations`, then run from this
directory (replace `YOUR_ORG`):

```sh
git remote add origin https://github.com/YOUR_ORG/broditech-odoo-migrations.git
git push -u origin main
git rev-parse HEAD
```

In the **root `requirements.txt` of your Odoo.sh project**, add this line, using
the full commit hash printed above:

```text
broditech-odoo-migrations @ git+https://github.com/YOUR_ORG/broditech-odoo-migrations.git@COMMIT
```

The package declares `odoo_upgrade` (official upgrade utilities) as a dependency.
It follows the same installation mechanism documented by Odoo:
https://github.com/odoo/upgrade-util#installation
The utility dependency currently follows upstream `master`, matching the local
setup; pin that URL in `setup.cfg` to a tested commit too if you need a completely
frozen dependency set.

A private repository must be readable by Odoo.sh's pip installation process.
Use a public migration-only repository if appropriate, or configure access
through your organization's supported mechanism. Do not put tokens in a URL
committed to `requirements.txt`.

## Odoo.sh: discovery and execution are separate

Installing this package registers external migration files under the
`odoo.upgrade` namespace. It neither connects to a database during installation
nor patches the Odoo loader.

The Modelo 347 and queue scripts run automatically when the corresponding
installed addon is upgraded through a qualifying version change. For these
`19.0.1.0.0` scripts, Odoo requires:

```text
installed module version < 19.0.1.0.0 <= target module manifest version
```

The package also includes an early `base/0.0.0` hook. **This hook runs only if
`base` is selected for upgrade and its installed version is lower than its
manifest version.** A normal `-u all` does not bypass this version comparison.
After Odoo's upgrade service has upgraded core modules, base may already be at
the target version. Consequently, a requirements entry alone does not guarantee
that commission renames happen before the addon graph is built.

The loader's rules are visible in Odoo's source:
https://github.com/odoo/odoo/blob/19.0/odoo/modules/migration.py

For the same guaranteed ordering used locally, invoke the explicit entry point
in an Odoo.sh staging shell, against the restored test database, before normal
module loading. With the regular Odoo process stopped using the platform's
supported maintenance procedure, run:

```sh
PRE_UPGRADE_SCRIPT="$(python3 -m broditech_odoo_migrations --pre-upgrade-script)"
odoo-bin -d "$PGDATABASE" \
  --pre-upgrade-scripts="$PRE_UPGRADE_SCRIPT" \
  -u all --stop-after-init
```

`PGDATABASE` must identify the restored staging database; replace it with an
explicit database name if it is not set. Use `odoo` instead of `odoo-bin` on
installations exposing that executable. The explicit entry point runs commission
renames first, then both field conversions, without module-version gating.
Odoo documents this early mechanism in its loader:
https://github.com/odoo/odoo/blob/19.0/odoo/modules/loading.py

For Odoo.sh's automatic restore/update pipeline, the platform must invoke this
entry point early, or the base hook must be eligible. If neither is available,
arrange the early step with Odoo.sh support before the production upgrade.
A staging-shell modification does not carry over automatically to a fresh
production restore. Installing this dependency does not change that constraint.

The ordinary `/web/database/manager` restore does not trigger module migrations.
Do not restore a source Odoo 17 database straight into Odoo 19: first obtain the
core-upgraded dump through the normal Odoo upgrade service.

## Local verification

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m pip wheel --no-deps --no-build-isolation . -w dist
```

Tests cover conversion guards, installed-module filtering, commission merge
preflight, namespace discovery, and the packaged entry points. The database
tests use cursor doubles and SQLite for metadata queries; they do not replace
an Odoo 19/PostgreSQL staging upgrade.

For local use without pip installation, this is also an external upgrade root:

```sh
odoo -d DATABASE --upgrade-path=/path/to/this/repo/src/odoo/upgrade \
  -u l10n_es_aeat_mod347,queue_job --stop-after-init
```

That last command does not guarantee early commission renaming. Use the explicit
pre-upgrade command above when names still need correction.
