---
title: Manual grid correction renderer rebind
status: done
last_updated: 2026-10-02
---

# TASK-0815 — ręczna korekta siatki po bumpie kontraktu renderera

## Status

`done`

## Goal

Przywrócić możliwość ręcznej zmiany siatki dla plansz zaimportowanych przed
podniesieniem wersji virtual renderera.

## Context

Operator po każdej zmianie siatki widział
`IMAGE_VIRTUAL_CELL_EXTRACTOR_MISMATCH`. Kontekst korekty odczytuje
`extractorVersion` z render speców istniejących komórek lub ze snapshotu
rolloutu joba, a `VirtualCellRenderer` akceptuje wyłącznie własną wersję
(v4 po TASK-0660/0661/0663).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`

## Scope

- Wiązanie konfiguracji renderu ręcznej korekty z bieżącym rendererem.
- Test regresyjny dla planszy przypiętej do historycznego renderera.

## Out of scope

- Zmiana historycznych render speców, reprocess, zmiany API i schematu.
- Dwa wcześniej czerwone testy `test_qualified_partial_preview_…`.

## Acceptance criteria

- [x] Zapis pojedynczej planszy i zapis źródła przechodzą dla komórek
      przypiętych do `virtual-cell-renderer-source-direct-v1`.
- [x] Nowe komórki zapisują bieżącą wersję extractora; pozostałe pola
      konfiguracji pozostają bez zmian.

## Technical notes

Ten sam wzorzec stosuje już manual continuation w `application/jobs.py`
(`replace(rollout, virtual_renderer_version=VIRTUAL_CELL_RENDERER_VERSION)`).
Rebind obejmuje też porównanie konfiguracji między slotami jednego źródła,
więc źródło z planszami renderowanymi różnymi wersjami nie kończy się
konfliktem kontekstu.

## Expected files

- `services/api/src/game_predictor_api/application/virtual_grid_geometry.py`
- `services/api/tests/test_virtual_grid_geometry.py`
- `ai_docs/requirements/IMAGE_INGESTION.md`

## Outcome

### Changed

- `_bind_current_renderer` w `VirtualGridGeometryService` dla `_prepare`,
  `_prepare_source` i `prepare_legacy_conversion`.

### Verification results

- `test_virtual_grid_geometry.py` + `test_virtual_grid_geometry_repository.py`:
  48 passed, 2 failed — oba błędy
  (`test_qualified_partial_preview_keeps_slots_without_rendering_missing_pixels`)
  występują identycznie bez tej zmiany.
- Nowy test pada bez poprawki i przechodzi z nią. Ruff check/format czysty;
  mypy bez nowych błędów w zmienionym pliku.

### Not completed

- Brak odbioru na żywym Reviewerze; API wymaga restartu z nowym kodem.

### Documentation updates

- `IMAGE_INGESTION.md`: reguła wersji extractora przy ręcznej korekcie.

### Recommended next task

- Naprawa dwóch czerwonych testów podglądu częściowej planszy.
