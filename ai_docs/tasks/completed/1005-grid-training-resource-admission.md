---
title: TASK-1005 — Preset i dopuszczenie zasobów
status: done
last_updated: 2026-10-16
---

# TASK-1005 — Preset i dopuszczenie zasobów

## Status

`done`

## Goal

Ustalić jawny budżet runu na podstawie danych.

## Context

Task jest częścią zaakceptowanej rewizji 6. Pomiar kosztu i wersjonowany preset. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0995; osobna zgoda na ograniczony pomiar GPU.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

Zmiana ról na jawne polecenie operatora2026-10-16 po ukończeniu TASK-0995: Claude Code wykonuje, Codex audytuje. Historycznych raportów i wykonawców ukończonych zadań nie zmieniamy.

- Wykonawca: `claude-opus-5-5`, reasoning `high` (zamiennik `claude-fable-5-1`/`medium` na jawną decyzję operatora 2026-10-16, zapisaną w sekcji 8 planu). parametry wynikają z raportów i mierzalnego testu.
- Dodatkowy review: `gpt-6-astra`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [Przekazanie po zamianie ról](../../guides/V3_GRID_FINE_TUNING_ROLE_HANDOFF.md).
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../../architecture/VISION_LAB.md).
- [VISION_LAB](../../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: VISION_LAB i raporty dotychczasowych iteracji Mumii.

## Scope

- Osobne presety grid-only/screen+grid, koszt kohorty, early stopping i limit czasu/kroków.
- Smoke kończy się po 50 krokach albo 120 sekundach, zależnie co nastąpi pierwsze.
- Dzierżawa obejmuje app grid runs.

## Out of scope

- Bez obietnicy kontroli wszystkich zewnętrznych procesów CUDA i bez zmian trenera symboli.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Brak GPU, niezgodny runtime, zajęta dzierżawa lub brak zatwierdzonego presetu blokuje run.
- [x] Resume nie odnawia budżetu.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Osobne presety grid-only/screen+grid, koszt kohorty, early stopping i limit czasu/kroków. Smoke kończy się po 50 krokach albo 120 sekundach, zależnie co nastąpi pierwsze. Dzierżawa obejmuje app grid runs.

### Kontrakt przed kodem (2026-10-16, Claude Code)

Stan zastany (sprawdzony odczytem HEAD v1.7.385): nie istnieje żadna dzierżawa GPU dla aplikacji; jedyną ochroną jest `RUN_BUSY` laboratoryjnego `vision_lab/runs.py::RunManager`. `acquire_job_admission` (`storage/job_admission.py`) to blokada per gra, nie GPU. Kontrola środowiska istnieje tylko w `vision_lab/run_worker.py::validate_runtime` (torch `2.12.1+cu130`, torchvision `0.27.1+cu130`, CUDA `13.0`) i działa dopiero po starcie procesu. Brak early stopping. Smoke laboratorium ma limit 1800 s. Budżet laboratorium (`used_seconds`, `reserved_steps`) jest trwały i retry go nie odnawia — ten model przenosimy.

Moduły (nowe, proponowane w planie):

- `training_core/grid_training_admission.py` — neutralny (bez importów `game_predictor*`, torch tylko leniwie w `probe_runtime`). Zawiera wersjonowane presety `grid-only-v1` i `screen-grid-v1` z odciskiem SHA-256 kanonicznego JSON parametrów, szacunek kosztu kohorty, fakty środowiska, trwały budżet runu i czystą decyzję dopuszczenia.
- `training_core/gpu_lease.py` — międzyprocesowa dzierżawa jednego GPU dla runów aplikacji (trening, smoke), plik `<artifact_root>/grid-training/gpu-lease.json` pod krótką blokadą pliku `.lock` (msvcrt/fcntl, ponawianie do 5 s). Zapis przez plik tymczasowy, `fsync` i `os.replace`. Rekord: token, rodzaj i ID runu, PID z czasem utworzenia procesu, `expiresAt`. Przejęcie wyłącznie przy wygasłym terminie i potwierdzonym braku procesu o tym PID i czasie utworzenia; żywy właściciel z wygasłym terminem nadal blokuje. Nieczytelny rekord lub błąd identyfikacji procesu blokuje (`GRID_RUN_LEASE_UNKNOWN`), bez automatycznego usuwania. Odnowienie/zwolnienie z obcym tokenem daje `GRID_RUN_LEASE_LOST`. Nie kontroluje procesów CUDA spoza aplikacji ani runów laboratorium.
- `vision_lab/grid_training_smoke.py` — ograniczony pomiar w izolowanym środowisku `.venv-vision-lab` na rolach `training` snapshotu referencyjnego 777 (bez danych operatora i bazy). Pobiera dzierżawę, przechodzi tę samą decyzję dopuszczenia (`purpose=smoke`), wykonuje pełny krok obecnego trenera laboratorium w kształcie wsadu presetu i kończy się po 50 krokach albo 120 s naliczonego czasu od dopuszczenia, zależnie co pierwsze. Bez checkpointu, kandydata, eksportu, publikacji i aktywacji. Raport JSON w `artifacts/` (ignorowany), wynik w Outcome. **Doprecyzowanie operatora 2026-10-16 po pierwszym smoke:** pierwszy przebieg z limitem 120 s liczonym od dopuszczenia zakończył watchdog po 150 s przed pierwszym krokiem (start ładowania danych). Operator polecił większy limit, aby test był dokładny i wykonany: 50 kroków albo 120 s treningu liczone od pierwszego kroku, osobny limit startu 300 s, cały naliczony run najwyżej 600 s, watchdog +30 s.
- API: `GET /admin/games/{gameId}/grid-training-cohorts/{cohortId}/run-preview` (`previewGridTrainingRun`) — tylko odczyt: nagłówek i istniejąca kwalifikacja kohorty, presety z odciskami, szacunek kosztu dla presetu trybu kohorty, odczyt stanu dzierżawy (free/held/stale/unknown, bez PID) oraz blokery po stronie API. Kontrole GPU/środowiska/VRAM/budżetu wykonuje worker przy dopuszczeniu; podgląd wypisuje je jako `pendingWorkerChecks`, bez udawania wyniku. Pion: router, schemat, serwis, OpenAPI, wygenerowany klient, wrapper, test żądania.

Presety (wartości z raportów `quality/GRID_V3_NEURAL_GRID_RUNS_20261002.md`, `MUMIE_CURRENT_APPROVALS_20261005.md` i pomiaru smoke): optymalizacja jak preset D (AdamW, lr `1e-4`, warmup 5%, końcowe 10%, weight decay `1e-4`, clip 5, fp16). `screen-grid-v1`: 12 pełnych zdjęć × 4 wycinki plansz (kształt D). `grid-only-v1`: 48 wycinków plansz, zamrożony detektor i BatchNorm (wykonanie w TASK-0996); koszt szacowany konserwatywnie pełnym krokiem D. Czas treningu: 60 s na zdjęcie TRAIN, przycięty do 300–1800 s; ocena VALIDATION co 300 s treningu; early stopping po 2 kolejnych ocenach bez poprawy o więcej niż `min_delta` monitorowanej miary walidacyjnej, nie wcześniej niż po 2 ocenach; REGRESSION nie służy do wyboru. Twardy limit runu 3600 s naliczonego czasu i limit kroków wynikający z pomiaru. Szacunki narzutu: start 180 s, ocena 60 s, checkpoint 30 s, rezerwa końcowa 60 s. Dokładne liczby, VRAM i `steps_per_second_estimate` zapisuje kod po pomiarze; preset bez pomiaru pozostaje `approved=false`.

Decyzja dopuszczenia (`evaluate_admission`) zbiera wszystkie powody w stałej kolejności: `GRID_RUN_PRESET_NOT_APPROVED` (nieznany ID, inny odcisk, preset niezatwierdzony; smoke wymaga znanego odcisku, nie zatwierdzenia), `GRID_RUN_COHORT_MODE_MISMATCH`, `GRID_RUN_COHORT_EMPTY`, `GRID_RUN_COHORT_COST_EXCEEDS_BUDGET`, `GRID_RUN_GPU_UNAVAILABLE`, `GRID_RUN_RUNTIME_INCOMPATIBLE`, `GRID_RUN_VRAM_INSUFFICIENT`, `GRID_RUN_LEASE_BUSY`/`GRID_RUN_LEASE_UNKNOWN`, `GRID_RUN_BUDGET_PRESET_MISMATCH`, `GRID_RUN_BUDGET_EXHAUSTED`. Dopuszczenie wymaga pustej listy. Brak danych środowiska nie jest PASS.

Budżet (`RunBudget`): `max_steps`, `max_seconds`, `reserved_steps`, `used_seconds`, `attempts`, odcisk presetu i cel (`train`/`smoke`); koperta `{payload, sha256}`. Wznowienie zwiększa `attempts` i zachowuje sumy; inny odcisk lub cel daje `GRID_RUN_BUDGET_PRESET_MISMATCH`; wyczerpany budżet blokuje. Ujemny lub nieskończony przyrost czasu (cofnięty zegar) wyczerpuje budżet. Smoke ma osobny budżet 50 kroków/120 s i nie przechodzi w budżet treningu. Trwały zapis budżetu w encji runu dostarcza TASK-0996; ten task dostarcza semantykę i serializację.

Pliki: nowe `training_core/grid_training_admission.py`, `training_core/gpu_lease.py`, `vision_lab/grid_training_smoke.py`, `services/worker/tests/test_grid_training_resource_admission.py`; API `api/grid_training_cohorts.py` (nowa trasa), `schemas/grid_training_cohorts.py` (`GridTrainingRunPreview`), `application/grid_training_cohorts.py` (`run_preview`), test `services/api/tests/test_grid_training_run_preview.py`; klient `packages/admin-api-client` (OpenAPI, wygenerowane pliki, wrapper `previewGridTrainingRun`, test żądania). Bez migracji, nowych tabel i zmian trenera symboli.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [neural_grid_finetune.py](../../../services/worker/src/game_predictor_worker/vision_lab/neural_grid_finetune.py) — `MixedBatchSampler`, `train_iteration`, wybór kandydata.
- Pozostały zakres wskazany w zaakceptowanym planie: istniejące protokoły runów; nowy proponowany `services/worker/src/game_predictor_worker/training_core/grid_training_admission.py`, presety i API podglądu.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/worker/tests/test_grid_training_resource_admission.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Brak GPU, niezgodny runtime, zajęta dzierżawa lub brak zatwierdzonego presetu blokuje run.
- Resume nie odnawia budżetu.

## Verification

Zakres: WORKER, API; ograniczony smoke tylko po zgodzie.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_neural_grid_proposal.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_neural_grid_finetune.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez obietnicy kontroli wszystkich zewnętrznych procesów CUDA i bez zmian trenera symboli.

## Outcome

### Execution phase

- Gotowe do commita: audyt R2 [PASS](../../quality/TASK-1005_AUDIT_gpt-6-astra_R2.md) (`gpt-6-astra`/`medium`), wszystkie uwagi R1 zamknięte, brak otwartych P0/P1/P2. Raport bieżący: `quality/TASK-1005_AUDIT_gpt-6-astra.md` (kopia R2), R1 zachowany.
- Audyt R1: [REVISE](../../quality/TASK-1005_AUDIT_gpt-6-astra_R1.md), P0-1/P0-2/P0-3 i P2-1, brak P1. Jedna runda poprawek: P0-1 pełna walidacja typów i skończoności rekordu dzierżawy (błąd daje `GRID_RUN_LEASE_UNKNOWN`, plik zostaje); P0-2 `SmokeWatchdog` pilnuje także terminu treningu od pierwszego kroku (+30 s); P0-3 watchdog zatrzymywany w `finally` przed powrotem, po zatrzymaniu nie zapisuje raportu i nie kończy procesu; P2-1 `release` obcym lub brakującym tokenem daje `GRID_RUN_LEASE_LOST` zgodnie z kontraktem.
- Wykonawca: Claude Code `claude-opus-5-5`/`high` jako jawny zamiennik `claude-fable-5-1`/`medium` na decyzję operatora 2026-10-16 (sekcja 8 planu).
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`; baza taska v1.7.385 / `f0cfa9bdf2deaf0e5abdf7970624bd5575f10dc7`.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: v1.7.386 (najwyższy wersjonowany commit lokalnych gałęzi: v1.7.385 tej gałęzi; `main` v1.7.374); pełny hash dopisany w następnym commicie zgodnie z AGENTS.
- Następny krok: audyt, ewentualna jedna runda poprawek, commit, potem scalenie `main` do gałęzi na polecenie operatora i TASK-0996.

### Changed

- Nowy neutralny `training_core/grid_training_admission.py`: presety `grid-only-v1` (48 wycinków, zamrożony detektor i BatchNorm) i `screen-grid-v1` (12 zdjęć × 4 wycinki) z odciskiem SHA-256, `estimate_cohort_cost`, `RuntimeFacts`/`probe_runtime`, `RunBudget` z kopertą checksum i `evaluate_admission`.
- Nowy `training_core/gpu_lease.py`: jedna międzyprocesowa dzierżawa GPU aplikacji pod blokadą pliku; `process_identity` przeniesiony do `training_core` z reeksportem w `vision_lab`.
- Nowy `vision_lab/grid_training_smoke.py`: ograniczony pomiar w `.venv-vision-lab` na roli `training` snapshotu referencyjnego 777, z dzierżawą i tą samą decyzją dopuszczenia.
- API: `GET /admin/games/{gameId}/grid-training-cohorts/{cohortId}/run-preview` (`previewGridTrainingRun`), schematy `GridTrainingRunPreview` i pokrewne, `GridTrainingCohortService.run_preview`; OpenAPI, wygenerowany klient, wrapper `previewGridTrainingRun` i test żądania.
- D-557, sekcje VISION_LAB (architektura i wymagania), mapa kodu. Zamiennik modelu wykonawcy zapisany w planie i sześciu taskach.
- Preset (uzasadnienie): optymalizacja presetu D; 60 s/zdjęcie TRAIN w zakresie 300–1800 s jak iteracje Mumii; ocena co 300 s i early stopping po 2 ocenach bez poprawy, bo iteracje 4–5 (900 s) nie poprawiały holdoutu; limit runu 3600 s mieści szacunek 2580 s dla kohorty z 1800 s treningu; szacunek 2,0 kroku/s konserwatywnie poniżej raportów (2,03–2,46) i smoke (2,63); VRAM 6,0 GB całkowitej i 5,0 GB wolnej po kontekście CUDA (szczyt alokacji 4,67 GB).

### Verification results

- Po poprawkach R1: `test_grid_training_resource_admission.py` 47 passed (nowe: 10 wariantów semantycznie błędnego rekordu, zwolnienie brakującego rekordu, limity startu/treningu/runu watchdog na kontrolowanym zegarze, zatrzymany watchdog bez zapisu i wyjścia, wyjątek pomiaru zatrzymuje watchdog i zwalnia dzierżawę); API 61 passed (w tym semantycznie błędny rekord: 200, `unknown`, bloker); `test_vision_lab_training_core.py` + `test_vision_lab_runs.py` z admission 64 passed; Ruff i `mypy --strict` PASS.
- Przed audytem: `pytest services/worker/tests/test_grid_training_resource_admission.py`: 33 passed (blokady GPU/runtime/VRAM/dzierżawy/presetu/kohorty/budżetu, kolejność powodów, smoke bez zatwierdzenia, wznowienie bez odnowienia po trwałej serializacji, cofnięty zegar, uszkodzona koperta, dzierżawa: wyłączność, nowy obiekt, żywy właściciel po terminie, przejęcie po martwym procesie i ponownym użyciu PID, nieczytelny rekord, rzeczywisty proces potomny trzymający dzierżawę do wyjścia, smoke bez GPU zablokowany przed dzierżawą).
- Regresje workera: `test_vision_lab_training_core.py` + `test_vision_lab_neural_grid_finetune.py` 22 passed (w tym strażnik importów neutralnego rdzenia), `test_vision_lab_runs.py` + `test_vision_lab_neural_grid.py` 32 passed.
- API: `test_grid_training_run_preview.py` + `test_grid_training_cohort_requests.py` + `test_grid_training_cohort_core.py` 61 passed.
- Ruff format/check zmienionych plików PASS; `mypy --strict` zmienionych modułów PASS.
- `npm run openapi:check` PASS; klient `@game-predictor/admin-api-client` test 125/125 i typecheck PASS; `typecheck` Admina PASS; mapa kodu zregenerowana, `code-map:check` PASS.
- Smoke GPU za zgodą operatora (RTX 4050 Laptop 6 GB, torch 2.12.1+cu130, CUDA 13.0), raporty w ignorowanym `artifacts/grid-training-smoke/`:
  - próba 1: dopuszczenie zablokowało run (`GRID_RUN_VRAM_INSUFFICIENT`, wolne 5,32 GB po kontekście < pierwotnego progu 5,5 GB); próg obniżono do 5,0 GB na podstawie raportów;
  - próba 2: błąd importu przed treningiem (brak ścieżki źródeł API w środowisku laboratorium); dzierżawa zwolniona;
  - próba 3 (120 s od dopuszczenia): watchdog po 150 s przed pierwszym krokiem; pozostał rekord dzierżawy, który kolejny odczyt rozpoznał jako `stale` (martwy proces); operator polecił większy limit;
  - próba 4 (limity D-557): `completed`, 50 kroków, start do pierwszego kroku 111,4 s (dane 17,7 s, start workerów loadera ok. 94 s), stały przepływ 2,63 kroku/s, szczyt alokacji 4 666 725 888 B, rezerwacji 5 842 665 472 B, budżet 50/50 kroków i 130,0/600 s, bez checkpointu i kandydata, dzierżawa zwolniona.
- Nie uruchamiano: usług, migracji, pełnego zestawu testów, treningu z danymi operatora.

### Not completed

- Trwały zapis budżetu w encji runu, wywołanie dopuszczenia przez handler i mapowanie metryk early stopping należą do TASK-0996/0997.
- Smoke mierzy pełny krok laboratorium (kształt D); rzeczywisty koszt grid-only z zamrożonym detektorem zmierzy TASK-0996. Rezerwacja VRAM może przekraczać wolną pamięć raportowaną po kontekście (alokator i sterownik Windows); próg opiera się na szczycie alokacji.
- Integracja (osobna zgoda operatora na końcu planu).

### Documentation updates

- D-557 (pełny wpis, indeks, kopia), `architecture/VISION_LAB.md`, `requirements/VISION_LAB.md`, `CODE_MAP*.md`, Technical notes i doprecyzowanie operatora w tym tasku, zamiennik modelu w planie i taskach.

### Recommended next task

- Scalenie `main` do gałęzi (polecenie operatora 2026-10-16), potem TASK-0996.
