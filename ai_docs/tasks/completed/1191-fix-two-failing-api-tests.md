---
title: TASK-1191 — Naprawa dwóch padających testów API
status: done
last_updated: 2026-11-12
---

# TASK-1191 — Naprawa dwóch padających testów API

## Status

`done`

## Goal

Oba testy wykryte jako zastane FAIL przy TASK-1190 przechodzą, a przyczyna jest
usunięta w kodzie albo w nieaktualnej atrapie testu.

## Context

Przy weryfikacji TASK-1190 dwa testy padały identycznie na czystym `main`
`33e9197e` (zapis w `Outcome` TASK-1190). Operator zlecił ich naprawę
(2026-11-12).

## Dependencies / entry conditions

TASK-1190 scalony (`main` `20635d36`). Bez migracji.

## Recommended execution

Claude Opus 5.5, reasoning standard — dwie małe, niezależne poprawki z
istniejącymi testami regresyjnymi; operator zlecił je bezpośrednio. Bez audytu
krzyżowego (brak planu z kolumną `Dodatkowy review`).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

1. `test_page_geometry_overrides.py::test_slot_decisions_survive_retry_and_change_revision_without_changing_quads`
   — błąd w kodzie: `PageGeometryOverrideService.save` (od `a41f8d8d`,
   v1.7.525) bez `expected_override_revision` zwracał jako powtórkę dowolną
   historyczną decyzję o tej samej sumie kontrolnej, także zastąpioną nowszą
   rewizją z kwalifikacjami slotów. Klient dostawał „sukces” ze starą
   geometrią zamiast `IMAGE_PAGE_GEOMETRY_QUALIFICATION_REQUIRED`.
2. `test_lateral_managed_reprocess.py::test_public_import_entrypoints_cannot_drop_guard_history[browser]`
   — nieaktualna atrapa: `SimpleNamespace` stagingu bez pola
   `replacement_selection` (dodanego w `ad92ac35`, v1.7.531) dawał
   `AttributeError` w `replacement_admission`.

## Out of scope

- Zmiana semantyki powtórki z jawną `expected_override_revision` (TASK-1128:
  paragon przed CAS i blokadą wycofanego źródła) — zostaje bez zmian.
- Inne zastane porażki spoza tych dwóch testów.

## Acceptance criteria

- [x] Oba testy przechodzą bez osłabiania asercji.
- [x] Powtórka bez `expected_override_revision` zwraca wyłącznie bieżącą
      decyzję; z jawną rewizją zachowanie TASK-1128 bez zmian
      (`test_retired_page_exact_receipt_precedes_current_cas_and_new_command_refuses`).
- [x] Atrapa używa prawdziwych `BrowserImageUpload`/`BrowserReadySelection`.

## Technical notes

`save` bez `expected_override_revision`: powtórka = bieżąca rewizja ma tę samą
`decision_checksum_sha256` (zachowanie sprzed `a41f8d8d`), sprawdzane przed
`require_mutable_source`, więc powtórka bieżącej decyzji wycofanego źródła nadal
działa. Z jawną rewizją: paragon dokładnie tej rewizji, jak dotąd.

## Expected files

- `services/api/src/game_predictor_api/application/page_geometry_overrides.py` — `PageGeometryOverrideService.save`
- `services/api/tests/test_page_geometry_overrides.py` — nowy test regresyjny powtórki bieżącej decyzji wycofanego źródła
- `services/api/tests/test_lateral_managed_reprocess.py` — atrapa stagingu

## Test cases

- Zastąpiona decyzja bez kwalifikacji po rewizji z kwalifikacjami →
  `IMAGE_PAGE_GEOMETRY_QUALIFICATION_REQUIRED`, bez nowego wpisu.
- Powtórka bieżącej decyzji bez rewizji na wycofanym źródle → ta sama decyzja,
  bez `require_mutable_source`.
- Start importu z przeglądarki dla istniejącego importu → 201, `created=false`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_page_geometry_overrides.py services/api/tests/test_lateral_managed_reprocess.py -q
```

## Outcome

Commit: v1.7.619 / `9ab662a97f3129140333ecc759247ca9acc9fe17`.

- `PageGeometryOverrideService.save` bez `expected_override_revision` uznaje za
  powtórkę wyłącznie bieżącą decyzję (zachowanie sprzed `a41f8d8d`); z jawną
  rewizją paragon tej rewizji jak w TASK-1128. Zastąpiona decyzja bez
  kwalifikacji znów daje `IMAGE_PAGE_GEOMETRY_QUALIFICATION_REQUIRED`.
- Odstępstwo świadome (fail-closed): na wycofanym źródle zapis bez rewizji nie
  zwraca już historycznego paragonu, tylko `SOURCE_REPLACEMENT_RETIRED`
  (PostgreSQL ukrywa wycofane źródła w `get_current`). Panel Admin zawsze
  wysyła `expectedOverrideRevision`, więc UI tego nie dotyka.
- Atrapa stagingu w `test_lateral_managed_reprocess.py` używa prawdziwych
  `BrowserImageUpload`/`BrowserReadySelection`.
- Nowy test `test_replay_without_revision_returns_only_the_current_decision`
  pada na `main` `20635d36` i przechodzi po poprawce.
- Weryfikacja:
  - `test_page_geometry_overrides.py` + `test_lateral_managed_reprocess.py`:
    PASS (oba docelowe testy zielone);
  - pokrewne testy API (14 plików): 284 passed, 1 failed —
    `test_geometry_qualification.py::test_override_repository_roundtrip_after_new_repository_instance`
    (`TypeError: 'Mock' object is not iterable`) pada identycznie na `main`;
    zastany, poza zakresem;
  - PostgreSQL (`test_source_replacement_geometry_guards_postgres.py`,
    `test_neural_page_geometry_postgres.py`): 5 passed, 1 failed —
    `test_0145_preserves_old_partitions_validates_binding_and_recovers_in_new_process`
    (`purged_at` nie istnieje w schemacie 0144) pada identycznie na `main`;
    grupa historycznych testów migracji (TASK-0940), poza zakresem;
  - ruff check/format PASS; mypy zmienionego modułu bez nowych błędów
    (2 zastane w `schemas/source_lattice_geometry.py`).
- Nie wykonano: audytu krzyżowego (niewymagany), scalenia do `main`.
