---
title: Globalna, wersjonowana biblioteka geometrii shape v2
status: done
task_id: TASK-0605
---

# TASK-0605 — globalna biblioteka geometrii shape v2

## Status

`done`

## Goal

Udostępnić trwałą, globalną i idempotentną bibliotekę wersji wspólnej geometrii
`framed_full_page_v2`, bez routingu per gra i bez zapisu obrazu lub semantyki gry.

## Context

G02 przygotowało czysty rdzeń propozycji geometrii. Przed integracją z
preflightem potrzebny jest osobny control plane, który wersjonuje możliwą do
ponownego użycia wiedzę o ramce, topologii i jakości, a jednocześnie nie
miesza danych gry ani istniejących danych v1/v1.1.

## Dependencies / entry conditions

- G00, G01 i G02 są ukończone; ich corpus i rdzeń pozostają wyłącznie
  źródłem kontraktów, nie danymi zapisywanymi przez to zadanie.
- Decyzje D-416–D-421 są obowiązujące.
- Aktualny router wiąże data plane z pojedynczą grą; biblioteka musi więc
  pozostać w `public` jako control plane.
- Brak corpusów produkcyjnych nie blokuje samego schematu ani repozytorium.

## Recommended execution

`gpt-5.6-terra` z reasoning `xhigh`, ponieważ zadanie zmienia trwały model
PostgreSQL, wymaga migracji, izolacji od routera gry i bezpiecznej
idempotencji. Niezależny audyt `gpt-6-astra` z reasoning `medium` sprawdza
migrację, własność danych i zachowanie retry. P0/P1 zatrzymuje dalszy plan do
naprawy; P2/P3 są naprawiane, ponownie testowane i audytowane w tym zadaniu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-416–D-421)
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/SHAPE_GEOMETRY_V2_EXECUTION_PLAN.md` (G06)
- `ai_docs/delivery/GLOBAL_GEOMETRY_LIBRARY_EXECUTION_PLAN.md` (badanie
  techniczne G06)
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`

## Scope

- Dodać migracją Alembic tabele `public` dla niezmiennych wersji globalnego
  profilu i ich dowodów oraz constrainty checksum, topologii, statusów,
  kolejności, unikalności i jedynej aktywnej wersji dla zgodnego zakresu.
- Przechowywać wyłącznie: rodzinę geometrii, topologię 3 × 3 / 3 × 5,
  znormalizowany szablon geometrii, wielokolorowy opis wyglądu ramki,
  checksummowany skrót dowodów, liczniki jakości, wynik i `source_game_ref`
  jako opisową proweniencję.
- Dodać typy domenowe i repozytorium tworzące wyłącznie kandydata w sposób
  content- i idempotency-addressed oraz odczytujące profile w stabilnym
  porządku.
- Zablokować zapis JPEG-ów, pikseli, symboli, OCR, payoutów, sekwencji,
  identyfikatorów lokalnych kotwic i klucza `game_id`; `source_game_ref` nie
  może stać się FK ani wejściem do `GameStorageRouter`.
- Udowodnić testami niezmienność payloadu, walidację danych, retry z tym samym
  kluczem i konflikt innego polecenia, deduplikację checksumy, kolejność
  wersji oraz brak zależności od routingowego data plane.

## Out of scope

- API, OpenAPI, UI, tworzenie gry, worker i resolver/preflight (G03/G04).
- Automatyczne kwalifikowanie, aktywacja, replay lub rollback kandydata (G07).
- Import, pilot Mumie/Gang i pomiar korekt (G05), acceptance (G08).
- Migracja istniejących profilów lokalnych, zmiana v1/v1.1, plików corpusów
  lub partycji `game_data_v2`.

## Acceptance criteria

- [x] Migracja ma następcę aktualnego head, tworzy tylko globalne tabele
  control plane i bezpiecznie odrzuca downgrade z zapisanymi danymi.
- [x] Wersja profilu zawiera rodzinę, topologię, metadane geometrii i ramki,
  stan dowodów oraz checksumę; nie może zawierać zakazanego payloadu.
- [x] Dowód zachowuje checksummowaną proweniencję bez game routingu i nie może
  powodować automatycznej akceptacji ani aktywacji.
- [x] Ten sam retry zwraca ten sam rekord, a inny command pod tym samym kluczem
  daje stabilny konflikt; identyczny profil nie dostaje nowego numeru wersji.
- [x] Testy, lint, kontrola typów i audyt Astra Medium potwierdzają zakres.

## Technical notes

Treść profilu i dowody są append-only. Kandydat ma numer globalny rosnący monotonicznie;
integralność polecenia stanowi SHA-256 kanonicznego payloadu. Najpierw
repozytorium sprawdza receipt idempotency, potem istniejący checksum profilu,
a dopiero na końcu tworzy nowy rekord. Powtórzenie nie może tworzyć nowego
numeru. Równoległy konflikt ograniczeń jest przedstawiany jako kontrolowany
błąd retry, nigdy jako drugie znaczenie tej samej wersji. Trigger bazy dopuści
w przyszłości jedynie przejścia stanu `candidate → active/rejected` oraz
`active → retired`, jeśli cały snapshot pozostaje identyczny; G06 nie wystawia
jeszcze operacji zmiany stanu.

`geometry_template`, `frame_appearance` i `evidence_summary` muszą być
kanonicznymi obiektami JSON z kontraktowymi polami liczbowymi i tekstowymi;
walidator domenowy odrzuca klucze i wartości sugerujące obraz, piksele lub
semantykę gry. Baza pilnuje rodzaju JSON i checksum, a nie zastępuje pełnej
walidacji struktury.

Przykład: poprawka Mumii może stworzyć kandydata z
`source_game_ref="mummies"` i metrykami dowodu. Ten wpis nie ma `game_id`, nie
uruchamia routera i nie może zostać użyty przez Gang bez późniejszej lokalnej
weryfikacji G03 oraz kwalifikacji G07.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/storage/models.py` — nowe
  modele globalnego control plane.
- Nowe: `services/api/src/game_predictor_api/domain/global_geometry_library.py`
  — typy, kanonizacja i walidacja kontraktu.
- Nowe: `services/api/src/game_predictor_api/storage/global_geometry_library_repository.py`
  — idempotentna persystencja.
- Nowe: `services/api/alembic/versions/0115_shape_geometry_v2_global_library.py`
  — migracja.
- Nowe: testy domeny, repozytorium i migracji G06.
- Istniejące: `ai_docs/architecture/DATA_MODEL.md`,
  `ai_docs/process/DECISION_LOG.md`, `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Poprawny kandydat 3 × 3 / 3 × 5 → kanoniczny checksum i status `candidate`.
- Obraz, pixels, OCR, symbol, payout, `game_id`, sekwencja lub kotwica w
  payloadzie → błąd kontraktu bez zapisu.
- Ten sam `idempotency_key` i command → istniejący rekord; ten sam klucz i
  inny command → kontrolowany konflikt.
- Druga prośba o identyczny checksum → istniejący profil oraz brak nowego
  numeru; różny poprawny checksum → następny numer.
- Dwie wersje w tej samej rodzinie/topologii w stabilnym sortowaniu → malejąco
  po `profile_number`; brak wywołania `GameStorageRouter`.
- SQL offline upgrade/downgrade → tabele, indeksy i constrainty są obecne;
  downgrade z rekordem → jawne odrzucenie.

## Verification

```powershell
# C:\Users\tuszy\.codex\worktrees\shape-geometry-v2\game_predicotr
# timeout: maks. 120 s na komendę
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m pytest services\api\tests\test_global_geometry_library_domain.py services\api\tests\test_global_geometry_library_repository.py services\api\tests\test_global_geometry_library_migration.py -q --basetemp .runtime\pytest-shape-v2-g06
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m ruff check services\api\src\game_predictor_api\domain\global_geometry_library.py services\api\src\game_predictor_api\storage\global_geometry_library_repository.py services\api\src\game_predictor_api\storage\models.py services\api\tests\test_global_geometry_library_domain.py services\api\tests\test_global_geometry_library_repository.py services\api\tests\test_global_geometry_library_migration.py
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m mypy --no-incremental --follow-imports=skip services\api\src\game_predictor_api\domain\global_geometry_library.py services\api\src\game_predictor_api\storage\global_geometry_library_repository.py
```

## Risks / open questions

- G06 nie ustanawia wartości progów jakości. Puste liczniki pozostają dowodem
  niekwalifikującym i G07 rozstrzyga politykę aktywacji.
- Jedna aktywna wersja jest chroniona na poziomie schematu, lecz G06 nie
  wystawia operacji jej zmiany. Pozostaje to przyszłą, atomową operacją G07.

## Outcome

Wypełnia agent po pracy.

### Changed

- Dodano migrację 0115 oraz modele i repozytorium publicznej biblioteki
  globalnych kandydatów geometrii, descriptorowych dowodów i receiptów retry.
- Dodano zamknięty, checksummowany kontrakt descriptorów. Chroni dane gier
  przed obrazami, semantyką i `game_id`, obsługuje proweniencję `777`, wymaga
  wypukłego quada w kolejności rdzenia G02 oraz zwraca głęboko niezmienne
  snapshoty.
- Dodano manifest własności v2, który klasyfikuje nowe tabele jako `shared`
  bez modyfikacji zamrożonego manifestu v1 i partycji gier.

### Verification results

- 90 testów G06, kontroli manifestu i offline SQL migracji przeszło.
- Ruff dla całego zmienionego zakresu przeszedł.
- Ograniczony mypy nowych modułów przeszedł; pozostaje wyłącznie wcześniejsze
  ostrzeżenie o nieużytym override ONNX w konfiguracji projektu.
- Astra Medium: pierwszy audyt wykrył pięć P2, re-audyt dwa P2; wszystkie
  naprawiono z regresjami. Końcowy re-audyt nie wykazał P0–P3.

### Not completed

- Nie dodano API, UI, resolvera, preflightu, kwalifikatora ani aktywacji;
  należą do G03 i G07.

### Documentation updates

- Zaktualizowano `DATA_MODEL.md`, `GAME_DATA_V2_OWNERSHIP.md`,
  `VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`, `DECISION_LOG.md` (D-422) i
  `CURRENT_STATE.md`.

### Recommended next task

- G03 — resolver i pion aplikacji.
