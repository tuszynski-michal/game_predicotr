# Audyt TASK-1182 — Zgodność oceny checkpointu i ONNX

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...6ee170d51a2786880014b7cee6584e9285df9ea9 oraz zmiany niezacommitowane, data 2026-11-11
Runda: 1
SHA pakietu: f007d551df950f1e8e2508460b213a9927f21d73295d334ec42b427225f98318
Otwarte P0: 0
Otwarte P1: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przejrzałem pakiet TASK-1182: nowy `CorrectionEvaluator` i dowód eksportu, kontekst `evaluation_precision`, podłączenie go w `torch_engine` oraz zmiany w `_train`, `_export` i `_correction_consistency`. Przeczytałem też potrzebny kod: `NeuralGridEngine`, `train`/`_result`, `selection_key`, `decide_game` i `parity_verdict`. Logika jest spójna z częścią T1 planu. Diagnoza w raporcie jest wewnętrznie spójna: TF32 w cuDNN przesuwa jedną planszę ponad próg NME 0,02, co daje 1/13 w metryce zdjęć. Kontrola eksportu porównuje całe A, surowe wyjścia na rzeczywistych wejściach ONNX, decyzje dyskretne, preferencję checkpointu i wynik warunku non-regression per gra, zgodnie z `decide_game`. Główny problem to testy. Żaden test nie dowodzi, że ocena w treningu naprawdę działa z wyłączonym TF32. Nie ma też testu podłączenia kontroli w świeżej ścieżce eksportu. Gdyby któreś z tych podłączeń zniknęło, żaden test by tego nie wykrył.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/worker/src/game_predictor_worker/images/grid_rescue_evaluation.py:50` — Właściwa naprawa przyczyny to opakowanie obu wywołań grafu w `torch_engine` w `with evaluation_precision()` (linie 51 i 58). Ta zmiana nie ma testu. Test `services/worker/tests/test_grid_correction_consistency.py:94` sprawdza tylko sam context manager. Wszystkie testy `CorrectionEvaluator` podmieniają `torch_engine` (`test_grid_correction_consistency.py:70`), a `test_grid_training_child.py` nie zawiera ścieżki korekt. Usunięcie bloku `with` przywróciłoby historyczną rozbieżność CUDA/TF32 przy zielonych testach. To łamie regułę `AGENTS.md:154` („Naprawa regresji dostaje test odtwarzający przypadek”) i wymóg planu „Test przyczyny”. Proponowana poprawka: test, który podmienia `ScreenExport` i `BoardExport` w `grid_rescue_evaluation` na stuby zapisujące `torch.backends.cudnn.allow_tf32`, `torch.backends.cuda.matmul.allow_tf32` i `torch.is_autocast_enabled(...)` w chwili wywołania. Test ustawia flagi na `True`, wywołuje `torch_engine(...).screen_runner` i `board_runner` na CPU, sprawdza `False` w trakcie wywołania i przywrócenie flag po nim. Test działa na CPU, bez treningu.
- [P1-2] `services/worker/src/game_predictor_worker/images/grid_training_child.py:779` — Świeża ścieżka eksportu nie ma testu. Nie jest sprawdzone, że `bundle["evaluationConsistency"]` trafia do publikowanego `bundle.json`. Nie jest sprawdzone, że `CorrectionConsistencyError` przy stagingu kończy się błędem `GRID_TRAINING_EVALUATION_INCONSISTENT` bez katalogu `destination`, ze sprzątniętym stagingiem i zapisanym `evaluation-consistency-failed.json`. Nie jest też sprawdzony warunek podłączenia w `_train` (`grid_training_child.py:593`: `corrections and not screen_corrections`). Test `test_grid_correction_consistency.py:228` wywołuje tylko pomocnicze `_correction_consistency`. Test `:249` pokrywa wyłącznie odzysk istniejącego katalogu. Kryterium „Rozbieżność blokuje eksport z trwałym raportem” (`ai_docs/requirements/VISION_LAB.md:9`) i zaznaczone kryterium akceptacji 1 opierają się więc na kodzie, nie na teście. Proponowana poprawka: test `_export` z podmienionymi `export_graphs`, `raw_parity`, `parity_inputs` i `bundle_document` w dwóch wariantach. Przy sukcesie stub ewaluatora zwraca proof, a test sprawdza klucz w opublikowanym `bundle.json`. Przy porażce stub rzuca wyjątek, a test sprawdza brak `destination`, brak `.export-*` w `run_dir` i treść raportu. Dodatkowo potrzebna jest asercja, że `_train` przekazuje `correction_evaluator` dla `grid-corrections-v1`, a `None` dla `screen-grid-corrections-v1` (przez podmianę `_export`).

### P2

- [P2-1] `services/worker/src/game_predictor_worker/images/grid_training_child.py:877` — Baza do warunku non-regression jest ładowana przez `onnx_engine(...)` bez `expected_bundle_sha256`. Spec bazy (`grid_training_handler.py:568-573`) przypina tylko `weights.pt` i `preset.json` z `training-base`, nie `bundle.json` ani grafy ONNX. Proof zapisuje `baselineMetrics` (`grid_correction_consistency.py:264`), ale nie tożsamość bazy, a `proof_binding` jej nie obejmuje. Ryzyko jest niskie, bo katalogi wersji są niezmienne, ale dokumentacja mówi o „pinned ONNX base”. Proponowana poprawka: zapisać w `body` sumy `screen.onnx`, `board.onnx` i `bundle.json` bazy i włączyć je do `proof_binding`, albo jawnie przyjąć ryzyko w Outcome.
- [P2-2] `services/worker/src/game_predictor_worker/images/grid_correction_consistency.py:175` — `verify_export` wykonuje trzy pełne przebiegi A (referencja CUDA, ONNX z dodatkowym torch na każdym wejściu ONNX, baza). Działa to wewnątrz budżetu watchdoga po zakończonym treningu, a przy odzysku wykonuje się ponownie. Zmierzono około 17,5 s dla jednej gry i 13 zdjęć. Przy wspólnych przebiegach wielu gier kontrola może przekroczyć `RUN_BUDGET_EXHAUSTED` już po treningu. Proponowana poprawka: odnotować koszt per gra w Outcome albo zarezerwować czas eksportu w budżecie, na przykład w TASK-1184.
- [P2-3] `ai_docs/tasks/1183-grid-learning-reference-split.md:3` — Plik TASK-1183 ma `status: in_progress`, a `ai_docs/process/CURRENT_STATE.md:100` pokazuje go jako `(todo)`. Proponowana poprawka: ujednolicić status przed commitem T1.
- [P2-4] `ai_docs/requirements/VISION_LAB.md:4` — Do wymagań i architektury (`ai_docs/architecture/VISION_LAB.md:4`) dodano sekcje TASK-1182, ale `last_updated` zostało na 2026-11-09. `CURRENT_STATE.md:4` ma nadal 2026-11-10. Proponowana poprawka: ustawić 2026-11-11, zgodnie z tym, czego wymaga `docs:check`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| T1: odtworzenie checkpointu 600 i ONNX na 13 zdjęciach A, porównanie wejść, detekcji, punktów, fitu, matchingu i metryk | niezweryfikowane (raport spójny, przebiegów nie powtarzano) | `ai_docs/quality/GRID_EVALUATION_CONSISTENCY_20261111.md:14`, `:25`; `ai_docs/quality/GRID_EVALUATION_CONSISTENCY_20261111.json` (`historicalReproduction`, `changedSource`) |
| T1: wyjaśnienie .8376068376 vs .9145299145 bez zakładania przyczyny | spełnione (dokumentacyjnie) | `GRID_EVALUATION_CONSISTENCY_20261111.md:9`; JSON `precisionExperiment` (TF32 on/off na tych samych wejściach) |
| T1: wspólne przygotowanie i ocena, osobne backendy PyTorch i ONNX | spełnione | `services/worker/src/game_predictor_worker/images/grid_training_data.py:590`; `grid_correction_consistency.py:175`, `:187` |
| T1: kontrola eksportu na całym A, różnica w matchingu, wyborze checkpointu lub werdykcie blokuje | spełnione w kodzie, niepełne w testach | `grid_correction_consistency.py:88`, `:106`, `:242`; `grid_training_child.py:779`, `:856`; brak testu świeżej ścieżki (P1-2) |
| T1: test przyczyny bez nowego treningu | niespełnione | Test samego kontekstu `test_grid_correction_consistency.py:94`; brak testu podłączenia w `grid_rescue_evaluation.py:50` (P1-1) |
| T1: raport odróżnia odtworzenie historyczne od nowych zabezpieczeń | spełnione | `GRID_EVALUATION_CONSISTENCY_20261111.md:14`, `:65`, `:118` |
| Ochrona historycznych wersji, danych i niezależnych kontroli | spełnione | Odzysk bez przepisywania `test_grid_correction_consistency.py:249`; REG poza kontrolą `test_grid_correction_consistency.py:201`; brak migracji i zmian API w diffie |
| Opus terminal PASS, brak otwartych P0/P1, docs/map i właściwe testy | niespełnione | Otwarte P1-1 i P1-2; `docs:check` i `code-map:check` niedeklarowane w Outcome taska |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P1-2, P2-1, P2-2, P2-3, P2-4.

## Proponowane testy

- `services/worker/tests/test_grid_correction_consistency.py`: test `torch_engine` ze stubami `ScreenExport` i `BoardExport` zapisującymi flagi TF32 i autocast w trakcie wywołania oraz ich przywrócenie (P1-1). Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_correction_consistency.py -k precision` z jawnym timeoutem ≤ 120 s.
- `services/worker/tests/test_grid_correction_consistency.py` lub `test_grid_training_child.py`: świeży `_export` z `correction_evaluator` w dwóch wariantach. Przy sukcesie proof trafia do `bundle.json`. Przy porażce nie ma `destination` ani stagingu, a `evaluation-consistency-failed.json` istnieje (P1-2).
- Test `_train` z podmienionym `_export`: `correction_evaluator` jest ustawiony dla `grid-corrections-v1` i `None` dla `screen-grid-corrections-v1` (P1-2).
- Opcjonalnie: odzysk z naruszonym `evaluationConsistency.sha256` (proof z `passed=True`, ale zmienionym ciałem) daje `GRID_TRAINING_EVALUATION_PROOF_REQUIRED`.

## Zakres przeglądu i ograniczenia

Przeczytałem cały zamrożony pakiet (task, plan, diff i nowe pliki). W kodzie przeczytałem: `grid_training_child.py` (`_train`, `_export`, `_correction_consistency`, `_verify_recovered`), `grid_rescue_evaluation.py`, `geometry_core/inference.py` (`BoardDetection`, `NeuralGridEngine`, `onnx_engine`), `training_core/grid_training.py` (pętla oceny, historia, `_result`, `parity_verdict`), `training_core/grid_correction_metrics.py` (`checkpoint_metrics`, `aggregate_checkpoint_metrics`, klucze selekcji), `game_predictor_api/domain/grid_correction_evaluation.py` (`decide_game`, `EPSILON`, `require_checkpoint_selection`) oraz fragmenty `AGENTS.md`. Nie uruchamiałem testów, lintu, typecheck, `docs:check`, `code-map:check` ani diagnozy CUDA/ONNX. Wyniki „23 PASS / 9 PASS / 6 PASS” i liczby z raportu jakości przyjmuję jako deklarację wykonawcy. Nie mogłem statycznie sprawdzić, czy wartości bazy z `measure_role` w pipeline oceny są numerycznie tożsame z `CorrectionEvaluator.measure(baseline)`. Nie mogłem też sprawdzić rozmiaru proof dla wielu gier wobec limitów odczytu bundle ani lokalnych artefaktów `artifacts/t1-diagnosis/`.