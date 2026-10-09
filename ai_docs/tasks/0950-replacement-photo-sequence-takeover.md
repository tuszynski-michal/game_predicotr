# TASK-0950 — Przejęcie sekwencji przez zdjęcie zastępcze i sprzątanie starego zdjęcia

## Status

`todo`

## Goal

Zwykły import lepszego zdjęcia (`seq_*`) przejmuje wyłącznie sekwencje odrzucone albo bez żywego właściciela, zamyka odrzucony slot starego zdjęcia i przelicza jego bramkę; dobre plansze starego zdjęcia zostają.

## Context

Plan `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, sekcja „Odrzucanie przyciętych plansz i zdjęcie zastępcze”, decyzje 5–6, wymaganie W9. Zmienia D-238 (proponowana D-539, wpis w TASK-0951).

## Dependencies / entry conditions

- TASK-0949 ukończony (status `rejected` slotu i odrzucanie planszy).

## Recommended execution

`claude-opus-5-5`, reasoning `high`: zmiana reguły własności sekwencji w API i workerze oraz przeliczanie bramki starego zdjęcia; błąd gubi plansze. Eskalacja: reguła koliduje z ponownym przetwarzaniem tej samej checksumy albo z `has_protected_lateral_owner` → zatrzymaj i zapytaj operatora. Review: Codex `gpt-6-astra`, `high`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — D-238, D-484, D-485

## Scope

- Reguła własności w `storage/pending_sequence_ownership.py` (`create_owned_pending_review_item`, `_supersede`) i ścieżce workera (`services/worker/src/game_predictor_worker/images/pipeline_store.py` ~440–540, ~668–710):
  - nowa plansza przejmuje sekwencję, gdy brak żywego właściciela albo właściciel jest odrzucony (pozycja `rejected` lub slot `rejected` tej sekwencji);
  - żywa pozycja `pending` innego zdjęcia zostaje; nowa plansza `superseded` + `image_sequence_alternatives` z powodem `superseded_existing_owner_kept` (nowa wartość CHECK, jeśli wymagana — wtedy w migracji `0153`, przed jej wykonaniem przez operatora);
  - kanoniczny właściciel wygrywa jak dotąd; ta sama checksuma zdjęcia — dotychczasowa ścieżka;
  - pojedyncza implementacja reguły jako czysta funkcja domenowa (proponowana `domain/sequence_takeover.py`) używana przez API i workera albo przez wspólne SQL; bez rozbieżnych kopii.
- Sprzątanie po przejęciu w tej samej transakcji: odrzucony slot starego zdjęcia → `superseded` (`superseded_at`); przeliczenie bramki starego zdjęcia (`recompute_source_image_geometry_completeness`, `sequence_live_elsewhere`) — gdy zdjęcie zostaje dopuszczone, cięcie pozostałych plansz istniejącą ścieżką `materialize_admitted_source_image`.
- Raport importu w Adminie: liczby „Zastąpione sekwencje” i „Pominięte — sekwencja ma właściciela” z listą numerów (rozszerzenie istniejącego raportu; OpenAPI i klient, jeśli zmienia się kontrakt).

## Out of scope

- Przejęcie kanonicznego właściciela (TASK-0305), osobny upload „Podmień zdjęcie”, zmiana nazewnictwa plików `seq_*`.

## Acceptance criteria

- [ ] Test PG: zdjęcie A z odrzuconym slotem sekwencji S i ośmioma dobrymi planszami; import zdjęcia B (zakres obejmuje S i sekwencje A) → B przejmuje tylko S; pozostałe sekwencje A zostają przy A; plansze B dla nich `superseded` z alternatywą.
- [ ] Odrzucony slot A → `superseded`; bramka A przeliczona; A dopuszczone i pocięte, gdy pozostałe pozycje są poprawne.
- [ ] Ponowne przetworzenie tej samej checksumy działa jak przed zmianą (istniejące testy bez zmian asercji).
- [ ] Raport importu pokazuje zastąpione i pominięte sekwencje.

## Technical notes

- Blokady sekwencji jak w `create_owned_pending_review_item`; kolejność: sekwencje → zdjęcie nowe → zdjęcie stare.
- Alternatywa i zdarzenia `superseded` zachowują audyt; nic nie jest usuwane.

## Expected files

- Zmieniane: `storage/pending_sequence_ownership.py`, `services/worker/src/game_predictor_worker/images/pipeline_store.py`, `storage/image_geometry_completeness_state_repository.py`, raport importu (API + Admin).
- Nowe (proponowane): `domain/sequence_takeover.py`, `services/api/tests/integration/test_replacement_photo_takeover_postgres.py`, testy workera.

## Test cases

- Scenariusz z kryteriów; sekwencja bez właściciela (wcześniej odrzucona przed importem w Adminie) → przejęcie.
- Właściciel `pending` tej samej checksumy → dotychczasowa ścieżka.
- Kanoniczny właściciel → nowa plansza `superseded`, alternatywa `superseded_first_save_wins` jak dotąd.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_replacement_photo_takeover_postgres.py services/api/tests/integration/test_image_geometry_completeness_gate.py services/api/tests/integration/test_virtual_deferred_resolution_postgres.py -q
npm run python:test -- -Suite Worker
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- D-539 zmienia D-238; operator, który chce zastąpić żywą pozycję `pending`, musi ją najpierw odrzucić.

## Outcome

Wypełnia agent po pracy.
