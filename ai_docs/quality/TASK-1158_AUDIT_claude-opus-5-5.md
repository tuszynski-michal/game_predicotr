Werdykt: PASS

# Audyt TASK-1158 — kompletność i rozdzielona kalibracja (focused R2)

Audytor: claude-opus-5-5/high
Wykonawca: gpt-6-astra/high
Zakres: baza `f78c5b5a1a6dcbc1c0d280a0f4d2204417e5d9a3` (v1.7.562) plus niezacommitowana delta R1→R2 TASK-1158 z pakietu `artifacts/audits/task1158-r2` (części 01–05), data 2026-11-04
Runda: 2

To był wyłącznie przegląd statyczny (Read/Glob/Grep). Nie zmieniałem plików, nie uruchamiałem testów, shella, usług ani bazy. Nie otwierałem prywatnego pliku stagingowego operatora, zdjęć, modeli ani `.env`.

## Streszczenie

Sprawdziłem trzy rzeczy: czy usterka P1 koordynatora (dawne R1 P2-1) jest zamknięta, czy zamknięto R1 P2-2 i P2-5, oraz jak zmiana wpływa na wskazanych w pakiecie wywołujących.

Zbiór celów B/REG jest teraz związany z niezależnym źródłem prawdy:
- **API:** raport → wiersz `GridTrainingCohortModel` w stanie `frozen` → SHA manifestu → `GridCohortSnapshot`.
- **Worker:** `_snapshot` z nagłówkiem z magazynu.
- **Porównanie:** dokładny zbiór krotek (sourceId, pikselowy SHA, slot, GT-SHA), sprawdzany przed deduplikacją kopii.

Sidecar z przeliczonymi wewnętrznie hashami po usunięciu, podmianie albo zduplikowaniu celu jest odrzucany. Test PG i test fazowy workera faktycznie odtwarzają ten regres. Routing ewaluatora i runtime liczy teraz jedna wspólna formuła, a dodatnia ścieżka v4 pozostaje osiągalna. Nie znalazłem otwartych P0/P1.

## Znaleziska

### P0

Brak.

### P1

Brak. Usterka P1 koordynatora jest zamknięta (dowody w sekcji „Listy zamknięte i otwarte”).

### P2

- [P2-3] `services/api/src/game_predictor_api/storage/neural_grid_operation_qualification.py:192`
  - **Problem:** sidecar i sweep są przeliczane synchronicznie pod blokadą admisji. Doszło jeszcze ponowne odczytanie snapshotu kohorty przez `load_frozen_assessment`.
  - **Skutek:** ryzyko przekroczenia limitu czasu przy dużym B.
  - **Status:** ryzyko zaakceptowane przez koordynatora, bez nowego cache ani benchmarku. Pozostaje otwarte.
- [P2-4] `services/worker/src/game_predictor_worker/images/full_board_calibration_observations.py:147`
  - **Problem:** minima liczą źródła po deduplikacji, a nie niezależne komponenty sesji lub pochodzenia.
  - **Status:** ograniczenie zaakceptowane i jawnie opisane. Pozostaje otwarte.
- [P2-6] (nowe, nieblokujące) `services/worker/tests/test_full_board_calibration_integration.py:432`
  - **Problem:** złożony test routingu buduje `observation` ręcznie z atrybutów `RescueAssessmentEngine` (`routed.routing`, `routed.path`). Nie przechodzi przez `observation_sink` w `run_with_rescue` (`grid_rescue_runtime.py:296`).
  - **Uwagi:** oba źródła statycznie czytają to samo wyrażenie `proof["selection"]["pathProofs"][path].get("routing")` (`grid_rescue_assessment.py:17-19`), więc ryzyko jest niskie. Ewentualny rozjazd i tak kończy się brakiem dowodu, czyli automat zostaje zablokowany.
  - **Poprawka:** opcjonalnie jedna asercja, że `observation_sink` z `run_with_rescue` (przy zamockowanym runnerze, na tym samym bundlu) daje ten sam `calibration_routing_sha` co `run.routing_sha`.

## Pokrycie kryteriów akceptacji (tylko zakres R2)

| Kryterium | Status | Dowód |
|---|---|---|
| P1 koordynatora: niezależne źródło prawdy w DB/raporcie/kohorcie, dokładne członkostwo i liczby w workerze (prepare/resume/finish) i w API | spełnione | szczegóły w sekcji „Listy zamknięte i otwarte” |
| Odrzucenie przeliczonych pominięć i podmian, przy zachowanych celach partial i dodatniej ścieżce v4 | spełnione | `test_calibrated_acceptance_postgres.py:337` (6 fałszerstw B/REG z przeliczonym seal/result/profile/SHA, dopasowanie `FROZEN_TARGET_SET_CHANGED`); dodatni prewrite przez `execution(... calibrated_report=...)` z `automaticQualification.state == "qualified"`; partial: `GridAssessmentDataset._partial_assessment → True`, a fixture ma B/REG bez pełnych zdjęć (`fullPhotos: 0`) |
| Wymagany `sourceId` w niewydanym formacie, bez zgadywania | spełnione | `full_board_calibration.py` (`AssessedTarget.sourceId: UUID` bez wartości domyślnej); brak pól planu daje `None != …`, czyli `CALIBRATION_FROZEN_PLAN_CHANGED`; brak dekodera rozróżniającego wersje |
| P2-2: wspólna formuła routingu i dodatni profil runtime | spełnione (P2-6 jako drobna luka testu) | `full_board_completeness.py:23` (`calibration_routing_sha`); `full_board_calibration_run.py` (`__init__`) i `full_board_runtime_evidence.py:61` wołają tę samą funkcję; test `test_full_board_calibration_integration.py:439` daje dodatni dowód i `calibrated_result_blockers == ()`, a zmiana ścieżki daje `{}` |
| P2-5: zimne VALIDATE i dryf | spełnione | `test_calibrated_acceptance_postgres.py:400`: subprocess, `find_neural_operation_pin` dla IMPORT i VALIDATE, równość SHA pinu, `acceptance_for_operation_pin == v4`, `recheck_operation_pin` pusty, a po unieważnieniu raportu blokery niepuste; `job_repository.py:65-144` bez zmian w kontrakcie VALIDATE |
| Ścisły dispatch v4, tożsamość rastra i prób, zimne wywołania IMPORT/VALIDATE i aktualności | spełnione (przeczytane statycznie) | `grid_reinference_handler.py:650-684` (tożsamość cache obejmuje pin v3, raster i box); `grid_rescue_runtime.py:827-835` (`GRID_RESCUE_RASTER_CHANGED`); `production_workflow.py:720-747`; `neural_page_geometry_preflight.py` (`input_raster` tylko dla v3) |

## Listy zamknięte i otwarte

### Zamknięte

**Usterka P1 koordynatora (dawne R1 P2-1).** Dowody:
- `full_board_calibration_evidence.py:23`: pin z `report["cohorts"]` dokładnie raz, wiersz DB `frozen`, zgodny `manifest_sha256`, a snapshot weryfikuje bajty i tożsamość gry/kohorty. Sidecar nie wskazuje źródła prawdy.
- `full_board_assessment_reference.py:27`: projekcja przez istniejące `GridBoardDataset`/`GridAssessmentDataset`, bez równoległego czytnika GT.
- `full_board_assessment_reference.py:81` (`require_targets`): dokładny posortowany zbiór krotek z gameId, odrzucenie duplikatów (source, slot).
- `full_board_assessment_reference.py:98` (`require_plan`): wiąże manifest kohorty, cohortId, referencje A/B/REG, liczby celów i źródeł, `roleProofSha256` i `plannedComparisons`.
- Strona API: `full_board_calibration_evidence.py:97-103`; wyjątki snapshotu (`GridCohortDatasetError` dziedziczy po `ValueError`) są łapane w `_automatic_evidence` jako stan „unqualified”.
- Strona workera:
  - `full_board_calibration_run.py:149` (A/REG z detali),
  - `full_board_calibration_run.py:220` (świeże B),
  - `full_board_calibration_run.py:232-236` (B z punktu kontrolnego po wznowieniu),
  - `full_board_calibration_run.py:254` (finish).
- `grid_model_evaluation_handler.py:467`: przed zbudowaniem raportu ponownie ładuje kohortę przez `_snapshot` (status `frozen`, SHA, kwalifikowalność) także przy pomiarach z punktu kontrolnego.
- Test fazowy `test_full_board_calibration_integration.py:591`: usunięte, podmienione i zduplikowane cele B, A i REG są odrzucane, bez nowych wywołań silnika.

**R1 P2-2.** Jedna funkcja `calibration_routing_sha`; dodatni złożony test na faktycznie wybranej ścieżce A (`board_only`).

**R1 P2-5.** Dodatnie zimne IMPORT i VALIDATE oraz dryf w nowym procesie.

### Otwarte

- P2-3 i P2-4: zaakceptowane ograniczenia.
- P2-6: nowe, nieblokujące.

## Proponowane testy

- `services/worker/tests/test_full_board_calibration_integration.py`: przejście `run_with_rescue` z zamockowanym runnerem i porównanie `calibration_routing_sha(observation_sink)` z `run.routing_sha` (P2-6).
- Opcjonalnie w tym samym pliku: A z częściowym źródłem w trybie grid-only. Ma potwierdzić, że detal `VALIDATION` zawiera wszystkie cele `GridBoardDataset(VALIDATION)` i że `require_targets("A")` nie blokuje dodatniej ścieżki (zob. ograniczenia).
- Uruchamianie: `.\.venv\Scripts\python.exe -m pytest <plik> -k <nazwa>`; PG z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`.

## Zakres przeglądu i ograniczenia

**Przeczytane w całości:**
- `INDEX.md` i części 01–05: raport R1, decyzja koordynatora, task, weryfikacja R2;
- nowy `full_board_assessment_reference.py`;
- delty R1→R2 domeny, obserwacji, przebiegu kalibracji, kompletności i handlera ewaluatora;
- kompletne pliki `full_board_calibration_evidence.py`, `neural_grid_operation_qualification.py`, `full_board_runtime_evidence.py` i `test_calibrated_acceptance_postgres.py`;
- wskazane funkcje z `job_repository`, `grid_reinference_handler`, `grid_rescue_runtime`, `neural_page_geometry_preflight`, `production_workflow`, `test_v3_engine_acceptance_postgres.execution` i `grid_cohort_dataset`;
- logi wykonania z części 03–05;
- `AUDIT_REPORT_TEMPLATE.md`.

**Celowane fragmenty poza pakietem:**
- grep `full_board_calibration_run.py` (budowa `self.rows`);
- grep `grid_rescue_assessment.py` (źródło `routing`/`path`);
- grep definicji `GridCohortDatasetError`;
- `grid_model_evaluation_handler.py:218-252` (`_snapshot`).

**Czego nie dało się sprawdzić statycznie:**
- Nie zweryfikowałem, że produkcyjny detal `VALIDATION` handlera zawiera cele wszystkich źródeł A z `GridBoardDataset(VALIDATION)`, gdy A ma źródła częściowe w trybie grid-only. Przy rozjeździe automat zostałby zablokowany, a nie fałszywie przepuszczony.
- Wyniki testów, ruff, mypy, formatu i mapy to deklaracje wykonawcy (14 unit + 1 routing + 1 PG). Nie powtarzałem ich.
- Dodatni scenariusz PG i złożony są syntetyczne. Dowodzą kontraktu integracyjnego, a nie empirycznej jakości sieci ani kwalifikacji u operatora.
