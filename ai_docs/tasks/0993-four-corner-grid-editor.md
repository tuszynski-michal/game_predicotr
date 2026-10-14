---
title: TASK-0993 — Edytor czterech rogów i 24 punktów
status: todo
last_updated: 2026-10-14
---

# TASK-0993 — Edytor czterech rogów i 24 punktów

## Status

`todo`

## Goal

Przyspieszyć korekty przesuniętej siatki bez utraty dokładnych węzłów.

## Context

Task jest częścią zaakceptowanej rewizji 6. Geometria edytora i zachowanie węzłów. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1015.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `medium`. istniejący kontrakt i ograniczona geometria.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [ADMIN_APP](../requirements/ADMIN_APP.md).
- [API_CONTRACT](../architecture/API_CONTRACT.md).
- Zakres odczytu uzupełniający z planu: ADMIN_APP, API_CONTRACT, reguły edytora w tym planie.

## Scope

- Oddzielić tryb uchwytów od danych.
- Dodać transformację wszystkich węzłów, przesunięcie całości, jawny reset, undo i konflikt szkicu.

## Out of scope

- Bez zmiany topologii, danych operatora i klasyfikacji symboli.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Roundtrip 24→4→24 zachowuje liczby.
- [ ] Homografia, translacja, reset/undo, błędny quad, dotyk i reload są sprawdzone.
- [ ] Podgląd i zapis mają zgodne wycinki.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Oddzielić tryb uchwytów od danych. Dodać transformację wszystkich węzłów, przesunięcie całości, jawny reset, undo i konflikt szkicu.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [board-lattice-state.ts](../../apps/reviewer/src/features/operational-reviews/board-lattice-state.ts) — `boardLatticePayload`, `translatedBoardLattice`; [edytor](../../apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx) — `BoardGeometryCorrectionEditor`, `DeferredBoardCellGeometryEditor`.
- Istniejące: [board-lattice-draft-storage.ts](../../apps/reviewer/src/features/operational-reviews/board-lattice-draft-storage.ts) — odczyt i zapis szkiców.
- Pozostały zakres wskazany w zaakceptowanym planie: testy interakcji Reviewera; opcjonalne rozszerzenie transportu tylko jeśli obecny kontrakt nie przenosi wymaganych danych.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `apps/reviewer/src/features/operational-reviews/four_corner_grid_editor.test.ts`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Roundtrip 24→4→24 zachowuje liczby.
- Homografia, translacja, reset/undo, błędny quad, dotyk i reload są sprawdzone.
- Podgląd i zapis mają zgodne wycinki.

## Verification

Zakres: REVIEWER, API przy zmianie transportu, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run test:geometry --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_virtual_grid_geometry.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez zmiany topologii, danych operatora i klasyfikacji symboli.

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

- Nie rozpoczęto. Docelowy zapis wyniku: interakcje, testy regresji i ograniczenia obsługiwanych geometrii.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1014
