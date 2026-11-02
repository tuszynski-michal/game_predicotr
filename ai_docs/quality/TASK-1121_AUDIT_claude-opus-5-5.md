# Audyt TASK-1121 — Trening i ocena częściowych zdjęć

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...e1fcae27dace97c5dea102a05c512b9bf77ec94c oraz zmiany niezacommitowane (śledzone i nowe pliki z listy briefu), data 2026-11-02
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Runda 2 była skupiona na poprawkach. Sprawdziłem zamknięcie P1-1 i P1-2 z rundy 1 oraz wpływ poprawek P2-1–P2-6. Pełnego przeglądu 75 plików nie powtarzałem. Scoped `set_default` sprawdza teraz pod registry lock, czy aktualny head to baza kandydata albo sam kandydat. Stabilny kod 409 pojawia się dopiero po replay receipt i CAS rewizji. Nowy plik testów wykonuje prawdziwe `execute` z zapisem dla publish, set_default, replay i activate. Nie znalazłem otwartych P0 ani P1. Zostały dwa drobne P2: jeden nieaktualny wiersz w CURRENT_STATE (resztka P2-6) i brak polskiej etykiety nowego kodu błędu w Adminie.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `ai_docs/process/CURRENT_STATE.md:45`: wiersz planu w tabeli nadal mówi „T2 code/tests ready, audit blocked limitem sesji Anthropic (reset 2026-11-02 20:10 Warsaw)”. Sekcja taska (`:70`) i plik taska (`ai_docs/tasks/1121-grid-correction-training-evaluation.md:3`, `:11`) mają już spójny `in_progress`. `TASK-1121_VERIFICATION.md` twierdzi jednak, że nieaktualny opis limitu usunięto, więc P2-6 z R1 jest poprawione tylko częściowo. Skutek: następna sesja dostaje sprzeczny stan startowy. Poprawka: przy task-close zaktualizować ten wiersz (np. „T2 audyt R2 PASS, commit …”).
- [P2-2] `apps/admin/src/features/model-quality/grid-model-state.ts:17-31` (fallback `:118`): nowy kod `GRID_MODEL_EVALUATION_SCOPE_STALE` z `services/api/src/game_predictor_api/application/grid_model_publication.py:134` nie ma etykiety w `REASON_LABELS`. Operator zobaczy „Inny powód (GRID_MODEL_EVALUATION_SCOPE_STALE)” zamiast polskiego wyjaśnienia, że default zmienił się od czasu oceny. Działanie pozostaje fail-closed, a skutek dotyczy tylko UX. Poprawka: dodać etykietę, np. „Default zmienił się od oceny — potrzebna nowa ocena”, w TASK-1122, który i tak buduje panel. Można też odnotować to jako zaakceptowane ryzyko.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Częściowe VALIDATION i REGRESSION przechodzą cały pion bez filtrowania | spełnione | Ocena z R1 bez zmian. Po P2-2 wspólna definicja: `services/worker/src/game_predictor_worker/images/grid_cohort_dataset.py:414-423,445-452`, `images/grid_model_evaluation_handler.py:269`, `images/grid_training_data.py:366`. Test `services/worker/tests/test_grid_correction_evaluation_pipeline.py:73-94` (screenEligible=True i 3 cele pozostają partial) |
| Checkpoint deterministyczny | spełnione | Ocena z R1. Poprawki R2 tego nie zmieniają |
| Scoped report v3 i publish gate v2 | spełnione | `services/api/src/game_predictor_api/application/grid_model_publication.py:111-124` (pominięte tylko sprawdzenie rodziny, currentness nadal wymagane). Test `services/api/tests/test_grid_model_publication_scoped.py:81-103` |
| Spójne publish/activate/default dla raportu scoped (P1-1 i P1-2 z R1) | spełnione | `grid_model_publication.py:125-136` (head == baza albo kandydat, pod lockiem z `:257`), `:269-287` (replay i CAS przed guardem). Testy `test_grid_model_publication_scoped.py:106-132` (brak defaultu, baza, ponowne ustawienie head, zmieniony head przy poprawnej rewizji, replay receipt) i `:135-144` (activate w scope i poza nim). D-578 uzupełnione w `ai_docs/process/decisions/DECISION_LOG_2026.md` |
| Legacy bez zmian | spełnione | Guard działa tylko przy `evidence.scoped` (`grid_model_publication.py:113,125`). Legacy set_default w teście `test_grid_model_publication_scoped.py:122`. Kanoniczne evidence publikacji niezmienione (`:137-142`, `:188-194`) |
| Właściwe testy, lint/typecheck i dokumentacja | spełnione (wg deklaracji wykonawcy) | Testów nie uruchamiałem. Wykonawca podaje w `ai_docs/quality/TASK-1121_VERIFICATION.md`: 38 PASS, 24 PASS, Ruff, scoped mypy z main/cli. Ograniczenie mypy (wyjątek `torch.*`) jest jawnie odłożone do T4 |
| Audyt Opus 5.5/high bez otwartych P0/P1 | spełnione | Ten raport: PASS |
| Outcome, task-close, osobny commit, record-hash | niezweryfikowane | Następny krok po tym audycie |

## Listy zamknięte i otwarte

Zamknięte:

- P1-1: `grid_model_publication.py:125-136`, wywołanie z `:285-287` pod lockiem `:257`. Test `test_grid_model_publication_scoped.py:126-128`.
- P1-2: `services/api/tests/test_grid_model_publication_scoped.py:81-144`.
- P2-1: deklaracja main/cli 2 PASS w `TASK-1121_VERIFICATION.md`.
- P2-2: `has_full_geometry` w `grid_cohort_dataset.py:414-423`, używane w `grid_model_evaluation_handler.py:269` i `grid_training_data.py:366`. Test `test_grid_correction_evaluation_pipeline.py:73`.
- P2-3: `services/api/src/game_predictor_api/application/grid_correction_learning.py:571-584` (55P03 → `GRID_LEARNING_BUSY`/409, inne błędy przepuszczane). Test `services/api/tests/integration/test_grid_correction_learning_postgres.py:128-132`.
- P2-4: `grid_correction_learning.py:394-401`. Test `test_grid_correction_learning_postgres.py:135-156`.
- P2-5: `services/api/src/game_predictor_api/schemas/grid_correction_learning.py:43-50` i `schemas/grid_model_evaluations.py` (walidator `canonical_exclusions`), sortowanie zgodne z `domain/grid_correction_evaluation.py:261`. Test `services/api/tests/test_grid_correction_learning_api.py:298`.
- P2-6: zamknięte częściowo, resztę przenoszę jako P2-1 tej rundy.

Otwarte: P2-1, P2-2 (rundy 2).

## Proponowane testy

- `apps/admin/test/grid-model-evaluation-state.test.mjs` (albo test `reasonLabel`): `GRID_MODEL_EVALUATION_SCOPE_STALE` daje polską etykietę, a nie „Inny powód”. Polecenie: `npm run test --workspace @game-predictor/admin`.
- Opcjonalnie w `services/api/tests/test_grid_model_publication_scoped.py`: `rollback` gry do wersji scoped spoza `requiredGameIds` zostaje odrzucony tym samym kodem co activate. Polecenie: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_model_publication_scoped.py`.

## Zakres przeglądu i ograniczenia

Brief podaje jako bazę porównania samo HEAD, więc pole Zakres zapisałem jako HEAD...e1fcae27 (sha HEAD). Commitowany diff jest pusty, a cały zakres to zmiany niezacommitowane.

Przeczytałem w całości: `application/grid_model_publication.py`, `services/api/tests/test_grid_model_publication_scoped.py` oraz brief razem z raportem R1 i `TASK-1121_VERIFICATION.md`. Fragmentami przeczytałem:

- `application/grid_correction_learning.py:290-596`,
- `schemas/grid_correction_learning.py:1-80`,
- diff `schemas/grid_model_evaluations.py`,
- `domain/grid_correction_evaluation.py:250-266`,
- `test_grid_correction_learning_postgres.py:95-189`,
- `test_grid_correction_evaluation_pipeline.py:1-100`,
- handler workera `grid_correction_learning_handler.py`,
- diffy `grid_cohort_dataset.py`, `grid_model_evaluation_handler.py` i `grid_training_data.py`,
- etykiety błędów w `apps/admin/src/features/model-quality/grid-model-state.ts`.

Grepem sprawdziłem pozostałe ścieżki ustawiania defaultu (`api/grid_model_registry.py`, `new_game_geometry.py`, `storage/grid_reinference.py`). Nie omijają one guardu, bo zmiana defaultu idzie wyłącznie przez `execute`.

Zgodnie z dyspozycją focused rundy 2 nie powtarzałem przeglądu całego pionu z R1. Nie uruchamiałem testów, lintu, typechecku, migracji ani usług. Zachowania PostgreSQL (advisory lock, `lock_timeout`, SQLSTATE 55P03) nie dało się potwierdzić statycznie. Opieram się tu na teście PG i deklaracji wykonawcy.
