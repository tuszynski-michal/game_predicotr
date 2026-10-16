# Audyt TASK-1005 - Preset i dopuszczenie zasobów

Werdykt: PASS
Audytor: gpt-6-astra, medium
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...f0cfa9bdf2deaf0e5abdf7970624bd5575f10dc7 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-16
Runda: 2

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono poprawki po rundzie 1 oraz presety, dopuszczenie zasobów, budżet, dzierżawę GPU, smoke i podgląd API. Poprawki zamykają wcześniejsze znaleziska: walidują rekord dzierżawy, nadzorują czas treningu, zatrzymują watchdog i sygnalizują utratę dzierżawy przy zwolnieniu. Nie stwierdzono otwartych P0 ani P1 w sprawdzonym zakresie.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Brak GPU, niezgodny runtime, zajęta dzierżawa lub brak zatwierdzonego presetu blokuje run | spełnione | `services/worker/src/game_predictor_worker/training_core/grid_training_admission.py:400`; testy blokad w `services/worker/tests/test_grid_training_resource_admission.py:134` |
| Resume nie odnawia budżetu | spełnione | `services/worker/tests/test_grid_training_resource_admission.py:189` oraz `:206`; dopuszczenie zachowuje zapisane zużycie |
| Wyniki kontroli i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | spełnione | `ai_docs/tasks/1005-grid-training-resource-admission.md:121`, `:140`, `:155`; zapisano wynik R1 i poprawki. Niniejszy raport R2 pozostaje do dołączenia przez wykonawcę |
| Smoke przestrzega limitów doprecyzowanych w D-557 | spełnione | `services/worker/src/game_predictor_worker/vision_lab/grid_training_smoke.py:80`; test granic startu, treningu i runu w `services/worker/tests/test_grid_training_resource_admission.py:424` |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1:** walidacja pól rekordu odrzuca niepoprawne typy i wartości nieskończone; błędny rekord pozostaje na dysku. Dowód: `services/worker/src/game_predictor_worker/training_core/gpu_lease.py:66`; regresje w `services/worker/tests/test_grid_training_resource_admission.py:383`.
- **P0-2:** watchdog sprawdza termin treningu od pierwszego zakończonego kroku, z tolerancją 30 sekund. Dowód: `services/worker/src/game_predictor_worker/vision_lab/grid_training_smoke.py:80`; test w `services/worker/tests/test_grid_training_resource_admission.py:424`.
- **P0-3:** `finally` zatrzymuje watchdog przed zwolnieniem dzierżawy i powrotem funkcji. Dowód: `services/worker/src/game_predictor_worker/vision_lab/grid_training_smoke.py:172`; testy w `services/worker/tests/test_grid_training_resource_admission.py:444` oraz `:457`.
- **P2-1:** zwolnienie obcego lub brakującego rekordu zgłasza `GRID_RUN_LEASE_LOST`. Dowód: `services/worker/src/game_predictor_worker/training_core/gpu_lease.py:223`; testy w `services/worker/tests/test_grid_training_resource_admission.py:261` oraz `:403`.

Otwarte: Brak.

## Proponowane testy

Brak dodatkowych testów wymaganych do zamknięcia zgłoszonych uwag. Dodane regresje obejmują poprawione zachowania.

## Zakres przeglądu i ograniczenia

Przeczytano brief, raport R1, task i Outcome, fragment planu, D-557, zmiany wymagań i architektury oraz implementację i testy wskazanego pionu. Sprawdzono również przeniesienie identyfikacji procesu, wrapper klienta i obecność wygenerowanego kontraktu podglądu.

Nie uruchamiano testów, smoke, usług ani poleceń zmieniających stan. Wyniki kontroli i pomiaru GPU zapisane w Outcome są deklaracjami wykonawcy, nie wynikami niezależnie odtworzonymi przez audytora. Trwały zapis budżetu i integracja z handlerem pozostają zakresem TASK-0996, a mapowanie metryk early stopping — TASK-0997.