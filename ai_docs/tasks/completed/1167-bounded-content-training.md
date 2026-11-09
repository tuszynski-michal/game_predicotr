---
title: Kontrolowane warianty treningu zawartości i ratunku
status: done
last_updated: 2026-11-09
---

# TASK-1167 — Kontrolowane warianty treningu zawartości i ratunku

## Status

`done`

## Goal

Istniejący trwały proces wykonuje ograniczony eksperyment R0–R3 z nowymi
celami, rzeczywistą oceną i wytrenowanymi wariantami ratunkowymi.

## Dependencies / entry conditions

2026-11-09: rzeczywisty focused Opus5.5/high R2 PASS0P0/0P1.
Pakiet03ae9457..., raport i receipt w quality/TASK-1167_AUDIT_claude-opus-5-5.*.
Pierwszy transport R2 przerwał rzeczywisty Anthropic429; po wskazanym resecie
wznowiono ten sam pakiet jako transport2, bez zmiany F snapshotu. Root
potwierdził139 frozen product/context sources w chronionym tree d0ba8e63.
T5 rozpoczęto osobno zgodnie z jawnym wyjątkiem operatora przy limicie Opus;
nie jest częścią tego commita. P2-4/5/6 przekazano do odbioru T5, P2-1
koszt inspektora pozostaje zaakceptowanym ryzykiem.

T1–T3. Implementacja bez rzeczywistego treningu operatora; gotowość
danych/budżetu sprawdzana i raportowana, nie symulowana jako PASS.

Warunek T3 spełniony: v1.7.575/ac724d297448785bdcb98b17dc6a3d5e3fc104e5,
rzeczywisty Opus R2 PASS0P0/0P1. Założenie wykonawcze zgodne z Technical notes:
jeden istniejący parent i jeden training child z zamkniętym planem ramion,
bez drugiego trenera/usługi i bez czterech odnawianych budżetów.
Wykonawcy Astra/high rozdzieleni: worker orchestration/dataset/runtime,
training core/network/export oraz API/command plumbing. Decyzję D-592
i wspólne piny interfejsu rejestruje root przed nową zmianą domenową.

## Recommended execution

gpt-6-astra/high; Claude Code claude-opus-5-5/high.

## Relevant docs

- AGENTS.md
- ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md (T4)
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/decisions/DECISION_LOG_2026.md (D-581/586/587)
- ai_docs/process/decisions/DECISION_LOG_2026.md (D-589/590/591; kontrakt24/15, human content, produkcyjna ocena)
- ai_docs/process/decisions/DECISION_LOG_2026.md (D-592; zamknięty plan/budżet/ranking/eksport T4)
- ai_docs/quality/TASK-1166_AUDIT_claude-opus-5-5.md (P2-6 handoff)
- ai_docs/architecture/CODE_MAP.md

## Scope

Dokładnie cztery maksymalne ramiona i budżety T4, bez drugiego trenera.
Bank błędów tylkoTRAIN/rodowód/SHA. Cele/maski i trzy próby jitter→skip.
Nowe batchnorm_stats bez zmiany starego tokenu. R2 screen768/1280,
board320×192/.15 i480×288/.30, równy udział. R3 pomocnicza głowica15
obwiedni i lokalnej widoczności wyłącznie po niezaliczeniu A przezR2.
R0/R1 bez niewytrenowanego rescue. 1redetekcja/zdjęcie+1crop/boardsuspect,
jednoznaczność, osobne progi i końcowa ocena zamrożonego routingu.

## Acceptance criteria

- [x] Przypięte base/dane/seed,1200kroków/ramię,1500/1500/2100/2100s, suma7200s.
- [x] Preflight i pełna rezerwa przed startem; niepełne ramię nie jest wybierane.
- [x] Ranking A/co200kroków i koniec, równa waga gier, REG nie stroi.
- [x] Checkpoint/resume zachowuje stan earlystop/rank/zużycie; replay nie duplikuje.
- [x] Bank nie korzysta z A/REG ani użytych przez przodka źródeł.
- [x] R3 wymaga właściwych zatwierdzonych etykiet, nie klasyfikuje symboli.
- [x] Rescue dostępny tylko po treningu/ocenie, jeden dozwolony routing.
- [x] B/REG30dobrych+30błędnych rzeczywistych źródeł per gra/ścieżka dla automatu,
  próbka zamknięta przed zwycięzcą, brak→unqualified, nie dobieranie po wynikach.
- [x] Prawdziwy test ONNX i zgodności wejść, trwałość/PG/scopedchecks i audyt.

## Technical notes

Handoff T3/R2 P2-6 (przyjęty residual):
`grid_model_evaluation_handler.py::_verify_details` musi sprawdzać limit96MiB
przed read/parse, także gdy przekazuje verified_details do finish. Końcowe
sprawdzenie całej operacji ma weryfikować hashe bez parsowania i trzymania
dokumentów wszystkich gier/legacy. Nie rozdzielać ponownie zweryfikowanych
bajtów od dokumentów użytych do finish. Test nadmiarowego rozmiaru wykonać
przy małym, przypiętym w fixture limicie, bez alokacji wielkiego pliku.
R2 T3 pozostał PASS0P0/0P1; to praca do wykonania i audytu T4.

Przygotowanie read-only 2026-11-08; implementacja po T3. Fakty z kodu i
zalecany minimalny pion, bez drugiego trenera:

- Istniejący `GridCorrectionLearningPanel.send` utrwala exact command w
  localStorage przed `startGridCorrectionLearning`. Ten sam wrapper/endpoint
  preview/start prowadzi do `GridCorrectionLearningService.advance`, freeze
  kohorty, jednego `GridTrainingRunService.create` i jednego joba ewaluacji.
  Parent zwalnia lease przy oczekiwaniu; deterministyczne `child_key` zachowują
  tożsamość po utracie odpowiedzi. Nowy jawny opt-in eksperyment musi przejść
  cały ten pion, łącznie z readiness, command hash i wyświetlonym stanem;
  same helpery ani sam preset nie realizują taska. Wygląd panelu dopracowuje T5.
- Zalecany zakres: jeden istniejący training child z wersjonowanym planem
  R0–R3 i stanem ramion w jego durable checkpoint, wspólnym nadzorcą oraz
  jednym globalnym budżetem. Nie tworzyć czterech niezależnych limitów 7200 s.
  Każde ramię ma własne checkpointy/eksporty pod wspólnym plan SHA, te same
  base weights, kohorty i seed; R1/R2/R3 nie startują z wyniku poprzednika.
  Rejestracja/publikowalny kandydat dotyczy wyłącznie wybranego pełnego ramienia.
- Plan przypina maksymalnie cztery ramiona, dokładnie 1200 planned steps każde,
  ocenę A co200 i na końcu, rezerwy 1500/1500/2100/2100 s, razem7200 s
  z walidacją. Admission środowiska/rezerwy przed GPU; rzeczywisty pomiar
  w tej samej dzierżawie przed pierwszym optimizerem (D-592). Brak wykonalności/rezerwy
  zatrzymuje start, bez obniżenia planu. Arm complete wymaga wykonania1200;
  earlystop/ranking zachowuje trwały stan, lecz wcześniejsze przerwanie nie
  może udawać ukończenia ani dopuścić wyboru ramienia.
- `RunBudget` i supervisor już naliczają czas/rezerwują kroki oraz odzyskują
  osierocone próby. Nowy stan musi zachować globalne zużycie, per-arm rezerwę,
  selectedArm/bestStep, RNG/optimizer/scaler/ranking, pointery i immutable
  manifests po restarcie i utracie odpowiedzi. Nowa polityka nie może przez
  `training_budget_limits` dostać historycznego minimum8000/7200 dla każdego
  ramienia. Wznowienie nie odnawia rezerwy ani limitu; ten sam klucz nie
  tworzy drugiej próby/eksportu. Ścieżki legacy zachowują D-581.
- R0 używa gotowych celów/masek T1 i zweryfikowanych frozen refs T2. Opt-in
  `supervised_board_crop` już losuje jitter do3 razy, potem daje zerowe maski;
  trzeba jawnie liczyć skip i nie potwierdzać nieistniejącego board optimizer
  exposure. Legacy `build_board_crop` nadal ma GT fallback: nie wywoływać go
  dla nowego eksperymentu i nie zmieniać starej wersji po cichu. Zachować
  wspólne dotychczasowe heavy-occlusion i poprawne targety support.
- R1 dodaje odrębny token `batchnorm_stats`: running stats w eval/frozen,
  affine weight/bias nadal z gradientem, także po każdym `network.train()`.
  Stary `batchnorm` zamraża oba i pozostaje bez reinterpretacji.
- R2 ma jawny równy udział screen768/1280 i board320×192/.15 oraz480×288/.30.
  Obecny `variant_step` przeplata wariant/bazę, ale `BoardCropGeometryV1`
  zmienia tylko margin; `export_graphs` i `RescueParity` mają statyczne192×320.
  Potrzebny rzeczywisty kontrakt canvas v2 przez augmentation/preprocessing,
  loss, inference, export, inspector i runtime. Dopuszczalne osobne przypięte
  grafy lub rzetelnie dynamiczny ONNX; każda używana konfiguracja wymaga
  rzeczywistej parity na właściwym rasterze, nie jedynie metadanych.
- R3 jest zadeklarowane w planie przed wynikami, uruchamia się wyłącznie po
  niezaliczeniu gate A przez ukończone R2, z pełną rezerwą i zatwierdzonymi
  TRAIN content labels. Nowa pomocnicza głowica15 obwiedni/lokalnej widoczności
  ma rzeczywiste wejście feature/loss/maski/gradient i provenance w modelu.
  Obecne globalne `BoardNetwork.visibility` nie jest taką głowicą. Nie dopisywać
  sztucznych15 wyjść, klas symboli ani heurystycznego przesuwania siatki.
  Dokładny kształt pomocniczej głowicy i jej eksportu przypiąć przed ramionami;
  nie zmieniać kontraktu R0–R2 ani starych checkpointów.
- Bank błędów mierzy zamrożoną bazę3ed60010 na TRAIN; wymaga pozytywnego
  dowodu ancestor-unseen przez istniejący lineage/provider/ledger i closure
  kopii. Sam brak modelId w pomocniczej liście nie wystarcza. Unknown ancestry
  lub niedobór blokuje bank i wymaga nowych TRAIN, bez A/REG/OoF. Przypiąć
  źródła, role, rodowód, wynik bazowy i SHA banku przed optymalizacją.
- Nowy evaluator checkpointów korzysta z T3 finalContentState i stałych
  instancji. Ranking wyłącznie A: średnia po grach liczby nowych uszkodzonych
  stałych komórek (unia state/wrong/tie/foreign/match ambiguity) przez visible,
  więcej użytecznych zdjęć, potem plansz, mniejszy NME, prostsze ramię,
  wcześniejszy krok; równa waga gier oraz gate każdej gry. `selectedArm` i
  `bestStep` wskazują ukończone ramię i jego faktyczny checkpoint/exposure.
  Stary `ScreenCorrectionEvaluator` optymalizuje photo/board/NME i porównuje
  kilka paths, więc nie może bez zmian udawać nowej reguły.
- Rescue-v2 to jeden zamrożony routing: najwyżej1 redetect1280 na zdjęcie,
  współdzielony przez plansze, i1 crop480×288/.30 na podejrzaną pozycję.
  Niejednoznaczność prowadzi do człowieka; bez sweepu screen_only/board_only/
  combined. R0/R1 bez treningu wariantu nie mają rescue. `TrainingExposure`
  musi potwierdzać konkretne rozmiary po rzeczywistym optimizer step, do
  bestStep; obecny receipt `RescueAttemptStore` nadal rezerwuje przed CPU,
  a crash bez wyniku zużywa próbę. Cache/piny obejmują wariant, raster i support.
- Roster B/REG (osobno losowy i trudny) jest zamknięty przed wyborem zwycięzcy;
  nie oznacza to dostępu optymalizatora do GT B/REG. Po wyborze A zamrozić
  routing/model, B dobiera tylko osobne progi wariantu/ścieżki, REG raz
  weryfikuje zamrożony wynik. Automat wymaga w B i REG po30 rzeczywistych
  dobrych i30 błędnych źródeł po kopiach per gra/używana ścieżka. Nie przenosić
  peak progów między rozdzielczościami i nie dobierać źródeł po wynikach.
  Brak danych pozostaje unqualified, nie zakaz inaczej dopuszczonego treningu.

Blokery wejścia do implementacji: gotowe T1–T3 kontrakty i strict readers,
zamrożony format dowodu TRAIN banku oraz A/rosterów, wersjonowany plan/preset
i jego durable envelope. Faktyczny dostęp do danych/rodowodu, etykiet R3,
wydajności R2/R3 i rezerwy pozostaje warunkiem przyszłego operator-run;
analiza nie dostarcza takich dowodów ani zgody na GPU.

Domknięcie AC8: pełne zasady i nazwy zapisano przed kodowaniem w D-592.
Wspólny interface wykonawców: `artifacts/TASK-1167_AC8_INTERFACE.md`.
Nowe domain context/calibration i worker context/run adapter realizują
niezależne progi, pełny roster/null→unqualified oraz parentprofilev3 i
result-evidencev3. Maksimum512 liczbowych konfiguracji/game (256/child),
bez dodatkowych NNcalls; historyczne formaty pozostają bez zmian.

## Expected files

Wszystkie ścieżki względne do repo; nazwy nowych wersji są proponowane.

- API `services/api/src/game_predictor_api/api/grid_correction_learning.py`,
  `schemas/grid_correction_learning.py`, `application/grid_correction_learning.py`
  (`_preview/start/advance/resume/view`), `application/grid_training_runs.py`
  (`create/resume/view`), `schemas/grid_training_cohorts.py` — preview/start,
  immutable plan, parent/child pins, readiness i postęp.
- `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx::send`,
  `grid-correction-learning-state.ts`, `packages/admin-api-client/src/index.ts`
  i generated/OpenAPI — realny przycisk i exact retry nowego polecenia;
  UI szczegółowego odbioru pozostaje T5.
- Worker `services/worker/src/game_predictor_worker/images/grid_correction_learning_handler.py`,
  `grid_training_handler.py::RunState/GridTrainingJobHandler`,
  `grid_training_child.py::_train/_export` — jeden trwały workflow, piny
  planu/ramion, wspólne zużycie, odzysk i eksport zwycięzcy.
- Worker `training_core/grid_training_admission.py::GridTrainingPreset/RunBudget/evaluate_admission`,
  `grid_training.py::apply_freeze/TrainingPlan/EarlyStopping/train/export_graphs`,
  `checkpoint.py`, `grid_rescue_training.py::TrainingExposure` — wersjonowane
  budżety, BNstats, ranking,1200/co200, resume/exposure.
- Worker `images/grid_training_data.py::ScreenGridBatches/photo_evaluator`,
  `training_core/grid_visibility_targets.py::supervised_board_crop`,
  `training_core/neural_grid_augmentation.py`, `training_core/neural_grid_network.py`
  — T1/T2 cele, skip, rzeczywiste wejścia R2 i auxiliary head R3.
- Worker `geometry_core/rescue.py`, `geometry_core/preprocessing.py`,
  `geometry_core/inference.py`, `images/grid_rescue_evaluation.py`,
  `images/grid_rescue_export.py`, `images/grid_rescue_strategy.py`,
  `images/grid_rescue_runtime.py`; API `domain/grid_rescue_policy.py`
  — canvas v2, real ONNX/parity, jeden routing i nieodnawialne1+1.
- API `domain/source_recording_groups.py::resolve_ancestor_references`,
  `application/grid_correction_history.py`; frozen T2 readers i T3 evaluator
  oraz `images/full_board_calibration_run.py` — bank TRAIN/ancestor proof,
  nowe metryki A, roster B/REG i kalibracja. Nie tworzyć drugiego ledgera ról.
- Proponowany mały moduł `training_core/grid_content_experiment.py` dla
  zamkniętego planu/stanów/rankingu, jeżeli ograniczy rozrost istniejących
  handlerów; nie jest samodzielnym trenerem ani zastępstwem integracji.

Sprawdzone testy do rozszerzenia (nie uruchomiono): worker
`test_grid_correction_learning_handler.py`, `test_grid_training_handler.py`,
`test_grid_training_child.py`, `test_grid_training_resource_admission.py`,
`test_durable_v3_grid_training.py`, `test_shared_grid_training.py`,
`test_grid_visibility_contract.py`, `test_vision_lab_training_core.py`,
`test_screen_rescue_contract.py`, `test_screen_rescue_proof.py`,
`test_screen_rescue_onnx.py`; API `test_grid_correction_learning_api.py`,
`test_grid_training_runs.py`, `test_grid_training_run_preview.py`;
disposable PG `test_grid_correction_learning_postgres.py` i
`test_grid_learning_v4_postgres.py`; klient
`packages/admin-api-client/test/grid-correction-learning-request.test.mjs`;
Admin `test/grid-correction-learning-state.test.mjs` i
`test-interactions/grid-correction-learning-panel.test.mjs`.
Nowe testy ramion muszą wykazać wspólny limit/restart, pełne1200,
samebase/seed, gated R3, ancestor-unseen bank, ranking T3, osobne wejścia i
rzeczywisty ONNX oraz UI→API→job; nie tylko zgodność helperów z własnym kodem.

Przy `batchnorm_stats` ponowne wejście w training po walidacji musi nadal
zamrażać running statistics, zachowując gradient affine. Test powinien przejść
train → validation → train; samo ustawienie eval na początku nie wystarcza.
Przypięta baza eksperymentu pochodzi z zaakceptowanej specyfikacji planu/runu;
nie wprowadzać stałego UUID bazy jako uniwersalnego defaultu przyszłych treningów.

## Test cases

Gradient affine i zamrożone statystyki, legacybatchnorm; rotacja wejść i export;
nierozdzielny budżet, restart/utrataodpowiedzi, routingcacheperfoto, cutoffR3,
braketykiet i ukrytegoGTfallback; ścieżka bez kalibracji nie otrzymuje automatu.

## Verification

Scoped testy+ONNX+PostgreSQL, typy/lint/docs/map; bez operatorGPU.
Dokładne komendy i dowody w quality/TASK-1167_VERIFICATION.md.

## Outcome

Commit: v1.7.576 / `a9951e94f8cb7ad1912c1888f3f47eb94cb5efea`.

### Changed

- Istniejący preview/start/parent prowadzi do jednego childa z immutable planem
  R0–R3, wspólnym4800logicsteps/7200s, actual TRAIN bank proof, preflight,
  równogrowym A/PASS-first checkpointem i eksportem rzeczywistych best weights.
  Restart/lost response zachowują child, bank, zużycie i eksport; samo4800
  nie blokuje dokończenia eksportu. Niepełne ramię nie jest eligible.
- R1 zamraża statystyki BN z uczonym affine; R2 używa rzeczywistych dwóch
  rastrów, R3 nadzorowanej głowicy15quad/visibility z dodatnią ekspozycją doBEST.
  Actual ONNX/parity trzech grafów i obu canvasów ma osobne dowody. Bez danych
  nadzoru wymagane R3 blokuje przed preflight; zero-head nie staje się complete.
- AC8 jest pełnym pionem: actual BASE/WIDE, osobne v2 child plans/progi/minima
  w v3 envelope, A menu przedB, pełny frozen roster z null blocker, used union,
  independent physical API replay, operation pin i oddzielny inputVariant stamp.
  Current source/crop support sprawdzają oba rzeczywiste finalizery API.
  WIDE nie dziedziczy BASE. Pion backend/OpenAPI/SDK/wrapper/request zgodny.
- Handoff T3P2-6 zamknięty:96MiB bound przed parse, końcowy streaming hash
  bez trzymania wszystkich dokumentów. Legacy formaty i receipt identity
  zachowują znaczenie. Nie przepisano ręcznych korekt ani historii.

### Verification results

- Pełne komendy, wcześniejsze FAIL/timeout i granice fixture:
  `quality/TASK-1167_VERIFICATION.md`. Meaningful CPU workflow potwierdził
  3600/4800successfulsteps, resume650/1850/4550/4800 i export lost response;
  actual ONNX two-canvas/head proof oraz owned parent/cohort PG są oddzielne.
- AC8 actual observer→run→physical API replay PASS87,95s; NONE PASS71,15s;
  cold process→pin→runtime→finalizer PASS25,35s; default null/failedcrop oraz
  exact legacy receipts mają osobne PASS.64 kontrolowane małe JPEG/264 częściowe
  cele nie są danymi operatora ani5pełnymiREG dla T3 geometry gate.
- Nowy current-source read: disposable PostgreSQL PASS20,90s, cold explicit
  DBURL/name guard, application role i fresh cleanup0baz/0ról. Parent PG
  wcześniejszej fazy PASS68,63s; wcześniejsze timeout nie są przedstawione
  jako zaliczone. Nie wykonano operator DB.
- Scoped lint/format, SDK/Admin typy, OpenAPI/client checks i właściwe mypy
  przeszły kompozycyjnie. Jeden historyczny Row-vs-tuple w niezmienionej
  funkcji virtual repository odtworzono na exact HEADac724d29; brak pełnego
  globalnego mypy PASS. Nie naprawiano obcej regresji.
- Root docs:check i code-map:check PASS. Root verified frozen tree matches139
  produktowych/context źródeł pakietu. Staged shadow przeszedł4 kontrole dokumentacji i mapę kodu; dowód
  artifacts/TASK-1167_STAGED_VERIFICATION.json wyklucza trwającą deltę T5.
- Niezależny terminal Claude Code Opus5.5/high: R1 REVISE, jedna runda poprawek,
  R2 PASS0P0/0P1. ReportSHA dda8228daa5a8fdbbaef6567737a29e99aaa17f81584e9522966139e718df40c.
  Receipt/request SHA i wcześniejszy429 zachowano; high jest żądaniem CLI,
  main model potwierdzony przez init. Kod0 nie zastąpił odczytu raportu.

### Risks and remaining work

- P2-1: registry list/view wykonuje physical TRAIN+ONNX replay; latencji nie
  zmierzono. Owner przyszłego usprawnienia: registry inspection. Brak
  cache SHA-only omijającego aktualność plików. T3P2-1 pozostaje osobny.
- P2-4 bounded reader production_cell_input, P2-5 obca BASE pod slotem WIDE
  i P2-6 env-only cold regression są jawnie przekazane do T5 odbioru.
  Ten historyczny PASS nie twierdzi, że te delty są już w tym commicie.
- Nie uruchomiono rzeczywistego treningu/GPU, migracji operatora, usług,
  default/apply, importu691 ani merge/push. Brak operatorowych30+30 nie
  stał się kwalifikacją; jakość nowego rzeczywistego modelu nie jest zmierzona.

### Documentation and next task

D592, wymagania/architektura/API, mapa oraz raporty audytu/weryfikacji.
Następny TASK-1168 jest już osobno realizowany za zgodą operatora.
