---
title: TASK-1014 — Zarządzane checkpointy na D
status: done
last_updated: 2026-10-15
---

# TASK-1014 — Zarządzane checkpointy na D

## Status

`done`

## Goal

Uniezależnić użycie baz od jedynej kopii checkpointu na C.

## Context

Task jest częścią zaakceptowanej rewizji 6. Trwałość i integralność artefaktów. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1015 done. Poprzedni task kolejności, TASK-0993, done v1.7.371 / `7d4b8cd60457650c8695be102399616cb9cf1692`; ograniczenie audytu jawnie odnotowane. Odczyt manifestów i dostępność miejsca są warunkiem faktycznej kopii.
- Pełny plan obejmuje odwracalną kopię potrzebnych artefaktów treningowych z C do zarządzanego katalogu na D, weryfikację i receipt. Bez usuwania C, zmiany aktywacji lub kopiowania korpusu. D-550/D-552 accepted; D-548/D-549/D-551 dotyczą późniejszych odrębnych pionów.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `medium`. kontrolowana kopia z hashami.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../../architecture/VISION_LAB.md).
- [VISION_LAB](../../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: TASK-0957, VISION_LAB, zasady przechowywania modeli.

## Scope

- Rozszerzyć instalator o potrzebne artefakty treningowe i receipt pochodzenia.
- Staging, weryfikacja, atomowa publikacja; wznowienie nie nadpisuje odmiennego pakietu.

## Out of scope

- Bez usuwania C, kopiowania całego korpusu i wykonywania treningu.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Zgodny hash i rozmiar; przerwana kopia wznawia się; obcy katalog nie jest nadpisywany; nowy proces odczytuje bazę z D.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

- Sprawdzone symbole: `GridEngineModelVersion` (domain/grid_engine_profiles.py), `ManagedGridEngineModelStore.directory/require` (storage/grid_engine_model_store.py), `install_version/_verify_source` (scripts/install_grid_engine_models.py) oraz neutralny `training_core.checkpoint.load_checkpoint` (CPU, bez treningu).
- Rozszerzenie opt-in: `install_version(..., training_checkpoint=Path(...))`; zwykły instalator i manifest inferencji zachowują kontrakt. Pola `checkpoint_size_bytes` i `weights_size_bytes` przypinają rozmiary artefaktów o SHA już zapisanym w statycznym rejestrze. Sprawdzone rozmiary: 777 checkpoint 106729511 B, Mumie checkpoint 53663320 B, oba weights.pt 26815171 B.
- Źródła: `C:/Users/tuszy/Documents/game_predictor_vision_data/neural-grid-runs/<run_id>/exports/<export_id>`; checkpoint `<run_id>/attempt-1/<sha>.pt` dla 777 i `<run_id>/attempt-3/<sha>.pt` dla Mumii. Run/export/checkpoint/weights SHA pochodzą z rejestru oraz wskazanych bundle manifestów. Kopia obejmuje wyłącznie checkpoint, eksportowe wagi, bundle i kanoniczny preset, bez korpusu.
- Docelowy root to jawne `D:/game_predicotr/artifacts`, nie względne artifacts worktree. `ManagedGridEngineModelStore.training_directory/require_training_base` używa osobnego `<profile>/<version>/training-base`, bez zmiany inferencyjnego manifestu, aktywacji lub przypisania gry.
- `training_base_files/identity` wiążą receipt z pełnym inference manifestem (model_version/architektura, preset/preprocessing fingerprint, snapshot/run/export, checkpoint/weights SHA) i rozmiarami. Checksumowana koperta `receipt.json` przechowuje także bezwzględne historyczne ścieżki pochodzenia. Resolver ich nie otwiera.
- Kolejność: poprawny target daje idempotentny sukces; odmienny target blokuje zapis. Potem pełne SHA/rozmiary źródeł, tożsamość bundle, rezerwa kopiowanych bajtów + 5 GiB, weryfikacja/instalacja inferencji. Blokada OS `.training-base.lock` ma limit 10 s i zwalnia się po śmierci procesu. Pod nią następuje ponowna kontrola targetu i właściciela stagingu oraz miejsca. Nie ma transakcji DB.
- Staging `.training-base.installing` otrzymuje receipt przez fsync i rename z katalogu inicjalizacyjnego. Każdy plik jest kopiowany do `.partial`, fsyncowany, sprawdzany SHA/rozmiarem i przenoszony. Retry zachowuje ukończony plik wyłącznie po SHA; nie ufa mtime/rozmiarowi. Wznowienie jest per plik, nie bajtowe; własny niepełny `.partial` kopiuje się od początku. Obcy receipt, nazwy, dowiązania/junctions lub target dają konflikt bez nadpisania. Błąd I/O pozostawia własny staging do retry.
- Publikacja kompletnego, zweryfikowanego stagingu jest pojedynczym rename na tym samym wolumenie, pod OS lockiem. Store ponownie sprawdza receipt, lineage, dokładną listę plików i bajty; brak/korupcja blokuje odczyt bez fallbacku. Nowy proces korzysta z `require_training_base` i `load_checkpoint` na CPU, bez optimizer restore, GPU, inferencji czy treningu. Checkpoint.py pozostaje tylko odczytany.
- Pliki pionu: domain/grid_engine_profiles.py, storage/grid_engine_model_store.py, scripts/install_grid_engine_models.py, nowy test API, instrukcja operatora, raport dowodowy, task i własna sekcja CURRENT_STATE. Publiczne symbole wymagają regeneracji CODE_MAP. Source-free testy i rzeczywisty odczyt nie upoważniają do cleanupu C.


Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [grid_engine_model_store.py](../../../services/api/src/game_predictor_api/storage/grid_engine_model_store.py) — `ManagedGridEngineModelStore`; [instalator](../../../scripts/install_grid_engine_models.py) — `install_version`.
- Istniejące: `services/api/src/game_predictor_api/domain/grid_engine_profiles.py` — `GridEngineModelVersion` i pinning rozmiarów baz.
- Nowe: `ai_docs/guides/MANAGED_GRID_TRAINING_BASES.md`, `ai_docs/quality/MANAGED_GRID_BASES_20261015.md`.
- Istniejące: [checkpoint.py](../../../services/worker/src/game_predictor_worker/training_core/checkpoint.py) — zapis, odczyt i odtworzenie checkpointu.
- Pozostały zakres wskazany w zaakceptowanym planie: nowy proponowany manifest receipt kopii i test instalatora. tylko do sprawdzenia odczytu checkpointu.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_managed_grid_checkpoints_on_d.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Zgodny hash i rozmiar; przerwana kopia wznawia się; obcy katalog nie jest nadpisywany; nowy proces odczytuje bazę z D.

## Verification

Zakres: API/WORKER dla kontraktu artefaktów, test instalatora, DOC.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_neural_grid_proposal.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_training_core.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez usuwania C, kopiowania całego korpusu i wykonywania treningu.

## Outcome

### Execution phase

- Faza: oczekiwanie na końcową akceptację i integrację całego planu; base HEAD v1.7.371 / `7d4b8cd60457650c8695be102399616cb9cf1692`.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14).
- Worktree: `D:/game_predicotr/worktrees/v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: v1.7.372 / `b11cdb19d81711fa801157c8effb3fc78863e46c`;17 plików, bez scalenia. Numer sprawdzono na lokalnych referencjach i HEAD-ach worktree, bez kolizji. Pełny hash dopisano po utworzeniu; zapis wejdzie z następnym taskiem, bez amend.
- Audit: `claude-fable-5-1`, reasoning `medium`, [raport](../../quality/TASK-1014_AUDIT_claude-fable-5-1.md): PASS, brak P0/P1; przegląd statyczny, bez uruchamiania kontroli i bez niezależnej weryfikacji realcopy receipts. Jedna runda audytu i jedna runda korekt P2. Raport zachowano bez zmian.
- Następny krok: TASK-0994. Końcowa integracja całego planu wymaga akceptacji operatora.

### Changed

- Opcjonalna instalacja `training_checkpoint`, osobny niezmienny `training-base`, registry-pinned SHA/rozmiary i pełna lineage manifestu/presetu. OS lock, staging z receipt, atomowa publikacja i zweryfikowane retry per plik. Store udostępnia `require_training_base`; domyślne inference store/instalator/manifest zachowane.
- Rozwinięcie Technical notes utrwalono po rozpoczęciu kodowania; wcześniejsze ustalenia manifestów i kierunku przekazano leadowi w wiadomości, co nie zastępuje wymaganego zapisu przed kodowaniem. Odstępstwo procesowe zapisano jawnie.
- Rzeczywiste źródła C i docelowe ścieżki D, wszystkie pełne SHA/rozmiary oraz niezmienność inferencyjnych manifestów zapisano w [raporcie](../../quality/MANAGED_GRID_BASES_20261015.md). Oba wymagane checkpointy, weights, bundle i preset skopiowano do `D:/game_predicotr/artifacts/models/grid-engine/<profile>/v1/training-base`; receipts pozostają poza Git. 777 SHA `2cd19738367121e6a36cf0630b4fd7d275d1966fbe25ca73d1329fa979183fe8`, 106729511 B; Mumie SHA `f896da7196431be2d6dc7b863cfa69f6ec27fd63cb3d3e00ff7acd1f2b745138`, 53663320 B.
- Dokładny zakres aplikacji: `services/api/src/game_predictor_api/domain/grid_engine_profiles.py`, `services/api/src/game_predictor_api/storage/grid_engine_model_store.py`, `scripts/install_grid_engine_models.py`, nowy `services/api/tests/test_managed_grid_checkpoints_on_d.py`. `checkpoint.py` tylko odczytano, bez zmiany.

### Verification results

- PASS: skoncentrowane testy installer/store/crash/new-process oraz istniejących profili bez niezwiązanego endpointu; końcowy wynik 22 passed / 1 deselected w 24.06 s zapisano w `artifacts/audits/TASK-1014_FINAL_CHECKS.json`; istniejący endpoint jest jawnie wyłączony.
- PASS: `pytest services/api/tests/test_neural_grid_proposal.py services/worker/tests/test_vision_lab_training_core.py -q --tb=short --basetemp=artifacts/tests/task1014-regression`: 27 passed w 10.28 s (twardy timeout 120 s). Bez rzeczywistego treningu/inferencji operatora; izolowane testy kontrolne używają własnych małych modeli.
- PASS: realcopy obu baz z pełną kontrolą hash/rozmiar i rezerwą 5 GiB; inference manifest SHA przed/po identyczne. Dowód `artifacts/audits/TASK-1014_REAL_COPY.json`.
- PASS: nowy proces `require_training_base` + neutralny `load_checkpoint` + weights-only odczyt eksportu na CPU; audit hook blokował każde otwarcie historycznego katalogu lab na C. Oba schemaVersion 2 / completed_epoch, po 670 kluczy stanu i eksportu. Nie wykonano forward/backward, GPU, restore optimizer ani treningu. Dowód `artifacts/audits/TASK-1014_NEW_PROCESS_READ.json`.
- Ruff check/format i mypy trzech zmienionych modułów: PASS; końcowe polecenia/wyniki i timeouty w `artifacts/audits/TASK-1014_FINAL_CHECKS.json`. Mapy zregenerowano po zmianie publicznych symboli; wynik i docs/diff zapisuje końcowy scope.
- PASS po naprawie kodowania: `npm run docs:check` (60 active tasks, 10 done sections, 97515 B), `npm run code-map:check`, `git diff --check`. Pierwszy docs:check miał FAIL na kodowaniu/rozmiarze CURRENT_STATE; końcowy wynik nie zastępuje historii nieudanej próby. Log `artifacts/audits/TASK-1014_DOC_CHECKS_FINAL.json`, kompletny zakres/polecenia `artifacts/audits/TASK-1014_SCOPE.json`.
- Nieudane próby nie są PASS: domyślny TEMP piaskownicy odmówił tworzenia fixture (17 setup errors, 3 pozostałe tests passed); druga próba basetemp miała nieutworzone katalogi nadrzędne (17 setup errors, 3 pozostałe tests passed). Utworzono własny `artifacts/tests` i użyto nowych basetemp. Niezwiązany test istniejącego endpointu zatrzymany twardym timeoutem 120 s; nie rozszerzano zakresu ASGI/DB. `subprocess.run(timeout=120)` zakończył własny child; niezależny CIM odczyt został początkowo odrzucony przez sandbox. Następny odczyt z eskalacją potwierdził zero własnych python/pytest task1014 procesów; cudzych procesów nie zmieniano. Początkowe Ruff/mypy błędy stylu i platformowego typu flock poprawiono, końcowe kontrole przechodzą.

### Not completed

- Commit i integracja: wykonuje lead po rozliczeniu audytu. Audyt statyczny PASS wykonano; nie jest dowodem niezależnego wykonania testów ani realcopy. Zapis hasha nastąpi po commicie.
- Endpoint regression miał timeout; pozostałe właściwe regresje i testy pionu odnotowano powyżej.
- Nie wykonano cleanupu C, kopiowania korpusu, nowego backupu bazy, zmian DB/operatora, migracji operatora, usług, treningu, inference, GPU, aktywacji, push ani scalenia. Restart Windows nie był wykonywany; trwałość sprawdzono odczytem z nowego procesu i testem crash/retry.

### Audit disposition

- Raport `ai_docs/quality/TASK-1014_AUDIT_claude-fable-5-1.md`: PASS, P0/P1 brak. Audytor wykonał wyłącznie statyczny przegląd; wyników testów i realcopy nie sprawdzał niezależnie. Raport zachowano dosłownie. Zawiera sześć P2 mimo procesowego limitu pięciu; odstępstwo audytora odnotowano, bez przepisywania jego raportu.
- P2-1: przyjęte ryzyko. Retry stagingu celowo wiąże pełny receipt i pierwotne bezwzględne ścieżki źródeł, aby rozpoznać właściciela operacji. Przeniesienie tożsamych plików może blokować retry; instrukcja wymaga tych samych źródeł, a usunięcie stagingu pozostaje jawną operacją. Nie rozszerzono polityki własności ani diagnostyki błędów.
- P2-2: przyjęte ograniczenie i dopisana instrukcja. Junction/symlink w dowolnym rodzicu, również powyżej artifact_root, blokuje instalację i odczyt. Obecny zwykły root D nie podlega temu ograniczeniu. Nie zmieniono granic kontroli ścieżki.
- P2-3: zamknięte korektą komentarza i instrukcji. Odmowa rename do istniejącego katalogu jest gwarancją Windows; POSIX może zastąpić pusty katalog. OS lock serializuje współpracujące instalatory, nie niezależnych zewnętrznych writerów. Bez zmiany zachowania.
- P2-4: zamknięte korektą docstringu i instrukcji. Opisano opt-in training flags, training-base, receipt, OS lock oraz możliwe katalogi inicjalizacyjne receipt. Trwały plik lock jest nieszkodliwy i nie jest stale lease.
- P2-5: przyjęte ryzyko istniejącego CLI. Surowy OSError daje widoczne niepowodzenie/niezerowe zakończenie, a własny staging pozostaje do retry; nie ma fałszywego sukcesu. Zadanie celowo nie rozszerza CLI/error contract. Instrukcja opisuje ograniczenie.
- P2-6: przyjęte odstępstwo procesowe. Późny zapis Technical notes i naprawa kodowania są jawnie rozliczone w Outcome; brak dalszej zmiany zachowania.
- Propozycje dodatkowych testów audytora są nieblokujące. Nie rozszerzono zakresu i nie ponawiano testów, mypy, map ani kopii modeli po wyłącznie komentarzach/docstringu i dokumentacji. Wykonano ponownie tylko właściwe kontrole format/Ruff oraz docs/diff: wszystkie PASS, dokładne polecenia i wyniki w `artifacts/audits/TASK-1014_AUDIT_CORRECTION_CHECKS.json`.

### Documentation updates

- Naprawiono własny błąd kodowania: stare sekcje taska przywrócono z `git show HEAD` odczytanego jako UTF8, zachowując jawne metadane startu i nowe Technical notes/Outcome. Przy kolejnych odczytach/zapisach użyto jawnego UTF8. Lead naprawia wyłącznie znane własne zmiany CURRENT_STATE z baseline; nie resetowano cudzej pracy.
- Rozwinięte Technical notes i ten Outcome; [instrukcja operatora](../../guides/MANAGED_GRID_TRAINING_BASES.md), [raport rzeczywistej kopii](../../quality/MANAGED_GRID_BASES_20261015.md), rozdział architektury VISION_LAB oraz własna sekcja CURRENT_STATE. Mapy generowane dla publicznych symboli.
- Pliki `README`, plan oraz rozliczenie wcześniejszego TASK-0993 należą do leada i nie są zmianą tego pionu.

### Recommended next task

- Po audycie i osobnym commicie TASK-1014: TASK-0994.
