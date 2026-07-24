# Mobile application

Expo SDK 57 Android application for offline sequence analysis.

The application opens the final M1 fixture at
`assets/snapshot/m1-snapshot.db` through `expo-sqlite`, validates schema
version 2 and its metadata/counts against `manifest.json`, and displays a
controlled `local_data_error` if the local contract is invalid.

After validation, the main screen loads the real game and symbol catalog from
SQLite. It provides a row-major board, game selection, symbol selection, Undo
and Reset. Prefix/exact matching and Target are added in the following M1.4 and
M1.5 tasks.

Run all commands from the repository root:

```powershell
npm run snapshot:generate
npm run snapshot:validate
npm run start --workspace @game-predictor/mobile
npm run android:build:debug
npm run android:build:offline
npm run android:verify:offline
```

Use `android:build:offline` for the standalone, test-signed APK that includes
the JavaScript bundle and SQLite snapshot. Verify its package and embedded
snapshot with `android:verify:offline`. The debug build expects Metro.
