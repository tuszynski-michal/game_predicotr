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
- for Android builds: JDK 17 and Android SDK Platform 36

All commands below are compatible with Windows PowerShell.

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
npm run android
npm run android:build:debug
npm run android:signing:setup
npm run android:build:offline
npm run android:verify:offline
npm run android:device:accept
```

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
npm run android:build:offline -- --VersionName 0.1.0 --VersionCode 1
```

The physical Pixel and Galaxy installation, offline and update procedure is
defined in
[`M1_DEVICE_ACCEPTANCE.md`](ai_docs/quality/M1_DEVICE_ACCEPTANCE.md). It must be
performed with a connected device before the M1.6 gate can be closed.

The mobile application never downloads its domain data. The snapshot generator
places a versioned SQLite asset and manifest directly in the application source,
so changing authored data requires generating a snapshot and building a new APK.
