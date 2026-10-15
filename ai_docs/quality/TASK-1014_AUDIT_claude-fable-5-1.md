Dokończyłem przegląd kodu, testów i dokumentacji; piszę raport.

# Audyt TASK-1014 — Zarządzane checkpointy na D

Werdykt: PASS
Audytor: claude-fable-5-1, reasoning medium
Wykonawca: gpt-6.1-sol, reasoning medium
Zakres: 7d4b8cd60457650c8695be102399616cb9cf1692...7d4b8cd60457650c8695be102399616cb9cf1692 oraz zmiany niezacommitowane, data 2026-10-15
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano rozszerzenie instalatora o opcjonalny `training-base` (`scripts/install_grid_engine_models.py`), nowe funkcje weryfikacji receiptu w `storage/grid_engine_model_store.py`, przypięcie rozmiarów w rejestrze domenowym, nowy test `test_managed_grid_checkpoints_on_d.py` oraz instrukcję, raport dowodowy, rozdział VISION_LAB i mapy kodu. Implementacja realizuje zakres taska: źródła są weryfikowane przed jakimkolwiek zapisem, staging z receiptem i plikami `.partial` wznawia się per plik wyłącznie po SHA i rozmiarze, obcy katalog lub odmienny receipt daje konflikt bez nadpisania, publikacja to pojedynczy rename pod blokadą OS, a store odmawia odczytu bez fallbacku. Inferencyjny manifest nie zmienia się, bo `grid_engine_manifest` nie zawiera nowych pól. Główne ryzyko to sztywne wiązanie receiptu stagingu z bezwzględnymi ścieżkami źródeł oraz odrzucanie każdego junction w całej ścieżce nadrzędnej, co może blokować poprawny retry w nietypowej konfiguracji operatora; oba zachowania są zamierzone i udokumentowane, więc pozostają jako P2.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `scripts/install_grid_engine_models.py:334` i `:348` — receipt stagingu zawiera `path.resolve()` źródeł, a retry porównuje bajty receiptu. Wznowienie tej samej kopii z innej ścieżki źródłowej (inna litera dysku, przeniesiony eksport, ścieżka UNC) kończy się `GRID_ENGINE_TARGET_CONFLICT` z komunikatem „Foreign staging directory is not overwritten”, mimo że pakiet jest tożsamy po SHA. Instrukcja mówi, że receipt musi zgadzać się z pierwotnymi źródłami, więc zachowanie jest zgodne z dokumentacją. Proponowana poprawka lub akceptacja ryzyka: w `details` błędu podać, który element receiptu się różni (tożsamość modelu czy ścieżki źródeł), aby operator odróżnił obcy pakiet od własnego retry z innej ścieżki; można też zaakceptować ryzyko, bo usunięcie własnego stagingu pozostaje jawną operacją operatora.
- [P2-2] `services/api/src/game_predictor_api/storage/grid_engine_model_store.py:145` oraz `scripts/install_grid_engine_models.py:288` — pętla sprawdza `is_symlink()`/`is_junction()` dla katalogu bazy i wszystkich rodziców aż do korzenia dysku, a nie tylko dla elementów poniżej `artifact_root`. Jeśli operator kiedyś umieści `artifact_root` pod junction (częsta praktyka przy relokacji folderów na Windows), odczyt i instalacja zostaną odrzucone kodem `GRID_ENGINE_TRAINING_INVALID`, choć baza jest nienaruszona. Dziś root `D:/game_predicotr/artifacts` jest zwykłym katalogiem, więc skutku nie ma. Proponowana poprawka: ograniczyć kontrolę do segmentów względnych wobec `self._artifact_root` albo odnotować ograniczenie w instrukcji operatora.
- [P2-3] `scripts/install_grid_engine_models.py:400` — komentarz zakłada, że rename odmówi, gdy katalog docelowy istnieje. Na Windows jest to prawda, ale na POSIX `rename` zastępuje pusty katalog docelowy. Projekt jest Windows-first i pod blokadą OS równoległy instalator jest wykluczony, więc ryzyko jest teoretyczne. Akceptacja ryzyka z adnotacją w komentarzu, że gwarancja dotyczy Windows.
- [P2-4] `scripts/install_grid_engine_models.py:1` do `:29` — docstring modułu opisuje wyłącznie instalację inferencji i nie wspomina `--training-checkpoint`, `--check-training`, katalogu `training-base`, blokady `.training-base.lock` ani możliwych pozostałości `.training-base.receipt-*`. Instrukcja w `ai_docs/guides/MANAGED_GRID_TRAINING_BASES.md` pokrywa to zachowanie poza trwałym plikiem blokady, który pozostaje w katalogu wersji po instalacji. Proponowana poprawka: jeden akapit w docstringu i zdanie w instrukcji o pliku `.training-base.lock`, który jest nieszkodliwy i nie jest „stale lease”.
- [P2-5] `scripts/install_grid_engine_models.py:493` — `main` przechwytuje tylko `GridEngineModelError`. Błąd I/O podczas kopiowania (np. zerwany dysk sieciowy) wychodzi jako surowy traceback bez ustrukturyzowanego JSON z kodem, choć staging pozostaje do retry zgodnie z projektem. Proponowana poprawka: przechwycić `OSError` i wypisać kod w tym samym formacie co pozostałe błędy, bez zmiany semantyki pozostawiania stagingu.
- [P2-6] `ai_docs/tasks/1014-managed-grid-checkpoints-on-d.md:238` — wykonawca zapisał Technical notes po rozpoczęciu kodowania, co jest odstępstwem od kolejności z `AGENTS.md`. Odstępstwo jest jawnie odnotowane w Outcome i nie wpływa na trwałość ani poprawność zmiany. Akceptacja z odnotowaniem; bez dalszej poprawki.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Zgodny hash i rozmiar źródeł przed zapisem i kopii po zapisie | spełnione | `scripts/install_grid_engine_models.py:305`–`318`, `:391`–`397`, `:398`, `:401`; `storage/grid_engine_model_store.py:99`–`104`; testy `test_managed_grid_checkpoints_on_d.py:144`–`166` |
| Przerwana kopia wznawia się (per plik, po SHA, bez ufania mtime/rozmiarowi) | spełnione | `scripts/install_grid_engine_models.py:375`–`397`; testy `test_managed_grid_checkpoints_on_d.py:101`–`127` i `:169`–`207` (crash procesu pod blokadą OS i wznowienie) |
| Obcy katalog nie jest nadpisywany (target i staging, odmienny receipt) | spełnione | `scripts/install_grid_engine_models.py:295`–`297`, `:339`–`362`; test `test_managed_grid_checkpoints_on_d.py:130`–`140` (sentinel w `training-base` i `.training-base.installing`); odmienny receipt pokryty statycznie przez `:348`, bez osobnego testu (patrz Proponowane testy) |
| Nowy proces odczytuje bazę z D bez źródeł | spełnione | `storage/grid_engine_model_store.py:144`–`153`; test subprocess `test_managed_grid_checkpoints_on_d.py:66`–`98` po usunięciu źródeł; test CLI `:223`–`232`; rzeczywista kopia i odczyt opisane w `ai_docs/quality/MANAGED_GRID_BASES_20261015.md:45`–`62` (dowody JSON w ignorowanym `artifacts/audits/`, nie weryfikowane statycznie) |
| Inferencyjny manifest, `require` i aktywacja niezmienione | spełnione | `domain/grid_engine_profiles.py:82`–`83` (nowe pola z domyślną wartością, poza `grid_engine_manifest` `:298`–`326`); `install_version` `:170`–`178` zachowuje stary kontrakt; test `test_managed_grid_checkpoints_on_d.py:60`–`65` |
| Wyniki kontroli, audytu i ograniczenia zapisane w Outcome; dokumentacja odpowiada zachowaniu | niezweryfikowane | Outcome zawiera wyniki wykonawcy (`ai_docs/tasks/1014-managed-grid-checkpoints-on-d.md:242`–`256`), raport audytu jeszcze nie został wpisany; dokumentacja zgodna z kodem poza drobiazgami z P2-4 |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy, runda 1.

Otwarte: P2-1, P2-2, P2-3, P2-4, P2-5, P2-6.

## Proponowane testy

- Staging z poprawnie podpisanym, lecz odmiennym receiptem (inna wersja lub inne ścieżki źródeł), który musi dać `GRID_ENGINE_TARGET_CONFLICT` i pozostawić staging nietknięty; plik `services/api/tests/test_managed_grid_checkpoints_on_d.py`, komenda `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_managed_grid_checkpoints_on_d.py -k foreign_receipt` z twardym timeoutem 120 s.
- Współbieżne wywołanie instalatora przy trzymanej blokadzie `.training-base.lock` w drugim procesie, oczekiwany `GRID_ENGINE_TRAINING_BUSY` po limicie, aby pokryć ścieżkę timeoutu w `_training_lock` (`scripts/install_grid_engine_models.py:254`–`261`); ten sam plik testowy, z krótkim limitem przez monkeypatch deadline.
- Odczyt `require_training_base` przy dodatkowym nieoczekiwanym pliku w `training-base` (np. `desktop.ini`), oczekiwany `GRID_ENGINE_TRAINING_INVALID` z powodem „unexpected training artifacts”, aby udokumentować ścisłość listy plików dla operatora.

## Zakres przeglądu i ograniczenia

Przeczytano w całości brief audytu, plik taska i wycinek planu, pełne post-change wersje `scripts/install_grid_engine_models.py`, `services/api/src/game_predictor_api/storage/grid_engine_model_store.py`, `services/api/src/game_predictor_api/domain/grid_engine_profiles.py`, `services/api/tests/test_managed_grid_checkpoints_on_d.py`, nową instrukcję i raport dowodowy, diffy VISION_LAB, CODE_MAP, CODE_MAP_SYMBOLS i sekcję TASK-1014 w CURRENT_STATE. Sprawdzono pomocniki testowe `_fake_export` i `_install_module` w `test_grid_engine_profiles.py`, sygnaturę `load_checkpoint` w workerze (tylko odczyt), konfigurację pytest `pythonpath` i obecność `torch` w zależnościach root. Nie uruchamiano testów, Ruff, mypy, `docs:check` ani `code-map:check`; wyniki tych kontroli oraz dowody rzeczywistej kopii i odczytu z nowego procesu (`artifacts/audits/*.json`, receipts na D) przyjęto wyłącznie na podstawie deklaracji wykonawcy i nie były weryfikowane. Nie sprawdzano zachowania `msvcrt.locking` ani POSIX `rename` w działaniu.
