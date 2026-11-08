# TASK-1164 — rzeczywisty audyt CLI, nieprawidłowy format raportu

To zapis koordynatora, nie zastępczy werdykt audytora. CLI zakończyło się
kodem 0 i pojedynczym udanym wynikiem; główny model `claude-opus-5-5`,
effort żądany `high`, sesja `cefc303a-4131-4b53-951a-7d3d8b1d0aee`.
Pakiet: `83cf0368c38d69b18224b29a17722a80c95054917e6ed0a6ef37bf4abbdc5cb1`.
Runda merytoryczna 1, drugie zgłoszenie po timeout bez werdyktu.

Walidator odrzucił raport: `Open findings list contradicts explicit counters.`
Audytor użył identyfikatorów F-01–F-05 zamiast wymaganych P1-/P2-.
Nie opublikowano poprawnie zweryfikowanego raportu ani PASS. Ograniczony ogon
strumienia nie zawiera nagłówka raportu, więc nie rekonstruujemy go z pamięci.
Poniżej zachowano dosłownie dostępny fragment odpowiedzi audytora, od sekcji
znalezisk. Receipt transportu zapisano obok. Cały surowy ogon pozostaje
w lokalnym `artifacts/audits/requests/`.

Dwa P1 oraz trzy P2 przekazano wykonawcy do jednej rundy poprawek.
Następny przegląd będzie skupioną rundą 2 z tym fragmentem i deltą poprawek;
nie będzie ponowieniem pełnego audytu bez zmian.

---

## Znaleziska

### P0

Brak.

### P1

**F-01 — `inputCropped` pozostaje niezweryfikowanym claimem workera**
- Miejsce: `services/api/src/game_predictor_api/domain/full_board_assessment_reference.py:118` (pin w `from_sources`, L80–91), `domain/input_edge_clearance.py:60`.
- Skutek: `require_plan` porównuje tylko parę hash+rewizja, a `FrozenAssessmentReferences.content_references` przechowuje wyłącznie tę parę. Wartość `inputCropped`, która decyduje o minimum 5/3 i o rankingu progu, pochodzi z utrwalonych `selectionReferences`. Sidecar z poprawnym, jawnym pinem i odwróconym `inputCropped` przechodzi rekalkulację API. Narusza to D-589 („sam claim workera nie jest dowodem”) i obchodzi kontrolę ryzyka „samozatwierdzenie inputEdge”. Test `test_api_requires_trusted_a_content_hash_and_revision_not_worker_claim` zmienia tylko hash i rewizję.
- Poprawka: zamrozić w targecie A wartość cięcia wynikającą z referencji (albo wyprowadzać ją z zawartości objętej hashem), porównywać w `require_plan` trójkę hash/rewizja/`inputCropped` i dodać test odwróconego `inputCropped` przy poprawnym pinie.

**F-02 — Kalibracja A liczy clearance względem pełnego rastra, a runtime względem `valid_box`**
- Miejsce: `services/worker/src/game_predictor_worker/images/full_board_calibration_observations.py:133` (brak `available_source_support`), porównanie: `full_board_runtime_evidence.py:102`, `grid_training_data.py:221`.
- Skutek: `domain/canonical_source.py:58` określa, że tylko piksele w `valid_box` pochodzą z oryginału. Runtime przekazuje ten box, a trening uwzględnia go w `source_support`. Observer dostaje jedynie `rgb`, więc na klatkach z `frame.crop` padding liczy się jako realne wejście. Próg A powstaje wtedy na innej mierze niż ta porównywana w `acceptance_reasons`: krawędź ucięta przez `valid_box` może mieć w kalibracji clearance dodatni, a w runtime ujemny. Narusza to definicję D-589 („przecięcie cropa i realnego wsparcia źródła”). `test_real_input_edge_uses_raw_nodes_and_available_pixels` i test runtime nie obejmują observera.
- Poprawka: przekazać atestowany box przez `CorrectionControlPhoto`/observer do `input_edge_clearance`, fail-closed przy nieznanym zasięgu. Ponieważ `features` używa tego argumentu także dla `COMPLETENESS_PIXELS_MISSING`, ścieżkę należy ograniczyć do kontraktu v2, aby nie zmienić semantyki v1. Dodać test równości wartości kalibracji i runtime na klatce z paddingiem.

### P2

**F-03 — Drugi odczyt klatki w `source_support`**
- Miejsce: `services/worker/src/game_predictor_worker/images/grid_training_data.py:220`, wywołanie per plansza L280.
- Skutek: `frame()` czyta plik ponownie, a jednoelementowy cache `_frame_cache` nie ma blokady przy `data_workers=6`. Wyścig istniał już dla `rgb`, ale drugi odczyt zwiększa koszt i może w rzadkim przeplocie użyć `valid_box` innego zdjęcia.
- Poprawka: pobierać `rgb` i box z jednego obiektu klatki albo dodać blokadę.

**F-04 — Bundle v2 przy specyfikacji bez kontraktu**
- Miejsce: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:868`, `domain/grid_visibility_contract.py:150`.
- Skutek: `expected=None` przy formacie v2 przechodzi bez porównania ze specyfikacją, więc legacy spec z bundle v2 nie jest odrzucany. Ryzyko ograniczają sumy SHA własnego runu.
- Poprawka: dla bundle v2 wymagać obecności `gridOutputContract` w specyfikacji.

**F-05 — Brak testu ekspozycji przy pominiętym kroku skalera**
- Miejsce: `services/worker/tests/test_grid_visibility_contract.py:103`, logika `training_core/grid_training.py:625`.
- Skutek: warunek `get_scale() >= scale_before` chroni „udane kroki”, ale na CPU skaler jest wyłączony i test obejmuje tylko sukces. Logika czyta się poprawnie, lecz ta gałąź nie ma dowodu testowego.
- Poprawka: dodać test z atrapą skalera wykonującego back-off, oczekując braku przyrostu ekspozycji.

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód |
| --- | --- | --- |
| Rzeczywisty BoardExport/runtime 24/15 | Spełnione statycznie | `inference.py` L245–295, `onnx_engine`, test L331–379 |
| Cele visible/occluded/out_of_frame/unknown i maski po augmentacji | Spełnione | `grid_visibility_targets.py`, `_occlusion`/`_hand` aktualizują `content_support` |
| Loss nie uczy węzłów nieosiągalnych/padded; brak celów jawny | Spełnione | `_supervised_losses`, `node_support_weights`, testy L191–230 |
| Niedobór 30+30/5 zdjęć blokuje oś/automat, nie geometrię | Spełnione | `require_visibility_contract`, `content_targets`, `features` |
| Ekspozycja obu klas przed wybranym `bestStep` | Spełnione; test częściowy (F-05) | `train`, `_result`, `require_output_contract` |
| `inputEdgeClearance` v2, ≥5 ucięć/3 zdjęcia, brak danych bez automatu | Niespełnione w części | Logika progu poprawna; F-01, F-02 |
| B/REG nie stroją progu, menu ≤256 | Spełnione | `make_plan`, observer tylko dla `VALIDATION-A` |
| Historyczne v1 zachowują semantykę | Spełnione statycznie | Dyspozycja po wersji, `exclude_if`, test L233–260 |
| Pion API/OpenAPI/SDK | Spełnione | `openapi.json` L615, L908; `types.gen.ts` L363, L532; test żądania |
| Dokumentacja/decyzja | Spełnione | D-589 L18–69 |
| Testy, lint, typy, ONNX | Niezweryfikowane niezależnie | Wyłącznie deklaracja wykonawcy |

## Listy zamknięte i otwarte

Zamknięte: Brak.
Otwarte: F-01, F-02, F-03, F-04, F-05

## Proponowane testy

1. `require_plan` odrzuca odwrócone `inputCropped` przy poprawnym hashu i rewizji.
2. Klatka A z `frame.crop` daje clearance równy wartości runtime dla tego samego `valid_box`.
3. Legacy v1 na klatce z `frame.crop` zachowuje dotychczasowe `hardReasons` i SHA.
4. Back-off skalera nie zwiększa `visibilityExposure`.
5. Bundle v2 przy specyfikacji bez `gridOutputContract` jest odrzucany.
6. `source_support` przy wielu wątkach zwraca box właściwego zdjęcia.

## Zakres przeglądu i ograniczenia

Przeczytałem rdzeń z pakietu oraz ze snapshotu:
- `_train`, augmentację, handler (`_spec`, `_verify_*`, `_descriptor`),
- observer, runtime evidence, `FullBoardCalibrationRun`,
- pin, evidence, registry, raport,
- D-589 i testy `test_grid_visibility_contract.py` L56–305,
- test forged hash/rewizja oraz test runtime L112–206.

Niezmieniony kontekst (`grid_cohort_dataset.py`, `preprocessing.py`, `rescue.py`, `canonical_source.py`, `grid_reinference_handler.py`) sprawdziłem w bieżącym drzewie, bo nie należy do snapshotu.

Niezweryfikowane lub nieprzeczytane linia po linii:
- `test_full_board_completeness.py`,
- `test_grid_visibility_calibration.py` L37–180,
- `test_full_board_calibration_integration.py` poza L112–206,
- `test_grid_visibility_contract.py` L307–328,
- `_verify_recovered`,
- `src/index.ts` L1740–1745 oraz pełne zakresy OpenAPI i typów (sprawdzone tylko wyszukiwaniem literałów v2),
- wejście A przez handler ewaluacji (ustalone z sygnatury observera i odczytu B w `prepare_b`),
- minimalna wersja Pydantic wymagana przez `exclude_if`.

Z dokumentów procesu przeczytałem tylko początek `AGENTS.md` (L1–120), bez pełnej kolejności lektury, zgodnie z ograniczeniem do pakietu. SHA plików snapshotu nie sprawdzałem niezależnie, a wyników testów wykonawcy nie potwierdzałem.
