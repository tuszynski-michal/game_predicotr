---
title: TASK-0132 Simple Jobs workspace and status filters
status: done
last_updated: 2026-08-01
---

# TASK-0132 — Simple Jobs workspace and status filters

## Status

`done`

## Goal

Uprościć trzeci workspace Admina do czytelnej listy jobów z jednym filtrem
statusu, podstawowym postępem i krótkim błędem, pozostawiając szczegóły oraz
istniejące operacje pod jawnym rozwinięciem wybranego joba.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- pozostawić `Joby` jako osobny trzeci workspace,
- usunąć dodatkowy filtr typu z głównego widoku,
- filtrować po `Wszystkie` albo jednym statusie kontraktu API,
- pokazać w każdym zwartym wierszu typ, identyfikator/kontekst, status, postęp,
  czas utworzenia i krótki błąd,
- rozwijać metadane, retry/cancel i istniejące operacje obrazu dopiero po
  kliknięciu joba,
- zachować bounded pobieranie, polling aktywnych jobów i stabilne błędy,
- nie dodawać wyszukiwania, retencji, cleanupu ani nowej logiki kolejki.

## Expected files

- `apps/admin/src/features/jobs/job-monitor.tsx`
- `apps/admin/src/features/jobs/job-state.ts`
- `apps/admin/src/app/globals.css`
- testy stanu i kontraktu workspace'u Joby,
- dokumentacja bieżącego stanu.

## Acceptance criteria

- [x] główny widok ma dokładnie jeden filtr statusu,
- [x] wszystkie statusy API są dostępne wraz z opcją `Wszystkie`,
- [x] zwarty wiersz zawiera wymagane informacje i krótki błąd,
- [x] szczegóły i operacje pojawiają się dopiero po rozwinięciu joba,
- [x] polling, retry i cancel nadal działają,
- [x] nie powstała logika retencji ani cleanupu jobów,
- [x] testy, lint, typecheck i build Admina przechodzą.

## Outcome

Zrealizowano prosty workspace `Joby` z jednym filtrem statusu. Każdy job jest
prezentowany jako zwarty, responsywny wiersz zawierający typ, identyfikator i
kontekst, status, czytelny postęp, czas utworzenia oraz skrócony błąd. Techniczne
metadane, liczniki, pełny błąd, retry/cancel i dotychczasowe operacje importu
obrazów są dostępne dopiero po rozwinięciu wiersza.

Nie zmieniono kontraktu API, modelu jobów, kolejki, retencji ani cleanupu.
Zachowano bounded pobieranie i polling wyłącznie aktywnych jobów.

Weryfikacja:

- `node --experimental-strip-types --test apps/admin/test/*.test.mjs` — 121/121,
- `tsc --noEmit` — OK,
- `eslint .` — OK,
- `next build` — OK.
