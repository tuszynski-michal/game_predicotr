# Audyt TASK-1178 — Gotowość korekt i zalecany cel uczenia

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: 0e1a02ec916629508570ee6570ded38d4df92817...0e1a02ec916629508570ee6570ded38d4df92817 (brak zmian zacommitowanych) oraz zmiany niezacommitowane, data 2026-11-10
Runda: 1
SHA pakietu: 6d14d842d178af771639b8888f23e8b1f11213d3e4fdc26cb42b06f5f15b0f78
Otwarte P0: 0
Otwarte P1: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadałem trzy rzeczy. Pierwsza to rozdzielenie historycznego zakresu publikacji (`verified_publication_scope`) od sprawdzania aktualności ponownie używanych kohort. Druga to opcjonalny dobór celu w GET ready, razem z kontraktem OpenAPI, SDK, wrapperem i testem żądania. Trzecia to panel Admina z ręcznym wyborem celu i wyjaśnionymi blokadami startu.

Przyczyna blokady jest trafnie rozpoznana. Globalny guard `GRID_LEARNING_HISTORY_STALE` w `verified_history` blokował każdą nową iterację po zmianie dowolnej dawnej etykiety. Naprawa nie osłabia barier publikacji, aktywacji i domyślnego modelu. Ponowne użycie konkretnej kohorty nadal sprawdza jej bieżącą kwalifikację, a na ścieżkach screen/v4 i przy tworzeniu runu także dowód aktualności.

Główny brak: żaden test nie sprawdza, jak `_preview` wylicza `partialTrainingPhotos` i `detectorReadiness` w trybie grid-only. Od tych pól zależy rekomendacja. Testy rekomendacji podstawiają gotowe wartości przez mock.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/src/game_predictor_api/application/grid_correction_learning.py:379` — Liczenie `detector_sources`, `partialTrainingPhotos` i zastępczego `detectorReadiness` dla grid-only (linie 379–395) jest nowym źródłem danych dla rekomendacji (linie 103–118). Spełnienie kryterium „Zalecany tryb wynika z danych” zależy właśnie od tego kodu.
  - `services/api/tests/test_grid_learning_recommendation.py:14` wpisuje `partialTrainingPhotos` i `detectorReadiness` bezpośrednio do zamockowanego `preview`.
  - `services/api/tests/test_grid_correction_workflow.py:453` wykonuje prawdziwe `_preview` na dziesięciu częściowych zdjęciach TRAIN, ale nie sprawdza nowych pól.
  - Skutek: pomyłka w kluczu roli, w filtrze reprezentantów albo w odczycie `qualifiedBoards`/`eligibleBoards` po cichu odwróciłaby rekomendację (na przykład na detektor mimo częściowych TRAIN, czyli z pominięciem korekt), a testy dalej by przechodziły.
  - Poprawka: w istniejącym teście dodać `first["partialTrainingPhotos"] == 10` oraz sprawdzenie, że `first["detectorReadiness"]["reasonCodes"]` zawiera `SCREEN_FULL_PHOTOS_REQUIRED`. Dodać wariant z pełnymi (9-planszowymi) zdjęciami TRAIN, częściowym zdjęciem w VALIDATION i aliasem niereprezentatywnym; w nim licznik musi wynosić 0, a częściowe zdjęcie spoza TRAIN nie może być liczone.

### P2

- [P2-1] `services/api/src/game_predictor_api/application/grid_correction_learning.py:490` — Globalne sprawdzenie aktualności zniknęło z `verified_publication_scope` (`grid_correction_history.py:46`). W trybie grid-only historyczne piny innych wymaganych gier nie przechodzą już w podglądzie przez `require_historical_cohort`, a więc ani przez dowód aktualności z raportu, ani przez sprawdzenie przodków.
  - Ochrona jest zachowana. Etykiety pilnuje bieżąca kwalifikacja (`storage/grid_training_cohort_currentness.py:146`), a tworzenie runu wywołuje `require_historical_cohort` (`application/shared_grid_model_candidate.py:106`).
  - Skutek: podgląd może pokazać `canStart=true`, a start odmówi z innym kodem. Dodatkowo `ITERATIVE_IMAGE_IMPORT.md:14` twierdzi, że ponowne użycie zawsze wymaga aktualnego dowodu wybranego pinu.
  - Poprawka: wywoływać `require_historical_cohort` także dla grid-only, gdy `baseVersionId` pinu różni się od wersji bazy, albo opisać to ograniczenie w dokumentacji.
- [P2-2] `services/api/src/game_predictor_api/application/grid_correction_learning.py:110` — Gdy w danych nie ma częściowych zdjęć TRAIN, rekomendujący GET wykonuje po kolei dwa pełne podglądy. Pojedynczy podgląd na rzeczywistych danych trwał według wykonawcy 56,938 s, więc odczyt może trwać około dwóch minut. Panel czeka na ten odczyt przed pokazaniem liczników. Proponuję zaakceptować ryzyko i opisać je w raporcie weryfikacji albo pokazać w panelu stosowny komunikat o czasie odczytu.
- [P2-3] `apps/admin/src/features/model-quality/grid-model-state.ts:243` — Kilka kodów blokady osiągalnych przy podglądzie lub starcie nie ma etykiety i wyświetla się jako „Inny powód (KOD)” bez wskazania dalszego działania. Dotyczy to kodów `GRID_LEARNING_HISTORY_COHORT_UNVERIFIED` i `GRID_LEARNING_HISTORY_BASE_MISMATCH` (`grid_correction_history.py:119` i `:126`), `GRID_LEARNING_IMPORT_SCOPE_INVALID` (`grid_correction_learning.py:152`), `GRID_LEARNING_BASE_MISSING` (`:292`) oraz `GRID_LEARNING_BASE_UNPUBLISHED`. To częściowo osłabia kryterium „każdy istotny disabled ma powód i dalsze działanie”. Poprawka: dodać etykiety z zalecanym działaniem w tym samym słowniku.
- [P2-4] `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx:789` — Po ręcznej zmianie celu, a przed odświeżeniem, wiersz „Wybrany cel” nadal pokazuje powody z poprzedniej automatycznej rekomendacji. Na przykład przy wybranym detektorze widać opis „Ten cel uczy położenia siatki…”, który dotyczy punktów. Poprawka: pokazywać `reasonCodes` tylko wtedy, gdy `!manualTrainingMode && ready.trainingRecommendation?.mode === trainingMode`.
- [P2-5] `services/api/src/game_predictor_api/application/grid_correction_history.py:86` — Po zmianie `verified_history` nie ma już żadnego wywołania w kodzie produkcyjnym; używają go tylko testy. Dokumentacja (`ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md:14`) opisuje go jako zachowany ścisły odczyt, co może sugerować, że gdzieś nadal działa jako bariera. Publikacja ma własną kontrolę w `grid_model_publication.py:172`. Poprawka: dopisać w dokumentacji, że jest to czytnik tylko dla starszych testów, albo wskazać faktyczną barierę publikacji.
- [P2-6] `ai_docs/archive/CURRENT_STATE_2026Q4.md:12` — Wpis TASK-1177 ma już uzupełniony hash, a obok pozostał dopisek „(hash dopisuje kolejny commit)”, który mu przeczy. Poprawka: usunąć dopisek, tak jak zrobiono w `tasks/completed/1177-symbol-review-performance-freeze.md:71`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Bieżąca przyczyna disabled rozpoznana i przedstawiona liczbowo | spełnione (liczby z rzeczywistego odczytu są deklaracją wykonawcy; nie weryfikowałem ich) | dawny guard w `verified_history` (usunięty fragment diffu `grid_correction_history.py`); `ai_docs/tasks/1178-grid-learning-readiness-guidance.md:67`; `ai_docs/quality/TASK-1178_VERIFICATION.md:9` |
| Ręczne korekty poprawnie kwalifikowane; podgląd aktualizuje liczniki | spełnione | `grid_correction_learning.py:300` (zakres publikacji bez blokady stale); `grid_correction_history.py:123` (aktualność tylko wybranego pinu); `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs:252` (odświeżenie liczników dla ręcznego celu) |
| Zalecany tryb wynika z danych; ręczny wybór zaawansowany zachowany | spełnione w logice; brak testu wyliczania danych wejściowych (P1-1) | `grid_correction_learning.py:97`; `grid-correction-learning-panel.tsx:798`; `grid-correction-learning-panel.tsx:227`; `services/api/tests/test_grid_learning_recommendation.py:12` |
| Każdy istotny disabled ma zrozumiały powód i dalsze działanie | spełnione z luką P2-3 | `grid-correction-learning-panel.tsx:660`, `:1164`, `:1172`; `grid-model-state.ts:12` |
| Kontrakty, historyczne polecenia i ochrona TRAIN/A/B/REG zachowane | spełnione | `api/grid_correction_learning.py:57` (domyślnie `false`); `grid_correction_learning.py:643` (zachowana tożsamość starych poleceń); `grid_correction_learning.py:609` (SHA bez rekomendacji); `openapi.json` i `packages/admin-api-client/src/index.ts:1745`; `packages/admin-api-client/test/grid-correction-learning-request.test.mjs:5`; `shared_grid_model_candidate.py:106`; `grid_model_evaluation.py:218` |
| Regresje, lint/typecheck/build/docs/map i Opus zakończone | niezweryfikowane (wyniki deklaruje wykonawca; ten audyt kończy się werdyktem REVISE) | `ai_docs/quality/TASK-1178_VERIFICATION.md:47` |
| Outcome i task-close; finalnie pytanie o scalenie całego zakresu | niezweryfikowane (etap po audycie; task ma status `in_progress`) | `ai_docs/tasks/1178-grid-learning-readiness-guidance.md:3` |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4, P2-5, P2-6.

## Proponowane testy

- Rozszerzyć `services/api/tests/test_grid_correction_workflow.py::test_metadata_preview_uses_game_cohort_reader_and_changes_pin_with_population` o asercje `partialTrainingPhotos` i `detectorReadiness` oraz dodać wariant z pełnymi zdjęciami TRAIN, częściowym zdjęciem VALIDATION i aliasem (P1-1): `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_correction_workflow.py -k metadata_preview`.
- Dodać test grid-only z historycznym pinem innej gry, który ma nieaktualny dowód, ale przechodzi bieżącą kwalifikację. Test powinien ustalić, czy blokada pojawia się już w podglądzie, czy dopiero przy starcie (P2-1): `services/api/tests/test_grid_correction_workflow.py`.
- Dodać test interakcji, że po ręcznej zmianie celu nie widać powodów poprzedniej rekomendacji (P2-4): `npm run test:geometry --workspace @game-predictor/admin` (lub odpowiedni skrypt `test-interactions` Admina).

## Zakres przeglądu i ograniczenia

Przeczytałem pełny pakiet z diffem i nowymi plikami. W kodzie sprawdziłem:

- `application/grid_correction_history.py` w całości;
- `application/grid_correction_learning.py` w liniach 80–700;
- `application/grid_model_evaluation.py` w liniach 190–320;
- `application/shared_grid_model_candidate.py` w całości;
- `storage/grid_training_cohort_currentness.py` w całości;
- `storage/grid_model_evaluation_repository.py` (`cohort_currentness`);
- `storage/grid_correction_split.py` w liniach 395–565;
- `domain/grid_detector_readiness.py`;
- panel Admina w liniach 160–1200 i `grid-model-state.ts` (`reasonLabel`);
- wywołania `verified_history`, `require_historical_cohort` i `cohort_currentness`, znalezione przez Grep.

Nie uruchamiałem testów, lintu, typechecku, buildu ani rzeczywistego odczytu. Liczby z bazy (362 plansze, 75 nowych TRAIN, `canStart=true`, 56,938 s) oraz zgłoszone wyniki PASS i 6 FAIL na stanie bazowym przyjąłem jako deklaracje wykonawcy, bez weryfikacji. Nie sprawdzałem zgodności wygenerowanego klienta z generatorem ani działania w przeglądarce.