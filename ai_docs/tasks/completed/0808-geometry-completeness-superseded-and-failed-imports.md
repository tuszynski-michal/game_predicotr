---
title: TASK-0808 — raport kompletności: pozycje zastąpione, nieudane importy, podgląd po zdjęciu
status: done
last_updated: 2026-10-02
---

# TASK-0808 — raport kompletności: pozycje zastąpione, nieudane importy, podgląd po zdjęciu

## Status

`done`

## Goal

Raport kompletności geometrii (TASK-0806) nie liczy jako braków plansz i
zdjęć zastąpionych nowszym importem, pokazuje kod błędu nieudanego pliku
importu i podaje podgląd każdego zdjęcia po `source_image_id` — nadal bez
żadnego zapisu do bazy.

## Context

Kontrola bazy 2026-10-02 po TASK-0806 (777, tylko `SELECT`):

- 10 390 plansz ma `recognized_boards.status = 'rejected'`; 10 389 należy
  do importu `7d10ae0a` (duplikat importu `f4ef3449`). Ich elementy review
  mają status `superseded` z powodem
  `pending_sequence_replaced_by_newer_import`
  (`system:pending-sequence-owner`); każdy numer sekwencji ma żywy element
  review na innym zdjęciu; żadna z tych plansz nie ma komórek. 1 154
  zdjęcia mają odrzucone wszystkie 9 plansz.
- 99 zdjęć bez żadnej planszy to nieudane pliki importu
  (`image_import_job_files.workflow_status = 'failed'`: 88
  `IMAGE_STAGE_EXECUTION_FAILED`, 6 `IMAGE_STAGE_RESULT_INVALID`, 5
  `IMAGE_VIRTUAL_CELL_SOURCE_SUPPORT_INCOMPLETE`); `source_images.status`
  pozostał `processing`. Pliki istnieją. 73 z 99 mają ten sam
  `checksum_sha256` zaimportowany poprawnie w innym imporcie.
- Lista z TASK-0806 pobiera zdjęcie przez endpoint kluczowany elementem
  review, więc zdjęcie bez planszy nie ma podglądu.

Operator potwierdził 2026-10-02: takie pozycje nie są brakami, a podgląd ma
działać dla każdego wgranego zdjęcia.

## Dependencies / entry conditions

- TASK-0806 ukończony (`v1.7.136`); gałąź `feat/grid-engine-v3`, HEAD
  `v1.7.139` lub nowszy; head Alembic `0138`. Zadanie nie dodaje migracji.
- TASK-0807 startuje po tym zadaniu i używa tej samej, poprawionej
  klasyfikacji.

## Recommended execution

`claude-sonnet-5-5`, reasoning `high`. Rozszerzenie istniejącego pionu
tylko do odczytu o dwa stany i jeden endpoint zasobu według istniejących
wzorców. Eskalacja do `claude-opus-5-5` `high`, jeżeli reguła „zastąpione”
okaże się niejednoznaczna na danych albo zapytanie całej gry przekroczy
kilka sekund. Audyt zawieszony decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md` (sekcja planu V3)
- `ai_docs/tasks/completed/0806-image-geometry-completeness-report.md`
- `ai_docs/delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` (etap V3-0,
  reguła izolacji per gra)
- `ai_docs/process/DECISION_LOG.md` (D-484)
- `ai_docs/requirements/ADMIN_APP.md` (sekcja „Kompletność siatek zdjęć”),
  `ai_docs/architecture/API_CONTRACT.md` (endpointy `geometry-completeness`)

## Scope

- Klasyfikator domenowy i SQL liczników: stan pozycji `superseded`, stany
  zdjęcia `superseded` i `import_failed`.
- Odpowiedzi API: nowe stany, kod błędu importu w elemencie listy, liczniki.
- Endpoint odczytu pliku źródłowego po `source_image_id`.
- Admin: etykiety nowych stanów, podgląd przez nowy endpoint dla każdego
  zdjęcia, kod błędu importu.
- OpenAPI, klient, wrapper, test żądania, dokumentacja.

## Out of scope

- Jakikolwiek zapis do bazy, migracje, usuwanie duplikatu `7d10ae0a`,
  ponawianie nieudanych importów.
- Przepinanie plansz na nowszą rewizję źródła (TASK-0807).
- Bramka w pipeline (TASK-0807).

## Acceptance criteria

- [x] Plansza `rejected` nie liczy się jako plansza z siatką; pozycja bez
      żywej planszy, której numer sekwencji ma żywy element review na innym
      zdjęciu tej gry, ma stan `superseded` i nie czyni zdjęcia
      niekompletnym.
- [x] Zdjęcie, którego wszystkie oczekiwane pozycje są `superseded`, ma stan
      `superseded` i nie wchodzi do liczby niekompletnych ani do listy
      domyślnej; ma własny licznik.
- [x] Zdjęcie bez żadnej żywej planszy, którego plik importu ma
      `workflow_status = 'failed'`, ma stan `import_failed` z kodem błędu;
      gdy ten sam `checksum_sha256` ma w tej grze inne zdjęcie z żywymi
      planszami, stan to `superseded`.
- [x] Liczniki na bazie deweloperskiej zgadzają się z niezależnym zapytaniem
      kontrolnym SQL z tej samej chwili (zapytanie i wynik w `Outcome`);
      raport całej gry nadal mieści się w kilku sekundach.
- [x] `GET` pliku źródłowego po `source_image_id` zwraca obraz z tą samą
      walidacją ścieżki, korzenia i sumy kontrolnej co istniejący endpoint
      zasobu źródłowego; lista nie zależy już od `previewReviewItemId`.
- [x] Test PG `*_test` pokrywa nowe stany, w tym zdjęcie mieszane (część
      pozycji `superseded`, reszta `ok` → `complete`) i drugą grę (numer
      sekwencji żywy tylko w innej grze nie daje `superseded`).
- [x] Brak `INSERT`/`UPDATE`/`DELETE`; kontrakt pionem; `openapi:check`
      przechodzi.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

### Definicje (uzupełniają tabelę z TASK-0806)

„Żywa plansza” = `recognized_boards.status <> 'rejected'`. „Żywy element
review” = `image_review_items.status IN ('pending', 'accepted',
'corrected')` (to samo `_LIVE_STATUSES` co w
`board_import_coverage_repository.py`).

Stan oczekiwanej pozycji — nowa kolejność reguł (pierwsza pasująca wygrywa):

| Stan | Warunek |
|---|---|
| `superseded` | brak żywej planszy na pozycji i numer sekwencji pozycji ma żywy element review na innym zdjęciu tej samej gry |
| `deferred` | brak żywej planszy i otwarty wiersz `image_board_geometry_pending` |
| `missing` | brak żywej planszy, pozostałe przypadki |
| `partial`, `uncertain`, `ok` | jak w TASK-0806, liczone tylko dla żywej planszy |

Stan zdjęcia — nowa kolejność:

| Stan | Warunek |
|---|---|
| `superseded` | zdjęcie ma rewizję źródła i wszystkie oczekiwane pozycje są `superseded`; albo zdjęcie nie ma żadnej żywej planszy, a inne zdjęcie tej gry z tym samym `checksum_sha256` ma żywe plansze |
| `import_failed` | brak żywej planszy, plik importu `failed`, nie `superseded`; kod błędu z `image_import_job_files.error_code` |
| `no_source_geometry` | brak rewizji źródła, pozostałe przypadki |
| `complete` | każda pozycja `ok` albo `superseded`, co najmniej jedna `ok` |
| `incomplete_*` | jak w TASK-0806; pozycje `superseded` są pomijane |

`superseded` i `complete` nie są niekompletne. `import_failed` i
`no_source_geometry` są osobnymi licznikami i filtrami listy; lista
domyślna („wszystkie niekompletne”) obejmuje `incomplete_*`,
`import_failed` i `no_source_geometry`.

Przed kodowaniem sprawdź na bazie deweloperskiej (tylko `SELECT`), ile
zdjęć i pozycji trafia do każdego stanu, i wpisz do `Outcome`. Oczekiwany
rząd wielkości: ok. 1 150 zdjęć `superseded` z importu `7d10ae0a`, ok. 70
`superseded` po SHA, ok. 26 `import_failed`. Jeżeli wynik odbiega
jakościowo (np. tysiące pozycji `superseded` na zdjęciach spoza duplikatu),
zatrzymaj się i opisz rozbieżność.

### Wydajność i izolacja

Sprawdzenie „numer sekwencji ma żywy element review na innym zdjęciu”
wykonuj wyłącznie dla pozycji bez żywej planszy (kilka–kilkanaście tysięcy),
przez indeks `(game_id, sequence_number)` elementów review, nie przez
złączenie całych tabel. Wszystkie zapytania filtrują po `game_id` i działają
po `GameStorageRouter.bind`; zmierz raport całej gry przed i po zmianie.

### Endpoint pliku źródłowego

Obok istniejących tras zasobów (`getOperationalImageReviewSourceAsset` w
`api/image_reviews.py` — przeczytaj jego implementację i użyj tego samego
resolvera ścieżki, tych samych nagłówków i kodów błędów). Parametry:
`game_id`, `source_image_id`. Zdjęcie innej gry → 404. Bez drugiego
mechanizmu serwowania plików. Pole `previewReviewItemId` usuń z odpowiedzi
listy, jeżeli nie ma innego konsumenta; Admin przechodzi na nowy endpoint.

### Niedozwolone skróty

- Nie ukrywaj zdjęć `superseded` bez licznika.
- Nie traktuj `rejected` jako dowodu poprawnej siatki.
- Reguły w SQL i w klasyfikatorze domenowym muszą pozostać zgodne (test PG
  porównuje oba, jak w TASK-0806).

## Expected files

- Istniejące: `services/api/src/game_predictor_api/domain/image_geometry_completeness.py`,
  `storage/image_geometry_completeness_repository.py`,
  `schemas/image_geometry_completeness.py`, `api/image_reviews.py`,
  `application/image_reviews.py`, testy
  `services/api/tests/test_image_geometry_completeness_{domain,api}.py`,
  `services/api/tests/integration/test_image_geometry_completeness_repository.py`,
  `apps/admin/src/features/imports/geometry-completeness-{section.tsx,state.ts}`,
  `apps/admin/test/geometry-completeness-state.test.mjs`,
  `packages/admin-api-client` (OpenAPI, klient, wrapper, test),
  `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/architecture/API_CONTRACT.md`.

## Test cases

- Pozycja z planszą `rejected` i żywym elementem review numeru gdzie indziej
  → `superseded`; bez żywego elementu → `missing`.
- Zdjęcie 9 × `superseded` → `superseded`; 7 `ok` + 2 `superseded` →
  `complete`; 7 `ok` + 1 `superseded` + 1 `missing` → `incomplete_missing`.
- Zdjęcie bez plansz, plik `failed`, brak bliźniaka SHA → `import_failed` z
  kodem; z bliźniakiem SHA mającym plansze → `superseded`.
- Numer sekwencji żywy tylko w drugiej grze → nie `superseded`.
- Endpoint pliku: 200 dla zdjęcia gry, 404 dla zdjęcia innej gry i
  nieznanego identyfikatora, błąd integralności przy złej sumie kontrolnej
  jak w istniejącym endpoincie.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_geometry_completeness_domain.py services/api/tests/test_image_geometry_completeness_api.py
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_image_geometry_completeness_repository.py
.\.venv\Scripts\python.exe -m ruff check services/api
npm run openapi:generate; npm run openapi:check
npm run typecheck --workspace @game-predictor/admin; npm run lint --workspace @game-predictor/admin; npm run test --workspace @game-predictor/admin
```

Limit 120 s na komendę (test PG do 300 s), testy PG pojedynczo. Testy są
planowane, nie zaliczone.

## Risks / open questions

- Reguła `superseded` po SHA zakłada, że bliźniak z żywymi planszami pokrywa
  te same numery sekwencji; pliki o tym samym SHA mają ten sam zakres z
  nazwy, ale sprawdź to na danych i odnotuj wyjątki.
- Usunięcie duplikatu `7d10ae0a` pozostaje osobną, niezatwierdzoną operacją
  destrukcyjną.

## Outcome

Status: `done`. Kod, testy, OpenAPI, klient, Admin i dokumentacja są gotowe;
z kryteriów akceptacji nie jest zaliczony tylko osobny commit i wpis w
`CURRENT_STATE.md` (należą do orkiestratora). **Rozbieżność do decyzji
orkiestratora** (patrz „Decyzja do potwierdzenia”): na danych 777 nie ma ani
jednego zdjęcia `import_failed`, bo 26 zdjęć, których oczekiwano jako
`import_failed`, spełnia pierwszą regułę `superseded`.

### Changed

- Domena `services/api/src/game_predictor_api/domain/image_geometry_completeness.py`:
  nowy stan pozycji `superseded`, nowe stany zdjęcia `superseded` i
  `import_failed`, fakt `sequence_live_elsewhere` w `GeometryPositionFacts`,
  `classify_position` (reguła `superseded` przed `deferred` i `missing`),
  `classify_image` z jawnymi faktami `has_live_boards`,
  `checksum_twin_has_live_boards`, `import_file_failed` oraz stała
  `INCOMPLETE_IMAGE_STATES` (lista domyślna: `incomplete_*`, `import_failed`,
  `no_source_geometry`).
- Repozytorium `storage/image_geometry_completeness_repository.py`: plansza
  `rejected` nie jest żywa w żadnym zapytaniu (liczniki, pozycje, odroczenia);
  pozycje bez żywej planszy („luki”) dostają flagę `superseded` jednym
  korelowanym `EXISTS` po `(game_id, sequence_number, status)` elementów review,
  liczonym tylko dla luk zdjęć, którym brakuje plansz; bliźniak po
  `checksum_sha256` jest liczony tylko dla zdjęć bez żywej planszy; błąd pliku
  importu z `image_import_job_files`. Odroczenia zlicza osobne, lekkie zapytanie
  po otwartych wierszach `image_board_geometry_pending`. Lista domyślna pomija
  `complete` i `superseded`; `imageState=superseded` jest dopuszczone jawnie.
  Element listy ma `import_error_code`, a pole `preview_review_item_id` i
  zapytanie `_PREVIEW_ITEMS_SQL` usunięto. Nowa metoda `source_image_asset`
  (ścieżka i suma zdjęcia gry po `source_image_id`; zdjęcie innej gry i nieznany
  identyfikator to `404 IMAGE_GEOMETRY_COMPLETENESS_SOURCE_IMAGE_NOT_FOUND`).
- API: `GET .../geometry-completeness/{gameId}/images/{sourceImageId}/source`
  (`getImageGeometryCompletenessSourceAsset`) w `api/image_reviews.py`;
  `OperationalImageReviewService.geometry_source_image`;
  `resolve_geometry_completeness_source_asset` w
  `application/image_review_assets.py` używa tego samego `_resolve`, więc tej
  samej walidacji ścieżki, korzenia `data/`, braku symlinku, typu obrazu i sumy
  kontrolnej co `getOperationalImageReviewSourceAsset`, te same nagłówki i kody
  błędów. Schematy: `superseded` i `importFailed` w `images`, stan `superseded`
  w pozycjach, `importErrorCode` zamiast `previewReviewItemId`.
- OpenAPI i wygenerowany klient (`openapi.json`, `generated/*`), wrapper
  `getImageGeometryCompletenessSourceAsset(gameId, sourceImageId)` w
  `packages/admin-api-client/src/index.ts`, testy żądań w
  `packages/admin-api-client/test/client.test.mjs`.
- Admin: `geometry-completeness-state.ts` (etykiety, `LISTED_IMAGE_STATES`,
  `geometryImportErrorLabel`, ton `muted` dla pozycji zastąpionych),
  `geometry-completeness-section.tsx` (licznik i linia „Zastąpione nowszym
  importem”, filtr „Zastąpione nowszym importem”, kod błędu importu, podgląd przez
  nowy endpoint dla każdego zdjęcia, także bez wymiarów i siatek jako zwykły
  obraz), `image-folder-import-actions.ts` (nazwa metody), `globals.css`
  (`geometryTone-muted`), test `apps/admin/test/geometry-completeness-state.test.mjs`.
- Zmienione istniejące testy (kontrakt zmienił się świadomie): PG
  `test_report_counts_every_image_state_and_position_state` (lista stanów pozycji
  zawiera teraz zawsze `superseded` z licznikiem 0, plus asercja
  `superseded`/`import_failed` = 0); PG
  `test_preview_review_item_is_a_board_item_and_prefers_a_non_superseded_one`
  zastąpiony `test_listed_images_carry_no_import_error_code_when_their_file_did_not_fail`
  (pole `previewReviewItemId` nie istnieje); PG
  `test_every_query_runs_in_a_read_only_transaction` obejmuje też nową grę i
  endpoint pliku; API: liczniki raportu, element listy (`importErrorCode`
  zamiast `previewReviewItemId`) i fake repozytorium rozszerzone o nowe pola;
  Admin: asercja `api.getOperationalImageReviewSourceAsset` w
  `geometry-completeness-state.test.mjs` zmieniona na nowy endpoint.
- Bez migracji, bez zapisu do bazy, bez zmian w pipeline, materializacji komórek
  i wyszukiwarce.

### Verification results

Wszystkie komendy z katalogu worktree, wyniki rzeczywiste.

- `pytest ...test_image_geometry_completeness_domain.py` (56 passed) oraz
  `...test_image_geometry_completeness_api.py` (31 passed).
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, jeden proces, baza `*_test`
  utworzona i usunięta): `test_image_geometry_completeness_repository.py` — 26
  passed w 9 s (16 poprzednich po zmianach opisanych niżej, 10 nowych). Nowy
  świat testowy (gra C, 20 zdjęć) obejmuje: wszystkie plansze odrzucone i numery
  żywe na innym zdjęciu (`superseded`); zdjęcie mieszane 7 `ok` + 2 `superseded`
  (`complete`) oraz 7 `ok` + 1 `superseded` + 1 `missing`
  (`incomplete_missing`); wszystkie plansze odrzucone bez pokrycia (`missing`);
  nieudany import bez bliźniaka z rewizją (`import_failed` z kodem) i bez rewizji
  (`import_failed`, nie `no_source_geometry`); nieudany import z bliźniakiem po
  `checksum_sha256` z rewizją i bez rewizji (`superseded`); numer sekwencji żywy
  tylko w drugiej grze (nie `superseded`); numer pokryty tylko elementem review
  `rejected` (nie `superseded`); `superseded` wygrywa z otwartym wierszem
  odroczonym; nieudany plik ze zdjęciem, które ma żywe plansze (`complete`);
  liczniki całej gry i jednego importu (bliźniak z drugiego importu jest
  znajdowany też przy zawężeniu do importu), filtry `superseded`,
  `import_failed`, `no_source_geometry`, zgodność SQL z klasyfikatorem domenowym
  na każdej wylistowanej pozycji i zdjęciu, endpoint zasobu (200/404/None dla
  nieznanej gry) oraz wykonanie wszystkich zapytań w transakcji `READ ONLY`.
- `ruff check services/api scripts`: czysto; `ruff format --check` na 9 zmienionych
  plikach Pythona: czysto. `mypy --strict` (z `MYPYPATH='services/worker/src;services/api/src'`)
  na 6 zmienionych modułach API: 0 błędów w tych plikach (27 znanych błędów w 6
  niezwiązanych plikach, bez zmian).
- `services/api/tests/test_openapi_contract.py`: 2 testy
  (`test_grid_review_openapi_is_topology_aware_and_checksum_bound`,
  `test_operational_image_reviews_openapi_exposes_bounded_cursor_queue`) nie
  przechodzą na `cells.minItems` w schematach review/grid-review, których to
  zadanie nie dotyka; pozostałe przechodzą. Błąd poprzedza zadanie (nie zbadano
  jego pochodzenia).
- `npm run openapi:generate`, `npm run openapi:check`: exit 0.
- `npm run typecheck --workspace @game-predictor/admin`: przechodzi. `npm run lint
  --workspace @game-predictor/admin`: 0 błędów, 4 istniejące ostrzeżenia w
  niezmienionych plikach. `npm run test --workspace @game-predictor/admin`: 617
  pass, 0 fail (2 nowe). Klient: `tsx --test test/client.test.mjs` 67 pass,
  `tsc --noEmit` czysto. Prettier (`--end-of-line auto`) czysto dla zmienionych
  plików TS/TSX/MJS.
- Plik zasobu na danych deweloperskich: 99 zdjęć bez żadnej planszy i 20 zdjęć
  `superseded` (119 plików) przechodzi `resolve_geometry_completeness_source_asset`
  na korzeniu artefaktów głównego checkoutu (`artifacts/data`), czyli ścieżka,
  typ `image/jpeg` i suma kontrolna się zgadzają; wywołanie przez HTTP na
  działającym API nie było możliwe (patrz „Not completed”).

Liczby na bazie deweloperskiej (gra 777, `SELECT`, transakcja `read only`),
repozytorium vs zapytanie kontrolne z tej samej chwili — identyczne:

| stan zdjęcia | status zdjęcia | zdjęcia | oczekiwane pozycje | ok | uncertain | partial | missing | deferred | superseded |
|---|---|---|---|---|---|---|---|---|---|
| complete | waiting_for_review | 55 423 | 498 803 | 498 778 | 0 | 0 | 0 | 0 | 25 |
| incomplete_partial | waiting_for_review | 60 | 540 | 408 | 24 | 108 | 0 | 0 | 0 |
| incomplete_uncertain | waiting_for_review | 76 | 684 | 257 | 425 | 0 | 0 | 0 | 2 |
| superseded | completed | 161 | 1 449 | 0 | 0 | 0 | 0 | 0 | 1 449 |
| superseded | processing | 99 | 819 | 0 | 0 | 0 | 0 | 0 | 819 |
| superseded | waiting_for_review | 993 | 8 937 | 0 | 0 | 0 | 0 | 0 | 8 937 |

Razem 56 812 zdjęć; `incomplete_missing` 0, `import_failed` 0,
`no_source_geometry` 0, `superseded` 1 253, `incomplete` 136 (60 + 76).
Pozycje (511 232 oczekiwane): `ok` 499 443, `uncertain` 449, `partial` 108,
`superseded` 11 232, `missing` 0, `deferred` 0. Dla porównania TASK-0806 (te
same dane, plansze `rejected` liczone jako poprawne): 399 niekompletnych,
w tym 94 `incomplete_missing`, 237 `incomplete_uncertain`, 8 `no_source_geometry`.

Rozbicie 1 253 zdjęć `superseded`: reguła „wszystkie pozycje `superseded`” — 1 245
(11 205 pozycji; 1 154 z duplikatu `7d10ae0a`, 65 + 26 spośród 99 zdjęć bez
planszy); reguła „bliźniak po `checksum_sha256`” — 1 227 (1 154 + 65 + 8); obie
naraz 1 219; tylko pozycje 26 (nieudane `IMAGE_STAGE_EXECUTION_FAILED`, z
rewizją, bez bliźniaka); tylko bliźniak 8 (nieudane bez rewizji geometrii źródła:
2 × `IMAGE_STAGE_EXECUTION_FAILED`, 6 × `IMAGE_STAGE_RESULT_INVALID`). 99 zdjęć
bez planszy według kodu błędu pliku: 88 `IMAGE_STAGE_EXECUTION_FAILED` (26 bez
bliźniaka), 6 `IMAGE_STAGE_RESULT_INVALID`, 5
`IMAGE_VIRTUAL_CELL_SOURCE_SUPPORT_INCOMPLETE`; 73 z 99 ma bliźniaka. 3 nieudane
pliki mają żywe plansze (nie dotyczą stanu).

Zapytanie kontrolne (niezależne od implementacji: pozycje z `generate_series` po
długości zakresu, korelowane `EXISTS`, bez CTE repozytorium; `:g` = identyfikator
gry), wynik 5,1 s:

```sql
WITH cur AS (
  SELECT r.source_image_id, r.sequence_range_start AS st, r.sequence_range_end - r.sequence_range_start + 1 AS n
  FROM image_source_geometry_revisions r
  WHERE r.game_id = :g
    AND r.revision = (SELECT max(r2.revision) FROM image_source_geometry_revisions r2
                      WHERE r2.game_id = r.game_id AND r2.source_image_id = r.source_image_id)
), pos AS (
  SELECT cur.source_image_id AS sid, gs.p, cur.st + gs.p AS seq,
    b.id AS bid, b.completeness_status AS comp, b.approved_geometry_revision AS apr,
    b.geometry_revision AS grev, pr.status AS pr_status
  FROM cur CROSS JOIN LATERAL generate_series(0, cur.n - 1) gs(p)
  LEFT JOIN recognized_boards b ON b.game_id = :g
        AND b.source_image_id = cur.source_image_id AND b.position_index = gs.p AND b.status <> 'rejected'
  LEFT JOIN image_source_geometry_revisions pr ON pr.game_id = :g
        AND pr.id = b.source_geometry_revision_id
), posstate AS (
  SELECT sid, p,
    CASE WHEN bid IS NULL THEN
           CASE WHEN EXISTS (SELECT 1 FROM image_review_items ri
                             WHERE ri.game_id = :g
                               AND ri.sequence_number = pos.seq
                               AND ri.status IN ('pending','accepted','corrected')
                               AND (SELECT rb.source_image_id FROM recognized_boards rb
                                    WHERE rb.game_id = ri.game_id AND rb.id = ri.recognized_board_id) <> pos.sid)
                THEN 'superseded'
                WHEN EXISTS (SELECT 1 FROM image_board_geometry_pending g
                             WHERE g.game_id = :g
                               AND g.source_image_id = pos.sid AND g.position_index = pos.p
                               AND g.status = 'pending') THEN 'deferred'
                ELSE 'missing' END
         WHEN comp = 'pending_partial' THEN 'partial'
         WHEN comp = 'complete' AND (apr IS NOT DISTINCT FROM grev AND apr IS NOT NULL OR pr_status = 'accepted') THEN 'ok'
         ELSE 'uncertain' END AS st
  FROM pos
), agg AS (
  SELECT sid, count(*) AS n,
    count(*) FILTER (WHERE st='ok') AS n_ok, count(*) FILTER (WHERE st='uncertain') AS n_unc,
    count(*) FILTER (WHERE st='partial') AS n_par, count(*) FILTER (WHERE st='missing') AS n_mis,
    count(*) FILTER (WHERE st='deferred') AS n_def, count(*) FILTER (WHERE st='superseded') AS n_sup
  FROM posstate GROUP BY sid
), img AS (
  SELECT s.id, s.status AS src_status, s.checksum_sha256,
    (agg.sid IS NOT NULL) AS has_rev, agg.n, agg.n_ok, agg.n_unc, agg.n_par, agg.n_mis, agg.n_def, agg.n_sup,
    (SELECT count(*) FROM recognized_boards b WHERE b.game_id = s.game_id AND b.source_image_id = s.id AND b.status <> 'rejected') AS live_any,
    EXISTS (SELECT 1 FROM image_import_job_files f WHERE f.game_id = s.game_id AND f.job_id = s.import_job_id
              AND f.file_execution_key = s.file_execution_key AND f.workflow_status = 'failed') AS failed
  FROM source_images s LEFT JOIN agg ON agg.sid = s.id
  WHERE s.game_id = :g
), fin AS (
  SELECT img.*,
    CASE WHEN has_rev AND n_sup = n THEN 'superseded'
         WHEN live_any = 0 AND EXISTS (SELECT 1 FROM source_images s2
                 WHERE s2.game_id = :g
                   AND s2.checksum_sha256 = img.checksum_sha256 AND s2.id <> img.id
                   AND EXISTS (SELECT 1 FROM recognized_boards b2 WHERE b2.game_id = s2.game_id
                               AND b2.source_image_id = s2.id AND b2.status <> 'rejected')) THEN 'superseded'
         WHEN live_any = 0 AND failed THEN 'import_failed'
         WHEN NOT has_rev THEN 'no_source_geometry'
         WHEN n_mis + n_def > 0 THEN 'incomplete_missing'
         WHEN n_par > 0 THEN 'incomplete_partial'
         WHEN n_unc > 0 THEN 'incomplete_uncertain'
         ELSE 'complete' END AS image_state
  FROM img
)
SELECT image_state, src_status, count(*) AS images, COALESCE(sum(n),0) AS expected, COALESCE(sum(n_ok),0) AS ok,
  COALESCE(sum(n_unc),0) AS unc, COALESCE(sum(n_par),0) AS par, COALESCE(sum(n_mis),0) AS mis,
  COALESCE(sum(n_def),0) AS def, COALESCE(sum(n_sup),0) AS sup
FROM fin GROUP BY 1,2 ORDER BY 1,2;
```

Czasy (baza deweloperska, jedna instancja PostgreSQL, 3 powtórzenia, cache
ciepły; te same zapytania uruchomione przez repozytorium w transakcji
`READ ONLY`):

- raport całej gry: przed zmianą (wersja z TASK-0806 wczytana z `git show HEAD`)
  4,6 s zimno, 2,1 s ciepło; po zmianie 3,5 s przy pierwszym wywołaniu, 2,9–3,3 s
  ciepło. Zapytanie SQL raportu samo w sobie: 2,7 s; odroczenia (osobne
  zapytanie): 6–25 ms. Wzrost o ok. 1 s wynika z sprawdzenia pokrycia numerów
  sekwencji dla ok. 11 tys. pozycji bez żywej planszy i z dołączenia pliku
  importu; bez zmiany schematu.
- strona listy (25 zdjęć, całej gry): przed 2,1–2,2 s, po 2,9–3,1 s; strona 100
  zdjęć `superseded` 3,1 s; przejście wszystkich stron: lista domyślna (136
  zdjęć) 6,1 s, filtr `superseded` (1 253 zdjęć, 13 stron) 40,5 s.
- sprawdzenie `EXPLAIN (ANALYZE)` raportu: dominują sekwencyjny odczyt ok. 500 tys.
  plansz i agregacja po zdjęciu (jak w TASK-0806), pokrycie numerów to ok. 11 tys.
  wyszukiwań po `(game_id, sequence_number, status)`.

### Decyzja do potwierdzenia

Zadanie oczekiwało ok. 26 zdjęć `import_failed` (99 nieudanych − 73 z
bliźniakiem). Zgodnie z pisemną kolejnością reguł pierwsza reguła zdjęcia
(`superseded`: rewizja źródła i wszystkie pozycje `superseded`) wygrywa z
`import_failed`. Wszystkie 26 zdjęć bez bliźniaka ma rewizję źródła, a ich 9
numerów sekwencji ma żywy element review na innych zdjęciach (zaimportowane
poprawnie innym plikiem), więc są `superseded`, a `import_failed` jest na danych
777 puste (0). Suma `superseded` + `import_failed` (1 253) zgadza się z
oczekiwanym rzędem wielkości (ok. 1 150 + ok. 70 + ok. 26), więc nie jest to
rozbieżność jakościowa tego rodzaju, o którym mówi zadanie (tysiące pozycji
`superseded` poza duplikatem), lecz skutek kolejności reguł. Zachowano literalną kolejność zadania, bo operator napisał, że pozycje
pokryte gdzie indziej „nie są brakami”. Jeżeli `import_failed` ma wygrywać z
regułą „wszystkie pozycje `superseded`” (wtedy 26 zdjęć bez bliźniaka trafi do
`import_failed`, a zdjęcia z bliźniakiem zostają `superseded`), zmiana to jedna
linia `CASE` w `_IMAGE_STATES_CTE` i kolejność dwóch bloków w `classify_image`
plus aktualizacja testów domenowych i PG oraz dokumentacji.

### Orchestrator closure (2026-10-02)

- Kolejność reguł pozostaje jak w zadaniu: 26 nieudanych plików bez
  bliźniaka SHA ma wszystkie numery sekwencji pokryte żywymi planszami na
  innych zdjęciach, więc są `superseded`, a `import_failed` jest dziś puste
  (stan pozostaje dla przyszłych importów). Kod błędu importu jest widoczny
  w elemencie listy.
- Odbiór na instancji worktree (API `127.0.0.1:8020` po restarcie, Admin
  `127.0.0.1:3020`): raport 56 812 zdjęć, 55 423 kompletne, 136
  niekompletnych (60 częściowych, 76 niepotwierdzonych), 1 253 zastąpione;
  sekcja pokazuje licznik i zakładkę „Zastąpione nowszym importem”;
  `GET …/images/{sourceImageId}/source` zwraca 200 `image/jpeg` dla zdjęcia
  bez planszy i 404 dla nieznanego identyfikatora.
- Dwa testy `test_openapi_contract.py` (`cells.minItems`) nie przechodzą na
  tej gałęzi niezależnie od zadania; gałąź integracyjna naprawiła jeden z
  nich w `v1.7.143` (TASK-0798), drugi nie przechodzi także tam.

### Not completed
- Widok w przeglądarce nie był sprawdzany: API na porcie 8020 nie przeładowuje
  kodu, więc działający Admin (3020, z gorącym przeładowaniem) rozmawia ze starą
  wersją API do czasu jego restartu; nowe pola (`importErrorCode`, `superseded`,
  `importFailed`) i endpoint pliku są potwierdzone testami kontraktu, nie
  ekranem. Po restarcie API na 8020 warto obejrzeć sekcję (filtr „Zastąpione
  nowszym importem”, podgląd zdjęcia bez planszy).
- Przejścia wszystkich stron listy `superseded` nie przyspieszano (40 s przy 13
  stronach po 100); strona 25 zdjęć to ok. 3 s. Jeżeli lista `superseded` ma być
  przeglądana intensywnie, warto wyliczyć stany zdjęć raz na żądanie i
  stronicować po nich (osobne zadanie).
- `npm run python:lint` i `python:typecheck` w całości nie były uruchamiane
  (cienkie `.venv` worktree; użyto `python -m ruff`, `mypy` na zmienionych
  modułach); 2 testy `test_openapi_contract.py` czerwone niezależnie od zadania.

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md` — sekcja „Kompletność siatek zdjęć”:
  definicje żywej planszy i żywego elementu review, nowa kolejność reguł pozycji
  i zdjęcia, liczniki, filtr i podgląd każdego zdjęcia.
- `ai_docs/architecture/API_CONTRACT.md` — endpoint pliku źródłowego po
  `sourceImageId`, nowe stany i pola odpowiedzi, usunięcie `previewReviewItemId`,
  lista domyślna.
- `CURRENT_STATE.md`, `DECISION_LOG.md` i przeniesienie zadania zostawiam
  orkiestratorowi. Nowy wpis w `DECISION_LOG.md` nie jest wymagany (D-484
  pozostaje spójne; to doprecyzowanie raportu), chyba że orkiestrator zmieni
  kolejność reguł `import_failed`/`superseded`.

### Recommended next task

- TASK-0807 na tej klasyfikacji: kolejka siatek to dziś 136 niekompletnych zdjęć
  (60 `incomplete_partial`, 76 `incomplete_uncertain`, z 449 niepotwierdzonymi i
  108 częściowymi planszami) zamiast 399 z TASK-0806; zdjęcia `superseded` (1 253)
  nie powinny wchodzić do bramki pipeline'u.
- Decyzja o kolejności `import_failed` względem reguły „wszystkie pozycje
  `superseded`” (wyżej) przed rozpoczęciem TASK-0807.
