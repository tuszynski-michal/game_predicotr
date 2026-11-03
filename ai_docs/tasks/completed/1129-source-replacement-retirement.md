---
title: Wycofanie źródła z zachowaniem historii
status: done
last_updated: 2026-11-03
---

# TASK-1129 — Wycofanie źródła z zachowaniem historii

## Status

`done`

## Goal

Po potwierdzeniu świeżego podglądu wycofać atomowo całe zdjęcie do trwałej, zarezerwowanej luki bez usunięcia historii oraz wyeksportować dokładny request do C1.

## Dependencies / entry conditions

B2a done a41f8d8d, record-hash 14e20787; czysty worktree, schema0175/manifestv21. Cały plan, koszt i Opus5.5 zatwierdzone. Main pozostaje przypięty40581449. Bez usług i danych operatora.

## Recommended execution

gpt-6-astra / high, audyt claude-opus-5-5 / high. Sprzeczność lub otwarty P0/P1 po jednej rundzie poprawek blokuje zamknięcie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/1128-source-replacement-ownership.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-580--wycofanie-całego-źródła-i-autoryzacja-otwartej-luki`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-579--manifest-wymiany-źródła-z-zachowaniem-historii`

## Scope

Fresh retirement-preview, per-photo command/receipt, reservations i wszystkie alias markers, zachowanie pełnego prior pending, invalidation current projections/supergame oraz mobile publication fence. Cancel tylko planned. Typed request-v1 selected gap_open, API/OpenAPI/generated/wrapper/fixture i UI potwierdzenia, postępu oraz wznowienia.

## Out of scope

Admission/import/restored C2, restore/expiry, operator retirement, pliki/model activation/trening, migracje operatora, usługi, merge/push.

## Acceptance criteria

- [x] Niezmienny planned snapshot; drift odmawia bez rebase i mutacji.
- [x] Jedna transakcja zdjęcia/aliasów, exact replay przed CAS, wszystkie slots i markery.
- [x] Obcy pending blokuje; własne review/deferred superseded z pełnym prior i bez fikcyjnego successor.
- [x] Current search/payout/supergame nie używają wycofanego zdjęcia; historia pozostaje.
- [x] Mobile blokowany na początku i pod fence przed publikacją/markready.
- [x] Cancel tylko planned; request-v1 tylko selected gap_open; postęp innego entry nie psuje poprawnego scope.
- [x] Jeden typed JSON export i rzeczywisty fixture C1; UI reload/lost response.
- [x] Testy, lint/type, dokumenty/mapa, audyt i task-close; hash zapisuje następujący commit.

## Technical notes

EXCLUSIVE game → seq rosnąco → sources rosnąco → item/board. Fresh preview przypina action/game/batch/entry/revision i exact facts; execute ponawia ten sam preflight. Drift wymaga nowego planned przez B1. Planned dokument nigdy nie jest nadpisywany; GET nakłada bieżącą fazę/revision na zachowany snapshot. Entry jest autorytetem postępu; batch jest podsumowaniem.

Review pending otrzymuje nowy resolved_value source_replacement_retired z pełnym poprzednim stanem i append-only resolution event bez canonical. Deferred pending otrzymuje status=superseded i superseded_at; pełny prior row w immutable source_replacement_retired.document każdego aliasu z command/actor/time/checksum. Stare successor/rejection events pozostają bez zmian. Błąd cofa całą transakcję i nie zmienia fazy.

Request-v1 zawiera schemaVersion, gameId/batchId, exact entryId/revision/digest i allowedRanges. Autorytetem jest ponowny GET z aktualnie skonfigurowanego uwierzytelnionego API przed zapisem/staging/import. Origin z pliku najwyżej informacyjny; nigdy automatyczne połączenie ani credentials do adresu z pliku. Bez UUID instalacji. Digest/revision entry nie zależy od zmiennej rewizji batcha. C2 zawsze waliduje backend ponownie.

## Expected files

Istniejące: storage/source_replacement.py, domain/source_replacement.py, schemas/source_replacement.py, api/cleanup.py, application/cleanup.py; worker releases/{handler,store,contracts}.py; mobile_release_repository.py; Admin source-replacement-panel.tsx i wrapper klienta. Nowe proponowane: storage/source_replacement_retirement.py, domain/source_replacement_retirement.py oraz testy pionu. Dokumenty właścicielskie, plan, mapa i generated kontrakt.

## Test cases

Atomic rollback; replay po nowej sesji/lost response; drift aliasów/pikseli/ocen/canonical/dependencies; foreign pending pod canonical; pełny prior review/deferred bez successor/rejection; alias markers/SHA; search incremental/rebuild; gaps/supergame; publication race; inne gry/historia; cancel planned-only; export selectedgapopen/partial batch i fixture konsumenta; UI reload/retry.

## Verification

Cwd worktree. Root Python D:/game_predicotr/.venv/Scripts/python.exe. Celowane pytest/lint/typecheck timeout120s; izolowane PG z name/OID/receipt guards i krótkim basetemp D:/game_predicotr/artifacts/t1129-*. HTTP/PG require_escalated. Audyt480s/external600, Opus5.5/high ReadGlobGrep/MCPoff. Code map i cztery checkery docs root Python. Wyniki wykonanych kontroli znajdują się w Outcome.

## Risks / open questions

Brak pytania blokującego. Poprzednie kolizje wersji pozostają; następny commit527 po bieżącym526. Nie wdrażamy na operatorze. C2 odpowiada za SHA admission preflight, brak duplikatów provisional i zamknięcie orphan przed restored.

## Outcome

Commit: v1.7.527 (hash dopisuje kolejny commit).

Zaimplementowano transakcję całego zdjęcia z niezmiennym planned snapshotem, świeżym preview, replay przed CAS, rezerwacją wszystkich seq i markerem każdego aliasu. Własne review/deferred pending zachowują pełny prior; obce pending blokują. Błąd cofa całą transakcję. Usuwane są tylko current canonical/staging/search refs; historyczne rekordy i pliki pozostają. GET pokazuje rzeczywiste markery jako przyczynę wycofania w UI.

D-580 jawnie dopuszcza wyłącznie dowiedziony wewnętrzny derive tego samego batcha: immutable receipt wiąże job/game/type/input key/payload digest. Nie zmienia to authoritative source snapshotu. Test dwóch wpisów dowodzi kontynuacji bez replanowania oraz odmowy dla obcego derive i zmiany payloadu. Search jest unieważniany, supergame generacja odświeżana istniejącym jobem, a bieżące odczyty supergame wykluczają wycofane accepted. Mobile sprawdza rezerwacje na początku oraz pod SHARED fence przed publikacją i markready; wydane wcześniej snapshoty pozostają.

Publiczny SourceReplacementRequestExport, OpenAPI/generated klient/wrapper i rzeczywisty fixture odpowiedzi mają jedno camelCase JSON. Export obejmuje selected gap_open i niezależne entry revision/scopeDigest; test potwierdza stabilność pierwszego wpisu po postępie drugiego. Aktualne uwierzytelnione API jest autorytetem, plik ani origin nim nie są. UI wymaga potwierdzenia, utrwala dokładne polecenie i ponawia je po utracie odpowiedzi/reload. Nie dodano migracji: schema0175/manifestv21 wystarczają.

### Verification results

- Izolowany PostgreSQL: `pytest services/api/tests/integration/test_source_retirement_postgres.py -x -q --tb=short --basetemp=D:/game_predicotr/artifacts/t1129-pgf` — **2 passed in 20.56s**. Baza testowa ma guards name/OID/receipt. Pokrycie: rollback, replay z nowej sesji, cancel/replay, alias markers, zachowany plan, pixel/revision drift, own/foreign deferred pending, pełny prior bez fikcyjnego successor/rejection, dwa wpisy/derive proof, current supergame/search i mobile publication lock. Nie jest to test pełnego C2 ani uruchomienie na bazie operatora.
- Końcowy zestaw: `pytest services/api/tests/test_source_retirement.py services/api/tests/test_source_replacement.py services/api/tests/test_cleanup_api.py services/api/tests/test_super_game_input_version.py services/api/tests/test_super_game_series_domain.py services/api/tests/test_board_search_approximate_win_domain.py services/worker/tests/test_release_workflow.py -k "not test_controlled_android_builder_restores_assets_and_publishes_immutable_apk" -q --tb=short --basetemp=D:/game_predicotr/artifacts/t1129-uf` — **93 passed, 1 deselected in 25.82s**. Wyłączenie dotyczy wyłącznie parametru tego przebiegu; test nie ma nowego skip ani osłabionej asercji. Dwa testy race blokują publikację oraz markready po otwarciu rezerwacji.
- Ruff format/check zmienionych 18 plików Python PASS; mypy scoped 8 plików PASS (`.tooling/task1129-mypy.ini`, follow_imports ograniczone do pionu). Admin scoped TypeScript i ESLint zmienionych komponentów PASS; build klienta TypeScript PASS. Testy UI/wrapper: **6 passed, 0 failed, 0 skipped** (reload/lost response, corrupt persisted command, stary planned workflow i typed request-v1).
- Mapa kodu, cztery checkery docs, aktualność OpenAPI/generated: PASS. Pełnego builda Next/Android oraz szerokiej regresji całego repo nie uruchamiano w B2b.

### Nierozstrzygnięta zależność kolejności/środowiska — APK

Dokładna wcześniejsza grupa (cwd worktree, root Python):

```powershell
& D:/game_predicotr/.venv/Scripts/python.exe -m pytest services/api/tests/test_source_retirement.py services/api/tests/test_source_replacement.py services/api/tests/test_cleanup_api.py services/api/tests/test_super_game_input_version.py services/worker/tests/test_release_workflow.py -q --tb=short --basetemp=D:/game_predicotr/artifacts/t1129-u1
```

Wynik: **46 passed, 1 failed in 25.40s**. Test `test_controlled_android_builder_restores_assets_and_publishes_immutable_apk` przy drugim buildzie po uszkodzeniu opublikowanego APK zgłosił `Failed: DID NOT RAISE <class 'game_predictor_worker.releases.android.AndroidReleaseError'>`. Log: `D:/game_predicotr/artifacts/t1129-unit1.log`.

Ten sam test osobno na aktualnym kodzie: `pytest services/worker/tests/test_release_workflow.py -k test_controlled_android_builder_restores_assets_and_publishes_immutable_apk -q --tb=short --basetemp=D:/game_predicotr/artifacts/t1129-apk-current` — **1 passed in 1.39s**. Kopia tego testu z HEAD w `D:/game_predicotr/artifacts/t1129-baseline-release.py`, osobno z `-k test_controlled_android_builder_restores_assets_and_publishes_immutable_apk -q --tb=short --basetemp=D:/game_predicotr/artifacts/t1129-base1` — **1 passed in 1.60s**. To nie dowodzi wcześniejszego błędu: różni się zakres izolowanego uruchomienia. Porażka grupy pozostaje niewyjaśnioną zależnością kolejności/środowiska. D1 może powtórzyć dokładną grupę w szerszej regresji. Kod pakowania i asercja collision pozostają bez zmian.

### Zakres, audyt i przekazanie

Nie wykonywano migracji, retirement, importu, backfillu, cleanupu, aktywacji modelu ani uruchomienia/restartu usług na danych operatora. Nie zmieniano main ani junction, nie wykonywano push. Admission, staged SHA preflight, provisional binding i closure orphan przed restored pozostają obowiązkami C2. Mutable admission nie może zmienić immutable planned scopeDigest; przyszły C2 ma czytać snapshot z batch.document albo oddzielić admission od planned dokumentu.

Audyt Opus5.5/high R1: **PASS**, brak P0/P1. Raport: `ai_docs/quality/TASK-1129_AUDIT_claude-opus-5-5.md`. Rzeczywiste modelUsage potwierdza claude-opus-5-5, koszt 1,2720716 USD. Audytor wykonał 26 wywołań zamiast limitu24; odstępstwo jawnie zapisano w raporcie, bez kolejnego audytu. Kryteria funkcjonalne spełnione w zakresie B2b; zamknięcie skryptem i zapis hasha kończą checklistę. Kolejność wersji527/528 wynika z HEAD526 tej gałęzi; istniejące kolizje historycznych numerów pozostają zgodnie wcześniejszą decyzją koordynatora.


### Rozstrzygnięcie uwag audytu i DoD

- P2-1 zamknięte przez odczyt istniejącej migracji0175: funkcja `source_replacement_excluded_reviews_v1` kończy INNER JOIN do `image_review_items` i zwraca jego `i.id` (PK NOT NULL, linie55–70). Nullable new_source_id w pośrednim CTE nie może stać się NULL w wyniku. Nie zmieniono audytowanego schematu.
- P2-2: kolejność review/board pozostaje pod EXCLUSIVE game zgodnie zatwierdzonym kontraktem B2b. Potencjalny uczestnik łamiący protokół może spowodować deadlock/rollback; to jawne ryzyko dostępności, nie zgoda na zapis bez ownership locka.
- P2-3: SHARED fence podczas fizycznego publish jest wymagany dla wyeliminowania race; może czasowo opóźnić zapisy. Hipotetyczne ustawienie idle_in_transaction_session_timeout wymaga uwzględnienia w konfiguracji publikacji; nie potwierdzono takiego timeoutu w środowisku operatora i nie zmieniano jego ustawień.
- P2-4/C2: restored ma usunąć aktywne slots albo jawnie dostosować warunek mobile; marker retired nadal zostaje. C2 musi także sprawdzić autoryzację dataset_version sprzed retirement po zamknięciu luki, aby nie dopuścić starego dowodu do nowego wydania.
- P2-5: resolutionUrls są pomocniczymi odnośnikami do canonical/pending i mogą obejmować własny wpis; deferred ma pełne pendingGeometry. Bez rozszerzania na nowy workflow rozwiązywania geometrii w B2b.
- Queue counters utrzymuje istniejący trigger migracji0106 przy UPDATE status. Liczniki symbol-cell celowo przechodzą w unavailable; bounded rebuild to istniejący workflow, nie zadeklarowano automatycznego uruchomienia. Do czasu odbudowy nie wolno prezentować ich jako aktualnych.
- DoD: funkcjonalność i granice taska pokryte; logika pure oddzielona od ORM/HTTP/UI, schemat bez zmian; backend/OpenAPI/generated/wrapper/request-test spójne. Stan trwały sprawdzony nową sesją PG i reload UI. Touch targets44px, jawne loading/error/confirm, blokada podwójnego submitu. Fizycznego Android UI nie testowano. Dokumenty właścicielskie, D580, plan i mapa aktualne. Nie wykonano wdrożenia ani działań na danych operatora.
