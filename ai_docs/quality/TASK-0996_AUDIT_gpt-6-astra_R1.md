# Audyt TASK-0996 - Trwały trening V3 w aplikacji

Werdykt: REVISE
Audytor: Codex, etykieta briefu `gpt-6-astra`, reasoning `high`
Wykonawca: `claude-opus-5-5`, reasoning `high`
Zakres: HEAD...9b6b25dce9a2670afb3b4abcbe8b3e1b88d1a6f5 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-16
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie uruchamiał testów ani operacji zmieniających stan.

## Streszczenie

Zbadano trener, nadzorcę, checkpointy, budżet, eksport, API, migrację oraz testy i dokumentację zadania. Implementacja zawiera mechanizmy odtwarzania stanu, lecz pozostawia błędy w rozliczaniu wznowień i odzyskiwaniu eksportu. Nie zapewnia też deklarowanego zatrzymania osieroconego trenera podczas operacji blokujących. Otwarte znaleziska P0 i P1 blokują commit.

## Znaleziska

### P0

- [P0-1] `services/worker/src/game_predictor_worker/images/grid_training_handler.py:553` — **Ponowienie instalacji zależy od bieżącej daty.** Pole `frozenOn` powstaje ponownie przy każdym `_descriptor()`. Awaria po instalacji katalogu, ale przed utrwaleniem `registered`, a następnie wznowienie następnego dnia tworzą inny manifest dla tej samej wersji. `_install()` odrzuci istniejący katalog przez porównanie manifestu i receiptu, mimo niezmienionego eksportu. Należy utrwalić cały deskryptor albo jego datę przed instalacją i odtwarzać dokładnie tę samą treść.

- [P0-2] `services/worker/src/game_predictor_worker/images/grid_training_handler.py:458` — **Powtórzone kroki nie zużywają budżetu.** `reserved_steps` jest maksimum globalnego numeru kroku, zamiast sumą wykonanych lub zarezerwowanych kroków wszystkich prób. Przykładowo po wykonaniu 500 kroków bez checkpointu wznowienie od zera ponownie wykonuje pierwsze 500 kroków bez zwiększania licznika. Dodatkowo przekazane w specyfikacji `remainingSteps` nie jest egzekwowane przez trenera. Należy oddzielić pozycję samplera od kumulatywnego zużycia budżetu i trwale rezerwować ograniczoną liczbę kroków każdej próby.

- [P0-3] `services/worker/src/game_predictor_worker/images/grid_training_child.py:113` — **Zatrzymanie po utracie nadzorcy działa tylko między krokami.** Kontrola czasu i heartbeat występuje wyłącznie w `before_step()`. Nie obejmuje przygotowania danych, zablokowanego batcha, walidacji ani eksportu. Po śmierci nadzorcy proces może więc działać znacznie dłużej niż deklarowane 60 sekund, trzymając dzierżawę GPU. Tymczasem `_charge_downtime()` nalicza najwyżej 70 sekund. Potrzebny jest niezależny watchdog obejmujący cały czas życia procesu oraz zgodne z nim rozliczanie czasu.

- [P0-4] `services/worker/src/game_predictor_worker/images/grid_training_child.py:325` — **Odzyskiwanie istniejącego eksportu może zalegalizować uszkodzony ONNX.** Ścieżka ponowienia sprawdza tylko identyfikator checkpointu w `bundle.json`, po czym `_export_view()` oblicza nowe sumy aktualnych plików. Jeśli przed ponowieniem uszkodzono `board.onnx` lub `screen.onnx`, nowe sumy trafią do deskryptora, a historyczny wynik parity pozostanie zachowany. Inspektor rejestru porównuje pliki z tymi nowymi sumami, więc nie wykryje takiego uszkodzenia. Należy porównywać odzyskiwane pliki z utrwalonymi sumami eksportu, w tym `bundle.files`, i odrzucać rozbieżności przed instalacją.

### P1

- [P1-1] `services/worker/src/game_predictor_worker/training_core/grid_training.py:346` — **Cancel nie zapisuje checkpointu zatrzymania.** `TrainingInterrupted` opuszcza pętlę bez zapisu aktualnego modelu, optymalizatora i RNG. Checkpoint powstaje dopiero przy okresowej ocenie. Cancel przed pierwszą oceną pozostawia wznowienie od bazy; późniejszy cancel traci pracę od poprzedniej oceny. Jest to sprzeczne z kontraktem taska „trener kończy po checkpoincie”. Należy obsłużyć kontrolowane przerwanie na granicy kroku, zapisać i opublikować checkpoint, a dopiero potem potwierdzić zatrzymanie.

- [P1-2] `services/worker/src/game_predictor_worker/images/grid_training_child.py:218` — **Nie jest egzekwowana zatwierdzona receptura D.** Trener pobiera recepturę z `training-base/preset.json` wybranej bazy i sprawdza jedynie zgodność bajtów z jej deskryptorem. Nie porównuje jej z zamrożonym odciskiem presetu D wymaganym w `ai_docs/tasks/0996-durable-v3-grid-training.md:75`. Historyczna baza 777 ma preset A, więc różnica nie jest wyłącznie hipotetyczna. Należy jawnie przypiąć zatwierdzoną recepturę D i sprawdzać jej odcisk niezależnie od integralności plików bazy.

- [P1-3] `services/api/src/game_predictor_api/application/grid_training_runs.py:65` — **Idempotencja tworzenia runu obejmuje tylko ostatnie 200 jobów i nie jest atomowa względem klucza.** Starszy klucz wypada z wyszukiwania i może zostać użyty z inną kohortą. Dwa równoległe żądania z tym samym kluczem i różnymi kohortami również mogą przejść kontrolę: `input_key` obejmuje cały payload, więc ograniczenie jego unikalności nie chroni samego klucza idempotencji. Należy wyszukiwać dokładny klucz bez ograniczenia listy oraz serializować jego użycie w bazie, zachowując konflikt dla innej treści.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Odtwarzanie RNG, samplera i optymalizatora z checkpointu | spełnione | Ścieżka odtworzenia w `services/worker/src/game_predictor_worker/training_core/grid_training.py:333`; test porównawczy w `services/worker/tests/test_durable_v3_grid_training.py:108`. Ocena statyczna. |
| Trwały budżet i obsługa cancel/resume | niespełnione | P0-2, P0-3 i P1-1. |
| Odzyskanie tej samej wersji po awarii eksportu i instalacji | niespełnione | P0-1; istniejący test `services/worker/tests/test_grid_training_handler.py:284` używa stałej daty. |
| Uszkodzony wskazany checkpoint nie daje kandydata | spełnione | Kontrola SHA w `services/worker/src/game_predictor_worker/images/grid_training_handler.py:374`; test w `services/worker/tests/test_grid_training_handler.py:303`. Ocena statyczna. |
| Zgodna logika laboratorium i aplikacji oraz zatwierdzona receptura | niespełnione | Wspólne moduły i reeksporty istnieją, lecz brakuje kontroli receptury opisanej w P1-2. |
| Zamrożenie detektora i BatchNorm w grid-only | spełnione | `services/worker/src/game_predictor_worker/training_core/grid_training.py:82` oraz ponowne zastosowanie w `:350`. |
| Integralność odzyskiwanego eksportu | niespełnione | P0-4. |
| Wyniki kontroli i ograniczenia zapisane w Outcome | spełnione | `ai_docs/tasks/0996-durable-v3-grid-training.md:142` i `:151`; są to deklaracje wykonawcy, bez ponownego uruchamiania kontroli. |
| Dokumentacja odpowiada zachowaniu | niespełnione | Rozbieżności dotyczą zatrzymania trenera, checkpointu przy cancel i receptury: P0-3, P1-1, P1-2. |
| Brak automatycznej publikacji i aktywacji | spełnione | Rejestracja `not_evaluated` w `services/worker/src/game_predictor_worker/images/grid_training_handler.py:578`. |

## Listy zamknięte i otwarte

Zamknięte: Brak. Pierwsza runda audytu.

Otwarte: P0-1, P0-2, P0-3, P0-4, P1-1, P1-2, P1-3.

## Proponowane testy

- W `services/worker/tests/test_grid_training_handler.py`: awaria po instalacji i po zatwierdzeniu rejestracji, wznowienie następnego dnia; wielokrotne wznowienie z checkpointu starszego niż rozliczony postęp. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_training_handler.py`.
- W `services/worker/tests/test_grid_training_child.py`: odzyskanie eksportu z uszkodzonym ONNX; odrzucenie niezatwierdzonej receptury z poprawną sumą pliku. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_training_child.py`.
- W `services/worker/tests/test_durable_v3_grid_training.py`: cancel między ocenami, checkpoint dokładnie na granicy zatrzymania i kontynuacja z zachowanym stanem. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_durable_v3_grid_training.py`.
- Dodać ograniczony test podprocesu z krótkimi limitami: utrata nadzorcy podczas zablokowanego batcha, walidacji i eksportu. Sprawdzić zakończenie procesu oraz możliwość odzyskania dzierżawy.
- W `services/api/tests/test_grid_training_runs.py` oraz teście integracyjnym PostgreSQL: ponowienie klucza starszego niż 200 jobów i równoległe żądania z tym samym kluczem, ale różnymi kohortami. Test integracyjny wykonać wyłącznie na izolowanej bazie `*_test`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task, odpowiednie fragmenty planu i dokumentacji oraz implementację nadzorcy, trenera, danych, checkpointów, eksportu, API i migracji. Sprawdzono również powiązane mechanizmy rejestru, dzierżawy, runtime jobów, klienta API i testy.

Nie uruchamiano testów, treningu, migracji, usług ani operacji na danych. Wyniki PASS przytoczone w Outcome pozostają deklaracjami wykonawcy. Istniejący test wznowienia tworzy nowe obiekty w tym samym procesie; nie potwierdza pełnego przebiegu po restarcie nadzorcy i rzeczywistego procesu trenera.