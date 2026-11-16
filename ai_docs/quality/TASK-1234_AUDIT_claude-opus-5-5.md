# Audyt TASK-1234 — Large grid cohort metadata compatibility

Werdykt: PASS
Audytor: claude-opus-5-5, reasoning standard
Wykonawca: Codex (inna rodzina modeli), reasoning nieznany
Zakres: HEAD...ace8de10b70e415adc3078c070a548c05bedc8c4 oraz zmiany niezacommitowane, data 2026-11-16
Runda: 1
SHA pakietu: 4a264a795c8661567e329907f083ba3ad3e3c39d31e3a6e015943f2e50919537
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem wspólny limit `METADATA_BYTE_LIMIT` (64 MiB) w trzech miejscach: w publikacji JSON, w czytniku API `read_json` i w czytniku migawki treningowej. Sprawdziłem też, czy API liczy SHA-256 dokładnie z tych bajtów, które potem dekoduje, oraz trzy nowe testy regresyjne. Zmiana jest mała i spójna. Ścieżka zamrożenia (`grid_training_cohort_freeze.py:137-139`) i trening czytają teraz manifest 21 181 768 B. Za duży JSON zostaje odrzucony przed powstaniem pliku niezmiennego. Hashe i kanoniczne bajty się nie zmieniły. Główne ryzyko leży poza wąskim zakresem taska: kopiowanie paczki porównawczej nadal ma twardy limit 16 MiB. Oprócz tego kryterium „stale human/source evidence” pozostało niezweryfikowane end-to-end.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/images/comparison_production_bundle.py:69` — Ten kod czyta ten sam manifest kohorty co `GridCohortSnapshot` (linia 64), ale kopiuje go do paczki porównawczej z limitem `16 * 1024 * 1024`. Ten sam limit dotyczy stron (linia 74). Skutek: dla kohorty TASK-1230 migawka przejdzie, a `_copy` zgłosi `CONTENT_COMPARISON_BUNDLE_CHECKSUM_OR_SIZE`. Paczka porównania produkcyjnego tej kohorty będzie wtedy niemożliwa, a źródła dostaną mylący kod błędu. Nie blokuje to zamrożenia, treningu ani wznowienia rodzica, więc nie narusza zakresu „publisher and both readers”. Narusza jednak zasadę z dokumentu architektury, że publikacja i odczyty mają ten sam limit. Propozycja: w liniach 69 i 74 użyć `METADATA_BYTE_LIMIT` z `game_predictor_api.domain.grid_training_cohorts` (indeks JSONL ma osobną granicę liniową) i dodać test granicy. Alternatywnie zapisać to jako znane ograniczenie w sekcji Risks taska.
- [P2-2] `ai_docs/tasks/1234-grid-cohort-large-metadata.md` (kryterium „Corruption, unsafe paths, stale human/source evidence still fail closed”) — Uszkodzenie i niebezpieczne ścieżki są pokryte testami jednostkowymi: `services/api/tests/test_grid_training_cohort_core.py:514-516`, `:574-576` oraz `test_artifact_namespace_rejects_escaping_paths`. Część „stale input” testu PostgreSQL E2E przerwał natomiast miękki deadline. Diff nie dotyka logiki aktualności (zmienia się tylko odczyt bajtów przed transakcją w `grid_training_cohort_freeze.py:137-139`), więc ryzyko regresji statycznie oceniam jako niskie. Mimo to kryterium jest otwarte. Propozycja: przed zamknięciem taska, za zgodą operatora, uruchomić sam przypadek stale-input w izolacji. Druga możliwość to jawne przyjęcie ryzyka w Outcome z uzasadnieniem, że kod aktualności jest bajtowo identyczny z HEAD.
- [P2-3] `services/api/src/game_predictor_api/storage/grid_training_cohort_artifacts.py:89-97` — `read_json` trzyma do 64 MiB surowych bajtów i od razu je dekoduje. Pełny obiekt Pythona z `photoSplit` może zająć kilkukrotnie więcej pamięci w procesie API podczas zamrożenia. Task świadomie opisuje to jako budżet pamięci. Propozycja: przyjąć ryzyko i zostawić zapis w Risks. Poprawka kodu nie jest wymagana.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Manifesty powyżej 16 MiB czytane przez API i trening | spełnione (statycznie; dowód na żywym pliku tylko zadeklarowany przez wykonawcę) | `services/api/src/game_predictor_api/domain/grid_training_cohorts.py:25`, `storage/grid_training_cohort_artifacts.py:90-91`, `services/worker/src/game_predictor_worker/images/grid_cohort_dataset.py:40,154,301`, `services/worker/tests/test_grid_cohort_dataset.py:193-194` |
| Publikacja i czytniki zgodne na nowej granicy; za duże wejście zamyka się bezpiecznie | spełnione dla zakresu taska (wyjątek poza zakresem: P2-1) | `storage/grid_training_cohort_artifacts.py:142-147`, `services/api/tests/test_grid_training_cohort_core.py:519-545`, `services/worker/tests/test_grid_cohort_dataset.py:204-211` |
| Uszkodzenie, niebezpieczne ścieżki i nieaktualne dowody nadal zamykają się bezpiecznie | niezweryfikowane (część stale-input) | `services/api/tests/test_grid_training_cohort_core.py:514-516,574-576`; `storage/grid_training_cohort_artifacts.py:83,95-96`; E2E stale-input przerwany (P2-2) |
| Powtórka po utraconej odpowiedzi i świeży proces używają tych samych artefaktów | spełnione | `services/api/tests/test_grid_training_cohort_core.py:495-503,533-535`, `services/worker/tests/test_grid_cohort_dataset.py:199-206`; `_publish` weryfikuje istniejący cel (`storage/grid_training_cohort_artifacts.py:122-123`) |
| Wymagany niezależny przegląd Claude przed commitem | spełnione tym raportem | Ten raport, Runda 1 |
| Wznowienie tego samego rodzica zweryfikowane lub blocker zapisany | niezweryfikowane | Task, sekcja „Not completed”: wymaga wdrożenia i świeżych procesów; blocker opisany |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P2-1, P2-2, P2-3.

## Proponowane testy

- `services/worker/tests/test_comparison_production_bundle.py` (lub istniejący odpowiednik): manifest większy od 16 MiB, ale mieszczący się w `METADATA_BYTE_LIMIT`, przechodzi przez `build_production_package` (`monkeypatch` limitu zamiast dużego fixture'a). Polecenie: `.\.venv\Scripts\python.exe -m pytest services/worker/tests -k production_package`.
- Sam przypadek stale-input z testu PostgreSQL freeze-currentness uruchomiony osobno (`$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`, `-k stale`), za zgodą operatora i w limicie czasu.
- Test `read_json` dla pliku, który rośnie między `is_file` a odczytem powyżej limitu: `BytesIO` z `METADATA_BYTE_LIMIT + 1` bajtami przy zmniejszonym limicie, oczekiwany `GRID_COHORT_METADATA_TOO_LARGE`.

## Zakres przeglądu i ograniczenia

Przeczytałem pełny diff z pakietu, plik taska oraz cały `services/api/src/game_predictor_api/storage/grid_training_cohort_artifacts.py`. Przeczytałem też fragmenty `grid_cohort_dataset.py` (`_read`, `_read_json`, `_verify_index`, `sources`), `grid_training_cohort_freeze.py:120-159`, `grid_training_cohort_commands.py:450-509`, `comparison_production_bundle.py:1-110`, `grid_model_registry.py:165-204`, funkcję `canonical()` oraz istniejący test `test_immutable_publish_survives_new_store_and_lost_response`. Wyszukałem w `services/` pozostałe limity 16 MiB i wywołania `read_json`/`publish_json`, a w `AGENTS.md` sprawdziłem zasady testów i błędów zastanych. Nie uruchamiałem testów, lintu, mypy, `docs:check` ani `code-map:check`. Nie mogłem więc potwierdzić wyników wykonawcy: 79 PASS i 6 zastanych FAIL, dowodu na kopii manifestu 21 181 768 B ani częściowego E2E PostgreSQL. Nie sprawdzałem regeneracji `CODE_MAP*.md` ani `CURRENT_STATE.md`, które są poza pathspec diffu.