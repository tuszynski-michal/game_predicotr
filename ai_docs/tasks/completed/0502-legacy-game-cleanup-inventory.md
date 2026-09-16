---
title: TASK-0502 — Inwentaryzacja i preview odchudzenia starej gry
status: done
last_updated: 2026-09-07
---

# TASK-0502 — Inwentaryzacja i preview odchudzenia starej gry

## Status

`done`

## Goal

Utworzyć powtarzalny, wyłącznie odczytowy preview wszystkich danych i plików,
które należy zachować, usunąć albo zablokować przed odchudzeniem gry
`777 v0.1`.

## Context

Stara gra ma pozostać tymczasowym archiwum wyszukiwania plansz. Zakresy
`1–19809` oraz `19810–45162` zostaną docelowo usunięte w całości, a dla
pozostałych numerów trzeba zachować wyszukiwanie po symbolach i obraz całej
planszy. Preview musi powstać przed jakąkolwiek operacją destrukcyjną.

## Dependencies / entry conditions

- Gra źródłowa: `80f3c7ec-6110-4e20-a263-2675ee5b15d6`, kod `777`, nazwa
  `777 v0.1`.
- Chroniona nowa gra: `03d64bfe-4d29-47dd-9153-76bd99b3b5d9`, kod
  `new-siedem`.
- Katalog `C:\Users\user\Documents\777` pozostaje poza skanowaniem i zmianami.
- TASK-0501 z wcześniejszego planu zajmuje już numer, dlatego pierwszy task
  Planu A otrzymuje numer 0502 bez zmiany zakresu.

## Recommended execution

`gpt-5.6-sol` z poziomem `high`: task obejmuje analizę dużego grafu danych i
artefaktów, ale nie wykonuje mutacji. Przed przyjęciem preview jako wejścia do
cleanupu wymagany jest niezależny review w `gpt-6-astra high`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- Powtarzalny skrypt read-only generujący kanoniczny preview w JSON.
- Inwentaryzacja tabel, rekordów, relacji, stagingów, modeli, raportów, cache i
  zarządzanych plików starej gry.
- Klasyfikacja `preserve`, `delete`, `shared` albo `blocked` wraz z powodem.
- Osobne zestawienie zakresu 1–45162 i plansz pozostających w archiwum.
- Sprawdzenie dostępności i checksum obrazów plansz pozostających w wynikach
  wyszukiwania.
- Raport wymaganej kopii bezpieczeństwa i przestrzeni przejściowej.

## Out of scope

- Usuwanie, kwarantanna, migracja, backfill lub zmiana statusu gry.
- Zmiana algorytmu wyszukiwania albo silnika importu.
- Odczyt lub zapis katalogu `C:\Users\user\Documents\777`.
- Globalny GC, VACUUM albo restart usług.

## Acceptance criteria

- [x] Preview jednoznacznie identyfikuje obie gry i odmawia pracy dla innego
      scope'u.
- [x] Każda wykryta grupa danych ma klasyfikację i uzasadnienie.
- [x] Zasoby współdzielone nie trafiają do kategorii `delete`.
- [x] Zakres 1–45162 jest raportowany oddzielnie od zachowywanego archiwum.
- [x] Obrazy zachowywanych plansz mają raport obecności oraz zgodności checksum.
- [x] Wynik nie zawiera sekretów ani binarnych danych i jest deterministyczny
      dla niezmienionego stanu.
- [x] Skrypt nie wykonuje DML, DDL, blokującego skanowania katalogu operatora ani
      operacji na uruchomionych jobach.

## Technical notes

Preview korzysta z aktualnego schematu PostgreSQL oraz tych samych invariantów
bezpiecznych ścieżek co operacyjny resolver assetów. Zapytania są ograniczone
czasowo i agregują dane po stronie bazy; skrypt nie materializuje milionów
rekordów. Pliki są klasyfikowane przez jawne referencje bazy i manifestów, a
nie przez wyszukiwanie UUID w treści.

Wynik zawiera fingerprint wejścia oraz sekcje: scope, database, managedFiles,
boardSearchArchive, blockers, backupRequirements i totals. Fingerprint nie jest
zgodą na cleanup; przyszła operacja musi ponownie wygenerować preview i uzyskać
osobne potwierdzenie użytkownika.

## Expected files

- Nowe: `scripts/preview_legacy_game_cleanup.py` — read-only generator preview.
- Nowe: test skryptu w `services/api/tests/`.
- Nowe: raport odbiorczy w `ai_docs/quality/` bez danych binarnych.
- Istniejące: `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Właściwa stara i chroniona gra zwracają deterministyczny preview.
- Inne UUID, brak gry albo zamienione role kończą się jawnym błędem.
- FK lub manifest wskazujący zasób z chronionej gry klasyfikuje go jako shared
  albo blocker, nigdy delete.
- Brak obrazu i niezgodna checksuma są raportowane jako blokada archiwizacji.
- Aktywny job starej gry jest blockerem następnego etapu, ale nie jest zmieniany.
- Dwa odczyty niezmienionej bazy dają ten sam fingerprint.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_legacy_game_cleanup_preview.py
.venv\Scripts\python.exe -m ruff check scripts/preview_legacy_game_cleanup.py services/api/tests/test_legacy_game_cleanup_preview.py
.venv\Scripts\python.exe -m mypy --follow-imports=skip scripts/preview_legacy_game_cleanup.py
npm run format:check
```

Komendy otrzymają timeout do 120 sekund. Testy planowane nie są wynikami;
rzeczywiste nazwy modułów należy uzupełnić po implementacji.

## Risks / open questions

- Pełne sprawdzenie setek tysięcy obrazów może wymagać wznowienia lub
  porcjowania; task nie może obchodzić tej kontroli próbką.
- Istniejący graf cleanupu może nie obejmować najnowszych tabel. Preview musi
  wykryć brak klasyfikacji jako blocker.

## Outcome

### Changed

- Dodano przypięty do obu znanych gier skrypt read-only z limitem zapytań,
  dynamicznym inwentarzem tabel, relacji FK i kolumn ścieżek.
- Zakresy wyszukiwania są rozdzielane na `1–45162` oraz zachowywane
  `45163–499995`; nierozstrzygnięte zależności pozostają `blocked`.
- Pełna kontrola plików działa keysetowo, z ograniczoną pamięcią i ponownym
  SHA-256 każdego zachowywanego obrazu.
- Zapisano kanoniczny JSON oraz raport odbiorczy. Żadnych danych nie usunięto.

### Verification results

- `pytest`: 7 testów przeszło.
- `ruff`: zmienione moduły przeszły.
- `mypy --follow-imports=skip`: skrypt przeszedł; zwykły mypy dociera do
  wcześniejszego błędu `redundant-cast` w niezwiązanym
  `image_import_geometry_guard.py:672`.
- Pełny preview: 369 554/369 554 plików istnieje i ma zgodną checksumę,
  25 989 394 598 B; fingerprint
  `2250d49f71cd937218222dae3dd62f108ffd7cc5992f3eb4a315a69ad19d19e4`.
- `npm run format:check`: uruchomiono; zgłasza wcześniejsze ostrzeżenia w 13
  plikach aplikacji, w tym chronionym `apps/admin/next-env.d.ts`. Żaden plik
  TASK-0502 nie należy do globu tego polecenia i nie został przez nie zmieniony.

### Not completed

- Nie wykonano migracji archiwum, backupu ani cleanupu. Preview pozostaje
  zablokowany przez `ARCHIVE_MIGRATION_REQUIRED` i wymaga niezależnego review
  `gpt-6-astra high` przed użyciem jako wejście operacji destrukcyjnej.

### Documentation updates

- Dodano `LEGACY_GAME_CLEANUP_INVENTORY.md` i zaktualizowano `CURRENT_STATE.md`.

### Recommended next task

- TASK-0503 — wyszukiwanie starej gry niezależne od operacyjnego review.
