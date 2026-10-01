---
title: TASK-0808 — raport kompletności: pozycje zastąpione, nieudane importy, podgląd po zdjęciu
status: todo
last_updated: 2026-10-02
---

# TASK-0808 — raport kompletności: pozycje zastąpione, nieudane importy, podgląd po zdjęciu

## Status

`todo`

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

- [ ] Plansza `rejected` nie liczy się jako plansza z siatką; pozycja bez
      żywej planszy, której numer sekwencji ma żywy element review na innym
      zdjęciu tej gry, ma stan `superseded` i nie czyni zdjęcia
      niekompletnym.
- [ ] Zdjęcie, którego wszystkie oczekiwane pozycje są `superseded`, ma stan
      `superseded` i nie wchodzi do liczby niekompletnych ani do listy
      domyślnej; ma własny licznik.
- [ ] Zdjęcie bez żadnej żywej planszy, którego plik importu ma
      `workflow_status = 'failed'`, ma stan `import_failed` z kodem błędu;
      gdy ten sam `checksum_sha256` ma w tej grze inne zdjęcie z żywymi
      planszami, stan to `superseded`.
- [ ] Liczniki na bazie deweloperskiej zgadzają się z niezależnym zapytaniem
      kontrolnym SQL z tej samej chwili (zapytanie i wynik w `Outcome`);
      raport całej gry nadal mieści się w kilku sekundach.
- [ ] `GET` pliku źródłowego po `source_image_id` zwraca obraz z tą samą
      walidacją ścieżki, korzenia i sumy kontrolnej co istniejący endpoint
      zasobu źródłowego; lista nie zależy już od `previewReviewItemId`.
- [ ] Test PG `*_test` pokrywa nowe stany, w tym zdjęcie mieszane (część
      pozycji `superseded`, reszta `ok` → `complete`) i drugą grę (numer
      sekwencji żywy tylko w innej grze nie daje `superseded`).
- [ ] Brak `INSERT`/`UPDATE`/`DELETE`; kontrakt pionem; `openapi:check`
      przechodzi.
- [ ] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

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
