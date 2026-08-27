---
title: Run page-local symbol review operations in background
status: done
version: 0.8
relevant_docs:
  - ai_docs/requirements/ADMIN_APP.md
  - ai_docs/architecture/API_CONTRACT.md
  - ai_docs/process/CURRENT_STATE.md
---

# TASK-0302: Run page-local symbol review operations in background

## Goal

Keep durable page-local bulk decisions visible and recoverable without blocking
navigation through other symbol pages.

## Scope

- track multiple submitted bulk operations in the workspace,
- keep exact submitted cards disabled with a progress spinner,
- allow page navigation and later page-local submissions while older jobs wait,
- remove successfully processed cards without refilling the current page,
- show operation progress while jobs execute in the general lane,
- move transient toast feedback to the lower-left viewport corner.

## Invariants

- the same checksum-bound crop cannot be submitted twice while its operation is active,
- each durable job retains its existing idempotency and per-board atomicity,
- partial/conflicted operations do not hide targets whose exact outcome is unknown,
- the browser does not fetch replacement crop metadata after a successful decision,
- filters and pages remain keyset-based and bounded to 500 items.

## Outcome

- Workspace śledzi wiele trwałych operacji równolegle i odpytuje każdą bez
  nakładania requestów.
- Dokładne targety aktywnych operacji mają spinner i nie mogą zostać wysłane
  ponownie, ale nawigacja oraz kolejne strony pozostają dostępne.
- Pełny sukces usuwa targety bez odświeżania lub uzupełniania strony; wynik
  częściowy zachowuje widoczne karty.
- Toast został przeniesiony 50 px od lewego i dolnego brzegu viewportu.
