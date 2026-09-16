---
title: Recover descending manual selection repair gaps
status: done
last_updated: 2026-09-06
---

# TASK-0487 — Recover descending manual selection repair gaps

## Goal

Restore gap detection for descending manual-selection outputs whose repair
manifest incorrectly retained only the first selected nine-board range.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- Derive immutable collection bounds from the union of persisted bounds,
  current `seq_*` names, known deletions and repair operations.
- Interpret a descending output manifest using its complete item range rather
  than treating `firstLayout` as the lower collection boundary.
- Persist a widened repair manifest during explicit directory inspection.
- Preserve JPEG bytes, checksums, decisions and existing repair history.
- Add regressions for descending output and an already-corrupted manifest.
- Diagnose the real `437742 - 412605` directory and recover its manifest only
  after the code and tests pass.

## Out of scope

- Changing image selection order or navigation.
- Filling any gap automatically.
- Modifying or deleting JPEG files.
- API, worker, PostgreSQL or staging changes.

## Tests

- Core repair-domain tests for monotonic bound widening.
- Admin storage test proving that inspection persists recovered bounds.
- Manual-selection core typecheck, Admin lint/typecheck and production build.

## Definition of Done

- The real directory reports 247 gaps across `412597–437742`.
- Reopening the directory keeps those bounds and enables `Uzupełnij luki`.
- No JPEG is modified.

## Outcome

- `deriveCollectionBounds` poszerza granice na podstawie wszystkich trwałych
  źródeł dowodu i nigdy nie redukuje poprawnego historycznego zakresu.
- Malejący output jest interpretowany przez minimum/maksimum wszystkich items.
- Inspekcja utrwala odzyskane granice i synchronizuje `selectionComplete`.
- Rzeczywisty katalog został odczytowo zweryfikowany: 2547 z 2794 zakresów,
  dokładnie 247 luk zgodnych 1:1 z `deletedRanges`. Otwarta aplikacja zastosowała
  nowy recovery: granice `412597–437742`, rewizja 248 i
  `selectionComplete=false`. JPEG-ów nie modyfikowano.
- Verification: 22 focused tests passed; full core 85 passed; core and Admin
  typecheck passed; Admin lint passed; production build and final format check
  are recorded before commit.
