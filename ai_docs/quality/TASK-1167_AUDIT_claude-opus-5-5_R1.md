# Audyt TASK-1167 — Kontrolowane warianty treningu zawartości i ratunku

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: ac724d297448785bdcb98b17dc6a3d5e3fc104e5 oraz zmiany niezacommitowane, data 2026-11-08
Runda: 1
SHA pakietu: f6a6049d53700a1d4992d473433f2a77d6726bdd14f8fd69eb0a9b9c0fc82462
Otwarte P0: 0
Otwarte P1: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Plan, ranking PASS-first, selekcja wyłącznie na A, eksport, inspekcja i pion API są spójne. Nie znalazłem drogi do publikacji ani automatu dla zwycięzcy, który nie zaliczył A. Dwie granice wymaganej ścieżki R3 są jednak wadliwe. Budżet 4800 kroków nie pozwala wznowić pracy po twardej awarii, a bramka startu R3 jest słabsza niż nadzór faktycznie zasilający głowicę. Obie wady dotyczą ścieżki z niezaliczonym A przez R2, czyli właśnie tej, w której R3 jest obowiązkowe.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `F/services/worker/src/game_predictor_worker/training_core/grid_training_admission.py:676` (także `images/grid_training_handler.py:678`, `:857`, `images/grid_training_child.py:154`, `tests/test_grid_content_experiment_workflow.py:302`)
  - **Trigger:** twarda awaria childa lub utrata nadzorcy w planie czterech ramion. Rezerwacja blokami po 200 kroków zostaje naliczona, kroki powtórzone po checkpoincie liczą się ponownie, a plan nie ma zapasu ponad 4800.
  - **Skutek po awarii w środku planu:** przy `reserved>checkpoint` limit `step-start_step>=remaining_steps` przerywa R3 przed 1200 kroków, po zużyciu większości czasu.
  - **Skutek od około kroku globalnego 4500, także przy eksporcie:** `remaining_steps==0`, więc `exhausted`, a `_admit` zwraca `GRID_RUN_BUDGET_EXHAUSTED`. Ukończony trening 4800 kroków nie może dokończyć eksportu, choć nie potrzebuje żadnego kroku optymalizatora. Narusza to AC1 (4800 kroków logicznych) i AC4 (wznowienie).
  - **Brak pokrycia:** fixture sam podstawia `4800 - pointer["step"]`, czyli inną wartość niż `_spec`, a odzysk i eksport po utracie odpowiedzi sprawdzono tylko przy 3600 oraz 1850 krokach.
  - **Poprawka:** dla `CONTENT_LIMIT_POLICY` rozliczać kroki logicznie według trwałej księgi lub checkpointu, a czasu nadal nie odnawiać. Admission ma przepuszczać próbę, gdy pozostała praca logiczna albo sam eksport. Dodać test prawdziwego handlera dla awarii przy 4550 i po 4800 przed eksportem.

- [P1-2] `F/services/worker/src/game_predictor_worker/images/grid_content_experiment_run.py:297` (także `:314`, `:466`, `training_core/grid_visibility_targets.py:51`, `:155`)
  - **Trigger:** `labels_ready` wymaga tylko jednej widocznej komórki w dowolnej grze. Cele i maski głowicy wymagają natomiast `supervision.qualified`, czyli co najmniej 30 komórek i 5 zdjęć obu klas w każdej grze TRAIN (`grid_visibility_contract.py:59-75`).
  - **Skutek:** przy niekwalifikującym się nadzorze R3 startuje i kończy 1200 kroków z zerowymi maskami, bez targetów głowicy, ale ze stanem `complete`. Jeśli wygra, eksport pada dopiero po zużyciu rezerwy. Jeśli wygra inne ramię, puste R3 spełnia warunek „R2 FAIL wymaga ukończonego R3”, bo ekspozycję sprawdza się tylko dla wybranego ramienia. Narusza to AC2, AC6 i D-592:141.
  - **Poprawka:** wyliczać `labels_ready` z `contract.supervision.qualified` i zatwierdzonych widocznych quadów przed preflightem. Przed oznaczeniem R3 jako `complete` wymagać dodatniego `content_head_exposure`. Dodać test zatwierdzonych etykiet poniżej progu.

### P2

- [P2-1] `F/services/api/src/game_predictor_api/storage/grid_content_experiment_evidence.py:65` — `inspect` dekoduje cały TRAIN i ładuje grafy ONNX przy każdym widoku wersji, także na liście (`application/grid_model_registry.py:78`, `:99`). Akceptacja T3 P2-1 tego nie obejmuje. Poprawka: pełny dowód przy instalacji lub publikacji, a w widokach wynik związany z SHA.
- [P2-2] `F/services/worker/src/game_predictor_worker/images/grid_rescue_assessment.py:44` (także `grid_rescue_runtime.py:198`) — ocena i runtime przyjmują bundle do 16 MiB, inspektor do 32 MiB (`storage/grid_content_experiment_evidence.py:19`), a `_export` nie ma limitu. Bundle zawiera bank z detekcjami, więc duży TRAIN przejdzie instalację i padnie dopiero przy ocenie. Poprawka: jeden limit sprawdzany przy eksporcie albo bank poza bundlem, przypięty SHA.
- [P2-3] `F/services/worker/src/game_predictor_worker/training_core/grid_training.py:323` — pomijany jest tylko batch złożony wyłącznie ze skipów. W batchu częściowym szare wycinki zastępcze trafiają w R0 do statystyk BatchNorm. Poprawka: forward statystyk tylko dla ważnych wycinków albo jawna akceptacja ryzyka.

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód |
|---|---|---|
| AC1 | niespełnione | Plan poprawny (`grid_content_experiment.py:66-112`); globalne 4800 wadliwe po awarii, P1-1 |
| AC2 | niespełnione | Preflight i rezerwa `grid_content_experiment_run.py:352-436`; bramka etykiet P1-2 |
| AC3 | spełnione | `grid_content_experiment.py:175-297`, `:479-501`; `grid_training.py:911-919`; filtr A `grid_cohort_dataset.py:507-527` |
| AC4 | niespełnione | Księga i checkpointy poprawne (`grid_training.py:694-716`); granica budżetu P1-1 |
| AC5 | spełnione | `grid_content_experiment_inputs.py:30-117`, `:165-260`; `grid_content_experiment_data.py:59-223`; domknięcie grup `source_recording_sql_v6.py:51-63` |
| AC6 | niespełnione | R0–R2 i pętla głowicy poprawne (`grid_training.py:137-153`, `:269-307`); start R3 P1-2 |
| AC7 | spełnione statycznie | `grid_training_child.py:780-814`; `grid_content_experiment_evidence.py` (domain) `:184-267`; `grid_rescue_runtime.py:206-231`; blokada `grid_model_publication.py:75-77`, `:191-193` |
| AC8 | częściowo niezweryfikowane | Rostery `grid_content_experiment_data.py:80-130`, silnik B/REG `grid_rescue_assessment.py:50-63`; progi oraz 30+30 w `full_board_calibration*` przejrzane tylko zakresowo |
| AC9 | spełnione statycznie | Delta mechaniczna przeczytana w całości; `grid_model_evaluation_handler.py:360-414`, `:515`, `:530`; dowody testów deklaratywne |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P1-2, P2-1, P2-2, P2-3.

## Proponowane testy

- `services/worker/tests/test_grid_content_experiment_workflow.py`: prawdziwe `_recover_previous_attempt`, `_admit` i `_spec` po awarii przy 650, 4550 i po 4800 przed eksportem, bez ręcznego `remainingSteps`.
- Ten sam plik: zatwierdzone etykiety poniżej progu `qualified` oraz gra joint bez etykiet, oczekiwane `CONTENT_EXPERIMENT_R3_LABELS_REQUIRED` przed preflightem.
- `services/worker/tests/test_grid_content_head.py`: odmowa ukończenia R3 przy zerowej ekspozycji głowicy.
- Test bundla między 16 a 32 MiB na granicy eksportu.

Uruchomienie: `.\.venv\Scripts\python.exe -m pytest <plik> -k <nazwa>`.

## Zakres przeglądu i ograniczenia

- **Przeczytane:** inline, grupy E i I, cała delta mechaniczna, D-592, plan T4, AC taska oraz wskazane zakresy w `F/`.
- **Poza `F/`, tylko do odczytu:** niezmienione pomocnicze moduły `grid_cohort_dataset.py`, `grid_correction_split.py`, `grid_correction_history.py`, `neural_grid_operation_qualification.py`, `source_recording_sql_v6.py`, `grid_visibility_contract.py`, `grid_model_publication.py` (domain) oraz `application/grid_model_registry.py`. Zgodność ich kopii z bazą przyjąłem z indeksu, bo nie są na liście zmian.
- **Nieprzeczytane w całości:** calibration runtime, `proposal_runtime`, pełny test PG i dokumenty mechaniczne.
- **Niewykonane:** testy, usługi i trening. Wyniki z pakietu traktuję wyłącznie jako deklaracje wykonawcy. Nie oceniam jakości modelu ani wydajności GPU.