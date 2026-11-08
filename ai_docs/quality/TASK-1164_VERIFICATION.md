# TASK-1164 — weryfikacja wykonawcy

Data: 2026-11-08. Worktree: `D:\game_predicotr\worktrees\full-symbol-crops`.
Stan: implementacja gotowa do niezależnego audytu; bez commita i bez kwalifikacji
rzeczywistego modelu. Raport nie zastępuje audytu wymaganej drugiej rodziny modeli.

## Zakres i wynik

Nowy opt-in bundle/model v2 zachowuje 24 węzły/peak i 15 ocen komórek.
Domyślny legacy v1 nie poświadcza trenowanej visibility. Nadzór wymaga rzeczywistych,
zatwierdzonych, unikalnych etykiet TRAIN: minimum30 dodatnich i30 ujemnych
z minimum5 zdjęć każdej klasy per gra, przed augmentacją. Eksport wymaga także
ekspozycji obu klas na udanym kroku optymalizatora przed wybranym checkpointem.

Maski obejmują unknown, brak referencji, padding, nieosiągalność softargmax
i brak rzeczywistych pikseli. Syntetyczna zasłona może zmienić target po
transformacji, ale nie zwiększa liczników rzeczywistych etykiet. Zerowe maski
nie tworzą fikcyjnego nadzoru ani kroku AdamW w board-only.

Nowa oś inputEdgeClearance ma jeden próg wybrany wyłącznie z A danego wariantu;
nie zwiększa menu B ponad256. `geometry_proxy` nie spełnia minimum5 faktycznie
uciętych plansz z3 zdjęć. `verified_content` wymaga SHA i rewizji zgodnych
z niezależnym frozen readerem A; test obejmuje obcy hash, rewizję i brak readera.
Observer T1 nadal emituje proxy. Bez T2/T3 próg pozostaje unset/unqualified.

## Środowisko i ograniczenie komend

Wszystkie grupy wykonano w świeżych procesach, z limitem120s na komendę.
Interpreter `.venv-vision-lab` nie zawiera pytest; właściwy interpreter to
`D:\game_predicotr\.venv\Scripts\python.exe`, zawierający także Torch/ONNX/ORT.

```powershell
$env:PYTHONPATH = "$PWD/services/api/src;$PWD/services/worker/src;$PWD/services/test_support"
$taskPython = 'D:/game_predicotr/.venv/Scripts/python.exe'
# Przykład rzeczywistego ograniczenia czasu używanego dla poniższych komend:
& $taskPython -c 'import subprocess,sys; sys.exit(subprocess.run(["D:/game_predicotr/.venv/Scripts/python.exe","-m","pytest","services/api/tests/test_grid_visibility_calibration.py","-q","--basetemp=.tmp/t1-proof-api"],timeout=120).returncode)'
```

Katalogi `--basetemp` pod `.tmp` worktree są celowe: domyślny systemowy katalog
tymczasowy zwracał PermissionError. Dwa testy istniejącego mechanizmu hardlink
powtórzono z podniesionymi uprawnieniami i osobnymi katalogami; oba przeszły.
To ograniczenie środowiska wykonawcy, nie zmiana aplikacji.

## Wykonane kontrole

| Kontrola | Wynik |
| --- | --- |
| Nowy kontrakt/kalibracja/integracja: komenda poniżej | 25 PASS, 2 deselected; 13,75s |
| Rzeczywisty BoardNetwork→BoardExport→ONNX→ORT CPU | 1 PASS; 7,13s; 2 ostrzeżenia deprecacji eksportera TorchScript |
| Handler i wspólne szkolenie po korekcie legacy FakeChild | 30 PASS; 14,87s |
| Child training/export/recovery przed grupą handlera | 10 PASS |
| Wcześniejsza grupa core/legacy loss/calibration | 31 PASS; 5 błędów utworzenia temp; te same5 po poprawie katalogu: 5 PASS |
| Granice importów neutralnego training_core | 1 PASS; 6,32s |
| Istniejący pin + kalibracja API | 28 PASS; 2 wcześniejsze błędy Mock; 1 błąd hardlink, następnie PASS |
| Changed-raster rescue baseline/replenishment (hardlink retry) | 1 PASS; 0,63s |
| v1.4 unqualified proposal (hardlink retry) | 1 PASS; 1,92s |
| SDK test żądania | 2 PASS |
| Ruff format --check i ruff check: jawne24 pliki Python | PASS |
| mypy --follow-imports=silent: jawne20 zmienionych modułów src | PASS |
| OpenAPI export --check, SDK check:generated i typecheck | PASS |
| generate_code_map.py --check | PASS |
| npm.cmd run docs:check | PASS; 651 links, 587 entries/index rows, startup44478 B |

Wyniki grup mogą obejmować te same testy; nie sumuje się ich do sztucznej liczby
unikalnych przypadków. Po PASS nie powtarzano rzeczywistego eksportu ani pełnych grup.

```powershell
& $taskPython -m pytest services/api/tests/test_grid_visibility_calibration.py services/worker/tests/test_grid_visibility_contract.py services/worker/tests/test_full_board_calibration_integration.py -k 'not real_board_export and not changed_raster' -q --basetemp=.tmp/t1-proof-final
& $taskPython -m pytest services/worker/tests/test_grid_visibility_contract.py::test_real_board_export_onnx_preserves_24_15_and_cannot_recover_missing_row -q --basetemp=.tmp/t1-onnx-2
& $taskPython -m pytest services/worker/tests/test_grid_training_handler.py services/worker/tests/test_shared_grid_training.py -q --maxfail=2 --basetemp=.tmp/t1-handler-final
& $taskPython -m pytest services/worker/tests/test_vision_lab_training_core.py::test_import_boundaries_are_transitive_source_constraints -q --basetemp=.tmp/t1-boundary
& $taskPython scripts/export_admin_openapi.py --check
npm.cmd run check:generated --workspace @game-predictor/admin-api-client
npm.cmd run typecheck --workspace @game-predictor/admin-api-client
node --import tsx --test packages/admin-api-client/test/grid-model-evaluation-request.test.mjs
& $taskPython scripts/generate_code_map.py --check
```

Lint/typecheck dostały jawne listy24/20 plików, zgodne z Python paths w
`artifacts/TASK-1164_SCOPE.txt`; raport nie wymaga szerokiego lint całego repo.
Realny eksport korzysta z produkcyjnego `BoardNetwork`, sprawdza kształty24/15,
parity poniżej1e-4 oraz granice softargmax dla rastra z brakującym rzędem.
Nie jest to TinyNetwork ani wynik kwalifikacji na zdjęciach operatora.

## Znany błąd niezwiązany z T1

Dwa warianty `test_exact_repository_lookup_has_no_ten_thousand_history_window`
w `services/api/tests/test_neural_grid_operation_pin.py` nie przechodzą:
niezmieniony `storage/job_repository.py` otrzymuje Mock z `.mappings().all()`
i wywołuje `len(Mock)`. Odtworzono oba błędy także w pełnej izolowanej kopii
drzewa T0/v1.7.572: `artifacts/task1163-index-8ic0jtio`. CWD oraz PYTHONPATH
wskazywały wyłącznie tę kopię API/worker; wydruk `__file__` modułów
`domain/neural_grid_operation_pin.py` i `storage/job_repository.py` potwierdził
import ze shadow, bez kodu T1. Wynik: 2 FAIL, 19 deselected, 1,00s, oba
`TypeError: object of type 'Mock' has no len()` w job_repository.py:126.
Nie naprawiano tego poza zakresem T1.
Nie deklaruje się pełnego PASS całej grupy pin API.

```powershell
# CWD: D:/game_predicotr/worktrees/full-symbol-crops/artifacts/task1163-index-8ic0jtio
$env:PYTHONPATH = "$PWD/services/api/src;$PWD/services/worker/src"
& D:/game_predicotr/.venv/Scripts/python.exe -c 'import subprocess,sys; sys.exit(subprocess.run(["D:/game_predicotr/.venv/Scripts/python.exe","-c","import game_predictor_api.domain.neural_grid_operation_pin as pin; import game_predictor_api.storage.job_repository as repository; import pytest; print(pin.__file__,flush=True); print(repository.__file__,flush=True); raise SystemExit(pytest.main([\"services/api/tests/test_neural_grid_operation_pin.py\",\"-k\",\"exact_repository_lookup\",\"-q\",\"--tb=short\",\"--basetemp=D:/game_predicotr/worktrees/full-symbol-crops/.tmp/t1-clean-t0-pin\"]))"],timeout=120).returncode)'
```

## Następne kroki i granice wyniku

T2 dostarcza trwały reader `photos.content_references(index)` zwracający opcjonalne
`BoardContentReference` wyrównane do posortowanych targetów. Klucze: gameId,
normalized pixel SHA, positionIndex, cellIndex; revision odnosi się do zawartości,
nie do geometrii. T3 zamraża zaufane `contentReferenceSha256` i
`contentReferenceRevision` w targetach A i dostarcza rzeczywiste przycięcia
zawartości. T4 jawnie wybiera `grid_output_contract` w jobie; brak pola to legacy.

Nie uruchamiano usług, GPU, treningu operatora, DB ani odczytu zdjęć/sekretów.
Nie wykonano pomiaru skuteczności, publikacji, aktywacji, wdrożenia ani commita.
Brak etykiet i audytu nie jest zaliczany jako PASS. Root prowadzi audyt Opus,
decyzję D589, zamknięcie taska i wersjonowany commit.

## Jedna runda poprawek po rzeczywistym R1 (2026-11-08)

R1 przekazanie1: timeout bez opinii. Przekazanie2: rzeczywisty wynik CLI Opus,
ale parser odrzucił format ID F-01–F-05. Nie oznacza to PASS. Zachowany fragment
i receipt: `TASK-1164_AUDIT_R1_INVALID_FORMAT.md` oraz plik `.receipt.json`.
Poniższe poprawki/testy pochodzą od wykonawcy, nie zastępują werdyktu audytora.

| Historyczne ID → ID dla R2 | Poprawka i dowód |
| --- | --- |
| F-01 → P1-1 | Frozen A wymaga hash/revision/contentReferenceInputCropped strictbool i porównuje trójkę. Test odrzuca odwrócony boolean przy poprawnym pinie. T3 dostarcza etykietę z wejścia wariantu; T2 jej nie zgaduje. |
| F-02 → P1-2 | CorrectionControlPhoto opcjonalnie ładuje RGB i box z jednego CanonicalSourceFrame; A/REG oraz B używają loadera. Observer stosuje box tylko dla v2, brak wsparcia blokuje oś. Test porównuje pełne features runtime/calibration z paddingiem i niezmienność features/SHA v1. |
| F-03 → P2-1 | Lock chroni cache frame; RGB i maska powstają z jednego odczytu per zdjęcie przed pętlą plansz. Test6 równoległych workerów sprawdza zgodność pikseli/masek,6 odczytów i maksymalnie1 równoczesny decode. |
| F-04 → P2-2 | Spec→eksport wymaga expected contract dla v2 przy instalacji i odzyskanym eksporcie. Runtime bez spec pozostaje dozwolony. Test odrzuca v2 z poprawnie zahashowanym legacy spec. |
| F-05 → P2-3 | Atrapa skalera pomija optimizer.step i obniża skalę; test potwierdza zerową ekspozycję obu klas/step i brak zmian parametrów. |

Focused27 PASS/2 deselected (10,80s), regresja callerów18 PASS (17,65s), Ruff
format/check14 PASS, mypy11 PASS. Pierwsze mypy wskazało opcjonalny typ support;
dodano asercję istniejącego niepustego kontraktu i uzyskano mypy11 PASS.
Nie powtarzano ONNX/SDK ani błędów baseline. Neutralna granica importów PASS.
`npm.cmd run docs:check` po poprawkach PASS:651 links,587 entries/index rows,
startup44616 B,11/11budżetów.
Mapy root generuje w izolowanym drzewie T1, bez równoległych zmian T2.

Komendy z runnerem subprocess timeout120s i PYTHONPATH opisanymi wyżej:

```powershell
& $taskPython -m pytest services/api/tests/test_grid_visibility_calibration.py services/worker/tests/test_grid_visibility_contract.py services/worker/tests/test_full_board_calibration_integration.py -k 'not real_board_export and not changed_raster' -q --maxfail=3 --basetemp=.tmp/t1-r2-focused-1
& $taskPython -m pytest services/worker/tests/test_grid_correction_metrics.py services/worker/tests/test_grid_correction_evaluation_pipeline.py services/worker/tests/test_grid_cohort_dataset.py::test_file_backed_reader_retains_one_page_and_frame_and_no_corpus_index services/worker/tests/test_grid_cohort_dataset.py::test_pixel_identity_mismatch_and_missing_snapshot_never_become_new_labels services/worker/tests/test_grid_training_child.py::test_recovered_export_must_match_its_recorded_hashes services/worker/tests/test_vision_lab_training_core.py::test_import_boundaries_are_transitive_source_constraints -q --maxfail=2 --basetemp=.tmp/t1-r2-callers
```

Trzy dodatkowe callery: `images/grid_cohort_dataset.py`,
`images/grid_model_evaluation_handler.py`, `training_core/grid_correction_metrics.py`.
R2 oczekuje na niezależny focused review. Wykonawca nie uruchomił nowego audytu,
nie wykonał stage/commita ani nie zmienił danych operatora.

## Odbiór koordynatora

Focused R2 Claude Code Opus 5.5, effort żądany high, transport CLI: PASS.
Weryfikacja SHA pakietu/raportu i pełny odczyt raportu: PASS; wszystkie pięć
uwag zamknięte, brak nowych P0/P1/P2. Receipt jest wersjonowany obok raportu.
Mapa kodu wygenerowana i `--check` PASS w izolowanym drzewie HEAD + dokładnie
38 źródeł R2; dowód lokalny `artifacts/task1164-isolated-map-proof.json`.
Nie powtarzano testów bez zmiany kodu. Brak rzeczywistego pomiaru jakości
lub treningu operatora pozostaje ograniczeniem, nie PASS modelu.
