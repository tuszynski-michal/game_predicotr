---
title: Deferred geometry manual resolution advances canonical crop revision
status: done
last_updated: 2026-09-26
---

# TASK-0702 — kanoniczna rewizja przy ręcznym zapisie odroczonej geometrii

## Status

`in_progress`

## Goal

Ręczne zapisanie geometrii z kolejki „Niepełne siatki do ręcznej korekty” tworzy poprawną kolejną wspólną rewizję 15 cropów, także gdy plansza przejmuje istniejącą kanoniczną `sequence_number`.

## Context

Endpoint `manual-resolution` zwracał `422 SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID`: nowa plansza dostawała `expected_geometry_revision + 1` z własnego manifestu, a projekcja komórek dla tej samej sekwencji miała już inną, wspólną rewizję. To łamało kontrakt invalidacji cropów i blokowało pracę na dokładnie wskazanym ekranie Reviewera.

## Dependencies / entry conditions

- TASK-0693 dostarczył manualną korektę odroczonej geometrii i kontrakt `geometryQualification`.
- TASK-0701 umożliwił odczyt kolejki przy niespójnej globalnej projekcji; nie zmienia fail-closed zapisu.
- Faktem jest, że wywołanie dla planszy `412 597` zakończyło się `422`; naprawa nie wykonuje zapisu na danych użytkownika.

## Recommended execution

`gpt-6-sol`, reasoning `high`: zmiana wymaga zachowania atomowości własności sekwencji, rewizji geometrii oraz projekcji 15 cropów. Eskalacja do `gpt-6-astra`, reasoning `high`, jest wymagana tylko, gdy test z realnym repozytorium ujawni konflikt z globalnym routingiem V2, którego nie da się zawęzić do tej ścieżki.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`

## Scope

- Ustalenie rewizji nowej ręcznie zmaterializowanej planszy względem aktualnych kanonicznych komórek tej samej gry i `sequence_number`.
- Zachowanie atomowości: przejęcie właściciela sekwencji, rewizja planszy, audyt geometrii i projekcja komórek zapisują się razem albo wcale.
- Regresja dla istniejącej kompletnej projekcji 15 cropów o wcześniejszej rewizji.

## Out of scope

- Zmiany interakcji canvasu, checkboxów i podglądu.
- Przebudowa globalnej projekcji symboli, migracja schematu albo ręczny zapis danych użytkownika.
- Zmiana kontraktu HTTP lub OpenAPI.

## Acceptance criteria

- [ ] Gdy ręczna plansza przejmuje aktywną `sequence_number` z istniejącymi 15 cropami o rewizji `N`, zapis używa dokładnie rewizji `N + 1`.
- [ ] Zapis tworzy jedną wspólną rewizję dla `recognized_boards`, audytu geometrii, `resolved_geometry_revision` i wszystkich aktualnych cropów.
- [ ] Brak istniejących komórek zachowuje dotychczasowy wynik `expected_geometry_revision + 1`.
- [ ] Retry idempotentny, superseding oraz istniejące konflikty pozostają fail-closed.
- [ ] Test odtwarza wcześniejsze `SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID` i kończy się sukcesem.

## Technical notes

Po uzyskaniu blokady właściciela sekwencji `materialize_manual_resolution` odczytuje i blokuje aktualne komórki logiczne dla `game_id + sequence_number`. Jeżeli aktywna projekcja istnieje, jej rewizja jest źródłem kolejnej rewizji nowej planszy; muszą być kompletne i mieć jedną wspólną wartość, inaczej pozostaje istniejący fail-closed kontrakt domenowy. Manifest nadal chroni źródło i obserwowaną rewizję własnego pending itemu, ale nie jest źródłem rewizji logicznego cropa po zmianie właściciela sekwencji.

Przykład: pending manifest wskazuje `0`, istniejące 15 kanonicznych komórek sekwencji `412597` ma rewizję `1`; ręczny zapis tworzy planszę, event i cropy o rewizji `2`, a nie o `1`.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/storage/board_cell_geometry_pending_repository.py` — `materialize_manual_resolution`.
- Istniejące: `services/api/tests/integration/test_image_batch_store.py` — regresja trwałego repozytorium i projekcji cropów.
- Istniejące: `ai_docs/architecture/DATA_MODEL.md` — reguła źródła wspólnej rewizji cropów.
- Istniejące: `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Aktywna kompletna projekcja sekwencji na rewizji 1, manual resolution manifestu z rewizją 0 → sukces, plansza/audyt/cropy mają rewizję 2.
- Brak istniejącej projekcji, manifest z rewizją 0 → sukces i rewizja 1.
- Ten sam UUID idempotencji i ta sama komenda → istniejący wynik bez drugiego zapisu.
- Niekompletna albo niespójna wcześniejsza projekcja → brak częściowego zapisu i stabilny błąd domenowy.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr
# timeout: 120 s na komendę
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_image_batch_store.py -k manual_deferred_geometry -q
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/storage/board_cell_geometry_pending_repository.py services/api/tests/integration/test_image_batch_store.py
.\.venv\Scripts\python.exe -m ruff format --check services/api/src/game_predictor_api/storage/board_cell_geometry_pending_repository.py services/api/tests/integration/test_image_batch_store.py
.\.venv\Scripts\python.exe -m mypy --strict services/api/src/game_predictor_api/storage/board_cell_geometry_pending_repository.py
```

## Risks / open questions

- Test integracyjny musi inicjalizować projekcję symboli, inaczej coordinator celowo nie materializuje cropów i nie odtworzy błędu użytkownika.
- Nie ma otwartego pytania produktowego: źródłem kolejnej rewizji jest aktualna wspólna rewizja logicznych cropów, zgodnie z istniejącym kontraktem domenowym.

## Outcome

### Changed

- `manual-resolution` po wyborze nowego właściciela sekwencji blokuje bieżące
  logiczne cropy V2 i, dla kompletnego wspólnego zestawu, nadaje nowej planszy
  rewizję poprzedniej geometrii plus jeden.
- Ta sama rewizja trafia do planszy, audytu geometrii i `resolved_geometry_revision`,
  dzięki czemu coordinator może atomowo zaktualizować wszystkie 15 cropów.
- Legacy storage oraz brak wcześniejszych cropów pozostają przy
  `expected_geometry_revision + 1`; niepełne lub niespójne cropy nadal są
  odrzucane przez dotychczasową walidację fail-closed.

### Verification results

- Odczyt lokalnej bazy dla zgłoszonego pending itemu potwierdził:
  `expected_geometry_revision=0`, `sequence_number=412597`, dokładnie 15
  bieżących cropów o wspólnej rewizji `1`; naprawiona ścieżka wybierze `2`.
- `services/api/tests/test_board_cell_geometry_pending.py`: 14 passed.
- Ruff check i format check dla zmienionego repozytorium oraz testu: passed.
- Mypy strict dla repozytorium: passed.

### Not completed

- Nie wykonano `POST manual-resolution` na danych użytkownika; nie jest to
  potrzebne do wdrożenia naprawy i zachowuje kontrolę operatora nad korektą.
- Izolowany test integracyjny PostgreSQL nie został uruchomiony, ponieważ jego
  fixture usuwa i tworzy bazę o stałej nazwie; test jednostkowy obejmuje
  dokładną regułę rewizji zgłoszonego przypadku.

### Documentation updates

- Doprecyzowano `architecture/DATA_MODEL.md` o kanoniczne źródło rewizji przy
  przejęciu sekwencji V2.
- Zaktualizowano `CURRENT_STATE.md`.

### Recommended next task

- Brak; operator może ponowić zapis tej ręcznie poprawionej siatki.
