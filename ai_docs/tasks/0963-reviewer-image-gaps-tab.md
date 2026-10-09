---
title: TASK-0963 — Zakładka „Braki zdjęć” w lokalnym Reviewerze
status: todo
last_updated: 2026-10-10
---

# TASK-0963 — Zakładka „Braki zdjęć” w lokalnym Reviewerze

## Status

`todo`

## Goal

Operator w lokalnym Reviewerze przegląda po jednym zdjęciu realne braki geometrii
(z prawdziwym zdjęciem pod siatką), filtruje je po stanie i poprawia siatkę
wybranej pozycji istniejącym edytorem.

## Context

Plan: `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`, decyzje 1, 3–6, 8.
Dziś te zdjęcia są widoczne tylko w Adminie jako długa lista z czarnym SVG,
a poprawa siatki prowadziła do kolejki, która ich nie zawierała. Edytor
narożników i cele zapisu już istnieją; brakuje widoku na poziomie zdjęcia.

## Dependencies / entry conditions

- TASK-0961 (filtr `gapsOnly`, `humanApproved`) i TASK-0962 (zakres gry,
  zakładki) zakończone.
- Fakty z kodu: `BoardGeometryCorrectionEditor` przyjmuje `target`, `symbols`,
  `onSaved`, `onConflict`; cele budują `deferredBoardGeometryTarget` i
  `reportedBoardGeometryTarget` z `ImageGridReviewItemResponse`;
  `listImageGridReviews` przyjmuje `sourceImageId` i `view=all` (obejmuje także
  sloty odroczone).
- Niewiadoma do sprawdzenia na początku: czy `reportedBoardGeometryTarget`
  poprawnie obsługuje pozycję bez zgłoszonych pól (`reportedCellIndices` puste)
  i planszę `partial`. Jeśli nie — minimalna korekta celu, bez nowej ścieżki
  zapisu; zapis w `Outcome`.

## Recommended execution

`claude-fable-5-1`, `high` — zgodnie z tabelą planu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-462, D-484, D-488)

## Scope

1. Zakładka „Braki zdjęć” w `LocalReviewerWorkspace` (zastępuje zaślepkę z
   TASK-0962): komponent `GeometryGapsWorkspace` (propozycja).
2. Dane: `getImageGeometryCompleteness({gameId})` dla liczników filtrów;
   `listIncompleteGeometryImages({gameId, gapsOnly: true})` albo
   `{gameId, imageState}` dla filtra szczegółowego; strony po 25, kursor,
   dociąganie następnej strony, gdy do końca zostały ≤ 3 zdjęcia. Odświeżenie
   po zapisie i przyciskiem „Odśwież”.
3. Filtry (przyciski z licznikiem): „Wszystkie braki” (domyślny), „Brakuje
   plansz”, „Plansza częściowa”, „Import nieudany”, „Bez geometrii źródła”.
   Przełącznik „Pokaż także zatwierdzone ręcznie” (domyślnie wyłączony):
   zdjęcie, w którym wszystkie pozycje `partial` mają `humanApproved`, jest
   ukrywane po stronie klienta. Pusty stan filtra: „Brak zdjęć w tym stanie”.
4. Widok zdjęcia (jedno naraz, „← Poprzednie / Następne →”, licznik pozycji w
   kolejce): prawdziwe zdjęcie ładowane automatycznie
   (`getImageGeometryCompletenessSourceAsset`, blob URL unieważniany przy
   zmianie zdjęcia i odmontowaniu) z nakładką SVG siatek i numerów pozycji;
   ścieżka względna, stan zdjęcia, zakres numerów, oczekiwane plansze, kod błędu
   importu z opisem; lista pozycji z etykietą stanu, powodem i znaczkiem
   „zatwierdzona ręcznie”.
5. Edycja pozycji: przy pozycji, dla której `listImageGridReviews({gameId,
   sourceImageId, view: 'all', limit: 100, counts: 'correction'})` zwraca
   wiersz o tym `positionIndex`, przycisk „Popraw siatkę tej planszy” otwiera
   `BoardGeometryCorrectionEditor` pod widokiem zdjęcia (cel: slot odroczony →
   `deferredBoardGeometryTarget`, plansza → `reportedBoardGeometryTarget`).
   Po zapisie: komunikat, odświeżenie bieżącego zdjęcia i liczników.
   Pozycje bez wiersza: tekst „Brak planszy i slotu do ręcznej korekty —
   przetwórz zdjęcie ponownie w Imporcie plansz” bez przycisku.
6. Stany `import_failed` i `no_source_geometry`: zdjęcie (jeśli dostępne),
   kod błędu, wskazówka; bez edytora.
7. Czyste funkcje (mapowanie etykiet stanów, punkty SVG, filtr „ukryj
   zatwierdzone ręcznie”) w osobnym module z testami jednostkowymi.

## Out of scope

- Ustawianie i wycofywanie wyjątków bramki (zabronione z origin Reviewera,
  decyzja 6 planu).
- Zatwierdzanie gotowych siatek, kolejka „Siatka niepotwierdzona”.
- Zmiana klasyfikacji stanów; nowe endpointy.
- Zakładka „Do korekty” (bez zmian).

## Acceptance criteria

- [ ] Mumie: filtr „Wszystkie braki” pokazuje 4 zdjęcia (1 „Brakuje plansz”,
      3 „Import nieudany”); 777: zdjęcia „Plansza częściowa”, domyślnie bez
      już zatwierdzonych ręcznie.
- [ ] Zdjęcie jest widoczne od razu, bez klikania; nakładka siatek zgodna z
      pozycjami; po zmianie zdjęcia poprzedni blob URL unieważniony.
- [ ] Pozycja z planszą/slotem otwiera edytor; zapis kończy się komunikatem i
      odświeżeniem; konflikt rewizji pokazuje komunikat bez pętli.
- [ ] Pozycja bez celu edycji nie ma przycisku i pokazuje wskazówkę.
- [ ] Filtry zmieniają listę i liczniki; pusty stan jest czytelny.
- [ ] Brak błędów konsoli; testy, typecheck i lint Reviewera zielone.

## Technical notes

Źródło prawdy dla stanu pozycji to odpowiedź `incomplete-images`; źródło
prawdy dla celu edycji to wiersz `grid-reviews` dla pary `(sourceImageId,
positionIndex)` — nie zgaduj celu z samego stanu pozycji. Zapytanie o wiersze
wykonuj leniwie, przy otwarciu zdjęcia, nie dla całej strony. Nie osadzaj
logiki Admina: pomocnicze funkcje SVG (`quadSvgPoints`, `quadCentre`) i
etykiety stanów kopiujesz do modułu Reviewera — kopia w Adminie znika w
TASK-0964, więc nie zostaje duplikat. Edytor montuj z `key` zależnym od
`target.key`, jak w `BoardGeometryCorrectionWorkspace`. Błędy sieci mapuj na
komunikaty bez ogólnego przechwytywania wyjątków programistycznych.

## Expected files

- Istniejące: `apps/reviewer/src/features/access/local-reviewer-workspace.tsx`,
  `apps/reviewer/src/features/operational-reviews/board-geometry-correction-target.ts`
  (tylko jeśli niewiadoma o `reportedBoardGeometryTarget` tego wymaga).
- Nowe (proponowane):
  `apps/reviewer/src/features/operational-reviews/geometry-gaps-workspace.tsx`,
  `apps/reviewer/src/features/operational-reviews/geometry-gaps-state.ts`,
  `apps/reviewer/test/geometry-gaps-state.test.mjs`,
  `apps/reviewer/test-interactions/geometry-gaps-workspace.test.mjs`.

## Test cases

- Stan: etykiety stanów; `quadSvgPoints` zwraca `null` dla czworokąta
  niepełnego/nieskończonego; filtr ukrywający zdjęcia, których wszystkie
  `partial` mają `humanApproved`.
- Interakcja: lista 3 zdjęć → nawigacja Następne/Poprzednie; zmiana filtra
  wywołuje `listIncompleteGeometryImages` z właściwym parametrem; zdjęcie
  ładuje się bez kliknięcia; pozycja z wierszem kolejki otwiera edytor, bez
  wiersza pokazuje wskazówkę; konflikt zapisu → komunikat.
- `import_failed`: kod błędu i brak edytora.

## Verification

```powershell
# katalog: korzeń worktree; timeout <= 120 s na komendę
npm run test --workspace @game-predictor/reviewer
npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
```

Zaliczenie: wszystkie zielone; odbiór na żywych danych w TASK-0965. Testy
planowane nie są wynikami wykonania.

## Risks / open questions

- Strona `incomplete-images` trwa 5–11 s (cały zakres gry): UI musi pokazać
  stan ładowania i nie blokować nawigacji po już pobranych zdjęciach.
- Zdjęcia `partial` zakwalifikowane ręcznie wracają do listy po włączeniu
  przełącznika — świadome (decyzja 8).

## Outcome

Wypełnia agent po pracy.

### Changed

- ...

### Verification results

- ...

### Not completed

- ...

### Documentation updates

- ...

### Recommended next task

- TASK-0964 (po odbiorze etapu A)
