---
title: Fix symbol review page response limit
status: done
version: 0.8
relevant_docs:
  - ai_docs/requirements/ADMIN_APP.md
  - ai_docs/architecture/API_CONTRACT.md
  - ai_docs/process/CURRENT_STATE.md
---

# TASK-0301: Fix symbol review page response limit

## Goal

Make the declared 500-item symbol verification page serializable by the API.

## Scope

- bind the response collection limit to the same 500-item application constant,
- add a regression test that converts a complete 500-item page,
- regenerate and verify OpenAPI and the Admin client,
- verify the real local endpoint after API reload.

## Invariants

- the request and response hard maximum remain 500,
- pagination remains keyset-based and bounded,
- no projection data, crop assets or review decisions are modified,
- the unrelated `apps/admin/next-env.d.ts` change remains untouched.

## Outcome

- `SymbolCellReviewPageResponse.items` używa wspólnego limitu aplikacyjnego 500.
- Test API buduje i serializuje pełne 500 cropów, a limit 501 nadal kończy się
  walidacją 422.
- OpenAPI deklaruje `maxItems: 500`, a wygenerowany klient pozostaje zgodny.
- Rzeczywisty endpoint gry `777` zwrócił 500 oczekujących cropów, poprawne
  liczniki i następny kursor zamiast HTTP 500.
