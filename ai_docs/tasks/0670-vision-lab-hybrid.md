---
title: TASK-0670 — T05 — hybryda
status: todo
last_updated: 2026-09-26
---

# TASK-0670 — T05 — hybryda

## Status

`todo`

## Goal

Wytrenować pierwszą hybrydę i pokazać jej checkpoint w galerii.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

T04 done, zamrożone podziały i zatwierdzony budżet eksperymentu. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

D-456 ogranicza pierwszy rzeczywisty trening do 5 × 3: development 90 siatek,
validation 30. Final_test Reels i unseen Treasure są zamrożone i nie służą
strojeniu ani wyborowi checkpointu. Wynik pilota nie ocenia 3 × 3 ani czasu
pracy. Testy kontraktu 3 × 3 pozostają, bez deklaracji wyuczonej jakości.

## Recommended execution

`gpt-6-sol`, reasoning `high`; osobny audyt `gpt-6-astra`, reasoning `medium`. Model geometrii i bramki pewności wymagają oceny błędów na obrazach. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T05 — hybryda)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447)

## Scope

MobileNetV3-Small, lokalizacja narożników, perspektywa, opcjonalne dopasowanie, wspólne bramki, ONNX; do 50 kroków próbnych i jeden trening max 20 epok/30 min.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [ ] Porównanie na development, pierwszy poprawny checkpoint w galerii, zgodność ONNX, błędne węzły wymagają korekty.
- [ ] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Zachowaj kontrakty z planu i właścicieli istniejących decyzji. Błędy wejścia oznaczaj per źródło lub próbka, a błąd integralności i infrastruktury zatrzymuje zależny run. Nie promuj predykcji do ręcznego zatwierdzenia. Istotne odstępstwo wymaga aktualizacji planu przed implementacją.

## Expected files

- Istniejące `services/worker/src/game_predictor_worker/images/keypoint_geometry/onnx_adapter.py` (wzorzec). Nowe (proponowane) `services/worker/src/game_predictor_worker/vision_lab/hybrid.py::HybridGeometryEngine`, `.../geometry_gate.py::validate_grid`, `services/worker/tests/test_vision_lab_hybrid.py`.

## Test cases

- Perspektywa/zasłonięcie/niekompletna plansza; 5 × 3 i 3 × 3; PyTorch–ONNX na tej samej próbce; niepewna siatka nie przechodzi gate.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_hybrid.py') -PassThru -NoNewWindow
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
