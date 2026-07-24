# Mobile application

Expo SDK 57 Android application for offline sequence analysis.

The application opens the final M1 fixture at
`assets/snapshot/m1-snapshot.db` through `expo-sqlite`, validates schema
version 2 and its metadata/counts against `manifest.json`, and displays a
controlled `local_data_error` if the local contract is invalid.

After validation, the main screen loads the real game and symbol catalog from
SQLite. It provides a row-major board, game selection, symbol selection, Undo
and Reset. Every non-empty board prefix is matched locally; one longer
candidate can be accepted from an accessible modal or dismissed for the current
prefix. A complete board is matched exactly and reports a unique sequence,
duplicate diagnostics, not found, loading, or a controlled local data error.
A unique sequence starts the local full-cycle Target calculation and displays
its loading, retryable error, and final summary states. Positive local peaks
are displayed below the summary in the same virtualized vertical list as the
screen header; an explicit empty state is shown when the cycle has no positive
peak.

Run all commands from the repository root:

```powershell
npm run snapshot:generate
npm run snapshot:validate
npm run start --workspace @game-predictor/mobile
npm run android:build:debug
npm run android:signing:setup
npm run android:build:offline
npm run android:verify:offline
npm run android:device:accept
```

Use `android:build:offline -- --VersionName 0.1.0 --VersionCode 1` for the
standalone, privately signed APK that includes the JavaScript bundle and SQLite
snapshot. Verify its package, certificate, missing `INTERNET` permission and
embedded snapshot with `android:verify:offline`. The ignored signing material
is created under `.tooling\android-signing`; back it up securely because the
same key is required for an in-place update. The debug build expects Metro.

Physical-device steps and controlled layouts are documented in
`ai_docs\quality\M1_DEVICE_ACCEPTANCE.md`.
