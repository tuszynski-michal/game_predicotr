---
title: TASK-0963 — Zakładka „Braki zdjęć” w lokalnym Reviewerze
status: done
last_updated: 2026-10-10
---

# TASK-0963 — Zakładka „Braki zdjęć” w lokalnym Reviewerze

## Status

`done`

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

- [x] Mumie: filtr „Wszystkie braki” pokazuje 4 zdjęcia (1 „Brakuje plansz”,
      3 „Import nieudany”); 777: zdjęcia „Plansza częściowa”, domyślnie bez
      już zatwierdzonych ręcznie. (Zweryfikowane testami z fixturami: licznik
      „Wszystkie braki (4)”, „Brakuje plansz (1)”, „Import nieudany (3)” i
      ukrywanie zatwierdzonych ręcznie; odbiór na żywych danych w TASK-0965.)
- [x] Zdjęcie jest widoczne od razu, bez klikania; nakładka siatek zgodna z
      pozycjami; po zmianie zdjęcia poprzedni blob URL unieważniony.
      (Test interakcji z fixturą; wyświetlenie prawdziwego pliku — TASK-0965.)
- [x] Pozycja z planszą/slotem otwiera edytor; zapis kończy się komunikatem i
      odświeżeniem; konflikt rewizji pokazuje komunikat bez pętli.
- [x] Pozycja bez celu edycji nie ma przycisku i pokazuje wskazówkę.
- [x] Filtry zmieniają listę i liczniki; pusty stan jest czytelny.
- [x] Brak błędów konsoli; testy, typecheck i lint Reviewera zielone.
      (Testy, typecheck i lint zielone; konsola przeglądarki — TASK-0965.)

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

### Changed

- Nowy `apps/reviewer/src/features/operational-reviews/geometry-gaps-state.ts`:
  czyste funkcje zakładki — filtry (`GEOMETRY_GAPS_FILTERS`, etykiety,
  liczniki z raportu kompletności), zapytanie strony
  (`geometryGapsListQuery`: `gapsOnly` dla „Wszystkie braki”, inaczej jeden
  `imageState`, nigdy oba), reguła ukrywania zdjęć z samymi zatwierdzonymi
  ręcznie pozycjami `partial` (`allPartialPositionsHumanApproved`,
  `visibleGapImages`), dociąganie strony (`shouldPrefetchNextPage`, próg 3),
  dobór celu edycji z wierszy `grid-reviews`
  (`geometryGapPositionTarget`: bieżąca plansza przed slotem odroczonym, brak
  wiersza → `null`), etykiety stanów/powodów/błędów importu, tony oraz
  `quadSvgPoints`/`quadCentre` skopiowane z Admina (bez importu z `apps/admin`).
- Nowy `apps/reviewer/src/features/operational-reviews/geometry-gaps-workspace.tsx`
  (`GeometryGapsWorkspace`): liczniki z `getImageGeometryCompleteness`,
  strony po 25 z kursorem i dociąganiem, gdy do końca zostały ≤ 3 widoczne
  zdjęcia (także gdy filtr ukrył całą pobraną stronę); jedno zdjęcie naraz z
  „← Poprzednie / Następne →” i licznikiem `Zdjęcie X z Y(+)`; przyciski
  filtrów z licznikami i przełącznik „Pokaż także zatwierdzone ręcznie”
  (domyślnie wyłączony, filtr po stronie klienta); zdjęcie ładowane
  automatycznie przez `getImageGeometryCompletenessSourceAsset` (blob URL
  unieważniany przy zmianie zdjęcia i odmontowaniu, komunikat „Zdjęcie
  źródłowe jest niedostępne” przy braku pliku) z nakładką SVG siatek i
  numerów; ścieżka, stan, status źródła, zakres numerów, oczekiwane plansze,
  kod błędu importu z opisem; lista pozycji ze stanem, powodem i znaczkiem
  „zatwierdzona ręcznie”. Cele edycji z
  `listImageGridReviews({gameId, sourceImageId, view: 'all', limit: 100,
  counts: 'correction'})` pobierane leniwie dla otwartego zdjęcia (nie dla
  stanów `import_failed`/`no_source_geometry`, które dostają wskazówkę bez
  edytora); pozycja z wierszem ma przycisk „Popraw siatkę tej planszy”
  montujący `BoardGeometryCorrectionEditor` (`key={target.key}`, cel
  `deferredBoardGeometryTarget` albo `reportedBoardGeometryTarget`,
  `saveLabel` „Zapisz siatkę pozycji”), pozycja bez wiersza pokazuje tekst
  wskazówki bez przycisku. Zapis: komunikat, zamknięcie edytora, odświeżenie
  liczników, listy (z zachowaniem wybranego zdjęcia) i celów. Konflikt
  rewizji: komunikat, zamknięcie edytora i jedno odświeżenie — bez pętli, bo
  edytor jest odmontowany do czasu ponownego otwarcia pozycji. Błędy sieci
  mapowane przez `apiErrorMessage` i stały komunikat o przerwanym
  połączeniu; przycisk „↻ Odśwież”.
- `apps/reviewer/src/features/access/local-reviewer-workspace.tsx`:
  zaślepka zastąpiona `GeometryGapsWorkspace` z `keyboardEnabled={tab ===
  'gaps'}`; edytor „Do korekty” pozostaje `keyboardEnabled={tab ===
  'correction'}` (mechanizm z TASK-0962).
- `apps/reviewer/src/features/operational-reviews/board-geometry-correction-target.ts`:
  `reportedBoardGeometryTarget` — `saveHint` zależny od zgłoszeń (plansza bez
  zgłoszonych pól dostaje tekst o nowej rewizji zamiast „usuwa zgłoszenia
  «Zła siatka»”); ścieżka zapisu, klucz, podgląd i symbole bez zmian.
- `apps/reviewer/src/app/reviewer.css`: style zakładki (`geometryGaps*`).
- Testy: nowy `apps/reviewer/test/geometry-gaps-state.test.mjs` (9 testów:
  filtry, zapytanie, liczniki, etykiety/tony, `quadSvgPoints` dla czworokąta
  niepełnego/nieskończonego, ukrywanie zatwierdzonych ręcznie, próg
  dociągania, dobór celu); nowy
  `apps/reviewer/test-interactions/geometry-gaps-workspace.test.mjs`
  (8 testów: nawigacja po 3 zdjęciach z automatycznym pobraniem zdjęcia i
  unieważnianiem blob URL, filtr z właściwym parametrem i pusty stan, slot
  odroczony otwiera edytor / pozycja bez wiersza pokazuje wskazówkę / zapis
  odświeża, plansza `partial` otwiera się jako częściowa i konflikt daje jeden
  komunikat bez pętli, `import_failed` z kodem błędu bez edytora i bez
  zapytania o wiersze, brak pliku źródłowego, przełącznik zatwierdzonych
  ręcznie, dociąganie strony przy ≤ 3 pozostałych);
  `board-geometry-correction.test.mjs` (atrapy metod zakładki, asercja
  zaślepki → pusty stan zakładki), `local-reviewer-workspace-contract.test.mjs`
  (brak zaślepki, `keyboardEnabled` obu zakładek, nowy test źródła: bez
  wyjątków bramki i importów z Admina).
- Mapa kodu zregenerowana (`CODE_MAP.md`, `CODE_MAP_SYMBOLS.md`).

Poprawki po audycie (sonnet, read-only, PASS z uwagami P2), wszystkie w
`geometry-gaps-workspace.tsx` i teście interakcji:

- Błąd dociągania następnej strony nie zastępuje widoku: lista zostaje
  `ready`, pobrane zdjęcia są nadal osiągalne, nad artykułem pojawia się
  baner z przyciskiem „Ponów pobieranie” (ponowienie po `nextCursor`); bez
  automatycznej pętli ponowień. Błąd pierwszej strony bez zmian (widok błędu
  i „Spróbuj ponownie”).
- „↻ Odśwież” oraz odświeżenie po zapisie/konflikcie są ciche: widok nie jest
  zasłaniany stanem ładowania, strony są czytane od początku po kursorze, aż
  wróci otwarte zdjęcie (albo tyle zdjęć, ile było), i podmieniane naraz;
  bieżące zdjęcie wybierane po `sourceImageId` także ze stron dalszych niż
  pierwsza. Edytor otwarty przy odświeżeniu przyciskiem nie jest
  odmontowywany: cel edycji jest stabilny po `target.key`, więc niezapisane
  narożniki przetrwają, a edytor przeładowuje się tylko, gdy zmieniła się
  rewizja planszy. Zdjęcie, które opuściło kolejkę, przełącza na pierwsze i
  zamyka edytor.
- Podczas ponownego pobierania celów (`rowsState === 'loading'`) przyciski
  „Popraw siatkę tej planszy” są wyłączone i widać status „Sprawdzam cele
  edycji pozycji…” — nieaktualny wiersz nie otworzy edytora.
- Pod filtrami zwięzły opis: liczniki to stan w bazie (z liczbą „Plansza
  częściowa”), a lista domyślnie ukrywa zdjęcia z samymi zatwierdzonymi
  ręcznie planszami częściowymi; logika filtra bez zmian.
- 5 nowych testów interakcji: błąd dociągania (baner, nawigacja po pobranych,
  ponowienie), błąd pierwszej strony i „Spróbuj ponownie”, błąd
  `listImageGridReviews` z ponowieniem, wyścig przy zmianie filtra (spóźniona
  odpowiedź nie nadpisuje), odświeżenie zachowujące zdjęcie ze strony drugiej
  i zamontowany edytor (ten sam `canvas`, bez nowego podglądu i zdjęcia).

### Verification results

Po poprawkach audytowych:

- `npm run test --workspace @game-predictor/reviewer` — 253/253 PASS
  (10 nowych).
- `npm run test:geometry --workspace @game-predictor/reviewer` — 66/66 PASS
  (13 nowych w `geometry-gaps-workspace.test.mjs`, w tym 5 po audycie).
- `npm run typecheck --workspace @game-predictor/reviewer` — PASS.
- `npm run lint --workspace @game-predictor/reviewer` — 0 błędów, 1 istniejące
  ostrzeżenie (`board-search-share-data-source.ts`, poza zakresem).
- `npm run format:check` — PASS (po `prettier --write` zmienionych plików).
- `scripts/generate_code_map.py --check` — PASS po regeneracji;
  `scripts/check_current_state_window.py` i `scripts/check_decision_links.py`
  — PASS.
- Niewiadoma z `Dependencies`: `reportedBoardGeometryTarget` obsługuje pozycję
  bez zgłoszonych pól (`reportedCellIndices` puste → `reported = []`,
  metadana „Zgłoszone pola —”) i planszę `partial`
  (`gridReviewQualification` → `pending_partial` → `initialFlags.partial`,
  współrzędne ujemne dozwolone, komenda zachowuje kwalifikację — potwierdza
  test „a partial board opens the reported target as partial”). Jedyna
  korekta: `saveHint` zależny od obecności zgłoszeń; bez nowej ścieżki zapisu.

### Not completed

- Odbiór na żywych danych (Mumie 4 zdjęcia, 777 76 `incomplete_partial`,
  wyświetlenie prawdziwego pliku, konsola przeglądarki) — TASK-0965; w tym
  tasku kryteria zweryfikowano testami z fixturami.
- Commit i audyt wykonuje orkiestrator (audyt po tasku zawieszony przez
  operatora; kolumna planu „Nie”).

### Documentation updates

- `ai_docs/process/CURRENT_STATE.md` (okno kroczące: sekcja `done`
  TASK-0963, TASK-0940 przeniesiony do `ai_docs/archive/CURRENT_STATE_2026Q4.md`,
  usunięcie z „Aktywne taski”).
- `ai_docs/architecture/CODE_MAP.md`, `CODE_MAP_SYMBOLS.md` (regeneracja).
- Bez wpisu `DECISION_LOG.md` (brak zmiany domeny/architektury; decyzja D-541
  należy do TASK-0965).

### Recommended next task

- TASK-0964 (po odbiorze etapu A)

### Audit

Niezależny audyt tylko do odczytu: subagent Claude `sonnet` (`medium`), niższy
model niż wykonawca (Codex niedostępny z powodu wyczerpanego limitu;
zastępstwo zgodne z poleceniem operatora z 2026-10-10). Werdykt: PASS z
uwagami P2, brak P0/P1. Uwagi P2 rozwiązane w tym samym tasku (blok „Poprawki
po audycie” wyżej): błąd dociągania strony jako baner, ciche odświeżenie
zachowujące edytor i zdjęcie, wyłączone przyciski przy odświeżaniu celów, opis
liczników, brakujące testy ścieżek błędów i wyścigu; literówka D-540 → D-541.
Poprawki nie były ponownie audytowane (zmiany lokalne w jednym module,
testy 253/253 i 66/66).
