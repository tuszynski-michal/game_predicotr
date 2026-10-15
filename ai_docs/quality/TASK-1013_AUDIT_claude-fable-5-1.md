# Audyt TASK-1013 — Trwałe propozycje dla „Złej siatki”

Werdykt: PASS
Audytor: claude-fable-5-1, reasoning high
Wykonawca: gpt-6.1-sol, reasoning high
Zakres: 62e9f71986a74d67776eabad6e99154f4d18c0b2...62e9f71986a74d67776eabad6e99154f4d18c0b2 (brak nowych commitów) oraz zmiany niezacommitowane i pliki nieśledzone z briefu R2, data 2026-10-15
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Runda 2 ograniczona do delty R1→R2: zbadano poprawki P0-1 (kwalifikacja w edytowanej propozycji), P1-1 (RLS na nowych partycjach z lifecycle) oraz bezpośrednio powiązane P2-1–P2-3, wraz z nowymi testami jsdom, PostgreSQL i jednostkowymi, dokumentacją ADMIN_APP i taskiem. Oba znaleziska blokujące są zamknięte zgodnie z kontraktem zapisanym przed zmianą: fallback kwalifikacji działa tylko przy braku wyliczonej wartości, serwer nadal wymaga jawnej kwalifikacji i 24 węzłów, a provisioning obu nowych tabel włącza i wymusza RLS z jedną polityką. Pozostałe ryzyka dotyczą niezawodności fixture PostgreSQL, zależności testu jsdom od interpretera Pythona i jednego zdania w kontrakcie API.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/tests/integration/test_grid_geometry_proposals_postgres.py:112-127` — teardown fixture odmawia `DROP DATABASE`, gdy `pg_stat_activity` pokazuje jakikolwiek backend bazy po `engine.dispose()`. Zamknięcie backendu w PostgreSQL jest asynchroniczne, więc guard okresowo trafia na własne, już zwolnione połączenie (log `TASK-1013_R2_pg_discovery_final.log:61-65`, PID 354153); baza i rola zostają do ręcznego recovery, a uruchomienie kończy się FAIL mimo zaliczonych asercji. To już drugi taki przypadek (R1 RLS, R2 discovery). Propozycja: po `dispose()` ograniczone oczekiwanie (np. do 5 s z odpytywaniem `pg_stat_activity`) zanim guard odmówi; bez zabijania połączeń i bez osłabiania warunku właściciela. Można też odnotować jako część długu P2-4.
- [P2-2] `apps/reviewer/test-interactions/grid-geometry-proposals.test.mjs:383-430` — test jsdom uruchamia interpreter Pythona (`spawnSync`) z fallbackiem `'python'` i `PYTHONPATH=services/api/src`, więc `npm run test:geometry` zależy od venv z pydantic i importowalnym `game_predictor_api`. Suite nie wchodzi do `npm test` ani `quality` (`package.json:118,143`), błąd jest jawny przez status/stderr, a wariant daje realną walidację backendu wymaganą przez kontrakt R1. Akceptacja ryzyka z krótkim komentarzem w nagłówku testu o wymaganym venv.
- [P2-3] `ai_docs/architecture/API_CONTRACT.md:3992-3993` — kolekcja po poprawce pomija wyniki `proposal_ready`, które nie przechodzą strukturalnej walidacji kandydata (`services/api/src/game_predictor_api/storage/grid_geometry_proposals.py:210-215`), a kontrakt mówi tylko o „do 100 niezapisanych wyników proposal_ready”. Propozycja: jedno zdanie, że strukturalnie niepoprawny wynik jest pomijany w kolekcji, a create odmawia go jawnie (409). Może pozostać jako dług dokumentacyjny.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Utworzenie nie zmienia cropów ani zgłoszenia | spełnione | bez zmian od R1: `services/api/src/game_predictor_api/storage/grid_geometry_proposals.py:288-348` wstawia tylko proposal i event; regresja PG z R1 zachowana w archiwum |
| Przyjęcie działa raz, zapisuje autora i zamyka właściwy problem | spełnione | tryb model bez zmian od R1; tryb edited przez UI: `apps/reviewer/src/features/operational-reviews/grid-geometry-proposals.tsx:278-283` uzupełnia tylko brak kwalifikacji, `board-geometry-correction-target.ts:643-653` daje pierwszeństwo wyliczonym partial/exclude, `deferred-board-cell-geometry-editor.tsx:248` nie pozwala na węzły poza zdjęciem bez flagi partial, kandydat ma zawsze kwalifikację complete (`storage/grid_geometry_proposals.py:583`); serwer bez zmian (`schemas/grid_geometry_proposals.py:29-37`); test `grid-geometry-proposals.test.mjs:301-432` waliduje realne ciało `ProposalAcceptCommand` i odmowę null; log `TASK-1013_R2_ui_green3.log` pass 5, fail 0 |
| Zmieniona rewizja daje konflikt | spełnione | bez zmian od R1: `storage/grid_geometry_proposals.py:355-377`; rejected sibling nie daje już fałszywego stale: `virtual_grid_geometry_repository.py:2805`, test `test_grid_geometry_proposals_postgres.py:550-569,639`, log `TASK-1013_R2_pg_green.log` 4 passed |
| Odrzucenie pozostawia zgłoszenie otwarte | spełnione | bez zmian od R1: `storage/grid_geometry_proposals.py:359-366` nie wywołuje writera |
| Wyniki kontroli, audytu i ograniczenia w Outcome; dokumentacja odpowiada zachowaniu | spełnione | Outcome taska sekcje „R1 correction round” i „Not completed”; `ai_docs/requirements/ADMIN_APP.md:1662-1666` opisuje montaż tylko w widoku zgłoszeń i fallback kwalifikacji; `ai_docs/architecture/DATA_MODEL.md:11-12` jest teraz prawdziwe dzięki `game_partition_lifecycle.py:221-237`; wpis wyniku R2 należy do leada; jedyna luka to P2-3 |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): R1 P0-1 — `grid-geometry-proposals.tsx:282-283` plus test `grid-geometry-proposals.test.mjs:301-432` z realnym walidatorem Pydantic i wariantem partial/exclude, serwer bez zmian; R1 P1-1 — `game_partition_lifecycle.py:226-227` oraz asercje `test_grid_geometry_proposals_postgres.py:866-881` (enabled/forced/1 policy na dzieciach obu gier) i `:913-916` (bezpośredni child obcej gry 0, własnej 1), red `TASK-1013_R2_pg_red.log:371` pokazuje (False, False, 0) przed poprawką; R1 P2-1 — wąski catch `storage/grid_geometry_proposals.py:210-215`, regresja PG `:676-724` i unit `test_grid_geometry_proposals.py:38-46` dla propagacji innych błędów; R1 P2-2 — filtr `virtual_grid_geometry_repository.py:2805` zgodny z `grid_reinference.py:460`, regresja z rejected_history; R1 P2-3 — `operational-review-workspace.tsx:1135-1143` montuje panel tylko w `needs_grid_fix`, test `grid-geometry-proposals.test.mjs:181-283` potwierdza zero GET poza widokiem; R1 P2-4 — przyjęty przez leada jako dług utrzymania (`ai_docs/quality/TASK-1013_CORRECTION_CODEX.md:17`).

Otwarte: P2-1, P2-2, P2-3 (numeracja tej rundy).

## Proponowane testy

- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py` (fixture `database`): po ograniczonym oczekiwaniu na zwolnienie backendów ponowne uruchomienie `-k discovery_skips` powinno zakończyć się bez odmowy teardown; polecenie z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'` na izolowanej bazie: `.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_geometry_proposals_postgres.py -k discovery_skips`.
- `apps/reviewer/test-interactions/grid-geometry-proposals.test.mjs`: trzeci wariant edycji z `item.geometryQualification` ustawionym (persisted) i bez flag, z asercją, że wysłana kwalifikacja pochodzi z przeliczenia, nie z kandydata; polecenie: `npm run test:geometry --workspace @game-predictor/reviewer`.

## Zakres przeglądu i ograniczenia

Przeczytano: brief R2 z dokładnymi diffami R1→R2, raport R1, odpowiedź wykonawcy, scope i evidence JSON R2, aktualną treść zmienionych plików (`grid-geometry-proposals.tsx`, `operational-review-workspace.tsx` fragmenty, test jsdom, `game_partition_lifecycle.py`, `storage/grid_geometry_proposals.py`, `virtual_grid_geometry_repository.py` w zakresie polityki current_live_slots, testy PG i unit) oraz niezmienione zależności potrzebne do oceny: `correctionGeometryQualification`, `boardLatticeQualification`, `allowOutsideSource`, `_candidate`, `_validate_result_scope`, filtr `source_targets`, schemat `ProposalAcceptCommand`, ADMIN_APP, DATA_MODEL, API_CONTRACT sekcja D-551, CURRENT_STATE sekcja TASK-1013. Z logów R2 sprawdzono linie podsumowań: pg_green 4 passed, ui_green3 pass 5/fail 0, unit 5 passed, pg_red 3 failed przed poprawką, pg_discovery_final 1 passed i błąd teardown. Nie uruchamiano testów, lintów ani usług; wyniki PASS przyjęto z logów wykonawcy. Nie weryfikowano ponownie artefaktów przypiętych hashem (OpenAPI, generated client, mapy) ani niezmienionych obszarów R1 poza miejscami, od których zależą poprawki. Ocena ścieżki UI opiera się na analizie statycznej i teście jsdom; brak potwierdzenia w przeglądarce.
