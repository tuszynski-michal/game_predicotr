---
title: Fast symbol review thumbnails and direct single-cell mutations
status: done
last_updated: 2026-08-27
---

# TASK-0298 — Fast symbol review assets and direct single-cell mutations

## Goal

Reduce first-view transfer cost in Symbol Verification and make a decision for
one selected crop complete immediately without creating a durable bulk job.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Serve a bounded 100 × 100 thumbnail for card assets while retaining the
  checksum-bound, immutable URL and browser cache.
- Add a local Admin API command for one exact crop using the existing atomic
  mutation service and optimistic crop identity.
- Route an explicit one-crop approve, reassign or grid-issue action through the
  direct command; retain durable jobs for multiple crops and filter snapshots.
- Disable and show progress on the submitted card, clear its selection after a
  successful decision and hide a successfully reassigned crop immediately.
- Show bounded success/error toast feedback without adding a UI dependency.

## Out of scope

- Removing durable bulk operations or historical jobs.
- Embedding image bytes in list JSON, copying thumbnails into domain tables or
  eagerly loading queued pages.
- Weakening revision, checksum, current-owner or projection-readiness checks.

## Acceptance

- Card requests transfer at most a 100 × 100 representation and remain
  content-addressed and immutable in browser cache.
- One explicit crop produces no operation row and no job row.
- Multiple explicit crops and filter selections continue to use the existing
  preview and durable worker path.
- A successful direct decision clears selection; reassignment disappears from
  the current symbol filter before bounded refresh.
- A conflict restores the card and reports a visible error toast.

## Outcome

- Asset karty jest generowany jako maksymalnie 100 × 100 WebP, związany z
  checksumą cropa i przechowywany przez prywatny, immutable cache
  przeglądarki. Lista nadal nie zawiera binariów ani pełnych cropów.
- Pojedyncze jawne `approve`, `reassign` i `mark_grid_issue` korzysta z nowego
  lokalnego endpointu i istniejącej atomowej mutacji planszy. Nie tworzy
  operacji masowej ani joba.
- Po sukcesie zaznaczenie jest czyszczone, a przeniesiony symbol znika z
  bieżącego filtra. Podczas requestu kafel pokazuje loader; konflikt lub błąd
  pozostawia zaznaczenie i pokazuje toast.
- Operacje wieloelementowe oraz wybór całego filtra zachowują trwały worker,
  checkpointy i częściowy raport.
- Zweryfikowano Ruff, 9 testów API, 46 testów klienta, testy kontraktowe Admina,
  typecheck, lint zmienionych plików, OpenAPI/generowany klient oraz produkcyjny
  build Admina. Pełny lint Admina został przerwany po 60 sekundach bez wyniku;
  zawężony lint zmienionych plików przeszedł.
