---
title: TASK-0669 — T04 — izolowany rdzeń treningu
status: todo
last_updated: 2026-09-25
---

# TASK-0669 — T04 — izolowany rdzeń treningu

## Status

`todo`

## Goal

Dostarczyć neutralny rdzeń, trwały backend runów i izolowane środowisko GPU z checkpointem v2.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

T03 done, zamrożony manifest i split. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

## Recommended execution

`gpt-6-sol`, reasoning `high`; osobny audyt `gpt-6-astra`, reasoning `high`. Granice importów, protokół runów i checkpointy wpływają na odtwarzalność treningu. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T04 — izolowany rdzeń treningu)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447)

## Scope

Wydzielić czyste funkcje bez przepinania training_job.py; adapter plikowy, constraints CUDA, kontrola GPU, checkpoint optimizer/scheduler/RNG/config/data SHA i odczyt v1. Zaimplementować backend `RunManager` oraz endpointy start/list/detail/cancel/retry dla późniejszego panelu T08. Stany: `queued`, `running`, `succeeded`, `failed`, `cancelled`; bez pauzy.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [ ] Test importów lab/produkcja/rdzeń; GPU wykonuje krótkie obliczenie lub jawny brak; v2 wznawia, v1 odczytuje bez obietnicy identyczności.
- [ ] `queued` jest trwałe przed startem; identyczny `requestId`+payload zwraca ten sam run, inny payload konflikt. Restart nie tworzy duplikatu. Cancel zachowuje checkpoint, jawne retry ma nowy lease i odgradza starego writera; sukces ma checksumowany raport.
- [ ] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Kanoniczny fingerprint runu obejmuje manifest, konfigurację, model, topologię, preprocessing i seed. W atomowym stanie zapisz `requestId` oraz fingerprint przed spawnem. `running` zawiera PID, czas startu procesu, lease token i heartbeat. Po restarcie sprawdź tożsamość procesu: żywy tylko obserwuj; wygasły lease przechodzi w recoverable `failed`, bez automatycznego spawnu. Cancel to trwała intencja i łagodne zakończenie po checkpointcie. Awaria zachowuje ostatni poprawny checkpoint; jawne retry ma kolejną próbę, nowy lease i fencing token. Stary proces nie może opublikować wyniku; `succeeded` wymaga atomowego raportu i checksum artefaktów. Wymagany kontrakt API i test żądania powstają w tym tasku. Zachowaj izolację od produkcyjnego handlera.

## Expected files

- Istniejące `services/worker/src/game_predictor_worker/symbols/training_job.py::_train_epochs` (tylko analiza), `services/worker/src/game_predictor_worker/images/keypoint_geometry/model.py::KeypointGeometryHeatmapNetwork`.
- Nowe (proponowane) `services/worker/src/game_predictor_worker/training_core/checkpoint.py::load_checkpoint`, `.../vision_lab/training_adapter.py::train_from_manifest`, `.../vision_lab/runs.py::RunManager`, `RunState`, `create_or_get_run`, `cancel_run`, `retry_run`, `.../vision_lab/api.py::start_training_run`, `services/worker/tests/test_vision_lab_training_core.py`, `services/worker/tests/test_vision_lab_runs.py`, `requirements-vision-lab.txt`.

## Test cases

- Nowy checkpoint odtwarza RNG i optimizer; stary v1 daje jawnie ograniczone wznowienie; importy nie przeciekają. Utrata odpowiedzi i identyczne retry → jeden run; inny payload pod tym samym ID → konflikt. Crash przed/po spawnie, restart z żywym procesem, wygasły lease, cancel po checkpointcie i fenced retry → brak duplikatu lub starego zapisu.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_training_core.py','services/worker/tests/test_vision_lab_runs.py') -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'pytest timeout 120s' }
if ($p.ExitCode -ne 0) { throw "pytest exit $($p.ExitCode)" }
```

Po teście wykonaj lint/typecheck zmienionych modułów i wymagane kontrole kontraktu, każdą jako skończony proces z limitem maksymalnie 120 s. Testy tu są planowane, niezaliczone; zaliczenie wymaga kryteriów powyżej i braku regresji.

## Risks / open questions

- Zmiana schematu danych, zakresu zdjęć lub kosztu poza planem wymaga jawnej aktualizacji przed zależnym działaniem.

## Outcome

Wypełnia agent po pracy.

### Changed

- Do uzupełnienia po wykonaniu.

### Verification results

- Do uzupełnienia po wykonaniu.

### Not completed

- Do uzupełnienia po wykonaniu.

### Documentation updates

- Do uzupełnienia po wykonaniu.

### Recommended next task

- Do uzupełnienia po wykonaniu.
