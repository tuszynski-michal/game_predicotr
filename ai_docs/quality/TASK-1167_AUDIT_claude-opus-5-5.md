# Audyt TASK-1167 — Kontrolowane warianty treningu zawartości i ratunku

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: ac724d297448785bdcb98b17dc6a3d5e3fc104e5 oraz zmiany niezacommitowane, data 2026-11-09
Runda: 2
SHA pakietu: 03ae9457bbcbc30dd376c2f571b18768726020eb82bf1d5f09c2e3ca4424e6c5
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem poprawki R1 oraz całe połączenie AC8: obserwator workera, plan przed B, pieczęć B, REG, raport, replay API, pin operacji, dowód runtime i akceptację końcową. Obie uwagi P1 z R1 są usunięte. Nie znalazłem drogi, w której wariant WIDE dziedziczy próg BASE, a brak wiązania lub referencji kończy się automatem. Główne ryzyko jest poza kodem: dane operatora mogą nie dać 30+30 na wariant, a rozstrzygający test zimnej ścieżki nie działa w domyślnej bramce (P2-6).

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `F/services/api/src/game_predictor_api/storage/grid_content_experiment_evidence.py:25` — pozostaje otwarte jako zaakceptowane ryzyko. Widok i lista rejestru odtwarzają fizyczny TRAIN i ONNX, a latencji nie zmierzono. Cache samego SHA ominąłby aktualność plików. Poprawka należy do przyszłego właściciela widoku rejestru.
- [P2-4] `F/services/worker/src/game_predictor_worker/images/production_cell_input.py:47` — `manifest_input_context` sprawdza `stat`, a potem wykonuje niezwiązane `read_bytes()`. Bundle rosnący między tymi krokami alokuje pamięć ponad 16 MiB, choć SHA nadal chroni wynik. Poprawka: użyć `read_content_bundle_bytes`.
- [P2-5] `F/services/worker/src/game_predictor_worker/images/full_board_variant_context.py:126` — `resolve_final_stage` nie sprawdza, czy detekcja jest obiektem zastępczym dla tej pozycji. Jeśli wiązanie końcowe zamieni sloty p (podmieniony) i q (bazowy), runtime oznaczy bazową detekcję jako WIDE. Kalibracja jest chroniona dopasowaniem do GT, a sam przypadek jest fizycznie mało prawdopodobny. Poprawka: porównać z `result.detections[binding[position]]`.
- [P2-6] `F/services/worker/tests/test_full_board_variant_pipeline.py:438` — zimny replay, pin, runtime i finalizer, w tym przypadek BASE/WIDE o identycznych węzłach, działają tylko przy ustawionym `GAME_PREDICTOR_VARIANT_CASE`. Bez tej zmiennej test jest pomijany. Regresja stempla nie zostanie więc wykryta w `quality`. Poprawka: dodać do testów domenowych przypadek `COMPLETENESS_INPUT_VARIANT_CHANGED`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód |
|---|---|---|
| AC1 | spełnione statycznie | Budżet logiczny `grid_training_admission.py:516-534`; czas nadal naliczany `grid_training_handler.py:851`; test 650/4550/4800 `test_grid_content_recovery_guards.py:27-138` |
| AC2 | spełnione statycznie | Bramka `grid_content_experiment_run.py:314-320`, `:340`; preflight `:387-461` |
| AC3 | spełnione (R1, bez zmiany granicy) | REG poza strojeniem: `full_board_variant_calibration.py:238-305` |
| AC4 | spełnione statycznie | `_recover_previous_attempt`, `_adopt_pointer`, `_settle_steps` `grid_training_handler.py:260-323`, `:679-699`, `:797-804`; `ChildControl` bez kroku 4801, test `:133` |
| AC5 | spełnione (R1, bez zmiany granicy) | Podzbiór banku nie zmienił się w tej rundzie |
| AC6 | spełnione statycznie | Ekspozycja głowicy `grid_content_experiment_run.py:219-228`, `:329-335`, `:483-484`; test `test_grid_content_r3_readiness.py:107-146` |
| AC7 | spełnione statycznie | Jedna trasa combined `grid_content_experiment_data.py:27-56`; budżet 1+1 `grid_rescue_runtime.py:267-345` |
| AC8 | spełnione statycznie | Rozpisane poniżej |
| AC9 | spełnione statycznie; wyniki testów deklaratywne | Delta mechaniczna przeczytana w całości; test PG `test_full_board_input_variant_postgres.py:65-169`; testy nie były uruchamiane |

**Dowody AC8:**

1. **Kontekst i świadek.** Klucz nie zależy od zdjęcia (`full_board_variant_context.py:21-56`). Świadek jest osobny (`:64-127`). Metadane podmiany pochodzą z faktycznej zamiany (`grid_rescue_strategy.py:184-192`). Nieudany recrop daje BASE (`full_board_variant_context.py:124-126`; test `test_full_board_variant_pipeline.py:397-427`). Raster i support API odtwarza z pikseli (`production_cell_input.py:244-279`), bez ORT. Preset D.json ma dokładnie pola `ScreenPreset` i `BoardPreset`, więc konteksty z bundla i silnika są zgodne.
2. **Wariant dozwolony i użyty.** `_contexts:45-63` daje NONE→BASE i combined→BASE+WIDE. Used jest sumą kluczy A/B/REG (`full_board_variant_calibration.py:255-265`). Null blokuje całą grę (`:287`). Kompletność rosteru pilnują `:190`, `:253`, `require_targets` oraz `require_variant_plan_scope:119-125`.
3. **Menu z A i minima.** Menu pochodzą tylko z A i są trwałe przed B (`full_board_variant_calibration_run.py:178-200`). Partycje po wariancie są rozłączne. Minimum 30+30 liczone jest osobno na child (`full_board_calibration.py:293-302`, `:328-332`). Test 15+15 potwierdza brak agregacji. Brak A daje `[None]` i powód braku referencji (`:196-198`, `:389-396`), bez progu zastępczego.
4. **Wersje i osie N/A.** Child pozostaje v2, envelope jest v3, limity to 256 i 512 (`full_board_calibration.py:103`; `full_board_variant_calibration_types.py:119`). Legacy 256 na grę jest zachowane (`full_board_calibration_report.py:176-180`). Reguła N/A wymaga pustego zbioru zastosowań w A i B (`full_board_variant_calibration.py:219-235`); zastosowanie w REG blokuje (`full_board_calibration.py:429-438`).
5. **Profil, pin i stempel.** Parent v3 wiąże dokładne child v2 (`full_board_variant_calibration_types.py:147-172`). Pin v3 ma politykę v3 (`neural_grid_operation_pin.py:259-265`). Stempel powstaje przed propozycją (`full_board_runtime_evidence.py:129-141`; `neural_page_geometry_preflight.py:628-649`) i jest objęty jej sumą kontrolną (`test_full_board_input_variant.py:108-111`). API sprawdza zgodność i odtwarza support (`full_board_input_variant.py:58-121`, `calibrated_neural_evidence.py:63-85`). Nieznany lub niespójny wariant oznacza ręczną akceptację. Aktualne pochodzenie źródła sprawdza `current_variant_source_box`, a obaj rzeczywiści wołający mają `artifact_root` (`pipeline_store.py:802`, `grid_reinference_handler.py:287`).
6. **Odczyt v6 i częściowe A.** Wariant v3 czytany jest wyłącznie przez jawny dispatch v6 (`full_board_calibration_report.py:192-194`; `full_board_variant_calibration_evidence.py:28-48`; wszyscy czytelnicy: `grid_model_evaluation.py:629-636`, `grid_model_publication.py:109-130`, `neural_grid_operation_qualification.py:198-208`). Raport v5 pozostaje ścisły. Częściowe A ma jedną centralną granicę (`grid_cohort_dataset.py:514-527`); TRAIN i B bez zmian (test `test_grid_content_partial_selection.py:123-137`).

Dowody pozytywne korzystają z prawdziwych pikseli i kontrolowanych detekcji, a nie z danych operatora. Nie potwierdzają 30+30 ani jakości modelu, co zgodnie z zakresem nie jest tu wymagane.

## Listy zamknięte i otwarte

Zamknięte: P1-1, P1-2, P2-2, P2-3

Otwarte: P2-1, P2-4, P2-5, P2-6.

Przyczyny zamknięcia:

- **P1-1:** kroki logiczne rozliczane są według potwierdzonego checkpointu, czas pozostaje naliczony, a przy 4800 admission dopuszcza sam eksport.
- **P1-2:** R3 wymaga `supervision.qualified` dla każdej gry TRAIN oraz dodatniej ekspozycji głowicy do bestStep przed `complete`. Komórka `visible` ma obowiązkowy quad (`grid_visibility_contract.py:31`), a licznik obejmuje tylko etykiety zatwierdzone.
- **P2-2:** wspólny limit 16 MiB z ograniczonym odczytem działa przy zapisie, eksporcie, instalacji i w ścieżkach odczytu bundla v2; pozostałą lukę opisuje P2-4.
- **P2-3:** pominięte wiersze są filtrowane przed `BoardNetwork` (`grid_training.py:343-370`). Test porównuje bufory BatchNorm i gradienty (`test_grid_content_mixed_batch.py:107-117`).

## Proponowane testy

- `services/api/tests/test_full_board_input_variant.py`: BASE/WIDE o identycznych węzłach, oczekiwane `COMPLETENESS_INPUT_VARIANT_CHANGED`, bez zmiennej środowiskowej.
- `services/worker/tests/test_full_board_variant_pipeline.py`: zamiana slotów p i q po podmianie, oczekiwany brak klasyfikacji WIDE dla bazowej detekcji.
- `services/worker/tests/test_grid_content_bundle_limits.py`: wzrost bundla po `stat` w `manifest_input_context`.

Uruchomienie: `.\.venv\Scripts\python.exe -m pytest <plik> -k <nazwa>`.

## Zakres przeglądu i ograniczenia

- **Przeczytane:** cała delta mechaniczna, D-592, plan T4, szablon, raport R1, wszystkie nowe moduły v3 w całości, wskazane funkcje AC8, funkcje poprawek P1 i P2 oraz testy na tych granicach wraz z asercjami.
- **Poza `F/`, tylko do odczytu:** niezmienione pliki `settings.py`, `D.json`, `grid_visibility_contract.py`, wywołanie w `pipeline_store.py` oraz okablowanie repozytorium w `main.py`. Zgodność z pakietem przyjąłem na podstawie indeksu.
- **Nieprzeczytane w całości:** duże klasy poza wskazanymi metodami, generowany SDK poza deltą oraz pełny plik delty źródeł (`TASK-1167_R2_SOURCE_DELTA.diff`), który przeszukałem punktowo.
- **Niewykonane:** testy, usługi, trening, ONNX i PostgreSQL. Wyniki z pakietu traktuję wyłącznie jako deklaracje wykonawcy. Nie oceniam jakości modelu, wydajności GPU ani dostępności danych operatora.