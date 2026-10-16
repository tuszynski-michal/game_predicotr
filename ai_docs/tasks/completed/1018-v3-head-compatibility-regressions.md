---
title: TASK-1018 — Zgodność narzędzi i regresji po zmianach V3
status: done
last_updated: 2026-10-16
---

# TASK-1018 — Zgodność narzędzi i regresji po zmianach V3

## Status

`done`

## Goal

Przywrócić zgodność wcześniejszych pionów zleconego planu z aktualnym manifestem, admission, katalogiem i warunkami migracji, zachowując chronione kontrakty.

## Context

TASK-1002 zakończył się v1.7.382 / `f0e457ea78b825063e460fcd0023b01e2cb27fd2`, Claude high R2 PASS. Szersze kontrole ujawniły wcześniejsze regresje tego samego planu i niepełne dowody. To konieczna poprawka zleconego zakresu, bez nowej funkcji produktu. Nie wolno uznać wszystkich43 PG FAIL za przedplanowe albo za błędy produktu; atrybucja jest rozdzielona w rejestrze. Numer1018 przydzielono po sprawdzeniu24 lokalnych refs, HEADów worktree i fizycznych nazw tasków; operator zatwierdził automatyczne wolne numery.

## Dependencies / entry conditions

- TASK-1002 done; baza wykonawcza382, branch `codex/v3-grid-fine-tuning`.
- Cały plan i koszt12–28 dni zlecone. Operacje na danych operatora, benchmarki/GPU, usługi i integracja pozostają poza zgodą tego taska.
- Dwie zastane zmiany to posthash1002 w jego completed tasku i CURRENT_STATE; są znane i wejdą do tego commita. Nie dołączać innych cudzych zmian.

## Recommended execution

- Wykonawca `gpt-6.1-sol`, reasoning `high`.
- Niezależny review `claude-fable-5-1`, reasoning `high`, tylko do odczytu, do1200s, brief ograniczony do taska/diffu.
- Ryzyko: rzeczywiste role/RLS, historyczne migracje i narzędzia lifecycle. Sprzeczność produktu lub wymagane poluzowanie ochrony zatrzymuje zależny fragment; bez ukrytego zamiennika modelu i bez osłabiania testów.

## Relevant docs

- [CURRENT_STATE](../../process/CURRENT_STATE.md), `AGENTS.md`, PLAN_STANDARD i TASK_TEMPLATE.
- [Plan](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje2–5 i opis1018 oraz ostatni wiersz modeli dla1018.
- [Rejestr obowiązków](../../quality/V3_BACKEND_REGRESSION_OBLIGATIONS_20261015.md), cały dokument i24 dokładne nodeIDs w końcowej sekcji.
- [R2 TASK1002](../../quality/TASK-1002_AUDIT_claude-fable-5-1_R2.md), uwagiP2-1/4/5; [Outcome1002](1002-source-recording-groups.md#outcome).
- [Nagrania i wdrożenie](../../guides/SOURCE_RECORDING_GROUPS.md), [operacje lokalne](../../guides/LOCAL_OPERATION_GUIDE.md).
- [Mapa kodu](../../architecture/CODE_MAP.md), [DATA_MODEL](../../architecture/DATA_MODEL.md), [własność geometrii](../../architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md), [IMAGE_INGESTION](../../requirements/IMAGE_INGESTION.md).
- D-549/D-551/D-554 z indeksu decyzji; pełne wpisy tylko gdy potrzebne do rozstrzygnięcia sprzeczności.
- Ignored materiały wejściowe: `artifacts/audits/PRIOR_PLAN_BACKEND_COMPATIBILITY_DRAFT.md`, `TASK-1002_R2_IMPLEMENTATION_EVIDENCE.json` i `auditCopyByOriginal`. Tylko bezpieczne kopie; żadnych raw logów, `.env` ani credentials. Nie wklejać całych archiwów do briefu.

## Scope

1. Historyczny test0140 przypiąć do jego faktycznego enum/DDL; osobno zachować aktualne pokrycie `neural_grid_v3` z0156. Nie brakuje produkcyjnego constraintu.
2. Poprawić test doubles admission/get_bind i własny resolver symboli dla obecnego kontraktu. Zachować replay/retry po nowym repozytorium, unknown sequence i odrębne modele symboli.
3. Rzeczywista application-role fixture tworzenia gry ma wysłać prawidłowy UUID key i przygotować własny zgodny published default w prawdziwym magazynie. Musi dojść do oryginalnych201/storage/RLS asercji; dependency mock nie zastępuje tego dowodu.
4. Zarejestrować intentional0158 boundary w frameworku cyklu: odmowa zachowuje właściwą rewizję, dalszy upgrade działa. Historyczne testy0154/supergame/LAB muszą nadal docierać do własnej starej ochrony przez odpowiednio przypięte własne fixture, a nie oczekiwać0158 zamiast starego guardu. Nie zmieniać polityk migracji.
5. `delete_archived_v2_game.py::collect_blockers` ma używać autorytatywnego bieżącego runtime manifestu. Nie następnej sztywnej wersji. Zachować scope/archive/Confirm i wszystkie blokery. Nie wykonywać usuwania.
6. Pięć narzędzi wskazanych w R2-P2-1: CREATE własnej DB → capability → head → application provisioning, z dokładnym createdHere/OID/role marker i cleanup. Nie importować modułów testowych do produkcyjnych narzędzi. Testować statyczny kontrakt i mały izolowany provisioning, bez uruchamiania benchmarków lub właściwego acceptance workload.
7. Baseline fixture ma mieć własną UUID nazwę oraz cleanup tylko po skutecznym CREATE; nie maskować pierwotnego CREATE error. RGB moduł dostaje jawny poprawny opt-in PG marker przy zachowaniu pełnych asercji po włączeniu.
8. Rozliczyć24 niezweryfikowane nodeIDs z rejestru w krótkich właściwych trybach. Szczególnie13 proposals i rzeczywisty application-role diagnostyki; sama zmiana flagi nie dowodzi RLS. Własny krótki TEMP na Windows ma być częścią wersjonowanego runnera, jeżeli potwierdzi się konkretny limit, bez zmian systemu i sesyjnego obejścia udającego trwałą naprawę.
9. Osiem engine-acceptance FAIL ma statycznego kandydata: nieograniczony lookup source revision. Najpierw wykazać konkretną przyczynę w własnej fixture, potem zawęzić do seed.game/source. Nie osłabiać rules/game guard. Trzy wcześniejsze bulk-start event-wait FAIL są częściowo przypisane; zachować kolejność współbieżności i5s kontrakt, bez zwiększania timeoutu dla zielonego wyniku. Jeżeli diagnoza ujawni sprzeczną politykę produktu/admission, STOP zależnego fragmentu i raport leada.

## Out of scope

- Nowa funkcja produktu, nowy model symboli, poluzowanie guardów, xfail lub usuwanie asercji.
- Naprawa niezależnego starego reset graph RESTRICT bez ustalonego osobnego zakresu; istniejący FAIL pozostaje.
- Baza operatora, jej migracja/reset/backfill, nowy backup, source sweep, benchmark/load, prawdziwe checkpointy/inference/GPU/trening, usługi, aktywacja/default, merge/push.
- Kolejna pełna614-modułowa/473-node macierz bez nowej uzasadnionej potrzeby. R2-P2-2/3 są przyjętymi ograniczeniami, nie zgodą na re-own lub automatyczny GC journals.

## Acceptance criteria

- [x] Dokładne przyjęte kontrakty unit i runtime preview mają test regresyjny i właściwy wynik bez osłabienia produkcyjnych zabezpieczeń.
- [x] Actual-role create i diagnostyka wykonują prawdziwe kontrole właściciela/RLS; symbole własnej gry pozostają odrębne.
- [x] Historyczne guardy0158 i wcześniejsze zachowane, cykl po odmowie może wrócić do aktualnego head.
- [x] Pięć runnerów provisionuje capability w prawidłowej kolejności i nie pozostawia własnych DB/ról; benchmarków nie uruchamiano.
- [x]24 wskazane niezweryfikowane przypadki mają dokładne terminalne wyniki albo jawny niezależny blocker, bez fikcyjnego full PASS.
- [x] Nowe przyczyny engine/locking udowodniono albo zgłoszono sprzeczność przed zmianą zachowania; nie przemianowano hipotezy na historyczną reprodukcję.
- [x] Jedna runda Claude i dozwolona korekta, dokumentacja/Outcome/stan; gotowe do osobnego commita bez otwartychP0/P1.

## Technical notes

Uściślenie wykonawcze przed zmianą pięciu runnerów (2026-10-16): wszystkie obecnie
używają połączenia owner bez provisioningu roli aplikacji. Zgodnie ze Scope6
powstaje wąski proponowany moduł
`services/api/src/game_predictor_api/storage/owned_tool_database.py` z publiczną
granicą `OwnedToolDatabase`: własna UUID baza, capability przed migracją,
ograniczona własna rola runtime po migracji, osobne `owner_url`/`runtime_url`
i cleanup z kontrolą absence/createdHere/OID/marker/idle==0. Narzędzia zachowują
owner tylko dla DDL i jawnego provisioningu, a praca aplikacyjna używa runtime.
To współdzielenie pięciu identycznych granic narzędzi, bez importu testów i bez
zmiany kontraktu HTTP lub domeny. Wąski wykonawca `gpt-6.1-sol/high` odpowiada
wyłącznie za ten moduł, pięć runnerów i ich skoncentrowane testy. Główny
wykonawca odpowiada za pozostałe fixture, testy PostgreSQL, Outcome i mapy.

Rozstrzygnięcie testów bulk-locking przed korektą (2026-10-16): własny test PG
potwierdził odmowę `GAME_JOB_ADMISSION_CONFLICT` z `existingJobId` dla nowego
niezależnego polecenia, gdy pierwszy bulk job ma status CREATED. Jest to przyjęty
kontrakt D-551/TASK-0999. Dawne trzy testy zakładały równoległy nowy start i
dlatego nie docierały do target INSERT w zachowanym limicie5s. Zgodnie z
rozstrzygnięciem leada test ma sprawdzić odmowę admission podczas rzeczywistej
blokady planszy, zwolnić worker zdarzeniem po tej odmowie, zachować replay oraz
po terminalnym pierwszym JOB oddzielnie sprawdzić niezależny start albo oryginalne
odmowy stale explicit/filter. Statusu joba nie wolno pozorować w trakcie pracy;
claim/complete mają przejść przez istniejący store z prawidłową dzierżawą.
Produkcyjny admission i limity5s pozostają bez zmian.

Analogiczne rozstrzygnięcie publication po exact PG FAIL: test zachowywał pierwszy
`VALIDATE/page_geometry_preflight` w PROCESSING, a następnie publikował drugi
nowy job tej samej gry. D-551 odmawia takiej nowej komendy. Po udowodnieniu
niezmienionego pinu PROCESSING po activate test kończy pierwszy job przez
rzeczywiste `SqlAlchemyWorkerJobStore.complete` z ważną dzierżawą. Dopiero potem
tworzy drugi job z nowym pinem. Końcowe kontrole dokładnych payloadów/replay
pozostają; pierwszy job ma wtedy prawidłowy status COMPLETED. Lead zatwierdził
korektę przed kodem. Historyczny guard0157 sprawdzamy przed upgrade do obecnego
head; nie oczekujemy nowej odmowy0158 zamiast starej polityki publikacji.

Przed kodem wersjonowanego runnera: konkretna próba `tmp_path` nie mogła utworzyć
katalogu w sandboxowym Windows TEMP; stare dowody1002 wskazują również MAX_PATH
przy zagnieżdżonych artefaktach. Proponowany
`scripts/run_scoped_python_tests.py` przyjmuje dokładne cele pytest, receipt oraz
limit1–120s. Używa wyłącznie nowego własnego UUID katalogu w krótkim
`artifacts/t` wspólnego checkoutu Git, nie zmienia systemowego TEMP ani PATH.
Zapisuje log do pliku, terminalne node outcomes i bezpieczną kopię z redakcją
sekretów, kontroluje własny PID/drzewo procesu i usuwa tylko potwierdzony własny
TEMP. Timeout lub ENV nie jest PASS. Wąski wykonawca runnera i jego testu to
`gpt-6.1-sol/high`, sekwencyjnie po korekcie helpera narzędzi.

Przed kodem odczytać task i fragment planu ponownie. Najpierw dokładny czerwony node/warunek, potem minimalna korekta istniejącego kontraktu. Nie naprawiać masowo wszystkich43 FAIL. Aktualizacje historycznych fixture muszą rozdzielać przypięty schemat od bieżącego routera/API; obecny runtime nie może udawać zgodności z dawnym manifestem. Bieżące stałe importować z autorytatywnego kontraktu, historyczne pozostawić zamrożone.

Testy na małych istniejących fixture, actualPG tylko w nowych własnych UUID bazach i rolach. Absence przed CREATE, createdHere/OID i marker przed każdym cleanup; żadnego FORCE/backendkill/DROP OWNED/REASSIGN. Bounded idle wait zachowuje końcowy active==0. Permission rejection nie upoważnia do powtórzenia nieguardowanej komendy z większymi uprawnieniami. Przywracanie błędu testu nie może zatrzeć oryginalnego wyjątku.

Model/storage/UI API nie zmienia się w tym tasku. Jeżeli konieczna okaże się zmiana publicznego kontraktu albo dodatkowa migracja, zgłosić ją przed kodowaniem, zachować backend/OpenAPI/generated/wrapper/request pion i decyzje właścicielskie. Nie przepisywać ręcznie wygenerowanych typów. Nowy wspólny moduł tylko przy wykazanej potrzebie, nie kolejny ogólny framework testowy.

## Expected files

- `services/api/src/game_predictor_api/storage/game_partition_lifecycle.py` — jawne eksporty istniejących `DELETE_TABLES`, `SCHEMA`, `VERSION` dla typowanego konsumenta aktualnego manifestu; wartości i zachowanie pozostają bez zmian.

- `services/api/tests/test_grid_engine_profiles_migration.py`, `test_image_symbol_review_backfill_storage.py`, `test_neural_page_geometry_api.py`, `test_symbol_model_iteration_storage.py` — dokładne wskazane nodeIDs w rejestrze.
- `services/api/tests/integration/test_postgres_baseline.py`, `_recording_capability_fixture.py`, `_application_role_database.py`, `test_application_role_isolation_postgres.py`, `test_grid_geometry_proposals_postgres.py`, `test_board_import_coverage_repository.py` — własne fixture i wymagane actual-role.
- `test_geometry_correction_revert_pending_postgres.py`, `test_super_game_series_postgres.py`, `test_historical_grid_acceptance_postgres.py`, historyczne LAB/routing cases z rejestru — wyłącznie udowodnione historyczne granice.
- `test_v3_engine_acceptance_postgres.py`, `test_symbol_review_bulk_start_locking_postgres.py`, `test_symbol_rgb_v2_writer_postgres.py` — zakres i ograniczenia powyżej.
- `scripts/delete_archived_v2_game.py::collect_blockers`, pięć runnerów i miejsca `command.upgrade(...,head)` dokładnie wymienione w rejestrze; `storage/source_recording_permissions.py::provision_recording_capability` jako istniejące wejście, bez obejścia własności.
- Proponowany nowy wąski test statyczny `services/api/tests/test_v3_head_tooling_compatibility.py`, jeśli istniejące testy skryptów nie pokrywają pięciu runnerów; nie deklaruje się istniejącego pliku.
- Plan, niniejszy task, rejestr, CURRENT_STATE, właściwe owner docs i generowane mapy przy zmianie modułu/publicznego symbolu. Root odpowiada za globalny plan/State/README, wykonawca za kod/testy, własny Outcome i mapy po uzgodnieniu.

## Test cases

- Cztery exact unit failures sprzed1002 przechodzą, oryginalne asercje replay/admission/DDL pozostają.
- RGB domyślnie bez PG nie próbuje połączenia, a opt-in zachowuje właściwe write/filter/revert.
- UUID fixture collision/nieudane CREATE nie dotyka obcej bazy i zachowuje pierwotny błąd.
- 0158 refusal i historyczne odmowy0154/supergame mają właściwe ustawienia; reupgrade działa.
- Aktualny manifest podglądu archiwalnej gry nie wymaga hardcodedv14; test nadal blokuje obcą/aktywną/niewłaściwą grę.
- Zgodna realna rola runtime, świeży proces i rzeczywiste201/diagnostic snapshot; deny private i sourceRLS nadal działają.
- Dokładny własny source/game w engine fixture i nienaruszona ochrona zgłoszenia człowieka/rollback.
-24 szczegółowe przypadki z rejestru, bez dodawania ich jako nowych testów przy powtórzeniu.

## Verification

Z worktree i właściwym PYTHONPATH API/worker/test_support. Każdy pytest/lint/typecheck krok ma twardy limit120s; dzielić po rzeczywistym koszcie setupu, z kontrolowanym procesem i receipts. W razie timeoutu zachować wynik/cleanup, nie uruchamiać automatycznej pętli. Najpierw exact node, potem dotknięty moduł/Ruff/mypy. DOC/MAP/diff i staged check przed osobnym commitem.

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_engine_profiles_migration.py -q
.\.venv\Scripts\python.exe -m ruff check <ustalone-pliki>
npm run docs:check
npm run code-map:check
git diff --cached --check
```

Przykładowy venv w worktree może wymagać użycia istniejącego `D:/game_predicotr/.venv/Scripts/python.exe`; zweryfikować, nie instalować środowiska po cichu. Placeholder listy plików dobiera wykonawca po analizie diffu; nie jest literalną komendą do uruchomienia. Nie wykonywać literalnego pełnego db:baseline:verify uruchamiającego Docker lub długiego pojedynczego pytest. Nowe API tylko przy udokumentowanej konieczności i właściwych kontrolach OpenAPI.

## Risks / open questions

- Wczesne źródła atrybucji nie są pełnym historycznym wykonaniem. Nierozstrzygnięte locking/engine błędy mogą wymagać decyzji leada zamiast poprawki testu.
-24 wcześniejsze niezweryfikowane przypadki mogą zawierać niezależne stare błędy; raportować dokładny status, bez uznaniowego PASS.
- Stare reset/supergame UI baselines pozostają jawne poza zakresem. Zweryfikować konkretne kontrakty, nie udawać zielonego repozytorium.

## Outcome

### Execution phase

Implementację zakończono 2026-10-16 na bazie `v1.7.382`,
`f0e457ea78b825063e460fcd0023b01e2cb27fd2`, w branchu
`codex/v3-grid-fine-tuning`. Task pozostaje `in_progress` do niezależnego audytu
Claude i osobnego commita wykonywanych przez leada. Wykonawca nie stage'ował,
nie commitował i nie uruchamiał własnego audytu. Kontrakt i rozstrzygnięcia
admission zapisano przed odpowiednimi zmianami kodu.

### Changed

- Rozdzielono historyczne 0140 od bieżącego 0156, poprawiono semantyczne fixture
  admission/retry oraz resolver symboli własnej gry dla unbound neural. Domyślny
  RGB ma rzeczywisty marker opt-in; jawny PG zachowuje write/filter/revert.
- Fixture PostgreSQL tworzą nowe UUID zasoby po sprawdzeniu nieobecności.
  Cleanup wymaga własnego OID/marker/createdHere i idle0; błąd CREATE ani kolizja
  nie pozwalają adoptować obcej bazy. Zachowano pierwotny wyjątek. Historyczne
  guardy 0150/0154/0158, supergame, registry/publication, LAB i neural są osiągane
  na rzeczywistych przypiętych rewizjach, po czym następuje upgrade do head.
- Actual-role create wykonuje HTTP201 z prawidłowym modelem/kandydatem. Snapshot
  diagnostyczny i historyczne acceptance używają rzeczywistej ograniczonej roli;
  sprawdzają RLS oraz deny private. Cancellation zachowuje cancel/reuse na
  własnej pustej bazie, bez łączenia do bazy aplikacyjnej operatora.
- Engine acceptance wybiera wszystkie revision/board/cell/snapshot dane przez
  własny game/source, zamiast niejednoznacznego pierwszego wiersza. Nowa próba
  dała 7FAIL/4PASS; wcześniejsze 8FAIL nie jest przedstawiane jako ten sam
  pomiar. Dodatkowe błędne selektory diagnostyczne wykonawcy zachowano jako
  nieudane własne próby, a nie wcześniejsze awarie produktu.
- Zgodnie z zaakceptowanym D-551/0999 locking wymaga odmowy nowego polecenia
  podczas board lock z `GAME_JOB_ADMISSION_CONFLICT` i właściwym existingJobId.
  Replay pozostaje idempotentny; po zdarzeniu zwalniającym worker oraz rzeczywistym
  `store.complete` zachowano niezależny start i stale explicit/filter rejection.
  Limit zdarzenia nadal wynosi 5s. Publication dowodzi niezmienionego pinu
  PROCESSING po activate, kończy job ważną dzierżawą i dopiero wtedy tworzy drugi
  job z nowym pinem. Produkcyjnej polityki admission nie zmieniano.
- Pięć narzędzi korzysta ze wspólnego wąskiego `OwnedToolDatabase`:
  capability przed head, ograniczona application role po head, owner URL tylko
  do provisioningu/DDL, runtime URL do pracy aplikacyjnej. Pending receipts
  przetrwają częściowy cleanup; jawne `close(retry_cleanup=True)` ponawia tylko
  potwierdzone pozostałe zasoby. Nie ma FORCE/backend kill ani automatycznej
  pętli cleanup. Caller benchmark tools nie importują modułów testowych.
- Podgląd archiwalnej gry używa autorytatywnego runtime manifestu. Jawne eksporty
  istniejących stałych lifecycle zapewniają zgodność strict mypy. Nowy mały PG
  proof wywołuje build_preview w transakcji READ ONLY i zachowuje blokery.
- Wersjonowany scoped runner zapisuje plik logu, dokładne node outcomes,
  deadline do120s, tożsamość/drzewo własnego procesu i krótki własny TEMP.
  Nie zmienia globalnego PATH/TEMP i nie przejmuje usług ani cleanup baz.

### Verification results

Pełne polecenia, timeouty, nodeIDs, bezpieczne kopie i SHA znajdują się w
`artifacts/audits/TASK-1018_IMPLEMENTATION_EVIDENCE.json`. Wyników nakładających
się prób nie sumuje się:

- Dokładne 24 wcześniejsze incomplete/harness-env nodeIDs z rejestru: **24/24
  PASS**. Dowody: diagnostics z `pg-role-create-diagnostics`, 13proposals z
  `pg-proposals-13`, registry z `pg-registry-publication-green`, publication z
  `publication-final-clean` oraz osiem z `pg-remaining-eight`. Mieszany bundle
  registry/publication zawiera wcześniejszy publication FAIL i nie jest w całości
  PASS; terminalne potwierdzenie publication ma osobny receipt.
- Pozostałe focused: unit final **111PASS/1SKIP**; engine **11PASS**; locking
  **5PASS**; baseline **2PASS**; actual-create/diagnostics **2PASS**; historyczne
  acceptance **9PASS** w partiach6+3; supergame/LAB PASS; RGB/readonly
  preview/neural0145 **3PASS**. Preview po jawnych eksportach ma osobne **8PASS**.
  Te grupy częściowo obejmują wcześniejsze dowody, nie stanowią nowego łącznego
  licznika. Aktualny helper po korekcie partial-cleanup przeszedł mały actualPG
  fresh-process/runtime/deny-private/normal-close proof. Fault i jawne wznowienie
  cleanup mają osobne testy unit. Runner ma również rzeczywisty timeout3s z
  potwierdzonym usunięciem własnego drzewa i TEMP.
- Ruff/format dla39 plików PASS; scoped mypy silent9 modułów PASS w118.765s;
  DOC/MAP/diff PASS. Każdy krok mieści się w120s. Pełne wyniki w manifeście.
  Zachowano wcześniejsze czerwone próby: tryb mypy skip daje te same7 artefaktów
  import-Any także na exact HEAD382 przez shadow-file; nie jest dowodem nowej
  regresji. Pierwszy proper silent ujawnił3 brakujące jawne eksporty, poprawione
  bez zmiany runtime.
- Pierwsza próba publication-final miała body PASS i teardown ERROR; cały wynik
  pozostaje FAIL. Własną zatrzymaną bazę/role sprzątnięto po osobnym sprawdzeniu
  dokładnego OID/marker i idle0. Następna próba ma oddzielny PASS. Dowody
  `publication-retained-cleanup.json` i niezmieniony wcześniejszy log pozostają.
- Wczesne neural/TestClient sandbox socketpair10013 i przerwane próby zachowują
  NOT_COMPLETED, nie PASS ani regresję produktu. Dokładny test po scoped
  escalation przeszedł; własne PID/drzewa sprawdzono po zakończeniu.
- Końcowy odczyt38 journals i aktualnego helper receipt potwierdził nieobecność
  **39 własnych baz,55 ról i0 aktywnych połączeń**. Brak własnych pozostałych PID
  potwierdza osobny dowód. Wszystkie receipted canonical TEMP usunięto;15 dawnych
  katalogów usunięto wyłącznie po21 zapisanych command/basetemp receipts.

### Not completed / limitations

- Niezależny Claude R1, dozwolona korekta, globalne owner docs, przeniesienie
  taska do completed i osobny commit należą do leada. Brak twierdzenia o audycie
  lub pełnym zielonym repozytorium przed ich wykonaniem.
- Nie uruchamiano pełnych macierzy614/473, literalnego db:baseline:verify,
  benchmark/acceptance workloads pięciu narzędzi, inference/checkpointów/GPU,
  operator migrations/reset/backfill/deletion, usług API/Admin/Docker, backupu
  ani push/merge. Istniejący reset/supergame UI baseline pozostaje poza zakresem.
- Nie uruchomiono istniejącego node `archived...previews_and_deletes` i nie
  usunięto jego DELETE assertions. Zakres wykonany obejmuje unit blockers,
  aktualny manifest oraz nowy mały build_preview READ ONLY proof; usuwania
  archiwalnej gry nie wykonywano. Node nie należy do wymaganych24.
- Dwa katalogi z przerwanych najwcześniejszych prób pozostawiono, ponieważ
  driver nie zapisał ich argv/receipt przed przerwaniem:
  `D:/game_predicotr/worktrees/v3-grid-fine-tuning/artifacts/t/02e01cde` oraz
  `D:/game_predicotr/worktrees/v3-grid-fine-tuning/artifacts/t/05526fd5`.
  Zawierają test_all_unbound_neural_source0, ale bez wystarczającego dowodu
  własności nie podjęto ich usunięcia. Nie twierdzimy, że globalny TEMP jest pusty.
- Surowe `.capture`, connection logs, środowisko i poświadczenia są wyłączone
  z briefu; do audytu wskazano tylko bezpieczne kopie i ich SHA. Timeouty i
  nieudane własne próby zachowują odrębne wyniki.

### Documentation updates

Zaktualizowano ten kontrakt/Outcome, LOCAL_OPERATION_GUIDE (scoped runner,
krótki TEMP, deadline i uczciwe wyniki), SOURCE_RECORDING_GROUPS (pięć narzędzi,
owner/runtime i kontrolowany cleanup) oraz generowane CODE_MAP/SYMBOLS.
Globalne README/plan/State/rejestr i posthash1002 pozostają własnością leada;
ich zastane zmiany zachowano i wyszczególniono w manifeście.

### Recommended next task

TASK-1009 po audycie i oddzielnym commicie1018 oraz zapisaniu pełnego hasha.
Lead kontynuuje pozostały zaakceptowany plan; wykonawca po freeze czeka na wynik
niezależnego audytu, bez dalszych zmian źródeł lub zamrożonych dowodów.


### Zamknięcie przez lead — 2026-10-16

- Execution phase: gotowe do osobnego commita **v1.7.383**, potem oczekiwanie na integrację całego planu. Pełny hash dopisany po commicie, bez amend.
- [Claude high R1 PASS](../../quality/TASK-1018_AUDIT_claude-fable-5-1_R1.md),678.683s/do1200s, brak P0/P1. Oryginały bez zmian;50 źródeł/160 dowodów SHA zweryfikowano po audycie. [Rozliczenie Codex](../../quality/TASK-1018_RESPONSE_CODEX.md).
- P2-1: Poprawione: cancellation fixture zachowuje ten sam pierwotny wyjątek CREATE/body przy błędach drop/dispose i dopisuje note; samodzielny błąd cleanup nadal propaguje. Red4FAIL/5PASS, cały moduł31PASS i końcowe dokładne9PASS; Ruff/format/diff PASS. Tylko dwa wskazane pliki, bez PG.
- P2-2: Poprawiona instrukcja M4: każdy run ma nową UUID bazę, bez keep cleanup następuje również po błędzie workloadu, keep zachowuje po sukcesie i błędzie workloadu; nie gwarantuje zatrzymania po błędzie provisioningu. Historyczne pole databaseRetainedForRetry oznacza inspekcję, nie adopcję przy retry.
- P2-3: Przyjęte ograniczenie zakresu: pięciu rzeczywistych workloadów nie uruchamiano. Zgodność runtime URL wykazano statycznie i małym provisioning proofem; ORM seed m34 może wymagać poprawki przy pierwszym osobno zleconym smoke. Nie deklarujemy gotowości benchmarku na podstawie tego taska.
- P2-4: Przyjęte ograniczenie uruchamiania: test importujący scripts wymaga python -m pytest z katalogu głównego worktree lub wersjonowanego runnera ustawiającego root. Wszystkie polecenia tego taska mają taki kontrakt. Dowolny cwd i bezpośredni pytest pozostają niewspierane; nie zmieniono globalnego pythonpath.
- P2-5: Poprawiona przenośna instrukcja: ścieżka venv głównego checkoutu wynika z git-common-dir. Odrębny proces PowerShell potwierdził istniejący interpreter; bez uruchamiania testów/usług i bez zmiany konfiguracji systemu.
- Jedna dozwolona korekta P2; R2 nie wymagany. Końcowe DOC/MAP/diff i staged lista/stat są kontrolowane przed commitem. Stan historyczny „audyt niewykonany” powyżej opisuje przekazanie wykonawcy, a niniejsza sekcja je zastępuje.
- Recommended next task:1009, geometria wszystkich9 pozycji obowiązkowa, symbole tylko według aktualnych ręcznych zatwierdzeń; pozostałe nieocenione. Bez rzeczywistej próby operatora przed zebraniem anotacji.
