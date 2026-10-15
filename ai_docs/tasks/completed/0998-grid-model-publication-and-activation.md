---
title: TASK-0998 — Publikacja, aktywacja, domyślna wersja i rollback
status: done
last_updated: 2026-10-15
---

# TASK-0998 — Publikacja, aktywacja, domyślna wersja i rollback

## Status

`done`

## Goal

Jawnie kontrolować wersję używaną przez grę i nowe zadania.

## Context

Task jest częścią zaakceptowanej rewizji 6. Aktywacje, CAS i historia wersji. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1012 done, v1.7.375 / `acf9ce4079b3ed176b1d40babb77f4e5a3ac9988`; Claude high R2 PASS, jedna korekta, P2-5 wcześniejszy runner poza zakresem. Parent0994 korekta v1.7.374 / `27ff986a873559330cd75aad3ee47081a41758d5`, Claude high R2 PASS.
- Kontrakt oceny jest wdrożony teraz; realny PASS nowego kandydata dostarczy TASK-0997.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. wyścigi aktywacji i niezmienność zadań.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [API_CONTRACT](../../architecture/API_CONTRACT.md).
- Zakres odczytu uzupełniający z planu: D-527/D-544, API_CONTRACT, kontrakt rejestru.

- [D-527](../../process/decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-544](../../process/decisions/DECISION_LOG_2026.md#d-544--nowe-gry-777-importują-przez-v3-z-profilem-grid_profile_777_v2) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-549](../../process/decisions/DECISION_LOG_2026.md#d-549--wspólna-geometria-v3-i-domyślna-wersja) — accepted shared geometry/default i zachowanie pinów TASK-1012.

## Scope

- Odrębne polecenia publish, activate, set-default i rollback.
- CAS przypisania, idempotencja i historia.
- Bazy historyczne wymagają jawnego dopuszczenia z istniejącym raportem; nowi kandydaci wymagają nowej bramki.

## Out of scope

- Bez żywej aktywacji i bez zmiany domyślnej wersji bez decyzji operatora.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Dwie konkurencyjne aktywacje nie nadpisują się; brak PASS blokuje nowego kandydata; rozpoczęty job zachowuje wersję; rollback nie zmienia wycinków.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

### Verified current behavior and protected boundary

`GridModelRegistryService` currently registers immutable descriptors and exposes read-only assignments. `SqlAlchemyGridModelRegistryRepository.lock` serializes catalogue writes with transaction advisory lock 9910994 and a 5 s PostgreSQL lock timeout. Migration0156 seeds two historical versions and explicit historical assignments, without publication. `SqlAlchemyGridProfileSnapshotResolver._assigned_snapshot` pins a descriptor into a v2 snapshot; start/reuse/restart read that pin, not a current assignment.

Existing historical assignments remain usable without implicit publication. This grandfathering applies only to an existing assignment head and its historical event; a new explicit activation, rollback or default command must satisfy the new publication/evidence gates. No assignment is seeded, switched or admitted by this task. Existing snapshots v1/v2 and descriptor admission are immutable. In particular, admission `not_evaluated` never changes to PASS.

### Implemented command and persistence contract

Extend the existing registry router rather than adding a parallel registry. Add publish(version), activate(game), set-default(global) and rollback(game) as separate POST operations, plus default/history reads. All commands carry UUID idempotencyKey and nonnegative expectedRevision. Activate/rollback/default carry versionId; publish references a server-owned evaluation ID for a candidate, or explicitly admits an exact frozen historical base. Actor comes from the local Admin convention (`ADMIN_ACTOR = local-owner`), not request JSON. Provenance distinguishes the four commands and historical admission.

Canonical command hashes include operation, target/version, game scope, expectedRevision, evidence reference and server actor. Under the existing catalogue transaction lock, scope/game checks precede game reads. Receipt lookup precedes CAS and current eligibility: exact retry returns the immutable original receipt after process restart/lost response, without moving the current head back. Idempotency is namespaced: publish/set-default share one global control ledger, activate/rollback share a ledger per game, and TASK-0994 registration retains its own receipt ledger. The same UUID in different namespaces denotes independent commands. Exact retry requires the same operation, scope and payload; changed content under the same key within one namespace gives GRID_MODEL_IDEMPOTENCY_CONFLICT. Initial revision is 0, successful head writes increment by 1. Two callers with the same expected revision produce one success and one conflict. No exception commits a partial head/event/receipt.

Publication is a separate immutable row (version revision 1), independent of registration. A global append-only command ledger contains publication/default receipts and audit provenance; a singleton mutable default head stores version/revision. Assignment events gain nullable receipt/provenance fields for legacy rows and new activate/rollback kinds. New events record expectedRevision, command JSON/SHA, actor, proof identity/SHA and original receipt. Historical rows are not rewritten. Rollback requires a prior target in this game's history and current published eligibility; it changes only assignment/event. It never touches source, crop, canonical, sequence, symbol or job tables.

### Evaluation and historical evidence boundary

The task introduces a minimal immutable server-owned persisted evaluation read contract and append-only invalidations. It pins candidate/base descriptor SHA, cohort identity/fingerprint, evaluation policy, producer and separate per-game outcomes. The publication API accepts only a report ID reference; it has no report creation endpoint and cannot accept client PASS booleans, arbitrary evidence JSON or cohort claims. TASK-0997 supplies real trusted evaluation records; missing, stale, invalidated, incompatible or unsuccessful evidence fails closed. This contract is not a claim that a real model has passed evaluation. Lead accepted the minimal read contract before implementation. Structural guards require the supported schema/producer/policy, canonical report JSON and SHA, exact candidate/base/cohort pins, unique requiredGameIds and exactly one complete validation+regression PASS outcome for each required game. Currentness is the absence of a persisted invalidation; the future evaluator/cohort writer must append invalidation under lock 9910994 atomically with a truth change, never mutate the report. No HTTP writer exists. The repository supplies only persisted rows; outcome calculation and checkpoint selection remain TASK-0997. Normal activation requires the existing target game in the evaluated scope. The eligible published-default read contract checks all evaluated games but does not require a future game UUID; TASK-1004 will record transfer provenance during atomic creation, without claiming measured quality for the new game.

Historical admission uses only an exact descriptor from `historical_catalogue()` and its real checked-in comparison report (`inferenceManifest.report`). The server reads the bounded existing UTF-8 report and pins its path/SHA together with frozen historical result descriptors. The historical proof is labelled historical admission, not a new PASS or fabricated cohort. New activation/default checks publication, current evidence and artifact bytes. New per-game activation also checks engine/configuration, supported topology/capabilities and the report's game scope. Global default does not update any existing game or job. Lead confirmed the existing TASK-1012 boundary: invalidation blocks new publish/activate/rollback/default and bootstrap eligibility, but does not implicitly deactivate a pinned assignment. A new preflight of an assigned game still uses that assignment; start/reuse/restart keep their stored snapshots. Catalogue responses expose published, available and eligible/eligibilityReasonCode separately, with GRID_MODEL_EVALUATION_STALE after invalidation. TASK-1000 must visibly warn about stale evidence and allow conscious rollback. New-game creation and UI remain TASK-1004/1011.

### One correction round after Claude R1

The auditor's REVISE report is preserved. Lead documented the architectural read contract and invalidation/writer ownership in D-549 after the audit; this is not represented as a pre-implementation log entry. Corrections add controlled 409 failures for a persisted candidate without a base and an unsupported adapter contract, route history through the application service, and explicitly document/test the existing idempotency namespaces. No migration, CAS or model scope changes were introduced. The PostgreSQL test now persists a PROCESSING JobModel before activation and another candidate-pinned job before rollback, then reloads both through SqlAlchemyJobRepository and a new interpreter after the commands. Fresh report/artifact SHA checks remain; linear catalogue cost and N+1 queries are an explicitly accepted risk, without a benchmark or mtime cache.

### Schema, compatibility and verification

Migration 0157 creates public control tables only and publishes frozen manifest v10; frozen manifests v1–v9 and game partition lists remain unchanged. New shared reports/publication/global commands/default belong to shared control plane; assignment events remain catalog with explicit game predicates. Central ORM registration must work in either import order. Downgrade refuses loss of immutable history. Migration execution is limited to a disposable test database and role with exact ownership/session cleanup receipts; no operator migration, backup, publish, activation or service lifecycle action.

Focused checks will cover missing/failed/stale/mismatched evidence, genuine historical report admission, immutable descriptor/hash, HTTP strict requests, exact retry across sessions, key/hash conflict, transactional failure, concurrent PostgreSQL CAS, cross-game scope rejection, default independence, rollback target history and unchanged artifacts/job pins. Update backend/OpenAPI/generated TypeScript/wrapper/request tests together. Run scoped lint/typecheck, docs checks and code map regeneration. Lead owns audit and commit; leave status in_progress with exact audit scope.

## Expected files

- Existing: `application/grid_model_registry.py`, `storage/grid_model_registry.py`, `storage/grid_model_registry_models.py`, `api/grid_model_registry.py`, `schemas/grid_model_registry.py`.
- New: `domain/grid_model_publication.py`, `application/grid_model_publication.py`, `storage/game_data_v2_manifest_v10.py`, migration `0157_grid_model_publication.py`.
- Current manifest/readiness imports: `storage/catalog_repository.py`, `storage/game_partition_lifecycle.py`, `storage/game_storage_routing.py`, `storage/schema_readiness.py`.
- Focused tests: new `test_grid_model_publication_and_activation.py` and PostgreSQL control/CAS test; existing registry/schema/readiness tests.
- Generated OpenAPI/client, `packages/admin-api-client/src/index.ts` and its request test; owner API/data/ownership docs and code maps. No form or new-game creation changes.

## Test cases

- Dwie konkurencyjne aktywacje nie nadpisują się; brak PASS blokuje nowego kandydata; rozpoczęty job zachowuje wersję; rollback nie zmienia wycinków.

## Verification

Zakres: API, OpenAPI, DOC.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run openapi:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_catalog_api.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez żywej aktywacji i bez zmiany domyślnej wersji bez decyzji operatora.

## Outcome

### Execution phase

- Faza: done; gotowe do osobnego commita i oczekiwania na integrację po całym planie.
- Baza taska: v1.7.375 / `acf9ce4079b3ed176b1d40babb77f4e5a3ac9988`.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14).
- Worktree: `D:/game_predicotr/worktrees/v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: **v1.7.376 / `6d89d079502a128047cfcd183e420ef35382a78c`**. Pełny hash zapisano po utworzeniu; te metadane wejdą z następnym taskiem. Bez scalenia i push.
- Audit: [Claude R1 REVISE](../../quality/TASK-0998_AUDIT_claude-fable-5-1.md), `claude-fable-5-1`/medium, osobny kontekst i tryb tylko do odczytu, limit operatora 20 min. Raport pozostaje bez zmian. [Rozliczenie leada](../../quality/TASK-0998_AUDIT_RESPONSE_CODEX.md) nie jest nowym werdyktem audytora. Procesowe P1-1 zamknięto rozszerzeniem D-549 po audycie; zachowanie objęte P1 nie zmieniło się. Nie uruchamiano automatycznego R2. Pierwotny scope `artifacts/audits/TASK-0998_SCOPE.json` pozostaje dowodem przed poprawkami; nowy `TASK-0998_CORRECTION_SCOPE.json` opisuje poprawki.

### Changed

- Dodano odrębne publish(version), activate(game), set-default(global) i rollback(game), immutable receipts z canonical command hash, CAS expectedRevision i historię. Exact replay zwraca pierwotny wynik po utracie odpowiedzi, zmianie head lub invalidation, bez ponownej mutacji.
- Serwer czyta zamknięty persisted evaluation contract: producer/schema/policy, SHA i identity candidate/base/cohort, pełny wymagany zakres i outcomes per gra. HTTP nie posiada writera raportów i odrzuca client PASS, arbitrary report JSON oraz actor. Brak/stale/mismatch/niepełny zakres blokuje nowe komendy. Rzeczywiste wyniki i obliczenia należą do TASK-0997; użyte testowe outcomes nie stanowią pomiaru modelu.
- Historyczny publish jest jawnym `historical_admission` exact frozen descriptor z odczytem rzeczywistego raportu i pinem SHA/historycznych wyników. Nie powstaje nowy PASS, kohorta ani zmiana immutable admission.
- `published`, `available` i `eligible` są niezależne. `eligibilityReasonCode=GRID_MODEL_EVALUATION_STALE` pokazuje invalidation. Lead potwierdził zachowanie resolvera TASK-1012: invalidation blokuje nowe komendy/initial eligibility, ale nie zdejmuje istniejącego assignment ani nie przełącza jego preflightów. Rozpoczęte joby nadal używają własnych snapshotów. Historyczne przypisania pozostają użyteczne bez automatycznej publikacji. TASK-1000 ma widocznie ostrzegać o stale.
- Dodano migrację `0157_grid_model_publication` i frozen manifest v10: pięć public shared control tabel oraz receipt/provenance w istniejących catalog assignment events. Nie zmieniono list/definicji game partitions, frozen manifestów v1–v9, historycznych descriptorów/SHA ani danych domenowych. Globalna historia pozostaje po usunięciu gry, a dotychczasowy cascade jej assignment/events działa dalej. Downgrade odmawia utraty historii.
- Advisory lock 9910994 i refreshed head odczytują aktualną revision także po oczekiwaniu na konkurenta. `populate_existing` dotyczy mutable head i nie porzuca innych oczekujących zmian sesji. Event/head/receipt są atomowe. Rollback wymaga wcześniejszego opublikowanego eligible targetu tej samej gry i zmienia tylko assignment/history.
- API, OpenAPI, wygenerowany klient, wrapper i testy żądań zmieniono razem. Globalne odczyty nie ujawniają raportów/assignmentów innych gier. Historia GET ma limit 200 najnowszych zdarzeń; pełny ledger pozostaje trwały w bazie.

### Verification results

Wszystkie komendy skończone miały jawne limity do 120 s. Nie uruchamiano usług ani rzeczywistego modelu. Python był uruchamiany w UTF-8; kontrolne nowe procesy używają jawnego worktree PYTHONPATH.

- Pierwsza skoncentrowana grupa: 53 PASS / 14.31 s. Następnie dodano i wykonano dodatkowe przypadki rollback/receipt/evidence oraz regresje.
- Finalna grupa API/worker: 92 PASS i 1 FAIL / 38.50 s. Zakres: `test_grid_model_publication_and_activation.py`, `test_grid_model_registry.py`, `test_game_data_v2_schema.py`, `test_schema_readiness.py`, `test_dynamic_grid_snapshots.py`, `test_catalog_api.py`, worker `test_dynamic_grid_snapshot_replay.py`. Jedyny FAIL dotyczył wcześniejszego testu subprocess: runner nie przekazał worktree PYTHONPATH, a wspólna editable .venv załadowała starszy checkout główny. Nie zmieniano źródła dla tej porażki. Ponowiono wyłącznie `test_third_family_roundtrip_immutable_and_new_process` z właściwym PYTHONPATH: 1 PASS / 7.82 s. Logi: `TASK-0998_FOCUSED_TESTS.log`, `TASK-0998_RESTART_REGRESSION.log`.
- Pierwsza sandboxowa próba testu: błąd setup TEMP `could not create numbered dir ... after 10 tries`; log `TASK-0998_FIRST_TEST.log`. Wykonano później te same fixtures poza sandboxem z zaakceptowanym require_escalated; nie zmieniono konfiguracji produkcyjnej ani nie oznaczono pierwszej próby jako PASS.
- PostgreSQL: pierwszy dowód 0156→0157, rzeczywisty wyścig CAS, niezmienność i nowy interpreter: 1 PASS / 14.24 s. Po zawężeniu odświeżania identity map do head wykonano uzasadnioną finalną kontrolę CAS i zmienionej regresji rejestru: 2 PASS / 25.68 s. Zakres: `integration/test_grid_model_publication_postgres.py` i `integration/test_grid_model_registry_postgres.py`. Sprawdzono NOBYPASSRLS, frozen JSON/history, identyczny hash definicji data plane, jednego zwycięzcę CAS, świeży head, atomic rollback, scoped access, immutable triggers, cascade gry, zero automatycznej publikacji/default oraz odmowę downgrade.
- Finalne PG receipty: `artifacts/audits/TASK-0998_PG_RECEIPT.json` i `artifacts/audits/TASK-0998_REGISTRY_REGRESSION_PG_RECEIPT.json`. Obie własne bazy i role mają phase=cleaned, zgodnego ownera, pidsBeforeCleanup=[], databaseRemaining=0, roleRemaining=0, operatorDatabaseChanged=false. Pierwszy receipt zachowano jako `TASK-0998_PG_RECEIPT_R1.json`; finalny log `TASK-0998_PG_TESTS_FINAL.log`. Nie użyto danych operatora ani nowej kopii bazy.
- Klient Admin API: 116 PASS, build, typecheck, lint oraz pełne `npm run openapi:check` PASS. Testy obejmują oddzielne URL/method/body/CAS/evaluationId i zachowanie published-but-stale niezależnie od dostępności plików. Log: `TASK-0998_CLIENT_CHECKS.log`.
- Ruff check/format: 21 zmienionych plików PASS. Scoped mypy `--follow-imports=silent`: 14 source files PASS. Importowane istniejące moduły nie były rozszerzane do globalnego typechecku; znany wcześniejszy source_lattice_geometry pozostaje poza zakresem. Log `TASK-0998_STATIC_CHECKS_FINAL.log`.
- `npm run docs:check`, `npm run code-map:check`, scoped Prettier i `git diff --check`:PASS. CODE_MAP i CODE_MAP_SYMBOLS zregenerowane po nowych modułach. Log `TASK-0998_DOC_MAP_FORMAT_CHECKS.log`.

### Definition of Done / accepted plan comparison

- Funkcjonalność i przypadki brzegowe: spełnione w mechanizmie i fixtures; konkurencyjne aktywacje nie nadpisują się, brak nowej oceny blokuje kandydata, retry nie resetuje head, rollback nie zmienia plików/snapshotów. Protected historical assignments i historyczna777 pozostają zachowane.
- Dane: Alembic i zamrożony manifest dodane; izolowany PostgreSQL potwierdza niezmienność data plane i pełne sprzątnięcie. Migracja operatora nie została wykonana i wymaga jego osobnego działania przed integracją kodu z działającym API.
- Kontrakt: pełny pion backend/OpenAPI/generated client/wrapper/request test wykonany; stabilne kody odmów i scope guards przetestowane.
- Kod/kontrole/dokumentacja: skoncentrowane lint, format, typy i regresje wykonane; owner docs i mapy aktualne. Wcześniejszy błąd runnera pojedynczej Suite pozostaje poza zakresem; użyto bezpośrednich ścieżek pytest.
- Audyt R1 REVISE i jedna runda poprawek są zapisane poniżej. P1-1 zamknął lead w D-549; P2-1/2/3/5 rozwiązano i zweryfikowano, P2-4 zaakceptowano z uzasadnieniem. Pozostaje osobny commit/Outcome hash oraz formalne zamknięcie przez leada. Task nadal nie jest przedstawiany jako scalony.

### Audit R1 — disposition and one correction round

- **P1-1 — zamknięte dokumentacyjnie przez leada.** Rozszerzenie [D-549](../../process/decisions/DECISION_LOG_2026.md#d-549--wspólna-geometria-v3-i-domyślna-wersja) opisuje kontrakt oceny, pięć shared tabel, oddzielną publikację, ownerów writerów i invalidations, currentness, namespace oraz istniejące assignment/piny. Wpis uczciwie odnotowuje uzupełnienie logu po audycie. Wykonawca poprawek nie edytował Decision Log ani rootowego rozliczenia.
- **P2-1 — rozwiązane.** Brak bazy w zapisanym kandydacie z evaluationId daje kontrolowane 409 GRID_MODEL_EVALUATION_REQUIRED. TypeError/ValueError adaptera modelu daje 409 GRID_MODEL_CONTRACT_UNSUPPORTED. Testy HTTP modyfikują wyłącznie adversarial SQLite fixture, przechodzą rzeczywisty adapter oraz transport i potwierdzają brak publication/event po odmowie; nie mockują walidatora.
- **P2-2 — rozwiązane.** Oba routery historii wywołują GridModelPublicationService.history; scope i ograniczony odczyt pozostają w repozytorium. Istniejące testy HTTP obu historii przeszły po zmianie.
- **P2-3 — rozliczone zgodnie z przyjętym kontraktem.** Globalny namespace publish/default i osobny namespace każdej gry activate/rollback są zgodne z obecnymi kluczami DB. Rejestracja ma własny ledger TASK-0994. Nie zwiększano globalnej unikalności. Test HTTP używa tego samego UUID we wszystkich trzech namespace, potwierdza niezależne zapisy, dokładne retry i konflikt zmienionej treści wewnątrz każdego namespace. Dokumentacja wskazuje potrzebę nowego UUID dla nowego zamiaru.
- **P2-4 — zaakceptowane ryzyko.** Zachowano świeże SHA raportu (plik ograniczony do 1 MiB) i artefaktów oraz zapytania eligibility per wersja. Katalog kontrolny jest pionem metadanych, a koszt GET rośnie liniowo z liczbą wersji; N+1 i brak pomiaru większej skali są jawne. Samo porównanie zapisanego SHA lub cache mtime ukryłoby zmianę realnego raportu i osłabiło fail-closed. Nie dodano takiego cache i nie uruchamiano benchmarku. Ewentualna przyszła optymalizacja TASK-1000 wymaga pomiaru oraz zachowania dowodu aktualnych bajtów; obecna akceptacja ryzyka nie jest wynikiem pomiaru.
- **P2-5 — rozwiązane.** Rzeczywisty PostgreSQL zapisuje przez SqlAlchemyJobRepository job PROCESSING z pinem bazy przed activate oraz drugi job z pinem kandydata przed rollback. Po activate i po rollback nowe sesje potwierdzają status, input_key i pełny input_payload/pin. Nowy interpreter po rollback odczytuje oba zapisy i odtwarza wcześniejszy receipt bez przestawienia head. Test nie uruchamia workera/inferencji, a stan PROCESSING jest wyłącznie fixture trwałego joba.
- **Kontrole poprawek:**35 PASS /18.56s (`test_grid_model_publication_and_activation.py`, `test_grid_model_registry.py`); jeden zmieniony PGtest: 1 PASS /15.67 s. Ruff check/format 4 plików i scoped mypy 2 source PASS. Logi: `TASK-0998_CORRECTION_FOCUSED_TESTS.log`, `TASK-0998_CORRECTION_PG_TESTS.log`, `TASK-0998_CORRECTION_STATIC_CHECKS.log`.
- **Kontrole kontraktu/dokumentacji:** export OpenAPI --check, docs:check oraz code-map:check PASS; mapy zregenerowano. Globalny diff --check pierwszej próby wykrył wyłącznie rootowy DECISION_LOG.md:286 (końcowa pusta linia); przekazano leadowi, bez zmiany jego pliku przez wykonawcę. Własny scope i końcowe wyniki opisuje `TASK-0998_CORRECTION_CHECK_RECEIPT.json`. Log: `TASK-0998_CORRECTION_DOC_MAP_CHECKS.log`.
- **PG cleanup:** `artifacts/audits/TASK-0998_CORRECTION_PG_RECEIPT.json`: phase=cleaned, owner i ownerBeforeCleanup zgodne, pidsBeforeCleanup=[], databaseRemaining=0, roleRemaining=0, operatorDatabaseChanged=false. Wcześniejsze receipty pozostają zachowane. Zmiana testu trwałego joba uzasadniała ten jeden PGtest; nie powtarzano niezwiązanej regresji rejestru ani szerokich zestawów.
- **Pozostałe uwagi:** brak otwartych P0/P1 po dokumentacyjnym zamknięciu P1-1 przez leada. P2-4 pozostaje zaakceptowanym ryzykiem wydajności. R1 nadal REVISE, bez dopisywania fikcyjnego PASS i bez samodzielnego R2. Root prowadzi końcowe rozliczenie/commit.

### Not completed

- Integracja i operacje operatora pozostają niewykonane. Task przeniesiono do completed; commit v1.7.376 zapisany, hash dopisano po utworzeniu. Audyt R1 i jedna runda poprawek wykonane; P1-1 zamknięte dokumentacyjnie przez leada, bez nowego werdyktu PASS.
- Realny wynik jakości/PASS TASK-0997, UI/panel TASK-1000, nowe gry/formularze TASK-1004/1011. Nie przeprowadzono treningu, inference/GPU, aktywacji, publikacji/default na danych operatora, jego migracji ani restartu/usług.
- Nie uruchamiano pełnej quality/całego Workera, benchmarków ani masowych fixtures; skupione kontrole pokrywają zmieniony pion. Nie powtarzano szerokich zestawów po zieleni bez nowego powodu.

### Documentation updates

- Owner docs: API_CONTRACT, DATA_MODEL, GAME_DATA_V2_OWNERSHIP, LOCAL_OPERATION_GUIDE; task oraz wyłącznie sekcja TASK-0998 CURRENT_STATE. Zapisano zaakceptowane przez leada rozdzielenie currentness, assignment i przyszłego bootstrapu.
- Rootowe README/plan/posthash1012 pozostają poza scope wykonawcy TASK-0998. Lead dołączy ich metadane osobno. Scope i hashe kontroluje `artifacts/audits/TASK-0998_SCOPE.json`.

### Recommended next task

- TASK-1004 po audycie i commicie TASK-0998. Wykorzystać eligible published-default read contract bez wymogu UUID przyszłej gry; atomowo zapisać grę/initial assignment i jawne pochodzenie transferu, bez deklaracji pomierzonej jakości nowej gry. Nie rozszerzano TASK-0998 o ten zapis.
