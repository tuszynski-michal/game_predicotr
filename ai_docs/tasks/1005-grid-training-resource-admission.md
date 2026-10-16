---
title: TASK-1005 — Preset i dopuszczenie zasobów
status: todo
last_updated: 2026-10-16
---

# TASK-1005 — Preset i dopuszczenie zasobów

## Status

`todo`

## Goal

Ustalić jawny budżet runu na podstawie danych.

## Context

Task jest częścią zaakceptowanej rewizji 6. Pomiar kosztu i wersjonowany preset. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0995; osobna zgoda na ograniczony pomiar GPU.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

Zmiana ról na jawne polecenie operatora2026-10-16 po ukończeniu TASK-0995: Claude Code wykonuje, Codex audytuje. Historycznych raportów i wykonawców ukończonych zadań nie zmieniamy.

- Wykonawca: `claude-fable-5-1`, reasoning `medium`. parametry wynikają z raportów i mierzalnego testu.
- Dodatkowy review: `gpt-6-astra`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [Przekazanie po zamianie ról](../guides/V3_GRID_FINE_TUNING_ROLE_HANDOFF.md).
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../architecture/VISION_LAB.md).
- [VISION_LAB](../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: VISION_LAB i raporty dotychczasowych iteracji Mumii.

## Scope

- Osobne presety grid-only/screen+grid, koszt kohorty, early stopping i limit czasu/kroków.
- Smoke kończy się po 50 krokach albo 120 sekundach, zależnie co nastąpi pierwsze.
- Dzierżawa obejmuje app grid runs.

## Out of scope

- Bez obietnicy kontroli wszystkich zewnętrznych procesów CUDA i bez zmian trenera symboli.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Brak GPU, niezgodny runtime, zajęta dzierżawa lub brak zatwierdzonego presetu blokuje run.
- [ ] Resume nie odnawia budżetu.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Osobne presety grid-only/screen+grid, koszt kohorty, early stopping i limit czasu/kroków. Smoke kończy się po 50 krokach albo 120 sekundach, zależnie co nastąpi pierwsze. Dzierżawa obejmuje app grid runs.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [neural_grid_finetune.py](../../services/worker/src/game_predictor_worker/vision_lab/neural_grid_finetune.py) — `MixedBatchSampler`, `train_iteration`, wybór kandydata.
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

- Nie rozpoczęto.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit: wymagany `gpt-6-astra`, reasoning `medium`; raport jeszcze nie istnieje, otwarte uwagi jeszcze nie ustalone.
- Następny krok: sprawdzić warunki wejściowe i ponownie odczytać task oraz odpowiadający fragment planu.

### Changed

- Nie rozpoczęto. Docelowy zapis wyniku: uzasadniony preset, wynik pomiaru i ograniczenia.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-0996
