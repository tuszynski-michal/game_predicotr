# Audyt TASK-0996 — Trwały trening V3 w aplikacji

Werdykt: REVISE
Audytor: Codex, etykieta briefu `gpt-6-astra`, reasoning `high`
Wykonawca: `claude-opus-5-5`, reasoning `high`
Zakres: HEAD...9b6b25dce9a2670afb3b4abcbe8b3e1b88d1a6f5 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-16
Runda: 3

Przegląd statyczny, bez zmian w plikach. Audytor nie uruchamiał testów ani operacji zmieniających stan.

## Streszczenie

Sprawdzono poprawki po R2 oraz ich integrację z trenerem, magazynem jobów, checkpointami i eksportem. Naprawiono kolejność odzyskiwania checkpointu i dodano rezerwowanie kroków przed wykonaniem. Pozostają błędy rozliczenia przerwanej próby, przedwczesne potwierdzanie anulowania oraz luka między zwolnieniem dzierżawy GPU a publikacją wyniku. Otwarte P0 blokują commit.

## Znaleziska

### P0

- **[P0-2] `services/worker/src/game_predictor_worker/images/grid_training_handler.py:611` — Twarde przerwanie nadal zwraca budżet wykonanych, niepotwierdzonych kroków.** `_settle_steps()` jest wywoływane również bez wyniku końcowego albo dla wyniku watchdoga bez pola `steps`. Wtedy podstawą rozliczenia jest ostatni `progress.json`, aktualizowany najwyżej co dwie sekundy (`images/grid_training_child.py:183`). Przykładowo trener wykonał 104 kroki, zapisał postęp 100 i został zabity; rezerwacja 200 zostaje zmniejszona do 100. Cztery wykonane kroki znikają z trwałego budżetu. Rezerwację można zwolnić wyłącznie na podstawie wiarygodnego końcowego licznika zakończonej próby. Przy zabiciu procesu, awarii albo wyniku watchdoga należy zachować nierozliczoną rezerwację.

- **[P0-6] `services/worker/src/game_predictor_worker/images/grid_training_child.py:319` — Zwolnienie GPU poprzedza trwałą publikację wyniku, więc odzyskiwanie może przeoczyć gotowy eksport.** Trener usuwa dzierżawę, a dopiero w linii 320 zapisuje `result-<attempt>.json`. Nadzorca uznaje zwolnienie dzierżawy za zakończenie poprzedniej próby i jednorazowo odczytuje wynik (`images/grid_training_handler.py:242`, `:260`). Jeśli odczyt przypadnie między tymi operacjami, rozpocznie dopuszczenie nowego treningu; wyczerpany budżet zakończy job błędem mimo gotowego eksportu. Awaria przed zapisem wyniku pozostawia analogiczną lukę na kolejnych wznowieniach. Należy publikować wynik przed zwolnieniem dzierżawy oraz zapewnić odzyskanie zweryfikowanego, kompletnego eksportu po awarii między instalacją katalogu eksportu a zapisem wyniku, bez wymagania nowego budżetu treningowego.

- **[P0-7] `services/worker/src/game_predictor_worker/images/grid_training_handler.py:597` — Poprawka zatrzymuje trenera dopiero po potwierdzeniu `CANCELLED` w bazie.** Przy cancel między heartbeat a checkpointem magazyn nadal wywołuje `acknowledge_job_cancellation()` podczas zapisu postępu (`jobs/store.py:202`). Transakcja zapisuje stan końcowy i zwalnia lease; następnie kontekst zgłasza `_ExecutionStopped`, a handler dopiero zapisuje intencję i czeka na dziecko. API może więc pokazywać `CANCELLED` i przyjąć resume, gdy poprzedni trener nadal działa. Test `services/worker/tests/test_grid_training_handler.py:585` sprawdza zatrzymanie przed powrotem handlera, ale nie kolejność zmiany stanu w bazie. Dla treningu zapis postępu powinien zachować oczekujące żądanie cancel, a potwierdzenie nastąpić po zatrzymaniu dziecka i utrwaleniu końcowego checkpointu oraz budżetu.

- **[P0-8] `services/worker/src/game_predictor_worker/images/grid_training_handler.py:457` — Awaria przed pierwszym zapisem postępu pomija czas uruchomionej próby.** Stan `admitted` jest zapisywany z `chargedAt=None`, a następnie uruchamiany jest proces trenera. Znacznik czasu powstaje dopiero w `_supervise()` i trafia do bazy przy późniejszym `_persist()`. Jeśli nadzorca zakończy się po uruchomieniu dziecka, lecz przed tym zapisem, odzyskiwanie pomija naliczenie czasu, ponieważ warunek w linii 244 nie jest spełniony. Czas pracy dziecka do wykrycia utraty nadzorcy nie obciąża budżetu. Początek rozliczania próby należy utrwalić przed uruchomieniem procesu, z konserwatywną obsługą niepotwierdzonego startu.

### P1

Brak.

### P2

- **[P2-1] `ai_docs/tasks/0996-durable-v3-grid-training.md:145` — Opis E2E nie odpowiada aktualnemu wskazanemu artefaktowi.** Outcome podaje przerwanie przy kroku 103, wznowienie od 105 i budżet 700 kroków. Obecny `artifacts/audits/TASK-0996_GPU_E2E.json:7` zawiera odpowiednio 107, 115 i 985. Należy zaktualizować opis albo zachować osobne, jednoznacznie oznaczone dowody kolejnych przebiegów.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Odtwarzanie RNG, samplera i optymalizatora z poprawnego checkpointu | spełnione | `services/worker/src/game_predictor_worker/training_core/grid_training.py:333`; test porównawczy `services/worker/tests/test_durable_v3_grid_training.py:109`. Ocena statyczna. |
| Odzyskanie końcowego checkpointu poprzedniego trenera | spełnione | Odczyt postępu po oczekiwaniu: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:242`; regresja `services/worker/tests/test_grid_training_handler.py:521`. |
| Trwały budżet kroków i czasu | niespełnione | P0-2, P0-8. |
| Cancel/resume z potwierdzeniem po zatrzymaniu trenera | niespełnione | P0-7. |
| Idempotentna rejestracja wersji | spełnione | Deterministyczne identyfikatory i utrwalony deskryptor: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:152`, `:780`. |
| Odzyskanie gotowego eksportu po awarii | niespełnione | Odzyskiwanie istniejącego wyniku dodano, lecz pozostaje P0-6. |
| Uszkodzony wskazany checkpoint nie daje kandydata | spełnione | `services/worker/src/game_predictor_worker/images/grid_training_handler.py:439`; walidacja zawartości w `training_core/grid_training.py:334`. |
| Zgodna logika laboratorium i aplikacji | spełnione | Wspólne moduły i reeksporty; regresja `services/worker/tests/test_durable_v3_grid_training.py:345`. |
| Zamrożenie detektora i BatchNorm w grid-only | spełnione | `services/worker/src/game_predictor_worker/training_core/grid_training.py:82`, `:380`. |
| Wyniki kontroli i ograniczenia zapisane w Outcome | spełnione | `ai_docs/tasks/0996-durable-v3-grid-training.md:143`; niespójność dowodu wskazuje P2-1. |
| Dokumentacja odpowiada zachowaniu | niespełnione | Deklaracje trwałości i odzyskiwania ograniczają otwarte P0. |
| Brak automatycznej publikacji i aktywacji | spełnione | Rejestracja `not_evaluated`: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:712`. |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-5:** oczekiwanie na poprzedniego trenera poprzedza rozliczenie czasu i odczyt checkpointu — `services/worker/src/game_predictor_worker/images/grid_training_handler.py:241`. Test obejmuje checkpoint opublikowany podczas oczekiwania.
- **P0-1, P0-3, P0-4, P1-1, P1-2, P1-3:** pozostają zamknięte zgodnie z R2. Zachowano utrwalony deskryptor, watchdog, kontrolę integralności eksportu, checkpoint przy kontrolowanym przerwaniu, przypiętą recepturę i dokładną idempotencję tworzenia runu.

Otwarte: **P0-2, P0-6, P0-7, P0-8, P2-1**.

## Proponowane testy

W `services/worker/tests/test_grid_training_handler.py` dodać:

- Twarde zakończenie dziecka po wykonaniu kroków nowszych niż ostatni zapis postępu; nierozliczona rezerwacja musi pozostać obciążona.
- Awarię nadzorcy po uruchomieniu dziecka, przed pierwszym checkpointem postępu; wznowienie musi naliczyć niepotwierdzony czas.
- Zwolnienie GPU przed publikacją wyniku oraz awarię po utworzeniu eksportu, przed wynikiem; odzyskiwanie przy wyczerpanym budżecie nie może uruchamiać treningu ani odrzucać gotowego eksportu.

Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_training_handler.py`.

W `services/api/tests/integration/test_grid_training_lane_gpu_e2e_postgres.py` dodać przeplot cancel między heartbeat a checkpointem z rzeczywistym magazynem jobów. Osobna sesja powinna potwierdzić, że `CANCELLED` pojawia się dopiero po zatrzymaniu dziecka.

Komenda w zatwierdzonym środowisku testowym: `.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_training_lane_gpu_e2e_postgres.py`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, raport R2, task, właściwe fragmenty dokumentacji i planu oraz implementację nadzorcy, trenera, rdzenia treningowego, adaptera danych, API, migracji i powiązanych mechanizmów checkpointów, jobów oraz dzierżawy GPU. Sprawdzono testy poprawek, pion klienta API i aktualny artefakt E2E.

Nie uruchamiano testów, treningu, migracji ani usług. Wyniki wykonawcy nie zostały niezależnie odtworzone. Integracja `SqlGridTrainingStore` z PostgreSQL pozostaje ograniczeniem zapisanym w Outcome; test E2E korzysta z zastępczego magazynu katalogu.