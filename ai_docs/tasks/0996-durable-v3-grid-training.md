---
title: TASK-0996 — Trwały trening V3 w aplikacji
status: todo
last_updated: 2026-10-16
---

# TASK-0996 — Trwały trening V3 w aplikacji

## Status

`todo`

## Goal

Wykonać odtwarzalny run z checkpointem i wznowieniem.

## Context

Task jest częścią zaakceptowanej rewizji 6. Trener, checkpoint i wznowienie. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0995, TASK-1005, TASK-1012.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

Zmiana ról na jawne polecenie operatora2026-10-16 po ukończeniu TASK-0995: Claude Code wykonuje, Codex audytuje. Historycznych raportów i wykonawców ukończonych zadań nie zmieniamy.

- Wykonawca: `claude-opus-5-5`, reasoning `high` (zamiennik `claude-fable-5-1`/`high` na jawną decyzję operatora 2026-10-16, zapisaną w sekcji 8 planu). stan treningu i maskowanie danych.
- Dodatkowy review: `gpt-6-astra`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Review high obejmuje trwały stan runu, checkpoint i dane dowodowe; zachowuje regułę AGENTS dla schematu/dowodów.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../architecture/VISION_LAB.md).
- [VISION_LAB](../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: VISION_LAB, architektura workera i kontrakt kohort.

## Scope

- Wydzielić wspólny rdzeń z istniejącego treningu.
- Grid-only zamraża detektor i BatchNorm.
- Obsłużyć lease, postęp, cancel/resume, eksport i trwały budżet.

## Out of scope

- Bez automatycznego rzeczywistego treningu lub aktywacji.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Restart odtwarza RNG/sampler/optimizer; crash po eksporcie nie dubluje wersji; uszkodzony checkpoint nie daje gotowego kandydata; lab i produkcja używają zgodnej logiki.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Wydzielić wspólny rdzeń z istniejącego treningu. Grid-only zamraża detektor i BatchNorm. Obsłużyć lease, postęp, cancel/resume, eksport i trwały budżet.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [neural_grid_training.py](../../services/worker/src/game_predictor_worker/vision_lab/neural_grid_training.py) — `compute_losses`, `train_run`, `evaluate_network`.
- Istniejące: [neural_grid_finetune.py](../../services/worker/src/game_predictor_worker/vision_lab/neural_grid_finetune.py) — `MixedBatchSampler`, `train_iteration`, wybór kandydata.
- Istniejące: [checkpoint.py](../../services/worker/src/game_predictor_worker/training_core/checkpoint.py) — zapis, odczyt i odtworzenie checkpointu.
- Pozostały zakres wskazany w zaakceptowanym planie: model i data adapter laboratorium; nowe proponowane `services/worker/src/game_predictor_worker/training_core/grid_training.py`, `services/worker/src/game_predictor_worker/images/grid_training_handler.py`, `services/api/src/game_predictor_api/application/grid_training_runs.py` i repozytorium runów.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/worker/tests/test_durable_v3_grid_training.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Restart odtwarza RNG/sampler/optimizer; crash po eksporcie nie dubluje wersji; uszkodzony checkpoint nie daje gotowego kandydata; lab i produkcja używają zgodnej logiki.

## Verification

Zakres: WORKER, API, MIG przy encjach runów, OpenAPI, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run openapi:check
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_verified_training_datasets.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_neural_grid_finetune.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez automatycznego rzeczywistego treningu lub aktywacji.

## Outcome

### Execution phase

- Nie rozpoczęto.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit: wymagany `gpt-6-astra`, reasoning `high`; raport jeszcze nie istnieje, otwarte uwagi jeszcze nie ustalone.
- Następny krok: sprawdzić warunki wejściowe i ponownie odczytać task oraz odpowiadający fragment planu.

### Changed

- Nie rozpoczęto. Docelowy zapis wyniku: kontrakt checkpointu, testy wznowienia i ewentualny run opisany osobno.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-0997
