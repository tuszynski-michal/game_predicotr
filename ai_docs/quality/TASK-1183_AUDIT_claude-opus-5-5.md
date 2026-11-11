# Audyt TASK-1183 — Przykłady korekt i niezależne kontrole

Werdykt: REVISE
Audytor: claude-opus-5-5, reasoning high
Wykonawca: gpt-6-astra, reasoning high
Zakres: HEAD...3991ff749f6af3a58c4f2e0bf6c5208c1b8392cb oraz zmiany niezacommitowane, data 2026-11-11
Runda: 1
SHA pakietu: 9230c54c55fef652d86ec6477005b8a70a3caddf7cb81394894b56a02ef075b2
Otwarte P0: 1
Otwarte P1: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przejrzałem pakiet TASK-1183: wykluczanie konfliktujących grup, raport `learningMaterial`, warstwową próbkę REG (zwykłą i trudną), częściowe TRAIN w trybie content oraz migrację 0184 z funkcjami SQL v10. Sprawdziłem też kod, z którego te zmiany korzystają: solver, czytnik dowodów, przechwytywanie kohorty i łańcuch wrapperów SQL v5–v9. Domknięcie grup, niezmienność historycznych funkcji i ograniczenie nowej ścieżki do opt-in są zrobione starannie.

Największy problem: wykluczone źródła są usuwane z populacji, zanim solver i losowanie REG policzą sąsiedztwo. Przez to znika 10-zdjęciowa ochrona wokół historycznych ról tych zdjęć. Są też dwie wady, które blokują główną ścieżkę content: wykluczone piny zachowują nieaktualny skrót etykiet, a wiązanie raportu oceny trafia do historycznej walidacji v3, która odrzuca częściowe TRAIN.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/storage/grid_correction_split.py:373` — **Utrata buforów wokół wykluczonych zdjęć.**
  - **Co się dzieje.** Źródła z wykluczonego domknięcia są usuwane z `sources`, zanim zbuduje się kolejność importów dla solvera (`_prepare_groups`, `services/api/src/game_predictor_api/domain/grid_correction_split.py:255-296`). To samo dotyczy losowania świeżego REG (`grid_correction_split.py:412-419` → `services/api/src/game_predictor_api/domain/grid_content_sampling.py:67-77`). Ochrona 10 zdjęć działa wyłącznie na podstawie pozycji w `orders`: `safe()` i wstawianie buforów w `services/api/src/game_predictor_api/domain/grid_correction_incremental_split.py:85-96,155-175` oraz `CONTENT_REG_BUFFER_PROTECTED`. Rejestr (`allowedRoles` w `services/api/src/game_predictor_api/storage/source_recording_sql_v6.py:98-102`) nie zna sąsiedztwa sekwencyjnego.
  - **Skutek.** Alias wykluczonej grupy może leżeć w uporządkowanym imporcie. W danych operatora domknięcie obejmuje aliasy w importach d7747436 i fbca1ab5. Jeśli taki alias ma historyczną rolę TRAIN, VALIDATION albo REG, jego wolni sąsiedzi mogą teraz dostać nową rolę kontrolną. Przykład: nowe A, B lub świeży REG tuż obok klatki, na której uczył się model bazowy, albo nowe TRAIN obok historycznej kontroli. Narusza to wymóg planu „Zachować … 10-photo bufory” i kryterium T2 „brak leakage”.
  - **Poprawka.** Wykluczone zdjęcia powinny zostać w kolejności importów jako zablokowane miejsca. Nie mogą dostać nowej roli, a ich historyczne role (lub każda rola, zachowawczo) mają blokować inne role w promieniu 10 zdjęć, zarówno w solverze, jak i w `fresh_regression_preview`. Potrzebny jest test z wykluczonym aliasem w uporządkowanym imporcie i wolnymi sąsiadami.

### P1

- [P1-1] `services/api/src/game_predictor_api/storage/grid_correction_split.py:349` — **Nieaktualny skrót etykiet wykluczonych pinów w trybie content.**
  - **Co się dzieje.** Wykluczone piny zachowują `qualifiedLabelsSha256` z pierwszego przechwycenia grid-only. W trybie content pętla ponownego przechwycenia (`grid_correction_split.py:536-551`) przelicza ten skrót tylko dla pinów aktywnych. Wykluczone dołącza się później, w linii 553. Tymczasem `split_mapping` (`grid_correction_split.py:633-662`) daje im `contentSamplingPolicy` i `expectedLabelsSha256`. Przy przechwyceniu kohorty etykiety dostają `content_pin` i `productionContentReference` (`services/api/src/game_predictor_api/storage/grid_training_cohort_evidence.py:471-493`).
  - **Skutek.** Bezwarunkowa kontrola w `services/api/src/game_predictor_api/application/grid_training_cohort_commands.py:309-322` zwróci `GRID_CORRECTION_LABELS_CHANGED`. Każda kohorta content, w której jest choć jedno wykluczenie, nie przejdzie etapu capture. Tak jest dokładnie w przypadku operatora (konflikt 1121). Test `test_adapter_retains_excluded_population…` sprawdza tylko grid-only, a test PostgreSQL wstawia członków bezpośrednio, z pominięciem capture.
  - **Poprawka.** Objąć wykluczone piny ponownym przechwyceniem z ich mapowaniem albo zdefiniować dla `newUseExcluded` jawny, spójny fence. Dodać test adaptera z polityką content i wykluczeniem, który przechodzi przez `_capture`.

- [P1-2] `services/api/src/game_predictor_api/storage/source_recording_sql_v10.py:59-77` — **Wiązanie raportu dla nowych kohort trafia do walidacji v3.**
  - **Co się dzieje.** Wrapper v7 przechwytuje tylko `register_cohort_use` i `validate_cohort_use`. Polecenie `bind_existing_report` (`services/api/src/game_predictor_api/application/grid_model_evaluation.py:127`) idzie dalej do v6 i `recording_correction_report_bind_v4`. Ta funkcja waliduje kohortę przez `recording_cohort_command_v6` → v5 → `recording_photo_cohort_v3` (`services/api/src/game_predictor_api/storage/source_recording_sql_v9.py:7-23`, `services/api/src/game_predictor_api/storage/source_recording_sql_v8.py:250-254`, `services/api/src/game_predictor_api/storage/source_recording_sql_v5.py:27-28`). Historyczna v3 odrzuca każde użyte TRAIN, które nie jest pełne, kodem `GRID_COHORT_FULL_PHOTO_REQUIRED` (`services/api/src/game_predictor_api/storage/source_recording_sql_v7.py:37-40`). Nie sprawdza też dowodów wykluczonych grup.
  - **Skutek.** Raportu oceny nie da się powiązać z kohortą efektywnego materiału, która ma częściowe TRAIN, więc ścieżka publikacji i bramek dla T3 jest zablokowana. Naprawa po wdrożeniu wymagałaby kolejnej migracji.
  - **Poprawka.** W migracji 0184 dodać wersjonowaną funkcję wiązania (lub przechwycenie w v7), która dla `learningMaterial` waliduje przez `recording_photo_cohort_v4`. Dodać test PostgreSQL `bind_existing_report` dla kohorty z częściowym TRAIN.

### P2

- [P2-1] `services/api/src/game_predictor_api/domain/grid_content_sampling.py:173` — **Zmiana znaczenia `selectionState` w starej ścieżce.** `selectionState` liczy się teraz z `selected_geometry_photos` także w trybie niewarstwowym, więc stara ścieżka v1 może pokazać `ready` tam, gdzie wcześniej było `not_evaluable`. Ścieżka jest obecnie nieużywana, bo `resolve_content_sampling` zawsze ustawia v2. Propozycja: ograniczyć zmianę do `stratified` albo jawnie opisać nowe znaczenie.
- [P2-2] `services/api/tests/integration/test_effective_grid_material_postgres.py:233-251` — **Brak testu utraty odpowiedzi.** Każde wywołanie `execute` generuje nowy `idempotencyKey`. Nie ma scenariusza ponowienia tym samym kluczem po zatwierdzonej transakcji, którego wymagają „Test cases” taska. Testowane są tylko rollback z ponowieniem i zimny odczyt. Propozycja: dodać ponowienie z tym samym kluczem dla v7/v4.
- [P2-3] `services/worker/src/game_predictor_worker/images/grid_cohort_dataset.py:562-581` — **Rejestracja przed gotowością workera.** Kohortę z częściowym TRAIN można zarejestrować (trwałe wpisy w ledgerze), ale obecny worker odrzuci ją kodem `FULL_PHOTO_REQUIRED` aż do T3. Zachowanie jest bezpieczne (fail-closed). Propozycja: jawnie zapisać, że migracji 0184 nie wdraża się u operatora przed T3.
- [P2-4] `services/api/src/game_predictor_api/domain/grid_learning_reference.py:44-49` — **Rozmiar manifestu.** `difficultyReferences` zapisuje dla każdej planszy wybranych źródeł pełny `producer` (binding, engineSnapshot, lineage) i `baselineNodes`, co może znacznie powiększyć manifest. Propozycja: przypinać skróty lub identyfikatory zamiast pełnych obiektów.
- [P2-5] `services/api/src/game_predictor_api/storage/grid_training_cohort_evidence.py:455-460` — **Wąska obsługa błędów `original_target`.** Przechwytywany jest tylko `NeuralGridProposalError`. Uszkodzony historyczny dowód, np. `KeyError` z `binding["confirmedRange"]` w `services/api/src/game_predictor_api/storage/grid_quality_observations.py:249`, przerwie cały podgląd content. Wcześniej ta funkcja nie była wywoływana podczas capture. Propozycja: mapować błędy dowodu na stan `unknown` z kodem przyczyny.
- [P2-6] `ai_docs/quality/TASK-1183_VERIFICATION.md` (sekcja „Verification”) — **Weryfikacja w innym worktree.** Testy wykonano w worktree `effective-grid-learning`. Na czystym delivery koordynator powtórzył tylko 48 testów; 25 testów split/incremental i test PostgreSQL nie zostały tam powtórzone. Mypy uruchomiono z `--follow-imports=silent` zamiast pełnej bramki projektu. Propozycja: powtórzyć te przebiegi na delivery i zapisać wynik.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Wszystkie kryteria T2 planu udowodnione testami i raportem | niespełnione | P0-1 (`storage/grid_correction_split.py:373`), P1-1 (`storage/grid_correction_split.py:349`), P1-2 (`storage/source_recording_sql_v10.py:59-77`) |
| Wagi 4:1, deduplikacja zdjęć i plansz, jawny BUFFER | spełnione | `domain/grid_learning_material.py:96-150`, `tests/test_grid_learning_material.py:85-117` |
| Konflikt 1121: całe domknięcie wykluczone, historia bez zmian | spełnione częściowo | `domain/grid_learning_material.py:21-73`; brak buforów wokół wykluczonych zdjęć (P0-1) |
| Zwykły REG z seedem 20261108, niezależny od trudności i etykiet; osobna trudna próbka | spełnione | `domain/grid_content_sampling.py:78-119`, `tests/test_grid_learning_material.py:119-139` |
| Kategoria bez osobnego dowodu = unknown; AI ≠ human GT | spełnione | `domain/grid_learning_reference.py:26-49`, `tests/test_grid_learning_material.py:142-152` |
| Partial TRAIN tylko dla geometrii, nadal 10 pełnych TRAIN i 5 pełnych A | spełnione częściowo | `storage/source_recording_sql_v10.py:41-54`, `tests/test_grid_learning_material.py:173-188`; wiązanie raportu odrzuca partial (P1-2) |
| Ochrona historycznych wersji, danych i niezależnych kontroli | niespełnione | historyczne SQL bajtowo identyczne (`tests/integration/test_effective_grid_material_postgres.py:41-56`), ale P0-1 |
| Migracja 0184 bez zmian tabel i historycznych funkcji; downgrade blokowany | spełnione | `alembic/versions/0184_effective_grid_material.py:18-59` |
| Opus terminal PASS, brak otwartych P0/P1, docs/map, właściwe testy | niespełnione | ten raport: REVISE; docs:check i code-map:check niezweryfikowane statycznie |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1, P1-1, P1-2, P2-1, P2-2, P2-3, P2-4, P2-5, P2-6.

## Proponowane testy

- **Bufory wokół wykluczonych zdjęć (P0-1).** W `services/api/tests/test_grid_learning_material.py`: wykluczony alias z historycznym TRAIN w uporządkowanym imporcie i wolnymi sąsiadami w promieniu 10 zdjęć. Asercja: sąsiedzi nie dostają VALIDATION ani REG w `prepare_split`, a `fresh_regression_preview` ich nie wybiera. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_learning_material.py -k excluded_neighbors`.
- **Capture kohorty content z wykluczeniem (P1-1).** Test adaptera z `content_sampling` i wykluczoną grupą, który przechodzi przez `_capture` w `application/grid_training_cohort_commands.py` bez `GRID_CORRECTION_LABELS_CHANGED`.
- **Wiązanie raportu dla partial TRAIN (P1-2).** Test PostgreSQL `bind_existing_report` dla kohorty z `learningMaterial` i częściowym TRAIN w `services/api/tests/integration/test_effective_grid_material_postgres.py`, uruchamiany z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`.
- **Utrata odpowiedzi (P2-2).** Ponowienie `register_cohort_use` tym samym `idempotencyKey` po zatwierdzonej transakcji, w tym samym pliku PostgreSQL.

## Zakres przeglądu i ograniczenia

**Przeczytane w całości:** brief, task, część T2 planu, pełne diffy i nowe pliki pakietu.

**Kod pomocniczy w potrzebnym zakresie:**
- `storage/grid_correction_split.py`, `domain/grid_content_sampling.py`, `storage/grid_content_sampling.py`;
- `domain/grid_correction_split.py`, `domain/grid_correction_incremental_split.py`, `domain/grid_detector_readiness.py`;
- `storage/grid_training_cohort_evidence.py`, `storage/grid_quality_observations.py` (`original_target`);
- `application/grid_training_cohort_commands.py` (capture i materializacja), `storage/grid_training_cohort_currentness.py`;
- SQL v4–v9, w tym wrappery, wiązanie raportów i kontekst rejestru;
- `services/worker/.../grid_cohort_dataset.py`, `grid_training_data.py`.

**Ograniczenia:**
- To był przegląd statyczny: żadnych testów, lintera, mypy, docs:check ani code-map:check nie uruchamiałem.
- Wyniki z raportu wykonawcy przyjmuję jako niezweryfikowane.
- Zachowanie SQL PL/pgSQL i kolejność operatorów oceniłem przez lekturę, bez wykonania.
- Nie sprawdzałem rzeczywistego układu importów operatora, więc skala P0-1 w danych operatora pozostaje niezmierzona.