---
title: TASK-1006 — Kandydat wspólnej geometrii Mumii i 777a2
status: todo
last_updated: 2026-10-16
---

# TASK-1006 — Kandydat wspólnej geometrii Mumii i 777a2

## Status

`todo`

## Goal

Udostępnić kontrolowany trening geometrii obu gier.

## Context

Task jest częścią zaakceptowanej rewizji 6. Wspólna kohorta i regresje między grami. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0997; kohorty obu gier; osobne zlecenie i budżet rzeczywistego runu.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

Zmiana ról na jawne polecenie operatora2026-10-16 po ukończeniu TASK-0995: Claude Code wykonuje, Codex audytuje. Historycznych raportów i wykonawców ukończonych zadań nie zmieniamy.

- Wykonawca: `claude-opus-5-5`, reasoning `high` (zamiennik `claude-fable-5-1`/`high`; wybór wykonawcy po sugestii operatora 2026-10-16, uzasadnienie w sekcji 8 planu). wspólne dane i ryzyko regresji.
- Dodatkowy review: `gpt-6-astra` (przy braku dostępności `gpt-6.1-sol`), reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../architecture/VISION_LAB.md).
- [VISION_LAB](../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: rozszerzenie D-527, VISION_LAB, reguły wspólnej kohorty.

- [D-527](../process/decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Wybór jednej bazy na VALIDATION, równoważenie gier/nagrań, dziedziczenie wyłączeń obu linii danych.
- Jeden jawny eksperyment, bez automatycznej pętli.

## Out of scope

- Brak dobrego wspólnego kandydata nie blokuje panelu i pracy na dotychczasowych wersjach.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Duża gra nie dominuje.
- [ ] Alias kontrolny nie trafia do treningu drugiej gry.
- [ ] Regresja blokuje publikację.
- [ ] Wynik nie przełącza gier automatycznie.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Wybór jednej bazy na VALIDATION, równoważenie gier/nagrań, dziedziczenie wyłączeń obu linii danych. Jeden jawny eksperyment, bez automatycznej pętli.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Pozostały zakres wskazany w zaakceptowanym planie: rejestr, kohorty, trener i ocena poprzednich tasków; nowy proponowany `services/api/src/game_predictor_api/application/shared_grid_model_candidate.py` i wersjonowana joint policy.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/worker/tests/test_shared_grid_model_candidate.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Duża gra nie dominuje.
- Alias kontrolny nie trafia do treningu drugiej gry.
- Regresja blokuje publikację.
- Wynik nie przełącza gier automatycznie.

## Verification

Zakres: API, WORKER; rzeczywisty run tylko po zgodzie i spełnieniu warunków.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_verified_training_cohorts.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_neural_grid_finetune.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Brak dobrego wspólnego kandydata nie blokuje panelu i pracy na dotychczasowych wersjach.

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

- Nie rozpoczęto. Docelowy zapis wyniku: mechanizm i wynik eksperymentu rozdzielone; brak pomiaru nie jest PASS.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1000
