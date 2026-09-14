---
title: TASK-0542 — Routing podglądu planszy do magazynu V2
status: done
last_updated: 2026-09-14
---

# TASK-0542 — Routing podglądu planszy do magazynu V2

## Status

`done`

## Goal

Podgląd operacyjnego wyniku wyszukiwania plansz odczytuje element review oraz
checksum-bound obraz z aktywnego magazynu gry V2.

## Context

Wyszukiwanie zwraca prawidłowy wynik operacyjny, lecz endpoint
`/image-review-items/{id}/assets/board` odpowiada
`IMAGE_REVIEW_ITEM_NOT_FOUND`. `gameId` jest parametrem zapytania, więc
middleware oparty na identyfikatorze w ścieżce nie zakłada scope'u magazynu.
Read-only diagnostyka potwierdziła, że rekord istnieje w V2, a wskazany JPEG
istnieje, ma zgodną checksumę i 279998 bajtów.

## Dependencies / entry conditions

- TASK-0519 dostarcza `game_storage_scope` i routing public/V2.
- TASK-0541 przywraca aktualne wyniki szybkiego wyszukiwania plansz.
- Rekord review, źródło i plik podglądu pozostają niezmienione; nie jest
  potrzebna operacja naprawcza na danych.

## Recommended execution

`gpt-6-astra high`; zadanie dotyka granicy HTTP, serwisu aplikacyjnego oraz
izolacji magazynu V2. Dodatkowy review nie jest wymagany, jeżeli test
PostgreSQL odtworzy odczyt z nowej, nieskopowanej sesji i rzeczywisty endpoint
zwróci obraz po przeładowaniu API.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/tasks/completed/0531-v2-image-job-operations-routing.md`

## Scope

- Powiązać odczyt pojedynczego operacyjnego elementu review z przekazanym
  `game_id` przed pierwszym zapytaniem repozytorium.
- Zachować obecny fail-closed kontrakt kontekstu `game + import job + item`.
- Pokryć routing V2 regresją PostgreSQL oraz zweryfikować rzeczywisty podgląd
  planszy wskazany przez wynik wyszukiwania.
- Udokumentować zasadę dla endpointów, w których `gameId` występuje w query.

## Out of scope

- Zmiana kontraktu URL, odpowiedzi wyszukiwania lub komponentu UI.
- Zmiana schematu bazy, migracja albo modyfikacja danych użytkownika.
- Przebudowa pozostałych operacji operacyjnego Reviewera niezwiązanych z
  odczytem pojedynczego elementu i jego assetów.

## Acceptance criteria

- [x] `OperationalImageReviewService.get_item` odczytuje element gry V2 z
  nowej sesji bez zewnętrznego scope'u.
- [x] Endpoint podglądu wyniku wyszukiwania zwraca `200` i właściwy typ obrazu.
- [x] Niewłaściwe `gameId`, `importJobId` albo `reviewItemId` nadal kończą się
  kontrolowanym błędem, bez odczytu z innej gry.
- [x] Test PostgreSQL, Ruff i mypy przechodzą.

## Technical notes

Endpoint ma pełny `game_id`, ale middleware nie może pozyskać go z adresu,
ponieważ występuje tylko w query. Serwis aplikacyjny ustanawia
`game_storage_scope(game_id)` wokół całego repozytoryjnego `get_item`. Dzięki
temu `_base_query` oraz późniejsze odczyty komórek i rewizji używają tego samego
`search_path` i RLS. Endpointy źródła, planszy i komórki współdzielą tę metodę,
więc nie należy powielać routingu w trzech handlerach HTTP.

## Expected files

- Istniejący: `services/api/src/game_predictor_api/application/image_reviews.py`
  — `OperationalImageReviewService.get_item`.
- Istniejący:
  `services/api/tests/integration/test_game_storage_routing_postgres.py` —
  regresja odczytu V2 z nieskopowanej sesji.
- Istniejący: `ai_docs/architecture/API_CONTRACT.md` — granica routingu query.
- Istniejący: `ai_docs/process/CURRENT_STATE.md`.
- Nowy: `ai_docs/tasks/0542-v2-operational-review-asset-routing.md`.

## Test cases

- Element review i jego zależności istnieją wyłącznie w partycjach V2; nowa
  sesja bez scope'u wywołuje serwis z `game_id` i otrzymuje właściwy element.
- Rzeczywisty wynik wyszukiwania dla sekwencji 12 zwraca przez endpoint assetu
  istniejący `image/jpeg`, zamiast `IMAGE_REVIEW_ITEM_NOT_FOUND`.
- Istniejące testy rozwiązywania assetów nadal odrzucają brak pliku, dryf
  checksummy i niebezpieczną ścieżkę.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_game_storage_routing_postgres.py::test_operational_review_item_reads_v2_in_a_new_unscoped_session -q
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_operational_image_reviews.py -q
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/application/image_reviews.py services/api/tests/integration/test_game_storage_routing_postgres.py
.\.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/application/image_reviews.py
```

Kryterium zaliczenia obejmuje również `200 image/jpeg` z rzeczywistego adresu
podglądu po przeładowaniu procesu API.

## Risks / open questions

- Brak pytań blokujących. Plik i jego checksumę potwierdzono przed zmianą.

## Outcome

### Changed

- `OperationalImageReviewService.get_item` ustanawia teraz
  `game_storage_scope(game_id)` przed całym odczytem repozytorium.
- Wspólna metoda naprawia odczyt pojedynczego elementu oraz endpointy assetów
  źródła, planszy i komórek bez zmiany URL, OpenAPI lub schematu bazy.
- Dodano regresję PostgreSQL dla elementu istniejącego wyłącznie w V2 oraz
  kontrolowanego braku przy błędnym `importJobId`.

### Verification results

- Izolowany test PostgreSQL: `1 passed`.
- Testy serwisu bez dwóch przypadków zależnych od `tmp_path`: `12 passed,
  2 deselected`.
- Dwa testy z `tmp_path` wykonały logikę, lecz pełny przebieg pytest został
  przerwany przy sprzątaniu katalogu przez istniejący Windows
  `PermissionError`; ten sam problem występował przed tym taskiem.
- Ruff, sprawdzenie formatowania i mypy zmienionego serwisu: passed.
- Rzeczywisty endpoint wyniku sekwencji 12: `200 image/jpeg`, 279998 B.
- Ten sam `reviewItemId` z obcym `importJobId`: `404`.

### Not completed

- Nie zmieniano danych użytkownika, schematu bazy, OpenAPI ani Admin UI.

### Documentation updates

- `API_CONTRACT.md` opisuje wymagany scope dla `gameId` przekazanego w query.
- `CURRENT_STATE.md` zapisuje przyczynę, zakres naprawy i wynik produkcyjnej
  weryfikacji.

### Recommended next task

- Brak zadania koniecznego do przywrócenia podglądu; po przeładowaniu Admina
  obserwować kolejne wyniki operacyjne i archiwalne.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0542 | `gpt-6-astra` | `high` | Poprawka routingu na granicy API i odczytu game-owned V2 wymaga regresji na rzeczywistym PostgreSQL. | Nie, jeśli test z nieskopowaną sesją oraz rzeczywisty endpoint przejdą. |
