# Audyt TASK-1153 — Propozycje modelu w korekcie i pełny kadr

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...c6f9597a0cbaf8c3a2d27966a586693ab2498fde oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem cztery części zmiany. Pierwsza to nowy wrapper `CorrectionGridProposals` w głównej Korekcie cięcia siatki. Druga to opcjonalny kadr 70% i pełne zdjęcie we wspólnym edytorze. Trzecia to skrót w Adminie, a czwarta trwały renderer HTML razem z jego testami i dokumentacją. Część funkcjonalna działa poprawnie:
- na montowaniu nie ma żadnego POST;
- tożsamość planszy jest sprawdzana przez grę, import, id, SHA źródła i obie rewizje (backend wypełnia je z tych samych kolumn `board.geometry_revision` i `item.resolution_revision`);
- spóźnione odczyty są odrzucane;
- dotychczasowi konsumenci edytora zachowują kadr 35%;
- allowlista proxy Reviewera obejmuje już używane endpointy propozycji.

Werdykt blokuje jedna rzecz: nowy plik testowy w `scripts/tests` nie przejdzie obowiązkowego `mypy --strict`, a typecheck Pythona nie był uruchomiony. Do tego dochodzą drobne problemy z informacją zwrotną dla operatora po decyzji w kolejce.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `scripts/tests/test_grid_correction_comparison.py:13` — `npm run python:typecheck` (`package.json:138`) uruchamia `mypy` w trybie `strict = true` (`pyproject.toml:45`) na całym katalogu `scripts`, więc obejmuje też ten nowy plik.
  - **Błędy, które mypy zgłosi:**
    - `spec.loader.exec_module(module)` wywołuje się na `ModuleSpec | None` i na `Loader | None` (union-attr), a `module_from_spec(spec)` dostaje `spec` typu Optional (arg-type);
    - metody `setUp` (linia 17), `write` oraz `test_*` (linie 87, 106, 116) nie mają adnotacji (no-untyped-def).
  - **Skutek:** pada `npm run typecheck` i `npm run quality`, wbrew `AGENTS.md:152` („testy zmienionego pionu, jego lint i typecheck”). Weryfikacja wykonawcy (`ai_docs/quality/TASK-1153_VERIFICATION.md`) deklaruje dla nowych skryptów tylko Ruff, a w `D:/game_predicotr/artifacts/task1153/` nie ma logu mypy.
  - **Poprawka:**
    - dodać `assert spec is not None and spec.loader is not None` przed użyciem;
    - dodać adnotacje (`-> None`, `name: str`, `data: object`);
    - uruchomić `.\.venv\Scripts\python.exe -m mypy scripts/render_grid_correction_comparison.py scripts/tests/test_grid_correction_comparison.py` i dopisać wynik do weryfikacji.

### P2

- [P2-1] `pyproject.toml:42` — `testpaths` obejmuje tylko `services/api/tests` i `services/worker/tests`, a `scripts/run_python_tests.ps1` w ogóle nie odwołuje się do `scripts`.
  - **Skutek:** nowe testy renderera (`scripts/tests/test_grid_correction_comparison.py`) nie wchodzą do `npm run python:test` ani do `quality`. Ochrona przed regresją renderera zależy więc od ręcznego uruchomienia.
  - **Poprawka:** wpiąć test do istniejącego zestawu albo jawnie zapisać w weryfikacji i w `VISION_LAB.md` komendę uruchomienia. Ryzyko można też przyjąć z adnotacją.

- [P2-2] `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx:372` — `onChanged` wrappera (używane też jako `onRejected`, `correction-grid-proposals.tsx:124-125`) woła `loadPage(undefined, { resetHistory: true })` bez `preserveNotice` i bez ustawienia komunikatu. `loadPage` od razu ustawia `pageState='loading'` i czyści `notice` (linie 129-131).
  - **Skutek po przyjęciu lub odrzuceniu propozycji:**
    - komponent propozycji jest odmontowywany, więc komunikat „Odrzucono propozycję. Zgłoszenie siatki pozostaje otwarte.” albo „Zapisano decyzję…” znika natychmiast i operator nie dostaje potwierdzenia;
    - przy odrzuceniu plansza zostaje w kolejce, ale kolejka wraca do pierwszej pozycji i traci historię „← Poprzednia”. Jeśli operator doszedł do planszy przez „Pomiń na razie”, trafi na inną planszę.
  - Niezapisany szkic głównego edytora jest chroniony przez `localStorage` (`deferred-board-cell-geometry-editor.tsx:470`, `530`), więc danych się nie traci.
  - **Poprawka:** ustawić komunikat przez `setNotice` i wołać `loadPage(..., { preserveNotice: true, resetHistory: true })`, tak jak robią `handleSaved` i `handleRejected`. Przy odrzuceniu warto rozważyć ponowny odczyt bieżącego kursora. Do tego test integracyjny odrzucenia w głównej kolejce.

- [P2-3] `apps/reviewer/src/features/operational-reviews/correction-grid-proposals.tsx:67` — przy niezgodności wersji wrapper każe „Odśwież kolejkę lub ponów odczyt”, ale ma tylko przycisk „Odśwież propozycje”. Ten ponownie porównuje tę samą nieaktualną pozycję kolejki, więc błąd się powtarza. Przycisk „Od początku” jest wyłączony przy pustej historii (`board-geometry-correction-workspace.tsx:401`).
  - Dodatkowo odpowiedź z `result.error` (bez `data`) też trafia w ten komunikat zamiast w komunikat błędu połączenia.
  - **Skutek:** operator może utknąć do przeładowania strony, choć bez ryzyka dla danych.
  - **Poprawka:** opcjonalny callback `onStale`, który przeładuje kolejkę, oraz rozróżnienie błędu API od niezgodności rewizji.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Propozycje w korekcie bez POST na otwarciu; ten sam workflow accept/edit/reject; konflikty, retry i spóźnione odpowiedzi nie przechodzą na inną planszę | spełnione (uwagi UX w P2-2, P2-3) | `correction-grid-proposals.tsx:48-92` (tylko GET i kontrola tożsamości oraz `active`), `board-geometry-correction-workspace.tsx:366-376` (key per target), `grid-geometry-proposals.tsx:101-121, 154-263`; testy `grid-geometry-proposals.test.mjs:1149-1311` (numeracja z diffu w briefie), `board-geometry-correction.test.mjs:1001-1071` |
| Skrót nie uruchamia treningu ani rozpoznania; workflow pilot/broader zachowany | spełnione | `grid-model-workspace.tsx:60-74` (tylko `details.open` i przewinięcie), `grid-reinference-preview.tsx:376-378`; test `grid-model-workspace.test.mjs:260-275` |
| Szerszy i pełny kadr w obu widokach; kadr nie zmienia geometrii; regresja 35% u starszych konsumentów | spełnione | `operational-review-state.ts:524-545`, `deferred-board-cell-geometry-editor.tsx:163, 345-347, 553-567, 1421-1447`; testy `board-geometry-correction.test.mjs:944-999, 1073-1106`, `operational-review-state.test.mjs:1378-1406`; szablon `grid-correction-comparison.html` (`bounds`, `#framing`) |
| Renderer HTML nie myli zmian z trafnością; provenance zachowane; raport przebudowany i sprawdzony | spełnione | `render_grid_correction_comparison.py` (kontrola wersji modeli i SHA, receipty apply); `sha256sum comparison-data.json` = `73a56c15…7960`, zgodny z deklaracją; `index.html` jest bajtowo równy `comparison.html`; log `report-final.log`: 3/3 OK |
| Testy, lint/typecheck/build Reviewer i Admin, docs/map, Opus bez P0/P1, task-close i commit | niespełnione | P1-1 (brak `mypy` dla nowych plików Pythona); logi buildów i testów Reviewer 56/56 w `artifacts/task1153/` są obecne; task-close i commit jeszcze się nie odbyły |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P1-1, P2-1, P2-2, P2-3.

## Proponowane testy

- `.\.venv\Scripts\python.exe -m mypy scripts/render_grid_correction_comparison.py scripts/tests/test_grid_correction_comparison.py` (albo pełne `npm run python:typecheck`) po dodaniu adnotacji.
- `apps/reviewer/test-interactions/board-geometry-correction.test.mjs`: odrzucenie propozycji w głównej kolejce. Test powinien sprawdzić, że:
  - plansza zostaje na ekranie lub w kolejce;
  - widoczny jest komunikat o otwartym zgłoszeniu;
  - nie ma `createImageGridReviewGeometryRevision`;
  - przy dojściu przez „Pomiń na razie” operator nie trafia na inną planszę bez informacji.
- Ten sam plik: przyjęcie propozycji pokazuje potwierdzenie (`notice`) po przeładowaniu kolejki.
- `apps/reviewer/test-interactions/grid-geometry-proposals.test.mjs`: niezgodność rewizji, a potem działanie ścieżki przeładowania kolejki (po ewentualnym `onStale`).
- Uruchamianie `scripts/tests/test_grid_correction_comparison.py` w ramach `npm run python:test` albo udokumentowana komenda `python -m unittest scripts.tests.test_grid_correction_comparison`.

## Zakres przeglądu i ograniczenia

Przeczytałem:
- brief z pełnym diffem i nowymi plikami;
- w worktree: `board-geometry-correction-workspace.tsx` w całości, `grid-geometry-proposals.tsx` w całości oraz fragmenty `deferred-board-cell-geometry-editor.tsx` (ładowanie, kadr, rysowanie canvasu);
- `reviewer-proxy-policy.ts` (allowlista propozycji);
- schematy i repozytoria API, żeby sprawdzić, skąd pochodzą `geometryRevision` i `resolutionRevision` w obu odpowiedziach;
- konfigurację `pyproject.toml` i `package.json` (mypy, pytest, Prettier);
- `AGENTS.md` (sekcja testów).

Tylko do odczytu sprawdziłem hash `comparison-data.json`, równość `index.html` i `comparison.html` oraz logi wykonawcy w `D:/game_predicotr/artifacts/task1153/`.

Nie uruchamiałem testów, lintu, typechecku ani buildów, bo mypy zapisuje cache. Błędy mypy w P1-1 wynikają z analizy statycznej konfiguracji `strict` i kodu. Nie oglądałem UI ani gotowego HTML w przeglądarce. Wydajności canvasu w trybie pełnego zdjęcia dla dużych fotografii nie dało się ocenić statycznie: backing store canvasu ma rozmiar kadru w pikselach źródła (`deferred-board-cell-geometry-editor.tsx:607-608`).
