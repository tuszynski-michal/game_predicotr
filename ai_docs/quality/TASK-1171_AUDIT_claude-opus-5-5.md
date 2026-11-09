# Audyt TASK-1171 — Porównanie produkcyjnych wycinków 8% i 0%

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...23055b1e0cfbc7c325b5a0d4f18f370d9f9ae1ac oraz zmiany niezacommitowane, data 2026-11-09
Runda: 2
SHA pakietu: 3a0be39256e817d77693cdb4ec11511c0a2354948c27da285164475998e5f2a1
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono poprawki wszystkich ośmiu znalezisk z rundy 1 na rzeczywistych kontraktach kodu: kontrakcie pipeline'u, autorze kandydata, resolverze snapshotu, repozytorium przeglądu symboli i obserwatorze produkcyjnym. Wszystkie znaleziska P0 i P1 są usunięte, a ścieżka do stanu `candidate` jest osiągalna przez rzeczywistego producenta. Nowe uwagi mają rangę P2 i dotyczą głównie sytuacji, w których narzędzie zachowuje się zachowawczo i raportuje brak dowodu. Główne ryzyko to dopuszczanie aktorów na podstawie listy zakazanych prefiksów oraz niejednoznaczne indeksy predykcji, istotne dla konsumenta w T4. Wyniki jakościowe na danych operatora pozostają `not_evaluable`, co task jawnie deklaruje.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-5] `services/worker/src/game_predictor_worker/images/production_crop_classification.py:94` — Rzeczywisty artefakt LAB zawiera wyłącznie `{"temperature": 1.05}` (`services/api/src/game_predictor_api/domain/lab_symbol_candidate.py:124`), więc nie ma klucza `version` i nie przechodzi warunku `schemaVersion`. Polityka LAB jest zawsze `unavailable`, także przy znanej granicy manualnej. `absolute_reference` zawsze dodaje wtedy `CLASS_ACCEPTANCE_POLICY_UNAVAILABLE` (`production_crop_comparison.py:137`), więc stan `reference` jest nieosiągalny niezależnie od danych. Test LAB (`services/worker/tests/test_production_crop_comparison.py:252`) sprawdza tylko `purpose`, a nie stan. Liczniki zawartości i klasyfikacji pozostają w raporcie, a LAB nie wpływa na rekomendację, dlatego skutek jest ograniczony. Propozycja: rozpoznać zweryfikowany manifest LAB i zwrócić `disabled` przy przypiętej granicy manualnej albo zapisać w dokumentacji, że LAB zawsze kończy się `not_evaluable`.

- [P2-6] `services/worker/src/game_predictor_worker/images/production_crop_classification.py:169` — Aktor jest filtrowany listą zakazanych prefiksów `system` i `worker`, a zapytanie w `services/api/src/game_predictor_api/storage/production_crop_capture.py:238` porównuje tylko tekst aktora z `resolved_by`. W kodzie istnieją aktorzy maszynowi spoza tych prefiksów, np. `m6-acceptance-runner` (`scripts/accept_m6_classifier_vertical_slice.py:490`) i `benchmark:local-admin` (`services/worker/src/game_predictor_worker/images/operations_benchmark.py:418`). Gdyby takie ścieżki działały na bazie operatora, ich decyzje planszy zostałyby uznane za ludzkie GT, co osłabia zasadę D-595, że tekst aktora nie jest samodzielnym dowodem. Propozycja: lista dozwolonych aktorów ludzkich albo jawne wykluczenie znanych aktorów maszynowych, z testem regresji.

- [P2-7] `services/worker/src/game_predictor_worker/images/production_crop_classification.py:163` — Zdarzenie `board_synchronized` jest uznawane tylko przy `assignment_source == "board_decision"`. Ludzka decyzja planszy zachowuje jednak źródło `human`, gdy komórka była już zatwierdzona tym samym symbolem (`services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:3001-3003`). Jeśli rewizja komórki wzrośnie, np. przez zmianę sekwencji albo właściciela, starsze zdarzenie `approve` odpada przez filtr `e.cell_revision=c.revision`, a nowe nie jest akceptowane. Skutek to zachowawcze `CLASS_HUMAN_APPROVAL_UNAVAILABLE` dla rzeczywiście zatwierdzonej klasy. Propozycja: uwzględnić ten przypadek przy zachowaniu wymogu aktualnej ludzkiej decyzji planszy albo zaakceptować ryzyko i zapisać je w dokumentacji.

- [P2-8] `services/api/src/game_predictor_api/storage/production_crop_capture.py:294` — Dla TRAIN `u` pochodzi z globalnego `_measurement(session, game)` (przypisanie w `:310`), które wymaga dokładnie jednego kwalifikowanego zamrożonego raportu w grze (`:151`). Poprawka R1 związała z właściwą sesją tylko A. Drugi poprawny raport trwale ustawi TRAIN na `CONTENT_UNCERTAINTY_MISSING`, choć brak dowodu będzie wtedy skutkiem wyboru reguły, a nie braku pomiaru. Stan jest jawny i bezpieczny. Propozycja: określić deterministyczny wybór pomiaru dla TRAIN albo opisać to ograniczenie w D-595.

- [P2-9] `services/worker/src/game_predictor_worker/images/production_crop_comparison.py:270` — `rasters[].predictionIndex` i `matchedPrediction` indeksują detekcje z węzłami, natomiast `modelPredictions[].predictionIndex` (`:462`) i wpisy świadka wejścia (`production_crop_inputs.py:75`) indeksują pełną listę `found`. Detekcja może mieć `nodes=None` (`services/worker/src/game_predictor_worker/geometry_core/inference.py:146`), a `predictions` je pomija (`training_core/grid_evaluation.py:48`). Klasyfikacja i rastry wewnątrz porównania są spójne, ale konsument T4 łączący te pola po nazwie może przypisać raster do niewłaściwej planszy. Propozycja: zapisać oba indeksy pod odrębnymi nazwami przed rozpoczęciem T4.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Każdy punkt T2 ma implementację lub jawny warunek zależny od danych | spełnione | `production_crop_capture.py:164`, `production_crop_classification.py:28`, `production_crop_comparison.py:81-85` |
| Rzeczywisty renderer | spełnione | `production_cell_evaluation.py:66-132`, `:278-303` |
| Najpierw geometria człowieka, potem model | spełnione | `production_crop_comparison.py`, `found_by_kind` w `run_comparison` |
| Te same instancje i zmiana wyłącznie marginesu 0.08/0.0 | spełnione | `production_crop_comparison.py`, `configurations` w `_pair`; regresja w `test_production_crop_comparison.py` |
| LAB RGB jako osobny kontrakt | spełnione, z uwagą P2-5 | `production_crop_comparison.py:552`, `:579`; test `:252` |
| Bez etykiet wynik unavailable | spełnione | `production_crop_comparison.py`, `paired_gate`; `production_crop_classification.py:162-169` |
| Bramka per gra bez kompensacji | spełnione | `production_crop_comparison.py:76-85`; testy `:744`, `:753`, `:761`, `:827` |
| Zachowanie historycznych kontraktów i ręcznych korekt | spełnione w analizie statycznej | `production_cell_evaluation.py:183-204`, `:257-259`; capture wymaga transakcji READ ONLY |
| Właściwe testy, lint, typy i docs/map | niezweryfikowane | Wyniki w `ai_docs/quality/TASK-1171_VERIFICATION.md` są deklaracją wykonawcy i nie zostały tu powtórzone |
| Niezależny audyt Opus i receipt | spełnione w części audytu; receipt niezweryfikowany | Niniejszy raport rundy 2; receipt powstaje poza zakresem audytora |

## Listy zamknięte i otwarte

Zamknięte: P0-1, P1-1, P1-2, P1-3, P2-1, P2-2, P2-3, P2-4

Dowody zamknięcia:

- P0-1: `_policy` dostarcza przypięty runtime i `runtimeAutoAccept` (`production_crop_capture.py:164`), a konsument waliduje koperty i zakres (`production_crop_classification.py:28`). Regresja przechodzi przez prawdziwego producenta (`test_production_crop_comparison.py:808`, `:859`).
- P1-1: obsłużono formaty M6 v1/v2 i `candidate_gate` (`production_crop_classification.py:73-94`). Pola zgadzają się z autorem i resolverem: temperatura i `inputSize` (`symbol_model_snapshot_resolver.py:164-165`), `symbol-candidate-manifest-v1` (`candidate_gate.py:42`).
- P1-2: `board_synchronized` wymaga aktualnej ludzkiej decyzji planszy (`production_crop_classification.py:162-164`, `production_crop_capture.py:238-249`). Testy: `test_production_crop_comparison.py:792` oraz `test_production_crop_capture_postgres.py:52`.
- P1-3: każdy licznik szkody ma parametryzowany test (`test_production_crop_comparison.py:744`), a przejęcie sąsiada przez rzeczywisty renderer ma regresję (`:761`).
- P2-1: poprawa liczy `clipped + missing`, a nowa instancja `missing` blokuje rekomendację (`production_crop_comparison.py:76-81`; testy `:753`, `:827`).
- P2-2: brak świadka ekranu daje `partial` z powodem (`production_crop_inputs.py:103-108`, `:133`, `:142`; test `:515`).
- P2-3: granica wewnętrznego JSON A jest jawna (`production_crop_comparison.py:580-581`), a ryzyko zapisano w D-595 i `ai_docs/requirements/VISION_LAB.md`.
- P2-4: LAB ma osobne podsumowanie `labGames` per gra, rola i geometria (`production_crop_comparison.py:552`, `:579`; test `:280`).

Otwarte: P2-5, P2-6, P2-7, P2-8, P2-9.

## Proponowane testy

- `services/worker/tests/test_production_crop_comparison.py`: test `_policy` i `acceptance_policy` na manifeście LAB w formacie rzeczywistego autora, z oczekiwanym stanem zgodnym z rozstrzygnięciem P2-5. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_production_crop_comparison.py -k lab`.
- Ten sam plik: `human_class` dla zdarzeń z aktorami `m6-acceptance-runner` i `benchmark:local-admin` oraz dla zachowanego `assignment_source=human` po podbiciu rewizji.
- Ten sam plik: scenariusz, w którym pierwsza detekcja ma `nodes=None`, ze sprawdzeniem powiązania `rasters`, `modelPredictions` i `neuralInput`.
- `services/api/tests/integration/test_production_crop_capture_postgres.py`: pełny `capture` dla zdjęcia A na dedykowanej bazie testowej oraz scenariusz dwóch kwalifikowanych raportów przy zdjęciu TRAIN, uruchamiany z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`.

## Zakres przeglądu i ograniczenia

Przeczytano zamrożony pakiet, `AGENTS.md` oraz fragmenty obserwatora i podsumowań produkcyjnych, kontraktu pipeline'u, resolvera snapshotów, autora kandydata, kontraktu LAB, repozytorium przeglądu symboli, pinów treści, silników rescue i raportu kalibracji M6. Użyto wyłącznie narzędzi odczytu. Nie uruchamiano testów, lintu, typowania, CLI, bazy ani usług, więc wyniki z raportów wykonawcy pozostają jego deklaracją.

Pełna ścieżka A oraz ścieżka LAB nie mają dowodu na danych operatora, a test PostgreSQL obejmuje czytniki, nie kompletny `capture` dla A. Gałąź polityki `available` z progiem jest dziś praktycznie nieosiągalna, ponieważ walidator kontraktu oczekuje `autoAcceptEnabled=False` (`services/worker/src/game_predictor_worker/images/pipeline_contract.py:698-699`), więc błędne akceptacje są liczone wyłącznie jako fakt konfiguracji. Polecenie `test:geometry` dla Admina, wymienione w sekcji Verification taska, zgodnie z raportem nie zostało uruchomione, a pakiet nie zmienia kodu Admina. Status gita wskazuje zmodyfikowany plik `ai_docs/tasks/1173-crop-preview-acceptance.md`, który nie należy do pakietu i nie był oceniany; przed commitem trzeba rozstrzygnąć jego przynależność.