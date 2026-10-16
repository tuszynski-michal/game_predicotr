---
title: TASK-1002 — Nagrania, aliasy i role kontrolne
status: done
last_updated: 2026-10-16
---

# TASK-1002 — Nagrania, aliasy i role kontrolne

## Status

`done`

## Goal

Zapobiec przeciekowi między treningiem i oceną.

## Context

Task jest częścią zaakceptowanej rewizji 6. Pochodzenie i niezależność nagrań. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0994.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. pochodzenie danych między grami i rodzinami.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../../architecture/VISION_LAB.md).
- [VISION_LAB](../../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: VISION_LAB, D-480/D-527, reguły kohorty tego planu.

- [D-480](../../process/decisions/DECISION_LOG_2026.md#d-480--zatwierdzona-geometria-produkcyjna-777-jako-dane-uczące-geometrii-zmienia-d-453) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-527](../../process/decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

- [D-554](../../process/decisions/DECISION_LOG_2026.md#d-554--nagrania-i-ochrona-danych-kontrolnych-geometrii-v3) — kontrakt przed kodem, wąskie capability i trwałe role.
- [Nagrania V3 — wdrożenie i praca operatora](../../guides/SOURCE_RECORDING_GROUPS.md).

## Scope

- Trwałe grupy nagrań, deklaracje operatora, aliasy, byte/pixel SHA, TRAIN/VALIDATION/REGRESSION i wyłączenia przodków.
- Folder jest sugestią, nie dowodem niezależności.

## Out of scope

- Bez przenoszenia plików źródłowych i zmiany sekwencji.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Alias w innej grze zachowuje rolę.
- [x] Holdout rodzica nie trafia do TRAIN dziecka.
- [x] Brak deklaracji nie daje niezależności.
- [x] Role przeżywają restart.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Trwałe grupy nagrań, deklaracje operatora, aliasy, byte/pixel SHA, TRAIN/VALIDATION/REGRESSION i wyłączenia przodków. Folder jest sugestią, nie dowodem niezależności.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

### Kontrakt wykonawczy przed kodem — 2026-10-15

Poniższe doprecyzowanie realizuje zaakceptowane sekcje2.6/4 i TASK-1002
planu, D-480/D-527/D-549. Nie łączy modeli symboli. Zgoda na mechanizm
nie upoważnia do migracji bazy operatora ani rejestracji jego zdjęć.
Wykonawca gpt-6.1-sol/high; niezależny Claude high, do1200s.

#### Źródła prawdy i trwałość ról

Jedyny nowy rejestr dotyczy geometrii V3. Grupa identyfikuje całe nagranie,
nie folder, zakres numerów, grę ani rodzinę modelu. Wystąpienie zachowuje
własne pochodzenie także przy identycznych pikselach. Serwerowe byteSHA
oraz pixelSHA z przypiętym algorytmem i wymiarami dowodzą aliasów;
brak trafienia nie dowodzi niezależności. Jawna deklaracja operatora wiąże
cały sprawdzony manifest nagrania. Niepełne członkostwo/deklaracja lub
nieznane pochodzenie oznacza unresolved, nigdy pustą listę wyłączeń.

Role TRAIN/VALIDATION/REGRESSION są przypisane do rodziny i grupy, lecz
ochrona jest domknięta przez aliasy między grami i przodków. Nieużywaną
błędną deklarację można poprawić/cofnąć przez CAS i zdarzenie; nie kasujemy
historii. Freeze resolution jest dowodem prowizorycznym, nie zużyciem
etykiet. Trwała ochrona zaczyna się przy udanym zamrożeniu kohorty kontrolnej,
zaufanym imporcie permanentnego holdoutu, rzeczywistym użyciu do oceny
lub odziedziczonej ochronie. Użycie TRAIN także zachowuje dowód pochodzenia.
Zwykła korekta nie usuwa ochrony ani nie rozdziela jej poza komponent aliasów.
final_test/unseen_game/Reels/Treasure i inne zapisane holdouty nigdy TRAIN.
Brak adaptera przodka nie oznacza pustych wyłączeń. Deskryptor Mumii
recordingIdentityAvailable=false potwierdza zdjęcia, nie niezależność filmu.

#### Minimalny magazyn i skala

Proponowane pięć współdzielonych tabel public: recording_groups,
recording_occurrences, recording_evidence, recording_role_heads,
recording_commands. Bez ogólnego silnika grafów i osobnych tabel stanu
globalnego/resolution. Zdarzenia mają zamknięte typy membership/alias/
declaration/retraction/resolution/use/holdout/ancestor/invalidation,
kanoniczny payload/SHA i indeksowany monotoniczny ordinal. Provisional
resolution zapisuje zależne group IDs w indeksie GIN, model/provider
references i relevant proofSHA. Role head: family/group/revision/event.
Ledger: game/kind/key UUID, bodySHA, zaufany actor i niezmienny receipt.

Domknięcie odwiedza wyłącznie osiągnięte grupy oraz indeksy byteSHA i
(pixelAlgorithm,pixelSHA), także niewybrane aliasy i zachowaną ochronę.
Jawne limity rozmiaru/głębokości oraz timeout dają unresolved, bez obcinania
wyniku do pozornego sukcesu. Nie skanujemy wszystkich zdjęć gry w GET.
Ordinal globalny jest tylko płotem konkurencji. Zmiana innej gry lub
niepowiązanego wystąpienia nie unieważnia modeli/defaultów.

Operator wybiera import/range/filter, otrzymuje dokładny frozen manifest
membership z ordinal/SHA, deklaruje film i niezależność raz dla tego zakresu.
Rejestracja ma strony maksymalnie200 elementów, page/key/CAS receipts oraz
wznowienie po reload. Członkostwo staje się kompletne dopiero po weryfikacji
całego manifestu; duże manifesty są plikami managed z SHA, nie obrazami w DB.
Istniejące metadane o nieudowodnionym pochodzeniu nie są zaufanym pixelSHA.
Brak zaufanej tożsamości pokazuje własne unresolved counts. Nie wykonujemy
autonomicznego sweepu93tys zdjęć. Jeśli potrzebny jest mechanizm ograniczonej
atestacji wybranej strony, ma byte/time bound i receipt oraz używa wspólnej
normalizacji; rzeczywiste wykonanie na danych operatora wymaga odrębnego zakresu.

#### Izolacja dostępu, atestacja i trwałe uprawnienia

Nowa capability role per database: gp_rec_<24hex SHA256(databaseName:OID)>,
NOLOGIN/NOSUPERUSER/NOBYPASSRLS/NOINHERIT, bez członkostwa runtime. Własność
potwierdza marker z databaseOID/name/nonce i roleOID. Kolizja nie daje prawa
ALTER/DROP. Rename/restore/clone zmieniające tożsamość wymagają jawnego
reprovision; nie obiecujemy automatycznej adopcji innej roli.
Cluster-global role DDL pozostaje w jawnym provisionerze, nie w Alembic.
Nowa migracja wymaga wcześniejszego provisioningu dokładnej capability role,
sprawdza marker/atrybuty i dopiero instaluje tabele/funkcje/grants. Brak roli
jest czytelnym blokerem wdrożenia, bez runtime owner fallback. Testfixtures
wykonują tę kolejność na własnej bazie i zapisują ownership receipts.

Capability owns wyłącznie nowy prywatny rejestr. Trzy stałe bezpieczne wejścia
(proponowane attest_own_source_ids, recording_command, resolve_own_groups)
mają dokładne typowane sygnatury, SECURITY DEFINER SET search_path=pg_catalog,
kwalifikowane obiekty i brak dynamic SQL. PUBLIC EXECUTE zabronione, runtime
otrzymuje tylko te wejścia. Atestacja ma wąskie SELECT/USAGE/EXECUTE istniejącej
polityki source RLS i zawsze jawny predykat własnej gry. Nie zmienia GUC gry,
nie używa owner session ani nie czyta źródeł innej gry. Potwierdzone źródło:
0138 current_game_id_v1 czyta game_predictor.game_id, niezależnie od current_user.
Test real-role musi to wykazać. Gdy nie da się utrzymać granicy bez BYPASSRLS,
zatrzymujemy zależną implementację.

HTTP przyjmuje lokalne IDs, deklarację, CAS/key; nigdy autorytatywne SHA,
actor, providerJSON, ścieżkę lub arbitralny raport do unieważnienia. Zaufany
adapter deskryptora jest oddzielnym wewnętrznym producentem. Nieudokumentowane
metadane nie stają się zaufane tylko dlatego, że pasują do CHECK. Własne widoki
nie ujawniają obcych IDs, ścieżek, etykiet, liczb, globalnego proofSHA ani
wyszukiwania po dowolnym hashu. Zwracają lokalny stan i ogólny powód ochrony.

storage/database_roles.py::provision_application_role przyznaje szerokie
ALL TABLES/FUNCTIONS i default grants. Sam REVOKE w migracji byłby nietrwały.
Po każdym provision/reprovision/default grant i po nowym migrationDDL musi
działać dokładna lista wyłączeń oraz kontrola zgodności wyłącznie obiektów1002:
pięć tabel, ich kolumny/sekwencje (w tym ordinal), wszystkie prywatne funkcje.
Runtime nie ma bezpośredniego SELECT/DML/proof/sequence/internal EXECUTE;
ma tylko trzy bezpieczne podpisy. Nie cofamy uprawnień niezwiązanych obiektów.
Kontrola ApplicationRoleReport uwzględnia dokładnie te prywatne wyjątki,
zamiast wymagać ALL DML dla nowego prywatnego rejestru lub pomijać zgodność.
Test po reprovision i z nowego procesu potwierdza odmowę, sourceRLS oraz
zwykły runtimeCRUD. Migracja sprawdza aktualny head0160/frozenv13 przed
przydzieleniem następnego numeru. Stare manifesty i raporty nie są zmieniane.

#### Atomowość, zależności i nowy wąski most unieważnienia

Każde polecenie autoryzuje bieżący zakres przed odtworzeniem receiptu;
replay poprzedza CAS/currentness. Inne body pod tym samym kluczem daje409.
Przy wspólnych blokadach zawsze catalog9910994 przed registry advisory lock,
nigdy odwrotnie; lock_timeout5s, statement_timeout30s. Zdarzenie, head,
membership, zmiana proof i receipt są jedną transakcją. Wykryty zaufany
alias może zostać zapisany wraz z typed409 odmowy roli, bez rollback przez
wyjątek domenowy. Infra rollback nie udaje pustego wyniku.

Dotknięte komponenty znajdują zależne resolutions przez prywatny indeks,
porównują relevant proofSHA i unieważniają wyłącznie faktycznie zmieniony
dowód. Niezmienny stary manifest/receipt/pin/assignment pozostaje zachowany.
Istniejący katalog ma czytnik i append-only tabelę
grid_model_evaluation_invalidations; nie ma produkcyjnego writera.
Nowy proponowany prywatny recording_invalidate_dependents_v1(changeEvidenceId)
działa wewnątrz recording_command i tylko dla capability role. Przyjmuje
istniejący zaufany event, nie dowolny reportId/reason/actor z HTTP.
Wąskie grants: SELECT(id) reportów i INSERT(id,report_id,reason,actor)
invalidations, bez zmiany default/assignment/publication. Fixed coarse reason
RECORDING_DEPENDENCY_CHANGED i serwerowy actor nie ujawniają obcych zależności.
Ta sama transakcja/blokady obejmuje proof/alias/heads/invalidation/receipt.

TASK1002 dostarcza provisional resolution/index i capability mostu. Nie ma
jeszcze prawdziwych producentów kohort/raportów: nie fabrykuje ich bindings,
permanent use lub PASS. TASK0995 atomowo wiąże rzeczywisty cohortfreeze/use
z resolution/proof; TASK0997 wiąże zaufany report/cohort/resolution po walidacji
niezmiennych IDs/SHA. Dodatkowe niezbędne kolumnowe grants dokumentuje dopiero
ten producent. Missing bindings pozostają blokadą, nie pustą ochroną.

#### Usuwanie danych, API/UI i kryteria dowodowe

Minimalny hash/identity/lineage/protected-use proof przeżywa usunięcie źródła
lub gry bez obrazów/ścieżek/etykiet/rawcomments/credentials. Nie dodajemy FK
blokującego istniejące usuwanie źródła/gry ani resurrection. Ewentualne live
references są odłączane w dotychczasowej transakcji cleanup; historyczne
tożsamości nie są ponownie adoptowane. Fixture cleanup rozpoznaje exact own
database/roleOID/marker/nonce/createdHere: dispose sessions, drop własnej DB,
potem tylko własna nieużywana rola. Bez DROP OWNED/REASSIGN cudzych obiektów.

Jeden pion backend/OpenAPI/generated client/wrapper/request tests/Admin;
bez równoległego modelu klienta. Durably exact body/key przed mutacją,
lost response/reload/retry zachowuje command; potwierdzane discard najpierw
archiwizuje rawcommand, potem clear. GET nie mutuje. Mobile loading/empty/
error/conflict, obca gra i opóźniona odpowiedź mają jawne stany.

Proponowane moduły domain/application/storage/schemas/api source_recording_groups,
storage/source_recording_group_models oraz minimalne SQL/permissions helpers;
existing database_roles.py, centralmodels/ownershipmanifest/lifecycle tylko
niezbędne zmiany; nowa migracja, recording-groups-panel i wspólny klient.
Wymagania/architektura opisują granice, mapa jest regenerowana.

Przed audytem: focused domain/API/HTTP/request/Admin testy, Ruff/mypy/types/lint,
OpenAPI/MAP/DOC. Izolowane PG fixtures dowodzą prawdziwych aliasów dwóch gier,
provisional versus permanent protection, whole-recording conflict, provider
missing, source drift, protected ancestor, retraction, receipt replay po nowym
procesie, freezeCAS, zależnej i niezależnej invalidation, atomowego rollback,
privilege/RLS/reprovision i deletionretention. Nie testujemy tylko stubów
resolvera ani ręcznie oznaczonego PASS. Twarde120s per ograniczony zestaw,
audit1200s. Wszystkie FAIL, brakujący dowód i ownfixture cleanup są zapisane.
Brak prawdziwych anotacji/deklaracji/niezależnych nagrań pozostaje widoczny
dla1009/0995 i nie blokuje implementacji mechanizmu syntetyczną obietnicą danych.

#### Doprecyzowanie adaptera dziedziczonej ochrony przed jego implementacją

Zaufany, jednorazowo zainstalowany adapter przodka wskazuje exact ancestor
reference i jawne pary groupId/protected role. TRAIN nie jest rolą holdoutu.
Każda wskazana grupa musi istnieć oraz mieć kompletne, zadeklarowane
członkostwo; brak mapowania blokuje resolution. Potwierdzone odziedziczone
holdouty zapisują osobny trwały ancestor proof z providerSHA/ref/rolą,
atomowo z właściwymi invalidations i receiptem. Taki zapis zachowuje już
istniejącą ochronę przodka; nie oznacza użycia prowizorycznego splitu dziecka.
Indeks adapterów jest trwale przypięty SHA w konfiguracji serwera. Instalacja
jest operacją deployment/provisioning; zwykłe deklaracje i podziały kolejnych
kohort odbywają się w aplikacji bez edycji Pythona ani CLI per kohorta.

### Addendum przed kodem: zaufane pochodzenie LAB_DESCRIPTOR

Data2026-10-15. Read-only/WIP przegląd ujawnił, że wyłącznie MAIN schema
nie może reprezentować chronionego Reels/Treasure z laboratorium bez
tworzenia fikcyjnej gry. Zlecony plan wymaga rozwiązywania takich wyłączeń.
Pozostaje pięć tabel; jawny origin MAIN/LAB_DESCRIPTOR i ścisłe CHECK/unique
odróżniają przypadki. MAIN wymaga rzeczywistych game/source IDs i dotychczasowego
RLS. LAB ma nullable game/source wyłącznie dla tego origin oraz stabilne opaque
provider/recording/source referenceSHA, nigdy fikcyjne game/source UUID. Tożsamość
wystąpienia zachowuje byte/pixel/algorithm i pochodzenie; nowa obserwacja nie
nadpisuje starej. Runtime nie otrzymuje nowego arbitralnego wejścia ani grantów.

Jednorazowy jawny trusted deployment importer działa z administracyjnym
provisioningiem, nigdy owner session żądania aplikacji. Weryfikuje przypięty
descriptor/split/provider SHA i jawne mapowanie całych nagrań. Czyta wyłącznie
zaufane artefakty wejściowe i własny rejestr, nie źródła innych gier. Do DB
trafiają minimalne opaque identities, hashe, role/protection proof i receipts;
bez obrazów, ścieżek, etykiet symboli, rawcomments lub credentials. Własne
widoki gry nadal nie ujawniają LAB IDs, counts lub globalnego proofSHA.

Instalacja ma exact command/body/provider/page hash i idempotentne receipts,
strony maksymalnie200, jawne wznowienie i rollback strony. Catalog9910994
poprzedza registry także tutaj; proof/alias/currentstate/dependent-invalidation/
receipt są atomowe. Indeks plikowy publikuje dopiero zweryfikowany kompletny
stan; crash/lostresponse nie tworzy drugiej ochrony ani fikcyjnego sukcesu.
Nie ma nowej zgody na rzeczywisty import deskryptorów lub DB operatora.

recordingIdentityAvailable=false zachowuje znaną ochronę konkretnych byte/pixel
identities, ale nie dowodzi tożsamości całego filmu i nie daje complete lineage.
Późniejsze prawdziwe mapowanie musi móc rozwiązać uprzedni unknown przez
dopisany zaufany dowód i jawny pochodny currentstate, bez skasowania pierwotnej
ochrony/historii lub wiecznie blokującego nierozwiązywalnego placeholdera.
Test ma wykazać photo-only unresolved, potem prawdziwe mapping resolution,
z zachowaniem ochrony identycznych zdjęć i niezmiennych starych dowodów.

TRAIN ancestor-use jest oddzielne od permanent holdout: nie oznaczamy danych
treningowych przodka jako final_test. Rejestrujemy zaufane użycie/role zgodnie
z rzeczywistym deskryptorem i egzekwujemy niezależność kontroli; protected-role
mapping nie może po cichu pominąć wymaganej innej proweniencji. Brak danych
lub mapowania pozostaje unresolved, nigdy empty exclusions. Zwykły proces
MAIN (deklaracja/korekta/kohorta) pozostaje w aplikacji; CLI to jednorazowa
zaufana konfiguracja wdrożenia, nie krok każdego treningu. Realne kohorty/
evaluation bindings nadal należą do0995/0997, bez fabrykowania ich w1002.

Nowe testy: typed MAIN/LAB constraints/privacy, exact trusted import replay
po nowym procesie i częściowym restarcie, brak fakegames/liveFK/deletionblockers,
photo-only upgrade z zachowaniem proof, protected/TRAIN role distinction,
late alias/dependent-only invalidation oraz rollback receipt/event/state.
Wszystko na małych własnych fixture; bez rzeczywistego importu lub treningu.

### Granica zaufania instalacji — wykonanie zaakceptowanego addendum

Runtime SQL wymaga immutable `membership` deployment proof z exact canonical
providerSHA i całym zamkniętym providerem. Sama kopia JSON w server envelope
nie stanowi dowodu. Instalator MAIN oraz LAB commitują prywatny proof/receipts
przed publikacją indeksu plikowego. Identyczne wznowienie po utracie odpowiedzi
lub DB-complete/index-absent nie tworzy drugiego use/holdout. TRAIN przodka
pozostaje dowodem `use`, nigdy chronionym holdoutem. Zaufane źródła i mapowania
są instalowane jawnie w deployment; nie wykonano instalacji danych operatora.

LAB finalizacja opiera się na dokładnych immutable receipts stron i agregatach
SQL, bez ponownego czytania wszystkich stron pod globalnym lockiem. Strona ma
do200 opaque source/group refs. Finalizacja zwraca do4096 grup i zachowuje
niepełne photo-only placeholdery; dopiero potwierdzone pełne mapowanie może
zmienić ich derived state z zachowaniem starego proof.

### Jedna runda poprawek po audycie R1

Rzeczywisty audyt Claude high R1 zakończył się `REVISE` po754.216s. Raport
`ai_docs/quality/TASK-1002_AUDIT_claude-fable-5-1_R1.md` oraz pierwszy manifest
implementacji i jego dowody pozostają niezmienne. Root przed poprawkami
uzupełnił D554 i plan o następujące granice techniczne:

- Aktualny schemat i fixture migrujące do `head` stosują manifestv14.
  Historyczne manifesty i testy przypiętych rewizji nie zmieniają kontraktu.
  Dodatkowe current/head importy i inserty wykryte przez rzeczywiste regresje
  otrzymują tę samą korektę zgodności; asercje nie są osłabiane.
- Wspólny helper izolowanych fixture jawnie provisionuje capability przed
  wejściem w0161, przechowuje dowód własnego CREATE/OID bazy i role receipts,
  a po dokładnym usunięciu własnej bazy usuwa tylko własne niezmienione role.
  Trwały journal zasobów pozwala rozliczyć także przerwaną partię testową.
- Downgrade0161 jest dozwolony wyłącznie przy pustych wszystkich pięciu
  tabelach rejestru. Dowolny wiersz, w tym receipt, provisional evidence lub
  ochronny proof, blokuje usunięcie historii. Alembic usuwa tylko dokładne
  obiekty1002 i odtwarza poprzedni manifest; nie wykonuje cluster role DDL,
  `REASSIGN OWNED` ani `DROP OWNED`.
- `--recording-capability`, również z `--check`, wykonuje wyłącznie operację
  capability. Kanoniczna kolejność migracji/resetu to capability, Alembic,
  provisioning roli aplikacji. Polecenia te nie są wykonywane na bazie
  operatora w ramach weryfikacji; testy sprawdzają ich kontrakt i izolowane
  fixture. Runtime readiness wymaga teraz rzeczywistego head0161.
- `RECORDING_BINDING_INVALID` ma SQLSTATE22023 i mapowanie HTTP422.
  Zapis cleanup receipt używa jawnego absolutnego katalogu własnych dowodów;
  błąd zapisu nie maskuje pierwotnego wyjątku testu.

Zaakceptowane ograniczenia P2 są jawne. Po GET/reload zapisany exactcommand409
pozostaje tym samym poleceniem. Operator sprawdza bieżący stan i świadomie
archiwizuje oraz porzuca stare polecenie przed nową intencją; reload nie czyści
pending key/body. Restore, rename i clone aktualnej bazy pozostają zablokowane
przez tożsamość capability; narzędzie re-own nie istnieje. Atestacja strony
jest all-or-nothing, więc licznik unresolved nie jest osobnym pełnym spisem
wszystkich nieatestowanych elementów. Nie dodano frameworku naprawczego.

Pełne odpowiedniki `python:test` i `db:baseline:verify` są rozliczane w partiach
do120s z własnymi fixture, kontrolą PID/OID i bez uruchamiania usług. Dwa
opcjonalne testy korzystające z prawdziwego checkpointu i kalibracji poza
worktree nie są wykonywane. Wynik nie może być opisany jako pełne PASS.
R2 otrzymuje osobny manifest
`artifacts/audits/TASK-1002_R2_IMPLEMENTATION_EVIDENCE.json` oraz raport
`ai_docs/quality/TASK-1002_CORRECTION_CODEX.md` z rzeczywistymi wynikami,
starszymi FAIL i ograniczeniami pokrycia.

## Expected files

- Główne wejścia pionu: `services/api/src/game_predictor_api/domain/source_recording_groups.py`, warstwy application/storage/API, migracja0161 i `recording-groups-panel.tsx`.

Zrealizowane moduły obejmują domain/application/schema/API, storage registry/
permissions/providers/LAB import, zamrożony SQL i manifestv14, Alembic0161,
deployment CLI, Admin z trwałymi intencjami oraz wygenerowany klient OpenAPI.
Dokładną listę plików i SHA zawiera ignored
`artifacts/audits/TASK-1002_IMPLEMENTATION_EVIDENCE.json`.

- Testy pionu: `services/api/tests/test_source_recording_groups.py`, `test_source_recording_permissions.py`, `test_source_recording_lab_import.py`, integration `test_recording_capability_fixture.py` i `test_source_recording_groups_postgres.py` oraz Admin/request testy.

## Test cases

- Alias w innej grze zachowuje rolę.
- Holdout rodzica nie trafia do TRAIN dziecka.
- Brak deklaracji nie daje niezależności.
- Role przeżywają restart.

## Verification

Zakres: API, MIG, ADMIN, OpenAPI, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run openapi:check
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_verified_training_cohorts.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez przenoszenia plików źródłowych i zmiany sekwencji.

## Outcome

### Execution phase

- Implementacja po kontrakcie przed kodem; baza wykonawcza v1.7.381 / `477bf91ae3d3ab81bf6fc8d96cec38bc0dfef192`, TASK1003 done/Claude R2 PASS/PG9 PASS.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit: rzeczywisty `claude-fable-5-1`, reasoning `high`, R1 `REVISE`; jedna autoryzowana runda poprawek zakończona i zamrażana do R2. R1 i jego manifest pozostają niezmienne. Otwartych uwag P1 nie uznaje się za zamknięte przed niezależnym przeglądem.
- Następny krok: root otrzymuje osobny manifest R2 i wykonuje jeden niezależny audyt high; wyniki1003 nie zastępują kontroli tego taska.

### Changed

- Wdrożono minimalny rejestr pięciu tabel, indeksowane globalne aliasy byte/pixel, deklaracje i role rodziny, prowizoryczne resolutions oraz trwałą ochronę trusted import/use. SQL porównuje bieżącą atestację z dokładną zamrożoną stroną przed insertem. Własne widoki nie zwracają obcych identyfikatorów, liczników ani proofSHA.
- Per-database capability powstaje wyłącznie w jawnym provisionerze przed migracją0161. Runtime ma trzy dokładne wejścia; reprovision odtwarza exact private deny przy zachowaniu zwykłego CRUD. Prywatne obiekty nie tworzą FK blokujących usuwanie źródła/gry. Downgrade jest dozwolony wyłącznie przy pustych wszystkich pięciu tabelach; każda historia blokuje cofnięcie. Alembic nie tworzy ani nie usuwa ról klastra.
- Późny alias/proof unieważnia wyłącznie zależne resolutions i przyszłe powiązane raporty0998 w tej samej transakcji. Historyczne raporty/defaulty/piny nie są przepisywane. Same-role binding nie unieważnia sam siebie, a unrelated registry change nie powoduje globalnego stale.
- Admin wybiera czytelny import i rejestruje nagranie jedną akcją przez bounded200 polecenia. Trwała intencja i dokładne receipts obsługują przerwanie/wznowienie; reload jest GET-only. Techniczne identyfikatory i ręczne strony pozostają w szczegółach.
- Jawne deployment CLI instalują checksum-pinned MAIN/LAB providers i immutable DB proof przed indeksem. LAB photo-only zachowuje ochronę bez udawania filmu; późniejsze prawdziwe mapowanie rozwiązuje wcześniejszy placeholder bez usuwania historii. Nie importowano realnych deskryptorów ani danych operatora.

### Verification results

- Koncentracja: `pytest` nowych recording/permissions/LAB/fixture oraz istniejącego `test_verified_training_cohorts.py`: **78 PASS**,7.28s (`TASK-1002_FOCUSED_FINAL.txt`).
- Rzeczywisty PostgreSQL z rolą runtime bez owner fallback: **8 PASS**,39.84s (`TASK-1002_PG_RESTART_FINAL.txt`). Obejmuje RLS, direct private deny i reprovision, normalny CRUD, dokładne sentinele obcej funkcji/overload, nowy proces/replay, alias cross-game/privacy, niezwiązane zmiany, same-role binding, atomowy rollback0998, drift między check/write, brak deployment proof, LAB partial/replay/late whole-film/half-page rollback oraz existing game-delete/retention. Nowy proces rzeczywistego deploymentCLI wznowił DB-complete/index-absent przez ten sam deterministic key bez nowego proof/use. Cleanup potwierdza DB0/roles0/PIDs[] z DB/role OID (`TASK-1002_PG_CLEANUP.json`). Wcześniejszy `TASK-1002_PG_FINAL.txt` zachowano jako8 PASS42.89s przed rozszerzeniem asercji restartu.
- Admin: **17 mounted +13 unit/workspace +2 request PASS**; kontrola końcowa mounted+request **19 PASS** z aktualnym wygenerowanym klientem (`TASK-1002_ADMIN_UX_VERIFICATION.json`, `TASK-1002_UI_FINAL.txt`). Typecheck Admin/client, ESLint sześciu modułów i Prettier13 własnych plików PASS w dowodzie UI.
- `npm run openapi:check` po dokładnym permission fallback **PASS**,21.30s (`TASK-1002_OPENAPI_FALLBACK.txt`). Pierwszy wynik zachowano jako FAIL: sandboxowy TEMP odmówił rename VisionLab generatora (`EPERM`); Admin contract/client check zaliczony także w pierwszej próbie. Bez osłabiania generatora lub zmiany zamrożonych danych.
- Ruff/format28 zmienionych Pythonów PASS, strict mypy21 production modules PASS73.52s (`--follow-imports=silent`; nie jest to pełny repo typecheck). Code-map PASS; docs PASS (stan98253B, indeks92157B). Dowody: `TASK-1002_LINT_FINAL_02.txt`, `TASK-1002_FORMAT_CHECK_FINAL.txt`, `TASK-1002_MYPY_FINAL.txt`, `TASK-1002_MAP_FINAL.txt`, `TASK-1002_DOCS_FINAL.txt`. Końcowy zmieniony test restartu ma osobną kontrolę lint. Wcześniejsze czerwone próby zachowano: sandbox TEMP/TestClient, fixture aktualnego manifestu oraz SQL ambiguous payload; końcowe skoncentrowane/PG wyniki weryfikują poprawki. Limit każdego kroku120s, bez benchmarku/masowych fixture. Dokładne ścieżki/SHA/komendy/ograniczenia zawiera manifest dowodowy.

### Wyniki jednej rundy korekty R1

- Zaktualizowano zweryfikowane bieżące fixture i runtime consumers do manifestu v14, zachowując historyczne rewizje i wszystkie asercje. Wspólny helper tworzy dokładną perDB capability przed migracją head; receipts wymagają absolutnego własnego katalogu, createdHere i OID. Dokładne17 plików i995 zachowanych asercji opisuje `TASK-1002_R2_CURRENT_MANIFEST_FIX.json`.
- Kanoniczny kontrakt i help: capability-only provisioner → Alembic → application-role provisioner. Dotyczy także semantyki flagi `--check`. Nie wykonano kanonicznego reset/migrate na bazie operatora. Sprawdzono statyczną kolejność i własne izolowane fixture; kontrola poleceń i mapowania błędu:7 PASS. Warunkowy empty downgrade/reupgrade, upgrade, nowy proces, reprovision, sentinele i niezależne odmowy historii:4 actualPG PASS. SQL22023→typed422 z rollback:1 actualPG PASS.
- Odpowiednik `python:test`:614 modułów,5833 PASS,5 FAIL,497 SKIP,0 incomplete i2 jawne safety deselections prawdziwego checkpointu/kalibracji. Zestaw nie jest pełnym PASS. Początkowy RGB ENV FAIL przed SQL zachowano; jego nieguardowanej konfiguracji nie uruchamiano ponownie z większymi uprawnieniami. Późniejszy właściwie guardowany RGB PG PASS jest osobnym dowodem.
- Odpowiednik katalogu testów `db:baseline:verify`:473 unikalne nodeIDs, końcowe405 PASS /43 FAIL /7 SKIP /18 NOT_COMPLETED. To448 unikalnych wyników PASS/FAIL, a nie suma prób. Sześć FAIL dotyczy harnessu/trybu środowiska przed potwierdzeniem domeny; lista niezweryfikowanych ma24 nodeIDs (18+6). Dokładne próby, końcowe wyniki i ostrożną atrybucję zawierają `TASK-1002_R2_PG_COMBINED.json` i `TASK-1002_R2_PG_FAILURE_CLASSIFICATION.json`. Nie wykonano literalnego kanonicznego polecenia operacyjnego ani jego części na danych operatora.
- Zmienione32 przypadki reinference:31 PASS i zachowany wcześniejszy `cleanup_reset` RESTRICT FAIL. Zmienione49 przypadków konsumentów head:47 PASS,422 starej fixture API i niezweryfikowany wymagany application-role mode. Te zbiory nakładają się na473. Osiem właściwych przypadków actual-role pionu1002 przeszło końcową macierz. Naprawa bounded idle-wait własnej fixture zachowała końcowe assert active==0;3 unit i2 rzeczywiste przypadki CALL+TEARDOWN PASS, wcześniejsze czerwone wyniki pozostają.
- Macierz główna4821.75s przy hard5400s. Suplement1500.781s; równoległe uzupełnienia miały ten sam absolutny deadline, bez odnowienia budżetu. Każda partia do120s. Pozostałe przypadki są jawnie niezweryfikowane, bez dalszej pętli. Zachowano błędne próby harnessu MAX_PATH i CLEANUP_BLOCKED; oddzielny późniejszy receipt potwierdza bezpieczny cleanup, bez przepisywania pierwotnego wyniku.
- Końcowe Ruff/format83 własnych Pythonów PASS, mypy zmienionego CLI/schema i helpera PASS; code-map zregenerowany i PASS. Niezmienione Admin/OpenAPI korzystają z wcześniejszych PASS. Nie powtarzano pełnych611 modułów po zmianie wspólnej fixture; sprawdzano jej dotkniętych konsumentów.
- Końcowy odczyt katalogu potwierdza261 własnych baz0 /363 ról0 /backendPID0. Pierwsze scannery obejmowały aktywne launchery własnego sprawdzacza; ich czerwone receipts zachowano. Osobny `TASK-1002_R2_FINAL_CLEANUP_AFTER_EXIT.json` potwierdza ownPID0 po ich wyjściu. Bez FORCE lub kończenia backendów.
- Raport: `ai_docs/quality/TASK-1002_CORRECTION_CODEX.md`. Nowy manifest: `artifacts/audits/TASK-1002_R2_IMPLEMENTATION_EVIDENCE.json`; SHA i dokładne ścieżki ustala finalny freeze. Evidence zawiera wyłącznie bezpieczne kopie z `auditCopyByOriginal`, a oryginały zachowano przez SHA. Nie wszystkie43 FAIL mają wykonany historyczny reproducer; statyczna lub częściowa atrybucja pozostaje jawna. Wcześniejsze zobowiązania całego planu prowadzi root w odrębnym rejestrze.

### Not completed

- Wymagany niezależny audyt Claude high prowadzi root po zamrożeniu manifestu. Task pozostaje in_progress do audytu i osobnego commita; nie stage'owano, nie commitowano i nie scalano.
- Brak migracji/provisioningu/importu na bazie operatora, nowego backupu, uruchamiania/restartu usług, source sweep, GPU/treningu, publikacji/aktywacji i push. Nowy proces testowy dowodzi replay; nie wykonano restartu komputera ani ręcznej akceptacji wizualnej przeglądarki. Mounted testy JSDOM nie zastępują tej akceptacji.
- Brakujących trusted descriptor/mapping nie uznano za gotowe ani puste exclusions. TASK0995 jest przyszłym producentem guided in-app mapping i rzeczywistych cohort-use;0997 raportów. Obecny group resolver obsługuje own list/point/family, ale nie reverse sourceId→groups ani publiczny installation-proof reader. Root przyjął jawne addytywne rozszerzenie istniejącego safeGET w kontrakcie1009 przed jego kodem; bez zgadywania po importJob i direct privateSELECT. Wynik1002 nie oznacza1009-ready.
- Lista importów używa istniejącego ograniczenia200 jobs i jawnie je opisuje. Nie dodano równoległego API/jobs frameworku. Pełny Admin/build nie był wykonywany; root ma niezależne potwierdzone wcześniejsze10 błędów pełnej mounted suite z TASK1003, poza tym zakresem.
- Zaakceptowane ograniczenia P2: exact409 pozostaje w journalu także po GET/reload; nowy zamiar wymaga sprawdzenia stanu i świadomej archiwizacji/porzucenia starego polecenia. Restore/rename/clone są blokowane bez nieistniejącego narzędzia re-own. Atestacja all-or-nothing nie zapewnia szczegółowego pełnego licznika unresolved. Nie zmieniono tych zachowań dla wyniku audytu.

### Documentation updates

- Właścicielskie VISION_LAB requirements/architecture, instrukcja deployment/operatora, wygenerowane CODE_MAP/CODE_MAP_SYMBOLS, ten task i wyłącznie subsection1002 stanu. Root zachowuje własność README/planu/DecisionLogs/globalstate i metadanych1003/1009.

### Recommended next task

- TASK-1009


### Zamknięcie przez lead po niezależnym R2 — 2026-10-16

- Execution phase: gotowe do osobnego commita **v1.7.382**, potem oczekiwanie na integrację całego planu. Pełny hash po utworzeniu, bez amend. Otwarte P0/P1: brak.
- [Claude high R2 PASS](../../quality/TASK-1002_AUDIT_claude-fable-5-1_R2.md),789.063s/do1200s; R1 REVISE zachowany, jedna runda poprawek. Lead odczytał cały raport i potwierdził123 źródła/1501 dowodów SHA po audycie. [Rozliczenie](../../quality/TASK-1002_CORRECTION_CODEX.md). R1 P1-1/2/3 oraz P2-4/5 zamknięto; R1 pozostałeP2 zachowują opisane ograniczenia.
- Wyniki5833/5/497 i PG405/43/7/18 pozostają bez zmiany; brak pełnego PASS.24 dokładne niezweryfikowane nodeIDs i5 narzędzi wymagających capability zapisano w [rejestrze obowiązków](../../quality/V3_BACKEND_REGRESSION_OBLIGATIONS_20261015.md), z wymaganym ograniczonym follow-up przed1001. Brak dalszych testów po wspólnym deadline.
- Lead rozliczył nowe P2:
- R2-P2-1: Pięć narzędzi acceptance/benchmark wymaga capability przed head; fail-closed. Dokładne miejsca i obowiązek poprawki zapisano przed TASK-1001; narzędzi nie uruchamiano.
- R2-P2-2: Obecne wdrożenie Alembic wymaga połączenia migracyjnego z uprawnieniami superuser; właściciel samego schematu nie jest wspierany. Dopisano instrukcję, bez runtime owner fallback.
- R2-P2-3: Trwałe journals testowych zasobów pozostają świadomym śladem rozliczeniowym w ignorowanym katalogu rundy. Nie są wyciekiem DB/roli ani zgodą na automatyczny GC.
- R2-P2-4: Stała nazwa bazy baseline jest bezpiecznie fail-closed przy kolizji, lecz może maskować pierwotny CREATE error. Odnotowano obowiązek poprawki własnej UUID fixture; nie wykonano FORCE ani adopcji istniejącej bazy.
- R2-P2-5: 24 dokładne niezweryfikowane nodeIDs zapisano do rejestru przed odbiorem. Pozostają niezweryfikowane do ograniczonej kontroli, bez kolejnej szerokiej macierzy i bez fikcyjnego PASS.
- Po audycie zmieniono tylko dokumentację zamknięcia i instrukcję uprawnień; zachowanie źródeł pozostaje zamrożone. Powtórne kontrole DOC/MAP/diff i staged check mają osobne wyniki przed commitem.
- Cleanup261 własnych baz0/363 ról0/backend0/PID0. Brak operatorDB migration/reset/backfill/provider import, nowego backupu, usług, inferencji/GPU/treningu, publikacji/aktywacji/defaultu, integracji i push. Symbole per gra; stara777 archiwalna.
- Recommended next task: osobna poprawka kompatybilności wcześniejszych kontraktów według rejestru, z pełnym taskiem i tabelą modeli przed kodem; potem1009. Cały plan pozostaje zlecony.

### Kontrole dokumentacji po zamknięciu R2

- DOC PASS13.422s, MAP PASS7.219s, git diff --check PASS1.359s. Logi: `artifacts/audits/TASK-1002_CLOSURE_CHECKS.json`. Bez nowego pytest i bez zmian kodu. Kontrola staged/list/stat zostanie zapisana przez guarded committer przed utworzeniem commita.

### Stan po commicie — 2026-10-16

- Execution phase: oczekiwanie na integrację całego planu. Commit **v1.7.382 / `f0e457ea78b825063e460fcd0023b01e2cb27fd2`** na `codex/v3-grid-fine-tuning`. Staged check/stat/list i post-show/status PASS,127 staged paths; po commicie worktree czysty. Ten zapis własnego hasha wejdzie do następnego commita, bez amend. Bez scalania, push i operacji operatora.
- Następny krok: pełny task osobnej poprawki zgodności wcześniejszych kontraktów, po nim1009.
