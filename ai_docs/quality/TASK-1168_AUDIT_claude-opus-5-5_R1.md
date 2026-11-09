# Audyt TASK-1168 — Panel pełnych symboli, porównanie HTML i odbiór

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: a9951e94f8cb7ad1912c1888f3f47eb94cb5efea...HEAD oraz zmiany niezacommitowane (zamrożony pakiet F=`artifacts/audits/TASK-1168-R1-sources`), data 2026-11-09
Runda: 1
SHA pakietu: 8ddad260208ebce551fc9713e5bd4d3351bcf05eac3f71b0e33b4e3c4a86badb
Otwarte P0: 1
Otwarte P1: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano T5 w zakresie AC1–AC7: tryby zwykły i ślepy, trwałość komend, pion targets/asset, panel v6, generator HTML oraz trzy poprawki po T4. Izolacja ślepego trybu, CAS, pion API i poprawki P2 z T4 są poprawne. Blokuje błąd generatora: CLI szuka manifestu kohorty pod ścieżką, której prawdziwa publikacja nie tworzy, więc dla rzeczywistych kohort nie powstanie żaden dowód 15 PNG. Testy tego nie wykrywają, bo fixture zapisuje manifest pod inną nazwą. Podobnie `displayName` działa tylko w fixture.

## Znaleziska

### P0

- [P0-1] `F/services/worker/src/game_predictor_worker/images/comparison_production_bundle.py:57` — Trigger: `render_grid_correction_comparison.py --artifact-root` na raporcie v6 z rzeczywistą zamrożoną kohortą. Generator buduje ścieżkę `data/grid-training-cohorts/{game}/{cohort}/manifest.json`. Producent publikuje korzeń przez `publish_json` (`services/api/src/game_predictor_api/application/grid_training_cohort_commands.py:474`, zapis ścieżki `:550`), czyli jako `.../pages/{sha}.json` (`F/services/api/src/game_predictor_api/storage/grid_training_cohort_artifacts.py:110,132`). Skutek: `GridCohortSnapshot` zgłasza `DATASET_ASSET_UNAVAILABLE` (`F/services/worker/src/game_predictor_worker/images/grid_cohort_dataset.py:141`), wyjątek przechwytuje `comparison_production_bundle.py:72`, indeks ma zero wpisów, a każda plansza jest unavailable (`F/scripts/render_grid_correction_comparison.py:55-56`). Wynik jest uczciwy, ale AC5 pozostaje niespełnione: CLI nie produkuje pakietu dowodowego dla realnych danych. Fixture maskuje błąd, bo zapisuje `manifest.json` (`services/worker/tests/test_grid_cohort_dataset.py:166`). Pin raportu nie ma ścieżki (`services/api/src/game_predictor_api/schemas/grid_model_evaluations.py:123-126`). Poprawka: wyprowadzać `.../pages/{manifestSha256}.json` zgodnie z adresowaniem treścią i dodać test publikujący korzeń przez `GridCohortArtifactStore.publish_json`.

### P1

- [P1-1] `F/services/api/src/game_predictor_api/storage/grid_cell_content_targets.py:49` — Trigger: każda rzeczywista kohorta. Kod czyta `logicalName` ze źródła strony albo z `sourceIdentity`, lecz builder strony tego klucza nie zapisuje (`services/api/src/game_predictor_api/application/grid_training_cohort_commands.py:420-445`). Nazwa występuje tylko w populacji podziału (`services/api/src/game_predictor_api/storage/grid_correction_split.py:153`). Skutek: `displayName` jest zawsze null, a operator widzi przy każdym zdjęciu „Zdjęcie bez nazwy”. To narusza D-593, który wymaga wyboru „po nazwie/roli” z istniejącej nazwy logicznej (`F/ai_docs/process/decisions/DECISION_LOG_2026.md:57-60`). Zielony test ręcznie wstawia nieprodukowany klucz (`F/services/api/tests/test_grid_cell_content_targets.py:54,126`), a test PostgreSQL nie sprawdza nazwy. Poprawka: ograniczony odczyt istniejącej nazwy dla strony (safe basename, wyłącznie do wyświetlania) oraz asercja w PG. Alternatywnie jawna decyzja root zmieniająca kontrakt na stałe null.
- [P1-2] `F/apps/admin/test-interactions/grid-content-reference.test.mjs:171` — Task wymaga testów „loading/empty/error/retry-refresh” (`F/ai_docs/tasks/1168-full-symbol-panel-acceptance.md:187`), a AC2 bezpieczeństwa przy trwającym starym requeście. Pomocnik `hold` nie jest nigdzie użyty. Żaden test nie obejmuje nieudanego lub pustego odczytu kohort, celów, etykiet i sesji ani ponowienia (`F/apps/admin/src/features/model-quality/grid-content-reference-workspace.tsx:194-216,258,400`; `grid-content-blind.tsx:94,216`). Nie ma też testu błędu odczytu budżetu (`grid-correction-learning-panel.tsx:127-135,1178`). Kod wygląda poprawnie, ale deklaracja nie ma dowodu testowego. Poprawka: testy opóźnionej odpowiedzi starej sesji/celu po zmianie stanu oraz error/empty/retry dla nowych odczytów i budżetu.

### P2

- [P2-1] `F/services/worker/src/game_predictor_worker/images/comparison_production_cells.py:332` — `render_cells` bez lokalnej obsługi `ValueError` dla dopasowanej predykcji poza kadrem (`F/services/worker/tests/test_comparison_production_cells.py:208`). T3 notuje taki przypadek per model (`production_cell_evaluation.py:260-263`), a generator wyłącza całe zdjęcie: 9 plansz i oba modele. Bez fałszywego dowodu, ale z dużym zasięgiem. Propozycja: lokalne unavailable, po sprawdzeniu zgodności z zapisanym świadkiem.
- [P2-2] `F/services/worker/src/game_predictor_worker/images/comparison_production_cells.py:426` — Dokładna równość węzłów z odrębnego przebiegu porównawczego i oceny. Inny backend lub determinizm da uczciwe, lecz masowe unavailable. Nie da się tego rozstrzygnąć statycznie. Propozycja: pomiar na realnym zestawie albo akceptacja ryzyka.
- [P2-3] `F/services/worker/src/game_predictor_worker/images/comparison_production_cells.py:62`, `comparison_production_bundle.py:114` — PNG i indeks są nadpisywane bezwarunkowo, w przeciwieństwie do `_copy`. To własne, odtwarzalne wyjścia, ale obcy plik pod tą ścieżką zniknie. Propozycja: nie nadpisywać różnej zawartości bez znacznika generatora albo zaakceptować ryzyko.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| AC1 ordinary/blind | spełnione | Montaż `F/apps/admin/src/features/model-quality/grid-model-workspace.tsx:45-81`. Klient blind bez referencji `grid-content-blind.tsx:22-30`; ordinary `grid-content-ordinary.tsx:67,99`; B/REG `grid-content-reference.test.mjs:297-337`; blokada unresolved `:509-567`. Odczyt: nowe moduły w całości. |
| AC2 komendy, współrzędne, izolacja | spełnione (luka testu: P1-2) | Klucz i scope `grid-content-state.ts:111-117,189-198`; dokładny retry `grid-content-command-control.tsx:46-62`; tokeny `grid-content-blind.tsx:81,94`; sourceXY `grid-content-canvas.tsx:80-92`; testy `grid-content-reference.test.mjs:385-430,569-602,663-766`. Odczyt: całość. |
| AC3 targets/asset i liczniki | niespełnione (P1-1) | Snapshot i strony `F/services/api/src/game_predictor_api/storage/grid_cell_content_targets.py:34-111`; pin przed odczytem pliku `:128-143`; no-store `api/grid_cell_content.py:103-107`; strict writer `storage/grid_cell_content.py:169-175,249`; P2-5 `domain/grid_cell_content.py:233-245,295-304`; wrapper `F/packages/admin-api-client/src/index.ts:1906-1932`; request test `test/grid-cell-content-request.test.mjs:185-245`; PG `F/services/api/tests/integration/test_grid_content_targets_postgres.py:95-197`. Reviewer: brak tras content w `reviewer-proxy-policy.ts`. |
| AC4 panel v6 | niespełnione (P1-2) | Własny verdict `grid-content-evaluation-summary.tsx:21,115-121`; BASE/WIDE i automat `grid-correction-learning-panel.tsx:1467-1501`; budżet `:1163-1186`; test `grid-correction-learning-panel.test.mjs:274-383`. Odczyt: nowe moduły i zmienione zakresy. |
| AC5 HTML/produkcyjne piksele | niespełnione (P0-1) | Sink `F/services/worker/src/game_predictor_worker/images/production_cell_evaluation.py:66-132`; replay i piny `comparison_production_cells.py:207-382,384-446`; wejście NN `:80-137`; testy `test_comparison_production_cells.py:174-406`. Odczyt: całe nowe moduły, CLI i szablon. Logika dowodu jest poprawna; zawodzi lokalizacja manifestu. |
| AC6 handoff T4 | spełnione | P2-4 `production_cell_input.py:48-56`, reader `storage/grid_content_bundle.py:12-22`, test `test_full_symbol_proof_guards.py:17-33`; P2-5 `full_board_variant_context.py:120-130`, test `:65-89`; P2-6 `F/services/api/tests/test_full_board_input_variant.py:114-201`. |
| AC7 odbiór i uczciwość | spełnione | Rozdział QA i treningu `F/ai_docs/quality/FULL_SYMBOL_CROPS_ACCEPTANCE_20261109.md:53-54,107-118`; `TASK-1168_VERIFICATION.md:16-24,91,150,222`. Zdania o automatycznym pakowaniu (`ACCEPTANCE:91-92`) staną się prawdziwe dla realnych danych dopiero po P0-1. |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1, P1-1, P1-2, P2-1, P2-2, P2-3.

## Proponowane testy

- `services/worker/tests/test_comparison_production_cells.py`: kohorta z korzeniem opublikowanym przez `GridCohortArtifactStore.publish_json`, a CLI daje 30 PNG. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_comparison_production_cells.py`.
- `services/api/tests/integration/test_grid_content_targets_postgres.py`: asercja niepustego, bezpiecznego `displayName` dla realnie zaimportowanego źródła, z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`.
- `apps/admin/test-interactions/grid-content-reference.test.mjs`: użycie `f.hold` dla starej sesji/celu oraz error/empty/retry. Uruchomienie: `node --test` przez istniejący tsx.
- `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs`: nieudany odczyt budżetu.
- `test_comparison_production_cells.py`: dopasowana predykcja poza kadrem przy poprawnej drugiej planszy.

## Zakres przeglądu i ograniczenia

Przegląd wyłącznie statyczny (Read/Glob/Grep). Audytor nie uruchamiał testów, usług, DB, treningu ani inferencji; wyniki wykonawców traktowano jako deklaracje. Sum SHA pakietu nie dało się przeliczyć tymi narzędziami.

Przeczytano w całości: indeks R1, szablon, D-593 (`DECISION_LOG_2026.md:18-105`), plan T5, task, raport weryfikacji, dokument odbioru, wszystkie nowe moduły UI/API/worker, ich testy, CLI i szablon HTML. Zmienione zakresy starszych plików odczytano według indeksu. Z delty mechanicznej przeczytano `MECHANICAL.diff:117-266,525-599`, czyli OpenAPI i SDK; delty `types.gen.ts` i `generated/index.ts` nie sprawdzano linia po linii, a wrapper i test żądań przeczytano bezpośrednio. Pełnego `SOURCE_DELTA.diff` ani `API_CONTRACT.md` nie czytano.

Dla potwierdzenia wyzwalaczy P0-1 i P1-1 sięgnięto wąsko po kod spoza F, bieżący w worktree i bez pinów SHA: `grid_training_cohort_commands.py`, `grid_correction_split.py`, `grid_reinference.py`, `schemas/grid_model_evaluations.py`, `application/grid_model_evaluation.py` oraz `test_grid_cohort_dataset.py`. Nie czytano zdjęć, wag, sekretów ani bazy.

Rezyduum kosztu inspektora T4P2-1/T3P2-1 pozostaje jawnie zaakceptowane i nie jest tu ponownie zgłaszane. Brak etykiet operatora, realnego treningu i wdrożenia jest granicą zakresu.