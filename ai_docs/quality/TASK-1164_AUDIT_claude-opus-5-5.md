# Audyt TASK-1164 — focused R2

Werdykt: PASS
Audytor: claude-opus-5-5/high
Wykonawca: gpt-6-astra/high
Zakres: pięć poprawek po R1 (P1-1, P1-2, P2-1, P2-2, P2-3) oraz naruszone callery, na podstawie frozen R2 i delty R2
Runda: 2
SHA pakietu: a1aa5801254230672337bf7589ea867deca441059b1ca340b2418a54d668b1b2
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Wszystkie pięć poprawek jest obecnych w kodzie i statycznie poprawnych, a callery są podłączone. Dotyczy to obu ścieżek A/REG i B, granic spec→bundle oraz współdzielonego cache klatek.

Pozostały ograniczenia świadomie przeniesione na T2/T3 w D-589: domyślny observer emituje wyłącznie `geometry_proxy`, który nie kwalifikuje progu. Nie są to braki tej rundy. Nie znalazłem regresji semantyki v1 ani nowych ścieżek fail-open.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| ID / kryterium | Status | Dowód zamknięcia |
| --- | --- | --- |
| P1-1 — pin `inputCropped` | Zamknięte | `full_board_assessment_reference.py:85-96` zapisuje trójkę i wymaga `type(...) is bool`. `:128-133` porównuje całą trójkę; brak pina daje `None` i odrzucenie. Cały target wchodzi też do hasha referencji A przez `digest(target)`. Proxy nie omija kontroli, bo `input_edge_clearance.py:51-59` liczy tylko `verified_content`. Test: `test_grid_visibility_calibration.py:248-255`, odwrócony boolean przy poprawnym pinie. |
| P1-2 — ta sama miara w kalibracji i runtime | Zamknięte | `grid_cohort_dataset.py:437-445` bierze RGB i box z jednej klatki, a `grid_correction_metrics.py:190-194` przenosi box przez `measure_role`. Podłączone są `grid_model_evaluation_handler.py:283-284,297` (A/REG) i `full_board_calibration_run.py:215-228` (B z purpose B). Observer stosuje box tylko dla v2 (`full_board_calibration_observations.py:62-68`) i waliduje go tak jak `full_board_runtime_evidence.py:45-50`. Brak wsparcia daje `None` i `COMPLETENESS_PIXEL_SUPPORT_REQUIRED` (`full_board_completeness.py:261-266`). Runtime dla `crop is None` podaje pełny raster (`grid_reinference_handler.py:551-555`), czyli tak samo jak `frame_rgb_and_box`. Test `test_full_board_calibration_integration.py:275-287` obejmuje równość pełnych features z runtime, fail-closed oraz niezmienność features/SHA v1. |
| P2-1 — wyścig cache i podwójny odczyt | Zamknięte | Blokada obejmuje guard, odczyt, dekodowanie i zwrot (`grid_cohort_dataset.py:360-366`). `_frame` nie jest wywoływane poza `frame`, nie ma re-entry, a snapshot nie przechodzi przez pickle ani deepcopy. `photo_pixels_and_support` działa raz na zdjęcie przed pętlą plansz (`grid_training_data.py:262-267,352-356`). Tablica `rgb` jest tylko do odczytu (`canonical_source.py:133`), więc zwrócona klatka jest bezpieczna poza blokadą. Test: `test_grid_visibility_contract.py:205-269`. |
| P2-2 — bundle v2 bez kontraktu w spec | Zamknięte | `grid_visibility_contract.py:160-161`, wywołania `grid_training_handler.py:868` i `grid_training_child.py:643`. Odzysk eksportu przechwytuje `ValueError` i pomija kandydata albo zgłasza `GRID_TRAINING_EXPORT_CORRUPT` (`grid_training_handler.py:578-583`). `_verify_export` przepuszcza błąd fail-closed, tak jak dotychczasowe naruszenia tego kontraktu. Runtime bez spec pozostaje legalny (`inference.py:322`, `full_board_runtime_evidence.py:64`). W bieżącym drzewie nie ma innych wywołań kontraktu spec→bundle. |
| P2-3 — back-off skalera | Zamknięte | Atrapa działa, bo `GradScaler` jest importowany z patchowanego modułu w czasie wywołania (`grid_training.py:519`). Skala jest pobierana przed `step`, a przyrost ekspozycji ma warunek `>=` (`:622-635`). Test `test_grid_visibility_contract.py:145-202` sprawdza zerową ekspozycję i niezmienione parametry; usunięcie warunku zmieniłoby wynik. |
| Historyczne v1 | Spełnione statycznie | Nowa gałąź `features` leży wewnątrz `output_contract is not None`, a observer buduje `available` tylko przy kontrakcie. Ścieżki v1 w batcherach zachowują `photos.rgb`. |
| Granica neutralnego rdzenia | Spełnione statycznie | `training_core/grid_correction_metrics.py` dostaje tylko typ wywoływalny; adapter `frame_rgb_and_box` pozostaje w `images/`. |
| Istniejący callerzy `CorrectionControlPhoto` | Spełnione statycznie | Nowe pola mają wartości domyślne, a `load_with_support` jest opcjonalny. Konstrukcje pozycyjne pozostają zgodne (np. `test_grid_correction_metrics.py:116`). |
| Testy, lint, typy | Niezweryfikowane niezależnie | Wyłącznie deklaracja wykonawcy w `TASK-1164_VERIFICATION.md:134-137`. |

## Listy zamknięte i otwarte

Zamknięte: P1-1, P1-2, P2-1, P2-2, P2-3
Otwarte: Brak.

## Proponowane testy

Żaden z tych testów nie blokuje rundy.

1. Pin z `contentReferenceInputCropped` równym `1` albo `"true"` nie trafia do `content_references`, więc `verified_content` jest odrzucany.
2. Test przez rzeczywiste `_photos` i `prepare_b` z klatką o `frame.crop`. Obecny test integracyjny podstawia loader atrapą.
3. Box równy całemu rastrowi przy planszy dochodzącej do krawędzi kadru. Wielokąt źródła i box pokrywają się wtedy dokładnie w `cv2.intersectConvexConvex`. Wynik powinien być liczbą równą w kalibracji i runtime; ewentualne `None` działa fail-closed, ale ograniczałoby dane.
4. W T3: etykieta `contentReferenceInputCropped` na klatce z paddingiem uwzględnia `valid_box`. `gt_cropped` nie zna tego boxa, co jest bezpieczne tylko dlatego, że proxy nie zasila progu.

## Zakres przeglądu i ograniczenia

Przeczytałem:

- całą deltę R2 i doprecyzowanie D-589,
- frozen `input_edge_clearance.py`, `full_board_runtime_evidence.py`, `full_board_calibration_run.py` (L43–329),
- wskazane zakresy `full_board_completeness.py`, `grid_training.py` (L515–724), `grid_training_handler.py` i `grid_training_data.py`,
- fragment weryfikacji wykonawcy oraz zakresy inline z pakietu.

Z bieżącego drzewa, poza pakietem, sprawdziłem wyłącznie kontekst:

- `grid_reinference_handler.py:540-561`,
- `canonical_source.py:50-139`,
- wyszukiwania callerów,
- fixture `test_grid_cohort_dataset.py`.

Ograniczenia:

- nie uruchamiałem testów, lintu ani typowania;
- nie weryfikowałem niezależnie 38 hashy manifestu, bo narzędzia tylko do odczytu tego nie umożliwiają;
- nie ponawiałem pełnej R1, w tym ONNX, SDK/OpenAPI i niezmienionych części augmentacji;
- integracja T2 i adapter T3 są poza pakietem, dlatego faktyczna kwalifikacja progu `inputEdgeClearance` pozostaje niedowiedziona do czasu T3, zgodnie z D-589.