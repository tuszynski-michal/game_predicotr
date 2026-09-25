---
title: TASK-0658 — Odroczenia v2 nie są naruszeniami topologii
status: done
---

# TASK-0658 — Odroczenia v2 nie są naruszeniami topologii

## Status

`done`

## Goal

Import z polityką `image-geometry-systemic-guard-v2-manual-review` kieruje
planszę bez gotowego cropa do ręcznej korekty, zamiast zatrzymywać cały job
przez fałszywe naruszenie topologii.

## Context

Job `753a4776-907f-42ea-81c3-ea2a8c886d4f` miał politykę v2. Pięć
odroczonych plansz zostało policzonych jako `topology`, mimo braku naruszeń
checksumy i kolejności. To jest sprzeczne z wymaganiem, że niski wynik próbki
oraz odroczone sloty v2 nie blokują katalogu.

## Dependencies / entry conditions

- Ustalony raport joba i jego checksum-bound artefakt są wyłącznie dowodem;
  nie będą zmieniane.
- Nie ma zmiany modelu danych, API, OpenAPI ani migracji.

## Recommended execution

`gpt-6-sol`, reasoning `high`: zmiana dotyczy granicy między semantyką
odroczenia a invariantami integralności i wymaga testu regresji pełnego
przepływu bramki. Niezależny review nie jest wymagany; eskalacja do
`gpt-6-astra`, reasoning `high` tylko jeżeli test ujawni, że crop zawiera
rzeczywiście niespójne identyfikatory 3 × 5, a nie jawne odroczenie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` — „Ochrona dużego importu przed regresją geometrii”
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md` — „Bramka systemowa przed materializacją dużego importu”
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Rozróżnić w raportowaniu bramki prawdziwie niepoprawny output topologii od
  jawnie odroczonego slotu bez finalnego cropa.
- Zachować blokadę v2 dla checksumy, kolejności i faktycznej niespójności
  topologii.
- Dodać test regresji odroczonego slotu oraz test dla rzeczywiście błędnego
  cropa.
- Uzupełnić stan projektu i Outcome taska.

## Out of scope

- Usuwanie lub podmiana zdjęć użytkownika.
- Mutacja failed joba, jego raportu albo danych gry.
- Zmiana progu 98%, polityki v1 lub kontraktu API.

## Acceptance criteria

- [ ] Brak finalnego cropa dla slotu jasno oznaczonego jako `deferred` nie
  zwiększa licznika `topology`.
- [ ] Polityka v2 przepuszcza taki import z `qualityWarningOnly: true` i
  zachowuje odroczenie do ręcznej korekty.
- [ ] Crop o złej liczbie lub tożsamości komórek nadal zwiększa `topology` i
  blokuje v2.
- [ ] Skoncentrowane testy, lint i typecheck zmienionych modułów przechodzą.

## Technical notes

`grid_profile_end_to_end_gate.run_grid_profile_gate_source` słusznie
interpretuje wpis z `board_crops.boards` bez kompletu 15 komórek jako
naruszenie topologii. Problem jest wcześniej: `_virtual_board_payload`
publikuje taki niekompletny wpis zamiast umieścić go w `deferredBoards`.
Należy wykryć niepełny zbiór renderów przed publikacją planszy, zapisać
deterministyczne odroczenie do ręcznej korekty oraz dopuścić utrwalenie tylko
tych nowych virtual deferrals. Nie wolno tolerować wpisu `boards` o złej
topologii bez zgodnego odroczenia.

## Expected files

- Istniejące: `services/worker/src/game_predictor_worker/images/production_workflow.py` — niepublikowanie niekompletnego virtual cropa jako gotowej planszy i trwałe odroczenie.
- Istniejące: `services/worker/src/game_predictor_worker/images/pipeline_execution.py` — walidacja bezpiecznego odroczenia wykrytego podczas virtual cropa.
- Istniejące: `services/worker/tests/test_production_image_workflow.py` — regresja incomplete virtual cropa i trwałego odroczenia.
- Istniejące: `services/worker/src/game_predictor_worker/images/grid_profile_end_to_end_gate.py` — klasyfikacja wyniku cropa.
- Istniejące: `services/worker/tests/test_grid_profile_end_to_end_gate.py` — ochrona granicy bramki.
- Istniejące: `services/worker/tests/test_large_import_geometry_guard.py` — kontrakt polityki v2.
- Istniejące: `ai_docs/process/CURRENT_STATE.md`.
- Ten task: Outcome, następnie przeniesienie do `ai_docs/tasks/completed/`.

## Test cases

- `deferredBoards` obejmuje slot bez finalnego cropa → brak `topology`,
  `finalCellGridReady` nie obejmuje slotu, powód odroczenia jest zachowany.
- Slot z wpisem cropa o mniej niż 15 komórkach i bez odroczenia → `topology`
  rośnie.
- Wynik dużej bramki v2 z odroczonym slotem i gotowością poniżej 98% →
  `passed=false`, `allows_import=true`, `qualityWarningOnly=true`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_profile_end_to_end_gate.py services/worker/tests/test_large_import_geometry_guard.py
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/grid_profile_end_to_end_gate.py services/worker/tests/test_grid_profile_end_to_end_gate.py services/worker/tests/test_large_import_geometry_guard.py
.\.venv\Scripts\python.exe -m mypy --strict services/worker/src/game_predictor_worker/images/grid_profile_end_to_end_gate.py
```

## Risks / open questions

- Report joba nie przechowuje surowych `board_crops`; regresja musi odtworzyć
  granicę na adapterach testowych.
- Istniejący failed job pozostaje niezmienny. Po wdrożeniu należy utworzyć
  nowy reprocess, nie retry starego joba.

## Outcome

### Changed

- Niekompletny virtual crop kompletnej planszy nie jest już publikowany jako
  wadliwy wynik 3 × 5. Powstaje deterministyczne odroczenie
  `incomplete_lattice` z technicznym powodem
  `VIRTUAL_CELL_RENDER_OUTPUT_INCOMPLETE`.
- Walidator pipeline'u dopuszcza takie odroczenie wykryte dopiero podczas
  virtual cropa i wymaga jego trwałego zapisu. Wcześniejsze odroczenia
  strukturalnej geometrii nadal nie są zapisywane drugi raz.
- Dodano testy granicy bramki, virtual cropa i trwałego odroczenia.

### Verification results

- `pytest services/worker/tests/test_grid_profile_end_to_end_gate.py services/worker/tests/test_large_import_geometry_guard.py services/worker/tests/test_production_image_workflow.py` — 76 passed.
- `ruff format` i `ruff check` dla zmienionych plików — passed.
- Pełny strict typecheck nie jest zielony przez wcześniejsze błędy typów w
  `shape_geometry_v2/core.py` oraz historyczne błędy zwracania `Any` w
  niezmienionych fragmentach zależności; żadnego błędu nie zgłoszono w nowych
  liniach taska.

### Not completed

- Nie zmieniono failed joba ani nie uruchomiono reprocessu na danych gry.
- Nie usunięto ani nie podmieniono zdjęć użytkownika.

### Documentation updates

- `ai_docs/process/CURRENT_STATE.md` — dodano wynik TASK-0658.

### Recommended next task

- Po wdrożeniu nowego workera utworzyć nowy reprocess joba
  `753a4776-907f-42ea-81c3-ea2a8c886d4f`; nie wykonywać retry istniejącego,
  ponieważ jego raport jest niezmienny.
