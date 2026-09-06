---
title: TASK-0497 — Anulowanie nieaktualnych odczytów Weryfikacji symboli
status: done
version: v0.10.212
---

# TASK-0497 — Anulowanie nieaktualnych odczytów Weryfikacji symboli

## Goal

Zapewnić, że zmiana zakresu Weryfikacji symboli rzeczywiście anuluje poprzednie
requesty strony, prefetchu i liczników, a jeden workspace wykonuje najwyżej
jeden request liczników naraz.

## Context

Obecne identyfikatory requestów chronią React przed zastosowaniem spóźnionej
odpowiedzi, ale nie przerywają `fetch`. Poprzednie żądania, a w konsekwencji
zapytania serwera, mogą nadal działać po zmianie gry, symbolu, stanu lub strony.

## Dependencies / entry conditions

- TASK-0359 i TASK-0360 są ukończone.
- Wygenerowany klient przyjmuje standardowe `RequestInit.signal`.
- Zmiana nie wymaga modyfikacji backendu ani OpenAPI.

## Recommended execution

`gpt-5.6-sol` z poziomem `high`: pion obejmuje stan React, kontrakt wrappera i
testy współbieżności, ale nie zmienia jeszcze cyklu życia połączenia SQL.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0359-fast-symbol-review-page-query.md`
- `ai_docs/tasks/completed/0360-decouple-symbol-review-counts.md`

## Scope

- przekazać opcjonalny `AbortSignal` przez klienta API i akcje Admina;
- wprowadzić koordynator requestów `page`, `prefetch` i `counts`;
- anulować poprzedni request danego rodzaju przed rozpoczęciem następnego;
- anulować wszystkie odczyty po zmianie filtrów, przeładowaniu i unmount;
- zachować request ID oraz kontrolę scope jako ochronę przed klientem
  ignorującym sygnał;
- traktować świadome anulowanie jako stan cichy, nie błąd UI.

## Out of scope

- PostgreSQL `statement_timeout`;
- anulowanie SQL po rozłączeniu klienta;
- przebudowa zapytania lub projekcji liczników;
- zmiana endpointów i wygenerowanego OpenAPI.

## Acceptance criteria

- [x] Zmiana gry, symbolu, stanu, confidence, rozmiaru strony lub kursora
      anuluje nieaktualne odczyty.
- [x] Jeden workspace ma najwyżej jeden aktywny request liczników.
- [x] Prefetch nie przeżywa zmiany filtra lub strony.
- [x] `AbortError` nie pokazuje komunikatu o awarii połączenia.
- [x] Klient API przekazuje ten sam sygnał do wygenerowanego requestu.
- [x] Testy Admina i klienta, lint oraz typecheck przechodzą.

## Technical notes

Koordynator posiada dokładnie jeden kontroler na kanał. `begin(channel)` najpierw
anuluje wcześniejszy kontroler, a `finish(channel, controller)` czyści kanał
wyłącznie wtedy, gdy kończy się nadal aktualne żądanie. Zapobiega to usunięciu
nowszego kontrolera przez spóźnione `finally` starszego requestu.

## Expected files

- Istniejący: `packages/admin-api-client/src/index.ts` — opcje i przekazanie
  sygnału dla listy oraz liczników.
- Istniejący: `apps/admin/src/features/symbol-reviews/symbol-review-actions.ts`
  — cichy wynik anulowania.
- Istniejący: `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`
  — integracja koordynatora.
- Nowy: `apps/admin/src/features/symbol-reviews/symbol-review-request-coordinator.ts`.
- Testy klienta, akcji i koordynatora.

## Test cases

- Drugi `begin('counts')` anuluje pierwszy sygnał i pozostawia jeden aktywny
  kontroler.
- Zakończenie starego requestu nie czyści nowszego kontrolera.
- Anulowanie wszystkich kanałów przerywa stronę, prefetch i liczniki.
- Akcje przekazują sygnał do klienta i zwracają `aborted`, gdy sygnał został
  anulowany.
- Wrapper klienta przekazuje sygnał do faktycznego `Request`.

## Verification

```powershell
node --test apps/admin/test/symbol-review-request-coordinator.test.mjs apps/admin/test/symbol-review-actions.test.mjs
node --test packages/admin-api-client/test/client.test.mjs
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin-api-client
```

## Risks / open questions

- Anulowanie `fetch` ogranicza pracę po stronie klienta, ale samo nie gwarantuje
  przerwania synchronicznego SQL. Ten zakres należy do TASK-0499.

## Outcome

- Opcjonalny `AbortSignal` przechodzi przez wrapper klienta i akcje strony oraz
  liczników do faktycznego requestu `fetch`.
- Koordynator rozdziela kanały `page`, `prefetch` i `counts`, zapewniając
  single-flight w każdym kanale oraz bezpieczne czyszczenie wyłącznie aktualnego
  kontrolera.
- Zmiana filtrów, nawigacja, reload i unmount aktywnie anulują zbędne odczyty;
  świadome anulowanie nie ustawia stanu błędu w UI.
- Zachowano request ID i porównanie scope'u jako defense-in-depth dla klienta,
  który nie respektowałby sygnału.
- Przeszły pełne testy Admina (426), testy klienta (52), lint oraz typecheck obu
  workspace'ów. Nie zmieniono backendu, OpenAPI ani bazy danych.
