# Audyt TASK-1005 - Preset i dopuszczenie zasobów

Werdykt: REVISE
Audytor: gpt-6-astra, medium
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...f0cfa9bdf2deaf0e5abdf7970624bd5575f10dc7 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-16
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono presety, dopuszczenie zasobów, serializację budżetu, dzierżawę GPU, smoke oraz pion API podglądu. Podstawowe blokady i zachowanie budżetu przy wznowieniu mają pokrycie testowe. Poprawek wymagają obsługa uszkodzonego rekordu dzierżawy oraz nadzór czasu i cyklu życia smoke.

## Znaleziska

### P0

- [P0-1] `services/worker/src/game_predictor_worker/training_core/gpu_lease.py:132` — Konstruktor `LeaseRecord` nie waliduje typów pól JSON. Rekord z poprawnym `format`, ale `expires_at: null` lub tekstem przechodzi `_read`, a porównanie w `_state` rzuca nieobsługiwany `TypeError`. W rezultacie podgląd API kończy się błędem 500 zamiast stanem `unknown` i blokerem `GRID_RUN_LEASE_UNKNOWN`. Należy walidować typy, zakresy i skończoność wartości rekordu oraz zamieniać błędy walidacji na kontrolowany błąd dzierżawy, bez usuwania pliku.

- [P0-2] `services/worker/src/game_predictor_worker/vision_lab/grid_training_smoke.py:101` — Watchdog nie pilnuje limitu 120 sekund treningu. Po pierwszym kroku kontroluje wyłącznie 630 sekund od rozpoczęcia runu. Jeśli kolejny `next(stream)` lub operacja CUDA zablokuje się, sprawdzenie limitu w pętli treningowej nie zostanie wykonane i smoke może przekroczyć dozwolony czas treningu o kilka minut. Należy nadzorować także termin treningu liczony od pierwszego kroku, z jawnie ustaloną tolerancją watchdog.

- [P0-3] `services/worker/src/game_predictor_worker/vision_lab/grid_training_smoke.py:109` — Uruchomiony watchdog nigdy nie zostaje zatrzymany. Po powrocie `run_smoke`, również po wyjątku, wątek nadal działa i ostatecznie wykonuje `os._exit(124)`. Przy wywołaniu funkcji z dłużej działającego procesu zakończy ten proces oraz może nadpisać raport zakończonego pomiaru. Należy użyć sygnału zakończenia i zatrzymać watchdog w `finally`, przed powrotem funkcji.

### P1

Brak.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/training_core/gpu_lease.py:204` — `release` z obcym tokenem kończy się bez błędu, podczas gdy kontrakt zapisany w tasku przewiduje `GRID_RUN_LEASE_LOST` zarówno dla odnowienia, jak i zwolnienia. Obca dzierżawa pozostaje chroniona, lecz utrata własności jest niewidoczna dla wywołującego. Należy ujednolicić implementację i test z kontraktem albo jawnie udokumentować idempotentne zwolnienie jako przyjętą semantykę.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Brak GPU, niezgodny runtime, zajęta dzierżawa lub brak zatwierdzonego presetu blokuje run | spełnione | `services/worker/src/game_predictor_worker/training_core/grid_training_admission.py:400`; przypadki blokad w `services/worker/tests/test_grid_training_resource_admission.py:134` |
| Resume nie odnawia budżetu | spełnione | `services/worker/tests/test_grid_training_resource_admission.py:189` i `:206`; implementacja zachowuje zapisane zużycie |
| Wyniki kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | niespełnione | Outcome zawiera deklarowane wyniki kontroli i ograniczenia; rozbieżności zachowania opisują P0-1, P0-2 i P2-1. Wynik bieżącego audytu pozostaje do zapisania przez wykonawcę |
| Smoke przestrzega limitów doprecyzowanych w D-557 | niespełnione | `services/worker/src/game_predictor_worker/vision_lab/grid_training_smoke.py:101`; P0-2 |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P0-1, P0-2, P0-3, P2-1.

## Proponowane testy

W `services/worker/tests/test_grid_training_resource_admission.py` dodać:

- Rekord dzierżawy z `expires_at` równym `null`, tekstem i wartością nieskończoną: `observe` zwraca `unknown`, przejęcie jest blokowane, plik pozostaje bez zmian.
- Zablokowany krok po pierwszym kroku: watchdog respektuje termin treningu niezależnie od terminu całego runu.
- Sukces i wyjątek z `_measure`: po zakończeniu `run_smoke` watchdog nie nadpisuje raportu ani nie wywołuje zakończenia procesu.
- Zwolnienie obcym tokenem zgodnie z ostatecznie przyjętym kontraktem.

W `services/api/tests/test_grid_training_run_preview.py` dodać przypadek semantycznie uszkodzonego JSON dzierżawy: odpowiedź 200, stan `unknown`, właściwy bloker.

Polecenie po poprawkach:

`.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_training_resource_admission.py services/api/tests/test_grid_training_run_preview.py`

Kontrole czasu wykonać z kontrolowanym zegarem i atrapami, bez GPU i rzeczywistego oczekiwania na pełne limity.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task i jego Outcome, fragment planu, zmiany wymagań i architektury, D-557 oraz implementację i testy wskazanego pionu. Sprawdzono także wrapper klienta i wygenerowaną operację SDK.

Nie uruchamiano testów, smoke, usług ani operacji zapisujących dane. Wyniki testów i pomiaru GPU w Outcome są deklaracjami wykonawcy, nie niezależnie odtworzonymi wynikami audytora. Trwały zapis budżetu w encji runu oraz integracja z handlerem pozostają zakresem TASK-0996 zgodnie z udokumentowanym podziałem prac.