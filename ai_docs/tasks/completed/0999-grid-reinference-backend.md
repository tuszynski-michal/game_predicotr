---
title: TASK-0999 — Backend ponownego rozpoznania wybranego zakresu
status: done
last_updated: 2026-10-15
---

# TASK-0999 — Backend ponownego rozpoznania wybranego zakresu

## Status

`done`

## Goal

Przeliczyć wskazane cele z trwałym postępem i ochroną danych.

## Context

Task jest częścią zaakceptowanej rewizji 6. Ponowne zapisy i ochrona sekwencji. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1017, TASK-1012, TASK-0998; bez zależności od treningu.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. zapis geometrii, wycinków i kontrola właściciela.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [IMAGE_INGESTION](../../requirements/IMAGE_INGESTION.md).
- [VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP](../../architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md).
- Zakres odczytu uzupełniający z planu: IMAGE_INGESTION, D-462/D-523/D-543, VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.

- [D-462](../../process/decisions/DECISION_LOG_2026.md#d-462--weryfikacja-per-komórka-bez-zatwierdzania-planszy-i-siatki) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-523](../../process/decisions/DECISION_LOG_2026.md#d-523--operational-neural-crops-and-recoverable-symbol-verification) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-543](../../process/decisions/DECISION_LOG_2026.md#d-543--odrzucanie-przyciętych-plansz-po-imporcie-i-przejęcie-sekwencji-przez-zdjęcie-zastępcze) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-551](../../process/decisions/DECISION_LOG_2026.md#d-551--propozycje-dla-błędnej-siatki-v3) — przyjęty kontrakt reinferencji i przekazania propozycji.
- [D-550](../../process/decisions/DECISION_LOG_2026.md#d-550--akceptacja-silnika-v3-i-statusowy-backfill) — engine acceptance bez zatwierdzenia człowieka.

## Scope

- Preview, zamrożony manifest, jeden inference na zdjęcie, zapis tylko wybranych celów.
- Dla zgłoszeń wynik pozostaje propozycją przekazywaną do TASK-1013.
- Admission uwzględnia kolidujące zadania geometrii i symboli.

## Out of scope

- Bez automatycznego przejęcia kanonu i uruchamiania pełnej gry.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Aktualna baza działa bez treningu.
- [x] Chronione decyzje pozostają identyczne.
- [x] Brak środkowego slotu nie przesuwa sekwencji.
- [x] Restart nie dubluje zapisu; identyczny wynik nie jest „naprawą”.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

### Kontrakt przyjęty przed implementacją — release2026-10-15

Kontrakt zapisano 2026-10-15 po read-only preflight i commicie TASK-1011
v1.7.378 / `d078938b18abdff5d6e1f99795f9d4aca09716b1`. Lead przyjął
kontrakt, udokumentował D-551 accepted i wydał release implementacji2026-10-15
przed zmianą kodu. Zakres produktu wynika z rewizji6,
sekcji2.5/4.2 oraz TASK-0999/1013; nie dodajemy nowej decyzji produktowej.

### Komendy, aktorzy, receipts i fazy joba

Rozszerzamy istniejący router `image-review-items`; stare GET preview i stary
POST pending-grid-reinference zachowują dotychczasowy kontrakt. Nie ożywiamy
`PendingGridReinferenceHandler`. Proponowane addytywne trasy pod tym routerem:

- `POST /grid-reinference/{game_id}/prepare`: UUID idempotencyKey, zamknięty
  selector, modelSelection i executionScope; zwraca operationId oraz jobId.
- `GET /grid-reinference/{game_id}/operations/{operation_id}`: stan,
  przygotowanie, model, manifest SHA, liczniki i raport; bez mutacji.
- `GET /grid-reinference/{game_id}/operations/{operation_id}/targets`:
  strona do100 celów i cursor; bez ponownego filtrowania żywej gry.
- `POST .../operations/{operation_id}/freeze`: idempotencyKey,
  expectedRevision i manifestSha256; zapisuje trwały receipt zamrożenia.
- `POST .../operations/{operation_id}/pilot-ack`: idempotencyKey,
  expectedRevision, pilotOperationId i pilotReportSha256; zapisuje świadome
  potwierdzenie raportu pilota dla przygotowanej szerszej operacji.
- `POST .../operations/{operation_id}/start`: idempotencyKey,
  expectedRevision, manifestSha256 i jawne broadScopeConfirmed, gdy potrzebne.
- `POST .../operations/{operation_id}/resume`: nowy idempotencyKey,
  expectedRevision i expectedPhase; wznawia przerwaną fazę bez nowego zakresu.
- `POST .../operations/{operation_id}/cancel`: idempotencyKey i
  expectedRevision; używa istniejącego mechanizmu żądania anulowania joba.

Actor pochodzi z istniejącego zaufanego kontekstu backendu, nie z body.
Prepare ma namespace `(gameId, prepare, key)`. Kolejne komendy mają namespace
`(gameId, operationId, commandKind, key)`. Receipts przechowują canonical
command/hash, aktora i oryginalną tożsamość wyniku. Te same key/body odtwarzają
receipt przed CAS i admission; inna treść daje409. Odtworzenie zwraca też
bieżący stan operacji, ale samo nie wznawia terminalnego joba. Operacja ma
ograniczony ledger JSONB tych komend (maksymalnie128 różnych kluczy; po limicie
jawny konflikt bez usuwania historii); nie wymaga czwartej tabeli gry.

Jedna operacja ma jeden trwały `IMAGE_GRID_REINFERENCE` job i payload nowego
kontraktu `grid-reinference-v1` (schema_version3). Pole `phase` w trwałym
rekordzie operacji jest źródłem fazy; payload identyfikuje operację i pin.
Historyczne payloady nadal trafiają do deprecated handlera i jego jawnego
`IMAGE_GRID_REINFERENCE_LEGACY_UNSUPPORTED`.

Przejścia operacji i joba:

| Komenda lub zdarzenie | Operacja | Job / lease / admission |
| --- | --- | --- |
| prepare | preparing, phase=prepare | created; admission zajęte |
| worker capture i kolejne strony | preparing, trwały nextOrdinal | processing z istniejącym lease |
| finalizacja manifestu | prepared, SHA i liczniki gotowe | waiting_for_review, lease usunięty; admission zwolnione |
| freeze | frozen, niezmienny receipt | nadal waiting_for_review, bez lease |
| start | queued, phase=infer | ten sam job ponownie created po admission |
| worker | running, trwały cursor/receipts | processing z lease |
| koniec | completed, niezmienny report SHA | completed, bez lease |
| kontrolowana awaria | failed z zachowaną phase/cursor | failed, bez lease |
| anulowanie bez aktywnego lease | cancelled z zachowaną phase | cancelled, bez lease |
| anulowanie processing | cancel_requested, następnie cancelled | processing blokuje do potwierdzenia przez worker |
| resume | preparing albo queued zgodnie z phase | ponowna admission, ten sam job created |

Finalizacja przygotowania i `wait_for_review` muszą być jednym zapisem pod
lease: nie można zostawić prepared z runnable jobem ani waiting joba bez
gotowego manifestu. Wznowienie prepare kontynuuje membership i strony,
nie wykonuje ponownie capture. Wznowienie infer wymaga wcześniejszego freeze,
start receipt i zgodnego modelu; nie odtwarza nowego assignment/pilota.
Po awarii przed capture następna próba może wykonać pierwszy capture; po
zatwierdzonym capture membership nigdy nie zmienia się.
Generic job retry oraz file retry/resume nie mogą ominąć tego automatu:
dispatch dla nowego kontraktu deleguje do wspólnego resume/admission.
Nieautoryzowana faza infer po prepared/frozen zwraca typed
`GRID_REINFERENCE_START_REQUIRED`; generic retry nie zastępuje jawnego startu
ani pilot acknowledgement. Może wznowić wyłącznie wcześniej autoryzowaną fazę.
Model snapshot i job payload są niezmienne: freeze/start/retry zmieniają
wyłącznie fazę/revision/receipts, nigdy nie rozwiązują nowego modelu. Finalny
target-manifest SHA wiąże jawny freeze receipt i start receipt. Cancelled/failed
infer wznawia ten sam zamrożony zakres i istniejące receipts po admission.
Przygotowanie nie wykonuje inference, renderowania ani zapisu geometrii.

### Model i zakres; pilot przed szerszym startem

Kod gry `7` jest odrzucany przed kontrolą konfiguracji, także przy błędnym
formacie V3. Aktualny assignment rozwiązuje istniejący
`SqlAlchemyGridProfileSnapshotResolver._assigned_snapshot`: historyczna baza
może być unpublished i stale evidence nie zdejmuje assignment (D-549).
Wymagane są dostępne, zgodne artefakty i niezmienny snapshot. Jawnie inna
wersja wymaga publikacji oraz aktualnego eligibility dla tej gry. Nie
publikujemy, nie aktywujemy, nie wybieramy default i nie uruchamiamy treningu.
Nowy start porównuje assignment revision z preview w trybie current;
rozpoczęty lub wznawiany infer zachowuje własny pin po późniejszej aktywacji.

Selector domyślnie obejmuje sumę `grid_issue` i odroczonych slotów, z
deduplikacją po wystąpieniu źródła/position_index. `unconfirmed` oraz
`all_automatic` są osobnymi opt-in; unconfirmed nie oznacza niskiego confidence.
Domyślny executionScope to pilot do100 różnych wystąpień zdjęć. Broader
wymaga jawnego wyboru już przy prepare i osobnego broadScopeConfirmed przy
start. Brak limitu po stronie broad nie oznacza automatycznego uruchomienia.

Broader dostaje nowy manifest, a nie rozszerzenie manifestu pilota. Pilot
musi mieć zakończony raport bez błędu infrastrukturalnego; dopuszczalne są
raportowane konflikty, brak poprawy i chronione cele. Potwierdzenie operatora
przypina pilotOperationId, report SHA, aktora i czas. Serwer porównuje signature
gry, kategorii i granic selektora, model/manifest SHA, topologii oraz wersji
bindingu/renderowania/zapisu. Limit100 i konkretne identyfikatory próbki nie
wchodzą do signature; pilot jest próbką tak samo zdefiniowanego zakresu.
Potwierdzenie nie jest PASS modelu ani dowodem jakości.

### Członkostwo, wystąpienie i stabilny kursor

Potwierdzono w `models.py::SourceImageModel` i
`pipeline_store.py::project_source`: source_image_id identyfikuje projekcję
konkretnego importu, z wymaganym import_job_id i file_execution_key oraz
unikalnościami job/checksum i job/execution. `image_file_executions` może być
współdzielone, ale source projection jest wyszukiwana po job/execution.
Cel przypina gameId, importJobId, sourceImageId, fileExecutionKey i
positionIndex; checksum pliku nigdy nie zastępuje occurrence.

Capture zapisuje membership źródeł jednym ograniczonym `INSERT ... SELECT`
w tabeli sources, w snapshotcie tego statementu; SQL timeout30s, błąd wycofuje
cały capture. Nie stosujemy UUIDv4 ani created_at jako high-watermark.
Porządek capture jest deterministyczny: import job, job-file order_index,
source ID; trwały ordinal jest kursorem po zapisie. Do membership wchodzą
wyłącznie istniejące w tym snapshotcie wystąpienia wskazanego zakresu,
z przynajmniej jednym celem pasującym do server-side selektora;
pilot stosuje limit100 źródeł. Nowe źródła nie są dopisywane.

Worker przygotowuje maksymalnie100 źródeł na transakcję, zapisując cele,
ich fences i nextOrdinal atomowo. Prepared finalizuje liczniki i SHA nad
kanonicznym, uporządkowanym manifestem, przy odczycie strumieniowym.
Raport podaje membershipCapturedAt oraz preparationStartedAt/FinishedAt.
Nie deklaruje atomowego snapshotu wszystkich żywych stanów gry: membership
pochodzi z jednego odczytu, fences celów z kolejnych stron. Zmieniony stan
celu po jego stronie przygotowania podlega CAS przy wykonaniu.
Cursor odczytu ma operationId, manifest SHA i ordinal; inna operacja/SHA
daje409. GET nie zmienia fazy ani niczego nie przygotowuje.

Start409 sprawdza globalnie polecenie/key, revision operacji, freeze/manifest
SHA, grę/format, polityki/model oraz current assignment przy pierwszym starcie,
pilot acknowledgement i admission. Nie wykonuje pozornego atomowego skanu
wszystkich targetów. Późniejszy drift źródła/decyzji/owner daje terminalny
`conflict` celu w raporcie. TASK-1003 ma rozróżniać HTTP409 starego
manifestu/polecenia i konflikt żywego celu podczas wykonania.

### Trwały wynik0999 i interfejs do1013

Trzy nowe tabele gry: `grid_reinference_operations`,
`grid_reinference_sources`, `grid_reinference_targets`. Operations przechowuje
jobId, command receipts, scope/pin, fazę/cursor, freeze i pilot ack.
Sources przechowuje membership/ordinal oraz niezmienny sourceResultId,
checkpoint path/SHA i stan inference. Targets przechowuje immutable
targetResultId, zamrożony target, wynik i terminalny domain-write receipt.
Unikalności obejmują operation/source oraz operation/source/position;
każda relacja sprawdza tę samą grę i właściwy import occurrence.

Wynik celu w kontrakcie `grid-reinference-target-result-v1` obejmuje pełną
tożsamość celu, sequence_number, aktywne sloty/topologię, dokładny model/policy
pin, checksumy pliku i znormalizowanych pikseli, wymiary/orientację,
normalization version, aktualny selector geometrii i SHA, workflow revision,
właściciela, fingerprint chronionych decyzji i bieżących zgłoszeń, a także
24 węzły/binding/kwalifikację albo konkretny powód braku wyniku. Zgłoszenie
przypina cell ID, revision i tożsamość bieżących pikseli. Duży source artifact
jest plikiem, w bazie pozostaje path/SHA; brak dużych bitmap w tabelach.

`proposal_ready` oznacza trwały materiał do1013, nie naprawę i jeszcze nie
wiersz grid_geometry_proposals.1013 zapisze unikalną referencję targetResultId
i atomowo utworzy propozycję/zdarzenie bez nowego inference. Przyjęcie sprawdzi
również aktualność problemu i decyzji komórek; sama zgodna geometria nie
wystarcza. Ręczna ścieżka `VirtualGridGeometryService.save_review_item`
pozostaje wyłącznie dla świadomego przyjęcia przez człowieka w1013.

### Automatic write, źródłowe fences i atomowość

Istniejące `save_virtual_geometry_revision` ustawia manual_v1 i human approval;
nie wywołujemy go dla wyniku automatycznego. Oddzielna metoda reużywa wspólny
renderer wirtualny, render manifests i write-through D-462/D-523, bez
approved_geometry_revision, nowej decyzji człowieka i zamykania grid_issue.
Po selected-only zapisie odrębny finalizer0999 w tej samej transakcji używa
czystej qualify_v3_engine_acceptance na wszystkich aktywnych pozycjach.
Operation/job/manifest przypinają niezmienną v3-engine-acceptance-v1. Brak
blockers promuje nową source revision do accepted bez human approval;
partial/deferred/issue/obcy owner/stare selectors lub mieszane bindings
zostawiają needs_review z trwałymi konkretnymi blockers w source/result report.
Nie używamy writera1017 ograniczonego do importowej revision0. Status,
receipt/recompute materialize=False i selected projections są atomowe.
Grid issue zawsze daje wyłącznie trwały wynik do1013. Automatic pomija
zatwierdzoną geometrię i każdą chronioną decyzję komórki; zachowuje historię.
Własny canonical owner nie jest automatycznie obcy: owner tuple musi pozostać
identyczny, a ewentualna synchronizacja jego identity nie może tworzyć ani
udawać nowej decyzji. Obcy owner i utrata aktualności blokują zapis.

Wspólne source fences to plik/piksele, orientacja, normalizacja, attested
range/topologia i przypięte polityki. Ich zmiana konfliktuje całe źródło.
Nie istnieje globalna jedna aktualna source geometry revision: selector
planszy jest parą source_geometry_revision_id/position_index, osobno od jej
workflow revision. Te selectors i decyzje sprawdzamy per target. Nowy pełny
source snapshot musi zachować aktualne geometrie niezmienianych slotów;
ich recognized_boards pointers, manual revisions, cropy i decyzje zostają
identyczne. Ręczna zmiana niewybranego rodzeństwa po freeze jest chroniona.
Jeżeli istniejący globalny kontekst/referencja źródła nie daje się bezpiecznie
scalić z aktualnym stanem, wynik to source conflict; nie zapis starego snapshotu.

Inference i renderowanie wykonujemy poza transakcją domenową. Następnie jedna
transakcja źródła sprawdza wszystkie wybrane cele. Target-local konflikt
pomija ten cel; inne poprawne cele mogą zapisać się w tej samej transakcji
razem z receipt konfliktu. Source-wide fence conflict pomija wszystkie cele.
Wyjątek infrastruktury/projekcji wycofuje wszystkie efekty, receipts oraz
postęp tego źródła. Nie maskujemy go jako konfliktu domenowego.
Recompute używa materialize=False; synchronizacja obejmuje wyłącznie frozen
targets. Nie używamy bezwarunkowego source-wide materialize/repoint helpera.
Identyczny wynik daje unchanged, nigdy naprawę. Pozostałe terminalne wyniki:
automatic_written, proposal_ready, protected, conflict, binding_required,
inference_timeout i failed. Anulowanie zachowuje ukończone receipts; wynik
niedokończonego celu nie jest udawanym sukcesem.

### Admission, blokady i limity wykonania

Wspólna transakcyjna blokada admission per gra poprzedza sprawdzenie kolizji
i publikację created joba. Symetrycznie uczestniczą starty i każde retry/resume
grid reinference, obrazowego IMPORT, VALIDATE/page_geometry_preflight,
geometry rollout backfill, symbol training, symbol reinference, symbol bulk
oraz symbol review backfill. Nie przebudowujemy algorytmu treningu symboli.
Blokują created/processing, także created/waiting_for_storage i processing
z cancellation request. Waiting_for_review po oddaniu lease nie blokuje;
gotowy kandydat symboli nie jest aktywnym runem. Wznowienie każdej ścieżki
musi ponownie przejść admission przed created. Generic job i file retry
otrzymują ten sam guard; sam nowy endpoint0999 nie wystarcza.

Komendy blokują w kolejności: command-key advisory, katalog9910994 jeśli
potrzebny do pin/eligibility, admission, job row FOR NO KEY UPDATE, operation.
Replay odczytuje receipt po serializacji key przed CAS. Worker zaczyna od
obowiązującej blokady lease joba, potem operation, EXCLUSIVE ownership,
projection/game guard, ascending sequence locks, ascending source rows,
board/pending/review/canonical, counters i cells. Nie blokuje joba ponownie
po ownership. Freeze i pilot ack nie pobierają ownership ani nie blokują
źródeł. Cancel/resume zachowują porządek admission/job/operation; generic
cancel synchronizuje operation przy już trzymanym job lock, bez późniejszego
admission/ownership. Receipt freeze/start/ack i zmiana fazy są atomowe.

Membership SQL ma30s; strony buildera100 źródeł; runtime trzyma jedno zdjęcie
i do9 slotów. Lock timeout5s, statement timeout30s. Wersjonowana polityka
`grid-reinference-runtime-v1` przypina source deadline30s zgodnie z obecnym
preflightem, nie jako deklarację pomierzonej wydajności. Istniejący
CPUGridProposalRunner utrzymuje jeden kontrolowany proces modelu między
zdjęciami; heartbeat, cancel, deadline i close sprzątają transport/proces.
Timeout ma trwały jawny wynik; brak automatycznej pętli ponowień. Crash przed
checkpointem może powtórzyć fizyczne obliczenie, receipt wyklucza duplikat
zapisu. Checkpoint poprzedza domain write. Binding nigdy nie zwija brakującego
środkowego slotu; brak bezpiecznego bindingu daje binding_required.

### Schemat i granice operacyjne

Statyczny odczyt AST wszystkich revision/down_revision potwierdził jedną głowę
`0158_new_game_v3_bootstrap`; nie łączono się z bazą. Proponowana migracja
`0159_grid_reinference`, parent0158, dodaje trzy partycjonowane tabele gry,
FK/unique/check/index i frozen manifestv12. Nie zmienia frozenv1–v11.
Wszystkie trzy tabele wchodzą do GAME_TABLES, CREATE_TABLES, MIGRATE_TABLES,
DELETE_TABLES i PARTITIONED_TABLES; nie do katalogu public/shared. Migracja
obejmuje rodziców w game_data_v2, partycje istniejących gier, manifest_version,
RLS game scope, grants i kolejność zależności lifecycle. Jawny bind WRITE
poprzedza zapis; identyfikator innej gry nie może odczytać operacji ani wyniku.
ORM rejestrowany centralnie, startup schema guard i consumers manifestu
przechodzą na v12. Downgrade fail-closed przy danych nowych tabel, bez utraty
receipts. Migracja/testy wyłącznie na małych izolowanych fixture z potwierdzonym
owner/PID/DB/role cleanup; bez migracji operatora, backupu/snapshotu, usług,
real inference/training/GPU, historycznego backfillu i integracji.

### Zgodność z cleanupem po doprecyzowaniu D-551

Przyjęte przez leada przed zmianą schematu i cleanupów 2026-10-15: frozen
`source_image_id` pozostaje niezmienną tożsamością manifestu bez fizycznego
FK; oddzielne nullable `live_source_image_id` ma same-game FK RESTRICT oraz
CHECK zgodności z frozen ID. Żywy link nie należy do manifest SHA. Zwykłe
usuwanie źródeł, usuwanie superseded importów, usuwanie nieużytego browser
stagingu oraz layout-data reset jawnie odpinają wyłącznie live link w swojej
istniejącej transakcji i zachowują trzy tabele historii, joby, checkpointy,
wyniki i piny. Preview pokazuje zachowanie historii i odłączenie zdjęć;
pozostałe FK, guardy i potwierdzenie/CAS pozostają obowiązujące. Rollback
przywraca link. Nie ma automatycznego podpinania ponownie. Brak linku lub
źródła daje `source_missing`, bez inference ani odtworzenia zdjęcia/celu.
Layout-data reset zachowuje joby zgodnie z istniejącym kontraktem; pełne
usunięcie gry pozostaje osobnym lifecycle. Regresje obejmują rollback,
niezmienną historię i izolację drugiej gry.

### Jedna runda korekt po audycie R1

R1 REVISE (`TASK-0999_AUDIT_claude-fable-5-1_R1.md`) zachowano bez zmian.
Lead przed kodem doprecyzował D-551/plan: enqueue/start/retry/resume nadal
CREATED+PROCESSING; worker claim/recovery PROCESSING innych ID. Scan ma bound
100 i osobną krótką session/transakcję per kandydat, z admission przed job row
lock, ponownym CAS i diagnostyką skip. Neutralny kod to
`GAME_JOB_ADMISSION_CONFLICT`. Globalny unique execution slot pozostaje.

Dalszy zapis D-551 przed kodem kwarantanny pozwala wyłącznie udowodnione
START_REQUIRED nowego grid-reinference-v1 w CREATED albo rzeczywiście expired
PROCESSING zamienić na FAILED/executionQuarantine i zwolnić lease/slot.
Istniejące recover_expired_job waliduje expiry; nie wywołujemy fail_job na
wygasłym tokenie. Cancel ma pierwszeństwo. Frozen dowody pozostają identyczne,
a flaga blokuje generic retry/resume także prepare. Konieczna jest nowa jawna
operacja freeze/start. Sto wyłączonych trwale kandydatów nie zasłania
prawidłowego joba za limitem w następnym bounded wywołaniu.

Cancellation checkpoint działa na granicach stron/źródeł i kontrolowanego
runnera, zachowuje postęp/receipts i zamyka runner bez kolejnych zapisów.
Fingerprinty owner/pending pomijają operational timestamps/counters;
foreign live pending bez canonical jest chroniony przed mutacją.
Cancel failed ma typowany phase conflict. Nowy test produkcyjnego model()
nie nadpisuje tej metody; obejmuje resolver/eligibility, assignment CAS,
resume pin oraz rzeczywistą paginację/kursor SQL. Pełny wcześniejszy reset
FAIL pozostaje bez xfail i bez niezatwierdzonego rozszerzenia.

### Ograniczona poprawka R2-P1-1 przed R3

Po zgodzie operatora i release leada zmieniamy wyłącznie payload granicy
anulowania. Gdy checkpoint nie ma poprawnego schema_version=1, handler buduje
v1 z workflow grid-reinference-v1, fazą wynikającą z zachowanego stage i cursorem
równym bieżącemu progress_current. Istniejący poprawny checkpoint pozostaje
identyczny. Nie zmienia to checkpointu źródła, receipts, modelu ani operacji.
Workerowy test granicy deleguje do rzeczywistych renew_job_lease,
checkpoint_job i acknowledge_job_cancellation. Oba scenariusze PG sprawdzą
utrwalone schema/stage/cursor oraz brak store.fail i reconciliation gałęzi
awarii, zachowując wcześniejsze asercje restartu i receipts. Zmieniane pliki:
handler workera, jego istniejący test, istniejący test PG, własny task i sekcja
State oraz nowa odpowiedź R2. Bez zmian kolejki, domeny jobów lub schematu;
R2-P2-1/2 i wcześniejszy reset pozostają jawnymi ograniczeniami.

## Expected files

- Istniejące: [image_review_repository.py](../../../services/api/src/game_predictor_api/storage/image_review_repository.py) — ochrona decyzji człowieka, licznik korekt.
- Istniejące: [jobs.py](../../../services/api/src/game_predictor_api/application/jobs.py) — preflight, snapshoty, admission i start zadań.
- Pozostały zakres wskazany w zaakceptowanym planie: istniejące blokady własności i runtime geometrii; nowe proponowane `services/api/src/game_predictor_api/application/grid_reinference.py`, `services/api/src/game_predictor_api/storage/grid_reinference.py`, `services/worker/src/game_predictor_worker/images/grid_reinference_handler.py` oraz migracja receipts.

Wymienione moduły zostały wdrożone w tym tasku. Końcowy manifest plików i dowodów znajduje się w `artifacts/audits/TASK-0999_IMPLEMENTATION_EVIDENCE.json`; kod ogranicza się do tego pionu i uzgodnionej zgodności cleanupu.

- Nowy proponowany test pionu: `services/api/tests/test_grid_reinference_backend.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

- Nowe: `schemas/grid_reinference.py`, `storage/grid_reinference_models.py`,
  `storage/job_admission.py`, `storage/game_data_v2_manifest_v12.py`,
  `services/api/alembic/versions/0159_grid_reinference.py`,
  `services/worker/tests/test_grid_reinference_handler.py`,
  `services/api/tests/integration/test_grid_reinference_postgres.py`,
  `packages/admin-api-client/test/grid-reinference-request.test.mjs`.
- Istniejące: `api/image_reviews.py`, `schemas/jobs.py`, `domain/jobs.py`,
  `storage/job_repository.py`, `storage/image_job_repository.py`,
  `storage/symbol_model_iteration_repository.py` i wszystkie potwierdzone
  kolidujące enqueue/resume wejścia; wspólny admission guard.
- Istniejące: `storage/virtual_grid_geometry_repository.py` — oddzielny automatic
  writer; `storage/image_symbol_review_repository.py` — wyłącznie konieczny
  selected-target write-through, z zachowaniem dotychczasowych defaultów.
- Istniejące: `storage/models.py`, `storage/game_storage_routing.py`,
  `storage/game_partition_lifecycle.py`, `storage/catalog_repository.py`,
  `storage/schema_readiness.py` i testy manifest/lifecycle/routing/schema.
- Istniejące: worker `cli.py`, `jobs/store.py`, `jobs/runtime.py` — dispatch,
  przygotowanie waiting boundary i trwałe fazy, bez nowej kolejki.
- Istniejące: `packages/admin-api-client/openapi/openapi.json`,
  `packages/admin-api-client/src/generated/`, `packages/admin-api-client/src/index.ts`
  oraz właściwy wrapper w `apps/admin/src/api/admin-api-client.ts` jeśli wymagany.
  Pełny pion backend/OpenAPI/generated client/wrapper/request test jest obowiązkowy.
- Dokumentacja zachowania/własności/API, mapa kodu i raport audytu zostaną
  zmienione dopiero po release implementacji. Metadata innych tasków prowadzi lead.

- Dodatkowe zgodne wejścia cleanup: `storage/grid_reinference_retention.py`,
  `storage/cleanup_repository.py`, `storage/superseded_import_image_removal_repository.py`,
  `storage/browser_staging_retention_repository.py`; istniejące widoki cleanup
  otrzymują wyłącznie czytelne etykiety nowych informacji.
- Regresje: `services/api/tests/integration/test_grid_reinference_postgres.py`,
  `services/worker/tests/test_grid_reinference_handler.py`,
  `packages/admin-api-client/test/grid-reinference-request.test.mjs`,
  `apps/admin/test/grid-reinference-cleanup-labels.test.mjs`.
- Po R1: `services/api/tests/test_grid_reinference_models_and_cursor.py`,
  wąskie pure domain quarantine przejście oraz rozszerzone testy worker/PG.


## Test cases

- Aktualna baza działa bez treningu.
- Chronione decyzje pozostają identyczne.
- Brak środkowego slotu nie przesuwa sekwencji.
- Restart nie dubluje zapisu; identyczny wynik nie jest „naprawą”.
- Prepare lost reply odtwarza ten sam operation/job; crash przed/po capture i
  między stronami zachowuje membership/cursor; finalizacja oraz oddanie lease
  są atomowe. Freeze/start/ack retry odtwarza receipt; zmienione body daje409.
- Generic retry_job/retry_file po przygotowaniu bez start receipt daje typed
  START_REQUIRED, także przy samym freeze lub brakującym pilot ack. Restart
  prepare zachowuje input model/cursor; freeze/start/retry nie zmieniają
  model snapshotu/payloadu. Cancelled/failed infer zachowuje ten sam manifest
  SHA, przypisane receipts i autoryzację startu oraz ponawia admission.
- Nowe źródło z mniejszym UUID między stronami nie trafia do membership;
  paginacja nie duplikuje celów. Inna gra/manifest/cursor daje błąd zakresu.
- Current unpublished historical assignment działa bez treningu; jawnie inna
  nieopublikowana albo ineligible per gra wersja blokuje. Kod7 zawsze blokuje.
  Zmiana assignment przed startem konfliktuje; później job zachowuje pin.
- Pilot<=100, fresh broader manifest, signature bez limitu/próbki; bez ack
  aktora/report SHA i jawnego broader confirmation brak startu. Ack nie jest PASS.
- Każda para colliding start/resume w obu kierunkach przechodzi wspólny guard;
  waiting human review i candidate_ready nie blokują, created/storage wait oraz
  processing cancellation blokują. Generic retry i file retry nie omijają guard.
- Własny owner bez ochrony nie jest mylony z obcym; obcy canonical nie jest
  przejmowany. Human geometry, etykiety oraz grid_issue pozostają identyczne.
- Ręczna korekta niewybranego rodzeństwa po freeze zachowuje jego geometrię,
  selector, cropy, human decisions i canonical owner; niemożliwy merge źródłowego
  kontekstu daje source conflict. Nie uruchamia się source-wide repoint/materialize.
- Dwa wybrane cele, jeden target conflict: drugi może zapisać się z receipts
  i postępem atomowo. Source provenance drift konfliktuje oba. Błąd projekcji
  wycofuje geometrię, receipts i cursor całego źródła.
- Jeden source checkpoint zasila wszystkie wybrane sloty; restart/lost reply
  nie dubluje zapisów; brak środkowej detekcji nie zmienia sequence_number.
  Timeout pozostaje timeoutem, cancel sprząta runner i nie cofa receipts.
- Proposal-ready wynik z pinami/fences trwa po restarcie bez tabel1013;
  nie zamyka zgłoszenia ani nie tworzy approval. Zmiana problemu/decisions jest
  widoczna w fences dla przyszłego przyjęcia1013.
- Migracja0159/v12: upgrade, istniejące i nowe partycje, CRUD/RLS dwóch gier,
  central ORM w obu porządkach importów, lifecycle create/migrate/delete i
  fail-closed downgrade. Dawne frozen manifesty pozostają identyczne.

## Verification

Zakres: API, WORKER, MIG, renderer parity, OpenAPI, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run openapi:check
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_virtual_grid_geometry.py services/api/tests/test_operational_image_reviews.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_neural_folder_correction_pipeline.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez automatycznego przejęcia kanonu i uruchamiania pełnej gry.

## Outcome

### Execution phase

- Faza: implementacja po release leada2026-10-15; D-551 accepted i kontrakt zapisane przed kodem.
- Baza taska: v1.7.378 / `d078938b18abdff5d6e1f99795f9d4aca09716b1`.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream bazowy: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit R1: `claude-fable-5-1`/high **REVISE** (3 P1 + 5 P2); raport zachowano bez zmian. Wykonano jedną zleconą rundę korekt; niezależny R2 high/do1200s prowadzi lead.
- [Odpowiedź na wszystkie 8 uwag](../../quality/TASK-0999_CORRECTION_CODEX.md); P2-1 pozostaje jawnym ograniczeniem wcześniejszego resetu, bez xfail i bez rozszerzenia zakresu.
- Następny krok: niezależny audyt Claude high/do1200s prowadzony przez leada; bez samodzielnego audytu, stage i commita wykonawcy.

### Changed

- Wdrożono jeden trwały job prepare/infer, membership INSERT SELECT, bounded
  preparation, stabilny manifest/kursor, jawne freeze/start/pilot acknowledgement
  i idempotent receipts. Model, runtime i acceptance policy są niezmiennie
  przypięte; retry/recovery nie zastępuje autoryzowanego startu.
- Automatic writer używa produkcyjnego renderera i wyłącznie selected-only
  zapisu/projekcji, bez human approval, manual_v1, globalnego repoint i
  bezwarunkowego materialize. Oddzielny finalizer D-550 nadaje accepted albo
  needs_review z konkretnymi blockerami; source checksum/payload nie zmienia
  się przy zmianie statusu. Grid issue daje wyłącznie trwały proposal_ready.
- Admission jest symetryczne dla geometrii i symboli, obejmuje starty,
  retry/resume, claim i recovery. Current assignment działa bez treningu;
  inne wersje korzystają z istniejącej per-game eligibility/publication.
- MIG0159/frozenv12 dodaje trzy game-owned tabele i komplet ORM/RLS/lifecycle.
  Frozen identity/history pozostają po cleanupie; cztery istniejące wejścia
  odpinają wyłącznie live link w tej samej transakcji, bez autoreattach.
  Uzupełniono backend, OpenAPI, generowany klient, wrapper i request tests oraz
  czytelne etykiety istniejących preview cleanupu.

### Verification results

Każda komenda miała twardy limit do120s. `PYTHONPATH` wskazywał wyłącznie
worktree `services/api/src`, `services/worker/src`, `test_support`, a dla PG
również `services/api/tests` i `services/api/tests/integration`.

- Focused API/worker/runtime: **37 PASS**; obejmuje lost reply, namespaces,
  freeze/start/retry/pilot acknowledgement, chronione owner/decisions, bieżące
  kontra historyczne grid issue, checkpoint corruption, deduplikację po
  restarcie, timeout i normalization fences. HTTP TestClient działał w
  uzgodnionym scoped wyjątku od sandbox Proactor/socketpair hang; bez usług.
- Wspólne regresje `test_virtual_grid_geometry`, repository, operational
  reviews, grid review domain, D-550 i neural folder correction: **102 PASS**
  (44.36s). Zachowano defaulty manual workflow i brak kompakcji środkowego slotu.
- Rejestr modeli/publication/activation/snapshot resolver: **38 PASS** (25.81s),
  bez rzeczywistych operacji modelowych ani inference.
- Izolowany PG: **11 PASS, 1 deselected** (80.15s), po wcześniejszym pełnym
  przejściu **8 PASS / 1 FAIL** (76.11s). Jedyny FAIL to niezależny wcześniejszy
  layout-data reset graph opisany poniżej; nie zmieniono go na PASS ani xfail.
  Dodatkowe dwa PG przypadki unchanged i global source selector conflict:
  **2 PASS** (38.85s). Admission/retencja były także osobno **3 PASS** (40.47s).
- PG używał jednej własnej losowej DB/roli na grupę. Fixture potwierdza owner,
  brak aktywnych PID i usuwa wyłącznie własną DB/rolę; każda zakończona próba
  ma cleanup bez błędów, a końcowy receipt ma `phase=cleaned`, `pids=[]`,
  `databaseRemaining=0`, `roleRemaining=0`. Schema helper sprawdził v11→v12,
  empty downgrade/upgrade, retained-history downgrade refusal, RLS i lifecycle.
- Ruff wszystkich zmienionych Pythonów i mypy **33 modułów źródłowych PASS**.
  Schematowy wykonawca dodatkowo potwierdził focused schema/lifecycle/startup
  oraz fresh-process import orders (dowód `TASK-0999_SCHEMA_EVIDENCE.json`).
- OpenAPI generate/check **PASS**, klient build **PASS**, request transport
  **2 PASS**, istniejące cleanup UI/regresja etykiet **4 PASS**, Admin typecheck
  i scoped ESLint **PASS**. Scratch TEMP generatora skierowano do worktree po
  sandbox EPERM w katalogu tymczasowym; bez zmiany konfiguracji hosta.
- Mapa kodu została zregenerowana. Końcowe docs/map/diff checks i pełny manifest
  dowodów są zapisane w `TASK-0999_IMPLEMENTATION_EVIDENCE.json`.

### Correction verification after R1

- Focused real model/cursor/API/worker/runtime: **48 PASS** (14.77s), w tym
  15 nowych testów rzeczywistego model() bez nadpisywania metody.
- Nowe PG cancellation/late-source/foreign-pending/queue/quarantine: **7 PASS**
  w grupie7/1; jej jedyny FAIL dotyczył schema_version fixture admission.
  Po korekcie wyłącznie fixture pojedynczy admission: **1 PASS** (32.30s).
  Osiem docelowych regresji przechodzi; wcześniejsze błędy fixture zachowano
  oddzielnie w logach, nie przedstawiono ich jako PASS.
- Worker claim używa osobnej krótkiej Session/transakcji per kandydat, bound100,
  admission przed row lock, skip/diagnostyki i existing unique slot. Enqueue
  nadal blokuje CREATED+PROCESSING; execution blokuje PROCESSING innych ID.
  Kwarantanna udowodnionego START_REQUIRED waliduje real expiry, zachowuje frozen
  dowody i zwalnia slot; cancel ma pierwszeństwo. Retry/resume wymaga nowej
  operacji po kwarantannie, również dla prepare. Test101 invalid→valid przechodzi.
- Cancel checkpoint zachowuje cursor/receipts i zamyka runner bez dalszych
  zapisów. Fingerprint pomija operational timestamps/counters; foreign live
  pending jest chroniony przed mutacją. Cancel failed ma typed phase conflict.
- Ostatni własny PG receipt: cleaned, brak aktywnych PID, DB=0, role=0.
  Ruff/format48 PASS, mypy33 PASS (57.849s, właściwy follow-imports=silent),
  pełne OpenAPI/check, docs/mapa/diff PASS; SHA są w implementation evidence.
  Zachowano wyniki niezmienionych kontroli; bez powtarzania szerokich zestawów.

### Not completed / limits

- **Preexisting FAIL: pełny layout-data reset.** Dotychczasowe
  `_GAME_RESET_STATEMENTS` usuwa `image_review_items` przed
  `image_symbol_review_cells`; FK RESTRICT blokuje reset istniejącej gry z
  takimi komórkami. Tuple pozostał semantycznie identyczny z HEAD. Nowy detach
  wykonał się w tej samej transakcji i rollback przywrócił live link; odbiór
  pełnego resetu pozostaje ograniczony tym wcześniejszym błędem. Lead prowadzi
  odrębny zakres/zgodę i ewentualny osobny task/commit. Test pozostaje FAIL.
- Brak real inference/training/GPU, benchmarku30s, usług, operatorDB, migracji
  operatora, backfillu, backupu/snapshotu, integracji, push i aktywacji modelu.
- Audyt, stage, commit, status done i przeniesienie taska wykonuje lead po
  niezależnym review; wykonawca nie deklaruje ich ukończenia.

### Documentation updates

- Technical notes, Expected files, Outcome i wyłącznie własna sekcja
  CURRENT_STATE; API_CONTRACT, VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP i mapa kodu.
  Root-owned README/plan/decision logs/pozostałe sekcje State nie były edytowane.

### Recommended next task

- TASK-1013, po audycie i commicie TASK-0999 prowadzonych przez leada.


### Lead disposition after R2 — blocked, 2026-10-15

- Execution phase: oczekiwanie na decyzję operatora po jednej rundzie poprawek; bez dalszej implementacji, audytu, stage lub commita.
- R2: [Claude high](../../quality/TASK-0999_AUDIT_claude-fable-5-1_R2.md), REVISE; rzeczywisty czas 713.771s przy limicie1200s. Audytor pracował statycznie i nie uruchamiał testów. Lead potwierdził po audycie zgodność wszystkich72 zamrożonych plików i20 dowodów z SHA w artifacts/audits/TASK-0999_R2_SCOPE.json. R1 i odpowiedź wykonawcy pozostają historycznymi dowodami, bez zmiany werdyktu.
- R1 P1-2/P1-3 i P2-2/3/4/5 zamknięte przez R2. R1 P1-1 zamknięte co do skutku, ale R2 wykrył wadliwy mechanizm potwierdzenia cancel.
- Otwarte R2-P1-1: cancellation_boundary przekazuje {} do domenowego checkpoint_job, zamiast payloadu z schema_version1. Końcowy cancelled osiągany jest dopiero przez awaryjną ścieżkę store.fail; nowy test musi odróżniać potwierdzenie checkpointem od obsługi błędu. Nie wprowadzono jeszcze proponowanej poprawki.
- R2-P2-1: nieobsługiwany brak operacji lub niedostępny magazyn może przerwać claim; zapisano ryzyko niespójnego stanu poza zwykłym przebiegiem, bez maskowania błędów infrastruktury ogólnym catch. R2-P2-2: obcy żywy item może nadmiernie chronić własny kanon; fail-closed, bez nadpisania danych. Oba ograniczenia pozostają jawne do dalszej dyspozycji; brak dodatkowego kodu. R1 P2-1: niezależny reset nadal FAIL; pytanie operatora o osobny zakres pozostaje otwarte.
- Dokładny następny krok: uzyskać zgodę operatora na dodatkową, ograniczoną rundę R2-P1-1 (payload checkpointu + test rzeczywistej walidacji + audyt zmienionego fragmentu Claude high/do1200s). Bez zgody nie rozpoczynać tej poprawki ani TASK-1013. AGENTS: otwarte P0/P1 po jednej rundzie poprawek zatrzymują task; brak raportu PASS nie jest PASS.
- Commit/version: brak nowego commita; HEAD nadal v1.7.378 / d078938b18abdff5d6e1f99795f9d4aca09716b1. Bez zmian danych operatora/usług.


### Operator-authorized continuation after R2 — 2026-10-15

Operator polecił: „kontynuuj pracę jak wcześniej zadanie po zadaniu autonomicznie - rób audyty z claude code”. To zgoda na zaproponowaną dodatkową rundę naprawy R2-P1-1 i kontrolny audyt R3 Claude high/do1200s, następnie dalsze taski zaakceptowanego planu. Historyczny blocker pozostaje powyżej jako zapis zdarzenia. Execution phase: poprawki audytu. Zakres: payload checkpointu v1, realna walidacja domenowa oraz regresja odróżniająca cancellation od gałęzi awarii; bez zmian niepowiązanego resetu i bez operacji operatora. Otwarte P2 z R2 pozostają jawnymi ograniczeniami. Raporty R1/R2 są niezmienne. Po kontroli R3 nadal nie commitować z otwartym P0/P1; nie deklarować wyników przed wykonaniem.


### Verification of operator-authorized R2-P1-1 correction

- Execution phase: oczekiwanie na ograniczony audyt R3; bez commita.
- Handler buduje prawidłowy payload checkpointu v1 z workflow/phase/cursor;
  istniejący poprawny checkpoint pozostaje identyczny. Zachowuje stage i
  liczniki, nie zmieniając trwałych receipts/cursora operacji ani modelu.
- Regresja rzeczywistej domeny przed poprawką odtworzyła dokładny błąd
  UNSUPPORTED_JOB_CHECKPOINT_VERSION (1 FAIL/1 PASS). Po poprawce worker suite
  9 PASS (2.90s); prawdziwe checkpoint_job i acknowledge_job_cancellation
  wykluczają poprzedni fałszywy wynik testowego store.
- Dwa rzeczywiste PG cancel_prepare/cancel_between_sources: 2 PASS (44.55s).
  Wymagają utrwalonego checkpointu v1/stage/cursor i braku store.fail oraz
  failure reconciliation, zachowując wcześniejsze asercje resume/receipts.
  Własna DB/rola usunięte po owner/PID checks; cleaned, PID[], DB0/role0.
- Ruff/format trzech zmienionych Pythonów PASS; mypy handlera PASS (43.705s,
  follow-imports=silent, 2515 zależności, 0 errors). Pierwszy timeout55s
  rozliczono oddzielnie; brak osieroconego PID, bez zmiany reguł typów.
- [Odpowiedź na R2](../../quality/TASK-0999_R2_CORRECTION_CODEX.md) i nowy manifest
  TASK-0999_R3_IMPLEMENTATION_EVIDENCE.json zawierają dokładne SHA, kontrole,
  ograniczenia i następny krok. Raporty R1/R2 oraz poprzednia odpowiedź
  wykonawcy pozostają niezmienione. R2-P2-1/2 i wcześniejszy reset nadal jawne;
  bez zmian kolejki/domeny/schematu lub danych operatora. Lead prowadzi R3.


### Lead closure — final R3 PASS, 2026-10-15

- Execution phase: gotowe do osobnego commita v1.7.379; oczekiwanie na integrację całego planu. Wszystkie kryteria taska rozliczono; brak otwartych P0/P1. Wcześniejsze sekcje blocked/R1/R2 dokumentują historię, nie bieżący status.
- [Claude high R3 PASS](../../quality/TASK-0999_AUDIT_claude-fable-5-1_R3.md), rzeczywisty czas254.241s przy limicie1200s. Dodatkowa poprawka i R3 zostały jawnie zatwierdzone przez operatora po R2. R1/R2 i odpowiedzi wykonawcy zachowano bez zmiany werdyktów. Lead sprawdził po audycie73 źródła i15 dowodów SHA; brak driftu. Audyt był statyczny, bez wykonania testów przez Claude.
- Zamknięte wszystkie P1: model/kursor/admission w R2; realny checkpoint anulowania w R3. Test R3 odtworzył przed poprawką1FAIL/1PASS; po poprawce worker9PASS i rzeczywiste PG cancel2PASS bez store.fail/reconciliation. Ruff/format3, mypy handlera, docs/map/diff PASS. Pozostałe niezmienione dowody R1/R2 pozostają ważne w swoim zakresie; nie sumujemy nakładających się zestawów.
- R3-P2-1 przyjęte: payload checkpointu może po drugim anulowaniu zawierać wcześniejszą diagnostyczną phase/cursor. Wznowienie używa trwałych pól operacji, a nie tego payloadu; poprawny istniejący checkpoint celowo zachowano. Bez dodatkowej zmiany zachowania po PASS.
- R2-P2-1 przyjęte jako ograniczenie niespójnego joba/niedostępnego magazynu: claim może przerwać próbę. Poprawne utworzenie jest atomowe, zwykłe kolejki mają regresje. Nie maskowano infrastruktury catch-all i nie raportuje się naprawy tej sytuacji.
- R2-P2-2 przyjęte: konserwatywna ochrona obcego live item może pominąć własny cel, ale nie przejmuje właściciela ani nie zmienia chronionych danych; ręczna korekta pozostaje dostępna. R1-P2-1: pełny reset nadal jawny wcześniejszy FAIL przez FK; brak xfail, rozszerzenia resetu lub wykonania go na danych operatora. Detach/rollback własnych relacji sprawdzono oddzielnie.
- Własne fixture PG cleaned: owner potwierdzony, PID[], DB0/role0. Bez operatorDB, nowego backupu/snapshotu, usług, rzeczywistej inferencji/treningu/GPU, aktywacji, push i integracji.
- Kontrole staged check/stat/list i post-commit show/status prowadzi lead. Commit v1.7.379 przygotowany; pełny hash zostanie dopisany po utworzeniu, bez amend i bez samoodwołania.
- Następny task: TASK-1013 po commicie0999 i utrwaleniu kontraktu propozycji. Root odpowiada za README, plan, decyzje, posthash1011 i księgowość okna stanu; wykonawca zmieniał własny pion i sekcję0999.


### Post-commit record

- Commit: **v1.7.379 / `62e9f71986a74d67776eabad6e99154f4d18c0b2`**. Staged check/stat/list i post-commit show/status PASS;79 plików, worktree czysty bezpośrednio po commicie. Hash zapisano po utworzeniu, bez amend. Nadal bez scalenia/push; ten zapis dokumentacyjny wejdzie do kolejnego taska.
