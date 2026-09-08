---
title: TASK-0521 — Indexed symbol review list
status: done
---

# TASK-0521 — Indeksowana lista Weryfikacji symboli

## Status

`done`

## Goal

Lista Weryfikacji symboli dla gry w `game_data_v2` korzysta wyłącznie z jej
bieżącej partycji/projekcji, stabilnego keysetu i indeksowalnych filtrów, bez
przeglądania historii ani danych innych gier.

## Context

TASK-0520 ustalił jeden bieżący rekord V2 na pozycję logiczną. Obecny read path
nadal wykonuje legacy owner join oraz wyprowadza confidence z historycznych
JSON-ów, co nie skaluje się do milionów komórek jednej gry.

## Dependencies / entry conditions

- TASK-0519 i TASK-0520 ukończone.
- Migracje 0105–0107 są w repo, lecz nie zostały zastosowane na danych użytkownika.
- W tym tasku nie tworzymy partycji gry ani nie przełączamy registry.

## Recommended execution

`gpt-6-astra high`; zmiana obejmuje fizyczny plan zapytań, spójność projekcji i
ważność kursora. Niezależny review w `gpt-6-astra high` jest wymagany przed
uznaniem taska za ukończony.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/quality/SYMBOL_REVIEW_FAST_PAGE_ACCEPTANCE.md`

## Scope

- Materializować bieżący confidence w projekcji komórki.
- Dla V2 usunąć z listy owner join i skany historycznych obserwacji/predykcji.
- Dodać indeksy filtrów symbolu, `?`, stanu, confidence i aktywnej kohorty.
- Używać stabilnego keysetu `(sequence_number, cell_index, cell_review_id)`.
- Związać cursor z grą, generacją storage, kompletem filtrów i kierunkiem.
- Pozostawić legacy read path zgodny wstecznie.

## Out of scope

- Optymalizacja liczników (TASK-0522).
- Tworzenie partycji i lifecycle gry (TASK-0523).
- Migracja lub usuwanie danych użytkownika.
- Zmiana cache atlasów i binarnych assetów.

## Acceptance criteria

- [x] V2 listuje tylko bieżącą projekcję jednej gry i nie łączy historii.
- [x] Seek oraz hydracja są bounded i korzystają z keysetu stabilnego rekordu.
- [x] Filtry mają indeksowalne kolumny/projekcje.
- [x] Cursor innej generacji lub scope kończy się kontrolowanym odświeżeniem.
- [x] Metadane strony nie pobierają ciężkiego render spec; assety pozostają osobnym odczytem.
- [x] Legacy zachowuje dotychczasową semantykę.

## Test cases

- SQL V2 nie zawiera fast document, observation ani prediction revision.
- SQL legacy zachowuje owner/current-geometry joins.
- Roundtrip cursora obejmuje generation i cell id; dawny cursor jest odrzucony.
- Zmiana gry, filtra, kohorty albo generacji unieważnia cursor.
- Zmiana właściciela nie zmienia stabilnej pozycji keysetu V2.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_image_symbol_reviews_domain.py services/api/tests/test_image_symbol_review_query_storage.py services/api/tests/test_current_symbol_cell_projection_v2.py -q
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/domain/image_symbol_reviews.py services/api/src/game_predictor_api/application/image_symbol_reviews.py services/api/src/game_predictor_api/storage/image_symbol_review_repository.py services/api/src/game_predictor_api/storage/models.py services/api/alembic/versions/0108_indexed_symbol_review_list.py services/api/tests/test_image_symbol_reviews_domain.py services/api/tests/test_image_symbol_review_query_storage.py
```

## Risks / open questions

- Migracja pozostaje kodem do chwili kontrolowanego cutoveru; nie jest wykonywana w tym tasku.
- Publiczny legacy confidence zachowuje fallback JSON, aby nie wymagać kosztownego backfillu starej gry.

## Outcome

### Changed

- Dodano materializowane confidence i indeksy V2 w migracji 0108.
- V2 używa bieżącej projekcji bez historycznych owner/confidence joins.
- Cursor v6 jest związany z generacją i stabilnym id komórki.

### Verification results

- 104 testy domeny/zapytań/migracji passed.
- 35 testów API i projekcji passed.
- Ruff oraz scoped mypy (4 moduły) passed.
- Audyt diffu potwierdził zachowanie legacy i brak binariów/render spec w liście.

### Not completed

- Migracji nie zastosowano na bazie użytkownika; provisioning należy do TASK-0523.

### Documentation updates

- `DATA_MODEL.md`, `API_CONTRACT.md`, `DECISION_LOG.md`, `CURRENT_STATE.md`.

### Recommended next task

- TASK-0522 — stałokosztowe liczniki Weryfikacji symboli.
