# Audyt TASK-1171 — Porównanie produkcyjnych wycinków 8% i 0%

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...23055b1e0cfbc7c325b5a0d4f18f370d9f9ae1ac oraz zmiany niezacommitowane, data 2026-11-09
Runda: 1
SHA pakietu: b18b4e919a887ce02e7109ba9536242009fa7c29a7c11e28a466bb00ad5e2846
Otwarte P0: 1
Otwarte P1: 3

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano zamrożony pakiet oraz kontrakty, od których zależy nowy pion: renderer, obserwator produkcyjny, zdarzenia przeglądu symboli, raporty kalibracji i piny A. Część geometryczna jest spójna: tylko margines różni 0.08 od 0.0, domyślne zachowanie obserwatora pozostało bez zmian, a ochrona ról działa przed odczytem pikseli. Głównym problemem jest ścieżka polityki akceptacji: rzeczywisty producent nigdy nie dostarcza pola wymaganego przez bramkę, więc rekomendacja `candidate` jest nieosiągalna niezależnie od danych. Dodatkowo klasy z ludzkiej decyzji planszy są pomijane wbrew D-595, a gałąź bramki blokująca uszkodzenia zawartości nie ma testu.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/storage/production_crop_capture.py:179` — `_policy` zwraca wyłącznie `{"artifact": pin, "report": report}`, natomiast `services/worker/src/game_predictor_worker/images/production_crop_classification.py:28` wymaga logicznego pola `runtimeAutoAccept`. Pole występuje tylko w tej walidacji i w testach (`services/worker/tests/test_production_crop_comparison.py:93`), gdzie jest wstrzykiwane ręcznie. W rzeczywistym przebiegu każda polityka ma więc stan `unavailable`, także `disabled`, a `paired_gate` zawsze dodaje `CLASS_ACCEPTANCE_POLICY_UNAVAILABLE` (`services/worker/src/game_predictor_worker/images/production_crop_comparison.py:42-43`). Skutek: stan `candidate` i pomiar błędnych akceptacji są nieosiągalne nawet przy komplecie danych. To brak implementacji, a nie „jawny warunek zależny od danych”, więc kryterium pierwsze jest niespełnione. Jest to też sprzeczne z notatką taska, że polityka pochodzi z przypiętego raportu kalibracji. Poprawka: capture powinien przypinać rzeczywiste ustawienie runtime, np. `policies.reviewBoundary.autoAcceptEnabled` z kontraktu pipeline'u (`services/worker/src/game_predictor_worker/images/pipeline_contract.py:1087-1088`), albo inne trwałe źródło. Regresja musi przechodzić przez `_policy`, bez ręcznie złożonego słownika.

### P1

- [P1-1] `services/worker/src/game_predictor_worker/images/production_crop_classification.py:29-30` — Walidacja przyjmuje tylko `schemaVersion=1` i `calibrationVersion="symbol-temperature-calibration-v1"`. Bieżąca stała to `symbol-temperature-calibration-v2-safe-floor-v1` (`services/worker/src/game_predictor_worker/images/symbol_confidence.py:14`) i używają jej obecni autorzy raportów (`scripts/calibrate_m6_symbol_confidence.py:495`, `scripts/release_m6_spatial_symbol_model.py:511`). Bramka kandydata treningowego zapisuje wersję pod kluczem `version` (`services/worker/src/game_predictor_worker/symbols/candidate_gate.py:347`), a `_policy` czyta właśnie artefakt `calibration` z manifestu iteracji. Zatwierdzony raport v1 (`ai_docs/quality/m6-symbol-confidence-calibration-report.json:2`) dotyczy modelu bootstrap, a dla snapshotu bez `iteration_id` `_policy` zwraca `None`. Skutek: po samej naprawie P0-1 progi z bieżących artefaktów nadal byłyby odrzucane, a fikstura v1 (`services/worker/tests/test_production_crop_comparison.py:96`) ukrywa rozjazd. Poprawka: jawnie obsłużyć rzeczywiste formaty raportów z zachowaniem wiązania z modelem i dodać test na formacie faktycznego autora.

- [P1-2] `services/api/src/game_predictor_api/storage/production_crop_capture.py:211` oraz `services/worker/src/game_predictor_worker/images/production_crop_classification.py:93` — Kod uznaje tylko zdarzenia `approve` i `reassign`, a D-595 wymaga „zdarzenia approve/reassign/decyzji planszy” (`ai_docs/process/decisions/DECISION_LOG_2026.md:56`). Ludzka decyzja planszy zapisuje `event_action = "board_synchronized"` i `assignment_source=board_decision` (`services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:2998-3032`) z aktorem `resolution.resolved_by` (`services/api/src/game_predictor_api/storage/image_review_repository.py:1158-1161`). Skutek: klasy zatwierdzone całą planszą trwale dostają `CLASS_HUMAN_APPROVAL_UNAVAILABLE`, więc luka implementacyjna wygląda jak brak danych. Poprawka: przyjąć `board_synchronized` wyłącznie dla bieżącej rewizji komórki z `assignment_source=board_decision`, stanem `approved`, ludzkim aktorem i pełną zgodnością tożsamości cropu albo zmienić decyzję i dokumentację w trybie jawnym.

- [P1-3] `services/worker/tests/test_production_crop_comparison.py:630` — Sekcja `Test cases` wymaga m.in. scenariusza sąsiada i braku pikseli, a plan w tabeli odbioru wiąże z T2 „Brak przejęcia sąsiada/przycięcia”. Gałąź `damage` w `paired_gate` (`services/worker/src/game_predictor_worker/images/production_crop_comparison.py:44-53`) jest wywoływana w testach tego pionu tylko z licznikami zerowymi lub bez pokrycia niezerowych wartości, a test braku kompensacji sprawdza wyłącznie klasy i politykę. Istniejące testy domenowe wykrywają obcy symbol, lecz nie dowodzą, że bramka T2 blokuje rekomendację przy mniejszej liczbie przycięć. `TASK-1171_VERIFICATION.md` nie doprecyzowuje też testów specyficznych dla tych scenariuszy, czego wymaga task. Skutek: usunięcie lub błąd warunku bezkompensacyjnego przeszedłby niezauważony. Poprawka: dodać parametryzowany test każdego licznika uszkodzeń oraz przynajmniej jeden test obserwatora, w którym 0.0 przejmuje sąsiada na tej samej instancji.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/images/production_crop_comparison.py:61` — Poprawa porównuje tylko licznik `clipped`, a `summarize_content` traktuje `clipped` i `missing` jako tę samą rangę uszkodzenia (`services/worker/src/game_predictor_worker/images/production_cell_run.py:254`). Przejście `clipped` w `missing` zmniejsza licznik przycięć i nie jest degradacją, więc może zostać policzone jako poprawa, gdy instancja nie ma klasyfikacyjnego pogorszenia. Propozycja: porównywać sumę `clipped + missing` albo blokować każdy wzrost `missing`.

- [P2-2] `services/worker/src/game_predictor_worker/images/production_crop_inputs.py:95` — Wynik `record("screen", ...)` jest ignorowany, a stan świadka zależy wyłącznie od listy plansz (`production_crop_inputs.py:121`). Brak zgodności tensora ekranu daje więc `available` bez wpisu ekranu. Propozycja: wymagać świadka bazowego wejścia ekranu, a dla ścieżek rescue oznaczać brak jako `partial`.

- [P2-3] `services/worker/src/game_predictor_worker/images/production_crop_comparison.py:403` oraz `production_crop_comparison.py:277` — Dla A raport JSON nadal zawiera węzły modelu, `screenQuad`, footprinty obserwacji i kody klas (`:239`), a `capture.json` także pełne adnotacje. Test `test_a_never_exports_png_or_render_hints` sprawdza tylko brak PNG i klucza `path`, podczas gdy dokumenty deklarują, że A nie eksportuje wskazówek. Propozycja: zredagować te pola dla A albo zawęzić deklarację do eksportu wizualnego i zapisać akceptację ryzyka.

- [P2-4] `services/worker/src/game_predictor_worker/images/production_crop_comparison.py:452` — Agregacja per gra i rola obejmuje tylko wariant legacy, więc LAB RGB ma wynik wyłącznie na poziomie zdjęcia. Obie konfiguracje LAB są identyczne (`:173-177`), dlatego bramka LAB z definicji nie może wskazać poprawy. Propozycja: dodać osobne podsumowanie LAB per gra i rola, z jawnym stanem referencyjnym zamiast semantyki `no_improvement`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Każdy punkt T2 ma implementację lub jawny warunek zależny od danych | niespełnione | `production_crop_capture.py:179`, `production_crop_classification.py:28` (P0-1) |
| Rzeczywisty renderer | spełnione | `production_cell_evaluation.py:278-303`, `render_cells` w `production_cell_evaluation.py:66-132` |
| Najpierw geometria człowieka, potem model | spełnione | `production_crop_comparison.py:397-403` |
| Te same instancje i zmiana wyłącznie marginesu 0.08/0.0 | spełnione | `production_crop_comparison.py:169-171` |
| LAB RGB jako osobny kontrakt | spełnione, z uwagą P2-4 | `production_crop_comparison.py:173-177`, `:272`; `lab_symbol_candidate.py:100-106` |
| Bez etykiet wynik unavailable | spełnione dla braku danych; luka dla decyzji planszy w P1-2 | `production_crop_comparison.py:39-40`, `production_crop_capture.py:211` |
| Bramka per gra bez kompensacji | niespełnione w ścieżce rzeczywistej: rekomendacja nieosiągalna | `production_crop_comparison.py:42-53`, `:61`; P0-1, P1-3 |
| Zachowanie historycznych kontraktów i ręcznych korekt | spełnione w analizie statycznej | `production_cell_evaluation.py:183-204`, `:257-259`; capture wymaga transakcji READ ONLY |
| Właściwe testy, lint, typy i docs/map | niezweryfikowane; brakuje też testu z P1-3 | Wyniki w `TASK-1171_VERIFICATION.md` są deklaracją wykonawcy i nie zostały tu powtórzone |
| Niezależny audyt Opus i receipt | niespełnione na tym etapie | Niniejszy raport ma werdykt REVISE; receipt nie jest częścią pakietu |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1, P1-1, P1-2, P1-3, P2-1, P2-2, P2-3, P2-4.

## Proponowane testy

- `services/worker/tests/test_production_crop_comparison.py`: test `_policy` i `acceptance_policy` na dokumentach o rzeczywistym formacie autorów, z pinem runtime dającym stany `disabled` i `available`. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_production_crop_comparison.py -k policy`.
- Ten sam plik: parametryzowany test `paired_gate` dla `degradedInstances`, `newWrongCells`, `newTies`, `newForeignSymbols` i `newMatchAmbiguities` przy mniejszej liczbie `clipped`, z oczekiwanym stanem `regression`.
- Ten sam plik: test przejścia `clipped` w `missing`, który nie może dać `fewerClipped=true`.
- Ten sam plik: test obserwatora z 0.0 przejmującym sąsiedni symbol na tej samej instancji.
- Ten sam plik: `human_class` dla zdarzenia `board_synchronized` z ludzkim aktorem i dla takiego samego zdarzenia systemowego lub po ponownym otwarciu planszy.
- Test integracyjny PostgreSQL ścieżki A, `_classes` i zapytań zdarzeń, uruchamiany z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`, wyłącznie na dedykowanej bazie testowej.

## Zakres przeglądu i ograniczenia

Przeczytano zamrożony pakiet, `AGENTS.md`, sekcję T2 i kryteria wspólne planu oraz fragmenty obserwatora, podsumowań, wejść produkcyjnych, pinów treści, modeli zdarzeń, repozytorium przeglądu symboli, polityki pewności, autorów raportów kalibracji i kontraktu LAB. Audyt wykonano wyłącznie narzędziami odczytu; nie uruchamiano testów, lintu, typowania, CLI, bazy ani usług, więc wyniki z raportu weryfikacji pozostają deklaracją wykonawcy.

Według raportu weryfikacji pilot objął jedno zdjęcie TRAIN bez `contentGT` i bez bieżących klas GT, dlatego dodatnia ścieżka `human_class`, porównanie zatwierdzonych pikseli oraz ścieżki A i LAB nie mają dowodu na danych operatora. Status gita wskazuje też zmodyfikowany plik `ai_docs/tasks/1173-crop-preview-acceptance.md`, którego nie ma w pakiecie i którego ten audyt nie ocenia; przy commicie trzeba rozstrzygnąć jego przynależność.