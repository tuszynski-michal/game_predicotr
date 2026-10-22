---
title: Audyt TASK-1085 — Przygotowanie bezpiecznego usunięcia starej kopii na C
status: active
last_updated: 2026-10-22
---

# Audyt TASK-1085 — Przygotowanie bezpiecznego usunięcia starej kopii na C

Werdykt: PASS
Audytor: claude-opus-5-5, medium
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...fde23c8a7a5642dcb5ef8bd58ca3ed001cffa549 oraz zmiany niezacommitowane, data 2026-10-22
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przejrzałem oba nowe skrypty: zabezpieczenie plików z porównaniem SHA oraz preview/apply migracji ścieżek. Przejrzałem też poprawkę loadera manifestu w `source_ingestion.py`, opcjonalny receipt w obu preflightach, wykrywanie Claude CLI w `audit_task.ps1`, testy i dokumentację. Rozwiązanie domyka się bezpiecznie. Archiwum nigdy nie nadpisuje istniejących plików, aktywny D nie jest celem zapisu, apply jest związany z SHA dokładnego podglądu i blokuje wiersze (`FOR UPDATE NOWAIT`) przed pierwszym UPDATE. Loader zmienia bazę źródła tylko po jawnym receipt i nadal wymaga zgodności SHA-256. Najważniejsze ryzyka:
- część kontroli przed apply może przejść „po cichu” (brak manifestu pod zakodowaną ścieżką jest pomijany);
- apply nie sprawdza ponownie, że `after_payload` różni się od `before` tylko dozwolonymi polami;
- zmiana `--effort` w `audit_task.ps1` wykracza poza opis taska i nie ma testu.

Nie znalazłem błędów P0 ani P1.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `scripts/legacy_job_path_migration.py:131-137` — Funkcja `verify_worker` buduje ścieżkę manifestu na stałe jako `destination/artifacts/data/originals/manifests`. Gdy pliku tam nie ma (`manifest_path.is_file()` zwraca fałsz), job jest pomijany bez błędu. Przy innym skonfigurowanym katalogu artefaktów, literówce w `--destination` albo braku manifestu kontrola „relocation-aware loader” przejdzie bez sprawdzenia ani jednego manifestu. Działa wtedy przeciwnie do zasady fail closed. Poprawka: liczyć sprawdzone manifesty i porównywać tę liczbę z oczekiwaną, zapisaną w podglądzie (raport mówi o 176). Przy rozbieżności odmówić. Ewentualnie brać katalog artefaktów z konfiguracji workera.
- [P2-2] `scripts/legacy_job_path_migration.py:120-137` — `verify_worker` sprawdza tylko kod zaimportowany przez proces skryptu (worktree albo editable install). Nie sprawdza działających procesów workera. Komunikat „Deploy the relocation-aware worker” sugeruje więcej, niż funkcja weryfikuje. Stary worker po migracji odrzuci preflight z nowym kluczem: ścisłe zbiory kluczy w `page_geometry_preflight.py:1330` i `neural_page_geometry_preflight.py:74`. Stary loader nadal brałby źródło z C. Bramka jest dziś czysto procesowa (restart przez operatora, raport). Poprawka: doprecyzować komunikat i dokumentację albo przed apply sprawdzić, że żaden proces workera nie działa ze starego kodu. Można też przyjąć ryzyko jako jawny punkt runbooka.
- [P2-3] `scripts/legacy_job_path_migration.py:235-239` — Apply zapisuje `after_payload` z pliku podglądu bez ponownego sprawdzenia, że różni się od `before["input_payload"]` wyłącznie polami `source_directory` i `source_directory_relocation`. Docstring (linie 1–8) i `DATA_MODEL.md` tego właśnie obiecują. SHA wiąże bajty pliku z zatwierdzeniem, ale ręcznie zmieniony plik z przeliczonym SHA mógłby zapisać dowolny payload. Poprawka: w apply wyliczyć oczekiwany payload z zablokowanego wiersza (`target_directory` i receipt) i porównać go z `after_payload` przed UPDATE.
- [P2-4] `services/worker/src/game_predictor_worker/images/source_ingestion.py:469-470` — Receipt nie przechodzi na joby pochodne. Managed reprocess tworzony po migracji (`application/jobs.py:1330` i `:1404`) kopiuje tylko `source_directory`, a jego sklonowany manifest zachowuje `sourceDirectory` z C (`source_ingestion.py:266-339`). Gdy zarządzany oryginał zniknie (np. ścieżka crop D-562/D-563), fallback do źródła trafi w nieistniejący C. Dziś ryzyko jest małe, bo raport potwierdza obecność wszystkich 112423 zarządzanych oryginałów na D. Poprawka: przy tworzeniu reprocessu propagować receipt albo odnotować ograniczenie w `DATA_MODEL.md` i w raporcie przed usunięciem C.
- [P2-5] `scripts/legacy_job_path_migration.py:140-190` — Podgląd skanuje tylko `public.jobs` i `remote_manual_selection_sessions`. Model ma też inne kolumny z możliwą ścieżką absolutną, np. `image_path`, `audit_path`, `snapshot_path`, `apk_path` (`storage/models.py:279, 5141, 5210, 5218, 6367`). Raport nie dokumentuje skanu całej bazy pod kątem prefiksu C. Poprawka: przed odcięciem C wykonać i odnotować odczyt tylko do odczytu wszystkich kolumn tekstowych i JSON pod kątem starego korzenia. Można też jawnie wpisać do raportu, że zakres skanu ograniczono do jobów i sesji.
- [P2-6] `scripts/audit_task.ps1:568-571` — Dodanie `--effort` dla audytora Claude nie wynika z Expected files taska (tam jest tylko wykrywanie `Claude-Data`) i nie jest opisane w Outcome. Domyślnie `Effort='medium'` (linia 92), więc każde wywołanie audytora Claude wymaga teraz flagi `--effort` w `--help`. Starszy CLI zakończy się kodem 3 zamiast uruchomić audyt. W `scripts/tests/test_auditor_cli.ps1` brakuje testu budowy argumentów. Poprawka: dopisać zmianę do Outcome taska i dodać test DryRun sprawdzający `--effort <wartość>` w poleceniu Claude. Można też wycofać zmianę do osobnego taska.
- [P2-7] `services/api/tests/test_legacy_job_path_migration.py:67-95` — Testy obejmują SHA podglądu, blokery, `validate_current_row` i `verify_input_receipts`. Nie obejmują ścieżki bazodanowej: `preview()` (wykrywanie blokerów, sesje) ani `apply()` (blokada, porównanie i UPDATE w jednej transakcji, rollback przy zmianie wiersza, rzutowanie `::json` na kolumnę JSONB). Nie obejmują też `verify_worker`. Operacja nie została jeszcze uruchomiona, a dotyczy danych operatora. Poprawka: test integracyjny PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`) na izolowanej bazie `*_test` z jobem przed i po podglądzie. Do tego test jednostkowy `verify_worker` z brakującym i niezgodnym manifestem.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Raport rozróżnia historię preflightów, używane importy i puste sesje | spełnione | `ai_docs/quality/LEGACY_C_COPY_RETIREMENT_20261022.md`, sekcja „Czy stare importy są potrzebne” (tabela 53/6/113/7/14) |
| Git C i wszystkie zarejestrowane worktree mają zabezpieczenie | niezweryfikowane | Tylko deklaracja w raporcie, sekcja „Zabezpieczenie na D” (bundle verify, 39/39 refs). Artefakty poza repozytorium, nie sprawdzone statycznie. |
| Zachowywane pliki mają weryfikację SHA i bezpieczny odpowiednik na D albo jawny blocker; żaden aktualny plik D nie został nadpisany | spełnione (kod), niezweryfikowane (dane) | `scripts/prepare_legacy_copy_retirement.py:137-159` (brak nadpisania, `os.link` + `FileExistsError`), `:199-205`, `:59-70`; testy `test_prepare_legacy_copy_retirement.py:20-57,68-84` |
| Podgląd nie przedstawia historycznych ścieżek jako aktywnych zależności bez kontroli konsumentów | spełnione (z uwagą P2-5) | `scripts/legacy_job_path_migration.py:150-152,165-190`; raport, sekcja „Zależności i ich rozliczenie” |
| Narzędzie odmawia zapisu po zmianie danych względem podglądu | spełnione | `scripts/legacy_job_path_migration.py:212-232` (SHA, blokery, `FOR UPDATE NOWAIT`, `validate_current_row`); testy `test_legacy_job_path_migration.py:42-95` |
| Wyniki, ograniczenia i kolejny krok są zapisane w raporcie | spełnione | raport, sekcje „Weryfikacja” i „Kolejny krok po akceptacji” |
| Kontrole zmienionych części i docs:check zaliczone; audyt rozliczony | niezweryfikowane | Deklaracje wykonawcy (78 testów PASS, ruff, mypy, docs:check). Audytor nie uruchamiał poleceń; ten raport jest audytem do rozliczenia. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy (runda 1).

Otwarte: P2-1, P2-2, P2-3, P2-4, P2-5, P2-6, P2-7.

## Proponowane testy

- `services/api/tests/test_legacy_job_path_migration.py`: test `verify_worker`, w którym brak manifestu albo niezgodny `source_directory` blokuje apply. Ma też odrzucać sytuację, gdy liczba sprawdzonych manifestów jest mniejsza od oczekiwanej. Polecenie: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_legacy_job_path_migration.py`.
- `services/api/tests/integration/` (nowy plik): `preview` i `apply` na izolowanej bazie `*_test`. Przypadki: zmiana `updated_at` lub statusu po podglądzie odrzuca całą transakcję bez częściowego UPDATE; poprawny apply zmienia tylko `source_directory` i receipt w kolumnie JSONB. Polecenie: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration -k legacy_job_path`.
- Test apply z ręcznie zmienionym `after_payload` (dodatkowy klucz) i poprawnie przeliczonym SHA: oczekiwana odmowa (po poprawce P2-3).
- `scripts/tests/test_auditor_cli.ps1`: przypadek DryRun dla `-Auditor claude -Effort high` sprawdzający obecność `--effort high` w wypisanym poleceniu.
- `services/worker/tests/test_image_source_ingestion.py`: test reprocessu relokowanego importu, gdy zarządzany oryginał nie istnieje, a stary katalog został usunięty. Ma udokumentować oczekiwane zachowanie (P2-4).

## Zakres przeglądu i ograniczenia

Przeczytałem cały brief, oba nowe skrypty (`scripts/prepare_legacy_copy_retirement.py`, `scripts/legacy_job_path_migration.py`) i oba nowe pliki testów w `services/api/tests/`. Przeczytałem też pełny diff zmian śledzonych:
- `source_ingestion.py` i jego testy, oba preflighty i ich testy;
- `audit_task.ps1` i `test_auditor_cli.ps1`;
- dokumentację: `DATA_MODEL.md`, `CURRENT_STATE.md`, `CODE_MAP*.md`, `DOC_INDEX.md`;
- raport operatora i plik taska.

Dla kontekstu przejrzałem `ManagedOriginalStore` (tworzenie i klonowanie manifestów, `ensure_original`), konsumentów `source_directory` w `application/jobs.py` i `api/image_imports.py`, typ kolumny `jobs.input_payload` (JSONB) oraz kontrolę flag w `audit_task.ps1:599-606`.

Nie uruchamiałem testów, lintów, typechecku ani `docs:check`. Nie miałem dostępu do bazy ani do artefaktów w `D:\game_predicotr\artifacts\maintenance\legacy-c-20261022`. Wszystkie liczby (179 jobów, 434131 plików, SHA podglądu, bundle 39/39) pochodzą z deklaracji wykonawcy. Zgodność rzutowania `%s::json` na kolumnę JSONB oceniłem na podstawie wiedzy o rzutowaniu przypisania w PostgreSQL, bez uruchomienia. Nie czytałem w tym przeglądzie `AGENTS.md`; zgodność z procesem oceniłem na podstawie reguł przytoczonych w briefie i w szablonie raportu.
