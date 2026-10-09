# Audyt TASK-0936 - Rozwinięcie super symbolu i koszt per pozycja w prognozie Adminu

Werdykt: PASS
Audytor: Codex, etykieta briefu: gpt-6-astra / high
Wykonawca: claude-opus-5-5 / high
Zakres: HEAD...7062cdc3a3355f2971e2130bb711ece7242cb8ce oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Poprawki zamykają trzy znaleziska P0 z poprzedniego raportu. Wykres i piny korzystają z jawnych zakresów kosztów, wkład uwzględnia darmowy pierwszy spin, a odczyty kalkulatora i szczegółów obejmuje wspólna migawka. Pozostaje drobne ograniczenie miniatur wykresów na kartach panelu, opisane już w Outcome.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/management_result_snapshots.py:90` — Miniatury wykresów nadal powstają wyłącznie z punktów wypłat i końca zakresu. Bez wypłat na granicach serii łączą płatne i darmowe odcinki prostą, pomijając plateau darmowych spinów. Pełny wykres i wartości pinów korzystają już z dokładnych zakresów. Propozycja: dodać punkty graniczne przed redukcją miniatury albo zaakceptować ograniczenie jej poglądowej prezentacji. Ograniczenie odnotowano w Outcome.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Golden cases przechodzą w Pythonie i TS z identycznymi wynikami | niezweryfikowane | Wspólne oczekiwania fixture sprawdzają `services/worker/tests/test_super_game_payout.py:122` i `packages/shared-ts/test/super-game.test.mjs:56`. Wyniki PASS deklaruje Outcome; testów nie uruchamiano. |
| Regresja 777 zachowuje wyniki i zamrożone dane | niezweryfikowane | `services/api/tests/test_super_game_777_regression.py:193` porównuje skróty z baseline v1.7.279. Odpowiedzi normalizuje do wcześniejszego kontraktu; payload porównuje bez usuwania nowych pól. |
| Brak super symbolu daje osobno sumowany wynik prowizoryczny, mogący wzrosnąć lub zmaleć | spełnione | `services/api/src/game_predictor_api/domain/board_search_approximate_win.py:312`; scenariusze obu kierunków: `services/worker/tests/test_super_game_payout.py:154`. |
| Koszt serii wynosi 0; trigger ma koszt normalny | spełnione | `services/api/src/game_predictor_api/domain/sequence_mode_projection.py:79`; test projekcji: `services/api/tests/integration/test_board_search_super_game_postgres.py:99`. |
| Pełny wykres, piny i wkład uwzględniają koszt per pozycja | spełnione | `packages/board-search-ui/src/board-search-approximate-win-state.ts:181`, `:354`, `:640`. Miniatury: P2-1. |
| Reguły, plansze i generacja są odczytywane spójnie | spełnione | `services/api/src/game_predictor_api/storage/board_search_approximate_win_repository.py:56`; podłączenie w `services/api/src/game_predictor_api/main.py:745` i `:765`. |
| Nieświeża generacja oznacza wynik prowizoryczny także poza dotychczasowymi seriami | spełnione | `services/api/src/game_predictor_api/domain/board_search_approximate_win.py:306`; testy: `services/api/tests/test_super_game_payout_api.py:320` i `:349`. |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1:** dokładny koszt wykresu i pinów wynika z `superSpinRanges`; snapshot zachowuje te zakresy. Dowody: `packages/board-search-ui/src/board-search-approximate-win-state.ts:354`, `services/api/src/game_predictor_api/storage/management_result_snapshots.py:141`. Regresje: `packages/board-search-ui/test/board-search-super-game-payout.test.mjs:112`, `:136`.
- **P0-2:** wkład uwzględnia koszt pierwszego spinu według harmonogramu. Dowód: `packages/board-search-ui/src/board-search-approximate-win-state.ts:648`; test startu w serii: `packages/board-search-ui/test/board-search-super-game-payout.test.mjs:171`.
- **P0-3:** kalkulator i szczegół rozpoczynają migawkę przed odczytami; panel używa osobnej migawki. Dowody: `services/api/src/game_predictor_api/storage/board_search_approximate_win_repository.py:75`, `services/api/src/game_predictor_api/storage/management_game_adapter.py:182`. Test dwóch sesji: `services/api/tests/integration/test_board_search_super_game_postgres.py:195`.

Otwarte: P2-1.

## Proponowane testy

- Przy poprawianiu P2-1 rozszerzyć `services/api/tests/test_super_game_payout_api.py` o miniaturę serii bez wypłat, sprawdzając punkty początku i końca darmowego odcinka. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_super_game_payout_api.py -q`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task i Outcome, poprzedni raport, właściwe fragmenty wymagań, planu, kontraktu API i decyzji D-537. Sprawdzono poprawki projekcji kosztów, wykresu, pinów, wkładu, snapshotów panelu, spójności odczytów oraz odpowiadające im testy.

Nie uruchamiano testów, usług ani operacji na danych. Wyniki wykonawcy są deklaracjami z Outcome. Ocena zamknięcia znalezisk wynika z analizy kodu i testów, bez niezależnego potwierdzenia ich wykonania.

## Nota leada po rundzie 2 (2026-10-09)

Werdykt PASS. P2-1 (miniatury wykresów na kartach panelu zarządzania budowane tylko z punktów wypłat, bez punktów granicznych serii) zaakceptowane jako ograniczenie poglądowej prezentacji; pełny wykres, piny i wkład są dokładne. Pierwsza runda w `TASK-0936_AUDIT_gpt-6-astra_round1.md`.
