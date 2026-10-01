---
title: TASK-0806 — raport kompletności geometrii zdjęć i lista zdjęć niekompletnych
status: done
last_updated: 2026-10-02
---

# TASK-0806 — raport kompletności geometrii zdjęć i lista zdjęć niekompletnych

## Status

`done`

## Goal

Admin pokazuje dla gry i dla pojedynczego importu, ile zdjęć źródłowych ma
komplet poprawnych siatek, a ile nie, oraz stronicowaną listę zdjęć
niekompletnych z podglądem całego zdjęcia i naniesionymi siatkami — bez
żadnego zapisu do bazy.

## Context

D-484: jednostką geometrii jest zdjęcie. Dotąd pipeline traktował każdą
planszę osobno, więc braki siatek na części zdjęć wychodziły dopiero w
weryfikacji symboli. To zadanie daje widok tylko do odczytu; egzekwowanie
bramki w pipeline to TASK-0807 i **nie** należy do tego zadania.

## Dependencies / entry conditions

- Fakt: plan `GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` zaakceptowany, etap
  V3-0 uruchomiony przez operatora 2026-10-01.
- Fakt: praca w worktree `worktrees/grid-engine-v3`, gałąź
  `feat/grid-engine-v3` (od `v1.7.134`). `.venv` worktree korzysta z
  pakietów głównego checkoutu przez plik `.pth`; `node_modules` zainstalowane.
- Fakt: baza deweloperska ma head Alembic `0137`; zadanie nie dodaje
  migracji.
- Kontrola 2026-10-01 (gra 777, `game_data_v2`): 56 816 zdjęć źródłowych,
  56 808 z rewizją geometrii źródła, 56 710 z kompletem rozpoznanych plansz,
  99 bez żadnej planszy (wszystkie `source_images.status = 'processing'`),
  7 z niepełną liczbą plansz, 4 z otwartą odroczoną geometrią. Liczby mogą
  się zmieniać — kryterium jest zgodność z zapytaniem kontrolnym wykonanym w
  tej samej chwili, nie z tymi wartościami.

## Recommended execution

`claude-sonnet-5-5`, reasoning `high`. Raport i widok tylko do odczytu na
istniejących tabelach, kontrakt pionem według istniejącego wzorca
`board-import-coverage`. Eskalacja do `claude-opus-5-5` `high`, jeżeli
zapytanie nie mieści się w budżecie czasu bez zmiany schematu albo definicja
stanu planszy okaże się sprzeczna z danymi. Audyt zawieszony decyzją
operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md` (sekcja planu V3)
- `ai_docs/delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` (reguły, etap V3-0)
- `ai_docs/process/DECISION_LOG.md` (D-484, D-449, D-462)
- `ai_docs/requirements/IMAGE_INGESTION.md` (sekcja „Kompletność geometrii
  zdjęcia — D-484” oraz opis `image_board_geometry_pending`)
- `ai_docs/requirements/ADMIN_APP.md` (panel importu zdjęć)

## Scope

- Czysta funkcja domenowa klasyfikująca planszę i zdjęcie.
- Repozytorium tylko do odczytu, serwis, endpointy Admin API, OpenAPI,
  wygenerowany klient, wrapper klienta Admina, test żądania.
- Sekcja w panelu importu zdjęć: liczniki, filtr importu, lista zdjęć
  niekompletnych, podgląd zdjęcia z siatkami.
- Sygnał „plansza z niską jakością symboli” jako osobne, jawnie uruchamiane
  zapytanie.
- Aktualizacja `ADMIN_APP.md` i `API_CONTRACT.md`.

## Out of scope

- Jakikolwiek zapis do bazy, migracje, nowy stan zdjęcia (TASK-0807).
- Zmiana pipeline, materializacji komórek, wyszukiwarki, kolejki odroczonej
  geometrii.
- Korekta siatek z nowego widoku — widok tylko linkuje do istniejących
  narzędzi korekty, jeżeli link da się zbudować z posiadanych
  identyfikatorów.
- Reviewer (zdalny) — tylko Admin.

## Acceptance criteria

- [x] `GET` raportu zwraca dla gry (i opcjonalnie jednego importu) liczniki:
      zdjęcia łącznie, kompletne, niekompletne w podziale na stany zdjęcia,
      oraz liczbę brakujących plansz w podziale na powód.
- [x] `GET` listy zwraca stronicowane zdjęcia niekompletne z: identyfikatorem
      zdjęcia i importu, ścieżką względną, zakresem numerów sekwencji,
      liczbą oczekiwanych plansz i stanem każdej oczekiwanej pozycji
      (pozycja, numer sekwencji, stan, kod powodu).
- [x] Liczniki na bazie deweloperskiej zgadzają się z zapytaniem kontrolnym
      SQL wykonanym w tej samej chwili (zapytanie i wynik w `Outcome`).
- [x] Panel importu pokazuje licznik zdjęć niekompletnych dla gry i dla
      wybranego importu; lista pokazuje podgląd całego zdjęcia z siatkami
      plansz, które siatkę mają, i wyróżnia pozycje bez siatki.
- [x] Sygnał niskiej jakości symboli działa jako osobne żądanie z jawnym
      progiem i nie spowalnia raportu podstawowego.
- [x] Zadanie nie wykonuje żadnego `INSERT`/`UPDATE`/`DELETE`; test PG na
      bazie `*_test` pokrywa wszystkie stany planszy i zdjęcia.
- [x] OpenAPI, klient, wrapper i test żądania zmienione razem;
      `npm run openapi:check` przechodzi.
- [x] Osobny commit, `Outcome`, wpis w `CURRENT_STATE.md`.

## Technical notes

### Definicje (źródło prawdy: D-484)

Bieżąca rewizja geometrii źródła zdjęcia = wiersz
`image_source_geometry_revisions` o największym `revision` dla
`source_image_id`. Oczekiwane pozycje = jej `active_board_slots`; numer
sekwencji pozycji `p` = `sequence_range_start + p`.

Stan oczekiwanej pozycji (pierwszy pasujący wiersz wygrywa):

| Stan | Warunek |
|---|---|
| `deferred` | brak `recognized_boards` dla (zdjęcie, pozycja) i istnieje `image_board_geometry_pending` ze `status = 'pending'`; kod powodu = `reason_code` |
| `missing` | brak `recognized_boards` i brak otwartego wiersza odroczonego |
| `partial` | plansza istnieje, `completeness_status = 'pending_partial'` |
| `uncertain` | plansza istnieje i jest kompletna, ale jej geometria nie jest ani zatwierdzona przez człowieka, ani zaakceptowana przez silnik bez zastrzeżeń |
| `ok` | plansza istnieje, jest kompletna i ma geometrię zatwierdzoną (`approved_geometry_revision = geometry_revision`) albo rewizja geometrii źródła, na którą wskazuje plansza (`source_geometry_revision_id`), ma `status = 'accepted'` |

Stan zdjęcia:

| Stan | Warunek |
|---|---|
| `no_source_geometry` | zdjęcie nie ma żadnej rewizji geometrii źródła (oczekiwana liczba plansz nieznana) |
| `complete` | wszystkie oczekiwane pozycje `ok` |
| `incomplete_missing` | co najmniej jedna pozycja `deferred` albo `missing` |
| `incomplete_partial` | brak pozycji `deferred`/`missing`, co najmniej jedna `partial` |
| `incomplete_uncertain` | pozostałe: co najmniej jedna `uncertain`, reszta `ok` |

Przed kodowaniem sprawdź na bazie deweloperskiej (tylko `SELECT`), czy
warunek `ok`/`uncertain` odpowiada danym: ile plansz wskazuje rewizję
źródła `needs_review` bez zatwierdzenia. Jeżeli `status` rewizji źródła
okaże się nieadekwatny jako dowód „zaakceptowana bez zastrzeżeń” (np.
plansze po korekcie per plansza w `image_board_geometry_revisions`),
zatrzymaj się i opisz rozbieżność — to decyzja definicji, nie szczegół
implementacji. Liczby dla każdego stanu wpisz do `Outcome`.

### Warstwy (wzorzec: `board-import-coverage`)

- Domena: klasyfikacja jako czysta funkcja na prostych rekordach wejściowych
  (pozycja, czy plansza istnieje, kompletność, zatwierdzenie, status rewizji,
  powód odroczenia) → stan pozycji i stan zdjęcia. Bez SQLAlchemy.
- Repozytorium: jak `SqlAlchemyBoardImportCoverageRepository` — najpierw
  `GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)`,
  bo tabele gry żyją w `game_data_v2`. Liczniki liczone w SQL (agregacja po
  zdjęciu), nie przez wczytanie 56 tys. zdjęć do Pythona. Lista stronicowana
  kursorem po (`relative_path`, `id`) albo innym stabilnym kluczu; limit ≤ 100.
- Endpointy w istniejącym routerze `api/image_reviews.py` obok
  `getBoardImportCoverage` (proponowane `operation_id`:
  `getImageGeometryCompleteness`, `listIncompleteGeometryImages`,
  `getImageGeometryLowQualityBoards`), parametry: `game_id` w ścieżce,
  `importJobId` opcjonalny, filtr stanu zdjęcia, kursor, limit.
- Podgląd zdjęcia: użyj istniejącego endpointu zasobu źródłowego
  (`getImageGridReviewSourceAsset` albo odpowiednika z weryfikacji symboli —
  sprawdź, który przyjmuje `source_image_id`); nie dodawaj równoległego
  serwowania plików. Quady plansz do naniesienia pochodzą z
  `recognized_boards.board_geometry` / `board_geometries` bieżącej rewizji;
  zwróć je w elemencie listy w przestrzeni pikseli zdjęcia
  (`exif-normalized-rgb-pixels-v1`) razem z `oriented_width/height`.

### Sygnał niskiej jakości symboli

Plansza „niskiej jakości” = plansza, na której co najmniej `minCells`
komórek nie ma decyzji człowieka i ma `prediction_confidence ≤ maxConfidence`
(`image_symbol_review_cells`). Domyślne `maxConfidence = 0.80`,
`minCells = 5` (założenie do weryfikacji przez operatora; oba jako parametry
zapytania z walidacją zakresu). Sprawdź w kodzie weryfikacji symboli, jak
liczony jest przedział „≤ 80%” (D-462, TASK-0749–0751), i użyj tej samej
definicji „decyzji człowieka” i jakości zamiast własnej. Tabela komórek ma
miliony wierszy: zapytanie musi być ograniczone do jednego importu albo
mieć `statement_timeout` ustawiony lokalnie dla transakcji; przekroczenie
czasu zwraca jawny błąd domenowy, nie pusty wynik. Zmierz `EXPLAIN (ANALYZE)`
na bazie deweloperskiej dla jednego importu i dla całej gry; wynik do
`Outcome`. Jeżeli zakres gry przekracza 10 s, udostępnij sygnał tylko per
import i zapisz to jako ograniczenie.

### UI

Nowa sekcja w `image-folder-import-panel.tsx` obok `MissingBoardsSection`
(osobny komponent i plik stanu, wzorzec `missing-boards-section.tsx` /
`missing-boards-state.ts`): liczniki, przełącznik „cała gra / wybrany
import”, filtr stanu, lista z miniaturą całego zdjęcia (SVG z quadami nad
obrazem), pozycje bez siatki oznaczone tekstem i kolorem z istniejących
tokenów. Odświeżanie jak w `MissingBoardsSection` (token + polling tylko
przy aktywnym imporcie). Teksty po polsku.

### Niedozwolone skróty

- Nie utożsamiaj „ma 9 rozpoznanych plansz” z „kompletne” — to tylko
  kontrola pomocnicza.
- Nie pomijaj po cichu zdjęć bez rewizji geometrii źródła ani zdjęć w
  statusie `processing`; mają własny stan/licznik.
- Nie pisz ręcznie typów odpowiedzi w Adminie.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/api/image_reviews.py`
  (router), `application/image_reviews.py::OperationalImageReviewService`,
  `main.py` (wiring repozytorium), `schemas/` (odpowiedzi),
  `apps/admin/src/features/imports/image-folder-import-panel.tsx`,
  `image-folder-import-actions.ts::ImageFolderImportClient`,
  `packages/admin-api-client` (OpenAPI + generowany klient),
  `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/architecture/API_CONTRACT.md`.
- Nowe (proponowane):
  `services/api/src/game_predictor_api/domain/image_geometry_completeness.py`,
  `storage/image_geometry_completeness_repository.py`,
  `services/api/tests/test_image_geometry_completeness_domain.py`,
  `services/api/tests/test_image_geometry_completeness_api.py`,
  `services/api/tests/integration/test_image_geometry_completeness_repository.py`,
  `apps/admin/src/features/imports/geometry-completeness-section.tsx`,
  `geometry-completeness-state.ts` i test w `apps/admin/test/`.

## Test cases

- Domena: każda kombinacja z tabeli stanów pozycji; zdjęcie 9/9 `ok` →
  `complete`; 8 `ok` + 1 `deferred` → `incomplete_missing`; 8 `ok` + 1
  `partial` → `incomplete_partial`; 8 `ok` + 1 `uncertain` →
  `incomplete_uncertain`; zakres 4 plansz (`active_board_slots` = 0..3) z 4
  `ok` → `complete`; brak rewizji → `no_source_geometry`.
- Repozytorium (PG `*_test`): gra z pięcioma zdjęciami po jednym na stan;
  liczniki i lista zgodne; filtr `importJobId`; stronicowanie stabilne;
  starsza rewizja źródła nie wpływa na wynik; zamknięty (`resolved`,
  `superseded`) wiersz odroczony nie daje `deferred`; druga gra nie
  przecieka do wyniku.
- API: 200 z kształtem odpowiedzi, 404 dla nieznanej gry, walidacja limitu
  i progów sygnału jakości.
- Admin: stan sekcji (ładowanie, błąd, pusto, lista), etykiety stanów.

## Verification

Z katalogu worktree, każda komenda z limitem 120 s (PG: do 300 s, znany
czas tworzenia bazy testowej):

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_geometry_completeness_domain.py services/api/tests/test_image_geometry_completeness_api.py
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_image_geometry_completeness_repository.py
npm run python:lint; npm run python:typecheck
npm run openapi:generate; npm run openapi:check
npm run typecheck --workspace @game-predictor/admin; npm run lint --workspace @game-predictor/admin; npm run test --workspace @game-predictor/admin
```

Testy są planowane, nie zaliczone. Testy PG uruchamiaj pojedynczo (limit
8 GB VM WSL, inne sesje korzystają z tej samej instancji PostgreSQL).

## Risks / open questions

- Kontrola definicji `ok`/`uncertain` 2026-10-01 (plansze 777 według rewizji
  źródła wskazanej przez planszę): 370 040 automatycznych `accepted` bez
  zatwierdzenia, 138 081 zatwierdzonych kompletnych, 461 ręcznych
  `accepted` bez bieżącego zatwierdzenia, 1 729 automatycznych
  `needs_review` bez zatwierdzenia (→ `uncertain`), 108 `pending_partial`
  (→ `partial`). 1 703 plansze wskazują rewizję źródła starszą niż
  najnowsza rewizja zdjęcia — oczekiwane pozycje bierz z najnowszej, status
  z rewizji wskazanej przez planszę.
- Próg sygnału jakości (0,80 / 5 komórek) jest założeniem.
- 99 zdjęć w `processing` bez plansz: przyczyna nieznana; raport je pokazuje,
  diagnoza poza zakresem.

## Outcome

Status: `done`. Kod, testy, OpenAPI i dokumentacja są gotowe; z kryteriów
akceptacji nie jest zaliczone jedno (panel importu, patrz „Not completed”), a
osobny commit, wpis w `CURRENT_STATE.md` i przeniesienie pliku należą do
orkiestratora.

### Changed

- Domena: `services/api/src/game_predictor_api/domain/image_geometry_completeness.py`
  — czyste `classify_position` / `classify_image` (tabele stanów z D-484),
  `extract_position_quad` (czworokąt z `symbolGridQuad`, potem `finalQuad`; brak
  zamiast wymyślonej siatki), kursor listy `(relative_path, id)` i walidowane
  progi sygnału jakości (`LowQualityThresholds`).
- Repozytorium tylko do odczytu:
  `storage/image_geometry_completeness_repository.py`
  (`SqlAlchemyImageGeometryCompletenessRepository`). Wiąże sesję przez
  `GameStorageRouter().bind(..., READ)`. Liczniki raportu i identyfikacja zdjęć
  niekompletnych są jednym zapytaniem agregującym po zdjęciu (bez wczytywania
  zdjęć do Pythona); pozycje, czworokąty i element podglądu pobiera dopiero
  zapytanie dla jednej strony (do 100 zdjęć) i przepuszcza przez czysty
  klasyfikator.
- Serwis i endpointy w istniejącym routerze `api/image_reviews.py`:
  `GET .../geometry-completeness/{gameId}` (`getImageGeometryCompleteness`),
  `.../incomplete-images` (`listIncompleteGeometryImages`),
  `.../low-quality-boards` (`getImageGeometryLowQualityBoards`); schematy w
  `schemas/image_geometry_completeness.py`, metody w
  `OperationalImageReviewService`, wiring w `main.py`.
- OpenAPI (`packages/admin-api-client/openapi/openapi.json`) i wygenerowany
  klient (`generated/index.ts`, `sdk.gen.ts`, `types.gen.ts`), wrapper w
  `packages/admin-api-client/src/index.ts` (trzy metody + opcje + eksport
  typów), test żądania w `packages/admin-api-client/test/client.test.mjs`.
- Admin: `geometry-completeness-section.tsx` i `geometry-completeness-state.ts`
  w `apps/admin/src/features/imports/`, montaż pod `MissingBoardsSection` w
  `image-folder-import-panel.tsx` (element `MissingBoardsSection` bez zmian),
  cztery nazwy metod w `ImageFolderImportClient`
  (`image-folder-import-actions.ts`), style `geometry*` w `globals.css`, test
  `apps/admin/test/geometry-completeness-state.test.mjs`.
- Testy: `services/api/tests/test_image_geometry_completeness_domain.py`,
  `test_image_geometry_completeness_api.py`,
  `services/api/tests/integration/test_image_geometry_completeness_repository.py`.
- Dokumentacja: `ai_docs/requirements/ADMIN_APP.md` (sekcja „Kompletność siatek
  zdjęć”), `ai_docs/architecture/API_CONTRACT.md` (trzy endpointy).
- Bez migracji, bez zapisu do bazy, bez zmian w pipeline, materializacji
  komórek i wyszukiwarce.

### Verification results

Testy i kontrole (z katalogu worktree, wyniki rzeczywiste):

- `pytest ...test_image_geometry_completeness_domain.py
  ...test_image_geometry_completeness_api.py` oraz istniejący
  `test_board_import_coverage_api.py`: 71 passed.
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, jeden proces, baza
  `*_test` utworzona i usunięta):
  `test_image_geometry_completeness_repository.py` — 16 passed w 10 s.
  Scenariusz: gra w `game_data_v2` z 11 zdjęciami (kompletne 9/9; brak planszy z
  otwartym wierszem odroczonym i bez; plansza częściowa; rewizja `needs_review`
  z zatwierdzonymi planszami i jedną z nieaktualnym zatwierdzeniem; zdjęcie bez
  rewizji w `processing`; zakres 4 plansz; plansze wskazujące starszą rewizję
  `needs_review` przy nowszej ręcznej `accepted`; wiersze odroczone `resolved` i
  `superseded`; starsza rewizja z 9 slotami przy nowszej z 4; drugi import) i
  druga gra. Sprawdzone: liczniki (11 zdjęć: 4 kompletne, 2 brak plansz, 1
  częściowe, 3 niepotwierdzone, 1 bez geometrii; 80 oczekiwanych pozycji: 56
  ok, 19 uncertain, 1 partial, 3 missing, 1 deferred), filtr importu, filtr
  stanu, stabilne stronicowanie kursorem (limit 2 daje tę samą kolejność co
  jedna strona), brak wycieku drugiej gry, 404 dla importu cudzej gry, zgodność
  liczników SQL z klasyfikatorem domenowym na każdej liście, sygnał jakości
  (próg `≤`, minCells, komórki niewidoczne i zatwierdzone nie liczą się, filtr
  importu), jawny błąd przy przekroczeniu limitu czasu (zasymulowany `pg_sleep`)
  oraz wykonanie wszystkich zapytań w transakcji `READ ONLY` (każdy zapis
  zakończyłby się błędem).
- `ruff check` na zmienionych/nowych plikach Pythona i `ruff format --check`:
  czysto. Uwaga środowiskowa: `npm run python:lint` w worktree kończy się
  błędem, bo cienkie `.venv` nie ma `ruff.exe` (`FileNotFoundError ...
  worktrees\grid-engine-v3\.venv\Scripts\ruff.exe`); uruchomiłem `ruff.exe` z
  `.venv` głównego checkoutu na plikach worktree (`ruff check services/api
  services/worker scripts`: 1 błąd E501 w
  `services/worker/tests/test_page_geometry_preflight.py:345`, plik niezmieniony
  przez to zadanie).
- `mypy` (strict) na nowych i zmienionych modułach API: 0 błędów w tych plikach.
  Uruchomienie z `MYPYPATH="services/worker/src;services/api/src"` zgłasza 27
  istniejących błędów w sześciu niezwiązanych plikach (m.in.
  `v7_label_geometry_calibration`, `contrast_frame_grid_v12`,
  `page_geometry_preflight`); bez tej zmiennej mypy nie rozwiązuje importów
  `game_predictor_worker` w cienkim venv (85 błędów `import-not-found`, żaden w
  nowych plikach). Pełnego `npm run python:typecheck` nie uznaję za zaliczony.
- `npm run openapi:generate` oraz `npm run openapi:check`: przechodzi (exit 0).
- `npm run typecheck --workspace @game-predictor/admin`: przechodzi.
  `npm run lint --workspace @game-predictor/admin`: 0 błędów, 4 istniejące
  ostrzeżenia w niezmienionych miejscach. `npm run test --workspace
  @game-predictor/admin`: 615 pass, 0 fail (w tym 11 nowych). Klient:
  `tsx --test test/*.test.mjs` w `packages/admin-api-client`: 73 pass, 0 fail
  (w tym nowy test żądania), `tsc --noEmit` czysto. Prettier (z
  `--end-of-line auto`) czysto dla zmienionych plików.
- Widok w przeglądarce nie był uruchamiany (zakaz startu serwerów deweloperskich).

Zapytanie kontrolne na bazie deweloperskiej (gra 777, `SELECT`, transakcja
`read only`, `search_path = game_data_v2, public`). Niezależne od implementacji:
oczekiwane pozycje z `generate_series` po długości zakresu, a nie z
`active_board_slots`, zliczenia korelowanymi podzapytaniami:

```sql
WITH cur AS (
  SELECT r.source_image_id, r.sequence_range_end - r.sequence_range_start + 1 AS n
  FROM image_source_geometry_revisions r
  WHERE r.game_id = :g
    AND r.revision = (SELECT max(r2.revision) FROM image_source_geometry_revisions r2
                      WHERE r2.game_id = r.game_id AND r2.source_image_id = r.source_image_id)
), per_image AS (
  SELECT s.id, s.status AS source_status, cur.n,
    (SELECT count(*) FROM generate_series(0, cur.n - 1) gs(p)
      WHERE NOT EXISTS (SELECT 1 FROM recognized_boards b
         WHERE b.game_id = s.game_id AND b.source_image_id = s.id AND b.position_index = gs.p)) AS absent,
    (SELECT count(*) FROM recognized_boards b
      WHERE b.game_id = s.game_id AND b.source_image_id = s.id AND b.position_index < cur.n
        AND b.completeness_status = 'pending_partial') AS partial,
    (SELECT count(*) FROM recognized_boards b
      WHERE b.game_id = s.game_id AND b.source_image_id = s.id AND b.position_index < cur.n
        AND b.completeness_status = 'complete'
        AND b.approved_geometry_revision IS DISTINCT FROM b.geometry_revision
        AND NOT EXISTS (SELECT 1 FROM image_source_geometry_revisions pr
                        WHERE pr.game_id = b.game_id AND pr.id = b.source_geometry_revision_id
                          AND pr.status = 'accepted')) AS uncertain,
    (SELECT count(*) FROM image_board_geometry_pending g
      WHERE g.game_id = s.game_id AND g.source_image_id = s.id AND g.status = 'pending'
        AND g.position_index < cur.n
        AND NOT EXISTS (SELECT 1 FROM recognized_boards b
           WHERE b.game_id = g.game_id AND b.source_image_id = g.source_image_id
             AND b.position_index = g.position_index)) AS deferred
  FROM source_images s LEFT JOIN cur ON cur.source_image_id = s.id
  WHERE s.game_id = :g
)
SELECT CASE WHEN n IS NULL THEN 'no_source_geometry' WHEN absent > 0 THEN 'incomplete_missing'
            WHEN partial > 0 THEN 'incomplete_partial' WHEN uncertain > 0 THEN 'incomplete_uncertain'
            ELSE 'complete' END AS image_state,
       source_status, count(*) AS images, sum(absent - deferred) AS missing_pos,
       sum(deferred) AS deferred_pos, sum(partial) AS partial_pos,
       sum(uncertain) AS uncertain_pos, sum(n) AS expected_pos
FROM per_image GROUP BY 1,2 ORDER BY 1,2;
```

Wynik zapytania kontrolnego (12 s):

| image_state | source_status | zdjęcia | missing | deferred | partial | uncertain | oczekiwane |
|---|---|---|---|---|---|---|---|
| complete | waiting_for_review | 56 413 | 0 | 0 | 0 | 0 | 507 713 |
| incomplete_missing | processing | 91 | 819 | 0 | 0 | 0 | 819 |
| incomplete_missing | waiting_for_review | 3 | 23 | 0 | 0 | 0 | 27 |
| incomplete_partial | waiting_for_review | 60 | 0 | 0 | 108 | 24 | 540 |
| incomplete_uncertain | completed | 161 | 0 | 0 | 0 | 1 254 | 1 449 |
| incomplete_uncertain | waiting_for_review | 76 | 0 | 0 | 0 | 425 | 684 |
| no_source_geometry | processing | 8 | – | – | – | – | – |

Wynik repozytorium `completeness_report` (wywołane z krótkiego skryptu w
transakcji `SET TRANSACTION READ ONLY`) oraz przez HTTP (`TestClient` z
własną zależnością w transakcji `READ ONLY`), ta sama chwila:

- zdjęcia: 56 812 łącznie, 56 413 kompletnych, 399 niekompletnych: 94
  `incomplete_missing`, 60 `incomplete_partial`, 237 `incomplete_uncertain`, 8
  `no_source_geometry`; rozbicie po statusie zdjęcia identyczne z tabelą
  (91 + 3, 60, 161 + 76, 8 `processing`);
- pozycje: 511 232 oczekiwane = 508 579 ok + 1 703 uncertain (24 + 1 254 +
  425) + 108 partial + 842 missing (819 + 23) + 0 deferred. Zgodne z kontrolą
  co do jednej pozycji; suma pozycji niepoprawnych z przejścia po wszystkich
  4 stronach listy (399 zdjęć) też równa się raportowi.
- Liczby zmieniły się względem wartości z opisu zadania (56 816 zdjęć, 4
  otwarte wiersze odroczone, 1 729 niepotwierdzonych): teraz 56 812 zdjęć, 0
  wierszy odroczonych `pending` (20 567 `resolved`), 1 703 niepotwierdzonych
  plansz. Rozbicie plansz według rewizji, na którą wskazują (510 390 plansz):
  370 040 automatycznych `accepted` bez zatwierdzenia, 138 186 zatwierdzonych
  (wszystkie na rewizjach `accepted`), 461 ręcznych `accepted` bez
  zatwierdzenia, 1 703 automatyczne `needs_review` bez zatwierdzenia. Stan
  `deferred` nie ma więc dziś żadnej pozycji; pokrywa go test PostgreSQL.
- Pozostałe wyniki: import `107a752a`: 3 104 zdjęcia, 3 081 kompletnych, 23
  niekompletne (19 niepotwierdzonych, 4 bez geometrii źródła); import
  `7d10ae0a`: 1 160 zdjęć, 998 kompletnych, 162 niepotwierdzone; import cudzej
  gry → 404 `IMAGE_GEOMETRY_COMPLETENESS_IMPORT_NOT_FOUND`. Wszystkie 3 519
  pozycji zdjęć niekompletnych mają czworokąt. 99 zdjęć nie ma żadnej planszy,
  a więc `previewReviewItemId = null`: 91 `incomplete_missing` w `processing` i
  8 `no_source_geometry` (to ta sama liczba 99 co w opisie zadania).

Czasy (baza deweloperska, jedna instancja PostgreSQL, bez ograniczania
cache):

- raport całej gry: 2,5–3,1 s przy ciepłym cache, 7,4–8,1 s przy zimnym
  (pierwsze wywołanie); raport jednego importu 0,14 s;
- strona listy (25–100 zdjęć) całej gry: ok. 2,5 s (klasyfikacja zdjęć jest
  liczona przy każdej stronie), przejście wszystkich 4 stron po 100 zdjęć:
  9,7 s; strona listy jednego importu: 0,29 s;
- sygnał niskiej jakości, `EXPLAIN (ANALYZE, BUFFERS)` (progi 0,80 i 5 pól):
  cała gra (7,5 mln komórek): `Parallel Seq Scan` po partycji komórek, 822 tys.
  stron, wykonanie 1,2–1,4 s przy ciepłym cache (5,0 s przez Pythona przy
  zimnym), 43 plansze; jeden import (`107a752a`, 418 500 komórek): `Parallel
  Index Scan` po `(game_id, import_job_id)`, 0,72–0,77 s (2,6 s zimno), 4
  plansze. Oba zakresy mieszczą się w progu 10 s, więc sygnał jest dostępny dla
  całej gry; limit 10 s i jawny błąd zostają jako zabezpieczenie.

### Orchestrator closure (2026-10-02)

- Commit zadania: `v1.7.136` / `0bcbff63` na `feat/grid-engine-v3`. Po nim
  `v1.7.137` / `a6426f3f` scala gałąź integracyjną (migracja `0138`,
  TASK-0784, TASK-0797) i przenumerowuje decyzję bramki kompletności z D-479
  na D-484, bo D-479 zajął równoległy tor. Po scaleniu: 64 testy domeny i API
  oraz 16 testów PG przechodzą, `openapi:check` kończy się kodem 0.
- Odbiór w przeglądarce (Admin z worktree `127.0.0.1:3020`, API
  `127.0.0.1:8020`, baza deweloperska, tylko odczyt): sekcja „Kompletność
  siatek zdjęć” pokazuje 56 812 zdjęć i 399 niekompletnych, podział stanów,
  filtry, listę z numerowanymi siatkami oraz zdjęcie pod siatkami po
  kliknięciu „Pokaż zdjęcie pod siatkami”; konsola bez błędów. Kryterium
  panelu zaliczone z ograniczeniem: 99 zdjęć bez żadnej planszy nie ma
  podglądu pliku (pokazują same siatki albo komunikat).
- `ruff.exe` skopiowany do `.venv` worktree; `python -m ruff check` działa i
  zgłasza wyłącznie wcześniejszy E501 w nietkniętym
  `services/worker/tests/test_page_geometry_preflight.py:345`.

### Not completed
- Kryterium „Panel importu pokazuje licznik … podgląd całego zdjęcia z siatkami”
  nie jest zaliczone w całości: (1) sekcja nie była obejrzana w przeglądarce
  (zakaz uruchamiania serwerów deweloperskich) — zweryfikowane są typy, lint,
  testy stanu i kontraktu; (2) żaden istniejący endpoint zasobu źródłowego nie
  przyjmuje `source_image_id` (`getOperationalImageReviewSourceAsset` wymaga
  elementu review, `getImageGridReviewSourceAsset` i
  `getPendingBoardCellGeometrySource` odpowiednio elementu review i wiersza
  odroczonego), więc zdjęcie bez żadnej rozpoznanej planszy (w danych: 99
  zdjęć — 91 `incomplete_missing` w `processing` i 8 `no_source_geometry`) nie
  ma podglądu pliku; pokazuje wyłącznie siatki z bieżącej rewizji (przerywane, na ciemnym
  tle) i komunikat. Nie dodałem równoległego serwowania plików zgodnie z
  zakresem; wymaga to decyzji (patrz niżej).
- Linku do narzędzi korekty nie zbudowano: panel Admina nie ma tras ani
  parametrów, a korekty siatek są w Reviewerze.
- `npm run python:lint` i pełny `npm run python:typecheck` nie przechodzą w
  worktree z powodów środowiskowych opisanych wyżej (cienki venv), nie przez
  zmiany tego zadania.

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md` — nowa sekcja „Kompletność siatek
  zdjęć” z definicjami, zachowaniem panelu i sygnałem jakości.
- `ai_docs/architecture/API_CONTRACT.md` — trzy endpointy, kształt odpowiedzi,
  kody błędów, limity i limit czasu sygnału jakości.
- `CURRENT_STATE.md`, `DECISION_LOG.md` i przeniesienie zadania zostawiam
  orkiestratorowi (zgodnie z poleceniem). Zadanie nie zmienia modelu domenowego
  ani architektury, więc nowy wpis w `DECISION_LOG.md` nie jest wymagany.

### Recommended next task

- TASK-0807 (bramka w pipeline) według planu etapu V3-0. Wejścia z tego zadania:
  1 703 niepotwierdzone plansze na 237 zdjęciach i 842 brakujące pozycje na 94
  zdjęciach to dzisiejsza kolejka siatek; decyzji wymaga, czy 1 703 plansz
  wskazujących starszą rewizję `needs_review` przy nowszej ręcznej `accepted`
  rewizji zdjęcia (`system:legacy-board-conversion-v1`, 240 zdjęć) ma być
  przepięte na nową rewizję, czy ma zostać w kolejce jako niepotwierdzone.
- Do rozstrzygnięcia przy tym lub osobnym zadaniu: endpoint zasobu źródłowego
  kluczowany `source_image_id` (powtarza istniejące sprawdzanie ścieżki i
  checksumy), żeby zdjęcia bez planszy miały podgląd.
