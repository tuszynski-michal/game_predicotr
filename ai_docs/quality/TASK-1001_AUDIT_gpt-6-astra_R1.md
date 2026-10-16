# Audyt TASK-1001 - Odbiór procesu i instrukcja operatora

Werdykt: REVISE
Audytor: gpt-6-astra, medium
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...eb2126294ef4854634c434d46b0573b2bba8c34a oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-16
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono test odbiorowy, zmiany regresji, parity ONNX, obsługę lane GPU i dokumentację operatora. Test odbiorowy jawnie rozdziela rzeczywisty trening od oceny przez atrapy, a dostępne artefakty potwierdzają raportowane wyniki wybranych kontroli. Zatrzymywanie lane GPU ma błąd zależny od konfiguracji nowego procesu, a instrukcja nieprawidłowo opisuje automatyczne zapisy ponownego rozpoznania.

## Znaleziska

### P0

- [P0-1] `scripts/manage_worker_lanes.ps1:156` — `Get-TargetLaneNames` pomija `grid-training`, gdy bieżący proces nie potrafi odnaleźć interpretera CUDA. Funkcja obsługuje również status (`:583`) i zatrzymywanie (`:694`). Po uruchomieniu lane przez `-GridTrainingPython`, bez zmiennej użytkownika i lokalnego `.venv-vision-lab`, późniejsze `npm run workers:status` nie pokaże tego workera, a `npm run workers:stop` go nie zatrzyma. Skrypt może zgłosić zatrzymanie wszystkich widocznych lane, mimo nadal działającego treningu. Ograniczyć filtr dostępności interpretera do akcji `Start`; `Status` i `Stop` muszą uwzględniać wszystkie lane i zapisane procesy niezależnie od konfiguracji CUDA nowego wywołania. Dodać regresję tego scenariusza.

### P1

- [P1-1] `ai_docs/guides/V3_GRID_FINE_TUNING_OPERATOR.md:89` — instrukcja przedstawia wyniki ponownego rozpoznania jako propozycje wymagające przyjęcia przez człowieka. Kontrakt planu, sekcja 2.5, oraz `ai_docs/requirements/ADMIN_APP.md:2064` rozróżniają propozycje i zapisy automatyczne: odroczone sloty oraz niechronione automatyczne plansze mogą zostać zapisane po bramkach bez dodatkowego zatwierdzenia. Operator wykonujący opisany przebieg otrzymuje więc błędną informację o skutkach uruchomienia. Opisać osobno zgłoszoną „Złą siatkę”, cele chronione i cele dopuszczające zapis automatyczny; uwzględnić wymagany pilot oraz osobne potwierdzenie szerszego zakresu.

### P2

- [P2-1] `ai_docs/guides/V3_GRID_FINE_TUNING_OPERATOR.md:30` — wspólny opis `workers:start` i `workers:start:all` sugeruje taki sam zestaw lane. W `package.json:125` pierwsze polecenie uruchamia tylko `general`; drugie uruchamia także `image-selection` oraz warunkowo `grid-training`. Rozdzielić opisy poleceń, aby instrukcja jednoznacznie wskazywała uruchamiane workery.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Proces działa po restarcie i utracie odpowiedzi | niezweryfikowane | `services/api/tests/integration/test_v3_grid_fine_tuning_acceptance_postgres.py:240` obejmuje ponowienia; `:459` uruchamia nowy interpreter. Artefakt `artifacts/audits/T1001_e60de9c93059/result.json` potwierdza zakończony trening i odczyt modelu po restarcie. Nie uruchamiano testu podczas audytu; pozostaje P0-1 dotyczące zarządzania procesami. |
| Obie gry i nowa gra zachowują izolację symboli | niezweryfikowane | Zaktualizowano manifest testów izolacji: `services/api/tests/integration/test_per_game_isolation_new_game.py:90`. Pełnego zachowania izolacji nie odtwarzano podczas przeglądu statycznego. |
| Stara 777 ma regresję | spełnione | Istnieje wskazany test `services/api/tests/integration/test_historical_grid_acceptance_postgres.py:376`; raport odbioru wskazuje również regresje resolvera i aktywacji w `ai_docs/quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md:119`. |
| Rzeczywiste liczby i ograniczenia opisano bez domniemanych wyników | spełnione | Raport ujawnia atrapy oceny i syntetyczne dane. Odczyt `result.json` potwierdza 1200 kroków, 351,3 s i 0 detekcji po restarcie; `pg_final.xml` potwierdza 241 testów, 1 porażkę i 4 pominięcia. |
| Kontrole, audyt i ograniczenia w Outcome; dokumentacja odpowiada zachowaniu | niespełnione | Wyniki i ograniczenia zapisano w Outcome; zgodność instrukcji z zachowaniem naruszają P1-1 i P2-1. Bieżący raport wymaga dołączenia przez wykonawcę. |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1, P1-1, P2-1.

## Proponowane testy

- Dodać izolowany test skryptu `scripts/manage_worker_lanes.ps1`: start lane z interpreterem przekazanym wyłącznie parametrem, następnie status i stop z nowego procesu bez tego parametru. Użyć atrap procesów i konfiguracji, bez uruchamiania usług operatora. Proponowany plik: `scripts/tests/manage_worker_lanes.Tests.ps1`; komenda: `Invoke-Pester -Path .\scripts\tests\manage_worker_lanes.Tests.ps1`.
- W tym samym teście sprawdzić, że brak interpretera pomija GPU wyłącznie dla `Start -Lane all`, natomiast jawny `Start -Lane grid-training` zgłasza błąd.

## Zakres przeglądu i ograniczenia

Przeczytano brief, aktywne zadanie, właściwe fragmenty planu, wymagania, architekturę, D-561, dokumentację odbioru oraz zmienione fragmenty kodu i testów. Sprawdzono także wybrane zapisane artefakty wykonania. `git diff --check` zakończył się kodem 0.

Nie uruchamiano testów, treningu, migracji ani usług. Zapisane wyniki wykonawcy nie zastępują niezależnego wykonania kontroli. Audyt nie potwierdza jakości modeli na danych operatora ani odbioru aplikacji w przeglądarce; te ograniczenia są jawnie opisane w dokumentacji.