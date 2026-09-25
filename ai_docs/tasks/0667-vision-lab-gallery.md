---
title: TASK-0667 — T02 — kontrakty i galeria
status: todo
last_updated: 2026-09-25
---

# TASK-0667 — T02 — kontrakty i galeria

## Status

`todo`

## Goal

Pokazać zdjęcia, siatki i cropy przez bezpieczny lokalny pion API–OpenAPI–klient–UI.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

T01 done i opublikowany snapshot. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

## Recommended execution

`gpt-6-sol`, reasoning `high`; osobny audyt `gpt-6-astra`, reasoning `high`. Pion UI, OpenAPI i zabezpieczeń HTTP przecina kilka modułów. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T02 — kontrakty i galeria)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447)

## Scope

Wspólne GeometryEngine/GeometryResult/SymbolRecognizer, adapter baseline, galeria Next.js, FastAPI, allowlist proxy, Host/Origin/JSON, zarejestrowane assety i klient generowany.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [ ] Wyniki na dostarczonych zdjęciach; 3 × 3 jawnie unsupported, jeśli baseline nie obsługuje; błąd obrazu nie blokuje galerii; obcy Host/Origin/trasa i prosty POST odrzucone.
- [ ] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Zachowaj kontrakty z planu i właścicieli istniejących decyzji. Błędy wejścia oznaczaj per źródło lub próbka, a błąd integralności i infrastruktury zatrzymuje zależny run. Nie promuj predykcji do ręcznego zatwierdzenia. Istotne odstępstwo wymaga aktualizacji planu przed implementacją.

## Expected files

- Istniejące `services/worker/src/game_predictor_worker/images/screen_layout_v3/engine.py::detect_screen_layout_v3` (adapter), `services/api/src/game_predictor_api/domain/board_topology.py::BoardTopology`, `package.json::openapi:check`. Nowe (proponowane) `services/worker/src/game_predictor_worker/vision_lab/contracts.py::GeometryResult`, `.../api.py::app`, `apps/vision-lab/src/app/page.tsx::Page`, `packages/vision-lab-api-client/`, `services/worker/tests/test_vision_lab_api.py`.

## Test cases

- 24/16 węzłów i poprawne cropy; uszkodzony obraz obok poprawnego; obcy Host/Origin, brak Origin, niedozwolona trasa i asset path; wygenerowany klient zgodny z OpenAPI.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_api.py') -PassThru -NoNewWindow
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
