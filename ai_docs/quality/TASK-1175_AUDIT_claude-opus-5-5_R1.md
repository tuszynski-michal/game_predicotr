# Audyt TASK-1175 — Pełne pola symboli bez marginesu 8%

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...1181797cbad2bdd62fda9ff249ee60ce8d1123b7 oraz zmiany niezacommitowane, data 2026-11-09
Runda: 1
SHA pakietu: d0608c1cf2a80ac4d095e5888b1b809004b11b07e510b68a75525486fba386d3
Otwarte P0: 1
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano pin `full-cell-v2` w snapshotach, ścieżkę preview → symbole → zapis → przyjęcie propozycji, CAS i idempotencję, kontekst pending, transport Reviewera oraz konsumentów snapshotu. Ścieżka ręcznej korekty jest spójna: token wchodzi do hasha komendy, render i efektywny snapshot są wiązane tak samo, a historyczne piny pozostają nienaruszone. Zmiana ma jednak błąd blokujący. Publiczny schemat payloadu joba nie zna nowego pola, a rzeczywisty resolver dodaje je do każdego nowego snapshotu, więc odczyt takich jobów przez API się nie powiedzie. Tej ścieżki nie obejmuje żaden test z nową polityką.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/schemas/jobs.py:61` — `SymbolModelJobSnapshotPayload` dziedziczy po `ApiModel` z `extra="forbid"` (`schemas/catalog.py:30`) i kończy się na `crop_size` (`jobs.py:73`), bez pola `crop_policy_version`. Tymczasem `SqlAlchemySymbolModelSnapshotResolver.resolve` zawsze zwraca snapshot z polityką (`storage/symbol_model_snapshot_resolver.py:43`, także cold start w linii 204), a `to_payload()` zapisuje `cropPolicyVersion` w `symbol_model` joba (`domain/symbol_model_snapshots.py:109`, `application/jobs.py:868`, `:1171`, `:1283`, `:1507`). `_payload_from_domain` waliduje ten payload modelami z `symbol_model: SymbolModelJobSnapshotPayload` (`jobs.py:1495`–`1500`, `:1545`) i odfiltrowuje wyłącznie wybrane klucze najwyższego poziomu (`jobs.py:1482`–`1487`).

  Skutek po wdrożeniu dotyczy każdego nowego importu, reprocessu i ponownej inferencji symboli. `JobResponse.from_domain` kończy się błędem walidacji, czyli w praktyce HTTP 500, choć job został już utworzony (`api/image_imports.py:1664`, `api/image_reviews.py:567`). Pojedynczy taki job psuje też całą listę `GET /jobs` (`api/jobs.py:90`–`91`), ponieważ odpowiedź jest budowana w jednej pętli. Kontrakt OpenAPI również nie zawiera pola (`packages/admin-api-client/openapi/openapi.json:48342`), co narusza kryterium spójnego pionu API. Testy nie wykrywają problemu: `cropPolicyVersion` i `full-cell-v2` występują tylko w czterech plikach testowych, a żaden nie serializuje takiego joba przez `JobResponse`.

  Proponowana poprawka: dodać do schematu opcjonalne `crop_policy_version: Literal["full-cell-v2"] | None` z `exclude_if` dla `None`, aby historyczne odpowiedzi pozostały bez zmian. Następnie zregenerować OpenAPI i klienta oraz dodać test odczytu joba przez `POST`/`GET`/listę ze snapshotem `with_full_cell_crops()`, np. rozszerzając `services/api/tests/test_image_imports_api.py:1097`.

### P1

Brak.

### P2

- [P2-1] `services/api/src/game_predictor_api/application/jobs.py:1163` — ponowna inferencja pending dostaje z resolvera snapshot z polityką 0%, ale handler czyta istniejące rendery z ich zapisanego `renderSpec` (`services/worker/src/game_predictor_worker/images/pending_symbol_reinference.py:100`–`112`) i nie porównuje paddingu z pinem. Pin joba deklaruje więc 0%, a klasyfikowane są piksele 8%. Rewizja predykcji jest związana sumą manifestu cropów (`pending_symbol_reinference.py:244`, `:258`), dlatego dane nie są błędne, ale proweniencja joba jest myląca. Propozycja: dla tego typu joba przypinać snapshot bez nowej polityki albo jawnie opisać, że `cropPolicyVersion` nie określa tu pikseli.
- [P2-2] `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py:2804` — job bez `symbol_model` nadal przyjmuje konfigurację z pierwszego bieżącego manifestu źródła lub importu. Po ręcznym zapisie 0% w sąsiednim slocie wywołanie bez tokenu może więc odziedziczyć 0%. Dotyczy to tylko niekompletnych, historycznych pinów bez klasyfikatora i jest zgodne z zapisem w Technical notes. Propozycja: zaakceptować ryzyko w `Outcome` albo pomijać w tym odczycie manifesty z `cropPolicyVersion`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Kryteria sekcji T2 planu i regresje dotychczasowych konsumentów | niespełnione | P0-1: `services/api/src/game_predictor_api/schemas/jobs.py:61`, `:1495`–`1500`; `services/api/src/game_predictor_api/api/jobs.py:90` |
| Spójny kontrakt API/OpenAPI/SDK/wrapper/test | niespełnione | Pola korekty są spójne (`packages/admin-api-client/src/generated/types.gen.ts:628`, `packages/admin-api-client/test/client.test.mjs:2437`), ale kontrakt payloadu joba nie ma nowego pola (`packages/admin-api-client/openapi/openapi.json:48342`) |
| Testy, lint, typy, build, dokumentacja, mapa i niezależny audyt Opus z receipt | niezweryfikowane | Przegląd statyczny, bez uruchamiania komend. `ai_docs/quality/TASK-1175_VERIFICATION.md` deklaruje wyniki i brak pełnego PASS mypy; receipt nie istnieje przed zakończeniem audytu |
| Outcome, task-close, osobny commit i hash w kolejnym commicie | niezweryfikowane | `Outcome` jest uzupełniony w `ai_docs/tasks/1175-full-cell-render-policy.md`; commit i task-close należą do etapu po audycie |
| Historyczny brak pola zachowuje payload, fingerprint i 8% | spełnione | `services/api/src/game_predictor_api/domain/symbol_model_snapshots.py:80`–`85`, `:109`, `:129`; `services/api/tests/test_full_cell_crop_policy.py:30`–`47` |
| Preview, symbole i zapis używają tego samego 0%, bez surowego paddingu z klienta | spełnione | `services/api/src/game_predictor_api/application/virtual_grid_geometry.py:1102`, `:1515`, `:1686`–`1707`; `services/api/tests/test_full_cell_crop_policy.py:88`–`138` |
| Zmiana tokenu daje konflikt; CAS i idempotencja zachowane | spełnione | `services/api/src/game_predictor_api/domain/image_reviews.py:401`–`408`; `services/api/src/game_predictor_api/application/virtual_grid_geometry.py:1010`; `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py:3443`; `services/api/tests/integration/test_full_cell_correction_postgres.py:205`–`222` |
| Transport Reviewera, w tym przyjęcie modelowe i edytowane | spełnione | `apps/reviewer/src/features/operational-reviews/grid-geometry-proposals.tsx:196`, `:226`, `:322`; `apps/reviewer/src/features/operational-reviews/board-geometry-correction-target.ts:712`, `:842`; `services/api/src/game_predictor_api/storage/grid_geometry_proposals.py:423` |
| Zmiana pikseli unieważnia stary symbol, a dowód 8% nie kwalifikuje 0% | spełnione | `services/api/tests/integration/test_full_cell_correction_postgres.py:248`–`255`; `services/worker/src/game_predictor_worker/images/production_crop_classification.py:103` |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1, P2-1, P2-2.

## Proponowane testy

- Odczyt joba z nową polityką: rozszerzyć parametryzację w `services/api/tests/test_image_imports_api.py` o snapshot `with_full_cell_crops()` i sprawdzić odpowiedź `POST`, `GET` oraz listy. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_imports_api.py`.
- Serializacja ponownej inferencji: w `services/api/tests/test_jobs_api.py` przepuścić job `IMAGE_SYMBOL_REINFERENCE` z polem `cropPolicyVersion` przez `JobResponse.from_domain`. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_jobs_api.py`.
- Reviewer: w `apps/reviewer/test-interactions/board-geometry-correction.test.mjs` dodać przypadki celu operacyjnego oraz przyjęcia propozycji w trybie `edited`, sprawdzające zgodność `cropPolicyVersion` w poleceniu i w `geometry`. Komenda: `npm run test:geometry --workspace @game-predictor/reviewer`.

## Zakres przeglądu i ograniczenia

Przeczytano pakiet audytu, `AGENTS.md` oraz fragmenty zmienionych i powiązanych modułów: snapshot domenowy, schematy jobów, serwis i repozytorium geometrii wirtualnej, przyjmowanie propozycji, cele korekty Reviewera, ponowną inferencję symboli i konsumentów kontraktu renderu. Nie uruchamiano testów, lintu, mypy, builda, usług ani bazy. Wyniki z `ai_docs/quality/TASK-1175_VERIFICATION.md` są więc deklaracją wykonawcy. Nie potwierdzono statycznie zastanego charakteru błędu mypy ani obecności artefaktów logów, a skutek HTTP P0-1 wynika z analizy kodu, nie z wykonania żądania. Nie oceniano jakości klasyfikacji na danych operatora.