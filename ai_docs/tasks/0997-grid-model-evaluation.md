---
title: TASK-0997 — Ocena per gra i bramka kandydata
status: todo
last_updated: 2026-10-14
---

# TASK-0997 — Ocena per gra i bramka kandydata

## Status

`todo`

## Goal

Zapobiec publikacji poprawy jednej gry kosztem drugiej.

## Context

Task jest częścią zaakceptowanej rewizji 6. Metryki i bramka osobno dla gier. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0996 i niezależne, kompletne dane kontrolne.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. metryki i kwalifikacja publikacji.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../architecture/VISION_LAB.md).
- [VISION_LAB](../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: D-483, VISION_LAB, reguły oceny tego planu.

- [D-483](../process/decisions/DECISION_LOG_2026.md#d-483--metryka-nadrzędna-silnika-siatek-odsetek-zdjęć-kompletnych-i-poprawnych) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Identyczne źródła dla bazy i kandydata, pełny inference od zdjęcia, wyniki per gra/nagranie.
- Wersjonowane definicje metryk.
- REGRESSION tylko do końcowej kontroli.

## Out of scope

- Nie zastępować nieznanej jakości zerowym błędem.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Regresja dowolnej gry blokuje wspólny PASS.
- [ ] Brak detekcji ma koszt.
- [ ] Brak danych, parity lub aktualnych dowodów blokuje publikację.
- [ ] Dobór checkpointu nie używa REGRESSION.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Identyczne źródła dla bazy i kandydata, pełny inference od zdjęcia, wyniki per gra/nagranie. Wersjonowane definicje metryk. REGRESSION tylko do końcowej kontroli.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [neural_grid_training.py](../../services/worker/src/game_predictor_worker/vision_lab/neural_grid_training.py) — `compute_losses`, `train_run`, `evaluate_network`.
- Istniejące: [gate.py](../../services/worker/src/game_predictor_worker/geometry_core/gate.py) — `GateThresholds`, `compare`, `decide`, `gate_photo`.
- Pozostały zakres wskazany w zaakceptowanym planie: i istniejące metryki; nowe proponowane `services/worker/src/game_predictor_worker/training_core/grid_evaluation.py`, `services/api/src/game_predictor_api/application/grid_model_evaluation.py`, `grid-model-comparison.tsx`.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/worker/tests/test_grid_model_evaluation.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Regresja dowolnej gry blokuje wspólny PASS.
- Brak detekcji ma koszt.
- Brak danych, parity lub aktualnych dowodów blokuje publikację.
- Dobór checkpointu nie używa REGRESSION.

## Verification

Zakres: WORKER, API, ADMIN, OpenAPI.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run openapi:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_verified_training_datasets.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_neural_grid.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Nie zastępować nieznanej jakości zerowym błędem.

## Outcome

### Execution phase

- Nie rozpoczęto.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit: wymagany `claude-fable-5-1`, reasoning `medium`; raport jeszcze nie istnieje, otwarte uwagi jeszcze nie ustalone.
- Następny krok: sprawdzić warunki wejściowe i ponownie odczytać task oraz odpowiadający fragment planu.

### Changed

- Nie rozpoczęto. Docelowy zapis wyniku: porównanie, wersja polityki i powody PASS/REVISE/braku możliwości oceny.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1006
