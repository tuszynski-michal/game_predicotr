---
title: TASK-0134 Admin 0.2 end-to-end usability and regression acceptance
status: done
last_updated: 2026-08-01
---

# TASK-0134 — Admin 0.2 end-to-end usability and regression acceptance

## Status

`done`

## Goal

Zweryfikować końcowy, mały workflow Admina 0.2 od pustej, izolowanej bazy do
gotowego testowego artefaktu oraz sprawdzić użyteczność trzech workspace'ów,
klawiaturę i stany loading/empty/error przed przekazaniem wersji właścicielowi.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- przygotować powtarzalny, ograniczony czasowo acceptance runner 0.2,
- użyć wyłącznie izolowanej bazy i małego kontrolowanego datasetu,
- sprawdzić pełny publiczny kontrakt od gry, symboli i reguł przez dataset,
  payout, wydanie, joby i cleanup,
- sprawdzić produkcyjny build Admina, trzy workspace'y, odtwarzanie URL,
  loading/empty/error, brak poziomego overflow oraz podstawową nawigację
  klawiaturą przy 1366 × 768,
- zapisać wersjonowany raport bez sekretów i ścieżek absolutnych,
- poprawić wyłącznie regresje wykryte w zakresie Admina 0.2,
- nie wykonywać destrukcyjnych scenariuszy na roboczych danych właściciela.

## Expected files

- runner i testy akceptacyjne w `scripts/` i `services/api/tests/integration/`,
- ewentualne poprawki Admina wykryte w odbiorze,
- raport w `ai_docs/quality/` lub kontrolowanym `artifacts/`,
- aktualizacja instrukcji operatorskiej i `CURRENT_STATE.md`.

## Acceptance criteria

- [x] workflow od pustej bazy do gotowego testowego wydania jest deterministyczny,
- [x] joby, retry/blokady i cleanup zachowują uzgodnione kontrakty,
- [x] trzy workspace'y nie duplikują kontekstu gry i odtwarzają stan z URL,
- [x] viewport 1366 × 768 nie ma poziomego overflow,
- [x] główne interakcje klawiatury, focus oraz stany loading/empty/error są czytelne,
- [x] konsola przeglądarki nie zgłasza nieobsłużonych błędów,
- [x] raport rozdziela testy automatyczne od końcowego odbioru właściciela,
- [x] lint, format, typecheck, testy, OpenAPI i build przechodzą w zakresie 0.2.

## Assumptions

- gotowy testowy artefakt może używać deterministycznego adaptera Android build
  z testów integracyjnych; fizyczny build i instalacja APK nie są powtarzane w
  tej bramce UX,
- bramka automatyczna nie zastępuje krótkiego odbioru właściciela na jego ekranie,
- pełne dane, kolejne gry i test urządzenia mobilnego pozostają poza TASK-0134.

## Outcome

Dodano ograniczoną czasowo komendę `npm.cmd run v02:admin:acceptance` i raport
maszynowy bez danych właściciela. Bramka wykonuje cztery testy na izolowanych,
migrowanych bazach PostgreSQL, 126 testów Admina, typecheck, lint, kontrolę
OpenAPI oraz produkcyjny build.

Pierwsze przebiegi wykryły nieaktualne `expectedLayoutCount` w dwóch fixture'ach
oraz zbyt długą ścieżkę tymczasową Windows. Fixture publicznego workflow ma cel
1000 layoutów, release ma cel 2, a pytest używa krótkiego, bezpiecznie
sprzątanego katalogu pod `.pytest-tmp`. Końcowy przebieg przeszedł w 56,8 s.

Odbiór przeglądarkowy produkcyjnego builda przy 1366 × 768 potwierdził trzy
workspace'y, odtwarzanie URL, czytelne puste stany, brak błędów konsoli i brak
poziomego overflow (`1351 <= 1366`). Szczegóły i oddzielna checklista odbioru
właściciela znajdują się w `ai_docs/quality/V0_2_ADMIN_ACCEPTANCE.md`.
