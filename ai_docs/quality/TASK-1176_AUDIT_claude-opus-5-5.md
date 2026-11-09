# Audyt TASK-1176 — Istniejące siatki do weryfikacji symboli

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...94c5bc6d7520c55a90375620fb6f279593e73100 oraz zmiany niezacommitowane, data 2026-11-09
Runda: 2
SHA pakietu: 9f8e4077a74741d8e92097d3703622539bccff6db6b7d1d3140c894773d7df66
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

W tej rundzie sprawdziłem poprawki po R1: wyznaczanie polityki z pinu w `prepare()`, odrzucanie par review z pinem innym niż v4, zachowanie ścieżki kalibrowanej v3/v4 w workerze oraz nowe testy. P0-1 jest usunięte. `prepare()` przypisuje politykę przez `acceptance_for_operation_pin`, a stała `ACCEPTANCE_POLICY` znów wskazuje v4. Niezgodna para review i v3 jest odrzucana w trzech warstwach: w domenie, w recheck storage i w pierwszym guardzie zapisu. Zakwalifikowany pin v3 nadal przekazuje `calibration_pin` i zapisuje `calibrationPin` w checkpoincie. P1-1 jest zamknięte przez nowy test reinferencji z pinem v3, test niezgodnej pary i udokumentowany baseline istniejących zestawów PG. Wyników testów nie weryfikowałem, bo ich nie uruchamiałem. Zostają dwa obronne ryzyka P2.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-5] `services/api/src/game_predictor_api/domain/neural_grid_operation_pin.py:134-137` oraz `149-155`. Jedyne miejsce, które pilnuje, że pin v4 oznacza niezakwalifikowany automat, to warunek `for_symbol_review=automatic["state"] != "qualified"` w `storage/neural_grid_operation_qualification.py:116`.
  - Ani `make_operation_pin`, ani `require_operation_pin` nie odrzucają pinu v4 z `automaticQualification.state == "qualified"`.
  - Taki pin dostałby od `acceptance_for_operation_pin` politykę review i ominąłby bramki kalibracji, mimo że kalibracja istnieje.
  - Dziś produkcja nie wywołuje tego połączenia, więc ryzyko jest obronne.
  - Propozycja: w `require_operation_pin` dla `is_review` wymagać `automaticQualification == {"state": "unqualified", "reasonCodes": [CALIBRATION_REQUIRED]}` i dodać test jednostkowy. Można też jawnie przyjąć to ryzyko.
- [P2-6] `services/api/tests/integration/test_grid_reinference_postgres.py:968-969`. Asercja porównuje politykę zapisaną w rewizji z `before["acceptancePolicy"]`, czyli z wartością z tej samej operacji, a nie z jawnie oczekiwaną polityką.
  - Po zmianie większość scenariuszy tego modułu przechodzi przez pin v4 i ścieżkę review. Wskazuje na to atrapa w liniach 257 i 362.
  - Gdyby polityka została źle wyznaczona w `prepare()`, ten test nadal by przeszedł.
  - Propozycja: dodać jawne `== "v3-symbol-review-v1"` dla scenariuszy z niezakwalifikowanym pinem. Można też zaakceptować ryzyko, bo ścieżkę kalibrowaną pokrywa osobny test w `test_symbol_review_routing_postgres.py:319`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Niekwalifikowany automat może dostarczyć pending symbole, nie human GT | spełnione (statycznie) | `neural_grid_operation_qualification.py:116`, `v3_engine_acceptance.py:84-88`, `grid_reinference_handler.py:965-1011`, `virtual_grid_geometry_repository.py:344` (`status="needs_review"`), `virtual_grid_geometry.py:1419-1431` (predykcja tylko dla deferred, model z importu), asercje `test_symbol_review_routing_postgres.py:75` i `144` |
| Stare piny i bramki automatu pozostają zgodne | spełnione (statycznie) | `application/grid_reinference.py:16` (v4), `storage/grid_reinference.py:273-318`, `v3_engine_acceptance.py:50-58` i `139-148`, `grid_reinference_handler.py:558-560`, `634-638`, `678-692`, `virtual_grid_geometry_repository.py:183-193` i `233`, `job_repository.py:140-145`; test `test_symbol_review_routing_postgres.py:319` |
| Zła topologia/pochodzenie/piksele nie przechodzą | spełnione (statycznie) | `neural_grid_operation_qualification.py:134-142`, `neural_grid_operation_pin.py:42-46` (None daje UNCHECKED), `neural_crop_policy.py:84-139` (zwalniany tylko FIT_OUTLIERS), `v3_engine_acceptance.py:165-247`, `virtual_grid_geometry_repository.py:213-264`; testy `test_symbol_review_routing.py:97`, `103`, `143`, `150`, `171`, `194` |
| Testy zmienionego pionu i Opus PASS przed commitem | niezweryfikowane (testy), audyt R2: PASS | Wyniki 117/3/163 oraz 21 PASS i 2 zastane FAIL to deklaracje w `TASK-1176_VERIFICATION.md`. Testów nie uruchamiałem |
| Rzeczywista partia i nowe importy potwierdzone przed deklaracją gotowości | niezweryfikowane | Task jawnie odkłada to na etap po odbiorze kodu (Outcome, sekcja „Pozostaje wdrożenie” w `TASK-1176_VERIFICATION.md`). Gotowości nie zadeklarowano |

## Listy zamknięte i otwarte

Zamknięte: P0-1 (`storage/grid_reinference.py:273`, `application/grid_reinference.py:16`, guardy `neural_grid_operation_pin.py:279-284`, `neural_grid_operation_qualification.py:137-142`, `v3_engine_acceptance.py:139-143`, `virtual_grid_geometry_repository.py:183-193`), P1-1 (`test_symbol_review_routing_postgres.py:319`, `test_symbol_review_routing.py:119`, atrapa `test_grid_reinference_postgres.py:257`/`362`, baseline w `TASK-1176_VERIFICATION.md`), P2-1 (`neural_grid_operation_pin.py:44-45`, test `test_symbol_review_routing.py:143`), P2-2 (jedna instancja predyktora `grid_reinference_handler.py:98-100`/`945`; predykcja w transakcji odczytu jako jawnie przyjęte ryzyko do pomiaru w pilocie), P2-3 (`CURRENT_STATE.md:91-93`, skrócona historia w `TASK-1176_VERIFICATION.md`), P2-4 (`test_symbol_review_routing.py:150`, `171`).

Otwarte: P2-5, P2-6.

## Proponowane testy

- Test jednostkowy w `services/api/tests/test_symbol_review_routing.py`: `require_operation_pin` dla pinu v4 z `automaticQualification.state == "qualified"` powinno zgłosić `NeuralOperationPinError` (po poprawce P2-5). Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_symbol_review_routing.py`.
- W `services/api/tests/integration/test_grid_reinference_postgres.py` dodać jawną asercję `acceptancePolicy == "v3-symbol-review-v1"` dla scenariuszy z niezakwalifikowanym pinem. Uruchomienie z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`.
- Rozszerzyć `test_qualified_reinference_keeps_calibration_pin_and_result_gates` o rzeczywisty zapis przez `save_automatic_reinference_source` z polityką v4, tak aby `calibrated_result_blockers` zadziałały także w repozytorium (`virtual_grid_geometry_repository.py:233`).

## Zakres przeglądu i ograniczenia

Przeczytałem cały pakiet: task, plan, diff, nowe pliki, raport R1 z receipt, odpowiedź na audyt i raport weryfikacji. Przeczytałem też powiązany kod:

- w całości: `neural_grid_operation_pin.py` i `storage/neural_grid_operation_qualification.py`;
- fragmenty `v3_engine_acceptance.py` (wyznaczanie polityk, `qualify_v3_engine_acceptance`) i `neural_crop_policy.py` (blokery, `full_neural_prediction_geometry`);
- `storage/grid_reinference.py` (`prepare`, `worker_record`) i `job_repository.find_neural_operation_pin`;
- `virtual_grid_geometry_repository.save_automatic_reinference_source` (początek do zapisu rewizji);
- `grid_reinference_handler.py` (pętla źródeł, `recognize`, `automatic_blockers`, `render`, `neural_provenance`);
- `neural_pending_geometry.py`, `application/jobs.py` (kolejność przypinania polityk);
- `application/virtual_grid_geometry.py` (`_predict_pending_slot`, `bind_manual_crop_policy`, metadane) i konstruktor `ManualBoardCellSymbolPredictor`.

Nie uruchamiałem testów, lintów, typechecka ani poleceń. Liczby PASS/FAIL, baseline na `main` i artefakty `artifacts/*.log` przyjmuję jako deklaracje wykonawcy. Zmianę fixture `deferred_stats` na historyczną politykę v1 oceniłem na podstawie opisu baseline, bez uruchomienia. Nie oceniałem jakości klasyfikatora, rzeczywistych danych operatora, wdrożenia ani pełnej zgodności wygenerowanego klienta TS poza tokenami z diffu.