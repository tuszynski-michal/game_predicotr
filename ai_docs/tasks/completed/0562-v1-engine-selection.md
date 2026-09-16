---
title: TASK-0562 — Wybór silnika v1.0
status: done
last_updated: 2026-09-16
---

# TASK-0562 — Wybór silnika v1.0

## Goal

Nowe importy używają domyślnie v1.0, a UI nie oferuje historycznych silników.

## Context

Zaakceptowany plan „v1.0 i v1.1 — selektywna korekta niepewnych plansz” w bieżącej rozmowie.

## Recommended execution

`gpt-5.6-sol high`; niezależny review `gpt-6-astra high` zgodnie z zaakceptowanym planem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Publiczna nazwa v1.0, domyślny wariant nowych uruchomień i wycofanie historycznych wyborów.
- Jednolite API, OpenAPI, wygenerowany klient, frontend i testy.
- Zachowanie starych snapshotów i wewnętrznej bazy v3.

## Out of scope

- Usuwanie danych i historycznych artefaktów.
- Algorytm v1.1, który jest osobnym TASK-0563.

## Acceptance criteria

- [x] Nowy import przeglądarkowy bez wariantu wybiera v1.0.
- [x] Po TASK-0563 publiczny wybór zawiera v1.0 i opt-in v1.1; stare warianty usunięto z panelu.
- [x] Stare joby są odczytywalne, a nowy browser staging nie używa starego silnika.
- [x] Idempotencja rozróżnia wynik historyczny i v1.0.
- [x] Testy, OpenAPI, klient, lint i typy zmienionych modułów przechodzą.

## Outcome

Domyślny wariant trzech żądań nowego browser stagingu to zapisany techniczny
identyfikator v1.0. API przypina wewnętrzny v3 niezależnie od starej polityki
gry; panel nie oferuje v20/v2/v3. Zachowano odczyt historii i idempotencję
zależną od efektywnego wariantu. Nie wykonano nowych jobów ani zmian danych.
Niezależne, starsze workflowy importu katalogowego nadal używają ich
historycznego kontraktu; nie były objęte zmianą browser stagingu.
