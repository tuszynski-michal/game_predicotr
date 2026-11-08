# TASK-1167 — Verification

Data: 2026-11-08. Baza: v1.7.575/ac724d297448785bdcb98b17dc6a3d5e3fc104e5.
Stan: implementacja i scoped checks zakończone; niezależny audyt, globalne
docs/maps i zamknięcie należą do root. Ten raport nie deklaruje audytu PASS.

## Zakres rzeczywistego wyniku

Jawny opt-in istniejącego Admin command przechodzi przez ten sam endpoint,
parent, real content prepare/freeze i jedno dziecko. Closed plan/full proof
wiążą bazę, kohorty, bank subset TRAIN, A/B/REG rostery i seed. Dziecko wykonuje
1200 successful steps na ukończone ramię; globalny limit4800/7200 obejmuje
startup/bank/preflight/validation/export. Resume zachowuje globalny offset,
stan, checkpoint i zużycie. R2 A_FAIL wymaga ukończonego R3, inaczej brak eksportu.
PASS-first obowiązuje checkpoint i winner; all-fail daje tylko proposal-only.

R1 zachowuje gradient affine przy frozen BN stats. R2 ma rzeczywiste dwa rastry
screen i board, R3 realny masked auxiliary loss/head i exposure do bestStep.
Każdy arm zaczyna od tej samej bazy/seed, finalny eksport używa wybranych best
weights i własnej parity. R2/R3 eksportują tę samą zmierzoną combined route;
A_FAIL nie usuwa jej, ale blokuje publication/default/automatic admission.

Actual A evaluator używa T3 renderera/source support/matchera i tylko A.
Każde wywołanie otrzymuje engine z bieżącymi wagami, a każde zdjęcie nowy
lokalny budżet1+1; krok400 nie korzysta z cache kroku200. Runtime receipts
wiążą bundle/proof/variant/raster i nie odnawiają próby po crash. Stare V1
identity/SHA zachowane; domyślna etykieta w summary nie mutuje receipt.

T3 residual P2-6: detail fstat bound96MiB przed read/parse, także load_documents;
finalny pass streamuje SHA i nie trzyma parsed docs wszystkich gier. Test
używa granicy128B i pliku129B, bez alokacji96MiB. T3 P2-1 pełny replay pozostaje
świadomie kosztowny; nie wprowadzono cache pomijającego physical proof.

## Wyniki primary

| Kontrola | Wynik | Dowód / granica |
|---|---|---|
| Real selected R3 export, 3 ONNX, oba rastry, install, cold inspector, lost-response reuse, graph tamper | 1 PASS,62.76s | `artifacts/TASK-1167-export4.log`; rzeczywiste małe Screen/Board FPN width8, frozen pixels i full TRAIN proof. Fixture completion/exposure jest jawnie syntetyczna; nie kwalifikuje modelu operatora. |
| Worker union, bank binding, cold ledger, A checkpoint/photo-local1+1, final4800 lease heartbeat, golden old receipt | 6 PASS,14.47s | `artifacts/TASK-1167-worker2.log` |
| V2 closed canvas/margin, actual warp/input support i replay odrzucający podmianę V1 | 3 PASS,2.21s | `test_grid_content_geometry.py`, scoped wynik terminalowy wykonawcy; nie ponawiano bez zmiany. |
| Detail bound/hash-only + początkowe geometry cases | 5 PASS,2.44s | `test_grid_content_detail_bounds.py` i ówczesne2geometry cases; późniejszy trzeci geometry case ma wynik powyżej. |
| Runtime/production-input legacy grupa | 52 PASS,9 FAIL początkowo | `TASK-1167-runtime-regression1.log`; szczegóły poniżej, bez deklaracji zbiorczego green. |
| Tylko9 dotkniętych przypadków, właściwy local filesystem/krótki basetemp | 2 PASS,7 FAIL | `TASK-1167-runtime-regression2.log`;7 ujawniło rzeczywisty nowy KeyError summary. |
| Wyłącznie7 po poprawce summary | 7 PASS,10.28s | `TASK-1167-runtime-regression3.log`;52 wcześniej passing nie powtarzano. |
| Ruff format/check primary24files | PASS | `TASK-1167-primary-ruff-final.log` |
| mypy primary19sourcefiles | PASS | `TASK-1167-primary-quality.log`; ten sam log zawiera wcześniejszy pojedynczy lint importu, zamknięty końcowym Ruff. |

Export run1 FAIL11.84s: fixture TRAIN nie miała purposeProofSha256; dodano
poprawny istniejący pin, nie ominięto guardu. Run2 FAIL11.06s ujawnił rzeczywisty
gap: legacy GridBoardDataset odrzucał legalne częściowe A w parity screen+grid.
Nowy jawny ContentSelectionDataset wymaga v4/contentSampling i roli A, zachowuje
target/source checks; legacy reader pozostaje strict. Finalny test dowodzi
jednego board A i nadal odrzucającego go legacy readera, bez czytania B.
Run3 przeszedł actual export/parity i FAIL58.13s na brakującym cohort_id testowego
joba. Poprawiono fixture; niezależny probe na tych samych plikach potwierdził
install/inspector/recovery, potem pełny run4 z cold processem PASS. Zachowano
wszystkie cztery logi. Trzy FutureWarning PyTorch nie są błędami parity.

Pierwsze runtime9FAIL obejmowało ograniczenie Windows hard-link w środowisku
testu oraz zbyt długą ścieżkę temp. Retry tylko tych przypadków z uprawnieniem
własnego filesystem i krótką ścieżką ujawniło7 realnych KeyError: summary
zakładało preprocessingContract w minimalnej historycznej identity. Trwała
poprawka używa default wyłącznie w summary, bez mutacji identity/SHA. Golden
receipt utworzony niezależnym starym kodowaniem pozostaje byte-identical/spent;
podmiana V2 nie daje nowego budżetu. Nie ukryto pierwszych FAIL jako środowiska.

## Wyniki helperów przyjęte bez zbędnego powtarzania

Szczegółowe granice i dokładne logi:
`artifacts/TASK-1167_CORE_HELPER.md`,
`artifacts/TASK1167_WORKFLOW_TEST_HELPER.md`,
`artifacts/TASK-1167_API_HELPER.md`.

| Pion | Wynik |
|---|---|
| Core plan/rank/BN/masks/exposure/budget |17 PASS12.20s; dodatkowy state guard1 PASS5.82s |
| Actual train650→cold process1200, identyczne current/best tensors/history/selection |1 PASS14.90s |
| Real ONNX screen/board/content,7outputs, oba canvas |1 PASS51.02s; znaleziony i naprawiony dynamic adaptive-pooling export bug |
| Core legacy |82 PASS/1 wcześniejszy stale3preset FAIL; exact HEADv575 reprodukcja FAIL0.57s, nowe exact4preset fingerprints unchanged PASS |
| Core Ruff/mypy |9plików/7modułów PASS, finaldelta guard PASS |
| Actual child/orchestrator/core3600steps + lost export response; infeasible preflight |2 PASS72.07s |
| R1local650/global1850 interruption/resume, bez R0retrain/reset |1 PASS63.68s |
| RequiredR3 actual4800steps/time accounting/PASS-first |1 PASS96.57s |
| Missing R3 labels blocks after complete R2; actual samebase/seed factory |2 PASS68.32s |
| Actual supervisor orphan/reserve/settle/load globaloffset |1 PASS |
| APIrequest/legacy |41 PASS4.45s |
| API/domain/admission/registry/publication |206 PASS/6 setup errors27.78s;6 przypadków ponowionych z wymaganym istniejącym fixture plugin:6 PASS1.04s |
| Latest inputs/evidence strict proof |30 PASS3.89s |
| API Ruff/mypy |PASS18sourcefiles plus finalproof delta |
| OpenAPI/generatedSDK/SDKtypecheck/Adminnexttypegen+tsc |PASS |
| SDK request/Admin persisted exactretry |9 PASS |
| Scoped Prettier |PASS |

Workflow fixture używa real train/TinyCPU/AdamW/file ledger, nie setterów counters.
Ciężka inferencja/evaluator/export są jego jawnymi adapterami; real pixels/proof
i graphs mają oddzielne testy primary/core. Pierwszy workflow fixture FAIL
brakowało counts.TRAIN.photos; uzupełniono i dotknięty przypadek PASS. Po tych
testach primary dodał wyłącznie heartbeat bez rezerwacji kroku oraz A parity
reader; nowe granice mają własne targeted PASS, nie powtarzano4800 pętli.

## Rzeczywisty PostgreSQL i izolacja

API helper: `test_grid_content_experiment_parent_postgres.py` rzeczywiście
preview/start/cold exactretry/prepare/capture/materialize/freeze/onechild,
worker verify_inputs i kolejny advance zachowujący ten sam trainingRunId.
**Phase2 PASS68.63s** na jawnie zachowanej własnej bazie po setup.
Nowy proces cleanup potwierdza **0 DB/0runtime role/0capability role**;
`TASK-1167-parent-cleanup2-fresh.json`. Nie użyto operatorowej bazy ani GPU.

Nie deklarujemy PASS dwóch wcześniejszych whole-flow timeout120s (setup97.94s,
następnie89.16s). Root zatwierdził oddzielne ograniczone fazy i zachowanie tej
samej owned bazy po sprawdzeniu procesów/sesji. Phase2 pierwszy FAIL11.39s miał
błędną testową nazwę public table zamiast game route; poprawiono fixture.
Końcowy setup ma jawne typed synthetic ContentRevision, real source frames,
source identities, append-only constraints, production oracle i strict u/δ.
Nie jest to powtórzenie human blind protocol T2. Historyczne model availability
jest fixture adapterem; role/lineage/split/currentness i nowy proof nie są mocked.

Jawny aplikacyjny URL i niezależna expectedDB są wymagane przed engine;
current_database sprawdzane przed SET/funkcjami. Własny cleanup waliduje
OID/marker/capability i nie usuwa aktywnej/obcej bazy. Disposable credential
usunięty, żaden private handoff/resource nie wchodzi do scope/audytu/commita.
Dokładne fazowe komendy i ograniczenia są w raporcie API helpera.

## Odtwarzanie scoped kontroli

Cwd: `D:/game_predicotr/worktrees/full-symbol-crops`, interpreter
`D:/game_predicotr/.venv/Scripts/python.exe`, PowerShell:

```powershell
$env:PYTHONPATH="$PWD/services/api/src;$PWD/services/worker/src"
```

Każde poniższe argv uruchomić przez `subprocess.run(argv, timeout=120)`;
unikalny krótki basetemp jest własny, nie operatorowy. Nie uruchamiać ponownie
bez zmiany/nowego błędu tylko dla zbiorczego licznika.

```text
-m pytest services/worker/tests/test_grid_content_experiment_export.py -q --tb=short --basetemp=D:/game_predicotr/.tmp/t47ex4
-m pytest services/worker/tests/test_grid_content_experiment_worker.py -q --tb=short --basetemp=D:/game_predicotr/.tmp/t47wk2
-m pytest services/worker/tests/test_grid_content_geometry.py -q --tb=short
-m pytest services/worker/tests/test_grid_content_detail_bounds.py -q --tb=short
-m pytest services/worker/tests/test_screen_rescue_contract.py -k "reservation_survives or completed_attempt or atomic_receipts or baseline_interrupted" -q --tb=short --basetemp=D:/game_predicotr/.tmp/t47r3
-m ruff format --check <24 paths z artifacts/TASK-1167_PRIMARY_PATHS.json>
-m ruff check <te same24paths>
-m mypy --follow-imports=silent <19src paths tego manifestu>
```

## AC i ograniczenia odbioru

1. Samebase/data/seed i1200/reserves/shared7200: core + actual workflow + PGpins.
2. Real preflight/fullreserve/incomplete guard: workflow blocked case, corestate;
   fixtureCPU nie gwarantuje budżetu przyszłego GPU.
3. A/eval200/equalgame/rank/REG isolation: strict selection, actual evaluator,
   union/photo-local tests i rostery; brak operator-quality claim.
4. Checkpoint/resume/earlystop/lostresponse: cold core, global1850 workflow,
   ledger coldread, actual export recovery i API PGcold retry.
5. Bank subset positiveancestorunseen: API resolver/fullproof/PG, worker
   frozen source/role comparison i actual base measurement w export fixture.
6. R3 humanlabels/head: actual masked gradients, requiredR3/missinglabels,
   actual inspector humanref i selected-head exposure guards.
7. Rescue trained/measuredfixedroute: exposure, real parity/raster/runtime,
   proposal-only publication guards, stale proof tests i legacy spent receipts.
8. B/REGclosedroster/qualification: inputs/evidence/legacy calibration dispatch,
   brak nowych źródeł po wynikach; nie deklarowano30+30 dla operatora.
9. ONNX/PG/quality: dowody powyżej. Niezależny audyt i final docs/maps/root
   DoD pozostają do odbioru, dlatego task nie jest done.

Nie uruchamiano treningu/operator GPU, usług API/Admin, operator DB migrations,
default/activation, import691, merge/push. Nie zmieniano wcześniejszego testu
stale3preset ani znanych historycznych T1/T2 fixtures. Nie wprowadzono nowego
trenera/usługi ani modelowej kwalifikacji na podstawie synthetic fixtures.

## Jedna runda poprawek po rzeczywistym R1

Rzeczywisty Opus R1: REVISE, 0 P0 / 2 P1 / 3 P2. Brief SHA
`f6a6049d53700a1d4992d473433f2a77d6726bdd14f8fd69eb0a9b9c0fc82462`.
Poniższe wyniki wykonawców nie zastępują werdyktu R2. Bez audytu własnej pracy,
stage, commita, operator GPU/DB/usług. Root prowadzi freeze i focused R2.

## P1-1 — logiczny budżet i eksport po 4800

`training_core/grid_training_admission.py::RunBudget`: CONTENT remainingSteps
opiera się na durable logical_completed_steps; spent time nie jest odnawiany.
Physical reservedSteps pozostaje wysokim stanem rezerwacji, nie licznikiem
powtórzonej pracy. Legacy payload pomija nowy klucz i zachowuje dawną semantykę.
`images/grid_training_handler.py::_recover_previous_attempt/_adopt_pointer/
_settle_steps/_reserve/_supervise/_spec`: potwierdzony SHA checkpointu, monotoniczny
global offset i allowance; reported progress bez checkpointu nie udaje trwałego
kroku. Admission dopuszcza sam eksport przy 4800 i pozostałym czasie, ale
ChildControl nie dopuszcza kroku 4801. Brak czasu nadal blokuje.

Nowy `test_grid_content_recovery_guards.py`: **4 PASS, 10,62 s**, prawdziwe
handler recovery→admit→spec→ChildControl dla 650/4550/4800; nie podstawia gotowego
remainingSteps. Scoped legacy **7 PASS, 3,91 s**; rzeczywisty orphan/pointer
settlement **1 PASS, 8,82 s**. Logi `TASK-1167-R1-recovery1.log`,
`...-budget-legacy.log`, `...-orphan.log`.

## P1-2 — rzeczywista gotowość i ekspozycja R3

`images/grid_content_experiment_run.py::run_experiment/require_head_exposure`:
actual contract.supervision.qualified dla gier z TRAIN i zatwierdzone visible
quads przed preflight. Control-only bez TRAIN nie tworzy dodatkowego minimum.
Każdy wymagany R3 potrzebuje dodatniego quadTargets/localVisibilityTargets/
optimizerSteps do BEST przed COMPLETE, również gdy wygrywa inne ramię. To samo
jest sprawdzane przy wznowieniu już zapisanego COMPLETE. Nie wystarczy head flag.

Nowy `test_grid_content_r3_readiness.py`: **7 PASS, 32,07 s**, w tym realne
1200 kroków R3 z zerowym nadzorem zatrzymane przed COMPLETE mimo gotowego R0.
W tym izolowanym teście wcześniejsze ramiona są jawnymi synthetic receipts.
Oddzielny rzeczywisty workflow wszystkich ramion: **4800 TinyCPU steps,
1 PASS, 90,74 s**, z qualified labels i head exposure. Fixture nie daje obietnicy
jakości ani wydajności operatorowego GPU. Logi `...-r3guard4.log`,
`...-r3positive2.log`. Known-input size bound w actual run przed baseline/bank/
optimizer: dodatkowy **1 PASS, 6,99 s**, `...-bound-run.log`.

## P2-3 — pominięte wiersze przed BatchNorm

Helper `training_core/grid_training.py::screen_grid_losses`: opt-in mask/weight
filtruje board rows przed forward, zachowuje oryginalny batch/source mapping;
legacy bez crop_skipped bez zmian. Nowy `test_grid_content_mixed_batch.py`:
**9 PASS, 10,12 s**, rzeczywisty FPN/BatchNorm/gradient, mixed vs valid-only,
head i bez head, źródłowy exposure. Ruff PASS; root mypy **1 source PASS,
32,70 s** po wcześniejszym helper timeout55 bez werdyktu. Raport
`artifacts/TASK1167_R1_CORE_FIX.md`.

## P2-2 — jeden bounded bundle contract

Nowe domain/storage `grid_content_bundle.py`: 16 MiB, typed
CONTENT_EXPERIMENT_BUNDLE_TOO_LARGE, stat + bounded limit+1 read przed JSON.
Known-input/bank lower bound przed optimizerem, pełny końcowy export check,
recovery/install/inspector/assessment/runtime stosują tę samą granicę.
`geometry_core.inference.onnx_engine` i proposal runtime przyjmują opcjonalne
już zweryfikowane bytes; nowy content path nie wykonuje drugiego unbounded read.
Legacy kwargs pozostają zgodne. Nie redukujemy po cichu danych dowodowych.

Helper: **11 guard tests PASS, 11,91 s**, legacy runtime **PASS, 9,63 s**,
Ruff13 PASS, mypy12 PASS. Szczegółowe ścieżki i SHA:
`artifacts/TASK1167_R1_API_FIX_SCOPE.json`; raport
`artifacts/TASK1167_R1_API_FIX.md`. Końcowy caller
`full_board_runtime_evidence.runtime_evidence` także używa bounded readera,
zachowując legacy COMPLETENESS_PRESET_SIZE/CHANGED i SHA przed JSON. Dodatkowy
targeted stat/read-growth + hashguard: **1 PASS, 2,20 s**, Ruff obu plików PASS,
mypy jednego źródła PASS. Poprzednich 11 przypadków nie powtarzano. Helper scope:
15 ścieżek, drift 0. Był to checkpoint sprzed dodatkowej zgody na AC8; wtedy
adapter nie był wdrożony i obowiązywał blocked. Późniejsze zatwierdzone domknięcie
opisano poniżej; zachowano prawdę o kolejności wyników.

## AC8 — centralne częściowe A i pełny zakres R2

Poprzednia korekta parity-only była niewystarczająca dla evaluator, production,
calibration i niezależnej storage projection. Centralny
`GridBoardDataset._partial_assessment` dopuszcza częściowe A tylko przy snapshot
v4, policy v4, content sampling v1 i jawnym purpose A. ContentSelectionDataset
zachowuje strict entry, dziedziczy tę samą regułę. TRAIN/B/legacy bez opt-in nie
dostają nowego uprawnienia. Dawna asercja odrzucenia tego samego new-policy A
została świadomie skorygowana; odrębne negatywne testy utrzymują stare granice.

Nowy `test_grid_content_partial_selection.py`: **3 PASS, 10,64 s**. Rzeczywiste
frozen pixels/readers/renderer i evaluator/calibration/projection, ścieżka R0
oraz combined R2; inferencja jest jawnym fixture. Małe B/REG pozostają
unqualified, bez whole-photo claims i bez udawania operatorowych 30+30.
R2 musi sprawdzić całe funkcje z `TASK-1167_R2_AC8_READ_MAP.md/.json`: menu A,
sealed B, 30+30 real sources, REG bez strojenia, variant/path identity,
runtime qualification i obydwa rzeczywiste callery. R1 nie przeczytał tego
zakresu w całości. Odkrytą przed freeze lukę wspólnego progu dla BASE320/WIDE480
uzupełniono po osobnej zgodzie operatora oraz D592; wyniki pełnego nowego adaptera
i jego ograniczenia opisuje poniższy końcowy odbiór AC8. Niezależny R2 pozostaje
wymagany i nie jest zastępowany niniejszym raportem wykonawcy.

## P2-1 — zaakceptowane ryzyko wydajności

Root zaakceptował osobny T4 P2-1: registry view/list powtarza fizyczny TRAIN
decode i ONNX load. Nie zmierzono opóźnienia. Cache samego JSON SHA ukrywałby
zmianę assets; nie wprowadzono go. Przyszły owner: registry view/inspection,
z jawną semantyką statusu i invalidacją. To odrębny koszt od T3 P2-1 replay.

## Jakość i wcześniejsze próby

Primary Ruff10 PASS; mypy4 source PASS oraz osobno oba partial-A readery PASS.
Logi `...-primary-ruff-final.log`, `...-primary-mypy.log`, `...-partial-types.log`.
Nie ponawiano niezmienionego ONNX/PG ani całych suites.

Trzy wcześniejsze R3 fixture runs: 3 FAIL/4 PASS (UUID, podwójny parametr zegara,
błędny import SHA), potem 7 PASS. Partial fixture: 3 FAIL (nazwa licznika i
nieodnowiony testowy split SHA), potem 3 PASS. Jedna błędna nazwa test node:
no tests ran, nie PASS. Oczekiwań bramek nie osłabiono.
Helper 33 PASS/2 FAIL ujawnił własną regresję T4 legacy descriptor.modelVersion;
frozen R1 nie był baseline sprzed taska. Porównanie HEAD sprzed T4 potwierdziło
regresję, additive `.get` ją naprawiło bez zmiany assertions. Pozostały hardlink
WinError5: ten sam test PASS z uprawnieniem hardlink. Mypy55/60 timeout bez
werdyktu nie jest PASS; końcowe kontrole i sprawdzenie zakończenia procesów są
jawne w raportach. Żaden synthetic fixture nie kwalifikuje operatorowego modelu.

## Końcowy pion AC8 — osobne finalne warianty

Nowy v3 envelope/childv2 zamyka menu A przed B, zachowuje pełny roster i null
targets, wymaga oddzielnych30+30 dla used union A/B/REG. NONE bez WIDE nie
dostaje fikcyjnego minimum drugiego wariantu. N/A zachowuje None/manualWhenApplicable;
applicable bez referencji A nadal blokuje. Niezależny reader ponawia fizyczne
source/input/witness i dokładne partycje/menu/seal/result. Runtime używa actual
successful replacement trace, a API porównuje oddzielny inputVariant stamp,
odtwarza support i sprawdza current source box. Brak fallback WIDE→BASE.

| Dowód primary | Wynik | Log w artifacts |
|---|---|---|
| Observer→variant_run→physical API replay, dwa różne progi | 1 PASS87,95s | TASK1167-ac8-joined3.log |
| NONE actual route, tylko BASE | 1 PASS71,15s | TASK1167-ac8-none1.log |
| Cold physical replay→operationpin→runtime→finalizer, stale source/support/child/context oraz same-node BASE proof/WIDE trace | 1 PASS25,35s | TASK1167-ac8-cold3.log |
| Null zachowany w pełnym rosterze + actual failed recrop | 2 PASS w batch32,33s | TASK1167-ac8-cold2.log |
| Exact legacy receipt bytes i lost-response replay | 2 PASS8,96s | TASK1167-ac8-legacy-receipt.log |
| Ruff9 | PASS | TASK1167-ac8-lint-final.log |

Pozytywny fixture:64 małe kontrolowane JPEG/264 częściowe cele (A4×6,B30×4,
REG30×4), osobne good/bad per wariant i jawny overlap źródeł. NONE:132 cele.
Prawdziwe canonical files, source SHA, frozen refs, renderer/support, file replay
i API reader; detekcje oraz modelowe metadata są kontrolowane, bez ORT/treningu.
Istniejący assessment reader dopuszcza częściowe B/REG; nie zmieniono jego
bramek i nie deklaruje się tym dowodu5pełnychREG/whole-photo/T3quality.

Wcześniejsze normalne FAIL115,31s i83,00s wynikały z niewłaściwego A fixture:
applicable rescue bez A referencji, następnie A niepokrywające faktycznego
neighborDeviation. Dodano właściwe A przykłady w NOWYCH immutable fixture,
nie zmieniono progów, minimów ani starych sealed danych. Cold1 FAIL19,54s był
złym kluczem testowej FeatureVector; cold2 2PASS/2FAIL32,33s — niepasujące WIDE
features w counterexample BASE oraz sandboxowy WinError5 hardlink. Po korekcie
fixture i uprawnieniu do własnego testowego katalogu wskazane przypadki PASS.
Stage PNG fixture wcześniej odrzucony przez canonical JPEG guard; poprawiono
format fixture, bez monkeypatch admission. Wszystkie logi zachowane.

Pierwsze mypy8 przerwano po >60s bez wyniku; własne PID/dzieci zakończone,
sprawdzony brak orphan. Wersja verbose zakończyła się78,48s:4 błędy typów w
jednym nowym module, pozostałych7 bez błędów. Doprecyzowano typy loaderów/null
guard; końcowy pojedynczy moduł PASS (`TASK1167-ac8-types3.log`).
Pełny opis: `artifacts/TASK-1167_AC8_PRIMARY_REPORT.md`; osobne API/domain/DTO/
SDK i current-source PG dowody dostarcza raport helpera. Bez nowej szerokiej
powtórki4800-step/ONNX/PG, operatorowego uruchomienia ani deklaracji audytu PASS.

API AC8 helper zakończony: `artifacts/TASK-1167_AC8_API_HELPER.md`, manifest
`TASK-1167_AC8_API_SCOPE.json`47 source/test/generated paths, drift0. Numeric/legacy
calibration18 PASS4,19s, dodatkowy runtime N/A1 PASS1,31s, po stamp affected2
PASS1,80s; actual router GET/list1 PASS2,18s; verified bundle dispatch1 PASS2,79s;
stamp/currentbox/proposal roundtrip2 PASS1,12s; legacy proposal24 PASS0,70s.
SDK requests4+5 PASS, SDK/Admin typecheck, OpenAPI drift/generated i lint/format
PASS. To kompozycyjne scoped wyniki, nie sumowany pozorny jeden pełny suite.

Nowa rzeczywista granica current source support ma osobny mały disposable PG:
1 PASS20,90s (`TASK-1167-AC8-stamp-pg1.log`), własna app rola, full/crop registry,
physical byte/pixel/dimensions, original_deleted/livecopy/missing target. Cold
child wymaga jawnego owned URL oraz niezależnego expected DB name przed connect
i sprawdza current_database przed SQL. Fresh cleanup0baz/0ról; żadnej operator DB.
Nie powtarzano dużego parent/cohort workflow. To dodatkowy test NOWEJ granicy,
nie ponowne badanie niezmienionego T4 PG.

API typy: pierwsze15 źródeł miały inferred dict w nowym module, potem poprawiony
moduł PASS; final15 miały tylko konflikt nazwy wyjątku, poprawiony moduł PASS.
Stamp8 źródeł mają7 bez błędów oraz jeden niezwiązany Row-vs-tuple w historycznej
funkcji virtual repository(current2901). Wąski fresh HEAD shadow jednoznacznie
odtworzył identyczny błąd HEADac724d29:2889;12 dodanych linii przesuwa numerację.
Nie nazywa się całego mypy8 PASS i nie naprawia obcej funkcji. Dowód to
`TASK-1167-AC8-stamp-head-receipt.json` i przypięte logi. Pierwszy TestClient
bez loopback zakończono bez wyniku; ten sam test z uprawnieniem PASS. Wszystkie
wcześniejsze fixture/type/lint błędy i ich poprawione próby są jawne w helper report.

## Root: końcowe bramki przed focused R2

Po zamrożeniu kodu primary/API wygenerowano mapę, a niezależnie zakończono
`npm.cmd run docs:check` i `npm.cmd run code-map:check` — PASS. Logi:
`artifacts/TASK-1167-ac8-root-map-generate.log`,
`TASK-1167-ac8-root-docs-final.log`, `TASK-1167-ac8-root-map-check.log`.
Docs:654anchorlinks/590entries, startup43959B/45000B. Root dopisał D592,
wymagania/architekturę/API oraz to zatwierdzone podsumowanie po source freeze;
finalny pakiet R2 zamraża ich aktualne bajty. Nie są to nowe testy treningu,
operatorowe etykiety ani werdykt audytora. R2 pozostaje wymagany przed commitem.

## Rzeczywisty focused R2 i izolacja commita

Po Anthropic429 i potwierdzeniu braku orphan wznowiono dokładnie ten sam
brief03ae9457.../request79d35b6f... jako transport2 po wskazanym resecie.
514,27s, terminal Opus5.5, high requested; formalny R2 PASS0P0/0P1.
ReportSHA dda8228daa5a8fdbbaef6567737a29e99aaa17f81584e9522966139e718df40c,
matching public receipt przeczytany i zweryfikowany. R1 i blocked transport
pozostają zachowane. Dowód root: artifacts/TASK-1167_R2_VERIFIED.json.

T4-only tree d0ba8e63c89e89ac4eeb8cc5b314c850ced49e06 zachowuje audytowane
źródła niezależnie od trwającego T5.139 product/context blobs odpowiada F
po normalizacji Git CRLF; żadnych różnic. Nowe źródła T5 i D593 nie trafiają
do T4 commita. P2-1 zaakceptowany; P2-4/5/6 wymagają oddzielnej delty/odbioru
T5 i nie są przedstawione jako zamknięte przez ten raport R2.

Staged-only root verification:4 kontrole dokumentacji i generate_code_map --check
PASS w izolowanym checkout-index, bez źródeł/dokumentów T5. Weryfikacja obejmuje
staged tree i exact frozen product sources;4nowe P2 są jawne w R2, trzy mają
osobny handoffT5. Dowód: artifacts/TASK-1167_STAGED_VERIFICATION.json.
