---
title: TASK-0357 — Odbiór i rollout półautomatycznej selekcji zdjęć
status: done
last_updated: 2026-08-31
---

# TASK-0357 — Odbiór i rollout półautomatycznej selekcji zdjęć

## Goal

Potwierdzić na kontrolowanych rzeczywistych próbach 10 i 100 JPEG-ów, że
półautomatyczna selekcja przypisuje wyłącznie poświadczone zakresy, nie uruchamia
geometrii, croppera ani rozpoznawania symboli oraz pozostaje domyślnie wyłączona
do jawnej decyzji rolloutowej.

## Context

TASK-0350–0356 dostarczyły kontrakt zakresów, OCR range-only, globalny run,
lokalny output oraz review i ręczną edycję. Ten task nie rozszerza workflowu:
stanowi kontrolowany odbiór jego obecnej wersji.

Do testu real-image zostanie użyty wyłącznie odczytowy podzbiór 10 i 100
istniejących plików `seq_1-9.jpg`…`seq_892-900.jpg` z lokalnego katalogu
operatora. Nazwy tych plików są oracle'em oczekiwanych zakresów; ich źródłowe
bajty ani katalog nie mogą być zmienione.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `.tmp/TASK-0350-0357-semi-automatic-selection-plan.md`

## Scope

- odbiór 10/100 prawdziwych JPEG-ów z jawnym raportem czasu, liczby wywołań OCR,
  RSS, wyborów, luk, wieloznaczności i fałszywych przypisań;
- kontrola braku wywołań geometrii, croppera i symbol inference;
- kontrole kontraktu API/OpenAPI/klienta/Admina/workera;
- aktualizacja dokumentacji i wyniku taska;
- zachowanie jednej serwerowej flagi feature'u domyślnie ustawionej na `false`.

## Out of scope

- duży benchmark, syntetyczny corpus albo skan całego katalogu użytkownika;
- zmiana OCR, grupowania, pipeline'u geometrii, croppera lub symboli;
- domyślne włączenie feature flagi;
- mutacja produkcyjnych stagingów, jobów albo lokalnego katalogu źródłowego.

## Acceptance criteria

- [x] Próby 10 i 100 używają realnych, checksummowanych JPEG-ów i mają zapisany wynik.
- [x] Każde fałszywe przypisanie jest jawnie raportowane; brak mocnego proof pozostaje luką.
- [x] Raport potwierdza jedną analizę OCR na źródło, O(N), bounded RAM oraz zero tras geometrii/croppera/symboli.
- [x] API, OpenAPI, wygenerowany klient, Admin i worker przechodzą właściwe kontrole jakości.
- [x] Flaga `GAME_PREDICTOR_ENABLE_SEMI_AUTOMATIC_IMAGE_SELECTION` pozostaje domyślnie `false`.
- [x] Nie zostają zmienione dane użytkownika ani katalogi obrazów użyte do odbioru.

## Technical notes

Odbiór real-image nie tworzy browser stagingu, globalnego runu ani lokalnego
outputu. Wywołuje wyłącznie ten sam adapter range-only OCR, którego używa
worker, na jednym deterministycznym, read-only podzbiorze. Pozwala to zmierzyć
realne dekodowanie i OCR bez skutków ubocznych pipeline'u.

## Expected files

- `scripts/run_semi_automatic_selection_acceptance.py`
- `services/worker/tests/test_semi_automatic_selection_acceptance.py`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/tasks/0357-semi-automatic-selection-rollout.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_semi_automatic_image_selections.py services/worker/tests/test_semi_automatic_selection_contracts.py services/worker/tests/test_semi_automatic_selection_range_only_ocr.py services/worker/tests/test_semi_automatic_selection_engine.py services/worker/tests/test_semi_automatic_selection_job.py services/worker/tests/test_semi_automatic_selection_acceptance.py -q
npm run test --workspace @game-predictor/admin
npm run test --workspace @game-predictor/admin-api-client
npm run openapi:check
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run admin:build
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api services/worker/src/game_predictor_worker/semi_automatic_selection scripts/run_semi_automatic_selection_acceptance.py
.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api services/worker/src/game_predictor_worker/semi_automatic_selection scripts/run_semi_automatic_selection_acceptance.py
```

## Risks / open questions

- Rzeczywisty OCR może pozostawić część źródeł jako luki; to poprawny wynik
  fail-closed, a nie powód do zgadywania zakresu.
- Wynik 10/100 nie uprawnia do automatycznego globalnego rollout'u. Po odbiorze
  flaga pozostaje wyłączona do osobnej jawnej decyzji operatora.

## Outcome

### Changed

- Dodano ograniczone, read-only narzędzie odbioru
  `scripts/run_semi_automatic_selection_acceptance.py`. Wykorzystuje dokładnie
  adapter range-only OCR workera, wylicza SHA-256 wejść, mierzy czas i peak RSS
  oraz raportuje wybory, luki, wieloznaczności i fałszywe przypisania.
- Dodano regresję narzędzia oraz lazy import `create_app`, aby import domeny API
  nie cyklicznie materializował ASGI i geometrii przed uruchomieniem OCR.
- Po wdrożeniu TASK-0358 narzędzie raportuje także poziomy `12/24/36`, batche,
  cropy, odrzucone surowe hipotezy, overlap, medianę czasu i checksumę
  deterministycznego manifestu źródeł.

### Verification results

- V2 na 10 rzeczywistych, niemodyfikowanych plikach: `7/10` exact, `3` luki,
  `0` false assignments, `0` overlap, `13.461687 s` i zero wywołań geometrii,
  croppera oraz symbol inference.
- V2 na 100 rzeczywistych plikach: `68/100` exact, `32` luki, `0` false
  assignments, `0` overlap, `131.883438 s`, mediana `1.421131 s/JPEG` i peak
  RSS `541708288 B`.
- Przebieg 100 wykonał `538` batchy dla `3228` cropów etykiet. Zakończył
  `31` zdjęć na poziomie 24, `30` na poziomie 36, a `39` pozostawił bez mocnego
  dowodu po maksymalnym poziomie.
- Stosunek czasu 100/10 wyniósł około `9.80`, zgodnie z liniowym kosztem O(N)
  tej ograniczonej próby.
- Pełny raport wraz z manifestami SHA-256 znajduje się w
  `ai_docs/quality/SEMI_AUTOMATIC_SELECTION_RANGE_OCR_V2_ACCEPTANCE.md`.
- Skoncentrowane testy API/workera: `54 passed`; testy Admina: `346 passed`;
  klient Admin API: `49 passed`; OpenAPI, Admin typecheck i produkcyjny build
  przeszły.
- Ruff i mypy dla zmienionego pionu przeszły. Pełny Admin lint pozostaje
  zablokowany przez istniejącą zmianę poza tym taskiem w
  `unreadable-board-review-workspace.tsx:133` (`react-hooks/set-state-in-effect`).
  Task OCR nie zmienia tego pliku.
- Pełny mypy API nie zwrócił wyniku przez 60 sekund i został kontrolowanie
  przerwany; ograniczony mypy trzech zmienionych modułów zakończył się bez
  błędów.

### Rollout decision

- Flaga `GAME_PREDICTOR_ENABLE_SEMI_AUTOMATIC_IMAGE_SELECTION` pozostaje
  domyślnie `false`.
- Włączenie funkcji wymaga osobnej jawnej decyzji operatora; samo zakończenie
  odbioru nie zmienia konfiguracji runtime.
