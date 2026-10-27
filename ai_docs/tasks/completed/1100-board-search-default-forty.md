---
title: Domyślnie 40 wyników wyszukiwania plansz
status: done
last_updated: 2026-10-27
---

# TASK-1100 — Domyślnie 40 wyników wyszukiwania plansz

## Status

`done`

## Goal

Nowe wyszukiwanie plansz domyślnie wysyła limit 40 zamiast 15, lokalnie i przez linki udostępniania.

## Context

Operator polecił zmianę wartości domyślnej. Wspólny UI ma stałą BOARD_SEARCH_LIMIT_DEFAULT oraz osobny literal 15 w hooku ciągów. Zapisane i odtwarzane jawne limity pozostają bez zmian.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`. Wąska zmiana istniejącej stałej i jej konsumenta; osobny audyt niewymagany.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — liczba wyników wyszukiwania.
- `ai_docs/architecture/API_CONTRACT.md` — istniejący limit żądania 1–100.
- `ai_docs/architecture/CODE_MAP.md`

## Scope

Jedno źródło wartości domyślnej dla wspólnego UI i hooka ciągów. Bez zmiany API, zakresu 1–100, rankingu i ręcznie wybranego lub odtwarzanego limitu. Bez restartów, merge i push.

## Acceptance criteria

- [x] Pole i pierwsze żądanie pojedynczego wyszukiwania mają limit 40.
- [x] Nowy zestaw wielu wzorów w Adminie, linku gry i panelu wysyła 40.
- [x] Jawne limity z historii i localStorage nadal mają pierwszeństwo.
- [x] Testy zmienionego pionu, lint, typecheck, formatowanie, docs i mapa kodu przechodzą.

## Expected files

- `packages/board-search-ui/src/board-search-results-state.ts` — BOARD_SEARCH_LIMIT_DEFAULT.
- `packages/board-search-ui/src/use-board-search-sequence.ts` — inicjalizacja limitu.
- `packages/board-search-ui/test-interactions/board-search-limit.test.mjs` — dotychczasowy test domyślnej wartości.
- `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs` — asercja limitu nowego zestawu w trzech scope'ach.
- Wymagania i dokumenty zamknięcia taska.

## Verification

Z katalogu repozytorium; jawny timeout każdej komendy 120 s. Testy interakcji pakietu board-search-ui, lint zmienionych plików, typecheck pakietu, Prettier zmienionych plików, `npm run docs:check`, `npm run code-map:check` po regeneracji mapy. Kryterium zaliczenia: brak regresji, zachowane jawne limity 15 w istniejących scenariuszach odtwarzania.

## Outcome

Commit: v1.7.487 (hash dopisuje kolejny commit).

### Changed

- BOARD_SEARCH_LIMIT_DEFAULT wynosi 40; hook ciągów korzysta z tej samej stałej. Jawne limity z localStorage, historii i ręcznej edycji pozostają bez zmian.
- Istniejący test pierwszego wyszukiwania sprawdza 40 w polu i żądaniu. Scenariusze czterech wzorów w Adminie, linku i panelu sprawdzają limit 40 także po ponownym zamontowaniu niewysłanego zestawu.

### Verification results

- 127/127 testów interakcji, w tym istniejące regresje jawnych limitów odtwarzanych jako 15: PASS.
- ESLint zmienionych plików, typecheck pakietu board-search-ui i Prettier: PASS.
- Mapa kodu zregenerowana (bez zmiany treści); docs:check i code-map:check sprawdzone przed commitem.
- Kryteria akceptacji i właściwe punkty Definition of Done spełnione; testy ponownego montowania sprawdzają zapisany stan bez nadpisywania jawnych preferencji.

### Not completed

- Bez buildów, restartów, odbioru działających usług, merge i push. Bez zmian API i danych operatora; zastane usunięcia artefaktów poza commitem.
- Audyt krzyżowy niewymagany dla tej samodzielnej zmiany.

### Documentation updates

- ADMIN_APP opisuje domyślne 40 i polecenie operatora zastępujące wcześniejsze 15; task i CURRENT_STATE zamknięte przez task-close.

### Recommended next task

- Akceptacja i integracja dotychczas przygotowanych poprawek wyszukiwarki.
