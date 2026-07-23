---
title: Architecture decision log
status: active
last_updated: 2026-07-23
---

# Decision Log

Statusy: `proposed`, `accepted`, `rejected`, `superseded`.

## D-001 — Monorepo

- **Status:** proposed
- **Decision:** jeden repository z `apps/mobile`, `apps/admin`, `services/api`, `services/worker`, `packages` i `ai_docs`.
- **Reason:** prostsze kontrakty, jedna dokumentacja i łatwiejsza praca Codex.
- **Consequences:** różne narzędzia JS/Python muszą mieć jasne komendy root-level.

## D-002 — Mobile technology

- **Status:** proposed
- **Decision:** React Native + Expo + TypeScript.
- **Reason:** wykorzystanie doświadczenia React, szybki Android development, prosty routing.
- **Alternatives:** natywny Kotlin, Flutter, PWA.

## D-003 — Admin technology

- **Status:** proposed
- **Decision:** Next.js jako lokalna aplikacja webowa.
- **Reason:** znajoma technologia i brak potrzeby utrzymywania aplikacji desktopowej.
- **Alternatives:** Electron/Tauri, panel w FastAPI templates.

## D-004 — Backend

- **Status:** proposed
- **Decision:** FastAPI z logiką domenową oddzieloną od endpointów.
- **Reason:** Python dla obrazu, OpenAPI dla TypeScript, prosta testowalność.

## D-005 — Canonical database

- **Status:** proposed
- **Decision:** PostgreSQL jako źródło prawdy; SQLite tylko jako ewentualny snapshot offline.
- **Reason:** skala, indeksy, równoległy admin/worker, staging i publikacja.
- **Alternatives:** SQLite only, embedded database, document database.

## D-006 — Image jobs

- **Status:** proposed
- **Decision:** osobny Python worker/CLI i tabela import jobs; bez Celery/Redis w pierwszej wersji.
- **Reason:** długie zadania nie mogą blokować requestów, ale na starcie nie potrzebujemy rozproszonej kolejki.

## D-007 — Layout representation

- **Status:** proposed
- **Decision:** zwarta tablica `cells` oraz deterministyczna `signature`; bez osobnego rekordu na każdą komórkę w MVP.
- **Reason:** ograniczenie liczby wierszy przy milionach layoutów.
- **Validation needed:** benchmark prefix matching i wygoda SQLAlchemy.

## D-008 — Duplicate layouts

- **Status:** proposed
- **Decision:** signature nie jest unikalna. Niejednoznaczność jest rozwiązywana przez confirmation chain następnych layoutów.
- **Reason:** odpowiada opisowi domeny; nie wolno arbitralnie wybierać pierwszego wystąpienia.

## D-009 — Forecast presentation

- **Status:** proposed
- **Decision:** skrócona tabela pokazuje pierwszy dodatni wynik oraz każdy nowy dodatni high-water mark.
- **Reason:** interpretacja wymagania „następny rekord, kiedy kredyty znów zaczną rosnąć”.
- **Requires:** potwierdzenie Q-013.

## Szablon nowej decyzji

```text
## D-XXX — Tytuł

- Status:
- Date:
- Decision:
- Context:
- Reason:
- Alternatives:
- Consequences:
- Supersedes:
```
