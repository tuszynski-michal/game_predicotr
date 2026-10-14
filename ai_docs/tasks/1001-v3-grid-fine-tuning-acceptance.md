---
title: TASK-1001 — Odbiór procesu i instrukcja operatora
status: todo
last_updated: 2026-10-14
---

# TASK-1001 — Odbiór procesu i instrukcja operatora

## Status

`todo`

## Goal

Potwierdzić działanie całego procesu i możliwość dalszej pracy bez historii czatu.

## Context

Task jest częścią zaakceptowanej rewizji 6. Odbiór procesu i dokumentacja trwałości. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- Ukończone piony aplikacji i audyty.
- Odbiór na rzeczywistych danych wymaga właściwych zgód i anotacji; wynik wspólnego modelu raportowany oddzielnie.
- Istniejąca kopia operatora: `D:\game_predictor_backup`, wskazana 2026-10-14 jako wystarczająco aktualna. Nie tworzyć nowego snapshotu ani dodatkowego backupu bazy. Nie mylić tego z niezmiennymi snapshotami kohort treningowych.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `medium`. integracja i dowody trwałości.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [DEFINITION_OF_DONE](../process/DEFINITION_OF_DONE.md).
- [AUDIT_REPORT_TEMPLATE](../quality/AUDIT_REPORT_TEMPLATE.md).
- Zakres odczytu uzupełniający z planu: DEFINITION_OF_DONE, AUDIT_REPORT_TEMPLATE, dokumenty właścicielskie tasków.

## Scope

- E2E na izolowanej bazie: korekta → kohorta → run → ocena → aktywacja → wybrany przebieg → restart.
- Osobno aktualna baza bez treningu, propozycja i przyjęcie przez człowieka.

## Out of scope

- Bez automatycznego wdrożenia, push, migracji operatora i masowego przetwarzania.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Proces działa po restarcie i utracie odpowiedzi; obie gry i nowa gra zachowują izolację symboli.
- [ ] Stara 777 ma regresję.
- [ ] Rzeczywiste liczby i ograniczenia są opisane bez domniemanych wyników.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

E2E na izolowanej bazie: korekta → kohorta → run → ocena → aktywacja → wybrany przebieg → restart. Osobno aktualna baza bez treningu, propozycja i przyjęcie przez człowieka.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Pozostały zakres wskazany w zaakceptowanym planie: nowe proponowane `ai_docs/guides/V3_GRID_FINE_TUNING_OPERATOR.md`, `ai_docs/quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md`, testy odbiorowe; wymagania, architektura, mapy i stan.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_v3_grid_fine_tuning_acceptance.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Proces działa po restarcie i utracie odpowiedzi; obie gry i nowa gra zachowują izolację symboli.
- Stara 777 ma regresję.
- Rzeczywiste liczby i ograniczenia są opisane bez domniemanych wyników.

## Verification

Zakres: API, WORKER, ADMIN, REVIEWER, wymagane buildy, OpenAPI, DOC, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run openapi:check
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_virtual_grid_geometry.py services/api/tests/test_catalog_api.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_training_core.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez automatycznego wdrożenia, push, migracji operatora i masowego przetwarzania.

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

- Nie rozpoczęto. Docelowy zapis wyniku: wyniki techniczne, odbiór operatora, zakres niewykonany, gałąź i dokładne commity gotowe do akceptacji.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- Zamknięcie całego zleconego zakresu, akceptacja wyniku i osobna zgoda na integrację.
