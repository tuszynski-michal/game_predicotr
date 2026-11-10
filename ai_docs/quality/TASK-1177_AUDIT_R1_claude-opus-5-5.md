# Audyt TASK-1177 — Wydajny zapis symboli i zamrażanie manifestu

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...f4d1672933487752e51f0e49b4e49513d6779a00 oraz zmiany niezacommitowane, data 2026-11-10
Runda: 1
SHA pakietu: 7dcfdfbb9811e7b5c4417b2ff132d2a2d7b3bafb68e6c250f2ec7e0a6ca57e76
Otwarte P0: 0
Otwarte P1: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadałem zamrożony pakiet i kod, którego on dotyczy: freeze z poświadczeniem bez blokady i fence'em pod krótką blokadą, nieblokującą próbę blokady własności, zmiany SQL inwentarza z CTE właściciela liczonym raz na planszę, liczniki bulk zwiększane razem z przejściami celów oraz obsługę STALE i WRITE_BUSY w Adminie. Rdzeń jest poprawny. Kolejność blokad (własność, potem gra, potem stan katalogu) jest zachowana. Mutacje komórek podbijają `catalog_revision` w tej samej transakcji (`_touch_catalog_revision`). Konflikt RR (40001) i zajęty wiersz (55P03) są poprawnie mapowane. Trwała idempotencja i `find_by_manifest` zapobiegają dublowaniu kohort. Nie znalazłem błędu P0. Dwa braki procesowe blokują jednak commit:

- opublikowany kontrakt API nie odpowiada nowemu zachowaniu freeze i nowym kodom błędów;
- rozszerzona definicja „ciężkiej operacji” nie ma testu.

Główne ryzyko merytoryczne: poprawność fence'u opiera się na niewymuszonej regule, że każdy pisarz danych wejściowych manifestu podbija `catalog_revision`.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `ai_docs/architecture/API_CONTRACT.md:4728` — Kontrakt endpointów verified-training-cohorts nadal mówi, że „Jawny POST blokuje grę i ponownie weryfikuje bajty przed zapisem” (4728–4729). Implementacja robi teraz co innego: poświadcza pliki bez blokady, a dopiero potem bierze krótki try-lock i NOWAIT (`services/api/src/game_predictor_api/application/verified_training_cohorts.py:320-331`). Opis POST (4735–4737) wymienia tylko `PREVIEW_STALE` i `HEAVY_JOB_ACTIVE`. Brakuje nowych, stabilnych kodów `VERIFIED_TRAINING_COHORT_WRITE_BUSY` i `VERIFIED_TRAINING_COHORT_PROJECTION_NOT_READY` (`services/api/src/game_predictor_api/storage/symbol_cell_training_source_repository.py:90-93,121-143`). Brakuje też informacji, że oczekujące lub trwające bulk, import i ponowne wyznaczanie siatek dają teraz `HEAVY_JOB_ACTIVE`. D-600 twierdzi, że nie ma zmian publicznych pól API. Nowe wartości błędów są jednak zmianą kontraktu w rozumieniu DoD („błędy mają stabilny kod”, „zmiana breaking jest jawnie odnotowana”), a kryterium „API/OpenAPI/SDK zgodne” nie jest spełnione w dokumentacji kontraktu. Skutek: klienci i kolejne zadania (T2) opierają się na nieaktualnym opisie semantyki blokady. Poprawka: zaktualizować obie sekcje `API_CONTRACT.md` (poświadczenie bez blokady, fence pod krótką blokadą, pełna lista kodów 409 z warunkami, nowe typy ciężkich jobów) i dopisać nowe kody w D-600.
- [P1-2] `services/api/src/game_predictor_api/storage/image_review_repository.py:713` — `has_active_heavy_job` blokuje teraz także `IMAGE_SYMBOL_REVIEW_BULK`, `IMPORT` i `IMAGE_GRID_REINFERENCE` w stanach CREATED/PROCESSING. To nowe zachowanie produkcyjne: blokuje przygotowanie i freeze, a w Adminie wyłącza przycisk. Nie ma dla niego żadnego testu. Jedyny test predykatu (`services/api/tests/test_image_review_repository_job_lock.py:10-18`) sprawdza tylko obecność `SYMBOL_TRAINING`. Testy UI symulują flagę `activeHeavyJob`, nie predykat backendu. DoD wymaga testów nowego zachowania, więc brak wymaganego testu to P1. Poprawka: test jednostkowy, który sprawdza dokładny zbiór typów jobów i statusów (w tym brak blokady dla innych typów oraz dla WAITING_FOR_REVIEW, COMPLETED i FAILED). Do tego najlepiej jeden test PostgreSQL: freeze przy oczekującym jobie bulk daje `VERIFIED_TRAINING_COHORT_HEAVY_JOB_ACTIVE`.

### P2

- [P2-1] `services/api/src/game_predictor_api/application/verified_training_cohorts.py:321` — Komentarz zakłada, że „every supported geometry/cell writer bumps catalog_revision”. To niewymuszona reguła, której nie sprawdza żaden test. Wcześniej pełna blokada własności na czas inwentarza czyniła ją zbędną. Testy potwierdzają ją tylko dla bulk (`test_symbol_review_performance_freeze_postgres.py`) i ręcznego zapisu geometrii (`test_full_cell_correction_postgres.py:174-179`). Wielu pisarzy biorących blokadę własności nie dotyka `catalog_revision` bezpośrednio, m.in. `page_geometry_override_repository.py`, `source_replacement_binding.py`, `source_replacement_admission.py`, `pending_sequence_ownership.py` i `storage_gc_repository.py`. Ograniczenie skutków: zapisany manifest jest identyczny z potwierdzonym podglądem, więc zgoda operatora nie jest naruszona. Ryzykiem jest kohorta złożona z danych zmienionych tuż przed zapisem. Propozycja: opisać tę regułę w architekturze D-600 i dodać test (lub listę kontrolną) dla pisarzy wejść manifestu: komórki, `recognized_boards.geometry_revision` i `source_geometry_revision_id`, właściciel w fast documents, `source_replacement_current_v1`, render manifest. Można też jawnie zaakceptować ryzyko.
- [P2-2] `services/api/src/game_predictor_api/storage/image_review_repository.py:713-720` — Zawieszony job CREATED/PROCESSING typu `IMAGE_GRID_REINFERENCE` lub `IMPORT` blokuje przygotowanie treningu na czas nieokreślony. Dotyczy to np. ponownego wyznaczania uruchamianego wyłącznie przez osobny supervisor albo importu iteracyjnego w PROCESSING. UI pokazuje wtedy tylko ogólny komunikat bez wskazania jobu (`apps/admin/src/features/model-quality/model-quality-workspace.tsx:802-807`). Propozycja: zwracać i wyświetlać typ lub identyfikator blokującego jobu albo odczytowo potwierdzić na danych operatora, że nie ma długo wiszących jobów tych typów.
- [P2-3] `apps/admin/src/features/model-quality/model-quality-workspace.tsx:242-246` — Po STALE wyjaśnienie „Dane zmieniły się…” pojawia się tylko wtedy, gdy nowy podgląd ma `canFreeze`. Jeśli nowy podgląd jest pusty albo zablokowany, operator widzi tylko „Brak wycinków…” i nie wie, że potwierdzenie odrzucono z powodu zmiany danych. Propozycja: ustawiać informację o odrzuceniu STALE niezależnie od wyniku `prepareCohort`.
- [P2-4] `services/api/src/game_predictor_api/storage/symbol_cell_training_source_repository.py:89-93` — Freeze wymaga teraz stanu katalogu `ready` i odrzuca brak wiersza stanu (`PROJECTION_NOT_READY`). Podgląd tego nie sprawdza, więc może pokazać `canFreeze`, a freeze skończy się ogólnym komunikatem z kodem. Propozycja: ten sam warunek w gotowości podglądu albo dedykowany komunikat w `model-quality-actions.ts`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Zmierzona przyczyna i ograniczone porównanie przed/po | spełnione (wg raportu, bez ponownego pomiaru) | `ai_docs/quality/TASK-1177_VERIFICATION.md`, sekcja „Performance limits”: 413→376 SQL, 1.229→1.180 s, inwentarz 12 s (deadline)→3.292 s |
| Mniej zbędnych SQL, krótsze sekcje blokad, zgodny wynik zapisów | spełnione | `image_symbol_review_bulk_operation_repository.py:406-417,536-574,628-645`; `symbol_training_board_owners.py:9-27`; `verified_training_cohorts.py:320-331`; test `test_symbol_review_performance_freeze_postgres.py` (2 rekonsyliacje na partię, replay bez zdarzeń) |
| Aktualne potwierdzenie manifestu, realne stale nadal blokuje | spełnione, z ryzykiem P2-1 | `verified_training_cohorts.py:326-339`; `symbol_cell_training_source_repository.py:113-156`; `test_verified_training_freeze_fence.py`; `test_full_cell_correction_postgres.py:174-179` |
| Czytelny konflikt/oczekiwanie i bezpieczny retry w Adminie | spełnione, z uwagami P2-3/P2-4 | `model-quality-actions.ts:639-660`; `model-quality-workspace.tsx:232-260`; `model-quality-loading.test.mjs:153-239` |
| Restart/utrata odpowiedzi/własność/holdouty/human approvals chronione | spełnione statycznie | `verified_training_cohorts.py:288-303,345-354`; `sequence_ownership_lock.py:122-158`; odcisk ochrony `symbol_cell_training_source_repository.py:100-110`; `test_sequence_ownership_lock.py:40-61` |
| API/OpenAPI/SDK zgodne, właściwe testy PG/UI i kontrole zaliczone | niespełnione | P1-1 (`API_CONTRACT.md:4728-4737`), P1-2 (brak testu `image_review_repository.py:713`); wyniki testów tylko deklarowane w raporcie wykonawcy |
| Opus i task-close przed commitem, P2 jawnie zapisane | niezweryfikowane | Ten audyt jest rundą 1; task-close i zapis P2 jeszcze nie nastąpiły |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P1-2, P2-1, P2-2, P2-3, P2-4.

## Proponowane testy

- `services/api/tests/test_image_review_repository_job_lock.py`: parametryzowany test dokładnego zbioru typów (`SYMBOL_TRAINING`, `IMAGE_SYMBOL_REVIEW_BULK`, `IMPORT`, `IMAGE_GRID_REINFERENCE`) i statusów (CREATED, PROCESSING) w skompilowanym zapytaniu `has_active_heavy_job`. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_review_repository_job_lock.py`.
- `services/api/tests/integration/test_symbol_review_performance_freeze_postgres.py`: `VerifiedTrainingCohortService.freeze` przy oczekującym jobie bulk zwraca `VERIFIED_TRAINING_COHORT_HEAVY_JOB_ACTIVE` i nie tworzy kohorty. Komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_symbol_review_performance_freeze_postgres.py`.
- Ten sam plik: pełny `freeze` przez serwis z prawdziwym repozytorium. Zmiana `recognized_boards.geometry_revision` albo właściciela fast document między poświadczeniem a fence'em daje STALE lub poprawnie odrzucony manifest. To potwierdza regułę z P2-1.
- `apps/admin/test-interactions/model-quality-loading.test.mjs`: STALE, po którym nowy podgląd ma `canFreeze=false`, nadal pokazuje informację o odrzuceniu (P2-3).

## Zakres przeglądu i ograniczenia

Przeczytałem cały zamrożony pakiet: task, wycinek planu, diff zmian śledzonych i nowe pliki. Przejrzałem też w repozytorium `verified_training_cohorts.py` (preview/freeze), `symbol_cell_training_source_repository.py` (fence, inventory, `_exclusion_counts`), `image_symbol_review_bulk_operation_repository.py` (`process_next_batch`, `_apply_board_targets`, `_record_board_error`, liczniki), `sequence_ownership_lock.py`, `image_review_repository.py` (`has_active_heavy_job`), fragmenty `image_symbol_review_repository.py` (`apply_board_mutations`, `_touch_catalog_revision`), `source_replacement_restore.py`, `grid_geometry_approvals.py`, `symbol_readability.py`, `main.py` (wspólna sesja serwisu), `model-quality-workspace.tsx`, `catalog-api-error.ts`, `API_CONTRACT.md` i `DEFINITION_OF_DONE.md`.

Nie uruchamiałem testów, lintu, typechecku, OpenAPI ani pomiarów. Liczby PASS i pomiary pochodzą wyłącznie z raportu wykonawcy. Nie sprawdzałem wszystkich ponad 30 pisarzy biorących blokadę własności pod kątem podbijania `catalog_revision` (P2-1). Nie widziałem planów EXPLAIN ani artefaktów `artifacts/task1177-*`. Nie znam rzeczywistej izolacji sesji API poza domyślną konfiguracją fabryki.