# Audyt TASK-0936 — Rozwinięcie super symbolu i koszt per pozycja w prognozie Adminu

Werdykt: REVISE
Audytor: gpt-6-astra, high
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...7062cdc3a3355f2971e2130bb711ece7242cb8ce oraz zmiany niezacommitowane, data 2026-10-09
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Ewaluatory Python i TypeScript realizują wymagane rozwinięcie, zachowują sztuki z planszy oryginalnej i rozdzielają wypłaty prowizoryczne. Backend sumuje koszt per pozycja, ale wykres i etykiety wkładu nadal zawierają założenia o płatnych spinach. Odczyty kalkulatora i szczegółów planszy poza migawką panelu mogą dodatkowo połączyć dane z różnych stanów bazy.

## Znaleziska

### P0

- [P0-1] `packages/board-search-ui/src/board-search-approximate-win-state.ts:266` — **Piny i wartości wykresu naliczają koszt darmowych spinów.** Funkcja wykrywa supergrę wyłącznie przez wiersze z dodatnią wypłatą, a między wierszami dolicza normalny koszt. W przykładzie z `packages/board-search-ui/test/board-search-super-game-payout.test.mjs:110` spiny 3–6 są darmowe: bilans po spinie 6 powinien wynosić 45, lecz test utrwala błędne 35. Jeśli żaden darmowy spin nie ma wypłaty, błędny jest również punkt końcowy, ponieważ `freeSpins` pozostaje `false`. Dotyczy to także zapisanego wyniku panelu: `management-result-view.tsx:134` przekazuje pozycje pinów do tego samego kalkulatora. Należy udostępnić dokładne zakresy kosztów w kontrakcie odpowiedzi i używać ich do wykresu oraz pinów, również po odtworzeniu snapshotu.

- [P0-2] `packages/board-search-ui/src/board-search-approximate-win-state.ts:560` — **Start wewnątrz serii zawyża wymagany wkład i stan kredytów.** `Math.min(-spinCost, ...)` wymusza wkład co najmniej równy kosztowi bazowemu, nawet gdy pierwszy i wszystkie rozpatrywane spiny są darmowe. Przy koszcie bazowym 100 i pierwszym darmowym spinie wypłacającym 50 funkcje zwracają wkład 100 oraz kredyty 150 zamiast odpowiednio 0 i 50. Należy liczyć minimum rzeczywistego bilansu przed wypłatami, zaczynając od zera i uwzględniając koszt każdej pozycji.

- [P0-3] `services/api/src/game_predictor_api/application/board_search_approximate_win.py:197` — **Świeża generacja może zostać zastosowana do wcześniej odczytanych plansz lub reguł.** Dokumenty są pobierane przed znacznikami; standardowa zależność w `main.py:743` nie ustanawia wspólnej migawki `REPEATABLE READ`. Równoległa korekta i publikacja generacji między odczytami pozwalają połączyć stare komórki z nowymi seriami oraz `fresh = true`, a następnie oznaczyć wynik jako `exact`. Ten sam problem występuje w `application/board_search_board_detail.py:230`. Jedno zapytanie znaczników zapewnia spójność znaczników ze stanem generacji, ale nie z wcześniej pobranymi wejściami wypłaty. Należy objąć reguły, plansze i znaczniki jedną migawką odczytu, analogicznie do `storage/management_game_adapter.py:107`, albo zastosować kontrolę wersji z ponowieniem całego odczytu.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Golden cases przechodzą w Pythonie i TS z identycznymi wynikami | niezweryfikowane | Obie implementacje testują wspólny zestaw: `services/worker/tests/test_super_game_payout.py:122`, `packages/shared-ts/test/super-game.test.mjs:56`. Wyniki PASS zapisano w Outcome; audyt nie uruchamiał testów. |
| Regresja 777: identyczne wyniki i zamrożone dane | niezweryfikowane | `services/api/tests/test_super_game_777_regression.py:188` porównuje skróty z baseline. Odpowiedzi porównuje po normalizacji do starego kształtu, ponieważ kontrakt otrzymał nowe pola. |
| Brak super symbolu daje osobny wynik prowizoryczny, mogący wzrosnąć lub zmaleć | spełnione | `services/api/src/game_predictor_api/domain/board_search_approximate_win.py:305`, `services/worker/tests/test_super_game_payout.py:154`. |
| Koszt serii w podsumowaniu wynosi 0; trigger ma koszt normalny | spełnione | `services/api/src/game_predictor_api/domain/sequence_mode_projection.py:79`, `services/api/tests/test_super_game_payout_api.py:274`. |
| Koszt per pozycja jest zachowany w prezentacji prognozy i panelu | niespełnione | P0-1, P0-2. |
| Ocena planszy korzysta ze spójnych wejść i generacji | niespełnione | P0-3. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P0-1, P0-2, P0-3.

## Proponowane testy

- W `packages/board-search-ui/test/board-search-super-game-payout.test.mjs` poprawić oczekiwanie dla darmowego spinu 6 na 45. Dodać serię bez dodatnich wypłat, pin po jej zakończeniu i porównanie końcowego punktu z podsumowaniem. Komenda: `npm run test --workspace @game-predictor/board-search-ui`.
- W tym samym pliku dodać start wewnątrz serii: pierwszy darmowy spin z wypłatą 50, wkład 0, kredyty 50. Sprawdzić też przejście do pierwszego płatnego spinu. Komenda jak wyżej.
- W `packages/board-search-ui/test-interactions/board-search-approximate-win.test.mjs` sprawdzić wartości kontrolowanych pinów odtworzonego wyniku supergry. Komenda: `npm run test:interactions --workspace @game-predictor/board-search-ui`.
- W `services/api/tests/integration/test_board_search_super_game_postgres.py` dodać test dwóch sesji: zatrzymać odczyt po pobraniu plansz, wykonać korektę i publikację generacji, następnie odczytać znaczniki. Zakres i szczegół muszą zwrócić spójny stan albo ponowić odczyt. Komenda po ustawieniu `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`: `.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_board_search_super_game_postgres.py -q`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task i Outcome, właściwe fragmenty planu, wymagania, kontrakt API oraz decyzje D-535–D-537. Zbadano ewaluatory, projekcję pozycji, integrację API, snapshoty panelu, zmiany UI i testy dotyczące supergry oraz regresji 777.

Nie uruchamiano testów, usług ani operacji na danych. Wyniki weryfikacji wykonawcy potraktowano jako deklaracje z Outcome. Zachowanie bazowych plansz przy nieaktualnej generacji oceniono według D-537, mającej pierwszeństwo przed odmiennym zapisem planu.