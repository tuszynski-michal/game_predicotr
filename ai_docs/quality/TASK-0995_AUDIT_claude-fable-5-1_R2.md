# Audyt TASK-0995 — Kwalifikacja korekt i niezmienny snapshot

Werdykt: PASS
Audytor: claude-fable-5-1, reasoning high
Wykonawca: gpt-6.1-sol, reasoning high
Zakres: d2b692dbc59f1de339ad1acd2a961d402fced8c8...d2b692dbc59f1de339ad1acd2a961d402fced8c8 oraz zmiany niezacommitowane, data 2026-10-16
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano wyłącznie zweryfikowaną deltę korekty R1 (`artifacts/audits/TASK-0995_R2_VERIFIED_DELTA.patch`, siedem plików) wraz z bezpośrednimi zależnościami zmienionych modułów: parserem przestrzeni kohort i polityką retencji w `domain/storage_retention.py`, skanerem `application/storage_gc.py`, helperami `current_targets`/`own_target` w `storage/grid_quality_observations.py` i `source_targets` w `storage/grid_reinference.py`, `target_fence` w `domain/grid_training_cohorts.py`, mapowaniem błędów w `storage/grid_training_cohort_currentness.py`, kodami wyjątków `source_recording_sql_v3.py`, notice w `grid_reinference_retention.py`, schematem i routerem completion oraz dowodami CPU/Ruff/mypy korekty. Wszystkie pięć uwag R1 zostało usuniętych: publisher produkuje `.tmp-<32 hex>.part`, które istniejący skaner GC rozpoznaje, chroni przed 24 h i przy referencji, a kwalifikuje po 25 h bez referencji; trigger 0163 emituje wybrany reason; mapper obejmuje `GRID_COHORT_`; completion wymaga aktualnego własnego, nieodrzuconego targetu z dokładną rewizją pod istniejącym ownership/source fence i bez nowych blokad; Outcome opisuje wdrożoną politykę. Pozostaje jedno nowe P2: po zmianie nazwy pliku tymczasowego istniejąca asercja `*.staged` w teście publikacji stała się pusta. Główne ograniczenie: po poprawce fixture nie powtórzono całego zestawu CPU01, a wyników PG/E2E/HTTP nie uruchamiano ponownie.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-5] `services/api/tests/test_grid_training_cohort_core.py:419` — asercja `assert not list(tmp_path.rglob("*.staged"))` odwołuje się do starej nazwy pliku tymczasowego; po korekcie P1-1 publisher tworzy `.tmp-<hex>.part` (`services/api/src/game_predictor_api/storage/grid_training_cohort_artifacts.py:95`), więc asercja przechodzi zawsze i nie sprawdza już sprzątania po udanej publikacji ani po wznowieniu z istniejącym plikiem. Skutek: utrata pokrycia gałęzi `finally: temporary.unlink` (`grid_training_cohort_artifacts.py:129`) w scenariuszu sukcesu. Proponowana poprawka: zmienić wzorzec na `*.part` (lub `.tmp-*.part`); można też zaakceptować ryzyko, bo gałąź twardej awarii jest pokryta nowym testem rezyduum.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Pełna plansza z niekompletnego zdjęcia działa w grid-only | spełnione | Delta nie dotyka tej ścieżki (manifest korekty: 7 zmienionych plików, brak `grid_training_cohort_evidence.py`/`source_recording_sql_v3.py`); dowody R1 pozostają aktualne: `services/api/src/game_predictor_api/storage/grid_training_cohort_evidence.py:363,446`, `services/api/src/game_predictor_api/storage/source_recording_sql_v3.py:190` |
| Niepełne zdjęcie nie jest screen targetem | spełnione | Jak wyżej, bez zmian w delcie; `grid_training_cohort_evidence.py:443,465`, `source_recording_sql_v3.py:188`, `services/api/tests/test_grid_training_cohort_core.py:392-410` |
| Auto-accept nie tworzy etykiety | spełnione | Bez zmian w delcie; `grid_training_cohort_evidence.py:137-168`, `test_grid_training_cohort_core.py:94`. Korekta P2-3 dodatkowo zaostrza completion tożsamości (`services/api/src/game_predictor_api/application/grid_source_identities.py:118-128`) |
| Drift między preview/freeze blokuje zapis | spełnione | Bez zmian w delcie; `services/api/src/game_predictor_api/application/grid_training_cohort_freeze.py:92-113,153-165`. Mapper `GRID_COHORT_` (`services/api/src/game_predictor_api/storage/grid_training_cohort_repository.py:300`) zapewnia typed 409 także dla `GRID_COHORT_MINIMUM_NOT_MET` (`source_recording_sql_v3.py:125-126`), a w GET eligibility kod trafia do `reasons` i daje `blocked` (`services/api/src/game_predictor_api/storage/grid_training_cohort_currentness.py:196-199,214`) |
| Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | niezweryfikowane | Dokumentacja odpowiada zachowaniu: `ai_docs/architecture/VISION_LAB.md:722-723` (24 h dla unreferenced staging) zgadza się z `storage_retention.py:172-179` i `storage_gc.py:235-240`; `ai_docs/tasks/0995-grid-training-cohort-snapshot.md:327` opisuje wdrożoną politykę (P2-4 usunięte); Outcome zawiera wpis korekty R1 z ograniczeniami (`0995-grid-training-cohort-snapshot.md:322` i wpis „Korekta R1 zamrożona”). Wpis wyniku R2 i zaznaczenie pola następują z natury po tym raporcie, więc nie da się ich potwierdzić statycznie teraz |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): P1-1 — `services/api/src/game_predictor_api/storage/grid_training_cohort_artifacts.py:95` tworzy `.tmp-{uuid4().hex}.part`; `services/api/src/game_predictor_api/domain/storage_retention.py:218-223` rozpoznaje tę nazwę; `services/api/src/game_predictor_api/application/storage_gc.py:223-240` przechodzi po katalogu kohort i yielduje obserwację pod guardem; `services/api/tests/test_grid_cohort_asset_retention.py:93-168` uruchamia rzeczywisty publisher w procesie potomnym z `os._exit(73)` w `os.replace` po fsync (pominięcie `finally` jak przy twardej awarii), sprawdza faktyczną nazwę i bajty rezyduum, `retention_not_elapsed` przy 23 h, `retained_cohort_reference` przy referencji i jedną pozycję do GC po 25 h bez referencji, bez fizycznego usunięcia; dowód przejścia: `artifacts/audits/TASK-0995_R1_CORRECTION_CPU_01.json:131-133`. P2-1 — `services/api/alembic/versions/0163_grid_training_cohorts.py:213` emituje `SOURCE_REMOVED_NEW_USE_BLOCKED`, zgodnie z `grid_reinference_retention.py:49`; test `services/api/tests/test_grid_training_cohort_storage.py:242-245` czyta rzeczywisty `NOTICE_SQL`; brak starego literału w `services/` poza asercjami negatywnymi. P2-2 — `grid_training_cohort_repository.py:300` mapuje prefiks `GRID_COHORT_`; `test_grid_training_cohort_core.py:571-605` parametryzuje oba kody z rollbackiem savepointu i używalną sesją. P2-3 — `grid_source_identities.py:116-128` wymaga `own_target` ∧ ¬`target_fence["rejected"]` ∧ `board.source_geometry_revision_id == expectedSourceGeometryRevisionId` po `acquire_sequence_ownership_lock` (`:71`) i `FOR UPDATE` na source (`:76-79`), przed `UPDATE source_images` (`:138`) i receiptem (`:160`); `current_targets` (`grid_quality_observations.py:110-135`) otwiera tylko czytelnik na tej samej connection, `source_targets` (`grid_reinference.py:527-603`) to zwykłe SELECT-y bez `FOR UPDATE`, więc brak nowej blokady projekcji i nowego resolvera; `target_fence["rejected"]` obejmuje board `rejected` i review `superseded` (`domain/grid_training_cohorts.py:104`); porównanie string/string jest poprawne, bo router przekazuje `model_dump(mode="json")` (`services/api/src/game_predictor_api/api/grid_training_cohorts.py:206`), a schemat waliduje UUID (`services/api/src/game_predictor_api/schemas/grid_training_cohorts.py:66`); testy `test_grid_training_cohort_core.py:608-734` obejmują current/already_complete (EXIF None, brak UPDATE przy komplecie) oraz odmowę historical/foreign/rejected/superseded/no_review z kolejnością decode → ownership → source_lock → current_targets; dowód: `TASK-0995_R1_CORRECTION_CPU_02.json:5,41-80` (7 PASS). P2-4 — `ai_docs/tasks/0995-grid-training-cohort-snapshot.md:327` nie zawiera już zdania o niewybranej polityce; grep „Docelowej polityki” trafia tylko w raporty audytu.

Otwarte: P2-5.

## Proponowane testy

- `services/api/tests/test_grid_training_cohort_core.py::test_immutable_publish_survives_new_store_and_lost_response`: zmienić glob na `*.part`, aby test ponownie sprawdzał brak rezyduum po udanej i powtórzonej publikacji; komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_training_cohort_core.py -k immutable_publish`.
- Jedno pełne powtórzenie komendy CPU01 po poprawce fixture (`services/api/tests/test_grid_cohort_asset_retention.py services/api/tests/test_grid_training_cohort_core.py services/api/tests/test_grid_training_cohort_storage.py services/worker/tests/test_grid_cohort_gc.py`), aby mieć jeden zielony przebieg całego zestawu zamiast sumy CPU01 (75/7) i CPU02 (7/0).
- `services/api/tests/integration/test_grid_cohort_retention_edges_postgres.py` (tylko przy `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`): po detach źródła asercja, że nowe notices triggera i detach zawierają wyłącznie `SOURCE_REMOVED_NEW_USE_BLOCKED`; nadal nieuruchomione.

## Zakres przeglądu i ograniczenia

Przeczytano: raport R1 w całości, `TASK-0995_R2_VERIFIED_DELTA.patch` w całości, `TASK-0995_R1_CORRECTION_HANDOFF.md`, nagłówek i listę źródeł `TASK-0995_R1_CORRECTION_MANIFEST.json`, `TASK-0995_RESPONSE_CODEX.md`, instrukcje, task i fragment planu z briefu; w całości `grid_training_cohort_artifacts.py`, `grid_source_identities.py`, `test_grid_cohort_asset_retention.py`; fragmenty `grid_training_cohort_repository.py:250-319`, `0163_grid_training_cohorts.py:185-234`, `test_grid_training_cohort_core.py:395-424,560-750`, `test_grid_training_cohort_storage.py:1-60,205-250` oraz zależności wymienione w streszczeniu. Dowody korekty sprawdzono z plików JSON (CPU01 failed z 7 nowymi fixture-failures i PASS testu rezyduum, CPU02 passed 7/7, Ruff/format/mypy/migration mypy/map check returncode 0, sourceUnchanged i cleanup true). Nie porównywano SHA manifestu z dyskiem i nie weryfikowano niezależnie, że pozostałe 70 plików źródłowych nie zmieniły się poza deltą; przyjęto deklarację root o SHA-verified delcie. Nie uruchamiano testów, Ruff/mypy, OpenAPI check, docs/code-map check ani PostgreSQL; wyniki E2E, PG, HTTP i cleanup pochodzą wyłącznie z deklaracji Outcome/handoff i pozostają niezweryfikowane. Nie czytano `.env`, surowych logów połączeń ani pozostałych 726 KB materiału R1 poza fragmentami potrzebnymi do zależności delty. Nie oceniano przyszłych zacommitowanych prac ani `CURRENT_STATE.md`.
