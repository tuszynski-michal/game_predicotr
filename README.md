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
npm run android:build:offline
npm run android:verify:offline
```

The development APK is created at
`apps\mobile\android\app\build\outputs\apk\debug\app-debug.apk`.
It expects a local Metro server. The standalone, test-signed APK containing the
JavaScript bundle and SQLite snapshot is created at
`apps\mobile\android\app\build\outputs\apk\release\app-release.apk`.
Both local commands target `arm64-v8a`, which covers the planned Pixel and
Galaxy test devices.

`android:verify:offline` checks the package identifier, architecture,
standalone JavaScript bundle, controlled local-data error contract and exact
SQLite checksum inside the APK. The spike still contains Expo's default
`INTERNET` permission declaration; removing it and enforcing its absence is an
explicit M1.6 release gate. No M1.1 application code performs network requests.

The mobile application never downloads its domain data. The snapshot generator
places a versioned SQLite asset and manifest directly in the application source,
so changing authored data requires generating a snapshot and building a new APK.
