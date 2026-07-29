---
title: Data model
status: accepted
last_updated: 2026-07-29
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

Niepusty `source_job_id` jest unikalny. Dataset opublikowany z ręcznego importu
wskazuje job walidacji `layout_import`, ma
`generator_version = layout-import-v1` oraz `generation_seed = 0`. Ponowienie
publikacji tej samej walidacji zwraca istniejący rekord.

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

Layout import M4 zapisuje w `input_payload` wyłącznie serwerowo poświadczone
wartości: `import_kind = layout_file`, kanoniczny względny `source_path`,
`source_checksum`, `source_size_bytes`, `file_format` i `contract_version = 1`.
Dla tego typu `input_key` pomija nazwę oraz rozmiar i identyfikuje grę,
checksumę, format oraz kontrakt. Dzięki temu kopia tych samych bajtów pod inną
nazwą nie tworzy drugiego joba.

Walidacja layout importu jest osobnym jobem `validate` z payloadem
`validation_kind = layout_import`, `import_job_id` oraz `rules_version_id`.
Wejście wymaga zakończonego surowego importu i opublikowanych reguł tej samej
gry. Oba UUID są częścią zwykłego `input_key`, dlatego ponowienie tej samej pary
nie tworzy duplikatu, a inna wersja reguł daje osobny wynik.

Tylko rekord `processing` ma komplet pól lease i `execution_slot = 1`.
Unikalność slotu gwarantuje najwyżej jedno lokalne wykonanie jednocześnie.
Worker zapisuje postęp i `checkpoint_payload` w tej samej transakcji, a każdy
checkpoint ma `schema_version = 1`. Wygaśnięcie lease usuwa pola wykonawcze i
przywraca ten sam rekord do `created`, zachowując checkpoint i liczniki.
`attempt_count` rośnie przy kolejnym przejęciu. Token lease jest wyłącznie
wewnętrzną ochroną zapisu i nie może być zwracany panelowi.

### image_file_executions

| Pole | Typ | Uwagi |
|---|---|---|
| file_execution_key | varchar(64) | PK, `image-file-execution-v1` |
| source_checksum_sha256 | varchar(64) | SHA-256 bajtów źródła |
| pipeline_fingerprint | varchar(64) | pełny fingerprint TASK-0068 |
| checkpoint_payload | JSONB | `image-pipeline-file-checkpoint-v1` |
| status | varchar | processing/waiting_for_review/completed/failed |
| review_required | boolean | kumulacyjna informacja o skierowaniu do review |
| error_code | varchar nullable | stabilny błąd pliku; używany od TASK-0071 |
| error_message | text nullable | bezpieczny opis |
| failed_stage | varchar nullable | dokładny `nextStage`, na którym zapisano błąd |
| retry_count | integer | liczba jawnych ponowień, `>= 0` |
| last_failed_at | timestamptz nullable | czas ostatniej trwałej awarii |
| created_at | timestamptz | |
| updated_at | timestamptz | |
| processed_at | timestamptz nullable | ustawiany po completed |

PK jest wyprowadzony wyłącznie z SHA-256 źródła i
`pipeline_fingerprint`. Dodatkowa unikalność
`(source_checksum_sha256, pipeline_fingerprint)` chroni ten sam kontrakt także
na poziomie bazy. Checkpoint zawiera pełne pochodzenie, uporządkowany prefiks
etapów i następny etap. Zapis jest dozwolony tylko przy aktywnym lease joba i
zgodnym oczekiwanym checkpointcie; stary worker nie może nadpisać nowszego
wyniku.

### image_import_job_files

| Pole | Typ | Uwagi |
|---|---|---|
| job_id | UUID | FK jobs, część PK |
| file_execution_key | varchar(64) | FK image_file_executions, część PK |
| order_index | bigint | deterministyczna kolejność w batchu |
| source_relative_path | varchar(1000) | diagnostyczna ścieżka POSIX |
| workflow_checkpoint_payload | JSONB | checkpoint recenzji i walidacji tego joba |
| workflow_status | varchar | processing/waiting_for_review/completed/failed |
| review_required | boolean | czy job-local workflow wymagał review |
| failed_stage/error_code/error_message | nullable | bezpieczny błąd tego powiązania |
| retry_count/last_failed_at | integer/timestamptz | historia ponowień tego joba |
| created_at | timestamptz | |
| updated_at | timestamptz | |

Osobne powiązanie pozwala wielu jobom wskazać jeden content-addressed wynik bez
kopiowania wyników automatycznych. Unikalne `(job_id, order_index)` zachowuje
kolejność, a ścieżka nie uczestniczy w tożsamości bajtów. Checkpoint
automatycznych etapów może być globalny, ale manual review i walidacja mają
job-local checkpoint/status, aby nowy import nie mutował historii wcześniejszej
decyzji. Identyczne źródło przetwarzane innym manifestem wskazuje inny
`image_file_execution`.

### Diagnostic exports bez tabeli domenowej

TASK-0073 nie dodaje tabeli eksportów diagnostycznych. Trwały stan `jobs`,
`image_import_job_files` i `image_file_executions` jest źródłem snapshotu, a
kanoniczny manifest JSON jest niezmiennym artefaktem systemu plików. Jego
tożsamością jest SHA-256 dokładnych bajtów, a ścieżka ma postać
`data/exports/image-jobs/<jobId>/<sha256>/diagnostics.json`.

Lista historyczna jest odtwarzana wyłącznie z checksumowanych manifestów w
zarządzanym root. Brak osobnej tabeli eliminuje ryzyko rozjazdu metadanych z
plikiem; koszt skanowania i ewentualny indeks są przedmiotem pomiaru TASK-0074.

### layout_import_rows

| Pole | Typ | Uwagi |
|---|---|---|
| job_id | UUID | FK jobs, część PK |
| line_number | bigint | fizyczna linia źródła, część PK |
| byte_offset_end | bigint | offset końca całej linii |
| sequence_number | bigint nullable | tylko dla poprawnego rekordu parsera |
| cells | smallint[] nullable | tylko dla poprawnego rekordu parsera |
| error_code | varchar nullable | tylko dla błędnego rekordu |
| error_message | varchar nullable | bezpieczny opis do 500 znaków |
| created_at | timestamptz | |

Klucz `(job_id, line_number)` zapewnia idempotentny replay partii. Constraint
wymaga dokładnie jednego wariantu: kompletnego `sequence_number/cells` albo
niepustego `error_code/error_message`. Numer sekwencji, offset i komórki mają
constraints zakresu; indeks `(job_id, byte_offset_end)` wspiera diagnostykę
fizycznego kursora.

Tabela jest surowym, izolowanym stagingiem parsera. Nie ma `dataset_version_id`
ani sygnatury i nie jest czytana przez release pipeline. TASK-0046 waliduje
wymiary oraz alfabet gry i dopiero z poprawnych wierszy tworzy znormalizowaną
postać datasetu.

Checkpoint importu schema v1 przechowuje poświadczone metadata źródła,
`byte_offset`, `line_number`, liczniki i `prefix_chain`. Przed wznowieniem
worker ponownie liczy łańcuch fizycznych linii do offsetu i usuwa rekordy z
`line_number` większym od trwałego kursora. Zapis partii zawsze poprzedza
checkpoint, dlatego awaria może powtórzyć upsert, ale nie tworzy duplikatu ani
nie zachowuje nietrwałego ogona.

### layout_import_normalized_rows

| Pole | Typ | Uwagi |
|---|---|---|
| validation_job_id | UUID | FK jobs, część PK |
| line_number | bigint | fizyczna linia źródła, część PK |
| import_job_id | UUID | wraz z linią FK do surowego stagingu |
| rules_version_id | UUID | opublikowana konfiguracja wymiarów i alfabetu |
| sequence_number | bigint nullable | zachowany dla parserowo poprawnego wiersza |
| cells | smallint[] nullable | zachowane dane row-major |
| signature | varchar nullable | wyłącznie dla poprawnego wiersza |
| error_code | varchar nullable | błąd parsera albo walidacji domenowej |
| error_message | varchar nullable | bezpieczny opis do 500 znaków |
| created_at | timestamptz | |

Klucz `(validation_job_id, line_number)` zapewnia idempotentny replay.
Poprawny wariant ma `sequence_number/cells/signature` bez błędu. Wariant błędu
ma niepusty kod i opis; dla błędu parsera numer i komórki są null, a dla błędu
wymiarów lub alfabetu pozostają zachowane. Indeksy
`(validation_job_id, sequence_number)` i `(validation_job_id, signature)`
przygotowują bounded raport integralności TASK-0047 bez wymuszania unikalności.

Checkpoint walidacji przechowuje wybrane UUID, liczbę surowych rekordów,
ostatni fizyczny `line_number`, liczniki oraz flagę ukończenia. Upsert partii
poprzedza checkpoint, dlatego replay daje ten sam wynik. Tabela nie ma
`dataset_version_id` i nie jest czytana przez release pipeline.

Raport TASK-0047 nie tworzy osobnej tabeli ani utrwalonego cache. Dla
zakończonego joba wykonuje dokładne agregaty SQL na niezmiennym stagingu:
liczniki wariantów, `min/max/count(distinct sequence_number)`, grupy duplikatów
numerów i sygnatur oraz liczniki kodów błędów. Liczba luk jest równa
`max(sequence_number) - count(distinct sequence_number)` dla poprawnych
dodatnich numerów. Bounded próbka luk powstaje z pierwszych uporządkowanych
przedziałów wyznaczonych przez `lag`, bez `generate_series` zależnego od
największego numeru. Dzięki temu dokładne liczniki nie wymagają materializacji
500 000 wierszy w procesie API.

Podgląd stagingu używa kursora `line_number`, ponieważ przed publikacją
`sequence_number` może mieć duplikaty. Poprawny wiersz jest częścią kontroli
ciągłości, a wiersz błędny pozostaje osobną blokadą i nie wypełnia brakującej
pozycji przyszłego datasetu.

### source_images

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | PK |
| import_job_id | UUID | FK jobs |
| file_execution_key | varchar(64) | FK globalnego wykonania pliku |
| relative_path | varchar(1000) | bezpieczna ścieżka POSIX |
| checksum_sha256 | varchar(64) | SHA-256 oryginału |
| width/height | integer | dodatnie wymiary discovery |
| status | varchar | discovered/processing/waiting_for_review/accepted/rejected/completed/failed |
| error_code | varchar nullable | zakres TASK-0071 |
| created_at/processed_at | timestamptz | |

Unikalne są `(import_job_id, checksum_sha256)` oraz
`(import_job_id, file_execution_key)`.

`source_images` i kolejne tabele wyników są zakresem integracji etapów M7.2.
Nie zastępują rejestru `image_file_executions`: pierwsze opisują domenowe
pochodzenie i rozpoznanie w konkretnym imporcie, drugie trwałą tożsamość
wykonania oraz checkpoint współdzielony przez bezpieczne retry.

### image_pipeline_stage_results

| Pole | Typ | Uwagi |
|---|---|---|
| file_execution_key | varchar(64) | FK execution, część PK |
| stage | varchar | część PK, jeden z sześciu etapów automatycznych |
| adapter_version | varchar(150) | dokładna wersja adaptera |
| result_payload | JSONB | wersjonowany wynik etapu |
| created_at | timestamptz | |

Wynik jest globalny i niezmienny per `(file_execution_key, stage)`. Zapis pod
aktywnym lease jest idempotentny tylko dla identycznej wersji i kanonicznego
payloadu. Manual review pozostaje projekcją konkretnego importu, a nie częścią
globalnego cache.

### recognized_boards

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | PK |
| source_image_id | UUID | FK source_images |
| position_index | smallint | 0..8, row-major |
| sequence_number_raw | varchar | niezmieniona odpowiedź OCR |
| sequence_number | bigint nullable | wyłącznie cyfrowa sugestia |
| sequence_confidence | float | 0..1 |
| board_geometry | JSONB | quad i provenance geometrii |
| board_relative_path | varchar | bezpieczna ścieżka artefaktu |
| board_checksum_sha256 | varchar(64) | |
| cells_prediction | JSONB | model, 15 predykcji i alternatywy |
| board_confidence | float | 0..1 |
| pipeline_fingerprint | varchar(64) | pełne provenance |
| status | varchar | pending_review/accepted/corrected/rejected |

Unikalne `(source_image_id, position_index)` uniemożliwia ciche przesunięcie
plansz lub duplikację wyniku row-major.

### cell_observations

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | PK |
| recognized_board_id | UUID | FK recognized_boards |
| row_index/column_index | smallint | odpowiednio 0..2 i 0..4 |
| crop_relative_path | varchar | bezpieczna ścieżka POSIX |
| crop_checksum_sha256 | varchar(64) | checksum konkretnego cropu |
| cropper_version | varchar(150) | |
| prediction | JSONB | symbol, confidence i maks. 4 alternatywy |
| created_at | timestamptz | |

Unikalność: `(recognized_board_id, row_index, column_index)`. Binarna wersja
cropu jest osobnym artefaktem wskazującym `cropper_version`,
`calibration_profile_version`, względną ścieżkę i checksumę. Zmiana geometrii
tworzy nową wersję cropu tej samej obserwacji; nie nadpisuje starego pliku ani
nie przenosi automatycznie decyzji symbolu.

W plikowym bootstrapie M6 `observationId` wynika z korpusu, źródła, domenowego
`sequence_number`, pozycji planszy i współrzędnych komórki, ale nie z bajtów
cropu. `cropSampleId` dodaje wersję croppera, profil kalibracji i checksumę
obrazu. `reviewed-cell-labels-v1` wskazuje dokładny `cropSampleId`; zmiana
geometrii wymaga nowej decyzji albo jawnej migracji w późniejszym zadaniu.

### image_review_items

Każda recognized board ma dokładnie jeden operacyjny element review M7.
`snapshot` zamraża źródło, planszę, geometrię, OCR, 15 predykcji i pełny
fingerprint. `resolved_value` dla accepted/corrected zawiera jawnie
zaakceptowany numer i 15 kodów symboli; rejected zawiera powód. Rewizja rośnie
po atomowej decyzji całej planszy.

Tabela jest oddzielona od `review_batches/review_items` M6. Tamte rekordy są
niezmiennym, bounded materiałem active learning; M7 obsługuje operacyjny import
katalogu i może być znacznie większy.

### image_review_resolution_events

Każda accepted/corrected/rejected decyzja i systemowe ponowne otwarcie konfliktu
numeracji tworzą append-only event z rewizją, UUID idempotencji, kanonicznym
SHA-256 komendy, aktorem, wartością i czasem. Unikalne
`(review_item_id, revision)` zachowuje historię, a
`(review_item_id, idempotency_key)` sprawia, że exact retry nie dodaje drugiego
eventu. Ponowne otwarcie zwiększa rewizję elementu review, ale nie usuwa
wcześniejszej decyzji z audytu.

### image_board_geometry_revisions

M6.5 dodaje append-only historię ręcznych korekt geometrii operacyjnej planszy.
Rekord zawiera:

- `recognized_board_id`,
- rosnącą `revision`,
- cztery narożniki w przestrzeni oryginalnego obrazu,
- wersję croppera, profilu i pipeline fingerprint,
- względne ścieżki oraz checksumy wyprostowanej planszy i dokładnie 15 cropów,
- aktora i czas utworzenia.

Unikalne `(recognized_board_id, revision)` zachowuje kolejność. Bieżąca
projekcja planszy może wskazać najnowszą rewizję, ale stary rekord i pliki nie
są nadpisywane. Zmiana checksumy cropu tworzy nowy `cropSampleId`; istniejąca
etykieta nie przechodzi na niego automatycznie.

Accepted/corrected `resolved_value` wskazuje dokładną rewizję geometrii i
`cropSampleId` każdej z 15 komórek. Dzięki temu późniejsze ulepszenie profilu
cięcia ani retraining nie zmienia danych, które rzeczywiście zatwierdził
człowiek.

### image_verified_cohort_exports

Zamrożony materiał z operacyjnego review jest wersjonowany per gra i import
job. Rekord przechowuje checksumę kanonicznego stanu wejściowego, checksumę
payloadu, względną ścieżkę artefaktu, liczby plansz/próbek/odrzuceń, autora i
czas. Exact retry tego samego stanu zwraca istniejący eksport, a nowa rewizja
planszy tworzy nową wersję.

Payload zawiera wyłącznie kompletne accepted/corrected wraz z numerem,
15 symbolami, geometrią, cropami, źródłem i pełnym provenance. Nie aktualizuje
modelu ani datasetu samym utworzeniem.

### image_layout_staging_rows

| Pole | Typ | Uwagi |
|---|---|---|
| import_job_id | UUID | FK jobs, część PK |
| recognized_board_id | UUID | FK board, część PK |
| review_item_id | UUID | unikalny FK rozwiązanej decyzji |
| sequence_number | bigint | zaakceptowany dodatni numer |
| cells | smallint[15] | aktywne `mobile_code`, row-major |
| created_at | timestamptz | |

Predykcja automatyczna nigdy nie tworzy wiersza. Materializacja następuje
wyłącznie z rozwiązania accepted/corrected i jest idempotentna. Duplikat numeru
nie jest ukrywany constraintem — walidacja ciągłości raportuje go jako blokadę
bez zmiany wartości. TASK-0071 usuwa wyłącznie nieopublikowane wiersze
konfliktujących plansz i ponownie otwiera ich review; pozostałe numery nie są
przesuwane.

### grid_calibration_profiles

```text
id
source_group
board_position
profile_version
interpolation_version
source_golden_sha256
source_detection_report_sha256
anchors
created_by
created_at
status
```

Unikalność opublikowanej wersji obejmuje
`(source_group, board_position, profile_version)`. Każdy anchor zachowuje
`sequence_number`, identyfikator obserwacji, quad detektora, zaakceptowany quad
oraz cztery korekty narożników w lokalnej bazie quadu detektora. Zastosowanie
profilu interpoluje te korekty liniowo po `sequence_number` albo klamruje je do
najbliższego anchora; nie wykonuje ekstrapolacji. Profil jest niezmienny po
publikacji i fingerprintowany razem ze źródłowym goldenem oraz raportem
detektora. Korekta tworzy kolejną wersję i osobne artefakty.

### review_batches

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| game_id | UUID | FK do gry |
| source_report_sha256 | char(64) | globalnie unikalny klucz idempotencji |
| active_learning_version | varchar | obecnie `whole-layout-active-learning-v1` |
| model_version | varchar | wersja modelu z raportu |
| model_artifact_sha256 | char(64) | checksum ONNX |
| calibration_report_sha256 | char(64) | |
| dataset_sha256 | char(64) | |
| split_sha256 | char(64) | |
| inventory_sha256 | char(64) | |
| temperature | double | dodatnia temperatura kalibracji |
| item_count | smallint | 1–100 |
| source_report | JSONB | dokładna, niezmienna kopia raportu |
| created_at | timestamptz | |

Batch jest atomowo importowany z raportu TASK-0063. Taki sam
`source_report_sha256` zwraca istniejący batch tylko wtedy, gdy gra i payload
są identyczne. Obrazy pozostają w lokalnym artifact store.

### review_items

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| review_batch_id | UUID | FK do `review_batches` |
| board_id | char(64) | identyfikator całej planszy |
| selection_rank | smallint | unikalny i ciągły w batchu |
| sequence_number | bigint | domenowa kolejność układu |
| source_image_id | varchar | |
| source_image_checksum_sha256 | char(64) | |
| source_group | varchar | |
| board_relative_path | varchar | bezpieczna względna ścieżka POSIX |
| status | enum | pending/accepted/corrected/rejected |
| prediction_snapshot | JSONB | dokładnie 15 komórek row-major wraz z confidence i alternatives |
| resolved_value | JSONB nullable | bieżąca projekcja pełnej decyzji |
| resolved_by | varchar nullable | lokalna tożsamość administratora |
| resolved_at | timestamptz nullable | czas bieżącej decyzji |
| resolution_revision | integer | 0 dla pending, rośnie przy każdej decyzji |
| created_at | timestamptz | |

Unikalne są `(review_batch_id, board_id)`,
`(review_batch_id, selection_rank)` oraz
`(review_batch_id, sequence_number)`. TASK-0064 zapisuje wyłącznie stan
`pending`. TASK-0066 aktualizuje bieżącą projekcję wyłącznie razem z nowym
zdarzeniem audytowym.

### review_resolutions

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| review_item_id | UUID | FK do `review_items` |
| revision | integer | dodatnia, unikalna w elemencie |
| idempotency_key | UUID | unikalny w elemencie |
| action | enum | accepted/corrected/rejected |
| command_sha256 | char(64) | canonical payload decyzji |
| resolved_value | JSONB | pełna niezmienna decyzja |
| resolved_by | varchar | lokalny administrator |
| created_at | timestamptz | |

Tabela jest append-only. Para `(review_item_id, revision)` zachowuje kolejność,
a `(review_item_id, idempotency_key)` zabezpiecza retry.

### review_feedback_exports

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| review_batch_id | UUID | FK do `review_batches` |
| game_id | UUID | FK do gry |
| version | integer | rosnąca wersja w grze |
| source_state_sha256 | char(64) | checksum bieżących rewizji |
| payload_sha256 | char(64) | checksum eksportu |
| sample_count | integer | liczba wyeksportowanych cropów |
| rejected_item_count | integer | odrzucone plansze, bez próbek |
| payload | JSONB | niezmienny manifest etykiet i lokalnych referencji |
| created_by | varchar | |
| created_at | timestamptz | |

Unikalne są `(game_id, version)` oraz
`(review_batch_id, source_state_sha256)`. Nowa decyzja tworzy nową wersję
eksportu; historyczny payload nie jest aktualizowany.

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

`version` jest globalnie unikalnym segmentem ścieżki o długości 1–100:
rozpoczyna się literą ASCII albo cyfrą, a dalej dopuszcza litery, cyfry, kropkę,
podkreślenie i łącznik. Nowy rekord zawsze ma `draft`; backend zapisuje aktualne
`algorithm_version = payout-v2` i `snapshot_schema_version = 2`.

### mobile_release_games

```text
mobile_release_id
game_id
dataset_version_id
rules_version_id
layout_count
```

Unikalność: `(mobile_release_id, game_id)`.

Wydanie zawiera od 1 do 15 gier i po utworzeniu nie pozwala zmieniać wyborów.
Źródła są blokowane podczas atomowego utworzenia rodzica i rekordów potomnych.
Dataset oraz rules muszą być opublikowane, należeć do tej samej aktywnej gry,
mieć zgodne wymiary, a dataset musi zawierać co najmniej jeden layout.
`layout_count` jest kopiowany do rekordu wyboru, aby zachować wejście wydania.

Start builda blokuje release i źródła, ponownie sprawdza ich stan, atomowo tworzy
dokładnie jeden job `android_build`, zapisuje `build_job_id` i ustawia
`building`. Job jest właścicielem całego workflow, nie tylko Gradle.

`snapshot_path` i `apk_path` są bezpiecznymi ścieżkami POSIX względnymi wobec
lokalnego katalogu artefaktów. Każda ścieżka występuje wyłącznie z pełnym
małym-hex SHA-256. Snapshot może zostać zapisany podczas `building` i użyty po
retry, lecz `apk_path`, `apk_checksum` i `ready_at` są zapisywane dopiero po
pełnej weryfikacji APK. Wydanie `ready` jest niezmienne. Błąd albo anulowanie
ustawia `failed` i nie tworzy nowego joba; jawny retry wznawia `build_job_id`.

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
