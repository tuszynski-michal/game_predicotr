Werdykt: PASS

**Audyt TASK-1155: audytor claude-opus-5-5/high, Runda 1**

- **Baza:** `codex/full-board-detection` @ `0a7ef2d3` plus niezacommitowane zmiany TASK-1155.
- **Zakres:** pakiet `artifacts/audits/TASK1155-scoped-review.md`, czyli task, plan T1, 3 moduły, 3 pliki testów, kontekst i dokumentacja. Do tego celowane odczyty `storage/database.py:203-216`, `storage/game_storage_routing.py:176-215,408-421` i `storage/source_replacement_guards.py:42-51`.
- **Tryb:** tylko przegląd statyczny. Niczego nie zmieniłem, nie uruchomiłem testów, usług ani bazy. Numery linii liczyłem względem bloków kodu w pakiecie.

### P0 / P1
Brak.

### P2 (5)

1. **Zastąpione źródło przerywa cały odczyt readiness.**
   - **Miejsce:** `services/api/src/game_predictor_api/storage/grid_diagnostic_readiness.py:18-27` i `:106`.
   - **Problem:** zapytanie wybierające źródła nie pomija źródeł z `source_replacement_retired`. Takie źródło zachowuje swoje `recognized_boards`, bo przy wymianie źródła nic ich nie usuwa. Następnie `capture()` zgłasza błąd przez `require_active_source` (lub `GRID_COHORT_SOURCE_REMOVED`) i cała strona, a z nią raport, kończy się wyjątkiem.
   - **Skutek:** błąd jest bezpieczny, bo nie ma fałszywego sukcesu. Jednak przy takich danych raport LIVE dla całej populacji jest nieosiągalny. Operator może tylko ręcznie przeskoczyć źródło kursorem i dostaje wtedy `partial`.
   - **Poprawka:** dodać do selekcji `NOT EXISTS` po `source_replacement_retired` albo łapać tylko `GridCohortError` dla jednego źródła i zapisywać je jako `rejectedSources[{sourceId, code}]`. Błędy SQL i przekroczenie czasu mają nadal przerywać raport. Do tego test z jednym zastąpionym źródłem na stronie.
   - **Uwaga:** jeśli w bazie są zastąpione źródła z ludzką akceptacją, ten punkt należy podnieść do P1.

2. **Odtworzenie nie sprawdza przypięcia presetu i modelu.**
   - **Miejsce:** `geometry_core/input_diagnostics.py:182-191` oraz `scripts/diagnose_full_board_input.py:207`.
   - **Problem:** `preset_sha256 = digest(bundle["preset"])` obejmuje cały preset z bundle, a rekord przechowuje tylko `screen`/`board`. Nie da się więc zweryfikować tego hasha z samego rekordu, a `reconstruct_input` go nie sprawdza. Nie sprawdza też `preprocessing_version`. Uwagi techniczne taska wymagają walidacji „preset/hash”.
   - **Skutek:** spójność zapewnia tylko capture (sprawdzenie SHA bundle). Rekord zmieniony razem z przeliczonym checksumem przejdzie odtworzenie z niezweryfikowanym przypięciem modelu.
   - **Poprawka:** hash liczyć z dokładnie zapisanego `{screen, board, preprocessing_version}` (albo zapisać cały preset) i sprawdzać go w `reconstruct_input`. Do tego test z rozbieżnym `preset_sha256` przy przeliczonym checksumie rekordu.

3. **Testy readiness nie odtwarzają ochron bazy danych.**
   - **Miejsce:** `services/api/tests/test_grid_diagnostic_readiness.py:42-44` mockuje `event.listen`, `event.remove` i `Session`.
   - **Problem:** limit czasu instrukcji ustawiany w `bounded_statement` (`grid_diagnostic_readiness.py:75-88`), ścieżka przekroczenia terminu (`:116-117`) i rzeczywisty tryb READ ONLY nie są w ogóle sprawdzane. Test potwierdza tylko obecność napisu "READ ONLY" w pierwszym SQL.
   - **Skutek:** regresja kolejności `SET TRANSACTION` albo wyłączenie `statement_timeout` przeszłaby testy.
   - **Poprawka:**
     - test jednostkowy, który przechwyci listener i wywoła go po upływie terminu, oczekując `TimeoutError`;
     - test, w którym termin mija po `capture`, i raport nie powstaje;
     - opcjonalnie test integracyjny PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS`): `SHOW transaction_read_only = on`, a INSERT kończy się błędem.

4. **Wpis `diagnosticUse` nie ma powiązania z raportem i brakuje testu duplikatu.**
   - **Miejsce:** `input_diagnostics.py:84-91` i `scripts/diagnose_full_board_input.py:261`.
   - **Problem:** task wymaga wpisu z „powiązaniem z raportem” oraz przypadku testowego „duplikat identycznego wpisu nie mnoży użycia”. Wpis nie zawiera SHA rekordów, `sequence_number`/`position_index` ani identyfikatora raportu. Nie ma też ani deduplikacji, ani jej testu.
   - **Skutek:** po wyjęciu wpisu z `report.json` dla T4 tracone jest pochodzenie, a liczenie użyć zostaje niezdefiniowane.
   - **Poprawka:** dodać `recordSha256` (lub `reportSha256`) do wpisu i zdefiniować klucz deduplikacji `(source_id, source_sha256, normalized_pixel_sha256, purpose)`. Do tego test sprawdzający, że dwa identyczne wpisy dają jedno użycie, albo jawny zapis, że deduplikację wykonuje T4.

5. **Zapisy wyników nie są trwałe ani wyłączne.**
   - **Miejsca:**
     - `scripts/diagnose_full_board_input.py:49-50`: `write_text` bez fsync;
     - `:243-275`: capture robi rename katalogu bez fsync plików ani katalogu;
     - `:310-312` (readiness) i `:321/339` (frozen): najpierw `exists()`, potem zwykły zapis.
   - **Skutek:**
     - po awarii systemu (a nie samego procesu) może zostać opublikowany katalog z uciętymi PNG/NPY;
     - między sprawdzeniem `exists()` a zapisem możliwe jest nadpisanie pliku;
     - przerwany zapis readiness lub frozen zostawia niepełny plik pod docelową nazwą.
   - **Poprawka:** zapis do pliku tymczasowego, potem fsync, potem `os.replace`. Docelowe pliki otwierać w trybie `"x"` i robić fsync plików w katalogu tymczasowym przed rename.

### P3 (bez wpływu na werdykt)
- **Nazwa pola:** task wymaga `fullHumanAnnotatedCount`, a kod używa `fullyHumanAnnotatedPhotos`.
- **Frozen:** `scripts/...:336-338` liczy `targets`/`screenEligible` także dla nieużytych źródeł, przez co sumy są mieszane. Indeks snapshotu liczy tylko użyte, a brak klucza dla nieużytego źródła da `KeyError`.
- **`fitted_nodes` przy FIT_FAILED** może zawierać zapasowe węzły z `grid_from_quad` (`scripts/...:219-221`). Odróżnia je tylko `reason_codes`.
- **Populacja readiness** to wyłącznie źródła z co najmniej jedną nominalną ludzką akceptacją, czego nie podano w `limitations`.
- **Konto bazy:** readiness używa konta właściciela schematu (`create_maintenance_database_engine`). Ryzyko ogranicza transakcja READ ONLY.
- **Słaby test „historyczny status nie nadpisuje T0”** (`test_full_board_diagnostic_cli.py:137-141`): kandydat ma `historical_disposition=None`, a baza nie ma blokerów. Konfliktu w jednym rekordzie test nie sprawdza.

### Pokrycie kryteriów (sprawdzone w kodzie)
- **Identyczny crop w nowym procesie i SHA pikseli z PNG:** spełnione. `reconstruct_input` używa produkcyjnych transformacji. Testy obejmują nowy proces oraz SHA PNG/NPY.
- **Identyfikacja źródła, modelu, transformacji, canvas, marginesu, interpolacji, paddingu i wersji:** spełnione, z zastrzeżeniem P2-2.
- **Brak surowych węzłów zapisany jako `unavailable`, `fitted_nodes` osobno:** spełnione.
- **Brak GT daje `unavailable` i null miary ucięcia:** spełnione, wymusza to typ `Literal`/`None`.
- **Historyczna akceptacja oddzielona od polityki T0:** spełnione strukturalnie, test słaby (P3).
- **Osobne zakresy, czasy i liczniki LIVE i frozen:** spełnione. Frozen nie zapisuje czasu, tylko `evidenceTime=historical`.
- **`diagnosticUse` zawiera tylko faktyczne przykłady, readiness daje `[]`:** spełnione, z zastrzeżeniem P2-4. Obecności 462205 w danych nie da się sprawdzić statycznie.
- **Brak TRAIN z predykcjami jest jawnie niedostępny:** opisany w dokumentach i `limitations`. Kod nie dobiera przykładów kontrolnych.
- **Role, historia, kopie i bufory bez zmian:** spełnione. Reader dostaje `role=None`/`unresolved`, transakcja jest READ ONLY i kończy się rollbackiem, nie ma zapisów.
- **Testy, audyt i commit:** otwarte zgodnie z procedurą.

### Zamknięte
- Odrzucanie przy zmianie dekodera, pikseli źródła, wersji schematu, macierzy, wymiarów, tensora lub OpenCV, oraz przy NaN.
- Ograniczenia canvas i quada.
- Brak kojarzenia po kolejności detekcji.
- Sprawdzanie zakresu atestacji i bindingu.
- Publikacja capture dopiero po pełnym odtworzeniu.
- Kursor keyset i `partial`, które nie udaje pełnej populacji.
- Ustawianie `search_path` w tej samej transakcji przez `GameStorageRouter`.

### Otwarte
P2-1 … P2-5 oraz kryterium dotyczące audytu i commita.

### Proponowane testy
- Zastąpione źródło na stronie readiness.
- Listener: przekroczony termin daje `TimeoutError`, a po `capture` raport nie powstaje.
- Integracyjny PostgreSQL: READ ONLY i timeout.
- Rozbieżny `preset_sha256` przy przeliczonym checksumie rekordu.
- Deduplikacja i powiązanie wpisu `diagnosticUse`.
- Rekord bazowy z dyspozycją `automatic` i blokerem T0.
- Frozen z nieużytym źródłem bez `targets`.

### Ograniczenia
- Wyłącznie przegląd statyczny pakietu i trzech celowanych plików kontekstu, bez moich zmian i bez uruchamiania testów. Wyników weryfikacji wykonawcy (22 testy, ruff, mypy, docs/map check) nie powtarzałem.
- Danych operatora (462205, 788 źródeł, smoke LIVE) nie widziałem i nie oceniam ich poprawności liczbowej.
- Zachowanie `GridCohortSnapshot.sources()` poza pokazanym fragmentem przyjąłem bez sprawdzenia.
