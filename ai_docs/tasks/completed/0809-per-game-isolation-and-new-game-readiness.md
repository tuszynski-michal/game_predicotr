---
title: TASK-0809 — kontrola izolacji danych per gra i gotowości na nową grę
status: done
last_updated: 2026-10-02
---

# TASK-0809 — kontrola izolacji danych per gra i gotowości na nową grę

## Status

`done`

## Goal

Test PostgreSQL dowodzi, że nowa gra utworzona obok dużej gry działa od
pierwszego importu (komplet partycji, stan kompletności, bramka, komórki,
wyszukiwarka) i że jej zapytania nie dotykają partycji innej gry; raport w
`ai_docs/quality/` opisuje stan izolacji na bazie deweloperskiej.

## Context

Wymaganie operatora z 2026-10-02: dane każdej gry osobno, aplikacja ma
działać prawidłowo od razu po dodaniu pierwszej nowej gry. Kontrola bazy
(tylko `SELECT`) pokazała 63 tabele gry partycjonowane `LIST (game_id)` z
RLS; osobna baza per gra została odrzucona przez operatora. TASK-0807 dodał
kolumny stanu na `source_images` (migracja `0139`) i bramkę — trzeba
potwierdzić, że nowa gra dostaje je automatycznie.

## Dependencies / entry conditions

- TASK-0807 w repo (`v1.7.145`), head Alembic w kodzie `0139`.
- Zadanie nie zmienia schematu. Każda potrzebna zmiana schematu jest
  zgłaszana, nie wykonywana.

## Recommended execution

`claude-sonnet-5-5`, reasoning `high`. Testy i raport bez zmian schematu na
istniejącym lifecycle magazynu gry. Eskalacja do `claude-opus-5-5` `high`,
jeżeli test ujawni przeciek między grami albo brak kolumn `0139` w partycji
nowej gry. Audyt zawieszony decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md` (sekcja planu V3)
- `ai_docs/delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` (reguła
  „Izolacja danych per gra”, TASK-0809)
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/tasks/0807-image-geometry-completeness-gate.md` (albo jego kopia
  w `completed/`)

## Scope

- Test PG na bazie `*_test`: dwie gry; pierwsza zasiana większą liczbą
  wierszy, druga utworzona istniejącym lifecycle magazynu gry po migracji
  `0139`.
- Asercje dla nowej gry: komplet partycji z manifestu i aktywna lokalizacja;
  partycja `source_images` ma kolumny i ograniczenia `0139`; zapis zdjęcia
  z kompletem siatek daje `geometry_complete` i komórki; zdjęcie 8/9 daje
  `geometry_incomplete` i brak komórek; raport kompletności nowej gry nie
  zawiera danych pierwszej gry.
- Asercje planu zapytania (`EXPLAIN (FORMAT JSON)`), że zapytania nowej gry
  w czterech ścieżkach — raport kompletności, przeliczenie stanu / bramka,
  materializacja komórek, projekcja wyszukiwarki — odwołują się wyłącznie
  do partycji tej gry (żadna relacja partycji pierwszej gry w planie).
  Dopuszczalne jest sprawdzenie reprezentatywnego zapytania każdej ścieżki
  pobranego z kodu repozytorium (to samo SQL / ten sam `select`), nie
  przepisanego ręcznie.
- Test strażniczy: model ORM z kolumną `source_image_id`,
  `recognized_board_id` albo `review_item_id` musi należeć do tabel klasy
  `game` bieżącego manifestu magazynu (sprawdź, czy istniejący test
  własności tabel już to gwarantuje; jeżeli tak, tylko to udokumentuj).
- Raport `ai_docs/quality/PER_GAME_ISOLATION_20261002.md`: wynik testów,
  rozmiary partycji per gra z bazy deweloperskiej (tylko `SELECT`), ocena
  tabel współdzielonych rosnących z liczbą zdjęć
  (`image_pipeline_stage_results`, `image_pipeline_terminal_manifests`,
  `image_file_executions`): klucze, typowe zapytania, czy filtr po grze
  istnieje, czy wymagają podziału — rekomendacja bez wykonania.

## Out of scope

- Zmiany schematu, migracje, zapis do bazy deweloperskiej.
- Osobna baza per gra. Benchmarki i testy obciążeniowe.

## Acceptance criteria

- [x] Test PG nowej gry przechodzi; partycja ma kolumny `0139`.
- [x] Cztery ścieżki mają asercję planu bez partycji innej gry.
- [x] Test strażniczy istnieje albo wskazano istniejący równoważny.
- [x] Raport w `ai_docs/quality/` z listą odstępstw albo stwierdzeniem ich
      braku; proponowane zmiany schematu wypisane osobno.
- [x] Brak zapisu do bazy deweloperskiej.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

Wzorce: `services/api/tests/integration/test_image_geometry_completeness_gate.py`
(zasiewanie zdjęć i plansz, wywołanie przeliczenia i bramki),
istniejące testy lifecycle partycji i routingu w
`services/api/tests/integration/` (tworzenie gry i partycji rolą
właściciela). Rola aplikacyjna i RLS: zapytanie bez
`GameStorageRouter.bind` ma kończyć się błędem, nie pustym wynikiem — dodaj
jedną asercję tego zachowania dla nowego repozytorium stanu kompletności.
Nazwy partycji są deterministyczne (`gpv2_<prefiks gry>_<hash tabeli>`);
asercja planu porównuje nazwy relacji z planu z partycjami drugiej gry
pobranymi z `pg_inherits`.

## Expected files

- Nowe (proponowane):
  `services/api/tests/integration/test_per_game_isolation_new_game.py`,
  `ai_docs/quality/PER_GAME_ISOLATION_20261002.md`.

## Test cases

- Nowa gra po `0139`: partycje, kolumny, stan `geometry_complete` i
  `geometry_incomplete`, komórki tylko dla zdjęcia dopuszczonego.
- `EXPLAIN` czterech ścieżek: brak partycji pierwszej gry.
- Zapytanie repozytorium stanu bez wiązania gry → błąd.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_per_game_isolation_new_game.py
.\.venv\Scripts\python.exe -m ruff check services/api
```

Limit 300 s dla testu PG, 120 s dla pozostałych; testy PG pojedynczo.
Testy są planowane, nie zaliczone.

## Risks / open questions

- Tabele współdzielone pipeline nie są partycjonowane po grze; raport ma
  rozstrzygnąć, czy to problem skali, czy tylko obserwacja.

## Outcome

Status: `done` (poza commitem, `CURRENT_STATE.md` i przeniesieniem pliku, które
należą do orkiestratora). Test PostgreSQL i raport są gotowe; test nie ujawnił
przecieku między grami ani braku kolumn `0139` na partycji nowej gry, więc nie
było podstaw do eskalacji ani zmian w kodzie produkcyjnym.

### Changed

- Nowy `services/api/tests/integration/test_per_game_isolation_new_game.py`
  (12 testów, w tym 2 bez PostgreSQL): baza `*_test` z prawdziwą rolą
  aplikacyjną LOGIN (`_application_role_database`), „duża” gra z czterema
  zaimportowanymi zdjęciami i „nowa” gra utworzona potem lifecycle'em
  partycji. Asercje: komplet 63 partycji nowej gry z `pg_inherits`, RLS na
  rodzicach, wpisy `game_storage_table_manifest`, receipt lifecycle i aktywna
  lokalizacja; kolumny, CHECK-i i indeksy `0139` na partycji `source_images`
  (zgodne z rodzicem) oraz ich egzekwowanie; stany `geometry_complete` /
  `geometry_incomplete` i komórki (135 / 0) po pierwszych importach nowej gry;
  raport kompletności bez danych dużej gry; plany `EXPLAIN` czterech ścieżek
  zbudowane z instrukcji zebranych z prawdziwych wywołań repozytoriów
  (`before_cursor_execute`); błąd zamiast pustego wyniku bez wiązania gry;
  strażnik własności tabel (ORM z `source_image_id` / `recognized_board_id` /
  `review_item_id` musi być tabelą klasy `game` manifestu v4; istniejący test
  tylko klasyfikuje wszystkie tabele, więc strażnik jest nowy).
- `services/api/tests/integration/test_virtual_deferred_resolution_postgres.py`:
  `_seed` dostał parametr `sequence_base` (domyślnie 100, bez zmiany
  zachowania), bo kilka zdjęć w jednej grze wymaga rozłącznych numerów
  sekwencji.
- Nowy `ai_docs/quality/PER_GAME_ISOLATION_20261002.md`: wyniki, rozmiary
  partycji z bazy deweloperskiej, ocena trzech tabel współdzielonych,
  odstępstwa i proponowane zmiany schematu.

### Verification results

- `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 pytest
  services/api/tests/integration/test_per_game_isolation_new_game.py`: 12
  passed (≈31 s). Bez zmiennej: 2 passed, 10 skipped.
- `pytest services/api/tests/integration/test_image_geometry_completeness_gate.py`
  (istniejący plik używający zmienionego `_seed`): 7 passed (77 s).
- `ruff check services/api`: czysto; `ruff format --check` obu plików
  testowych: czysto.
- Baza deweloperska: tylko `SELECT` w transakcji tylko do odczytu (Alembic head
  tam: `0138`); brak zapisu, migracji i backfillu.

### Orchestrator closure (2026-10-02)

- Ustalenie o słabym CHECK `ck_source_images_geometry_exception` (wyjątek z
  powodem `NULL` przechodził przez logikę trójwartościową) poprawione przed
  wdrożeniem: migracja `0139` i model ORM wymagają teraz jawnie
  `geometry_exception_reason IS NOT NULL` i `geometry_exception_by IS NOT
  NULL`; test nowej gry sprawdza odrzucenie powodu `NULL` (12 testów
  przechodzi, test bramki 7/7).
- Tabele współdzielone pipeline zostają bez podziału (rekomendacja raportu).

### Not completed

- Commit, `CURRENT_STATE.md`, przeniesienie pliku do `completed/` (orkiestrator).
- Plany zapytań nie były mierzone na danych skali 777; pruning partycji nie
  zależy od statystyk, ale kosztów nie sprawdzano.
- Migracja `0139` na bazie deweloperskiej (krok przejścia operatora).

### Documentation updates

- `ai_docs/quality/PER_GAME_ISOLATION_20261002.md` (nowy). Bez zmian w
  `GAME_DATA_V2_OWNERSHIP.md`, `DECISION_LOG.md` i planie (do decyzji
  orkiestratora).

### Recommended next task

- Opcjonalnie: migracja zaostrzająca `ck_source_images_geometry_exception`
  (CHECK przepuszcza `geometry_exception` z `NULL` w `geometry_exception_reason`
  z powodu logiki trójwartościowej; aplikacja waliduje powód, więc niski
  priorytet) — do połączenia z kolejną migracją `source_images`.
- Podział tabel współdzielonych pipeline'u: nie teraz (uzasadnienie w raporcie).
