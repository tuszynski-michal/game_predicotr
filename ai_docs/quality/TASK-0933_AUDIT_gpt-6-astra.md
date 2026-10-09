# Audyt TASK-0933 — Wyprowadzanie serii supergry i API serii

Werdykt: REVISE
Audytor: Codex (etykieta briefu: gpt-6-astra, high)
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...190644853b2db51d8e53137cc5704c6d0cb6ab99 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 3

Przegląd statyczny, bez zmian w plikach. Audytor nie uruchamiał testów ani operacji zmieniających stan.

## Streszczenie

Poprawka usuwa niespójny odczyt parametrów przy inicjalizacji generacji. Ograniczenie wyjątku cleanupu do zakolejkowanych jobów nie usuwa jednak wyścigu między sprawdzeniem blokad a rozpoczęciem joba. Dodatkowo odpowiedź plansz serii może połączyć poprzednią generację z informacją o świeżości nowej generacji.

## Znaleziska

### P0

- **[P0-4] `services/api/src/game_predictor_api/storage/cleanup_repository.py:123` — Sprawdzenie statusu joba nie zabezpiecza resetu przed jego późniejszym startem.** Zapytanie `count(*)` pomija job `created`, ale nie blokuje jego przejęcia. Worker może zmienić go na `processing` po sprawdzeniu: `claim_next` blokuje wiersz joba, nie wiersz gry (`services/worker/src/game_predictor_worker/jobs/store.py:81`). Reset nadal usuwa dane przed zablokowaniem stanu supergry (`cleanup_repository.py:273`). Przykładowy przeplot: po korekcie usuwającej ostatni trigger istnieją stara seria i zakolejkowany job; reset blokuje grę i przepuszcza sprawdzenie, worker rozpoczyna pustą generację, a publikacja blokuje stan i próbuje zapisać audyt usunięcia serii (`super_game_series_repository.py:660`, `:677`). FK audytu do gry czeka na blokadę resetu, natomiast reset przy podbiciu wersji czeka na stan. Pozostaje deadlock oraz ryzyko rollbacku resetu po usunięciu plików (`services/api/src/game_predictor_api/application/cleanup.py:332`). Należy zsynchronizować końcowe sprawdzenie i cały reset z przejmowaniem joba, np. blokując pomijane wiersze jobów do końca transakcji, albo zastosować wspólną blokadę wyłączającą równoległe wykonanie. Nowe testy sprawdzają oddzielnie stany `created` i `processing`, ale nie przejście między nimi podczas resetu.

- **[P0-5] `services/api/src/game_predictor_api/application/super_game_series.py:446` — `fresh` może dotyczyć innej generacji niż zwracana seria.** `boards()` odczytuje serię w linii 421, dokumenty w linii 425, a stan dopiero przy budowaniu odpowiedzi. Sesja używa READ COMMITTED, bez wspólnego snapshotu lub blokady publikacji. Jeśli między tymi odczytami worker opublikuje generację usuwającą albo przedłużającą serię, odpowiedź zawiera poprzednią serię i jej zakres, lecz `fresh = true` oraz wersję nowej generacji. Operator otrzymuje więc nieaktualne dane oznaczone jako świeże. Należy odczytywać serię, dokumenty i stan ze wspólnego snapshotu albo wykrywać zmianę generacji i ponawiać odczyt. Taką samą spójność należy zapewnić dla listy, która odczytuje stan i serie osobnymi zapytaniami (`:383`, `:388`).

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

Ocena „spełnione” oznacza potwierdzenie statyczne, bez uruchamiania testów.

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Trigger i retriggery tworzą jedną przedłużaną serię | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:352` |
| Brak planszy nie skraca serii; odpowiedź oznacza `missing` | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:362`, `services/api/src/game_predictor_api/application/super_game_series.py:441` |
| Koniec poza ostatnią znaną planszą oznacza `incomplete` | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:371` |
| Trigger lub retrigger wymagający predykcji oznacza `unverified` | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:357` |
| Zachowanie symbolu i rewizji; audyt utraty lub pochłonięcia triggera | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:381` |
| Retrigger 40 000 zapisuje się i odczytuje | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:421` |
| Restart nie ujawnia roboczej generacji | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:448` |
| Zmiana wejścia odrzuca kandydata i pozostawia jeden ponowny przebieg | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:480`, `:1093` |
| Odpowiedź serii poprawnie informuje o nieaktualności do publikacji | niespełnione | P0-5: `services/api/src/game_predictor_api/application/super_game_series.py:446` |
| Punkty zapisu transakcyjnie podbijają wersję, także przy usunięciu danych | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:990`, `:1011` |
| Zmiana rekordu o niskiej rewizji jest wykrywana | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:502` |
| Nieaktualne `expectedRevision` nie powoduje zapisu | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:537` |
| Bramka własności klasyfikuje nowe tabele | niezweryfikowane | Pełna bramka manifestu pozostaje poza ograniczonym zakresem tej rundy |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-3** — `begin_generation` blokuje stan przed odczytem wersji i parametrów: `services/api/src/game_predictor_api/storage/super_game_series_repository.py:486`. Test dwóch sesji potwierdza oczekiwanie zapisu katalogu, odrzucenie kandydata i poprawny kolejny przebieg: `services/api/tests/integration/test_super_game_series_postgres.py:1093`.
- **P0-1, P0-2, P1-1, P1-2** — pozostają zamknięte zgodnie z poprzednim raportem: `ai_docs/quality/TASK-0933_AUDIT_gpt-6-astra.md:55`.

Otwarte: **P0-4, P0-5**.

## Proponowane testy

- W `services/api/tests/integration/test_cleanup_repository.py` dodać test dwóch sesji: zatrzymać reset po sprawdzeniu joba `created`, następnie przejąć job przez produkcyjny `claim_next` i wznowić reset. Sprawdzić brak deadlocka i brak usunięcia artefaktów przy odrzuconej operacji.
- W `services/api/tests/integration/test_super_game_series_postgres.py` zatrzymać `boards()` po odczycie serii, opublikować generację usuwającą lub przedłużającą tę serię, następnie dokończyć odpowiedź. Stara seria nie może otrzymać stanu świeżości nowej generacji.
- Po poprawkach uruchomić na jednorazowej bazie PostgreSQL, z jawnym limitem czasu: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`, następnie `.\\.venv\\Scripts\\python.exe -m pytest services/api/tests/integration/test_cleanup_repository.py services/api/tests/integration/test_super_game_series_postgres.py -q`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, poprzedni raport, task z Outcome, odpowiednie fragmenty wymagań, planu i architektury. Sprawdzono pliki wskazane w briefie oraz powiązane granice transakcji, konfigurację sesji, przejmowanie jobów i blokady potrzebne do oceny opisanych przeplotów.

Brief nie zawierał fragmentu planu; odczytano właściwą sekcję bezpośrednio. Wyniki testów podane przez wykonawcę nie były odtwarzane. Nie wykonywano migracji, benchmarków ani zmian plików. Wydajność dla 500 000 pozycji pozostaje niezweryfikowana.

## Nota leada po rundzie 3 (2026-10-09)

Oba P0 rundy 3 naprawione przez wykonawcę: wyłączenie joba wyprowadzania z blokady czyszczenia usunięte w całości (job blokuje jak każdy inny; nowy test PG: zakolejkowany job blokuje reset, a podbicie po resecie kolejkuje nowe wyprowadzenie), a `list()`, `boards()` i `state()` czytają w jednym snapshocie `REPEATABLE READ` (`begin_read_snapshot`, test PG publikujący generację w trakcie odczytu). PG 37 PASS, bramka jakości zielona. Commit bez czwartej rundy zgodnie z regułą szybkiego audytu w `AGENTS.md`.
