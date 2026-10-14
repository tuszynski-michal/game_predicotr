---
title: TASK-0998 — Publikacja, aktywacja, domyślna wersja i rollback
status: todo
last_updated: 2026-10-14
---

# TASK-0998 — Publikacja, aktywacja, domyślna wersja i rollback

## Status

`todo`

## Goal

Jawnie kontrolować wersję używaną przez grę i nowe zadania.

## Context

Task jest częścią zaakceptowanej rewizji 6. Aktywacje, CAS i historia wersji. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1012.
- Kontrakt oceny jest wdrożony teraz; realny PASS nowego kandydata dostarczy TASK-0997.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. wyścigi aktywacji i niezmienność zadań.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [API_CONTRACT](../architecture/API_CONTRACT.md).
- Zakres odczytu uzupełniający z planu: D-527/D-544, API_CONTRACT, kontrakt rejestru.

- [D-527](../process/decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-544](../process/decisions/DECISION_LOG_2026.md#d-544--nowe-gry-777-importują-przez-v3-z-profilem-grid_profile_777_v2) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Odrębne polecenia publish, activate, set-default i rollback.
- CAS przypisania, idempotencja i historia.
- Bazy historyczne wymagają jawnego dopuszczenia z istniejącym raportem; nowi kandydaci wymagają nowej bramki.

## Out of scope

- Bez żywej aktywacji i bez zmiany domyślnej wersji bez decyzji operatora.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Dwie konkurencyjne aktywacje nie nadpisują się; brak PASS blokuje nowego kandydata; rozpoczęty job zachowuje wersję; rollback nie zmienia wycinków.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Odrębne polecenia publish, activate, set-default i rollback. CAS przypisania, idempotencja i historia. Bazy historyczne wymagają jawnego dopuszczenia z istniejącym raportem; nowi kandydaci wymagają nowej bramki.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [grid_profile_snapshot_resolver.py](../../services/api/src/game_predictor_api/storage/grid_profile_snapshot_resolver.py) — `resolve_neural_grid_proposal`, routing profilu.
- Pozostały zakres wskazany w zaakceptowanym planie: moduły rejestru z TASK-0994, , API/schema/klient; testy aktywacji i preflightu.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_grid_model_publication_and_activation.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Dwie konkurencyjne aktywacje nie nadpisują się; brak PASS blokuje nowego kandydata; rozpoczęty job zachowuje wersję; rollback nie zmienia wycinków.

## Verification

Zakres: API, OpenAPI, DOC.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run openapi:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_catalog_api.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez żywej aktywacji i bez zmiany domyślnej wersji bez decyzji operatora.

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

- Nie rozpoczęto. Docelowy zapis wyniku: historia poleceń i dowody rozdziału bazy historycznej od kandydata.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1004
