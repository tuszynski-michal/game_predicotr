# Audyt TASK-1013 — Trwałe propozycje dla „Złej siatki”

Werdykt: REVISE
Audytor: claude-fable-5-1, reasoning high
Wykonawca: gpt-6.1-sol, reasoning high
Zakres: 62e9f71986a74d67776eabad6e99154f4d18c0b2...62e9f71986a74d67776eabad6e99154f4d18c0b2 (brak nowych commitów) oraz zmiany niezacommitowane i pliki nieśledzone z briefu, data 2026-10-15
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano migrację 0160 i manifest v13, modele ORM, repozytorium i serwis propozycji, router i granicę bezpieczeństwa, opt-in politykę `current_live_slots` w repozytorium geometrii, pion klienta, proxy i komponent Reviewera oraz testy jednostkowe, request i PostgreSQL. Backend jest spójny z kontraktem D-551: immutable kandydat, typed 409 z utrwalonym receiptem, jedna transakcja dla `save_review_item` plus event, zaufany aktor bez fallbacku z body, brak FK do żywych tabel. Główne ryzyko to ścieżka „Edytuj propozycję → Przyjmij własną korektę” w Reviewerze: dla zwykłej planszy V3 bez zapisanej kwalifikacji UI wysyła `geometryQualification: null`, a serwer odrzuca takie polecenie walidacją 422, czego test jsdom z zaślepionym API nie wykrywa. Drugie ryzyko to brak RLS na partycjach nowych tabel dla gier tworzonych po migracji, bo lifecycle ma zamkniętą listę tabel chronionych per partycja.

## Znaleziska

### P0

- [P0-1] `apps/reviewer/src/features/operational-reviews/grid-geometry-proposals.tsx:278-295` — zapis edytowanej propozycji buduje `geometry` z `base.commandKey(...)`, czyli z `correctionGeometryQualification(persisted, flags, ...)` w `apps/reviewer/src/features/operational-reviews/board-geometry-correction-target.ts:643-653,682,710`. Dla planszy bez `item.geometryQualification` i bez flag partial/exclude funkcja zwraca `null`. Standardowy import V3 zapisuje `geometry_qualification` tylko gdy pipeline ją dostarczył (`services/worker/src/game_predictor_worker/images/pipeline_store.py:624-635`), więc typowa plansza ma `null`. Serwer w `services/api/src/game_predictor_api/schemas/grid_geometry_proposals.py:29-37` wymaga dla `mode=edited` jawnej kwalifikacji i zwraca 422. Skutek: funkcja „Edytuj propozycję” z zakresu taska nie działa dla zwykłych plansz; test `apps/reviewer/test-interactions/grid-geometry-proposals.test.mjs:181-235` tego nie wykrywa, bo API jest zaślepione i nie waliduje ciała. Poprawka: w `save` celu propozycji uzupełnić brak kwalifikacji kwalifikacją kandydata (`proposal.candidate.originalGeometry.geometryQualification`, czyli `complete` v1) albo zrezygnować z wymogu jawnej kwalifikacji po stronie serwera i rozstrzygać ją jak ręczny writer (`resolve_manual_geometry_qualification`), zachowując wymóg 24 węzłów; dodać test, który sprawdza, że polecenie zbudowane przez UI przechodzi walidację `ProposalAcceptCommand` (lub asercję `geometryQualification !== null` w teście jsdom plus test API z `geometryQualification: null`).

### P1

- [P1-1] `services/api/src/game_predictor_api/storage/game_partition_lifecycle.py:221-235` — provisioning partycji nowej gry włącza i wymusza RLS oraz tworzy politykę per partycja tylko dla zamkniętego zbioru tabel (`image_geometry_shadow_results`, trzy tabele 0999). Migracja 0160 robi to dla istniejących gier (`services/api/alembic/versions/0160_grid_geometry_proposals.py:27-46`), ale gry utworzone po migracji dostaną partycje `grid_geometry_proposals` i `grid_geometry_proposal_events` bez RLS na dziecku. Odczyt przez rodzica nadal podlega polityce rodzica, lecz ochrona jest niespójna między grami migrowanymi i nowymi, odbiega od wzorca 0999 w tym samym pliku i od deklaracji „composite FK/RLS … właściwy lifecycle” w Outcome, CURRENT_STATE i DATA_MODEL. Test `services/api/tests/integration/test_grid_geometry_proposals_postgres.py:762-851` nie sprawdza `relrowsecurity`/`pg_policy` na partycjach nowych tabel. Poprawka: dodać obie tabele do zbioru w lifecycle (lub wyprowadzić zbiór z manifestu) i rozszerzyć test dwóch gier o asercję RLS i liczby polityk na dzieciach `gpv2_*` obu tabel, analogicznie do `services/api/tests/integration/test_grid_shadow_rls_postgres.py:294-304`.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/grid_geometry_proposals.py:216,552-564` — `list_proposals` wywołuje `_candidate(target)`, który dla niekompletnego wyniku rzuca `ImageReviewNotFoundError`; jeden wadliwy target 0999 zamienia cały GET kolekcji w 404 i ukrywa pozostałe propozycje i kandydatów. Propozycja: pomijać takiego kandydata lub zwracać go z `applicable=false` i powodem `RESULT_INVALID`; create nadal może odrzucać go jawnie.
- [P2-2] `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py:1576-1611` — merge bieżących slotów bierze każdą `recognized_boards` źródła z review w stanie pending/accepted/corrected bez filtra `status <> 'rejected'`, którego używa `source_targets` (`services/api/src/game_predictor_api/storage/grid_reinference.py:460`). Odrzucona plansza na tej samej pozycji dałaby fałszywy `IMAGE_GRID_REVIEW_REVISION_CONFLICT`, a więc trwałe `stale` propozycji. Propozycja: dodać ten sam filtr statusu planszy albo odnotować ryzyko, jeśli taki układ wierszy jest niemożliwy.
- [P2-3] `apps/reviewer/src/features/operational-reviews/operational-review-workspace.tsx:1132-1138` — komponent propozycji jest montowany dla każdej planszy w każdym widoku, więc każde wejście na planszę wykonuje GET kolekcji i po jednym `source_targets` na kandydata, także poza `needs_grid_fix`. Wymaganie ADMIN_APP mówi o widoku zgłoszenia złej siatki. Propozycja: montować sekcję tylko w `needs_grid_fix` lub gdy pozycja ma otwarte zgłoszenie; można też zaakceptować koszt jako ograniczony do 100 kandydatów.
- [P2-4] `services/api/tests/integration/test_grid_geometry_proposals_postgres.py:93-98,138-140` — fixture testu zapisuje receipty do `artifacts/audits/` względem bieżącego katalogu i importuje prywatne helpery z innych modułów testowych (`execution`, `_provision_game`, `_factory`, `cleanup_fixture`) z `patch` na ich symbolach. Sprzężenie utrudnia utrzymanie i uzależnia ten test od nazw w cudzych plikach. Propozycja: przenieść wspólne helpery do modułu wsparcia (jak `grid_reinference_schema_support.py`) i pisać receipt do `tmp_path`; można odnotować jako dług.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Utworzenie nie zmienia cropów ani zgłoszenia | spełnione | `services/api/src/game_predictor_api/storage/grid_geometry_proposals.py:282-342` tylko wstawia proposal i event; `services/api/tests/integration/test_grid_geometry_proposals_postgres.py:400-416` sprawdza niezmienioną rewizję i otwarte `grid_issue` po create+reject/stale |
| Przyjęcie działa raz, zapisuje autora i zamyka właściwy problem | niespełnione dla ścieżki edycji w Reviewerze, spełnione dla trybu `model` | tryb model: `grid_geometry_proposals.py:349-352,388-447`, test `:392-399,412-414` (`geometry_approved_by == "local-owner"`, `issue is None`, drugi UUID 409); tryb edited przez UI blokuje P0-1 |
| Zmieniona rewizja daje konflikt | spełnione | `grid_geometry_proposals.py:349-350` (REVISION_CONFLICT bez stale), `:361-364` i `:409-424` (rzeczywisty drift → stale); test `:386-391,332-346,689-704` |
| Odrzucenie pozostawia zgłoszenie otwarte | spełnione | `grid_geometry_proposals.py:353-360` nie wywołuje writera; test `:327-331,416` |
| Wyniki kontroli, audytu i ograniczenia w Outcome; dokumentacja odpowiada zachowaniu | niespełnione | Outcome i `ai_docs/architecture/DATA_MODEL.md:9-12` deklarują pełny lifecycle RLS (P1-1); `ai_docs/requirements/ADMIN_APP.md:1655-1662` opisuje działającą edycję propozycji (P0-1); wyniki audytu jeszcze nie wpisane |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy, runda 1.

Otwarte: P0-1, P1-1, P2-1, P2-2, P2-3, P2-4.

## Proponowane testy

- `services/api/tests/test_grid_geometry_proposals.py`: walidacja `ProposalAcceptCommand` dla ciała identycznego z tym, które buduje Reviewer dla planszy bez kwalifikacji (`geometryQualification: null`, 24 węzły) — po poprawce P0-1 ma przejść albo UI ma takie ciało nie wysyłać; polecenie: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_geometry_proposals.py`.
- `apps/reviewer/test-interactions/grid-geometry-proposals.test.mjs`: asercja, że `calls[0][3].geometry.geometryQualification` nie jest `null` dla `item` bez `geometryQualification`; polecenie: `npm run test:geometry --workspace @game-predictor/reviewer`.
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_two_game_rls_composite_reference_and_whole_game_lifecycle`: po provisioningu drugiej gry sprawdzić `relrowsecurity AND relforcerowsecurity` oraz `count(pg_policy) = 1` na partycjach `gpv2_*` obu nowych tabel; polecenie z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'` na izolowanej bazie.
- Scenariusz PG dla `list_proposals` z jednym wadliwym wynikiem `proposal_ready` (np. 23 węzły): kolekcja nie zwraca 404 (P2-1).

## Zakres przeglądu i ograniczenia

Przeczytano w całości: brief z diffem plików śledzonych, nowe pliki `application/grid_geometry_proposals.py`, `schemas/grid_geometry_proposals.py`, `storage/grid_geometry_proposal_models.py`, `storage/grid_geometry_proposals.py`, `storage/game_data_v2_manifest_v13.py`, migrację 0160, testy `test_grid_geometry_proposals.py`, `test_grid_geometry_proposal_requests.py`, `integration/test_grid_geometry_proposals_postgres.py`, komponent `grid-geometry-proposals.tsx`, testy jsdom i klienta oraz fragmenty istniejącego kodu, od którego zależy pion: `authorize` i middleware lokalnego Admina, `GameStorageRouter.bind`, `source_targets`/`target_fence`/`source_fence`, `save_review_item`, `_context_from_row`, lifecycle partycji, proxy Reviewera, `correctionGeometryQualification`, `pipeline_store`. Nie uruchamiano żadnych testów, lintów ani usług; wyniki PASS z Outcome przyjęto jako deklaracje wykonawcy, nie zweryfikowano ich wykonaniem. Nie weryfikowano zawartości wygenerowanego OpenAPI i klienta poza wrapperem, zgodnie z informacją leada o przypięciu hashem. Nie oceniano zakończonej implementacji TASK-0999 poza miejscami, z których 1013 korzysta. Ocena P0-1 opiera się na statycznej analizie ścieżki UI → schemat Pydantic; nie potwierdzono jej w przeglądarce.
