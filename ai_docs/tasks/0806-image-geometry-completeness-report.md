---
title: TASK-0806 — raport kompletności geometrii zdjęć i lista zdjęć niekompletnych
status: todo
last_updated: 2026-10-01
---

# TASK-0806 — raport kompletności geometrii zdjęć i lista zdjęć niekompletnych

## Status

`todo`

## Goal

Admin pokazuje dla gry i dla pojedynczego importu, ile zdjęć źródłowych ma
komplet poprawnych siatek, a ile nie, oraz stronicowaną listę zdjęć
niekompletnych z podglądem całego zdjęcia i naniesionymi siatkami — bez
żadnego zapisu do bazy.

## Context

D-479: jednostką geometrii jest zdjęcie. Dotąd pipeline traktował każdą
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
- `ai_docs/process/DECISION_LOG.md` (D-479, D-449, D-462)
- `ai_docs/requirements/IMAGE_INGESTION.md` (sekcja „Kompletność geometrii
  zdjęcia — D-479” oraz opis `image_board_geometry_pending`)
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

- [ ] `GET` raportu zwraca dla gry (i opcjonalnie jednego importu) liczniki:
      zdjęcia łącznie, kompletne, niekompletne w podziale na stany zdjęcia,
      oraz liczbę brakujących plansz w podziale na powód.
- [ ] `GET` listy zwraca stronicowane zdjęcia niekompletne z: identyfikatorem
      zdjęcia i importu, ścieżką względną, zakresem numerów sekwencji,
      liczbą oczekiwanych plansz i stanem każdej oczekiwanej pozycji
      (pozycja, numer sekwencji, stan, kod powodu).
- [ ] Liczniki na bazie deweloperskiej zgadzają się z zapytaniem kontrolnym
      SQL wykonanym w tej samej chwili (zapytanie i wynik w `Outcome`).
- [ ] Panel importu pokazuje licznik zdjęć niekompletnych dla gry i dla
      wybranego importu; lista pokazuje podgląd całego zdjęcia z siatkami
      plansz, które siatkę mają, i wyróżnia pozycje bez siatki.
- [ ] Sygnał niskiej jakości symboli działa jako osobne żądanie z jawnym
      progiem i nie spowalnia raportu podstawowego.
- [ ] Zadanie nie wykonuje żadnego `INSERT`/`UPDATE`/`DELETE`; test PG na
      bazie `*_test` pokrywa wszystkie stany planszy i zdjęcia.
- [ ] OpenAPI, klient, wrapper i test żądania zmienione razem;
      `npm run openapi:check` przechodzi.
- [ ] Osobny commit, `Outcome`, wpis w `CURRENT_STATE.md`.

## Technical notes

### Definicje (źródło prawdy: D-479)

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

Wypełnia agent po pracy.

### Changed

- Do uzupełnienia po wykonaniu.

### Verification results

- Do uzupełnienia po wykonaniu.

### Not completed

- Do uzupełnienia po wykonaniu.

### Documentation updates

- Do uzupełnienia po wykonaniu.

### Recommended next task

- Do uzupełnienia po wykonaniu.
