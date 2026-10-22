---
title: 777a2 — nierozpoznane symbole jako wildcard w wyszukiwaniu
status: done
last_updated: 2026-10-23
---

# TASK-1087 — Nierozpoznane symbole w wyszukiwaniu 777a2

## Status

`done`

## Goal

W grze o kodzie `777a2` nierozpoznana pozycja zapisanej planszy pasuje do każdego symbolu zapytania, a wynik pokazuje czerwony licznik takich pozycji.

## Context

Operator zlecił eksperyment 2026-10-23 i doprecyzował, że chodzi o zapisane `?` oraz akcję `Nieczytelny` w oknie planszy, nie o zmianę edytora wzoru.

## Dependencies / entry conditions

Gałąź `codex/777a2-unknown-search-wildcards` od `main` v1.7.463. Zastane usunięcia dwóch artefaktów i nieśledzony katalog `worktrees/cloudflare-link-health/` należą do operatora i pozostają poza zakresem.

## Recommended execution

`gpt-6.1-sol`, `high`. Jeden ograniczony pion rankingu i prezentacji; dodatkowy audyt nie jest wymagany. Eskalacja przy konieczności migracji albo zmianie wyliczania wypłat.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` — wyszukiwanie niepełnym wzorem
- `ai_docs/architecture/API_CONTRACT.md` — wyszukiwanie plansz
- `ai_docs/architecture/DATA_MODEL.md` — projekcja wyszukiwania
- `ai_docs/architecture/CODE_MAP.md`
- `.agents/skills/task-close/SKILL.md`

## Scope

- Opt-in domenowy wildcard dla nierozpoznanej pozycji bez dowodu; aktywny wyłącznie dla kodu gry `777a2`.
- Punkt za wildcard bez zwiększania exact ani alternatyw. `unknownCount` nadal liczy nierozpoznane pozycje porównywane ze znanym wzorem.
- Jawny znacznik `unknownMatchesAll` w istniejącym score API, OpenAPI, generowanym kliencie i testach transportu.
- Czerwony komunikat przy wybranym wyniku, również po zmianie wyniku i w panelu linku.

## Out of scope

Zmiany symboli w bazie, przeliczenie wypłat, backfill, nowe ustawienie ogólne, migracje, restart usług, merge i push.

## Acceptance criteria

- [x] 777a2: znany symbol i jeden brak danych dają 100%, exact=1, unknown=1.
- [x] Same braki danych mogą znaleźć się w wynikach, z licznikiem i bez udawania exact.
- [x] Znane sprzeczności i alternatywy zachowują punktację; remisy preferują rzeczywiste exact.
- [x] Inne gry i walidacja wzoru z samych `?` zachowują poprzednie działanie.
- [x] Czerwony tekst podaje liczbę nierozpoznanych pozycji; znika przy zerze i przy zwykłym rankingu.
- [x] Testy domeny, SQL, API, wrappera i interakcji oraz właściwe lint/typecheck i docs:check przechodzą.

## Technical notes

Założenie: jednostką jest logiczny brak dowodu istniejącej projekcji (`NULL`/`?`, brak primary i dopuszczalnych alternatyw). Projekcja sprowadza do niego także wstrzymane komórki z problemem siatki/kadru; nie nadajemy im symbolu i nie zmieniamy ich stanu. Wyszukiwanie traktuje taki brak jako niepewne dopasowanie wyłącznie w 777a2. Licznik dotyczy porównywanych pozycji zapytania, nie pustych pól wzoru ani wszystkich 15 pól planszy. Przybliżona wygrana zachowuje dotychczasowe zasady.

Źródłem reguły jest `GameModel.code`, nie nazwa wyświetlana. SQL nadal czyta tylko fast documents; bez joinów do komórek i bez zmiany schematu bazy. Publiczny score przenosi ten sam znacznik co Admin API. Brak znacznika w starszym zapisanym wyniku oznacza dotychczasowe zachowanie UI.

## Expected files

- `services/api/src/game_predictor_api/domain/board_search.py` — score/ranking, opcja z domyślnym false.
- `services/api/src/game_predictor_api/storage/board_search_projection_repository.py` — search i wyrażenia SQL.
- `services/api/src/game_predictor_api/schemas/board_search.py` — score odpowiedzi.
- `packages/board-search-ui/src/board-search-results.tsx`, `board-search.css` — licznik.
- OpenAPI i klient generowany; testy tych modułów i dokumentacja wymieniona powyżej.

## Test cases

Znane+unknown, samo unknown, null i literalne `?`, znane sprzeczności, alternatywy, obie wartości opcji, deterministyczny remis, wybór gry, transport znacznika, zmiana wyniku i znikanie komunikatu.

## Verification

Sprawdzone wejścia: `.venv/Scripts/python.exe -m pytest` dla zmienionych testów API (bez wrappera `-Suite`), `ruff`, `mypy`; npm `test`, `test:interactions`, `lint`, `typecheck` workspace board-search-ui; `openapi:generate`, `docs:check`, `code-map:check`. Każda komenda uruchamiana z limitem 120 s. Bez benchmarków i bez startu usług.

## Risks / open questions

Plansza z wieloma brakami może dostać 100%; czerwony licznik ujawnia niepewność. Co najmniej jedna znana pozycja wzoru nadal jest wymagana do rozpoczęcia wyszukiwania. Brak blokujących pytań.

## Outcome

Commit: v1.7.464 (hash dopisuje kolejny commit).

### Changed

- Ograniczona do `GameModel.code=777a2` reguła rankingu: brak dowodu otrzymuje pełny punkt, pozostaje w `unknownCount` i dopuszcza wynik bez exact/alternatyw. Dotychczasowe tie-breakery nadal preferują rzeczywiste exact.
- Opcja domenowa i SQL mają domyślne `false`; inne gry zachowują poprzednie działanie.
- `unknownMatchesAll` w score backendu, OpenAPI, generowanym kliencie i wrapperze. Testy żądań Admina i publicznego endpointu potwierdzają przekazanie znacznika.
- Czerwony tekst `Nierozpoznane symbole: X. Pasują do dowolnego symbolu.` w obu wariantach wspólnego panelu. Licznik zmienia się wraz z wynikiem i znika przy zerze/standardowym rankingu.
- Potwierdzono odczytem lokalnego API: `777 a2` ma kod `777a2`; `777 a2 del` ma inny kod `777v2` i pozostaje poza wyjątkiem.

### Verification results

- Backend: 58 PASS (domena, repozytorium, Admin API i dwa warianty publicznego żądania search), 37,62 s.
- PostgreSQL: 1 PASS, 15,73 s; izolowana baza testowa, zapis projekcji i odczyt w nowych sesjach, znane+unknown+sprzeczne oraz samo unknown; porównanie 777a2 z inną grą. Baza testowa sprzątnięta przez fixture.
- board-search-ui: 105 testów jednostkowych PASS; 94 testy interakcji PASS (w tym komunikat w obu wariantach panelu i zmiana wybranego wyniku); lint i typecheck PASS.
- admin-api-client: 133 testy PASS, build i typecheck PASS; nowy test wrappera zachowuje parametry zapytania i serwerowy score.
- Python: Ruff check i format check dla ośmiu zmienionych plików PASS. Mypy dla trzech zmienionych modułów z `--follow-imports=silent`: PASS.
- Eksport OpenAPI `--check`, kontrola generowanego klienta, code-map:check, docs:check i git diff --check: PASS.
- Początkowy pakiet testów API przekroczył 120 s z powodu blokady socketpair/gniazd w sandboxie Windows; potwierdzono stosem i ponowiono ograniczony zestaw poza sandboxem. Szerszy plik publiczny przekroczył kolejny limit 90 s bez zgłoszonych porażek; ukończono dwa testy zmienianego żądania publicznego osobno. Brak osieroconych procesów pytest/mypy potwierdzono odczytem procesów.

### Not completed

- Pełne `quality` i pełny plik publicznych testów nie były bramką tej zmiany; bez szerokich benchmarków i bez testu operatorskiego w przeglądarce/na Androidzie.
- Szerszy Mypy, podążający za importami, zgłosił dwa wcześniejsze błędy w `schemas/source_lattice_geometry.py:36,38`, po czym przekroczył 120 s. Nie zmieniano niezwiązanego modułu. Ograniczony typecheck zmienionych trzech modułów przeszedł.
- Bez migracji, restartów, modyfikacji symboli operatora, przeliczeń wypłat, merge i push. Audyt krzyżowy nie jest wymagany w przypisaniu tego taska.

### Documentation updates

- D-569, wymagania Admina, kontrakt API, opis istniejącej projekcji i wygenerowana mapa kodu. Założenie o wszystkich logicznych brakach (w tym problemach siatki/kadru) zapisano przed kodowaniem i podano operatorowi w czacie.
- Kryteria akceptacji i właściwe punkty Definition of Done porównano punkt po punkcie: ranking i granice — testy domeny/SQL; kontrakt — eksport i żądania; UX — dwa warianty panelu i komunikat tekstowy niezależny od koloru; trwałość — zapis kodu i nowe sesje SQL; dokumentacja — zaktualizowana. Nie ma zmiany schematu ani operacji na danych operatora.

### Recommended next task

- Odbiór w panelu 777 a2 przez operatora i osobna zgoda na merge do main. Zachowane ryzyko eksperymentu: 100% może obejmować nierozpoznane pozycje; licznik ujawnia ich liczbę w porównywanym wzorze.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1087 | gpt-6.1-sol | high | Ograniczony pion rankingu, istniejący indeks i kontrakt. | Nie jest wymagany. |
