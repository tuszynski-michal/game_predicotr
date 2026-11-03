---
title: Audyt krzyżowy TASK-1136
status: active
last_updated: 2026-11-03
---

# Audyt TASK-1136 — Awaria procesu treningowego

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...40581449aa35091a42ec263b87aadd13f7efaa4d oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem zmianę w `grid_training_child.py`: nowa gałąź `except Exception` w `run()` oraz osobny log diagnostyczny dla każdej próby w `main()`. Sprawdziłem też nowy test regresji, aktualizacje dokumentacji i to, jak nadzorca w `grid_training_handler.py` korzysta z wyniku procesu potomnego. Poprawka usuwa potwierdzony defekt. Niespodziewany wyjątek Python zapisuje teraz trwały wynik `failed` z osiągniętym krokiem, zanim zostanie zwolniony lease. Nadzorca obsługuje taki wynik tak samo jak inne kody `failed`: rozlicza kroki i rzuca `JobHandlerError`. Probe działa bez zmian. Pozostałe ryzyko dotyczy kompletności logu przy twardym zakończeniu procesu: log jest buforowany, a przekierowanie obejmuje tylko `sys.stderr` na poziomie Pythona. Task jawnie uznaje twarde zakończenie za ograniczenie, więc oba punkty mają wagę P2.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/images/grid_training_child.py:655` — Log `diagnostic-<attempt>.log` jest otwierany w trybie tekstowym z domyślnym buforowaniem blokowym. `faulthandler` pisze bezpośrednio do deskryptora, więc jego wpis przetrwa. Natomiast wcześniejsze wpisy Pythona z `sys.stderr` (ostrzeżenia, komunikaty bibliotek) zostają w buforze i giną, gdy proces kończy się natywnym crashem, zewnętrznym kill albo przez `os._exit(4)` z `Watchdog` (linia 289). To właśnie scenariusz typu nieodtworzonej pierwszej awarii, a w nim log będzie niekompletny lub pusty. Proponowana poprawka: otworzyć plik z `buffering=1` (buforowanie liniowe) albo wywoływać jawny `flush` po każdym zapisie, np. przez opakowanie strumienia. Alternatywnie zaakceptować ryzyko i opisać je w VISION_LAB.
- [P2-2] `services/worker/src/game_predictor_worker/images/grid_training_child.py:661` — `contextlib.redirect_stderr` podmienia tylko `sys.stderr`. Deskryptor 2 procesu nadal wskazuje na `DEVNULL` ustawiony przez nadzorcę (`services/worker/src/game_predictor_worker/images/grid_training_handler.py:168`). Komunikaty pisane natywnie na fd 2 (CUDA/cuDNN, `TORCH_WARN` z C++, komunikat CRT przy `abort`) nadal przepadają. VISION_LAB poprawnie pisze o „Python stderr”, ale Outcome taska („Osobny log stderr”) i ciąg testowy `native-library warning` (`services/worker/tests/test_grid_training_child_diagnostics.py:22`, wypisywany przez `print` w Pythonie) sugerują szersze pokrycie, niż jest naprawdę. Proponowana poprawka: na czas działania `run()` przekierować fd 2 na deskryptor logu przez `os.dup2`, z odtworzeniem w `finally`. Alternatywnie zawęzić opis w Outcome i nazwę komunikatu w teście do „Python stderr”.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Potwierdzony defekt obsługi błędu ma regresję; pierwsza awaria jawnie nieodtworzona, bez hipotetycznej przyczyny | spełnione | `services/worker/tests/test_grid_training_child_diagnostics.py:53`; task, sekcje Context i „Not completed” (brak przypisania OOM ani błędu danych) |
| Niespodziewany wyjątek Python zostawia diagnostykę i failed result per attempt przed release; probe bez zmian; twarde zakończenie jako ograniczenie | spełnione | `grid_training_child.py:329-342` (wynik zapisany przed `lease.release`), `grid_training_child.py:649-650` (probe przed odczytem spec), `services/worker/tests/test_grid_training_child_diagnostics.py:37`, `ai_docs/architecture/VISION_LAB.md:939-945` |
| Naprawa ma regresję odtwarzającą potwierdzony przypadek | spełnione | `services/worker/tests/test_grid_training_child_diagnostics.py:76-80` (`Lease.release` sprawdza istnienie `result-3.json` z kodem `GRID_TRAINING_UNEXPECTED_ERROR` i `steps == 12`), `:100-103` |
| Identyfikator, zamrożona kohorta i oryginalny budżet zachowane, bez automatycznej aktywacji | niezweryfikowane | Kod nie zmienia budżetu ani rejestracji. Stan rzeczywistego runu `5eeaac0b…` (próba 2, 4000/4000 kroków, 1149,282 s) jest tylko deklaracją w Outcome; nie da się go sprawdzić statycznie bez bazy |
| Scoped testy/lint/typecheck, docs/map, Opus i task-close rozliczone | niezweryfikowane (otwarte w tasku) | `artifacts/task1136-tests.log`: „46 passed, 2 warnings in 57.53s”. Wyniku ruff i mypy nie sprawdzałem. `CODE_MAP.md:130` (277 plików). `CODE_MAP_SYMBOLS.md:564` bez zmian, co jest poprawne, bo nie ma nowych symboli publicznych. Ten audyt to krok Opus. task-close jeszcze nie wykonany |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2.

## Proponowane testy

- Test podprocesu dla natywnego błędu: uruchomić `python -c` z `main()` na spec, w którym podmieniony `run` najpierw wypisuje linię na `sys.stderr`, a potem wywołuje `faulthandler._sigsegv()`. Sprawdzić, że `diagnostic-<attempt>.log` zawiera zrzut `faulthandler` oraz wcześniejszą linię stderr. Druga część potwierdzi lub obali P2-1. Plik: `services/worker/tests/test_grid_training_child_diagnostics.py`, komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_training_child_diagnostics.py`.
- Test nadzorcy: wynik `failed` z kodem `GRID_TRAINING_UNEXPECTED_ERROR` i `steps` niższym od rezerwacji powinien rozliczyć rezerwację przez `_settle_steps`, kończyć się `JobHandlerError` z tym kodem i zostawić run wznawialny. Plik: `services/worker/tests/test_grid_training_handler.py`.

## Zakres przeglądu i ograniczenia

Przeczytałem brief, plik taska, pełny diff zmian niezacommitowanych, nowy plik testów, `grid_training_child.py` (linie 1–400 i 600–676), fragmenty `grid_training_handler.py` (launcher, `_recover_previous_attempt`, `_train`, `_supervise`, `_settle_steps`), mapę komunikatów `apps/admin/src/features/model-quality/grid-model-state.ts`, odpowiednie sekcje `AGENTS.md`, końcówkę `artifacts/task1136-tests.log` oraz wpis w `CODE_MAP_SYMBOLS.md`. Nie uruchamiałem testów, ruff, mypy ani `npm run docs:check`. Nie sprawdzałem stanu rzeczywistego runu w PostgreSQL ani plików w jego katalogu. Deklaracje o diagnostyce na rzeczywistych danych (CPU 9,77 s, CUDA 5,28 s, partie 388–600) i o próbie 2 przyjmuję jako niezweryfikowane deklaracje wykonawcy.
