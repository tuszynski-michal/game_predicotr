---
title: TASK-0019 Admin shell and games identity UI
status: in_progress
last_updated: 2026-07-26
---

# TASK-0019 — Admin shell and games identity UI

## Goal

Dostarczyć lokalny interfejs panelu do listowania, tworzenia, edycji statusu i
archiwizacji tożsamości gier przez typowany Admin API.

## Context

TASK-0018 udostępnił domenę, PostgreSQL i kontrakt CRUD. Drugi pion M2.2
zastępuje ekran fundamentu pierwszym rzeczywistym workflow administratora,
zachowując wymiary, koszt spinu i symbole dla kolejnych zadań.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- trwały shell panelu z nawigacją i informacją o lokalnym działaniu,
- ekran katalogu gier używający wygenerowanego klienta,
- stany loading, empty, error i success oraz jawny Retry,
- formularz tworzenia gry z kodem, nazwą i statusem,
- edycja nazwy i statusu bez możliwości zmiany stabilnego kodu,
- jawne potwierdzenie archiwizacji bez fizycznego usuwania,
- blokada wielokrotnego submitu i czytelny feedback błędu/sukcesu,
- responsywny układ oraz podstawowa dostępność klawiatury i etykiet,
- testy logiki widoku i interakcji z typowanym klientem.

## Out of scope

- pola wymiarów planszy i kosztu spinu,
- katalog i formularze symboli oraz obrazy referencyjne,
- wersje reguł, paylines, payout rules i datasety,
- autoryzacja, publiczny deployment i połączenie z aplikacją mobilną.

## Acceptance criteria

- [ ] panel po wejściu pobiera i pokazuje listę gier,
- [ ] brak danych, ładowanie i błąd API mają osobne czytelne stany,
- [ ] administrator tworzy grę z kodem, nazwą i statusem,
- [ ] formularz waliduje wymagane wartości i blokuje podwójny submit,
- [ ] edycja pozwala zmienić nazwę/status, ale nie stabilny kod,
- [ ] archiwizacja wymaga jawnego potwierdzenia i pozostawia grę na liście,
- [ ] sukces i błąd zapisu są przekazywane tekstem, nie tylko kolorem,
- [ ] UI nie zawiera jeszcze wymiarów, kosztu spinu ani edycji symboli,
- [ ] produkcyjny build, lint, typecheck, testy i pełna bramka jakości przechodzą.

## Technical notes

- prosty lokalny stan React jest wystarczający dla pierwszego katalogu; warstwa
  cache nie jest dodawana bez potrzeby,
- formularz używa typów `GameCreate`, `GameUpdate` i `GameStatus` wyłącznie z
  `@game-predictor/admin-api-client`,
- po udanym zapisie lokalna lista jest aktualizowana z odpowiedzi API bez
  dodatkowego, ukrytego requestu,
- `DELETE` w UI jest opisywany jako „Archiwizuj”, zgodnie z D-024.

## Expected files

- `apps/admin/src/app/page.tsx`
- `apps/admin/src/app/globals.css`
- `apps/admin/src/features/games/**`
- `apps/admin/src/components/**`
- `apps/admin/test/**`
- `apps/admin/package.json`
- `package-lock.json`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run admin:build
npm run quality
```

## Risks / open questions

- Brak pytania blokującego. UI symboli dołączy do tego samego shellu w
  TASK-0020.

## Outcome

Do uzupełnienia po implementacji.
