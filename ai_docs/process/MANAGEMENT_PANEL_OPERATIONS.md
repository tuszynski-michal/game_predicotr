---
title: Management panel operator guide
status: active
last_updated: 2026-10-09
---

# Panel Administracyjny — operations

## D-538 compact redesign — migration and destructive scope gate

TASK-0940 adds `0152_management_compact_panel` after 0151 in its independent
worktree. This section is the operator gate, not permission to execute it.
Before production migration, make and verify a binary backup with the existing
guide below. Restore it into a separate database and confirm representative
saved results, receipts and history. Structural deletion has no data downgrade.

Follow this order; the commands later in this guide are not permission to skip
an earlier gate:

1. Read the actual revision and pending predecessor SQL. Verify a binary backup
   by restoring it into a separate database before any prerequisite upgrade.
2. Obtain explicit authorization for prerequisites and stop at0151 if the current schema is earlier; never downgrade an installed0152 series branch.
3. Run the read-only receipt classifier and inspect the legacy count.
4. Preview compact-migration SQL; resolve any integrated migration branches.
5. Verify a current binary backup/restore and obtain explicit backfill approval.
6. Apply the exact reviewed revision using [Apply schema and application role](#apply-schema-and-application-role),
   then provision/check roles. Start services manually only after those checks.

The classifier accepts one pre-compact head: `0151_super_game_roles` or
`0152_super_game_series`. The latter changes game-series data, not receipt scope;
do not downgrade it. If current is earlier, review prerequisite SQL, verify the
backup and obtain authorization before reaching0151. Never run `upgrade head`
from an earlier schema before the receipt preview gate. All commands below are
operator actions; the prerequisite command applies only when current is earlier.

```powershell
.venv\Scripts\python.exe -m alembic current
.venv\Scripts\python.exe -m alembic upgrade 0151_super_game_roles
if ($LASTEXITCODE -ne 0) { throw 'Prerequisite upgrade failed; keep services stopped.' }
.venv\Scripts\python.exe -m alembic current
```

After confirming a single accepted pre-compact revision, and before applying
`0152_management_compact_panel` or changing receipts, run the read-only receipt classifier:

```powershell
.venv\Scripts\python.exe scripts/preview_management_receipt_migration.py
```

It reports journal/context/response-derived receipts and the exceptional
`legacy_redacted` count. Review that count before separately confirming
migration/backfill. Unknown receipts become fail-closed markers; they cannot
be retried as new operations. Migration uses the owner maintenance mode while
preserving operation UUID, actor, checksum and timestamp.

Only after explicit operator confirmation: apply the branch's single-head
migration using the existing manual migration/provisioning procedure, then
run `scripts/provision_database_roles.py --check`. It must verify owner,
fixed search_path, SECURITY DEFINER purge, SECURITY INVOKER trigger,
no PUBLIC execute on purge and a distinct application role without memberships.
Agents do not start/restart API/Admin. TASK-0945 supplies the empty merge
`0153_merge_compact_super_games` with both0152 parents and a matching guard.
It preserves both branches; its parents contain real DDL/backfill. Check one head.

The only apply command is in
[Apply schema and application role](#apply-schema-and-application-role), after
the SQL and verified-backup sections. Do not substitute `head` before integration
has produced and reviewed a single successor revision.

The compact machine editor sends the final game list with its name in one
command. Removing an existing assignment, including a legacy
`attached=false` row, requires the preview. Do not bypass confirmation.

Point/machine/game-detach confirmation displays preview counts. The ten-minute
token is actor/body/scope-bound; expiry or intervening writes requires a new
preview. Both local owner and valid online recipients have this accepted
destructive capability. It removes scoped management journal/saves, including
correction audit entries, while actual global corrections and game data remain.
Only the minimal pure-delete receipt persists and stays retryable.
Ordinary slot Clear still retains history.

The local PostgreSQL database is authoritative. The local Admin and recipient
Reviewer use the same panel components. Recipient access covers this module and
assigned active-game search/corrections. It does not grant imports, model or
rules administration. Only the local administrator creates and revokes links.

## Before applying this delivery

All commands below are for the operator, from the repository root in Windows
PowerShell. Acceptance tests do not migrate the operator's database or start,
stop or restart API, Admin, Reviewer or the tunnel. Stop your own application
and worker terminals for a planned maintenance window before applying DDL.
Check other running workers and finish or safely pause their work first.

An earlier production check recorded `0146_symbol_review_import_filter_index`.
The final read-only T7 check on 2026-10-08 returned
`0149_management_stake_saves`; acceptance did not apply that change. Always
read the actual current revision again before rollout. The original T1–T7
delivery requires `0150_management_sessions`; the D-538 compact delivery
requires `0153_merge_compact_super_games` and both0152 branches. The intervening graph includes the V7 branch
`0146_v7_operator_sources` joined by `0147_merge_v7_main`; the merge itself is
empty, but its other ancestry can contain real DDL. Do not assume the entire
upgrade is limited to the management additions. Review the exact pending SQL
and prerequisites for the actual database state before applying it.

```powershell
.venv\Scripts\python.exe -m alembic current
.venv\Scripts\python.exe -m alembic heads
.venv\Scripts\python.exe -m alembic history -r 0151_super_game_roles:0153_merge_compact_super_games
.venv\Scripts\python.exe -m alembic upgrade 0151_super_game_roles:0153_merge_compact_super_games --sql > artifacts\management-upgrade-preview.sql
if ($LASTEXITCODE -ne 0) { throw 'SQL preview failed; do not apply it.' }
```

Use the revision actually returned by `current` for the SQL preview if it
differs; for an installed series branch use `0152_super_game_series:0153_merge_compact_super_games`. An installed compact branch uses `0152_management_compact_panel:0153_merge_compact_super_games` and skips the already-applied receipt backfill. Preview any earlier predecessor range separately before reaching0151.
A disconnected offline preview is not proof that live data meets every
predecessor's constraints. Resolve unexpected branches or prerequisite
failures before proceeding. Management migrations 0148/0149/0150 are additive;
0152 backfills receipt scope. Their downgrade does not restore deleted data.
Do not use
`db:rollback`, database reset or a manual table drop as rollback.

## Back up and verify recovery

Back up the complete canonical database and preserve managed image storage,
configuration and the exact code commit separately. Images are paths and
metadata in the database; a database dump alone does not preserve their pixels.
Keep secrets out of shared screenshots, logs and acceptance artifacts.

The following uses default Compose database/user names. Replace both names
with the configured values if customized. It writes a PostgreSQL custom-format
archive inside the container and copies it as a binary file; PowerShell text
redirection must not be used for the archive.

```powershell
$backupName = 'game-predictor-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dump'
$backupFolder = Join-Path (Get-Location) 'backups'
New-Item -ItemType Directory -Path $backupFolder -Force | Out-Null
docker compose -f infra/docker/compose.yaml exec -T postgres pg_dump -U game_predictor -d game_predictor -Fc -f "/tmp/$backupName"
if ($LASTEXITCODE -ne 0) { throw 'Database backup failed.' }
docker compose -f infra/docker/compose.yaml cp "postgres:/tmp/$backupName" (Join-Path $backupFolder $backupName)
if ($LASTEXITCODE -ne 0) { throw 'Backup copy failed.' }
docker compose -f infra/docker/compose.yaml exec -T postgres pg_restore --list "/tmp/$backupName"
if ($LASTEXITCODE -ne 0) { throw 'Backup archive inspection failed.' }
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $backupFolder $backupName)
```

Archive inspection checks readability, not restoration. Before maintenance,
verify restoration into a separately named empty disposable database, and
check representative point/machine/slot/history and game data there. Never
restore over the authoritative database merely to test the backup. Recovery
after incompatible DDL requires restoring that verified backup with matching
code/configuration; it is a separate explicit operator action.

For a disposable database, use a unique name, create it empty, restore the
binary archive and compare representative counts and frozen results with the
source snapshot. Run this only after checking that the chosen name is unused;
never target `game_predictor`. The following example assumes the default
container and user, with the dump retained in the container:

```powershell
$restoreDb = 'game_predictor_restore_check_' + (Get-Date -Format 'yyyyMMddHHmmss')
docker compose -f infra/docker/compose.yaml exec -T postgres createdb -U game_predictor $restoreDb
if ($LASTEXITCODE -ne 0) { throw 'Disposable database creation failed.' }
docker compose -f infra/docker/compose.yaml exec -T postgres pg_restore -U game_predictor -d $restoreDb --exit-on-error "/tmp/$backupName"
if ($LASTEXITCODE -ne 0) { throw 'Disposable restore failed; do not migrate production.' }
docker compose -f infra/docker/compose.yaml exec -T postgres psql -U game_predictor -d $restoreDb -c 'SELECT count(*) FROM management_points;'
docker compose -f infra/docker/compose.yaml exec -T postgres psql -U game_predictor -d $restoreDb -c 'SELECT count(*) FROM management_stake_slots;'
docker compose -f infra/docker/compose.yaml exec -T postgres psql -U game_predictor -d $restoreDb -c 'SELECT count(*) FROM management_operations;'
docker compose -f infra/docker/compose.yaml exec -T postgres psql -U game_predictor -d $restoreDb -c 'SELECT count(*) FROM management_journal;'
```

Compare counts with read-only counts from the source at the backup snapshot.
Inspect representative frozen result IDs and values separately. This proves
restore readability for the checked archive, not rollback by Alembic downgrade.
Keep the disposable database until verification is recorded; remove it only as
a separate, deliberate cleanup action.

## Apply schema and application role

After the SQL review, verified backup and maintenance window, run each command
separately. Stop on the first nonzero exit code.

```powershell
.venv\Scripts\python.exe -m alembic upgrade 0153_merge_compact_super_games
if ($LASTEXITCODE -ne 0) { throw 'Migration failed; keep services stopped.' }
.venv\Scripts\python.exe scripts/provision_database_roles.py
if ($LASTEXITCODE -ne 0) { throw 'Application role provisioning failed.' }
.venv\Scripts\python.exe scripts/provision_database_roles.py --check
if ($LASTEXITCODE -ne 0) { throw 'Application role check failed.' }
.venv\Scripts\python.exe -m alembic current
```

`GAME_PREDICTOR_DATABASE_URL` is the restricted runtime role and
`GAME_PREDICTOR_OWNER_DATABASE_URL` is the schema owner for the same database.
Role checking must report compliance; `skipped` means the runtime uses the
owner and does not demonstrate application-role isolation. The startup schema
guard requires exactly `0153_merge_compact_super_games`. A
schema readiness error is not resolved by restarting the same unmigrated
database. The 0152 receipt backfill requires its separate read-only classifier
and operator confirmation above.

## Start local services and expose the recipient panel

After migration, the operator starts the API and Admin in their own separate
terminals and checks visible startup errors:

```powershell
npm run api:dev
```

```powershell
npm run admin:dev
```

Open Admin at `http://127.0.0.1:3000`, then **Panel Administracyjny**. Read-only
health check in a further terminal:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 10
npm run reviewer:remote:status
```

For first public exposure, install/configure the existing Reviewer tunnel
prerequisites using `npm run reviewer:remote:setup`. This setup can download
tools and is an explicit operator action. Build the current Reviewer with
`npm run reviewer:build` during maintenance before creating a public link.
Public ingress uses the existing production Reviewer on loopback port 3001;
a development Reviewer on that port is rejected. Do not start a second copy
or kill an unidentified process. Resolve port ownership in the operator's
terminal. No generic port forwarding or public Admin API exposure is needed.

In the local panel choose **Udostępnij panel online**, enter a recipient label
and choose 1/4/8/24/48/72 hours (default 8). Explicit link creation checks/starts
the existing shared Reviewer ingress. Send the returned link and the separate
eight-character code through your chosen channels. The backend issues the code
only at creation; the creating local browser retains it for display until
expiry or revocation. Session lists and journals never reveal it. The recipient opens
the HTTPS link and enters the code. Five failed codes lock that link.

Revoke access from the local link list. Revocation does not require a working
tunnel and never removes saves or history. Expiry/revocation blocks subsequent
reads and mutations, including commit-bound authorization checks. Re-unlocking
rotates that session's token; browser tabs retaining the old identity may lose
access. A stale tab cannot reassign its pending command to another link.
Existing board-search links remain limited to one game and also offer 48/72h;
existing expiry timestamps are preserved.

The same tunnel can serve other Reviewer assignments and search links. Closing
the last assignment preserves ingress while an active management/search link
requires it. Explicitly stopping the tunnel still makes every such link
unreachable. Check link usage before any planned tunnel stop.

## Daily panel workflow and recovery

- Create/edit a point (name, city, street), then its named machines. Assign only
  currently active games. Use **Edytuj** or **Usuń** on a tile. Deleting a
  point, machine or machine/game assignment requires a fresh preview with
  counts and confirmation. It removes management saves and journal within
  that scope. Actual global symbol corrections and game-owned data remain.
  Historical archived entities appear in a collapsed section for deletion.
- Select a machine and game. Six independent stakes appear in descending order:
  20,10,6,4,2,1.20 PLN. Browsing, ranges and 0–6 pins are drafts. Use
  **Zapisz układ** to persist exactly the selected start/range/pins.
- **Nowy układ** resets only the draft; the saved slot remains until confirmed
  **Zastąp układ** or **Usuń zapisany układ**. The latter clears only that stake
  slot and retains its ordinary journal. **Zapisz zmiany** updates the same
  start. Current symbol corrections write immediately to global game data.
- Selecting a saved stake shows prior quick pin rows while current data is
  checked. Expanding the saved result loads the full rows. Changed data
  records before/after; stale/error retains prior numbers. Unavailable pinned
  spin positions are explicit. Historical charts, rows, symbols and rules stay
  frozen; the historical board editor explicitly targets current data.
- After a lost response, preserve the browser tab's pending command and use its
  recovery action. Reload uses the same operation UUID/body/revision. Do not
  repeatedly create new commands or clear session storage to hide uncertainty.
  A revision conflict retains the draft; inspect the latest acknowledged state
  before choosing a replacement. Do not share storage across different links.

History defaults to 20 entries per page; full result rows load after expanding
the saved result/table and paginate 50. Point lists do not preload charts. A
selected game loads six compact cards and at most two concurrent refreshes.
The quick pin rows load from summaries. Names are labels; stable
UUIDs and domain sequence numbers identify the actual records.

## Availability and remaining live checks

72 hours is an access lifetime, not an uptime promise. PC, PostgreSQL, API,
Reviewer and the public tunnel must remain available. Sleep, shutdown, network
loss or a replaced Quick Tunnel URL can interrupt access. Starting a fresh
computer process alone does not recreate a stopped public tunnel. Hosting only
the frontend cannot make this workflow independent of the local backend/data.

After operator rollout, verify local and recipient visibility of the same save,
two-tab revision conflicts, loss/recovery of a response, revocation/expiry,
detached/archive history, and no access to unrelated Admin functions. Check
actual Android touch/keyboard and narrow-screen scrolling. Validate service
startup and existing records after a planned computer reboot, and confirm the
current public URL. Automated static browser fixtures and disposable database
process tests do not replace those real-device/live-ingress/reboot checks.

The reproducible browser gate uses an already installed Chrome/Edge, static
React/CSS and mock API records. It performs touch gestures at 390px and checks
390/1440/1920px geometry with 1/4/40 points, up to 40 machines per point and
200 active game IDs. It checks 44px controls, maximum 320px tiles and horizontal
overflow, and writes stage screenshots/results under
`artifacts/management-panel-browser/browser`. It starts no application service
and downloads no browser. The displayed symbol bitmap is a fixture, not a
production image. Each CDP command has a 15-second bound; the full run has a
110-second deadline and closes only its own isolated browser profile.

```powershell
npm run reviewer:management:browser
```

If auto-discovery cannot find an existing installation, set
`MANAGEMENT_BROWSER_EXECUTABLE` to that browser's actual executable path.
A missing browser or failed check exits nonzero; it is not accepted as PASS.

T7 recorded bounded read-only catalog/schema/count timings only. They are not
representative hierarchy, saved-chart or search performance measurements.
Measure only bounded operations on existing authorized data after rollout;
do not seed synthetic scale fixtures or run load benchmarks for acceptance.
