---
title: TASK-1190 — Podgląd raportu importu przy zajętej blokadzie gry
status: done
last_updated: 2026-11-12
---

# TASK-1190 — Podgląd raportu importu przy zajętej blokadzie gry

## Status

`done`

## Goal

Podgląd raportu przed importem plansz (`POST /api/v1/admin/image-imports/browser-selections/{upload_id}/preflight`)
działa równolegle z zapisami przeglądu symboli tej samej gry, a zajęta blokada
sekwencji kończy się czytelnym błędem 409 zamiast HTTP 500.

## Context

Zgłoszenie operatora z 2026-11-12: dla Mumie a2 (`mumie-aktu2`, gra
`246a1f54-…`) po odświeżeniu importu panel Admin pokazywał „Nie udało się
przygotować raportu przed importem plansz.”. Diagnoza na działającym API:

- endpoint zwracał zwykłe `Internal Server Error` (HTTP 500), a panel zamienia
  błąd bez `code`/`message` na tekst zastępczy;
- traceback: `psycopg.errors.LockNotAvailable` na `pg_advisory_xact_lock` w
  `validate_ordinary_staging` (`storage/source_replacement_admission.py`), po
  `lock_timeout='5s'` ustawianym przez `SourceReplacementRepository.bind`;
- podgląd brał **wyłączną** blokadę własności sekwencji gry, choć tylko czyta,
  a w tym czasie trwały zapisy decyzji komórek symboli (106 jobów
  `super_game_series_derive` z powodem `symbol_cells` między 14:05 a 15:26
  czasu lokalnego), które trzymają blokadę **współdzieloną**
  (`cell_decision_lock_mode`);
- po ustaniu zapisów to samo żądanie zwracało 200.

## Dependencies / entry conditions

Brak. Poprawka niezależna od otwartych planów; bez migracji.

## Recommended execution

Claude Opus 5.5, reasoning standard — mała poprawka jednego pionu API z
testem regresyjnym; operator zlecił ją bezpośrednio w rozmowie („napraw
tutaj”). Bez audytu krzyżowego (brak planu z kolumną `Dodatkowy review`).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- Podgląd raportu waliduje zwykły staging pod blokadą `SHARED`; start importu
  i preflight geometrii zostają przy `EXCLUSIVE`.
- Przekroczenie `lock_timeout` przy tej blokadzie daje `SourceReplacementError`
  `IMAGE_IMPORT_SEQUENCE_OWNERSHIP_BUSY` (HTTP 409, komunikat po polsku), także
  na ścieżce startu.

## Out of scope

- Ścieżka zamiennika (`validate_staging`) — pisze stan dopuszczenia, zostaje
  przy blokadzie wyłącznej.
- Globalne mapowanie `LockNotAvailable` na 409 dla wszystkich endpointów.
- Zmiany UI: Admin już pokazuje `message (code)` z odpowiedzi błędu.
- Duplikat nazwy „Mumie a2” (`mumie-a2` i `mumie-aktu2`) w katalogu gier.

## Acceptance criteria

- [x] Podgląd przy trzymanej blokadzie `SHARED` innej sesji zwraca raport.
- [x] Podgląd przy trzymanej blokadzie `EXCLUSIVE` zwraca 409
      `IMAGE_IMPORT_SEQUENCE_OWNERSHIP_BUSY`, nie 500.
- [x] Start importu nadal waliduje pod blokadą wyłączną.
- [x] Inne błędy sterownika nie są maskowane.
- [x] Suma kontrolna raportu się nie zmienia (ten sam `preflightChecksumSha256`).

## Technical notes

`validate_ordinary_staging(..., lock_mode=EXCLUSIVE)` przyjmuje tryb blokady;
`SqlAlchemyJobRepository.validate_replacement_staging(..., preview=False)`
wybiera `SHARED` dla `preview=True`; `JobService` i router przekazują flagę
tylko z `preview_ready_browser_import`. Rozpoznanie timeoutu: istniejący
`is_lock_not_available` (SQLSTATE 55P03). Blokada jest re-entrant i nie
podnosi trybu; start bierze `EXCLUSIVE` przed swoim wywołaniem
`browser_preflight`, więc nie ma próby podniesienia trybu. Kontrakt OpenAPI bez
zmian (nowy jest tylko kod błędu w istniejącej odpowiedzi 409).

## Expected files

- `services/api/src/game_predictor_api/storage/source_replacement_admission.py` — `validate_ordinary_staging`, `SEQUENCE_OWNERSHIP_BUSY`
- `services/api/src/game_predictor_api/storage/job_repository.py` — `SqlAlchemyJobRepository.validate_replacement_staging`
- `services/api/src/game_predictor_api/application/jobs.py` — `JobService.validate_replacement_staging`
- `services/api/src/game_predictor_api/api/image_imports.py` — `replacement_admission`, `browser_preflight`, `preview_ready_browser_import`
- testy: `services/api/tests/test_source_replacement_admission.py`, `services/api/tests/test_replacement_browser_api.py`, `services/api/tests/integration/test_source_replacement_admission_postgres.py`

## Test cases

- Jednostkowo: timeout 55P03 → `IMAGE_IMPORT_SEQUENCE_OWNERSHIP_BUSY`; inny
  SQLSTATE → `OperationalError` bez zmian; `lock_mode=SHARED` trafia do blokady.
- API: podgląd przekazuje `preview=True`, start — `False`.
- PostgreSQL (osobna baza testowa): SHARED+SHARED przechodzi; SHARED trzymany +
  EXCLUSIVE żądany → busy; EXCLUSIVE trzymany + SHARED żądany → busy.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_source_replacement_admission.py services/api/tests/test_replacement_browser_api.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_source_replacement_admission_postgres.py -k lock_contention -q
```

## Outcome

Commit: v1.7.617 (hash dopisuje kolejny commit).

- Podgląd raportu (`preview_ready_browser_import`) przekazuje `preview=True`;
  zwykły staging jest walidowany pod blokadą `SHARED`. Start importu i
  preflight geometrii bez zmian (`EXCLUSIVE`).
- Timeout blokady (SQLSTATE 55P03) w `validate_ordinary_staging` →
  `SourceReplacementError` `IMAGE_IMPORT_SEQUENCE_OWNERSHIP_BUSY` (HTTP 409,
  komunikat po polsku); inne błędy sterownika przechodzą bez zmian.
- Weryfikacja:
  - `test_source_replacement_admission.py` + `test_replacement_browser_api.py`:
    12 passed;
  - PostgreSQL na jednorazowej bazie (`-k lock_contention`): 3 passed;
  - pokrewne testy API (11 plików): 210 passed, 2 failed — te same 2 testy
    (`test_lateral_managed_reprocess.py::test_public_import_entrypoints_cannot_drop_guard_history[browser]`,
    `test_page_geometry_overrides.py::test_slot_decisions_survive_retry_and_change_revision_without_changing_quads`)
    padają identycznie na czystym `main` `33e9197e`; zastany błąd poza
    zakresem;
  - ruff check/format zmienionych plików PASS; mypy zmienionych modułów bez
    nowych błędów (2 zastane w niezmienionym `schemas/source_lattice_geometry.py`);
    `openapi:check` i `code-map:check` PASS.
- Odbiór na danych operatora (nowy kod w osobnym procesie, tylko odczyt,
  staging `189939e3…` Mumie a2): przy obcej blokadzie `SHARED` podgląd zwrócił
  200 z niezmienionym `preflightChecksumSha256` `10220d5f…`; przy obcej
  `EXCLUSIVE` 409 `IMAGE_IMPORT_SEQUENCE_OWNERSHIP_BUSY` po ~7,7 s.
- Nie wykonano: restartu API (wymaga operatora po scaleniu), audytu krzyżowego
  (niewymagany), scalenia do `main` (wymaga zgody).
