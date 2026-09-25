---
title: TASK-0673 — T08 — panel treningu
status: todo
last_updated: 2026-09-25
---

# TASK-0673 — T08 — panel treningu

## Status

`todo`

## Goal

Udostępnić panel treningu korzystający z trwałego kontraktu runów T04 i odtwarzający widok po restarcie.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

T04–T07 done, w tym trwały `RunManager` z T04 i gotowy kontrakt API. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

## Recommended execution

`gpt-5.6-terra`, reasoning `high`; osobny audyt `gpt-6-astra`, reasoning `medium`. Panel korzysta z gotowego protokołu runów T04; ryzyko koncentruje się na interakcjach i stanie UI. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T08 — panel treningu)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447)

## Scope

UI start/cancel/postęp/checkpoint/jawne retry/historia korzysta z backendu T04. Pokazuje stany `queued`, `running`, `succeeded`, `failed`, `cancelled`, bez pauzy. Przekazuje trwały `requestId`; identyczne żądanie pokazuje ten sam run, konflikt payloadu pokazuje błąd bez drugiego startu.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [ ] Powtórne żądanie nie tworzy drugiego treningu; restart zachowuje stan i lineage model→dane→konfiguracja→raport. `queued` jest trwałe przed spawnem, `running` wiąże PID, czas startu, lease i heartbeat; sukces wymaga checksumowanego raportu.
- [ ] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Właścicielem atomowego stanu, blokady, procesu, lease, heartbeat i retry pozostaje `vision_lab/runs.py::RunManager` z T04. Panel jest klientem: po restarcie odczytuje listę runów, nie uruchamia automatycznie drugiego procesu. Pokazuje recoverable `failed`, ostatni checkpoint i konflikt `requestId`; nie trzyma jedynego stanu runu. Jeśli brak wymaganego endpointu, rozszerz istniejący kontrakt labu oraz generowanego klienta w tym samym pionie.

## Expected files

- Istniejące po T04 (proponowane) `services/worker/src/game_predictor_worker/vision_lab/runs.py::RunManager` oraz `.../api.py::start_training_run`; nowe (proponowane) `apps/vision-lab/src/components/training-panel.tsx::TrainingPanel`, `apps/vision-lab/test-interactions/training-panel.test.mjs::trainingPanel`; generowany klient laboratorium i test żądania, jeśli rozszerza się API.

## Test cases

- UI: podwójny start/utrata odpowiedzi → ten sam widoczny run; konflikt `requestId` → komunikat bez drugiego startu. Restart strony i backendu → stan odczytany z T04, bez spawnu; cancel/retry pokazują terminalne stany oraz checkpoint. Regresja backendu T04 nadal przechodzi.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_runs.py') -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'pytest timeout 120s' }
if ($p.ExitCode -ne 0) { throw "pytest exit $($p.ExitCode)" }
$ui = Start-Process -FilePath 'npm.cmd' -ArgumentList @('run','test','--workspace','@game-predictor/vision-lab') -PassThru -NoNewWindow
if (-not $ui.WaitForExit(120000)) { $ui.Kill(); throw 'UI test timeout 120s' }
if ($ui.ExitCode -ne 0) { throw "UI test exit $($ui.ExitCode)" }
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
