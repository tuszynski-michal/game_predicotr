---
title: TASK-0691 — T12 — końcowy odbiór V2-only
status: todo
last_updated: 2026-09-25
---

# TASK-0691 — T12 — końcowy odbiór V2-only

## Status

`todo`

## Goal

Zamknąć plan dowodem, że V2 jest jedynym game data plane oraz że dokumentacja i ryzyka odzwierciedlają stan rzeczywisty.

## Context

Końcowy odbiór następuje dopiero po DDL, operational acceptance i usunięciu martwych pathów.

## Dependencies / entry conditions

T11 done, T10 report aktualny, Alembic head i manifests bez driftu. Niewyjaśniony finding blokuje zamknięcie.

## Recommended execution

`gpt-6-astra`, reasoning `high`; niezależny review `gpt-6-sol`, reasoning `high`. Rozbieżność dokumentacja–DB–runtime wymaga korekty właścicielskiego źródła przed `done`.

## Relevant docs

- `AGENTS.md`, plan D-448, `CURRENT_STATE.md`, `DATA_MODEL.md`, `DECISION_LOG.md`
- Raporty T01, T06, T08, T09, T10 oraz testy migration/routing

## Scope

- Zestawić evidence z etapów, ponowić bounded read-only catalog/schema audit oraz sprawdzić nowy proces.
- Zaktualizować źródła prawdy i przenieść ukończone taski zgodnie z AGENTS.md.
- Opisać wyłączone zakresy i brak downgrade jako świadome ryzyko/ograniczenie.

## Out of scope

Nowe DDL, modyfikacja danych, GC, migracja katalogu/shared i automatyczne wdrożenie.

## Acceptance criteria

- [ ] Baza/runtime/dokumentacja zgodnie mówią: V2 jest jedynym game-owned store, `public` pozostaje catalog/control/shared.
- [ ] Końcowy raport zawiera traceability od D-448 przez preflight, migration i restart acceptance.
- [ ] Nie ma nierozwiązanych P0–P2 ani nieudokumentowanego odchylenia od planu.

## Technical notes

Odbiór nie zastępuje rollbacku: po utracie danych historycznych pełna rekonstrukcja nie jest obiecywana. Wszystkie raporty wykluczają sekrety i niepotrzebne ścieżki użytkownika.

## Expected files

- Nowe: `ai_docs/quality/LEGACY_PUBLIC_STORE_FINAL_ACCEPTANCE.md`.
- Zmienione: `CURRENT_STATE.md`, `DATA_MODEL.md`, `DECISION_LOG.md`, indeksy i task outcomes zgodnie z wynikiem.

## Test cases

- Manifest vs schema; V2 active locations/partycje; brak 65 legacy tables; catalog/shared zachowany; fresh process routing.

## Verification

```powershell
# Read-only audit i testy zestawione przez wcześniejsze taski; każda komenda z timeoutem <= 120 s.
```

## Risks / open questions

- Przyszła zmiana własności danych wymaga nowej decyzji i migracji, nie reaktywacji `public`.

## Outcome

Wypełnia agent po pracy.
