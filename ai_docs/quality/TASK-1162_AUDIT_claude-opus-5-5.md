# Audyt TASK-1162: routing zapisu w CLI rejestracji diagnostyk

Werdykt: PASS

- **Audytor:** claude-opus-5-5/high, Runda 1 (pierwsza runda, nie focused review).
- **Baza:** `119f4716` / v1.7.568, worktree `full-board-detection`.
- **Zakres:** pakiet `artifacts/task1162-audit/part-01.txt` i `part-02.txt`. Zawiera skrypt `scripts/register_grid_diagnostics.py`, nowy test PG/CLI, `game_storage_routing.py`, `database.py`, `diagnostic_registration.py`, plik zadania i weryfikację. Dodatkowo celowo zajrzałem w jedno miejsce poza pakietem: wyszukałem `lock_timeout` w `_application_role_database.py`.
- **Charakter:** wyłącznie przegląd statyczny (Read/Grep). Nic nie zmieniłem, nie uruchamiałem testów, shella, usług ani bazy. Pliku planu nie zapisałem, bo zamiast planu zwracam raport.

## P0 / P1

Brak.

## Ocena merytoryczna

- **Kolejność w transakcji jest poprawna** (`scripts/register_grid_diagnostics.py:47-50`). Najpierw `SET LOCAL statement_timeout` (10 s) i `lock_timeout` (3 s), potem jawne `GameStorageRouter().bind(..., WRITE)`, a dopiero na końcu SQL capability.
  - Zwykły `Session` nie ma listenerów `GameStorageSession`. Dzięki temu `SET LOCAL` nie wywołuje przedwczesnego bind i oczekiwanie na blokadę w routerze podlega limitowi 3 s. Wcześniejsza luka z PGOPTIONS jest zamknięta.
  - `game_storage_scope` jest tu tylko kontekstem nadmiarowym i niczego nie psuje.
- **Ochrona zapisu pochodzi z istniejącego routera.** Router pobiera wspólną blokadę advisory (`hashtextextended(game, 519)`), czyta wiersz rejestru przez `FOR SHARE` i sprawdza `_require_writable`. Potem lokalnie ustawia `search_path`, `game_predictor.game_id` i generację. Nie ma surowego `set_config`, obejścia przez właściciela ani `expected_generation`. Bez `expected_generation` jest bezpiecznie, bo blokada fence i wiersz `FOR SHARE` trzymają lokalizację do commita.
- **Role się nie mieszają.** `create_database_engine` łączy się przez `database_url` roli aplikacyjnej. URL właściciela jest w env subprocessu (wymaga go zapewne konfiguracja), ale CLI z niego nie korzysta.
- **Atomowość i trwałość.** Jeden `session.begin()` obejmuje wszystkie requesty, a każdy wyjątek cofa całą transakcję. Komunikat sukcesu drukuje się dopiero po commicie. Utrata odpowiedzi po commicie jest obsłużona ponowieniem: manifest się nie zmienia, więc klucze idempotencji (`uuid5`) są te same. `require_registration` ponownie wylicza manifest i odrzuca każdą rozbieżność.
- **Historia bez zmian.** Format manifestu, klucze idempotencji, sygnatura funkcji SQL, schemat i API pozostają takie jak w T6.
- **Test rzeczywiście odtwarza regresję** (`test_diagnostic_registration_cli_postgres.py:121,136,147`). Przed poprawką każde wywołanie kończyłoby się `GAME_STORAGE_SCOPE_REQUIRED`, więc:
  - asercja komunikatu maintenance by nie przeszła,
  - asercja `"lock timeout"` by nie przeszła,
  - `first.returncode == 0` by nie przeszło.
- **Test blokady sprawdza limit samego CLI.** Klucz blokady jest identyczny jak w routerze (`str(UUID)`, 519). Bez `lock_timeout` w CLI subprocess przekroczyłby swój limit 15 s i test by padł. `PGOPTIONS` jest usunięte (`:80`), a helper nie ustawia `lock_timeout` na poziomie roli ani bazy. Ustawia tylko `statement_timeout` dla silnika provisioningu, nie dla roli aplikacyjnej (`_application_role_database.py:151`).

## P2 (nieblokujące)

1. **Receipt przy ponowieniu nie jest sprawdzany.**
   - Gdzie: `scripts/register_grid_diagnostics.py:62` odrzuca wynik `scalar_one()`, a test (`:147-149`) porównuje tylko wiersze `recording_evidence`.
   - Skutek: AC2 („ledger/receipt”) jest pokryte tylko po stronie ledgera. Zmiana receipt przy ponowieniu nie zostałaby wykryta.
   - Minimalna poprawka: CLI wypisuje kanoniczny JSON receiptów (albo ich digest), a test sprawdza, że `first.stdout == replay.stdout`. Alternatywnie test wywołuje funkcję drugi raz w sesji roli aplikacyjnej i porównuje wynik.
2. **Atomowość partii nie jest sprawdzona na kilku requestach.**
   - Gdzie: test stage'uje jeden rekord (`:72`).
   - Skutek: AC3 („atomowo”) jest pokryte tylko dla odmowy, która następuje przed pierwszym requestem. Rollback częściowej partii nie jest odtworzony.
   - Minimalna poprawka: dwa rekordy w manifeście, a po sukcesie i ponowieniu dokładnie dwa wpisy. Opcjonalnie wywołać błąd na drugim requeście i sprawdzić, że ledger jest pusty.
3. **Brak limitu całej transakcji.**
   - Gdzie: `scripts/register_grid_diagnostics.py:48-49` ograniczają tylko pojedynczą instrukcję.
   - Skutek: przy limicie 250 requestów transakcja może trwać około 250 × 10 s i tyle czasu trzymać wspólny fence oraz `FOR SHARE`, blokując cutover. To zachowanie istniało już w T6, poprawka go nie wprowadza.
   - Minimalna poprawka: `SET LOCAL transaction_timeout` (PostgreSQL 17+) albo `idle_in_transaction_session_timeout`, ustawione przed bind.
4. **Błędy wychodzą jako surowy traceback.**
   - Gdzie: wyjątki z `:47-62` nie są przechwytywane, a test (`:121-138`) szuka podciągów w treści tracebacku.
   - Skutek: nie ma stabilnego kodu wyjścia ani kodu błędu dla operatora, a asercje są kruche.
   - Minimalna poprawka: przechwycić `GameStorageRoutingError` i `DBAPIError`, wypisać `code` lub `SQLSTATE` (np. `55P03`) i zakończyć z ustalonym kodem wyjścia. Test sprawdza wtedy kod błędu.
5. **Typowanie sprawdzone powierzchownie.**
   - Gdzie: mypy uruchomiono z `--follow-imports skip`, a skrypt ma `# type: ignore[import-not-found]` (`:9`).
   - Skutek: typy wywołań routera i ustawień nie są realnie sprawdzone. Ryzyko jest niskie, bo kod jest krótki.
   - Minimalna poprawka: przy okazji uruchomić mypy na tym pliku z normalnym podążaniem za importami pakietów API i workera.

## Pokrycie kryteriów

| AC | Ocena statyczna |
|---|---|
| AC1: realne CLI jako applicationRole w świeżym procesie | Pokryte. Subprocess z prawdziwymi `get_settings` i `create_database_engine` na URL roli aplikacyjnej, bez mocków. Migracji 0181 nie mogłem zweryfikować. |
| AC2: dokładne ponowienie bez duplikatów | Ledger pokryty (jeden wpis, identyczne id/payload/digest/actor). Receipt nie jest porównywany (P2-1). |
| AC3: maintenance i fence blokują zapis, brak obejścia | Pokryte. `migrating` daje odmowę bez zapisu, wyłączny fence daje lock timeout bez zapisu. Rollback partii nie jest odtworzony (P2-2). |
| AC4: testy, lint, docs, mapa, audyt | Logów nie widziałem. Zmian w guide, CURRENT_STATE i CODE_MAP nie ma w pakiecie, więc ich nie sprawdziłem. Ten audyt nie ma otwartych P0/P1. Task-close pozostaje osobnym krokiem. |

## Status uwag

- **Zamknięte:**
  - routing WRITE przed SQL capability,
  - kolejność timeoutów względem bind (wcześniej maskowana przez PGOPTIONS),
  - użycie roli aplikacyjnej bez obejścia przez właściciela,
  - zgodność manifestu i idempotencji z T6,
  - realne odtworzenie regresji w teście.
- **Otwarte (tylko P2):** pozycje 1–5 powyżej.

## Proponowane testy

1. Porównanie stdout lub receiptów między pierwszym wywołaniem a ponowieniem.
2. Manifest z dwoma rekordami: dokładnie dwa wpisy, a przy błędzie w środku partii zero wpisów.
3. Ponowienie z innym `--actor`, żeby udokumentować zachowanie funkcji SQL. Ma to znaczenie dla ponowienia przez root requestów zarejestrowanych wcześniej obejściem.
4. Asercja SQLSTATE `55P03` zamiast podciągu w tracebacku (jeśli wejdzie P2-4).

## Ograniczenia

- Przegląd był wyłącznie statyczny. Nie wykonałem żadnych testów, a wyników wykonawcy (1 PASS / 29.75 s) nie traktowałem jako dowodu.
- Poza pakietem są i nie zostały sprawdzone: ciało funkcji `public.recording_diagnostic_use_v1`, RLS i uprawnienia capability, `application_role_database` (poza celowanym wyszukaniem), `scope()` z `test_grid_correction_registry_postgres`, fixture T1, diff docs/mapy/guide oraz rejestracja 32 rekordów operatora wykonana przez root obejściem.
- Nie czytałem danych operatora, zdjęć, `.env` ani sekretów.
