# Audyt TASK-0935 — Oznaczenie supergry w wyszukiwaniu plansz

Werdykt: REVISE
Audytor: Codex, etykieta briefu gpt-6-astra; reasoning niepotwierdzony
Wykonawca: claude-sonnet-5-5, high według zadania
Zakres: HEAD...9a2bbc685e2763553ce31b621c5e3c112e78e671 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie uruchamiał testów ani usług.

## Streszczenie

Implementacja obejmuje odczyt znaczników i świeżości jednym zapytaniem, integrację API oraz współdzielone oznaczenia kart i wierszy. Publiczne odpowiedzi usuwają identyfikator serii, a link Admina wskazuje właściwy widok. Pozostał brak ostrzeżenia przy pustym wyniku wyszukiwania oraz wymagane uzupełnienia dokumentacji przed commitem.

## Znaleziska

### P0

- [P0-1] `packages/board-search-ui/src/board-search-results.tsx:110` — Dla `results: []` komponent kończy renderowanie przed `SuperGameStateBanner`. Odpowiedź z `superGameState.fresh = false` pokazuje wyłącznie informację o braku dopasowania, bez wymaganego ostrzeżenia dla całego wyniku. Należy renderować baner również w pustym stanie i dodać test interakcyjny tego przypadku.

### P1

- [P1-1] `ai_docs/tasks/0935-board-search-super-game-marker.md:240` — Aktualizacja wymagań wyszukiwania w `ADMIN_APP.md` i stanu prac w `CURRENT_STATE.md` pozostaje jawnie niewykonana. Samo przypisanie tych czynności prowadzącemu nie spełnia wymagań dokumentacyjnych AGENTS.md i Definition of Done. Przed commitem należy opisać oznaczenia, ostrzeżenie świeżości oraz dostępność linku i uzupełnić stan TASK-0935. Hash nowego commita należy dopisać po jego utworzeniu zgodnie z procesem.

### P2

- [P2-1] `apps/reviewer/src/features/board-search-share/board-search-share-data-source.ts:216` — Trafienie w pięciominutową pamięć podręczną zwraca wcześniejsze znaczniki i `fresh = true` bez kontaktu z API. Zmiana wejścia albo super symbolu w innej sesji może więc pozostać niewidoczna także po ponownym wyszukiwaniu. Ograniczenie jest odnotowane w Outcome. Zalecane jest pomijanie cache dla odpowiedzi gier z supergrą albo jawna akceptacja tego opóźnienia.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Oznaczenie triggera i spinów w wynikach oraz przybliżonej wygranej | spełnione | `services/api/tests/test_board_search_super_game_api.py:226`, `:333`; `packages/board-search-ui/test-interactions/board-search-super-game.test.mjs:224`, `:344` |
| Właściwa seria w linku; brak linku w Reviewerze i panelu | spełnione | `apps/admin/test/board-search-super-game-link.test.mjs:15`; `packages/board-search-ui/test-interactions/board-search-super-game.test.mjs:300`, `:329` |
| Gra `none` bez oznaczeń | spełnione | `services/api/tests/test_board_search_super_game_api.py:295`; API reprezentuje brak znacznika jako `null`, zgodnie z opisem w `API_CONTRACT.md:316` |
| Zachowanie istniejących testów gry `none` | niezweryfikowane | Wyniki regresji zadeklarowano w Outcome; audyt nie uruchamiał testów |
| Ostrzeżenie dla całej odpowiedzi przy `fresh = false` | niespełnione | `packages/board-search-ui/src/board-search-results.tsx:110` — pominięcie pustego wyniku |
| Publiczne odpowiedzi bez `seriesId` | spełnione | `services/api/tests/test_board_search_super_game_api.py:370`, `:465`; konwersja publicznego wyszukiwania i wykluczenie pola w przybliżonej wygranej |
| Brak zmian sposobu naliczania wypłat | spełnione | `services/api/src/game_predictor_api/application/board_search_approximate_win.py:208` — znaczniki dołączane po kalkulacji |

## Listy zamknięte i otwarte

Zamknięte: Brak. Pierwsza runda audytu.

Otwarte: P0-1, P1-1, P2-1. Ryzyko P2-1 jest już opisane w Outcome.

## Proponowane testy

- W `packages/board-search-ui/test-interactions/board-search-super-game.test.mjs` dodać `results: []` ze stanem `fresh: false`; sprawdzić jednoczesną obecność komunikatu pustego wyniku i ostrzeżenia. Uruchomienie: `npm run test:interactions --workspace @game-predictor/board-search-ui`.
- Jeśli cache zostanie zmieniony, w `apps/reviewer/test/board-search-share-data-source.test.mjs` sprawdzić ponowne wyszukiwanie po zmianie generacji lub super symbolu. Uruchomienie: `npm run test --workspace @game-predictor/reviewer`.

## Zakres przeglądu i ograniczenia

Przejrzano brief, zadanie i Outcome, właściwe fragmenty planu, wymagań, kontraktu API oraz decyzji D-535/D-536. Sprawdzono zmiany backendu, repozytorium znaczników, schematów, adapterów konsumentów, współdzielonego UI i testów. Zweryfikowano również przepływ żywego podglądu panelu zarządzania oraz wyłączenie znaczników z historycznych migawek.

Podane wyniki testów, lintowania i kontroli typów pochodzą z deklaracji wykonawcy. Audyt nie potwierdza ich wykonaniem, nie obejmuje wizualnej oceny kolorów ani działania na uruchomionym PostgreSQL. Brak commita TASK-0935 jest prawidłowy na etapie audytu przed commitem.

## Nota leada po rundzie 1 (2026-10-09)

Wszystkie trzy uwagi naprawione przez wykonawcę: baner „Serie w trakcie przeliczania” renderowany także przy pustym wyniku (test interakcji), akapit o oznaczeniu supergry dodany do wymagania wyszukiwania plansz w `ADMIN_APP.md`, cache Reviewera pomijany dla odpowiedzi ze znacznikiem albo `fresh = false` (test źródła danych). board-search-ui 85 + 60, Reviewer 240, typecheck/lint/format PASS. Commit bez drugiej rundy zgodnie z regułą szybkiego audytu; `CURRENT_STATE.md` uzupełnia lead w tym commicie.
