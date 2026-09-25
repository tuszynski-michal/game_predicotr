---
title: TASK-0671 — T06 — etykiety symboli
status: todo
last_updated: 2026-09-25
---

# TASK-0671 — T06 — etykiety symboli

## Status

`todo`

## Goal

Zbudować zbiór symboli z weryfikowalnym pochodzeniem DB lub lab.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

T03 done; zatwierdzone słowniki lokalnych gier. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

## Recommended execution

`gpt-6-sol`, reasoning `high`; osobny audyt `gpt-6-astra`, reasoning `high`. Proweniencja cropów i słowniki decydują o legalnym wejściu danych do treningu. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T06 — etykiety symboli)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447)

## Scope

Import kwalifikujących zatwierdzeń DB, decyzje lab_human_approved, lokalne słowniki, tożsamość cropa i ponowne zatwierdzenie po recrop.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [ ] Każda próbka ma sprawdzalne źródło; unknown/unreadable/grid issue poza klasami; brak mapowania nie tworzy rekordów DB.
- [ ] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Zachowaj kontrakty z planu i właścicieli istniejących decyzji. Błędy wejścia oznaczaj per źródło lub próbka, a błąd integralności i infrastruktury zatrzymuje zależny run. Nie promuj predykcji do ręcznego zatwierdzenia. Istotne odstępstwo wymaga aktualizacji planu przed implementacją.

## Expected files

- Istniejące `services/worker/src/game_predictor_worker/symbols/training_job.py` (reguły DB). Nowe (proponowane) `services/worker/src/game_predictor_worker/vision_lab/symbol_labels.py::qualify_symbol_sample`, `apps/vision-lab/src/components/symbol-label-editor.tsx::SymbolLabelEditor`, `services/worker/tests/test_vision_lab_symbol_labels.py`.

## Test cases

- Recrop i rewizja geometrii wykluczają próbkę; predykcja nie jest approval; słownik lokalny bez DB; konflikt klasy fail-closed.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_symbol_labels.py') -PassThru -NoNewWindow
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
