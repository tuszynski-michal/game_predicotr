---
title: TASK-0598 — V7 worker handler integration
status: done
last_updated: 2026-09-21
---

# TASK-0598 — bezpieczne podłączenie runtime'u V7 do handlera workera

## Status

`done`

## Goal

Handler produkcyjny rozpoznaje `v7_selection`, używa przypiętego lokalnego
manifestu oraz dedykowanego runtime'u V7 zamiast historycznego skanera, przy
niezmienionej blokadzie startu V7 w API i bez zapisu JPEG-ów.

## Context

Audyt T12 wykazał, że schema joba V7 ma wersję `4`, natomiast handler ładował
lokalny manifest wyłącznie dla wersji `3`. Po przyszłym zdjęciu blokady API
V7 mogłoby więc trafić do browserowego, historycznego workflowu. T13b tworzy
dedykowany pion runtime'u i trwałego checkpointu, ale nie zastępuje potrzebnej
kalibracji geometrii ani odbioru release'u.

## Dependencies / entry conditions

- T00–T12 oraz TASK-0597 są ukończone, lecz `v7.activationStatus` pozostaje
  `blocked`.
- V7 ma kanoniczną konfigurację payloadu v4, `LocalSourceManifest` i
  `V7ScanRunState`, lecz nie ma zaakceptowanego adaptera lokalizacji/OCR/jakości
  dla rzeczywistych danych.
- Brak aktywnej kalibracji jest stanem bezpiecznym: bezpośrednio uruchomiony
  job V7 musi zatrzymać się przed dekodowaniem, OCR i outputem.

## Recommended execution

`gpt-5.6-terra` z reasoning `xhigh`; po self-audycie wymagany niezależny review
`gpt-6-astra` z reasoning `medium`. Eskalacja jest wymagana, gdy implementacja
wymagałaby aktywacji V7, wprowadzenia niezmierzonego OCR/geometrii, zapisu do
`cut`, zmiany istniejącego workflowu albo obniżenia bramek bezpieczeństwa.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/quality/V7_T12_ACCEPTANCE.md`
- `ai_docs/tasks/completed/0596-v7-holdout-acceptance-and-release-gate.md`
- `ai_docs/tasks/completed/0597-v7-reels-holdout-evaluator.md`

## Scope

- Rozdzielić dispatch V7 od historycznego `SemiAutomaticImageSelectionJobHandler`
  przed legacy `_scan` i legacy writera.
- Traktować payload v3 i v4 jako lokalne źródło, walidować pełny manifest i
  przekazać V7 dokładnie jego `LocalSourceManifest`.
- Dodać mały, testowalny runtime workerowy: buduje `V7ScanRunState`, przyjmuje
  zastrzyk obserwatora źródeł, utrwala checkpoint po uporządkowanym prefiksie,
  finalizuje wyłącznie po EOF oraz nie tworzy operacji outputu.
- Dodać produkcyjny adapter fail-closed, który odmawia runtime'u bez
  zaakceptowanej server-owned kalibracji przed odczytem obrazu.
- Pokryć testami routing, restart z checkpointu, zmianę manifestu oraz ochronę
  przed fallbackiem do browserowego legacy scanera.

## Out of scope

- Aktywacja bramki API/UI, OCR, lokalizacja geometrii, analiza jakości,
  kalibracja, wybór ręczny, `V7OutputWriter`, `manual_output`, zapis JPEG-a,
  zmiana katalogu `cut` albo migracja schematu.
- Zmiana istniejących historycznych jobów i ich kontraktów.

## Acceptance criteria

- [x] Job `v7_selection`/schema `4` nigdy nie wywołuje legacy `_scan`,
  browserowego stagingu ani legacy writera.
- [x] V3 zachowuje obecną ścieżkę local-folder, a V7 ładuje tylko checksumowany
  manifest lokalny zgodny z runem.
- [x] Runtime V7 utrwala oraz przywraca checkpoint `V7ScanRunState`; po EOF
  istnieją wyłącznie propozycje/diagnostyka, bez operacji outputu i JPEG-a.
- [x] Brak aktywnej kalibracji zwraca stabilny kod błędu przed dekodowaniem i OCR.
- [x] Drift dowolnego pliku manifestu podczas wznowienia blokuje V7 fail-closed.
- [x] API gate, stan release'u i wszystkie testy regresji historycznego handlera
  pozostają niezmienione.

## Technical notes

`workflow_mode=v7_selection` jest nadrzędne nad `recognizer_fingerprint`.
Najpierw handler waliduje identyczność runu i payloadu, następnie ładuje lokalny
manifest dla schema `{3, 4}`. Dla V7 przekazuje manifest oraz checkpoint do
`V7WorkerRuntime`; nie konwertuje go do `_StagedSource` dla legacy scanera.

Runtime ma dwa kontrakty. `V7SourceObserver` zwraca jedną kompletną
`V7ScanObservation` dla przypiętego indeksu; `V7CalibrationRuntimeFactory`
pozwala serwerowi dostarczyć takiego obserwatora tylko dla zatwierdzonego,
zgodnego fingerprintu kalibracji. Domyślna fabryka odrzuca fingerprint
`unavailable` kodem `V7_CALIBRATION_UNAVAILABLE` bez otwierania JPEG-a. To jest
celowa granica między istniejącą trwałą orkiestracją i przyszłym, zmierzonym
adapterem obrazu.

Na każdej obserwacji runtime wywołuje `V7ScanRunState.consume`, po czym zapisuje
cały checkpoint przez istniejący fenced store. Restart odtwarza tylko
nieprzetworzony uporządkowany prefiks. Po EOF `finalize` tworzy wyłącznie
deterministyczne propozycje do diagnostyki. W tym tasku żadna ścieżka nie może
wywołać writera, `apply_selection` ani dotknąć docelowego katalogu.

Przykład: payload V7 z manifestem A i obserwatorami A[0], A[1] → checkpoint
po A[0], restart → obserwuje wyłącznie A[1], kończy `finalization_pending` /
`finalized` zgodnie z `V7ScanRunState`; nie kopiuje pliku. Ten sam run z
innym SHA A[1] → `V7_SOURCE_MANIFEST_DRIFT`, bez późniejszej obserwacji.

## Expected files

- Istniejące: `services/worker/src/game_predictor_worker/semi_automatic_selection/job.py` — dispatch i local-manifest routing.
- Istniejące: `services/api/src/game_predictor_api/domain/jobs.py` — schema `4` jest prawidłową wersją joba półautomatu.
- Nowe: `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_worker_runtime.py` — orkiestracja checkpointu i fail-closed factory.
- Istniejące: `services/worker/tests/test_semi_automatic_selection_job.py` — integracja handlera.
- Nowe: `services/worker/tests/test_v7_worker_runtime.py` — runtime, restart i drift.
- Istniejące: `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`, `ai_docs/process/CURRENT_STATE.md`, `ai_docs/process/DECISION_LOG.md`, `TEMP PLAN V7.md`.

## Test cases

- V7/schema 4 z zastrzykniętym obserwatorem → local manifest, checkpoint i
  finalizacja; legacy scanner, browser root i writer nie są użyte.
- Restart po pierwszej obserwacji → druga iteracja nie przetwarza prefiksu drugi
  raz; propozycje są deterministyczne.
- Zmieniony niewybrany plik lokalnego manifestu → fail-closed przed finalizacją.
- Domyślny runtime V7 bez kalibracji → `V7_CALIBRATION_UNAVAILABLE`, zero
  odczytów obrazów oraz zero plików outputu.
- Schema 3 i legacy v1/v4/v5/v6 przechodzą obecne skoncentrowane regresje.
- Test API potwierdza, że `SEMI_AUTOMATIC_SELECTION_V7_BLOCKED` nadal odrzuca
  start przed utworzeniem runu.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr; maks. 120 s na krok
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_v7_worker_runtime.py services/worker/tests/test_semi_automatic_selection_job.py services/api/tests/test_semi_automatic_image_selections.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection/v7_worker_runtime.py services/worker/src/game_predictor_worker/semi_automatic_selection/job.py services/worker/tests/test_v7_worker_runtime.py services/worker/tests/test_semi_automatic_selection_job.py
.\.venv\Scripts\python.exe -m mypy --follow-imports=skip services/worker/src/game_predictor_worker/semi_automatic_selection/v7_worker_runtime.py services/worker/src/game_predictor_worker/semi_automatic_selection/job.py
```

## Risks / open questions

- Ten task celowo nie uruchamia prawdziwego OCR. Dopóki kalibracja i adapter
  obserwacji nie zostaną oznaczone oraz odebrane, V7 pozostaje zablokowane.
- `finalize_analysis` i raport legacy nie są właściwym zapisem dla V7; ewentualny
  kontrakt diagnostyki musi pozostać addytywny i nie udawać output acknowledgement.

## Outcome

Zakończono bez aktywacji V7. Schema v4 dociera teraz do dedykowanego runtime'u
workerowego z checksumowanym local manifestem; historyczny handler nie jest
fallbackiem dla V7. Brak kalibracji zatrzymuje job stabilnym kodem przed JPEG,
OCR i outputem.

### Changed

- `create_job` uznaje półautomatyczną schema `4`, zgodnie z istniejącym
  kontraktem V7.
- Handler rozdziela schema v3/v4 lokalnego źródła i dispatchuje V7 przed
  historycznym auditorem, `_scan`, `_select` oraz writerem. Waliduje także w
  obie strony zgodność workflow payloadu i durable runu.
- `V7WorkerRuntime` przywraca checkpoint, persistuje każdy uporządkowany
  prefiks i finalizację bez output operation. Domyślna fabryka jest fail-closed
  (`V7_CALIBRATION_UNAVAILABLE`).
- Zmiana, usunięcie lub wyzerowanie przypiętego JPEG-a przy dostępnym katalogu
  utrwala `blockedReason`; niedostępność całego katalogu pozostaje błędem
  przejściowym, który można bezpiecznie wznowić.

### Verification results

- `24 passed`: `test_v7_worker_runtime.py` oraz pełna regresja
  `test_semi_automatic_selection_job.py`.
- `33 passed`: API, repository i migracja półautomatu; jedno istniejące
  ostrzeżenie deprecacyjne Starlette.
- Ruff i Mypy runtime'u przeszły. Mypy handlera/domeny przeszło z
  `--ignore-missing-imports`, ponieważ konfiguracja pojedynczego pliku nie
  widzi stubów sąsiedniego pakietu API.
- Self-audyt wykrył brak schema `4` w `create_job` i brak trwałego checkpointu
  driftu; oba przypadki otrzymały regresje. Astra Medium wykryła dwukierunkową
  niespójność workflow oraz rozróżnienie usuniętego pliku i niedostępnego
  katalogu; poprawki przeszły testy, a końcowy review Astra ma wynik `approved`.

### Not completed

- Nie dostarczono mierzonego adaptera lokalizacji/OCR/jakości, ręcznej
  kalibracji, snapshotu holdoutu, writera ani aktywacji API. V7 nie tworzy
  katalogu `cut` i nadal nie nadaje się do testu end-to-end przez UI.

### Documentation updates

- D-410, `CURRENT_STATE.md`, plan wykonawczy V7 i `TEMP PLAN V7.md` opisują
  pion workerowy i niezmienioną bramkę wydania.

### Recommended next task

- Dostarczyć server-owned, kalibrowany adapter obserwacji V7 oraz jego pomiar na
  ręcznie opisanych danych; po nim zamrozić snapshot i powtórzyć odbiór T12.
