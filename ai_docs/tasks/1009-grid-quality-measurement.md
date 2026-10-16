---
title: TASK-1009 — Losowa kontrola Mumii i 777a2
status: todo
last_updated: 2026-10-14
---

# TASK-1009 — Losowa kontrola Mumii i 777a2

## Status

`todo`

## Goal

Zmierzyć rodzaje błędów zamiast opierać decyzję o treningu na liczniku.

## Context

Task jest częścią zaakceptowanej rewizji 6. Dobór próby i interpretacja wyników. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1010, TASK-0993, TASK-1002 i korekta kompatybilności TASK-1018; kontrola operatora jest warunkiem raportu rzeczywistej jakości.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. poprawna populacja, próba i interpretacja.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../architecture/VISION_LAB.md).
- [VISION_LAB](../requirements/VISION_LAB.md).
- [ADMIN_APP](../requirements/ADMIN_APP.md).
- Zakres odczytu uzupełniający z planu: VISION_LAB, ADMIN_APP, sekcja pomiaru w tym planie.

## Scope

- Zamrożona losowa próba do 100 zdjęć per gra, pełna kontrola oczekiwanych pozycji, osobny zbiór trudnych przypadków.
- Wyniki zapisane z wersją i pochodzeniem.

## Out of scope

- Nie deklarować niezależności filmów bez dowodów ani jakości całej gry na podstawie celowo trudnych przykładów.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Ten sam seed i populacja odtwarzają próbę.
- [ ] Trudne przykłady nie zmieniają częstości z próby losowej.
- [ ] Brak pełnej kontroli zdjęcia jest widoczny.
- [ ] Raport rozdziela detekcję, geometrię, symbole i sekwencję.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Zamrożona losowa próba do 100 zdjęć per gra, pełna kontrola oczekiwanych pozycji, osobny zbiór trudnych przypadków. Wyniki zapisane z wersją i pochodzeniem.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [virtual_grid_geometry.py](../../services/api/src/game_predictor_api/application/virtual_grid_geometry.py) — `VirtualGridGeometryService.save_review_item`, `save_pending_slot`.
- Pozostały zakres wskazany w zaakceptowanym planie: nowe proponowane `services/api/src/game_predictor_api/application/grid_quality_measurements.py`, repozytorium i manifest pomiaru, schema/router oraz panel kontroli; dla zapisanych korekt.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_grid_quality_measurement.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Ten sam seed i populacja odtwarzają próbę.
- Trudne przykłady nie zmieniają częstości z próby losowej.
- Brak pełnej kontroli zdjęcia jest widoczny.
- Raport rozdziela detekcję, geometrię, symbole i sekwencję.

## Verification

Zakres: API, ADMIN/REVIEWER, test deterministycznego próbkowania, DOC.

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
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_operational_image_reviews.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Nie deklarować niezależności filmów bez dowodów ani jakości całej gry na podstawie celowo trudnych przykładów.

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

- Nie rozpoczęto. Docelowy zapis wyniku: wynik pomiaru albo jawny stan oczekiwania na anotacje.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-0995
