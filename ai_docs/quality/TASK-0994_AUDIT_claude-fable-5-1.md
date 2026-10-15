# Audyt TASK-0994 — Rejestr rodzin, wersji i przypisań

Werdykt: PASS
Audytor: claude-fable-5-1, high
Wykonawca: gpt-6.1-sol, high
Zakres: c06b7432e76e6e3d24b1cd78757d9f900bc9cac7...c06b7432e76e6e3d24b1cd78757d9f900bc9cac7 oraz zmiany niezacommitowane (korekta w trzech plikach kodu/testów i niezatwierdzony plik taska), data 2026-10-15
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano wyłącznie zakres korekty po rundzie 1: rejestrację modułu `grid_model_registry_models` w `storage/models.py`, przełączenie testu wyczerpującego klasyfikację tabel na manifest v9 z jawnymi kluczami `public.*`, nowy test własności shared/catalog, test niezależności od kolejności importów w świeżych procesach oraz nowy test równości zamrożonego seeda migracji 0156 z `historical_catalogue()` i przypiętym SHA. Poprawka P1-1 jest kompletna i trwała: sześć nowych mapowań ładuje się razem z `models`, a test wyczerpujący ponownie obejmuje wszystkie tabele ORM. P2-3 zamknięte przez test. P2-1 pozostaje świadomie przyjętym kosztem bez zmiany kodu, P2-2 jest zamknięte w części dotyczącej metadanych, a cykl downgrade baseline pozostaje nienaruszonym wcześniejszym ograniczeniem. Jedyne nowe ryzyko to dwa pliki taska o tym samym identyfikatorze i sprzecznym statusie w tym checkoucie, do rozliczenia przez leada przed commitem.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/src/game_predictor_api/application/grid_model_registry.py:63,72-73,105,108` — bez zmian wobec rundy 1: GET katalogu i POST liczą świeże pełne SHA-256 wszystkich plików inference i training przy każdym wywołaniu. Zgodnie z briefem i Outcome wykonawcy pozostawiono to celowo jako kontrakt fail-closed bez cache po mtime. Akceptacja ryzyka: koszt rośnie liniowo z liczbą wersji; ewentualna optymalizacja wymaga osobnej decyzji i pomiaru. Pozostaje otwarte jako udokumentowane ograniczenie, nie wada.
- [P2-2] `services/api/tests/integration/test_postgres_baseline.py:187-192` — część metadanowa z rundy 1 jest zamknięta (patrz lista zamkniętych). Pozostaje wcześniejsze ograniczenie cyklu: komentarz „Everything above 0150 is reversible” i `command.downgrade(config, LAST_MANAGEMENT_RETENTION_REVISION)` zakładają odwracalność ponad 0150, podczas gdy `services/api/alembic/versions/0156_grid_model_registry.py:190-192` oraz wcześniejsza 0152 odmawiają downgrade. Korekta tego nie zmieniała i nie uruchamiała `db:baseline:verify`, więc wynik tego cyklu na PostgreSQL pozostaje niezweryfikowany. Propozycja: osobne rozliczenie przez leada (zaktualizować oczekiwanie cyklu na odmowę i zapisać wynik `npm run db:baseline:verify` w Outcome); poza zakresem tej korekty.
- [P2-4] `ai_docs/tasks/0994-grid-model-registry.md:3,10` wobec `ai_docs/tasks/completed/0994-grid-model-registry.md:3,11` — w tym checkoucie istnieją dwa pliki taska o tym samym identyfikatorze: zacommitowany w `completed/` ze statusem `done` i niezatwierdzony w `tasks/` ze statusem `in_progress`, zawierający nowe sekcje Outcome o korekcie. Skutek: przy commicie korekty repozytorium miałoby dwa sprzeczne źródła statusu TASK-0994, co narusza regułę jednego pliku taska z `AGENTS.md`. Wykonawca jawnie zostawił rozliczenie leadowi (`copyToPrimary: false` w `artifacts/audits/TASK-0994_CORRECTION_RESULT.json:36-40`). Propozycja: przed commitem przenieść nowe sekcje Outcome do pliku w `completed/` i usunąć duplikat albo przywrócić jeden plik z właściwym statusem; nie commitować obu.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Addytywny enum/CHECK dopuszcza `neural_grid_v3` i wszystkie stare wartości; istniejące gry nie są przepisywane | spełnione (bez zmian w rundzie 2) | `services/api/alembic/versions/0156_grid_model_registry.py:49-57`; dowody rundy 1 |
| Migracja zachowuje modele obu gier, stara 777 nie otrzymuje neural assignment | spełnione statycznie (bez zmian w rundzie 2) | migracja i test PG z rundy 1; korekta nie dotyka migracji ani frozen JSON (`artifacts/audits/TASK-0994_CORRECTION_RESULT.json:262`) |
| Brak artefaktu blokuje udostępnienie | spełnione (bez zmian w rundzie 2) | dowody rundy 1; P2-1 utrzymuje świeżą kontrolę plików |
| Powtórna rejestracja jest idempotentna | spełnione (bez zmian w rundzie 2) | `services/api/tests/test_grid_model_registry.py:189-200`; dowody rundy 1 |
| Gra nie odczytuje cudzych danych przez błędny zakres | spełnione (bez zmian w rundzie 2) | dowody rundy 1 |
| Wyniki kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | spełnione z zastrzeżeniem P2-4 | `ai_docs/tasks/0994-grid-model-registry.md:344-366` (REVISE rundy 1, zakres korekty, wyniki, nieuruchomione kontrole); duplikat pliku taska wymaga konsolidacji |
| Korekta P1-1: rejestracja ORM i wyczerpująca klasyfikacja tabel | spełnione | `services/api/src/game_predictor_api/storage/models.py:6977-6979`; `services/api/tests/test_game_data_v2_schema.py:66-82,145-164,167-202`; `game_data_v2_manifest_v9.py:22-32`; `grid_model_registry_models.py:23,34,51,61,75,93`; wynik `pytest-focused`/`pytest-reverse` 19 PASS i `pytest-final` 9 PASS z deklaracji w `TASK-0994_CORRECTION_RESULT.json:128-177` |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później):

- P1-1 — `services/api/src/game_predictor_api/storage/models.py:6977-6979` importuje `grid_model_registry_models` w istniejącym bloku rejestracji, tym samym wzorcem co `management_models` i `grid_engine_acceptance_models`, bez importu klas z częściowo zainicjalizowanego modułu. `services/api/tests/test_game_data_v2_schema.py:66-82` używa manifestu v9 (`VERSION == "game-data-v2-manifest-v9"`), odejmuje sześć nazw z `CATALOG | SHARED` i dodaje je z prefiksem `public.`, więc asercje `set(Base.metadata.tables) <= known` i różnicy `known` pozostają wyczerpujące i fail-closed. `test_game_data_v2_schema.py:145-164` utrwala cztery tabele shared i dwie catalog, równość `GAME_TABLES == V8_GAME_TABLES`, schemat `public` każdej tabeli, brak w `PARTITIONED_TABLES` i odmowę `v8_ownership`. Wykonawca uruchomił wspólną kolekcję obu plików w obu kolejnościach (19 PASS każda).
- P2-2 (część metadanowa) — `services/api/tests/test_game_data_v2_schema.py:167-202` uruchamia świeży proces z `PYTHONPATH` wyłącznie tego drzewa, importuje najpierw `models` albo `grid_model_registry_models`, sprawdza tożsamość pliku `models.py` z izolowanym checkoutem, obecność sześciu kluczy `public.*` w `Base.metadata` i zawieranie nazw w `EXPECTED_PUBLIC_TABLES` wczytanym przez `runpy` z `test_postgres_baseline.py:95-97`. Zależność zestawu oczekiwanych tabel od kolejności importów została usunięta.
- P2-3 — `services/api/tests/test_grid_model_registry.py:173-186` porównuje pełny frozen JSON z `list(historical_catalogue())`, wczytuje moduł migracji przez `runpy` (co wykonuje guard `GRID_MODEL_BASELINES_CORRUPT` z `0156_grid_model_registry.py:18-26` bez DDL), porównuje `BASELINES` i `BASELINES_CANONICAL` z `canonical_json(frozen)` i sprawdza przypięty SHA. Kanoniczna serializacja w `domain/grid_model_registry.py:27-30` i w migracji używa tych samych parametrów (`ensure_ascii=True`, `sort_keys=True`, kompaktowe separatory); plik JSON nie zawiera znaków spoza ASCII, więc porównanie jest deterministyczne.

Otwarte: P2-1 (przyjęte ryzyko kosztu), P2-2 (wyłącznie wcześniejszy cykl downgrade baseline), P2-4.

## Proponowane testy

- Po konsolidacji pliku taska (P2-4) uruchomić `npm run docs:check` i `git diff --check` w drzewie, które otrzyma commit.
- Pełny zestaw API w jednym procesie, który pierwotnie ujawnił P1-1: `.\.venv\Scripts\python.exe -m pytest services/api/tests` (docelowo `npm run python:test`); wykonawca uruchomił tylko dwa pliki w obu kolejnościach.
- Dla pozostałej części P2-2: `npm run db:baseline:verify` z oczekiwaniem odmowy `GRID_MODEL_REGISTRY_DOWNGRADE_REFUSED` w `services/api/tests/integration/test_postgres_baseline.py:187-192`, po zaktualizowaniu oczekiwań cyklu; osobny task lub rozliczenie leada.

## Zakres przeglądu i ograniczenia

Przeczytano w całości: brief rundy 2 z diffem niezacommitowanym, raport rundy 1, `artifacts/audits/TASK-0994_CORRECTION_RESULT.json`, `services/api/tests/test_game_data_v2_schema.py`, `storage/game_data_v2_manifest_v9.py`, blok rejestracji `storage/models.py:6950-6989`, nagłówek i deklaracje tabel `storage/grid_model_registry_models.py`, `test_grid_model_registry.py:1-200`, `0156_grid_model_registry.py:1-60` i jego `downgrade`, `test_postgres_baseline.py:1-230`, `management_manifest.py` (`SHARED_TABLES`), `canonical_json`/`historical_catalogue` w domenie oraz nagłówki obu plików taska. Nie uruchomiono żadnych testów, poleceń git ani obliczeń SHA; wyniki pytest/Ruff/format/mypy/map/diff z korekty przyjęto z deklaracji w `TASK-0994_CORRECTION_RESULT.json`. Nie weryfikowano ponownie zakresu rundy 1 poza liniami powiązanymi z P1-1 i P2-1..P2-3, zgodnie z briefem. Nie badano `CURRENT_STATE.md` ani innych plików spoza pathspec.
