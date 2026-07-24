---
title: Data model
status: accepted
last_updated: 2026-07-24
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

Symbol użyty w opublikowanej wersji nie jest fizycznie usuwany. Archiwizacja nie zmienia jego historycznego kodu.

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

Lista symboli należących do wersji może być zapisana w tabeli łączącej `rules_version_symbols`, jeżeli symbole mogą być aktywowane niezależnie między wersjami.

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
- nie można zapisać dwóch komórek dla jednej kolumny, ponieważ pozycja tablicy reprezentuje kolumnę.

### payout_rules

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| rules_version_id | UUID | |
| symbol_id | UUID | zwykły symbol tej samej gry |
| match_length | smallint | co najmniej 3 |
| payout_credits | integer | |
| is_active | boolean | |

Unikalność: `(rules_version_id, symbol_id, match_length)`.

Walidacja:

- `3 <= match_length <= columns`,
- `payout_credits >= 0`,
- joker nie ma payout rule.

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
| source_job_id | UUID nullable | |
| created_at | timestamptz | |
| published_at | timestamptz nullable | |

Unikalność: `(game_id, version)`.

Wydanie może połączyć dataset i rules wyłącznie przy zgodnych wymiarach.

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
- numery tworzą dokładnie ciąg `1..layout_count`,
- brak luk i duplikatów numeru.

Indeksy:

- unique `(dataset_version_id, sequence_number)`,
- `(dataset_version_id, signature)` dla exact match i raportu duplikatów,
- indeks dla prefix match wybrany po benchmarku reprezentacji.

### layout_payouts

| Pole | Typ | Uwagi |
|---|---|---|
| dataset_version_id | UUID | |
| rules_version_id | UUID | |
| sequence_number | bigint | |
| algorithm_version | varchar | |
| total_payout | integer | |
| audit_path | varchar nullable | opcjonalny raport szczegółowy |
| calculated_at | timestamptz | |

Klucz logiczny:

```text
(dataset_version_id, rules_version_id, sequence_number, algorithm_version)
```

Oddzielna tabela zapobiega uznaniu payoutu za aktualny po zmianie reguł.

### jobs

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| job_type | enum | import/validate/payout/snapshot/android_build |
| game_id | UUID nullable | |
| status | enum | |
| input_payload | JSONB | wersjonowany kontrakt |
| progress_current | bigint | |
| progress_total | bigint nullable | |
| error_code | varchar nullable | |
| error_message | text nullable | |
| worker_version | varchar | |
| created_at | timestamptz | |
| started_at | timestamptz nullable | |
| finished_at | timestamptz nullable | |
| cancel_requested_at | timestamptz nullable | |

Szczegóły importu mogą być w tabeli `import_job_details`. Job jest wznawialny i idempotentny dla tego samego klucza wejścia.

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

Indeks `(game_id, signature)` obsługuje exact match i wykrycie duplikatu. Prefix match używa tej samej deterministycznej reprezentacji oraz indeksu zatwierdzonego benchmarkiem.

Snapshot nie zawiera:

- `cells` jako osobnej tabeli,
- zdjęć i wycinków,
- stagingu,
- kolejek review,
- pełnych reguł wypłat, jeżeli payout został poprawnie precomputed,
- danych wymagających połączenia z PostgreSQL.

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
- zamockowane paylines i payouty długości 3, 4 i 5,
- celowo 5–10 przypadków zduplikowanych sygnatur na grę,
- ciągłe `sequence_number` od 1 do 1000,
- precomputed payout dla każdego layoutu,
- wygenerowany SQLite dołączony do APK.
