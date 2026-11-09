# Audyt TASK-1174 — Następna plansza i szybkie ładowanie korekty

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...41c784fda6e4335b85c3439e5037328de15ff49d oraz zmiany niezacommitowane, data 2026-11-09
Runda: 1
SHA pakietu: 93eb70f143e893c0d01df0656d990eb96252ed9c62159982a302e4c7a28d3f51
Otwarte P0: 1
Otwarte P1: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano nawigację po zapisie w `reviewAll`, kontrakt `counts=none`, predykaty partycji w repozytorium oraz testy Reviewera, API, klienta i PostgreSQL. Główna ścieżka jest poprawna: zapis przechodzi kursorem dalej, rozpoznaje materializację po import/source/position, a spóźniona odpowiedź nie zmienia nowego zakresu. Pion `counts=none` jest spójny i nie wykonuje agregatów. Problemem jest czyszczenie historii przy każdym przejściu po zapisie, bo wyłącza ręczną nawigację i sprawia, że odświeżenie bieżącej planszy otwiera pierwszą planszę zakresu. Do początku wracają też ponowienie po błędzie odczytu i przyjęcie propozycji, czyli zgłoszony przez operatora objaw nadal występuje na tych ścieżkach.

## Znaleziska

### P0

- [P0-1] `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx:340` — Przejście po zapisie używa `resetHistory: true`, chociaż plansza nie jest już pierwszą w zakresie. Skutki są trzy. Po każdym zapisie „← Poprzednia” jest wyłączona (`:573`), więc w normalnym przebiegu nie da się wrócić do zapisanej planszy. Na ostatniej planszy osiągniętej zapisem „Od początku” jest wyłączone (`:590`), a plan wymaga: „Jawne Od początku i ręczne poprzednia/następna pozostają”. Najpoważniejsza jest regresja wprowadzona tą zmianą: „Odrzuć propozycję” i „Odśwież kolejkę” przeładowują bieżącą planszę przez `history.at(-1)?.nextCursor ?? undefined` (`:522`, `:530`). Przy pustej historii i pozycji w środku zakresu oznacza to odczyt bez kursora, więc otwiera się pierwsza plansza, a komunikat mówi o poprawianiu „tej planszy”. Przed zmianą zapis kończył się na pierwszej planszy, więc pusta historia była spójna z pozycją. Istniejący test `test-interactions/board-geometry-correction.test.mjs:1255` chroni ten kontrakt tylko po „Pomiń”. Proponowana poprawka: przechowywać kursor bieżącej strony i stos kursorów, nie czyścić ich przy przejściu po zapisie w `reviewAll`, a „Poprzednią” wczytywać ponownie z API, żeby nie pokazać nieaktualnej rewizji. Odświeżanie bieżącej planszy powinno używać kursora bieżącej strony, a „Od początku” w `reviewAll` nie powinno zależeć od `history.length`. Potrzebne są testy: odrzucenie i odświeżenie propozycji po zapisie, „Poprzednia” po zapisie oraz „Od początku” na ostatniej planszy po zapisie.

### P1

- [P1-1] `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx:460` — Gdy zapis się udał, a odczyt następnej planszy zawiedzie (`:228-241`) albo kolejka drugi raz zwróci zapisaną pozycję (`:213-218`), przycisk „Spróbuj ponownie” wywołuje `loadPage(undefined, { resetHistory: true })`. Operator trafia wtedy na pierwszą planszę zakresu, wbrew wymaganiu przejścia dalej i bez jawnego „Od początku”. Przy zakresie liczącym tysiące pozycji traci miejsce pracy. Test `test-interactions/board-geometry-correction.test.mjs:1460` obejmuje utratę odpowiedzi zapisu, ale nie błąd odczytu po udanym zapisie, którego dotyczy wymagany przypadek „lost response/błąd” i reguła regresji z `AGENTS.md`. Proponowana poprawka: zapamiętać parametry ostatniego odczytu (kursor i `skipSavedSlot`) i ponawiać właśnie je. Dodać test nieudanego odczytu po zapisie, który po ponowieniu sprawdza `afterCursor` i otwarcie następnej planszy.
- [P1-2] `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx:512` — Przyjęcie propozycji siatki zapisuje zatwierdzone punkty, ale w `reviewAll` nadal wywołuje `loadPage(undefined, { resetHistory: true })`. Sekcja propozycji jest renderowana także w tym widoku (`:502`) dla pozycji z `reviewItemId`, jeśli klient udostępnia API propozycji. Pozycje `view=all` pozostają na liście po zatwierdzeniu, więc operator wraca do pierwszej planszy zakresu, czyli widzi ten sam objaw, który task miał usunąć. Test `test-interactions/board-geometry-correction.test.mjs:1102` obejmuje tylko kolejkę correction. Proponowana poprawka: po przyjęciu propozycji w `reviewAll` użyć tej samej ścieżki przejścia co `handleSaved` i dodać test interakcji.

### P2

- [P2-1] `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx:421` — W `reviewAll` konflikt, a także odrzucenie planszy, odmowa odrzucenia i cofnięcie korekty (`:358`, `:365`, `:403`) nadal wczytują początek zakresu. To zachowanie istniało wcześniej i nie jest wprost objęte T1, ale teraz częściej dotyczy pozycji w środku zakresu. Komunikat „Wczytano aktualny stan kolejki” ukrywa utratę miejsca. Propozycja: po naprawie P0-1 przeładowywać bieżący kursor albo świadomie zaakceptować ryzyko w `Outcome`.
- [P2-2] `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx:480` — Ekran „Koniec zakresu” przy aktywnym filtrze zdjęcia oferuje tylko „Od początku”, a „Wszystkie zdjęcia” jest renderowane wyłącznie przy widocznej planszy (`:544-556`). Wyjście z filtra wymaga ponownego otwarcia tego samego zdjęcia. Propozycja: pokazać na ekranie końcowym przełącznik filtra.
- [P2-3] `services/api/tests/integration/test_geometry_review_cursor_postgres.py:73` — Gałąź ponownego pojawienia się zmaterializowanej pozycji zależy od losowej kolejności UUID, więc pojedynczy przebieg sprawdza tylko jeden wariant. Test nie porównuje też `import_job_id` ani `source_image_id` przed i po materializacji, a Reviewer opiera na nich rozpoznanie tej samej pozycji (`board-geometry-correction-workspace.tsx:196-198`). Propozycja: dodać asercje tożsamości i deterministycznie objąć oba warianty kolejności.
- [P2-4] `ai_docs/process/CURRENT_STATE.md:17` — Zmieniony wiersz „Mumie A2” dotyczy importu 691 zdjęć, a nie TASK-1174. Stan roboczy zawiera też zmienione pliki generowanego klienta spoza zamrożonego pakietu, których różnic nie oceniano. Propozycja: przy `task-close` dodać wyłącznie pliki i hunki taska, a pozostałe zmiany przypisać do ich źródła.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Zapis `reviewAll` przechodzi dalej w bieżącym zakresie | niespełnione | Główna ścieżka: `board-geometry-correction-workspace.tsx:322-342`; wyjątki: P1-1 (`:460`), P1-2 (`:512`) |
| Correction nadal odświeża pierwszy nierozwiązany element | spełnione | `board-geometry-correction-workspace.tsx:343-346` |
| Ostatni zapis nie wraca do początku | spełnione | `board-geometry-correction-workspace.tsx:324-336`; test `board-geometry-correction.test.mjs:1376` |
| Ręczne poprzednia/następna i jawne „Od początku” pozostają | niespełnione | P0-1: `board-geometry-correction-workspace.tsx:340`, `:573`, `:590` |
| Materializacja pomijana ograniczoną liczbą odczytów, bez pomijania innego źródła | spełnione | `board-geometry-correction-workspace.tsx:163-221`; test `board-geometry-correction.test.mjs:1399` |
| Błąd lub utrata odpowiedzi zapisu nie przesuwa wyboru | spełnione | `deferred-board-cell-geometry-editor.tsx:1002-1006`; test `board-geometry-correction.test.mjs:1460` |
| Stare odpowiedzi i zmiana zakresu nie przywracają dawnej planszy | spełnione | `board-geometry-correction-workspace.tsx:179-184`, `:222-227`, `:306-311`; test `board-geometry-correction.test.mjs:1505` |
| `counts=none` nie wykonuje agregatów i dokumentuje nieobliczone zera | spełnione | `application/image_grid_reviews.py:155-162`; `api/image_grid_reviews.py:183-189`; `test_image_grid_review_api.py:1054` |
| `all` i `correction` pozostają zgodne | spełnione | `application/image_grid_reviews.py:163-175` |
| Spójny pion API/OpenAPI/SDK/wrapper/test | spełnione | `openapi.json` (enum i opis parametru), `types.gen.ts`, `packages/admin-api-client/src/index.ts:1459`, `client.test.mjs` (sekcja `counts: 'none'`) |
| Predykaty partycji nie osłabiają filtrów i działają przy routingu gry | spełnione | `image_grid_review_repository.py:426-429`, `:476-477`; `game_storage_routing.py:412`; `main.py:2092-2098` |
| Rzeczywisty test PostgreSQL stronicowania | spełnione, z uwagą P2-3 | `test_geometry_review_cursor_postgres.py:32-81` (statycznie; nie uruchamiano) |
| Ograniczony pomiar read-only po zmianie | niezweryfikowane | Deklaracja w `TASK-1174_VERIFICATION.md`; artefaktów nie czytano |
| Testy, lint, typy, build, docs i mapa | niezweryfikowane | Deklaracja wykonawcy w `TASK-1174_VERIFICATION.md`; audyt nie uruchamiał poleceń |
| Outcome, task-close, osobny commit i hash | niezweryfikowane | Etap po audycie; otwarte P0/P1 blokują commit |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1, P1-1, P1-2, P2-1, P2-2, P2-3, P2-4.

## Proponowane testy

- `apps/reviewer/test-interactions/board-geometry-correction.test.mjs`: po zapisie w `reviewAll` odrzucić propozycję i użyć „Odśwież kolejkę”, sprawdzając, że ostatni odczyt ma kursor bieżącej planszy. Komenda: `npm run test:geometry --workspace @game-predictor/reviewer`.
- Ten sam plik: po zapisie „← Poprzednia” jest aktywna i wczytuje świeżą wersję zapisanej planszy, a „Od początku” działa na ostatniej planszy osiągniętej zapisem.
- Ten sam plik: udany zapis, nieudany odczyt następnej planszy i „Spróbuj ponownie” z zachowaniem `afterCursor` oraz pominięcia zapisanej pozycji.
- Ten sam plik: przyjęcie propozycji w `reviewAll` nie wraca do pierwszej planszy.
- `services/api/tests/integration/test_geometry_review_cursor_postgres.py`: asercje `import_job_id`, `source_image_id` i `position_index` po materializacji oraz deterministyczne pokrycie obu kolejności UUID. Uruchamiane wyłącznie na bazie `*_test` z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`.

## Zakres przeglądu i ograniczenia

Przeczytano pakiet, `AGENTS.md`, pełny `board-geometry-correction-workspace.tsx`, `correction-grid-proposals.tsx`, pełne repozytorium `image_grid_review_repository.py` i serwis `application/image_grid_reviews.py`. Sprawdzono też wybrane fragmenty edytora, celu korekty, routingu partycji, testów Reviewera i testów PostgreSQL. Przegląd był wyłącznie statyczny: nie uruchamiano testów, lintu, typecheckingu, builda, usług ani bazy, a wyniki i pomiary wykonawcy traktowano jako niezweryfikowane deklaracje. Nie czytano artefaktów `artifacts/t1174-*`. Nie oceniano różnic w generowanych plikach klienta spoza zamrożonego pakietu ani planów zapytań PostgreSQL, więc wpływu predykatów partycji na czas nie potwierdzono niezależnie.