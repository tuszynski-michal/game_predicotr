---
title: Wyszukiwanie ciągu plansz — API i historia
status: done
---

# TASK-1091 — Wyszukiwanie ciągu plansz — API i historia

## Status

`done`

## Goal

Udostępnić deterministyczny ranking 1–4 kolejnych układów w Admin API i obu linkach, z kompletną historią i zachowaniem kontraktu pojedynczej planszy.

## Context

Zadanie A zaakceptowanego planu. Operator 2026-10-24 zaakceptował cały plan i koszt implementacji z testami; nie zezwolił na migrację jego bazy, restarty ani merge do main. Dwa audyty implementacji (A high, B medium) należą do zaakceptowanego kosztu; nie są kolejnymi audytami planu.

## Dependencies / entry conditions

Plan 3.1 po audytach: przyjęty 2026-10-24. Czysty worktree od main 59ddbca3, gałąź codex/board-search-sequence-implementation. Numery 1091/1092 sprawdzone w lokalnych gałęziach i aktywnych katalogach. Główny checkout i usługi pozostają nietknięte.

## Recommended execution

gpt-6.1-sol / high. Ranking SQL, kontrakt, dane dowodowe i migracja wymagają spójnego pionu. Audyt Claude Code claude-opus-5-5 / high, przed commitem. Zatrzymać przy niedostępności modelu lub otwartym P0/P1 po jednej rundzie poprawek.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md — A i wspólne reguły
- ai_docs/requirements/ADMIN_APP.md — wyszukiwanie i udostępnianie
- ai_docs/architecture/API_CONTRACT.md — board-search, historia i korekty
- ai_docs/architecture/CODE_MAP.md oraz CODE_MAP_SYMBOLS.md
- ai_docs/process/DECISION_LOG.md — D-548 (panel), D-570

## Scope

- Czysty ranking referencyjny i ranking SQL bez top-N, cykl według expected_layout_count.
- POST Admin/public, OpenAPI, klient/wrapper, oba proxy, limity strumienia i autoryzacja.
- Historia v2, tożsamości legacy, replay API, filtr korekt searchEventId, kontekst snapshotu.
- Migracja limitu logu 4096→32768 i testy tylko izolowanej bazy testowej.
- Timeout z SAVEPOINT, niższy istniejący limit, stabilne błędy, obsługa supergier.

## Out of scope

UI badży i trwałość przeglądarki należą do TASK-1092. Bez operator DB, restartów, benchmarku, merge/push i zmian wypłat.

## Acceptance criteria

- [x] POST1 daje te same wyniki co GET; 2–4 wzory uwzględniają pełną sekwencję bez indywidualnego top-N.
- [x] SQL i domena zgodne na PostgreSQL; wrap, luka, k>L, 777a2, scope i remisy pokryte.
- [x] Oba proxy przepuszczają jedynie dozwolony POST, 32 KiB wyłącznie dla niego; brak wycieku ID i nieograniczonego body.
- [x] Historia/grupowanie/wholePattern/korekty obsługują v2 oraz niezmienione klucze legacy.
- [x] Migracja i downgrade z ochroną danych sprawdzone na *_test; baza operatora nietknięta.
- [x] Zmienione testy, lint/typy, OpenAPI, docs i mapa przechodzą; audyt rozliczony jako timeout, bez werdyktu.

## Technical notes

Wiążące algorytm, kontrakty, walidacja, granice transakcji i błędy są w zaakceptowanym planie A (rewizja 3.1). Kotwica wygranej to koniec ciągu; korekta detalu używa istniejącego start=edytowana plansza, bez rozszerzenia zakresu serwera. Pusty/same ? wzór nie uruchamia rankingu. Nie powielać istniejących endpointów w nowej rodzinie tras.

## Expected files

- Istniejące: domain/application/api/schemas board_search; storage/board_search_projection_repository.py, board_search_share_*; main.py; modele i nowa migracja Alembic.
- Istniejące: packages/admin-api-client, apps/reviewer/src/security/board-search-*-proxy.ts.
- Proponowane: domain/board_search_sequence.py, storage/board_search_sequence.py, api/board_search_sequence_body.py i odpowiadające testy.

## Test cases

Mapa testów planu A: POST1=GET, najlepszy ciąg poza top100, wrap, braki, k>L, różne mianowniki, wyjątek 777a2, exact/alternatywy/unknown, timeout+restore+log, maksymalne kody Unicode, 32 KiB streaming, legacy/v2 grouping i korekty, upgrade i bezpieczny downgrade.

## Verification

Komendy planu przez subprocess.run(timeout=120, check=True), pytest bezpośrednio, testy npm pakietów klienta i Reviewera. PostgreSQL tylko po asercji izolowanej nazwy *_test. Wyniki będą w Outcome.

## Risks / open questions

Nie uruchamiać nowego kodu na starej bazie operatora. Brak benchmarku i fizycznego Androida nie jest wynikiem pozytywnym.

## Outcome

Commit: v1.7.467 / `9319bde6392c2e913a49cccb08eafa7a3290ebed`.

### Changed

- Dodano referencyjny ranking domenowy i SQL ciągów, jawne wiązanie magazynu gry, timeout z SAVEPOINT i zachowaniem niższego limitu.
- POST Admin/public, ograniczony body streaming, pełny klient OpenAPI i wrapper, oba proxy z zachowaniem ochrony Origin/cookie.
- Historia v2, grupowanie/wholePattern/replay, kompatybilne klucze legacy, filtr korekt searchEventId i pochodny patternCount.
- Migracja 0169 zwiększa constraint logu do 32 KiB i blokuje downgrade z większymi wpisami. Zastosowana wyłącznie w jednorazowych bazach *_test.

### Verification results

- Nowy pion i regresje API/historii: 39 PASS; domena i istniejące repozytorium: 50 PASS.
- PostgreSQL: 8 PASS — SQL=domena, wrap/luki, timeout/restore, pełna migracja w fixture, ochronny downgrade, maksymalny Unicode snapshot, izolacja filtra korekt.
- Istniejąca integracja korekt: 1 PASS (39,46 s), w tym receipt/retry i odczyt po nowym procesie Pythona.
- Klient API: 134 PASS; Reviewer: 290 PASS, w tym nowe proxy i zgodność allowlisty OpenAPI.
- Ruff PASS. Mypy z normalnie rozwiązywanymi importami i follow-imports=silent: 6 nowych/core + 8 zmienionych + main/models 2 pliki PASS. Pierwsza próba skip-imports była niewłaściwa dla tego grafu i została zastąpiona pełnym rozwiązywaniem importów; bez osłabiania typów w kodzie.
- ESLint zmienionych plików Reviewera PASS; typecheck Reviewera PASS. OpenAPI (oba klienty), docs:check i code-map:check PASS.
- W sandboxie TestClient zatrzymywał się w socketpair asyncio; testy HTTP i połączenia testowe uruchomiono poza sandboxem. Nie uruchamiano API/Admina jako usług.

### Not completed

- Audyt Claude Code `claude-opus-5-5` / high uruchomiony przed commitem, przerwany po 480 s bez werdyktu. [Zapis próby](../../quality/TASK-1091_AUDIT_TIMEOUT_20261024.md). Brak wyniku nie oznacza PASS; zgodnie ze skillem timeout nie blokuje taska. Bez automatycznego ponowienia.
- UI i trwałość należą do TASK-1092. Brak benchmarku i odbioru fizycznego Androida w zadaniu A.
- Baza operatora, restarty, main i origin nietknięte.

### Documentation updates

- Zaakceptowany plan, zadania, D-573, wymagania, API_CONTRACT i DATA_MODEL; mapa kodu zregenerowana.

### Recommended next task

TASK-1092 — Badże i trwałość po zamknięciu TASK-1091.
