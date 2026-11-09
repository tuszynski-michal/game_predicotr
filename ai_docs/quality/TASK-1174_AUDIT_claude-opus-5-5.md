# Audyt TASK-1174 — Następna plansza i szybkie ładowanie korekty

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...41c784fda6e4335b85c3439e5037328de15ff49d oraz zmiany niezacommitowane, data 2026-11-09
Runda: 2
SHA pakietu: 2fd6022c900673562dd7fc841aafea8a3ba2645c3eb8114b846abeda69b39d8d
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono, czy poprawki usuwają znaleziska rundy 1, oraz czy nie wprowadzają nowych błędów w nawigacji `reviewAll`, kolejce correction, kontrakcie `counts=none` i predykatach partycji. P0-1, P1-1 i P1-2 są zamknięte: bieżący kursor i historia są jawne, ponowienie powtarza dokładnie nieudany odczyt, a przyjęcie propozycji przechodzi tą samą ścieżką co zapis. Nie znaleziono nowych P0 ani P1. Pozostają cztery znaleziska P2 o ograniczonym skutku; najistotniejsze dotyczy „Poprzedniej” po zapisie planszy odroczonej na niekompletnym zdjęciu.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-4] `ai_docs/process/CURRENT_STATE.md:17` — Wiersz „Mumie A2” nadal należy do innej operacji niż TASK-1174. Wykonawca opisał jego pochodzenie i zadeklarował, że do commita trafią tylko hunki taska, ale tego nie da się potwierdzić przed `task-close`. Skutek ogranicza się do czystości commita. Propozycja: przy `task-close` świadomie dołączyć albo wyłączyć ten hunk i odnotować decyzję w `Outcome`.
- [P2-5] `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx:307` — „Poprzednia” w `reviewAll` czyta stronę po kursorze zapisanej planszy. Po zapisie planszy odroczonej na niekompletnym zdjęciu ta pozycja prawdopodobnie znika z `view=all`: wiersz pending ma już status `resolved`, a projekcja powstaje dopiero po skompletowaniu zdjęcia albo wyjątku (`services/api/tests/integration/test_geometry_review_cursor_postgres.py:74`, `services/api/tests/integration/test_virtual_deferred_resolution_postgres.py:600-614`). Operator widzi wtedy ponownie bieżącą planszę, a historia skraca się o jeden krok, bez wyjaśnienia. Dane pozostają bezpieczne, a stary obiekt nie jest edytowany. Propozycja: dodać komunikat, że zapisana pozycja wróci po skompletowaniu zdjęcia, albo zaakceptować ryzyko w `Outcome`. Wniosek o znikaniu pozycji wynika ze statycznego odczytu i komentarza testu.
- [P2-6] `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx:511` — Odrzucenie lub cofnięcie korekty na końcu zakresu przeładowuje bieżący kursor (`:387`, `:438`) i może zwrócić pustą stronę. Bez `skipSavedSlot` ekran podaje wtedy „Brak plansz w tym zakresie” i „Wybierz istniejący import”, choć wcześniejsze plansze istnieją, a „Od początku” jest niedostępne (`:524`). Zostaje tylko „Poprzednia”. Podobnie cofnięcie korekty po „Koniec zakresu” zostawia w historii kotwicę tej samej planszy (`:341-347`), więc pierwsza „Poprzednia” pokaże ją ponownie. Propozycja: traktować pustą stronę przy niepustej historii jako koniec zakresu i pokazać „Od początku”.
- [P2-7] `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx:225` — Komunikat „Odśwież zakres” nie ma odpowiadającej mu akcji: „Spróbuj ponownie” (`:501-504`) powtarza ten sam odczyt z tym samym `skipSavedSlot`, a ekran błędu nie daje innej nawigacji. Wymagałoby to co najmniej trzech wierszy tej samej pozycji po kursorze, co jest mało prawdopodobne, także mimo braku wykluczenia nieaktualnego wiersza pending w `view=all` (`image_grid_review_repository.py:497-503`). Propozycja: dodać „Od początku” na tym ekranie błędu albo zaakceptować ryzyko.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Zapis `reviewAll` przechodzi dalej w bieżącym zakresie | spełnione | `board-geometry-correction-workspace.tsx:339-363`; test `board-geometry-correction.test.mjs:1342` |
| Correction nadal odświeża pierwszy nierozwiązany element | spełnione | `board-geometry-correction-workspace.tsx:364-367` |
| Ostatni zapis nie wraca do początku | spełnione | `board-geometry-correction-workspace.tsx:345-357`; test `board-geometry-correction.test.mjs:1376` |
| Ręczne poprzednia/następna i jawne „Od początku” pozostają | spełnione, z uwagami P2-5 i P2-6 | `board-geometry-correction-workspace.tsx:297-309`, `:524-541`, `:629-653`; test `board-geometry-correction.test.mjs:1577` |
| Materializacja pomijana ograniczoną liczbą odczytów, bez pomijania innego źródła | spełnione | `board-geometry-correction-workspace.tsx:173-231`; test `board-geometry-correction.test.mjs:1399` |
| Błąd lub utrata odpowiedzi nie przesuwa wyboru bez dowodu sukcesu | spełnione | `deferred-board-cell-geometry-editor.tsx:1002-1017`; `grid-geometry-proposals.tsx:226-252`; testy `board-geometry-correction.test.mjs:1460`, `:1622` |
| Stare odpowiedzi i zmiana zakresu nie przywracają dawnej planszy | spełnione | `board-geometry-correction-workspace.tsx:159`, `:189-194`, `:232-237`, `:322-327`; test `board-geometry-correction.test.mjs:1505` |
| Filtr zdjęcia i importu pozostaje aktywny | spełnione | `board-geometry-correction-workspace.tsx:177-180`; testy `board-geometry-correction.test.mjs:1547`, `:1756` |
| Przyjęcie, odrzucenie i odświeżenie propozycji nie gubią miejsca | spełnione | `board-geometry-correction-workspace.tsx:570-591`; testy `board-geometry-correction.test.mjs:1695`, `:1729` |
| `counts=none` nie wykonuje agregatów i dokumentuje nieobliczone zera | spełnione | `application/image_grid_reviews.py:155-162`; `api/image_grid_reviews.py:183-189`; `domain/image_grid_reviews.py:120-135`; `test_image_grid_review_api.py:1054` |
| `all` i `correction` pozostają zgodne | spełnione | `application/image_grid_reviews.py:163-175`; `board-geometry-correction-workspace.tsx:181-183` |
| Spójny pion API/OpenAPI/SDK/wrapper/test | spełnione | `openapi.json` (enum i opis parametru), `types.gen.ts`, `packages/admin-api-client/src/index.ts:1459`, `:4168`, `client.test.mjs` (żądanie `counts: 'none'`) |
| Predykaty partycji nie osłabiają filtrów i działają przy routingu gry | spełnione | `image_grid_review_repository.py:426-429`, `:476-477`; `game_storage_routing.py:412`; `main.py:2092-2098`; worker: `jobs/runtime.py:380-386` |
| Rzeczywisty test PostgreSQL stronicowania | spełnione statycznie, bez uruchomienia | `test_geometry_review_cursor_postgres.py:34`, `:82-90`, `:93-98` |
| Ograniczony pomiar read-only po zmianie | niezweryfikowane | Deklaracja w `TASK-1174_VERIFICATION.md`; plik `artifacts/t1174-read-timing.json` istnieje, treści nie czytano |
| Testy, lint, typy, build, docs i mapa | niezweryfikowane | Deklaracja wykonawcy w `TASK-1174_VERIFICATION.md`; wskazane logi `artifacts/t1174-*` i `t1174-r2-*` istnieją, treści nie czytano |
| Outcome, task-close, osobny commit i hash | niezweryfikowane | `Outcome` jest uzupełniony; `task-close`, commit i hash następują po audycie |

## Listy zamknięte i otwarte

Zamknięte: P0-1, P1-1, P1-2, P2-1, P2-2, P2-3.

Otwarte: P2-4, P2-5, P2-6, P2-7.

Dowody zamknięcia:

- P0-1: historia jest zachowywana przy przejściu po zapisie (`board-geometry-correction-workspace.tsx:341-362`). „Poprzednia” czyta aktualną rewizję (`:307-309`), „Od początku” nie zależy w `reviewAll` od historii (`:648`), a odświeżanie używa kursora bieżącej strony (`:580`, `:588`). Testy: `board-geometry-correction.test.mjs:1577`, `:1695`.
- P1-1: parametry ostatniego odczytu są zapamiętywane (`:161`) i ponawiane bez zmian (`:501-504`). Test: `board-geometry-correction.test.mjs:1622`.
- P1-2: przyjęcie propozycji korzysta z `handleSaved` (`:570-575`). Test: `board-geometry-correction.test.mjs:1729`.
- P2-1: konflikt, odrzucenie, odmowa i cofnięcie przeładowują w `reviewAll` bieżący kursor (`:387`, `:397`, `:438`, `:459`).
- P2-2: ekran końcowy oferuje „Wszystkie zdjęcia” (`:542-550`). Test: `board-geometry-correction.test.mjs:1756`.
- P2-3: test PostgreSQL deterministycznie obejmuje oba porządki UUID (`test_geometry_review_cursor_postgres.py:34`, `:93-98`) i porównuje tożsamość pozycji (`:82-90`).

## Proponowane testy

- `apps/reviewer/test-interactions/board-geometry-correction.test.mjs`: odrzucenie ostatniej planszy w `reviewAll` przy niepustej historii; ekran nie twierdzi, że zakres jest pusty, i oferuje „Od początku”. Komenda: `npm run test:geometry --workspace @game-predictor/reviewer`.
- Ten sam plik: zapis planszy odroczonej, której pozycja nie wraca na listę, a następnie „Poprzednia”, z asercją zachowania i komunikatu.
- `services/api/tests/integration/test_geometry_review_cursor_postgres.py`: odczyt `view=all` po zapisie, a przed wyjątkiem kompletności, potwierdzający, czy pozycja znika. Uruchamiać wyłącznie na bazie `*_test`, z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`.

## Zakres przeglądu i ograniczenia

Przeczytano pakiet, `AGENTS.md`, pełny `board-geometry-correction-workspace.tsx` i `correction-grid-proposals.tsx`, a także fragmenty `grid-geometry-proposals.tsx`, edytora korekty, celu korekty, repozytorium `image_grid_review_repository.py`, routingu partycji, runtime'u workera i testów Reviewera oraz PostgreSQL. Przegląd był wyłącznie statyczny: audytor nie uruchamiał testów, lintu, typecheckingu, builda, usług ani bazy, a wyniki i pomiary wykonawcy pozostają jego deklaracjami. Sprawdzono tylko istnienie artefaktów `artifacts/t1174-*`, bez czytania ich treści. Nie oceniano planów zapytań PostgreSQL, więc wpływu predykatów partycji na czas nie potwierdzono niezależnie. Plik `ai_docs/architecture/CODE_MAP_SYMBOLS.md`, zmieniony w drzewie roboczym, był poza zamrożonym pakietem i jego różnicy nie oceniano.