# Audyt TASK-0967 — Cofnięcie korekty istniejącej planszy

Werdykt: PASS
Audytor: Codex, etykieta briefu `gpt-6-astra`, reasoning `high`
Wykonawca: `claude-opus-5-5`, reasoning `high`
Zakres: HEAD...25a7c099c10a11da7dec6be86aa56c2505e8d362 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 2

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono implementację przypadku A oraz poprawki sześciu znalezisk poprzedniego audytu. Odtwarzanie zatwierdzeń i silnika uwzględnia wcześniejsze cofnięcia, a przywrócenie decyzji komórek porównuje zatwierdzone piksele z wynikiem renderera. Zmieniony plan określa zasady przenoszenia zatwierdzenia geometrii i blokowania przez przypięte dane. Nie stwierdzono otwartych P0 ani P1; pozostają dwa ograniczenia P2.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:412` — **Pierwsze cofnięcie do geometrii importu korzysta z zastępczego weryfikatora.** `_RecordedRenderVerifier` zwraca zapisane checksumy, ponieważ fixture rewizji 0 nie zawiera renderowalnej specyfikacji. Test sprawdza przywrócenie danych, lecz nie integrację rzeczywistego renderera z manifestem importu. Zalecane uzupełnienie o renderowalną rewizję 0 i `VirtualRestoredRenderVerifier`; do tego czasu odnotować ograniczenie pokrycia.

- [P2-2] `ai_docs/architecture/DATA_MODEL.md:1307` — **Opis manifestu zawiera sprzeczne reguły.** Początek akapitu wymaga dosłownej równości dokumentów `virtual_render_spec` rewizji przywracanej i nowej, natomiast późniejszy opis oraz implementacja dopuszczają nowe checksumy pikseli. Należy opisać jeden obowiązujący kontrakt: kopiowanie specyfikacji komórek i aktualizację checksum pikseli według ponownego renderowania.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Przywrócenie `grid_issue`, widoku `correction`, geometrii i zatwierdzenia zgodnie z doprecyzowanym kontraktem | spełnione | `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:425`, `:462`, `:746` |
| Wycofanie symboli D-488; zatwierdzenia wracają wyłącznie dla identycznych pikseli | spełnione | `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:1381`; testy przy `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:316` i `:834` |
| Odmowa `GEOMETRY_REVERT_REOPENED_RESOLUTION` bez zapisu | spełnione | `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:964` |
| Drugie cofnięcie odmawia; nowa korekta zapisuje `N + 2` | spełnione | `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:474` |
| Porównanie liczników, wyszukiwarki i bramki ze stanem sprzed korekty w teście PG | spełnione | Porównanie tabel: `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:280`; wywołania przy `:425` i `:738` |

Status „spełnione” oznacza zgodność ustaloną statycznie i obecność odpowiednich asercji. Wykonania testów nie potwierdzano niezależnie.

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1:** metadane zatwierdzenia są odczytywane również z audytu wcześniejszego cofnięcia — `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:1942`; regresja kolejnego cyklu przy `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:761`.
- **P0-2:** historia zatwierdzenia pochodzi z kompletnego zapisu o zgodnej tożsamości; brak dowodu powoduje odmowę — `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:2259`; test przy `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:871`.
- **P0-3:** cofnięcie wywołuje renderer i porównuje jego wynik z historią zatwierdzenia — `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:1120` i `:1381`; test zmiany wyniku renderera przy `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:778`.
- **P0-4:** doprecyzowany plan zezwala na przeniesienie zatwierdzenia przywracanej geometrii na `N + 1` — `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md:182`; zgodne asercje przy `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:746`.
- **P0-5:** silnik rewizji utworzonej przez cofnięcie pochodzi z jego migawki audytowej — `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:1906`; regresja przy `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:495`.
- **P1-1:** plan określa wyjątek dla zachowywanego renderu, a implementacja sprawdza tożsamość renderu lub oczekiwaną rewizję — `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md:124`, `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:377`; testy przy `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:814`.

Otwarte: P2-1, P2-2.

## Proponowane testy

- W `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py` dodać cofnięcie pierwszej korekty do rzeczywiście renderowalnego manifestu importu. Zweryfikować checksumy, przywrócone zatwierdzenia i odczyt podglądu komórki.

Komenda na dedykowanej bazie testowej:

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_geometry_correction_revert_board_postgres.py -q
```

## Zakres przeglądu i ograniczenia

Przeczytano brief, poprzedni raport, task i `Outcome`, odpowiednie fragmenty planu, decyzje D-462/D-467/D-488, dokumentację oraz zmienione moduły i testy. Sprawdzono odtwarzanie historii, renderowanie, warunki odmowy, idempotencję, projekcje i zapis audytu.

Nie uruchamiano testów, migracji, usług ani operacji na bazie. Wyniki PG, lint i mypy pozostają deklaracjami wykonawcy. `git rev-parse HEAD` potwierdził hash briefu; `git diff --check` nie zgłosił błędów białych znaków. Raportu nie zapisano na dysku zgodnie z zakazem zmian plików.