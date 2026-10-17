# Audyt TASK-1048 — Job usuwania oryginałów, cleanup i zabezpieczenia kotwic oraz kohort

Werdykt: REVISE
Audytor: Codex `gpt-6.1-sol`, reasoning `high` — oznaczenie briefu
Wykonawca: Claude `claude-opus-5-5`, reasoning `xhigh`
Zakres: HEAD...4d157a61d33a908d3020907aaafacf86b3f6d337 oraz niezacommitowane zmiany wskazane w briefie, data 2026-10-17
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano potwierdzanie usuwania, handler, zapis stanu, wznowienie, cleanup oraz zabezpieczenia kalibracji i kohort. Mechanizm sprawdza token, potwierdzenia i integralność plików, ale nie sprawdza pokrycia aktualnej geometrii przez wcześniej utworzony crop. Brakuje także synchronizacji z równoległymi zmianami kwalifikacji, a awaria przed checkpointem powoduje utratę części liczników usuwania.

## Znaleziska

### P0

- [P0-1] `services/worker/src/game_predictor_worker/source_original_deletion.py:322` — Weryfikacja cropu sprawdza jego historyczny atest, ale nie porównuje zachowanego kadru z aktualnymi `eligibility.protected_points`. Po utworzeniu cropu można zatwierdzić geometrię poza jego kadrem albo zakończyć import kolejnego źródła współdzielącego blob. Blob ponownie spełnia kwalifikację, więc handler usuwa oryginał mimo braku pikseli wymaganych przez aktualną geometrię. Należy przed usunięciem sprawdzać pokrycie wszystkich aktualnych chronionych quadów, wraz z wymaganym marginesem i odstępem od pasa krawędziowego. Zmianę poza pokryciem należy odrzucić, zachowując oryginał.

- [P0-2] `services/worker/src/game_predictor_worker/source_crop.py:292` — Ponowny odczyt kwalifikacji odbywa się w migawce `REPEATABLE READ`, lecz blokowane są tylko job usuwania i wiersz cropu. Równoległy zapis `grid_issue`, nowego źródła lub joba może zatwierdzić zmianę po odczycie kwalifikacji, a przed `unlink`; transakcja usuwania nadal uzna blob za kwalifikujący się. Blokada bloba jest używana wyłącznie przez handlery cropu i usuwania. Analogicznie odczyt w `services/api/src/game_predictor_api/storage/grid_calibration_repository.py:67` pozwala wybrać kotwicę przy stanie `verified`, a następnie zapisać profil już po usunięciu oryginału. Potrzebna jest wspólna synchronizacja usuwania z zapisami zmieniającymi kwalifikację i przypinaniem kotwic, obejmująca świeżą kontrolę przed operacją plikową.

- [P0-3] `services/worker/src/game_predictor_worker/source_original_deletion.py:312` — Awaria po zatwierdzeniu `original_deleted`, ale przed checkpointem przebiegu, zmienia wynik wznowienia na `alreadyDeleted`. Checkpoint powstaje dopiero po paczce (`:239`), więc skutecznie usunięte przez ten przebieg pliki zostają policzone jako pominięte, bez doliczenia `saved_bytes`. Dla pojedynczego bloba wynik może wynosić zero sukcesów i zero zwolnionych bajtów mimo usunięcia oryginału. Należy trwale zapisywać wynik jednostki i jego powiązanie z przebiegiem, aby wznowienie odtwarzało sukces oraz bajty dokładnie raz.

### P1

- [P1-1] `services/api/tests/integration/test_source_original_deletion_postgres.py:168` — Test opisany jako sprawdzenie ostatniej referencji wywołuje bezpośrednio `_delete_crop_registry`, przekazując gotowe ścieżki. Nie usuwa referencji przez właściwy workflow cleanupu ani nie sprawdza usunięcia plików. Test w `services/api/tests/test_source_original_deletion_guards.py:59` również obejmuje tylko helper ścieżek. Brakuje wymaganego testu integracyjnego potwierdzającego zachowanie cropu, atestu i rejestru przy pozostającej referencji oraz ich usunięcie dopiero przy ostatniej referencji. Należy objąć współdzielenie w jednej grze i między grami, także przy już nieobecnym oryginale.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Własny preview, token, `confirmed` i `acknowledgeIrreversible` | spełnione | `services/api/src/game_predictor_api/application/source_crop_runs.py:150`; `services/api/src/game_predictor_api/storage/source_crop_run_repository.py:136`; ocena statyczna |
| Zmiana kwalifikacji, zmieniony oryginał lub wadliwy crop zatrzymują usuwanie | niespełnione | P0-1 i P0-2; kontrole integralności istnieją w `services/worker/src/game_predictor_worker/source_original_deletion.py:351` i `:380` |
| Przerwanie po `unlink`, przed zapisem stanu, jest uzgadniane | spełnione | `services/worker/src/game_predictor_worker/source_original_deletion.py:385`; scenariusz w `services/api/tests/integration/test_source_original_deletion_postgres.py:116`; ocena statyczna |
| Cleanup usuwa crop, atest i rejestr dopiero przy ostatniej referencji | niezweryfikowane | Implementacja w `services/api/src/game_predictor_api/storage/cleanup_repository.py:565` i `:1111`; brak testu właściwego workflow — P1-1 |
| Nowe profile nie przypinają usuniętych oryginałów; kohorty odmawiają ich użycia | niespełnione | Wyścig kotwic — P0-2; kontrola kohort przed kopiowaniem w `services/api/src/game_predictor_api/application/grid_training_cohort_commands.py:308` |
| Lint, mypy, testy skupione i PostgreSQL przechodzą | niezweryfikowane | Brief nie zawiera wyników weryfikacji; poleceń testujących nie uruchamiano |
| R8: wznowienie zachowuje poprawny wynik zakończonych jednostek | niespełnione | P0-3 |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P0-1, P0-2, P0-3, P1-1.

## Proponowane testy

- W `services/worker/tests/test_source_original_deletion_job.py` dodać zatwierdzoną zmianę geometrii poza istniejący crop oraz awarię po zapisie `original_deleted`, przed checkpointem. Sprawdzić zachowanie oryginału w pierwszym przypadku i dokładne liczniki po wznowieniu w drugim. Komenda: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_source_original_deletion_job.py`.
- W `services/api/tests/integration/test_source_original_deletion_postgres.py` dodać kontrolowane przeploty dwóch transakcji: zmiana kwalifikacji między odczytem a usunięciem oraz wybór kotwicy równolegle z usuwaniem.
- W tym samym pliku dodać cleanup przez właściwy serwis, z dwiema referencjami, kontrolą plików i rejestru po usunięciu pierwszej oraz ostatniej referencji. Uruchomić na izolowanych bazach testowych: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = "1"; D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_source_original_deletion_postgres.py`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, aktywny task, odpowiednie reguły planu i D-562, wymagania dotyczące oryginałów, zmienione moduły i dokumentację oraz powiązane implementacje kwalifikacji, rejestru, checkpointów, loadera i cleanupu. Sprawdzono nowe testy jednostkowe i PostgreSQL oraz istniejące testy potwierdzania API.

Przegląd był wyłącznie statyczny. Nie uruchamiano testów, lintowania, mypy, usług ani operacji na bazach. Nie tworzono, nie modyfikowano i nie usuwano plików. Ustalenia o awariach i współbieżności wynikają z analizy kolejności operacji i blokad; wymagają wskazanych testów regresyjnych.