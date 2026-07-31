---
title: Remote reviewer threat model and session hardening
status: done
last_updated: 2026-07-30
---

# TASK-0113 — Remote reviewer threat model and session hardening

## Status

`done`

## Goal

Zatwierdzić model zagrożeń i bezpieczną granicę systemu dla zdalnego Reviewera,
bez wystawiania pełnego panelu Admin ani surowych portów routera.

## Context

Właściciel chce przekazywać link osobie spoza domu i miasta. Lokalna sesja
TASK-0112 jest wyłącznie bramą UX na loopback i nie stanowi zabezpieczenia
internetowego.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_08_EXECUTION_PLAN.md`
- `ai_docs/project/OPEN_QUESTIONS.md`
- D-087 i D-091 w `ai_docs/process/DECISION_LOG.md`

## Scope

- zinwentaryzować dane, endpointy, aktorów i granice zaufania,
- rozstrzygnąć Q-021 na podstawie aktualnego porównania tunelu HTTPS i VPN,
- zdefiniować osobny publiczny ingress wyłącznie dla Reviewera,
- określić TTL, rotację, odwołanie, audit i wymagania prywatności obrazów,
- potwierdzić brak zdalnego dostępu do Admin CRUD, jobów, eksportów i wydań.

## Out of scope

- implementacja autoryzacji i tunelu,
- port forwarding bez TLS,
- publiczny Admin API albo synchronizacja mobile.

## Acceptance criteria

- [x] diagram przepływu nie wystawia PostgreSQL ani pełnego Admin API,
- [x] Q-021 ma zaakceptowaną odpowiedź,
- [x] opisane są brute force, wyciek linku/kodu, replay, konflikt recenzentów,
  logi, odwołanie i utrata domowego połączenia,
- [x] domyślny tryb lokalny nadal binduje tylko loopback,
- [x] decyzja architektoniczna wskazuje warunki wejścia do TASK-0114.

## Verification

```powershell
rg -n "Q-021|TASK-0113|remote reviewer|zdalne review" ai_docs
```

## Risks / open questions

- Blokada: lokalne G6.5 i model bezpieczeństwa G8.1 muszą zostać zamknięte.

## Outcome

Zaakceptowano D-095 oraz model
`security/REMOTE_REVIEWER_THREAT_MODEL.md`. Q-021 zamknięto wyborem Cloudflare
Quick Tunnel dla czasowego pilota v0.1. Publiczny jest wyłącznie origin
Reviewera; API, Admin, PostgreSQL i worker pozostają na loopback.
