# Audyt TASK-0996 — Trwały trening V3 w aplikacji

Werdykt: REVISE
Audytor: Codex, etykieta briefu `gpt-6-astra`, reasoning `high`
Wykonawca: `claude-opus-5-5`, reasoning `high`
Zakres: HEAD...9b6b25dce9a2670afb3b4abcbe8b3e1b88d1a6f5 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-16
Runda: 2

Przegląd statyczny, bez zmian w plikach. Audytor nie uruchamiał testów ani operacji zmieniających stan.

## Streszczenie

Sprawdzono poprawki znalezisk R1 oraz ich współdziałanie z nadzorcą, trenerem, eksportem i API. Naprawiono utrwalanie deskryptora, kontrolę receptury, integralność odzyskiwanego eksportu i wyszukiwanie klucza idempotencji. Pozostają błędy rozliczania przerwanej próby, kolejności odzyskiwania stanu, odzyskania ukończonego eksportu oraz potwierdzania anulowania. Otwarte znaleziska P0 blokują commit.

## Znaleziska

### P0

- [P0-2] `services/worker/src/game_predictor_worker/images/grid_training_handler.py:388` — **Budżet nadal pomija kroki przerwanej próby bez nowego checkpointu.** Odzyskiwanie zwiększa licznik wyłącznie po przyjęciu nowszego checkpointu. Przykładowo baza zawiera rozliczone 100 kroków, a `progress.json` potwierdza 150, ale wskazuje ten sam wcześniejszy checkpoint. Po awarii obu procesów albo wymuszonym zakończeniu trenera funkcja wraca przed rozliczeniem dodatkowych 50 kroków. Kolejna próba otrzymuje zawyżone `remainingSteps`. Poprawka R1 zapewnia sumowanie kroków już rozliczonych, lecz nie zapewnia trwałego rozliczania pracy niepotwierdzonej. Należy oddzielić odzyskiwanie zużycia od przyjmowania checkpointu oraz trwale rezerwować ograniczone porcje kroków przed wykonaniem.

- [P0-5] `services/worker/src/game_predictor_worker/images/grid_training_handler.py:415` — **Checkpoint i czas poprzedniej próby są odzyskiwane przed zakończeniem poprzedniego trenera.** `_adopt_orphan_checkpoint()` wykonuje się przed `_admit()`, które dopiero w linii 331 czeka na zwolnienie GPU. Jeżeli trener opublikuje checkpoint podczas tego oczekiwania, nowa próba go nie odczyta i wznowi starszy stan. Również `_charge_downtime()` jest wywoływane wcześniej, w linii 214, i zeruje `charged_at`; dalszy czas działania starego trenera podczas oczekiwania pozostaje nienaliczony. Należy najpierw potwierdzić zakończenie poprzedniej próby, następnie odczytać jej końcowy postęp/checkpoint i rozliczyć pełny niepotwierdzony przedział, a dopiero potem przygotować nową specyfikację.

- [P0-6] `services/worker/src/game_predictor_worker/images/grid_training_handler.py:219` — **Gotowy eksport może stać się nieodzyskiwalny po awarii nadzorcy.** Gdy trener zapisał eksport i `result-<attempt>.json`, ale nadzorca nie utrwalił jeszcze `state.export`, ponowienie bezwarunkowo przechodzi przez dopuszczenie nowej próby treningowej. Nie odczytuje wyniku poprzedniej próby. Jeżeli rozliczenie czasu po restarcie wyczerpie budżet, `_admit()` odmówi wykonania mimo kompletnego eksportu wymagającego już tylko instalacji i rejestracji. Należy przed dopuszczeniem kolejnego treningu odzyskać i zweryfikować wynik zakończonej próby oraz utrwalić eksport. Odzyskanie gotowego wyniku nie powinno wymagać nowego budżetu treningowego.

- [P0-7] `services/worker/src/game_predictor_worker/images/grid_training_handler.py:533` — **Wyścig anulowania pozwala potwierdzić `CANCELLED`, zanim trener się zatrzyma.** Jeżeli żądanie cancel pojawi się po `context.heartbeat()`, lecz przed `_persist()`, lokalne `cancel_requested` pozostaje fałszywe. Tymczasem `services/worker/src/game_predictor_worker/jobs/store.py:202` automatycznie potwierdza anulowanie przy zapisie checkpointu, a kontekst przerywa handler. Nie powstaje `cancel.intent` i nie ma oczekiwania na zakończenie dziecka; trener może pracować aż do wykrycia nieaktualnego heartbeat. Należy zapewnić zapis postępu bez przedwczesnego potwierdzania cancel oraz potwierdzać anulowanie dopiero po zakończeniu procesu i zachowaniu jego końcowego checkpointu.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Odtwarzanie RNG, samplera i optymalizatora z przekazanego checkpointu | spełnione | `services/worker/src/game_predictor_worker/training_core/grid_training.py:333`; test porównawczy `services/worker/tests/test_durable_v3_grid_training.py:109`. Ocena statyczna. |
| Wznowienie z ostatniego poprawnego checkpointu po utracie nadzorcy | niespełnione | P0-5. |
| Trwały budżet oraz obsługa cancel/resume | niespełnione | P0-2, P0-5, P0-7. |
| Odzyskanie jednej wersji po awarii eksportu | niespełnione | Utrwalony deskryptor i deterministyczne ID chronią przed duplikatem, lecz P0-6 blokuje część odzyskań. |
| Uszkodzony wskazany checkpoint nie daje kandydata | spełnione | `services/worker/src/game_predictor_worker/images/grid_training_handler.py:416`; walidacja zawartości w `training_core/grid_training.py:334`. |
| Integralność odzyskiwanego eksportu | spełnione | `services/worker/src/game_predictor_worker/images/grid_training_child.py:490`. |
| Zgodna logika laboratorium i aplikacji, zatwierdzona receptura | spełnione | Wspólne moduły i reeksporty; `services/worker/src/game_predictor_worker/images/grid_training_child.py:324`; test zgodności w `services/worker/tests/test_durable_v3_grid_training.py:345`. |
| Zamrożenie detektora i BatchNorm w grid-only | spełnione | `services/worker/src/game_predictor_worker/training_core/grid_training.py:82` oraz `:380`. |
| Wyniki kontroli i ograniczenia zapisane w Outcome | spełnione | `ai_docs/tasks/0996-durable-v3-grid-training.md:142` i `:156`. Wyniki wykonawcy nie były ponownie uruchamiane. |
| Dokumentacja odpowiada zachowaniu | niespełnione | Deklarowane zachowanie odzyskiwania i anulowania ograniczają P0-2, P0-5, P0-6 i P0-7. |
| Brak automatycznej publikacji i aktywacji | spełnione | Rejestracja `not_evaluated`: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:638`. |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1:** deskryptor zostaje utrwalony przed instalacją i odtworzony przy ponowieniu — `services/worker/src/game_predictor_worker/images/grid_training_handler.py:706`.
- **P0-3:** dodano watchdog niezależny od granic kroków — `services/worker/src/game_predictor_worker/images/grid_training_child.py:193`. Odrębny błąd rozliczania podczas oczekiwania opisuje P0-5.
- **P0-4:** odzyskiwane pliki są porównywane z zapisanymi sumami — `services/worker/src/game_predictor_worker/images/grid_training_child.py:490`.
- **P1-1:** kontrolowane przerwanie pętli publikuje checkpoint bieżącego kroku — `services/worker/src/game_predictor_worker/training_core/grid_training.py:370`. Integrację odzyskiwania i anulowania ograniczają P0-5 oraz P0-7.
- **P1-2:** receptura D ma przypięty odcisk i kontrolę zgodności bazy — `services/worker/src/game_predictor_worker/images/grid_training_child.py:324`.
- **P1-3:** dokładne wyszukiwanie klucza i blokada transakcyjna zastępują przeszukiwanie ostatnich 200 jobów — `services/api/src/game_predictor_api/application/grid_training_runs.py:69`, `services/api/src/game_predictor_api/storage/grid_training_run_jobs.py:15`.

Otwarte: **P0-2, P0-5, P0-6, P0-7**.

## Proponowane testy

W `services/worker/tests/test_grid_training_handler.py` dodać:

- Odzyskanie po awarii z postępem nowszym niż rozliczenie w bazie, ale bez nowego checkpointu; powtórzone kroki muszą ponownie zużywać budżet.
- Publikację checkpointu podczas oczekiwania na zakończenie starego trenera; nowa specyfikacja musi zawierać ten checkpoint i pełne rozliczenie czasu.
- Awarię po zapisaniu wyniku eksportu, przed utrwaleniem `state.export`, z budżetem wyczerpanym podczas odzyskiwania; istniejący eksport powinien zostać zarejestrowany bez nowego treningu.
- Cancel pomiędzy heartbeat a zapisem postępu; status końcowy może zostać potwierdzony dopiero po zatrzymaniu dziecka i zapisaniu checkpointu.

Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_training_handler.py`.

Wyścig cancel należy dodatkowo pokryć rzeczywistym `JobExecutionContext` i magazynem jobów, ponieważ obecny kontrolowany moment anulowania nie odtwarza tego przeplotu.

## Zakres przeglądu i ograniczenia

Przeczytano brief, raport R1, task, właściwe fragmenty dokumentacji i planu oraz implementację nadzorcy, trenera, rdzenia treningowego, adaptera danych, API, migracji i powiązanych mechanizmów checkpointów, jobów, dzierżawy GPU i rejestru. Sprawdzono testy poprawek, pion klienta API oraz zapisany dowód E2E GPU.

Nie uruchamiano testów, treningu, migracji ani usług. Dowód E2E potwierdza opisany przebieg wykonawcy, ale nie obejmuje wskazanych przeplotów awarii i anulowania. Integracja `SqlGridTrainingStore` z PostgreSQL pozostaje ograniczeniem jawnie zapisanym w Outcome.