---
title: Secure ingress runbook and remote end-to-end acceptance
status: in_progress
last_updated: 2026-07-30
---

# TASK-0115 — Secure ingress runbook and remote end-to-end acceptance

## Status

`in_progress`

## Goal

Udostępnić osobie na innym urządzeniu bezpieczny link HTTPS do samego Reviewera
i potwierdzić pełny zdalny scenariusz bez otwierania surowego portu routera.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_08_EXECUTION_PLAN.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- wyniki `TASK-0113` i `TASK-0114`

## Scope

- skonfigurować zaakceptowany tunel HTTPS albo VPN,
- zachować lokalny loopback jako tryb domyślny,
- dodać kontrolowane start/stop/status i rotację adresu,
- opisać generowanie linku, oddzielne przekazanie kodu i odwołanie sesji,
- przeprowadzić test z urządzenia poza domową siecią,
- sprawdzić brak ekspozycji Admin, PostgreSQL i pozostałych endpointów.

## Out of scope

- chmura aplikacyjna, Google Play i publiczny backend,
- surowy port forwarding,
- stałe udostępnienie pełnej administracji.

## Acceptance criteria

- [ ] Reviewer działa przez HTTPS z urządzenia w zewnętrznej sieci,
- [ ] niepoprawny lub wygasły kod nie ujawnia danych,
- [ ] zdalny użytkownik widzi tylko wskazaną grę/import,
- [ ] odwołanie sesji działa natychmiast,
- [ ] skan ekspozycji nie wykazuje Admin, bazy ani nieobjętych endpointów,
- [x] runbook zawiera start, stop, status, odzyskanie i reakcję na incydent,
- [ ] lokalny tryb po wyłączeniu ingress nadal działa wyłącznie na loopback.

## Verification

```powershell
npm run api:test
npm run reviewer:build
```

Test zewnętrzny i kontrola HTTPS są obowiązkową częścią Outcome.

## Risks / open questions

- Blokada: wymaga ukończonych TASK-0113 i TASK-0114.

## Outcome

Zaimplementowano kontrolowane `setup/start/status/stop` Cloudflare Quick
Tunnel, automatyczne użycie aktywnego publicznego originu w nowej sesji oraz
runbook. Skrypty mają bounded 10-sekundowy start, zapis PID i walidację procesu.
Reviewer nadal binduje loopback, a publiczny proxy ma testowaną allowlistę i
nagłówki CSP/anti-clickjacking.

Na życzenie właściciela testowanie odłożono. Kryteria wymagające urządzenia w
zewnętrznej sieci, rzeczywistego TLS oraz potwierdzenia natychmiastowego revoke
pozostają niezaznaczone; do tego czasu TASK-0115 i G8.7 nie są zamknięte.
