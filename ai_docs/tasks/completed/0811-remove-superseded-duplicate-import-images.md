---
title: TASK-0811 — usunięcie martwych zdjęć zduplikowanego importu 7d10ae0a
status: done
last_updated: 2026-10-02
---

# TASK-0811 — usunięcie martwych zdjęć zduplikowanego importu 7d10ae0a

## Status

`done`

## Goal

Narzędzie z podglądem i wykonaniem usuwa z magazynu gry wyłącznie te zdjęcia
wskazanego importu, które są w całości zastąpione nowszym importem i nie
niosą żadnej pracy człowieka ani żywych danych; zdjęcia będące jedynym
żywym źródłem numerów sekwencji zostają nietknięte.

## Context

Polecenie operatora z 2026-10-02: „usuń duplikat importu, jeśli jest to
bezpieczne”. Inwentaryzacja bazy deweloperskiej (tylko `SELECT`, 2026-10-02)
importu `7d10ae0a-60ee-404c-a8b6-38fb3c416ba3` (gra 777,
`bfc4f949-5c14-4850-b02a-db99610bcfa5`):

- 1 160 zdjęć, 10 440 plansz: 10 389 `rejected` (elementy review
  `superseded`, powód `pending_sequence_replaced_by_newer_import`) i **51
  żywych** (`pending_review`, elementy `pending`).
- **Usunięcie całego importu nie jest bezpieczne.** 51 żywych plansz leży na
  6 zdjęciach, których bliźniak w imporcie `f4ef3449` nie przeszedł pipeline
  (`IMAGE_STAGE_EXECUTION_FAILED`); 51 numerów sekwencji (zakresy od
  122077, 126460, 127451, 127640, 127801, 127990) ma żywą planszę wyłącznie
  w tym imporcie. Te zdjęcia mają 765 komórek, 376 zdarzeń weryfikacji
  symboli, 26 zatwierdzonych siatek i 51 dokumentów wyszukiwarki.
- Pozostałe 1 154 zdjęcia mają wszystkie plansze `rejected`; każdy ich numer
  sekwencji ma żywy element review w innym imporcie.
- Tabele z wierszami importu: `source_images` 1 160,
  `image_source_geometry_revisions` 1 325, `recognized_boards` 10 440,
  `board_render_manifests` 10 440, `image_review_items` 10 440,
  `image_review_queue_items` 10 440, `image_review_queue_states` 1,
  `image_review_resolution_events` 10 389, `image_board_geometry_pending`
  205 (`resolved`), `image_board_geometry_revisions` 427,
  `image_board_geometry_review_events` 27,
  `image_symbol_prediction_revisions` 62, `image_import_job_files` 1 160,
  oraz w `public`: 1 160 `image_file_executions` z wynikami etapów i
  manifestami terminalnymi (żadne wykonanie nie jest współdzielone z innym
  importem).
- Zero wierszy: kanon sekwencji, kohorty, eksporty, sesje Reviewera,
  staging layoutów, alternatywy sekwencji.
- Pliki źródłowe są współdzielone (1 160 tych samych `relative_path` w innych
  importach) — **plików nie wolno usuwać**.
- W repo nie istnieje mechanizm usuwania importu ani zdjęcia (tylko
  usunięcie całej gry).

## Dependencies / entry conditions

- Gałąź `feat/grid-engine-v3`, head Alembic `0139`; klasyfikacja
  `superseded` z TASK-0808 (`domain/image_geometry_completeness.py`).
- Zgoda operatora na usunięcie warunkowa: „jeśli bezpieczne”. Wykonawca
  zadania **nie** uruchamia trybu wykonania na bazie deweloperskiej; robi to
  orkiestrator po przeglądzie podglądu.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Nieodwracalne usuwanie z kilkunastu
tabel powiązanych kluczami `RESTRICT`; błąd oznacza utratę danych gry 777.
Audyt zawieszony decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md` (operacje destrukcyjne, trwałe workflowy)
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md` (role, RLS, kolejność
  usuwania dzieci przed rodzicami, lifecycle delete)
- `ai_docs/tasks/completed/0808-geometry-completeness-superseded-and-failed-imports.md`
- `ai_docs/guides/DATABASE_MAINTENANCE.md`

## Scope

- Skrypt `scripts/remove_superseded_import_images.py` z wpisem npm
  `images:remove-superseded-import-images`, parametry `--game-id`,
  `--import-job-id`, tryby `--preview` (domyślny) i `--execute`.
- Logika w repozytorium/storage, testowalna na bazie `*_test`.
- Test PG.
- Wpis w `ai_docs/guides/DATABASE_MAINTENANCE.md`.

## Out of scope

- Usuwanie plików z dysku i jakichkolwiek artefaktów.
- Usuwanie joba importu, żywych zdjęć, zdjęć innych importów, nieudanych
  zdjęć innych importów (`import_failed` / `superseded` po SHA w innych
  jobach).
- Endpoint API i UI.

## Acceptance criteria

- [x] Zdjęcie kwalifikuje się do usunięcia tylko wtedy, gdy spełnia
      **wszystkie** warunki z sekcji „Kwalifikacja”; każde zdjęcie
      niekwalifikujące się jest w raporcie z powodem.
- [x] Podgląd nie zapisuje niczego i podaje liczbę wierszy do usunięcia per
      tabela oraz listę zdjęć zachowanych z powodem.
- [x] Wykonanie: kopia usuwanych wierszy do pliku przed usunięciem, jedna
      transakcja, kontrola niezmienników przed `COMMIT`, raport.
- [x] Test PG: import z mieszanką zdjęć martwych, żywych, mieszanych i z
      pracą człowieka → usunięte tylko martwe; drugi import i druga gra bez
      zmian; ponowne uruchomienie nie usuwa nic (idempotencja); naruszenie
      niezmiennika wycofuje transakcję.
- [x] Brak zapisu do bazy deweloperskiej przez wykonawcę.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

### Kwalifikacja zdjęcia (wszystkie warunki)

1. należy do wskazanej gry i importu;
2. każda jego plansza ma `status = 'rejected'`, a każdy element review tych
   plansz ma `status = 'superseded'`;
3. każdy numer sekwencji tych elementów ma żywy element review
   (`pending`/`accepted`/`corrected`) na zdjęciu innego importu tej gry;
4. nie ma wierszy w: `image_symbol_review_cells`,
   `image_symbol_review_events`, `image_symbol_review_bulk_targets`,
   `symbol_reference_images`, `verified_training_cohort_items`,
   `verified_training_cohort_cells`, `image_sequence_canonical`,
   `image_sequence_alternatives`, `image_sequence_source_override_events`,
   `image_board_search_candidates`, `image_board_search_fast_documents`,
   `image_layout_staging_rows`;
5. żadna plansza nie ma zatwierdzonej geometrii
   (`approved_geometry_revision IS NOT NULL`) ani zdarzenia
   `image_board_geometry_review_events`, żadna rewizja geometrii planszy ani
   źródła nie została utworzona przez aktora innego niż `system:%`;
6. żaden wiersz innego zdjęcia, importu ani tabeli spoza listy usuwania nie
   wskazuje na jego wiersze (sprawdź katalog `pg_constraint` dla wszystkich
   kluczy obcych do usuwanych tabel oraz odwołania w JSON:
   `ownerReviewItemId` w `image_review_resolution_events`);
7. nie ma stanu `geometry_exception`.

Zdjęcie niespełniające któregokolwiek warunku zostaje w całości (nie usuwa
się części plansz zdjęcia).

### Usuwanie

Kolejność dzieci przed rodzicami wyznacz z kluczy obcych (jak lifecycle
delete w `GAME_DATA_V2_OWNERSHIP.md`), bez `CASCADE` w poleceniach i bez
wyłączania kluczy. Zakres dla zakwalifikowanych zdjęć: kolejka review i jej
elementy, zdarzenia rozstrzygnięć, odroczona geometria, rewizje geometrii
plansz, rewizje predykcji, manifesty renderu, elementy review, plansze,
rewizje geometrii źródła, zdjęcia, pliki joba importu, a w `public` wyniki
etapów, manifesty terminalne i wykonania plików — te trzy ostatnie tylko
gdy po usunięciu żaden wiersz żadnej gry nie odwołuje się do
`file_execution_key` (sprawdź wszystkie gry, wzorzec
`load_pipeline_execution_references` / `CrossGameOwnerSession`).
Liczniki projekcji i stany (`image_review_queue_states`,
`image_symbol_review_states`, stan projekcji wyszukiwarki, rollout) —
ustal z kodu, czy przechowują liczby zależne od usuwanych wierszy; jeżeli
tak, przelicz je istniejącym mechanizmem albo zatrzymaj się i zgłoś.

Rola: ustal z kodu, czy rola aplikacyjna z wiązaniem gry może usuwać te
wiersze (RLS), czy potrzebna jest sesja właściciela; trzymaj się
istniejących wzorców i udokumentuj wybór. Blokada: wyłączna blokada
advisory gry używana przez operacje lifecycle, żeby nie biec równolegle z
importem.

### Kopia i niezmienniki

Przed usunięciem zapisz usuwane wiersze każdej tabeli do
`artifacts/data/exports/remove-superseded-import-images/<gra>/<znacznik>/`
(JSON Lines per tabela + manifest z licznikami i sumami SHA-256), w tej
samej migawce (`REPEATABLE READ`). Niezmienniki sprawdzane w transakcji
przed `COMMIT`; naruszenie → `ROLLBACK` i błąd:

- liczba żywych plansz, żywych elementów review, komórek, zdarzeń symboli,
  dokumentów wyszukiwarki i kanonu gry bez zmian;
- zbiór numerów sekwencji z żywym elementem review bez zmian;
- inne importy: liczba zdjęć, plansz i elementów bez zmian;
- liczba usuniętych wierszy per tabela równa podglądowi;
- raport kompletności gry: `complete`, `incomplete_*` bez zmian, `superseded`
  mniejsze dokładnie o liczbę usuniętych zdjęć.

### Niedozwolone skróty

- Żadnego `TRUNCATE`, `CASCADE`, `session_replication_role`, wyłączania
  triggerów ani RLS.
- Nie usuwaj plików.
- Nie usuwaj zdjęcia częściowo.

## Expected files

- Nowe (proponowane): `scripts/remove_superseded_import_images.py`,
  `services/api/src/game_predictor_api/storage/superseded_import_image_removal_repository.py`,
  `services/api/tests/integration/test_superseded_import_image_removal.py`.
- Istniejące: `package.json`, `ai_docs/guides/DATABASE_MAINTENANCE.md`.

## Test cases

- Wymienione w kryteriach; dodatkowo: wykonanie współdzielone przez dwa
  importy nie jest usuwane z `public`; zdjęcie z planszą `rejected`, której
  numer nie ma żywego następcy, zostaje; zdjęcie z rewizją geometrii
  autorstwa człowieka zostaje.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_superseded_import_image_removal.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check services/api scripts
```

Limit 300 s dla testu PG; testy PG pojedynczo. Testy są planowane.

## Risks / open questions

- Operacja jest nieodwracalna poza odtworzeniem z kopii JSON Lines; kopia
  nie jest automatycznym mechanizmem przywracania.
- Oczekiwany wynik na bazie deweloperskiej: do 1 154 zdjęć i 10 386 plansz;
  każde odstępstwo w dół jest dopuszczalne (zdjęcia zachowane z powodem).

## Outcome

Status: `done` — narzędzie, test PG i dokumentacja są gotowe; z kryteriów nie
jest zaliczony tylko osobny commit i wpis w `CURRENT_STATE.md` (należą do
orkiestratora). **Wynik na bazie deweloperskiej: 0 z 1 160 zdjęć importu
`7d10ae0a` kwalifikuje się do usunięcia** (szczegóły niżej) — usunięcie
duplikatu tym narzędziem nie jest dziś możliwe bez naruszenia reguły 6.

### Changed

- Nowy `services/api/src/game_predictor_api/storage/superseded_import_image_removal_repository.py`:
  `build_removal_plan` (kwalifikacja), `plan_report`, `collect_metrics`,
  `invariant_violations`, `write_backup`, `load_foreign_keys`, `delete_order`
  i `SupersededImportImageRemovalRepository` (`preview`, `execute`).
- Nowy `scripts/remove_superseded_import_images.py` (`--game-id`,
  `--import-job-id`, `--preview` domyślnie, `--execute` wymaga
  `--confirm-plan-sha256` z podglądu, `--report-dir`); kody wyjścia 0/2/3.
- `package.json`: `images:remove-superseded-import-images`.
- Nowy test PG `services/api/tests/integration/test_superseded_import_image_removal.py`
  (6 testów, własna baza `gp_task0811_<hex>_test`).
- Kwalifikacja (zdjęcie zostaje w całości przy dowolnym powodzie; kody w
  raporcie): reguły 1–7 z sekcji „Kwalifikacja”, przy czym reguła 3 obejmuje
  także oczekiwane pozycje najnowszej rewizji źródła i wymaga stanu
  `superseded` w raporcie kompletności (D-484, `incomplete_images`), reguła
  4 sprawdza także `image_sequence_alternatives` po (import, suma pliku) albo
  numerze sekwencji i `image_sequence_source_override_events` po numerze
  sekwencji, reguła 5 traktuje brak aktora rozstrzygnięcia elementu
  `superseded` jako pracę nie-systemową, a otwarty wiersz
  `image_board_geometry_pending` jako żywe dane; dodatkowo plik joba importu
  musi być `waiting_for_review`/`completed` i nie może być współdzielony z
  innym zdjęciem importu. Reguła 6: wszystkie klucze obce z `pg_constraint`
  (`conparentid = 0`, z mapowaniem partycji na korzeń) do tabel usuwanych;
  wiersz spoza zbioru usuwania (inna tabela albo wiersz innego zdjęcia)
  zatrzymuje zdjęcie; pętla do punktu stałego (zatrzymanie jednego zdjęcia
  może zatrzymać inne). Plus `ownerReviewItemId` w `resolved_value`
  elementów review i zdarzeń rozstrzygnięć oraz kolumny bez FK
  `image_symbol_review_states.last_review_item_id`/`count_rebuild_cursor`,
  `layouts.source_board_id`.
- Usuwanie: kolejność dzieci przed rodzicami z tych samych kluczy obcych
  (TopologicalSorter); bez `CASCADE`; elementy kolejki i stan kolejki
  utrzymuje istniejący trigger `project_image_review_queue_delete_v1` (jawne
  usunięcie elementu kolejki przed elementem review wywołałoby błąd
  triggera). Wykonania w `public` usuwane tylko, gdy żaden wiersz żadnej gry
  (kontrola międzygrowa w tej samej transakcji) nie wskazuje
  `file_execution_key`. `image_symbol_review_states` i stan projekcji
  wyszukiwarki nie zależą od usuwanych wierszy (zakwalifikowane zdjęcie nie
  ma komórek ani dokumentów; `skipped_review_item_count` to raport ostatniej
  przebudowy); `image_geometry_rollout_states.last_source_image_id` jest FK,
  więc wskazane zdjęcie zostaje.
- Rola: połączenie właściciela schematu (silnik utrzymaniowy), z kontrolą
  `rolsuper OR rolbypassrls` (odmowa `REMOVAL_OWNER_SESSION_REQUIRED`),
  wiązanie gry przez `GameStorageRouter` (READ w podglądzie, WRITE w
  wykonaniu). Blokada: `pg_try_advisory_lock(hashtextextended(game_id, 519))`
  na poziomie sesji przed migawką `REPEATABLE READ`, zwalniana po
  `COMMIT`/`ROLLBACK`.

### Verification results

- `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_superseded_import_image_removal.py -q -p no:cacheprovider`
  — 6 passed (ok. 35 s). Świat testu: gra A z importem starszym, docelowym
  i następcą, gra B. W imporcie docelowym: 3 martwe zdjęcia (jedno z
  manifestami renderu, systemową rewizją geometrii planszy, zamkniętym
  wierszem odroczonym i rewizją predykcji), żywe, mieszane, z rewizją
  geometrii `reviewer-operator`, bez następcy jednego numeru, wskazywane
  przez `ownerReviewItemId` elementu starszego importu, wskazywane przez FK
  `image_geometry_rollout_states` (tylko z katalogu), z alternatywą
  sekwencji. Wykonanie wspólne z importem następcy i z grą B zostaje w
  `public`, niewspólne znika. Testy: podgląd bez zapisu i z powodami;
  wykonanie usuwa tylko martwe, inne importy, gra B, statusy jobów bez
  zmian, stan kolejki mniejszy o 9 elementów `superseded`, kopia JSONL zgodna
  z manifestem (liczby, SHA-256); ponowne uruchomienie nic nie usuwa;
  naruszenie niezmiennika (hak zmienia żywy element innego importu) wycofuje
  wszystko, a ponowna próba po zwolnieniu blokady przechodzi; zmieniony
  `planSha256` → odmowa bez zapisu; skrypt: podgląd → raport → odmowa bez
  potwierdzenia / ze złym skrótem (kod 2) → wykonanie z `planSha256` (kod 0,
  `report.json`, `manifest.json`).
- `.\.venv\Scripts\python.exe -m ruff check services/api scripts` — czysto;
  `ruff format` na nowych plikach.
- `mypy --strict` (z `MYPYPATH='services/worker/src;services/api/src'`) na
  module i skrypcie: 0 błędów w nich (27 znanych błędów w 6 niezwiązanych
  plikach).
- Podgląd na bazie deweloperskiej (wykonawca uruchomił `--preview`: jedna
  transakcja `REPEATABLE READ READ ONLY`, sprawdzona `SHOW
  transaction_read_only`; zapisany tylko raport
  `artifacts/data/exports/remove-superseded-import-images/bfc4f949-5c14-4850-b02a-db99610bcfa5/20261002T073551Z-preview.json`
  w worktree; 31 s): 1 160 zdjęć, **0 kwalifikujących się**, blokery brak,
  `planSha256` `1dde5081c7bebdfbca0ff63e792a2320256b5a78dc7483e5802e607f2a9f1fc5`.
  Powody: 993 zdjęcia tylko `PROTECTED_ROWS:image_symbol_review_events`; 161
  tego samego plus `NON_SYSTEM_BOARD_GEOMETRY_REVISION`; 6 zdjęć z żywymi
  planszami (żywe elementy, komórki, dokumenty wyszukiwarki, zdarzenia
  symboli, w tym 3 z zatwierdzoną geometrią lub zdarzeniem geometrii).
- Przyczyna (osobne `SELECT`, tylko odczyt): 152 865 zdarzeń
  `image_symbol_review_events` (`system:image-pipeline`, 10 191 elementów
  review importu `f4ef3449`, 2026-09-14) ma `previous_source_geometry_revision_id`
  wskazujące 1 158 różnych rewizji geometrii źródła zdjęć importu `7d10ae0a`
  (FK `RESTRICT`). Diagnostyka tylko do odczytu tą samą logiką (`_reference_blocks`
  dla 993 zdjęć) potwierdza, że jedyną przeszkodą tych 993 zdjęć jest FK
  `image_symbol_review_events(game_id, previous_source_geometry_revision_id)`.
  Hipotetycznie (gdyby tej referencji nie było) usunięto by: 993 zdjęcia, 993
  rewizje źródła, 8 937 plansz, 8 937 elementów review, 8 937 manifestów
  renderu, 8 937 zdarzeń rozstrzygnięć, 8 937 elementów kolejki, 993 pliki
  joba, w `public` 993 wykonania, 2 979 wyników etapów, 993 manifesty
  terminalne.

### Orchestrator closure (2026-10-02)

- Decyzja: usunięcie **nie zostało wykonane**. Podgląd na bazie
  deweloperskiej kwalifikuje 0 z 1 160 zdjęć: rewizje geometrii źródła tego
  importu są wskazywane przez 152 865 zdarzeń weryfikacji symboli importu
  `f4ef3449` (`previous_source_geometry_revision_id`, klucz `RESTRICT`),
  czyli przez historię żywych komórek innego importu. Warunek operatora
  („jeśli bezpieczne”) nie jest spełniony.
- Narzędzie zostaje w repo jako bezpieczny mechanizm z podglądem; tryb
  wykonania nie był uruchamiany.
- Usunięcie wymagałoby osobnej decyzji o historii zdarzeń `f4ef3449` (np.
  przepięcie `previous_source_geometry_revision_id` na bliźniacze rewizje) —
  to zmiana zapisu audytowego, nie porządek.

### Not completed

- `--execute` nie był uruchamiany na bazie deweloperskiej (zgodnie z
  zadaniem); przy obecnych danych usunąłby 0 zdjęć.
- Brak testu PG z prawdziwym zdarzeniem `image_symbol_review_events`
  wskazującym rewizję zdjęcia (seeding komórki i zdarzenia jest ciężki);
  mechanizm FK z katalogu pokrywa test z `image_geometry_rollout_states`, a
  przypadek symboli potwierdza diagnostyka na bazie deweloperskiej.
- `CURRENT_STATE.md`, `DECISION_LOG.md`, commit i przeniesienie zadania —
  orkiestrator.

### Documentation updates

- `ai_docs/guides/DATABASE_MAINTENANCE.md` — sekcja 2.8: kwalifikacja,
  zakres i kolejność usuwania, rola, blokada, polecenia podglądu i wykonania,
  kopia, niezmienniki, wynik podglądu na bazie deweloperskiej.

### Recommended next task

- Decyzja operatora/architekta: czy zdarzenia weryfikacji symboli importu
  `f4ef3449` mogą zachować historię bez FK do rewizji geometrii zdjęć
  `7d10ae0a` (np. przepięcie `previous_source_geometry_revision_id` na
  bliźniaczą rewizję `f4ef3449` albo osobna decyzja o archiwizacji tej
  historii). Bez takiej decyzji duplikat zostaje; wymaga osobnego zadania i
  wpisu w `DECISION_LOG.md`, bo zmienia audyt pracy symboli.
