---
title: Data model
status: accepted
last_updated: 2026-08-24
---

# Model danych

Model rozdziela kanoniczne dane administracyjne PostgreSQL od generowanego, niezmiennego SQLite dla mobile. Nazwy i dokładne typy zostaną utrwalone migracjami Alembic; poniższe reguły integralności są obowiązkowe.

Audyt ochrony lokalnego Admina nie jest tabelą domenową. Jest append-only
artefaktem JSONL pod `artifacts/admin-audit/local-admin-events.jsonl`, aby awaria
lub odrzucenie requestu mogły zostać zapisane niezależnie od transakcji
domenowej. Każdy wpis ma UUID zdarzenia, czas UTC, serwerowego aktora
`local-owner`, akcję, jednoznaczny cel, wynik i opcjonalny stabilny kod
przyczyny; body, Authorization, kody, tokeny, hasła i klucze nie są zapisywane.

## PostgreSQL — dane kanoniczne

### Zdalna ręczna selekcja zdjęć

Stan protokołu zdalnej ręcznej selekcji jest przechowywany w ośmiu tabelach:

- `remote_manual_selection_sessions` — sesja, host-only binding katalogu oraz
  opcjonalne sole i skróty poświadczeń; publiczna projekcja nie ujawnia tych
  wartości;
- `remote_manual_selection_collections` — kolekcje w scope sesji;
- `remote_manual_selection_batches` — partie przypisane do jednego
  `base_binding + normalized collection + normalized batch`, wraz z
  monotonicznym `server_revision` i `last_client_sequence`;
- `remote_manual_selection_files` — wyłącznie względne metadane plików,
  desired state, generacja, zakres i checksumy; bez JPEG/BLOB;
- `remote_manual_selection_operations` — append-only dziennik komend i ich
  wyników, unikalny po `operationId` oraz
  `batch + clientInstance + clientSequence`;
- `remote_manual_selection_transfers` — metadane prób transferu, bez zawartości
  obrazu; TASK 10 wykorzystuje istniejące pola attempt/generation, deklarowane i
  odebrane bajty, checksumy, status oraz wyłącznie host-internal
  `temp_relative_path`, dlatego nie wymaga nowej migracji;
- `remote_manual_selection_host_actions` — kolejka host-only weryfikacji,
  materializacji, usunięcia i reconciliacji; aktywna akcja jest unikalna dla
  `file + generation + action type`;
- `remote_manual_selection_audit_events` — append-only audyt bez sekretów.

TASK 6 aktywuje opcjonalne pola poświadczeń i writer lease utworzone w migracji
`0056`. Kod ma 16-bajtową sól i 32-bajtowy PBKDF2-SHA256 hash; token występuje
wyłącznie jako 32-bajtowy SHA-256 i wygasa nie później niż sesja. Piąta błędna
próba ustawia `locked_at` i usuwa token oraz pełną trójkę lease. Revoke ustawia
status `revoked`, `revoked_at` i również atomowo czyści token/lease.

Aktywny writer jest opisany przez nierozdzielną trójkę
`writer_client_instance_id + writer_lease_token + writer_lease_expires_at`.
Klient zna tylko własne `clientInstanceId`; fencing token pozostaje host-only.
Lease trwa 45 sekund, heartbeat zachowuje token fencing, a takeover tworzy nowy
token dopiero po expiry. Lookup bearer tokenu przy duplikacie skrótu kończy się
fail-closed. Nie dodano nowej migracji, ponieważ 0056 zawiera komplet wymaganych
pól i constraintów.

Composite foreign keys wiążą każdy rekord z tym samym
`session + batch + file` scope. Operacja domenowa blokuje wiersz partii i pliku,
więc zwiększenie rewizji, aktualizacja desired state oraz dopisanie operacji są
jedną transakcją. Tworzenie globalnego mapowania partii dodatkowo serializuje
się advisory lockiem; constraint unikalności pozostaje ostateczną ochroną.
Indeksy delta obsługują ograniczone strony zmian plików po rewizji i operacji
po numerze klienta. Aktualizacja lub usunięcie rekordów operations/audit jest
blokowane triggerem bazy.

TASK 11 aktywuje akcje `materialize` i istniejące pola lease migracji `0056`.
Claim używa `FOR UPDATE SKIP LOCKED`; `queued`, gotowy `retry` oraz wygasły
`processing` mogą zostać przejęte z nowym tokenem. `attempt`,
`next_attempt_at` i `last_error_code` opisują bounded retry, a ukończenie czyści
lease. Terminalna akcja nie jest automatycznie zastępowana nową akcją tej samej
generacji.

Spójny commit materializacji ustawia plik na `synced`, transfer na wewnętrzne
`materialized`, akcję na `completed`, `final_relative_path` oraz zwiększa
`server_revision` i `transferred_file_count` dokładnie raz. Warunkiem są nadal
bieżące desired state/generation, zgodna check­suma transferu i finalnego pliku
oraz ten sam fencing token. Host-internal `temp_relative_path` i
`final_relative_path` nie są polami publicznego DTO. Brakująca akcja dla
spójnego rekordu `verified` jest odtwarzana przez bounded reconciliation;
istniejąca akcja dowolnego statusu zapobiega nieograniczonemu resetowaniu limitu
prób.

TASK 12 wykorzystuje ten sam dziennik operacji i kolejkę host actions dla
generacyjnego tombstone'u. `deselect`/`undo` wskazuje wcześniejszy zastosowany
`select`; repozytorium w jednej transakcji anuluje starsze transfery, superseduje
starsze materializacje i tworzy akcję `remove`. Projekcja pliku może zachować
nowszy desired state podczas usuwania starszej generacji. Po bezpiecznej
kwarantannie stara finalna ścieżka jest czyszczona, ale artefakt i checksumowany
journal pozostają poza tabelami domenowymi do czasu osobnej decyzji o retencji.
Nie dodano migracji: statusy i typ `remove` są już dopuszczone przez schemat
`0056`.

### games

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | techniczny klucz |
| code | varchar | stabilny kod, unique |
| name | varchar | nazwa użytkowa |
| status | enum | draft/active/archived |
| expected_layout_count | bigint | dodatnia konfiguracja, domyślnie 500 000 |
| created_at | timestamptz | |
| updated_at | timestamptz | |

Wersjonowane wymiary i koszt spinu znajdują się w `rules_versions`, aby
historyczne wydanie było odtwarzalne. `expected_layout_count` określa bieżący
cel kompletności gry. Testowa gra `0.2` może mieć mniejszą wartość; docelna
wartość domyślna pozostaje `500 000`.

### cleanup_operations

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | techniczny klucz potwierdzenia wykonania |
| operation_type | varchar | `mobile_release` albo `game_layout_data` |
| target_id | UUID | historyczny cel bez FK do usuniętego rekordu |
| preview_token | char(64) | SHA-256 kanonicznego preview |
| result_payload | jsonb | minimalny wynik i liczniki operacji |
| created_at | timestamptz | czas wykonania |

Unikalność `(operation_type, target_id, preview_token)` zapewnia idempotentny
retry po utracie odpowiedzi. Tabela jest append-only i nie przechowuje
usuniętych danych domenowych ani sekretów. Niezależny audyt bezpieczeństwa JSONL
zapisuje próbę autoryzacji i wynik requestu; `cleanup_operations` jest trwałym
potwierdzeniem skutku domenowego.

### symbols

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | |
| game_id | UUID | FK games |
| mobile_code | smallint | stabilny mały kod w ramach gry |
| code | varchar | np. S1 |
| name | varchar | wymagana nazwa kompatybilnościowa |
| name_pl | varchar nullable | polska etykieta prezentacyjna od 0.3 |
| name_en | varchar nullable | angielska etykieta prezentacyjna od 0.3 |
| image_path | varchar nullable | ścieżka względna |
| is_wildcard | boolean | |
| display_order | integer | |
| status | enum | active/archived |

Unikalność:

- `(game_id, mobile_code)`,
- `(game_id, code)`.

Walidacja: `1 <= mobile_code <= 32767`. Wartość `0` jest zarezerwowana i nie
jest kodem symbolu.

Opcjonalne `name_pl` i `name_en` są dodawane migracją Alembic. Wartości puste po
trimowaniu są odrzucane. `name` pozostaje wymaganym fallbackiem dla danych
utworzonych przed 0.3 oraz klientów starszego kontraktu.

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

Bieżący workspace reguł jest projekcją istniejących danych, a nie osobną encją:
wybiera najnowszy `draft`, a przy jego braku najnowszy `published`. Rozpoczęcie
edycji opublikowanej wersji tworzy najwyżej jeden bieżący draft. Kopiowane są
wartości `rules_versions` oraz wszystkie powiązane `paylines`,
`rules_version_symbols` i `payout_rules`; rekordy podrzędne dostają nowe
identyfikatory, natomiast źródło pozostaje niezmienne. Nie jest potrzebna nowa
kolumna ani migracja schematu.

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
| name | varchar | opisowa etykieta; Admin przy tworzeniu ustawia ją równą `code` |
| row_path | smallint[] | indeksy 0-based, po jednym na kolumnę |
| display_order | integer | deterministyczna kolejność prezentacji; Admin nadaje ją automatycznie |
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
| expected_layout_count | bigint | zamrożony cel kompletności tego datasetu |
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

`expected_layout_count` jest kopiowane z konfiguracji gry przy utworzeniu
stagingu i nie zmienia się później razem z grą. Publikacja wymaga
`layout_count = expected_layout_count`. Pole służy walidacji kompletności i nie
uruchamia syntetycznego generowania brakujących layoutów.

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
| job_type | enum | import/image_selection/validate/payout/snapshot/android_build |
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
| execution_slot | smallint nullable | `1` dla general albo `2` dla image selection, wyłącznie przy `processing` |
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

Tylko rekord `processing` ma komplet pól lease. General używa
`execution_slot = 1`, a `image_selection` używa `execution_slot = 2`.
Unikalność slotu gwarantuje najwyżej jedno lokalne wykonanie w każdym lane.
Worker zapisuje postęp i `checkpoint_payload` w tej samej transakcji, a każdy
checkpoint ma `schema_version = 1`. Wygaśnięcie lease usuwa pola wykonawcze i
przywraca ten sam rekord do `created`, zachowując checkpoint i liczniki.
`attempt_count` rośnie przy kolejnym przejęciu. Token lease jest wyłącznie
wewnętrzną ochroną zapisu i nie może być zwracany panelowi.

### worker_lane_runtime

| Pole | Typ | Uwagi |
|---|---|---|
| lane | varchar PK | `general` albo `image_selection` |
| instance_token | UUID | fencing statusu procesu po restarcie/rejestracji |
| worker_id | varchar | diagnostyczny identyfikator, nie trafia do API |
| worker_version | varchar | wersja implementacji lane |
| process_id | integer | dodatni PID, nie trafia do API |
| thread_budget | smallint | współbieżność 1–64 przekazana procesowi |
| started_at | timestamptz | start aktualnie zarejestrowanej instancji |
| heartbeat_at | timestamptz | sygnał procesu także przy pustej kolejce |
| stopped_at | timestamptz nullable | jawne kontrolowane zakończenie |
| updated_at | timestamptz | ostatnia zmiana rekordu |

Tabela jest projekcją operacyjną, nie kolejką i nie zastępuje lease joba. Upsert
nowej instancji zmienia `instance_token`; heartbeat i stop starego tokenu nie
mogą zmienić bieżącego rekordu.

### image_selection_runs, image_selection_groups i image_selection_candidates

Migracja `0025_image_selection` wprowadza trzy lekkie projekcje. Wszystkie UUID
są kluczami technicznymi, a kolejność domenowa pozostaje jawna.

#### image_selection_runs

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | PK |
| game_id | UUID | FK `games`, `RESTRICT` |
| job_id | UUID | unikalny FK `jobs`, dokładnie jeden job `image_selection` |
| source_selection_id | UUID | unikalna referencja do kontrolowanego stagingu; poświadczenie purpose dodaje TASK-0152 |
| input_manifest_sha256 | varchar(64) | małe litery hex |
| selector_fingerprint | varchar(64) | małe litery hex |
| ordering_policy | varchar(100) | zawsze `natural_relative_path_v1` |
| contract_version | smallint | zawsze `1` |
| output_manifest_sha256 | varchar(64) nullable | oba pola outputu są `null` albo kompletne |
| output_manifest_relative_path | varchar(1000) nullable | bezpieczna względna ścieżka POSIX |
| created_at / updated_at | timestamptz | |

Idempotency key runu to unikalne
`(game_id, input_manifest_sha256, selector_fingerprint)`. Ten sam manifest
przeliczony inną wersją selektora może utworzyć nowy run. Jeden staging może
zostać przejęty tylko przez jeden run.

#### image_selection_groups

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | PK |
| run_id | UUID | FK run, `CASCADE` |
| group_order | bigint | nieujemna deterministyczna kolejność, unikalna w runie |
| range_start / range_end | bigint nullable | oba `null` albo dodatnie i `start <= end` |
| fingerprint_sha256 | varchar(64) nullable | małe litery hex |
| board_count_consensus | smallint nullable | 1–9 |
| status | varchar | `collecting`, `auto_selected`, `manual_required`, `manually_selected`, `missing_image`, `skipped_existing_range`, `range_required`, `range_confirmed`, `skipped_unreadable`, `rejected_by_user` |
| rejection_origin_status | varchar nullable | dla `rejected_by_user`: `manual_required` albo `range_required` |
| created_at / updated_at | timestamptz | |

Częściowy indeks unikalny blokuje dwa wybrane outputy tego samego
`(run_id, range_start, range_end)`, ale pozwala zachować późniejsze pominięte
wystąpienia w audycie.

#### image_selection_candidates

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | PK |
| run_id | UUID | FK run, `CASCADE` |
| group_id | UUID nullable | złożony FK gwarantuje grupę z tego samego runu |
| order_index | bigint | nieujemny i unikalny w runie |
| source_relative_path | varchar(1000) | względna ścieżka POSIX, unikalna w runie |
| checksum_sha256 | varchar(64) | małe litery hex |
| width / height | integer | dodatnie |
| quality_metrics | JSONB | obiekt z metrykami selektora |
| range_confidence | float nullable | 0–1 |
| reason_codes | JSONB | tablica stabilnych kodów diagnostycznych |
| decision | varchar | `eligible`, `rejected`, `selected_automatic`, `selected_manual` |
| created_at | timestamptz | |

Wybrany kandydat musi należeć do grupy. Częściowy indeks unikalny pozwala na
dokładnie jedną decyzję `selected_automatic` albo `selected_manual` w grupie;
`selected_candidate_id` w API jest projekcją tej decyzji, a nie dodatkowym
cyrkularnym kluczem obcym. Żadna tabela nie przechowuje JPEG jako BLOB.

#### image_selection_manual_decisions

| Pole | Typ | Uwagi |
|---|---|---|
| idempotency_key | UUID | PK przekazany przez klienta; retry tego samego payloadu nie tworzy rewizji |
| run_id | UUID | FK run, `CASCADE` |
| group_id | UUID | złożony FK gwarantuje grupę z tego samego runu |
| candidate_id | UUID nullable | FK kandydata, `RESTRICT`; wymagany dla `selected_image` i `range_confirmed` |
| resolution | varchar | `selected_image`, `missing_image`, `duplicate_range`, `range_confirmed`, `rejected_group` albo `restored_group` |
| range_start / range_end | bigint nullable | oba `null` dla nierozpoznanego pominięcia albo dodatnie i `start <= end` |
| revision | integer | dodatnia, rośnie osobno dla każdej grupy |
| payload_sha256 | varchar(64) | SHA-256 kanonicznej decyzji |
| created_at | timestamptz | czas append-only zdarzenia |

Migracje `0027`, `0029` i `0030` rozwijają append-only audyt ręcznych
zatwierdzeń o jawny brak zdjęcia oraz opcjonalny zakres nierozpoznanego zestawu.
Unikalne `(run_id, group_id, revision)` zachowuje historię korekt, a bieżący
stan grupy i decyzja `selected_manual` kandydata pozostają projekcją ostatniej
rewizji. Plik JPEG jest przechowywany w kontrolowanym storage; tabela zawiera
wyłącznie identyfikatory, zakres i checksumę payloadu.

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
| geometry_revision | integer | `0` dla pipeline'u, potem bieżąca ręczna rewizja |
| status | varchar | pending_review/accepted/corrected/rejected |

Unikalne `(source_image_id, position_index)` uniemożliwia ciche przesunięcie
plansz lub duplikację wyniku row-major.

`sequence_number` w `recognized_boards` pozostaje sugestią OCR. Opcjonalny
numer zaakceptowany lub poprawiony przez człowieka jest zapisywany w
wersjonowanej decyzji review wraz z aktorem i rewizją; nie nadpisuje surowej
odpowiedzi OCR. Brak ręcznej decyzji pozwala pozostawić lukę i doładować kolejne
zdjęcia.

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
zaakceptowany numer i 15 kodów symboli; rejected zawiera powód. Systemowy
`superseded` wskazuje kanonicznego właściciela numeru, przyczynę i zachowane
źródło przegranej decyzji. Rewizja rośnie po atomowej decyzji całej planszy.

Tabela jest oddzielona od `review_batches/review_items` M6. Tamte rekordy są
niezmiennym, bounded materiałem active learning; M7 obsługuje operacyjny import
katalogu i może być znacznie większy.

TASK-0291 denormalizuje na rekordzie operacyjnego review zakres właścicielski
`game_id`, `import_job_id` i `sequence_number`. Częściowy indeks unikalny
egzekwuje najwyżej jeden rekord `pending` dla
`(game_id, sequence_number)`, gdy numer jest znany. Wartości są wyprowadzane i
synchronizowane w bazie z recognized board, source i joba, dzięki czemu także
legacy zapisy nie mogą ominąć invariantu.

Właściciel nierozwiązanej sekwencji jest wybierany deterministycznie według
malejącego `(job.created_at, job.id)`. Nowszy import oznacza starsze oczekujące
źródła jako `superseded`, usuwa ich operacyjny staging i pozostawia historię
oraz event decyzji do audytu. Jeżeli istnieje kanoniczna plansza
`accepted/corrected`, żaden nowy pending nie przejmuje numeru. Migracja `0069`
naprawia istniejące duplikaty według tej samej reguły i odbudowuje projekcję
wyszukiwania tak, aby wskazywała tego samego właściciela.

### image_review_queue_items i image_review_queue_states

TASK-0249 utrwala osobną projekcję topologii operacyjnej kolejki per import.
`image_review_queue_items` zamraża przy utworzeniu elementu review klucz
`(source_order_index, position_index, review_item_id)` oraz `import_job_id`.
Wartości topologii pochodzą z `image_import_job_files`, `source_images` i
`recognized_boards`; późniejsza zmiana statusu albo `sequence_number` nie może
ich przesunąć. Constraint i guard bazy blokują aktualizację pól klucza.

`status` w projekcji jest transakcyjnym lustrem bieżącego statusu
`image_review_items`. `image_review_queue_states` przechowuje per import
`total_count` oraz liczniki
`pending/accepted/corrected/rejected/superseded` i dodatni `queue_version`.
Suma liczników musi być równa `total_count`.

`queue_version` jest wersją topologii: rośnie przy dodaniu lub usunięciu
elementu, ale nie przy zwykłej zmianie statusu, decyzji ani numeru sekwencji.
Dzięki temu zapis poprawnej decyzji nie unieważnia pozycji tylko dlatego, że
zmieniły się liczniki. Projekcja i liczniki są utrzymywane przez transakcyjne
triggery PostgreSQL, obejmujące zarówno zapis API, jak i workera. Brak
jednoznacznego powiązania source-order kończy się fail-closed. Migracja
backfilluje wszystkie istniejące elementy i odmawia ukończenia, jeżeli choć
jeden z nich nie ma tego powiązania.

Konkurencyjność komendy planszy jest niezależna od wersji tej projekcji.
`expectedRevision` porównuje wyłącznie rewizję wskazanego
`image_review_items`, natomiast `queue_version` chroni wyłącznie topologię.
Odpowiedź poprawnego zapisu czyta liczniki projekcji już po wykonaniu triggerów;
nie rekonstruuje ich z poprzedniego snapshotu klienta.

Ta sama transakcja synchronizuje status właścicielskiego joba importu. Dodatni
`pending_count` oznacza `waiting_for_review`; `pending_count = 0` przy
`total_count > 0` oznacza `completed` i ustawia `finished_at`. Ponowne otwarcie
planszy zeruje `finished_at` i przywraca `waiting_for_review`. Migracja
backfilluje istniejące importy, których projekcja była już całkowicie
rozwiązana, ale historyczny job pozostał w stanie oczekiwania.

Job-local read model używa tej projekcji bez ponownego wyprowadzania kolejności
z numeru sekwencji albo bieżącego statusu. Keyset cursor przechowuje zamrożony
klucz pozycji oraz `queue_version`; liczniki odpowiedzi pochodzą z rekordu
`image_review_queue_states`. Zmiana statusu może usunąć element z filtrowanego
widoku, ale nie usuwa jego granicy z niezmiennej topologii.

TASK-0294 dodaje do tego samego read modelu wirtualny widok
`needs_grid_fix`. Nie jest to flaga planszy ani kolejna projekcja: element
należy do widoku wyłącznie wtedy, gdy dla jego bieżącej rewizji geometrii
istnieje co najmniej jedna `image_symbol_review_cells` z
`review_state = pending` i `has_grid_issue = true`. Repozytorium używa
skorelowanego `EXISTS`, dlatego wiele oznaczonych komórek nadal zwraca jedną
planszę. Zapis nowej geometrii tworzy nową rewizję, resetuje wszystkie 15
komórek i usuwa poprzednie flagi, więc plansza znika z tego widoku bez osobnego
czyszczenia. Odpowiedź zwraca również licznik takich plansz. Kursor schematu
v3 wiąże dodatkowo wybrany `grid_issue_view`; kursora `all` nie wolno użyć w
`needs_grid_fix` ani odwrotnie.

### image_review_resolution_events

Każda accepted/corrected/rejected decyzja, systemowe `superseded` oraz ponowne
otwarcie konfliktu numeracji tworzą append-only event z rewizją, UUID
idempotencji, kanonicznym SHA-256 komendy, aktorem, wartością i czasem. Event
`superseded` zachowuje numer, identyfikatory kanonicznego właściciela, przyczynę
i opcjonalną akcję przegranej komendy. Unikalne
`(review_item_id, revision)` zachowuje historię, a
`(review_item_id, idempotency_key)` sprawia, że exact retry nie dodaje drugiego
eventu. Ponowne otwarcie zwiększa rewizję elementu review, ale nie usuwa
wcześniejszej decyzji z audytu.

### image_symbol_review_states, image_symbol_review_cells i image_symbol_review_events

TASK-0294 wprowadza trwały, checksum-bound stan pojedynczego cropa, bez
przechowywania jego bajtów w PostgreSQL. `image_symbol_review_states` jest
jednym rekordem per gra i ma stan `rebuilding`, `ready` albo `failed`, keysetowy
kursor `last_review_item_id`, monotoniczną `catalog_revision`, liczniki oraz
kontrolowany raport braków numeru, cropów lub geometrii. Rewizja rośnie najwyżej
raz na transakcję dla danej gry po zmianie widocznego katalogu komórek. Gra nie
staje się `ready`, dopóki każdy aktualnie wybrany
właściciel z `image_board_search_fast_documents` nie ma dokładnie 15 komórek z
bieżącą rewizją geometrii i aktualną tożsamością cropa.

`image_symbol_review_cells` ma unikalny klucz `(review_item_id, cell_index)` i
zapisuje grę, import, planszę, dodatni `sequence_number`, pozycję row-major
`0..14`, `crop_sample_id`, bezpieczną ścieżkę, SHA-256, rewizję geometrii,
wersję croppera, sugestię modelu oraz opcjonalnie przypisany aktywny symbol.
`NULL` w przypisaniu oznacza techniczne `?`; `approved` wymaga realnego
symbolu. Flaga `has_grid_issue` może wystąpić wyłącznie przy stanie `pending`.
Indeksy wspierają przyszłe listowanie po grze/symbolu/stanie i filtrowanie
plansz mających problem siatki.

`image_symbol_review_events` jest append-only audytem przyszłych akcji komórki.
Zapisuje oba stany, przypisania, dokładną tożsamość cropa, rewizje, aktora oraz
opcjonalną operację masową. Początkowy backfill nie tworzy sztucznych eventów:
jego pochodzenie jest zapisane w rekordzie komórki i raporcie przebudowy.
Pełna decyzja Reviewera, jej ponowne otwarcie, zmiana geometrii, wynik
reinferencji, powstanie nowego elementu pipeline’u i zmiana właściciela
sekwencji aktualizują tę projekcję w tej samej transakcji. Korekta geometrii
zawsze zastępuje wszystkie
15 bieżących komórek nowymi cropami `pending` bez flagi siatki; reinferencja
zmienia sugestię modelu, ale nie może nadpisać zatwierdzenia człowieka.
Pojedyncza akcja `approve`, `reassign` albo `mark_grid_issue` jest związana z
dokładną rewizją i checksumą cropa, zapisuje event i atomowo agreguje rodzica:
15 aktualnych `approved` bez `?` oraz bez flagi siatki domyka planszę przez
istniejący canonical flow jako `accepted` lub `corrected`. Oznaczenie złej
siatki na domkniętej planszy usuwa canonical i staging, otwiera jej kolejkę
oraz job importu, ale zachowuje pozostałe 14 zatwierdzeń dla niezmienionych
cropów. Tylko zapis nowej geometrii unieważnia wszystkie 15 pozycji.
Write-through zaczyna materializować komórki dopiero po jawnym rozpoczęciu
backfillu gry; przed tym checkpointem dotychczasowy Reviewer działa bez
niekompletnej, pozornej projekcji.

Read path TASK-0294 nie tworzy drugiego read modelu cropów. Keysetowe API
listuje najwyżej 100 rekordów jednocześnie po
`(sequence_number, cell_index, review_item_id)`, zawsze łącząc komórkę z
aktualnym `image_board_search_fast_documents` i bieżącą rewizją geometrii
planszy. Dzięki temu historyczne rekordy komórek mogą pozostać audytowalne, ale
nie są widoczne jako aktywne cropy. `catalog_revision` jest częścią odpowiedzi
i pozwoli późniejszym mutacjom wykrywać drift katalogu; nie jest to wersja
obrazu ani substytut checksumy cropa.

### image_symbol_review_bulk_operations i image_symbol_review_bulk_targets

Od `v0.8.24` masowa weryfikacja cropów jest trwałą operacją, a nie jednym
requestem HTTP. `image_symbol_review_bulk_operations` utrwala grę, job typu
`image_symbol_review_bulk`, akcję `approve` / `reassign` /
`mark_grid_issue`, opcjonalny docelowy symbol, sposób zaznaczenia, aktora,
idempotency key, canonical checksumę komendy, stan oraz liczniki
`applied` / `conflict` / `failed`. Ten sam `game_id + idempotency_key` zwraca
wyłącznie tę samą komendę; inna komenda z tym kluczem jest konfliktem.

`image_symbol_review_bulk_targets` zamraża pozycje operacji bez binariów:
klucz komórki, rodzica, planszę, sekwencję i pozycję, oczekiwaną rewizję,
rewizję geometrii oraz sample id i SHA-256 cropa. Dla wyboru filtrem snapshot
powstaje przez bazowe `INSERT … SELECT`, bez materializowania wielotysięcznej
listy w pamięci procesu. Target ma jawny wynik `pending`, `applied`,
`conflict` albo `failed`; retry joba dotyka wyłącznie `pending`.

Worker general lane pobiera najwyżej 100 plansz na checkpoint. Wszystkie
targety jednej planszy są ponownie walidowane i zapisywane w pojedynczej
transakcji wraz z pełną decyzją, canonical, stagingiem, kolejką i projekcją
wyszukiwania. W szczególności masowe `mark_grid_issue` nie może otworzyć
planszy po pierwszym cropie i zgubić pozostałych targetów: otwarcie oraz
agregacja następują dopiero po zmianie całej partii tej planszy. Awaria
wycofuje wyłącznie bieżącą planszę; wcześniejsze wyniki pozostają audytowalne.

### image_sequence_source_override_events

TASK-0124 utrwala wyłącznie jawne odstępstwa od automatycznego rankingu źródeł.
Każdy rekord zawiera `game_id`, dodatni `sequence_number`, rosnącą `revision`,
opcjonalne `selected_review_item_id`, aktora i czas. `null` oznacza świadome
wycofanie override i powrót do rankingu automatycznego.

Unikalne `(game_id, sequence_number, revision)` zachowuje append-only historię.
Wybrane review item musi być zaakceptowanym kandydatem tej samej gry i
sekwencji. Automatyczny wybór pozostaje odtwarzalny i jest porządkowany po
confidence planszy, confidence numeru, rozdzielczości oraz UUID; ręczna decyzja
nie nadpisuje metryk ani provenance źródła.

### symbol_reference_images

Każdy symbol ma co najwyżej jedną aktywną, ręcznie wybraną referencję. Rekord
wiąże `symbol_id` z `review_item_id`, `recognized_board_id`, `sequence_number`,
`cell_index`, rewizją decyzji, rewizją geometrii, trwałą względną ścieżką,
SHA-256, aktorem oraz czasem wyboru. Checksum i źródłowy crop są weryfikowane
przed zapisem, a plik referencji jest content-addressed poza tabelą domenową.

Referencja może pochodzić wyłącznie z aktualnego właściciela
`image_sequence_canonical`, decyzji `accepted/corrected` i finalnego kodu
komórki zatwierdzonego przez człowieka. Cropy pending, rejected, superseded,
alternatywne źródła i predykcje modelu nie tworzą rekordów. Poprzednia
referencja może zostać atomowo zastąpiona, ale obraz binarny pozostaje w
zarządzanym storage do osobnego cleanupu.

Historyczna migracja `0023_symbol_bootstrap` pozostaje audytowalna, lecz tabela
`symbol_bootstrap_runs` została usunięta przez migrację `0065`; bieżący model
nie posiada automatycznej ścieżki tworzenia katalogu ani referencji.

### image_board_geometry_revisions

M6.5 dodaje append-only historię korekt geometrii operacyjnej planszy. Rewizja
może pochodzić z ręcznego edytora albo jawnego pending-only recropu; oba źródła
zachowują poprzednie rekordy i pliki. Rekord zawiera:

- `review_item_id` oraz `recognized_board_id`,
- rosnącą `revision`,
- UUID idempotencji i SHA-256 kanonicznej komendy,
- cztery narożniki w przestrzeni oryginalnego obrazu,
- wersję croppera, profilu i pipeline fingerprint,
- względną ścieżkę i checksumę obrazu referencyjnego oraz dokładnie 15 cropów,
- aktora i czas utworzenia.

Rewizja v19 zapisuje w `geometry` także `latticeBoundsQuad`, source/padded quady
15 komórek, checksumę źródła, source-order, pozycję, numer, wersje geometrii i
croppera, fingerprint, oczekiwane rewizje, aktora oraz
`decisionChecksumSha256`. Checksum decyzji kanonicznie wiąże te pola; nie jest
zamiennikiem `command_sha256`, który nadal chroni idempotentny transport.
Historyczna rewizja v1 może nie mieć checksumy decyzji i pozostaje czytelna.
Automatyczna rewizja TASK 8 ma `corrected_by = pending-board-cell-recrop-v19`,
pełne evidence automatycznego estymatora, checksumę przypiętej konfiguracji i
15 immutable cropów. Nie udaje decyzji człowieka i nie zmienia
`image_review_items.status` ani `resolution_revision`.

`corners`, wynikowa `geometry` i `crop_artifacts` są JSONB; constraint wymaga
czterech narożników oraz dokładnie 15 artefaktów cropów. Unikalne
`(recognized_board_id, revision)` zachowuje kolejność, a
`(review_item_id, idempotency_key)` zabezpiecza exact retry. Bieżąca projekcja
planszy wskazuje najnowszą rewizję przez `recognized_boards.geometry_revision`,
ale stary rekord i pliki nie są nadpisywane. Zmiana checksumy cropu tworzy nowy
`cropSampleId`; istniejąca etykieta nie przechodzi na niego automatycznie.

Accepted/corrected `resolved_value` wskazuje dokładną rewizję geometrii i
`cropSampleId` każdej z 15 komórek. Dzięki temu późniejsze ulepszenie profilu
cięcia ani retraining nie zmienia danych, które rzeczywiście zatwierdził
człowiek.

Pending-only zapis jest dozwolony wyłącznie, gdy zablokowany item nadal ma
status `pending`, a jego resolution revision oraz pełna projekcja planszy są
identyczne ze snapshotem workera. Rozwiązana lub równolegle zmieniona pozycja
nie tworzy rekordu. Istniejąca rewizja geometrii/croppera v19 jest uznawana za
aktualną i nie jest nadpisywana.

### image_board_geometry_pending

Trwała projekcja fail-closed przechowuje plansze, dla których nie istnieje
zweryfikowana geometria 3 × 5. Rekord należy do gry, joba importu, źródła i
pozycji 0–8 oraz zachowuje poświadczony `sequence_number`. Powiązanie z
`recognized_boards` i `image_review_items` jest opcjonalne: brak geometrii nie
może wymuszać utworzenia planszy z pustym `cells_prediction`.

Rekord zawiera status `pending | resolved | superseded`, zamknięty reason code,
ścieżkę i SHA-256 `BoardCellProcessingManifestV1`, fingerprint pipeline'u oraz
oczekiwane rewizje geometrii i decyzji. Nie przechowuje JPEG-a ani cropów.
Unikalność manifestu zapewnia idempotentny retry, a częściowy indeks dopuszcza
tylko jeden bieżący `pending` dla `job + source + position`. Nowy manifest
superseduje poprzedni. Rozwiązanie zapisuje wyłącznie numer nowej rewizji;
zmiana planszy albo review po snapshotcie kończy rekord jako `superseded`.

### reviewer_access_sessions i reviewer_access_audit_events

Trwała sesja Reviewera wiąże dokładnie `game_id` i `import_job_id`. Przechowuje
salt i PBKDF2 hash kodu, licznik maksymalnie pięciu prób, `locked_at`,
`revoked_at`, hash opaque tokenu, jego wygaśnięcie oraz czas ostatniego unlock.
Kod i token nie występują jawnie. Token wygasa nie później niż sesja i jest
usuwany przy revoke lub blokadzie.

Nowa sesja może wskazać wyłącznie image import tej samej gry w statusie
`waiting_for_review` albo `completed`, dla którego istnieje co najmniej jeden
`image_review_items`. Jest to warunek utworzenia sesji, a nie nowy stan ani
zdenormalizowany licznik w tabeli.

Append-only `reviewer_access_audit_events` zapisuje `created`,
`unlock_failed`, `unlocked`, `locked` i `revoked`. Decyzje plansz pozostają w
istniejącym audycie review, a ich aktor ma postać `reviewer-session:<UUID>`.

### reviewer_work_assignments

Trwałe przypisanie pracy jest oddzielone od procesu Reviewera i Quick Tunnel.
Wiąże dokładnie `game_id + import_job_id`, ma typ `local` albo `online` i
przechowuje ogrodzony lease (`lease_owner`, `lease_token`, `heartbeat_at`,
`lease_expires_at`). Import musi należeć do wskazanej gry, być gotowym importem
obrazów i zawierać pozycje review; repozytorium blokuje rekord importu przed
utworzeniem przypisania.

Assignment `online` wskazuje dokładnie jedną `reviewer_access_session`, a
assignment `local` nie może wskazywać sesji. Złożony FK obejmuje identyfikator
sesji, grę i import, dlatego nie można przypiąć sesji innego scope'u. Jedna
sesja może należeć najwyżej do jednego assignmentu. Zamknięcie assignmentu
online unieważnia tylko tę sesję; nie jest operacją zatrzymania współdzielonego
procesu ani ingressu.

Częściowy unikalny indeks po `import_job_id`, ograniczony do
`closed_at IS NULL`, gwarantuje najwyżej jedno aktywne przypisanie na import.
Różne importy nie współdzielą tego ograniczenia. Online capacity jest jednak
globalnie ograniczona do trzech różnych aktywnych importów. Każde otwarcie,
zamknięcie i odzyskanie wygasłych prac online przechodzi przez jeden
transakcyjny advisory lock PostgreSQL, dlatego równoległe transakcje nie mogą
osobno zobaczyć wolnego czwartego miejsca. Local assignment nie zajmuje online
capacity. Heartbeat wymaga aktualnego tokenu i niewygasłego lease; zapis stosuje
ten sam token jako fencing condition.

Zamknięcie nie usuwa rekordu ani tokenu lease. Uzupełnia atomowo `closed_at`,
`close_reason` i `closed_by`, dlatego ponowne otwarcie tego samego importu tworzy
nowy rekord, a wcześniejszy pozostaje historią. Wygasły aktywny wpis jest
zamykany z powodem `lease_expired` przed utworzeniem następcy i powoduje
unieważnienie własnej scoped sesji. Gdy nie pozostaje żaden aktywny online
assignment, warstwa lifecycle wykonuje ogrodzony `stop-if-current` wspólnego
tunelu. Tabela nie przechowuje kodu wejścia, bearer tokenu, URL tunelu ani
danych procesu.

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | PK |
| game_id | UUID | FK `games`, część scope'u |
| import_job_id | UUID | FK `jobs`, najwyżej jeden aktywny |
| assignment_type | varchar(16) | `local` albo `online` |
| reviewer_access_session_id | UUID nullable | wymagane tylko dla `online`; złożony FK zachowuje scope |
| lease_owner | varchar(200) | niepusty identyfikator właściciela lease |
| lease_token | UUID | fencing token, pozostaje w historii |
| heartbeat_at | timestamptz | monotoniczny heartbeat |
| lease_expires_at | timestamptz | późniejszy niż heartbeat |
| closed_at | timestamptz nullable | `NULL` oznacza aktywne przypisanie |
| close_reason | varchar(100) nullable | ustawiane razem z zamknięciem |
| closed_by | varchar(200) nullable | aktor zamknięcia |
| created_at / updated_at | timestamptz | trwałe czasy lifecycle'u |

### image_verified_cohort_exports

Zamrożony materiał z operacyjnego review jest wersjonowany per gra i import
job. Rekord przechowuje checksumę kanonicznego stanu wejściowego, checksumę
payloadu, względną ścieżkę artefaktu, liczby plansz/próbek/pending/odrzuceń,
autora i czas. Exact retry tego samego stanu zwraca istniejący eksport, a nowa
rewizja decyzji albo geometrii tworzy nową wersję.

Payload zawiera wyłącznie kompletne accepted/corrected wraz z numerem,
15 symbolami, geometrią, cropami, źródłem i pełnym provenance. Nie aktualizuje
modelu ani datasetu samym utworzeniem.

| Pole | Typ | Uwagi |
|---|---|---|
| id | UUID | PK |
| game_id | UUID | FK games |
| import_job_id | UUID | FK image-directory job |
| version | integer | dodatnia, rosnąca w kontekście gry i importu |
| input_state_sha256 | char(64) | kanoniczny stan wszystkich rewizji review |
| payload_sha256 | char(64) | dokładne bajty niezmiennego JSON |
| artifact_relative_path | varchar(1000) | POSIX pod `<artifact-root>/data` |
| board_count | integer | kompletne accepted/corrected |
| sample_count | integer | dokładnie `board_count * 15` |
| pending_item_count | integer | informacyjny stan chwili zamrożenia |
| rejected_item_count | integer | bez próbek |
| created_by | varchar(200) | lokalny aktor |
| created_at | timestamptz | czas pierwszego utworzenia stanu |

Unikalne są `(game_id, import_job_id, version)` oraz
`(game_id, import_job_id, input_state_sha256)`. Artefakt nie zawiera binarnych
obrazów ani ścieżek absolutnych.

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

## Planowane encje M6.6 — iteracyjne ulepszanie modelu symboli

Szczegółową semantykę definiuje
`architecture/SUPERVISED_MODEL_IMPROVEMENT.md`. Encje zostaną dodane wyłącznie
przez migracje Alembic w TASK-0143 i TASK-0148.

### verified_training_cohorts

```text
id UUID PRIMARY KEY
game_id UUID NOT NULL REFERENCES games(id)
iteration_number INTEGER NOT NULL
manifest_schema_version INTEGER NOT NULL
manifest_checksum_sha256 TEXT NOT NULL
idempotency_key UUID NOT NULL
command_sha256 TEXT NOT NULL
resolved_layout_count INTEGER NOT NULL
cell_sample_count INTEGER NOT NULL
source_image_count INTEGER NOT NULL
pending_item_count INTEGER NOT NULL
rejected_item_count INTEGER NOT NULL
incomplete_item_count INTEGER NOT NULL
artifact_relative_path TEXT NOT NULL
created_by TEXT NOT NULL
created_at TIMESTAMPTZ NOT NULL
UNIQUE (game_id, iteration_number)
UNIQUE (game_id, manifest_checksum_sha256)
UNIQUE (game_id, idempotency_key)
```

### verified_training_cohort_items

```text
id UUID PRIMARY KEY
cohort_id UUID NOT NULL REFERENCES verified_training_cohorts(id)
item_order INTEGER NOT NULL
review_item_id UUID NOT NULL REFERENCES image_review_items(id)
recognized_board_id UUID NOT NULL REFERENCES recognized_boards(id)
source_image_id UUID NOT NULL REFERENCES source_images(id)
import_job_id UUID NOT NULL REFERENCES jobs(id)
sequence_number BIGINT NOT NULL
decision_status TEXT NOT NULL
resolution_revision INTEGER NOT NULL
geometry_revision INTEGER NOT NULL
source_checksum_sha256 TEXT NOT NULL
board_checksum_sha256 TEXT NOT NULL
pipeline_fingerprint TEXT NOT NULL
item_checksum_sha256 TEXT NOT NULL
board_manifest JSONB NOT NULL
UNIQUE (cohort_id, item_order)
UNIQUE (cohort_id, review_item_id)
```

`board_manifest` jest małym, niezmiennym manifestem pozycji. Wiąże dokładną
rewizję review i geometrii, 15 `cropSampleId`, checksumy i ścieżki cropów, kod
symbolu człowieka, zdjęcie źródłowe, import oraz pipeline. Nie zawiera binariów.
Kohorta jest append-only. `accepted` i `corrected` mogą wejść do treningu;
`rejected`, `superseded`, `pending` i niekompletne decyzje pozostają policzone w manifeście
stanu, ale nie tworzą pozycji treningowych.

### symbol_model_iterations

```text
id UUID PRIMARY KEY
game_id UUID NOT NULL REFERENCES games(id)
cohort_id UUID NOT NULL REFERENCES verified_training_cohorts(id)
iteration_number INTEGER NOT NULL
status TEXT NOT NULL
configuration_fingerprint TEXT NOT NULL
configuration_payload JSONB NOT NULL
dataset_manifest_checksum_sha256 TEXT nullable
dataset_manifest_relative_path TEXT nullable
checkpoint_checksum_sha256 TEXT nullable
checkpoint_relative_path TEXT nullable
gate_configuration_fingerprint TEXT nullable
gate_configuration_payload JSONB nullable
candidate_manifest_checksum_sha256 TEXT nullable
candidate_manifest_relative_path TEXT nullable
gate_report_checksum_sha256 TEXT nullable
gate_report_relative_path TEXT nullable
gate_metrics JSONB NOT NULL DEFAULT '{}'
rejection_reasons TEXT[] NOT NULL DEFAULT '{}'
job_id UUID NOT NULL REFERENCES jobs(id)
last_completed_epoch INTEGER NOT NULL DEFAULT 0
partial_metrics JSONB NOT NULL DEFAULT '{}'
error_code TEXT nullable
error_message TEXT nullable
created_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
UNIQUE (game_id, iteration_number)
UNIQUE (job_id)
UNIQUE (game_id, cohort_id, configuration_fingerprint)
```

Status należy do automatu opisanego w architekturze M6.6. Artefakty są
niezmienne i content-addressed; tabela przechowuje ścieżki oraz metadata.
TASK-0146 implementuje stany `created`, `dataset_build`, `training`, `trained`,
`failed` i `cancelled`. Pola ONNX, kalibracji i raportu bramki dochodzą w
TASK-0147 zamiast udawać gotowego kandydata już po samym treningu.

TASK-0147 dodaje stany `evaluating`, `candidate_ready` i `rejected` oraz
checksumy manifestu i raportu bramki. `gate_metrics` zawiera metryki kandydata,
opcjonalnej aktywnej bazy, parity, kalibrację i smoke CPU; `rejection_reasons`
jest jawną, stabilną listą przyczyn odrzucenia. Żadne z tych pól nie jest
aktywnym wskaźnikiem modelu.

### game_symbol_model_activations

```text
id UUID PRIMARY KEY
game_id UUID NOT NULL REFERENCES games(id)
model_iteration_id UUID NOT NULL REFERENCES symbol_model_iterations(id)
previous_model_iteration_id UUID nullable
action TEXT NOT NULL
activation_number INTEGER NOT NULL
actor TEXT NOT NULL
reason TEXT nullable
idempotency_key UUID NOT NULL
command_sha256 TEXT NOT NULL
created_at TIMESTAMPTZ NOT NULL
UNIQUE (game_id, activation_number)
UNIQUE (game_id, idempotency_key)
```

Bieżący aktywny model jest projekcją ostatniego skutecznego zdarzenia. Aktywacja
i rollback są append-only i nie zmieniają historycznych iteracji.
`activation_number` jest nadawany monotonicznie pod blokadą rekordu gry, dlatego
porządek projekcji nie zależy od czasu rozpoczęcia transakcji ani losowego UUID.
`command_sha256` wiąże treść komendy z kluczem idempotencji.

### symbol_prediction_revisions

```text
id UUID PRIMARY KEY
game_id UUID NOT NULL REFERENCES games(id)
review_item_id UUID NOT NULL
crop_sample_id TEXT NOT NULL
crop_checksum_sha256 TEXT NOT NULL
model_iteration_id UUID NOT NULL REFERENCES symbol_model_iterations(id)
prediction_payload JSONB NOT NULL
prediction_checksum_sha256 TEXT NOT NULL
job_id UUID nullable REFERENCES jobs(id)
created_at TIMESTAMPTZ NOT NULL
UNIQUE (review_item_id, crop_sample_id, model_iteration_id,
        prediction_checksum_sha256)
```

Tabela jest append-only i nie przechowuje decyzji użytkownika. Zapis nowej
rewizji jest dozwolony wyłącznie po warunkowym sprawdzeniu, że item nadal ma
status `pending`, oczekiwaną rewizję i zgodny crop. Rozstrzygnięcia `accepted`,
`corrected` i `rejected` nie są aktualizowane przez operacje modelu.

Image import job zapisuje przypięte `model_iteration_id`, manifest SHA-256 i
fingerprint inferencji. Aktywacja innej wersji podczas joba nie zmienia tego
snapshotu.

## SQLite — snapshot mobilny

Snapshot jest generowany, nie migrowany przez mobile jako baza robocza. Minimalny logiczny schemat:

Finalny kontrakt M1 ma `snapshot_schema_version = 2`,
`PRAGMA user_version = 2` i `PRAGMA application_id = 0x47505244`. Schema `1`
była wyłącznie diagnostycznym spike’em M1.1 i nie jest kompatybilna.

Wersja 0.3 wprowadza `snapshot_schema_version = 3` i `PRAGMA user_version = 3`
wyłącznie przez dodanie opcjonalnych etykiet `name_pl` i `name_en` do tabeli
`symbols`. Generator, manifest i mobile muszą zgadzać się co do schema v3;
starsze APK nadal używają własnego niezmiennego snapshotu schema v2.

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
name_pl TEXT nullable
name_en TEXT nullable
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

## Projekcja wyszukiwania plansz częściowym układem

Wyszukiwanie Admina nie skanuje surowych obserwacji komórek ani obrazów. Trwała
projekcja kandydatów zachowuje dowód symboli dla wszystkich pozycji review, a
`image_board_search_documents` wybiera deterministycznie jednego właściciela
dla `game_id + sequence_number`. Obie projekcje są aktualizowane w tej samej
transakcji co import, nowa predykcja, korekta geometrii lub decyzja review.

`image_board_search_fast_documents` jest wąskim, fizycznym read modelem
wyłącznie aktualnie wybranego dokumentu. Zachowuje identyfikatory planszy,
status, checksumę, znane pozycje oraz pięć tablic kodów mobilnych 3 × 5
(primary i cztery alternatywy). Nie zawiera tokenów tekstowych, JSON, cropów
ani innych danych binarnych. Dzięki temu ranking częściowego wzoru wykonuje
deterministyczny odczyt tylko niezbędnych kolumn także wtedy, gdy dodatni wzór
jest zbyt częsty, aby indeks tokenów skutecznie zawężał zbiór.

Klucz główny fast modelu pozostaje `(game_id, sequence_number)`, a unikalne
`review_item_id` chroni przed wyświetleniem tej samej pozycji w dwóch wynikach.
Migracja najpierw kopiuje istniejące dokumenty, a synchronizator zapisuje oba
read modele atomowo. Obrazy nadal są assetami filesystemu powiązanymi przez
`review_item_id` i checksumę; żadna z tych tabel nie przechowuje JPEG-a.

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
