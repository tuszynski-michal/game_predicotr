---
title: TASK-1002 — Nagrania, aliasy i role kontrolne
status: todo
last_updated: 2026-10-14
---

# TASK-1002 — Nagrania, aliasy i role kontrolne

## Status

`todo`

## Goal

Zapobiec przeciekowi między treningiem i oceną.

## Context

Task jest częścią zaakceptowanej rewizji 6. Pochodzenie i niezależność nagrań. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0994.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. pochodzenie danych między grami i rodzinami.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../architecture/VISION_LAB.md).
- [VISION_LAB](../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: VISION_LAB, D-480/D-527, reguły kohorty tego planu.

- [D-480](../process/decisions/DECISION_LOG_2026.md#d-480--zatwierdzona-geometria-produkcyjna-777-jako-dane-uczące-geometrii-zmienia-d-453) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-527](../process/decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Trwałe grupy nagrań, deklaracje operatora, aliasy, byte/pixel SHA, TRAIN/VALIDATION/REGRESSION i wyłączenia przodków.
- Folder jest sugestią, nie dowodem niezależności.

## Out of scope

- Bez przenoszenia plików źródłowych i zmiany sekwencji.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Alias w innej grze zachowuje rolę.
- [ ] Holdout rodzica nie trafia do TRAIN dziecka.
- [ ] Brak deklaracji nie daje niezależności.
- [ ] Role przeżywają restart.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Trwałe grupy nagrań, deklaracje operatora, aliasy, byte/pixel SHA, TRAIN/VALIDATION/REGRESSION i wyłączenia przodków. Folder jest sugestią, nie dowodem niezależności.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Pozostały zakres wskazany w zaakceptowanym planie: nowe proponowane `services/api/src/game_predictor_api/domain/source_recording_groups.py`, warstwa application/storage, migracja, API i `recording-groups-panel.tsx`.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_source_recording_groups.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Alias w innej grze zachowuje rolę.
- Holdout rodzica nie trafia do TRAIN dziecka.
- Brak deklaracji nie daje niezależności.
- Role przeżywają restart.

## Verification

Zakres: API, MIG, ADMIN, OpenAPI, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run openapi:check
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_verified_training_cohorts.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez przenoszenia plików źródłowych i zmiany sekwencji.

## Outcome

### Execution phase

- Nie rozpoczęto.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit: wymagany `claude-fable-5-1`, reasoning `high`; raport jeszcze nie istnieje, otwarte uwagi jeszcze nie ustalone.
- Następny krok: sprawdzić warunki wejściowe i ponownie odczytać task oraz odpowiadający fragment planu.

### Changed

- Nie rozpoczęto. Docelowy zapis wyniku: pochodzenie grup, nierozstrzygnięte nagrania i blokady kwalifikacji.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1009
