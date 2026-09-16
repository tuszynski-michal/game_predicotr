---
title: Single symbol review renderer and symbol filter
status: done
version: 0.10.85
---

# TASK-0383 — Single symbol review renderer and symbol filter

## Goal

Restore explicit symbol filtering and remove the misleading A/B preview mode
from Symbol Verification. The workspace must render the current crop identity
stored by the selected game's actual import engine.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- Add `Wszystkie`, active catalog symbols and `Nierozpoznany (?)` to the symbol
  filter.
- Keep game-wide `symbolId=all` as an explicit option, not a forced scope.
- Remove the current/experimental renderer selector and read-only notice.
- Always request the `current` preview; its asset mode follows each persisted
  cell (`legacy_file` or `virtual_source`).
- Keep selections, decisions, pagination and atlas caching unchanged.

## Out of scope

- Promoting the per-game import engine to virtual primary.
- Reprocessing existing imports.

## Definition of Done

- A user can filter one active symbol, all symbols or unknown cells.
- No experimental renderer control or read-only branch remains in the UI.
- Current virtual cells remain rendered through their checksum-bound virtual
  asset contract.

## Outcome

The symbol filter once again exposes all, one active catalog symbol and
unknown cells. The A/B selector and its read-only mutation branch were removed.
The atlas request always uses the current persisted asset identity, so legacy
and virtual cells share one operational review path without a misleading
experimental label.
