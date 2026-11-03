# Audyt TASK-1131 — Import zamienników i zamknięcie rezerwacji

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: 6af10ac0149df93ce845326e1eadf0308c92993e (v1.7.530) oraz niezacommitowane zmiany C2, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików i nie zapisał raportu na dysku.

## Streszczenie

Sprawdziłem cały łańcuch C2: walidację wyboru, świeże dopuszczenie w bazie, przypięcie joba, materializację po stronie workera, wiązanie całego zdjęcia, roboczy undo, restored, migrację 0176, ślad źródła w publikacji mobile oraz UI admina. Najważniejsze invarianty są zachowane:

- odmowy przed jakąkolwiek mutacją,
- `scopeDigest` z niezmiennego `batch.document`,
- wspólna transakcja przy tworzeniu joba,
- odtworzenie zapisanego wyniku (receipt) przed sprawdzeniem rewizji,
- atomowe zamknięcie osieroconych review przed usunięciem slotów,
- whitelist w 0176 domyka brak review (NULL) bezpiecznie,
- publikacja mobile odmawia staremu datasetowi pod blokadą SHARED.

Główne ryzyko to krótkie okno wyścigu (TOCTOU) przy projekcji geometrii przez spóźnionego workera (P2-1). Nie znalazłem P0 ani P1.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/images/pipeline_store.py:335` — `project_source_geometry` wywołuje `require_open_admission`, zanim weźmie blokadę własności. Blokadę bierze dopiero `append()` (`services/api/src/game_predictor_api/storage/image_geometry_v2_repository.py:111`). Przy READ COMMITTED restore może się zatwierdzić między sprawdzeniem a blokadą. Wtedy spóźniony worker dopisze rewizję geometrii źródła, które już ma fazę restored. Review ani plansz to nie tworzy, bo projekcja plansz jest prawidłowo chroniona w liniach 456–461. **Poprawka:** wywołać `acquire_sequence_ownership_lock(session, game_id=job.game_id)` przed linią 335, w tej samej kolejności co w linii 456.
- [P2-2] `services/api/src/game_predictor_api/storage/source_replacement_restore.py:57-79,107-112` — zapytanie `_working` łączy przez LEFT JOIN review (`r.status<>'superseded'`, więc razem z rejected) i pending geometry (`pending/resolved/rejected`) bez wymogu jednego wiersza na numer. Jeśli na sekwencji slotu leży osierocone review rejected lub druga pending geometry, wiersze się mnożą. Wtedy `len(slots) != len(proof.sequences)` i entry nigdy nie osiąga `ready_to_restore`, a operator dostaje mylący `REVIEW_INCOMPLETE`. Dodatkowo `canonical_ids` ma duplikaty. Mechanizm zamyka się bezpiecznie, więc to problem dostępności, nie bezpieczeństwa. **Poprawka:** filtrować review po `sl.bound_review_id` (lub agregować per numer) i jawnie zgłaszać niejednoznaczność.
- [P2-3] `services/api/src/game_predictor_api/storage/source_replacement_restore.py:93` — `identity_is_current(s, s)` porównuje snapshot sam ze sobą, więc filtr nic nie robi. Świeżość i tak jest wymuszona przez porównanie tożsamości i rewizji w liniach 140–147 oraz przez `SNAPSHOT_SQL` z `source_replacement_current_v1` (`services/api/src/game_predictor_api/storage/symbol_readability.py:49-51`). **Poprawka:** usunąć warunek albo porównywać z planned reason lub świeżym cropem. Inaczej kod sugeruje gwarancję, której nie daje.

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód |
|---|---|---|
| Request A+B → importowane wyłącznie wybrane A; realny SHA, bez recropu | spełnione | `domain/source_replacement_admission.py:28-77` (podzbiór, zakres ≤9, unikalny SHA, SHA ≠ stary); `storage/source_replacement_admission.py:196-208` (serwerowy manifest: SHA i zakres) |
| Błędny lub obcy SHA, zakres, entry, rewizja, job → odmowa przed mutacją | spełnione | `storage/source_replacement_admission.py:99-180` (PLAN_DRIFT, REVISION_CONFLICT, RESERVED, SHA_SCOPE_CONFLICT przed UPDATE w 246-267); `:223-235`; `:280-293` |
| Replay staging, startu i discovery po restarcie lub utracie odpowiedzi bez duplikatów | spełnione | `api/image_imports.py:1163-1184` (startReceipt przed FS i `ready_selection`); `storage/job_repository.py:221-247` (wspólna transakcja); `pipeline_store.py:210-248` (materializacja także przy rehydracji) |
| Provisional niewidoczne; powtórna korekta zachowuje tożsamość i wiąże całe zdjęcie | spełnione | 0176 i 0175 `current_v1` (reserved → niewidoczne); `storage/image_review_repository.py:657-689` (zawężony, nietrwały odczyt kolejki); `source_replacement_binding.py:153-219`; test `test_source_replacement_manual_postgres.py:133-205` |
| Partial/rejected zostaje w entry z rezerwacjami; verified working undo | spełnione | `geometry_rejection_revert.py:367-463` (adapter roboczy, receipt w `source_replacement_commands`, replay przed blokadami w 361-364) |
| Restored: wszystkie canonical z jednego nowego source, świeża ocena pikseli, orphan i late worker zamknięte przed usunięciem slotów | spełnione (z P2-1, P2-2) | `source_replacement_restore.py:120-147` (receipt przed CAS, `READABILITY_STALE`), `:166-273` (zamknięcie orphan, potem DELETE slotów); `source_replacement_admission.py:326-338`; UI `source-replacement-working.tsx:332-380` (`onLoad` warunkiem checkboxa) |
| Stary SHA/source pozostaje retired; historia chroniona | spełnione | restore nie dotyka `source_replacement_retired`; `source_replacement_sources` zachowane (test `:393-399`) |
| 0176 tylko w zakresie SQL current/excluded i indeksu | spełnione | `0176_source_replacement_closed.py:66-109`; bazowy SQL zgodny z 0175 (`0175_source_replacement_guards.py:29-59`); brak review (NULL) → wykluczone; downgrade blokowany, gdy istnieje restored |
| Zwycięska geometria po restored edytowalna zwykłą ścieżką | spełnione | test `test_source_replacement_manual_postgres.py:206-223` |
| Nowa publikacja mobile odmawia staremu datasetowi; historia bez zmian | spełnione | `mobile_source_proof.py:62-128` (bez backfillu: tylko `status='staging'` i `source_board_id IS NULL`); worker `releases/store.py:46-96` (SHARED, re-entrant ContextVar); `mobile_release_repository.py:94-118` |
| Testy, typy/lint, docs/map | niezweryfikowane przez audytora | wyniki raportowane w Outcome `ai_docs/tasks/1131-source-replacement-import.md:104-112`; mypy zawężony (follow-imports=skip) — ograniczenie jawnie opisane |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2, P2-3.

## Proposed tests

- PG: restore, gdy na sekwencji slotu istnieje dodatkowe review rejected lub pending (dziś orphan w teście ma `sequence_number=None` i pending na 2002, `test_source_replacement_manual_postgres.py:308-345`). Oczekiwanie: jawna odmowa zamiast cichego „not ready”, albo poprawne zamknięcie orphan.
- PG: wyścig restore kontra `project_source_geometry` (dwie sesje; worker zatrzymany po `require_open_admission`). Oczekiwanie po poprawce P2-1: `ADMISSION_CLOSED`, brak nowej rewizji geometrii. Komenda: `pytest services/api/tests/integration/test_source_replacement_working_undo_postgres.py -k late` z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`.

## Zakres przeglądu i ograniczenia

Przeczytane w ograniczonych zakresach:
- szablon audytu, task 1131, plan 70–107;
- warstwa domenowa i storage admission w całości;
- `job_repository.py` 170–259, `application/jobs.py` 664–718;
- `pipeline_store.py` 150–349 i 430–479, `production_workflow.py` 755–800;
- `source_replacement_binding.py` i `source_replacement_restore.py` w całości, migracja 0176 w całości;
- `geometry_rejection_revert.py` 340–604, `image_review_repository.py` 630–692;
- `mobile_source_proof.py` w całości, `releases/store.py` 40–119, `mobile_release_repository.py` 80–129;
- `api/image_imports.py` 630–674 i 1150–1249;
- `source-replacement-working.tsx` 140–389, test manual PG 195–439, `SNAPSHOT_SQL`.

Reszta sprawdzona tylko przez Grep: 0175, schematy, lokalizacje blokad.

Nie przeczytane: `replacement-import-picker.tsx`, `replacement-start-recovery.tsx`, `test_source_replacement_working_undo_postgres.py`, `test_replacement_browser_api.py`, test wrappera klienta, schematy `source_replacement`/`jobs` w szczegółach oraz pliki generated/OpenAPI. W tych miejscach polegam na wynikach wykonawcy.

Nie uruchamiałem testów, typechecku, lintu ani usług. Pełny typecheck i build backendu oraz regresja APK należą do D1.

## Rozliczenie wykonawcy po R1

Rzeczywisty `modelUsage` CLI: `claude-opus-5-5`, uruchomienie z `--effort high`, exit0. P0/P1 brak; bez zmian kodu i bez rundy2.

P2-1: sprostowanie na podstawie istniejącego callchain, nie poprawka. `project_source_geometry` wywołuje `_require_candidate_lease` przed odczytem źródła i `require_open_admission` (pipeline_store.py:310–335). Helper już bierze ownership lock w tej samej transakcji (pipeline_store.py:1421–1422), więc wskazane okno między open-check a pierwszą blokadą nie występuje.

P2-2 pozostaje przyjętym ograniczeniem dostępności dla dodatkowych, niejednoznacznych orphan na tej samej sekwencji: workflow odmawia zakończenia, nie publikuje niewłaściwego źródła. P2-3 pozostaje redundantnym filtrem; autorytatywne sprawdzenie bieżącej identity/revision przy restore działa niezależnie. Pilny zakres operatora kończy rozpoczęty workflow jednego zdjęcia; nie dodano kolejnych wariantów ani testów hipotetycznych. Oryginalny raport audytora powyżej pozostawiono bez zmian.
