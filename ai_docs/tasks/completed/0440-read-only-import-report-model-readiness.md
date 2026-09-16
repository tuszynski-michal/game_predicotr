---
title: TASK-0440 Read-only import report model readiness
status: done
last_updated: 2026-09-04
---

# TASK-0440 — Raport importu dostępny przed aktywacją modelu symboli

## Problem

Po ochronie katalogu klas z TASK-0439 przycisk `Pokaż raport` dla gotowego
stagingu kończy się `SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED`. Read-only raport
wywołuje ten sam rygorystyczny resolver co start importu, przez co operator nie
może zobaczyć zakresów ani rozpocząć niezależnego preflightu geometrii.

## Scope

- raport stagingu zwraca jawny stan gotowości modelu symboli,
- brak zgodnego modelu nie blokuje odczytu raportu ani preflightu geometrii,
- fingerprint modelu jest obecny wyłącznie dla gotowego snapshotu,
- start importu nadal wymaga zgodnego, aktywnego modelu i aktualnego raportu,
- Admin pokazuje po polsku wymagany krok i blokuje wyłącznie start importu,
- OpenAPI, wygenerowany klient i testy pozostają zgodne.

## Out of scope

- uruchamianie treningu, aktywacji, importu albo joba na danych użytkownika,
- przywrócenie niezgodnego globalnego bootstrapu,
- automatyczne przenoszenie zatwierdzeń między różnymi cropami,
- import bez inferencji symboli.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Definition of Done

- brak zgodnego bootstrapu zwraca raport HTTP 200 z jawną blokadą modelu,
- preflight geometrii pozostaje dostępny,
- start importu bez zgodnego modelu kończy się stabilnym konfliktem i nie
  tworzy joba,
- gotowy model zachowuje dotychczasowy fingerprint oraz ścieżkę startu,
- UI wyjaśnia trening i aktywację zamiast pokazywać surowy angielski błąd,
- testy API, Admina, OpenAPI, lint, typecheck i build przechodzą.

## Outcome

- Raport browser stagingu używa tolerancyjnego resolvera preview i zwraca jawne
  pola gotowości modelu, nie blokując niezależnego preflightu geometrii.
- Start importu zachowuje rygorystyczny resolver; brak zgodnego aktywnego modelu
  zwraca stabilny konflikt i nie tworzy joba.
- Admin pokazuje stan modelu, polską instrukcję treningu/aktywacji i blokuje
  przycisk startu do czasu odświeżenia raportu z gotowym snapshotem.
- OpenAPI i klient zostały wygenerowane ponownie. Test regresyjny API potwierdza
  HTTP 200 raportu, dostępność geometrii oraz fail-closed start.
- Weryfikacja: 29 testów API, 393 testy Admina, 51 testów klienta, Ruff, ESLint,
  TypeScript, OpenAPI drift i produkcyjny build Admina przeszły. Ograniczony
  mypy nadal raportuje istniejące błędy importów bez `py.typed` oraz wcześniejsze
  błędy typów poza zmienionymi liniami.
