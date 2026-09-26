---
title: TASK-0686 — T07 — instrukcja operacyjna usunięcia legacy public
status: done
last_updated: 2026-09-26
---

# TASK-0686 — T07 — instrukcja operacyjna usunięcia legacy `public`

## Status

`done`

## Goal

Opisać powtarzalny preflight, explicit approval, apply i postflight 0125 bez mylenia `public` catalog plane z legacy data plane.

## Context

T09 jest operacją destrukcyjną mimo pustości tabel; operator potrzebuje dokładnego, audytowalnego runbooka.

## Dependencies / entry conditions

T05–T06 done. Żadna komenda produkcyjna nie trafia do instrukcji bez potwierdzonego rehearsal.

## Recommended execution

`gpt-6-sol`, reasoning `high`; niezależny review `gpt-6-astra`, reasoning `medium`. Brak konkretnych kryteriów abortu blokuje STOP B.

## Relevant docs

- `AGENTS.md`, plan D-448, T01/T05/T06
- `guides/LOCAL_OPERATION_GUIDE.md`, `quality/` i istniejące instrukcje migracji

## Scope

- Runbook z rolami, wymaganym aktualnym raportem, komendami read-only, wymaganym tekstem potwierdzenia, limitami i oczekiwanymi rezultatami postflight.
- Jednoznaczne rozróżnienie: 65 legacy relacji usuwa się; catalog/control/shared pozostają.
- Utrwalenie lokalizacji raportu, checksumy, Alembic revision i kryteriów stop/retry.

## Out of scope

Automatyczne uruchomienie migracji, instrukcja `DROP ... CASCADE`, GC, backup policy i usuwanie partycji V2.

## Acceptance criteria

- [ ] Runbook nie dopuszcza apply bez świeżego preflightu i jawnego potwierdzenia.
- [ ] Zawiera odrębne reakcje na niepustość, lock, timeout, drift i postflight failure.
- [ ] Recenzent może odtworzyć checklistę bez historii rozmowy.

## Technical notes

Polecenia Windows PowerShell są skończone i nie ujawniają sekretów. „Co zrobić po błędzie” opisuje zatrzymanie i stan do zebrania, nie automatyczne cofnięcie.

## Expected files

- Nowe: `ai_docs/guides/LEGACY_PUBLIC_STORE_REMOVAL.md`.
- Zmienione: indeks dokumentacji, jeśli instrukcja zostanie dodana.

## Test cases

- Review checklisty przez niezależnego wykonawcę: brak approval/raportu/warunku jobs → nie da się przejść do apply.

## Verification

```powershell
rg -n "CASCADE|approval|preflight|postflight|game_data_v2|shared" ai_docs/guides/LEGACY_PUBLIC_STORE_REMOVAL.md
```

## Risks / open questions

- Dane po T01 mogą się zmienić; runbook wymaga nowego raportu również w T09.

## Outcome

Dodano runbook `ai_docs/guides/LEGACY_PUBLIC_STORE_REMOVAL.md` i indeks w
`ai_docs/README.md`. Dokument wymaga świeżego checksummowanego preflightu,
opisuje jedyne dozwolone `alembic upgrade 0125`, osobne approval z path/hash
raportu oraz postflight ze znanym, dokładnie ograniczonym wynikiem 65 missing
relacji. Zawiera reakcje na niepustość, lock, timeout, drift i postflight
failure bez ręcznego DDL, `CASCADE`, downgrade lub auto-retry. Weryfikacja
`rg` potwierdziła wymagane bramki. Nie uruchomiono komendy apply ani nie
dotknięto bazy użytkownika.

Następny krok: STOP B — pokazać świeży preflight i review DDL operatorowi.
T08/T09 nie rozpoczynają się bez tego punktu i odrębnej zgody T09.
