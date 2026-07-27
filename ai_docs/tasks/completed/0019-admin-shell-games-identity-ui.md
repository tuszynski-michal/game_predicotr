---
title: TASK-0019 Admin shell and games identity UI
status: done
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

- [x] panel po wejściu pobiera i pokazuje listę gier,
- [x] brak danych, ładowanie i błąd API mają osobne czytelne stany,
- [x] administrator tworzy grę z kodem, nazwą i statusem,
- [x] formularz waliduje wymagane wartości i blokuje podwójny submit,
- [x] edycja pozwala zmienić nazwę/status, ale nie stabilny kod,
- [x] archiwizacja wymaga jawnego potwierdzenia i pozostawia grę na liście,
- [x] sukces i błąd zapisu są przekazywane tekstem, nie tylko kolorem,
- [x] UI nie zawiera jeszcze wymiarów, kosztu spinu ani edycji symboli,
- [x] produkcyjny build, lint, typecheck, testy i pełna bramka jakości przechodzą.

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

### Zmieniono

- dodano responsywny shell panelu z lokalną nawigacją i jawnym adresem API,
- zastąpiono ekran fundamentu katalogiem gier korzystającym wyłącznie z
  wygenerowanego klienta Admin API,
- dodano stany loading, empty, error/success, Retry, formularz create/edit,
  blokadę wielokrotnego submitu i jawne potwierdzenie archiwizacji,
- stabilny kod jest wyłączony w edycji, a archiwizacja aktualizuje status bez
  usuwania rekordu z listy,
- wydzielono czyste przejścia stanu i akcje UI–API; testy dowodzą, że create
  wysyła kod, update go nie wysyła, a archive używa identyfikatora,
- generator klienta przestał dopisywać `.js` do wewnętrznych importów źródeł
  TypeScript, dzięki czemu pakiet jest zgodny z produkcyjnym buildem Turbopack.

### Zweryfikowano

- `npm run test --workspace @game-predictor/admin` — 11/11 testów,
- `npm run typecheck --workspace @game-predictor/admin`,
- `npm run lint --workspace @game-predictor/admin`,
- `npm run openapi:check`,
- `npm run admin:build` — statyczna trasa `/` zbudowana poprawnie,
- lokalny smoke: panel HTTP 200, API `ok`, pusty katalog oraz poprawny preflight
  CORS dla `http://127.0.0.1:3000`,
- `npm run quality`.

### Nie wykonano

- nie dodano wymiarów, kosztu spinu ani symboli zgodnie z granicą zadania,
- automatyczna kontrola wizualna w oknie przeglądarki nie była dostępna z powodu
  ograniczenia uprawnień środowiska; render został zweryfikowany buildem i
  lokalnym żądaniem HTTP, a interakcje przez testowane akcje UI–API.

### Następny krok

`TASK-0020 — Symbols UI, reference assets and archival rules`.
