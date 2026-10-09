# TASK-0934 — Sekcja „Supergry” w Adminie

## Status

`done`

## Goal

W Adminie operator widzi listę serii supergry gry, otwiera serię, przegląda
planszę wyzwalającą i kolejne plansze w karuzeli, wybiera super symbol
klawiszem (`1`–`9`, `0`) lub z listy i zapisuje go z kontrolą rewizji.

## Context

Super symbol jest widoczny tylko na zdjęciach. Plan: etap S-B. Istniejące
komponenty podglądu planszy z liniami (`packages/board-search-ui`) i karuzela
wyników wyszukiwania (← / →) są bazą.

## Dependencies / entry conditions

- TASK-0933 (API serii) zacommitowany i zaudytowany.
- Fakt: `BoardSearchBoardLinesModal` i podgląd planszy przyjmują
  `sequenceNumber` i `symbols`; nawigacja ← / → istnieje w
  `board-search-results.tsx`.

## Recommended execution

claude-sonnet-5-5 / high (subagent z tej sesji; wykonanie zamiast Codex na
decyzję operatora 2026-10-08). Nowy ekran Adminu na istniejących
komponentach, zapis CAS. Eskalacja do claude-opus-5-5 / high przy
konieczności zmiany kontraktu komponentów współdzielonych. Audyt:
gpt-6.1-sol / high; do czasu CLI zamiennik claude-opus-5-5 / medium.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Nowa zakładka gry „Supergry” (tylko dla gier z rodzajem ≠ `none`): lista
  serii z filtrem statusu i weryfikacji, licznik `pending_symbol`, przycisk
  „Przelicz serie” (job).
- Widok serii: plansza wyzwalająca (z oznaczeniem komórek symbolu
  uruchamiającego), karuzela plansz `start…start+length-1` istniejącym
  podglądem (obraz, linie), brakująca plansza jako pusta karta „brak
  planszy”, retriggery oznaczone; wybór super symbolu: select + skróty
  `1`–`9`, `0` (rozszerzona mapa z TASK-0930); `Enter` zapisuje z
  `expectedRevision`; 409 → komunikat i odświeżenie bez nadpisania.
- Trzy niezależne oznaczenia serii: kompletność (`incomplete`), symbol
  (zdefiniowany / do zdefiniowania), wiarygodność przebiegu (`unverified`,
  gdy trigger lub retrigger opiera się na predykcji); `null` (wyczyść
  symbol) dostępny. Zapis symbolu nie zmienia kompletności ani
  wiarygodności.
- Testy stanu (node --test) i kontrakt renderu; wrapper klienta.

## Out of scope

- Wyszukiwanie plansz (TASK-0935), wypłaty serii (TASK-0936), Reviewer.

## Acceptance criteria

- [x] Lista serii stronicowana kursorem, filtry działają.
- [x] Karuzela pokazuje wszystkie pozycje serii, w tym brakujące.
- [x] Zapis super symbolu: sukces ustawia symbol, a oznaczenia kompletności
      i wiarygodności pozostają; konflikt rewizji nie nadpisuje i pokazuje
      aktualny stan.
- [x] Skróty klawiszowe nie działają w polach tekstowych i z modyfikatorami.
- [x] Gra `none` nie pokazuje zakładki.

## Technical notes

- Stan ekranu jako czysta maszyna stanów w `super-game-series-state.ts`
  (proponowany), testowana bez DOM, wzorem `board-search-results-state.ts`.

## Expected files

- Nowe: `apps/admin/src/features/super-games/{super-game-series-workspace.tsx,
  super-game-series-state.ts, super-game-series-keyboard.ts}`,
  `apps/admin/test/super-game-series-state.test.mjs`.
- Istniejące: nawigacja gry w Adminie, wrappery klienta, `ADMIN_APP.md`.

## Test cases

- Seria 101–120 z retriggerem 105: karuzela ma 20 kart, karta 105 oznaczona.
- Brak planszy 103: karta „brak planszy”.
- Skróty cyfrowe mapują się na listę zwykłych symboli widoczną w selekcie
  (bez Wild i symboli uruchamiających), w kolejności katalogu; `0` wybiera
  dziesiąty symbol tej listy, a przy dziewięciu zwykłych symbolach (gra
  `mumie`) nie robi nic. Symbol uruchamiający (np. Mumia) nie jest ani opcją
  selektu, ani celem skrótu; gdyby mimo to został kandydatem (stan wymuszony
  poza UI), zapis jest blokowany w Adminie przed wysłaniem żądania i odrzucany
  przez API (decyzja leada 2026-10-09 po audycie Codex; zastępuje wcześniejszy
  zapis „`0` wybiera Mumię jako kandydata”).
- 409 → stan nie zmieniony, komunikat.

## Verification

```powershell
# katalog worktree, timeout 120 s każda
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
```

## Risks / open questions

- Czy super symbolem może być Wild albo symbol uruchamiający? Plan: nie
  (tylko zwykłe symbole); walidacja po stronie API w TASK-0933.

## Outcome

Wykonawca: claude-sonnet-5-5 (subagent sesji prowadzącej). Commit, audyt
krzyżowy, `CURRENT_STATE.md` i ewentualny wpis `DECISION_LOG.md` wykonuje
sesja prowadząca. Task nie zmienia API ani klienta; używa wrapperów z
TASK-0933.

### Changed

- **Nawigacja.** `admin-navigation-state.ts`: sekcja `super-games` w
  `GAME_SECTIONS`, pole `seriesId: string | null` stanu nawigacji
  (parametr `series`, odczytywany i zapisywany w adresie tylko w sekcji
  `super-games` wybranej gry), `isGameSectionAvailable` (sekcja tylko dla gier
  z `superGameKind !== 'none'`) i `normalizeAdminNavigation` (odrzuca serię
  poza sekcją). `catalog-workspace.tsx`: wpis „Supergry” w
  `GAME_SECTION_OPTIONS`, ukrywanie sekcji dla gry `none`, czyszczenie
  `section=super-games` po załadowaniu gry bez supergry, zerowanie
  `seriesId` przy zmianie gry i sekcji, montowanie
  `SuperGameSeriesWorkspace` tylko w rozwiniętej sekcji. Link z wyszukiwania
  plansz (TASK-0935): `?workspace=games&game=<gameId>&section=super-games&series=<seriesId>`
  otwiera serię przy ładowaniu.
- **Stan** `features/super-games/super-game-series-state.ts` (czysty, bez
  DOM): filtry i zapytanie listy, stronicowanie kursorem (odrzuca spóźnione i
  powtórzone strony), licznik serii bez symbolu, baner i polling stanu
  generacji, karuzela pozycji (`trigger … start+length-1`, luki i pozycje poza
  zakresem jako puste karty), wybór kandydata, blokada zapisu
  Wild/uruchamiającego/zarchiwizowanego, zapis z `expectedRevision`, obsługa
  sukcesu, konfliktu 409 i odmowy API, trzy niezależne oznaczenia, komunikaty
  błędów, wybór wersji reguł do odczytu symboli planszy.
- **Skróty** `super-game-series-keyboard.ts`: `1`–`9`, `0` (dziesiąty),
  `Enter` zapis, `Esc` anulowanie, ← / →; nieaktywne w polach tekstowych i
  selectach, z Ctrl/Alt/Meta/Shift; `Enter` na sfokusowanym przycisku/linku
  wykonuje ten przycisk. Używa `extendedDigitShortcutIndex`,
  `extendedDigitShortcutLabel` i `isTextEntryKeyboardTarget` z
  `lib/keyboard-shortcuts.ts`.
- **Widok** `super-game-series-workspace.tsx` + `.module.css`: lista serii
  (filtry, licznik, „Przelicz serie”, „Wczytaj kolejne”), widok serii z
  karuzelą (kadr planszy, układ symboli 3×5 z wyróżnionymi komórkami symbolu
  uruchamiającego, nakładka na kadrze przy dostępnych wielokątach, pasek
  pozycji, przycisk „Pokaż planszę z liniami” otwierający
  `BoardSearchBoardLinesModal` z `board-search-ui`), panel „Super symbol”
  (select tylko ze zwykłymi symbolami z numerami skrótów, „Zapisz”, „Anuluj”,
  „Wyczyść symbol”), baner „Serie w trakcie przeliczania”, toast po
  „Przelicz serie”.
- **Testy:** `test/super-game-series-state.test.mjs`,
  `test/super-game-series-keyboard.test.mjs`,
  `test/super-game-series-workspace-contract.test.mjs`, rozszerzony
  `test/admin-navigation-state.test.mjs` (istniejące oczekiwania dostały
  `seriesId: null`), nowy test jsdom
  `test-interactions/super-game-series-workspace.test.mjs` (uruchamiany przez
  `npm run test:geometry`; nie wchodzi do `npm run test`).
- **Dokumentacja:** `ai_docs/requirements/ADMIN_APP.md`, podsekcja „Sekcja
  „Supergry” (TASK-0934, D-535, D-536)”.

### Verification results

Katalog worktree, polecenia z timeoutem poniżej 300 s.

- `npm run test --workspace @game-predictor/admin`: 724 tests, 724 pass,
  0 fail (w tym 45 nowych: 23 testy stanu, 6 skrótów, 10 kontraktu renderu i
  6 przypadków nawigacji).
- `npm run typecheck --workspace @game-predictor/admin`: kod wyjścia 0.
- `npm run lint --workspace @game-predictor/admin`: 0 errors, 5 warnings
  (wszystkie sprzed taska, w plikach `board-search-share-corrections.tsx`,
  `image-folder-import-panel.tsx`, `page-geometry-correction-panel.tsx`); żaden
  nie dotyczy plików taska.
- `npx tsx --tsconfig tsconfig.json --test test-interactions/super-game-series-workspace.test.mjs`
  (w `apps/admin`): 6 pass, 0 fail (lista i „Przelicz serie”, karuzela ←/→
  z luką 103 i retriggerem 105, cyfry/Enter/Esc z zapisem, brak skrótów w
  select i z modyfikatorami, konflikt 409 z odświeżeniem, odmowa API).
- `npx prettier --check` na wszystkich zmienionych i nowych plikach taska
  oraz `ADMIN_APP.md`: All matched files use Prettier code style.
- Nie uruchamiano serwerów ani `openapi:generate`; test w przeglądarce na
  żywym API nie był wykonywany.

### Not completed

- Brak ręcznego sprawdzenia w przeglądarce z prawdziwym API i danymi gry
  `mumie` (agent nie uruchamia API/Admina). Układ CSS nie był oglądany.
- Test `test:geometry` całego pakietu nie był uruchamiany (tylko nowy plik).
- Nakładka wielokątów na kadrze działa tylko, gdy `getBoardSearchBoardDetail`
  zwraca `view.cellPolygons`; przy nieaktualnym odczycie planszy pozostaje
  siatka symboli 3×5.

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md`: nowa podsekcja sekcji „Supergry”.
- Do uzupełnienia przez sesję prowadzącą: `CURRENT_STATE.md`, przeniesienie
  taska do `completed/` po audycie i zmianie statusu.

### Recommended next task

TASK-0935 (złote oznaczenie serii w wyszukiwaniu plansz, link do sekcji
„Supergry”), a po audycie TASK-0936.

Instrukcja operatora: uruchom `npm run api:dev` i `npm run admin:dev` we
własnych terminalach, otwórz grę z supergrą (np. `mumie`), rozwiń „Supergry”,
użyj „Przelicz serie” i poczekaj, aż baner „Serie w trakcie przeliczania”
zniknie. Otwórz serię przyciskiem „Otwórz”, przejdź ← / → po pozycjach,
wybierz symbol klawiszem `1`–`9`/`0` albo z listy i zatwierdź `Enter`. Po
zapisie kompletność i wiarygodność przebiegu nie powinny się zmienić. Dwa
okna przeglądarki z tą samą serią pozwalają sprawdzić konflikt 409: zapis w
drugim oknie po zapisie w pierwszym pokazuje komunikat i aktualny symbol bez
nadpisania.

### Audyt i runda poprawek

Audyt krzyżowy: gpt-6.1-sol / high, werdykt `REVISE`, raport
`ai_docs/quality/TASK-0934_AUDIT_gpt-6.1-sol.md` (3 × P0, 1 × P1, 2 × P2).
Jedna runda poprawek wykonana przez claude-sonnet-5-5.

| Znalezisko | Poprawka |
|---|---|
| P0-1 odpowiedź zapisu stosowana do dowolnego widoku | Każdy zapis ma operację (`saveOperation`, id i `seriesId`) ustawianą na starcie żądania; opuszczenie lub otwarcie serii (`openSeries`, `closeSeries`) unieważnia operację. Konflikt 409, odmowa i błąd sieci starej operacji są ignorowane, a stosowanie do widoku wymaga też `state.series.id === savedSeriesId`. Sukces starej operacji tylko odświeża listę. Testy jsdom: opóźniony zapis serii A po otwarciu B (sukces, konflikt, błąd sieci). |
| P0-2 wiersz listy niezgodny z filtrem po zmianie symbolu | `replaceSeriesInList` usuwa wiersz, który nie spełnia aktywnych filtrów (`seriesMatchesFilters`), a sukces zapisu czyta listę od nowa z filtrami (`reloadList`, to odświeża też licznik). Testy stanu i jsdom: ustawienie symbolu pod „Do zdefiniowania” i wyczyszczenie pod „Z super symbolem”. |
| P0-3 spóźnione strony i błędy listy | Stan listy ma `generation` zmieniane przy zmianie filtrów i przy odświeżeniu; `applySeriesListPage` i `failSeriesList` odrzucają strony i błędy z wcześniejszej generacji, a komponent nie stosuje wtedy `superGameState` ani nie dokleja strony. Testy stanu (odrzucenie strony z tym samym kursorem, pierwszej strony i błędu) oraz jsdom („Wczytaj kolejne” przed odświeżeniem, sukces i błąd). |
| P1-1 sprzeczność taska i wymagań w sprawie `0` | Rozstrzygnięcie leada: skróty mapują się na listę zwykłych symboli z selektu; zaktualizowano przypadek testowy taska (sekcja Test cases), `ADMIN_APP.md` i test jsdom bez zmian. |
| P2-1 pominięty błąd pobrania symboli | Jawny komunikat z przyciskiem „Spróbuj ponownie”; „Odśwież listę” ponawia także pobranie symboli. Test jsdom. |
| P2-2 zdjęcie niezwiązane z rewizją widoku | Obraz karty jest budowany z sumy kontrolnej i `view.revision` odczytu planszy (jak w oknie linii), więc zdjęcie i wielokąty oznaczeń pochodzą z tej samej rewizji; do czasu odczytu karta pokazuje „Odczytuję planszę…”. Odczyty planszy obejmują też sąsiednie karty (wstępne ładowanie obrazów z rewizją). Test jsdom. |

Wyniki po poprawkach (katalog worktree, `apps/admin` dla tsx):

- `npm run test --workspace @game-predictor/admin`: 732 tests, 732 pass, 0 fail.
- `npm run typecheck --workspace @game-predictor/admin`: kod wyjścia 0.
- `npm run lint --workspace @game-predictor/admin`: 0 errors, 5 warnings (te
  same co wcześniej, poza plikami taska).
- `npx tsx --tsconfig tsconfig.json --test test-interactions/super-game-series-workspace.test.mjs`:
  15 pass, 0 fail.
- `npx prettier --check` na plikach taska: czysto.

#### Runda 2

Codex (runda 2) zamknął P0-2, P0-3, P1-1 i P2-1; pozostały dwa punkty,
poprawione w drugiej, końcowej rundzie.

| Znalezisko | Poprawka |
|---|---|
| P0-1 (reszta) unieważnienie zapisu przy zmianie serii przez historię przeglądarki | Ważność operacji zapisu wynika z cyklu otwarcia serii: efekt na `[seriesId]` zeruje `saveOperation` i zapisuje bieżący `seriesId` w `openSeriesId`, a `isCurrent` wymaga zarówno tej samej operacji, jak i `openSeriesId === savedSeriesId`. Wszystkie skutki odpowiedzi (stosowanie do widoku, odświeżenie serii po konflikcie, komunikaty) są za tą bramką; jedynie odświeżenie listy po sukcesie jest bezwarunkowe. Test jsdom: zapis A rozpoczęty, zmiana propsa `seriesId` na B (jak `popstate`), wybór kandydata w B, a potem opóźniony konflikt, odmowa albo sukces A. B zachowuje kandydata, nie jest ponownie czytane i nie pokazuje komunikatu. Sprawdzono, że test pada bez poprawki. |
| P2-3 brak ponowienia po nieudanym „Wczytaj kolejne” | `startLoadingMoreSeries` przyjmuje stan `error`, gdy jest `nextCursor` (ten sam kursor); `loadMore` odrzuca tylko stan `loading`. Przycisk ma po błędzie etykietę „Ponów wczytanie”. Błąd pierwszej strony (bez kursora) nadal wymaga „Odśwież listę”. Testy stanu i jsdom. |

Wyniki po rundzie 2:

- `npm run test --workspace @game-predictor/admin`: 733 tests, 733 pass, 0 fail.
- `npm run typecheck --workspace @game-predictor/admin`: kod wyjścia 0.
- `npm run lint --workspace @game-predictor/admin`: 0 errors, 5 warnings
  (sprzed taska, poza plikami taska).
- `npx tsx --tsconfig tsconfig.json --test test-interactions/super-game-series-workspace.test.mjs`
  (w `apps/admin`): 19 pass, 0 fail.
- `npx prettier --check` na plikach taska: czysto.
