---
title: TASK-0675 — T10 — pełna sieć węzłów
status: todo
last_updated: 2026-09-25
---

# TASK-0675 — T10 — pełna sieć węzłów

## Status

`todo`

## Goal

Warunkowo dodać neural_grid przewidujący pełną siatkę obu topologii.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

Osobne uruchomienie etapu D po STOP C; T09 uzasadnia T10; wystarczające pełne anotacje. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

## Recommended execution

`gpt-6-astra`, reasoning `high`; osobny audyt `gpt-6-sol`, reasoning `high`. Predykcja pełnych siatek obu topologii wymaga oceny architektury i danych. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T10 — pełna sieć węzłów)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447)

## Scope

Bezpośrednie węzły 24/16, wspólny kontrakt/renderer/editor/cropper/gate, walidacyjny wybór; do 50 kroków i jeden trening 20 epok/30 min.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [ ] Ten sam kontrakt i odbiorcy; brak danych daje konkretną listę brakujących anotacji; brak nieograniczonych prób.
- [ ] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Zachowaj kontrakty z planu i właścicieli istniejących decyzji. Błędy wejścia oznaczaj per źródło lub próbka, a błąd integralności i infrastruktury zatrzymuje zależny run. Nie promuj predykcji do ręcznego zatwierdzenia. Istotne odstępstwo wymaga aktualizacji planu przed implementacją.

## Expected files

- Istniejące `services/worker/src/game_predictor_worker/images/keypoint_geometry/model.py::KeypointGeometryHeatmapNetwork` (wzorzec); nowe (proponowane) `services/worker/src/game_predictor_worker/vision_lab/neural_grid.py::NeuralGridEngine`, `services/worker/tests/test_vision_lab_neural_grid.py`.

## Test cases

- 24 i 16 węzłów, partial/occlusion, PyTorch–ONNX, zmiana silnika bez zmiany odbiorcy.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_neural_grid.py') -PassThru -NoNewWindow
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
