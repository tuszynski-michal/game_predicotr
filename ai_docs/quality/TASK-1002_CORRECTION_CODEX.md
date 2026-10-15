# TASK-1002 — jedna runda poprawek po R1

Wykonawca: gpt-6.1-sol, reasoning high. Baza: v1.7.381 / `477bf91ae3d3ab81bf6fc8d96cec38bc0dfef192`. Dokument wykonawczy, nie audyt własnej pracy. R1 Claude high pozostaje `REVISE`; jego raport, manifest i dowody są niezmienne. Końcowe rozstrzygnięcie należy do niezależnego R2 prowadzonego przez root. Nie wykonano stage, commita ani operacji na bazie operatora.

## Zakres poprawek

- **P1-1:** bieżący runtime korzysta z manifestu v14. Zaktualizowano konkretne asercje i importy konsumentów aktualnego schematu, a następnie udowodnione fixture migrujące do head. Historyczne manifesty, ich DDL i testy historycznych rewizji zachowano. Dodatkowe dowody obejmują 17 plików aktualnych fixture i zachowanie 995 asercji AST (`TASK-1002_R2_CURRENT_MANIFEST_FIX.json`). Wspólny helper reinference porównuje rollback z bieżącym `EXPECTED_ALEMBIC_HEAD`, zamiast z poprzednim0160; `CREATE_TABLES` importuje jawnie z aktualnego v14. Nie przeklasyfikowano starych tabel ani nie osłabiono ochrony API.
- **P1-2:** każda własna fixture osiągająca0161 provisionuje dokładną capability przed upgrade. Wspólny helper zapisuje niezależny dowód udanego CREATE i OID, pełny marker capability i tożsamość własnej roli runtime. Cleanup używa wyłącznie własnej bazy/OID i dokładnie własnych ról; nie wykonuje `DROP OWNED` ani `REASSIGN OWNED`. Alembic nie tworzy i nie usuwa ról klastrowych. Downgrade0161 usuwa dokładnie obiekty1002 tylko przy pustych wszystkich pięciu tabelach. Jakikolwiek wiersz historii, protection, resolution lub receipts powoduje odmowę. Nie dodano sztucznej granicy nieodwracalności.
- **P1-3:** kanoniczne `db:migrate` i `db:reset:local` mają kolejność capability-only → Alembic → application role. Nowa flaga `--recording-capability`, także z `--check`, kończy się po capability i nie próbuje sprawdzać jeszcze nieistniejących tabel. Zaktualizowano help, instrukcje i testy kontraktu komend. Kanonicznych komend nie uruchamiano na bazie operatora.
- **P2-4:** `RECORDING_BINDING_INVALID` ma SQLSTATE22023 i mapowanie typed422. Mały rzeczywisty test PG dowodzi także atomowego rollbacku unieważnienia, gdy nie istnieje przyszły powiązany raport.
- **P2-5:** receipt trafia do jawnego absolutnego własnego katalogu, z bezpiecznym mkdir i atomowym zapisem. Błąd zapisu dowodu podczas istniejącego błędu testu nie zastępuje pierwotnego błędu.

## Zaakceptowane ograniczenia P2

- **P2-1:** konserwatywny konflikt roli może utrwalić blokadę i rewizję mimo409. Reload/GET odświeża stan, lecz nie usuwa trwałego replay409. Operator musi sprawdzić stan, świadomie potwierdzić porzucenie i archiwizację starego dokładnego polecenia przed nową intencją. UI nie czyści automatycznie body/key przy reload. Zachowania nie zmieniono.
- **P2-2:** restore/rename/clone z inną tożsamością bazy jest zablokowane fail-closed. Nie istnieje narzędzie re-own; sama instrukcja reprovision nie rozwiązuje tego przypadku. Brak owner fallback.
- **P2-3:** atestacja strony pozostaje all-or-nothing. Brak zaufanej tożsamości jednego źródła blokuje przygotowanie i nie daje szczegółowego licznika unresolved. Nie dodano nowego frameworku lub skanowania zdjęć.

## Metoda kontroli i bezpieczeństwo

`npm run python:test` oznacza `scripts/run_python_tests.ps1`. Wykonano semantycznie ten sam spis modułów API/worker w ograniczonych częściach, z oddzieleniem przypadków wymagających zgody na prawdziwy checkpoint/kalibrację. `db:baseline:verify` uruchamia katalog `services/api/tests/integration`; jego odpowiednik korzysta z już działającego PostgreSQL, bez startu Docker/usług i bez migracji/resetu bazy operatora. Każda część ma limit120s; pierwszy driver ma limit5400s, autoryzowany suplement1500s. Dokładne komendy znajdują się w agregatach i receipts.

Własny guard wymaga nieobecności bazy przed CREATE, skutecznego CREATE w tym procesie i zgodnego OID przed cleanup. Nieznana lub istniejąca obca baza blokuje część; nie wykonuje się wymuszonego usunięcia. Każdy testowy proces dostaje własne nieutworzone cele URL, własne katalogi i `CUDA_VISIBLE_DEVICES=''`. Bazy/role/PID są sprawdzane po każdej części. Zachowano pierwszą odmowę automatic approval review: stały target bez dowodu własności mógł usunąć cudzą bazę. Bezpieczna alternatywa wymusza CREATE-only oraz createdHere/OID; odrzuconej komendy nie wykonano.

Dwa rzeczywiste testy miały CALL PASS, lecz teardown FAIL z jednym jeszcze zamykającym się połączeniem. Nie zamieniono ich na PASS na podstawie stanu po zakończeniu procesu. Tylko te dwie fixture dostały polling maksymalnie5s, każdorazowo sprawdzający własną bazę i OID; asercja `active == 0` pozostała. Bez kończenia backendów. Dwa pełne powtórzenia CALL+TEARDOWN przeszły, a trzy małe testy helpera sprawdzają sukces, wygaśnięcie i podmieniony OID. Stare metody helpera i 17 testów zachowano bajtowo; dowód w `TASK-1002_R2_IDLE_WAIT_FIX.json`.

Pierwszy guard odrzucił znany UUID fixture0629 przed CREATE; po weryfikacji dokładnego formatu dopuszczono tylko ten wzorzec. Pierwszy długi Windows TEMP i brak mkdir rodzica krótkiego TEMP były błędami własnego harnessu. Ich czerwone wyniki pozostają; nie są przedstawiane jako historyczny błąd produktu. Suplement obejmuje tylko te przypadki, zmienionych konsumentów oraz przypadki wcześniej niewykonane.

## Dane wrażliwe w dowodach

Pierwotny agregat Python SHA `03cca7f960903fadfc05b715f54ce17008045c842d873b60f851e24fdb474abc` zawierał parametry połączenia w exception i pozostaje lokalnie niezmienny. Nie jest wejściem audytora. Jawna kopia audytowa `TASK-1002_R2_PYTHON_AUDIT_COPY/aggregate.json` SHA `b5c84dda9119f9cb3a5cc631f6dc4bb13c0ef69886b4409c5ac1e169f1ea8386` usuwa URL/hasła/SCRAM i remapuje297 kopii liści;3 liście zmienione,50 zastąpień. Receipt wiąże oryginalne SHA i kopie oraz potwierdza niezmienne liczniki i wyniki testów. Nie publikuje się pełnych URL ani poświadczeń.

Końcowy manifest R2 udostępnia `auditCopyByOriginal` i receipt wiążący SHA obu
wersji. Pola `directory`, `log` lub `path` opisujące oryginalny przebieg należy
rozwiązywać wyłącznie przez to mapowanie. Audytor nie otwiera surowych logów
ani diagnostyki połączeń, także gdy wskazuje je skopiowany aggregate.
Wszystkie wejścia `evidenceSha256` są bezpiecznymi kopiami.

## Ograniczenia i atrybucja szerszych kontroli

Macierz domyślna obejmuje614 modułów i5833 PASS /5 FAIL /497 SKIP, bez
niedokończonych modułów. Dwa przypadki prawdziwego checkpointu/kalibracji
wyłączono ze względów bezpieczeństwa, z dokładnymi nodeIDs w agregacie.
Nie jest to literalne wykonanie jednego pełnego polecenia ani pełne PASS.
Później dopisane trzy testy idle-helpera mają oddzielny wynik3 PASS, a nowy
przypadek binding ma oddzielne rzeczywiste PG PASS. Nie dopisano ich sztucznie
do niezmiennego agregatu ani nie sumuje się duplikatów z macierzą PG.

Pięć domyślnych FAIL to:0140 historyczny DDL kontra bieżący enum, admission
mock backfill, brak game-scoped resolvera w neural fixture, brak `get_bind`
w symbol-iteration session fake oraz setup RGB przed SQL. Dla pierwszych
trzech i symbol-iteration istnieją dokładne próby HEAD381; ich źródła były
weryfikowane przed i po. RGB jest osobnym błędem ograniczenia środowiska
w początkowej partii sprzed pełnego guarda. `_database_url` bierze endpoint
i credentials z `ApiSettings`, zmieniając tylko nazwę bazy na maintenance
`postgres`; nie jest to hardcoded URL. Socket PermissionDenied10013 wystąpił
przed SQL/CREATE i przed ciałem testu. Fixture nie utworzyła bazy ani roli,
nie uruchomiono nieguardowanego fallbacku i nie ładowano checkpointu.
Późniejszy właściwie guardowany przypadek RGB ma osobne PG PASS wpart123;
nie zastępuje czerwonego wyniku domyślnego.

Granica0158 pozostaje niezmienna. Dokładny HEAD381 cycle odtwarza jej odmowę,
z jawnym targetoverride wyłącznie dla własnej UUID bazy. Historyczne fixture
acceptance i test downgrade supergier również trafiają w tę ochronę;
nie zamieniono oczekiwanego komunikatu kosztem pokrycia starej blokady.
Skrypt usuwania starej gry ma manifestv8 niezgodny już z v9 przed1002;
potwierdza to wyłącznie pure-predicate proof na HEAD381, bez wykonania
usuwania. Public-only reset probe zachowuje rzeczywisty FAIL DuplicateSchema
`game_data_v2`; aktualizacja kolejności provisioning/migracja nie naprawia
tego starszego mechanizmu resetu.

Actual-role API422 ma statycznie brakujący wymagany idempotencyKey w starym
żądaniu. Historyczna próba zakończyła się wcześniejszym setupERROR, więc nie
jest odtworzeniem422. Nie osłabiono ochrony API; samo dodanie klucza również
nie jest dowodem201 bez prawidłowego model-default fixture.

Osiem acceptance FAIL ma kod `IMAGE_GEOMETRY_TOPOLOGY_INVALID`. Guard
`image_geometry_v2_repository.py:122–131` wymaga dokładnego rulesID i gameID;
blame wskazuje48e12ea9c/8b7f56143 z sierpnia2026. Test z TASK1017
(5451da2ea2df923a7e8788731ceb58c6ba2915b3) wybiera revision bez filtra
source/game w bazie modułu zawierającej wiele gier. To konkretny statyczny
kandydat przyczyny fixture, a nie dowód przechwyconego obcego wiersza lub
historycznego wykonania. Guard, worker i test odpowiadają HEAD381 po
normalizacji CRLF. Dokładne osiem nodeIDs i SHA zawiera
`TASK-1002_R2_ACCEPTANCE_ATTRIBUTION.json`. Pozostałe starsze admission,
historyczne routing i lock-event FAIL zachowują ostrożną atrybucję partial,
jeżeli nie wykonano konkretnego node na starej bazie kodu. Root rozlicza te
kontrakty osobno przed odbiorem całego planu.

## Uzupełnienia harnessu po pierwszym przebiegu

Pierwszy przebieg PG zakończył się po4821.75s, w nieodnawianym limicie5400s.
Suplement i równoległy repair mają jeden absolutny deadline: utworzenie
pierwotnego logu suplementu+1500s. Repair obejmuje wyłącznie wcześniejsze
FAIL związane z MAX_PATH, bez ponawiania zaliczonych przypadków. Nie
uruchamia się dalszej szerokiej macierzy po tym terminie.

Windows MAX_PATH wystąpił przy atomic rename checkpointu (ścieżka docelowa
260 znaków). Pierwsza podmiana wieloliniowa nie zadziałała przez podwójne
CRLF; wykazał to rzeczywisty childreceipt, mimo zmiany pola diagnostycznego.
Szkic `MAX_PATH_GUARD_PROOF_UNAPPLIED_DRAFT` zachowano. Poprawna podmiana ma
exact-count assertion i rzeczywisty receipt part007 wskazujący nowy krótki
TEMP `D:/game_predicotr/.tooling/t1002/<UUID>`. Wszystkie ancestors są
sprawdzane pod kątem junction/symlink, UUID musi być nieobecny. Bez usuwania
cudzych katalogów i zmian globalnej konfiguracji Windows. Czerwone próby
zostają; nie są przypisywane produktowi.

Dokładny node slim0137 zmienia tylko runtime URL na własną fixture.
Usunięcie jawnego OWNER z jego childENV daje konfigurację owner na tym samym
runtime endpoint/db, nie odczyt dotenv. Potwierdza to pure-config proof bez
DB queries oraz źródło `ApiSettings.from_environment`. Guard endpointu,
createdHere i OID nadal obowiązuje.

Dokładny node query-cancellation nie miał własnej bazy. Autoryzowana fixture
w ignorowanym pluginie tworzy wyłącznie nową własną UUID bazę, zapisuje
createdHere/OID przed udostępnieniem obu URL i nie uruchamia Alembic ani
dodatkowych ról. Teardown wymaga zakończenia własnego wątku, zera połączeń
i powtórnej kontroli OID. Anulowanie dotyczy tylko zapytania testu.
Nie zmieniono jego źródła ani asercji. Końcowy accounting rozstrzyga wynik
rzeczywistego wykonania; sama obecność mechanizmu nie jest dowodem PASS.

Oba zmienione moduły reinference mają końcowe31 PASS i1 FAIL
`cleanup_reset` (23 source cases +9 stats cases). Dokładny wcześniejszy
node i ten sam RESTRICT komórek symboli istnieją w
`TASK-0999_PG_WORKING.txt`; task0999:600–607 i jego raport korekty jawnie
zachowują ten błąd. Rzeczywisty SQL usuwa `image_review_items` przed
referencjami w `image_symbol_review_cells`. Reset graph jest równy HEAD381;
nie wykonano nowej historycznej próby resetu. Dowód:
`TASK-1002_R2_CLEANUP_RESET_ATTRIBUTION.json`.

Pierwsza równoległa partia repair została przerwana po120s. Jej cleanup
odmówił DROP, widząc jeszcze backend własnej bazy. Zachowano
`CLEANUP_BLOCKED`, bez przepisania na PASS. Późniejszy osobny receipt
potwierdza dokładną tożsamość/OID, idle0 i cleanup1 własnej bazy oraz2 ról,
bez FORCE i kończenia backendów. Tylko siedem brakujących przypadkówP1
otrzymało jeden końcowy part (7 PASS,92.625s); bez dalszych prób. Wszystkie
drivery nadal miały ten sam pierwotny deadline suplementu.

Zmodyfikowani konsumenci aktualnego manifestu zachowują też dwa jawne
ograniczenia: POST nowej gry w actual-role API nadal ma422 starej fixture,
a diagnostyka board coverage wymaga osobnego `PG_TEST_ROLE=application`.
Driver nie dziedziczy wspólnej roli. Dziesięć pozostałych coverage cases
i24 pozostałe role-isolation cases przeszły. Nie włączano starego globalnego
role fixture ani nie osłabiano asercji dla zielonego wyniku.

## Wyniki końcowe

Wszystkie drivery zakończyły pracę. Pierwsza macierz trwała4821.75s w limicie5400s.
Suplement zakończył się po1500.781s; równoległe uzupełnienia korzystały
z tego samego absolutnego deadline. Nie uruchomiono dalszych testów.

Końcowy inwentarz PG obejmuje473 unikalne nodeIDs:405 PASS,43 FAIL,7 SKIP
i18 NOT_COMPLETED. To448 unikalnych terminalnych wyników PASS/FAIL,
nie liczba wszystkich prób. Sześć z43 FAIL zatrzymał harness lub wymagany
tryb środowiska przed potwierdzeniem domeny. Dlatego lista niezweryfikowanych
ma24 nodeIDs:18 nieukończonych i6 takich FAIL. Siedem SKIP jest oddzielnym
wynikiem. Dokładne nodeIDs, wcześniejsze czerwone próby, ostatnie wykonanie
i źródło atrybucji zawierają `TASK-1002_R2_PG_COMBINED.json` oraz
`TASK-1002_R2_PG_FAILURE_CLASSIFICATION.json`. Żaden FAIL nie został
przepisany na PASS na podstawie samego późniejszego cleanupu.

Zmienione32 przypadki reinference mają31 PASS i zachowany wcześniejszy
`cleanup_reset` FAIL. Z49 przypadków konsumentów zmienionego head47 PASS,
422 starej fixture tworzenia gry oraz niezweryfikowany wymagany tryb
application-role. Te zbiory i skoncentrowane kontrole nakładają się na
inwentarz; nie dodaje się ich ponownie do473. Osiem przypadków właściwego
pionu1002 zaliczyło końcowy actual-role PostgreSQL, w tym reprovision,
prywatne deny, normalny CRUD, sentinele, privacy, restart, LAB i rollback.
Nowe lifecycle4, SQL22023/rollback1 oraz idle-wait2 mają osobne PASS.

Pozostałe dwa wcześniej niesklasyfikowane FAIL mają konkretne bieżące
przyczyny: M2 public HTTP otrzymuje422 za brak `idempotencyKey`, a supergame
`game_layout_reset` trafia na RESTRICT `image_symbol_review_cells` podczas
usuwania `image_review_items`. Nie wykonano tych dokładnych historycznych
nodeIDs. Atrybucja pozostaje statyczna lub częściowa, a oba FAIL pozostają
w zestawieniu. Nie wszystkie błędy są przedstawiane jako wcześniejsze
wobec całego planu. Osobny root-owned rejestr zobowiązań rozlicza te kontrakty
przed odbiorem planu.

Odpowiednik `python:test` obejmuje614 modułów:5833 PASS,5 FAIL,497 SKIP,
0 incomplete oraz2 jawnie niewykonane przypadki prawdziwego checkpointu
i kalibracji. Bez rzeczywistych checkpointów, GPU ani korpusu użytkownika.
Początkowy RGB ENV FAIL przed SQL pozostaje oddzielny od późniejszego
zaliczonego, prawidłowo guardowanego przypadku PG. Nie wykonano permission
fallback dla nieguardowanej próby.

Końcowe Ruff i formatowanie83 własnych Pythonów PASS. Mypy zmienionego
CLI/schema i wspólnego helpera PASS; wcześniejsze błędne lub przerwane
próby zachowano. Code-map zregenerowano i sprawdzono. Niezmienione kontrole
Admin/OpenAPI wykorzystują wcześniejsze PASS; nie ogłasza się pełnego
Admin/build ani pełnego repo typecheck.

Read-only katalog sprawdził261 dokładnych własnych baz i363 ról:0 pozostało,
0 backendów. Pierwsze dwa scannery procesów objęły własny aktywny launcher
i runner, więc ich czerwone receipts zachowano. Osobna kontrola po ich
zakończeniu potwierdza0 procesów TASK1002 (`TASK-1002_R2_FINAL_CLEANUP_AFTER_EXIT.json`).
Bez FORCE, kończenia backendów ani odczytu danych operatora.

Wynik jest zamrożeniem jednej rundy korekty do niezależnego R2, nie pełnym
PASS. Manifest `TASK-1002_R2_IMPLEMENTATION_EVIDENCE.json` zawiera wyłącznie
bezpieczne kopie audytowe i jawne `auditCopyByOriginal`. Oryginały pozostają
niezmienne i mają SHA; auditor nie podąża do surowych logów ze ścieżek
w ich treści. R1, pierwszy manifest i jego raport nie zostały nadpisane.
Audyt R2, stage, commit i operacje operatora nie zostały wykonane przez
wykonawcę.


## Rozliczenie leada po R2 — 2026-10-16

Rzeczywisty Claude high R2: PASS,789.063s, brak P0/P1. Lead potwierdził123
źródła i1501 dowodów SHA po audycie. Raport R1 i R2 pozostają niezmienione.

- R2-P2-1: Pięć narzędzi acceptance/benchmark wymaga capability przed head; fail-closed. Dokładne miejsca i obowiązek poprawki zapisano przed TASK-1001; narzędzi nie uruchamiano.
- R2-P2-2: Obecne wdrożenie Alembic wymaga połączenia migracyjnego z uprawnieniami superuser; właściciel samego schematu nie jest wspierany. Dopisano instrukcję, bez runtime owner fallback.
- R2-P2-3: Trwałe journals testowych zasobów pozostają świadomym śladem rozliczeniowym w ignorowanym katalogu rundy. Nie są wyciekiem DB/roli ani zgodą na automatyczny GC.
- R2-P2-4: Stała nazwa bazy baseline jest bezpiecznie fail-closed przy kolizji, lecz może maskować pierwotny CREATE error. Odnotowano obowiązek poprawki własnej UUID fixture; nie wykonano FORCE ani adopcji istniejącej bazy.
- R2-P2-5: 24 dokładne niezweryfikowane nodeIDs zapisano do rejestru przed odbiorem. Pozostają niezweryfikowane do ograniczonej kontroli, bez kolejnej szerokiej macierzy i bez fikcyjnego PASS.

To akceptacja ograniczeń tego commita, nie zniesienie obowiązków całego planu
i nie pełny PASS szerszych zestawów. Po audycie tylko dokumentacja, bez zmiany
kodu, dodatkowego pytest, operacji operatora lub trzeciej rundy audytu.
