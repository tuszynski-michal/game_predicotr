---
title: Nieblokujące ładowanie źródeł do uzupełniania luk
status: done
last_updated: 2026-09-15
---

# TASK-0557 — Nieblokujące ładowanie źródeł do uzupełniania luk

## Status

`done`

## Goal

Wybór katalogu bazowego dla `Uzupełnij luki` pokazuje postęp listowania i po
zakończeniu od razu otwiera pierwsze zdjęcie, bez oczekiwania na pomocniczy
zapis lokalnej sesji.

## Context

Katalog `D:\777\177562 -200583 cut` ma 2497 poprawnych JPEG-ów, 61 luk oraz
brak podkatalogów; sąsiedni katalog bazowy `D:\777\177562 -200583` ma 2558
obrazów i także nie ma podkatalogów. Nie ma błędu nazw ani manifestu. Obecny
widok obejmuje jedną fazą `listing_source` rekurencyjne listowanie oraz
oczekiwanie na `ManualSelectionRepairStore.save`, więc operator widzi stale
„Wczytuję listę…” bez informacji, co jeszcze trwa.

## Dependencies / entry conditions

- TASK-0554/0555 utrzymują repair manifest jako źródło prawdy, a IndexedDB
  wyłącznie dla uchwytów, trybu i ustawień widoku.
- Katalog bazowy pozostaje read-only; zmiana nie może odczytywać obrazów ani
  zapisywać JPEG-ów w trakcie jego listowania.

## Recommended execution

`gpt-6-astra` z reasoning `high`: należy rozdzielić progres listowania od
pomocniczego zapisu stanu, zachowując deterministyczne sortowanie oraz kolejkę
zapisów IndexedDB. Ponowna analiza jest wymagana, jeżeli rozwiązanie wymaga
zmiany repair manifestu, formatu handoffu lub transakcji fill/delete.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `apps/admin/src/features/manual-image-selection/manual-image-selection-fsa-adapter.ts`
- `apps/admin/src/features/manual-image-selection/manual-selection-repair-workspace.tsx`
- `apps/admin/src/features/manual-image-selection/manual-selection-repair-storage.ts`

## Scope

- Raportowanie liczby odwiedzonych wpisów i rozpoznanych obrazów podczas
  rekurencyjnego listowania katalogu bazowego.
- Oddzielenie gotowości interfejsu fill od zapisu pomocniczego rekordu
  IndexedDB, z kontrolowaną kolejnością zapisów i czytelnym błędem trwałości.
- Regresja oraz dokumentacja zachowania.

## Out of scope

- Zmiana repair manifestu, handoffu uzupełnionych luk, JPEG-ów, kolejek
  fill/delete, polityki cropów albo katalogu użytkownika.
- Zmiana wyboru źródła, sortowania naturalnego lub rekursji katalogu.

## Acceptance criteria

- [x] Podczas listowania UI pokazuje rosnącą liczbę sprawdzonych wpisów i
      znalezionych obrazów.
- [x] Po pełnym listowaniu pierwsze zdjęcie staje się dostępne bez oczekiwania
      na zapis IndexedDB.
- [x] Kolejne zapisy lokalnego stanu zachowują kolejność; błąd zapisu pokazuje
      komunikat, ale nie fałszuje sukcesu trwałego recovery.
- [x] Pusta lista, anulowanie selektora i błąd listowania zachowują obecne,
      czytelne zachowanie.
- [x] Nie zmieniono repair manifestu, handoffu ani danych katalogu podczas
      wyboru źródła.

## Technical notes

`FileSystemManualSelectionSourceAdapter.listImages` otrzyma opcjonalny callback
postępu i okresowo zwolni pętlę do renderowania, bez zmiany wyniku ani jego
naturalnego sortowania. `startFill` aktualizuje pamięciowy `localState` po
zakończeniu listowania, kończy fazę interaktywną i oddaje zapis do osobnej,
uporządkowanej kolejki IndexedDB. Błąd tej kolejki nie może udawać, że sesja
jest dostępna po restarcie; UI informuje o potrzebie ponownego wskazania
katalogu po restarcie, lecz nie zmienia już załadowanych obrazów.

## Expected files

- Istniejące: `apps/admin/src/features/manual-image-selection/manual-image-selection-fsa-adapter.ts` — postęp listowania.
- Istniejące: `apps/admin/src/features/manual-image-selection/manual-selection-repair-workspace.tsx` — UI i kolejka stanu lokalnego.
- Istniejące: `apps/admin/test/manual-local-image-selection.test.mjs` — sortowanie oraz callback postępu adaptera.
- Istniejące: `apps/admin/test/manual-selection-repair.test.mjs` — kontrakt nieblokującego wejścia fill.
- Istniejące: dokumentacja selekcji ręcznej, `CURRENT_STATE.md` i Decision Log.

## Test cases

- Katalog z wieloma wpisami i obrazami w podkatalogu → callback ma monotoniczne
  liczniki, a końcowy wynik zachowuje sortowanie.
- Po wyniku listowania pamięciowy stan fill jest dostępny przed zakończeniem
  pomocniczego zapisu IndexedDB.
- Odrzucony zapis IndexedDB → stan interaktywny pozostaje prawidłowy, a UI
  pokazuje, że po restarcie trzeba ponownie wskazać katalog.
- Anulowany picker, pusty katalog i błąd FSA → nie wejście w tryb fill.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, timeout pojedynczego kroku <= 120 s
node --experimental-strip-types --test apps/admin/test/manual-local-image-selection.test.mjs apps/admin/test/manual-selection-repair.test.mjs
node_modules\.bin\tsc --project apps/admin/tsconfig.json --noEmit
node_modules\.bin\eslint.cmd src/features/manual-image-selection/manual-image-selection-fsa-adapter.ts src/features/manual-image-selection/manual-selection-repair-workspace.tsx test/manual-local-image-selection.test.mjs test/manual-selection-repair.test.mjs
node_modules\.bin\prettier --check apps/admin/src/features/manual-image-selection/manual-image-selection-fsa-adapter.ts apps/admin/src/features/manual-image-selection/manual-selection-repair-workspace.tsx apps/admin/test/manual-local-image-selection.test.mjs apps/admin/test/manual-selection-repair.test.mjs
```

## Risks / open questions

- Liczba wszystkich wpisów katalogu nie jest znana przed końcem rekursji, więc
  UI pokazuje licznik wykonanej pracy, a nie nieuczciwy procent.
- Nie można bezpiecznie anulować aktywnego iteratora FSA poza unieważnieniem
  wyniku przez istniejący numer generacji; task zachowuje to zachowanie.

## Implementation plan

1. Dodać opcjonalny, monotoniczny postęp i okresowe oddanie renderowania do
   adaptera listującego, bez zmiany listy wynikowej.
2. Rozdzielić w workspace fazę listowania od asynchronicznego zapisu stanu;
   zapisać lokalne rekordy przez kolejkę zachowującą kolejność.
3. Pokazać postęp i ewentualny błąd trwałości, następnie dodać testy i
   zaktualizować dokumentację.

### Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0557 — Nieblokujące ładowanie źródeł do uzupełniania luk | gpt-6-astra | high | Trzeba zachować rozdział pomocniczego UI od trwałego repair workflowu i uniknąć wyścigu zapisów IndexedDB. | Nie; ponowna analiza gpt-6-astra/high tylko przy potrzebie zmiany manifestu, handoffu lub transakcji. |

## Outcome

### Changed

- `listImages` publikuje monotoniczny licznik odwiedzonych wpisów i obrazów,
  oddając renderowanie co 64 wpisy. Nie otwiera JPEG-ów i zachowuje istniejące
  naturalne sortowanie.
- `startFill` po kompletnej liście od razu ustawia pamięciowy stan `fill` i
  dopiero potem przekazuje local state do uporządkowanej kolejki IndexedDB.
  Odrzucony zapis wyjaśnia, że po restarcie trzeba ponownie wskazać źródło.
- Zweryfikowano tylko do odczytu, że katalog `177562 -200583 cut` i sąsiedni
  katalog bazowy mają poprawną strukturę; nie zmieniono żadnego pliku danych.

### Verification results

- Skoncentrowane testy Admina: 46/46.
- Pełne `npm.cmd test` w `apps/admin` — zielone.
- Typecheck, skoncentrowany ESLint i Prettier — zielone.
- Produkcyjny `npm.cmd run build` w `apps/admin` — zielony.

### Not completed

- Nie wykonano fill ani nie uruchamiano zapisu w katalogu użytkownika. Odbiór
  wizualny wymaga jedynie odświeżenia otwartej karty i ponownego wyboru źródła.

### Documentation updates

- Zaktualizowano wymagania i architekturę lokalnej korekty, `CURRENT_STATE.md`
  oraz D-391 w `DECISION_LOG.md`.

### Recommended next task

- Przy najbliższym otwarciu `177562 -200583 cut` potwierdzić w UI rosnący
  licznik listowania i przejście do pierwszego obrazu.
