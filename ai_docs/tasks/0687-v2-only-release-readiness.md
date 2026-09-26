---
title: TASK-0687 — T08 — readiness release V2-only
status: todo
last_updated: 2026-09-25
---

# TASK-0687 — T08 — readiness release V2-only

## Status

`todo`

## Goal

Potwierdzić przed operacją, że wydanie aplikacji działa z head 0125 bez obecności legacy relacji `public`.

## Context

Przed application DDL trzeba wykryć zależność procesu od usuwanych tabel bez zmieniania danych użytkownika.

## Dependencies / entry conditions

STOP B passed; T02–T07 done i udokumentowane. T09 nie jest uruchomiony.

## Recommended execution

`gpt-6-sol`, reasoning `high`; niezależny review `gpt-6-astra`, reasoning `high`. Każdy blocker środowiska lub niezgodność binary/revision zatrzymuje C.

## Relevant docs

- `AGENTS.md`, plan D-448, runbook T07
- testy routingu/lifecycle i konfiguracja uruchomienia API/workera

## Scope

- Na izolowanej bazie po 0125 uruchomić skończone smoke API/worker dla reprezentatywnej gry V2.
- Porównać build/revision/konfigurację planowanego release z testowanym artefaktem i zapisać wynik readiness.

## Out of scope

Apply production, nowy feature, permanent dev server, data import, deployment lub GC.

## Acceptance criteria

- [ ] API i worker w nowym procesie nie próbują odwołać się do legacy `public`.
- [ ] Wszystkie smoke są read-only lub korzystają wyłącznie z izolowanej bazy.
- [ ] Wynik zawiera revision aplikacji/Alembic i jednoznaczne go/no-go dla T09.

## Technical notes

Uruchomienia są kontrolowane PID-em i krótkim pollingiem; procesy są zatrzymywane po smoke. Nie należy startować drugiej kopii istniejącej usługi.

## Expected files

- Nowe (proponowane): `ai_docs/quality/LEGACY_PUBLIC_STORE_RELEASE_READINESS.md`.

## Test cases

- Fresh process/API/worker na isolated head 0125; active V2 game; public 65 relations absent; missing location remains fail-closed.

## Verification

```powershell
# Komendy smoke są ustalone z repo podczas taska i mają timeout <= 120 s.
```

## Risks / open questions

- Readiness jest dowodem na izolowanym środowisku, nie zgodą na T09.

## Outcome

Wypełnia agent po pracy.
