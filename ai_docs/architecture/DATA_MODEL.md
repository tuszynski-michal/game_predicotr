---
title: Data model
status: proposed
last_updated: 2026-07-23
---

# Model danych

Poniższy model jest logiczny. Nazwy i typy mogą zostać doprecyzowane przy tworzeniu migracji.

## games

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | techniczny klucz |
| code | varchar | stabilny kod |
| name | varchar | nazwa użytkowa |
| rows | smallint | np. 3 |
| columns | smallint | np. 5 |
| spin_cost | integer | kredyty, bez float |
| forecast_limit | integer | domyślnie 100000 |
| status | enum | draft/active/archived |
| created_at | timestamptz | |
| updated_at | timestamptz | |

Walidacja: `rows > 0`, `columns > 0`, `spin_cost >= 0`.

## symbols

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| game_id | UUID | FK games |
| code | varchar | np. S1 |
| name | varchar | |
| image_path | varchar nullable | ścieżka względna/URL |
| is_wildcard | boolean | |
| display_order | integer | |
| status | enum | active/archived |

Unikalność: `(game_id, code)`.

## dataset_versions

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| game_id | UUID | |
| version | integer | rosnąca wersja |
| status | enum | staging/published/archived |
| source_import_job_id | UUID nullable | |
| created_at | timestamptz | |
| published_at | timestamptz nullable | |

Tylko jedna wersja może być aktywna dla mobile, zależnie od strategii publikacji.

## layouts

| Pole | Typ | Uwagi |
|---|---|---|
| id | bigint/UUID | techniczny klucz |
| game_id | UUID | denormalizowane dla indeksów |
| dataset_version_id | UUID | |
| sequence_number | bigint | domenowa kolejność |
| signature | text | row-major, np. `1,2,3,...` |
| cells | JSONB lub smallint[] | dokładna reprezentacja |
| source_board_id | UUID nullable | pochodzenie z importu |
| payout_cache | integer nullable | tylko po decyzji o precomputingu |

Unikalność: `(dataset_version_id, sequence_number)`.

Nie ustawiaj unikalności na `signature`, ponieważ duplikaty są dozwolone.

### Indeksy początkowe

- `(dataset_version_id, sequence_number)` — unique,
- `(dataset_version_id, signature)` — exact duplicate lookup,
- indeks wspierający prefix lookup sygnatury po benchmarku,
- `(game_id, dataset_version_id)`.

Reprezentacja `cells` zostanie ostatecznie wybrana przy prototypie. Najważniejsze kryteria to proste mapowanie w Pythonie i wydajne pobieranie zakresów.

## win_patterns

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| game_id | UUID | |
| code | varchar | |
| name | varchar | |
| pattern_type | enum | PAYLINE / CONSECUTIVE_COLUMNS_ANY_ROW |
| row_path | JSONB nullable | np. `[0,1,2,1,0]` |
| start_column | smallint | domyślnie 0, do decyzji |
| is_active | boolean | |

Dla `PAYLINE` długość `row_path` nie może przekraczać liczby kolumn, a każdy indeks musi być mniejszy niż liczba rzędów.

## payout_rules

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| game_id | UUID | |
| symbol_id | UUID | |
| win_pattern_id | UUID nullable | null może oznaczać cały typ, do decyzji |
| match_length | smallint | np. 3/4/5 |
| payout_credits | integer | |
| is_active | boolean | |

Unikalność docelowa zależy od semantyki wzorców, ale system musi blokować dwa aktywne rekordy opisujące tę samą regułę.

## rules_versions

Reguły używane do obliczeń powinny być wersjonowane lub snapshotowane przy publikacji. Minimalne pola:

```text
id, game_id, version, status, created_at, published_at
```

`win_patterns` i `payout_rules` mogą wskazywać `rules_version_id`.

## import_jobs

| Pole | Typ |
|---|---|
| id | UUID |
| game_id | UUID |
| source_path | varchar |
| status | enum |
| pipeline_version | varchar |
| total_files | integer |
| processed_files | integer |
| failed_files | integer |
| review_items | integer |
| error_message | text nullable |
| created_at | timestamptz |
| started_at | timestamptz nullable |
| finished_at | timestamptz nullable |

## source_images

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

## recognized_boards

```text
id
source_image_id
position_index       # 0..8
sequence_number_raw
sequence_number
sequence_confidence
board_bbox
cells_prediction
board_confidence
status
```

## review_items

```text
id
import_job_id
source_image_id
recognized_board_id nullable
cell_index nullable
review_type
predicted_value
alternatives
confidence
status
resolved_value
resolved_by
resolved_at
```

## Dlaczego nie osobna tabela dla każdej komórki layoutu

Dla milionów layoutów i 15 pól osobna tabela mogłaby utworzyć dziesiątki milionów wierszy bez wyraźnej potrzeby w MVP. Preferowana jest zwarta tablica plus sygnatura. Osobna tabela komórek może zostać dodana tylko wtedy, gdy wymagane będą zapytania analityczne po pozycji symbolu.

## Mock data

Dla pierwszego milestone'u:

- 3 gry,
- 1000 layoutów na grę,
- 3 × 5,
- 10–12 symboli,
- deterministyczny generator z zapisanym seedem,
- celowo wstawione co najmniej 3 duplikaty sygnatur na grę,
- ciągłe `sequence_number` od 1 do 1000.
