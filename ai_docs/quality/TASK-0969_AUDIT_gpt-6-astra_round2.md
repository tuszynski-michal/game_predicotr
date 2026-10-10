# Audyt TASK-0969 - Sekcja „Ostatnie korekty” w Reviewerze

Werdykt: REVISE
Audytor: gpt-6-astra, medium
Wykonawca: claude-sonnet-5-5, medium
Zakres: HEAD...cbf0d588803f20ccfc2a732b7350b2c5c4ff3ff0 oraz zmiany niezacommitowane, data 2026-10-09
Runda: 2

Przegląd statyczny, bez zmian w plikach.

## Streszczenie

Sprawdzono poprawki po pierwszej rundzie, komponent historii, integrację kolejki, testy i zachowanie klienta API. Dodane testy pełnego ekranu zamykają brak pokrycia odświeżania, a modal otrzymał obsługę fokusu i klawiatury. Obsługa utraty odpowiedzi nadal nie działa z rzeczywistym klientem API: test symuluje wyjątek, podczas gdy klient zwraca obiekt błędu.

## Znaleziska

### P0

- [P0-1] `apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx:217` — Zachowanie klucza idempotencji działa wyłącznie wtedy, gdy wywołanie rzuci wyjątek. Rzeczywisty klient przechwytuje również błędy transportu i zwraca `{ error, request, response }`, gdzie `response` może być niezdefiniowane (`packages/admin-api-client/src/generated/client/client.gen.ts:213–240`). Wrapper nie włącza `throwOnError`. Utrata odpowiedzi trafia więc do `setPending(null)` i komunikatu o niepowodzeniu (`:222–225`), zamiast pozostawić modal z możliwością ponowienia. Klucz i podgląd zostają utracone mimo nieznanego wyniku operacji. Należy rozróżnić potwierdzoną odmowę API od błędu transportu lub odczytu odpowiedzi i dla nieznanego wyniku zachować identyczny klucz oraz treść żądania. Test `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:192` powinien używać rzeczywistego klienta z atrapą `fetch` albo wiernie odtwarzać zwracany przez niego obiekt błędu.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Lista korekt i blokada niedozwolonego cofnięcia | spełnione | `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:113` |
| Podgląd skutków przed potwierdzeniem | spełnione | `apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx:159`, `:353` |
| Jedno żądanie przy podwójnym kliknięciu, z CAS i kluczem idempotencji | spełnione | `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:133` |
| Ponowienie po utracie odpowiedzi zachowuje klucz i treść żądania | niespełnione | P0-1; rzeczywisty klient zwraca błąd zamiast rzucać wyjątek |
| Konflikt pokazuje komunikat i odświeża listę | spełnione | `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:165` |
| Sukces odświeża rzeczywistą kolejkę i historię | spełnione | `apps/reviewer/test-interactions/board-geometry-correction.test.mjs:675` |
| Zapis korekty ponownie pobiera historię | spełnione | `apps/reviewer/test-interactions/board-geometry-correction.test.mjs:660` |
| `typecheck`, `lint`, `test` i `build` Reviewera są zielone | niezweryfikowane | Outcome deklaruje 241 testów podstawowych, 47 interakcyjnych oraz poprawne typecheck, lint i build; nie uruchamiano ich podczas audytu |

## Listy zamknięte i otwarte

Zamknięte:

- **P1-1** — Dodano testy pełnego workspace: zapis ponownie pobiera historię, a cofnięcie przeładowuje kolejkę i pokazuje przywrócony slot (`apps/reviewer/test-interactions/board-geometry-correction.test.mjs:660`, `:675`).
- **P2-1** — Modal przenosi i ogranicza fokus, obsługuje Escape oraz zatrzymuje propagację klawiszy (`apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx:105–145`). Edytor pomija skróty przy otwartym modalu (`apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx:869`).

Otwarte: **P0-1** — częściowo poprawione, lecz nadal występuje przy rzeczywistym zachowaniu transportu.

## Proponowane testy

- W `apps/reviewer/test-interactions/geometry-correction-history.test.mjs` użyć `createAdminApiClient` z atrapą `fetch`: pierwsza próba traci odpowiedź, druga zwraca sukces `created=false`. Sprawdzić zachowanie modala, identyczny klucz i CAS oraz odświeżenie listy i kolejki.
- Dodać przypadek błędu odczytu odpowiedzi po wykonaniu operacji oraz zachować istniejący test potwierdzonej odmowy 409.

Komenda: `npm run test:geometry --workspace @game-predictor/reviewer`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, raport pierwszej rundy, zmiany komponentów, style, testy, odpowiednie fragmenty dokumentacji oraz implementację wrappera i transportu klienta API. Tokeny CAS z podglądu są zgodne z wymaganiami i kontraktem API, mimo wzmianki „z listy” w przypadku testowym taska.

Nie uruchamiano testów, builda, usług ani operacji na danych. Wyniki wykonawcy nie zostały niezależnie potwierdzone. Nie zweryfikowano wyglądu w przeglądarce ani działania na Androidzie.

Task pozostaje `in_progress`. Aktualizacja dokumentacji zamknięcia, regeneracja mapy kodu oraz zapis wersji i hasha po commicie pozostają po stronie wykonawcy lub leada.