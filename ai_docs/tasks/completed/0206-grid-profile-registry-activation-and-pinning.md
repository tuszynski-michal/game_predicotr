---
title: TASK-0206 grid profile registry activation and pinning
status: done
release: "0.5"
last_updated: 2026-08-09
---

# TASK-0206 — Grid profile registry activation and pinning

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md

## Goal

Dodać append-only aktywację i rollback profilu oraz przypinać go tylko do
nowych importów.

## Verification

Trwające i historyczne joby zachowują snapshot; brak profilu bezpiecznie używa
detektora.

## Dependencies

TASK-0205 i TASK-0201.

## Outcome

Migracja `0039_grid_calibration_profiles` dodała rejestr kandydatów oraz
append-only aktywacje i rollback. Nowy image import przypina checksum,
fingerprint i payload aktywnego profilu; trwające i historyczne joby nie są
zmieniane. Brak aktywnego lub pasującego profilu bezpiecznie pozostawia surowy
wynik detektora.
