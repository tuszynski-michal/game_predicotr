---
title: Kontrakt 24 punktów i 15 ocen widoczności
status: done
last_updated: 2026-11-08
---

# TASK-1164 — Kontrakt 24 punktów i 15 ocen widoczności

## Status

`done`

## Goal

Zgodny, wersjonowany przepływ visibility15/peak24 z uczonym nadzorem i maskami.

## Context

Runtime i fixture wymagają24visibility, chociaż BoardNetwork ma15; loss
korekt nie korzysta z visibility. Softargmax nie obserwuje brakujących pikseli.

## Dependencies / entry conditions

T0 procedura gotowa; implementację można kontynuować przy odłożonym audycie
Opus zgodnie z poleceniem operatora. Zakres planu i koszt zatwierdzone.
Trwały reader nowych etykiet jest w T2; T1 dostarcza opcjonalny kontrakt
wejściowy, nie fabrykuje etykiet z samych punktów ani nie wymaga danych operatora.

## Recommended execution

gpt-6-astra/high, audyt Claude Code claude-opus-5-5/high; brak modelu blokuje.

## Relevant docs

- AGENTS.md
- ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md (T1 i reguły wspólne)
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/decisions/DECISION_LOG_2026.md (D-584–589, zakresy według nagłówków)
- ai_docs/architecture/CODE_MAP.md

## Scope

T1 planu w całości: wersje features/runtime/loss/eksport/API,24/15,
visibility target/mask, node_weights[N,24], osiągalność softargmax i realne
wsparcie, próg inputEdgeClearance z A oraz minima nadzoru. Reuse istniejącego
API; przy zmianie pion backend/OpenAPI/SDK/wrapper/requesttest.

## Out of scope

Operatortraining, dane operatora, nowe etykiety z domysłu, zmiana starych raportów.

## Acceptance criteria

- [x] Prawdziwy BoardExport i runtime dostarczają peak24/visibility15 bez utraty.
- [x] Cele visible/occluded/out_of_frame/unknown i maski stosowane po augmentacji.
- [x] Loss nie uczy nieosiągalnych/padded węzłów; brak ważnych celów jawny.
- [x] Niedobór30+30/5zdjęć blokuje oś/automat, nie geometrię.
- [x] inputEdgeClearance wersjonowane, ≥5ucięć/3zdjęcia dla progu; brak danych nie daje PASS.
- [x] Historyczne modele/raporty zachowują semantykę, fixture rzeczywiście15.
- [x] Testy/scoped lint/types/ONNX, dokumentacja/decyzja i audyt albo jawne oczekiwanie.

## Technical notes

Nie maskować niskiego peak przy inferencji informacją GT. Oś brzegu jest
podejrzeniem, nie detektorem wszystkich brakujących rzędów. Rozbudować
Expected files i komendy po scoped odczycie kodu, przed implementacją.

### Scoped preparation (2026-11-08)

Potwierdzono: `BoardNetwork.forward` i `BoardExport.forward` już zwracają
24 węzły/peak i 15 visibility. Błąd `features` wymaga wspólnie rozmiaru24;
fixture w `test_full_board_completeness.py` i części testów integracyjnych
utrwalają ten błąd. `weighted_node_losses` waży całe cropy `[N]`, a oba
correction losses ignorują visibility. `ScreenGridBatches` pomija istniejące
`visible`; jego pusta lista unavailable nie jest etykietą visible.

Proponowane wersjonowanie: addytywny kontrakt nadzoru/wyjścia w nowym
bundle, osobne features/plan/profile/evidence v2 i dispatcher po wersji.
Istniejące `neural-grid-v1`, `neural-grid-bundle-v1`, features/calibration/
profile/evidence v1 oraz report-read-v5 pozostają czytelne bez zmiany SHA.
Brak nowego kontraktu oznacza legacy; nie dowodzi nadzoru visibility.
Nowa oś nie rozszerza globalnego `AXES` v1 ani jego menu256. Jej jeden próg
pochodzi wyłącznie z A per wariant; B nie stroi routingu.

T1 przyjmuje opcjonalne zatwierdzone stany i obwiednie komórek z identyfikatorem
źródła; T2 dostarczy trwały reader. Bez etykiet maska visibility jest zerowa.
Minima30 dodatnich i30 ujemnych z≥5 zdjęć na klasę liczy się przed augmentacją
na rzeczywistym TRAIN po deduplikacji. Sztuczny crop/zasłona nie zwiększa
minimum. Dostępność zawartości po transformacji wynika z obwiedni i realnych
pikseli; same węzły nie tworzą targetu. `node_weights[N,24]` łączy wagę cropa,
realne wsparcie oraz osiągalność `[stride/2, wymiar-stride/2]`.
Jawne liczniki masek obejmują unknown, niedobór nadzoru, padding i brak celu;
nie wchodzą jako składniki do sumy loss.

## Expected files

Ścieżki poniżej są względem repo; nowe moduły oznaczono jawnie.

- `services/worker/src/game_predictor_worker/training_core/neural_grid_network.py`
  (`BoardNetwork`, `BoardExport`, `soft_argmax`), `grid_training.py`
  (`weighted_node_losses`, `board_only_losses`, `screen_grid_losses`,
  `bundle_document`, `export_graphs`, `raw_parity`) i `neural_grid_augmentation.py`
  (`build_board_crop`, `build_screen_item_with_indices`).
- `services/worker/src/game_predictor_worker/images/grid_training_data.py`
  (`GridOnlyBatches`, `ScreenGridBatches`, `CohortPhotos`, `JointPhotos`),
  `grid_training_child.py` (wybór kontraktu przy treningu/eksporcie).
- `services/worker/src/game_predictor_worker/geometry_core/inference.py`
  (`BoardDetection`, `NeuralGridEngine`, `onnx_engine`) i `settings.py` (legacy).
- `services/worker/src/game_predictor_worker/images/full_board_completeness.py`
  (`features`, `input_support`), `full_board_runtime_evidence.py`
  (`runtime_evidence`), `full_board_calibration_observations.py`
  (`CalibrationObserver`) i `full_board_calibration_run.py`
  (`FullBoardCalibrationRun`).
- `services/api/src/game_predictor_api/domain/full_board_calibration.py`
  (`FeatureVector`, `ReferenceTarget`, `CalibrationPlan`, `make_plan`,
  `acceptance_reasons`), `full_board_calibration_report.py`
  (`AutomaticProfile`, `AutomaticCalibration`), `calibrated_neural_evidence.py`,
  `neural_grid_operation_pin.py`; `storage/full_board_calibration_evidence.py`
  (niezależna rekalkulacja dowodów), `schemas/grid_model_evaluations.py`.
- Proponowane nowe, małe moduły kontraktu nadzoru i v2 kalibracji zamiast
  przepisywania v1; nazwy ustalić przy implementacji.
- `packages/admin-api-client/openapi/openapi.json`, wygenerowane `src/generated`,
  istniejący wrapper eksportowany przez `src/index.ts` i
  `test/grid-model-evaluation-request.test.mjs`.
- Testy: istniejące `test_durable_v3_grid_training.py`,
  `test_full_board_completeness.py`, `test_full_board_calibration_integration.py`,
  API `test_full_board_calibration.py`, `test_full_board_calibration_report.py`;
  proponowany `services/worker/tests/test_grid_visibility_contract.py`
  z realnym eksportem BoardExport/ONNX na CPU.
- Wymagania/architektura VISION_LAB; decyzję i mapę kodu koordynuje lead.

Rzeczywisty zakres implementacji doprecyzowany: `neural_grid_network.py`,
`settings.py` i `schemas/grid_model_evaluations.py` nie wymagały zmian.
Nowe moduły to API `domain/grid_visibility_contract.py`,
`domain/input_edge_clearance.py` oraz worker
`training_core/grid_visibility_targets.py`. Dodatkowo zmieniono
`domain/full_board_assessment_reference.py`, `domain/grid_model_registry.py`
i `images/grid_training_handler.py`; dodano API
`tests/test_grid_visibility_calibration.py`. Pełna jawna lista plików znajduje
się w `artifacts/TASK-1164_SCOPE.txt`; obejmuje wygenerowane mapy oraz tylko diff
root-owned `DECISION_LOG.md`, `DECISION_LOG_2026.md`, `DECISION_INDEX_ARCHIVE.md`.

## Test cases

15vs24 fixture i realny eksport, masked gradients/unknown/all masked,
cel poza wejściem i pas stride/2, prawdziwe ucięcie górnego rzędu,
brak pozytywnych przypadków A, progi/remisy, stare wersje.

## Verification

Root .venv i .venv-vision-lab, PYTHONPATH właściwego worktree. Skończone
testy/scoped lint/types ≤120s, większy znany eksport osobno kontrolowany.
Zapisać dokładne komendy/wyniki w quality/TASK-1164_VERIFICATION.md.

Wejścia narzędzi; dokładne wykonane grupy i wyniki zawiera raport weryfikacji:

```powershell
# cwd D:\game_predicotr\worktrees\full-symbol-crops; każda komenda w procesie
# kontrolowanym przez runner z timeout120s, ONNX jako osobna komenda.
$env:PYTHONPATH = "$PWD\services\api\src;$PWD\services\worker\src;$PWD\services\test_support"
$taskPython = 'D:\game_predicotr\.venv\Scripts\python.exe'
& $taskPython -m pytest services/worker/tests/test_grid_visibility_contract.py -q
& $taskPython -m pytest services/worker/tests/test_durable_v3_grid_training.py services/worker/tests/test_full_board_completeness.py -q
& $taskPython -m pytest services/worker/tests/test_full_board_calibration_integration.py -q
& $taskPython -m pytest services/api/tests/test_full_board_calibration.py services/api/tests/test_full_board_calibration_report.py -q
# Ruff format --check, ruff check i mypy: jawna lista zmienionych plików,
# interpreter D:\game_predicotr\.venv\Scripts\python.exe, ten sam PYTHONPATH.
npm.cmd run openapi:generate
node --import tsx --test packages/admin-api-client/test/grid-model-evaluation-request.test.mjs
npm.cmd run typecheck --workspace @game-predictor/admin-api-client
npm.cmd run docs:check
```

Realny eksport nie może być zastąpiony TinyNetwork ani stałym fixture15.
Wymaga sprawdzenia output shapes24/15, parity i rzeczywistego ograniczenia
softargmax na wejściu z uciętym rzędem; nie dowodzi jakości losowych wag.

## Risks / open questions

Nowych rzeczywistych negatywnych etykiet może brakować; raportować blokadę,
nie wymyślać zatwierdzeń. To nie blokuje implementacji bezpiecznego kontraktu.

## Outcome

Commit: v1.7.573 (hash dopisuje kolejny commit).

Implementacja i jedna runda poprawek zakończone; niezależny focused R2 Opus PASS.
Wersjonowany pion v2 obejmuje wyjście24/15, nadzór komórek, maskowane straty,
eksport, runtime, kalibrację i API/SDK. Historyczny v1 pozostaje domyślny.
`trainedVisibility` wymaga zarówno unikalnych etykiet TRAIN per gra, jak
i poświadczonego niezerowego nadzoru obu klas przed wybranym checkpointem.
Stan ekspozycji przechodzi przez checkpoint i wznowienie. Całkowicie zamaskowany
board-only batch nie wykonuje kroku AdamW.

`inputEdgeClearance` korzysta z rzeczywistych pikseli wejścia, a jeden próg
może pochodzić tylko z A tego samego wariantu. Historyczne `gt_cropped`
pozostaje `geometry_proxy`: nie spełnia minimum 5 plansz/3 zdjęć. API wymaga
zgodności SHA i rewizji `verified_content` z niezależnym frozen readerem A;
sam claim workera jest odrzucany. Brak danych pozostawia próg unset/unqualified.

Weryfikacja: scoped Python/SDK, rzeczywisty BoardNetwork→BoardExport→ONNX→ORT
na CPU, lint/format 24 plików, mypy 20 modułów, spójność wygenerowanego SDK,
OpenAPI i mapy. Szczegóły: `ai_docs/quality/TASK-1164_VERIFICATION.md`.
Znany wcześniejszy błąd dwóch testów Mock w `test_neural_grid_operation_pin.py`
odtworzono w pełnej izolowanej kopii T0/v1.7.572, z potwierdzonym importem
modułów wyłącznie ze shadow; nie rozszerzano zakresu.
Środowiskowe błędy hardlink/temp powtórzono w odizolowanym katalogu i uzyskano PASS.

Nie wykonano treningu operatora, pomiaru jakości, usług, zmian danych ani
kwalifikacji rzeczywistego modelu. T2 musi dostarczyć trwałe zatwierdzone
`BoardContentReference` i reader; T3 zaufane piny zawartości A, T4 opt-in
kontraktu w jobie. Audyt Opus, zamknięcie i commit wykonuje lead. Brak audytu
nie jest PASS, a testy na syntetycznych danych nie dowodzą jakości modelu.

Po rzeczywistym R1, którego format parser odrzucił, wykonano jedną rundę
poprawek wszystkich5 uwag: trusted inputCropped strictbool, wspólny atestowany
RGB/valid_box dla kalibracji v2 i runtime, blokada cache frame i jeden odczyt
per zdjęcie, wymagany kontrakt spec dla eksportu v2, test back-off skalera.
Dodatkowe callery: `images/grid_cohort_dataset.py`,
`images/grid_model_evaluation_handler.py`, `training_core/grid_correction_metrics.py`.
Focused27 PASS, caller regressions18 PASS, Ruff14/mypy11 PASS; R2 oczekuje
na niezależny werdykt. Historia ID/provenance i komendy są w raporcie weryfikacji.

Audyt terminalowy: `ai_docs/quality/TASK-1164_AUDIT_claude-opus-5-5.md`
i receipt o zgodnym SHA pakietu. Runda 2 zamknęła oba P1 i trzy P2;
pozostało 0 otwartych P0/P1/P2. Historia timeout i nieprawidłowego formatu R1
jest zachowana jawnie, bez odtwarzania brakującego nagłówka lub fikcyjnego PASS.
Opcjonalne scenariusze integracyjne z raportu przechodzą do zależnych T2/T3.

Odbiór AC/DoD: kontrakt, maski, widoczność, minima i próg wejścia mają testy;
historyczne wersje zachowane. Testy 27 oraz 18 po poprawkach, scoped lint/types,
realny ONNX z pierwotnej weryfikacji i pion API/SDK mają zapisane wyniki.
Mapę kodu wygenerowano i sprawdzono w izolowanym drzewie 38 źródeł T1, bez T2.
Zmian schematu i UI w T1 nie było; PostgreSQL/build interfejsów nie są tu
właściwymi kontrolami. Rzeczywista kwalifikacja wymaga nadal adapterów T2/T3
oraz danych człowieka; nie jest deklarowanym wynikiem tego taska.
