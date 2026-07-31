---
title: Revocable game-scoped authorization and brute-force protection
status: done
last_updated: 2026-07-30
---

# TASK-0114 — Revocable game-scoped authorization and brute-force protection

## Status

`done`

## Goal

Wdrożyć trwałą, odwoływalną i ograniczoną do gry/importu autoryzację zdalnego
Reviewera z ochroną kodu, limitem prób i pełnym audytem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_08_EXECUTION_PLAN.md`
- wynik `TASK-0113`

## Scope

- migracja Alembic trwałych sesji i audytu,
- hash kodu, TTL, limit prób, blokada oraz natychmiastowe odwołanie,
- game/import-scoped token po poprawnym unlock,
- allowlista endpointów Reviewera,
- actor/session id na każdej decyzji,
- idempotency i optimistic revision dla konfliktów.

## Out of scope

- ingress HTTPS/VPN,
- zdalny dostęp do panelu Admin,
- automatyczne publikowanie danych po review.

## Acceptance criteria

- [x] kod nie występuje jawnie w bazie, URL ani logach,
- [x] link bez kodu nie ujawnia obrazów ani metadanych gry,
- [x] limit prób i wygaśnięcie są deterministycznie testowane,
- [x] odwołanie blokuje kolejne odczyty i zapisy,
- [x] próba użycia tokenu poza grą/importem zwraca stabilny błąd,
- [x] Reviewer nie może wywołać endpointów administracyjnych,
- [x] OpenAPI i generowany klient są aktualne.

## Verification

```powershell
npm run openapi:check
npm run api:test
npm run reviewer:build
```

## Risks / open questions

- Blokada: wymaga zaakceptowanego TASK-0113.

## Outcome

Migracja `0021_reviewer_access` dodaje trwałe sesje i append-only audyt.
PBKDF2 chroni kod, token jest przechowywany jako SHA-256, piąta błędna próba
blokuje sesję, a revoke usuwa token. Same-origin proxy trzyma bearer w HttpOnly
cookie, mapuje kontekst do jednej gry/importu i przepuszcza wyłącznie
operacyjne review. Backend sprawdza scope oraz zapisuje aktora sesji.

Weryfikacja: pełny pakiet API 208/208 (`16 skipped` środowiskowo), 18 testów
Reviewera, 17 testów klienta, 77 testów Admina, TypeScript strict, Ruff, aktualny
OpenAPI/generated client oraz produkcyjne buildy Admin i Reviewer.
