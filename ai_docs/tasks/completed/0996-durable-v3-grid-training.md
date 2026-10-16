---
title: TASK-0996 — Trwały trening V3 w aplikacji
status: done
last_updated: 2026-10-16
---

# TASK-0996 — Trwały trening V3 w aplikacji

## Status

`done`

## Goal

Wykonać odtwarzalny run z checkpointem i wznowieniem.

## Context

Task jest częścią zaakceptowanej rewizji 6. Trener, checkpoint i wznowienie. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0995, TASK-1005, TASK-1012.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

Zmiana ról na jawne polecenie operatora2026-10-16 po ukończeniu TASK-0995: Claude Code wykonuje, Codex audytuje. Historycznych raportów i wykonawców ukończonych zadań nie zmieniamy.

- Wykonawca: `claude-opus-5-5`, reasoning `high` (zamiennik `claude-fable-5-1`/`high`; wybór wykonawcy po sugestii operatora 2026-10-16, uzasadnienie w sekcji 8 planu). stan treningu i maskowanie danych.
- Dodatkowy review: `gpt-6-astra`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Review high obejmuje trwały stan runu, checkpoint i dane dowodowe; zachowuje regułę AGENTS dla schematu/dowodów.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../../architecture/VISION_LAB.md).
- [VISION_LAB](../../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: VISION_LAB, architektura workera i kontrakt kohort.

## Scope

- Wydzielić wspólny rdzeń z istniejącego treningu.
- Grid-only zamraża detektor i BatchNorm.
- Obsłużyć lease, postęp, cancel/resume, eksport i trwały budżet.

## Out of scope

- Bez automatycznego rzeczywistego treningu lub aktywacji.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Restart odtwarza RNG/sampler/optimizer; crash po eksporcie nie dubluje wersji; uszkodzony checkpoint nie daje gotowego kandydata; lab i produkcja używają zgodnej logiki.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Wydzielić wspólny rdzeń z istniejącego treningu. Grid-only zamraża detektor i BatchNorm. Obsłużyć lease, postęp, cancel/resume, eksport i trwały budżet.

### Kontrakt przed kodem (2026-10-16, Claude Code)

Stan zastany (HEAD v1.7.387): trener laboratorium (`vision_lab/neural_grid_training.py`, `neural_grid_finetune.py`) wznawia dokładnie tylko na granicy rundy; `TrainingDataset` bierze RNG z niezapisywanego licznika wywołań, `MixedBatchSampler` nie ma stanu. `compute_losses` zawsze liczy detektor (`network.screen`). Brak zamrażania modułów i ważenia próbek. Eksport ONNX (`neural_grid_onnx.export_bundle`) i rejestr wersji (`GridModelRegistryService.register`, inspektor `training-base/`) istnieją. Środowisko `.venv-vision-lab` (CUDA) nie ma `sqlalchemy`/`psycopg`; główne `.venv` ma torch CPU. Worker `general` ma jeden slot i obsługuje importy.

Decyzja operatora 2026-10-16: osobny lane `grid_training`. Architektura (D-558):

- **Nadzorca** `images/grid_training_handler.py` działa w workerze lane `grid_training` (główne `.venv`, baza). Nowy `JobType.GRID_TRAINING`, `JobExecutionSlot.GRID_TRAINING = 3`, `WorkerLaneName.GRID_TRAINING`; migracja `0165_grid_training_lane` dodaje wartość enum, rozszerza `ck_jobs_processing_lease_fields` (porównanie `job_type::text`, bez użycia nowej etykiety w tej samej transakcji) i `ck_worker_lane_runtime_lane`. Lane `general` nie pobiera `grid_training`.
- **Trener** `images/grid_training_child.py` działa jako podproces w skonfigurowanym interpreterze GPU (`GAME_PREDICTOR_GRID_TRAINING_PYTHON`), bez bazy: czyta przypięty plik specyfikacji, trenuje, zapisuje niezmienne checkpointy, postęp i eksport w katalogu runu `<artifact_root>/grid-training/runs/<jobId>/`. Trzyma dzierżawę GPU D-557 (PID trenera) i kończy się sam, gdy znika nadzorca (PID i czas utworzenia) albo plik heartbeat nadzorcy przestaje się zmieniać przez 60 s.
- **Wspólny rdzeń** (neutralny, bez importów `game_predictor*`): `training_core/neural_grid_network.py` (sieć, eksport grafów i straty przeniesione z `vision_lab/neural_grid_model.py`), `training_core/neural_grid_augmentation.py` (`perturb_quad`, `photometric`, `screen_targets` z `neural_grid_data.py`), `training_core/grid_training.py` (pętla, sampler, RNG kroku, checkpoint, early stopping, zamrożenie, ważone straty, eksport ONNX i parity). Laboratorium reeksportuje przeniesione symbole; jego wyniki dla tych samych wejść pozostają identyczne (regresje laboratorium).
- **Receptura:** preset aplikacji D-557 + parametry board/screen/augmentacji z zamrożonego presetu laboratorium `D` (plik JSON i jego odcisk z `FROZEN_PRESET_FINGERPRINTS`), czytane neutralnym parserem; brak zgodnego odcisku blokuje run.

Determinizm i wznowienie: sampler wyznacza indeks dla kroku globalnego z permutacji `(seed, epoka)`; RNG augmentacji to `numpy.random.default_rng([seed, step, slot])`; stan to numer kroku. Checkpoint po każdej ocenie (co 300 s treningu) i na końcu zawiera model, optymalizator, GradScaler, RNG torch/numpy/python, krok, stan early stopping, najlepszy stan i historię; plik niezmienny `<step>-<sha256>.pt` przez tmp+fsync+replace, wskaźnik w `jobs.checkpoint_payload` dopiero po ponownym odczycie i walidacji. Uszkodzony lub niezgodny checkpoint nie zostaje wskaźnikiem; przy wznowieniu brak ważnego wskaźnika oznacza start od bazy z zachowanym budżetem, a uszkodzony wskazany plik daje `GRID_TRAINING_CHECKPOINT_CORRUPT` i FAILED bez kandydata. Wznowienie po kroku N daje te same indeksy i ziarna dalszych kroków co przebieg bez przerwy (test na CPU z małą siecią; GPU może różnić się numerycznie).

Tryby: grid-only trenuje tylko `network.board` na wycinkach z `GridBoardDataset` (rectify z 24 węzłów + `perturb_quad`), `network.screen` i wszystkie BatchNorm pozostają w `eval()` z `requires_grad=False` po każdym `train()`; strata widoczności maskowana (kohorty nie mają etykiet niedostępnych komórek), straty węzłów ważone `sampleWeight` 4:1. Screen+grid trenuje całą sieć na pełnych zdjęciach `GridScreenDataset` (cele detektora z 9 plansz, 4 losowe wycinki). Ocena VALIDATION: grid-only — udział plansz poprawnych (NME ≤ 0,02 i maks. błąd węzła ≤ 0,05 przekątnej) na wycinkach z prawdziwych rogów; screen+grid — udział zdjęć kompletnie poprawnych po pełnym dekodowaniu `geometry_core`. REGRESSION nie jest czytany.

Nadzorca: przy claim (i każdym ponownym claim) w kolejności: przypięty payload (`schema_version`), kohorta frozen i `eligibility == eligible` (D-556, w tym `SOURCE_REMOVED_NEW_USE_BLOCKED`), wersja bazowa i jej `training-base/`, odcisk presetu, budżet z `checkpoint_payload` (konserwatywne naliczenie `now - last_charged_at` przy przejęciu po wygasłym leasie), fakty środowiska z `child --probe`, `evaluate_admission`. Odmowa kończy job FAILED z kodem powodu. Następnie spawn trenera, pętla nadzoru co ≤ 5 s: heartbeat joba, odczyt postępu, naliczenie budżetu, zapis wskaźnika checkpointu, przekazanie cancel (plik intencji, trener kończy po checkpoincie). Wynik trenera `exported` → weryfikacja SHA plików, instalacja w `models/grid-engine/<family>/<version>/` (staging + `os.replace`, `training-base/` z receiptem) i rejestracja `not_evaluated` z deterministycznym `versionId = uuid5(jobId, checkpointSha)` i kluczem idempotencji `uuid5(jobId, 'export')`; ponowienie po awarii odtwarza tę samą wersję albo kończy konfliktem, bez duplikatu. Bez publikacji, aktywacji i zmiany default.

API (`application/grid_training_runs.py`, router `/admin/games/{gameId}/grid-training-runs`): POST utworzenia (klucz idempotencji, `cohortId`, `presetId`, `presetFingerprint`) tworzy job z przypiętym payloadem po tych samych blokerach co `run-preview`; GET listy i szczegółu z jobów gry (status, faza, postęp, budżet, wynik); POST cancel i resume (retry FAILED/CANCELLED z zachowanym budżetem). Pełny pion OpenAPI/klient/wrapper/test. Bez nowych tabel: stan runu to job, jego `checkpoint_payload` i katalog runu.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [neural_grid_training.py](../../../services/worker/src/game_predictor_worker/vision_lab/neural_grid_training.py) — `compute_losses`, `train_run`, `evaluate_network`.
- Istniejące: [neural_grid_finetune.py](../../../services/worker/src/game_predictor_worker/vision_lab/neural_grid_finetune.py) — `MixedBatchSampler`, `train_iteration`, wybór kandydata.
- Istniejące: [checkpoint.py](../../../services/worker/src/game_predictor_worker/training_core/checkpoint.py) — zapis, odczyt i odtworzenie checkpointu.
- Pozostały zakres wskazany w zaakceptowanym planie: model i data adapter laboratorium; nowe proponowane `services/worker/src/game_predictor_worker/training_core/grid_training.py`, `services/worker/src/game_predictor_worker/images/grid_training_handler.py`, `services/api/src/game_predictor_api/application/grid_training_runs.py` i repozytorium runów.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/worker/tests/test_durable_v3_grid_training.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Restart odtwarza RNG/sampler/optimizer; crash po eksporcie nie dubluje wersji; uszkodzony checkpoint nie daje gotowego kandydata; lab i produkcja używają zgodnej logiki.

## Verification

Zakres: WORKER, API, MIG przy encjach runów, OpenAPI, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run openapi:check
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_verified_training_datasets.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_neural_grid_finetune.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez automatycznego rzeczywistego treningu lub aktywacji.

## Outcome

### Execution phase

- Gotowe do commita: audyt R5 [PASS](../../quality/TASK-0996_AUDIT_gpt-6-astra_R5.md) (Codex `gpt-6-astra`/`high`), brak otwartych P0/P1/P2. Rundy R1–R4 zachowane w `quality/TASK-0996_AUDIT_gpt-6-astra_R1..R4.md`; dodatkowe rundy poprawek R2–R4 zatwierdził operator po każdym audycie z otwartymi P0.
- Czwarta runda poprawek zakończona za zgodą operatora 2026-10-16 (po R4 z dwoma P0).
- Audyt R4: [REVISE](../../quality/TASK-0996_AUDIT_gpt-6-astra_R4.md), P0-2 i P0-4. Poprawki: licznik końcowy trenera aktualizowany po każdym zakończonym kroku i każdej publikacji checkpointu (P0-2); odzyskany eksport bez pliku wyniku wymaga `preset.json` identycznego z przypiętą recepturą D oraz zgodnych odcisków w bundle i provenance (P0-4). Testy: nadzorca + trener 29 passed. E2E na GPU nie powtarzano: zmiana nie dotyczy przebiegu treningu.
- Trzecia runda poprawek zakończona za zgodą operatora 2026-10-16 (po R3 z otwartymi P0).
- Audyt R3: [REVISE](../../quality/TASK-0996_AUDIT_gpt-6-astra_R3.md), P0-2, P0-6, P0-7, P0-8 i P2-1. Poprawki: rezerwacja kroków zwalniana wyłącznie według wiarygodnego końcowego licznika (`steps` w każdym wyniku trenera; brak wyniku, wynik watchdoga lub zabicie zachowują rezerwację) (P0-2); trener zapisuje wynik przed zwolnieniem dzierżawy GPU, a odzyskiwanie przyjmuje zweryfikowany katalog eksportu bez pliku wyniku (sumy `bundle.files`, kopia checkpointu, `runId`, parity) bez nowego budżetu (P0-6); zapis postępu treningu nie potwierdza oczekującego cancel (`checkpoint(..., acknowledge_cancellation=False)` w magazynie jobów, domyślnie bez zmian dla innych handlerów); potwierdzenie następuje po zatrzymaniu trenera (P0-7); znacznik naliczania próby zapisywany przed uruchomieniem trenera (P0-8); opis E2E rozdziela kolejne przebiegi (P2-1).
- Audyt R2: [REVISE](../../quality/TASK-0996_AUDIT_gpt-6-astra_R2.md), P0-2 (kontynuacja), P0-5, P0-6, P0-7; uwagi R1 pozostałe zamknięte. Poprawki: odzyskiwanie poprzedniej próby w kolejności czekanie na trenera → czas z oczekiwaniem → kroki z postępu bez względu na checkpoint → adopcja checkpointu → odzyskanie gotowego eksportu bez nowego budżetu (P0-5, P0-6); rezerwacja kroków blokami 200 w `checkpoint_payload` przed wykonaniem i rozliczenie do potwierdzonej liczby (P0-2); stop z `checkpoint()` przy późnym cancel zapisuje intencję i czeka na zatrzymanie trenera przed zakończeniem handlera (P0-7).
- Audyt R1: [REVISE](../../quality/TASK-0996_AUDIT_gpt-6-astra_R1.md), P0-1–P0-4 i P1-1–P1-3. Jedna runda poprawek: P0-1 deskryptor wersji (z `frozenOn`) zapisany w stanie przed instalacją i odtwarzany przy ponowieniu; P0-2 budżet kroków kumulatywny między próbami (`attemptStart`), trener egzekwuje `remainingSteps`; P0-3 watchdog całego procesu trenera (utrata nadzorcy po 30 s karencji, limit czasu +5 s), naliczanie niepotwierdzonego odstępu do 100 s; P0-4 odzyskany eksport porównywany z zapisanymi sumami `bundle.files`, checkpointem, presetem i parity; P1-1 przerwanie (cancel, budżet, utrata nadzorcy) publikuje checkpoint kroku, a ponowny claim adoptuje nowszy nienaruszony checkpoint osieroconego trenera; P1-2 receptura przypięta do zamrożonego presetu laboratorium D (odcisk `b94a96…`) i zgodności dekodowania bazy; P1-3 idempotencja tworzenia runu po dokładnym kluczu z blokadą advisory w transakcji.
- Pełny przebieg E2E na GPU z workerem (zgoda operatora na testy 2026-10-16) wykrył i zamknął dwa dalsze błędy kontraktu jobów: brak `schema_version` w `checkpoint_payload` oraz malejące liczniki postępu.
- Wykonawca: Claude Code `claude-opus-5-5`/`high` (wybór wykonawcy po sugestii operatora 2026-10-16, sekcja 8 planu).
- Baza taska: v1.7.387 / `9b6b25dce9a2670afb3b4abcbe8b3e1b88d1a6f5` (scalenie `main` v1.7.376); original base v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: v1.7.388 (poprzedni wersjonowany commit gałęzi v1.7.387, `main` v1.7.376); pełny hash w następnym commicie zgodnie z AGENTS.
- Następny krok: audyt, ewentualna jedna runda poprawek, commit, TASK-0997.

### Changed

- D-558 i decyzja operatora o osobnym lane: `JobType.GRID_TRAINING`, `JobExecutionSlot.GRID_TRAINING = 3`, `WorkerLaneName.GRID_TRAINING`, `execution_slot_for`, migracja `0165_grid_training_lane` (enum w autocommit, ograniczenia przez `job_type::text`, downgrade odmawia przy historii), CLI `--lane grid-training`, `npm run worker:grid-training:poll`, etykieta Admina.
- Neutralny rdzeń: `training_core/neural_grid_network.py` (przeniesione z `vision_lab/neural_grid_model.py`, reeksport), `training_core/neural_grid_augmentation.py` (przeniesione z `neural_grid_data.py`, reeksport, `build_screen_item_with_indices`, `build_board_crop`), `training_core/grid_training.py` (sampler i RNG kroku, pętla z checkpointem po ocenie, early stopping, zamrożenie detektora/BatchNorm, ważone straty węzłów, metryki, eksport ONNX przeniesiony z laboratorium i parity raw).
- `images/grid_training_data.py` (batch grid-only/screen+grid z kohorty, walidacja wycinków i zdjęć), `images/grid_training_child.py` (trener bez bazy, `--probe`), `images/grid_training_handler.py` (nadzorca: przypięty payload, ponowna kwalifikacja D-556, baza, preset, dopuszczenie D-557, spawn, nadzór, cancel, budżet, instalacja i rejestracja `not_evaluated`), `images/grid_training_store.py` (SQL), `GridBoardDataset.indexed`.
- API `application/grid_training_runs.py`, `api/grid_training_runs.py`, schematy `GridTrainingRun*`, `GridTrainingJobPayload` w odpowiedziach jobów; OpenAPI, wygenerowany klient, wrappery i test żądania.
- Dokumentacja: D-558, `architecture/VISION_LAB.md`, `requirements/VISION_LAB.md`, mapa kodu.

### Verification results

- **E2E GPU + PostgreSQL** (`services/api/tests/integration/test_grid_training_lane_gpu_e2e_postgres.py`, izolowana baza `*_test`, prawdziwy `LocalJobWorker` lane `grid_training` slot 3, trener w `.venv-vision-lab` na RTX 4050, wygenerowana kohorta 0995, plikowy magazyn z prawdziwą walidacją rejestru): 1 passed w każdym przebiegu po poprawkach; wartości kolejnych przebiegów różnią się chwilą zabicia. Pierwszy przebieg PASS (415 s, przed rezerwacją kroków): normalny run 40 kroków: claim, trening, eksport z parity, instalacja i rejestracja w 76,3 s. Zabicie procesu nadzorcy przy kroku 103 (planowane 700): osierocony trener zapisał checkpoint przy kroku 105 i zakończył się; nowy worker po wygaśnięciu leasu przejął job, poczekał na zwolnienie dzierżawy GPU, wznowił od kroku 105 i zarejestrował jedną wersję; budżet 700 kroków (kumulatywnie) i 290,5 s, 2 próby, odzysk 254,6 s. Przebieg po R2 (437,7 s, z rezerwacją blokami 200): normalny run 90,0 s; zabicie przy kroku 107, wznowienie od 115, zarezerwowane 985 kroków (cała porcja przerwanej próby naliczona zachowawczo), 292,4 s. Przebieg po R3 (421,9 s): normalny run 76,7 s; zabicie przy kroku 103, osierocony trener zapisał checkpoint i wynik przy kroku 107, nowy worker wznowił od 107; budżet rozliczony dokładnie do 700 kroków (wiarygodne liczniki obu prób), 296,3 s, jedna rejestracja. PostgreSQL po R3: 3 passed (w tym odroczone potwierdzenie cancel w magazynie jobów). Nadzorca po R3: 20 passed; trener 8 passed. Aktualny dowód: `artifacts/audits/TASK-0996_GPU_E2E.json` (nadpisywany przez ostatni przebieg).
- PostgreSQL: `test_grid_training_lane_migration_postgres.py` 2 passed (migracja 0165 oraz dokładne wyszukanie klucza idempotencji i serializacja blokadą).
- Po poprawkach R1: rdzeń + nadzorca + dopuszczenie 71 passed (w tym przerwanie przed pierwszą oceną i po niej wznawia do identycznych wag, deskryptor z innego dnia, kumulatywne kroki, adopcja checkpointu osieroconego trenera i odrzucenie nieweryfikowalnego wskaźnika); trener 6 passed (receptura niezgodna, odzyskany uszkodzony eksport, watchdog); API/migracje 91 passed; regresje laboratorium i jobów 39 passed; Ruff i `mypy --strict` PASS.
- Przed audytem: `test_durable_v3_grid_training.py` 11 passed: sampler, LR jak w laboratorium, **przerwany run wznowiony z checkpointu w nowym module/optymalizatorze/RNG daje identyczne wagi i historię** co run bez przerwy (CPU), uszkodzony i obcy checkpoint odrzucone, early stopping, zamrożenie detektora i BatchNorm (wagi i statystyki bez zmian), ważone straty = straty laboratorium przy równych wagach, metryki, deterministyczne batch grid-only z wagą 0 dla wypełnień, element laboratorium identyczny po wydzieleniu.
- `test_grid_training_handler.py` 8 passed (fałszywy trener zapisujący pliki, prawdziwa instalacja, `validate_manifest` i `GridModelArtifactInspector`): kandydat `not_evaluated` z deterministycznym ID, replay bez ponownego treningu, **awaria po eksporcie i instalacji → ta sama wersja raz, bez ponownego treningu**, uszkodzony wskazany checkpoint bez kandydata i bez startu trenera, wznowienie z wskaźnikiem i ograniczonym naliczeniem (70 s), usunięte źródło blokuje, cudza dzierżawa blokuje, cancel z intencją i potwierdzeniem, błąd trenera bez kandydata.
- `test_grid_training_child.py` 3 passed (prawdziwy trener na CPU, mała wygenerowana kohorta 0995, świeża sieć jako baza): 2 kroki, checkpoint, **eksport ONNX z parity PASS**, zwolnienie dzierżawy, detektor bez zmian i ruch etapu planszy; zmieniona baza → `GRID_TRAINING_BASE_DRIFT`; intencja cancel → `RUN_CANCELLED`.
- API: `test_grid_training_runs.py` + `test_jobs_api.py` + `test_schema_readiness.py` 53 passed; `test_grid_training_run_preview.py`/cohort 13 passed.
- PostgreSQL (izolowana baza `*_test`, `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`): `test_grid_training_lane_migration_postgres.py` 1 passed — upgrade do head, etykieta enum, slot 3 tylko dla `grid_training`, lane runtime, downgrade blokowany historią joba i lane, czysty downgrade i ponowny upgrade.
- Regresje: lab training_core/runs/admission/cohort 79, neural_grid/finetune 37, job runtime/lane 13, worker CLI 6, grid reinference/shadow 29, preflight/proposal/silent audit 27, assisted/comparison 33, hybrid 38, managed checkpoints 13 — wszystkie PASS.
- Ruff format/check 32 zmienionych plików PASS, `mypy --strict` nowych i zmienionych modułów PASS, `openapi:check` PASS, klient 127/127 i typecheck PASS, typecheck Admina PASS, `code-map:check` i `docs:check` PASS.
- Nie uruchamiano: rzeczywistego treningu GPU na danych operatora (wymaga osobnej zgody), usług, migracji bazy operatora, pełnego zestawu testów.

### Not completed

- `scripts/manage_worker_lanes.ps1` nie zna jeszcze lane `grid_training`; operator uruchamia go poleceniem npm (instrukcja do TASK-1001).
- `images/grid_training_store.py` (SQL nadzorcy) nie ma testu na PostgreSQL; logika nadzorcy testowana z fałszywym magazynem, a prawdziwe repozytoria pokrywają testy 0994/0995.
- Pełny przebieg wykonano na izolowanej bazie z wygenerowaną kohortą i plikowym magazynem katalogu; trening na danych operatora i rzeczywistym katalogu po migracji 0165 wymaga osobnej zgody.
- Ocena kandydata (TASK-0997); integracja i migracja bazy operatora na końcu planu (zgoda operatora 2026-10-16).

### Documentation updates

- D-558, VISION_LAB (architektura, wymagania), mapa kodu, zamiennik modelu w planie i taskach.

### Recommended next task

- TASK-0997.

### Uruchomienie lane (dla operatora, po migracji `0165`)

```powershell
$env:GAME_PREDICTOR_GRID_TRAINING_PYTHON = 'C:\Users\tuszy\Documents\game_predicotr\.venv-vision-lab\Scripts\python.exe'
npm run worker:grid-training:poll
```
