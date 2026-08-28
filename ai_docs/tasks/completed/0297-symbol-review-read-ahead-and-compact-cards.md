---
title: Symbol review sequential read-ahead and compact cards
status: done
last_updated: 2026-08-27
---

# TASK-0297 — Sequential read-ahead and compact symbol cards

## Goal

Make high-volume symbol verification feel immediate while keeping rendering and
network work bounded, and reduce each result card to the symbol crop itself.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Load the first keyset page immediately, then prefetch up to four following
  metadata pages sequentially in cursor order.
- Keep at most the previous, current and first queued page mounted in the DOM;
  queued pages must not eagerly load image assets.
- Render symbol crops at 100 × 100 px without labels, sequence/position or
  review-state text.
- Show a centered spinner and muted card while a submitted target waits for its
  durable operation.
- Hide successfully reassigned visible targets immediately and reconcile the
  page from the server without clearing the whole workspace.

## Out of scope

- API or database schema changes.
- Parallel page requests, unbounded caching or eager image preloading.
- Removing filters, bulk controls or checksum/revision validation.

## Acceptance

- Read-ahead requests are sequential, cursor-ordered and bounded to four future
  pages.
- At most 180 cards are mounted and image assets remain lazy-loaded.
- A result card occupies exactly 100 × 100 px and contains no descriptive body.
- Submitted targets cannot be toggled again, show a visible loading indicator,
  and successful reassignment disappears before the background refresh.
- Failed or conflicting operations restore interactive cards.

## Outcome

Implemented sequential cursor-ordered read-ahead for four future metadata
pages while keeping only the previous, current and first queued page mounted.
Cards now render only a 100 × 100 crop. Submitted visible targets are disabled,
muted and show a spinner; successful reassignment is hidden before a bounded
page refresh reconciles server state. Focused state and workspace contract
tests, Admin typecheck and Admin lint pass.
