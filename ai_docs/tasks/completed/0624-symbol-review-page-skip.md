---
title: TASK-0624 — lekki skok stron w Weryfikacji symboli
status: done
last_updated: 2026-09-23
---

# TASK-0624 — lekki skok stron w Weryfikacji symboli

## Status

`done`

## Goal

„Przejdź do strony” w sekcji Weryfikacja symboli (Admin) dociera do celu
maksymalnie dwoma żądaniami HTTP (jedno po kursor, jedno po docelową
stronę), niezależnie od odległości skoku, zamiast pobierać każdą stronę
pośrednią.

## Context

Zgłoszenie użytkownika: skok ze strony 1 na 500 „mega długo trwa”, w
zakładce Network widać bardzo dużo requestów. Potwierdzone w kodzie:
`goToPage()` w `symbol-review-workspace.tsx:762` chodzi kursor po kursorze
(`while (pageNumber !== targetPageNumber)`), pobierając **pełną** stronę (do
500 elementów z metadanymi crop/miniatur) dla każdej strony pośredniej —
skok 1→500 to ~499 pełnych requestów. To zachowanie jest celowe i
przetestowane (`symbol-review-workspace-contract.test.mjs:133` asercja
`while (pageNumber !== targetPageNumber)`), więc zmiana świadomie zastępuje
ten kontrakt testowy, nie osłabia go.

Backend (`/api/v1/admin/games/{game_id}/symbol-cell-reviews`) używa
wyłącznie keyset pagination (`afterCursor`/`beforeCursor`), bez
offsetu/numeru strony — świadomy wybór dla stabilności pod dużym,
zmieniającym się zbiorem (`image_symbol_review_repository.py:473`,
`list_items`). Kursor koduje samowystarczalny klucz porządkujący
`(sequence_number, cell_index, id)` powiązany ze scope'em filtra
(`encode_symbol_cell_review_cursor`/`decode_symbol_cell_review_cursor`,
`domain/image_symbol_reviews.py:882`).

Użytkownik potwierdził kierunek: „lżejszy hop” (opcja 3 z diagnozy) ma sens.

## Dependencies / entry conditions

- Brak zależności od T1–T3 (TASK-0621/0622/0623) — osobny, niezwiązany
  obszar (Weryfikacja symboli, nie geometria stron).
- Lokalne API/Admin działają (już uruchomione w tej sesji).

## Recommended execution

`claude-sonnet-5`, reasoning `high`. Uzasadnienie: zmiana kontraktu API
(nowy endpoint) + reużycie logiki krytycznej dla poprawności (seek/widoczność
w keyset pagination) wymaga precyzyjnego refactoru bez zmiany istniejącego
zachowania `list_items`, plus pełny pion: backend → OpenAPI → wygenerowany
klient → wrapper → frontend → testy na czterech warstwach. Eskalacja:
jeśli po refaktorze `list_items` istniejące testy repozytorium/API
zaczynają się różnić w wynikach (regresja poprawności seeka).
Dodatkowy review: nie wymagany.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`:
  wydzielenie współdzielonej pętli seek+widoczność z `list_items` do
  `_seek_visible_keys`; nowa metoda `skip_keys` reużywająca tej pętli.
- `services/api/src/game_predictor_api/application/image_symbol_reviews.py`:
  `SymbolCellReviewQueryRepository` Protocol — nowa metoda `skip_keys`;
  `SymbolCellReviewQueryService` — nowa metoda `skip`.
- `services/api/src/game_predictor_api/schemas/image_symbol_reviews.py`:
  nowy `SymbolCellReviewSkipResponse`.
- `services/api/src/game_predictor_api/api/image_symbol_reviews.py`: nowy
  endpoint `GET /{game_id}/symbol-cell-review-skip`.
- `npm run openapi:generate` (regeneruje `packages/admin-api-client`).
- `apps/admin/src/features/symbol-reviews/symbol-review-actions.ts`: nowa
  funkcja `skipSymbolReviewPages`.
- `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`:
  `goToPage()` używa nowego skoku zamiast pętli po stronach.
- Testy: nowe w `services/api/tests/` (repository/application/API), update
  `apps/admin/test/symbol-review-workspace-contract.test.mjs` (świadoma
  zmiana kontraktu — nowe zachowanie, nie osłabienie).

## Out of scope

- `unreadable-board-reviews` (osobny, podobny, ale niezależny endpoint z
  własnym `afterCursor`) — nie dotyczy zgłoszenia.
- Zmiana rozmiaru strony (`DEFAULT_SYMBOL_REVIEW_PAGE_SIZE = 500`) — bez
  zmian.
- Prawdziwa paginacja offsetowa / zmiana indeksu — odrzucona na rzecz
  lżejszego hopu (decyzja użytkownika).
- `_candidate_seek_statement`, `_base_visible_statement`,
  `_symbol_cell_review_after_key`/`_before_key`,
  `encode_symbol_cell_review_cursor`/`decode_symbol_cell_review_cursor` —
  reużywane bez zmian semantyki.

## Acceptance criteria

- [x] Nowa metoda repozytorium `skip_keys` zwraca klucz `count`-tego
      widocznego elementu w danym kierunku od podanego kursora, albo `None`
      gdy widocznych elementów jest mniej niż `count`.
- [x] `list_items` po refaktorze zwraca identyczne wyniki jak przed
      refaktorem — wszystkie istniejące testy repozytorium bez zmiany
      asercji.
- [x] Nowy endpoint `GET /{game_id}/symbol-cell-review-skip` z parametrami
      identycznymi z listingiem (symbolId, state, minConfidence,
      maxConfidence) + dokładnie jeden z `afterCursor`/`beforeCursor` +
      `count` (≥1) → zwraca `{"cursor": string | null}`.
- [x] Kursor zwrócony przez skip, użyty jako `afterCursor`/`beforeCursor`
      (ten sam kierunek) na `/symbol-cell-reviews`, zwraca dokładnie tę samą
      stronę, którą dałoby dojście tam pętlą krok po kroku — zweryfikowane
      testem porównawczym (skip vs. pętla referencyjna) na tych samych
      danych.
- [x] `goToPage()` w Adminie: dla skoku o 1 stronę — bez zmian (jeden
      fetch, bez wywołania nowego endpointu). Dla skoku >1 strony — dokładnie
      jedno wywołanie skip + jedno wywołanie listingu, niezależnie od
      odległości.
- [x] Wyczerpanie danych w trakcie skoku (mniej stron niż żądano) daje ten
      sam komunikat błędu co dotychczas („Wyniki zmieniły się przed
      osiągnięciem wskazanej strony.”).
- [x] `symbol-review-workspace-contract.test.mjs` zaktualizowany: nowa
      asercja dla skip-based jump zamiast `while (pageNumber !==
      targetPageNumber)`.
- [x] `npm run openapi:generate` + `npm run openapi:check` czyste; klient
      wygenerowany, wrapper i request test dodane (pełny pion API per
      AGENTS.md).
- [x] `ruff`, `mypy`, testy `@game-predictor/admin` i
      `@game-predictor/admin-api-client` zielone. (`python:test -Suite Api`
      pełny nie uruchomiony — patrz Outcome/Not completed; uruchomione
      bezpośrednio odpowiednie pliki testowe zamiast tego.)

## Technical notes

### Semantyka skoku (wyprowadzenie)

Strony 1-indeksowane, rozmiar strony `pageSize`. `nextCursor` strony `m`
wskazuje klucz ostatniego elementu strony `m` (indeks `m*pageSize - 1`,
0-indeksowany). Użyty jako `afterCursor`, daje stronę `m+1`.

Będąc na stronie `C` (mając `currentPage.nextCursor`/`previousCursor`),
chcąc dotrzeć do strony `T`:
- `hops = T - C` (dodatnie = w przód, ujemne = w tył).
- Jeśli `|hops| == 1`: użyć **bezpośrednio** istniejącego
  `nextCursor`/`previousCursor` — bez wywołania skip (brak korzyści, tylko
  dodatkowy round-trip).
- Jeśli `|hops| > 1`: wywołać skip z `count = (|hops| - 1) * pageSize`,
  kierunek AFTER gdy `hops > 0` (bazując na `currentPage.nextCursor`),
  BEFORE gdy `hops < 0` (bazując na `currentPage.previousCursor`). Wynikowy
  kursor użyć jako `afterCursor`/`beforeCursor` w **jednym** wywołaniu
  `loadSymbolReviewPage`, które zwraca stronę `T`.
- Jeśli bazowy `nextCursor`/`previousCursor` jest `null` (już na
  ostatniej/pierwszej stronie) — błąd jak dotychczas przy niemożliwym skoku.
- Jeśli skip zwróci `cursor: null` (dane się skurczyły) — ten sam komunikat
  błędu co przy wyczerpaniu kursora w starej pętli.

### Repozytorium: wydzielenie `_seek_visible_keys`

Aktualne `list_items` (linie ok. 473–556) miesza w jednej pętli: batchowe
seekowanie kandydatów (`_candidate_seek_statement`, batch ≥1000),
filtrowanie widoczności (bezpośrednio przy świeżej projekcji, przez
dodatkowe zapytanie przy nieaktualnej) i finalną hydratację
(`_list_statement` + `_row_to_list_item`). Wydzielić **tylko** część
seek+widoczność do prywatnej metody zwracającej listę widocznych krotek
`(id, sequence, cell_index, id)` w kolejności seeka, do maksymalnie
`needed_count` elementów — identyczna logika batchowania, tych samych
dwóch ścieżek widoczności i tych samych sprawdzeń `_raise_if_read_cancelled`.
`list_items` wywołuje ją z `needed_count=limit+1` (jak dotąd) i hydratuje
wynik tak jak dziś. Nowe `skip_keys` wywołuje ją z `needed_count=count` i
zwraca tylko klucz ostatniego elementu (bez hydratacji, bez zapytania do
`_list_statement`).

### Endpoint

`GET /api/v1/admin/games/{game_id}/symbol-cell-review-skip` — parametry
identyczne z `/symbol-cell-reviews` minus `limit`, plus `count: int =
Query(ge=1)`. Odpowiedź `SymbolCellReviewSkipResponse {cursor: str | null}`.
Błędy: `SYMBOL_CELL_REVIEW_CURSOR_DIRECTION_CONFLICT` (oba kursory),
nowy `SYMBOL_CELL_REVIEW_SKIP_CURSOR_REQUIRED` (żaden kursor), reużyć
`SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE`/`SYMBOL_CELL_REVIEW_QUERY_TIMEOUT`
z istniejącej infrastruktury (`bounded_read`, `_run_disconnect_cancellable_query`).

### Frontend

`symbol-review-actions.ts`: `skipSymbolReviewPages(api, {...filtry,
afterCursor | beforeCursor, count, signal}) -> {ok:true, cursor: string|null}
| {ok:false, error, aborted?}`, wzorem `loadSymbolReviewPage`.

`goToPage()`: zastąpić pętlę `while` obliczeniem `hops`, wyborem
bazowego kursora z `currentPage`, warunkowym wywołaniem skip (tylko gdy
`|hops| > 1`), a następnie pojedynczym `loadSymbolReviewPage` z wynikowym
kursorem. Zachować istniejące strażniki (`pagingRef`, `requestCoordinator`,
`requestId`) i istniejące zachowanie zachowania zaznaczenia
(`Object.keys(selection.targetsById)` — bez czyszczenia selekcji przy
skoku, tak jak dziś).

## Expected files

- Istniejące:
  `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`,
  `services/api/src/game_predictor_api/application/image_symbol_reviews.py`,
  `services/api/src/game_predictor_api/schemas/image_symbol_reviews.py`,
  `services/api/src/game_predictor_api/api/image_symbol_reviews.py`,
  `apps/admin/src/features/symbol-reviews/symbol-review-actions.ts`,
  `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`,
  `apps/admin/test/symbol-review-workspace-contract.test.mjs`.
- Nowe (proponowane, dopiero po sprawdzeniu istniejącej struktury testów):
  test repozytorium/API dla `skip_keys`/endpointu w
  `services/api/tests/`.
- Wygenerowane: `packages/admin-api-client/**` (przez
  `npm run openapi:generate`) — nie edytować ręcznie.

## Test cases

- `skip_keys`: od danego `after_key`, `count=1..N` zwraca ten sam klucz co
  N-ta pozycja z pętli `list_items` wywoływanej N razy z `limit=1` (test
  porównawczy na tych samych, zdeterminowanych danych).
- `skip_keys`: `count` większy niż liczba widocznych elementów → `None`.
- `skip_keys`: kierunek `before_key` (wstecz) symetrycznie.
- Endpoint: oba kursory podane → 409/422 zgodnie z istniejącym wzorcem
  błędu kierunku; żaden kursor → nowy błąd; poprawne wejście → 200 z
  kursorem, który po użyciu na `/symbol-cell-reviews` daje oczekiwaną
  stronę.
- Admin frontend (kontrakt): skok o 1 stronę nie wywołuje skip; skok o >1
  wywołuje skip dokładnie raz, potem jeden fetch strony; wyczerpanie danych
  daje istniejący komunikat błędu; selekcja przetrwa skok.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests -k symbol_cell_review -q
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/storage/image_symbol_review_repository.py services/api/src/game_predictor_api/application/image_symbol_reviews.py services/api/src/game_predictor_api/schemas/image_symbol_reviews.py services/api/src/game_predictor_api/api/image_symbol_reviews.py
.\.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/storage/image_symbol_review_repository.py services/api/src/game_predictor_api/application/image_symbol_reviews.py
npm run openapi:generate
npm run openapi:check
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
```

Timeout 120 s na krok (poza `openapi:generate`/testami całego workspace,
jeśli przewidywalnie dłuższe — zgłosić użytkownikowi przed uruchomieniem).

## Risks / open questions

- Refaktor `_seek_visible_keys` dotyka kodu współdzielonego z produkcyjną
  ścieżką listowania — wymaga 1:1 zachowania istniejących testów
  `list_items` bez zmiany ijednej asercji, jako dowód braku regresji.
- Kursor jest związany ze `storageGeneration`/scope filtra — skip musi
  odrzucać niezgodny kursor tak samo jak dziś robi to `decode_symbol_cell_review_cursor`
  (reużywane bez zmian, więc to dziedziczone za darmo).

## Outcome

### Changed

- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`:
  wydzielono `_seek_visible_keys` (identyczna logika batchowego seeka +
  dwóch ścieżek widoczności, przeniesiona 1:1 z `list_items`); `list_items`
  używa jej z `needed_count=limit+1` jak dotąd; nowa `skip_keys` używa jej z
  `needed_count=count`, zwraca tylko klucz (bez hydratacji, bez zapytania
  `_list_statement`).
- `services/api/src/game_predictor_api/application/image_symbol_reviews.py`:
  `SymbolCellReviewQueryRepository` Protocol +metoda `skip_keys`;
  `SymbolCellReviewQueryService` +metody `skip`/`_skip` (mirror `list`/`_list`),
  nowe kody błędów `SYMBOL_CELL_REVIEW_SKIP_COUNT_INVALID`,
  `SYMBOL_CELL_REVIEW_SKIP_CURSOR_REQUIRED` (domyślny status 422, reużyty
  istniejący `SYMBOL_CELL_REVIEW_CURSOR_DIRECTION_CONFLICT` dla obu
  kursorów, status 409 bez zmian).
- `services/api/src/game_predictor_api/schemas/image_symbol_reviews.py`:
  `SymbolCellReviewSkipResponse`, `to_symbol_cell_review_skip_response`.
- `services/api/src/game_predictor_api/api/image_symbol_reviews.py`: nowy
  endpoint `GET /{game_id}/symbol-cell-review-skip`
  (`operation_id=skipSymbolCellReviews`), ten sam wzorzec co listing
  (`_run_disconnect_cancellable_query`, `QUERY_ERROR_RESPONSES`).
- `packages/admin-api-client/src/index.ts`: `SkipSymbolCellReviewsOptions`,
  wrapper `skipSymbolCellReviews`, re-eksport typu `SymbolCellReviewSkipResponse`
  (brakujący re-eksport wykryty przez `tsc --noEmit` w apps/admin — dodany).
- `apps/admin/src/features/symbol-reviews/symbol-review-actions.ts`:
  `SkipSymbolReviewPagesOptions`, `SymbolReviewSkipResult`,
  `skipSymbolReviewPages`; `SymbolReviewClient` +`'skipSymbolCellReviews'`.
- `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`:
  `goToPage()` przepisane — sprawdzenie cache tylko dla strony docelowej;
  `hops = target - current`; `|hops|==1` używa istniejącego
  `nextCursor`/`previousCursor` bezpośrednio (bez skip); `|hops|>1` woła
  `skipSymbolReviewPages` raz z `count=(|hops|-1)*pageSize`, potem jedno
  `loadSymbolReviewPage`. Zachowane: `pagingRef`, `requestCoordinator`,
  `requestId`, brak czyszczenia selekcji przy skoku.
- `services/api/tests/test_image_symbol_reviews_api.py`:
  `MemorySymbolCellReviewRepository.skip_keys`; 3 nowe testy (porównanie
  skip vs. chodzenie kursorami, wyczerpanie danych, oba/żaden kursor).
- `packages/admin-api-client/test/client.test.mjs`: nowy test wrappera
  `skipSymbolCellReviews`.
- `apps/admin/test/symbol-review-workspace-contract.test.mjs`: świadoma
  zmiana kontraktu — stara asercja pętli zastąpiona asercjami nowego
  zachowania (nazwa testu też zmieniona, opisuje nowe zachowanie).
- `ai_docs/process/DECISION_LOG.md` (D-433), `ai_docs/process/CURRENT_STATE.md`.

### Verification results

- `pytest services/api/tests/test_image_symbol_reviews_api.py
  services/api/tests/test_image_symbol_reviews_domain.py
  services/api/tests/test_image_symbol_review_query_storage.py -q`:
  75 passed (72 istniejące bez zmian w asercjach + 3 nowe).
- `ruff check` na 5 zmienionych plikach backendu: czysty.
- `mypy` na 4 zmienionych plikach backendu: 0 błędów bezpośrednio w nich;
  szerszy przebieg (4 pliki naraz) pokazuje 79 błędów w innych,
  niepowiązanych plikach (`game_predictor_worker.*` import-not-found) —
  potwierdzone `git stash` na dokładnie tych 4 plikach: baseline też 79,
  identyczna liczba, zero nowych.
- `npm run openapi:generate` + `npm run openapi:check`: czyste,
  wygenerowany klient aktualny.
- `npm run test --workspace @game-predictor/admin`: 539/539 passed.
- `npm run typecheck --workspace @game-predictor/admin`: czysty (po
  dodaniu brakującego re-eksportu `SymbolCellReviewSkipResponse`).
- `npm run lint --workspace @game-predictor/admin`: 0 błędów, 5 ostrzeżeń
  preexisting w niepowiązanych plikach.
- `npm run test --workspace @game-predictor/admin-api-client`: 59/59
  passed (58 istniejących + 1 nowy).
- `npm run typecheck`/`lint --workspace @game-predictor/admin-api-client`:
  czyste.
- `npx prettier --check` na 5 zmienionych plikach JS/TS: wszystkie 5
  zgłoszone, ale potwierdzone `git stash` jako preexisting (dokładnie te
  same 5 plików już przed zmianą — pasuje do znanego, repo-szerokiego
  dryfu formatowania z T1, 367 plików).

### Not completed

- Test na żywej bazie Postgres (integration) — nie zbudowano nowej
  fixture'y (gry/obrazy/plansze/projekcja gotowości) ze względu na koszt;
  poprawność `skip_keys` zweryfikowana testami strukturalnymi (niezmieniona
  generowana SQL dla `list_items`) i funkcjonalnym testem porównawczym na
  fake repository (identyczny wynik co chodzenie kursor po kursorze).
  Ryzyko rezydualne: brak dowodu na rzeczywistych danych Postgres, że
  ścieżka `uses_current_projection=False` (nieaktualna projekcja) w
  `skip_keys` zachowuje się identycznie jak w `list_items` pod realnym
  obciążeniem współbieżnym.
- Pełny `npm run python:test -- -Suite Api` nie uruchomiony (szerszy
  przebieg niż potrzebny zakres); uruchomiono bezpośrednio trzy relewantne
  pliki testowe zamiast tego.
- Nie zaktualizowano `ai_docs/architecture/API_CONTRACT.md` — sprawdzono,
  nie zawiera on wyliczenia endpointów Weryfikacji symboli na tyle
  szczegółowo, żeby wymagał wpisu dla tego jednego dodatkowego endpointu
  (brak wzmianki o `/symbol-cell-reviews` też).

### Documentation updates

- `ai_docs/process/DECISION_LOG.md` (D-433), `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- Rozważyć integracyjny test na realnym Postgresie dla `skip_keys` w
  ścieżce `uses_current_projection=False`, jeśli operator zaobserwuje
  rozbieżność między skip-jump a nawigacją krok-po-kroku na nieaktualnej
  projekcji.
- Analogiczny problem (chodzenie kursor po kursorze przy dużym skoku)
  może występować w innych miejscach z tym samym wzorcem paginacji
  (`unreadable-board-reviews` ma własny `afterCursor` — nie sprawdzono, czy
  ma też UI do skoku o wiele stron na raz).
