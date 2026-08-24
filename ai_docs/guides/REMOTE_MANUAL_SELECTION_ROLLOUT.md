# Rollout zdalnej ręcznej selekcji zdjęć

## Status i granice

Ten runbook jest checklistą TASK-0290. Nie jest zgodą na publiczne
udostępnienie ani na uruchomienie dużej partii. Lokalny wybór zdjęć pozostaje
pełnoprawnym fallbackiem na każdym etapie.

Każdy etap tworzy kanoniczny, checksumowany raport
`remote-manual-selection-rollout-v1`. Raport nie może zawierać kodu dostępu,
tokenu, cookie ani ścieżki absolutnej. Etap następny wymaga checksum wszystkich
wcześniejszych raportów w kolejności.

| Etap | Wielkość | Dodatkowa zgoda | Wymagane fault injection |
| --- | ---: | --- | --- |
| 1 | 10 operacji | nie | duplicate replay, restart recovery, stale generation |
| 2 | 100–500 | nie | API 5xx/retry, offline operator, revoke |
| 3 | około 1 000 | nie | restart API, restart workera, refresh/resume |
| 4 | około 8 000 | jawna zgoda właściciela | network fault, controlled restart, long-session resume |
| 5 | do 15 000 | jawna zgoda właściciela | unique-file scale, operation scale, resume after fault |

Nie przechodź do następnego etapu, gdy raport ma status `blocked` albo
`failed`. Dotyczy to także pojedynczego konfliktu, błędu kolejki, niezgodności
checksum manifestu/JPEG/JSON, utraty decyzji, duplikatu, zapisu obcego pliku lub
ponownego transferu wcześniej zweryfikowanego pliku.

## Flaga, monitoring i rollback

Zdalną powierzchnię można odciąć bez kasowania danych, audytu, outputu ani
lokalnej sesji:

```powershell
$env:GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED = 'false'
npm run api:dev
```

Następnie zatrzymaj uruchomiony Reviewer, aby przejął tę samą flagę. Sprawdź,
że `/manual-selection` i `/selection-api` nie są dostępne, a lokalny moduł nadal
działa. W razie incydentu unieważnij sesje zdalne w Adminie; nie usuwaj raportu
ani katalogu wynikowego. Tunel zatrzymuj wyłącznie przez kontroler:

```powershell
npm run reviewer:remote:stop
npm run reviewer:remote:status
```

Przed każdą próbą zanotuj wyłącznie nieczułe informacje: wersję aplikacji,
wersję przeglądarki, rodzaj połączenia, liczbę źródeł, rozkład ich rozmiarów,
czas, retry, konflikty, metryki UI/API/transferu/kolejki oraz CPU/pamięć procesu.
Nie zapisuj URL tunelu, kodu, tokenu, cookie ani ścieżek hosta do raportu.

## Etap 1 — deterministyczna bramka lokalna

Nie wymaga API, workera ani Quick Tunnel. Wykonuje dziesięć deterministycznych
operacji na syntetycznych JPEG-ach: select, deselect, undo, exact retry,
odrzucenie starej generacji, finalizację i ponowne odtworzenie manifestów po
symulowanym restarcie. Sprawdza też parity host-file/output-v1/trace-v1 oraz
brak nadpisania istniejącego pliku.

```powershell
npm run remote-selection:rollout:stage1
npm run remote-selection:rollout:check
```

Artefakt znajduje się w
`artifacts/remote-manual-selection-rollout/stage-1.json` i pozostaje lokalny.
Weryfikacja `check` potwierdza checksumę i kanoniczny JSON. W razie błędu
nie poprawiaj raportu ręcznie: zatrzymaj rollout, napraw przyczynę i utwórz
raport ponownie.

## Etapy 2–5 — obserwacja operatorska

Etapy 2 i 3 wykonuje się najpierw lokalnie (dwie karty, następnie dwa profile i
LAN). Quick Tunnel jest ręcznym, małym testem dopiero po zaliczeniu lokalnych
bramek. Nie uruchamiaj podczas implementacji tunelu ani partii 8k/15k.

Po zakończeniu kontrolowanej próby przygotuj lokalny plik obserwacji bez
sekretów i ścieżek. Ma zawierać następujące pola:

```json
{
  "stageId": "stage-2",
  "environment": { "browser": "Chrome", "network": "LAN" },
  "sourceManifestChecksumSha256": "<64 lowercase hex>",
  "sourceFileCount": 100,
  "sourceSizeBytes": [123456],
  "operationCount": 100,
  "selectedFileCount": 80,
  "hostOutputFileCount": 80,
  "outputManifestItemCount": 80,
  "traceEventCount": 100,
  "uiLatencySamplesMs": [12.0],
  "apiLatencySamplesMs": [8.0],
  "transferLatencySamplesMs": [40.0],
  "hostQueueLatencySamplesMs": [6.0],
  "throughputBytesPerSecondSamples": [3000000.0],
  "durationMilliseconds": 120000.0,
  "processCpuMilliseconds": 9000.0,
  "peakProcessMemoryBytes": 104857600,
  "retryCount": 0,
  "conflictCount": 0,
  "queueErrorCount": 0,
  "faultOutcomes": {
    "api_5xx_retry": true,
    "offline_operator": true,
    "revoke": true
  },
  "priorStageChecksums": { "stage-1": "<64 lowercase hex>" }
}
```

Opcjonalne liczniki integralności (`missingFinalFileCount`,
`duplicateFinalFileCount`, `foreignFileOverwriteCount`, `lostDecisionCount`,
`verifiedResendCount`, `manifestChecksumMismatchCount`,
`jpegChecksumMismatchCount`, `jsonParityMismatchCount`) domyślnie wynoszą zero.
Wartość dodatnia kończy etap statusem `failed`.

Zbuduj raport bez automatycznego uruchamiania transferu:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_remote_manual_selection_rollout.ps1 `
  -Observation .\artifacts\remote-manual-selection-rollout\stage-2-observation.json `
  -Output .\artifacts\remote-manual-selection-rollout\stage-2.json `
  -TimeoutSeconds 120
```

Przed etapem 4 lub 5 właściciel musi wyraźnie zatwierdzić zakres konkretnej
próby. Dopiero wtedy operator może przekazać identyczny znacznik zgody w
obserwacji i parametrze. Sam skrypt tylko zapieczętuje obserwację; nie startuje
sesji, tunelu ani transferu.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_remote_manual_selection_rollout.ps1 `
  -Observation .\artifacts\remote-manual-selection-rollout\stage-4-observation.json `
  -Output .\artifacts\remote-manual-selection-rollout\stage-4.json `
  -AllowLarge -OwnerApproval 'approved-<date>-<scope>' -TimeoutSeconds 120
```

## Checklista decyzji

Przed oznaczeniem etapu jako zaliczonego potwierdź:

1. `selectedFileCount == hostOutputFileCount == outputManifestItemCount`.
2. `traceEventCount == operationCount`.
3. Wszystkie wymagane fault injection mają wartość `true`.
4. Zatrzymanie/restart nie zgubiło decyzji confirmed ani outboxowej.
5. Wznowienie nie wysłało ponownie plików `verified`.
6. Interakcja nie czekała na upload; p50/p95/p99 są porównane z baseline etapu 1.
7. Finalizacja nie nastąpiła przy aktywnej wymaganej kolejce.
8. Lokalny fallback działa po revoke i rollbacku.

Etap 5 zawiera dwa osobne pomiary: dużo unikalnych plików oraz dużo operacji
select/deselect/reselect. Dopiero jego raport może uzasadnić decyzję, czy TASK
19 (chunkowanie) jest potrzebny. Brak takiego dowodu oznacza pozostanie przy
jednoplikowym transferze v1.
