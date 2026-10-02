---
title: Izolacja danych per gra i gotowość na nową grę (TASK-0809)
status: accepted
last_updated: 2026-10-02
---

# Izolacja danych per gra i gotowość na nową grę — TASK-0809

## Zakres i metoda

Wymaganie operatora z 2026-10-02: dane każdej gry osobno; aplikacja ma działać
prawidłowo od pierwszego importu po dodaniu pierwszej nowej gry. Kontrola nie
zmienia schematu, nie dodaje migracji i nie zapisuje do bazy deweloperskiej
(tylko `SELECT` w transakcji `default_transaction_read_only = on`).

Dowód składa się z dwóch części:

1. test PostgreSQL `services/api/tests/integration/test_per_game_isolation_new_game.py`
   na jednorazowej bazie `*_test` z prawdziwą rolą aplikacyjną typu LOGIN
   (`_application_role_database`: bez `SUPERUSER`/`BYPASSRLS`, bez własności
   obiektów), czyli z wymuszonym RLS jak w produkcji. Dwie gry: „duża”
   (utworzona pierwsza, cztery zaimportowane zdjęcia: trzy komplety 9/9 i jedno
   8/9, razem 35 plansz i 405 komórek) oraz „nowa” (utworzona potem tym samym
   lifecycle partycji, po migracji `0139`, dwa zdjęcia: komplet 9/9 i 8/9);
2. kontrola bazy deweloperskiej (rozmiary partycji, ocena tabel
   współdzielonych).

Plany zapytań (`EXPLAIN (VERBOSE, FORMAT JSON)`) dotyczą instrukcji SQL, które
repozytoria faktycznie wysłały do bazy. Test podpina się pod
`before_cursor_execute` silnika aplikacyjnego, zbiera instrukcje wykonane przez
prawdziwe wywołania repozytoriów, a potem planuje każdą (z jej parametrami) w
transakcji związanej z nową grą (`GameStorageRouter.bind`). Wersja `VERBOSE` jest
potrzebna tylko po to, żeby plan zawierał nazwę schematu relacji. Nazwy relacji
z planu porównuje się z partycjami obu gier odczytanymi z `pg_inherits`
(`FOR VALUES IN ('<uuid gry>')`), a nie z samej reguły nazewnictwa; osobna
asercja sprawdza zgodność obu źródeł.

## Wynik testów

`pytest services/api/tests/integration/test_per_game_isolation_new_game.py` z
`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`: 12 passed (≈31 s). Bez tej zmiennej
przechodzą 2 testy niewymagające PostgreSQL (strażnik własności tabel i test
czytnika planu), reszta jest pomijana.

| Obszar | Co sprawdzono | Wynik |
|---|---|---|
| Komplet partycji | 63 tabele klasy `game` manifestu v4 mają po jednej partycji nowej gry (`pg_inherits`, granica `FOR VALUES IN`), rozłączne z partycjami dużej gry; RLS włączone i wymuszone na wszystkich 63 rodzicach; `game_storage_table_manifest` = `GAME_TABLES`; receipt lifecycle `done` z 63 tabelami | zgodne |
| Lokalizacja | obie gry: `game_data_v2`, status `active`, zapis dostępny, manifest `game-data-v2-manifest-v4` | zgodne |
| Kolumny `0139` | partycja `source_images` nowej gry ma dokładnie te same kolumny (nazwa i typ) co rodzic, pięć kolumn `0139` z oczekiwanymi typami, te same trzy CHECK-i (zwalidowane) i oba indeksy częściowe jako dzieci indeksów rodzica | zgodne |
| Egzekwowanie CHECK-ów | UPDATE na partycji nowej gry łamiący każdy z trzech CHECK-ów jest odrzucany z nazwą ograniczenia | zgodne (uwaga: odstępstwo 2 poniżej) |
| Pierwszy import nowej gry | 9/9: `geometry_complete`, 9 plansz, 135 komórek bez duplikatów, 9 dokumentów z dowodami; 8/9: `geometry_incomplete`, 8 plansz, 0 komórek, 0 dowodów w wyszukiwarce (dokumenty sekwencji zostają bez dowodów, zgodnie z adaptacją 1 TASK-0807) | zgodne |
| Raport nowej gry | 2 zdjęcia, 1 kompletne, `gate`: 1 / 1 / 0 wyjątków, 8 plansz wstrzymanych; lista niekompletnych zawiera wyłącznie zdjęcie 8/9 nowej gry; `low_quality_boards` bez zdjęć dużej gry; import i plik źródłowy dużej gry odrzucone jako obce (`IMAGE_GEOMETRY_COMPLETENESS_IMPORT_NOT_FOUND`, `..._SOURCE_IMAGE_NOT_FOUND`); zapytania bez predykatu gry widzą tylko 2 zdjęcia, 17 plansz, 135 komórek nowej gry; sesja związana z dużą grą nie widzi zdjęć nowej | zgodne |
| Zapytania bez wiązania | ten sam SQL repozytorium wysłany bez wiązania gry: błąd `42P01` (niekwalifikowana tabela nie istnieje w `search_path`); kwalifikowana `game_data_v2.*`: `42501` `GAME_STORAGE_SCOPE_REQUIRED`; ORM bez zakresu: `42P01`; nigdy pusty wynik. Repozytoria raportu wiążą grę same, więc wywołane na sesji bez zakresu zwracają dane własnej gry | zgodne |

### Plany zapytań czterech ścieżek

Instrukcje zebrane z prawdziwych wywołań, po deduplikacji tekstu; INSERT-y są
pominięte (plan INSERT nazywa tylko rodzica, wybór partycji następuje w czasie
wykonania).

| Ścieżka | Wywołania | Instrukcje zaplanowane | Partycje nowej gry w planach | Partycje dużej gry |
|---|---|---|---|---|
| Raport kompletności | `completeness_report` (z importem i bez), `incomplete_images`, `low_quality_boards` | 15 | 7 | 0 |
| Przeliczenie stanu i bramka | `recompute_source_image_geometry_completeness` (zdjęcie 8/9 i 9/9), `withheld_review_item_ids` (zwraca 8 wstrzymanych plansz) | 7 | 7 | 0 |
| Materializacja komórek | `set_exception` (dopuszczenie 8/9: 8 plansz, 120 komórek) + `synchronize_after_geometry_admission`, w transakcji wycofanej | 29 (z 361 wykonanych) | 14 | 0 |
| Projekcja wyszukiwarki | `stale_review_item_ids`, `sync_review_items`, `rebuild_game` | 23 | 8 | 0 |

W każdym planie relacje schematu `game_data_v2` to wyłącznie partycje nowej gry;
poza nimi pojawiają się tylko tabele katalogu (`games`, `jobs`, `symbols`,
`game_storage_locations`). Żaden plan nie zawiera rodzica partycjonowanego,
kopii `public` tabeli gry ani partycji innej gry. Asercja nie jest pusta:
każda ścieżka dotyka partycji nowej gry (m.in. `source_images`,
`recognized_boards`, `image_symbol_review_cells`,
`image_board_search_candidates`, `image_board_search_fast_documents`), a test
czytnika planów (bez PostgreSQL) dowodzi, że partycja obcej gry, rodzic i kopia
`public` są wykrywane.

### Instrukcje bez jawnego predykatu `game_id`

Kilka instrukcji repozytoriów filtruje tylko po identyfikatorze wiersza
(`session.get`, UPDATE po kluczu głównym przy flush ORM, `DELETE ... WHERE
review_item_id = ...`; w zebranych ścieżkach 0, 2, 4 i 1 takich instrukcji
tabel gry, nie licząc odczytu `games` z katalogu). Ich izolację zapewnia wiązanie transakcji oraz
polityka RLS: dla roli aplikacyjnej plan takiej instrukcji nazywa dokładnie
jedną partycję (osobny test:
`SELECT count(*) FROM source_images WHERE id = :id` po `bind` → jedna partycja
nowej gry). Gdyby ta sama instrukcja szła rolą z `BYPASSRLS`/superużytkownika
bez wiązania, plan obejmuje partycje wszystkich gier (sprawdzone kontrolnie rolą
właściciela: 2 partycje przy dwóch grach). To nie jest przeciek w obecnym
układzie (runtime zawsze używa roli aplikacyjnej, `GAME_DATA_V2_OWNERSHIP.md`,
„Role bazy i egzekwowanie RLS”), ale oznacza, że izolacja tych instrukcji
zależy od roli i wiązania, a nie od samego tekstu SQL.

## Strażnik własności tabel

`test_game_data_v2_schema.py::test_manifest_is_exhaustive_disjoint_and_fail_closed`
gwarantuje, że każda tabela ORM jest sklasyfikowana (katalog, wspólna albo gra),
ale nie gwarantuje klasy tabel z wierszem per zdjęcie, plansza albo pozycja
review. Dodany test
`test_orm_tables_with_image_board_or_item_keys_are_game_owned` (bez PostgreSQL)
wymaga, żeby każda tabela ORM z kolumną `source_image_id`,
`recognized_board_id` albo `review_item_id` należała do `GAME_TABLES` manifestu
v4 i miała klasę `game`. Dziś spełnia to 21 tabel; test jest zabezpieczeniem
przed dodaniem takiej tabeli jako wspólnej (np. w planie V3).

## Baza deweloperska (tylko `SELECT`)

Head Alembic bazy: `0138` (migracja `0139` jeszcze nie zastosowana w momencie
kontroli, więc partycje deweloperskie nie mają kolumn `0139`; to właśnie robi
migracja na rodzicu, a test powyżej potwierdza, że lifecycle i dziedziczenie
dają je każdej partycji).

| Gra | Partycje | Rozmiar razem z indeksami i TOAST |
|---|---|---|
| `7` (777) | 63 | 34 GB (36 868 145 152 B) |
| `mums` | 63 | 6 856 kB |
| `mums-test-1` | 63 | 3 616 kB |

- 63 rodziców `game_data_v2` jest partycjonowanych, wszystkie z RLS włączonym i
  wymuszonym; w schemacie nie ma tabel niepartycjonowanych.
- Największe partycje gry 777 (szacunek wierszy z `reltuples`):
  `image_symbol_review_cells` ≈ 7,5 mln / 11 GB, `board_render_manifests`
  ≈ 510 tys. / 6,9 GB, `image_symbol_prediction_revisions` ≈ 784 tys. /
  6,7 GB, `image_symbol_review_events` ≈ 1,96 mln / 2,8 GB,
  `image_board_geometry_revisions` ≈ 136 tys. / 2,1 GB, `recognized_boards`
  ≈ 510 tys. / 1,4 GB. Odpowiedniki `mums`: `image_symbol_review_cells` 390
  wierszy / 2,1 MB.
- Wszystkie trzy gry mają lokalizację `game_data_v2`, `active`, generacja 2,
  manifest v4.

## Tabele współdzielone rosnące z liczbą zdjęć

| Tabela | Rozmiar łączny (heap / indeksy) | Szac. wierszy | Klucz | Kolumna gry |
|---|---|---|---|---|
| `image_file_executions` | 73 MB (52 MB / 21 MB) | 55 529 | PK `file_execution_key`, UNIQUE `(source_checksum_sha256, pipeline_fingerprint)`, indeks `(pipeline_fingerprint, status)` | brak |
| `image_pipeline_stage_results` | 399 MB (70 MB / 18 MB, reszta TOAST) | 170 819 | PK `(file_execution_key, stage)`, FK do execution | brak |
| `image_pipeline_terminal_manifests` | 143 MB (13 MB / 17 MB, reszta TOAST) | 56 710 | PK `id`, UNIQUE `(file_execution_key, manifest_checksum_sha256)`, indeks `(compacted_at, file_execution_key)` | brak |

Fakty z bazy i kodu:

- Klucz jest adresowany treścią (`file_execution_key` = hash sumy bajtów źródła i
  odcisku pipeline'u, D-079); tabele nie mają `game_id`, nie mają RLS i leżą w
  `public`. Powiązanie z grą istnieje wyłącznie przez tabele gry
  (`source_images.file_execution_key`, `image_import_job_files.file_execution_key`,
  FK `ON DELETE RESTRICT` z partycji gier do `public`).
- Próbka 2–5 % wierszy (tylko odczyt): ani `result_payload` etapów
  `discovery`/`normalization`/`board_detection`, ani `checkpoint_payload`, ani
  `manifest_payload` nie zawierają `gameId`, `game_id`, `symbolCode` ani ścieżek
  względnych. Po kompakcji (po 24 h, `DATA_MODEL.md`) w tabeli wyników zostają
  tylko trzy etapy (`discovery` 253 B, `normalization` 483 B, `board_detection`
  ≈ 4,8 kB średnio). Etapy późne (`board_crops`, `sequence_ocr`,
  `symbol_inference`), które zawierają kody symboli modelu gry, żyją w tabeli
  tylko do kompakcji.
- Dziś żadne wykonanie nie jest współdzielone: wśród 56 816 zdjęć (777 i
  `mums`) żaden `file_execution_key` nie jest użyty przez więcej niż jedną grę
  ani więcej niż jedno zdjęcie.
- Typowe zapytania (kod): odczyt/zapis po PK `file_execution_key`
  (`pipeline_store`, `orchestration_store`), odczyt `board_detection` po
  `(file_execution_key, stage)` złączony ze `source_images` gry
  (`grid_calibration_repository`, `board_cell_geometry_pending_repository`),
  przegląd kompakcji po całej tabeli keysetem po `file_execution_key`
  (`pipeline_state_compaction_repository`, zadanie utrzymaniowe, celowo
  globalne), usuwanie niewspółdzielonych kluczy przy sprzątaniu staging
  (`browser_staging_retention_repository`). Filtra po grze po stronie tabel
  współdzielonych nie ma; zawężenie do gry wykonuje strona tabel gry (złączenie
  po `file_execution_key`).

### Ocena i rekomendacja

Podział tych trzech tabel po grze: **nie jest potrzebny teraz**.

- Izolacja: tabele nie zawierają danych domenowych gry (planszy, komórki,
  symbole zatwierdzone, ścieżki), tylko wyniki analizy obrazu adresowane
  treścią; to jest zgodne z klasą `shared` manifestu („globalne wykonania
  content-addressed”) i nie narusza reguły planu V3 (zabronione są tabele
  wspólne z wierszem per zdjęcie, plansza albo komórka *danych gry*; wiersz
  wykonania jest per plik/pipeline, nie per gra).
- Skala: ≈ 0,6 GB łącznie przy 56 816 zdjęciach (≈ 10 kB na zdjęcie po kompakcji)
  wobec 34 GB danych gry; wszystkie dostępy idą po PK/UNIQUE, więc koszt
  zapytania rośnie logarytmicznie. Przy 10-krotnym wzroście liczby zdjęć
  (rzędu 6 GB) nie ma ścieżki skanującej tę tabelę per gra poza globalną
  kompakcją, która jest keysetem.
- Przesłanki, które zmieniłyby ocenę na „później”: (1) wymaganie usunięcia
  *całej* gry wraz z jej wynikami pipeline'u (dziś FK z partycji gier do
  wykonań i `ON DELETE RESTRICT` oraz współdzielenie po treści blokują
  automatyczne usunięcie; sprzątanie usuwa tylko klucze niewspółdzielone);
  (2) pojawienie się tego samego pliku w dwóch grach z różnym znaczeniem
  (dziś zero przypadków); (3) rozmiar rzędu dziesiątek milionów wykonań albo
  okno utrzymaniowe kompakcji przekraczające akceptowalny czas.
- Gdyby kiedyś zapadła decyzja o podziale: tabela per gra `LIST (game_id)` z
  kluczem `(game_id, file_execution_key)` i zmianą FK z partycji gier, w nowej
  wersji manifestu magazynu, z utratą deduplikacji między grami. To wymaga
  migracji i okna bez zapisów, zgody operatora i osobnego planu. Nie
  wykonywano i nie proponuje się tego teraz.

## Odstępstwa i obserwacje

1. **Brak przecieku między grami.** Cztery ścieżki nie dotykają partycji innej
   gry; brak odstępstw w izolacji. Brak brakujących kolumn `0139` w partycji
   nowej gry; nowa gra po pierwszym imporcie działa pod rolą aplikacyjną bez
   brakujących uprawnień (rola została utworzona przed grą, partycje nowej gry
   powstały później).
2. **CHECK `ck_source_images_geometry_exception` nie jest odporny na NULL.**
   Dla `geometry_completeness_status = 'geometry_exception'` z
   `geometry_exception_reason IS NULL` (przy ustawionych `_by` i `_at`) wyrażenie
   daje `NULL`, które CHECK przepuszcza. Sprawdzone na partycji nowej gry
   (rodzic ma to samo ograniczenie, więc dotyczy wszystkich gier). Pusty tekst
   `'   '` jest odrzucany. Aplikacja zawsze waliduje powód
   (`require_geometry_exception_reason`), więc to luka obrony w głąb, nie błąd
   działania. Test egzekwuje zatem odrzucenie powodu złożonego z samych spacji.
3. **Instrukcje bez predykatu gry** (opis wyżej) polegają na wiązaniu i RLS.
   Obecny runtime je spełnia; wartościowe jest utrzymanie reguły „runtime tylko
   rolą aplikacyjną” i testu planu jednej instrukcji bez predykatu.
4. **Warunek wstępny `active_review_item_ids`.** Funkcja wykonuje SQL na
   poziomie połączenia z niekwalifikowanymi nazwami i zakłada, że sesja jest
   już związana z grą. Wywołana bez wiązania kończy się błędem `42P01` (fail
   closed), nie pustym wynikiem; wszystkie obecne wywołania wołają ją po
   `bind`.

## Proponowane zmiany schematu (niewykonane)

- Nowa migracja zaostrzająca `ck_source_images_geometry_exception` o jawny
  warunek niepustego powodu niezależny od NULL (np. `COALESCE(length(btrim(
  geometry_exception_reason)), 0) > 0` zamiast `length(btrim(...)) > 0`); zmiana
  CHECK na rodzicu partycjonowanym, z walidacją na istniejących wierszach.
  Niski priorytet (aplikacja już wymusza powód); do ewentualnego połączenia z
  kolejną migracją tabeli `source_images`.
- Brak innych proponowanych zmian schematu. Podział trzech tabel
  współdzielonych nie jest rekomendowany teraz (patrz wyżej).

## Czego nie zweryfikowano

- Planów na danych produkcyjnej skali (777): plany w teście powstały na małych
  tabelach; wybór partycji (pruning) jest niezależny od statystyk, ale kosztów
  planów dużej gry nie mierzono. Bazy deweloperskiej nie planowano ani nie
  odpytywano poza metadanymi i próbkami.
- Zachowania na bazie z migracją `0139` zastosowaną na istniejących
  partycjach 777 (to krok przejścia operatora, `LOCAL_OPERATION_GUIDE.md`).
- Ścieżek zapisu poza czterema wskazanymi (np. backfill symboli
  `backfill_next_batch`, endpointy Reviewera) — objęte wcześniejszymi testami
  TASK-0807/0795/0797.
