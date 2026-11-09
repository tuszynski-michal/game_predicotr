# Audyt TASK-1176 — Istniejące siatki do weryfikacji symboli

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...94c5bc6d7520c55a90375620fb6f279593e73100 oraz zmiany niezacommitowane, data 2026-11-09
Runda: 1
SHA pakietu: 4004b2b8a5f8c5b6e02204d120e9df8c67629c9ea217b84e7f18a2c2cb70ae17
Otwarte P0: 1
Otwarte P1: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przejrzałem nowy pin v4, politykę `v3-symbol-review-v1` i `neural-symbol-review-v1`, ponowne sprawdzenie pinu w storage, zapis automatyczny reinferencji, workera `neural_pending_geometry` oraz testy z pakietu. Na ścieżce nowego importu zmiana działa spójnie. Pin v4 powstaje tylko przy niekwalifikowanym automacie. Polityka wynika deterministycznie z pinu, a kontrole topologii, wiązania, sekwencji i pikseli zostają. Wynikiem nadal są pending symbole bez pól zatwierdzenia człowieka. Główny błąd dotyczy reinferencji: każda nowa operacja dostaje bezwarunkowo politykę review, także wtedy, gdy przygotowany pin jest skalibrowanym v3 z zakwalifikowanym automatem. Wtedy pomijane są bramki kalibracji v4 i profil kalibracji w inferencji. Ten scenariusz nie ma testu, a dotychczasowe zestawy PostgreSQL reinferencji nie występują w zapisie weryfikacji.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/application/grid_reinference.py:16` (w powiązaniu z `services/api/src/game_predictor_api/storage/grid_reinference.py:262-295` i `services/api/src/game_predictor_api/storage/neural_grid_operation_qualification.py:116`). `ACCEPTANCE_POLICY` zmieniono globalnie z `v3-engine-acceptance-v4` na `v3-symbol-review-v1`. `prepare()` zapisuje tę stałą w każdej nowej operacji niezależnie od pinu. Gdy model ma zakwalifikowaną ocenę gry i kalibrację automatu, `prepare_operation_pin` zwraca pin v3, a operacja i tak dostaje politykę review. W tym połączeniu:
  - `operation_pin_blockers(..., for_symbol_review=True)` zwraca `()` dla dowolnej wersji pinu (`neural_grid_operation_pin.py:278-279`);
  - `recheck_operation_pin` kończy się przed sprawdzeniem nieaktualności dowodów (`neural_grid_operation_qualification.py:137-138`);
  - `qualify_v3_engine_acceptance` nie ma kontroli zgodności pinu i polityki dla review, ma ją tylko dla v4 (`v3_engine_acceptance.py:139-143`);
  - worker przekazuje `calibration_pin=None` do inferencji, więc nie stosuje przypiętego profilu ani rastra kalibracji (`grid_reinference_handler.py:554-556`);
  - worker pomija `calibrated_result_blockers` (`grid_reinference_handler.py:674-677`, `1044-1047`);
  - repozytorium sprawdza bramkę kalibracji tylko dla `v3-engine-acceptance-v4` (`virtual_grid_geometry_repository.py:233`).

  Skutek: dla skalibrowanego automatu nowa reinferencja zapisuje automatyczną geometrię, którą v4 by odrzuciła. `frozen_recognition_status` nadal pokazuje automat jako `qualified`. To narusza kryterium „Stare piny i bramki automatu pozostają zgodne” i zakaz „obniżania bramek akceptacji automatu” z sekcji Scope. Poprawka:
  - w `prepare()` wyznaczać politykę z pinu przez istniejące `acceptance_for_operation_pin(operation_pin)` (v4 → review, v3 → v4) i zapisywać ją w payloadzie, dokumencie i sygnaturze zamiast stałej;
  - w `qualify_v3_engine_acceptance` i `save_automatic_reinference_source` odrzucać `v3-symbol-review-v1` z pinem innym niż `neural-grid-operation-pin-v4` (analogicznie do `NEURAL_GRID_OPERATION_POLICY_MISMATCH`);
  - dodać test opisany w P1-1.

### P1

- [P1-1] `services/api/tests/integration/test_symbol_review_routing_postgres.py:122-125` oraz `ai_docs/quality/TASK-1176_VERIFICATION.md:52-61`. Zmiana domyślnej polityki reinferencji wpływa na zestawy, które importują `ACCEPTANCE_POLICY` i od niego zależą: `services/api/tests/integration/test_grid_reinference_postgres.py:909-931` oraz `services/api/tests/integration/test_grid_geometry_proposals_postgres.py:445-550`. Zapis weryfikacji podaje tylko „2 testy PostgreSQL PASS”, czyli dwa nowe testy, bez przebiegu tych zestawów i bez dowodu, że ich porażki są zastane. Atrapa `recognize` w `test_grid_reinference_postgres.py:235-246` nie przyjmuje `operation_pin` i ustawia `executionPolicy` tylko dla `neural-auto-crop-v2` (linie 321-322), więc nowy domyślny stan tego zestawu jest niewiadomy. Brakuje też testu reinferencji z zakwalifikowanym pinem v3, który pokazałby, że gałąź v4 i bramki kalibracji pozostają (scenariusz P0-1). Skutek: kryterium „Testy zmienionego pionu … PASS przed commitem” nie jest wykazane dla zmienionej ścieżki reinferencji. Poprawka:
  - dodać test jednostkowy lub PostgreSQL: reinferencja z pinem v3 zachowuje `v3-engine-acceptance-v4`, `calibrationPin` i `calibrated_result_blockers`, a niezgodna para v3 i review jest odrzucana;
  - uruchomić oba zestawy, dostosować atrapy do bieżącej sygnatury lub udokumentować baseline na `main`;
  - zapisać wyniki w `TASK-1176_VERIFICATION.md`.

### P2

- [P2-1] `services/api/src/game_predictor_api/domain/neural_grid_operation_pin.py:38-45` oraz `services/api/src/game_predictor_api/domain/v3_engine_acceptance.py:153-159` i `services/worker/src/game_predictor_worker/images/neural_pending_geometry.py:142-148`. Dla polityki review `qualification_blockers=None` daje `()`, a kod `NEURAL_GRID_GAME_EVALUATION_UNCHECKED` jest jawnie zwolniony. Kontrola topologii reguł jest wykonywana wyłącznie w `recheck_operation_pin`. Jeśli przyszły wywołujący pominie recheck, zła topologia przejdzie po cichu. Obecni wywołujący recheck wykonują (`production_workflow.py:733-744`, `v3_engine_acceptance_repository.py:104-114`, `virtual_grid_geometry_repository.py:183-193`), więc to ryzyko obronne. Propozycja: nie zwalniać `UNCHECKED` i traktować `None` jako blokadę także dla review.
- [P2-2] `services/worker/src/game_predictor_worker/images/grid_reinference_handler.py:934-946` i `1003-1011`. `ManualBoardCellSymbolPredictor` powstaje przy każdym wywołaniu `render`, czyli dla każdego źródła, więc jego cache modelu jest tracony. Klasyfikacja (`predict=True`) biegnie wewnątrz otwartej transakcji `session.begin()`. Przy 691 zdjęciach i 6219 planszach oznacza to wielokrotne ładowanie ONNX i długie transakcje odczytu. Propozycja: jedna instancja predyktora na handler i ewentualnie przeniesienie predykcji poza transakcję. Można też przyjąć ryzyko po pomiarze na pilocie.
- [P2-3] `ai_docs/process/CURRENT_STATE.md:93` oraz `ai_docs/quality/TASK-1176_VERIFICATION.md:19-37`. `CURRENT_STATE` podaje „testy61+44 PASS … Trwa odbiór PG/API”. Raport weryfikacji zachowuje sekcje „Nie wykonano jeszcze: PostgreSQL…” i „Zatrzymanie na limicie operatora”, sprzeczne z późniejszą sekcją „Odbiór po wznowieniu” i z Outcome taska (110 PASS, 2 PG PASS). Propozycja: zaktualizować wpis `CURRENT_STATE` i oznaczyć wcześniejsze sekcje jako historyczne albo je skrócić.
- [P2-4] `services/api/tests/test_symbol_review_routing.py:119-126`. Wariant `pixels` zmienia tylko `width`, więc wywołuje `V3_ACCEPTANCE_SOURCE_OR_MODEL_DRIFT`, a nie kontrolę fizycznej widoczności (`NEURAL_GRID_PIXELS_UNAVAILABLE`, `neural_crop_policy.py:125-136`). Brakuje też testu `recheck_operation_pin(..., for_symbol_review=True)` z regułami o złej topologii lub obcej grze. Propozycja: dodać detekcję z węzłami poza kadrem lub `cellVisibility` innym niż `full` oraz test recheck z regułami 4×5 lub innym `game_id`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Niekwalifikowany automat może dostarczyć pending symbole, nie human GT | spełnione (statycznie dla importu i reinferencji z pinem v4) | `neural_grid_operation_qualification.py:116`, `v3_engine_acceptance.py:84-88`, `grid_reinference_handler.py:967-1011`, `virtual_grid_geometry_repository.py:341-344` (`status="needs_review"`), asercje `test_symbol_review_routing_postgres.py:69-75`, `199-207`; testów nie uruchamiano |
| Stare piny i bramki automatu pozostają zgodne | niespełnione | Ścieżka importu jest zgodna (`v3_engine_acceptance.py:50-58`, `job_repository.py:140-145`), ale reinferencja wymusza review dla pinu v3: `application/grid_reinference.py:16`, `storage/grid_reinference.py:282`, `grid_reinference_handler.py:554-556` (P0-1) |
| Zła topologia/pochodzenie/piksele nie przechodzą | spełnione z zastrzeżeniem P2-1 | `neural_grid_operation_qualification.py:129-136`, `neural_crop_policy.py:84-138`, `v3_engine_acceptance.py:160-214`, `virtual_grid_geometry_repository.py:213-264`, `grid_reinference_handler.py:602-619` |
| Testy zmienionego pionu i Opus PASS przed commitem | niespełnione | Ten audyt: REVISE. Brak dowodu dla zestawów reinferencji PG i scenariusza pinu v3 (P1-1) |
| Rzeczywista partia i nowe importy potwierdzone przed deklaracją gotowości | niezweryfikowane | Task jawnie odkłada to na etap po odbiorze kodu (`ai_docs/tasks/1176-symbol-review-routing.md`, Outcome). Gotowości nie zadeklarowano |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1, P1-1, P2-1, P2-2, P2-3, P2-4.

## Proponowane testy

- Test jednostkowy w `services/api/tests/test_symbol_review_routing.py`: `qualify_v3_engine_acceptance(policy="v3-symbol-review-v1", operation_pin=<pin v3>)` zwraca `NEURAL_GRID_OPERATION_POLICY_MISMATCH`. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_symbol_review_routing.py`.
- Test reinferencji, w którym `prepare_operation_pin` zwraca zakwalifikowany pin v3, a zapisana operacja ma `acceptancePolicy == "v3-engine-acceptance-v4"`, checkpoint zawiera `calibrationPin` i działają `calibrated_result_blockers`. Plik: `services/api/tests/integration/test_symbol_review_routing_postgres.py` lub `test_grid_reinference_postgres.py`, uruchomienie z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`.
- Przebieg `services/api/tests/integration/test_grid_reinference_postgres.py` i `test_grid_geometry_proposals_postgres.py` na tym branchu i na `main` jako baseline. Wyniki do zapisania w `TASK-1176_VERIFICATION.md`.
- Test `recheck_operation_pin(..., for_symbol_review=True)` z regułami 4×5 lub obcej gry, oczekujący `NEURAL_GRID_TOPOLOGY_UNSUPPORTED`. Plik: `services/api/tests/test_neural_grid_operation_qualification.py`.
- Wariant fizycznych pikseli dla polityki review: węzły poza kadrem lub `cellVisibility` z `partial` daje `NEURAL_GRID_PIXELS_UNAVAILABLE` w `neural_auto_crop_blockers` i w zapisie repozytorium.

## Zakres przeglądu i ograniczenia

Przeczytałem pełny pakiet: task, plan, diff, nowe pliki i dokumentację. Przeczytałem też powiązany kod:
- `neural_grid_operation_pin.py`, `v3_engine_acceptance.py`, `neural_crop_policy.py` i `neural_grid_operation_qualification.py` w całości;
- fragmenty `storage/grid_reinference.py` (prepare i walidacja `worker_record`), `job_repository.find_neural_operation_pin`, `v3_engine_acceptance_repository.py`, `virtual_grid_geometry_repository.save_automatic_reinference_source`, `application/virtual_grid_geometry.py` (`_predict_pending_slot` i `bind_manual_crop_policy`), `application/jobs.py` (kolejność przypinania polityk), `production_workflow.py`, `neural_pending_geometry.py`, `grid_reinference_handler.py` (recognize, raw_inference, render, neural_provenance), `image_geometry_completeness_state_repository.withheld_review_item_ids` i `grid_recognition_status.frozen_recognition_status`;
- fragmenty istniejących testów PG reinferencji.

Żadnych testów, lintów, typecheck ani poleceń nie uruchamiałem. Wyniki 110, 2, 163 i 44+2 oraz artefakty `artifacts/*.log` i `batch-preview.json` przyjmuję wyłącznie jako deklaracje wykonawcy. Nie oceniałem jakości klasyfikatora, rzeczywistych danych operatora ani wdrożenia. Wygenerowanego klienta TS porównałem z OpenAPI tylko w zakresie tokenów z diffu.