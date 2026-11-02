# Audyt TASK-1123 — Odbiór i dokumentacja uczenia z korekt

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol/high według taska; sekcja Outcome wskazuje, że zmiany wykonał lead
Zakres: HEAD...470faf466dc1b0184169e3800ea82c8f6b1ca1d9 oraz zmiany niezacommitowane, data 2026-11-02
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano trzy poprawki w `grid_correction_apply.py`, które zamykają P2-3, P2-5 i P2-6 z audytu R2 TASK-1122. Zbadano też nowe testy jednostkowe i testy PostgreSQL, zmiany w trzech legacy testach e2e/bridge, dokumentację wymagań i architektury oraz raport odbioru. Poprawki odpowiadają propozycjom z poprzedniego audytu:

- `resume` sprawdza `_active` pod tą samą blokadą rejestru co `start`;
- `_view` nie zawodzi przy obcej publikacji z innym dowodem;
- adopcja w GET wymaga ukończonych porównań.

Nowe testy rozróżniają zachowanie sprzed poprawki i po niej. Nie znaleziono błędów P0 ani P1. Główne ryzyko dotyczy odporności zmienionych fixture legacy: współdzielony katalog journali z env oraz sztywna głowa migracji.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/tests/integration/test_grid_training_cohort_e2e_postgres.py:825-830` (tak samo `test_grid_model_evaluation_e2e_postgres.py:197-204`) — gdy `GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT` jest już ustawione w środowisku, oba testy używają tego samego katalogu journali. Wcześniej każdy test miał własny, unikalny `evidence/resources`. `_check_cleanup` czyta wszystkie `*.json` z tego katalogu (`:765-768`) i wymaga, by nazwa bazy zaczynała się od `game_predictor_t0995e_` (`:786`).
  - **Skutek:** wspólne uruchomienie kilku plików integration z ustawioną zmienną, na przykład obu „pozostałych przebiegów legacy” z raportu odbioru, albo ponowne użycie tego samego katalogu da fałszywy FAIL na journalu t0997e lub z poprzedniego przebiegu. Danych to nie narusza.
  - **Propozycja:** zawsze tworzyć podkatalog per test, na przykład `Path(env_root) / uuid4().hex`. Alternatywnie w `_check_cleanup` filtrować journale po prefiksie, zamiast asercją odrzucać obce.
- [P2-2] `services/api/tests/integration/test_grid_model_evaluation_bridge_postgres.py:50-52,84-86` — asercje wpisują na sztywno `0171_grid_correction_learning`. Tak właśnie powstał P2-8 z T1: poprzednia wartość `0168_source_crop_runs` przestała pasować po kolejnych migracjach.
  - **Skutek:** każda następna migracja znowu zepsuje ten legacy test, choć jego cel, czyli łańcuch manifestów oraz downgrade/upgrade 0165↔head, się nie zmienia.
  - **Propozycja:** porównywać z `ScriptDirectory.from_config(config).get_current_head()`. Alternatywnie jawnie zaakceptować ryzyko w raporcie odbioru jako świadomą bramkę „aktualizuj przy migracji”.
- [P2-3] `ai_docs/quality/GRID_CORRECTIONS_LEARNING_ACCEPTANCE_20261102.md:899-906` — kanoniczny `mypy services/api/src services/worker/src scripts` dwukrotnie przekroczył 110 s. Kryterium „lint/typecheck” opiera się więc na scoped strict mypy jednego zmienionego modułu produkcyjnego. Jest to jawnie opisane, bez maskowania diagnostyk i bez zmiany configu. Zmiana produkcyjna ma 22 linie w jednym module. Ryzyko jest akceptowalne, zgodnie z wcześniejszymi audytami T1–T3, ale pełny baseline mypy pozostaje otwarty.
  - **Propozycja:** odnotować w CURRENT_STATE osobny punkt na pełny przebieg mypy z dłuższym, uzgodnionym limitem, poza tym taskiem.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Pokrycie DoD planu T4, stare kontrakty i historia; jawne wyniki testów i niewykonanych operacji | spełnione (wyniki uruchomień deklarowane przez wykonawcę, nie powtórzone) | Mapa wymaganie–test: `ai_docs/quality/GRID_CORRECTIONS_LEARNING_ACCEPTANCE_20261102.md:789-806`. Wyniki: `:817-853`. Niewykonane operacje: `:911-916`. Outcome taska: `ai_docs/tasks/1123-grid-correction-learning-acceptance.md:91-123` |
| P2-3 R2 T3: konkurencyjne resume | spełnione | `grid_correction_apply.py:394-398`; `test_grid_correction_apply.py` (test `test_resume_refuses_a_competing_active_apply_without_mutating_parent`); `test_grid_correction_apply_postgres.py:436-439`. Bez guardu `resume` zwróciłby tu `GRID_APPLY_DEFAULT_CHANGED`, więc asercja `GRID_APPLY_BUSY` rozróżnia oba przypadki |
| P2-5 R2 T3: historia mimo obcej publikacji | spełnione | `grid_correction_apply.py:456-465`. Blokada pozostaje w preview (`:190`) i advance (`:592`, `:637`). Testy: `test_grid_correction_apply.py` (`test_history_survives_conflicting_external_publication`) oraz `test_grid_correction_apply_postgres.py:345-382`, gdzie krok 0 to `publish`, więc gałąź konfliktu jest faktycznie wykonana |
| P2-6 R2 T3: adopcja GET po porównaniach | spełnione | `grid_correction_apply.py:433-436,453-455`; test parametryzowany `test_history_adopts_publication_only_after_prior_comparisons` (stany pending/waiting, potem completed) |
| Właściwe testy, lint/typecheck i dokumentacja | spełnione z zastrzeżeniem P2-3; wyniki niezweryfikowane uruchomieniem | Dokumentacja: `ai_docs/requirements/ADMIN_APP.md:47-50`, `ai_docs/architecture/VISION_LAB.md:46-50`, zgodne z kodem. T4 nie dodaje nowych modułów, więc brak zmiany CODE_MAP jest uzasadniony. Ruff i scoped mypy są deklarowane jako PASS |
| Audyt Opus 5.5/high bez otwartych P0/P1 | spełnione (ten raport) | Werdykt PASS |
| Outcome, task-close, osobny wersjonowany commit i record-hash | niezweryfikowane (etap po audycie) | `ai_docs/tasks/1123-grid-correction-learning-acceptance.md:113-116` jawnie wskazuje oczekiwanie |
| Out of scope: brak treningu i migracji operatora, restartu, merge/push | spełnione | W diffie brak zmian konfiguracji, migracji i danych operatora; `GRID_CORRECTIONS_LEARNING_ACCEPTANCE_20261102.md:913-916` |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy (runda 1).

Otwarte: P2-1, P2-2, P2-3.

## Proponowane testy

- `services/api/tests/integration/test_grid_training_cohort_e2e_postgres.py` razem z `test_grid_model_evaluation_e2e_postgres.py` w jednym wywołaniu pytest z ustawionym `GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT`. Test potwierdzi P2-1 albo jego poprawkę. Komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_model_evaluation_e2e_postgres.py services/api/tests/integration/test_grid_training_cohort_e2e_postgres.py` (tylko za zgodą, z limitem czasu jak w raporcie odbioru).
- `services/api/tests/test_grid_correction_apply.py`: wariant P2-5 z `checkpoint_payload`, w którym `set_default` lub `activate` ma już własny receipt. Test potwierdzi, że konflikt na `publish` nie przerywa odczytu dalszych kroków. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_correction_apply.py -k history`.

## Zakres przeglądu i ograniczenia

Przeczytano:

- brief z diffem;
- `grid_correction_apply.py`, linie 180–681: `start`, `list`, `get`, `resume`, `_view`, `_active`, `_publication_receipt`, `advance`;
- odpowiedni fragment `test_grid_correction_apply_postgres.py`, linie 230–489;
- fragment testu bridge;
- `_check_cleanup` w teście cohort e2e;
- importy obu testów e2e;
- listę migracji (głowa `0171_grid_correction_learning`);
- poprzednie raporty audytu TASK-1120 i TASK-1122, czyli źródła P2-3/5/6/8/9.

Nie uruchamiano testów, lint, mypy, `docs:check` ani `code-map:check`. Wszystkie czasy i wyniki PASS w Outcome i raporcie odbioru pochodzą od wykonawcy. Potwierdzono tylko, że plik `artifacts/task1123-legacy-verification.md` istnieje, bez weryfikacji jego treści.

Zmiany w `ai_docs/process/CURRENT_STATE.md`, `ai_docs/archive/CURRENT_STATE_2026Q4.md` i `ai_docs/tasks/completed/1122-grid-correction-learning-panel.md` są widoczne w `git status`, ale leżą poza pathspec briefu i nie były przeglądane.
