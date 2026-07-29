# Game Predictor

Offline-first Android application and local authoring tools for deterministic
layout-sequence analysis.

The product and architecture documentation lives in [`ai_docs`](ai_docs/README.md).
The active implementation state is tracked in
[`CURRENT_STATE.md`](ai_docs/process/CURRENT_STATE.md).

## Prerequisites

- Node.js 22.13 or newer LTS (Node.js 24 LTS recommended)
- npm 11
- Python 3.12
- Docker Desktop with Linux containers for the local PostgreSQL service
- for Android builds: JDK 17 and Android SDK Platform 36

All commands below are compatible with Windows PowerShell.

If Docker is missing, follow the official
[Docker Desktop installation guide for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
and use the WSL 2/Linux containers backend. Start Docker Desktop before running
the database commands.

## Bootstrap

```powershell
npm install
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

If JDK 17 and Android SDK 36 are not installed system-wide, the repository can
download a verified, isolated toolchain into the ignored `.tooling` directory.
Running this command accepts the Android SDK license agreement displayed by
Google's `sdkmanager`:

```powershell
npm run android:toolchain:setup
```

## Common commands

```powershell
npm run snapshot:generate
npm run quality
npm run api:dev
npm run admin:dev
npm run admin:build
npm run db:up
npm run db:migrate
npm run db:reset:local -- -ConfirmReset
npm run db:baseline:verify
npm run m2:acceptance
npm run openapi:generate
npm run openapi:check
npm run android
npm run android:build:debug
npm run android:signing:setup
npm run android:build:offline
npm run android:verify:offline
npm run android:device:accept
```

## Local administration foundation

M2 provides a local-only FastAPI service, Next.js panel and PostgreSQL 18
canonical database. The panel covers games, symbols, versioned rules, paylines,
symbol payout matrices, deterministic mock datasets, validation, preview and
immutable publication. Android remains independent from this local platform.

Start Docker Desktop first. The defaults work without environment variables.
From the repository root, initialize PostgreSQL and its migration history:

```powershell
npm run db:up
npm run db:migrate
npm run db:current
```

`db:up` waits for the PostgreSQL healthcheck. The database port is exposed only
on `127.0.0.1:5432`. PostgreSQL data lives in the named Docker volume
`game_predictor_postgres_data`; `npm run db:down` stops the service without
deleting that volume.

Run the isolated migration lifecycle test when changing Compose or migrations:

```powershell
npm run db:baseline:verify
```

This command starts PostgreSQL if needed and recreates only the dedicated
`game_predictor_baseline_test` and `game_predictor_catalog_test` databases. It
also runs the isolated `game_predictor_m2_acceptance_test` and
`game_predictor_worker_jobs_test` databases. It never drops the development
database `game_predictor`.

Run the complete M2 acceptance scenario separately with:

```powershell
npm run m2:acceptance
```

The scenario starts with an empty isolated database, creates the game, 12
symbols, three paylines, complete payouts, published rules and a published
1000-layout mock exclusively through the public Admin API. The isolated
database is removed after the test.

To run the full local platform, open two PowerShell terminals after migrating.

Terminal 1:

```powershell
npm run api:dev
```

Terminal 2:

```powershell
npm run admin:dev
```

The durable worker is a separate local process. Once a concrete workflow
handler is registered, run one claim attempt or continuous polling in another
terminal:

```powershell
npm run worker:once
npm run worker:poll
```

The worker has a registered `payout-v2` handler. It reads published datasets
in batches, stores versioned results in PostgreSQL and writes structural JSONL
audits under `artifacts/`. Use
`python -m game_predictor_worker --artifact-root <path>` when the default local
artifact directory is not appropriate. Import, validation, snapshot and build
handlers remain unregistered; claiming one of those jobs ends it with the
stable `JOB_HANDLER_NOT_REGISTERED` error and releases the execution slot.

The panel is available at `http://127.0.0.1:3000`. The health endpoint is
`http://127.0.0.1:8000/api/v1/health`, and generated FastAPI documentation is
available locally at `http://127.0.0.1:8000/docs`.

The `Manual review` section reads immutable TASK-0064 batches and writes
revisioned whole-board decisions plus immutable feedback versions. Image
endpoints use the local roots below; override them only when the accepted crop
namespace or source corpus is stored elsewhere:

```powershell
$env:GAME_PREDICTOR_REVIEW_CROP_ROOT = 'artifacts\m5-reviewed-manual-merge-v16-full-preflight'
$env:GAME_PREDICTOR_REVIEW_SOURCE_ROOT = 'examples\imgs'
```

The browser never supplies a filesystem path. Source images are selected by
the stored SHA-256, while board and cell paths come from the immutable review
snapshot.
Accepted/corrected decisions always contain 15 labels and require explicit
geometry confirmation. Feedback export is available only after every item in
the selected batch is resolved; rejected boards are retained in audit but
excluded from training samples.

Game and symbol operations use the `/api/v1/admin/games` resource. `DELETE`
archives a record and never physically removes it.

Stop local PostgreSQL without deleting authored data:

```powershell
npm run db:down
```

To deliberately erase all domain data from the exact local development
database `game_predictor` and recreate the current Alembic schema:

```powershell
npm run db:reset:local -- -ConfirmReset
```

The reset command refuses to run without `-ConfirmReset`, rejects a non-loopback
URL and rejects every database name other than exactly `game_predictor`. It
does not remove the Docker volume or any isolated test database. Back up any
authored development data before using it.

Configuration names and safe loopback defaults are documented in
`.env.example`. Override them in the relevant PowerShell process when needed:

```powershell
$env:GAME_PREDICTOR_API_PORT = '8000'
$env:GAME_PREDICTOR_ADMIN_ORIGIN = 'http://127.0.0.1:3000'
$env:GAME_PREDICTOR_DATABASE_URL = 'postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor'
npm run api:dev
```

The API rejects non-loopback host, origin and database configuration. The
database URL must use the `postgresql+psycopg` driver and explicit credentials,
port and database name. None of these processes is exposed to the local network
by the repository defaults.

## Generated Admin API client

FastAPI owns the HTTP response schemas. Export OpenAPI and regenerate the
private TypeScript client workspace after every API contract change:

```powershell
npm run openapi:generate
npm run openapi:check
```

Generation reads the FastAPI application directly and does not require a
running API process. `openapi:check` fails when either the saved OpenAPI file or
generated Fetch client is stale. The Next.js panel imports
`@game-predictor/admin-api-client`; the mobile workspace does not depend on it.

The development APK is created at
`apps\mobile\android\app\build\outputs\apk\debug\app-debug.apk`.
It expects a local Metro server. The standalone, privately signed APK containing
the JavaScript bundle and SQLite snapshot is created at
`apps\mobile\android\app\build\outputs\apk\release\app-release.apk`.
Both local commands target `arm64-v8a`, which covers the planned Pixel and
Galaxy test devices.

`android:verify:offline` checks the package identifier, architecture,
standalone JavaScript bundle, controlled local-data error contract and exact
SQLite checksum inside the APK. It also rejects a debug certificate, a
debuggable release and any final manifest that declares
`android.permission.INTERNET`.

Create or validate the persistent private signing material with
`android:signing:setup`. The ignored `.tooling\android-signing` directory
contains the keystore and local secrets. Back it up securely outside the
repository: losing this key prevents in-place updates of an already installed
APK. Never commit or print its contents.

Build explicit private versions with:

```powershell
$env:GAME_PREDICTOR_GRADLE_USER_HOME = 'C:\gp-gradle'
npm run android:build:offline -- --VersionName 0.1.2 --VersionCode 3
```

The short Gradle cache avoids the legacy Windows `MAX_PATH` limit in native
React Native dependencies when the repository itself has a longer path.

The physical Pixel and Galaxy installation, offline and update procedure is
defined in
[`M1_DEVICE_ACCEPTANCE.md`](ai_docs/quality/M1_DEVICE_ACCEPTANCE.md). M1.6 was
accepted on 2026-07-26; the changed-snapshot update check and detailed device
measurements are explicitly deferred to M3 under D-020.

The mobile application never downloads its domain data. The snapshot generator
places a versioned SQLite asset and manifest directly in the application source,
so changing authored data requires generating a snapshot and building a new APK.
