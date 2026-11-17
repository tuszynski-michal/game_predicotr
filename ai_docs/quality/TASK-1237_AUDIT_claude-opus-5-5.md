# Audyt TASK-1237 — Scoped grid training budget extension and checkpoint recovery

Werdykt: PASS
Audytor: claude-opus-5-5, reasoning domyślny
Wykonawca: model innej rodziny (gałąź codex/*), reasoning nieznany
Zakres: HEAD...498ccebf9a63e68145361785860cdbc07eb47a08 oraz zmiany niezacommitowane, data 2026-11-17
Runda: 1
SHA pakietu: 012591837d65bc316152635dcf3012ae97b67599e63e0f02afd07f5463ba1f14
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przejrzałem czystą funkcję przyznania limitu (`run_budget_extension.py`), operatorskie CLI podglądu i zastosowania, testy jednostkowe i test PostgreSQL oraz zmiany w dokumentacji. Porównałem je z rzeczywistą ścieżką wznowienia: `GridTrainingJobHandler`, `RunBudget.with_current_limits`, admission, `ChildControl`/`Watchdog`, `train()` i API `resume`/`requeue_job`.

Zmiana podnosi wyłącznie `max_seconds` z 7200 do 14400. Ustawia też wskaźnik checkpointu i dopisuje zdarzenie historii. Zużyte sekundy, kroki i próby pozostają bez zmian. Wynikowy budżet z polityką `grid-training-limits-v2` przechodzi przez `with_current_limits` i admission bez obcięcia, a dziecko dostaje `remainingSeconds` z tego budżetu.

CAS pod `FOR UPDATE` odbudowuje podgląd z zablokowanego wiersza. Drugi grant jest niemożliwy, bo `prepare_extension` wymaga `max_seconds == 7200`. Nie znalazłem błędów P0 ani P1. Główne ryzyko rezydualne to słabsze niż deklarowane asercje w teście PostgreSQL.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/tests/integration/test_grid_run_budget_extension_postgres.py:118` — Asercja „brak drugiego grantu” sprawdza `saved`, czyli migawkę odczytaną w linii 111 przed ponowieniem z linii 115–117. Nie dowodzi więc, że ponowienie po utraconej odpowiedzi nie zmieniło wiersza w bazie. Outcome twierdzi, że „lost-response replay adds no second grant” zostało zweryfikowane na prawdziwej bazie. Kod jest poprawny z inspekcji: gałąź `alreadyApplied` w `scripts/extend_grid_training_run.py:157-158` kończy się przed `UPDATE`. Dowód testowy jest jednak pozorny. Proponowana poprawka: po ponowieniu odczytać wiersz jeszcze raz przez `cli.read_row`. Następnie sprawdzić `len(history) == 1`, równość `checkpoint_payload` z `afterState` i niezmienione `updated_at`.
- [P2-2] `scripts/extend_grid_training_run.py:112` i `scripts/extend_grid_training_run.py:123` — Docstring w linii 58 obiecuje „exact production binding”. Produkcyjne dziecko buduje jednak `selectionInput` z `manifest["gameId"]` i `mode` z `preset.mode` (`services/worker/src/game_predictor_worker/images/grid_training_child.py:481` i `:540`). CLI używa w tych miejscach `row["game_id"]` i `inputs["mode"]`. Rozbieżność działa fail-closed: inny wynik dałby `CHECKPOINT_BINDING_MISMATCH`, a nie fałszywą akceptację. Według wykonawcy rzeczywisty checkpoint przeszedł walidację. Proponowana poprawka: użyć tych samych źródeł co dziecko (`manifest["gameId"]`, `PRESETS[...].mode`). Można też zaakceptować ryzyko jako wyłącznie fałszywie negatywne.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Podgląd jest tylko do odczytu i fail-closed przy stanie aktywnym, obcym, zdryfowanym lub uszkodzonym | spełnione | Transakcja `READ ONLY` i odmowa nadpisania pliku podglądu: `scripts/extend_grid_training_run.py:212-217`. Status, dzierżawa, polityka, rozliczenie i budżet: `run_budget_extension.py:21-55`. Ścieżka, spec, manifest, binding i stan: `scripts/extend_grid_training_run.py:75-143`. Testy: `test_grid_run_budget_extension.py:93-131,215-239`. |
| Apply zmienia tylko limit, wskaźnik i historię; nieaktualny podgląd odpada; ponowienie nie daje drugiego grantu | spełnione (dowód testowy ponowienia osłabiony, P2-1) | `deepcopy(before)` z podmianą trzech kluczy: `run_budget_extension.py:85-88`. Ponowne sprawdzenie pod blokadą i odbudowa podglądu: `run_budget_extension.py:117-127`, `scripts/extend_grid_training_run.py:163-174`. Gałąź `alreadyApplied`: `run_budget_extension.py:105-116`. Drugi grant blokuje warunek `budget.max_seconds != 7200`: `run_budget_extension.py:44-53`. Testy: `test_grid_run_budget_extension.py:68-90,134-162`, `test_grid_run_budget_extension_postgres.py:99-118`. |
| Weryfikacja bindingu i bajtów checkpointu; zużycie pozostaje 7200 s / 1200 kroków | spełnione statycznie | Sprawdzenie SHA, bindingu oraz RNG/optimizera przez istniejący `load_checkpoint`: `checkpoint.py:97-147`, wywołanie w `scripts/extend_grid_training_run.py:128`. Odtworzenie early-stop i ekspozycji: `scripts/extend_grid_training_run.py:129-143`. Zachowanie zużycia: `test_grid_run_budget_extension.py:76-84`. Brak obcięcia limitu przy wznowieniu: `grid_training_admission.py:501-514,695`, `grid_training_handler.py:234,507`. |
| Celowane testy unit/PostgreSQL/lint/typy/docs/mapy oraz przegląd Claude | niezweryfikowane (wyniki deklarowane przez wykonawcę); przegląd Claude: niniejszy raport | Sekcja „Verification results” w pliku taska. Audytor nie uruchamiał poleceń. |
| Wznowienie tego samego rodzica i dziecka z 14400 s i checkpointem z kroku 575 | niezweryfikowane (krok operacyjny po commicie, poza zakresem przeglądu statycznego) | Ścieżka statycznie spójna: `api/.../grid_training_runs.py:296-317` (`requeue_job` zachowuje `checkpoint_payload`, `domain/jobs.py:498-520`), `grid_training_handler.py:589,719` (`resume` = `state.checkpoint`). |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P2-1, P2-2.

## Proponowane testy

- W `services/api/tests/integration/test_grid_run_budget_extension_postgres.py`: ponowny odczyt wiersza po ponowieniu `apply_preview` i asercje na `history`, `checkpoint_payload` oraz `updated_at` (P2-1). Komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_run_budget_extension_postgres.py`.
- W tym samym pliku: scenariusz dla gałęzi `scripts/extend_grid_training_run.py:167-168`. Inna transakcja zatwierdza ten sam grant między pierwszym odczytem a `FOR UPDATE`, np. wewnątrz monkeypatchowanego `checkpoint_pointer`. Wynik powinien mieć `alreadyApplied` i zawierać dokładnie jedno zdarzenie historii.
- Scenariusz w tym samym pliku: po zastosowaniu grantu zmienić status na `created`, tak jak robi `requeue_job` przy resume, i wywołać nowy podgląd lub apply innego podglądu. Oczekiwany wynik to `RUN_BUDGET_UNSUPPORTED` lub `RUN_NOT_STOPPED`, bez zapisu.
- W `services/worker/tests/test_grid_run_budget_extension.py`: przypadek `quiescent` z dzierżawą GPU w stanie `held`. Oczekiwany wynik to `GPU_NOT_QUIESCENT` przed jakimkolwiek zapisem. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_run_budget_extension.py`.

## Zakres przeglądu i ograniczenia

Przeczytałem cały zamrożony pakiet: plik taska, CLI, moduł worker i oba pliki testów oraz diff dokumentacji. Dodatkowo przeczytałem kod potrzebny do oceny:

- `grid_training_admission.py`: `RunBudget`, `digest`, `with_current_limits`, admission;
- `grid_training_handler.py`: `RunState`, `_recover_previous_attempt`, `_adopt_pointer`, `_train`, `_reserve`, `_settle_steps`, `_supervise`, `_spec`;
- `grid_training_child.py`: `ChildControl`, `Watchdog`, budowa `TrainingPlan`;
- `grid_training.py`: ścieżka resume w `train()`;
- `checkpoint.py`: `load_checkpoint`, `write_checkpoint`;
- `grid_rescue_training.py`;
- `grid_training_runs.py`: `resume`/`view`;
- `domain/jobs.py`: `requeue_job`;
- `config.py`: `owner_database_url`;
- `grid_training_cohort_artifacts.py`;
- `_application_role_database.py`.

Nie uruchamiałem testów, lintu, mypy, `code-map:check` ani CLI. Nie czytałem plików `.runtime/task1237-*.json`. Nie weryfikowałem stanu produkcyjnej bazy ani artefaktów. Deklarowany SHA podglądu i walidacja rzeczywistego checkpointu z kroku 575 pochodzą wyłącznie z Outcome wykonawcy.

Statycznie nie da się ustalić, dlaczego produkcyjny wskaźnik checkpointu był pusty. Przy wznowieniu istniejące `_adopt_pointer` może przyjąć nowszy, nienaruszony checkpoint z `progress.json` próby 2. Wtedy rzeczywisty krok startowy może być wyższy niż 575, co trzeba potwierdzić przy weryfikacji kryterium 5.

Pliki `CODE_MAP*.md` są zmienione w drzewie roboczym, ale nie należą do zakresu pathspec pakietu i nie zostały ocenione.