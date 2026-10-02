---
title: TASK-0701 — dostęp do odczytu kolejki siatek przy niespójnej projekcji symboli
status: in_progress
---

# TASK-0701 — dostęp do odczytu kolejki siatek przy niespójnej projekcji symboli

## Status

`in_progress`

## Goal

Operator może otworzyć listę i obraz źródłowy wskazanego importu w kolejce
walidacji siatek, nawet gdy niezależna projekcja symboli gry jest oznaczona jako
`failed`; zapis geometrii pozostaje fail-closed.

## Context

Lokalny Reviewer wysyła `GET /games/{gameId}/grid-reviews?view=all&importJobId=…`
i otrzymuje `409 IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE`. Przyczyna jest
globalna dla gry, natomiast odczyt kolejki i assetu używa wyłącznie aktualnych
plansz, źródeł oraz geometrii — nie czyta `image_symbol_review_cells`.

## Dependencies / entry conditions

- Potwierdzono lokalnie odpowiedź `409` dla gry
  `bfc4f949-5c14-4850-b02a-db99610bcfa5`.
- `image_symbol_review_states` tej gry ma status `failed` z kontrolowanym
  błędem niezgodności renderów i maski dostępności.
- Nie wolno uruchamiać przebudowy projekcji ani zmieniać danych użytkownika w
  ramach tego taska.

## Recommended execution

`gpt-6-astra`, reasoning `high`. Zmiana rozdziela dostęp odczytu i zapisowej
bramki spójności, dlatego wymaga regresji API oraz sprawdzenia, że mutacje nadal
zwracają ten sam kontrolowany konflikt.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/API_CONTRACT.md` — sekcja grid reviews
- `ai_docs/architecture/DATA_MODEL.md` — `image_symbol_review_states`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Rozdzielić w repozytorium siatek sprawdzenie istnienia gry od wymagania
  gotowej projekcji symboli.
- Pozwolić na listę kolejki i odczyt assetu źródłowego dla istniejącej gry przy
  projekcji `failed` albo niegotowej.
- Wymagać gotowej projekcji przed każdą mutacją geometrii.
- Dodać regresje API i zaktualizować kontrakt architektury.

## Out of scope

- Naprawa pojedynczej planszy powodującej błąd projekcji symboli.
- Uruchomienie joba backfill, ręczna korekta danych lub zmiana stanu produkcyjnej
  gry.
- Zmiana kontraktu symbol-cell reviews.

## Acceptance criteria

- [ ] `GET grid-reviews` zwraca `200` i stronę zgodną z filtrem importu, gdy
      gra istnieje, a projekcja symboli jest niegotowa.
- [ ] Odczyt assetu źródłowego działa w tym samym stanie przy poprawnej
      checksumie.
- [ ] Zatwierdzenie geometrii i zatwierdzenie źródła nadal zwracają
      `409 IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE` bez zapisu.
- [ ] Brak gry nadal zwraca `404 GAME_NOT_FOUND`.
- [ ] Testy, lint i kontrola typów zmienionego pionu są zielone.

## Technical notes

`SqlAlchemyImageGridReviewRepository.require_game()` obecnie łączy dwa różne
warunki: istnienie gry i gotowość projekcji symboli. `ImageGridReviewService`
woła go zarówno dla odczytu, jak i dla mutacji. Docelowo odczyt ma sprawdzać
wyłącznie istnienie gry; metody zapisujące wywołują prywatną bramkę projekcji
przed pierwszą zmianą. To nie osłabia kontroli danych: żadna geometria ani
projekcja komórek nie zostanie zapisana, gdy stan jest niegotowy.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/storage/image_grid_review_repository.py`.
- Istniejące: `services/api/tests/test_image_grid_review_api.py`.
- Istniejące: `ai_docs/architecture/API_CONTRACT.md`.
- Istniejące: `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Projekcja `failed`, istniejąca gra i filtr `importJobId` → lista `200`.
- Projekcja `failed`, poprawny asset źródłowy → odczyt `200`.
- Projekcja `failed`, próba approve i approve-source → `409`, bez delegacji do
  zapisu.
- Nieistniejąca gra → `404`.

## Verification

```powershell
# services/api, timeout maks. 120 s
..\..\.venv\Scripts\python.exe -m pytest tests/test_image_grid_review_api.py
..\..\.venv\Scripts\python.exe -m ruff check src/game_predictor_api/storage/image_grid_review_repository.py tests/test_image_grid_review_api.py
..\..\.venv\Scripts\python.exe -m ruff format --check src/game_predictor_api/storage/image_grid_review_repository.py tests/test_image_grid_review_api.py
..\..\.venv\Scripts\python.exe -m mypy --strict src/game_predictor_api/storage/image_grid_review_repository.py
```

## Risks / open questions

- Widok może wskazać planszę, której zapis nadal będzie zablokowany; komunikat
  zapisu musi zachować istniejący kod 409 zamiast udawać powodzenie.

## Outcome

### Changed

- Rozdzielono `require_game()` (istnienie gry dla odczytu) od
  `require_ready_game()` (gotowa projekcja symboli wymagana przed zapisem).
- Lista `grid-reviews` i checksum-bound asset źródłowy pozostają dostępne przy
  `failed`/niegotowej projekcji; zatwierdzenie pojedynczej siatki i całego
  źródła nadal kończy się tym samym kontrolowanym `409` bez delegacji do zapisu.

### Verification results

- `pytest tests/test_image_grid_review_api.py` — 18 passed.
- Ruff check i format check dla zmienionych plików — passed.
- `mypy --strict` dla aplikacji i repozytorium siatek — passed.
- Żywy lokalny odczyt importu `f786fed3-9814-42ce-941f-9cb04cbe2c17` —
  `GET grid-reviews` 200; odczyt assetu pierwszej zwróconej planszy — 200.

### Not completed

- Nie naprawiano źródłowej niespójności projekcji symboli i nie uruchamiano
  przebudowy danych; zapis geometrii świadomie pozostaje zablokowany do czasu
  jej usunięcia.

### Documentation updates

- `ai_docs/architecture/API_CONTRACT.md` — jawna granica pomiędzy odczytem
  kolejki a fail-closed zapisem geometrii.
- `ai_docs/process/CURRENT_STATE.md` — wynik TASK-0701.

### Recommended next task

- Osobno zdiagnozować i naprawić planszę, której render kwalifikowany nie
  odpowiada masce dostępności, a następnie wykonać kontrolowaną odbudowę
  projekcji symboli.
