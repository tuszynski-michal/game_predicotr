# TASK-0945 — Migracja 0153, status `reverted` i cofnięcie korekty slotu odroczonego

## Status

`todo`

## Goal

Operacja aplikacyjna cofa ostatnie ręczne rozstrzygnięcie odroczonego slotu (przypadek B) w jednej transakcji, przywracając stan sprzed zapisu i zapisując audyt z migawką.

## Context

Operator chce cofać pomyłkowe zapisy z ekranu „Korekta cięcia siatki”. Przykład: slot `378a273f-…` (Mumie, sekwencja 69004) rozstrzygnięty 2026-10-09 08:39:41 UTC. Plan: `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, sekcje „Model domenowy”, „Przypadek B”, „Rewizja źródła `reverted`”, „Audyt i powtórzenia”.

## Dependencies / entry conditions

- Head migracji `0152_super_game_series` na gałęzi integracyjnej; sprawdź, czy nie ma nowszej (kolizje numerów).
- Operator wykonuje migrację na swojej bazie dopiero w TASK-0951.

## Recommended execution

`claude-opus-5-5`, reasoning `high`: migracja, zmiana semantyki „latest” i fizyczne usuwanie grafu wierszy. Eskalacja: niejednoznaczny wpływ na bramkę kompletności (D-484/D-485) → zatrzymaj i zapytaj operatora. Review: Codex `gpt-6-astra`, `high`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — D-462, D-484, D-485, D-488

## Scope

- Migracja `0153_geometry_correction_revert` (schemat `game_data_v2`, wzorzec strażnika `0145_neural_page_geometry_binding.py:44`):
  - `ck_image_source_geometry_revisions_state`: dodaj `reverted`;
  - UNIQUE `(source_image_id, geometry_checksum_sha256)` → indeks unikalny częściowy `WHERE status <> 'reverted'`;
  - `ck_image_board_geometry_review_events_action`: dodaj `geometry_reverted`;
  - `ck_image_symbol_review_events_action`: dodaj `geometry_reverted`;
  - `image_symbol_review_events.previous_assignment_source` (nullable, ten sam CHECK wartości co `assignment_source` komórki);
  - `image_board_geometry_pending`: status `rejected`, kolumny `rejection_reason` (`cropped`, `blurred`, `other`), `rejection_note`, `rejected_at`, `rejected_by`; aktualizacja `ck_image_board_geometry_pending_lifecycle` (W7; logika w TASK-0949, w tym tasku tylko schemat i model);
  - tabela `image_geometry_correction_reverts` (kolumny z planu; UNIQUE `(game_id, idempotency_key)`; indeks `(game_id, import_job_id, created_at DESC)`; brak FK do usuwanych wierszy; FK do gry i joba).
  - Zaktualizuj `storage/models.py`, bazowy schemat testów migracji, jeśli wymagany, oraz strażnika schematu startowego (wymagana rewizja `0153`).
- Semantyka „latest” rewizji źródła (pomijaj `reverted`) we wszystkich miejscach:
  `storage/virtual_grid_geometry_repository.py` (`_pending_context` ~1893, `legacy_conversion_plan` ~721),
  `storage/image_grid_review_repository.py` (`_pending_statement` ~406),
  `storage/image_geometry_completeness_repository.py` (~108, ~237, ~281),
  `storage/image_geometry_completeness_state_repository.py` (`_REPOINT_PLAN_SQL` ~470),
  `storage/grid_shadow.py` (~79),
  `storage/superseded_import_image_removal_repository.py` (~716).
  Numeracja w `storage/image_geometry_v2_repository.py:155` nadal liczy wszystkie wiersze. Deduplikacja po checksumie (`image_geometry_v2_repository.py:140`, worker `services/worker/src/game_predictor_worker/images/pipeline_store.py:295` i `:420`) pomija `reverted`.
- `previous_assignment_source` zapisywane przez każde tworzenie zdarzenia komórki (`_apply_symbol_cell_review_transition` i ścieżki `geometry_invalidated`/`board_synchronized`).
- Nowy moduł aplikacyjny (proponowany) `application/geometry_correction_reverts.py`: `GeometryCorrectionRevertService` z metodami `list_recent(game_id, import_job_id, limit)`, `preview(…, board_geometry_revision_id)`, `revert(…, idempotency_key, expected_geometry_revision, expected_resolution_revision, actor)`; port repozytorium; czysta funkcja domenowa `evaluate_revert_eligibility(facts) -> RevertBlockingReason | None` w `domain/geometry_correction_reverts.py` (proponowane).
- Repozytorium (proponowane) `storage/geometry_correction_revert_repository.py`: fakty dla warunków, migawka, usunięcia, przywrócenie slotu, status `reverted`, odwrotne przepięcie (nowy planner + istniejące `apply_board_repoint`), liczniki, wyszukiwarka, bramka kompletności, wiersz audytu. Dla przypadku A (`kind = board_revision`) w tym tasku `revert` zwraca `GEOMETRY_REVERT_NOT_SUPPORTED` (implementacja w TASK-0946), ale `list_recent` i warunki wspólne obejmują oba rodzaje.
- Strażnik powtórzeń: `_find_replay` (`application/virtual_grid_geometry.py:911`) zwraca 409 `GEOMETRY_CORRECTION_REVERTED`, gdy klucz należy do cofniętego zapisu.
- Punkt zapisu wersji wejścia supergry `geometry_correction_revert` w `SUPER_GAME_INPUT_WRITE_POINTS`.

## Out of scope

- Przypadek A (TASK-0946), HTTP (TASK-0947), UI (TASK-0948), wykonanie migracji na bazie operatora i cofnięcie 69004 (TASK-0951).

## Acceptance criteria

- [ ] Migracja `0153` przechodzi upgrade/downgrade na bazie `*_test`; downgrade odmawia, gdy istnieją wiersze `reverted` albo audytu (bez cichej utraty danych).
- [ ] Cofnięcie slotu przywraca stan sprzed zapisu: slot `pending` z wyzerowanymi polami rozstrzygnięcia, brak planszy/pozycji/komórek/rewizji planszy/manifestu/zdarzeń, rewizja źródła `reverted`, sąsiedzi wskazują poprzednią rewizję, kolejka przeglądu, status joba, wyszukiwarka, `count_projection`, `cell_count` i stan bramki zdjęcia równe stanowi sprzed zapisu (porównanie migawek w teście).
- [ ] Slot wraca do widoku `correction` z propozycją poprzedniej rewizji źródła.
- [ ] Każdy kod blokady z planu ma test odmowy bez zapisu.
- [ ] Ponowny zapis tej samej geometrii po cofnięciu tworzy nową rewizję źródła (nie wskrzesza `reverted`).
- [ ] Powtórzenie żądania cofnięcia z tym samym kluczem zwraca ten sam wynik; powtórzenie starego zapisu korekty → 409 `GEOMETRY_CORRECTION_REVERTED`.
- [ ] Istniejące testy bramki kompletności i korekty slotu przechodzą bez zmian asercji.

## Technical notes

- Kolejność blokad jak przy zapisie: `acquire_image_sequence_locks` → `source_images FOR UPDATE` → slot `FOR UPDATE` → plansza/pozycja.
- Warunki oceniaj po zablokowaniu, z faktów z bazy; nie ufaj danym klienta poza tokenami CAS.
- „Przed zapisem” dla sąsiadów: przepnij tylko plansze, które wskazują cofaną rewizję, mają `geometry_revision = 0`, nie są `rejected`, i których wpis slotu jest identyczny w obu rewizjach (porównanie jak `_REPOINT_PLAN_SQL` ~486); inna sytuacja → `GEOMETRY_REVERT_SHARED_SOURCE_REVISION`.
- `GEOMETRY_REVERT_SEQUENCE_OWNERSHIP`: wykryj zastąpienie (zdarzenie `superseded` innej pozycji tej sekwencji z czasem transakcji korekty lub późniejszym) i przejęcie komórek (komórki pozycji z `created_at` wcześniejszym niż transakcja korekty albo zdarzenie `board_synchronized` zmiany właściciela).
- `GEOMETRY_REVERT_IMAGE_ADMITTED`: zdjęcie `geometry_complete`/`geometry_exception`, a ocena bez cofanego slotu daje inny stan.
- `source_images.status`: `waiting_for_review`, gdy zdjęcie ma oczekujący slot albo pozycję `pending`; inaczej bez zmiany.
- Migawka: JSON wierszy w kolejności usuwania, kolumny jak w bazie (UUID i daty jako tekst ISO), `snapshot_checksum_sha256` z kanonicznego JSON (sortowane klucze).
- Nie maskuj błędów: konflikt FK lub `rowcount` ≠ oczekiwany → wyjątek i rollback całości.

## Expected files

- Nowe (proponowane): `services/api/alembic/versions/0153_geometry_correction_revert.py`, `services/api/src/game_predictor_api/domain/geometry_correction_reverts.py`, `services/api/src/game_predictor_api/application/geometry_correction_reverts.py`, `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py`, testy `services/api/tests/test_geometry_correction_reverts.py`, `services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py`.
- Zmieniane: `storage/models.py`, zapytania „latest” wymienione w Scope, `storage/image_geometry_v2_repository.py`, `services/worker/src/game_predictor_worker/images/pipeline_store.py`, `storage/image_symbol_review_repository.py` (`previous_assignment_source`), `application/virtual_grid_geometry.py` (`_find_replay`), `storage/super_game_input_version.py`, strażnik schematu.

## Test cases

- Rozstrzygnięty slot (baza: `test_virtual_deferred_resolution_postgres.py::_seed`) → cofnięcie → pełne porównanie stanu z migawką sprzed zapisu.
- Slot z symbolami D-488 na części komórek (bez pełnego rozstrzygnięcia) → cofnięcie usuwa komórki i zdarzenia.
- Każdy kod blokady: późniejsza weryfikacja symbolu, rozstrzygnięta pozycja, nowsza rewizja źródła, zastąpiona pozycja sekwencji, przejęte komórki, dopuszczone zdjęcie, kohorta, CAS, drugie cofnięcie.
- Ponowny zapis identycznej geometrii po cofnięciu → nowa rewizja źródła, sąsiedzi przepięci do przodu.
- Zapytania „latest” z wierszem `reverted` na szczycie → wybierają poprzednią rewizję (testy repozytorium kompletności i kolejki).
- Worker: deduplikacja checksumy pomija `reverted`.

## Verification

```powershell
# z katalogu worktree, timeout 120 s na komendę
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/test_geometry_correction_reverts.py services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py -q
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_virtual_deferred_resolution_postgres.py services/api/tests/integration/test_image_geometry_completeness_gate.py services/api/tests/integration/test_image_geometry_completeness_repository.py -q
npm run db:baseline:verify
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- Zmiana semantyki „latest” dotyka bramki kompletności; każda rozbieżność istniejących testów zatrzymuje task.

## Outcome

Wypełnia agent po pracy.
