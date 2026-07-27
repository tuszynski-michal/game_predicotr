---
title: Data model
status: accepted
last_updated: 2026-07-27
---

# Model danych

Model rozdziela kanoniczne dane administracyjne PostgreSQL od generowanego, niezmiennego SQLite dla mobile. Nazwy i dokładne typy zostaną utrwalone migracjami Alembic; poniższe reguły integralności są obowiązkowe.

## PostgreSQL — dane kanoniczne

### games

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | techniczny klucz |
| code | varchar | stabilny kod, unique |
| name | varchar | nazwa użytkowa |
| status | enum | draft/active/archived |
| created_at | timestamptz | |
| updated_at | timestamptz | |

Wersjonowane wymiary i koszt spinu znajdują się w `rules_versions`, aby historyczne wydanie było odtwarzalne.

### symbols

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| game_id | UUID | FK games |
| mobile_code | smallint | stabilny mały kod w ramach gry |
| code | varchar | np. S1 |
| name | varchar | |
| image_path | varchar nullable | ścieżka względna |
| is_wildcard | boolean | |
| display_order | integer | |
| status | enum | active/archived |

Unikalność:

- `(game_id, mobile_code)`,
- `(game_id, code)`.

Walidacja: `1 <= mobile_code <= 32767`. Wartość `0` jest zarezerwowana i nie
jest kodem symbolu.

Symbol nie jest fizycznie usuwany przez publiczne Admin API. `DELETE` oznacza
archiwizację i nie zmienia historycznego kodu. Po dodaniu wersji reguł i
datasetów ich klucze obce dodatkowo chronią użyte symbole.

### rules_versions

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| game_id | UUID | |
| version | integer | rosnąca wersja |
| rows | smallint | |
| columns | smallint | |
| spin_cost | integer | kredyty, bez float |
| status | enum | draft/published/archived |
| created_at | timestamptz | |
| published_at | timestamptz nullable | |

Walidacja:

- `rows > 0`,
- `columns > 0`,
- `spin_cost >= 0`,
- `(game_id, version)` unique,
- opublikowany rekord jest niezmienny.

### rules_version_symbols

| Pole | Typ | Uwagi |
|---|---|---|
| rules_version_id | UUID | FK rules_versions |
| symbol_id | UUID | symbol tej samej gry |
| minimum_match_length | smallint nullable | null wyłącznie dla jokera |
| is_active | boolean | |

Unikalność: `(rules_version_id, symbol_id)`.

Walidacja:

- zwykły symbol ma `2 <= minimum_match_length <= columns`,
- domyślna wartość nowego zwykłego symbolu wynosi 3 dla wersji mającej co
  najmniej 3 kolumny,
- joker ma `minimum_match_length = null` i nie otrzymuje payout rules,
- konfiguracja należy do wersji reguł, a nie globalnego rekordu `symbols`,
  dzięki czemu historyczne wydania pozostają odtwarzalne.

Pierwsza aktualizacja wykonuje upsert konfiguracji. Zwykły symbol bez
utrwalonego rekordu jest prezentowany przez panel z domyślnym minimum 3, ale
nie należy do wersji do czasu zapisu. Aktywne rekordy `rules_version_symbols`
definiują skład publikowanej wersji; publikacja wymaga co najmniej jednego
aktywnego zwykłego symbolu. Po utworzeniu rekordu nie można zmienić katalogowej
roli zwykły/joker tego symbolu.

### paylines

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| rules_version_id | UUID | |
| code | varchar | stabilny w wersji |
| name | varchar | |
| row_path | smallint[] | indeksy 0-based, po jednym na kolumnę |
| display_order | integer | |
| is_active | boolean | |

Nie ma pola `pattern_type`: jedynym typem jest `PAYLINE`.

Walidacja:

- długość `row_path` równa `columns`,
- każdy indeks spełnia `0 <= row < rows`,
- `(rules_version_id, row_path)` unique,
- `(rules_version_id, code)` unique,
- nie można zapisać dwóch komórek dla jednej kolumny, ponieważ pozycja tablicy reprezentuje kolumnę.

`code` jest stabilny po utworzeniu. Publiczne usunięcie draftu ustawia
`is_active = false`; rekord i jego `row_path` pozostają w wersji oraz mogą być
ponownie aktywowane. Zmiana wymiarów draftu nie może unieważnić istniejącego
`row_path`.

### payout_rules

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| rules_version_id | UUID | |
| symbol_id | UUID | zwykły symbol tej samej gry |
| match_length | smallint | od progu symbolu do liczby kolumn |
| payout_credits | integer | |
| is_active | boolean | |

Unikalność: `(rules_version_id, symbol_id, match_length)`.

Walidacja:

- `minimum_match_length <= match_length <= columns`,
- `payout_credits >= 0`,
- joker nie ma payout rule.

Publiczne usunięcie payout rule ustawia `is_active = false`; rekord i klucz
wersja/symbol/długość pozostają zarezerwowane. PATCH może zmienić kredyty i
ponownie aktywować rekord. Podniesienie `minimum_match_length` automatycznie
archiwizuje reguły poniżej nowego progu. Zmniejszenie liczby kolumn nie może
pozostawić konfiguracji ani payout rule poza zakresem.

Przed precomputingiem i publikacją pełna wersja reguł musi zawierać każdą parę
`(aktywny zwykły symbol, match_length minimum_match_length..columns)`, nie może
zawierać aktywnej reguły poniżej progu, a payout danego symbolu musi rosnąć
ściśle wraz z długością. CRUD draftu może być chwilowo niekompletny; niepełna
wersja nie może zostać użyta do wydania.

Reguła nie wskazuje konkretnej payline. Wartość symbol/długość obowiązuje na wszystkich aktywnych paylines.

### dataset_versions

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| game_id | UUID | |
| version | integer | rosnąca wersja |
| rows | smallint | wymiary danych |
| columns | smallint | |
| signature_cell_width | smallint | 1–5, zapisana konfiguracja codeca |
| layout_count | bigint | po walidacji |
| status | enum | staging/published/archived |
| generation_seed | bigint | 0–2147483647 dla mock generatora |
| generator_version | varchar | `mock-v1` dla TASK-0025 |
| source_job_id | UUID nullable | |
| created_at | timestamptz | |
| published_at | timestamptz nullable | |

Unikalność: `(game_id, version)`.

Wydanie może połączyć dataset i rules wyłącznie przy zgodnych wymiarach.
Generator mocka zapisuje seed i wersję algorytmu, dzięki czemu powtórzenie tych
samych wejść daje identyczny uporządkowany zestaw logiczny mimo nowych UUID i
numeru wersji.

Lifecycle wersji jest jawny: `staging → published → archived`. Publikacja
ustawia serwerowy `published_at` po walidacji pod blokadą rekordu. Dataset
`published` i jego layouty są niezmienne; archiwizacja zachowuje timestamp i
rekordy potomne. Wiele historycznych wersji jednej gry może pozostać
opublikowanych.

### layouts

| Pole | Typ | Uwagi |
|---|---|---|
| id | bigint | techniczny klucz |
| dataset_version_id | UUID | |
| sequence_number | bigint | domenowa kolejność |
| signature | varchar lub bytea | stałoszeroka, row-major |
| cells | smallint[] | dokładna zwarta reprezentacja |
| source_board_id | UUID nullable | pochodzenie z importu |

Unikalność: `(dataset_version_id, sequence_number)`.

Nie ma unikalności na `signature`, ponieważ duplikaty treści są dozwolone.

Integralność opublikowanej wersji:

- liczba komórek równa `rows * columns`,
- każda komórka zawiera stabilny kod symbolu danej gry,
- każdy kod symbolu mieści się w `signature_cell_width`,
- `signature` jest dokładnym stałoszerokim kodowaniem `cells` w kolejności
  row-major,
- numery tworzą dokładnie ciąg `1..layout_count`,
- brak luk i duplikatów numeru.

Indeksy:

- unique `(dataset_version_id, sequence_number)`,
- `(dataset_version_id, signature)` dla exact match i raportu duplikatów,
- indeks dla prefix match wybrany po benchmarku reprezentacji.

Administracyjny podgląd używa keyset pagination:
`sequence_number > after_sequence_number`, kolejności rosnącej i bounded
`limit`. Techniczny `id` nie definiuje kolejności ani kursora domenowego.

### layout_payouts

| Pole | Typ | Uwagi |
|---|---|---|
| dataset_version_id | UUID | |
| rules_version_id | UUID | |
| sequence_number | bigint | |
| algorithm_version | varchar | |
| total_payout | bigint | suma wielu nieujemnych wypłat |
| audit_path | varchar nullable | opcjonalny raport szczegółowy |
| calculated_at | timestamptz | |

Klucz logiczny:

```text
(dataset_version_id, rules_version_id, sequence_number, algorithm_version)
```

Oddzielna tabela zapobiega uznaniu payoutu za aktualny po zmianie reguł.

Wyniki są zapisywane przez worker partiami po kluczu logicznym. FK do
`(dataset_version_id, sequence_number)` gwarantuje, że payout wskazuje
istniejący layout, `total_payout` jest nieujemny, a `algorithm_version` nie może
być pusty. Idempotentny upsert pozwala bezpiecznie powtórzyć partię po awarii
między zapisem wyników a checkpointem.

`audit_path` jest względną ścieżką do deterministycznego pliku JSONL partii.
Nagłówek identyfikuje dataset, rules, algorytm i zakres, a każdy kolejny rekord
zawiera `sequenceNumber`, `totalPayout`, matches, komórki, jokery i
interpretacje. Wiele rekordów `layout_payouts` jednej partii świadomie wskazuje
ten sam plik; właściwy wpis identyfikuje `sequence_number`.

Gotowość payoutów jest oceniana wyłącznie dla dokładnej kombinacji
`(dataset_version_id, rules_version_id, algorithm_version)`. Wymaga
opublikowanego datasetu i reguł tej samej gry oraz wymiarów, dokładnie jednego
wyniku dla każdego `sequence_number` i niepustego `audit_path` każdego wyniku.
Historyczne wyniki innej wersji nie uzupełniają braków. Repozytorium wyznacza
dokładne liczniki zapytaniami agregującymi, a do raportu pobiera najwyżej 100
rosnących numerów brakujących sekwencji.

### jobs

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| job_type | enum | import/validate/payout/snapshot/android_build |
| game_id | UUID nullable | |
| status | enum | created/processing/waiting_for_review/completed/failed/cancelled |
| input_payload | JSONB | wersjonowany kontrakt |
| input_key | varchar(64) | unikalny SHA-256 typu, gry i kanonicznego payloadu |
| stage | varchar nullable | etap workflow, np. scanning/validating/writing_layouts |
| progress_current | bigint | |
| progress_total | bigint nullable | |
| success_count | bigint | |
| failure_count | bigint | |
| review_count | bigint | |
| error_code | varchar nullable | |
| error_message | text nullable | |
| worker_version | varchar nullable | ustawiany po przejęciu przez worker |
| checkpoint_payload | JSONB nullable | wersjonowany stan wznowienia workflow |
| attempt_count | integer | liczba skutecznych przejęć tego samego rekordu |
| execution_slot | smallint nullable | `1` wyłącznie dla aktywnego `processing` |
| lease_owner | varchar nullable | diagnostyczny identyfikator lokalnego workera |
| lease_token | UUID nullable | wewnętrzny fencing token, nie jest częścią Admin API |
| lease_expires_at | timestamptz nullable | granica ważności bieżącego lease |
| heartbeat_at | timestamptz nullable | ostatnie odnowienie lease |
| created_at | timestamptz | |
| updated_at | timestamptz | |
| started_at | timestamptz nullable | |
| finished_at | timestamptz nullable | |
| cancel_requested_at | timestamptz nullable | |

Status opisuje wyłącznie wspólny cykl życia. `scanning`, `validating` i podobne
wartości są `stage`, a nie statusami. Liczniki są nieujemne,
`progress_current <= progress_total`, gdy total jest znany. Unikalny
`input_key` blokuje dwa enqueue dla tego samego wejścia. Szczegóły importu mogą
być w tabeli `import_job_details`. Retry wznawia istniejący rekord zamiast
tworzyć duplikat.

Tylko rekord `processing` ma komplet pól lease i `execution_slot = 1`.
Unikalność slotu gwarantuje najwyżej jedno lokalne wykonanie jednocześnie.
Worker zapisuje postęp i `checkpoint_payload` w tej samej transakcji, a każdy
checkpoint ma `schema_version = 1`. Wygaśnięcie lease usuwa pola wykonawcze i
przywraca ten sam rekord do `created`, zachowując checkpoint i liczniki.
`attempt_count` rośnie przy kolejnym przejęciu. Token lease jest wyłącznie
wewnętrzną ochroną zapisu i nie może być zwracany panelowi.

### source_images

```text
id
import_job_id
relative_path
checksum
width
height
status
error_code
created_at
processed_at
```

Unikalność w ramach importu: `(import_job_id, checksum)`.

### recognized_boards

```text
id
source_image_id
position_index
sequence_number_raw
sequence_number
sequence_confidence
board_geometry
cells_prediction
board_confidence
pipeline_version
status
```

### review_items

```text
id
job_id
source_image_id
recognized_board_id nullable
cell_index nullable
review_type
predicted_value
alternatives
confidence
status
resolved_value
resolved_by nullable
resolved_at nullable
```

### mobile_releases

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| version | varchar | stabilna wersja użytkowa |
| status | enum | draft/building/ready/failed/archived |
| algorithm_version | varchar | |
| snapshot_schema_version | integer | |
| snapshot_path | varchar nullable | |
| snapshot_checksum | varchar nullable | |
| apk_path | varchar nullable | |
| apk_checksum | varchar nullable | |
| build_job_id | UUID nullable | |
| created_at | timestamptz | |
| ready_at | timestamptz nullable | |

### mobile_release_games

```text
mobile_release_id
game_id
dataset_version_id
rules_version_id
layout_count
```

Unikalność: `(mobile_release_id, game_id)`.

Wydanie `ready` jest niezmienne. Nie można wskazać wersji stagingowej ani niekompletnego zestawu payoutów.

## SQLite — snapshot mobilny

Snapshot jest generowany, nie migrowany przez mobile jako baza robocza. Minimalny logiczny schemat:

Finalny kontrakt M1 ma `snapshot_schema_version = 2`,
`PRAGMA user_version = 2` i `PRAGMA application_id = 0x47505244`. Schema `1`
była wyłącznie diagnostycznym spike’em M1.1 i nie jest kompatybilna.

### metadata

```text
key TEXT PRIMARY KEY
value TEXT NOT NULL
```

Obowiązkowe klucze:

- `release_version`,
- `snapshot_schema_version`,
- `algorithm_version`,
- `created_at`,
- `content_checksum`.

Snapshot M1 zapisuje dodatkowo `fixture_version`, `fixture_fingerprint`,
`dataset_version`, `rules_version`, `game_count` i `layout_count`. Zewnętrzny
manifest powtarza te wartości, opisuje kontrolowane duplikaty, unikalne prefiksy
i golden Target oraz zawiera SHA-256 całego pliku. `content_checksum` jest
SHA-256 kanonicznej logicznej treści tabel i wersji, natomiast
`fixture_fingerprint` identyfikuje pełne wejście build-time.

Produkcyjny generator M3 nie zapisuje pól fixture ani golden cases. Zachowuje
globalne `release_version`, `snapshot_schema_version`, `algorithm_version`,
`created_at`, `content_checksum`, `game_count` i `layout_count`, natomiast
`dataset_version` i `rules_version` są zapisane osobno w rekordzie każdej gry.
Logiczny checksum obejmuje znormalizowane metadata bez samej wartości checksumy
oraz rosnąco uporządkowane rekordy games, symbols i layouts.

### Materializacja na Android

Snapshot jest niezmiennym assetem wydania. Lokalna kopia używana przez
`expo-sqlite` ma nazwę zawierającą `release_version` lub `content_checksum`.
Przy uruchomieniu mobile:

1. porównuje manifest APK z aktywną lokalną kopią,
2. materializuje brakującą wersję bez nadpisywania aktywnego pliku w połowie
   operacji,
3. waliduje metadata i obsługiwaną wersję schematu,
4. aktywuje nową kopię,
5. dopiero potem może usunąć poprzednią nieaktywną wersję.

Nie wolno stosować wyłącznie warunku „plik już istnieje”, ponieważ katalog
danych Android pozostaje po aktualizacji APK.

### games

```text
id INTEGER PRIMARY KEY
code TEXT UNIQUE
name TEXT
rows INTEGER
columns INTEGER
spin_cost INTEGER
signature_cell_width INTEGER
layout_count INTEGER
dataset_version INTEGER
rules_version INTEGER
```

### symbols

```text
game_id INTEGER
mobile_code INTEGER
code TEXT
name TEXT
is_wildcard INTEGER
display_order INTEGER
image_asset_key TEXT nullable
PRIMARY KEY (game_id, mobile_code)
```

### layouts

```text
game_id INTEGER
sequence_number INTEGER
signature TEXT_OR_BLOB
payout INTEGER
PRIMARY KEY (game_id, sequence_number)
```

Indeks `(game_id, signature)` obsługuje exact match, wykrycie duplikatu i
zakresowy prefix match `[prefix, prefix + ":")`. Plan zapytania i benchmark
fixture M1 potwierdzają covering index dla 1000 layoutów. Zatwierdzenie tej
reprezentacji dla 500 000 rekordów pozostaje osobną bramką M3 na Androidzie.

Constraints chronią dodatnie wymiary i wersje, zakres kodów symboli, wartości
boolean jokera, nieujemny payout, klucze obce oraz unikalność
`(game_id, sequence_number)`. Ciągłość `1..layout_count`, poprawność symboli
zakodowanych w sygnaturze i zgodność grup duplikatów są dodatkowo sprawdzane
przez walidator artefaktu.

Snapshot nie zawiera:

- `cells` jako osobnej tabeli,
- zdjęć i wycinków,
- stagingu,
- kolejek review,
- pełnych reguł wypłat, jeżeli payout został poprawnie precomputed,
- danych wymagających połączenia z PostgreSQL.

Generator produkcyjny przydziela mobilne `games.id` deterministycznie po
stabilnym `games.code`, a symbole porządkuje po `mobile_code`. Każda kombinacja
dataset/rules/algorithm przechodzi bramkę gotowości payoutów przed utworzeniem
pliku. Layouty są odczytywane keysetowo i zapisywane partiami po 1000, z jawną
kontrolą ciągłości. Kompletny plik tymczasowy jest publikowany atomowo, a
istniejący cel nie może zostać nadpisany.

## Produkcyjny manifest i katalog artefaktu

Manifest M3 ma `manifestVersion = 1` i zawiera:

- release, czas, wersję schema SQLite i algorytmu,
- nazwę pliku `snapshot.db`,
- logiczny SHA-256 oraz SHA-256 całego pliku,
- dokładne liczniki gier, symboli i layoutów,
- dla każdej gry: mobilny id, stabilny kod, kanoniczne UUID oraz numery wersji
  dataset/rules, wymiary, szerokość sygnatury i liczniki.

Nie zawiera pól fixture, golden cases ani ścieżek absolutnych. Jest zapisywany
jako kanoniczny UTF-8 JSON z sortowanymi kluczami i końcowym newline.

Niezmienny katalog ma dokładną postać:

```text
<artifact-root>/
  snapshots/
    <releaseVersion>/
      <logicalContentSha256>/
        manifest.json
        snapshot.db
```

Istniejący katalog nie jest nadpisywany. Identyczny retry może zwrócić go
wyłącznie po pełnej walidacji i porównaniu manifestu; uszkodzona albo odmienna
zawartość pod tą samą ścieżką jest kolizją.

## Reprezentacja sygnatury

Każda komórka ma stałą szerokość kodu, dzięki czemu:

- nie ma kolizji typu `[1, 23]` kontra `[12, 3]`,
- prefiks wprowadzania odpowiada prefiksowi sygnatury,
- serializacja jest deterministyczna.

Codec v1 używa dodatnich kodów dziesiętnych dopełnionych zerami z lewej.
`signature_cell_width` ma zakres 1–5, jest zapisana przy wersji datasetu i w
rekordzie gry snapshotu oraz pozostaje stała dla całego datasetu. Nie wolno
wyprowadzać jej z pojedynczego layoutu. Zakres kodów odpowiada dodatniej części
typu `smallint`: `1..32767`.

Repozytorium traktuje wynikową sygnaturę jako wartość nieprzezroczystą, aby
możliwa była zmiana tekstu na BLOB po pomiarach.

## Dlaczego nie osobna tabela komórek

Przy około 7,5 miliona layoutów i 15 polach osobna tabela mogłaby utworzyć ponad 100 milionów wierszy bez potrzeby dla obecnych zapytań. Zwarta tablica plus sygnatura upraszczają import, wyszukiwanie i snapshot.

## Mock data M1

- 3 gry,
- po 1000 layoutów,
- plansza 3 × 5,
- 10–12 symboli,
- deterministyczny generator z zapisanym seedem,
- zamockowane paylines, wersjonowane minimum każdego symbolu oraz payouty dla
  wszystkich długości od minimum do 5,
- celowo 5–10 przypadków zduplikowanych sygnatur na grę,
- ciągłe `sequence_number` od 1 do 1000,
- precomputed payout dla każdego layoutu,
- wygenerowany SQLite dołączony do APK.

Aktualne logiczne fixture `m1-fixture-v2` powstaje przed zapisem SQLite. Używa
`algorithm_version = payout-v2`, dataset/rules version `2`, osobnych seedów
`71401`, `71402`, `71403`, tworzy dokładnie sześć par duplikatów na grę i
odrzuca podczas generowania wszystkie przypadkowe dodatkowe duplikaty.
Kontrolowane niezerowe payouty to:

- `game-1`: sekwencje `100 = 200`, `111 = 100`, `112 = 10`,
- `game-2`: sekwencja `200 = 100`,
- `game-3`: brak niezerowego payoutu.

Pozostałe layouty mają payout `0`. Dzięki temu golden pełnego cyklu obejmuje
kilka szczytów z późniejszym niższym szczytem i plateau (`game-1`, spin 0 =
`99`), pojedynczy szczyt (`game-2`, spin 0 = `199`) oraz brak dodatniego wyniku
(`game-2`, spin 0 = `200`). Fingerprint logicznego fixture chroni
deterministyczność wejścia, ale nie zastępuje checksumy pliku SQLite z
manifestu. Aktualny fingerprint wynosi
`2b8345577ec949f102ae21992cef197e5c5756e184d43815a5dd527d25eb2b79`.
