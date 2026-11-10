# Audyt TASK-1178 — Gotowość korekt i zalecany cel uczenia

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: 0e1a02ec916629508570ee6570ded38d4df92817...0e1a02ec916629508570ee6570ded38d4df92817 (brak zmian zacommitowanych) oraz zmiany niezacommitowane, data 2026-11-10
Runda: 2
SHA pakietu: 109a10e2bdc3144e58c7ad821a2727e8af4c382d5658259a602ae9c3c3918e90
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

W rundzie 2 sprawdziłem poprawki znalezisk z rundy 1. Przejrzałem też ponownie nowe ścieżki, których dotknęły: sprawdzanie aktualności wybranego pinu w podglądzie grid-only, wyliczanie `partialTrainingPhotos` i `detectorReadiness`, warunki blokady startu w panelu oraz nowe etykiety powodów. P1-1 jest zamknięte: prawdziwe `_preview` ma teraz test w wariantach częściowego i pełnego TRAIN, z aliasem niereprezentatywnym, częściowymi kontrolami i buforem. P2-1, P2-3, P2-4, P2-5 i P2-6 są poprawione i, tam gdzie to dotyczy kodu, pokryte testami. Zostaje ryzyko czasu odczytu z dwoma podglądami (P2-2). Wykonawca jawnie je zaakceptował, a panel je opisuje. Doszła jedna drobna uwaga o tym, jak pokazywane jest uzasadnienie.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-2] `services/api/src/game_predictor_api/application/grid_correction_learning.py:110` — Kiedy nie ma częściowych zdjęć TRAIN, a detektor ma komplet pełnych zdjęć, rekomendujący GET wykonuje drugi pełny podgląd. Każdy podgląd dostaje własny budżet `CohortDeadline()` (`grid_correction_learning.py:181`, 60 s według `storage/grid_training_cohort_repository.py:49`). Zmierzony odczyt na zimnym interpreterze trwał 56,938 s (`artifacts/task1178-ready-after.json:5`), więc margines jest mały. Przy wzroście danych pojedynczy podgląd może zwrócić `GRID_COHORT_TIMEOUT`, a odczyt rekomendacji może trwać około dwóch minut. Wykonawca zaakceptował to ryzyko (`ai_docs/quality/TASK-1178_VERIFICATION.md`, sekcja „Audit and boundaries”). Panel informuje o długim sprawdzaniu (`apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx:703`), a kod timeoutu ma etykietę z dalszym działaniem (`apps/admin/src/features/model-quality/grid-model-state.ts:48`). Akceptuję ryzyko. Proponuję odnotować w raporcie weryfikacji mały zapas względem budżetu 60 s na pojedynczy podgląd.
- [P2-7] `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx:799` — Uzasadnienie `GRID_LEARNING_PARTIAL_TRAIN_PRESENT` jest pokazywane wyłącznie jako opis słowny. Backend zwraca liczbę `partialTrainingPhotos` (`grid_correction_learning.py:392`; w odczycie rzeczywistym 150, `artifacts/task1178-ready-after.json:159`), ale panel jej nie wyświetla. Linia „częściowe” przy detektorze (`grid-correction-learning-panel.tsx:915`) podaje inną populację: wszystkie role razem z buforami (180). Skutek: operator nie widzi, ile częściowych zdjęć TRAIN przesądziło o wyborze punktów. Nie łamie to kryterium, bo cel i powód są widoczne. Poprawka: przy tym kodzie dopisać „(N zdjęć TRAIN)” z `ready.partialTrainingPhotos` albo przyjąć to jako ryzyko.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Bieżąca przyczyna disabled rozpoznana i przedstawiona liczbowo | spełnione (liczby z bazy to deklaracja wykonawcy) | usunięty globalny guard i nowy `verified_publication_scope` w `services/api/src/game_predictor_api/application/grid_correction_history.py:46`; liczby w `ai_docs/tasks/1178-grid-learning-readiness-guidance.md:69`; `artifacts/task1178-ready-after.json:122-151` (`priorGameIds` zawiera tylko bieżącą grę, `historicalCohorts=[]`, więc poprawka P2-1 nie zmienia tego wyniku) |
| Ręczne korekty poprawnie kwalifikowane; podgląd aktualizuje liczniki | spełnione | `grid_correction_learning.py:300`, `:379-395`; test `services/api/tests/test_grid_correction_workflow.py:380`, `:467-475`; odświeżanie liczników przy ręcznym celu w `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs:250` |
| Zalecany tryb wynika z danych; ręczny wybór zaawansowany zachowany | spełnione | `grid_correction_learning.py:97-122`; `services/api/tests/test_grid_learning_recommendation.py:12`; `grid-correction-learning-panel.tsx:227`, `:809-848`; testy interakcji `grid-correction-learning-panel.test.mjs:210`, `:250`, `:2229` |
| Każdy istotny disabled ma zrozumiały powód i dalsze działanie | spełnione | `grid-correction-learning-panel.tsx:660-678` (`startGuardReasons` obejmują wszystkie człony dawnego `disabled` z `:636`), `:1175-1183`; etykiety w `grid-model-state.ts:12-59` bez zdublowanych kluczy |
| Kontrakty, historyczne polecenia i ochrona TRAIN/A/B/REG zachowane | spełnione | domyślnie `false` w `services/api/src/game_predictor_api/api/grid_correction_learning.py:60`; tożsamość starych poleceń i replay przed przeliczeniem w `grid_correction_learning.py:642-668`; rekomendacja dodana po SHA (`:607`, `:119`); aktualność wybranego pinu w podglądzie, przy ocenie, przy tworzeniu runu i w workerze (`grid_correction_learning.py:490`, `grid_model_evaluation.py:218`, `shared_grid_model_candidate.py:101`, `services/worker/src/game_predictor_worker/images/grid_training_store.py:114`); OpenAPI, SDK, wrapper i test żądania w `packages/admin-api-client/src/index.ts:1745` i `packages/admin-api-client/test/grid-correction-learning-request.test.mjs:5` |
| Regresje, lint/typecheck/build/docs/map i Opus zakończone | niezweryfikowane (wyniki deklaruje wykonawca; ta runda kończy się PASS) | `ai_docs/quality/TASK-1178_VERIFICATION.md`, sekcja „Tests performed” |
| Outcome i task-close; finalnie pytanie o scalenie całego zakresu | niezweryfikowane (etap po audycie; task ma status `in_progress`) | `ai_docs/tasks/1178-grid-learning-readiness-guidance.md:3` |

## Listy zamknięte i otwarte

Zamknięte: P1-1 (test `test_grid_correction_workflow.py:380-475`: parametr `full_train`, alias niereprezentatywny `:436`, asercje `partialTrainingPhotos` i `detectorReadiness` z rolami), P2-1 (`grid_correction_learning.py:490` bez warunku `screen or purpose_aware`; test nieaktualnego pinu `test_grid_correction_workflow.py:476-520` oraz `:736`, `:764`), P2-3 (`grid-model-state.ts:12-21`), P2-4 (`grid-correction-learning-panel.tsx:795-798`; test `grid-correction-learning-panel.test.mjs:296`), P2-5 (`ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md:14-16`; Grep potwierdza brak produkcyjnego wywołania `verified_history`), P2-6 (`ai_docs/archive/CURRENT_STATE_2026Q4.md:12`).

Otwarte: P2-2, P2-7.

## Proponowane testy

- Test interakcji: przy rekomendacji z `GRID_LEARNING_PARTIAL_TRAIN_PRESENT` panel pokazuje liczbę `partialTrainingPhotos` (P2-7). Plik `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs`, komenda `npm run test:geometry --workspace @game-predictor/admin` albo odpowiedni skrypt interakcji Admina.
- Test jednostkowy rekomendacji z prawdziwym `_preview`: zero częściowych TRAIN i komplet pełnych zdjęć prowadzi do drugiego podglądu w trybie `screen+grid`, a gdy ten ma blokadę, rekomendacja wraca do punktów i przenosi jej kod. Plik `services/api/tests/test_grid_correction_workflow.py`, komenda `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_correction_workflow.py -k metadata_preview`.

## Zakres przeglądu i ograniczenia

Przeczytałem cały pakiet, w tym diff, raport R1, receipt i raport weryfikacji. W kodzie sprawdziłem:

- `application/grid_correction_history.py` w całości;
- `application/grid_correction_learning.py` w liniach 90–130, 270–530 i 585–695;
- `application/grid_model_evaluation.py` w liniach 205–300;
- `domain/grid_detector_readiness.py`;
- `storage/grid_training_cohort_repository.py`: `CohortDeadline` i mapowanie timeoutu;
- `services/worker/.../grid_training_store.py` w liniach 100–130;
- panel Admina: definicje stanu, `refresh`, warunki `disabled` i blokady startu, sekcję celu i detektora;
- `grid-model-state.ts`: nowe klucze, sprawdzone pod kątem duplikatów;
- testy `test_grid_correction_workflow.py` w liniach 370–540 i nazwy nowych testów historii;
- testy interakcji: nowe przypadki i ich lokalizacje;
- artefakt `artifacts/task1178-ready-after.json` (tylko odczyt).

Wywołania `verified_history`, `verified_publication_scope` i `require_historical_cohort` znalazłem przez Grep.

Nie uruchamiałem testów, lintu, typechecku, buildu ani odczytu z bazy. Wyniki PASS, 6 FAIL na HEAD i czasy przyjąłem jako deklaracje wykonawcy. Nie sprawdzałem zgodności wygenerowanego klienta z generatorem ani działania w przeglądarce.

Sekcja pakietu „Outcome verification lines” podaje brak wyników, choć Outcome taska je zawiera. Traktuję to jako ograniczenie parsera pakietu, nie jako znalezisko. W worktree istnieje też nieobjęty pakietem plik `ai_docs/quality/TASK-1178_AUDIT_claude-opus-5-5.md`, kopia treści R1. Nie oceniałem go.