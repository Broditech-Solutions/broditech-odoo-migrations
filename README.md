# Broditech Odoo migrations

Installable, project-specific migrations for an OCA database upgraded from
Odoo 17 to Odoo 19. This repository contains only migration code and tests.
It does not contain database dumps, filestores, credentials, or OCA addon code.

## Included changes

| Migration | Behavior |
| --- | --- |
| Modelo 347 | Convert `res_partner.not_in_mod347` from Boolean to JSONB, preserving its value for every existing company. |
| Queue jobs | Convert the five serialized queue payload columns from JSON text to JSONB. |
| Avant sync queue | Transfer partner/project sync jobs and history to `am.sync.job` before removing `queue_job`. |
| Retired addons | Uninstall non-standard addons, including `am_update`, before loading the addon graph. Keep standard addons, `am_integration`, `am_project`, `disable_vat_check`, and their current dependencies. |
| Commission module names | Rename legacy OCA modules to their `_oca` names and handle existing target entries after checking XML ID conflicts. |

The explicit entry point applies field conversions only to modules marked
installed, pending upgrade, or pending removal. Current standard module names
are preserved using the installed-version checks from the locally tested
commission migration. Unsupported legacy commission modules are not guessed or
renamed. The scripts are safe to repeat and leave transactions to Odoo.

Version 0.3.0 moves the cleanup out of `am_update` and into this package.
It removes module-owned data and schema using Odoo's SQL upgrade helpers;
back up the database and verify the result on staging before production.
Retired modules are uninstalled in dependent-first order, including pending
installations and upgrades, without requiring their legacy Python sources.
Referenced payment methods, task stages, and contacts are preserved by detaching
their XML IDs; unreferenced configuration records are deleted.

Current manifests determine which dependencies must be retained. A retained
addon depending on `am_update`, a retained addon marked for removal, or cyclic
retired dependencies stops the cleanup. The complete removal plan is logged,
and any candidate still active after cleanup aborts the migration. Repeat runs
skip modules already uninstalled. The old addon migration must be removed from
the deployed addon repository as well; this repository contains its replacement.

## Studio customizations (0.4.1 onwards)

Cleanup preserves `studio_customization` when it is active in the database,
along with `web_studio` and its transitive dependencies. Studio's imported
module does not need a filesystem manifest: its database dependencies are
retained when there is no exported manifest. An exported module uses its
current manifest dependencies. Other retained addons still require valid
manifests, including the `web_studio` runtime itself.

An absent or already uninstalled Studio customization module is not installed
by this migration. A retained module marked for removal still stops cleanup.
Studio views referring to fields from retired addons may need adjustment.
If a previous cleanup removed Studio customizations, use a fresh upgraded
restore; this exception cannot recover deleted customizations.

## Avant sync job transfer (0.4.0 onwards)

Before cleanup, the entry point transfers all jobs for
`res.partner._job_sync_partner_to_am` and
`project.project._job_sync_project_to_am` into `am_sync_job`. It creates the
new model's stored columns before `am_integration` initializes its schema.
The source queue can contain JSON text or JSONB payloads. No retired addon
imports, sync method calls, HTTP requests, or manual commits are used.

| Legacy state | Destination state |
| --- | --- |
| `pending`, `enqueued` | `pending` |
| `done` | `done` |
| `failed`, `cancelled`, `started`, `wait_dependencies` | `failed` |

The destination model has only pending/done/failed states. Interrupted jobs
are kept failed for remote-result reconciliation; cancelled/completed work is
never automatically replayed. Pending jobs with an ETA or graph dependencies
also require review and are kept failed because the replacement runner cannot
honor those scheduling constraints. The original state, UUID, dates, error
information, retries, and other source metadata are retained in the job details.
Record ID, user, company, description, and creation/update dates are preserved;
missing company values fall back to the original user's main company.

UUID-based XML IDs owned by retained `am_integration` prevent duplicate imports.
Malformed recordsets, arguments unsupported by the replacement, missing owners,
and unknown states abort the migration before destructive cleanup. Only the
known singleton, argument-free calls are supported. Unrelated queue jobs are
not transferred and remain subject to the retired-addon cleanup policy.

The new cron processes pending jobs after the addon upgrade (normally every
five minutes); historical and failed jobs remain available for inspection.
Run against a fresh core-upgraded restore while the legacy `queue_job` table
still exists. Jobs already deleted by an earlier cleanup cannot be recovered
from that cleaned database. Look for `Transferred ... Avant queue jobs to
am.sync.job` before the cleanup plan in staging logs.

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

## Automatic execution on Odoo.sh (version 0.2.0 onwards)

Commit the pinned requirement to the Odoo 19 branch in Odoo.sh's upgrade
"update on commit" workflow. The dependency installation and subsequent Python
startup register the migration before Odoo loads its module graph. No addon
needs to import this library and no staging-shell command is required for the
intended workflow. The root requirements commit must point to version 0.4.1 or
later to include Studio preservation; the original 0.1.0 commit did not include startup registration.

Execution order:

1. Odoo.sh installs the requirement in Python's site-packages.
2. On the next interpreter startup, Python processes the installed
   `broditech_odoo_migrations_autoload.pth` file.
3. Our startup hook checks that `ODOO_VERSION` identifies Odoo 19, then prepends
   the packaged entry point to `ODOO_PRE_UPGRADE_SCRIPTS`. Existing script paths
   are retained and repeated registration does not duplicate paths.
4. Odoo 19 reads that environment setting during configuration parsing.
5. When Odoo.sh requests module updates, Odoo executes the entry point before
   loading `base`: commission renames, Avant job transfer, retired-addon cleanup
   (including `am_update`), then JSONB conversions for modules still installed.
6. The normal addon upgrade proceeds. Later duplicate calls safely skip work
   that is already complete.

This is a project-specific Python startup integration using Odoo's supported
environment setting, not a documented Odoo.sh build-hook API. The hook sets
configuration only: it does not import Odoo, open database connections, or change
the database at pip installation or Python startup. Odoo owns migration execution
and the transaction. It does not depend on a change to `base`'s manifest version.

The relevant mechanisms are documented in:

- Python site-package startup hooks:
  https://docs.python.org/3.12/library/site.html
- Odoo 19 environment option loading and `pre_upgrade_scripts`:
  https://github.com/odoo/odoo/blob/19.0/odoo/tools/config.py
- Execution before loading base:
  https://github.com/odoo/odoo/blob/19.0/odoo/modules/loading.py
- Odoo.sh's `ODOO_VERSION` environment variable:
  https://www.odoo.sh/faq

### Verify the staging build

The package's startup behavior is tested in a fresh Python interpreter after
wheel installation. Actual Odoo.sh execution must still be verified on staging.
In the build's update/upgrade log, look for these messages **before the affected
addons load**:

```text
extra upgrade scripts: [.../broditech_odoo_migrations/pre_upgrade.py]
Running Broditech Odoo 19 migrations for installed modules
Transferred ... Avant queue jobs to am.sync.job (...)
Non-standard addon cleanup plan (...)
Cleanup successfully uninstalled ... non-standard addons
Broditech Odoo 19 pre-upgrade migrations completed
```

The first is logged by Odoo's CLI; the other two are logged by our entry point.
Treat missing registration or a missing completion message as a failed
integration; do not assume the version-gated fallback has performed the work.

Python must process normal site-packages startup hooks. Launchers that disable
`site` processing, disable the user site where the dependency was installed, or
only add the package directory to `PYTHONPATH` will not process the `.pth` file.
Also, an explicit `--pre-upgrade-scripts` CLI option takes precedence over the
environment value; if the platform supplies that option, it must include our
entry point. These launcher details cannot be verified from the local workspace.

The migration runs on module-update startups, not every ordinary server restart.
A rebuild that does not request a module update does not execute migrations.
The ordinary `/web/database/manager` restore likewise does not trigger them.
Use Odoo.sh's upgrade workflow with a core-upgraded database; do not restore a
source Odoo 17 database directly into Odoo 19.

## Other environments and fallback hooks

External scripts remain available under the `odoo.upgrade` namespace for normal
version-gated discovery. The `base/0.0.0` fallback is subject to base's installed
version being lower than its manifest version. These hooks are not the primary
automatic registration mechanism on Odoo.sh.

Outside Odoo.sh, the startup hook leaves the environment unchanged unless
`ODOO_VERSION=19.0` is set. To invoke the explicit entry point locally instead:

```sh
PRE_UPGRADE_SCRIPT="$(python3 -m broditech_odoo_migrations --pre-upgrade-script)"
odoo -d DATABASE --pre-upgrade-scripts="$PRE_UPGRADE_SCRIPT" \
  -u all --stop-after-init
```

## Local verification

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m pip wheel --no-deps --no-build-isolation . -w dist
python3 tools/verify_wheel.py dist/broditech_odoo_migrations-0.4.1-py3-none-any.whl
```

Tests cover conversion guards, installed-module filtering, commission merge
preflight, namespace discovery, and startup registration. The wheel verifier
installs the built wheel in a temporary virtualenv and starts fresh interpreters
to check the `.pth` behavior without manually importing the package. The database
tests use cursor doubles and SQLite for metadata queries; they do not replace
an Odoo 19/PostgreSQL staging upgrade.

For local use without pip installation, this is also an external upgrade root:

```sh
odoo -d DATABASE --upgrade-path=/path/to/this/repo/src/odoo/upgrade \
  -u l10n_es_aeat_mod347,queue_job --stop-after-init
```

That last command does not guarantee early commission renaming. Use the explicit
pre-upgrade command above when names still need correction.
