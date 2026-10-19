---
title: Rozmiar strony weryfikacji symboli
status: done
last_updated: 2026-10-19
---

# TASK-1070 — Rozmiar strony weryfikacji symboli

## Status

`done`

## Goal

Dodać 100 do filtra „Na stronę” i ustawić domyślny rozmiar strony na 2500.

## Context

Bezpośrednie polecenie operatora z 2026-10-19. Dotychczasowy domyślny rozmiar
wynosi 500, a lista opcji to 500, 1000, 2000 i 2500.

## Dependencies / entry conditions

Brak pytań blokujących. Backend już obsługuje limit 1–2500. Widok inicjalizuje
filtry ze wspólnej stałej; nie wymaga zmiany API ani zapisu preferencji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md` — Weryfikacja symboli.
- `ai_docs/architecture/API_CONTRACT.md` — Odczyt pojedynczych cropów do weryfikacji symboli.
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — stronicowanie i atlasy.
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Uzupełnienie istniejącej listy opcji o 100 i domyślny rozmiar 2500.
- Aktualizacja istniejącego testu i wymagań.

## Out of scope

Zmiany API, wirtualizacji, limitów backendu i uruchamianie usług.

## Acceptance criteria

- [x] Filtr pozwala wybrać 100, 500, 1000, 2000 i 2500.
- [x] Nowo otwarty widok domyślnie wybiera 2500.
- [x] Istniejące testy stanu i kontraktu widoku przechodzą.

## Expected files

- `apps/admin/src/features/symbol-reviews/symbol-review-state.ts` — DEFAULT_SYMBOL_REVIEW_PAGE_SIZE, SYMBOL_REVIEW_PAGE_SIZES.
- `apps/admin/test/symbol-review-state.test.mjs` — istniejący test rozmiarów strony.
- `ai_docs/requirements/ADMIN_APP.md` — lista i domyślny rozmiar strony.
- Nowy: `ai_docs/tasks/1070-symbol-review-page-size.md`; stan i archiwum aktualizuje skill task-close.

## Verification

Testy stanu i kontraktu widoku, ESLint zmienionego modułu, formatowanie testu,
typecheck Admina, regeneracja mapy kodu i docs:check. Każda komenda ma limit 120 s.

## Risks / open questions

Brak otwartych pytań. Większa strona domyślna używa istniejącej wirtualizacji i limitów.
Audyt krzyżowy niewymagany: zadanie nie należy do planu wymagającego audytu.

## Outcome

Commit: v1.7.445 / `a978fa701b0679621a5b10fc2b1ed4a9a74ea690`.

### Changed

- Dodano 100 do wspólnej listy rozmiarów strony, używanej przez selektor i walidację.
- Domyślny rozmiar wynosi 2500; INITIAL_FILTERS widoku korzysta z tej stałej.
- Zaktualizowano istniejący test opcji i wartości domyślnej oraz wymagania Admina.

### Verification results

- `node --experimental-strip-types --test test/symbol-review-state.test.mjs test/symbol-review-workspace-contract.test.mjs` w `apps/admin`: 26/26 PASS, nowy proces.
- ESLint zmienionego modułu i testu: PASS.
- Prettier zmienionego testu: PASS. Format modułu poza zmienionymi stałymi zachowano.
- `tsc --noEmit` w `apps/admin`: PASS.
- `scripts/generate_code_map.py`: wykonano, bez zmian wygenerowanych map.
- `npm run docs:check`: PASS; kontrola zamknięcia skryptem: PASS.
- Kontrola aktualności mapy kodu: PASS.
- Wszystkie kryteria akceptacji i właściwe punkty Definition of Done spełnione.

### Not completed

- Nie wykonywano odbioru w przeglądarce ani restartu usług, buildu i szerokich testów: zmiana dwóch stałych, zweryfikowana istniejącymi testami.
- Audyt krzyżowy niewymagany; brak planu wymagającego dodatkowego review.

### Documentation updates

- `ADMIN_APP.md`: lista opcji i domyślny rozmiar strony.
- Stan i archiwum zadania aktualizuje skrypt zamknięcia.

### Recommended next task

- Odbiór operatora po odświeżeniu widoku. Brak znanych blokerów lub dalszych zmian w tym zakresie.
