# Audyt TASK-1047 - Trwały job `source_crop` z API

Werdykt: REVISE
Audytor: gpt-6.1-sol / high (oznaczenie z briefu)
Wykonawca: claude-opus-5-5 / high (według briefu)
Zakres: HEAD...a793c14e77030bab3455be8dd1b48853f183f334 oraz zmiany niezacommitowane i nowe pliki TASK-1047, data 2026-10-17
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano migrację, API, OpenAPI, klienta, worker, adapter `jpegtran` i testy względem taska, planu oraz D-562. Podstawowy przebieg zawiera wymagane kontrole pikseli i tożsamości oryginału. Implementacja ma jednak luki w trwałości zapisu i synchronizacji stanów, które mogą pozostawić rejestr bez plików, zablokować następne przebiegi lub zgłosić pozorny sukces ponowienia.

## Znaleziska

### P0

- [P0-1] `services/worker/src/game_predictor_worker/source_crop.py:485`, `services/worker/src/game_predictor_worker/source_crop.py:596`, `services/api/src/game_predictor_api/storage/source_crop_run_repository.py:231` — Zapisy plików, rejestru i postępu nie sprawdzają aktualnego `lease_token`. Kontrola dzierżawy przez `context.checkpoint` następuje dopiero po tych operacjach. Po wygaśnięciu dzierżawy i przejęciu joba przez drugi worker stary wykonawca może wznowić pracę po wcześniejszym odczycie rejestru, usunąć opublikowany crop albo nadpisać nowszy checkpoint. Należy powiązać mutacje z aktualną dzierżawą i zabezpieczyć publikację oraz cleanup plików przed równoległym wykonawcą tego samego bloba. Sama unikalność aktywnego przebiegu nie rozwiązuje tego przypadku.

- [P0-2] `services/worker/src/game_predictor_worker/source_crop.py:713`, `services/worker/src/game_predictor_worker/source_crop.py:720` — Każdy wyjątek z `record_if_still_eligible` powoduje usunięcie cropu i atestu. Jeżeli COMMIT w bazie powiedzie się, ale odpowiedź połączenia zginie, wyjątek nie oznacza wycofania transakcji. Cleanup usunie wtedy pliki wskazane przez istniejący wiersz `verified`. Późniejsze przetwarzanie pomija taki wiersz bez sprawdzania plików (`source_crop.py:548`). Po niejednoznacznym wyniku zapisu trzeba uzgodnić stan z bazą, a przy braku możliwości odczytu zachować pliki do uzgodnienia.

- [P0-3] `services/worker/src/game_predictor_worker/source_crop.py:322`, `services/api/src/game_predictor_api/storage/source_crop_run_repository.py:253` — Stan przebiegu jest synchronizowany z anulowaniem wyłącznie przez wyjątek z działającego handlera. Anulowanie joba w stanie `created` przez ogólne API zmienia tylko `jobs`; handler już się nie uruchomi. Podobnie odzyskanie wygasłej dzierżawy z żądaniem anulowania kończy job bez wywołania handlera. Przebieg pozostaje `planning`, `created` lub `processing` i nadal blokuje następne przez `uq_source_crop_runs_active`. Należy synchronizować te przejścia atomowo przy zmianie stanu joba, również podczas recovery.

- [P0-4] `services/worker/src/game_predictor_worker/source_crop.py:341`, `services/worker/src/game_predictor_worker/source_crop.py:467` — Ogólne ponowienie joba `failed` lub `cancelled` nie przywraca odpowiedniego stanu przebiegu. Przykładowo po `SOURCE_CROP_TOOL_UNAVAILABLE` run pozostaje `failed`; po instalacji narzędzia i retry handler natychmiast wraca, a runtime oznacza job jako `completed` bez wykonania cropów. Analogicznie zachowuje się ponowiony plan. Należy obsłużyć retry wraz ze stanem przebiegu i zachowaniem checkpointu albo jawnie odmawiać takiego ponowienia stabilnym błędem.

- [P0-5] `services/api/src/game_predictor_api/application/source_crop_runs.py:129`, `services/worker/src/game_predictor_worker/cli.py:562` — API przyjmuje `kind="original_deletion"` i tworzy aktywny przebieg z jobem `source_original_deletion`, ale worker nie rejestruje handlera tego typu. Ponieważ pobiera tylko typy zarejestrowanych handlerów, taki job pozostaje w kolejce, a przebieg blokuje także przycinanie. Do wdrożenia TASK-1048 należy odrzucać ten rodzaj przed utworzeniem joba i przebiegu; przygotowanie tabeli oraz enumów może pozostać.

### P1

- [P1-1] `services/worker/src/game_predictor_worker/images/jpegtran.py:76` — Sprawdzenie wersji akceptuje dowolny napis zaczynający się od `libjpeg-turbo version `. Nie wymusza zatwierdzonej wersji 3.2.0 ani zgodności z inną jawnie skonfigurowaną wersją, czego wymaga R7. Binarium innej wersji może więc utworzyć crop oznaczony `verified`. Należy porównywać odczytaną wersję z wersją oczekiwaną i dodać test odrzucenia niezgodnej wersji przed zapisem cropu.

- [P1-2] `services/worker/src/game_predictor_worker/images/jpegtran.py:24` — Timeout pojedynczego wywołania wynosi 60 sekund, podczas gdy R8 zaakceptowanego planu określa 30 sekund. Task nie zapisuje odstępstwa dla tego limitu. Należy ustawić 30 sekund i sprawdzić przekazanie tej wartości do `subprocess.run` oraz obsługę `TimeoutExpired`.

- [P1-3] `services/worker/tests/test_source_crop_job.py:473`, `services/api/tests/integration/test_source_crop_runs_postgres.py:192` — Test wznowienia wywołuje ponownie ten sam handler z tymi samymi repozytoriami w pamięci. Test PostgreSQL używa kontekstu zastępczego, który nie wykonuje operacji dzierżawy. Brakuje wymaganej weryfikacji trwałości w nowym procesie, z odzyskaniem joba i stanem odczytanym z bazy. Należy dodać test przerwania przed checkpointem i po publikacji plików, a następnie wznowienia przez nowy proces, oraz przypadek utraconego potwierdzenia COMMIT.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Migracja upgrade/downgrade na `*_test`, odmowa downgrade z historią | niezweryfikowane | Implementacja: `services/api/alembic/versions/0168_source_crop_runs.py:56`, `:142`; test: `services/api/tests/integration/test_source_crop_runs_postgres.py:80`. Nie uruchamiano migracji ani testu. |
| Manifest kwalifikacji, liczniki powodów | spełnione | Statycznie: paginacja i manifest w `services/worker/src/game_predictor_worker/source_crop.py:350`, `:386`; test liczników w `services/worker/tests/test_source_crop_job.py:336`. |
| Zweryfikowane cropy, atest, wiersz `verified`, niezmienione oryginały | niespełnione | Kontrole pikseli i atest są w `services/worker/src/game_predictor_worker/source_crop.py:649`; P0-1 i P0-2 naruszają trwałą spójność plików z rejestrem. |
| Wznowienie bez duplikatów; błąd weryfikacji jednego bloba nie zatrzymuje przebiegu | niespełnione | Kontynuację po błędzie pokrywa `services/worker/tests/test_source_crop_job.py:441`; trwałość wznowienia blokują P0-1, P0-4 i P1-3. |
| HTTP preview/start/get, potwierdzenie, stale token, aktywny run; OpenAPI i klient | spełnione | Dla rodzaju `crop`, statycznie: `services/api/tests/test_source_crop_runs_api.py:137`, `:164`, `:186`; SDK `packages/admin-api-client/src/generated/sdk.gen.ts:7092`; wrapper `packages/admin-api-client/src/index.ts:2883`; test żądania `packages/admin-api-client/test/source-crop-runs-request.test.mjs:5`. |
| Lint, mypy, testy API/workera i PostgreSQL przechodzą | niezweryfikowane | `ai_docs/tasks/1047-source-crop-job.md:121` — brak wyników w `Outcome`; audyt nie uruchamiał kontroli. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak. Runda 1.

Otwarte: P0-1, P0-2, P0-3, P0-4, P0-5, P1-1, P1-2, P1-3.

## Proponowane testy

- W `services/api/tests/integration/test_source_crop_runs_postgres.py` dodać przejęcie wygasłej dzierżawy przez drugi worker, wznowienie starego wykonawcy oraz potwierdzenie, że nie zmienia on plików ani postępu. Dodać restart w nowym procesie i utratę odpowiedzi po skutecznym COMMIT.
- W tym samym pliku dodać anulowanie obu faz przed pobraniem joba, anulowanie podczas recovery oraz retry po błędzie narzędzia. Sprawdzić stan joba, przebiegu i możliwość utworzenia następnego przebiegu. Komenda po poprawkach, przy włączonych izolowanych testach PostgreSQL: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_source_crop_runs_postgres.py`.
- W `services/worker/tests/test_source_crop_job.py` dodać testy niezgodnej wersji narzędzia i timeoutu 30 sekund. Komenda: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_source_crop_job.py`.
- W `services/api/tests/test_source_crop_runs_api.py` sprawdzić odmowę nieobsługiwanego rodzaju bez utworzenia joba i aktywnego przebiegu. Komenda: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_source_crop_runs_api.py`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task, właściwe reguły planu i D-562, dokumentację dotyczącą cropów oraz implementację migracji, repozytoriów, API, workera i adaptera. Sprawdzono testy, odpowiednie fragmenty OpenAPI i wygenerowanego klienta, wrapper oraz istniejące mechanizmy anulowania, ponawiania i odzyskiwania dzierżaw.

Był to wyłącznie przegląd statyczny. Nie zmieniano plików, nie uruchamiano testów, narzędzi jakości, migracji, usług ani jobów na danych operatora. Obecność testów i wygenerowanych artefaktów nie stanowi potwierdzenia ich przejścia ani aktualności generatora.