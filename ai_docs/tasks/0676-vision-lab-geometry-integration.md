---
title: TASK-0676 — T11 — geometria w aplikacji
status: todo
last_updated: 2026-09-26
---

# TASK-0676 — T11 — geometria w aplikacji

## Status

`todo`

## Goal

Wprowadzić kandydata geometrii do review/shadow tylko dla 5 × 3, także
równolegle do starego silnika na zdjęciu istniejącej gry `777 v1.1`.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

STOP C lub D z zamrożonym kandydatem i jawne uruchomienie E. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

## Recommended execution

`gpt-6-sol`, reasoning `medium`; osobny audyt `gpt-6-astra`, reasoning `medium`. Rewizje geometrii i ochrona decyzji człowieka wymagają spójnego pionu API–UI. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T11 — geometria w aplikacji)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447, D-453, D-461)

## Scope

Spójny pion backend–OpenAPI–klient–UI, zachowanie właściciela geometrii i rewizji człowieka, domyślnie wyłączony silnik.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [ ] 3 × 3 daje czytelny unsupported bez dopełnienia do 15 i bez zapisu; stare przepływy bez regresji.
- [ ] Na tym samym niezmiennym obrazie `777 v1.1` można w jednym widoku porównać geometrię starego silnika i v3, wraz z wersjami, bez tworzenia kopii gry; nazwa/wydanie gry i `comparison_only` nie blokują inferencji v3. V3 nie nadpisuje starego wyniku ani rewizji człowieka.
- [ ] Brak mapowania symboli nie blokuje porównania geometrii; niedopasowane pozycje i błędy są jawne.
- [ ] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Zachowaj kontrakty z planu i właścicieli istniejących decyzji. Błędy wejścia oznaczaj per źródło lub próbka, a błąd integralności i infrastruktury zatrzymuje zależny run. Nie promuj predykcji do ręcznego zatwierdzenia. Istotne odstępstwo wymaga aktualizacji planu przed implementacją.

## Expected files

- Istniejące `services/api/src/game_predictor_api/application/image_grid_reviews.py::ImageGridReviewService`, `services/api/src/game_predictor_api/api/image_grid_reviews.py::create_image_grid_reviews_router`, `services/worker/src/game_predictor_worker/images/keypoint_geometry/geometry_engine.py::KeypointGeometryEngine`, `packages/admin-api-client/src/index.ts::createAdminApiClient`, `apps/reviewer/src/api/admin-api-client.ts::createConfiguredAdminApiClient`, `apps/reviewer/src/features/grid-reviews/grid-review-workspace.tsx::GridReviewWorkspace`.
- Nowe (proponowane) `services/worker/src/game_predictor_worker/images/vision_lab_shadow_adapter.py::VisionLabShadowGeometryAdapter`, `services/api/tests/test_vision_lab_geometry_review_api.py::test_shadow_3x3_rejected`, `services/worker/tests/test_vision_lab_shadow_adapter.py::test_5x3_shadow`, `apps/reviewer/test/grid-review-vision-lab.test.mjs::shadowReview`; generowany OpenAPI i klient/wrapper w tym samym pionie.

## Test cases

- Shadow nie nadpisuje człowieka; 3 × 3 bez mutacji; 5 × 3 pełny pion API–OpenAPI–klient–wrapper–UI i regresja starego silnika. Żądanie API dla nieobsługiwanej topologii daje stabilny błąd bez zapisu.
- Scenariusz `777 v1.1`: dwa wyniki na tym samym SHA, niezależne wersje, bez odczytu dawnej predykcji przez adapter v3 i bez mutacji starej ścieżki.

## Verification

Z katalogu repozytorium (proponowane nowe testy powstają w tym tasku):

```powershell
function Invoke-Limited([string]$File, [string[]]$Arguments) {
  $p = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru -NoNewWindow
  if (-not $p.WaitForExit(120000)) { $p.Kill(); throw "$File timeout 120s" }
  if ($p.ExitCode -ne 0) { throw "$File exit $($p.ExitCode)" }
}
Invoke-Limited '.\.venv\Scripts\python.exe' @('-m','pytest','services/api/tests/test_vision_lab_geometry_review_api.py','services/worker/tests/test_vision_lab_shadow_adapter.py','services/worker/tests/test_keypoint_geometry_engine.py')
Invoke-Limited 'npm.cmd' @('run','openapi:check')
Invoke-Limited 'npm.cmd' @('run','test','--workspace','@game-predictor/reviewer')
Invoke-Limited 'npm.cmd' @('run','lint','--workspace','@game-predictor/reviewer')
Invoke-Limited 'npm.cmd' @('run','typecheck','--workspace','@game-predictor/reviewer')
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
