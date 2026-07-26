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
npm run db:baseline:verify
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

TASK-0015 provides a local-only FastAPI service and Next.js panel. TASK-0016
adds PostgreSQL 18, SQLAlchemy and an empty Alembic baseline. TASK-0018 adds the
first canonical domain tables and API operations for games and symbols.

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
never drops the development database `game_predictor`.

To run the full local platform, open two PowerShell terminals after migrating.

Terminal 1:

```powershell
npm run api:dev
```

Terminal 2:

```powershell
npm run admin:dev
```

The panel is available at `http://127.0.0.1:3000`. The health endpoint is
`http://127.0.0.1:8000/api/v1/health`, and generated FastAPI documentation is
available locally at `http://127.0.0.1:8000/docs`.

Game and symbol operations use the `/api/v1/admin/games` resource. `DELETE`
archives a record and never physically removes it.

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
