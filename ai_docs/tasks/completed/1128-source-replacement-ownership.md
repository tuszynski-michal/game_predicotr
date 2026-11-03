---
title: Strażnicy własności i historii wymiany źródeł
status: done
last_updated: 2026-11-03
---

# TASK-1128 — Strażnicy własności i historii wymiany źródeł

## Status

`done`

## Goal

Zablokować bieżące użycie wycofanych źródeł i przejęcie rezerwacji bez dokładnego bindingu, zachowując historię oraz wszystkie referencjonowane dane.

## Dependencies / entry conditions

B1 ukończone: c4436c79, zapis hasha 8b361ca4; czysty worktree, schemat 0174/manifest v21. Cały plan, koszt i audyt Opus 5.5 zatwierdzone. Implementacja bez danych operatora, usług, merge ani push.

## Recommended execution

gpt-6-astra / high; niezależny claude-opus-5-5 / high. Niedostępność modelu lub sprzeczność wymagań blokuje zależny zakres.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/tasks/completed/1127-source-replacement-manifest.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-579--manifest-wymiany-źródła-z-zachowaniem-historii`

## Scope

- Wspólna ochrona retired source/SHA, rezerwacji i current review w API, workerze, odbudowach oraz treningu.
- Pierwszeństwo reservation przed canonical, dokładny binding i atomowe związanie całego zdjęcia.
- Kodowane blokery retencji w preview i execute, także planned/restored i wszystkie aliasy; zamknięcie P2-2 audytu B1.
- Historia frozen i odczyty audytowe pozostają; bieżące listy, liczniki, bulk, geometria, reinferencja i nowe kohorty wykluczają niedozwolone źródła.

## Out of scope

Wycofywanie danych operatora, endpoint retirement, pełny pion staging/import C2, trening, aktywacja, usługi i scalenie.

## Acceptance criteria

- [x] Retired sprawdzane przed canonical, również po restored i przy późnym seq; wcześniejsza historia pozostaje bez zmian.
- [x] Reservation dopuszcza tylko exact server binding; normalny import i override nie przejmują luki.
- [x] Provisional INSERT/flush nie łamie FK i nie daje widoczności; kompletne zdjęcie wiąże wszystkie sloty atomowo.
- [x] Current reads, counts, search incremental/rebuild, bulk start/execute i recovery mają zgodne guardy.
- [x] Nowe użycie treningowe blokuje retired, w tym photo-only SQL i freeze; historyczny frozen odczyt pozostaje.
- [x] Cleanup/reset/release/GC/cropy/staging odmawiają przed side effects, także dla aliasów i cross-game cropów.
- [x] Regresje zwykłego reject canonical i legacy fallbacku pozostają zielone.
- [x] Testy, scoped lint/typecheck, docs/mapa, audyt i commit rozliczone.

## Technical notes

Bootstrap zaakceptowany przez koordynatora w ramach zatwierdzonego planu: serwerowy dowód game/batch/entry/job/source/newSHA/range/revision pozwala utworzyć i flushować robocze review przy reserved. Nieodroczony FK otrzymuje review ID dopiero po INSERT. Provisional review nie jest current i nie trafia do list/count/search/bulk/canonical. Finalizator sprawdza komplet zdjęcia i atomowo ustawia wszystkie pending_bound przed synchronizacją projekcji; niepełna geometria pozostaje robocza. CLAIM_RESERVED oznacza zgodę przygotowania, a nie finalne prawo canonical. Bez publicznego force. C2 dostarczy pełne serwerowe admission.

Wspólny lock pozostaje game ownership, sequence rosnąco, source rosnąco, potem board/review. Retention zależy od referencji, nie fazy batcha. Legacy wyszukiwarka zachowuje fallback accepted/corrected, gdy brak canonical i replacement go nie wyklucza; rebuild dostaje tę samą kolejność wyboru.

Dokładny receipt poprzedza retired guard, konflikt key/body pozostaje błędem. SQL recording `bind_existing_report` odtwarza istniejący receipt przez dotychczasowy dispatch; nowy register/validate podlega fence. Photo-only register nie ma własnego klucza; replay nadrzędnego freeze jest atomowy. Same-SHA source poza exact attested alias group blokuje preview/create (`SOURCE_REPLACEMENT_SHA_SCOPE_CONFLICT`), aby tombstone nie ukrył niewybranego zakresu. Retencja obejmuje również wspólną kohortę/model przy cleanupie innego zdjęcia. GC nie dopuszcza namespace modeli ani datasetów do usuwania.

Implementacja geometry i selection została delegowana przez koordynatora równolegle wykonawcom gpt-6-astra/high, z rozłącznymi plikami i jednym wspólnym audytem B2a. TestClient wymagał require_escalated; bez niego własny test zakończył się timeoutem, bez usług operatora. Krótkie izolowane katalogi testowe omijają Windows MAX_PATH.

## Expected files

Nowe: storage/source_replacement_guards.py, storage/source_replacement_binding.py, odpowiednie testy i migracja funkcji ochronnych. Istniejące: domain/sequence_takeover.py; storage/pending_sequence_ownership.py, image_review_repository.py, board_search_projection_repository.py, image_symbol_review_repository.py, cleanup_repository.py, grid_correction_split.py, grid_training_cohort_currentness.py; pozostałe konsumenci geometry/reinference/training/GC oraz worker pipeline_store.py/source_crop.py. Wymagania, API/schema/client/UI dla metadata historii, mapa kodu i ten plan.

## Test cases

Reservation z canonical; obca gra/batch/entry/job/SHA/review; retired bez seq oraz po restored; bootstrap dwóch slotów, rollback, retry/lost response; niewidoczne provisional; parity fallbacku; wcześniej zamrożony bulk; reinferencja i backfill po restarcie; SQL register_cohort_use oraz freeze po retirement; historyczny frozen GET; blokada cleanup przed detach i plikami; wspólny crop dwóch gier.

## Verification

Cwd worktree, Python `D:/game_predicotr/.venv/Scripts/python.exe`. Bezpośredni pytest zmienionych pionów z timeoutem 120 s, następnie ruff/mypy; izolowane PostgreSQL z kontrolą name/OID, bez bazy operatora. Audyt Opus 5.5/high 480 s (zewnętrzny limit 600 s). Code-map i cztery checkery docs root Python. Wyniki będą w Outcome.

## Risks / open questions

Brak blokującego pytania. Operacyjny retirement/import mają osobne bramki i dalsze taski. Istniejące kolizje numerów wersji pozostają; kolejny patch wynika z bieżącego brancha zgodnie z AGENTS.

## Outcome

Commit: v1.7.525 / `a41f8d8d18e9dce4a8f31afe9e145886c1404e41`.

Wdrożono wspólne predykaty ID/SHA/reservation/current i guardy API/worker. Migracja 0175 dodaje funkcje ochronne, bez zmian danych operatora ani frozen manifestu v21. Exclusion set powstaje od małych tabel retired/slots; zwykłe odczyty bez replacement nie skanują geometrii. Legacy accepted/corrected fallback pozostaje, direct read od razu ukrywa stale fastdoc. Bootstrap dwóch slotów działa przed FK, finalny binding całego zdjęcia jest atomowy i idempotentny; roboczy dostęp nie daje current visibility. Normalny reject/revert i późne przypisanie sekwencji zachowują kontrakt.

P2-2 audytu B1 zamknięte: coded retention preview/execute przed side effects, planned/gap_open/restored i każdy alias. Retention obejmuje nowe robocze source także po zwolnieniu slotów. Istniejący deletion scope chroni wspólne kohorty oraz nieaktywne modele, których usunięcie skasowałoby prediction history innego retained zdjęcia. Cleanup nie usuwa public grid_model_versions ani ich ancestry; GC ma zamknięty namespace bez modeli/datasetów. Recovery/finalize po commicie odczytuje receipt i inventory oraz trzyma jeden bulk SHARED fence/session per game przez usunięcie; chroniona kwarantanna pozostaje, zwykły odczyt może trwać. Restore nie nadpisuje plików. Cross-game crop registry odróżnia game+source ID.

Same SHA z innym lub nieznanym zakresem blokuje planned preview/create; operacja nie rozszerza zakresu. B2b ma użyć świeżego preview również przed retirement. Exact recording receipt przechodzi do istniejącego dispatch z walidacją body; nowe validate/register są blokowane. Photo-only register nie ma osobnego receipt, a nadrzędny freeze zachowuje swój replay. Nowa prepare kohorta filtruje current przed count/insert i pod właściwymi locks.

Selection ma pełny backend/OpenAPI/generated/wrapper/UI: reserved_gap/pending_bound/history_only, sourceState i selectable, link do istniejącego batch GET oraz history asset. Provisional pozostaje poza standardową kolejką. Operatorowy admission/import i pion UI roboczej geometrii pozostają C2.

### Verification results

- Wspólny PostgreSQL po 0175: 8 PASS / 75,65 s — `test_source_replacement_guards_postgres.py`, `test_grid_correction_registry_postgres.py`, `test_source_replacement_geometry_guards_postgres.py` (5), `test_source_replacement_selection_postgres.py` (1). Own disposable DB, name/OID guard, migracje do head, nowe sesje/restart/replay, rollback pomiędzy bindingami, obcy proof, niepełny zakres, SHA ambiguity, stale fastdocs, inactive model/prediction retention i SQL use/replay. Dodatkowy core PG po artifact path guard: 1 PASS / 17,83 s.
- Wspólne guardy/trening/count/bulk/backfill/cleanup/GC: 319 PASS / 21,61 s. Po końcowej integracji takeover/cleanup/GC: 55 PASS / 3,25 s; cohort core/storage/request + recovery: 95 PASS / 3,80 s. Te przebiegi częściowo powtarzają wcześniejsze testy, nie są sumą unikalnych przypadków.
- Paczka geometry: 67 unit/application/repository PASS, 8 sąsiednich PASS, 2 page replay/reapply PASS (jeden wspólny z poprzednim przebiegiem); PostgreSQL ujęty we wspólnym przebiegu. Paczka recovery: 26 cleanup PASS (część ponownie w 95).
- Paczka selection: HTTP quality 5 PASS, history assets 2 PASS, Admin interaction + wrapper request 4 PASS, Reviewer regression 2 PASS; OpenAPI freshness, scoped TS Admin/Reviewer, ESLint 0 errors (istniejący img warning). PG ujęty wyżej.
- Ruff format/check wszystkich 61 zmienionych plików Python PASS; scoped mypy 39 modułów PASS (`--follow-imports=skip --disable-error-code=no-any-return`). Geometry dodatkowo scoped 11+2 moduły PASS; selection 3 PASS. Nie jest to pełny backend typecheck. Main recovery sprawdzony przez wykonawcę z pominięciem zależnych dekoratorów FastAPI; pełny main typecheck nie był deklarowany.
- Krótkie katalogi testowe w `D:/game_predicotr/artifacts/t1128-*`; pytest przez root `.venv` z timeout120. PostgreSQL/HTTP require_escalated z powodu socket10013/TestClient hang w ograniczonym środowisku. Własne przerwane procesy sprawdzone; brak pozostawionych Pythonów. Test fixture wymagał korekt job status/shape configuration/frozen lifecycle; faktyczna kolizja aliasu PL/pgSQL `m` została naprawiona i wspólny PG przeszedł.
- Code-map wygenerowana. Cztery checkery docs PASS: decision links, current-state window, startup budgets, skill mirrors. R1 audytu Opus5.5/high PASS, modelUsage potwierdzone `claude-opus-5-5`, exit0, bez P0/P1; raport `ai_docs/quality/TASK-1128_AUDIT_claude-opus-5-5.md`.

### Audyt i jedna runda poprawek

R1 jawnie zamknął P2-2 z B1. Uwagi B2a: P2-1 i P2-2 pozostają obowiązkowymi kryteriami C2 przed udostępnieniem admission/restored (test korekty provisional i braku orphan visibility po zwolnieniu slotów); zapisano je w zaakceptowanym planie. B2b nie wprowadza restore. P2-3 naprawiono: każdy SQL anchor migracji wymaga dokładnie jednego wystąpienia, inaczej upgrade odmawia; trzy testy missing/ambiguous/single. P2-4 zaakceptowany przez koordynatora jako ograniczenie dostępności: shared lock/session na grę może wyczerpać pulę, co kończy się odmową bez usuwania; bez benchmarku poza zakresem. P2-5 zachowuje kompatybilny standalone filesystem API; jedyny produkcyjny konstruktor `services/api/src/game_predictor_api/main.py:979` zawsze wstrzykuje bulk guard, pozostałe callsites są testowe. Ryzyko przyszłego pominięcia callbacku opisane, brak produkcyjnej ścieżki bez ochrony.

W tej samej jedynej rundzie potwierdzono rzeczywistym testem PG rozbieżność aliasu reserved newSHA: source_current=False, current_review=True dla innego source/job/seq. Test t1128-32 odtworzył błąd. Migracja 0175 rozszerza mały affected_sources set o aliasy reserved SHA w tej samej grze; nowe źródło nie dostaje prawa current przez inny numer. Po poprawce ponownie wszystkie 8 PG PASS / 73,37 s; późniejszy błąd unit fixture `no anchor` poprawiono na `absent`, końcowy przebieg unit migration+guards 25 PASS / 3,34 s. Ruff zmienionych części PASS. Celowany R2 Opus5.5/high PASS, exit0 i modelUsage `claude-opus-5-5`; alias invariant oraz P2-3 zamknięte, rozliczenie pozostałych P2 przyjęte, brak otwartych P0/P1/P2.

C2 ma dodatkowo obowiązkowy admission preflight nowego SHA pod lockiem: obce istniejące current źródło z innym/nieznanym zakresem odmawia SHA_SCOPE_CONFLICT przed reservation, aby globalny SHA fence nie ukrył niewybranego zakresu. Dopuszczony tylko exact entry/range alias i własny replay; regresja zakresu 1200 bez mutacji jest zapisana w planie. To handoff, bez operatorowego admission w B2a.

Nie uruchamiano usług, treningów, operatorowego importu/retirement/cleanup/GC ani migracji bazy operatora. Nie wykonano merge/push. Wdrożenie później wymaga migracji 0175 przez upoważniony workflow operatora. B2b/C2 dostarczają komendy operacyjne; obecny task daje trwałe guardy/prymitywy i ich testy.
