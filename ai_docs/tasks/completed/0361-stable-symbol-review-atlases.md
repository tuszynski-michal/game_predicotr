---
title: Stable symbol review preview atlases
status: done
version: 0.10
---

# TASK-0361 — Stable symbol review preview atlases

## Goal

Serve one stable, checksum-bound WebP atlas per deterministic group of at most
100 symbol cells, for both legacy files and virtual source-backed cells.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- use deterministic page chunks independent of the viewport;
- validate revision and checksum for every legacy or virtual target;
- cache atlases by complete crop provenance;
- load the visible chunk first and the remaining chunks sequentially;
- prune derived cache only when its bounded size threshold is exceeded.

## Acceptance

- a 500-cell page needs no more than five atlas requests;
- legacy cards no longer issue one image request per cell;
- revisiting the same page reuses identical atlas keys;
- changed crop provenance cannot display a stale tile;
- focused API, service, Admin, lint and type checks pass.

## Outcome

- Dodano wspólny endpoint atlasu dla `legacy_file` i `virtual_source` z
  kontrolą rewizji, checksummy cropa i opcjonalnego render specu.
- Strona jest dzielona na stabilne grupy po 100; widoczna grupa jest pobierana
  pierwsza, a kolejne sekwencyjnie.
- Usunięto request pojedynczego obrazu z każdej karty legacy.
- Cache ma stabilne klucze pełnej proweniencji, 24-godzinny TTL i pruning tylko
  po przekroczeniu limitu.
- Testy serwisu, API, Admina, Ruff, lint, typecheck i OpenAPI przeszły.
