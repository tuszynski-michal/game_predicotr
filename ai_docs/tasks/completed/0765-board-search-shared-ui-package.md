---
title: TASK-0765 — Wspólny pakiet UI wyszukiwarki plansz
status: done
last_updated: 2026-09-30
---

# TASK-0765 — Wspólny pakiet UI wyszukiwarki plansz

## Status

`done`

## Goal

Komponenty i stan wyszukiwarki żyją w `packages/board-search-ui`, Admin działa identycznie, a karuzela używa przyciętego widoku z TASK-0763.

## Context

Punkt 5 zgłoszenia operatora z 2026-09-30, decyzja D-471. Pełna specyfikacja: plan §3 R4, §4.3–4.5 i §5 T6. Etap B zlecony przez operatora 2026-09-30 po zakończeniu etapu A i poprawek TASK-0773.

## Dependencies / entry conditions

- TASK-0764, TASK-0772, TASK-0773 done.
- Etap B zlecony przez operatora.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz taska w tabeli planu). Audyt: niezależny agent `claude-opus-5-5`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope (doprecyzowany po etapie A)

- Nowy pakiet `@game-predictor/board-search-ui` (źródła `.ts/.tsx` eksportowane
  bez budowania, jak `manual-image-selection-core`; `board-search.css`).
- Przeniesienie (`git mv`) wszystkich modułów `apps/admin/src/features/board-search/`
  oraz testów jednostkowych i interakcyjnych `board-search-*`.
- `BoardSearchDataSource`: podzbiór wygenerowanego `AdminApiClient` (ten sam
  kształt `{ data, error }`). Wymagane: `listSymbols`, `symbolImageAssetUrl`,
  `searchGameBoards`, `getBoardSearchApproximateWin`,
  `getBoardSearchBoardDetail`, `boardSearchBoardViewUrl`. Opcjonalne (tylko
  Admin): `applySymbolCellReviewDecision`, `refreshBoardSearchBoardDocument`,
  `archivedBoardSearchAssetUrl`, `operationalImageReviewBoardAssetUrl`,
  `getOperationalImageReviewItem`. Bez mutacji okno planszy jest tylko do
  odczytu; bez zasobów pełnego zdjęcia karuzela nie ma awaryjnego kadru.
- `apiErrorMessage` i pomocniki skrótów klawiszowych skopiowane do pakietu
  (Admin zachowuje własne kopie dla innych sekcji).
- Karuzela: najpierw widok `boardSearchBoardViewUrl` (przycięty po stronie
  serwera, powiązany z sumą planszy); dopiero błąd widoku (np. nieaktualny
  odczyt, 409) przełącza na dotychczasowe pełne zdjęcie z kadrowaniem CSS
  (`computeBoardCropTransform` zostaje jako ścieżka awaryjna). Sąsiednie
  wyniki są wstępnie ładowane przez widok.
- Admin: cienkie opakowanie `apps/admin/src/features/board-search/board-search-workspace.tsx`
  tworzy klienta Admin API i przekazuje go do pakietu; `layout.tsx` importuje
  `board-search.css`; reguły `.boardSearch*` usunięte z `globals.css`.

## Out of scope

Według planu §8. Panel udostępniania (TASK-0769) i aplikacja online (TASK-0768).

## Acceptance criteria

- [x] Testy `board-search-*` przeniesione i zielone bez zmiany asercji (poza
  testami karuzeli, które najpierw symulują błąd widoku).
- [x] Typecheck, lint i testy Admina oraz pakietu bez nowych błędów.
- [x] Brak różnic funkcjonalnych poza źródłem obrazu karuzeli.
- [x] Brak otwartych uwag P0–P2 audytu.

## Technical notes

- W repozytorium są dwie kopie React: `apps/admin` i `apps/reviewer` mają
  zagnieżdżone `react@19.2.3`, a w korzeniu jest `react@19.2.8` (zależności
  mobile i `@tanstack/react-virtual`). Next aliasuje React do własnej kopii,
  więc w aplikacji to nie przeszkadza. Testy interakcyjne pakietu działają w
  pakiecie (`test:interactions`), gdzie React i React DOM pochodzą z jednej
  kopii; renderowanie komponentów pakietu z testów Admina dałoby „Invalid hook
  call”. Kontrakt adaptera Admina sprawdza typecheck (`AdminApiClient`
  przekazywany jako `BoardSearchDataSource`). Pakiet deklaruje w
  `devDependencies` `react`/`react-dom` w wersji kopii z korzenia (19.2.8),
  aby testy nie zależały od tego, co przypadkiem podciągają inne pakiety.

## Expected files

- `packages/board-search-ui/` (`package.json`, `tsconfig.json`,
  `eslint.config.mjs`, `src/`, `test/`, `test-interactions/`).
- `apps/admin/src/features/board-search/board-search-workspace.tsx`
  (opakowanie), `apps/admin/src/app/layout.tsx`, `apps/admin/src/app/globals.css`,
  `apps/admin/package.json`, `package-lock.json`.

## Test cases

- Testy jednostkowe pakietu (stan edytora, wyników, stawki, linii, poprawki
  pola, skróty).
- Interakcje: widok najpierw, bez pobierania geometrii; błąd widoku →
  pełne zdjęcie z kadrem; brak zasobów awaryjnych → komunikat; źródło danych
  bez mutacji → okno planszy tylko do odczytu, także dla nieaktualnego odczytu.

## Verification

```powershell
npm run test --workspace @game-predictor/board-search-ui
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run typecheck --workspace @game-predictor/board-search-ui
npm run lint --workspace @game-predictor/board-search-ui
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run test --workspace @game-predictor/admin
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

Według planu §7.

## Outcome

### Changed

- Nowy pakiet `@game-predictor/board-search-ui` z przeniesionymi komponentami,
  stanem, testami jednostkowymi i interakcyjnymi oraz `board-search.css`
  (blok `.boardSearch*` z `globals.css` bajt w bajt, plus nagłówek).
- `BoardSearchDataSource` (podzbiór `AdminApiClient`, mutacje i zasoby pełnego
  zdjęcia opcjonalne); okno planszy tylko do odczytu bez mutacji.
- Karuzela: najpierw przycięty widok serwera, pełne zdjęcie z kadrem CSS
  tylko po błędzie widoku; geometria pobierana dopiero wtedy.
- Admin: opakowanie `board-search-workspace.tsx`, import CSS w `layout.tsx`,
  zależność workspace.

### Verification results

- Pakiet: testy 72/72, interakcje 33/33 (w tym nowe: widok najpierw bez
  geometrii, brak zasobów awaryjnych, okno tylko do odczytu), typecheck i lint
  czyste.
- Admin: typecheck czysty, lint bez nowych uwag (4 wcześniejsze ostrzeżenia
  w `features/imports`), testy 582/582, `next build` OK. `test:geometry`
  Admina: 23/29 — 6 awarii `symbol-review-partial` („Invalid hook call”,
  dwie kopie React przez `@tanstack/react-virtual`) istniało przed zadaniem.
- Ręcznie na `127.0.0.1:3010`: sekcja renderuje się z pakietu ze stylami,
  karuzela pobiera `/board-search/boards/{n}/view`.
- Audyt niezależnego agenta `claude-opus-5-5`: PASS w pierwszym cyklu, bez
  P0–P2. P3 „deklaracja React dla testów pakietu” poprawione.

### Not completed / known limitations

- P3 z audytu: po odświeżeniu nieaktualnego odczytu w oknie planszy
  karuzela pokazuje pełne zdjęcie awaryjne do przejścia na inną planszę
  (klucz karuzeli się nie zmienia). Świadomie pozostawione.
- Po scaleniu gałęzi główny checkout i inne worktree potrzebują
  `npm install`, aby powstało dowiązanie nowego pakietu.
