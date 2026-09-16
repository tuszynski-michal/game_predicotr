---
title: Decouple symbol review counts
status: done
version: 0.10
---

# TASK-0360 — Decouple symbol review counts

## Goal

Return a symbol review page without waiting for a global aggregate and load
revision-bound counts independently in Admin.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- remove counts from the page response critical path;
- add a filter- and catalog-revision-bound counts endpoint;
- load counts independently without overlapping requests;
- ignore late results from an older filter or catalog revision;
- refresh counts after successful decisions.

## Acceptance

- page data remains usable when counts fail;
- delayed counts cannot overwrite a newer scope;
- OpenAPI and the generated TypeScript client remain aligned;
- focused API and Admin tests pass.

## Outcome

- Strona metadanych nie wywołuje repozytorium liczników.
- Dodano osobny, revision-bound endpoint oraz wygenerowany klient Admina.
- Admin pobiera liczniki niezależnie, odrzuca spóźnione wyniki i zachowuje
  działającą listę przy błędzie agregacji.
- Bezpośrednia i zakończona masowa decyzja przełącza licznik na nową rewizję.
- Testy API, testy kontraktowe Admina, Ruff, lint, typecheck i OpenAPI przeszły.
