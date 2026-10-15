# Audyt TASK-1003 — Podgląd i raport ponownego rozpoznania

Werdykt: PASS
Audytor: claude-fable-5-1, reasoning medium
Wykonawca: gpt-6.1-sol, reasoning medium
Zakres: a688a40108f33ede3a894002a6fc8a8ed53d8141...a688a40108f33ede3a894002a6fc8a8ed53d8141 oraz zmiany niezacommitowane, data 2026-10-15
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Runda 2 ograniczona do delty wobec R1: zamknięcie P1-1 (producent `notRecordedTargetCount`) oraz poprawki P2-2, P2-3, P2-4, P2-5 i świadomie przyjęte P2-1. Producent istnieje i działa w trzech wymaganych miejscach: po finalizacji manifestu, w transakcji źródła workera i w terminalnym `synchronize_grid_job` przed nowym `reportSha256`; pole zostało usunięte z addytywnych `EFFECT_FIELDS`, walidacja odmawia zamiast clampować, legacy i mieszany pin nie są dotykane. Dowody red/green (2 FAIL → 2 PASS), 11 PASS hash/cleanup, 37 PASS backend i 3 PASS PG na izolowanej bazie są spójne z kodem. Główne pozostałe ryzyko: walidacja `STATS_INVALID` działa także w terminalnej ścieżce FAILED/CANCELLED ze zgodnym pinem, a pełne PG po zmianie uruchomiono tylko dla trzech z ośmiu scenariuszy pliku stats.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/grid_reinference.py:733` — `SET LOCAL statement_timeout='30s'` obowiązuje do końca transakcji finalizacji. Wykonawca jawnie przyjął ryzyko w tasku (`ai_docs/tasks/1003-grid-reinference-preview-and-report.md:201-204`) i w API_CONTRACT (`ai_docs/architecture/API_CONTRACT.md:4022-4023`); dodatkowo repozytoryjny `bind()` ustawia ten sam limit dla każdej transakcji (`storage/grid_reinference.py:91`), więc ścieżka finalizacji nie jest wyjątkiem. Akceptacja ryzyka, bez poprawki.
- [P2-6] `services/api/src/game_predictor_api/storage/grid_reinference.py:964-968` z `application/grid_reinference_stats.py:64-65` — `refresh_effect_gap` jest wywoływany przed rozgałęzieniem statusu, więc przy zgodnym pinie i uszkodzonych licznikach (`recordedTargetCount` ujemny lub większy od `targetCount`) także przejście FAILED/CANCELLED kończy się `STATS_INVALID` i cofnięciem zamknięcia dzierżawy. Kontrakt korekty zwalnia z blokady tylko błędny lub mieszany pin, nie uszkodzone sumy, a odmowa clampowania jest zamierzona. Ryzyko niskie: liczniki produkuje wyłącznie ten sam kod w atomowych transakcjach. Proponuję odnotować w Outcome jako świadomy wybór fail-closed, bez zmiany kodu.
- [P2-7] `artifacts/audits/TASK-1003_R2_RUNS.jsonl:14` wobec `services/api/tests/integration/test_grid_reinference_postgres.py:534, 789, 840` — nowe asercje gap (prepared = `targetCount`, replay/completed = 0) obejmują wszystkie scenariusze parametryzacji, ale po zmianie uruchomiono PG tylko z filtrem `cancel_between_sources or rollback_retry or inconsistent_partial`. Scenariusze `accepted`, `unchanged`, `grid_issue`, `target_conflict`, `deferred_stats` z `test_grid_reinference_stats_postgres.py:32-39` nie mają zielonego dowodu po edycji testu. Logika dla nich wynika z kodu (każdy cel otrzymuje `recordedTargetCount=1` w `grid_reinference_handler.py:405-409`, więc gap po COMPLETED wynosi 0), lecz nie została wykonana. Proponuję przed commitem uruchomić cały plik `test_grid_reinference_stats_postgres.py` na izolowanej bazie.
- [P2-8] `ai_docs/tasks/1003-grid-reinference-preview-and-report.md:243` — dopisana komenda `npm run test:geometry --workspace @game-predictor/admin` jest w bloku Verification, a jej pełny wynik to FAIL 226/236 z powodu niezmienionych plików SuperGame (`artifacts/audits/TASK-1003_R2_admin_geometry_01.log:250-253`). Rozbieżność jest jawnie opisana w Outcome (`:304, :311`) i poza zakresem 1003; baseline potwierdzono tylko czystym helperem, nie pełnym przebiegiem na HEAD. Decyzja leada: przyjąć czerwony wynik jako znany dług z osobnym taskiem albo wykonać pełny baseline na czystym HEAD przed integracją. Bez poprawki w tym tasku.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| P1-1: `notRecordedTargetCount` = bieżące `targetCount − recordedTargetCount`, nie addytywne | spełnione | `application/grid_reinference_stats.py:23-32` (pole poza `EFFECT_FIELDS`), `:50-55` (empty_effect z 0), `:58-66` (helper, odmowa bez clamp) |
| Producent po finalizacji manifestu | spełnione | `storage/grid_reinference.py:761-767`; PG `test_grid_reinference_postgres.py:534` |
| Producent w atomowej transakcji źródła | spełnione | `grid_reinference_handler.py:409-414` (po `add_counts`, przed `progress`); PG `:718-719` (recorded 2 / gap 1 po cancel) |
| Producent w terminalnym sync przed nowym reportSHA; replay nie dubluje | spełnione | `storage/grid_reinference.py:964-968, 984-995`; `test_grid_reinference_stats.py:135, 155` (gap 99 → 0 w hashu, powtórne sync bez zmiany), `:223-244` |
| FAILED/CANCELLED zachowuje gap; legacy i mieszany/nieznany pin bez zmian | spełnione | `test_grid_reinference_stats.py:196-220` (gap 2), `:170-205` (pin `unsupported` i mieszany, `{"untouched": True}` nietknięte); red `TASK-1003_R2_gap_red.log` 2 FAIL → `gap_green.log` 2 PASS; `gap_cleanup_hash_green_02.log` 11 PASS |
| Rollback źródła zachowuje poprzedni gap; COMPLETED daje 0 | spełnione | PG `test_grid_reinference_postgres.py:699, 759-761, 789, 840`; `TASK-1003_R2_pg_gap_01.log` 3 PASS; receipt `TASK-1003_R2_PG_01_PG_RECEIPT.json` (owner zgodny, PID [], remaining 0) |
| P2-2: pin/capacity raz na `prepare_page` | spełnione | `storage/grid_reinference.py:651-662, 689` |
| P2-3: usunięte tylko martwe helpery Admina, backend/SDK zachowane | spełnione | `model-quality-actions.ts:174-183` (zawężony `Pick`); brak referencji `previewPendingGridReinference`/`startPendingGridReinference` w `apps/admin/src`; pułapka w `grid-reinference-preview.test.mjs:398-402` |
| P2-4: rzeczywista komenda test:geometry w Verification | spełnione z zastrzeżeniem P2-8 | `ai_docs/tasks/1003-grid-reinference-preview-and-report.md:243`; `ADMIN_INTERACTIONS_1.log` 19/19 PASS, `admin_geometry_01.log` 226/236 |
| P2-5: nowy pin bez manifestu pokazuje nieukończony zakres, legacy „nie zapisano” | spełnione | `grid-reinference-report.tsx:33-35, 86-87, 121-122`; test `grid-reinference-preview.test.mjs:667-735` |
| Dokumentacja odpowiada zachowaniu | spełnione | `API_CONTRACT.md:4015-4023`, `ADMIN_APP.md:2042-2046`, `DECISION_LOG_2026.md:57`, `DECISION_LOG.md:277` |
| Stary preview → konflikt; utrata odpowiedzi; zmiana gry; automatyczne niezaznaczone | spełnione (bez zmian od R1) | dowody R1 (`TASK-1003_AUDIT_claude-fable-5-1_R1.md:37-41`); regresja `ADMIN_INTERACTIONS_1.log` 19/19 PASS |
| Wyniki kontroli, audytu i ograniczenia w Outcome; dokumentacja odpowiada zachowaniu | niezweryfikowane (wpis R2 należy do leada) | Outcome zawiera R1 i rundę poprawek (`1003-…md:294-311`); werdykt R2 powstaje tym raportem i wymaga dopisania przez leada |

## Listy zamknięte i otwarte

Zamknięte: P1-1 (producent w trzech miejscach: `storage/grid_reinference.py:767, 964-968`, `grid_reinference_handler.py:412`; red/green `gap_red.log` → `gap_green.log`; PG `pg_gap_01.log`), P2-2 (`storage/grid_reinference.py:651-662`), P2-3 (`model-quality-actions.ts:174-183`, brak konsumentów w `apps/admin/src`), P2-4 (`1003-…md:243`, komenda wykonana), P2-5 (`grid-reinference-report.tsx:33-35, 86-87, 121-122`; test `:667-735`).

Otwarte: P2-1 (zaakceptowane ryzyko), P2-6, P2-7, P2-8.

## Proponowane testy

- Pełny przebieg `services/api/tests/integration/test_grid_reinference_stats_postgres.py` bez filtra `-k` na izolowanej bazie z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, aby pokryć nowe asercje gap dla `accepted`, `unchanged`, `grid_issue`, `target_conflict`, `deferred_stats` (P2-7); timeout 120 s, własny `--basetemp`.
- `services/api/tests/test_grid_reinference_stats.py`: przypadek FAILED ze zgodnym pinem i `recordedTargetCount > targetCount`, dokumentujący jawnie, że terminalne cleanup kończy się `GRID_REINFERENCE_STATS_INVALID` (P2-6), jeśli lead potwierdzi ten wybór; komenda `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_reinference_stats.py -k not_recorded`.
- Pełny `npm run test:geometry --workspace @game-predictor/admin` na czystym HEAD v1.7.380 (osobny worktree) jako baseline dziesięciu błędów SuperGame przed integracją (P2-8).

## Zakres przeglądu i ograniczenia

Przeczytano brief z patchami R1→R2 i raport R1 oraz odpowiedź wykonawcy, a w worktree zweryfikowano aktualną treść: `application/grid_reinference_stats.py` w całości, `storage/grid_reinference.py:84-145, 700-770, 930-1007`, `grid_reinference_handler.py:340-415`, `grid-reinference-report.tsx` w całości, `model-quality-actions.ts:170-215`, `types.gen.ts:6480-6576`, fixture i nowy test w `grid-reinference-preview.test.mjs`, parametryzację i nowe asercje w `test_grid_reinference_postgres.py`, listę scenariuszy `test_grid_reinference_stats_postgres.py`, wpisy w `API_CONTRACT.md`, `ADMIN_APP.md`, `DECISION_LOG_2026.md`, `DECISION_LOG.md` oraz logi R2 (`gap_red`, `gap_green`, `gap_cleanup_hash_green_02`, `backend_green_1`, `pg_gap_01`, `ADMIN_INTERACTIONS_1`, `ADMIN_ACTION_UNIT_1/2`, `admin_geometry_01`, `supergame_pure_baseline_01`), `RUNS.jsonl`, `PG_01_PG_RECEIPT.json` i `R2_IMPLEMENTATION_EVIDENCE.json`. Nie audytowano ponownie niezmienionej implementacji z R1 (keyset, collector, komendy Admina). Nie uruchamiano testów, lintu, typecheck ani SQL; wyniki przebiegów przyjęto z zachowanych logów bez niezależnej reprodukcji, a zgodność SHA plików z evidence nie była liczona. Nie oceniano wydajności szerokiego zakresu ani zachowania w przeglądarce.
