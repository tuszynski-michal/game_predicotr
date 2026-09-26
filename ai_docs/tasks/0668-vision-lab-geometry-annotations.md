---
title: TASK-0668 — T03 — edytor i zbiór geometrii
status: todo
last_updated: 2026-09-25
---

# TASK-0668 — T03 — edytor i zbiór geometrii

## Status

`todo`

## Goal

Zatwierdzać warstwowe anotacje geometrii z trwałymi rewizjami i zamrożonymi podziałami.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

STOP A; wybór gry niewidzianej zapisany przed pierwszym treningiem; zatwierdzony budżet B. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

## Recommended execution

`gpt-6-sol`, reasoning `high`; osobny audyt `gpt-6-astra`, reasoning `high`. Trwałość decyzji oraz brak przecieku rodzin źródeł wymagają kontroli rewizji i podziałów. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T03 — edytor i zbiór geometrii)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447)

## Scope

Edycja narożników i pełnych węzłów, rewizje, backup/restore, pochodzenie 777 V2, split rodzin i duplikatów; pomiar pierwszych 10 zdjęć na grę i prognoza pracy.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [ ] Brak przecieku rodzin; restart i odtworzenie backupu; narożniki nie udają pełnej siatki; nierozstrzygnięte 777 V2 wykluczone.
- [ ] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Zachowaj kontrakty z planu i właścicieli istniejących decyzji. Błędy wejścia oznaczaj per źródło lub próbka, a błąd integralności i infrastruktury zatrzymuje zależny run. Nie promuj predykcji do ręcznego zatwierdzenia. Istotne odstępstwo wymaga aktualizacji planu przed implementacją.

## Expected files

- Istniejące `services/api/src/game_predictor_api/domain/board_topology.py::BoardTopology`, `apps/vision-lab/src/app/page.tsx::Page`. Nowe (proponowane) `services/worker/src/game_predictor_worker/vision_lab/annotations.py::approve_geometry`, `.../splits.py::freeze_splits`, `apps/vision-lab/src/components/geometry-editor.tsx::GeometryEditor`, `services/worker/tests/test_vision_lab_annotations.py`.

## Test cases

- Rewizja cropa unieważnia approval; dwa zdjęcia jednej rodziny zawsze w jednym splicie; backup po restarcie zachowuje decyzje; interpolacja nie jest referencją.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_annotations.py') -PassThru -NoNewWindow
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
