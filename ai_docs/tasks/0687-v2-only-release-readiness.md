---
title: TASK-0687 — T08 — readiness release V2-only
status: blocked
last_updated: 2026-09-26
---

# TASK-0687 — T08 — readiness release V2-only

## Status

`blocked`

## Goal

Potwierdzić przed operacją, że wydanie aplikacji działa z head 0125 bez obecności legacy relacji `public`.

## Context

Przed application DDL trzeba wykryć zależność procesu od usuwanych tabel bez zmieniania danych użytkownika.

## Dependencies / entry conditions

Użytkownik polecił rozpocząć T08; T02–T07 są done i udokumentowane. T09 nie
jest uruchomiony. STOP B w zakresie apply nadal wymaga świeżego preflightu i
osobnej zgody według runbooka.

Fakt wejściowy z sesji `2026-09-26` (TASK-0693): izolowany integracyjny test
`test_manual_deferred_geometry_materializes_one_complete_review_projection`
(`services/api/tests/integration/test_image_batch_store.py`) failuje na
świeżym head `0125` błędem `relation "source_images" does not exist`,
reprodukowalnym też na czystym `HEAD` bez niepowiązanych zmian. Ten sam plik
miał już wcześniej (commit `v0.10.447`) identyczny wzorzec błędu w innym
teście — bezscope'owy insert `SourceImageModel` przez zwykłą `Session(engine)`
zamiast `GameStorageSession` + V2 scope. To pierwszy konkretny sygnał
blokujący go/no-go T08 i naturalny punkt startu tego taska.

## Recommended execution

`gpt-6-sol`, reasoning `high`; niezależny review `gpt-6-astra`,
reasoning `medium`. Każdy blocker środowiska lub niezgodność binary/revision
zatrzymuje C.

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

### Changed

- Dodano powtarzalny smoke rzeczywistych entrypointów API/workera i probe
  tożsamości/PID. Release source-run ma revision oraz hash źródeł/config.
- Naprawiono trzy produkcyjne upserty (ukończony TASK-0697), część fixture
  (nieukończony TASK-0694); szczegóły w raporcie readiness.

### Verification results

- Smoke67,56s: worker completed, restart API, drugi worker no_job,
  65 public absent, zachowany catalog/shared i missing location409.
- Trzy czerwone asercje: dataset layouts500, review-batches500, geometry
  rollout422 schema3. Wszystkie procesy i izolowana baza posprzątane.
- Niezależne audyty upsertów oraz fixture/smoke: brak nowych P0–P2.
  Audit routingu potwierdził dwa P1 i krytyczny konflikt D-038/V2.
- Baza użytkownika0124 bez DDL/DML. Właściwy Python3.12.10 działa poza
  sandboxem; poprzednią diagnozę uszkodzonej instalacji sprostowano.
- Ruff/format/mypy smoke passed; szczegóły pozostałych testów i ograniczeń
  są w LEGACY_PUBLIC_STORE_RELEASE_READINESS.md.

### Not completed

- T08 no-go: kryterium poprawnego globalnego routingu API nie jest spełnione.
  Task blocked na decyzji TASK-0698; nie oznaczono go done.
- T09–T12 niewykonane. Dokładny apply wymaga później świeżego preflightu
  i osobnej zgody użytkownika, zgodnie z runbookiem.
- Pełna suite i część fixture nadal do ukończenia w TASK-0694.

### Documentation updates

- CURRENT_STATE, raport readiness, plan naprawczy i zgrupowany backlog0695;
  nowe pytanie architektoniczne0698. Ukończony0697 w completed.

### Recommended next task

- Rozstrzygnąć TASK-0698, wdrożyć zgodne rozwiązanie, domknąć0694 i ponowićT08.
