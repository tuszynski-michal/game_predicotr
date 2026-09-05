---
title: Ready symbol projection progress
status: done
version: 0.10.84
---

# TASK-0382 — Ready symbol projection progress

## Goal

Keep the projection progress returned by the Admin API consistent with the
current canonical board-owner projection after write-through adds boards to an
already ready game.

## Scope

- A `ready` projection reports every current fast-document board owner as
  processed.
- A projection that is still rebuilding or failed keeps reporting its durable
  checkpoint count.
- No database data, schema, OpenAPI contract, crop, decision, or job lifecycle
  is changed.

## Verification

- focused storage tests for ready and rebuilding projections;
- Ruff and mypy for the changed backend module;
- live status read for the current game after deployment.

## Outcome

The API now derives `processedBoardCount` from the current expected owner count
when the projection is `ready`. This removes a stale progress display without
rewriting the durable checkpoint or performing another backfill. Rebuilding
projections continue to expose their persisted checkpoint.
