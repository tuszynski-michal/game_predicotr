---
title: TASK-0688 — T09 — zastosowanie usunięcia legacy public
status: todo
last_updated: 2026-09-25
---

# TASK-0688 — T09 — zastosowanie usunięcia legacy `public`

## Status

`todo`

## Goal

Po osobnym, dokładnym potwierdzeniu operatora zastosować 0125 raz i utrwalić dowód przed/po bez naruszenia catalog/control/shared lub V2.

## Context

To jedyny task planu wykonujący produkcyjne DDL. Pustość tabel nie czyni go automatycznym ani odwracalnym.

## Dependencies / entry conditions

T01–T08 done; świeży read-only preflight z runbooka T07 jest `ready`; podano jawne potwierdzenie dokładnego raportu/checksumy i zakresu 65 tabel; brak aktywnych jobs/maintenance/niezgodnych locków. Brak któregokolwiek warunku oznacza stop bez DDL.

## Recommended execution

`gpt-6-astra`, reasoning `high`; niezależny review `gpt-6-sol`, reasoning `high`. Niepodpisany raport, timeout, drift albo finding P0–P2 wymaga przerwania przed kolejnym krokiem.

## Relevant docs

- `AGENTS.md`, plan D-448, runbook `LEGACY_PUBLIC_STORE_REMOVAL.md`
- T01 inventory, T05 migration, T06 rehearsal, T08 readiness

## Scope

- Wykonać preflight read-only zgodnie z runbookiem, uzyskać osobną zgodę użytkownika i zastosować wyłącznie `alembic upgrade 0125_remove_legacy_public_game_store`.
- Utrwalić report pre/post, revision, czas, wynik oraz katalog relacji pozostających/usuniętych.
- Przy błędzie zatrzymać operację i zebrać stan opisany w runbooku.

## Out of scope

`downgrade`, ręczne `DROP`, `CASCADE`, dane/plikowy GC, upgrade dalszych niezatwierdzonych rewizji, push/merge/deployment oraz kontynuowanie po błędzie.

## Acceptance criteria

- [ ] Przed DDL istnieje aktualny, checksummowany preflight i jawna zgoda obejmująca ten raport.
- [ ] Po sukcesie head jest 0125, nie ma 65 legacy tabel, a control/shared/catalog/V2 przechodzą postflight.
- [ ] Przy odrzuceniu lub błędzie brak nieautoryzowanego DDL; state jest opisany do następnej decyzji.

## Technical notes

Nie używać shellowego globu ani ręcznie sklejonego SQL. Alembic jest jedyną ścieżką DDL. Ostateczna kontrola empty/dependencies zachodzi w kontrolowanej sesji migracji zgodnie z 0125. Jeżeli aplikacja ma być zatrzymana dla maintenance, wymaga to odrębnej instrukcji operatora; task nie kończy istniejących procesów samodzielnie.

## Expected files

- Istniejące: migracja 0125, runbook T07, raporty quality T01/T06/T08.
- Nowe: raport rzeczywistego apply/postflight w `ai_docs/quality/` bez sekretów.

## Test cases

- Aktualny `ready` → apply; brak exact approval → stop; niepusta relacja/lock/drift → stop przed DDL; po apply nowy proces nie widzi legacy tabel.

## Verification

```powershell
# Wyłącznie komendy zatwierdzonego runbooka; każda skończona z limitem i raportem.
```

## Risks / open questions

- Ten task nie wolno rozpocząć na podstawie samego planu lub wyniku rehearsal.

## Outcome

Wypełnia agent po pracy.
