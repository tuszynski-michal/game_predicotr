---
title: TASK-0679 — plan usunięcia legacy magazynu public
status: done
last_updated: 2026-09-25
---

# TASK-0679 — plan usunięcia legacy magazynu `public`

## Status

`done`

## Goal

Zapisać implementowalny plan, taski i proponowaną decyzję D-448 dla przejścia na V2-only bez wykonania DDL ani zmian danych.

## Context

Aktywne gry są już greenfieldowo routowane do `game_data_v2`, lecz 65 pustych kopii game-owned pozostaje w `public`.

## Dependencies / entry conditions

Sprawdzono: TASK-0679–0691, D-448 i 0125 są wolne; Alembic kończy się na 0124. Zmiany obecne w worktree laboratorium wizji nie należą do tego taska.

## Recommended execution

`gpt-6-sol`, reasoning `high`; niezależny review `gpt-6-astra`, reasoning `medium`. Rozbieżność aktualnego manifestu, stanu migracji lub numeracji wymaga aktualizacji planu przed T01.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/architecture/DATA_MODEL.md`, `ai_docs/process/DECISION_LOG.md` (D-377, D-440)
- `ai_docs/quality/TASK_0525_GREENFIELD_CUTOVER_AUDIT.md`

## Scope

- Nowy plan `ai_docs/delivery/LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md`, TASK-0680–0691 i D-448 jako propozycja.
- Zapis zasad explicit approval, V2-only, `RESTRICT` i braku pozornego downgrade.

## Out of scope

Kod aplikacji, migracja 0125, database DDL, usuwanie danych lub plików oraz uruchamianie etapu A.

## Acceptance criteria

- [x] Plan odróżnia game-owned od catalog/control/shared i ma komplet tasków 0679–0691.
- [x] D-448 oraz finalna tabela modeli są zgodne z planem.
- [x] Plan zawiera bramki przed każdą operacją DDL i nie autoryzuje jej.

## Technical notes

Źródłem listy 65 tabel pozostaje zamrożony manifest v1. Każda zmiana fizyczna zależy od świeżego inventory, izolowanego testu PostgreSQL i osobnego potwierdzenia użytkownika.

## Expected files

- Nowe: `ai_docs/delivery/LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md` oraz TASK-0680–0691.
- Zmienione: `ai_docs/process/DECISION_LOG.md`, `ai_docs/process/CURRENT_STATE.md`, `ai_docs/README.md`.

## Test cases

- Weryfikacja wolności numerów i spójności linków/każdego taska z tabelą modeli.

## Verification

```powershell
rg -n "TASK-0679|TASK-0680|TASK-0691|D-448|0125" ai_docs services/api/alembic/versions
git diff --check
```

## Risks / open questions

- Pustość 65 tabel z 2026-09-25 jest historycznym faktem; T01/T09 sprawdzą ją ponownie.

## Outcome

### Changed

- Dodano plan V2-only, D-448 i backlog TASK-0680–0691.

### Verification results

- Numery były wolne przed zapisem; weryfikacja końcowa jest uzupełniana z commitem taska.

### Not completed

- Nie wykonano kodu, migracji, testów nowej implementacji ani DDL.

### Documentation updates

- Plan, decision log, Current State i indeks dokumentacji.

### Recommended next task

- T01 / TASK-0680 wyłącznie po jawnym uruchomieniu etapu A.
