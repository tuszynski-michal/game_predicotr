---
title: TASK-0655 — Kadrowanie podglądu znalezionej planszy w „Wyszukaj plansze"
status: done
---

# TASK-0655 — Kadrowanie podglądu znalezionej planszy

## Status

`done`

## Goal

W karuzeli wyników „Wyszukaj plansze” pokazywać, dla plansz w trybie
`operational_review`, kadrowany fragment zdjęcia źródłowego wokół znalezionej
planszy (z paddingiem), zamiast całego zdjęcia strony ze wszystkimi
planszami.

## Context

Zgłoszenie użytkownika: dla gry 777 (`virtual_source`/geometria wirtualna,
D-428) endpoint `/assets/board` **z założenia projektowego** serwuje CAŁE
zdjęcie źródłowe, nie pojedynczą planszę — potwierdzone w
`storage/image_review_repository.py::_item_from_records` (gałąź
`asset_mode == "virtual_source"`): `board_relative_path=source.relative_path`,
z komentarzem „Structured boards deliberately have no persistent board
bitmap. The Reviewer displays a bounded source context for this mode.”. To
świadoma decyzja architektoniczna (brak trwałego bitmapa per-plansza dla
geometrii wirtualnej) — Reviewer radzi sobie z tym inaczej (nakłada siatkę
na całe zdjęcie w edytorze). Karuzela „Wyszukaj plansze” nie miała żadnego
odpowiednika i po prostu pokazywała surowe, niekadrowane zdjęcie.

Tryb `legacy_archive` **nie jest dotknięty** — archiwum przechowuje już
gotowy „obraz całej planszy” (nie strony), potwierdzone w
`API_CONTRACT.md`.

## Dependencies / entry conditions

Brak — niezależne od planu „Przybliżona wygrana” (TASK-0649–0654).

## Recommended execution

Sonnet 5, reasoning `medium` — czysta funkcja geometryczna + jeden dodatkowy
odczyt istniejącego, już wystawionego pola API; brak zmiany backendu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/API_CONTRACT.md` (§„Wyszukiwanie plansz częściowym
  układem”)

## Scope

- `apps/admin/src/features/board-search/board-search-results-state.ts`:
  nowe czyste funkcje `parseBoardCropQuad` (bezpieczne wyodrębnienie 4
  punktów `{x,y}` z `geometry.sourceQuad`/`geometry.quad`, `unknown` →
  `readonly BoardCropPoint[] | null`) i `computeBoardCropTransform` (bbox +
  padding → procentowe `width/height/left/top` obrazu w kontenerze o
  wymuszonym `aspectRatio`).
- `apps/admin/src/features/board-search/board-search-results.tsx`:
  `BoardCrop` (przemianowany kontekst) pobiera — wyłącznie dla
  `assetMode === 'operational_review'` — istniejący, już wystawiony
  endpoint `getOperationalImageReviewItem(reviewItemId, {gameId,
  importJobId})` (zero zmian backendu, pole `geometry` już tam jest),
  wyciąga quad, po załadowaniu obrazu (`naturalWidth/naturalHeight`) liczy
  transformację i renderuje kadrowany fragment. Brak quadu, błąd
  pobierania albo tryb `legacy_archive` → bezpieczny fallback: pełny obraz
  jak dotychczas (funkcja kosmetyczna, nigdy nie blokuje wyniku
  wyszukiwania).
- `apps/admin/src/app/globals.css`: nowa klasa `.boardSearchBoardAssetFrame`
  (kontener `overflow:hidden` + `aspect-ratio`) i modyfikacja
  `.boardSearchBoardAsset` (pozycjonowanie absolutne, `max-width:none`).

## Out of scope

- Zmiana backendu / nowy endpoint — istniejący `getOperationalImageReviewItem`
  już wystawia potrzebne dane.
- Tryb `legacy_archive` (nie ma problemu — już pojedyncza plansza).
- Reviewer (`apps/reviewer`) — ma własny, celowy sposób prezentacji
  (nakładka siatki na całe zdjęcie), nietknięty.
- Zmiana wartości paddingu jako konfigurowalnego przez operatora (stała
  20% w kodzie; do rewizji na podstawie realnego odbioru).

## Acceptance criteria

- [x] Dla planszy `operational_review` z poprawnym `sourceQuad`/`quad` w
      `geometry`, wyświetlany fragment jest kadrowany wokół bounding-boxa
      quadu z ~20% paddingiem po każdej stronie (proporcjonalnie), bez
      zniekształcenia proporcji obrazu.
  - [x] Fragmenty sąsiednich plansz mogą być widoczne (padding nie jest
      przycinany do samego bounding-boxa planszy).
  - [x] Brak quadu, błędny kształt geometrii albo błąd pobierania →
      pokazywany jest pełny obraz jak dotychczas, bez błędu blokującego
      wynik wyszukiwania.
  - [x] Tryb `legacy_archive` nigdy nie wykonuje dodatkowego zapytania o
      geometrię i renderuje się jak dotychczas.
  - [x] Przełączanie między wynikami (klawisze/przyciski) poprawnie
      resetuje stan kadrowania dla nowej planszy (ten sam `key` remount co
      dotychczas) i nie miesza geometrii poprzedniej planszy z nową.
  - [x] `npm run test`, `npm run test:geometry`, `npm run typecheck`,
      `npm run lint` dla `@game-predictor/admin` czyste.

## Technical notes

**Dlaczego zero zmian backendu:** `OperationalImageReviewItemResponse`
(zwracana przez już istniejący, wystawiony `GET
/admin/image-review-items/{reviewItemId}?gameId=&importJobId=`,
`operation_id=getOperationalImageReviewItem`) już zawiera pole `geometry:
dict[str, object]` — to surowe `recognized_boards.board_geometry` JSONB,
przekazywane 1:1 (`geometry=dict(board.board_geometry)` w
`storage/image_review_repository.py::_review_item_from_current_cells`).
Klient TS (`getOperationalImageReviewItem`) był już opakowany. Wystarczyło
dodać jedno wywołanie po stronie Admina.

**Matematyka kadrowania (bez znajomości wymiarów zdjęcia z backendu):**
quad jest w pikselach oryginalnego zdjęcia źródłowego — tej samej
przestrzeni współrzędnych co `naturalWidth`/`naturalHeight` załadowanego
`<img>`. Kontener ma wymuszone CSS `aspect-ratio: paddedWidth/paddedHeight`;
obraz jest pozycjonowany absolutnie z `width/height/left/top` jako procent
kontenera:

```text
scaleX% = 100 / paddedWidth
scaleY% = 100 / paddedHeight
img.width  = naturalWidth  * scaleX%
img.height = naturalHeight * scaleY%
img.left   = -paddedX * scaleX%
img.top    = -paddedY * scaleY%
```

Ponieważ `aspect-ratio` kontenera wymusza `Wc/Hc = paddedWidth/paddedHeight`,
powyższe dwie niezależne skale procentowe (pozioma/pionowa) dają
zagwarantowany brak zniekształcenia (`Wc/paddedWidth == Hc/paddedHeight`
wynika wprost z definicji `aspect-ratio`) — czysty CSS, bez canvasu i bez
przeliczeń przy każdej klatce.

**Fail-safe:** `parseBoardCropQuad`/`computeBoardCropTransform` zwracają
`null` przy jakiejkolwiek nieoczekiwanej strukturze (brak pola, zły typ,
zdegenerowany bbox o zerowej szerokości/wysokości) — komponent wtedy po
prostu renderuje pełny obraz jak przed tym taskiem. Błąd pobrania geometrii
(sieć, 404, itp.) jest łapany i traktowany tak samo — funkcja jest czysto
kosmetyczna i nigdy nie zamienia poprawnego wyniku wyszukiwania w błąd.

## Expected files

- Istniejące: `board-search-results-state.ts`, `board-search-results.tsx`,
  `globals.css`.
- Nowe: brak plików produkcyjnych; nowe testy w
  `test/board-search-results-state.test.mjs` i nowy
  `test-interactions/board-search-crop-preview.test.mjs`.

## Test cases

- `parseBoardCropQuad`: poprawny `sourceQuad`/`quad` (4× `{x,y}`) → 4
  punkty; brak pola, zła długość tablicy, punkt bez `x`/`y` liczbowego,
  `geometry` nie będące obiektem → `null`.
- `computeBoardCropTransform`: bbox + 20% padding daje oczekiwane
  `aspectRatio`/`width%/height%/left%/top%` dla przykładowego quadu i
  wymiarów obrazu; zdegenerowany quad (zerowa szerokość/wysokość) → `null`;
  ujemne/zerowe `naturalWidth`/`naturalHeight` → `null`.
- Interakcja jsdom: `operational_review` z poprawną geometrią renderuje
  kadr (kontener z `aspectRatio`, obraz z obliczonym `left/top/width/height`);
  brak geometrii/błąd pobrania → pełny obraz bez kadru i bez błędu;
  `legacy_archive` → zero wywołań `getOperationalImageReviewItem`;
  przełączenie na kolejny wynik poprawnie podmienia kadr (nowy `reviewItemId`
  w kolejnym wywołaniu, brak wycieku poprzedniej geometrii).

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
```

Timeout: 120 s na komendę.

## Risks / open questions

- Stała wartość paddingu (20% z każdej strony bounding-boxa) nie była
  konsultowana z użytkownikiem liczbowo — użytkownik zaakceptował ogólny
  kierunek („z jakimś paddingiem”, „może być widać pobliskie ramki”).
  Łatwa do dostrojenia (jedna stała w kodzie), jeśli po realnym użyciu
  okaże się za ciasna/za luźna.
- Brak testu na żywych danych gry 777 w tej sesji (bez zgody na
  uruchomienie API/Admina, zgodnie z wcześniejszą decyzją użytkownika).

## Outcome

### Changed

- [board-search-results-state.ts](../../apps/admin/src/features/board-search/board-search-results-state.ts):
  nowe `BoardCropPoint`, `parseBoardCropQuad`, `BoardCropTransform`,
  `computeBoardCropTransform` (stała `BOARD_CROP_PADDING_FACTOR = 0.2`).
- [board-search-results.tsx](../../apps/admin/src/features/board-search/board-search-results.tsx):
  `BoardCrop` pobiera `getOperationalImageReviewItem` (istniejący,
  wcześniej niewykorzystywany tu endpoint) dla `assetMode ===
  'operational_review'`, wyodrębnia quad z `geometry`, po załadowaniu
  obrazu liczy transformację CSS i renderuje kadr; fallback do pełnego
  obrazu przy braku/błędzie geometrii albo trybie `legacy_archive`.
- [board-search-workspace.tsx](../../apps/admin/src/features/board-search/board-search-workspace.tsx):
  `BoardSearchClient` Pick rozszerzony o `getOperationalImageReviewItem`.
- [globals.css](../../apps/admin/src/app/globals.css): nowe klasy
  `.boardSearchBoardAssetFrame` / `.boardSearchBoardAssetCropped`.
- Testy: 5 nowych w `test/board-search-results-state.test.mjs`
  (`parseBoardCropQuad` ×3, `computeBoardCropTransform` ×2), nowy
  `test-interactions/board-search-crop-preview.test.mjs` (5 scenariuszy).
  Zaktualizowane fałszywe klienty w `board-search-limit.test.mjs` i
  `board-search-approximate-win.test.mjs` (dodano stub
  `getOperationalImageReviewItem`, wymagany od tego taska).

### Verification results

```
npm run test --workspace @game-predictor/admin        → 589/589 (5 nowych)
npm run test:geometry --workspace @game-predictor/admin → 40/40 (5 nowych)
npm run typecheck --workspace @game-predictor/admin    → czysty
npm run lint --workspace @game-predictor/admin         → 0 błędów (po
  naprawie react-hooks/set-state-in-effect przez usunięcie zbędnego resetu
  stanu — komponent i tak remontuje się w pełni przy zmianie planszy); 4
  istniejące, niezwiązane ostrzeżenia bez zmian
```

### Not completed

- Odbiór na żywych danych gry 777 nie wykonany w tej sesji (brak zgody na
  uruchomienie API/Admina, zgodnie z wcześniejszą decyzją użytkownika w tej
  samej rozmowie). Wartość paddingu (20%) nie była konsultowana liczbowo.

### Documentation updates

- Brak — kosmetyczna zmiana prezentacji istniejącego, już udokumentowanego
  wyniku wyszukiwania; nie zmienia kontraktu API ani danych.

### Recommended next task

- Brak zaplanowanego. Ewentualne dostrojenie wartości paddingu po odbiorze
  na żywych danych.
