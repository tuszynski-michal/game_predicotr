---
title: TASK-0994 — Rejestr rodzin, wersji i przypisań
status: done
last_updated: 2026-10-15
---

# TASK-0994 — Rejestr rodzin, wersji i przypisań

## Status

`done`

## Goal

Zastąpić statyczny wybór wersji trwałym katalogiem.

## Context

Task jest częścią zaakceptowanej rewizji 6. Rejestr i migracja przypisań. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1014 done, v1.7.372 / `b11cdb19d81711fa801157c8effb3fc78863e46c`, statyczny Claude PASS bez P0/P1 i rozliczone P2. Checkpointy obu baz zabezpieczone na D i odczytane z nowego procesu. Aktualne Alembic heads potwierdzić przed projektowaniem migracji.

- D-549 przyjęta przed TASK-0994 na podstawie zleconej rewizji6 i wcześniejszych wyborów operatora; D-550/D-552 accepted. D-548/D-551 dotyczą odrębnych późniejszych pionów. Bez migracji operatora, nowych aktywacji lub wyboru default; izolowana baza testowa dozwolona.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. migracja i zgodność istniejących gier.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [DATA_MODEL](../../architecture/DATA_MODEL.md).
- [API_CONTRACT](../../architecture/API_CONTRACT.md).
- Zakres odczytu uzupełniający z planu: DATA_MODEL, API_CONTRACT, D-527/D-544.

- [D-527](../../process/decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-544](../../process/decisions/DECISION_LOG_2026.md#d-544--nowe-gry-777-importują-przez-v3-z-profilem-grid_profile_777_v2) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Addytywne encje rodzin, wersji, przypisań i zdarzeń.
- Zarejestrować bazy historyczne bez fikcyjnych kohort i PASS.
- Przypisania istniejących V3 odzwierciedlają dotychczasowe wersje.

## Out of scope

- Bez aktywacji nowych modeli i migracji bazy operatora.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Addytywny enum/CHECK dopuszcza `neural_grid_v3` i wszystkie stare wartości; istniejące gry nie są przepisywane.
- [x] Migracja zachowuje modele obu gier, stara 777 nie otrzymuje neural assignment.
- [x] Brak artefaktu blokuje udostępnienie.
- [x] Powtórna rejestracja jest idempotentna.
- [x] Gra nie odczytuje cudzych danych przez błędny zakres.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu (brak werdyktu audytu, jawny wyjątek timeout).


## Technical notes

Kontrakty ustalono i zapisano przed kodowaniem 2026-10-15. Alembic `heads` potwierdza `0155_historical_grid_acceptance`. Nowa proponowana migracja `0156_grid_model_registry` rozszerza istniejący CHECK `games` o `neural_grid_v3`, zachowuje NULL i cztery stare wartości oraz nie aktualizuje żadnego formatu gry.

### Własność i moduły

- `domain/grid_model_registry.py`: proponowane `GridModelRegistryError`, kanoniczny descriptor/sha256, walidacja manifestu oraz deterministyczne deskryptory dwóch historycznych baz z niezmiennych `GRID_ENGINE_PROFILES`. Deskryptor przypina family/version UUID, topologię screen 3x3 i board 5x3, capabilities screen/grid, model/bundle/preprocessing/decoding contract, bazę, kohortę nullable, pochodzenie i historyczne raporty. Historyczna baza ma `historical_baseline`, kandydat `not_evaluated`; nie powstaje nowa ocena PASS ani kohorta.
- `storage/grid_model_registry_models.py`: proponowane SQLAlchemy encje `GridModelFamilyModel`, `GridModelVersionModel`, `GridModelRegistrationReceiptModel`, `GridModelVersionEventModel`, `GameGridModelAssignmentModel`, `GameGridModelAssignmentEventModel`. Wszystkie mają jawne schema `public`: rodziny/wersje/receipty/zdarzenia wersji są shared control, assignment i jego zdarzenia są catalog/control jak istniejący `games`. Nie zawierają zdjęć, etykiet, symboli, sekwencji ani danych importu. FK do wersji są RESTRICT; assignment oraz jego events mają game FK CASCADE zgodnie z istniejącym DELETE gry (zdarzenie wolno usunąć wyłącznie w kaskadzie po usunięciu parent gry), game assignment ma PK game_id i dodatnią rewizję; event PK(game_id,id) i UNIQUE(game_id,idempotency_key). Wersja ma UNIQUE(family_id,version), checksum canonical descriptor i nullable FK bazy.
- Proponowany frozen `game_data_v2_manifest_v9.py` dziedziczy v8 bez zmiany listy GAME_TABLES/provisioningu/partycji; dopisuje wyłącznie klasyfikację powyższych public tabel. Migracja zmienia wersję control registry i revision, nie dane gry. `catalog_repository.py`, `game_partition_lifecycle.py`, `game_storage_routing.py` importują v9, readiness wymaga head0156. V1–V8 pozostają bez zmian.
- `storage/grid_model_registry.py`: proponowane `SqlAlchemyGridModelRegistryRepository` i `GridModelArtifactInspector`. Repository używa plain Session, zawsze jawne public ORM i game_id predicate, nigdy globalnego katalogu przez GameStorageRouter. Sesja z przypiętą inną grą odmawia `GRID_MODEL_GAME_SCOPE_CONFLICT`; GET sprawdza istnienie konkretnej gry i filtruje jej assignment/events. Globalny GET nie zwraca przypisań innych gier.
- `application/grid_model_registry.py`: proponowane `GridModelRegistryService`, interfejs repozytorium i inspector. Rejestracja tworzy immutable rodzinę/wersję/receipt/zdarzenie atomowo; odczyt i rejestracja weryfikują niezmienność sha oraz pliki. Nie publikuje, nie aktywuje i nie wybiera default.
- `schemas/grid_model_registry.py`, `api/grid_model_registry.py`, `main.create_app`: typowane Admin GET katalogu i GET assignment konkretnej gry oraz POST rejestracji wersji. Wpięcie przez istniejącą fabrykę create_app, z injectable dependency jak pozostałe piony. `packages/admin-api-client/openapi/openapi.json`, generated oraz wrapper `src/index.ts` i `test/client.test.mjs` domykają kontrakt.

### Manifest i dostępność

Manifest ma jawny `schemaVersion`, family/version, `modelKind=neural_grid`, model/bundle version, preprocessing/decoding policy, topology/capabilities, baseVersionId, provenance, historyczne wyniki, managedDirectory, inferenceManifest i pliki z SHA256/sizeBytes. Zamknięty typed descriptor wyklucza nieznane pola. SHA256 jest liczona z canonical UTF-8 JSON (sort keys, compact separators, no NaN); immutable JSON string unika mutowalnych zagnieżdżeń domeny. InferenceManifest musi zgadzać się z version/model/bundle/provenance i każdym plikiem. Historyczne inferenceManifest pozostają dokładnie dotychczasowe; plik `manifest.json` musi mieć równoważną treść, wszystkie pliki wymagają zgodnego rozmiaru i SHA. Descriptor trainingArtifacts przypina checkpoint.pt, weights.pt, bundle.json i preset.json z rozmiarami/SHA; inspector kontroluje pliki training-base i sumę/tożsamość istniejącego receipt1014. Ich integralność jest warunkiem dostępności rejestru, nie oceną nowej bramki. Manifest inference jest zamkniętym GridInferenceManifest (extra forbid), więc nie przechowuje dowolnych pól danych gry. Nie tworzymy ani nie modyfikujemy modelowych plików.

Ścieżka względna jest wyłącznie POSIX pod `models/grid-engine`, bez `..`, absolutnych ścieżek i ucieczki po resolve (symlink/junction). Brak/niezgodność manifestu lub pliku zwraca niedostępność w GET; POST odmawia 409 `GRID_MODEL_ARTIFACT_UNAVAILABLE` przed zapisem. Nie stosujemy fallbacku do innej rodziny/wagi. Weryfikacja plików jest odczytem bez ładowania ONNX/GPU. Zgodność struktury/zamrożonych kontraktów nie jest runtime inference ani publikacją.

### Transakcje, idempotencja i migracja

POST przyjmuje UUID idempotencyKey i pełny descriptor. Kolejność: walidacja descriptor/hash, transakcyjna advisory lock wspólnego zakresu katalogu z lock_timeout5s (jedna blokada; brak cykli), receipt lookup, conflict check, sprawdzenie rodziny/bazy i identycznej wersji, integralność artefaktów, INSERT rodzina jeśli brak, INSERT wersja jeśli brak, INSERT registration event tylko dla nowej wersji, INSERT receipt, flush; commit w dependency. W PG lock serializuje również dwa różne klucze próbujące ten sam family/version; unique constraints bronią zapisu. Retry tej samej treści/key zwraca tę samą wersję bez duplikacji, odmienna treść/key daje 409 `GRID_MODEL_IDEMPOTENCY_CONFLICT`; odmienna treść pod family/version daje 409 `GRID_MODEL_VERSION_CONFLICT`. Nowy klucz z identyczną immutable wersją tworzy tylko receipt. Brak zgodnej rodziny/bazy daje 409; FK nie pozwala na brak podstawy. Wyjątek cofa wszystkie zapisy; awaria po commit odzyskuje wynik z receipt. Retry nie ukrywa później utraconego pliku jako dostępnego. Infrastrukturalny błąd nie staje się sukcesem; klient może ponowić ten sam command/key po usunięciu przyczyny. Brak automatycznej pętli retry.

Migracja bierze control lock locations i sprawdza brak trwającego lifecycle oraz oczekiwaną wersję v8. Rejestruje dwie osobne historyczne rodziny/version z UUID5 i istniejącymi manifestami/raportami, bez filesystem lookup w migracji i bez fikcyjnych kohort/PASS. Przypisuje istniejące profile V3 dokładnie ich dotychczasowym wersjom; jawnie wyklucza code `7` nawet przy błędnym profilu. Zapisuje tylko zdarzenie `historical_assignment` i nie przepisuje formatów/cropów. Alembic revision zapewnia jednokrotne wykonanie; deterministyczne UUID i UNIQUE nie nadpisują immutable danych. Downgrade odmawia utraty jakiejkolwiek historii (`GRID_MODEL_REGISTRY_DOWNGRADE_REFUSED`), nie obiecuje destrukcyjnego rollbacku. Triggery blokują UPDATE/DELETE immutable family/version/receipt/events; wyjątek DELETE assignment event dotyczy wyłącznie kaskady po usunięciu gry, shared wersje pozostają; assignment pozostaje CAS-ready z revision, jego przyszłe mutacje należą do0998.

### Ochrona okresu przejściowego i testy

Do TASK-1012 neutralny `neural_grid_v3` jest kontrolowanym `GRID_MODEL_DYNAMIC_ROUTING_REQUIRED`, nigdy klasycznym fallbackiem. `neural_import_profile` i `grid_engine_profile_for` odmawiają tego nierozwiązanego formatu; snapshot resolver przekazuje kontrolowany JobConflictError przed wyborem klasycznej ścieżki. Wszystkie stare profile i stare snapshoty zachowują zachowanie. Addytywna etykieta exhaustive frontend Record służy wyłącznie odczytowi. game-catalog.tsx filtruje neural_grid_v3 z Object.entries listy wyboru; cztery stare opcje i domyślny requires_clarification pozostają. Filtr znika dopiero w pionie1004/1011, który zastępuje ten wybór.

Testy nowego pionu obejmują domain manifest hash/topology, brak/uszkodzenie/traversal pliku, idempotentne ponowienie po nowej sesji, zmieniony key/payload i family/version, rollback po częściowym INSERT, obcy game scope, rzeczywiste HTTP POST/GET ze statusem/błędem i wrapper request. Isolated PG: upgrade0155→0156, obie V3 i old777, niezmienione formaty i wcześniejsze partition definitions/data, classifier v9, immutable SQL triggers, NOBYPASSRLS app role i jawny game predicate. Disposable test fixture zapisuje własną nazwę/owner/PID i potwierdza brak obcych sessions przed cleanupem; usuwa wyłącznie własne DB/role, receipt w artifacts/audits. Żadnej migracji operatora, backupu, usługi, treningu ani aktywacji.

## Expected files

- Istniejące: [models.py](../../../services/api/src/game_predictor_api/storage/models.py) — encje i relacje magazynu.
- Pozostały zakres wskazany w zaakceptowanym planie: `services/api/src/game_predictor_api/domain/grid_engine_profiles.py`; nowe proponowane `services/api/src/game_predictor_api/domain/grid_model_registry.py`, `services/api/src/game_predictor_api/application/grid_model_registry.py`, `services/api/src/game_predictor_api/storage/grid_model_registry.py`, schema/router i migracja.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_grid_model_registry.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Migracja zachowuje modele obu gier, stara 777 nie otrzymuje neural assignment.
- Brak artefaktu blokuje udostępnienie.
- Powtórna rejestracja jest idempotentna.
- Gra nie odczytuje cudzych danych przez błędny zakres.

## Verification

Zakres: API, MIG, OpenAPI, MAP, DOC.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run openapi:check
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_catalog_domain.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez aktywacji nowych modeli i migracji bazy operatora.

## Outcome

### Execution phase

- Faza bieżąca: done, korekta P1 zamknięta przez Claude high PASS w rundzie2; oczekiwanie na osobny commit poprawki i końcową integrację całego planu. Historyczne fazy limitu i timeout zapisano poniżej.
- Original base v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`; zatwierdzony upstream main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d`.
- Baza taska v1.7.372 / `b11cdb19d81711fa801157c8effb3fc78863e46c`; branch `codex/v3-grid-fine-tuning`, worktree `D:/game_predicotr/worktrees/v3-grid-fine-tuning`.
- Technical notes zapisano przed kodem. Doprecyzowania CASCADE przy istniejącym usuwaniu gry, typed inferenceManifest, trainingArtifacts/receipt i przejściowego filtra UI uzgodniono z leadem w zakresie0994.
- Commit nieutworzony. Audyt wymagany `claude-fable-5-1/high`, brak raportu nie jest PASS. Dokładne pliki, komendy, wyniki i nieudane próby: `artifacts/audits/TASK-0994_SCOPE.json`.

### Changed

- Migracja0156: public immutable family/version/registration receipt/events oraz public catalog assignment/events; addytywny CHECK neural_grid_v3. Frozen JSON baseline z canonical SHA rejestruje rzeczywiste dwie bazy/raporty, bez kohort/PASS; istniejące V3 zachowują dokładną wersję, code7 pozostaje unassigned. Żaden format gry nie jest przepisywany.
- Manifestv9 dziedziczy identyczne game tables/partycje i provisioning/deletion lists z v8. Trzy istniejące storage entrypoints/readiness wymagają nowego head; locations zmieniają tylko control metadata version/revision.
- Atomowa rejestracja pod advisory lock z limitem5s i receipt hash/key. Restart/utrata odpowiedzi nie dubluje wersji/events. Konflikty family/version/key mają409. SQL trigger broni historii; dotychczasowy lifecycle usuwania gry kaskadowo usuwa tylko jej assignment/events, globalna historia pozostaje.
- Zamknięte descriptor/inferenceManifest pinują topology/capabilities/model/bundle/preprocessing/decoding/base/provenance oraz SHA/size inference/trainingArtifacts. Inspector kontroluje bezpieczne ścieżki i receipt1014, bez Torch/ONNX/GPU. Brak/uszkodzenie pliku blokuje rejestrację i daje niedostępność zamiast fallbacku.
- Istniejąca fabryka create_app dostarcza Admin catalogue GET/POST i scoped game assignment GET. OpenAPI/generated/wrapper/request tests stanowią spójny pion. Stary statyczny GET i snapshoty zachowane.
- Neutralny enum do1012 odmawia klasycznego fallbacku kodem GRID_MODEL_DYNAMIC_ROUTING_REQUIRED. UI ma label do odczytu; zachowuje stare cztery opcje i wcześniejszy default. Nie dodano wyboru default ani aktywacji.

### Verification results

Każdy subprocess miał twardy timeout20–110s. Pytest i nowy proces importują services/api/src tego worktree; junction .venv dostarcza tylko interpreter/zależności. Bez service control.

- API/REG: registry + stary profile suite19 PASS (unit6); wcześniejsze catalog/schema25 PASS (unit5); skoncentrowane retry/family conflict/invalid receipt2 PASS (unit8), closed domain/historical descriptor2 PASS (domain-final). HTTP wykonał POST/GET, assignment własnej gry i obcy unassigned game, missing game404, extra game field422, utratę pliku/retry409.
- MIG: izolowany PostgreSQL, head0155→0156. PG4 PASS15.58s: v8 partycja i wiersz zachowane, oba modele, old7 unassigned, neutral CHECK, NOBYPASSRLS role, scope, immutable SQL, lifecycle.run_next, retry nowej sesji i receipt-failure rollback. Końcowy PG test PASS15.19s: pełne definicje kolumn/constraints/index/RLS mają identyczny SHA ba1337f7964267a8b02fd4936c8eca6cc9482084f5b0f0ab24cb81057ae0944a przed/po; szczegóły w Scope/receipt.
- Cleanup receipt `artifacts/audits/TASK-0994_PG_RECEIPT.json`: wyłącznie własna DB/role, owner sprawdzony przed usunięciem, brak pozostałych PID, DB0/role0. Żadnej migracji operatora.
- Nowy hash-only proces sprawdził oba rzeczywiste managed baselines na D: AVAILABLE/AVAILABLE, także checkpoint/weights/receipt. Dowód `TASK-0994_BASELINE_INTEGRITY.json`; bez inference i zmian plików.
- Ruff wszystkich zmienionych Pythonów PASS. Scoped mypy --follow-imports=silent:8 plików PASS; po ostatniej walidacji closed descriptor dodatkowy domain-final1 PASS. Szerszy mypy napotkał istniejące source_lattice_geometry.py36/38 i timeout110s; poza zakresem.
- Klient TypeScript build i rzeczywisty wrapper request1 PASS. Admin typecheck (next typegen+tsc) PASS; scoped ESLint2 modułów PASS po eskalacji. UI17 wcześniejszych cases PASS, zmieniony label/classifier1 PASS oraz kontrakt filtra1 PASS.
- Admin OpenAPI i generated check PASS. Umbrella openapi:check zatrzymał się na VisionLab sandbox TEMP EPERM rename; osobny VisionLab OpenAPI/generated check z eskalacją PASS. Umbrella nie jest raportowany jako PASS.
- Code map wygenerowano; map:check i git diff --check PASS. Końcowy docs:check i Scope rozliczają przekazanie.

### Failed / corrected attempts

- Pierwszy sandbox unit run bez odczytanego końcowego wyniku (nie PASS), z limitem110s; brak własnych procesów po zakończeniu. HTTP dalej bounded require_escalated.
- Unit2: Ruff usunął niejawne reexports v9; naprawione __all__. Unit3:6 PASS/2 failures (SQLite UUID binding i asercja JobConflictError.code), naprawione.
- Unit5:42 PASS/2 failures (testowy import text, stara enum assertion). Naprawione i zweryfikowane unit6 19 PASS.
- PG1: CRLF/LF checksum frozen JSON; naprawiona canonical content SHA. PG3: prawidłowy409 kolizji familyCode zamiast planowanej awarii receipt; rollback fixture otrzymał niezależny code. PG4 PASS, cleanup0/0.
- Scoped mypy: iteracja po object w historycznych files, naprawiona typowana projekcja version.files; następnie8 PASS.
- UI: neutralny fallback description błędnie klasyfikował format jako profil. Description usunięto, label zachowano; focused case PASS. ESLint: błędny względny moduł, potem sandbox timeout50s; poprawny absolutny root node_modules i eskalacja dały PASS. Żadnych produkcyjnych obejść sandboxa.

### Not completed

- Formalny audit, ewentualna jedna runda poprawek, stage/commit i zamknięcie należą do leada. Task nie jest done ani w completed.
- Nie wykonano operator DB migration/data writes, backupu, cleanupu danych, start/stop/restart usług, treningu/inference/GPU, publication/activation/default, nowego game workflow, push ani integracji/wdrożenia.
- Nie uruchomiono całego quality/build ani benchmarków. Szerszy mypy ma niezwiązane ograniczenie opisane wyżej; zmienione moduły scoped są zielone.

### Documentation updates

DATA_MODEL/API_CONTRACT/GAME_DATA_V2_OWNERSHIP i istniejący LOCAL_OPERATION_GUIDE opisują schemat, własność, immutable guards, idempotencję, artifact states, downgrade refusal i osobną migrację operatora. CODE_MAP/CODE_MAP_SYMBOLS zregenerowane. CURRENT_STATE wykonawca zmienił wyłącznie w sekcji0994. Root utrzymuje README/plan/decision logs i Outcome1014.

### Definition of Done / accepted plan

Pięć implementacyjnych kryteriów spełniono: enum/CHECK, historyczne przypisania, fail-closed artefakty, idempotencja i zakres gry. Pion backend/OpenAPI/generated/wrapper/HTTP jest sprawdzony. Własność, restart/utrata odpowiedzi/rollback i existing game deletion mają testy. Sekwencje, symbole i cropy nie są zmieniane. Dokumentacja/wyniki zapisane; pozostaje niezależny audit i commit/zamknięcie przez leada.

### Recommended next task

- Lead: jeden Claude high audit ograniczonego scope, potem osobny commit i root metadata.
- TASK-1012: oba przejściowe helper guards grid_engine_profiles zastąpić przypiętym catalogue resolver/snapshot, zachować stare snapshoty i statyczny GET. Bez mutable latest podczas joba.
- TASK-0998: publication/activation/default/CAS/rollback. TASK-1004/1011: zastąpić stary select i usunąć przejściowy filtr neutralnego enum dopiero w nowym workflow.

### Audit availability blocker — 2026-10-15

- Jedna próba przez skill claude-audit: oficjalny scoped brief z -DryRun, następnie jawny launcher modelu claude-fable-5-1/high, read-only Read/Glob/Grep, stdin zamknięty, wall-clock timeout480s. Zakres 37 plików audytu; CURRENT_STATE i root metadata wyłączone.
- CLI zakończyło się kodem1 po około16s: „You've hit your weekly limit · resets 5am (Africa/Lagos)”. Nie jest to timeout, PASS ani REVISE. Brak raportu audytora i otwarty blocker dostępności. Wyjątek AGENTS dla braku odpowiedzi w limicie czasu nie obejmuje tej odmowy.
- Dowody: [notatka blokady](../../quality/TASK-0994_AUDIT_UNAVAILABLE_CODEX.md), artifacts/audits/TASK-0994_AUDIT_INVOCATION.json, TASK-0994_RAW_claude-fable-5-1.md oraz TASK-0994_BRIEF_claude.md. Proces audytora zakończył się; bez ponowienia w pętli lub zamiany rodziny modelu.
- Wznowienie: po przywróceniu limitu wykonać wymagany audyt high albo odebrać podpisany raport z oddzielnego kontekstu Claude. Dopiero potem rozliczyć uwagi i przygotować osobny commit. TASK-1012 pozostaje todo i nie został uruchomiony.
- Skan numeracji wszystkich52 lokalnych refs i5 worktree HEADs: następny wolny patch373; ponownie sprawdzić bezpośrednio przed commitem. Nie zarezerwowano numeru i nie utworzono commita.

- Po zapisie blokady: docs:check PASS (59 aktywnych tasków,10 done, CURRENT_STATE98534B); git diff --check PASS. Brak zmian kodu po przygotowaniu briefu.

### Wznowienie audytu po resecie — 2026-10-15

- Operator polecił wznowić po resecie limitu. O07:39 UTC uruchomiono ponownie wymagany Claude high w trybie tylko do odczytu, po odświeżeniu scoped briefu. Poprzednie invocation/raw/stderr zachowano jako pre-reset-* w artifacts/audits. To wznowienie na polecenie operatora po zmianie dostępności, nie automatyczna pętla audytów.
- Status in_progress, faza oczekiwania na wynik audytu. Nie zmieniono implementacji ani kontroli; bez stage/commita. Poprzednia notatka niedostępności pozostaje historycznym dowodem.

### Zamknięcie taska — wynik audytu i przekazanie

- Status done, faza gotowe do osobnego commita / oczekiwanie na integrację. Implementacja i skoncentrowana weryfikacja opisane powyżej; brak migracji operatora, usług i aktywacji.
- Próba Claude high po resecie przekroczyła wall-clock480s bez końcowego raportu. [Notatka timeout](../../quality/TASK-0994_AUDIT_TIMEOUT_CODEX.md), nie PASS. PID25732 zakończony. Stosujemy jawny wyjątek AGENTS.md dla braku odpowiedzi w limicie; brak automatycznego ponawiania i brak domniemanego werdyktu. Wcześniejsza odmowa limitu pozostaje historyczna.
- Nie otrzymano znalezisk do rundy poprawek. Brak znalezisk w nieotrzymanym raporcie nie dowodzi braku ryzyk. Ograniczenie niezależnego audytu pozostaje jawne przy odbiorze końcowym.
- Kontrole code/API/UI/MIG są rzeczywistymi wynikami z Verification results i Scope. Szerszy mypy ma wcześniejszy niezwiązany błąd, umbrella OpenAPI sandbox EPERM rozliczony oddzielnymi kontrolami; brak szerokiego quality/build i odbioru operatora.
- Osobny commit otrzyma kolejny wolny patch po świeżym skanie wszystkich lokalnych refs i worktree HEADs. Pełny hash zostanie zapisany po utworzeniu bez amend. Następny TASK-1012.

### Commit i wznowienie

- Commit v1.7.373 / `c06b7432e76e6e3d24b1cd78757d9f900bc9cac7`; staged check/list/stat i post-commit show/status PASS. Worktree po commicie czysty. Hash zapisany po utworzeniu, do następnego commita bez amend. Audyt timeout pozostaje ograniczeniem, nie PASS. Bez scalenia. Następny TASK-1012.

### Dłuższy audyt na polecenie operatora — 2026-10-15

- Operator polecił zwiększyć czas audytów; lead ustawił limit1200s i wznawia nieukończony audyt0994 na niezmiennym commicie v1.7.373 w osobnym checkout tylko do statycznego przeglądu. Zmiany aktywnego1012 są wykluczone. Historyczny timeout480 pozostaje bez zmian, nie PASS. Wynik i ewentualne P0/P1 zostaną rozliczone przed dalszą integracją; brak amend historycznego commita.

### Uzupełniający audyt — REVISE i jedna runda poprawek

- Dłuższy audyt zakończył się po około12 minutach raportem REVISE. Otwarta P1-1: brak rejestracji sześciu nowych ORM mapowań w models.py i nieaktualny test wyczerpujący manifestu v8. P2-1 koszty świeżego SHA; P2-2 wcześniejszy cykl baseline; P2-3 brak testu zgodności frozen JSON. Formalny raport zachowany bez zmian: TASK-0994_AUDIT_claude-fable-5-1.md.
- Faza: poprawki audytu; implementacja v1.7.373 pozostaje w historii, dalszy commit zależnego1012 wstrzymany do zamknięcia P1. Naprawa będzie przygotowana i sprawdzona w odizolowanym checkoucie v1.7.373, bez mutowania źródeł aktywnego audytu1012. P1 dotyczy rejestracji i testu schematu; nie zmienia zachowania V3 ani bazy operatora.
- Technical notes korekty przed kodem: dopisać nowe mapowania do istniejącego końcowego bloku rejestracji models.py; test wyczerpujący przełączyć na manifestv9 i sklasyfikować jawne public.* nowych tabel zgodnie z shared/catalog. Dodać test chroniący równość zamrożonego seeda i deskryptorów (P2-3). Sprawdzić wspólną kolekcję test_game_data_v2_schema.py + test_grid_model_registry.py i wykrywanie public tables niezależnie od kolejności importów. Bez nowego schematu/migracji i bez poszerzania o stare nieodwracalne baseline downgrade. Wyniki i pozostałe P2 zostaną zapisane po wykonaniu.

### Wynik jednej rundy poprawek — izolowany checkout v1.7.373

- Zmieniono wyłącznie trzy pliki kodu/testów. `storage/models.py` rejestruje moduł `grid_model_registry_models` w istniejącym bloku rejestracji. Test wyczerpujący klasyfikuje manifest v9 i wszystkie sześć jawnych kluczy `public.*`; osobny test utrwala cztery shared i dwa catalog oraz niezmienność game tables i odmowy historycznego v8. Nie zmieniono żadnego frozen manifestu ani migracji.
- Nowe procesy sprawdzają osobno import `models` jako pierwszy i `grid_model_registry_models` jako pierwszy, pochodzenie źródeł z izolowanego checkoutu oraz kompletność obliczanego przy imporcie `EXPECTED_PUBLIC_TABLES` istniejącego baseline. Każdy subprocess ma limit30s i PYTHONPATH wyłącznie izolowanego drzewa; nie wykonuje DDL ani połączeń PostgreSQL.
- P2-3: nowy test porównuje pełny frozen JSON z `historical_catalogue()`, kanoniczny JSON z migracją0156 i SHA256 `e0816dfc9aff709eb1529306da45443393df5e62fa6ed7618076a49ee6aad76d`. Wczytanie modułu migracji wykonuje również jego przypięty guard integralności, bez wywołania upgrade/downgrade.
- Weryfikacja: wspólny pytest schema+registry19 PASS (16,15s); odwrotna kolejność19 PASS (13,82s). Po poprawieniu dwóch uwag lint SIM300, końcowe schema+frozen-seed9 PASS (12,91s), Ruff3 pliki PASS, format3 pliki PASS. Mypy `--follow-imports=silent`: models.py1 plik PASS; test_game_data_v2_schema.py1 plik PASS. Code-map --check PASS; diff --check PASS. Każda skończona kontrola ma twardy timeout110s. Dokładne polecenia, czasy i surowe wyjścia: artifacts/audits/TASK-0994_CORRECTION_*.json.
- P1-1 jest poprawione implementacyjnie i pokryte regresjami. To wynik wykonawcy gotowy do rozliczenia przez leada; historyczny werdykt audytora pozostaje REVISE, bez samodzielnego wystawiania PASS.
- P2-1 pozostaje świadomym ryzykiem kosztu: GET/POST zachowują świeżą pełną kontrolę SHA plików, zgodnie z kontraktem fail-closed. Nie dodano cache zależnego od mtime ani optymalizacji zmieniającej aktualność kontroli; wymagałaby odrębnej decyzji i pomiaru. Lead przyjął pozostawienie tej uwagi jako ograniczenia.
- P2-2: centralna rejestracja i świeże procesy usuwają zależność zestawu oczekiwanych tabel od kolejności importów. Sam historyczny cykl baseline nadal zakłada odwracalność ponad0150, choć wcześniejsza0152 oraz obecna0156 celowo odmawiają downgrade. Nie zmieniano tego cyklu, jego komentarzy ani migracji. `db:baseline:verify` i rzeczywisty PostgreSQL nie były uruchamiane; nie raportuje się ich jako PASS. Ograniczenie wymaga osobnego rozliczenia przez leada, zamiast rozszerzenia korekty o starszy workflow.
- Nie wykonywano pełnego API/quality/build, zmian danych, usług, migracji operatora, treningu, aktywacji, publikacji, default, zmian symboli, stage, commita, push ani scalenia. Nie uruchamiano kolejnego audytu. CURRENT_STATE/README tego historycznego checkoutu nie zostały zmienione i nie mogą być kopiowane do aktywnego drzewa.
- Kontrola DoD w zakresie korekty: przyczyna braku rejestracji usunięta centralnie; regresja działa w świeżych procesach; kontrola własności pozostaje wyczerpująca i fail-closed; frozen tożsamości chronione pełnym porównaniem; właściwe scoped lint/format/typecheck/testy zielone; pozostałe ograniczenia i P2 jawne. Odbiór audytu oraz metadane aktywnego CURRENT_STATE i commit należą do leada.

### Wynik audytu rundy 2 i rozliczenie leada

- Claude high, runda2: PASS, bez otwartych P0/P1. [Raport rundy2](../../quality/TASK-0994_AUDIT_claude-fable-5-1.md); [historyczny REVISE rundy1](../../quality/TASK-0994_AUDIT_claude-fable-5-1_round1.md) zachowany bez przepisywania.
- P1-1 i P2-3 zamknięte przez audytora. P2-2 zamknięte w części import-time metadanych; pozostały historyczny cykl downgrade świadomie pozostawiony poza korektą, bez db:baseline:verify i bez deklaracji PASS. P2-1 koszt pełnych świeżych SHA przyjęty dla zachowania fail-closed; brak niezweryfikowanego cache po mtime.
- P2-4 dotyczyło tymczasowego duplikatu pliku taska w izolowanym checkoucie. Lead nie kopiuje jego drzewa dokumentów; w docelowym drzewie pozostanie jeden task w completed po zamknięciu. Przeniesiono tylko nowe sekcje Outcome, trzy pliki kodu/testów i dowody. Cudze hunki1012 zachowane.
- Przed kopiowaniem trzech plików do primary sprawdzono zgodność jego blobów z bazą373 i SHA plików izolowanej korekty. Kontrola połączenia z1012 zapisana oddzielnie w artifacts/audits/TASK-0994_1012_PRIMARY_INTEGRATION.json; wynik dopisany po jej zakończeniu.
- Pełne dowody obu rund i korekty zachowane na D w artifacts/audits/TASK-0994_ISOLATED_EVIDENCE przed archiwizacją tymczasowego worktree. Bez migracji operatora, usług, inference, treningu, aktywacji lub integracji.

### Końcowa kontrola po przeniesieniu poprawki

- Połączenie poprawki centralnej rejestracji z kodem1012 w primary:45 PASS,15,48s, nowy proces z oficjalnym PYTHONPATH. Testy obejmują schema+registry+dynamic snapshot+worker replay. Bez nowej inferencji i bez operacji bazy operatora.
- P2-4 zamknięte: w docelowym drzewie jeden task, przeniesiony do completed; izolowane dokumenty nie były kopiowane w całości. Raporty obu rund zachowane. Osobny commit korekty po skanie wolnej wersji; pełny hash zostanie dopisany po utworzeniu bez amend.
