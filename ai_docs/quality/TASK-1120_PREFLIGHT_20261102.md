# TASK-1120 — preflight danych Mumie A2, 2026-11-02

## Wynik

**BLOCKED przed implementacją.** Aktualne dane nie pozwalają na podział zgodny
z metodą `attested-sequence-order-v1` z zaakceptowanego planu. Nie zmieniono
aplikacji, danych, ról, usług ani przypisań modeli. Nie wykonywano treningu,
migracji, kopiowania ani dekodowania zdjęć.

## Tożsamość gry i liczby

W katalogu są dwie gry nazwane „Mumie a2”. `mumie-a2`
(`8563b353-9c5c-4282-bed5-825412d8bdd1`) ma zero źródeł. Korekty są w grze
`mumie-aktu2` (`246a1f54-eee8-49d5-b11a-0fde70e5eecd`).

| Import | Źródłowe zdjęcia | Zdjęcia z zatwierdzeniami | Aktualne ludzkie siatki z 24 punktami | Istniejące pliki |
|---|---:|---:|---:|---:|
| trening set, `fbca1ab5-37d2-4206-b18d-1ecc52d1f317` | 479 | 89 | 117 | 479 |
| trening set 2, `d7747436-5ebb-46af-af02-070d4cdaa290` | 309 | 0 | 0 | 309 |
| Razem | 788 | 89 | 117 | 788 |

Wszystkie 117 siatek przeszło istniejący `GridCohortEvidenceReader.capture`
w trybie grid-only: aktualne źródło/geometria, 24 węzły, właściciel, brak
wykluczającego grid issue oraz dowód ludzkiego zatwierdzenia. Sprawdzono
wszystkie 89 zdjęć w trzech partiach (41 + 36 + 40 kwalifikujących siatek).
Reader otrzymał prowizoryczne dane roli TRAIN wyłącznie do izolowanego pomiaru
etykiet; nie jest to deklaracja kwalifikacji nagrania ani nadanie prawa treningu.
Nie utworzono kohorty. Pozostałe pozycje zdjęć zachowują brak zatwierdzenia;
jedna dodatkowa niekwalifikująca pozycja ma `GRID_ISSUE_OR_TOPOLOGY`.

Sprawdzenie plików obejmuje `is_file` dla zarządzanych oryginałów pod
`D:/game_predicotr/artifacts/data/`. Nie weryfikuje bieżącej zawartości SHA ani
dekodowalności; materializacja musi wykonać te kontrole ponownie.

## Atesty i blokada kolejności

788/788 źródeł ma zgodne zakresy aktualnej geometrii, aktywne sloty, checksum
atestu i przypisanie `sequence_number = range_start + position_index`.
903 rewizje referencjonowane przez bieżące plansze mają wersję
`source-sequence-attestation-v2`; kilka korekt może wskazywać różne zgodne
rewizje tego samego źródła.

Jednocześnie **788/788 wartości `image_import_job_files.source_relative_path`**
to nazwy zarządzanych oryginałów, a nie nazwy `seq_<start>-<end>.jpg`.
Join wykonano przez `game_id`, `job_id = import_job_id` i `file_execution_key`.
Nie użyto omyłkowo wyłącznie pola `source_images.relative_path`.
Przykłady rzeczywiście zapisanych wartości:

- `originals/b7/b7ab3f548bf68eb332a66b187fbde8fcf81655b12e23d7a896c9d65c936b96db.jpg`
- `originals/59/592356106af00f987f69d91c7b49bce2f748b329def839382358826fbdd50e03.jpg`
- `originals/a7/a7459f1a7c9daed302568cdab38420f597d995b1ff3fc8e410f74eb240d0ce21.jpg`

Istniejący `parse_attested_sequence_range_filename` odrzuca wszystkie te
nazwy. Oba importy mają `previous_job_id = null`, `import_kind = image_directory`.
Sama zgodność geometrycznych atestów nie spełnia podwójnego warunku planu.
Nie użyto UUID, kolejności rekordów, `order_index` ani czasu jako dowodu.

Według obecnej reguły fallback każdy import jest nierozdzielny. Tylko jeden
import zawiera kwalifikujące etykiety. Nie może równocześnie należeć do TRAIN,
VALIDATION i REGRESSION. Dla dwóch pozostałych ról dostępne minimum wynosi
0 zdjęć/0 plansz, wobec wymagań TRAIN 10/30 oraz każdej kontroli 5/15.
Bufor dziesięciu źródłowych zdjęć nie usuwa tej blokady; bez dopuszczonej
kolejności nie wyznaczano granic ani proporcji 70/15/15.

## Znane aliasy, role i ograniczenia dowodów

Porównanie istniejących źródeł po byte SHA oraz znormalizowanym pixel SHA nie
wykazało aliasów dla 788 źródeł — ani w tej grze, ani w innych grach.
`recording_groups`, `recording_occurrences`, `recording_role_heads` i
`recording_evidence` są puste. Nie ma pliku
`artifacts/data/recording-providers/index.json` w głównym checkoutcie.

Nie ma zatem zarejestrowanych sesji ani ról do zastosowania w tym odczycie.
Nie jest to dowód niezależności ani braku historycznego użycia w LAB.
Niezainstalowane historyczne descriptor/provider i ancestor use pozostają
nierozstrzygnięte. Nie prowadzono szerokiego skanowania LAB ani innych zdjęć.

## Metoda i dalsza decyzja

Każda sesja bazy używała jawnego `REPEATABLE READ READ ONLY`; odczyt
`transaction_read_only` zwrócił `on`. Zapytania miały limit 15–20 s, oczekiwanie
na blokadę 3 s, każdy proces diagnostyczny limit 110 s. Sesje zakończono rollback.
Diagnostyka jest w ignorowanym katalogu `artifacts/`; raport nie zawiera sekretów.

Przed implementacją potrzebna jest decyzja operatora: zmiana zaakceptowanej
metody dowodzenia kolejności po ustaleniu innego wiarygodnego źródła lub
pozyskanie etykiet w odpowiedniej liczbie odrębnych nierozdzielnych grup.
Nie uznano atestów geometrii za automatyczny zamiennik wymaganej nazwy.
Preflight nie kończy TASK-1120; implementacja, testy i audyt nie rozpoczęły się.
