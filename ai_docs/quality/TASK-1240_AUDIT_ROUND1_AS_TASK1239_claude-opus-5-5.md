# Audyt TASK-1239 — Wykorzystanie częściowych korekt siatki i uczciwe porównanie modeli historycznych

Werdykt: REVISE
Audytor: claude-opus-5-5, przegląd statyczny
Wykonawca: brief nie podaje modelu wykonawcy; wiadomo tylko, że należy do innej rodziny modeli niż audytor
Zakres: 2b4537e5de99bde9d2507d532a0bf2500e068016...2b4537e5de99bde9d2507d532a0bf2500e068016 oraz zmiany niezacommitowane z pathspec briefu, data 2026-11-17
Runda: 1
SHA pakietu: 19d5ea523555bb732980a656d6182da94678f854fdae7f92ba7234615d2d61ef
Otwarte P0: 0
Otwarte P1: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadałem przejęty skrypt operatorski i porównałem go z zachowaną kopią oryginału. Przejrzałem też narzędzie do porównania historycznego, skrypt podglądu w trybie READ ONLY, dwa nowe pliki testów, raporty jakości i dokumentację. Skrypt startowy spełnia wymagania: domyślnie wybiera grid-only, odrzuca zapisane polecenie z innym trybem przed POST, nie przepisuje zapisanych poleceń i sprawdza kontrakt OpenAPI. Porównanie modeli używa istniejących adapterów i metryk, a wybór starszego modelu ustala wyłącznie na VALIDATION. Główny problem dotyczy lejka danych. Brakuje dokładnej liczby pełnych reprezentantów TRAIN i powodów ich pominięcia, więc wynik 10 zdjęć nie jest wyjaśniony dokładnymi licznikami, czego wymaga zakres i pierwsze kryterium akceptacji.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `scripts/compare_grid_historical_models.py:92` — Funkcja `frozen_funnel` (linie 92–106) liczy reprezentantów TRAIN (379) i reprezentantów częściowych, czyli takich z liczbą kwalifikowanych plansz od 1 do 8 (367). Nie liczy reprezentantów TRAIN z `qualifiedBoards == 9`, a według `grid_detector_readiness.py:19` właśnie ta liczba wyznacza materiał dla `screen+grid`. Nie liczy też reprezentantów z zerem kwalifikowanych plansz. Z różnicy 379 − 367 = 12 nie da się więc ustalić, ile było pełnych zdjęć i dlaczego snapshot użył 10, a nie 12. Dowód dodatkowo zapisuje `"exclusionReasons": null` (`ai_docs/quality/TASK-1239_COMPARISON_EVIDENCE.json:300`) bez wyjaśnienia. Raport w `ai_docs/quality/PARTIAL_GRID_CORRECTIONS_COMPARISON_20261117.md:17-20` podaje 10 pełnych zdjęć tylko jako stwierdzenie. Skutek: zakres („record distinct counts/reasons for omissions”) i kryterium „Exact frozen counts explain the 10-photo result” są spełnione jakościowo, ale nie dokładnymi licznikami, mimo że kryterium jest odhaczone. Poprawka: dodać do lejka liczbę reprezentantów TRAIN z 9 kwalifikowanymi planszami, liczbę z zerem plansz i rozbicie pozostałych pominięć (na przykład duplikaty kopii i bufor) według kodów przyczyn. Jeśli manifest nie zawiera powodów, trzeba to jawnie napisać w raporcie i JSON zamiast samego `null`. Następnie przeliczyć artefakt w nowym pliku z receiptem SHA.

### P2

- [P2-1] `scripts/Start-GridCorrectionLearning.ps1:19` — Ścieżka domyślna była związana z `GameId` przez nazwę pliku, a `-CommandFile` (linie 19–20) zrywa to powiązanie. Zapisane polecenie (linie 35–45) nie zawiera `gameId`, więc ten sam plik podany z innym `-GameId` wyśle ten sam klucz idempotencji do innej gry. Serwer szuka klucza w obrębie gry, więc po cichu powstanie nowy przebieg. To łamie zasadę z komentarza w linii 22, że aktualizacja nigdy nie może po cichu uruchomić kolejnego przebiegu. Poprawka: zapisywać `gameId` obok polecenia, na przykład w osobnym pliku metadanych, żeby nie zmieniać body POST, i odrzucać niezgodność przed POST. Można też jawnie zaakceptować to ryzyko jako błąd operatora.
- [P2-2] `ai_docs/quality/TASK-1239_COMPARISON_EVIDENCE.json:351` — Plik `data-funnel-v2.json` jest przypięty SHA, ale nie występuje w `artifacts/TASK-1239-comparison/execution-receipt.json`. Ten receipt obejmuje tylko `data-funnel.json` i zamrożony runner. Wersja v2 zawiera nową wartość `assignedTrainPhotos=428`, której nie ma w v1 (tam pod tą nazwą jest 379). Oznacza to nowe obliczenie, a nie tylko zmianę nazwy, i nie ma hasha kodu, który je wykonał. Raport (`PARTIAL_GRID_CORRECTIONS_COMPARISON_20261117.md:72`) wspomina tylko o rozdzieleniu nazw liczników. Poprawka: dopisać receipt v2 z SHA źródła, które go utworzyło, albo opisać pochodzenie liczby 428.
- [P2-3] `pyproject.toml:42` — Nowe testy w `scripts/tests/` leżą poza `testpaths`. Skrypt `scripts/run_python_tests.ps1:14-18` uruchamia tylko `services/api/tests` i `services/worker/tests`, więc `npm run quality` ich nie wykona i regresja startera może przejść niezauważona. Taki był już wcześniej przyjęty sposób dla `scripts/tests`. Poprawka: zaakceptować ryzyko i zapisać w Outcome jawną komendę uruchomienia (`.\.venv\Scripts\python.exe -m pytest scripts/tests/test_partial_grid_learning_starter.py scripts/tests/test_grid_historical_comparison.py`) albo dołączyć te pliki do istniejącego zestawu bez zmiany zakresu.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Dokładne zamrożone liczniki wyjaśniają wynik 10 zdjęć i niewykorzystane poprawne korekty | niespełnione (częściowo) | Niewykorzystane korekty są wyjaśnione: 367 zdjęć i 424 plansze w `TASK-1239_COMPARISON_EVIDENCE.json` i `PARTIAL_GRID_CORRECTIONS_COMPARISON_20261117.md:17-20`. Brakuje licznika pełnych zdjęć i powodów pominięć (P1-1, `compare_grid_historical_models.py:92-106`). |
| Nowe polecenia domyślnie wybierają grid-only, a jawny tryb detektora nadal działa | spełnione | `Start-GridCorrectionLearning.ps1:5`, `:39`; test sparametryzowany `test_fresh_starter_defaults_to_partial_compatible_grid_mode` |
| Stare polecenia nie są przepisywane, a niezgodne opcje kończą się błędem bez POST | spełnione | `Start-GridCorrectionLearning.ps1:34-60` (sprawdzenie trybu i klucza przed pobraniem OpenAPI i przed POST); testy `test_old_detector_command_requires_explicit_replay_and_is_never_rewritten`, `test_invalid_saved_key_never_reaches_network`, `test_old_api_contract_blocks_training_post`. Plik oryginału w głównym checkoutcie nadal zawiera `trainingMode = 'screen+grid'` (`D:\game_predicotr\scripts\Start-GridCorrectionLearning.ps1:28`). |
| Częściowe cele są używalne w grid-only, a nieoznaczone plansze nie są negatywami ani wyciekiem | niezweryfikowane statycznie | Brak zmian w kodzie danych. Wykonawca powołuje się na istniejące testy datasetu (7 PASS), których nie uruchamiałem. Serwer domyślnie ustawia `trainingMode="grid-only"` (`schemas/grid_correction_learning.py:37`). |
| Kandydat i modele historyczne mają porównywalne dowody związane sumami kontrolnymi na tych samych zdjęciach, a reguła wyboru i ograniczenia są ujawnione | spełnione | `compare_grid_historical_models.py` sprawdza manifest, rodzinę, SHA i `input_sha256` przed inferencją, a REGRESSION mierzy dopiero po zapisie `historical-selection.json`. Ograniczenia opisuje sekcja „Dowody i ograniczenia” raportu. Liczby w raporcie zgadzają się z JSON (45/45, 43 i 42, 17 i 18, 0,006198 i 0,006031, około 2,7%). |
| Testy, lint, typy, dokumentacja, mapy i audyt Claude przechodzą | niezweryfikowane | Kryterium jest jawnie odznaczone jako otwarte. Mapy kodu (`CODE_MAP*.md`) leżą poza pathspec pakietu. |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P2-1, P2-2, P2-3.

## Proponowane testy

- `scripts/tests/test_grid_historical_comparison.py`: do `test_funnel_separates_roles_aliases_and_actual_consumed_counts` dodać asercje nowych liczników (pełne reprezentanty TRAIN z 9 planszami i reprezentanty z zerem plansz) oraz przypadek bez `qualifiedBoards`. Komenda: `.\.venv\Scripts\python.exe -m pytest scripts/tests/test_grid_historical_comparison.py`.
- `scripts/tests/test_partial_grid_learning_starter.py`: jeśli P2-1 zostanie naprawione, dodać test, w którym ten sam `-CommandFile` z innym `-GameId` kończy się błędem i nie wysyła żadnego żądania. Komenda: `.\.venv\Scripts\python.exe -m pytest scripts/tests/test_partial_grid_learning_starter.py`.
- Test startera z kontraktem OpenAPI, w którym brakuje ścieżki `/api/v1/admin/games/{game_id}/grid-correction-learning`, żeby potwierdzić bezpieczne zatrzymanie (fail-closed) przy braku `$ref`.

## Zakres przeglądu i ograniczenia

Przeczytałem pliki z pakietu:

- `scripts/Start-GridCorrectionLearning.ps1` i `artifacts/TASK-1239-original-starter.ps1.txt`,
- `scripts/compare_grid_historical_models.py` i `scripts/inspect_grid_correction_selection.py`,
- dwa nowe pliki testów,
- plik taska, raport jakości, JSON dowodów i różnice w dokumentacji wymagań i architektury.

Poza pakietem przeczytałem tylko to, co było potrzebne do oceny:

- `grid_correction_metrics.py` (`measure_role`, `evaluate_photo`, `cell_cut_fraction`),
- `GridModelEvaluationJobHandler._photos` i `_measure_unit`,
- schemat `GridCorrectionLearningStartCommand` w worktree i w żywym checkoutcie (pola `prepareInBackground`, `preparationOnly` i `previewSha256` są opcjonalne tylko w żywym checkoutcie),
- `grid_detector_readiness.py`,
- `pyproject.toml` i `scripts/run_python_tests.ps1`,
- artefakty `data-funnel.json`, `data-funnel-v2.json` i `execution-receipt.json`.

Nie uruchamiałem testów, lintu ani mypy. Nie liczyłem sum SHA artefaktów i nie porównywałem bajtowo zamrożonego runnera z bieżącym skryptem. Nie czytałem plików wyników per model ani zamrożonego manifestu kohorty, więc wyniki inferencji i zgodności z poprzednim raportem przyjmuję na podstawie deklaracji wykonawcy i spójności JSON. Map kodu i `CURRENT_STATE.md` nie oceniałem, bo leżą poza pathspec pakietu.