# Audyt TASK-1009 — Losowa kontrola Mumii i 777a2

Werdykt: REVISE
Audytor: claude-fable-5-1, reasoning high
Wykonawca: gpt-6.1-sol, reasoning high
Zakres: ea9a27b29be948c9328da2670dc2b4159675ac4e...ea9a27b29be948c9328da2670dc2b4159675ac4e oraz zmiany niezacommitowane (58 plików śledzonych i 31 nowych z brief), data 2026-10-16
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano pełny pion pomiaru: domenę próbkowania i raportu, schematy Pydantic, router, repozytoria capture/assess/approve, obserwacje i lineage, verifier repointu, migrację 0162 z manifestem v15, seam nagrań v2 (SQL i uprawnienia), retencję/cleanup, panel Admin z testami interakcji, allowlistę Reviewera, wrapper klienta oraz dokumentację i evidence wykonawcy. Implementacja jest zgodna z kontraktem D-555: random/hard mają osobne mianowniki, brak producenta daje coverage gap zamiast pozornego sukcesu, approval-only zapisuje prawdziwą projekcję, event i receipt w jednej transakcji bez recropu, a usunięcie źródła zachowuje dowody. Jedyne znalezisko blokujące to uszkodzone kodowanie pliku taska (podwójnie zakodowany UTF-8 w całym dokumencie), przez co wymagany artefakt procesu jest nieczytelny, a lista kryteriów nie odpowiada stanowi implementacji. Główne ryzyko techniczne (P2) to wyścig dwóch równoległych capture pod tym samym kluczem w REPEATABLE READ, który kończy się naruszeniem klucza głównego zamiast replayu.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `ai_docs/tasks/1009-grid-quality-measurement.md:2` (także linie 7, 15, 19, 23–25 i cała sekcja Technical notes oraz Outcome; 141 wystąpień sekwencji mojibake, żaden inny plik w `ai_docs/` ich nie zawiera) — plik taska zapisano z podwójnie zakodowanymi znakami polskimi („TASK-1009 Ă˘â‚¬â€ť”, „ZmierzyĂ„â€ˇ rodzaje bÄąâ€šĂ„â„˘dÄ‚Ĺ‚w”, w Outcome inny wariant „zamroĹĽona”). Skutek: wymagany artefakt procesu (kontrakt wykonawczy, kryteria, Outcome przenoszone do `completed/`) jest nieczytelny dla człowieka i kolejnych agentów, narusza regułę AGENTS o pisaniu dokumentów w języku dokumentu, a `docs:check` tego nie wykrywa. Dodatkowo lista kryteriów w liniach 57–61 jest niespójna z implementacją: kryteria „Trudne przykłady nie zmieniają częstości” i „Brak pełnej kontroli zdjęcia jest widoczny” są zaimplementowane i przetestowane (patrz tabela niżej), a pozostają odhaczone jako niespełnione, podczas gdy kryteria 1 i 4 są odhaczone. Poprawka: odtworzyć plik w poprawnym UTF-8 (niezmienione fragmenty z wersji HEAD, nowe sekcje przepisać z poprawnymi znakami), potwierdzić `git diff` że różni się tylko treść zamierzona, uzgodnić checkboxy ze stanem faktycznym i dopiero wtedy uzupełnić wynik audytu w Outcome.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/grid_quality_measurements.py:171-184` oraz `:318-327` — w nowym połączeniu REPEATABLE READ snapshot powstaje przy pierwszym SELECT (kontrola roli w linii 171–176, bind i `set_config` w 181–182), a blokada klucza idempotencji jest brana dopiero w linii 183. Drugi równoległy capture z tym samym kluczem czeka na advisory lock, po czym w swoim starszym snapshocie nie widzi receiptu pierwszego, losuje ponownie i przy INSERT do `grid_quality_measurement_commands` dostaje naruszenie PK (IntegrityError, nie 57014), czyli 500 zamiast replayu; plik manifestu drugiej próby pozostaje osierocony. UI ma mutationLock i sekwencyjny retry, więc skutek dotyczy tylko równoległych klientów. Poprawka: wziąć `key_lock` na sesji żądania (READ COMMITTED) przed otwarciem połączenia snapshotu albo mapować naruszenie unikalności na tej tabeli na `GRID_QUALITY_IDEMPOTENCY_CONFLICT`/replay.
- [P2-2] `apps/admin/src/features/model-quality/grid-quality-measurement-state.ts:69-88` i `grid-quality-measurement-member.tsx:454-461` — link „Otwórz korektę w Reviewerze dla tego importu” buduje URL `http://127.0.0.1:3001/?mode=local&gameId=…&importJobId=…`, ale aplikacja Reviewer nie odczytuje żadnego z tych parametrów (brak `useSearchParams`/parsowania `window.location.search` poza proxy). Link otwiera jedynie stronę główną; parametry są bezczynne, a opis obiecuje przejście „dla tego importu”. Poprawka: zostawić sam origin:3001 z opisem ręcznego wyboru albo dodać obsługę parametrów po stronie Reviewera w osobnym tasku; odnotować jako ryzyko UX.
- [P2-3] `services/api/src/game_predictor_api/security/local_admin.py:260-264` — komentarz nad listą wzorców nadal brzmi „there is no geometry approval and no whole-source save (TASK-0727)”, a bezpośrednio pod nim dodano wzorzec `geometry-approvals`. Komentarz jest teraz fałszywy względem D-555. Poprawka: zaktualizować komentarz (D-555: jawne approval-only exact frozen current, nadal bez whole-source save).
- [P2-4] `ai_docs/requirements/APP_V3_FUNCTIONAL_INVENTORY.md:63-64` — wiersz MODEL-11 wstawiono po pustej linii kończącej tabelę MODEL-01…MODEL-10, więc w renderowaniu Markdown nie jest wierszem tabeli, lecz osobnym akapitem z pionowymi kreskami. Poprawka: usunąć pustą linię 63, aby wiersz należał do tabeli.
- [P2-5] `services/api/src/game_predictor_api/storage/grid_quality_measurements.py:524-534` i `apps/admin/src/features/model-quality/grid-quality-measurement-panel.tsx:389` — lista pomiarów stronicuje po `Measurement.id DESC`, a identyfikatory są losowe (uuid4), więc kolejność i przycisk „Starsze pomiary” nie są chronologiczne. Keyset jest stabilny, więc to tylko mylący opis. Poprawka: zmienić etykietę na neutralną („Kolejne pomiary”) albo stronicować po `(captured_at, id)`; akceptowalne jako ryzyko.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Ten sam seed i populacja odtwarzają próbę | spełnione (statycznie) | `services/api/src/game_predictor_api/domain/grid_quality_measurements.py:21-53` (SHA(policy, seed, sourceId), pełny digest, kopiec 100); `services/api/tests/test_grid_quality_measurements.py:24-30`; replay z nowego procesu `services/api/tests/integration/test_grid_quality_measurements_postgres.py:223-234`; wykonawca raportuje PASS w `artifacts/audits/TASK-1009_IMPLEMENTATION_EVIDENCE.json:316-334` |
| Trudne przykłady nie zmieniają częstości z próby losowej | spełnione (statycznie) | `domain/grid_quality_measurements.py:68-72` (osobna pętla per sampleKind, własne mianowniki); `storage/grid_quality_measurements.py:256-269` (hard nie wchodzi do samplera); `services/api/tests/test_grid_quality_measurements.py:57-63` |
| Brak pełnej kontroli zdjęcia jest widoczny | spełnione (statycznie) | `domain/grid_quality_measurements.py:90-96, 148-155` (fullyReviewedCount, completeUnknownCount, unreviewed); `apps/admin/src/features/model-quality/grid-quality-measurement-report.tsx:49-60, 101-103`; `services/api/tests/integration/test_grid_quality_measurements_postgres.py:323-324`; `apps/admin/test-interactions/grid-quality-measurement.test.mjs` (test „missing original stays visible”) |
| Raport rozdziela detekcję, geometrię, symbole i sekwencję | spełnione (statycznie) | `domain/grid_quality_measurements.py:75-80, 137-162` (axes geometry/detection/sequence, symbols z `classifierAccuracy: None`); `grid-quality-measurement-report.tsx:76-114`; `services/api/tests/test_grid_quality_measurements.py:66-85` |
| Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | niespełnione | Outcome wypełniono (`ai_docs/tasks/1009-grid-quality-measurement.md:345-392`), lecz plik jest nieczytelny (P1-1), checkboxy w liniach 57–61 nie odpowiadają stanowi, a wynik audytu nie jest jeszcze wpisany; dokumenty ADMIN_APP/API_CONTRACT/DATA_MODEL/VISION_LAB/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP opisują zachowanie zgodnie z kodem |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy, runda 1.

Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- Równoległy duplikat capture pod tym samym `idempotencyKey` (dwa wątki, jedno DB): oczekiwany jeden zapis i jeden identyczny replay albo jawne 409, nigdy IntegrityError; plik `services/api/tests/integration/test_grid_quality_measurements_postgres.py`, komenda `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_quality_measurements_postgres.py -k concurrent` (timeout 120 s).
- Upgrade 0161→0162 na bazie, w której rola runtime istnieje i ma granty na `source_images` przed migracją: po samym `alembic upgrade head`, bez reprovision, `recording_permission_errors(connection, role) == ()` oraz SELECT na pięciu nowych tabelach działa pod tą rolą (pętle `_protect` i `enforce_recording_permissions` w `services/api/alembic/versions/0162_grid_quality_measurements.py:296-306, 390-399`); obecny fixture tworzy rolę dopiero po upgrade (`test_grid_quality_measurements_postgres.py:82-90`).
- Strażnik kodowania dokumentów: test lub krok `docs:check` odrzucający sekwencje mojibake (`Ă˘`, `Äą`, `Ĺ‚`, `Ä…`) w `ai_docs/**/*.md`; komenda `npm run docs:check`.
- Semantyka nadmiarowej detekcji ocenionej jako `correct`: test jednostkowy w `services/api/tests/test_grid_quality_measurements.py` utrwalający, że takie zdjęcie liczy się jako complete-incorrect (`domain/grid_quality_measurements.py:107-112`), aby zmiana interpretacji była świadoma.

## Zakres przeglądu i ograniczenia

Przeczytano w całości brief `artifacts/audits/TASK-1009_BRIEF_claude.md` (plik taska, fragment planu, diff plików śledzonych bez pełnego przeglądu 2448 linii `openapi.json` i wygenerowanego klienta, które zweryfikowano wyrywkowo przez grep operacji `approveOperationalGeometry`, `getGridQualityMeasurementSource` i parametru `sourceId`) oraz wszystkie 31 nowych plików: domena, schematy, router, aplikacja, repozytoria measurements/approvals/observations/repoint/manifest, modele, manifest v15, migracja 0162, SQL i uprawnienia v2, testy jednostkowe, request, lineage, repoint, membership v2, integracyjny PostgreSQL, panel/member/report/state/command Admin z testami jednostkowymi i interakcji oraz test wrappera klienta. W repozytorium sprawdzono zależności nowego kodu: `_resolve` zasobów, `_IMAGE_STATES_CTE` i jego placeholder, `source_fence`, `source_targets` (kategoria `all_automatic` obejmuje także plansze poprawione ręcznie), kolejność blokad w `virtual_grid_geometry_repository.py:600-608`, model `ImageBoardGeometryReviewEventModel`, `recompute_source_image_geometry_completeness`, routing `GameStorageSession`, `authorize_scope`, `_REVIEWER_MUTATION_PATTERNS`, `partition_name` i topologiczne usuwanie partycji (DROP TABLE omija trigger niezmienności), pola `declared`/`membershipComplete` w `recording_group_view_v1`, proxy Reviewera oraz nagłówek i sekcję weryfikacji `TASK-1009_IMPLEMENTATION_EVIDENCE.json`. Nie uruchamiano żadnych testów, lintów, migracji ani usług; liczby PASS pochodzą wyłącznie z deklaracji wykonawcy i receiptów w `artifacts/audits/`. Nie sprawdzono renderowania panelu w przeglądarce, pełnej treści CODE_MAP/CODE_MAP_SYMBOLS (poza zakresem brief), `CURRENT_STATE.md` i `decisions/DECISION_LOG_2026.md` (własność leada), ani zachowania `SET TRANSACTION READ WRITE` po `SET LOCAL statement_timeout` wykonanym w zdarzeniu `before_cursor_execute`, które zweryfikowano tylko rozumowaniem o regułach PostgreSQL i deklarowanym wynikiem testów PG.
