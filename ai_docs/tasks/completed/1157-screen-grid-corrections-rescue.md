---
title: Detector correction learning and bounded rescue
status: done
last_updated: 2026-11-04
---

# TASK-1157 — Detektor w procesie korekt i dowodowy ratunek

## Status

`done`

## Dependencies / entry conditions

T0–T2 zakończone; HEAD wejścia6325a057 (v1.7.561). Operator zatwierdził dodatkowe
4–6 godzin T3–T6 z audytami: „Tak, dokończ T3–T6 z audytami”. Rozszerzenie istniejącego
preview/start o trainingMode i detectorReadiness zostało zapowiedziane. Zgoda obejmuje
kontrolowane małe CPU optimizer/ONNX fixtures i disposable PostgreSQL; nie obejmuje
treningu na danych operatora, migracji operatora, usług, aktywacji, merge/push.
Sprawdzono wszystkie refs/heads i refs/remotes: TASK1157/D586 wolne; najwyższa migracja0179.
Rezerwacja: D-586 oraz0180_screen_grid_corrections (po0179_empty_replacement_search).

## Recommended execution

gpt-6-astra / high. Jeden właściciel pionu API/SQL/trenera/runtime. Niezależny audyt
Claude Code claude-opus-5-5/high tylko do odczytu, przed commitem; uruchamia root.
Otwarty P0/P1 po jednej rundzie poprawek blokuje commit. Brak modelu lub audytu nie jest PASS.

## Scope

Nowa polityka screen+grid, pełne TRAIN/A, jawna gotowość, photo-first checkpoint,
jedna jawna konfiguracja ratunku z dowodem TRAIN/A/ONNX, inspector i trwały runtime1+1.
Partial REG assessment zachowuje opisane cele w istniejącym ledgerze.

## Out of scope

T4 niezależne A/B i kalibracja, T5 panel, T6 odbiór; nowy trener/klasyfikator,
operator DB/usługi/GPU/trening/inferencja/aktywacja/merge/push; niezwiązane P2 T2.

## Acceptance criteria

- [x] Nowy preview/start i frozen policy mają spójne counts/used/reasons; full0 blokuje screen.
- [x] Partial TRAIN/A nie są tłem; REG partial zachowane z jawnością celu oceny.
- [x] Rzeczywisty CPU optimizer fixture zmienia detektor screen, grid-only pozostaje zamrożony.
- [x] Photo/board/error/earliest wybiera checkpoint na A, equal games, bez REG i resetu resume.
- [x] Jedna konfiguracja ma pełną ścieżkę recipe→TRAIN exposure→A paths→export/parity→inspector→runtime.
- [x] Screen-only, board-only i combined mają własne dowody; brak dowodu oznacza manual.
- [x] Rezerwacje przed CPU egzekwują1redetect/source+1crop/position po restarcie i lost response.
- [x] Stare polityki, fingerprinty, snapshoty i funkcje SQL zachowują interpretację.
- [x] Backend/OpenAPI/generated client/wrapper/request tests zgodne.
- [x] Scoped tests/lint/types/docs/map oraz niezależny audyt rozliczone; scoped baseline limitations jawne, Opus R2 PASS.

## Expected files

Istniejące moduły i symbole są wymienione w tabeli sprawdzonych punktów poniżej.
Nowe: domain/grid_rescue_policy.py (strict contracts/proof); geometry_core/rescue.py
(typed geometry); images/grid_rescue_runtime.py (durable executor); storage/source_recording_sql_v7.py,
source_recording_permissions_v7.py i alembic/versions/0180_screen_grid_corrections.py.
Dokładne miejsca mogą być dopasowane do istniejących warstw bez zmiany reguł domeny.

## Goal

Wykonalny, wersjonowany trening screen+grid z dowodowym ratunkiem i trwałym limitem prób.

## Context

Detektor w istniejącym procesie korekt, wykorzystując SCREEN_GRID_V1,
ScreenGridBatches i ocenę od oryginalnego zdjęcia. Bez drugiego trenera.
T1 jest dowodem danych, nie pretekstem do ich ponownego skanowania:
197 GT / 134 zdjęcia LIVE, full0; frozen TRAIN98/146, VAL13/17, REG13/21, full0.
Nie ma GT462205 ani zmierzonej amplitudy asymetrycznego błędu.

Root zatwierdził następujący wybór w preflight:
- opcjonalny `trainingMode` w istniejącym preview/start, domyślnie `grid-only`;
- `screen+grid` jawny, oddzielny wybór: full0 => canStart=false; bez fallbacku;
- partial pozostają użyteczne w grid-only; w screen trybie są jawnie wyłączone
  z liczb użycia detektora z powodem, a nie usuwane po cichu;
- wymagane gry historyczne nie znikają. Historyczne grid-only kohorty nie mogą
  zostać przepisane na screen. Brak zgodnych nowych kohort dla requiredScope blokuje;
- nowa wersja SQL/Alembic zachowuje stare funkcje/piny/semantykę. Tylko przygotowanie
  i testy disposable, migracja operatora wymaga osobnej zgody przy wdrożeniu.
Root poinformuje operatora o rozszerzeniu istniejącego kontraktu przed kodowaniem.

## Relevant docs

- AGENTS.md, ai_docs/process/PLAN_STANDARD.md, TASK_TEMPLATE.md i DEFINITION_OF_DONE.md.
- ai_docs/delivery/FULL_BOARD_DETECTION_PLAN_20261103.md, sekcja T3 oraz granice T4.
- ai_docs/requirements/VISION_LAB.md: D-577/578 oraz D-556–560.
- ai_docs/architecture/VISION_LAB.md: Correction learning pipeline; Grid training
  admission; Durable application grid training; Shared candidate.
- ai_docs/quality/FULL_BOARD_INPUT_DIAGNOSIS_20261103.md.
- ai_docs/process/DECISION_LOG.md: D-577/578/581/582; pełne odpowiednie wpisy
  odczytać przed D-entry implementacji. Decyzja D-586.

## Sprawdzone punkty kodu i rzeczywiste ograniczenia

Wszystkie ścieżki względem worktree. Prefiksy A=`services/api/src/game_predictor_api`,
W=`services/worker/src/game_predictor_worker`.

| Punkt | Obecne zachowanie / potrzebna zmiana |
|---|---|
| W/training_core/grid_training_admission.py:203–251 | SCREEN_GRID_V1 istnieje; GRID_CORRECTIONS_V1 ma tylko grid-only i board-first rule. preset_for_mode rozpoznaje policyv1/v2 przez warunek boolean. Zastąpić jawną mapą policy+mode bez zmiany wyborów legacy. |
| A/domain/grid_correction_policy.py | Obecne correctionsv2, snapshotv2, presetgrid-corrections-v1. Nowa para ma własne nazwy. |
| A/application/grid_correction_learning.py:85,217–263,484–552 | Preview/historical checks/prepare są hardcoded grid-only; eligibleFullPhotos=0 jest wpisywane, nie mierzone. Potrzebne rzeczywiste pełne liczniki z tego samego readera i splitu oraz pin trybu w preview/parent/child. |
| A/schemas/grid_correction_learning.py:33,104 | Closed preview/start nie mają trybu; preview ma canStart/blockers/pendingWorkerChecks/dataAvailability. Rozszerzyć istniejący pion, bez endpointu ani równoległego workflow. |
| A/storage/grid_correction_split.py:prepare_split,split_mapping | Pełna populacja definiuje kolejność i bufory; solver używa eligibleBoards. Nie filtrować populacji przed solverem. W nowej polityce ekranowej partial mają zero eligible detector targets z jawnym powodem, pozostają w order/buffer/alias checks. |
| A/application/grid_training_cohort_commands.py:113–130 | Prepare whitelist korekt narzuca grid-only; osobna para nowego policy+mode, stare nadal zamknięte. |
| A/domain/grid_training_cohorts.py:115–174 | Minima: TRAIN30boards/10photos, screen TRAIN10full; kontrola15boards/5photos, legacyfull5. Nowa screen polityka wymaga full TRAIN10/checkpointA5. Nowe REG assessment zachowuje5photos/15GT przy requiredFullREG=0; dawne polityki zachowują swoje minima i full requirements. |
| A/schemas/grid_training_cohorts.py:48–59 | Literal polityk i model validator odrzucają nowy tryb. |
| W/images/grid_cohort_dataset.py:153–173,428–461 | Whitelist snapshot/policy oraz v1/v2 corrections=>grid-only. GridBoardDataset już odrzuca użyte partial dla screen; utrzymać tę obronę. |
| W/images/grid_training_data.py:49–56 | CohortPhotos full_only filtruje wiersze. Dla nowego screena nie polegać na tym jako admission: used rows i frozen count muszą już być pełne; rozjazd ma rzucać błąd, nie zmniejszać datasetu. |
| W/images/grid_training_child.py:387–482 | Wybór presetu i fingerprint, trainfull_only, validations, JointPhotos, ScreenGridBatches, photo_evaluator, override correction_evaluator. Rozszerzyć dispatch jawnie, nie zmieniać starego correction override. |
| W/images/grid_training_data.py:272–298,325–370 | photo_evaluator analizuje oryginał, dziś zwraca scalar; correction_evaluator ma już photo-macro error i equal-game mean. Wspólny opcjonalny wersjonowany adapter zbierze kompletne metryki bez drugiej inferencji/dublowania trenera. |
| W/training_core/grid_correction_metrics.py:checkpoint_metrics,selection_key | Obecnie boardCorrectRate,-normalizedError,-step. Nowa reguła dodaje photoCorrectRate jako pierwsze kryterium i wymaga pełnych zdjęć w każdej grze. |
| W/training_core/grid_training.py:239–292,334–341,481–543 | EarlyStopping state/restore, binding, history, best_state i exported checkpointSelection zakładają dwa wskaźniki. Nowe trzy wskaźniki muszą przejść cały łańcuch, nie tylko comparator. |
| A/domain/grid_correction_evaluation.py:157,269–295,445–473 | Raport/gate zamknięte na grid-only i starą regułę selection; potrzebny nowy strict dispatch raportu, z zachowaniem dotychczasowych progów i requiredScope. |
| A/domain/shared_grid_model_candidate.py:80–85 | Shared run wymaga jednego trybu; stare kohorty grid-only nie mogą być cicho dodane do screen run. |

## Technical notes — wersje nowej polityki

Stare v1/v2 korekt, snapshoty, fingerprinty, recipe oraz checkpointy pozostają bez zmian.
Nowy screen tryb:

| Element | Proponowana wersja |
|---|---|
| Polityka kohorty | `application-grid-corrections-v3` (tylko screen+grid; grid-only default zachowuje v2) |
| Manifest kohorty | `application-grid-snapshot-v3` |
| Preset | `screen-grid-corrections-v1`, version3, pochodny istniejącego SCREEN_GRID_V1 |
| Reguła checkpointu | `validation-photo-board-correct-photo-macro-error-earliest-v1` |
| Binding checkpointu | `grid-training-checkpoint-v3` |
| Stan metryk | `photo-board-checkpoint-state-v1`; photoCorrectRate, boardCorrectRate, normalizedError, step, evaluations/stale |
| Wejście selection | `grid-checkpoint-input-v1`: VALIDATION + all-validation-v1 + exact cohort/source hashes |
| Raport / gate | `grid-model-evaluation-read-v4` / `grid-model-per-game-gate-v3`; nowa reguła i screen mode, stare progi porównań zachowane |
| Plan ratunku | `grid-rescue-policy-v1`; pin w nowej operacji/bundle metadata, nie modyfikacja NeuralGridSnapshotv1/v2 |

Klucz wyboru: `(photoCorrectRate, boardCorrectRate, -normalizedError, -step)`.
Najpierw równe wagi zdjęć wewnątrz gry, potem równe wagi gier. NME pozostaje
odległością24punktów / GTbbox diagonal, missing=1. REGRESSION nie trafia do evaluate
podczas train. best_weights musi odtwarzać cały zwycięski checkpoint, nie ostatni krok.
Brak/niezgodny metric-state, selection rule, preset fingerprint lub input hash przy
resume => jawny błąd, bez defaultowania pól i bez przeliczenia budżetu.

T4: selectionInput zapisany w obecnym binding/manifest i dowodach użycia kohorty
stanowi hook dla przyszłego jawnego VALIDATION-A. T3 all-validation-v1 oznacza
faktyczne wykorzystanie całego VALIDATION do selection; nie nazywać tego niezależnym
VALIDATION-B. T4 podzieli grupy w istniejącym rejestrze i przypnie nową wersję wejścia.
Nie tworzyć dodatkowej tabeli/ledgera ról. Zmiana selectionInput nigdy nie działa na resume.

## Granica T3/T4 — uzgodniona z rootem i wykonawcą T4

Nowa ścieżka optymalizatora screen+grid wymaga pełnych źródeł TRAIN i checkpointA.
T4 B/REG to inny cel oceny: `assessmentPolicy=human-labeled-targets-v1`,
`scope=labelled_targets`, niezależny od trainingMode modelu. Reuse aktualnego readera
kwalifikacji i istniejącego ledger; jawny reference wiąże cohort/member/source,
exact GT target IDs i geometry revisions, sourceSetSHA, role-purpose/selectionExposure
oraz proof grup/kopii. Nie jest to nowe źródło ról ani kopia magazynu.

Partial B/REG pozostają w frozen reference oraz licznikach. Matching i bezpieczeństwo
mierzą opisane GTcele; complete-photo/false-board/duplicate metryki tylko dla fullGT.
Nie wywoływać treningowego GridBoardDataset w trybie screen do odczytu T4, bo jego
obecny full-only guard odrzuci partial. T4 dostarczy jawny assessment adapter/reference,
który zachowuje policzone cele bez filtrowania i nie reinterpretowuje snapshotów legacy.

Dla nowej corrections-v3 screen policy admission/freeze nie wymagają9/9 w REG:
pozostają minima5photos/15GT i requiredFullREG=0. REG nie jest konsumowany przez
optimizer/checkpoint selector. TRAIN10full i checkpointA5full pozostają wymagane.
B/minima kwalifikacji automatu są T4; trainingMode nie może narzucić im full9/9.
Stare correctionsv1/v2 i legacy screen snapshots zachowują swoje ścisłe semantyki.
Przyszły reference może wiązać dodatkowe zakwalifikowane partial z tego samego
ledger nawet jeśli wcześniejszy historyczny training snapshot ich nie zawierał;
nie dopisywać tych celów do starego snapshotu ani nie zmieniać jego SHA.

## Readiness, API i granice danych

Preview/start zachowują dotychczasowe ścieżki i domyślny grid-only. Nowe additive
pola: trainingMode, detectorReadiness (photo counts/full counts/partial excluded,
per-role required/eligible/deficits, reasonCodes). Nullable liczniki oznaczają brak
pomiaru, a nie0. `canStart` wymaga wszystkich danych i historycznego scope. GPU
pozostaje pendingWorkerChecks, nie twierdzeniem backendu o gotowym runtime.

Planowane stabilne powody: SCREEN_FULL_PHOTOS_REQUIRED,
SCREEN_FULL_TRAIN_REQUIRED, SCREEN_FULL_VALIDATION_REQUIRED,
SCREEN_HISTORY_COHORT_REQUIRED,
SCREEN_PARTIAL_PHOTO_EXCLUDED. Nazwy scalić z istniejącymi równoważnymi kodami,
bez równoległych znaczeń. Te same counts/used flags w preview, frozen manifest,
worker dataset i kosztach. Post-freeze drift => błąd, nigdy ponowne filtrowanie.

Pion obowiązkowy: backend/schema -> OpenAPI -> generated klient -> wrapper ->
request tests. UI wyboru/messaging może korzystać z T5, lecz backend nie może
zależnie od full0 sam zmienić żądanego trybu. Stary parent bez trainingMode ma
historyczny grid-only; nowe idempotency/preview hashes zawierają jawny tryb.

## SQL/Alembic i historia

Sprawdzone: `A/storage/source_recording_sql_v6.py:PHOTO_SQL/WRAPPER_SQL` dopuszcza
wyłącznie correctionsv1/v2, a incremental flag jest dokładnie policy==v2. Kod
odziedziczony z v4 wymaga mode=grid-only. Repository wywołuje
`recording_cohort_command_v3` (grid_training_cohort_repository.py:297).
To jest funkcja SECURITY DEFINER, nie zwykła kontrola Python.

Przygotować moduł SQL v7 (migracja0180)/permission surface z nowymi nazwami funkcji dla v3
korekt (proponowane recording_photo_cohort_v2 / recording_cohort_command_v4).
Stare funkcje i ich routing pozostawić dla historycznych polityk; nie edytować
historycznego modułu v6 ani migracji0178. Nowy wrapper deleguje stare żądania do
starej funkcji; tylko nowa polityka dostaje nową ścieżkę. Zachować RLS, advisory
locks, source-replacement fences, append-only użycia, released reservations oraz
bufory/kopie. Nie przyznawać runtime bezpośredniego dostępu do internal definer.

Proponowana migracja po0178 (numer0180 sprawdzony na wszystkich refs), z testem ograniczeń
uprawnień i odtwarzania dawnych cohort commands. Bez nowej tabeli roli/rewizji
historycznych dokumentów. Downgrade ma zablokować cofnięcie przy danych nowej
polityki zamiast usuwać historię. Zaktualizować runtime schema readiness/manifest
jeśli nowe funkcje są częścią jego kontraktu; nie uruchamiać migracji operatora.

## Augmentacja i ratunek — granica dowodu

Pełna wykonalna ścieżka config→TRAIN+A→checkpoint/export→inspector→runtime1+1:
sekcja „Kontrakt wariantów ratunkowych” poniżej. Pusta lista dziś nie jest stubem.

`W/training_core/neural_grid_augmentation.py:perturb_quad` już robi scale, shift,
rotation i niezależny per-corner Gaussian jitter. Zachować go w całości.
T1 nie dowodzi liczbowych asymetrycznych amplitud: w T3 nie wprowadzać nowych
wartości ani nie nazywać istniejącego jitteru pomiarem462205. Mechanizm wersjonowanego
asymmetric config może mieć pustą listę aktywnych zmian; uzupełnienie wymaga dowodu.

Istniejące punkty wpięcia: `W/geometry_core/inference.py:NeuralGridEngine.analyse`,
`W/images/neural_page_geometry_preflight.py` (import proposal + durable entry),
`W/images/grid_reinference_handler.py:raw_inference` (immutable raw cache/checkpoint).
Nie tworzyć innego interpretera geometrii. Rescue planner jest czysty, egzekutor
używa istniejącego CPU runnera; polityka/model/input/allowed variant pins muszą
być częścią tożsamości wyniku. Trigger to blocker geometrii T0 lub przyszły T4;
samo podejrzenie nigdy nie zatwierdza wyniku.

Limit na operację+źródło: max1 dodatkowy redetect i max1 crop na stabilną tożsamość
podejrzanej planszy, bez ponownego zerowania po redetect/resume. Rezerwację próby
zapisać PRZED zleceniem runnera w istniejącym trwałym checkpoint/artifact flow;
po awarii bez wyniku próba pozostaje zużyta, znany wynik jest odczytywany. Nie
odtwarzać budżetu tylko z liczby wyników. Brak wolnej próby => manual.

Allowed variants wyłącznie z przypiętego dowodu użycia w TRAIN i walidacji tej
samej konfiguracji scale/margin ORAZ faktycznej kombinacji runtime path
(screen-only/base-margin, board-only/base-screen, combined). Brak takiego dowodu w obecnym materiale => pusta
lista, manual, zero dodatkowych wywołań. Nie dodawać ad hoc większego cropa/768+
ani defaultowego safety margin. Testy adaptera mogą używać jawnego fixture dowodu;
fixture nie kwalifikuje rzeczywistego modelu. Nowe identyfikatory operacji T2
acceptance-v3 i top-level operation pin trzeba odczytać po jego commicie; nie
zmieniać starego NeuralGridSnapshotv1/v2 ani interpretacji historycznych operacji.

## Trwałość i budżet

Użyć istniejącego parent child_key/cohort receipts i grid_training_handler RunBudget.
Nowy trainingMode/policy/preset/input pins w preview fingerprint i sealed spec.
Retry/lost response adoptuje te same child IDs. D-581 TRAIN8000steps/7200chargedseconds
pozostaje globalnym kumulatywnym limitem; optimization plan nadal niezmienny.
Nie zmieniać samego fingerprintu SCREEN_GRID_V1 ani GRID_CORRECTIONS_V1.

## Test cases / Verification — planowane

- full0 => brak child/run, jasny reason/count, grid-only nadal zgodny; mixed preview
  ma jawne partial excluded, identyczne used w snapshot i dataset.
- Pełne photos screen mode zmieniają detector params, grid-only utrzymuje freeze.
  Kontrolowany krótki CPU test existing test harness, bez realnego treningu danych.
- Ranking photo > board > niższe NME > wcześniejszy step, equal-game weighting,
  rozbieżny state/input fail-closed, zgodny resume zachowuje best/history/budżet.
- REGRESSION load spy nigdy nie wywołany podczas train/evaluate checkpoint.
- Stare polityki/fingerprinty/checkpointy/state/SQL zachowują interpretację.
- Brak rescue variant=>0calls; valid fixture=>1redetect+1crop, crash po rezerwacji,
  restart/lost response nie przywraca próby; zmienione piny fail-closed.
- PostgreSQL disposable: stare/newpolicy routing, permissions, freeze/replay,
  RLS, role protections i downgrade guard; operator DB nietknięta.
- API closed enum/default/hash/idempotency oraz pełny generated/request pion.

Istniejące moduły testowe do scoped doboru:
`services/worker/tests/test_grid_training_resource_admission.py`,
`test_grid_correction_metrics.py`, `test_grid_cohort_dataset.py`,
`test_grid_training_child.py`, `test_durable_v3_grid_training.py`,
`test_grid_correction_learning_handler.py`, `test_shared_grid_training.py`;
`services/api/tests/test_grid_correction_learning_api.py`,
`test_grid_correction_cohort_contract.py`, `test_grid_correction_evaluation.py`,
`test_grid_training_run_preview.py`, `test_grid_training_cohort_requests.py`;
PG wzorzec `integration/test_grid_correction_growth_migration_postgres.py`.

Komendy po implementacji z root WT, każda timeout<=120s: `.venv/Scripts/python.exe
-m pytest <wybrane sprawdzone ścieżki> -q --basetemp=<krótki unikalny artifacts>`,
Ruff zmienionych plików; mypy `--follow-imports=silent` z repo config;
OpenAPI/generator w lokalnym cwd pakietu (junction nie może pisać do main),
SDK request test/tsc, docs:check, code-map:check. Opus review uruchamia root.
Nie oznaczać żadnej planowanej kontroli PASS.


## Kontrakt wariantów ratunkowych

## Fakty z kodu

- geometry_core/settings.py:ScreenPreset.long_side to Literal[768]. BoardPreset.margin
  ma zakres0..0.5; domyślny board canvas320x192. Stary typ pozostaje niezmieniony.
- preprocessing.screen_geometry już przyjmuje int long_side; screen_input używa
  INTER_AREA, pad32 i fill114. board_rectifier/crop_board używają margin i INTER_LINEAR.
- neural_grid_augmentation.build_screen_item_with_indices wykorzystuje zarówno
  screen.long_side, jak i train_canvas. Sama zmiana inferencyjnego long_side nie
  dowodzi treningu tej skali. Board crop musi przeliczać etykiety tą samą homografią.
- ScreenGridBatches stackuje cały batch; różne canvas sizes wewnątrz jednego batcha
  nie zadziałają. Wariant musi być wybierany deterministycznie dla całego kroku.
- grid_training_child obecnie pinujefixed D.json oraz RECIPE_FINGERPRINT i porównuje
  pełne screen/board/fit do bazy. Nie wolno usunąć tej walidacji dla dawnych runów.
- export_graphs: screen N dynamic1..64, H/W=32*Dim(2..64), czyli deklarowany zakres
  eksportu64..2048px. Board ma dynamic wyłącznie batch1..64, stałe spatial dimensions.
  To ograniczenia eksportera, nie dowód każdego istniejącego artefaktu ONNX.
- onnx_engine waliduje ScreenPreset z bundle.preset, ładuje CPU ONNX po SHA.
- GridModelArtifactInspector.inspect sprawdza manifest/plik/training-base receipt
  i SHA. Nie ma dziś semantycznej walidacji TRAIN+VALIDATION proof dla rescue.
- NeuralGridEngine.analyse robi detector i board pass dla wszystkich detekcji.
  Użycie go jako redetect zrobiłoby dodatkowe cropy również dla innych plansz.

## Minimalny kontrakt (proponowany, zamknięty)

`grid-rescue-recipe-v1` w nowej sealed training spec:
- baselinePresetSha256 (dokładny dotychczasowy D/preset, bez mutacji),
- variant: null albo JEDEN `grid-rescue-variant-v1`,
- schedule: `baseline-variant-alternate-v1` (stałe wagi 1:1 na poziomie kroków),
- selectionInputSha256 (wersjonowany exact VALIDATION-A/selection set).

Wariant:
- opcjonalny screen: longSide (jawny int, większy niż baseline768, podzielny przez32,
  <=2048) i trainCanvas[width,height] (jawne wymiary,32-multiple,64..2048),
- opcjonalny board: margin (jawne finite, większe niż baseline, <=0.5),
- board canvas pozostaje dokładnie320x192; przynajmniej jedna zmiana jest wymagana,
- preprocessingContract=`neural-grid-rescue-preprocessing-v1`, fixed INTER_AREA /
  INTER_LINEAR, pad32/fill114; reszta decode/loss/fit/augmentation pochodzi z bazy,
- variantId = SHA kanonicznej pełnej konfiguracji; nie dowolna nazwa UI.

Żadnej domyślnej „zmierzonej” wartości L/M. Konfiguracja jest jawna w nowej
recepturze preview/start, początkowo null. Dobór naA oznacza wybór baseline albo
tego jednego zadeklarowanego wariantu; nie ukryty sweep ani dobór naREGRESSION.
Więcej wariantów nie jest potrzebne do obecnego limitu1+1 i wymaga przyszłej wersji.

Przygotowanie: nowy typed recipe decoder, validation, canonicalSHA, readiness,
sealed spec oraz TrainingPlan.binding. Preview zwraca exact recipeSHA, plan wariantu
oraz dodatkowy koszt/parity/runtime checks. Start z innym configiem wymaga nowego
preview, retry nie może podmienić wariantu. Dynamic recipeSHA jest odrębny od
niezmiennego trainingPresetFingerprint; oba są obowiązkowymi pinami nowej wersji.

## Typowanie i reuse preprocessingu bez bypass

Dodać nowy walidowany `ScreenInputGeometryV1` i `BoardCropGeometryV1`, zamiast
poszerzać ScreenPreset lub używać model_copy(update=...). Istniejące funkcje
screen_input / build_screen_item_with_indices oraz board_rectifier / build_board_crop
przyjmują opcjonalny keyword-only geometry override; brak opcji ma dotychczasową
ścieżkę bajtowo/RNG zgodną. Decoder configu konstruuje typ przez pełne model_validate.
ScreenPreset nadal dostarcza decode threshold/stride/targets; override dostarcza
wyłącznie wymiary. Board target transform używa tej samej zmienionej homografii,
co crop. Nie zmieniać canvas board, strat sieci ani architektury modeli.

ScreenGridBatches pozostaje tym samym loaderem: `variant_for_step(seed,step,recipe)`
wybiera jedną geometrię dla całego kroku, a istniejący sampler i step_rng zostają.
TRAIN data to tylko zakwalifikowane pełne zdjęcia. Sampling gier/grup zachowuje
równą wagę; exposure liczony pergame, nie tylko łączna liczba batchy.

Większy longSide nie dziedziczy automatycznie dowodu VRAM/throughput presetu768.
Preview ma jawny area-based estimate jako szacunek, a runtime readiness wymaga
sprawdzenia wariantu w istniejącym admission/lease/deadline. Nie powiększać czasu
ani kroków D581; brak zasobów/timeout/OOM to błąd, bez cichej redukcji rozdzielczości
lub batcha. Realny pomiar/trening wymaga odrębnej zgody; preflight go nie wykonuje.

## TRAIN → checkpoint → VALIDATION-A → export

1. Po rzeczywistym optimizer.step trainer dopisuje potwierdzone exposure wariantu
   (step, variantId, source/cohort SHA, game, stage). Samo zbudowanie batcha lub
   zadeklarowane planowane kroki nie są dowodem TRAIN. Statystyki i hash confirmed
   schedule/exposure są w nowym checkpoint state i history; resume je odtwarza.
2. Gdy checkpoint staje się best, zachować jego exposure snapshot. Export best_weights
   nie może użyć dowodu wariantu trenowanego dopiero PO bestStep. Wymagane co najmniej
   jedno potwierdzone użycie wariantu w każdej wymaganej grze i odpowiednim etapie;
   to dowód użycia, nie nowy próg jakości/statystyki. Exposure jest stage-specific;
   jego zgodność z runtime paths opisuje sekcja poniżej.
3. Na tym samym frozen selectionInput A, od oryginalnych zdjęć i dla dokładnie tych
   samych weights, evaluator mierzy baseline i ograniczoną strategię rescue1+1.
   Oba używają istniejących matching/metrics, ten sam zestaw gier/źródeł i GT.
   Reuse photo_evaluator/correction_evaluator przez wersjonowany opcjonalny adapter;
   żadnego drugiego trenera ani odrębnego źródła metryk. Wymagane actual invocation
   counts dla stosowanych etapów: pusty zestaw podejrzeń nie udowadnia działania cropa.
4. Przyjęta przez roota bramka dopuszczenia wariantu naA: rank T3 photo>board>-NME nie gorszy
   w żadnej wymaganej grze i ścisła poprawa w co najmniej jednej; przy remisie zostaje
   baseline i wariant inactive. Brak pełnych zdjęć, zakresu, exposure lub wykonanej
   walidacji => inactive z konkretnym powodem. Zatwierdzono tę decyzję;
   nie zmienia ona progów T4/automat30good+30bad ani publikacji modelu.
5. Eksportować dokładnie wybrany checkpoint. Dla jego weights wykonać/reużyć
   checksummed dowód A (jeżeli ostatnia ewaluacja dotyczy innych wag, nie używać jej).
   T3 all-validation-v1 jest jawnie selection-exposed A-purpose, nie niezależnym B;
   T4 dostarczy osobny frozen A/B input. REGRESSION nie wybiera wariantu/checkpointu.
6. ONNX export istniejących grafów + rzeczywista parity na baseline i zadanym wariancie
   (screen w obu orientacjach/kształtach użytych wA, board crops z nowym margin), istniejący
   relative threshold1e-4. Fail parity => brak dopuszczonego wariantu, nigdy success
   z brakującym dowodem. Export/recovery sprawdza recipe/proofSHA i bestWeightsSHA.

## Obowiązkowy proof faktycznych kombinacji runtime

Jedna konfiguracja L/M nie jest trzema wariantami parametrycznymi. Ma do trzech
kombinacji wykonania; każda dopuszczona kombinacja ma własny path proof:

| pathId | Detector | Crop podejrzanej planszy | Dodatkowe wywołania |
|---|---|---|---|
| `screen_only` | jawny wariant longSide L | BAZOWY margin M0, quad z redetect | <=1redetect/photo i <=1crop/slot |
| `board_only` | BAZOWY longSide768 i istniejąca detekcja | jawny wariant margin M | 0redetect, <=1crop/slot |
| `combined` | jawny wariant longSide L | jawny wariant margin M, quad z redetect | <=1redetect/photo i <=1crop/slot |

Runtime nie może najpierw wykonać screen_only cropa M0, a potem dodatkowego cropaM
tego samego slotu: to dwa cropy. Path jest przypięty przed pierwszym dodatkowym
wywołaniem. Nie ma przejścia screen_only→combined po ocenie wyniku. Jeśli redetect
nie przyniósł jednoznacznego quad i runtime chciałby użyć pierwotnego quad z marginM,
to jest board_only path: wymaga ODRĘBNEGO proof i dopuszczonego, przypiętego routing
przed cropem; najprostsza implementacja kończy taki combined attempt jako manual.
Nie traktować tej gałęzi jako udowodnionej przez forced combined.

### Pokrycie TRAIN

Obecna NeuralGridNetwork posiada osobne parametry screen i board (dwa niezależne
subnety). Dlatego można reuse deterministic baseline/variant schedule bez trzech
osobnych treningów: zapisywać exposure komponentów screen(base/L) i board(base/M)
z fingerprintem preproc/loss/target-transform, liczbą potwierdzonych kroków,
pergame source/cohort SHA oraz maxStep<=bestStep. Dowód `stage-composed-train-v1`
wiąże każdy path z wymaganymi komponentami:
- screen_only: screenL + boardM0,
- board_only: screen768 + boardM,
- combined: screenL + boardM.
Nie twierdzić, że wystąpił joint batch screenL+M0, jeśli użyto wyłącznie faktoryzacji.
Inspector weryfikuje typ tego dowodu i niezależność/pin architektury subnetów.
Jeśli przyszła architektura/augmentacja wprowadzi zależność między tymi komponentami,
nie wolno stosować tej wersji proof bez rzeczywistego exposure odpowiedniego path.

### Pokrycie VALIDATION-A, eksport i koszt

Dla każdego REQUESTED runtime path rzeczywiście uruchomić ograniczoną strategię
na tych samych pełnych oryginałach A z tym samym checkpointem. Baseline jest wspólne;
pathId w dowodzie wiąże effective screen longSide, margin, trigger/routing policy,
binding/ambiguity rules i actual stage calls. Forced analiza tylko L+M nie wystarcza
ani dla screen_only, ani board_only, ani ich warunkowego routingu.

Wyniki, actual invocation counts, source-setSHA, GT revisions i decision pergame
są osobne dla każdego path. Każdy path spełnia przyjętą bramkę A niezależnie.
Walidacja baseline+do3kombinacji to najwyżej4 oceny A na checkpoint, a nie sweep
parametrów; uwzględnić to w estimate, eval interval i kumulatywnym D581 budget.
Nie wolno oznaczyć nieprzeprowadzonej oceny PASS po wyczerpaniu budżetu.

Eksport zapisuje `pathProofs` mapę i jawny `selectedPath`. W minimalnej wersji runtime
wykonuje tylko ten jeden wybrany naA path; inne proofy są dowodem rozważonych
kombinacji, nie pozwoleniem na lokalne improwizowane przełączanie. Wygrywa rank T3
z równymi wagami gier; remis z baseline=>brak aktywnego path. Równe ranki dwóch
poprawiających paths rozstrzyga stała wersjonowana kolejność pathId (wyłącznie
techniczna deterministyka), zapisana w selection evidence. Późniejszy złożony
routing wymaga własnego walidowanego routing proof, nie samej unii trzech PASS.

Parity/graph proof obejmuje każdy effective input path: screenL dla screen_only i
combined; board M0 na quadzie wariantowego detektora oraz boardM na quadzie bazowym
i wariantowym. Dopasowane identyczne component tensors mogą reuse ten sam
checksummed parity result, lecz mapping path→result jest jawny; sam fakt wspólnego
ONNX nie daje PASS dla wszystkich wejść. Training exposure samo nie daje parity.

Inspector żąda proof wybranego path i komponentów, exact A weights/input hashes oraz
parity. Brak choć jednego elementu => ten path niedopuszczony. W pełni poprawny
proof tylko combined może aktywować combined bez fallbacku do board_only; nie
aktywuje automatycznie pozostałych dwóch. Unknown pathId zawsze fail-closed.

## Pakiet dowodu i inspector

Najmniejsza zmiana artefaktów: baseline bundle/preset nadal opisuje768 i320x192;
nowy wersjonowany OPTIONAL `bundle.rescue` zawiera recipe i `grid-rescue-evidence-v1`.
Jest to jawny opt-in kontrakt, nie interpretacja starego ScreenPreset. Dla braku
rozszerzenia engine zachowuje poprzednią ścieżkę. Nie trzeba dodawać nowych plików
do zamkniętej listy czterech inference/training artifacts katalogu.

Dowód zawiera: recipe/variantSHA, runId, bestStep, weightsSHA, checkpointSHA,
trainingPresetFingerprint, cohort/joint manifestSHA, exposure do bestStep,
selectionInputSHA/purpose/source-setSHA/group proof, pergame baseline/rescue metrics,
actual stage counts per runtime path, pathProofs/selectedPath/routingSha,
decyzję/ruleVersion, SHA obu grafów, path parity i shape limits.
NIE zawiera hash własnego bundle (unikamy cyklicznego SHA). Zewnętrzny katalog
wiąże całość SHA bundle; training-base receipt zawiera identyczne bundle bytes.

`GridModelArtifactInspector.inspect_rescue` (nowa metoda, zwykłe inspect bez zmiany
semantyki legacy) najpierw używa inspect, potem czyta bounded bundle.rescue i strict
versioned validator. Sprawdza relacje z rzeczywistymi sealed run/export receipts,
registered descriptor i existing cohort/use/currentness proof; nie ufa fladze
trained=true/passed=true przekazanej przez klienta. Hash dowodzi integralności,
nie ludzkiego GT ani niezależności. Unknown version, hash/pin/proof drift, missing
stage evidence lub niezgodne weights => brak dopuszczenia, jawny reason.

Przed runtime ONNX inspector sprawdza faktyczne input names/dtypes/dimensions:
screen float32 N3HW ze spatial dynamic albo dokładnie obsługiwanym kształtem;
board spatial dokładnie exportcanvas320x192 i legalny batch. Dla każdej fotografii
padded H/W muszą wejść w zadeklarowane/proven shape bounds64..2048 i limit pamięci
operacji. Sam longSide<=2048 nie wystarcza dla skrajnego aspectratio (short side32).
ONNX symbolic dimensions nie są dowodem poprawności; konieczne shape checks i parity.

Nowa operacja przypina variantId + bundleSHA + proofSHA + rescuePolicy, pobrane
wyłącznie z wyniku inspect_rescue. Stare operacje bez pinu pozostają bez rescue.
Zmiana modelu/konfiguracji wymaga nowej operacji, nigdy nowego budżetu w resume.
Brak kwalifikowanego wariantu dziś => allowedVariants=[], ale poprawny przyszły
run/exposure/A/parity/export da rzeczywiście wykonywalny variant, nie specjalny stub.

## Runtime i trwała rezerwacja 1+1

Wydzielić wewnętrzne etapy istniejącego NeuralGridEngine:
- screen-only detect z nowym ScreenInputGeometry,
- board-only crop/decode/fit jednej jawnie przypisanej planszy z BoardCropGeometry.
Legacy analyse składa te same etapy bez override i musi mieć test zgodności wyjścia.
CPU runner dostaje nowy zamknięty request kind, wariant pin i opcjonalny target quad;
start-up/time/cancellation/cleanup nadal istniejące. Nie wykonywać pełnego analyse
jako ukrytego redetect. Nigdy crop innych niepodejrzanych plansz.

Budżet scope: istniejący operation/jobID + sourceSHA, a dla cropa stabilny positionIndex
z potwierdzonego bindingu. Klucz budżetu NIE zależy od nowego variantId/modelSHA;
piny są treścią kontrolowanego envelope, żeby podmiana konfiguracji nie utworzyła
nowego licznika. Przy braku jednoznacznej tożsamości pozycji: manual, bez zgadywania
lub przeszeregowania numerów według nowej listy detekcji.

Stany append-only: available -> reserved -> completed albo failed/unknown.
Przed wysłaniem requestu CPU zapisać wyłącznie tworzony reservation receipt do
istniejącej przestrzeni trwałych artifact/checkpointów, fsync i odczyt kontrolny.
Deterministyczne keys: source/redetect i source/position/crop. Istniejący receipt
reserved bez wyniku oznacza zużytą próbę po crashu, nie pozwolenie na ponowienie.
Result jest osobnym immutable plikiem z SHA i wskazaniem reservation; restart adoptuje
wynik. Single-writer lease/fence + exclusive publication zapobiegają równoległym
podwójnym wywołaniom. Unknown/corrupt receipt => fail-closed, nie reset do0.

Dla page preflight trzeba rozróżnić started source od completed entry: obecne
`if sourceSHA not in entries` nie może omijać źródła tylko dlatego, że zapisano
reservation. Dla reinference receipt leży pod tym samym immutable operation path
co raw/checkpoint, a cache identity zawiera dodatkowy rescue pin. Budżet odzyskiwać
z reservation, nie liczyć samych gotowych wyników. Retencja zgodna z checkpointem.

Redetect<=1/photo. Nowe quady kojarzyć jednoznacznie z dotychczasowymi stable slots;
konflikt/sąsiad/ambiguity => manual. Następnie max1 dodatkowy crop na podejrzany slot.
Zmiana detectionId po redetect nie daje drugiego crop tokena. Gdy screen override
brak, margin-only może przejść od razu do jednego recrop. Błąd/incomplete wyniku po
obu próbach => manual; dowody T0/T4 nadal kwalifikują wynik, rescue nie autoryzuje go.

## Testy wymagane (plan, niczego nie wykonano)

- Legacy ScreenPreset odrzuca longSide!=768; nowy typ waliduje jawny wariant, rejects
  invalid/NaN/extra config. Brak model_copy/update bypass.
- Baseline output/RNG/fingerprint bez zmian, trening wariantu rzeczywiście zmienia
  screen shape/board margin i target transform; whole-step shape i equal-game sampler.
- Resume ma identyczny schedule/exposure; bestStep przed first exposure => brak proof.
- Snapshot/core trainer wykonuje faktyczny optimizer step na małym CPU fixture;
  brak testu, który sam wpisuje trained=true. Pełny GPU/operator run poza tym taskiem.
- A evaluator faktycznie wywołuje screen-only/base-margin, board-only/base-screen
  i combined fixture jako osobne paths; proof forcedcombined nie aktywuje pozostałych.
  Spy sprawdza rzeczywisty longSide/margin, quad provenance oraz <=1crop/slot.
  Nieznany/nieoceniony path, brak component exposure lub routing proof=>fail-closed.
- A evaluator korzysta z przypiętej konfiguracji;
  REGRESSION spy niewywołany; stale/mismatched weights/input/proof odrzucone.
- Kontrolowany test export/ONNX CPU parity dla dwóch screen shapes i niezmienionego
  boardcanvas; brak testu opierającego PASS wyłącznie na dynamic_shape deklaracji.
- Bundle proof roundtrip, inspector rzeczywistych plików/receipts, hash drift,
  unknownversion, brakA lub brakTRAIN => empty; poprawny proof => execute variant.
- Crash/lost response przed i po reservation/CPU/result/checkpoint, drugi proces,
  dwa claimanty: counter nigdy>1+1, zużycie nigdy nie spada. Nowy detectionId nie resetuje.

## Przyjęte decyzje i granica T4

Zatwierdzono max1jawnyvariant/run i bramkę A: brak pogorszenia każdej wymaganej
gry oraz poprawa co najmniej jednej; remis z baseline daje inactive. Faktyczne
kombinacje screen_only/board_only/combined wymagają opisanych własnych dowodów.
Decyzje trafią do D-entry po T2; D-586 zarezerwowano po sprawdzeniu numeracji.

Wspólnie z wykonawcą T4 uzgodniono odrębny `human-labeled-targets-v1` assessment
reference nad tym samym readerem i ledger: częściowe B/REG służą do oceny opisanych
GTcelów niezależnie od trainingMode kandydata; whole-photo/FP/duplicates tylko full.
Screen TRAIN/checkpointA nadal full, starych polityk nie zmieniamy. Nowa ścieżka REG
ma5photos/15GT i requiredFullREG=0; optimizer jej nie czyta. Assessment nie filtruje
policzonych partial ani nie modyfikuje starych snapshotów. Reference wiąże exact
cohort/member/source/target/revision/sourceSetSHA i role-purpose/selectionExposure.

Warianty asymetrycznych perturbacji są oddzielne: bez pomiaru T1 nie dodajemy
amplitudy. Jawny longSide/margin nie jest parametrem empirycznie wyznaczonym.


## Risks / open questions

Brak pełnych danych rzeczywistych blokuje screen run i aktywne rescue proofs, nie implementację.
Brak GT462205 nie uprawnia do wymyślonej amplitudy asymetrycznych perturbacji.
Migracja operatora wymaga osobnej zgody. Pierwszy rzeczywisty trening wymaga danych i osobnej zgody.

## Final implementation decisions

`historicalCohorts` replaces only an already required other game's cohort. D-586
records the accepted choice: exact family/base/currentness/full TRAIN+A, no scope
addition/removal/latest selection. Old commands with absent additive defaults replay
unchanged. New pins include selected cohort/SHA/currentness/selection input.

Legacy screen snapshots without photoSplit-v3 return
SCREEN_HISTORY_CORRECTION_POLICY_REQUIRED before indexing. They are not rejected as
bad labels. Existing independent prepare/capture/materialize/freeze with policyVersion
application-grid-corrections-v3 reuses qualified GT and frozen roles, without mutating
old snapshots or starting shared training. This avoids A/B games blocking each other.
T5 exposes the existing preparation action in advanced settings. The compatibility
matrix and exact T4/T5 handoff are in the verification report.

New routing proof remains fit-or-pixels-v1; arbitrary completeness callback returns
manual/proof-required. T4 must introduce and validate a new routing version on TRAIN/A,
not tune routing on B. Receipt projection preserves actual preprocessing/OpenCV and
effective geometry; reserved-only state does not claim an analysed input.

## Outcome

Commit: v1.7.562 / `f78c5b5a1a6dcbc1c0d280a0f4d2204417e5d9a3`.

### Changed

Completed new screen correction policy/snapshot/preset, role-specific full TRAIN/A
and partialREG, exact checkpoint input/exposure/resume, explicit historical cohort
selection, additive API/OpenAPI/SDK/wrapper, report-v4, migration0180 and actual
recipe→TRAIN/A→ONNX proof→artifact inspector→durable1+1 runtime path. Reused existing
network/trainer/evaluator/preprocessing. Legacy contracts retain their interpretation.

### Verification results

See [TASK-1157 verification](../../quality/TASK-1157_VERIFICATION.md) for exact commands,
counts, corrected fixture failures, scoped type limitations and T4/T5 interfaces.
Final API/worker set67 PASS; targeted HTTP3 PASS; wrapper4 PASS; CPU ONNX2 PASS;
proof/inspector/runtime3 PASS; disposablePG migration1 PASS, role closure2 PASS,
independent second-cohort lifecycle1 PASS. Counts overlap and are not added.
Client typecheck PASS. Admin uses isolated strict WT SDK paths, not standard workspace
resolution. Scoped mypy57 modules: zero new errors; one pre-existing object iteration
error confirmed with shadow HEAD (line199→228), torch/torch.* skipped only in temporary
config. No global mypy PASS. Ruff/generated/docs/map results recorded in report.
Actual Opus5.5/high R1 PASS (0P0/P1,5P2), preserved in TASK-1157_AUDIT_ROUND1.md.
Coordinator reclassified normal-crash recovery as durability P1. The single correction
round adds atomic no-replace receipt publication, conservative same-byte alias scope,
real reader/capture hash composition and documented P2 cost/pipeline semantics.
Correction tests21+1 PASS; scoped Ruff and runtime mypy PASS. Exact findings and
limitations are in verification. Focused Opus5.5/high R2 PASS,0P0/P1; coordinator
P1 closed. [R2 report](../../quality/TASK-1157_AUDIT_claude-opus-5-5.md),
[preserved R1](../../quality/TASK-1157_AUDIT_ROUND1.md). No third round.
Before commit, code/non-doc SHA matched frozen R2; final edits are documentation only.

### Not completed

P2-3 sync inspection cost and unavailable
archived reason accepted pending measurement; T5 must show unavailable/unknown.
No operator database writes/migration, services,
operator-data training/inference, GPU, default/assignment, activation, merge or push.
The last bounded T1 reading (full0) still blocks actual detector/rescue qualification;
no fresh operator-data scan was performed.
R2 P2-6 accepted: alias completed receipt entries belong to the original scope and
were not applied to this occurrence. T5 must show another scope, never its actual input.
R2 P2-7 accepted: NTFS/hardlinks required (root read-only D: check confirmed NTFS),
no directory-fsync/power-loss guarantee, orphan temp GC outside scope. No contract change.
No GT462205/amplitude was invented; old jitter remains. No calibration quality claim
is made from synthetic protocol tests. T2 residual P2 remain documented there.

### Documentation updates

D-586, requirements/architecture VISION_LAB, plan consent, compact CURRENT_STATE pointer,
code map and verification/handoff. Active task retains accepted preflight decisions.

### Recommended next task

TASK-1158 / T4 after ownership handoff from root. Use the exact versioned
assessment/routing/receipt interfaces in the verification report.
