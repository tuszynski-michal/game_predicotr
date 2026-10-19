# Audyt TASK-1059 - Modal serii supergry w udostępnionej wyszukiwarce

Werdykt: REVISE
Audytor: Codex, etykieta modelu z briefu: gpt-6.1-sol; reasoning niepodany
Wykonawca: Claude; plan wskazuje claude-fable-5-1 / high warunkowo
Zakres: HEAD...9fff1457210db8bf1be4692c7b6affeaf5704953 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-19
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono modal, przekazywanie akcji znaczników, adapter publicznych danych, integrację obu bramek oraz testy. Integracja zachowuje wspólny panel serii i rozdzielenie klientów poszczególnych gier. Zamknięcie modala podczas zapisu może jednak pozostawić stare wyniki po skutecznej zmianie na serwerze. Brakuje też części wymaganych testów integracyjnych.

## Znaleziska

### P0

- [P0-1] `packages/board-search-ui/src/super-game-series/super-game-series-modal.tsx:105` — „Zamknij” pozostaje aktywne podczas zapisu super symbolu. Jeśli użytkownik zamknie modal przed odpowiedzią pierwszego zapisu, `edited` nadal wynosi `false`, więc workspace pomija odświeżenie (`packages/board-search-ui/src/board-search-workspace.tsx:1069`). Późniejszy sukces wywoła wyłącznie `setEdited(true)` odmontowanego modala przez callback z linii 121; nie odświeży wyników ani zakresu. Serwer ma już nowy symbol, a użytkownik widzi poprzednie dane. Należy blokować zamknięcie do rozstrzygnięcia zapisu albo obsługiwać zakończenie mutacji w nadal zamontowanym hoście i wtedy odświeżyć oba widoki.

### P1

- [P1-1] `packages/board-search-ui/test-interactions/super-game-series-modal.test.mjs:162` — klient testowy zawsze zwraca błąd przybliżonej wygranej. Testy nie sprawdzają więc otwarcia modala z wiersza zakresu ani odświeżenia tabeli i `superSymbolCode`. Nie realizują też wymaganego scenariusza poprawki komórki z modala, Esc przy otwartym oknie linii oraz powrotu fokusu. Test zapisu z linii 332 potwierdza tylko kolejne wywołanie wyszukiwania. Należy dodać wymagane scenariusze z udanymi odpowiedziami zakresu i korekty oraz asercjami danych i fokusu. Wymóg wynika z kryteriów i przypadków testowych TASK-1059 oraz sekcji 6 planu.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Znaczniki wyników i zakresu otwierają modal; bez klienta pozostaje etykieta | spełnione | `packages/board-search-ui/src/board-search-results.tsx:163`, `packages/board-search-ui/src/board-search-approximate-win.tsx:781`, `packages/board-search-ui/test-interactions/super-game-series-modal.test.mjs:404` |
| Skróty nie zmieniają wzoru; Esc pozostawia modal i zamyka tylko okno linii | spełnione | Statycznie: `packages/board-search-ui/src/board-search-workspace.tsx:556`, `packages/board-search-ui/src/super-game-series/super-game-series-modal.tsx:94`, `packages/board-search-ui/src/board-search-board-lines-modal.tsx:572`. Luka testowa: P1-1 |
| Zapis symbolu i korekta komórki odświeżają wyniki oraz zakres po zamknięciu | niespełnione | P0-1; standardowa ścieżka odświeżenia: `packages/board-search-ui/src/board-search-workspace.tsx:1072` |
| Brak listy i przeliczania; obecny baner stanu | spełnione | `packages/board-search-ui/src/super-game-series/super-game-series-modal.tsx:111`, `packages/board-search-ui/test-interactions/super-game-series-modal.test.mjs:304` |
| Zmiana gry odmontowuje modal; klient używa prefiksu gry | spełnione | `apps/reviewer/src/features/board-search-panel/board-search-panel-gate.tsx:102`, `apps/reviewer/src/features/board-search-panel/board-search-panel-gate.tsx:162` |

## Listy zamknięte i otwarte

Zamknięte: Brak — runda 1.

Otwarte: P0-1, P1-1.

## Proponowane testy

- W `packages/board-search-ui/test-interactions/super-game-series-modal.test.mjs` dodać opóźniony zapis i próbę zamknięcia przed odpowiedzią; potwierdzić późniejsze odświeżenie wyników i zakresu.
- W tym samym pliku dodać otwarcie z tabeli, zmianę `superSymbolCode`, korektę komórki, Esc w zagnieżdżonym dialogu i powrót fokusu.
- Uruchomić: `npm run test:interactions --workspace @game-predictor/board-search-ui`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task, plan, właściwe wymagania i kontrakt API, zmienione pliki oraz powiązany panel serii i obsługę okna linii. `git diff --check` dla zakresu audytu zakończył się bez uwag.

Nie uruchamiano testów, buildów, usług ani przeglądarki. Wyniki testów zapisane przez wykonawcę w `Outcome` nie zostały niezależnie potwierdzone. Zachowanie natywnych dialogów i fokusu wymaga weryfikacji w przeglądarce.