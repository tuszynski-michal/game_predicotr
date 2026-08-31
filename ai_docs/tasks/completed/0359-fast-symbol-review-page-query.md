---
title: Fast symbol review page query
status: done
version: 0.10
---

# TASK-0359 — Fast symbol review page query

## Goal

Remove the wide pre-limit scan from `Weryfikacja symboli` while preserving the
current logical owner, filters and deterministic keyset order.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- use a narrow `seek` query for at most `limit + 1` cell identities;
- hydrate full response rows only for the selected identities;
- emit cursor v3 with a native UUID key;
- continue accepting scoped cursor v2;
- retain symbol, unknown, state and confidence filtering.

## Out of scope

- asynchronous counts;
- preview atlas changes;
- Admin A/B preview.

## Acceptance

- forward and backward traversal has no duplicates or omissions;
- cross-scope cursors remain blocked;
- the wide ORM row is never selected before the page limit;
- focused API tests, Ruff and mypy pass.

## Outcome

- Listing now performs an index-ordered candidate seek, bounded ownership and
  geometry verification, and hydrates only the visible page.
- New cursors use native UUID key version 3; scoped version 2 cursors remain
  readable.
- On the current database, five reads of 500 pending cells from a population
  of about 1.12 million took `0.066–0.357 s`; the previous query took about
  `4.6–5.7 s` before counts.
- `27` focused domain/API tests pass and Ruff passes for changed modules.
