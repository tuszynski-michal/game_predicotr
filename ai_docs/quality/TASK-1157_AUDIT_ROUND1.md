# Audyt TASK-1157: detektor w procesie korekt i dowodowy ratunek

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: baza 6325a0579c6f2cd5aed66b4cf894c09682be4ab1 (v1.7.561) plus niezacommitowane zmiany z pakietu `artifacts/audits/task1157-r1-final` (manifest c2b0b89c…), data 2026-11-04
Runda: 1

To był wyłącznie przegląd statyczny (Read/Glob/Grep). Nie zmieniałem żadnych plików, nie uruchamiałem testów, usług, bazy ani sieci.

## Streszczenie

Sprawdziłem kod pod kątem polityki v3 i trybu screen+grid, podziału full TRAIN/A i partial REG, wyboru checkpointu od zdjęcia (photo-first), łańcucha recipe → exposure → A → ONNX → inspector → pin v2 → runtime 1+1, migracji 0180 i kontraktu API. Logika gate'ów i pinów jest spójna i zamyka się bezpiecznie (fail-closed). Stare polityki, raporty v3, pin v1 i funkcje SQL v3 zachowują swoją interpretację. Nie znalazłem P0 ani P1. Główne ryzyka to niezawodność magazynu prób ratunku przy przerwanym zapisie lub kopiach źródła oraz brak testu integracyjnego zgodności hashy etykiet.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/images/grid_rescue_runtime.py:43` — `_create` otwiera plik w trybie `xb` i pisze bezpośrednio do pliku docelowego, bez zapisu do pliku tymczasowego i atomowej zamiany.
  - **Skutek:** awaria między utworzeniem pliku a `fsync` zostawia pusty lub ucięty `*.reserved.json`, `*.result.json` albo `baseline.json`. Przy każdym restarcie `_read` (linia 28) rzuca wtedy `JSONDecodeError`. Budżet nie jest odnawiany, więc kryterium jest dotrzymane. Źródło lub cała operacja zostaje jednak trwale zablokowana błędem zamiast przejść do ręcznej korekty i stanu `consumed_without_result`.
  - **Poprawka:** zapis do pliku tymczasowego, potem `os.link` / no-replace rename. Alternatywnie: nieczytelną rezerwację traktować jako zużytą próbę bez wyniku.
- [P2-2] `services/worker/src/game_predictor_worker/images/grid_rescue_runtime.py:168-177` razem z `grid_reinference_handler.py:716-717` — katalog prób jest kluczowany tylko `source_sha`, a tożsamość magazynu zawiera `positions`.
  - **Skutek:** dwa wystąpienia tego samego pliku w jednej operacji (kopie lub aliasy) z różnym zakresem plansz dają `GRID_RESCUE_CHECKPOINT_INVALID`, czyli błąd zadania zamiast ręcznej korekty.
  - **Poprawka:** przy niezgodnej tożsamości zwracać baseline z powodem `GRID_RESCUE_SLOT_BINDING_REQUIRED` (budżet pozostaje zużyty) albo dodać test, który pokazuje, że taki przypadek nie występuje.
- [P2-3] `services/api/src/game_predictor_api/storage/neural_grid_operation_qualification.py:89-95` — `inspect_rescue` wykonuje się synchronicznie przy tworzeniu pinu operacji, w otwartej sesji: `onnx.load`, indeksowanie zbiorów VALIDATION/TRAIN wszystkich kohort. Kod powodu jest odrzucany (`rescue, _ =`).
  - **Skutek:** dłuższe trzymanie transakcji i blokad przy admisji. Operator nie widzi też, dlaczego ratunek nie został przypięty.
  - **Poprawka:** zapisać kod powodu w pinie lub widoku (np. `rescueReason`) i rozważyć wykonanie inspekcji przed transakcją. Ewentualnie zaakceptować ryzyko na T5.
- [P2-4] `services/api/src/game_predictor_api/application/grid_training_cohort_commands.py:286-300` oraz `storage/grid_correction_split.py:259-267,309` — nowa kontrola `expectedLabelsSha256` porównuje hash etykiet z `prepare_split` (`reader.capture(..., "grid-only")`, rola TRAIN) z hashem z `_capture` (`row.document["mode"]` = `screen+grid`, faktyczna rola).
  - **Brak testu:** test PG (`test_grid_correction_registry_postgres.py`, funkcja `split` w `_assert_command_lifecycle`) podstawia split bez `qualifiedLabelsSha256`, więc ta ścieżka nie jest nigdzie wykonywana razem z prawdziwym `prepare_split`.
  - **Skutek:** jeśli etykieta zależy od trybu lub roli, każde capture v3 skończy się `GRID_CORRECTION_LABELS_CHANGED`. Działa to bezpiecznie, ale blokuje drogę odzyskania opisaną w D-586.
  - **Poprawka:** test, w którym `prepare_split(policy=v3)` i `_capture` działają na tym samym czytniku.
- [P2-5] `services/worker/src/game_predictor_worker/images/grid_rescue_evaluation.py:307-311` — ewaluator checkpointu zwraca metryki wybranej ścieżki ratunku (`result["metrics"]`), a nie samego modelu bazowego.
  - **Skutek:** wybór checkpointu i `checkpointSelection` mierzą potok z ratunkiem. Między ewaluacjami może się zmieniać, czy ścieżka jest dopuszczona. Jest to spójne z `RescueAssessmentEngine` w ocenie REG, ale nie zostało jawnie opisane w D-586 („Checkpoint ocenia oryginały na A”).
  - **Poprawka:** udokumentować to w handoffie T4 albo zapisać w `checkpointSelection`, czy wynik pochodzi z baseline czy ze ścieżki.

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód |
|---|---|---|
| preview/start i zamrożona polityka mają spójne counts/used/reasons; full0 blokuje screen | spełnione | `grid_correction_split.py` (readiness, `SCREEN_FULL_PHOTOS_REQUIRED` przed solverem), `grid_correction_learning.py` (`detectorReadiness`, blokery), `grid_correction_progress.py` (v3 qualified/excluded) |
| Partial TRAIN/A nie są tłem; partial REG zachowane z jawnym celem oceny | spełnione | `role_boards` (`grid_correction_split.py:444`), `split_mapping` `detectorExcluded`/`assessmentPolicy`, `grid_training_cohort_evidence.py:455-562` (`used` dla REG), `GridAssessmentDataset`, `role_summary` REG min=0 dla v3 |
| Rzeczywisty optimizer CPU zmienia detektor screen; grid-only pozostaje zamrożony | spełnione (zgodnie z deklaracją testu) | `test_screen_correction_training.py:567-634` (zmiana wag, exposure, resume) |
| Checkpoint wybierany photo/board/error/earliest na A, równe wagi gier, bez REG, bez resetu przy resume | spełnione | `grid_training.py` (`EarlyStopping` PHOTO rule, restore state v1), `aggregate_checkpoint_metrics(photo_first)`, `TrainingExposure.restore` |
| Pełna ścieżka recipe → TRAIN exposure → A → export/parity → inspector → runtime | spełnione | `grid_training_child.py` `_export` (proof), `grid_rescue_policy.require_rescue_evidence`, `inspect_rescue`, pin v2, `run_with_rescue` |
| Screen-only, board-only i combined mają własne dowody; brak dowodu oznacza manual | spełnione | `COMPONENTS` / `_require_selection_choice`, `pathProofs`, `inspect_rescue` → `None` |
| Rezerwacje przed CPU egzekwują 1 redetect/źródło + 1 crop/pozycję po restarcie i lost response | spełnione (uwagi P2-1, P2-2) | `RescueAttemptStore.attempt`, katalog `operation_id/rescue/source_sha`, test subprocess `consumed_without_result` |
| Stare polityki, fingerprinty, snapshoty i funkcje SQL zachowują interpretację | spełnione | rozgałęzienia v3/v4, `operation-pin` v1, `source_recording_sql_v7` (nowe nazwy), wrapper v4 deleguje do v3, test migracji z porównaniem definicji |
| Backend/OpenAPI/klient/wrapper/testy żądań zgodne | spełnione statycznie | schematy pydantic, eksport `index.ts`, `grid-correction-learning-request.test.mjs`, test API roundtrip i 422 |
| Testy, lint, typy, dokumentacja, mapa i niezależny audyt rozliczone | niezweryfikowane przeze mnie | wyniki tylko z raportu wykonawcy; niczego nie uruchamiałem |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- `services/worker/tests/test_screen_rescue_contract.py`: pusty lub ucięty `redetect.reserved.json` i `crop-N.result.json` po symulowanej awarii. Oczekiwane: brak nowego wywołania i stan zużycia albo kontrolowany manual zamiast `JSONDecodeError`.
  - Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_screen_rescue_contract.py`
- Test handlera reinferencji z pinem v2: dwa wystąpienia tego samego `checksum_sha256` z różnym zakresem sekwencji w jednej operacji.
- Test integracyjny PG: prawdziwe `prepare_split(policy=v3)`, potem `_capture`. Pokazuje zgodność `qualifiedLabelsSha256` z etykietami capture (P2-4).
- Test `prepare_operation_pin` z celowo uszkodzonym dowodem ratunku. Sprawdza, że powstaje pin v1, operacja idzie bez ratunku, a kod powodu jest widoczny.
- Test preflight (`neural_page_geometry_preflight.py:546-562`) z pinem ratunku i ponownym przejściem przez `prior["rescueExecution"]`.

## Zakres przeglądu i ograniczenia

- **Przeczytane w całości:** INDEX oraz part-01 do part-08. Przeczytałem plan, D-586, weryfikację, wszystkie diffy API, domeny, storage i workera, nowe moduły ratunku, migrację 0180 i SQL v7.
- **Przeczytane celowanymi zakresami:** part-09 (testy treningu i kontraktu ratunku), part-10 (testy proof/runtime oraz początek wygenerowanego SQL), `grid_correction_split.py:256-269` i `neural_grid_operation_qualification.py:62-132` z repozytorium.
- **Nieprzeczytane w całości:** pozostała część part-09 do part-11 (pozostałe testy, emitowany SQL) oraz moduł `GridCohortEvidenceReader.capture`.
- **Nie uruchamiałem:** testów, lint, mypy, migracji ani usług. Wyniki wykonawcy (67 PASS itd.) przyjmuję tylko jako deklarację.
- **Czego nie da się ocenić:** rzeczywistej jakości detektora ani kalibracji. Zgodnie z zakresem T3 full0 blokuje trening na danych operatora, a T4/T5 są poza zakresem tego zadania.
