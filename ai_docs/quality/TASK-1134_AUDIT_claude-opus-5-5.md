# Audyt TASK-1134 — Gotowość GPU i czytelne przebiegi uczenia

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...a28aca30fe8d1b46e3e8262c4423f2be96a50517 oraz zmiany niezacommitowane, data 2026-11-02
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem nową fabrykę `_grid_training_python` w CLI workera i jej użycie przez rodzica uczenia z korekt w lane general oraz przez supervisor treningu. Sprawdziłem też nowe regresje fabryki, zmianę listy przebiegów w panelu i CSS oraz aktualizacje dokumentacji i mapy kodu. Zmiana jest mała i spójna z zakresem. Jawna zmienna ma pierwszeństwo, a błędna jawna ścieżka nie przełącza się na inny interpreter. Brak konfiguracji kończy się `GRID_TRAINING_PYTHON_UNSET`, a obaj konsumenci w CLI korzystają z tej samej funkcji. Główne ryzyko leży poza Pythonem. Skrypt `manage_worker_lanes.ps1` rozwiązuje interpreter według innej polityki i przekazuje wynik tylko do lane grid-training. Przy niestandardowej konfiguracji rodzic i trener mogą więc dostać różne interpretery.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/cli.py:224` — Polityka CLI różni się od `Resolve-GridTrainingPython` w `scripts/manage_worker_lanes.ps1:140`. Skrypt pomija błędne kandydaty (`-GridTrainingPython`, zmienna Process, zmienna User) i przechodzi do następnego. Rozwiązaną ścieżkę ustawia tylko dla lane grid-training (`scripts/manage_worker_lanes.ps1:399`). Worker general dziedziczy wyłącznie środowisko procesu.
  - Skutek 1: start z `-GridTrainingPython <inny interpreter CUDA>` bez `.venv-vision-lab` w checkoutcie. Trener ma wtedy CUDA, a rodzic w general dostaje `GRID_TRAINING_PYTHON_UNSET`. Wraca dokładnie ten fałszywy `GRID_RUN_GPU_UNAVAILABLE`, który task naprawia.
  - Skutek 2: zmienna środowiskowa zawiera błędną ścieżkę. Trener po cichu dostaje repozytoryjny venv, a rodzic kończy probe błędem `GRID_TRAINING_PROBE_FAILED`.
  - Zdanie w `ai_docs/architecture/VISION_LAB.md:898` („An explicit path always wins, including when invalid”) jest więc prawdziwe tylko dla samego CLI.
  - Domyślna konfiguracja (brak zmiennej i istniejący `.venv-vision-lab`) działa w obu procesach tak samo. Błąd zawsze kończy się bezpieczną odmową, a nie wyborem CPU, dlatego to P2.
  - Proponowana poprawka: w skrypcie lane przekazać rozwiązany interpreter także do lane general i nie przechodzić do kolejnego kandydata po błędnej jawnej wartości. Alternatywnie zapisać ryzyko i doprecyzować dokument, że gwarancja dotyczy fabryki CLI.
- [P2-2] `apps/admin/src/features/model-quality/grid-correction-learning.css:65` — Prezentacji listy nie chroni żaden test automatyczny: klasa `gridCorrectionRunList`, `list-style: none`, gap 12 px oraz `--button-height` 38/44 px przy `pointer: coarse`. Dowodem są tylko oględziny w przeglądarce. Wariant coarse nie został zweryfikowany nawet tam. Poprawność zależy od reguły `.modelQualityWorkflowGroup .primaryButton { min-width: 0; overflow-wrap: anywhere }` w `apps/admin/src/app/globals.css:32`. Bez niej `min-width: max-content` z `packages/ui/src/buttons.css:15` blokowałby zawijanie długich etykiet na mobile. Skutek: przeniesienie panelu poza tę grupę albo zmiana specyficzności może po cichu przywrócić przepełnienie lub punktory. Proponowana poprawka: dodać lekki test kontraktu w `apps/admin/test` (klasa w TSX i reguły w CSS) albo zaakceptować ryzyko.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Brak env przy istniejącym lokalnym CUDA daje poprawny probe fabryki w nowym procesie | spełnione | `services/worker/src/game_predictor_worker/cli.py:230-233`; testy `services/worker/tests/test_grid_training_runtime_resolution.py:34-42` i `:83-104`; `artifacts/task1134-after-probe.json` (`configuredPython` = `.venv-vision-lab\Scripts\python.exe`, `cuda_available: true`, `admitted: true`) |
| Jawna ścieżka ma pierwszeństwo; błędna jawna konfiguracja nie uruchamia fallbacku | spełnione (w CLI; uwaga P2-1 dla skryptu lane) | `cli.py:226-229`; testy `test_grid_training_runtime_resolution.py:45-52` i `:55-72`; `grid_training_handler.py:323-324` |
| Brak obu konfiguracji nadal bezpiecznie blokuje start, bez wybierania CPU | spełnione | `cli.py:234`; `images/grid_training_handler.py:311-312`; `images/grid_correction_learning_handler.py:54-57`; test `test_grid_training_runtime_resolution.py:75-80` |
| Parent general i właściwy trener korzystają z tej samej polityki rozwiązywania | spełnione w CLI (częściowo na ścieżce skryptu lane, P2-1) | `cli.py:216` i `cli.py:250` (jedna fabryka dla `GRID_CORRECTION_LEARNING` w `cli.py:617` i `GRID_TRAINING` w `cli.py:406`); `scripts/manage_worker_lanes.ps1:140-155`, `:399-405` |
| Lista przebiegów jest niższa, zielona, ma odstępy i mieści się na mobile | spełnione statycznie; wygląd niezweryfikowany przez audytora | `grid-correction-learning-panel.tsx:624-628`; `grid-correction-learning.css:52-73`; `apps/admin/src/app/globals.css:32-38`; specyficzność `.gridCorrectionLearning .gridCorrectionRunList` (0,2,0) wygrywa z `.modelQualityWorkflowGroup ul:has(> li > button)` (0,1,3) |
| Regresje workera, interakcje UI, scoped lint/typecheck, docs/map i Opus PASS | niezweryfikowane (testy nieuruchomione); docs/map spełnione; Opus PASS — ten raport | `ai_docs/architecture/CODE_MAP.md:130`: 276 zgadza się z `git ls-files --cached --others --exclude-standard services/worker/tests` (276 plików `.py`); `VISION_LAB.md:897-901`; `ADMIN_APP.md:29-32`; wyniki 34/34 i 29/29 znane tylko z Outcome |
| Outcome, task-close, osobny commit i record-hash | niezweryfikowane (oczekujące po audycie) | `ai_docs/tasks/1134-grid-learning-runtime-history.md`: `status: in_progress`, kryteria nieodhaczone; brak commita taska |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2.

## Proponowane testy

- Test kontraktu w `apps/admin/test/` (np. `grid-correction-run-list.test.mjs`). Powinien sprawdzać, że lista przebiegów ma klasę `gridCorrectionRunList`, a przyciski `primaryButton gridCorrectionRunButton`, oraz że CSS zawiera `list-style: none`, `--button-height: 38px` i regułę `pointer: coarse` z 44px. Komenda: `npm run test --workspace @game-predictor/admin`.
- Opcjonalny test Pester albo statyczny dla `scripts/manage_worker_lanes.ps1`: rozwiązany interpreter (z `-GridTrainingPython`) trafia także do środowiska lane general. Dotyczy tylko sytuacji, gdy P2-1 zostanie naprawione, a nie zaakceptowane.
- Uruchomienie regresji: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_training_runtime_resolution.py services/worker/tests/test_grid_training_handler.py`.

## Zakres przeglądu i ograniczenia

Przeczytałem:
- brief audytu i plik taska;
- `services/worker/src/game_predictor_worker/cli.py` (importy, fabryki `_grid_correction_learning_handler`, `_grid_training_python` i `_grid_training_handler` oraz miejsca ich rejestracji);
- `images/grid_training_handler.py` (`probe`, `_environment`);
- `images/grid_correction_learning_handler.py` (preflight runtime);
- nowy plik testów;
- `scripts/manage_worker_lanes.ps1` (`Resolve-GridTrainingPython` i ustawianie środowiska lane);
- `packages/ui/src/buttons.css`;
- `grid-correction-learning.css` i fragment panelu;
- reguły `modelQualityWorkflowGroup` w `apps/admin/src/app/globals.css`;
- diffy `CODE_MAP.md`, `VISION_LAB.md`, `ADMIN_APP.md` i `CURRENT_STATE.md`;
- dowód `artifacts/task1134-after-probe.json`.

`CODE_MAP_SYMBOLS.md` nie ma różnicy treści względem HEAD, tylko ostrzeżenie o końcach linii. Nie uruchamiałem testów, lintów, typechecku, przeglądarki ani probe CUDA. Wyniki 34/34, 29/29 i pomiary 38 px / 12 px / 237.3 px znam wyłącznie z Outcome wykonawcy. Nie sprawdziłem fizycznie wariantu `pointer: coarse` ani zachowania rzeczywistych procesów lane po restarcie, bo restart jest poza zakresem.
