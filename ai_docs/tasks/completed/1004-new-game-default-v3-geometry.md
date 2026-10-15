---
title: TASK-1004 — Tworzenie gry z domyślną geometrią V3
status: done
last_updated: 2026-10-15
---

# TASK-1004 — Tworzenie gry z domyślną geometrią V3

## Status

`done`

## Goal

Nowa gra korzysta z opublikowanej geometrii bez treningu od zera.

## Context

Task jest częścią zaakceptowanej rewizji 6. Nowe gry i izolacja symboli. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0998 done, v1.7.376 / `6d89d079502a128047cfcd183e420ef35382a78c`; R1 REVISE i jedna runda poprawek, procesowe P1 zamknięte D-549, P2-4 jawnie zaakceptowane. Bez fikcyjnego PASS i bez automatycznego R2.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. spójny pion tworzenia i izolacja symboli.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [ADMIN_APP](../../requirements/ADMIN_APP.md).
- Zakres odczytu uzupełniający z planu: ADMIN_APP, D-527, wymagania cold-start symboli.

- [D-527](../../process/decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Backend przypina domyślną wersję.
- Zaawansowany wybór/fork kontroluje zgodność i dziedziczy wyłączenia.
- Utworzenie gry i przypisania jest atomowe.
- Format danych strony nie pełni funkcji identyfikatora checkpointu.

## Out of scope

- Bez tworzenia rzeczywistych gier i przełączania istniejących przypisań.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] GameCreate bez `shapeGeometryConfiguration` zapisuje neutralne V3; modelassignment jest niezależny.
- [x] Brak default dopuszcza draft/unassigned, blokuje import do assignment; jawna zgodna opublikowana wersja tworzy assigned.
- [x] Nowe klasyczne tworzenie jest zablokowane, historyczny read/update zachowuje stare wartości.
- [x] Brak default blokuje import; fork nie kopiuje etykiet ani wag.
- [x] Nowa gra ma własny katalog i cold-start symboli, bez modelu obcej gry.
- [x] Retry nie tworzy drugiej gry.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

### Contract accepted before implementation — D-549 recorded

The lead accepted the concrete contract on 2026-10-15 and recorded matching D-549 annual/index entries and the plan clarification before implementation. The changed task, plan section and both D-549 copies were read again before code. The following contract is the implementation target, not a verification result. Existing dirty README/plan/CURRENT_STATE and TASK-0998 post-commit metadata belong to the lead and remain preserved. Repository history confirms base v1.7.376 / `6d89d079502a128047cfcd183e420ef35382a78c`.

**HTTP create contract.** Extend the existing `POST /api/v1/admin/games` and `GameCreate`, not a parallel creation endpoint. Require `idempotencyKey: UUID`; omission returns transport validation422. Omitted `shapeGeometryConfiguration` normalizes to `neural_grid_v3`; an explicit value is accepted only when it is exactly `neural_grid_v3`. Known legacy values return `GAME_CREATE_V3_REQUIRED`, while unknown enum values remain422. `GameUpdate`, historical GET, all five enum values and historical NULL retain their existing behavior. Preserve DRAFT as the omitted status, and preserve an explicit ACTIVE or ARCHIVED status even without an assignment.

The proposed optional discriminated `gridModel` selection is `{mode: "default"}` (also the normalized omitted value), `{mode: "published", versionId: UUID}`, or `{mode: "fork", baseVersionId: UUID, familyCode: str, familyLabel: str}`. Family code uses the existing registry pattern and is a new unique family identity; the server generates its UUID. There is no new version/checkpoint ID for a fork. Default selection occurs once under the existing catalogue lock. No default, or a default whose publication/artifacts/evidence are no longer eligible, permits an unassigned game and records the exact blocker. Registry corruption, infrastructure failures and malformed evidence are errors, not a silent unassigned success. Explicit published/fork requests fail atomically if the selected base is unavailable, unpublished, stale or incompatible. Reuse `GridModelPublicationService.eligible(version_id, game_id=None)` and `catalogue_model_version` for the closed topology/capabilities/preprocessing/render contract. Never call evaluated activation with the future game UUID.

**Create namespace and durable receipt.** Add proposed public catalogue table `game_create_receipts`: `idempotency_key UUID PK`, `game_id UUID UNIQUE NOT NULL`, `command_json TEXT NOT NULL`, `command_sha256 CHAR(64) NOT NULL`, `reservation_json TEXT NOT NULL`, `reservation_sha256 CHAR(64) NOT NULL`, `actor VARCHAR(64) NOT NULL`, `created_at TIMESTAMPTZ NOT NULL`. Both SHA fields have hexadecimal CHECKs, JSON uses the existing canonical serializer, and SQL UPDATE/DELETE is rejected by the existing immutable guard function. The ledger namespace is global to `game-create-v1`, separate from register/global publish-default/per-game assignment ledgers. The same UUID in a different ledger is not a collision. Do not FK the durable receipt to `games`: physical deletion must not erase an idempotency claim or block the existing deletion workflow. Replay of a removed result returns `GAME_CREATE_RESULT_REMOVED`, never a second game.

The canonical command contains kind/schema, normalized code/name/status/count/neutral format/super kind and requested gridModel selection, plus key and server-owned actor. It excludes mutable resolution such as current default revision. The immutable reservation stores game ID, original selection outcome/reason, resolved default revision, version ID/manifest SHA, training family ID, assignment revision/event ID, and transfer provenance SHA when assigned. Exact retry reads and validates this receipt before current eligibility/default/CAS checks. It returns the same current game after resuming its reserved provisioning, without rewriting assignment or selecting a new default. A changed command under the same key returns `GAME_CREATE_IDEMPOTENCY_CONFLICT`. Another key with the same code remains `GAME_CODE_ALREADY_EXISTS`; matching fields alone are no longer permission to adopt a reservation. Known lifecycle failures remain failures and expose the original retry key; they do not imply rollback of an already committed reservation.

**Atomic boundary and locks.** `SqlAlchemyCatalogRepository.add_game` currently flushes GameModel, then `_provision_v2_game` calls lifecycle `start_or_resume` and commits at `catalog_repository.py:181–189` before per-table DDL. Introduce an explicit initializer callback/port passed from the create orchestration into the repository and invoked after lifecycle reservation but before that first commit. The initializer and registry repository share the request Session. Order: validate syntax; obtain catalogue advisory transaction lock9910994 with5s timeout; inspect receipt; resolve eligible base/default and immutable lineage; reserve/flush GameModel; reserve MIGRATING location and lifecycle receipt; create fork family/lineage if requested; write assignment revision1 plus bootstrap event; write create receipt; flush; commit once. Any failure before that commit rolls back every item, including family and lifecycle metadata. Non-PostgreSQL adapters perform the same logical initializer before their outer transaction commits.

PostgreSQL verification exposed the existing GameStorageSession ORM flush rule: any pending record with game_id enters the data-plane WRITE gate, which correctly rejects MIGRATING. Bootstrap assignment/head/event and create receipt therefore use typed Core writes to explicit public tables through the same Session connection and application role. Family records remain ORM because they have no game_id. This preserves one reservation transaction without weakening routing, opening an owner catalogue session, or adding a commit. The injected failure now occurs after the receipt Core INSERT and must roll back every reservation item.

After the reservation commit, release catalogue and game row locks before owner DDL. Preserve existing per-table lifecycle transactions, operation receipt, progress checkpoints, retry bounds and schema-owner factory. A resumed create looks up the receipt first, checks its exact game ID, leaves the reserved model untouched and resumes the same lifecycle operation. Concurrent same-key requests serialize the reservation, then lifecycle locks serialize individual DDL steps. Do not acquire9910994 from within an owner partition-DDL transaction. Initial bootstrap uses catalogue lock then game row then assignment; normal activate/rollback already uses catalogue lock then game row. No game data-plane reads occur before provisioning is active.

**Transfer provenance, distinct from evaluation.** Extend assignment-event CHECK/history schema with `kind="bootstrap"` and `evidenceKind="transfer_bootstrap"`. The closed proposed `grid-model-transfer-v1` evidence pins source version/family, source manifest SHA, source publication evidence kind/SHA and evaluation reference where present, chosen training family, observed default revision where applicable, lineage SHA, and `qualityScope="source-games-only"`. It asserts compatibility/transfer, never evaluation of the new game. Store the existing complete command/receipt/actor/hash fields and use expected revision0, resulting revision1. Add nullable `training_family_id` FK to `game_grid_model_assignments` for historical compatibility; initialize it to source family or fork family. Include it in assignment GET. Existing evaluated activation continues to require per-game evidence; on an explicit later activation/rollback the training family follows the selected version's family and the original fork provenance remains immutable history. Old receipts retain their canonical JSON and SHA; new optional response fields do not rewrite them.

**Unassigned bootstrap after creation.** Extend the existing assignment activate command with optional `mode="initial_transfer"`; omitted mode remains the current evaluated behavior and keeps the old command canonicalization. The new mode accepts an explicit eligible published version and `expectedRevision=0`, requires neutral V3 plus a receipt from this creation path, and requires no assignment head or assignment history. It performs the same transfer-only bootstrap under catalogue lock/game lock/CAS and uses the existing per-game receipt namespace. The UI reads the current eligible default or an advanced selection and sends its exact version; no automatic adoption runs in GET, import or background jobs. An exact retry recovers the original bootstrap receipt before eligibility/CAS. After any assignment exists, initial_transfer cannot replace it; normal evaluated activate/rollback retains the per-game gate. This also supports an explicitly ACTIVE unassigned record without silently changing its status. A late bootstrap is an explicit user action, not an operational activation executed by this implementation task.

**Fork and inherited exclusions.** Add proposed shared public `grid_model_family_forks`: `family_id UUID PK/FK grid_model_families RESTRICT`, `base_version_id UUID FK grid_model_versions RESTRICT`, `base_manifest_sha256 CHAR(64) NOT NULL`, `lineage_json TEXT NOT NULL`, `lineage_sha256 CHAR(64) NOT NULL`, `actor VARCHAR(64) NOT NULL`, `created_at TIMESTAMPTZ NOT NULL`; immutable SQL guard and SHA CHECKs. Create the ordinary family descriptor with existing topology/capabilities, then this lineage row, without inserting any cloned version, publication, evaluation, checkpoint, symbols or labels. The assigned inference version remains the exact existing published base; `trainingFamilyId` is the new family. No artifact directory is copied or invented.

The server builds bounded canonical `grid-model-family-lineage-v1` from the baseVersionId chain (maximum64 distinct versions; missing link, cycle or limit returns `GRID_MODEL_LINEAGE_INVALID`). Each entry pins version ID, manifest SHA, original snapshotId, optional cohortId and, where present, the actual publication/evaluation ID+SHA or historical report SHA. Also pin any existing family-fork lineage. The protected source references are inherited from these immutable ancestor snapshots/cohorts/evaluations; the fixed policy protects ancestral VALIDATION/REGRESSION, final_test, unseen_game, Reels/Treasure and declared holdouts. These references are not invented source lists or copied labels. TASK-1002/0995 must resolve them to recording/alias/byte/pixel identities and reject TRAIN admission if any protected reference cannot be resolved. The contract reader returns this requirement explicitly; it never treats an unresolved reference as an empty exclusion set. Registration into a fork family must prove that its base lineage contains the frozen fork base with the same manifest SHA; missing/changed/foreign ancestry is rejected. Publication remains unavailable until a real trained version and its own real evidence exist. Tests cover persisted reference inheritance and fail-closed ancestry, not a claim that the future TRAIN pipeline is already implemented.

**Symbol isolation for all new V3 selections.** `SqlAlchemySymbolModelSnapshotResolver._resolve_in_game_storage` currently takes a global `bootstrap_symbol_model_snapshot()` at `storage/symbol_model_snapshot_resolver.py:79–87` when no activation exists and codes happen to match. This happens before cold-start: `JobService._resolve_import_symbol_snapshot` calls `resolve` at `application/jobs.py:883`, and only on `SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED` calls `resolve_unclassified_cold_start` at890. Report preflight likewise calls resolve at1765–1768 before the cold-start fallback at1784–1794. Therefore changing only neutral-game creation would leave a foreign-weight path for existing 777v2/Mumie formats.

Proposed narrow extension: before the global-bootstrap branch, read the requested game's code/configuration through a typed explicit `public.games` catalogue SELECT with game-ID predicate; for every `uses_neural_grid` format (777v2, Mumie, neutral), return `SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED` when there is no own activation. A ready own candidate still requires explicit activation; an own active iteration continues through existing ownership/hash/catalog checks. The scoped unclassified resolver remains the only first-import fallback and checks this game's labels/cohort/iterations/activations. Preserve global legacy bootstrap for non-V3 and historical game7; preserve persisted job snapshots and historical payload readers, so replay never reselects a model. Production wiring already always injects the resolver; missing-resolver direct JobService shortcuts must also fail closed for a known V3 new-selection path instead of manufacturing the global model. Inspect the caller boundary and add focused regression coverage before changing those shortcuts. No worker execution, foreign symbol import, model inference or training is authorized. This is an explicit cross-format new-selection correction within1004 and requires the lead's D-549 acceptance.

Existing symbol cold-start requires at least two active own codes (domain/symbol_model_snapshots.py:199–205). The lead confirmed preservation of this existing rule: an empty new catalogue blocks symbol snapshot/start, then two explicitly defined own codes enable the existing scoped unclassified snapshot. No placeholder symbols, new cold-start contract, foreign weights or threshold change. PostgreSQL checks both states and excludes a foreign game catalogue; the advanced geometry UI states this prerequisite.

**Migration/ownership/permissions.** The migration graph inspected with both Assign and AnnAssign has one head, `0157_grid_model_publication`. Proposed `0158_new_game_v3_bootstrap` depends on0157. Frozen manifestv11 inherits v10's GAME/CREATE/MIGRATE/DELETE/PARTITIONED lists exactly, adds `game_create_receipts` as public catalog and `grid_model_family_forks` as shared, and updates control manifest/location revision only. No game payload partitions, existing format values, assignments, model JSON/SHA or historic frozenv1–v10 change. Update active runtime imports and startup head guard to0158. Migration uses the existing5s lock/120s statement limits, rejects unfinished lifecycle or unexpected prior manifest and refuses downgrade loss of immutable history. New ORM mappings must be registered centrally through the existing model registration path; public table ownership must never fall through the game router or implicit unqualified SQL. Per-game assignment/bootstrap reads retain scope/session guards. Global default/version GET never returns game receipt IDs, private source identities or fork/game assignments. Tests use application role NOSUPERUSER/NOBYPASSRLS and a separate owner only for DDL; grants derive from the established database_roles mechanism. Operator migration is not executed.

**UI and recovery.** The ordinary create form removes page/model selectors, sends neutral format by omission and preserves code/name/count/status/super kind. A collapsed advanced block offers compatible eligible published versions and new-family-from-base fields. Historical edit keeps every old format option and update semantics. The form displays default/unassigned/import-blocker state from backend reads; a failed registry read is an error state, not assumed default absence. Persist the exact pending create command and key in localStorage before submission, namespace by API origin/schema; reload restores it and retry sends identical content. Ambiguous errors retain it; a changed form cannot overwrite an unresolved command. Success clears it. Never reconcile creates by code/name matching. Offer explicit first-assignment action only when the backend allows initial_transfer. Reuse the existing default/version/assignment HTTP surface, generated client and wrapper; no client-maintained eligibility rules.

**Planned checks, not results.** Add `test_new_game_default_v3_geometry.py` plus a focused PostgreSQL integration test. Cover default/explicit/fork/unassigned, explicit status preservation, legacy-create rejection versus historical GET/PATCH, actual atomic rollback before first commit, injected failure after a partition checkpoint, same key from a fresh interpreter after lost response/default change/invalidation, changed command conflict, concurrent same-key/different-key same-code, no repeated family/assignment/event, and removed-result replay. Verify actual application-role writes and owner-only DDL. Extend the existing greenfield lifecycle and lock retry regressions. Cover initial_transfer once then normal activation without per-game evidence rejected, published-but-stale/unavailable choices, immutable family/base references, own empty symbol catalogue, identical foreign class names across all three V3 formats, own activation, cold-start history blockers/scope and legacy bootstrap/persisted snapshots. Admin tests cover omitted format, advanced selection, restart recovery, duplicate submit and historical edit; client tests assert request bodies and new optional mode. Run focused pytest first, then scoped Ruff/mypy, Admin/client tests/lint/typecheck, OpenAPI generation/check, manifest/schema/head regressions, code-map regeneration/check and docs/diff checks. Each command is bounded to120s, with worktree PYTHONPATH in every new process. Isolated PostgreSQL fixtures have unique task1004 DB/role names and exact owner/PID/cleanup receipts; no operator DB, services, backup, actual game/default/publication/activation, GPU or benchmark actions.

### R1 correction contract accepted before recovery changes

The lead accepted the concrete recovery contract and recorded matching D-549 annual/index and plan clarifications before this behavioral correction. Those fragments were read again on2026-10-15 before code. A controlled domain create failure may receive details.createRecovery with schemaVersion game-create-recovery-v1, exact idempotencyKey and reservation not_created only after successful rollback and a fresh9910994 lock plus explicit public-ledger absence check. Existing receipts, idempotency conflicts, storage-not-ready, transport/infra/qualification failures and5xx have no marker. Qualification failure preserves the original error. The client trusts only the exact marker/key, including422 without proof as ambiguous. Confirmed abandonment first archives raw storage, namespace and timestamp durably, then removes pending. Failed archival retains pending. The archive is never automatically removed and does not delete any server reservation or adopt a game by code/name. This same recovery handles corrupted create/assignment storage.

## Expected files

- Additional existing owners confirmed during preread: `api/catalog.py:create_catalog_router`, `api/grid_model_registry.py:create_grid_model_registry_router`, `application/grid_model_publication.py:GridModelPublicationService`, `application/grid_model_registry.py:GridModelRegistryService`, `storage/catalog_repository.py:SqlAlchemyCatalogRepository`, `storage/grid_model_registry.py:SqlAlchemyGridModelRegistryRepository`, `storage/grid_model_registry_models.py`, `storage/schema_readiness.py`, `storage/game_partition_lifecycle.py`, `storage/game_storage_routing.py`, `main.py`, `schemas/grid_model_registry.py`, `application/jobs.py`, `packages/admin-api-client/src/index.ts`, generated OpenAPI/client files, and the owner docs `requirements/ADMIN_APP.md`, `requirements/SUPERVISED_MODEL_IMPROVEMENT.md`, `architecture/DATA_MODEL.md`, `architecture/API_CONTRACT.md`, `architecture/GAME_DATA_V2_OWNERSHIP.md`, `architecture/SUPERVISED_MODEL_IMPROVEMENT.md`.
- Proposed new modules: `domain/new_game_geometry.py` (closed create/transfer/lineage contracts), `application/new_game_geometry.py` (creation/initial-transfer orchestration), `storage/game_create_receipts.py` (durable create ledger), `storage/game_data_v2_manifest_v11.py`, and Alembic `0158_new_game_v3_bootstrap.py`. Split only where these responsibilities keep existing modules bounded. New ORM receipt/fork mappings remain centrally registered beside the existing registry mappings.
- Proposed new integration file: `services/api/tests/integration/test_new_game_v3_bootstrap_postgres.py`; existing lifecycle/migration/manifest/schema/symbol tests and Admin/client catalog tests receive focused regressions or fixture adaptation to the deliberate create-contract change.

- Istniejące: [game-catalog.tsx](../../../apps/admin/src/features/games/game-catalog.tsx) — komunikat klasycznej gotowości i formularz.
- Istniejące: [game-catalog-state.ts](../../../apps/admin/src/features/games/game-catalog-state.ts) — `SHAPE_GEOMETRY_CONFIGURATION_LABELS`.
- Istniejące: [catalog.py](../../../services/api/src/game_predictor_api/application/catalog.py) i [schematy katalogu](../../../services/api/src/game_predictor_api/schemas/catalog.py) — tworzenie i aktualizacja gry.
- Istniejące: [symbol_model_snapshot_resolver.py](../../../services/api/src/game_predictor_api/storage/symbol_model_snapshot_resolver.py) — `resolve_unclassified_cold_start`.
- Pozostały zakres wskazany w zaakceptowanym planie: –, `game-catalog-actions.ts`; klient i testy żądań.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_new_game_default_v3_geometry.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Brak default blokuje import; fork nie kopiuje etykiet ani wag.
- Nowa gra ma własny katalog i cold-start symboli, bez modelu obcej gry.
- Retry nie tworzy drugiej gry.

## Verification

Zakres: API, ADMIN, OpenAPI, DOC.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run openapi:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_catalog_api.py services/api/tests/test_symbol_model_catalog_binding.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez tworzenia rzeczywistych gier i przełączania istniejących przypisań.

## Outcome

### Execution phase

- Faza: done; Claude R2 PASS, brak otwartych P0/P1; gotowe do osobnego commita i oczekiwania na integrację po całym planie.
- Akceptacja: lead przyjął konkretny kontrakt i zapisał D-549 przed kodem 2026-10-15; task, odpowiedni fragment planu i obie kopie decyzji ponownie odczytano. Dopiski widoczności formularza oraz neutralnego importu odczytano przed zależną zmianą UI.
- Baza: v1.7.376 / `6d89d079502a128047cfcd183e420ef35382a78c`; branch `codex/v3-grid-fine-tuning`, worktree `D:/game_predicotr/worktrees/v3-grid-fine-tuning`.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`; zatwierdzony upstream main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d`.
- Commit: przygotowany v1.7.377; pełny hash po utworzeniu. Bez scalenia i push. Audyt Claude high R2 PASS po jednej rundzie poprawek; R1 pozostaje historycznym REVISE.

### R1 audit and one correction round

- [R1](../../quality/TASK-1004_AUDIT_claude-fable-5-1_R1.md): prawdziwy Claude high11m42s, REVISE; oryginał bez zmian. [Odpowiedź wykonawcy](../../quality/TASK-1004_CORRECTION_CODEX.md) rozlicza P1-1/2/3 i P2-1–5. R2 zakończył niezależny Claude: PASS; nie oznaczono własnych poprawek jako niezależnego audytu.
- Recovery zaakceptowano i zapisano D-549 przed kodem; szczegóły w Technical notes. Marker po rollback+ponownej blokadzie+braku public receiptu ma dokładny UUID. Istniejący receipt, storage-not-ready,5xx i błąd kwalifikacji pozostają niejednoznaczne. Potwierdzane porzucenie najpierw archiwizuje surowy wpis; awaria archiwum zachowuje pending. Nie usuwa rezerwacji serwera.
- Dodano cztery nietestowe create UUID i artifact_root callerów, bieżący operator guide0158/v11, jawne protokoły, pojedynczy receipt read i typowany brak gry. Testy HTTP initial_transfer oraz interakcje advanced/recovery uzupełnione. Stara statyczna asercja importu została dostosowana do zatwierdzonego routingu V3; regresja zachowania przy zmianie gry pozostała.
- Końcowy backend115 PASS, PG1 PASS21.21s, Admin738 unit PASS/24 interakcje PASS/14 scoped unit PASS. Pełny python:lint PASS. Mypy worker/src+scripts502 pliki PASS. Pełna łączna komenda mypy timeout100s nie jest PASS; API397 plików ujawnia dwa wcześniejsze błędy schemas/source_lattice_geometry.py:36,38, identycznego z HEAD. Własny Any→bool poprawiono; wynik końcowej kontroli API i pozostałe kontrole w odpowiedzi/manifestach. Bez napraw poza zakresem.
- Bieżący PG receipt: own DB game_predictor_task1004_fde9e2a7985b_test, rola task1004_fde9e2a7985b, owner game_predictor, PID26132/child39252; cleaned, pids[], DB/role remaining0. Obejmuje kwalifikację odrzucenia oraz zachowanie existing receipt/przerwanego provisioningu. Poprzednia baza i cleanup opisane niżej dotyczą pierwszej fazy; jej receipt zachował początkowy manifest audytowy.
- Correction scope/SHA/logs: `artifacts/audits/TASK-1004_CORRECTION_MANIFEST.json`; pierwotny manifest poprawek pozostaje zachowany. R2 PASS prowadził lead; commit prowadzi lead, bez integracji.

### Changed

- Istniejący GameCreate wymaga UUID idempotencji, pomija wybór formatu i domyślnie tworzy neutralne V3. Default, jawna opublikowana wersja i nowa rodzina z bazy korzystają z jednej rezerwacji. Brak default pozwala unassigned i zachowuje jawny status. Oczekiwane warunki nieeligible są zamkniętą whitelistą; uszkodzony kontrakt i infrastruktura kończą się błędem.
- Migracja0158 i frozen manifestv11 dodają trwały ledger tworzenia, immutable lineage forka i training family przypisania. Gra, MIGRATING, lifecycle, fork, head, event oraz receipt zapisują się przed pierwszym commitem; istniejące partycyjne checkpointy pozostają. Typowane Core na public tables przez tę samą connection i rolę aplikacyjną rozwiązują opisany wyżej hazard ORM/MIGRATING.
- Retry sprawdza canonical command/receipt przed wyborem aktualnego default, wraca do tej samej gry i wznawia provisioning. Zmienione pole pod tym kluczem, drugi klucz z tym kodem oraz replay usuniętego wyniku nie tworzą nowej gry.
- Fork jest pustą rodziną z immutable base/SHA, bez nowej wersji, skopiowanych wag, publikacji, etykiet i fikcyjnej oceny. Lineage zachowuje chronione referencje; przyszły TRAIN musi rozwiązać ich wyłączenia. Transfer source-games-only nie udaje oceny nowej gry. Jednorazowy jawny initial_transfer obsługuje pierwotnie unassigned; kolejne aktywacje wymagają dotychczasowego per-game proof. Omitted/evaluated canonical commands i historyczne SHA pozostają identyczne.
- Wszystkie trzy V3 blokują globalny symbol bootstrap przy nowych wyborach. Puste własne symbole blokują start; dwa własne aktywne kody włączają dotychczasowy scoped cold-start. Historyczne piny/replay i stara7 zachowane.
- Create i edycja V3 nie mają pickera formatu/profilu; klasyczna/stara7 edycja oraz szerokie GameUpdate zachowane. Advanced pokazuje rodzinę i skutek wyboru. Frontend zapisuje dokładny create command i klucz przed POST, odtwarza je po przeładowaniu i nie adoptuje gry po kodzie. Neutralny import używa tej samej prezentacji V3 co Mumie/777v2; zmiana gry odrzuca stare radio V1.1.
- Backend, OpenAPI, generowany klient, istniejący wrapper i test żądania stanowią jeden pion. Istniejące fixture'y GameCreate otrzymały wymagane klucze; dawne konfiguracje są nadal testowane przez GET/PATCH.

### Verification results

**Wyniki końcowe po jednej rundzie poprawek; zastępują liczby z fazy przed R1 poniżej.**

- Backend115 PASS,40.98s: `TASK-1004_R1_BACKEND_FINAL.log`. Izolowany PostgreSQL1 PASS,21.21s: `TASK-1004_R1_PG.log`; nowa granica recovery, restart i równoległość oraz owner/PID/DB/role cleanup potwierdzone. Bez danych operatora.
- Admin738 unit PASS,24 interakcje PASS,14 scoped recovery unit PASS: `TASK-1004_R1_ADMIN_ALL.log`, `TASK-1004_R1_UI_INTERACTION.log`, `TASK-1004_R1_UI_UNIT.log`. Pełny python:lint, scoped ESLint, typy Admina, OpenAPI, mapa i docs/diff PASS.
- Mypy worker/src+scripts502 pliki PASS. API397 plików ma wyłącznie dwa wcześniejsze błędy `schemas/source_lattice_geometry.py:36,38`, plik identyczny z bazowym HEAD. Pełna łączna komenda timeout100s nie jest PASS; własny PID43776 i potomkowie nie pozostali. Ograniczenie: `TASK-1004_R1_TYPECHECK_LIMITATION.json`. Bez napraw niezwiązanego kodu i bez deklaracji pełnej quality/build.
- [Claude R2](../../quality/TASK-1004_AUDIT_claude-fable-5-1.md): PASS, high, limit1200s, wykonany2026-10-15. Wszystkie P1-1/2/3 i P2-1–5 z [R1](../../quality/TASK-1004_AUDIT_claude-fable-5-1_R1.md) zamknięte; raporty pozostają bez zmian. P2-7 uporządkowano tym rozdzieleniem wyników historycznych i końcowych.
- P2-6 zaakceptowane ryzyko UX: walidacja przed repozytorium nie ma autorytatywnego dowodu braku rezerwacji, więc zachowuje pending zgodnie z D-549. Jawne potwierdzane archiwizowanie/porzucenie daje trwałą drogę odzyskania, bez ręcznego kasowania storage i bez usuwania możliwej rezerwacji. Dodatkowa walidacja pola może być osobnym ulepszeniem; po jednej rundzie poprawek nie rozszerzano kodu.
- Manifesty/SHA, logi i receipts: `artifacts/audits/TASK-1004_CORRECTION_MANIFEST.json`, `TASK-1004_R2_SCOPE.json`, `TASK-1004_AUDIT_DISPOSITION.json`. Kontrole zamknięcia dokumentów i staged zostaną zapisane przez leada przed commitem.

#### Wyniki historyczne przed poprawkami R1 — nie są wynikiem końcowym

- Nowy pion backendu: 13 PASS (`TASK-1004_BACKEND_NEW_FINAL.log`). Obejmuje rzeczywisty resolver blokujący unassigned, source-only transfer bez fikcyjnej oceny nowego UUID, późniejszy per-game gate, odrzucenie lineage pomijającej bazę, konflikt klucza/kodu oraz brak odtworzenia usuniętego wyniku. Początkowe błędy nowych fixture'ów manifestu i klasy wyjątku poprawiono bez osłabienia asercji.
- Łączny końcowy zestaw backendu:112 PASS,39.82s (`TASK-1004_BACKEND_FINAL.log`): new-game, registry/publication/activation, catalog API/domain, symbol snapshot/catalog binding, manifest/schema/head.
- Izolowany PostgreSQL: 1 PASS,34.03s (`TASK-1004_PG_ESCALATED.log`). Faktyczna rola aplikacyjna NOSUPERUSER/NOBYPASSRLS zapisuje katalog; owner służy wyłącznie DDL. Test obejmuje rollback po Core receipt INSERT przed pierwszym commitem, przerwanie po dwóch checkpointach, nowy interpreter i tę samą rezerwację, równoległy retry oraz pusty/własny katalog symboli. Fixture'y są syntetyczne, bez model inference ani rzeczywistych ocen jakości.
- Admin:30 testów jednostkowych PASS,20 interakcji PASS, osobny test rzeczywistego żądania klienta1 PASS. Logi: `TASK-1004_UI_0.log`, `TASK-1004_UI_SCOPED_0.log`, `TASK-1004_CLIENT_TEST.log`.
- Ruff format/check44 zmienionych plików Python PASS; Prettier zmienionych plików UI/testów PASS. Scoped ESLint PASS:0 błędów,1 istniejące ostrzeżenie `<img>` w panelu importu. Typy Admin PASS. Mypy3 nowych i16 istniejących modułów PASS; wcześniejszy łączny55s timeout zastąpiono tymi ograniczonymi grupami, nie uznano timeoutu za PASS. Odczyt procesu potwierdził brak pozostawionego mypy.
- Admin i Vision Lab OpenAPI oraz oba generated-client checks PASS. Sandbox TEMP zablokował rename klienta Vision Lab; identyczna kontrola poza sandboxem przeszła, bez zmiany konfiguracji produkcyjnej. Pytest/PostgreSQL także wymagały scoped escalated z powodu TEMP/Win10013; każda komenda miała limit, nowe procesy otrzymywały worktree PYTHONPATH i UTF-8.
- Mapa kodu zregenerowana i check PASS. Kontrole decyzji584/550/550, okna State97221B i git diff --check PASS. Dokładny manifest ścieżek/SHA256 oraz logów: `artifacts/audits/TASK-1004_AUDIT_READY_MANIFEST.json`; root-owned metadata są z niego wyłączone, poza wyraźnie oznaczoną współdzieloną sekcją State.

### Test data and cleanup receipts

- Dokładnie własna baza: `game_predictor_task1004_1d748b0207be_test`; rola: `task1004_1d748b0207be`; właściciel `game_predictor`. Python fixture PID43444; fresh interpreter PID29932.
- `artifacts/audits/TASK-1004_PG_RECEIPT.json`: phase=cleaned, ownerBeforeCleanup=game_predictor, pidsBeforeCleanup=[], databaseRemaining=0, roleRemaining=0, operatorDatabaseChanged=false. Zakończone procesy testowe nie są usługami i nie pozostawiono ich w tle.
- Nie wykonano nowego backupu/snapshotu, operator migration, rzeczywistych gier/publication/default/activation, usług API/Admin, GPU, inferencji, treningu ani benchmarku.

### Not completed / limitations

- Audyt i jedna runda poprawek zakończone: R2 PASS. Osobny commit prowadzi lead; integracja wymaga końcowej akceptacji całego planu. P2-6 i ograniczenie pełnego mypy jawnie opisano powyżej.
- Migracja0158 nie została wykonana na bazie operatora. Startup wymaga nowej głowy dopiero po świadomej migracji operatora; żadna usługa nie została uruchomiona ani zrestartowana.
- Nie uruchomiono pełnego monorepo quality/build ani wszystkich adaptowanych integracyjnych fixture'ów. Wykonano skoncentrowane kontrole zmienionego pionu i rzeczywisty isolated PostgreSQL. Przyszłe TASK-1002/0995 muszą zastosować protected-source lineage przed TRAIN;1004 zapisuje referencje i guard rejestracji, nie wykonuje treningu.
- Pozostały globalny quality-panel/classic-readiness cleanup należy do TASK-1011. Nie rozszerzano tego zakresu.

### Documentation updates

- Właścicielskie wymagania Admin/symboli oraz architektura API, modelu danych, storage ownership i symbol selection opisują wdrożony kontrakt, Core hazard i granicę dwóch własnych kodów. Aktualizowano tylko własną sekcję1004 State; README, plan, D-549 i metadata0998 pozostają własnością leada.
- Root docs: po audycie potrzebują wyłącznie statusu/wyników taska w planie i README oraz późniejszego pełnego hash commita. D-549 nie wymaga nowej decyzji produktowej.

### Recommended next task

- TASK-1011 po zakończeniu audytu i zapisie osobnego commita1004 przez leada.
