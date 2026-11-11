# Audyt TASK-1182 — Zgodność oceny checkpointu i ONNX

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...6ee170d51a2786880014b7cee6584e9285df9ea9 oraz zmiany niezacommitowane, data 2026-11-11
Runda: 2
SHA pakietu: 5b73993a533f42a2719db2ef62696678a0e4297201a63b412076d9c7e5a91f4a
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

W rundzie 2 sprawdziłem, czy poprawki usunęły dwa znaleziska P1 i cztery P2 z rundy 1. Sprawdziłem je w zamrożonym pakiecie oraz w kodzie: `grid_training_child.py`, `grid_rescue_evaluation.py`, `geometry_core/inference.py::onnx_engine`, `grid_training_data.py` i nowym pliku testów `test_grid_correction_consistency_wiring.py`.

Oba P1 są zamknięte:

- Nowy test wywołuje rzeczywiste runnery `torch_engine` dla obu grafów. Sprawdza, że TF32 i autocast są wyłączone w chwili wywołania grafu i że ustawienia wracają po sukcesie oraz po wyjątku.
- Świeży `_export` ma test sukcesu i porażki. Osobny test sprawdza, że `_train` kieruje ewaluator korekt wyłącznie do eksportu grid-only.

P2-1, P2-3 i P2-4 również usunięto. Zostają tylko ryzyka P2: budżet czasu kontroli dla wielu gier, którego wykonawca nie naprawiał i przyjął jako ryzyko, oraz trzy nowe drobne uwagi. Żadna z nich nie blokuje commitu.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-2] `services/worker/src/game_predictor_worker/images/grid_correction_consistency.py:176` — Znalezisko z rundy 1, nadal otwarte jako ryzyko przyjęte w Outcome taska. `verify_export` wykonuje trzy pełne przebiegi A. Pierwszy to referencja torch. Drugi to ONNX z dodatkowym wywołaniem torch na każdym wejściu. Trzeci to baza, od linii 244. Przy odzysku kontrola uruchamia się ponownie, w `grid_training_child.py:669`. Zmierzono około 17,5 s dla jednej gry; kosztu dla wielu gier nie zmierzono. Rezerwę czasu przekazano do TASK-1184. Akceptuję ryzyko pod warunkiem odbioru tej rezerwy w T3.
- [P2-5] `services/worker/src/game_predictor_worker/images/grid_training_child.py:872` — `baseline_identity["bundleSha256"]` jest liczony z tych samych bajtów, które trafiają do `onnx_engine`. Kontrola w `geometry_core/inference.py:326` jest więc tautologiczna. Realnie chronią tylko dwa mechanizmy: sprawdzenie SHA grafów względem `files` bazy (`inference.py:347`) oraz zapis tożsamości w proof i w `proof_binding`. `bundle.json` bazy nie jest powiązany z przypiętym `spec["base"]["weightsSha256"]` (`grid_training_handler.py:571`). Skutek: dryf bazy przed pierwszym eksportem nie zostałby wykryty. Odzysk wykrywa dryf poprawnie. Ryzyko jest niskie, bo zarządzane katalogi wersji są niezmienne. Proponowana poprawka: porównać `base_bundle["provenance"]["weightsSha256"]` (lub `files["weights.pt"]`) z `spec["base"]["weightsSha256"]` i odrzucić rozbieżność. Alternatywnie można odnotować ryzyko.
- [P2-6] `services/worker/src/game_predictor_worker/images/grid_training_data.py:498` — `board_evaluator` (linie 498–511) i niekorekcyjna gałąź `photo_evaluator` (linie 536–561) nadal wywołują grafy bez `evaluation_precision`. Dla presetów innych niż korekty ocena CUDA dalej zależy od procesowego TF32. Mieści się to w zakresie T1, bo sekcja wymagań dotyczy korekt. Zdanie z `ai_docs/requirements/VISION_LAB.md:11` („Ocena PyTorch używa jawnego FP32…”) można jednak odczytać szerzej. Proponowana poprawka: doprecyzować w wymaganiach, że reguła dotyczy oceny korekt. Opcjonalnie można owinąć te ewaluatory w osobnym tasku.
- [P2-7] `ai_docs/tasks/1182-grid-evaluation-consistency.md:99` — Wiersz koordynatora podaje „13 testów consistency PASS”. W pakiecie `test_grid_correction_consistency.py` ma 10 testów bez parametryzacji oraz test parametryzowany pięcioma wariantami (linia 258), czyli 15 przypadków. Plik wiring ma 8 przypadków. Liczba nie zgadza się z żadnym z tych zestawów ani z deklarowanymi „33 PASS”. Skutek: zapis weryfikacji jest niejednoznaczny. Proponowana poprawka: przed commitem podać dokładną komendę, zbiór plików i liczbę testów.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| T1: odtworzenie checkpointu 600 i ONNX na 13 zdjęciach A oraz porównanie wejść, detekcji, punktów, fitu, matchingu i metryk | niezweryfikowane: raport jest spójny, przebiegów nie powtarzano | `ai_docs/quality/GRID_EVALUATION_CONSISTENCY_20261111.md` (sekcja „Dowód historyczny”); JSON `historicalReproduction`, `changedSource`, `precisionExperiment` |
| T1: wyjaśnienie wyników .8376068376 i .9145299145 bez zakładania przyczyny | spełnione (w dokumentacji) | JSON `precisionExperiment`: TF32 on/off na tych samych `inputSha256s.screen` |
| T1: wspólne przygotowanie i ocena, osobne backendy PyTorch i ONNX | spełnione | `grid_training_data.py:590`; `grid_correction_consistency.py:176`; `grid_training_child.py:520` |
| T1: kontrola eksportu na całym A; różnica w matchingu, wyborze checkpointu lub werdykcie blokuje eksport | spełnione | `grid_training_child.py:779`, `:856`, `:893`; test `test_grid_correction_consistency_wiring.py:69` (sukces i porażka bez publikacji i bez stagingu), `test_grid_correction_consistency.py:127`, `:169` |
| T1: test przyczyny bez nowego treningu | spełnione | `grid_rescue_evaluation.py:51`, `:58`; test `test_grid_correction_consistency_wiring.py:20` (rzeczywiste runnery, obie głowy, sukces i wyjątek) |
| Podłączenie ewaluatora tylko dla grid-only | spełnione | `grid_training_child.py:593`; test `test_grid_correction_consistency_wiring.py:163` |
| T1: raport odróżnia odtworzenie historyczne od nowych zabezpieczeń | spełnione | `GRID_EVALUATION_CONSISTENCY_20261111.md` (sekcje „Dowód historyczny” oraz „Zmiana i jej granice”) |
| Ochrona historycznych wersji, danych i niezależnych kontroli | spełnione | Odzysk bez przepisywania: `test_grid_correction_consistency.py:258`; tylko VALIDATION: `:201`; tożsamość bazy w `proof_binding`; brak migracji i zmian API |
| Opus terminal PASS, brak otwartych P0/P1, docs/map i właściwe testy | spełnione w zakresie tego audytu; docs/map i testy niezweryfikowane statycznie | Brak otwartych P0/P1; `CODE_MAP.md` i `CODE_MAP_SYMBOLS.md` zaktualizowane; deklaracja koordynatora `1182-...md:99` (zob. P2-7) |

## Listy zamknięte i otwarte

Zamknięte: P1-1 (`test_grid_correction_consistency_wiring.py:20` testuje rzeczywiste `torch_engine.screen_runner` i `board_runner` z flagami w chwili wywołania), P1-2 (`test_grid_correction_consistency_wiring.py:69` i `:163` testują świeży eksport z proof albo trwałym raportem bez publikacji oraz routing w `_train`), P2-1 (`grid_training_child.py:872-890`: tożsamość bazy w proof, `proof_binding` w `grid_correction_consistency.py` obejmuje `baselineIdentity`, test wariantu „baseline”), P2-3 (`CURRENT_STATE.md:100` ma `in_progress`), P2-4 (`last_updated: 2026-11-11` w obu plikach VISION_LAB i w `CURRENT_STATE.md:4`).

Otwarte: P2-2, P2-5, P2-6, P2-7.

## Proponowane testy

- `services/worker/tests/test_grid_correction_consistency_wiring.py`: wariant, w którym `bundle.json` bazy ma `weightsSha256` inny niż `spec["base"]["weightsSha256"]`. Jeśli przyjąć poprawkę P2-5, oczekiwany jest błąd przed `verify_export`. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_correction_consistency_wiring.py` z jawnym timeoutem ≤ 120 s.
- `services/worker/tests/test_grid_correction_consistency.py`: odzysk z prawidłowym proof, w którym świeży `verify_export` rzuca `CorrectionConsistencyError`. Oczekiwane: `GRID_TRAINING_EVALUATION_INCONSISTENT`, zapisany `evaluation-consistency-failed.json` i niezmieniony `bundle.json`.
- W TASK-1184: pomiar czasu `verify_export` dla wielu gier wobec budżetu watchdoga (P2-2).

## Zakres przeglądu i ograniczenia

Przeczytałem cały zamrożony pakiet: task, plan, diff, nowe pliki oraz raporty i receipty z rundy 1. W kodzie przeczytałem:

- `grid_training_child.py`, linie 560–915 (`_train`: wywołanie `_export`; `_export`, `_correction_consistency`), oraz importy;
- `grid_rescue_evaluation.py::torch_engine`;
- `geometry_core/inference.py::onnx_engine`;
- `grid_training_data.py`, linie 480–594 (pozostałe ewaluatory i `correction_evaluator`);
- fragment `grid_training_handler.py` ze specyfikacją bazy;
- nagłówki testów obu plików consistency.

Nie uruchamiałem testów, lintu, typecheck, `docs:check`, `code-map:check` ani diagnozy CUDA/ONNX. Wyniki „33 PASS”, mypy i ruff oraz liczby w raporcie jakości przyjmuję jako deklarację wykonawcy i koordynatora. Nie mogłem statycznie potwierdzić, że test świeżego eksportu przechodzi z rzeczywistym `bundle_document` przy `preset_payload={}`, ani że `torch.is_autocast_enabled("cuda")` działa w zainstalowanej wersji Torch. Nie sprawdzałem lokalnych artefaktów `artifacts/t1-diagnosis/`.