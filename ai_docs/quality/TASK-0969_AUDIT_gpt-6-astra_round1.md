# Audyt TASK-0969 - Sekcja „Ostatnie korekty” w Reviewerze

Werdykt: REVISE
Audytor: gpt-6-astra, medium
Wykonawca: claude-sonnet-5-5, medium
Zakres: HEAD...cbf0d588803f20ccfc2a732b7350b2c5c4ff3ff0 oraz zmiany niezacommitowane, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach.

## Streszczenie

Sprawdzono komponent historii, integrację z kolejką, testy interakcji, style i zgodność z kontraktem API. Podstawowa ścieżka cofnięcia jest zaimplementowana, ale ponowienie po utracie odpowiedzi nie zachowuje klucza idempotencji. Testy nie potwierdzają odświeżania rzeczywistej kolejki ani listy po zapisie korekty.

## Znaleziska

### P0

- [P0-1] `apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx:145` — Każda próba potwierdzenia generuje nowy klucz idempotencji. Jeżeli backend wykona cofnięcie, ale odpowiedź zaginie, ponowienie nie odzyska zapisanego wyniku. W ścieżce wyjątku modal zachowuje ten sam podgląd (`:154`), mimo komentarza o jego odświeżeniu. Następne żądanie z nowym kluczem może otrzymać konflikt, po którym odświeżana jest tylko historia (`:158`), a kolejka pozostaje nieaktualna mimo wykonanego cofnięcia. Należy zachować klucz i treść żądania dla ponowień operacji o nieznanym wyniku; odpowiedź odtworzona przez API powinna odświeżać historię i kolejkę tak samo jak pierwszy sukces.

### P1

- [P1-1] `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:126` — Test deklarujący odświeżenie kolejki renderuje wyłącznie komponent historii i sprawdza zwiększenie licznika atrapowego callbacku (`:133`). Nie wykryje usunięcia przeładowania kolejki z `handleReverted`. Ponadto atrapa historii w `apps/reviewer/test-interactions/board-geometry-correction.test.mjs:186` nie rejestruje wywołań, więc zapis korekty nie ma testu wymaganego odświeżenia listy. Należy dodać testy pełnego workspace: zapis ponownie pobiera historię, a cofnięcie ponownie pobiera historię i kolejkę oraz pokazuje przywróconą pozycję.

### P2

- [P2-1] `apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx:232` — Modal deklaruje `aria-modal`, ale nie przenosi ani nie ogranicza fokusu i nie unieczynnia tła. Nawigacja klawiaturą może nadal docierać do edytora, którego globalne skróty symboli pozostają aktywne (`apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx:864`). Zalecane jest zarządzanie fokusem, blokowanie interakcji z tłem i przywracanie fokusu po zamknięciu; alternatywnie jawne odnotowanie ryzyka.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Lista korekt i blokada przycisku dla niedozwolonego cofnięcia | spełnione | `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:108` |
| Podgląd skutków przed potwierdzeniem | spełnione | `apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx:95`; test podglądu `:138` w pliku testowym |
| Jedno żądanie przy podwójnym kliknięciu, z CAS i kluczem idempotencji | spełnione | `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:140`; ograniczenie ponowień opisuje P0-1 |
| Konflikt `GEOMETRY_REVERT_CELLS_CHANGED` pokazuje komunikat i odświeża listę | spełnione | `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:158` |
| Test sukcesu potwierdza odświeżenie kolejki i historii | niespełnione | P1-1: test sprawdza callback, nie przeładowanie kolejki |
| Historia odświeża się po zapisie korekty | spełnione | Połączenie w kodzie: `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx:200` i `:316`; brak testu regresyjnego opisuje P1-1 |
| `typecheck`, `lint`, `test` i `build` Reviewera są zielone | niezweryfikowane | Wyniki zadeklarowane w `ai_docs/tasks/0969-geometry-correction-revert-reviewer-ui.md:84`; audyt nie uruchamiał komend weryfikacyjnych |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P0-1, P1-1, P2-1.

## Proponowane testy

- W `apps/reviewer/test-interactions/geometry-correction-history.test.mjs`: backend wykonuje cofnięcie, odpowiedź ginie, ponowienie wysyła identyczny klucz i CAS, a odtworzony sukces odświeża oba widoki.
- W `apps/reviewer/test-interactions/board-geometry-correction.test.mjs`: zapis korekty ponownie pobiera historię; cofnięcie przywraca pozycję kolejki i odświeża historię.
- W tym samym teście workspace: otwarty modal zatrzymuje fokus i blokuje skróty edytora w tle.

Komenda dla tych testów: `npm run test:geometry --workspace @game-predictor/reviewer`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, zmienione pliki, testy, odpowiednie fragmenty dokumentacji i istniejącego kodu integracyjnego. Tokeny CAS z podglądu są zgodne z dokumentem wymagań i kontraktem API, mimo wzmianki o tokenach „z listy” w przypadku testowym taska.

Nie uruchamiano testów, builda, usług ani operacji na danych. Wyniki wykonawcy nie zostały niezależnie potwierdzone. Nie sprawdzono wyglądu w przeglądarce ani działania na Androidzie.

Task pozostaje `in_progress`. Zamknięcie dokumentacji, regeneracja mapy kodu dla nowego modułu oraz zapis wersji i hasha po commicie pozostają czynnościami wykonawcy lub leada.