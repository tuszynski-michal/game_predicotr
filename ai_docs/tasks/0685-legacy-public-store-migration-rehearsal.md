---
title: TASK-0685 — T06 — rehearsal migracji legacy public
status: todo
last_updated: 2026-09-25
---

# TASK-0685 — T06 — rehearsal migracji legacy `public`

## Status

`todo`

## Goal

Zweryfikować, że release i 0125 mają kontrolowaną ścieżkę wykonania, timeouty, diagnosowalny fail oraz postflight bez dotykania bazy użytkownika.

## Context

85 GB bazy nie zmienia małego zakresu DDL, lecz zwiększa wagę locków i operator-facing dowodów.

## Dependencies / entry conditions

T05 done z niezależnym review i zielonym izolowanym PostgreSQL. Rehearsal działa wyłącznie na odtwarzalnym klonie/test database.

## Recommended execution

`gpt-6-astra`, reasoning `high`; niezależny review `gpt-6-sol`, reasoning `high`. Timeout, niespójny raport lub częściowy state jest blokadą STOP B.

## Relevant docs

- `AGENTS.md`, plan D-448, T05 migration
- istniejące konwencje timeoutów Alembic i `quality/`

## Scope

- Udowodnić na izolowanym PostgreSQL preflight → Alembic 0125 → nowa sesja postflight.
- Ustalić bounded `lock_timeout`, `statement_timeout`, warunek braku aktywnych maintenance/jobs i raport katalogu przed/po.
- Przetestować odrzucenie niepustej tabeli, blokady i błędu przed DDL.

## Out of scope

Production DB, benchmark pełnego backupu, kasowanie danych, „rollback” DDL i zmiana aplikacji poza obsługą istotnego findingu T05.

## Acceptance criteria

- [ ] Rehearsal ma powtarzalny transcript z wersjami, checksum raportów i kompletnym postflightem.
- [ ] Każdy negatywny scenariusz kończy się bez utraty relacji spoza świadomie testowanego scope.
- [ ] Ustalona instrukcja przekazuje do T09 mierzalne warunki start/stop.

## Technical notes

Nie symulować sukcesu przez wyłączenie locków lub FK. Jeśli test wykryje częściowy wynik po błędzie infrastruktury, zatrzymać plan i opisać dokładny stan katalogu potrzebny do ręcznej oceny.

## Expected files

- Nowe (proponowane): `ai_docs/quality/LEGACY_PUBLIC_STORE_MIGRATION_REHEARSAL.md` oraz test/rehearsal helper wyłącznie jeśli potrzebny.

## Test cases

- Happy path; row exists; dependency exists; advisory/DDL lock timeout; nowy proces po head; brak `CASCADE` w SQL.

## Verification

```powershell
# Rehearsal uruchomiony tylko na izolowanej bazie, skończony proces z timeoutem <= 120 s na krok.
```

## Risks / open questions

- Realne wartości timeoutów pochodzą z obserwacji środowiska, nie z tego planu.

## Outcome

Wypełnia agent po pracy.
