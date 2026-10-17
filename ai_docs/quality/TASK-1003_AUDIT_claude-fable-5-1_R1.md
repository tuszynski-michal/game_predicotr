# Audyt TASK-1003 — Podgląd i raport ponownego rozpoznania

Werdykt: REVISE
Audytor: claude-fable-5-1, reasoning medium
Wykonawca: gpt-6.1-sol, reasoning medium
Zakres: a688a40108f33ede3a894002a6fc8a8ed53d8141...a688a40108f33ede3a894002a6fc8a8ed53d8141 oraz zmiany niezacommitowane, data 2026-10-15
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano cały pion taska: schematy i router API, repozytorium `storage/grid_reinference.py` (view, prepare, execute, prepare_page, finalize_preparation, synchronize_grid_job), nowy moduł `grid_reinference_stats.py`, collector w `virtual_grid_geometry_repository.py`, handler workera, wrapper klienta i test transportu, nowe moduły Admina z testami interakcji oraz dokumentację owner. Pin polityki statystyk, keyset historii, filtr pilotów, atomowość receiptów, GET-only wejście, trwałe polecenia i odrzucanie spóźnionych odpowiedzi są zaimplementowane zgodnie z Technical notes i D-551; cztery przypadki testowe taska mają pokrycie w testach interakcji. Główne ryzyko: pole `notRecordedTargetCount` z kontraktu effectStats nie ma żadnego producenta i zawsze pokazuje zero, także dla operacji przerwanych z nieprzetworzonymi celami, co jest fikcyjną liczbą w raporcie operatora.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/src/game_predictor_api/application/grid_reinference_stats.py:32` — pole `notRecordedTargetCount` jest zadeklarowane w `EFFECT_FIELDS`, w DTO (`schemas/grid_reinference.py:93`) i w kontrakcie Technical notes, ale nigdzie w `services/` nie jest inkrementowane ani wyliczane. Handler workera (`services/worker/src/game_predictor_worker/images/grid_reinference_handler.py:404-408`) nadaje każdemu przetworzonemu celowi `recordedTargetCount=1`, a ścieżki terminalne FAILED/CANCELLED/COMPLETED w `services/api/src/game_predictor_api/storage/grid_reinference.py:965-995` nie uzupełniają różnicy `targetCount − recordedTargetCount`. Skutek: raport w `apps/admin/src/features/model-quality/grid-reinference-report.tsx:146` pokazuje „Pozycje bez zapisanych statystyk: 0” także dla operacji przerwanej lub anulowanej z nieprzetworzonymi celami (scenariusz `inconsistent_partial_stats` ma `targetCount` 3 i `recordedTargetCount` 0), czyli fikcyjne zero, którego kontrakt zakazuje. Proponowana poprawka: przy przejściu terminalnym nowego pinu (`synchronize_grid_job`, gałęzie FAILED/CANCELLED/COMPLETED) ustawić `notRecordedTargetCount = targetCount − recordedTargetCount` w tej samej transakcji, a w `test_grid_reinference_stats.py` oraz w scenariuszu `inconsistent_partial_stats` dodać asercję wartości niezerowej. Alternatywnie usunąć pole z DTO, OpenAPI, klienta, UI i dokumentacji; wtedy wymagany ponowny `openapi:generate`.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/grid_reinference.py:732` — `SET LOCAL statement_timeout='30s'` obowiązuje do końca transakcji, nie tylko dla zapytania DISTINCT. W ścieżce `synchronize_grid_job` (WAITING_FOR_REVIEW) finalizacja działa w transakcji zamknięcia dzierżawy workera, więc limit obejmie też późniejsze flush/aktualizację joba. Ryzyko niskie przy małych statementach; proponuję przywrócić poprzednią wartość po zapytaniu (`SET LOCAL statement_timeout` na zapamiętaną wartość) albo odnotować akceptację ryzyka w Outcome.
- [P2-2] `services/api/src/game_predictor_api/storage/grid_reinference.py:674-685` — `NeuralGridSnapshot.from_payload(d["modelSnapshot"])` i wyliczenie `capacity` wykonują się dla każdego celu w każdej stronie wyłącznie na potrzeby asercji i stałej pojemności. Dla szerokiego zakresu (setki tysięcy plansz) to zbędny koszt parsowania w nieskończonej pętli; proponuję wyliczyć `pin`/`capacity` raz na wywołanie `prepare_page`, przed pętlą po źródłach.
- [P2-3] `apps/admin/src/features/model-quality/model-quality-actions.ts:184-185`, `:272`, `:296` — po usunięciu legacy pending-preview/start z `GridQualityPanel` helpery `previewPendingGridReinference` i `startPendingGridReinference` oraz wymagane przez `GridQualityClient` metody klienta pozostały jako martwy kod bez konsumenta. Task wymienia ten plik w Expected files. Proponuję usunąć helpery i zawęzić `Pick` typu, aby fixture'y testowe nie musiały udawać legacy metod.
- [P2-4] `ai_docs/tasks/1003-grid-reinference-preview-and-report.md:204` — blok Verification wymienia `npm run test --workspace @game-predictor/admin`, który uruchamia wyłącznie `test/*.test.mjs`. Nowy test pionu `apps/admin/test-interactions/grid-reinference-preview.test.mjs` uruchamia tylko `npm run test:geometry --workspace @game-predictor/admin`, którego w bloku brak. Proponuję dopisać tę komendę do Verification, aby następny przebieg kontroli nie pominął testu interakcji.
- [P2-5] `apps/admin/src/features/model-quality/grid-reinference-report.tsx:84` z `services/api/src/game_predictor_api/storage/grid_reinference.py:140` — `scopeStats` jest nullowane, gdy brak `manifestSha256`, więc nowa operacja, która zawiodła lub została anulowana w fazie prepare, pokazuje „Statystyki zakresu: nie zapisano”, czyli etykietę zarezerwowaną w kontrakcie dla operacji legacy. UI rozróżnia tylko stan `preparing`. Proponuję rozróżnić po `statsPolicy` (nowy pin bez manifestu → „niedostępne, zakres nie został sfinalizowany”) albo zaakceptować ryzyko w dokumentacji.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Stary preview daje konflikt (HTTP 409 zachowuje polecenie, odrębne od conflict celu) | spełnione | `apps/admin/src/features/model-quality/grid-reinference-preview.tsx:231-241`; test `apps/admin/test-interactions/grid-reinference-preview.test.mjs:260-282`; backend `application/grid_reinference.py:59-64` |
| Utrata odpowiedzi odtwarza tę samą operację | spełnione | zapis body/UUID przed POST `grid-reinference-preview.tsx:223-228`, `grid-reinference-command.ts:56-70`; replay prepare `storage/grid_reinference.py:241-244`; test `grid-reinference-preview.test.mjs:222-258` |
| Zmiana gry nie miesza stanu | spełnione | keyed workspace `grid-reinference-preview.tsx:51`, generation token `:89-90`; test `grid-reinference-preview.test.mjs:326-361` oraz `:479-523` (spóźniony detail) |
| Wszystkie automatyczne nie są domyślnie zaznaczone | spełnione | `grid-reinference-state.ts:32-37`; test `grid-reinference-preview.test.mjs:179-184` |
| Wejście/reload GET-only, brak autopost i brak legacy start | spełnione | `grid-reinference-preview.tsx:161-214`; test `grid-reinference-preview.test.mjs:386-419` |
| Oddzielne liczby zdjęć, slotów, plansz, komórek; DISTINCT przy finalizacji; nullable dla legacy | spełnione z zastrzeżeniem P1-1 | `storage/grid_reinference.py:514-516, 673-694, 729-759`; `grid_reinference_stats.py:105-133`; testy `test_grid_reinference_stats.py:49-81`, `test_grid_reinference_stats_postgres.py:52-131` |
| Pin statsPolicy: oba absent legacy, mismatch fail-closed, replay/resume bez retrofitu, stary reportSHA zachowany | spełnione | `grid_reinference_stats.py:36-44`; `storage/grid_reinference.py:352, 457, 957-988`; testy `test_grid_reinference_models_and_cursor.py:366-446`, `test_grid_reinference_stats.py:117-182` |
| Keyset historii 1..50, cursor związany z grą/filtrem/scopeSignature, filtr pilota zgodny z ACK | spełnione | `storage/grid_reinference.py:147-202` vs `application/grid_reinference.py:74-82`; test `test_grid_reinference_stats.py:229-247` |
| Jeden pion API→OpenAPI→klient→wrapper→test transportu | spełnione | `packages/admin-api-client/src/index.ts:3174-3195`; `openapi/openapi.json` i `generated/*` zawierają `listGridReinferenceOperations`; test `test/grid-reinference-request.test.mjs:70-107` |
| Wyniki kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | niespełnione | audyt dopiero w tej rundzie; P1-1 oznacza, że dokumentacja effectStats (`API_CONTRACT.md:4008-4018`, `ADMIN_APP.md:2032-2037`) opisuje pole bez implementacji |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy, runda 1.

Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- `services/api/tests/test_grid_reinference_stats.py`: scenariusz terminalny FAILED z `targetCount` 3 i `recordedTargetCount` 1, asercja `notRecordedTargetCount == 2` oraz niezmienność pozostałych pól; komenda `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_reinference_stats.py -k not_recorded` (timeout 120 s).
- `services/api/tests/integration/test_grid_reinference_postgres.py`, scenariusz `inconsistent_partial_stats`: rozszerzyć asercje o `effectStats.notRecordedTargetCount == targetCount` po rollbacku; komenda z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1` na izolowanej bazie testowej.
- `apps/admin/test-interactions/grid-reinference-preview.test.mjs`: przypadek nowej operacji w stanie `failed` bez manifestu, asercja etykiety innej niż „nie zapisano” (po poprawce P2-5); komenda `npm run test:geometry --workspace @game-predictor/admin`.
- Dopisać `npm run test:geometry --workspace @game-predictor/admin` do bloku Verification taska i wykonać przed commitem (P2-4).

## Zakres przeglądu i ograniczenia

Przeczytano w całości brief z diffem śledzonych plików i treścią plików nowych, a w worktree zweryfikowano symbole wywoływane przez diff: `schemas/grid_reinference.py` (ApiModel z `extra="forbid"`, `GridReinferenceSelector`), `application/grid_reinference.py:1-134` (conflict, receipt_replay, command_transition, warunki pilot-ack), `storage/grid_reinference.py` (view, list_operations, prepare, execute, source_targets, prepare_page, finalize_preparation, worker_record, synchronize_grid_job, target_protection), `virtual_grid_geometry_repository.py:141-350`, `grid_reinference_handler.py:1-70, 200-440`, `virtual_grid_geometry.py` (`target_id`), unikalność `uq_image_symbol_review_cells_item_cell` w `models.py:2894`, mapowanie `JobConflictError` na 409 w `main.py:2666-2683`, helpery Admina (`apiErrorMessage`, `serializeAdminNavigation`, `buildPreparedLocalReviewUrl`), `apps/admin/package.json`, root `package.json` (gate), konfigurację ruff oraz obecność `listGridReinferenceOperations` w OpenAPI i wygenerowanym kliencie. Nie uruchamiano testów, lintu, typecheck, generacji OpenAPI ani zapytań SQL; poprawność zapytania JSONB DISTINCT na PostgreSQL, zgodność hashy wygenerowanego klienta i wyniki raportowane przez wykonawcę przyjęto na podstawie deklaracji w Outcome bez niezależnego potwierdzenia. Nie oceniano wydajności szerokiego zakresu ani zachowania w przeglądarce.
