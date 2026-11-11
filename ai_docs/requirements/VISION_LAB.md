---
title: Laboratorium geometrii i symboli — wymagania
status: accepted
last_updated: 2026-11-11
---

# Laboratorium wizji

## Zgodność oceny korekt (TASK-1182)

Ocena PyTorch korekt używa jawnego FP32 bez TF32 i autocast, niezależnie od
ustawień treningu. Zakończenie oceny lub jej błąd przywraca poprzednie ustawienia.
Progi poprawności plansz i reguły wyboru checkpointu pozostają bez zmian.

Eksport uczenia grid-only korekt sprawdza całe zamrożone A każdej gry:
rzeczywiste wejścia obu grafów, dopasowania, dopasowanie siatki i decyzje
poszczególnych plansz. Tolerancja surowych wyjść nie usprawiedliwia zmiany
decyzji, preferencji wybranego checkpointu wobec zapisanej historii ani warunku
niepogorszenia błędu A względem bazy. Rozbieżność blokuje eksport z trwałym
raportem. REG nie uczestniczy w tej kontroli i pozostaje końcowym testem ONNX.
Odzyskanie eksportu ponawia kontrolę A oraz wymaga tego samego dowodu wejść.
Historyczne raporty i wagi nie są przepisywane.

## Nowe pełne wycinki (D-598, TASK-1175)

Aktualny resolver może przypiąć pełne pole0% również do istniejących wag
klasyfikatora. Nowy token nie jest nowym dowodem jakości. Historyczne piny,
adnotacje i geometrie pozostają odtwarzalne, a zmiana renderu unieważnia dowód
dla poprzedniego paddingu. Import i aktualny kontrakt pomiaru nadal są osobne.
Przeniesiona kalibracja8% nie kwalifikuje automatycznej akceptacji pełnego pola;
predykcje pozostają propozycjami. Brak GT nie zamienia się w deklarację poprawy.

## Przypięty zwykły podgląd (D-594, TASK-1170)

Zwykły edytor ma trzy niezależne warstwy: siatkę pól z dokładnie zapisanych
24 punktów, obrysy grafik z aktualnych etykiet oraz rzeczywiste zakresy
produkcyjnych wycinków. Legenda opisuje je tekstem. Powiększony kadr do
oznaczania zawiera otoczenie i nie udaje produkcyjnego rastra ani wejścia NN.
Brak quadu nie tworzy obrysu, także jeżeli archiwalny szkic ma boxInPreview.
Pochodzenie, rewizja i zatwierdzenie zawartości są jawne; odczyt ich nie zmienia.

Footprint wymaga aktualnego, zgodnego manifestu renderowania. Braki są jawne,
z licznikiem dostępnych wycinków, bez zastępowania ich całymi polami.
Niezgodne manifesty lub błędne komórki nie blokują istniejących adnotacji i edytora:
zapisane punkty oraz poprawne footprinty pozostają dostępne z jawnym kodem.
Częściowa komórka może mieć rzeczywisty footprint poza zdjęciem; pokazuje się
go bez przycinania współrzędnych i bez deklaracji realnych pikseli poza kadrem.
Nowe podpowiedzi i pomocnicza galeria chronią całe źródła wszystkich zapisanych
ślepych sesji, również kopie o tych samych pikselach i inne sloty; nowe preview
chroni też B/REG. Historyczny zwykły odczyt i zapis etykiet pozostają dostępne.
Ślepy kontroler zachowuje pusty canvas i nie pobiera nowego preview.

Domyślne pomocnicze przygotowanie to odczyt bieżących adnotacji przez
`scripts/export_grid_content_preview.py`. Nie uruchamia generatora jasności/
koloru, nie regeneruje detektora i nie zapisuje ani nie zatwierdza szkiców.
Zachowuje istniejące szkice do sprawdzenia; galeria obejmuje wyłącznie TRAIN
poza chronionymi źródłami. Archiwalne helpers/overlay PNG nie są źródłem obrysów.

## Izolowane oznaczenia i rzeczywisty HTML (D-593, TASK-1168)

Zwykły edytor15pól obejmuje również B/REG, a osobny ślepy pomiar TRAIN/A
zaczyna każdy cel/przebieg od pustego canvasu. Zwykłe etykiety, szkice i
predykcje nie wchodzą do ślepego kontrolera. Retry zachowuje dokładną komendę,
bez odtwarzania jej dawnych punktów na ślepym canvasie. Zapis content labels
nie zmienia geometrii ani symboli.

Lista celów i plain asset są przypięte do źródeł zamrożonej kohorty i dostępne
przed pierwszą etykietą. Operator wybiera zdjęcia po nazwie/roli, bez ręcznego
wpisywania SHA/UUID. Konflikt live sekwencji dotyczy jednej planszy i nie
ukrywa frozenPinCoverage; nie znosi niezależnych warunków aktualności oceny.

HTML pokazuje15rzeczywistych rastrów produkcyjnego klasyfikatora oraz źródłowo
zweryfikowany RGB wejścia NN. Szerszy podgląd i brak zapisanego tensora są
jawne. CLI tworzy pinned pakiet bez ręcznego JSON; niepewne dopasowanie nie
udaje poprawnego porównania. Dokładny kontrakt i ograniczenia opisuje D-593.

## Kontrolowane warianty pełnych symboli (D-592, TASK-1167)

Istniejące uczenie przyjmuje jawny opt-in `full-symbol-content-experiment-v1`.
Jeden proces porównuje R0–R3 z tej samej bazy/danych/ziarna, po1200 ukończonych
kroków, ze wspólnym limitem4800kroków/7200s i rezerwami1500/1500/2100/2100s.
Ponowienie lub restart nie odnawia budżetu; nieukończone ramię nie jest wybierane.
Gotowość metadanych nie zastępuje pomiaru kosztu na urządzeniu workera.

Historyczny TRAIN pozostaje dostępny do powtórnego uczenia. Jedynie bank
rzeczywistych błędnych obszarów wymaga dodatniego dowodu ancestor-unseen dla
wybranego podzbioru TRAIN; nie korzysta z A/B/REG. R2 używa obu rzeczywistych
rozmiarów wejścia, R3 dodaje nadzorowaną głowicę obwiedni15pól, bez klas symboli.
R3 uruchamia się wyłącznie po niezaliczonym A przez ukończone R2, przy gotowych
etykietach i pełnej rezerwie. Ranking A waży gry równo i nie kompensuje nowych
uszkodzonych instancji. Zaliczone A ma pierwszeństwo także dla checkpointu.

Kandydat z niezaliczonym A może być wyłącznie informacyjną propozycją z tym samym
zmierzonym routingiem; nie dostaje publikacji/defaultu/automatu. Braki B/REG
pozostają jawnym brakiem kwalifikacji. Dokładny kontrakt i ograniczenia opisuje
D-592; stary workflow, raporty i ręczne korekty zachowują swoją interpretację.


Automat nowego eksperymentu ma osobne progi dla faktycznie zwróconych
zwykłych i szerszych wejść. Każdy używany wariant spełnia własne minima30good
+30bad źródeł w B i REG; łączna liczba obu wariantów nie wystarcza. Brak
wariantu lub niejednoznaczny wynik pozostaje w raporcie i blokuje kwalifikację.
Szersze wejście nigdy nie dziedziczy progów zwykłego. Nieobserwowany wariant
pozostaje ręczny. Historyczne profile i raporty zachowują swoje reguły.

## Ocena produkcyjnej zawartości (D-591, TASK-1166)

Nowa ocena rozróżnia `finalContentState` rzeczywistego rastra klasyfikatora od
`inputContentState` wejścia sieci geometrii. Utrata pikseli na wejściu NN może
blokować automat, lecz nie zmienia pełnego końcowego wycinka w clipped. Geometry
proxy nie zastępuje pełnej, zatwierdzonej obwiedni symbolu. Unknown i opcjonalne
fragmenty nie dają dowodu preserved; brak detekcji lub renderu to missing.

Każda oznaczona instancja i każda wymagana gra A/REG mają stały mianownik dla
bazy i kandydata. Nie wolno kompensować nowego pogorszenia, obcego pola, remisu
lub pełnego obcego symbolu poprawą innej instancji. Wymagane są jednoznaczne
Hungarian/slot binding, brak regresji recall/board/full-photo correctness oraz
FP/duplikatów na pełnych zdjęciach i NME≤base+zamrożoneδ. Bieżąca gra wymaga
co najmniej jednej dodatkowej poprawnej planszy z15visible/preserved bez
niejednoznaczności. REG wymaga5pełnych opisanych zdjęć per gra; partial nie
ustanawia poprawności całego zdjęcia, unknown>10% roli blokuje ocenę.

Dowód dotyczy przypiętych rzeczywistych ustawień wycinka. Zmiana paddingu,
rozmiaru, interpolacji lub wersji renderowania blokuje użycie starego raportu
do publikacji/defaultu/automatycznego zastosowania. Sama zmiana wag przy tej
samej konfiguracji cropu nie zmienia geometrii. Historyczne raporty zachowują
swoją interpretację; brak nowych pinów nie tworzy kwalifikacji nowej wersji.

## Niezależna zawartość i ślepy pomiar (D-590, TASK-1165)

Obwiednie 15 symboli są niezależnymi, wersjonowanymi adnotacjami źródła po EXIF,
z aktorem, pochodzeniem i jawnym zatwierdzeniem. Zmiana siatki nie przesuwa
obwiedni. `visible` wymaga pełnego wypukłego quadu; pozostałe stany pozwalają
zapisać wyłącznie faktycznie widoczny fragment, bez odgadywania brakujących pikseli.

Dwa ślepe przebiegi TRAIN/A zapisują osobno 24 punkty geometrii i 15 stanów/quadów,
bez poprzednich adnotacji i propozycji. Pomiar obejmuje co najmniej 30 plansz na
10 zdjęciach per gra; jawny wybór slotów pozwala uniknąć wymuszenia 90 plansz.
P95 nearest-rank: u to Hausdorff wypukłych wypełnionych quadów podzielony przez
mniejszą przekątną bbox komórki z dwóch geometrii; δ to maksimum dwóch NME na
planszę, średnia na zdjęcie i P95 zdjęć. Caps .02/.002 pozostają niezmienione.
Niepoprawne dane nie dają zera; unknown ponad 10% roli oznacza `not_evaluable`.

Nowa opcjonalna polityka ocenia A względem drugiej ślepej geometrii, nie starych
punktów kanonicznych. Oracle używa rzeczywistego renderera/paddingu i blokuje
kwalifikację, jeśli sam wycinek obcina symbol. Wejście sieci ocenia się osobno.
Świeży REG wymaga pięciu pełnych oznaczonych zdjęć per gra, seed 20261108 oraz
istniejących ochron ról, ekspozycji, kopii, sesji, rodowodu i buforów. Historyczne
REG pozostają chronione, lecz nie są nowym testem. Brak etykiet blokuje nową
kwalifikację, nie legalne starsze treningi geometrii ani propozycje ręczne.
T5 dostarcza izolowany pusty edytor; T4 przekazuje opt-in przez eksperyment.

## Explicit cell visibility (TASK-1164)

The opt-in v2 geometry contract exports 24 node confidences and 15 row-major cell
visibility probabilities. A low value in any of the 15 cells blocks automatic use;
no ground-truth mask may hide weak runtime output. Historical contracts keep their
original interpretation. Missing metadata does not establish trained visibility.

Visibility supervision uses human-approved content references, independently of
geometry revisions: visible=1, occluded/out_of_frame=0, unknown=masked. Crop,
source padding and artificial occlusions update content availability using content
quads and actual pixels. Geometry points alone never create content labels.
Before augmentation, each required TRAIN game needs 30 unique positive and 30
unique negative cells, each class spanning at least five source photos after
pixel-copy deduplication. Missing coverage masks this loss and prevents automatic
qualification; otherwise admissible geometry learning remains available.

The new inputEdgeClearance signal measures the distance of raw outer nodes from
real crop/source support in nominal cell units. A selects one threshold for the
exact input/routing variant: fewer missed cuts, fewer unnecessary rescues, lower
threshold. At least five real cut boards from three A photos are required.
Insufficient data leaves the threshold unknown, never PASS. This signal is a
suspicion of missing content, not proof that all omitted rows can be detected.
T1 supplies the optional supervision interface; durable reference collection and
new training-arm admission remain the responsibilities of T2 and T4.
Geometry-only coverage is a proxy and cannot supply the five verified cut boards.
The actual content reference and its revision must be pinned independently in A;
missing T2/T3 evidence keeps the new automatic path unqualified.

## Actual-input presentation (TASK-1159)

The compact panel separates proposal quality, per-game automatic qualification,
training readiness and human geometry labels. Details remain advanced. File-backed
HTML distinguishes the original, actual network input, saved geometry, baseline
and candidate. Viewport framing never changes the input; margin is read from the
archived preset/request. RGB uint8 previews and float32 tensor identities differ.

Only a completed exact request with matching source/model/preset/version and actual
raster can support rescue input replay. Reserved-without-result, alias receipts and
missing managed-crop rasters are explicitly unavailable. V1 history stays unchanged.
The actual saved diagnostic case462205 has two T1 records and no qualified human
GT. The150-board/101-photo gallery is historical comparison; only462205 has these
two input records. It does not claim current labels or complete input diagnostics. Diagnostic registration and new model
training were not performed by the presentation task.

## Model capabilities and game qualification (TASK-1156, D-585)

New operations support boards of five columns and three rows, on pages of
three columns and three rows. Capacity does not require nine present boards;
the attested source range remains authority. `expectedLayoutCount` limits game
sequence numbers and does not declare page topology. Unsupported layouts stop
before neural inference and preserve the source for manual work.

A compatible new game receives proposals. Automatic geometry requires an exact
server-owned passing evaluation naming that game. Historical admission, family
labels and another game's report do not qualify it. Preparation freezes qualified
evidence or an unqualified state; retries never upgrade or substitute evidence.
Missing/stale proof blocks automatic writes while preserving proposals. This gate
does not claim the stronger T4 calibration requirement.

Identical selection and stable import parameters are an idempotent retry, even
when a later report exists. To use new evidence on existing data, explicitly
prepare new grid reinference; a new source, model or preflight also has a new pin.
T5 must explain this and direct the operator to that action. T2 adds no new UI.
Worker geometryQualification metadata never creates human approval/GT for strict
neural jobs; true manual approvals keep their server-owned workflow.


## Reproducible input diagnostics (TASK-1155)

Diagnostics distinguish RGB uint8 previews from the float32 values actually
prepared for the runner. Screen input is NCHW with N=1; a board diagnostic
stores the exact CHW sample before runtime batching, without claiming that
the original full batch was archived. Neither stage divides values by255.
Source/model checksums, preprocessing settings, transforms, interpolation,
padding, OpenCV version and separate pixel/tensor hashes make replay explicit.
Different source pixels or an incompatible replay environment fail visibly.
Replay verifies the canonical checksum of the entire archived preset, its
screen/board contract and the supported preprocessing version. This preset
checksum is distinct from the bundle file checksum and is not authentication.

Missing archived raw nodes or qualified human geometry remain unavailable;
fitted nodes and a saved automatic disposition cannot substitute for either.
Readiness metadata counts use the existing human-evidence qualification and
are separate from diagnostic comparisons used to design models or thresholds.
The read budget is explicit and expandable; a truncated or continuation page
does not claim complete population readiness. Nine qualified human boards
establish annotation completeness, not eligibility of roles, copies or ancestry.
Actual diagnostic examples are listed for T4 to exclude, with known copies and
groups, from new VALIDATION-B and REGRESSION. Readiness access alone does not
reassign controls. Diagnostics change neither existing labels nor role history.
Reports count only the nominal-current-human source population and explicitly
list retired/removed source rejections. SQL errors and deadlines abort publication.
Frozen labels and full-photo counts include only used sources. Diagnostic uses
retain record checksums, sequence/position bindings and stable deduplication keys.

## Incremental correction cohorts (D-582, TASK-1139)

New learning uses `application-grid-corrections-v2`. Actual uses, existing buffers,
explicit holdouts, ancestry and entire known copy/session components stay protected.
Only legacy metadata reservations without any component protection may be released;
freeze appends release evidence atomically, never edits history. New reservations
are protected. Historical unused reservations do not invalidate actual old controls
after a lawful release.

With sufficient controls, deterministic protected islands admit additional labelled
TRAIN blocks beyond ten complete photos from controls. Unlabelled tails remain free.
Up to five pending photos per control role may be reserved in protected neighborhoods
without consuming TRAIN. Missing reserves are explicit. The bootstrap retains the
bounded solver and original minima. Unknown ordering still means an indivisible import.
This policy does not claim a 70/15/15 optimum. Labelled exclusions have explicit reasons.

Ready/preview counters share deduplicated split representatives and expose photos
and boards. Available TRAIN boards partition into previously used exact labels and
new labels; used/new photo counts may overlap when one photo contains both.
Control counts describe current labels, not the size of a completed evaluation.
Unlabelled reserves have zero measured boards; buffers are also exclusions when labelled.

## Photo-only correction cohorts (D-577, TASK-1120)

The explicit `application-grid-corrections-v1` policy extends the existing cohort
workflow for grid-only human corrections without declaring fictitious recordings.
Legacy cohorts retain their full-control and recording requirements. Complete
imports, including unlabelled photos, define ordering and buffers. Exact byte/pixel
copies and known recording components are indivisible. Protected uses never become
TRAIN; TRAIN ancestry never becomes an independent control. Unknown session and
ancestor evidence is an explicit photo-only limitation, not independence.

Logical `seq_*` names must agree with current geometry attestations. Where only
managed SHA names survive, the operator-approved `verified-attestation-order-v1`
uses checksums, slots, sequence bindings and nonoverlapping ranges. UUIDs, times
and ordinals prove no chronology. Unordered imports remain indivisible; contradictory
sequence names block. Each ordered import permits one to three consecutive blocks,
each role once, with ten unique source photos between blocks. Exact bounded search
minimizes total deviation from 70/15/15 after buffers in this class of partitions.
Resource exhaustion reports a limit, never an incomplete optimum.

TRAIN needs 30 boards and ten photos; each control needs 15 boards and five photos.
Partial controls qualify only in the new grid-only policy. Exact human labels and
weights retain D-556 proofs. Preview consumes no role. Freeze atomically records
actual photo uses and every buffer in the private recording registry. Buffers,
aliases and known sessions protect future iterations and legacy cohort commands.
Changed populations require a fresh preview; history is immutable. Snapshot metadata
records ordering methods, ranges, representatives, roles, buffers and limitations.
This policy alone does not authorize training, evaluation or publication.

## Correction learning and scoped evaluation (D-578, TASK-1121)

The grid-only corrections preset accepts partial VALIDATION and REGRESSION photos
through training and evaluation. It measures only their human-labelled boards;
false detections and whole-photo completeness remain unavailable on partial photos.
Full photos additionally retain false-board, duplicate and complete-photo guards.
Node error is the mean of 24 distances divided by the ground-truth bounding-box
diagonal, clamped to one; missing predictions score one. Matching remains one-to-one.
Checkpoint selection uses VALIDATION photo-macro board correctness, then lower
photo-macro node error, then the earliest step. Shared training weighs games equally.

Report v3 and gate v2 require nonregression for every required game and both roles.
The current game's REGRESSION must gain at least one correct board or reduce error
by both five percent relatively and 0.001 absolutely. These product thresholds do
not prove statistical significance or session independence. Required scope includes
the current game, every TRAIN game and the verified previous default's explicit
scope. Legacy report labels cannot invent game IDs. Confirmed exclusions retain
their reasons and historical protections; current and TRAIN games cannot be excluded.

The durable parent previews metadata and cost, pins the default and source split,
creates/finalizes the cohort, trains and evaluates through existing child jobs.
Readiness exposes pending worker runtime checks. Admission never shrinks data.
Restart, lost responses, cancellation and resume preserve child identities and the
original budget. Status GETs do not advance the workflow. Starting this workflow
does not publish, activate or change game assignments.

A scoped candidate may replace the default only while its declared base is still
the current default, checked under the registry lock. Reaffirming the same head
and replaying a successful receipt remain safe. Concurrent replacement requires
fresh evidence instead of silently dropping the new default's evaluated scope.

Readiness exposes nullable `dataAvailability`: deduplicated annotated photos and
boards before role/buffer allocation, aggregate minima and server-computed deficits.
Deficits are lower bounds, not a claim that adding exactly that amount makes a split
possible. `minima`, `infeasible` and `ready` distinguish shortage from protected
partition failure and a successful split. Unmeasured availability is null; an
infeasible split does not invent per-role counts. Existing `roleCounts` describes
only the actual allocation after buffers, never the whole available population.

An additional assigned-model comparison is separate evidence: the server pins the
game's actual assignment, revision and baseline descriptor. It never substitutes
that model for the candidate's declared base or overwrites the publication report.
Apply must still verify current evidence and compare-and-swap the assignment (TASK-1122).

## Larger isolated RGB experiment (D-506)

An explicitly versioned local multi-reference experiment may add only independently
agreed high/high exact AI crops to the qualified R2 cohort. Preserve all human
origins, validation, diagnostic and photo-disjoint audit evidence. One new RGB
variant is bounded to 20 epochs, 7200 seconds and 50000 steps in its immutable run
root. Earlier generation1–4 and reference limits remain unchanged. Selection and
calibration use human84 only; per-class regression against V4 RGB and R2 RGB blocks
acceptance. Require real best_weights and CPU ONNX parity before success. The
experimental model cannot automatically activate or modify production labels.

## Isolated AI-assisted experiment (D-505)

The user's2026-10-06 autonomous-training/internal-AI instruction permits a
separate experimental symbol cohort with explicit ai_visual_assessment origin.
Two blind, exact-raster visual reviews must agree high/high on a readable crop.
Human approvals and raw batch trainable=false remain untouched. Preserve full
source/dictionary/base/exclusion gates and frozen human validation. Withheld
photo-disjoint AI examples from the same film measure AI agreement only.
One bounded generation4 pair cannot automatically qualify or activate production.
No AI-derived Super targets or whole-grid approvals are created.
New exact human approvals retain original provenance and take priority over AI;
operator unreadable/grid_issue decisions exclude those rasters. New human-training
photos cannot be in the AI audit; selection is frozen before any experiment run.

## Qualified feedback diagnosis (D-504)

Unlabelled inference with generation3 requires actual parity-qualified exports
and a recomputed per-class gate against the identical frozen V1 validation.
It preserves full recording/alias/protected exclusions, including external
feedback sources and diagnostic_test. Independent-folder diagnostics remain
unlabelled and cannot report accuracy. New case review retains current base
approval history/dictionary and exact immutable case rasters after full cohort
qualification; unrelated raw training sources need not be rehashed on every UI
operation. Cases stay trainable=false. Existing reference behavior is unchanged.

## Exact relocation of reviewed sources (D-503)

A moved complete recording may retain its logical identity and labels through
an explicit manifest-bound source location. Every filename/source SHA and exact
reviewed crop must match the qualified inventory. Other metadata cannot be
remapped. No location configuration preserves the strict original behavior;
source content drift always blocks training. The operator's 2026-10-06
declaration covers each new directory as an independent film, while moved
duplicates and technical aliases remain the same recording.

## Exact symbol feedback qualification (D-502)

An operator-approved exact raster/class may enter a separate classifier-only
cohort after current quad re-rendering, source/PNG/dictionary/history checks and
whole-recording split qualification. This never approves other cells, a photo,
whole geometry, sequence or geometry-training targets. Raw batch_crop_review
remains trainable=false; only the explicit derived manifest is trainable.
Preserve original D-498 assignments and strict default consumers. Protected,
comparison, cross-game, alias, label/source drift and cross-partition pixel/photo
duplicates block qualification. Recording declarations must come from the operator.

For the bounded next Mumie iteration, first recording1–23175 is excluded in
full from new training. Its9 labels are a limited diagnostic_test, not a blind
final benchmark. Use264 unique development (246 existing+18 feedback) and
unchanged84 validation, with all10 classes in both. Selection/calibration uses
only validation. Feedback sampling weight4 does not create extra labels or
increase the reported unique cohort. Validation/test data never enter sampling.

Generation 3 is bounded to one admitted RGB and one gray run from scratch,
with the existing durable budgets and exact sampler/RNG resume. Report the
18 training feedback outcomes separately from validation and the diagnostic
labels evaluated after selection. Missing sources block execution, preserving
decisions and artifacts; never substitute an identically named photo whose
SHA differs. An interrupted pre-training attempt is not model qualification.

## Przygotowanie aktualnych etykiet Mumii (TASK-0853)

Pakiet przygotowawczy zawiera wyłącznie najnowsze ważne decyzje approve
aktywnej wersji D-496. Zachowuje dokładne cropy, tożsamości i pełną historię
symboli jako dowód; stare decyzje nie są próbkami. Liczność 30 na klasę jest
celem zbierania przykładów, nie sztywną bramką kwalifikacji.
Raport ujawnia liczności, komponenty, duplikaty i blokery. Pakiet ma
purpose=qualification_only i trainable=false, bez przydziałów train/validation.
Nie zastępuje potwierdzenia nagrań i splitu T06b. Klasa symbolu nie jest
etykietą obecności ramki Super; jej uczenie wymaga odrębnych zatwierdzeń.

## Wersja referencji etykiet po korektach geometrii (D-496)

Jawnie zaakceptowana wersja `lab-symbol-label-reference-v1` pozwala etykietować
przypięte, aktualnie zatwierdzone zdjęcia mimo stale dawnego splitu geometrii.
Nie zastępuje splitu ani zgód. Zachowuje oryginalną historię, receipts, słownik,
role i historyczne użycie, bez ponownego nadania zgody przez narzędzie.
Chronione role i całe komponenty z dawnych oraz aktualnych powiązań pozostają
niedostępne przed odczytem pikseli. Zmiana geometrii, katalogu lub aktywnego
słownika zatrzymuje wersję; operator potrzebuje nowego jawnego preview.
Ta referencja nie kwalifikuje danych do treningu, nie nadaje verified i nie
tworzy podziału symboli. Bez konfiguracji obowiązują dotychczasowe guardy.

## V3-D — shadow w aplikacji (D-495, TASK-0805)

Jawnie uruchomiony etap porównuje na tym samym niezmiennym zdjęciu 5 × 3
obecną geometrię i propozycję sieci. Domyślnie jest wyłączony. Operator
uruchamia ograniczony job dla 1–20 zmaterializowanych źródeł; staging nie
jest materializacją. Historyczna nazwa/wydanie gry ani brak słownika symboli
nie blokują samego porównania.

Propozycje i powody są zapisane oddzielnie z wersją modelu, SHA obrazu i
rewizjami. Każda wymaga ręcznego przeglądu; niekalibrowane Mumie nigdy nie
dziedziczą pewności runu1. Brak siatki nie usuwa aktywnego slotu. Dodatkowe
wykrycie nie zwiększa liczby slotów wynikającej z poświadczonego zakresu.
Rozbieżne metadane mają błąd, bez cichego ograniczenia numerów.

Admin pokazuje pełne węzły i obecną siatkę; aktualny slot można otworzyć w
istniejącej korekcie Reviewera. Jeżeli edytor odtwarza siatkę z narożników,
oznacza ją jako szkic do korekty, nie pełną zaakceptowaną siatkę sieci.
Zmiana SHA/revision oznacza stale i blokuje przekazanie starej propozycji.
Start, odczyt i worker shadow nie zmieniają geometrii ani decyzji symboli.

Migracja, aktywacja, przebieg na danych i odbiór skali pozostają osobne.
Kontrakt: `delivery/GRID_V3_SHADOW_CONTRACT_20261005.md`.

Hybryda D-457 jest jawnym wariantem podglądu, nigdy nowym domyślnym silnikiem.
Poprawia obrazowe propozycje baseline zamrożonym MobileNetV3-Small i uczoną
głowicą narożników. Ręczne węzły służą wyłącznie targetom i ocenie; nie tworzą
cropu wejściowego. Brak anotacji oznacza unknown, nie absent; brak presence-head
i kalibracji oznacza, że każda poprawna propozycja wymaga ręcznego przeglądu.
Nie dopełnia się wyniku do dziewięciu plansz. Nieobsługiwane 3 × 3 pozostaje jawne.

Pilot wykorzystuje wyłącznie development/validation; wybór modelu na zdjęciu
final_test/unseen jest blokowany przed dekodowaniem. Najlepsza ukończona epoka
jest wybierana stałą metryką walidacyjną z karą za brak lub nieważną propozycję,
nie tylko na łatwych dopasowanych planszach. Raport rozróżnia rzeczywiste węzły
baseline od początkowej homografii hybrydy oraz ujawnia brak poprawy.
Jedna próba smoke i jeden niezależny trening zachowują budżety D-457;
walidacja, eksport ONNX, kontrola zgodności i publikacja należą do tego samego limitu.
Sukces i odczyt wymagają zgodnych checksum artefaktów. Galeria pokazuje wybraną
epokę i informację o niekalibrowanej bramce, bez automatycznych zatwierdzeń.

T04 dostarcza trwały backend runów z idempotentnymi start/cancel/retry i historią
prób. Najwyżej jeden run jest aktywny. Restart obserwuje żywy proces, a nie
uruchamia drugiego. Wygasły run po potwierdzonej śmierci procesu wymaga jawnego
retry, które zachowuje budżet oraz checkpoint. T05 dodaje zamknięty rejestr
hybrydy; nieznany wykonawca jest jawnym błędem, nie pozornym sukcesem.

Checkpoint v2 wznawia na granicy ukończonej epoki. Cancel kończy pracę po takim
checkpointcie; twardy limit czasu może przerwać epokę i pozostawia ostatnią
ukończoną. Kroki rezerwuje się przed obliczeniem, a niepotwierdzony czas po
awarii nalicza konserwatywnie. Retry nie zwraca budżetu. Odczyt checkpointów
v1 jest zgodnościowy i jawnie nie gwarantuje identycznego wznowienia.

D-456 dopuszcza osobny pilot geometry-only 5 × 3 z całymi grami przypisanymi
do rozłącznych development/validation/final_test/unseen_game. W tej jawnej
polityce nie wymaga się verified rodzin wewnątrz gry ani pomiaru czasu.
Nie zmienia się pochodzenia rodzin i nie twierdzi, że są niezależne. Pełny
graf wszystkich źródeł musi pozostać wewnątrz przydziałów gier; każde znane
powiązanie przecinające części blokuje cały zapis. Wybrane targety nadal
wymagają aktualnych zgód, ręcznej pełnej geometrii, SHA oraz D-453 dla 777.
Stare polityki i ich wymagania poniżej pozostają bez zmian. Pilot nie mierzy
jakości 3 × 3, symboli, oszczędności czasu ani gotowości produkcyjnej.

Doprecyzowanie użytkownika przy wznowieniu etapu B: zapisane i zaakceptowane
siatki są referencją geometrii plansz, a nie zatwierdzeniem symboli. Część
zdjęć lub ich oznaczeń symboli może być niepoprawna. Brak poprawnej etykiety
symbolu sam w sobie nie wyklucza poprawnej geometrii z jej uczenia; etykiety
symboli nie są targetem etapu B i wymagają osobnego zatwierdzenia w etapie C.
Operator ocenia wybrane geometrie jako poprawne lub w większości poprawne,
nie jako bezbłędny zbiór. Kontrola techniczna nie zastępuje oceny wizualnej;
wykryty błąd geometrii wyłącza daną próbkę do poprawy i ponownej akceptacji,
bez automatycznego poprawiania ani nadpisywania decyzji operatora.

Szybki przegląd pokazuje jedno pełne zdjęcie ze wszystkimi zapisanymi siatkami
(linie i numery) bez galerii, rodzin i edytora. Dwa główne przyciski:
Zatwierdź/Odrzuć, po potwierdzonym zapisie następne. Kolejka stabilna według
katalogu wybranej gry/wszystkich, tylko full/present bez accept/reject/needs_correction.
Odrzucenie całego zdjęcia oznacza Do poprawy bez zmiany geometrii i bez
oznaczania wszystkich plansz. Edycja/mark/withdraw nie usuwa odrzucenia;
kasuje je dopiero jawna akceptacja spełniająca zwykłe warunki. Brak wymogu9.
Decyzja dotyczy wyświetlonych wersji i źródła po załadowaniu zdjęcia; błąd
obrazu blokuje oba przyciski. Pending blokuje wyjście i zachowuje retry.

Przegląd zdjęcia pokazuje numerowane zapisane siatki oraz cropy wybranej planszy.
Przegląd zapisanych plansz na całym zdjęciu jest przy wejściu domyślnie
zwinięty; użytkownik może ręcznie rozwinąć lub zwinąć go nagłówkiem.
Operator może oznaczyć wybrane plansze „Do poprawy” z opcjonalną uwagą lub
wycofać błędne oznaczenie. Zapis poprawki daje „Do ponownego sprawdzenia”, bez
automatycznej akceptacji i bez przejścia do następnej planszy. Po sprawdzeniu
poprawek użytkownik klika „Akceptuj całe zdjęcie”, co domyka ich uwagi.
Ta decyzja obejmuje bieżący niepusty zestaw pełnych obecnych geometrii (nie
wymaga9), nie promuje szkiców ani lokalizacji. Needs_correction i poprawki
zapisane wyłącznie jako szkic/lokalizacja blokują akceptację.
Zmiana/dodanie geometrii unieważnia akceptację tylko tego zdjęcia. Stare dane
pozostają nieprzejrzane. Filtry i badge rozróżniają „Do przeglądu”, „Do poprawy”
i „Zaakceptowane”. Akceptacja jest dodatkową bramką splitu, nie uprawnieniem
do treningu ani zmianą roli777 (D-450).

Aktualizacja folderu zdjęć tworzy nowy niezmienny snapshot. Istniejące decyzje
można przenieść wyłącznie do nowego katalogu i tylko gdy każde źródło użyte
w zapisach, timingach i historii zachowuje id, SHA oraz metadane. Zmiana lub
brak takiego źródła zatrzymuje operację. Historia, autorzy, rewizje i zgody
pozostają identyczne; operacja nie zatwierdza nowych zdjęć. Wersja T03c nie
przenosi zbiorów z rodzinami lub podziałem. Rola 777 nie zmienia się przy imporcie.

Galeria pokazuje osobne liczniki zapisanych obecnych pełnych siatek, lokalizacji
i szkiców. Filtry obejmują całą wybraną grę przed podziałem na strony; „Z pełną
siatką” oznacza co najmniej jedną pełną geometrię, nie ukończenie zdjęcia ani
kwalifikację treningową. Pozycje 1–9 i istniejące dalsze zapisy mają jawne statusy.
Kliknięcie pozycji lub numerowanego obrysu na pełnym zdjęciu wczytuje dokładny
zapis wraz z topologią i cropami; brak zapisu pozwala jawnie utworzyć propozycję.
Nawigacja porzuca niezapisane lokalne zmiany bez modalnego pytania i bez
automatycznego zapisu. Nie ma promptu przy opuszczeniu karty. Busy/pending
blokuje nawigację w aplikacji; jawny przycisk odczytu po konflikcie wystarcza
bez dodatkowego potwierdzenia. Zatwierdzenie pozycji 1–8
otwiera kolejną na tym samym zdjęciu; szkic i pozycja 9 pozostają na miejscu.
Pełne zatwierdzenie jest jawnym kliknięciem bez checkboxa; aktor nowych decyzji
geometrii to stały operator. Powiadomienia są wyłącznie toastami w lewym dolnym
rogu (wszystkie rodzaje 4 s, kliknięcie body zamyka, przycisk Kopiuj kopiuje
wyłącznie wiadomość bez zamykania; sukces kopiowania dopiero po jego wykonaniu,
wstrzymanie przy hover/focus/ukrytej karcie). Raporty i instrukcje pozostają w body.

Edytor pokazuje duże zdjęcie po lewej i zwarte cropy aktualnej siatki po
prawej (na małych ekranach poniżej). Po puszczeniu uchwytu odświeża cropy
i dopasowuje kadr do granic siatki z niewielkim marginesem. Podczas gestu
kadr jest stały. Zdjęcie zachowuje perspektywę i współrzędne źródła;
kontrolka przywraca pełne zdjęcie. Numeracja jest mała i stabilna ekranowo,
z wygodnym obszarem chwytania. Preview nie zatwierdza ani nie zapisuje danych.

Lokalna galeria pokazuje dostarczone zdjęcia, siatki i cropy. Użytkownik może
poprawiać, zatwierdzać, trenować i porównywać modele. Obsługuje 5 × 3 i 3 × 3;
integracja z obecną aplikacją obejmuje wyłącznie 5 × 3. Pełne 3 × 3 wymaga
osobnego planu dla modelu danych, review i wyszukiwania. Model startuje
review/shadow, domyślnie wyłączony; D-261 dotyczy późniejszej aktywacji.

Obecny pilot v3 odpowiada na pytanie, czy podejście w ogóle potrafi znajdować
siatki, ciąć plansze i rozpoznawać symbole. Nie jest odbiorem stuprocentowej
jakości ani skali produkcyjnej. Po ocenie wykonalności wolno przygotować nowy
zbiór i wytrenować modele geometrii oraz symboli od początku; obecne etykiety
i checkpointy nie muszą być promowane. Przed produkcyjną aktywacją lub
masowym przetwarzaniem v3 wymagany jest osobny, udokumentowany odbiór
wydajności i trwałości dla przewidywanej liczby gier, zdjęć, plansz i cropów.
Brak tego dowodu albo wynik przekraczający możliwości magazynu lub workera
blokuje wdrożenie, nawet gdy mały pilot jakościowy wypadnie dobrze.

Istniejąca gra i jej wydanie, np. `777 v1.1`, mogą być ocenione przez nowy
silnik v3 bez zmiany tożsamości gry i bez migracji starych wyników. Operator
może uruchomić na tym samym zdjęciu stary silnik i v3, a następnie porównać
oddzielne wyniki geometrii, cropów i (po ukończeniu etapu symboli) symboli.
Wynik wskazuje silnik i wersję modelu; v3 pozostaje review/shadow i nie
nadpisuje v1.1 ani zatwierdzeń człowieka. Brak mapowania symboli danej gry
ogranicza porównanie symboli, lecz nie może blokować samej geometrii v3.
Historyczna rola źródła danych nie może być używana jako blokada inferencji;
zasady dopuszczenia do treningu i etykietowania pozostają osobne (D-461).

D-453 zastępuje ograniczenie D-447 `comparison_only` wyłącznie dla geometrii
historycznego 777: te zdjęcia mają uczestniczyć w uczeniu modelu, aby obsługiwał
przyszłe podobne zdjęcia. Referencją są nowe ręcznie zatwierdzone siatki
laboratorium, bez używania dawnych geometrii silnika v1.1 jako targetów.
Historyczne pochodzenie pozostaje jawne; nie trzeba zmieniać go na 777 V2.
Kwalifikacja wymaga poprawnej i aktualnie zaakceptowanej geometrii oraz
podziału bez przecieku rodzin. Zgoda na geometrię nie zatwierdza symboli
ani nie zmienia ich dotychczasowych bramek.

Decyzja nie modyfikuje istniejących niezmiennych snapshotów ani zapisanych
ról. Jawna kwalifikacja geometrii T03e zachowuje pochodzenie i ważne zgody
na niezmienione źródła; jej techniczny kontrakt określa architektura labu. Sam import
lub przyjęcie zdjęcia nie wykonuje tej zmiany. 777 V2 nadal wymaga deklaracji
użytkownika dla nagrania/rodziny i kontroli konfliktów checksum oraz
podobieństwa. Brak trafienia podobieństwa nie dowodzi niezależności.

Operator deklaruje, że zdjęcia pozostałych pięciu gier z folderu
`C:\Users\tuszy\Documents\game_predictor_traning_set` pochodzą z innych
zakresów/folderów nagrań niż materiał wskazany do dotychczasowych siatek;
ocenia je jako zdjęcia z odległych brzegów nagrań, oddzielone kilkoma
katalogami. To deklaracja pochodzenia, nie dowód wynikający z nazw plików.
Pozostaje techniczne przypisanie źródeł do rodzin i kontrola konfliktów
z dotychczasowym zbiorem. Brzegi tego samego filmu należą do jednej rodziny;
różne foldery nie oznaczają automatycznie niezależnych filmów.
Nierozstrzygnięte powiązania wykluczają zależne próbki do wyjaśnienia.

Oprócz zatwierdzenia DB dopuszcza się `lab_human_approved`: niezmienną
decyzję człowieka z grą, wersją słownika, obrazem źródłowym i SHA-256,
planszą, komórką, rewizją geometrii, dokładnym cropem i SHA-256, etykietą,
rewizją zatwierdzenia i czasem. Zmiana cropa lub geometrii wymaga ponownego
zatwierdzenia nowych pikseli przed treningiem. Predykcja nie jest decyzją.
Zapis laboratoryjny nie podszywa się pod DB review i nie zmienia istniejących
reguł kohorty bazodanowej. Gra bez DB ma lokalną tożsamość i ręcznie
zatwierdzony słownik; rejestracja kandydata wymaga jawnego mapowania do gry
i symboli aplikacji, bez automatycznego tworzenia rekordów.

Anotacja lokalizacji zatwierdza obecność, topologię i narożniki. Pełna
geometria zatwierdza wszystkie węzły i granice komórek. Anotacja symbolu
zatwierdza dokładny crop i klasę. Interpolowana siatka jest propozycją,
nie pełną referencją. `unknown`, nieczytelność i błąd siatki nie są zwykłymi
klasami. Pilot obejmuje do 40 zdjęć na grę z co najmniej 10 rodzin, jeśli są
dostępne, i 30 pełnych siatek na kombinację gra–topologia. Czas mierzy się
na pierwszych 10 zdjęciach. Braki i rozszerzenie zakresu są jawne.

Rodziny nagrań, duplikaty i pochodne obrazu nie przeciekają między train,
validation i test. Przed pierwszym treningiem geometrii zamraża się grę
niewidzianą; symbole tej gry mają osobny podział per gra. Pomiar oszczędności
czasu używa rozłącznych, losowo przydzielonych zdjęć baseline/hybryda;
referencję ocenia się bez informacji o silniku, a przerwa ponad 30 s kończy
aktywny odcinek. Redukcja o 30% jest celem, nie gwarancją.

Jawna kohorta geometrii T03f wybiera wyłącznie źródła targetów. Nieanotowany
alias poza kohortą nie potrzebuje skopiowanej akceptacji, ale nadal uczestniczy
w pełnym grafie rodzin, duplikatów SHA i pochodnych. Cały powiązany komponent
wymaga zweryfikowanego pochodzenia i dopuszczonej roli lub własnej skutecznej
kwalifikacji D-453, z wyjątkiem jawnej polityki D-455 opisanej poniżej.
Akceptacja i pełny ręczny target są wymagane od każdego
wybranego źródła; błąd jednego wyklucza wybrane źródła całego komponentu.
Niewybrany członek nie omija granic gry niewidzianej ani niezależności pomiaru.
Wybór kohorty nie potwierdza rodzin, nie tworzy zgód i nie odblokowuje treningu
przed pozostałymi bramkami T03. Bez jawnej kohorty obowiązuje poprzedni workflow.

D-455 dodaje opcjonalną politykę `lab-geometry-cohort-777-targets-v2` dla
geometry-only z jawną niepustą kohortą. Niewybrane źródło folderowe o dokładnej
nazwie gry `777`, pierwszym segmencie ścieżki `777` i roli `comparison_only`
nie wymaga własnej kwalifikacji geometrii. Pozostaje wyłącznie kontekstem
pełnego grafu, bez zatwierdzenia, targetu ani przypisania. Każde wybrane 777
nadal wymaga własnej skutecznej D-453, zgodnego SHA i rewizji, akceptacji zdjęcia
oraz pełnej ręcznej geometrii. Wyjątek nie obejmuje DB, V2 ani innych
comparison_only. Verified całego komponentu, unseen, pomiar i pełne fingerprints
pozostają obowiązkowe. Pominięcie nowej polityki i istniejące podziały zachowują
poprzednie reguły; wdrożenie nie zatwierdza rodzin ani nie uruchamia treningu.

D-456 stanowi osobny wariant pilota `lab-geometry-whole-game-pilot-v1`.
Jawna mapa przypisuje wszystkie źródła każdej gry do jednej części;
pełny graf duplikatów, rodzin i pochodnych nie może przecinać tych części,
również poza kohortą. Pilot dopuszcza brak decyzji rodziny lub unresolved,
bez awansu do verified i bez pomiaru czasu. Wymaga targetów w każdej z czterech
części oraz aktualnych akceptacji i pełnych ręcznych geometrii wyłącznie 5 × 3.
Wybrane 777 wymagają własnej kwalifikacji D-453; kontekst zachowuje wąski
wyjątek D-455. Błąd dowolnego wybranego źródła odrzuca cały pilot.
To ograniczony test transferu między grami, bez oceny 3 × 3, symboli ani
oszczędności czasu. Dotychczasowe polityki zachowują swoje bramki.

T06a może rozpocząć pracę z pustymi słownikami i etykietami, aby umożliwić
ich jawne zatwierdzanie w laboratorium (D-458). Nie tworzy zgód za operatora
i nie utożsamia zatwierdzonej geometrii z poprawnością symboli. T06b wymaga
rzeczywistych zatwierdzeń oraz spełnienia bramek pochodzenia i podziału
symboli. Ukończenie narzędzi nie zamyka T06 ani nie odblokowuje treningu.
Unknown, unreadable i grid_issue pozostają stanami review, nie klasami.

W formularzu słownika operator wpisuje wyłącznie nazwę symbolu. Nowy wpis
otrzymuje automatycznie stabilne techniczne ID i kod, niewidoczne jako pola
edycji. Poprawka nazwy zachowuje tożsamość wpisu. Inny rodzaj symbolu należy
dodać jako nową pozycję, nie zmieniać znaczenia istniejącej. Zapis nowej wersji
i jej jawne zatwierdzenie pozostają oddzielnymi akcjami; pusta nazwa blokuje
zapis i jest zgłaszana toastem. Istniejące słowniki nie wymagają migracji.

Etykietowanie symboli pokazuje całą zapisaną planszę z jej rzeczywistą siatką
i numerami pól. Pod nią są dokładne cropy oraz kompaktowe selecty w układzie
5 × 3 (3 × 3 dla tej topologii), w kolejności od lewej do prawej, rzędami.
Operator ustala wszystkie 15 albo 9 wyborów i zapisuje komplet jednym
przyciskiem. Oprócz klas słownika może jawnie wybrać nieznany symbol,
nieczytelność albo błąd siatki; brak wyboru nie staje się żadnym z tych stanów.
Aktualne etykiety są odtwarzane, nieaktualne wymagają ponownego wyboru.
Zapis całej planszy jest atomowy i idempotentny; błąd dowolnego pola nie
publikuje części decyzji. Nie ma autosave ani automatycznego przejścia dalej.
Źródła chronione nie mogą ujawnić pikseli również w pełnym podglądzie planszy.

Poczekalnia symboli pokazuje stronicowane, dokładne cropy z zaakceptowanych
zdjęć i aktualnych pełnych geometrii danej gry, także przed utworzeniem
słownika. Brak decyzji albo jej wycofanie daje „Nieprzypisany”; aktualnie
ocenione `unknown`, nieczytelne i błąd siatki nie są nieprzypisane. Po zmianie
geometrii, renderera lub słownika stary wybór wymaga osobnej ponownej oceny.
Operator wybiera jedną lub kilka widocznych miniatur i jedną istniejącą
klasę słownika, po czym zapisuje tylko zaznaczone cropy atomowo. Brak
zatwierdzonego słownika blokuje zapis, ale nie podgląd. Poczekalnia sama
nie zapisuje etykiety, nie uruchamia treningu i nie ujawnia chronionych źródeł.
„Grupa” symboli jest zwykłym wpisem słownika, nie nowym poziomem danych.
Panel pokazuje do 2000 cropów na jednej przewijanej stronie, pobierając je
jednym ograniczonym żądaniem. To limit widoku, nie jednej transakcji: pojedyncze
przypisanie pozostaje ograniczone do 30 świadomie wybranych cropów.
Miniatury pozostają zamrożone do jawnego odświeżenia. Potwierdzony zapis
oznacza wybrane pola jako „Zapisany” i blokuje ich ponowny wybór bez
przeładowywania strony. Podczas zapisu można przygotować kolejny wybór pól
i klasy; następny zapis czeka na receipt. Brak odpowiedzi wymaga identycznego
retry albo jawnego odczytu po konflikcie. Stary token strony nie jest
odnawiany przez UI; nawigacja po zapisie pobiera aktualny token serwera.
Pod poczekalnią operator może wybrać symbol aktywnego słownika i obejrzeć
wszystkie jego aktualnie przypisane cropy z nazwą źródła, numerem planszy i
pola. Widok jest tylko do odczytu i stronicowany; decyzje nieaktualne po
zmianie siatki, źródła, renderera lub słownika pozostają w poczekalni do
ponownej oceny, nie na liście aktualnych przypisań.

## Scoped Mumie symbol qualification (D-498, TASK-0854)

An explicit operator declaration of independent recordings may qualify a fresh
per-game symbol cohort in a separate immutable manifest. Preserve the original
geometry split, label history and D-496 labels-only reference. Assign entire
transitive old/current components, including unselected aliases. Reject protected,
comparison or cross-game members, class coverage gaps and exact cross-partition
photo/crop pixel duplicates. Bind live stores and source bytes; any drift blocks
training. Small validation is preliminary and must not be called a final test.

## First scoped Mumie symbol runs (TASK-0855)

Two from-scratch RGB/gray models use only D-498 development/validation samples.
Each variant admits one train per cohort in the durable configured run root,
20epochs/1800seconds/10000steps. Retry retains budget and exact v2 epoch state.
Validation selection/calibration and agreement coverage are preliminary evidence;
flag reference conflicts without modifying human labels. No default activation.

## Independent Mumie inference (D-499, TASK-0856)

Frozen models may propose symbols on an explicitly authorized unlabelled folder.
Exclude full training/validation/protected components and exact source aliases
before pixel decoding. Preserve source/model/live-store SHA bindings and durable
per-photo evidence. Proposals and model confidence never become human approvals
or reported accuracy. Bound board candidates by filename and operator folder
end; flag disagreements, omit excess boards and never invent missing pixels or
final sequence numbers. Review shows full photos and exact cell locations.

## Bounded Mumie appearance experiment (D-500, TASK-0857)

An optional second RGB/gray generation trains from the same qualified human
labels with versioned deterministic lighting/payline augmentation. Validation
pixels remain unchanged; selection and calibration use only original validation.
Preserve v1, original stores and defaults. Each variant keeps the existing
20-epoch/1800-second/10000-step admission limit. Before exploratory inference,
require at least 83/84 validation and ONNX parity on all 84 crops per variant.
Reuse exact geometry and crop pixels for all 600 sources, with SHA checks and
fresh-process replay. Confidence and agreement are not accuracy or approvals.
An unsuccessful pair requires new human labels for difficult appearances,
not repeated random experiments or default activation. A read-only targeted
review identifies exact locations without approving or training those cases.

## Independent batch crop correction (D-501, TASK-0858)

The operator can correct the 18 diagnostic crops without changing their grid.
Click selects the crop; the approved dictionary palette and 1–9/0 shortcuts
are available immediately. An explicit save confirms only the displayed crop
and class, with unreadable/grid_issue alternatives. Retain frozen PNGs and
confirm only the receipt's exact case. Keep lost-response retry identical;
conflicts require an explicit read. Full photos open through a separate link.
Place the palette beside the gallery on desktop and above it on mobile.

These decisions have batch_crop_review provenance in a separate store. They
do not approve the photo, whole geometry or sequence and remain trainable=false
until a separate qualification task satisfies geometry/split gates. Preserve
the original lab history, training parts, models and immutable batch evidence.

## V3 source recording qualification (D-554, TASK-1002)

Geometry training uses explicitly declared whole recordings. Folder names,
sequence ranges and unmatched checksums do not establish independence. Missing
membership, declarations or ancestor mappings keep qualification unresolved.
Byte and normalized pixel aliases carry protective roles across games; the
response reveals only the selected game's groups. Historical game code `7`
and symbol classifiers retain their separate workflows.

The operator selects an import and registers its recording through one explicit
action. Registration uses bounded pages, durable receipts, cancellation between
pages and explicit resume. Reload reads state without resubmitting writes.
Draft roles can be corrected. A provisional resolution does not consume a split;
permanent protection begins with actual cohort freeze, evaluation, trusted
holdout import or inherited use. Final test, unseen game, Reels and Treasure
never qualify as TRAIN. Existing immutable reports and pins remain historical
evidence; later relevant alias changes invalidate their eligibility separately.

Laboratory descriptors require trusted deployment installation and explicit
whole-recording mapping. Photo-only protection remains effective while identity
is unresolved; a later proven mapping can resolve that state without erasing
history. The application does not infer recordings or scan images automatically.

## Descriptive production grid measurements (D-555, TASK-1009)

Production measurements are independent of training split qualification. Missing
recording identity remains unresolved for later cohort eligibility and does not
remove difficult sources from descriptive sampling. Frozen original observations
require exact source/target/producer lineage. A current human correction is not
a model prediction. Mixed producers are reported separately; missing provenance
does not become active-model accuracy. All nine positions require explicit
geometry review. Symbol information uses only existing current human decisions
from the same game, without assigning labels or sharing classifiers.

## Application geometry cohorts (D-556, TASK-0995)

One cohort belongs to one game and pins a base model, training family,
preprocessing and whole-recording TRAIN, VALIDATION and REGRESSION roles.
Unknown membership, declarations, providers or ancestor independence remain
visible and unresolved. Selecting a source subset does not narrow the recording
or global alias checks. Protected holdouts, final test, unseen game, Reels and
Treasure never qualify as TRAIN. A control recording must also be independent
of known ancestor TRAIN use.

Only current human geometry evidence qualifies a target. A guarded manual save
and a later unchanged approval preserve corrected origin; missing historical
prediction attribution does not erase a real current label. The versioned pilot
weight is four for proven manual corrections and one for checked unchanged
geometry. Each complete board preserves all 24 exact nodes. Grid-only TRAIN can
use complete boards from an incomplete photo without materialized symbol cells.
Screen targets and control photos require all nine complete annotated boards.
TRAIN requires at least 30 boards and ten photos. Each control role requires
15 boards and five full photos from a separate independent recording; with
nine boards per full photo the smallest complete cohort has 120 boards and
20 photos. Counts, weights and topology are versioned policy.

Preview retains every selected member with explicit reasons and a server-derived
used flag. Excluded members contribute no image copy, negative example, minimum
or actual recording use. After preview, drift fails explicitly and requires a
new preview rather than silently shrinking the data. Freeze commits immutable
evidence, replay receipts and permanent actual use for all three roles together.
No quality result or training permission follows from descriptive judgments,
preview counts or snapshot creation alone.

Human label withdrawal, a live source link and snapshot byte availability are
separate nullable facts. Metadata GET does not read image files and leaves byte
availability unknown. Operational source removal blocks new training and
evaluation use with `SOURCE_REMOVED_NEW_USE_BLOCKED`, while retaining history.
It does not establish human label withdrawal. Removed used sources make metadata
qualification blocked even alongside unresolved reasons; excluded sources do
not block the actually used selection. Source and layout resets retain history
with detached live links.
Whole-game deletion follows existing partition deletion and separate approved
reference-aware asset GC, without creating a permanent full image archive.
The present preview has technical identity fields; TASK-1000 must integrate
selection by understandable import, recording and family names into the final
operator workflow.

## Grid training presets and admission (D-557, TASK-1005)

### Detector correction policy (D-586, TASK-1157)

### Independent automatic qualification (D-587, TASK-1158)

The explicit `application-grid-corrections-v4` cohort preparation refines existing
VALIDATION roles with `validationAssignments` A/B/BUFFER. It uses whole imports,
copy/session/ancestry components and existing ten-photo buffers. Legacy selection
exposure belongs to A only. Fresh legacy freeze/start/resume cannot consume B.
Preview has no role writes; freeze is atomic. Historical role rows, JSON proofs,
receipts and snapshots retain their interpretation and bytes.

Screen TRAIN and checkpoint A still require full photos. B and REGRESSION assess
every qualified labelled target on partial photos; whole-photo false positives and
duplicates need full GT. Qualification needs 30 distinct deduplicated baseline-bad
sources and 30 baseline-good sources separately in B and REG. Different targets of
one mixed photo can serve both strata, within one partition; overlap is reported.
Corrected baseline errors still satisfy the bad-stratum minimum. Candidate errors
and false acceptance are judged independently against human GT. Conflicting current
GT on a known copy/slot is unresolved, never a favourable label choice.

The outcome definition is frozen before B: existing IoU matching, normalized 24-node
correctness and GT-cell coverage in actual source/crop support. Coverage epsilon
1e-6 is dimensionless floating-point tolerance, not allowed content loss. Eight
named confidence/fit/pixel/agreement/proportion signals need real references; unknown
means manual. Perspective and neighbour proportions are signals, not GT. Runtime
checks fitted cells against real pixels, and cannot guarantee every omitted row is
detected. Managed-crop padding is not original image content.

At most 256 deterministic configurations per game use two nearest-rank TRAIN/A
levels per axis (minimum axes 1%/5%, maximum axes 95%/99%). The complete menu, counts,
routing and comparison budget are sealed before B; B selects only acceptance, REG
never tunes. Recognition/rescue routing is validated on exact A with its own preset
and hash. No new neural calls occur per threshold configuration. Accepted crops or
unknown coverage block automatic qualification; correct automatic results must
increase over the T0-protected baseline. The pre-T0 comparator is also reported.

`grid-model-evaluation-read-v5` separates raw quality/publication PASS from
`automaticCalibration` per game. Missing calibration data blocks only automatic
acceptance, not otherwise admissible training, proposals or manual model application.
New operation pin v3/acceptance v4 carries the exact qualified profile; old operations
replay their original pin and policy together. No early acceptance or human stamp is
created by worker availability metadata. Strict T1 diagnostic uses must be registered
in the existing ledger, with closure, before new B/REG use; readiness-only access is
not diagnostic exposure. Operator registration/migration still needs deployment approval.

### Detector workflow compatibility

Correction preview/start accepts explicit `trainingMode=screen+grid`; the default is
still grid-only. The new `application-grid-corrections-v3` policy needs ten fully
labelled TRAIN photos and five fully labelled checkpoint VALIDATION photos. A partial
photo cannot become detector background. The original population still defines ordering,
buffers, aliases and protected roles. The new REGRESSION assessment needs five photos
and fifteen qualified targets, with no full-photo minimum; it evaluates only labelled
targets and never selects a checkpoint. Old policies retain their original requirements.
Readiness exposes full/partial counts, role deficits and reasons. Zero full photos blocks
detector training; the separate grid-only workflow remains available.

The new checkpoint rule orders original-photo metrics by photo correctness, board
correctness, lower photo-macro normalized point error, then earlier step, with equal
photo and game weights. All used VALIDATION sources are checkpoint-exposed A. Restart
preserves the exact input, optimizer exposure, best step and charged run budget.

At most one explicit scale/margin variant accompanies a run. Each permitted runtime
path (screen-only with base margin, board-only with base detector, or their combination)
needs optimizer exposure before the selected checkpoint, original-photo A evidence,
and actual exported ONNX parity. A path must worsen no required game and improve at
least one; a tie retains baseline. Current evidence supplies no measured asymmetric
jitter amplitude, so existing augmentations remain and no empirical amplitude is invented.
No qualified variant means manual correction. Runtime reserves at most one redetection
per operation/source and one crop per stable position before computation. A crash
without a result consumes the reservation; changing a variant cannot renew the budget.

An explicit `historicalCohorts` choice can replace the cohort of an already required
other game without adding/removing games or silently narrowing scope. It must satisfy
the same family, base ancestry, currentness, full TRAIN/A and frozen-input rules.
Legacy screen snapshots without the new selection reference are not bad labels; they
need a new v3 cohort. Existing prepare/capture/materialize/freeze actions can reuse
their qualified labels and protected roles independently of any shared training start.
The old snapshot and its hash are never rewritten. The advanced UI exposes this
existing preparation path in T5. No actual training or operator migration is authorized
by implementing this policy.

Grid-only and screen+grid runs use separate versioned presets with a fingerprint, a
training-time range, a step limit, early stopping on VALIDATION and a charged run limit.
A run is refused when no GPU is available, the runtime versions differ, VRAM is too
small, the application GPU lease is held or unknown, the preset is unknown or not
approved, the cohort is empty, of another mode or too costly, or the budget is spent.
Resuming a run never renews its steps or seconds. A smoke ends after 50 steps or 120
training seconds and produces no candidate. The preview reads metadata only; it starts
no job and does not claim worker-side checks.

## Durable application grid training (D-558, TASK-0996)

An operator starts a run from a frozen, eligible cohort and the approved preset of its
mode. The run is queued in its own lane and never blocks imports. It can be cancelled and
resumed; resume keeps the spent budget and continues from the last valid checkpoint with
the same data order. A damaged checkpoint, a removed source, a changed base or preset,
missing GPU or a held GPU lease stops the run without a candidate. A finished run
registers one not-evaluated candidate version, also after a crash and retry; it is never
published or activated by the run.

## Per-game candidate evaluation (D-559, TASK-0997)

An operator evaluates a trained candidate against its base on the control photos of the
training game and of every other game of its family. Both models analyse the same photos
from the original image; results are shown per game, role and recording. A regression in
any game, a missing board, a missing control photo, failed parity or a stale proof blocks
publication; the training game must improve. REGRESSION photos are used only for the
final non-regression check and never for checkpoint selection. When a control photo's
geometry changes later, the candidate is blocked until the operator checks currentness
again; a withdrawn label keeps it blocked. The evaluation never publishes or activates a
model.

## Shared candidate of several games (D-560, TASK-1006)

An operator may train one candidate from the frozen cohorts of several games of one family
and base. Every game and recording weighs the same, so a large game never dominates; a
control photo of one game never becomes training data of another. The candidate is
evaluated on every game it trained on; a regression in any game blocks publication, and the
result never switches a game automatically.

## Diagnostic production crop comparison (D-595, TASK-1171)

A bounded read-only command compares legacy margins 0.08 and 0.0 with the same
output size, preprocessing and classifier weights. It first uses approved human
geometry, then actual pinned grid-model predictions with their runtime rescue
routing. LAB RGB is a separate pinned 96-to-64 contract. Existing renderer
semantics remain unchanged: zero uses the exact cell quad; a positive margin
uses the outer-board homography, including on irregular internal nodes.

The diagnostic retains every selected instance and reports each game and role
separately. A recommendation requires fewer clipped-plus-missing graphics without any
new missing instance or new content
damage, wrong-cell assignment, ambiguity, foreign glyphs, classification errors
or false acceptance. Missing content, uncertainty, current human class approval,
model or pinned acceptance policy is explicit lack of evidence, never success.
An immutable report with `diagnosticOnly=true` and `qualificationAllowed=false`
cannot qualify, publish or activate a model or crop setting.

Current source/owner, copy and role protection is checked before pixel access.
TRAIN helpers exclude aliases of every stored blind session. Internal A scoring
requires current approved pass-2 references bound to one qualified frozen
measurement; an unrelated abandoned session does not invalidate those references.
A never exports visual hints. Fresh inference preserves witnessed neural inputs
even without content labels; visual raster export is restricted to eligible TRAIN.
Sealed internal A JSON retains geometry/classes for replay and metrics; its local
metadata exposure is an accepted diagnostic risk. It must not feed HTML or hints.
The visual consumer requires both TRAIN and visualExportAllowed=true.
The actual current diagnostic runtime policy is separately pinned, never asserted
as historical import policy. Known manual/disabled permits a diagnostic recommendation
without claiming automatic acceptance quality; a missing runtime pin is unavailable.
LAB reports absolute reference totals per game/role, not a fictitious paired improvement.

### Content measurement for the active render (D-596)

A new measurement may opt into `active-symbol-render-v2`. The server pins the
verified active symbol model and its real crop configuration before the first
blind pass. Existing photographs and independent corrections need no reimport:
their original import provenance remains separate and immutable. Omitted or null
policy retains v1, including historical command fingerprints and receipt replay.
The Admin form describes this choice as “Pomiar dla aktualnego sposobu wycinania”.

The current approved A labels must reference one ready frozen measurement. That
measurement supplies the exact evaluation contract to the cohort and every R0–R3
child. An unrelated unfinished measurement still protects TRAIN/gallery sources,
but does not invalidate a different qualified A reference. Missing or latest
pass-1 A labels block evaluation. B/REG evidence may remain unavailable without
blocking a legal A experiment; unavailable evidence cannot qualify a model.
Invalid or mixed used render pins fail before network, bank or optimizer work.

A changed crop invalidates prior admission and publication evidence. Weight-only
changes with the same crop retain existing report-v6 freshness semantics. No old
session, annotation or report is rewritten or retargeted. Cohort inventory states
its scope and reports current annotations separately from frozen pins, without
claiming global correction totals or measured model quality.

D-597 separates diagnostic repeatability from render qualification. A frozen
measurement whose valid human label pairs establish u/delta may diagnose a crop
that its actual oracle marks as clipping. The diagnostic reader reconstructs the
pair report and verifies current pass-2 revisions and witnessed render receipts;
missing, unknown or unavailable rendering cannot use this exception. The original
`render_contract_blocked` state remains visible. Only T2 comparison opts in;
training, freeze eligibility, publication and defaults retain their strict gates.
Thus human-geometry 8%-versus-0% diagnosis does not require activating 0% first.

Outside A, a v2 reference carries no blind measurement: independent labels from
older sessions remain usable, and missing import provenance stays explicitly
unavailable. Only A requires a compatible measurement and oracle on every board.
New cohort-wide render consistency checks apply only to v2; legacy v1 retains
its original per-source interpretation. Diagnostics prefer a unique qualified
measurement before considering the narrowly validated blocked-render fallback.

### Standalone crop comparison (TASK-1173)

The explicit HTML crop-report mode consumes sealed diagnostic artifacts without
running inference or changing labels. Only TRAIN with visualExportAllowed=true
may enter public JSON or image export; internal A metadata must never be rendered.
It shows the exact original, saved shared grid, approved content or its absence,
actual neural inputs and 15 production raster pairs for 8% and 0% margins.
Original-found neural input indices remain separate from usable detections.
Missing or ambiguous evidence stays unavailable; unlabelled pictures are a
visualization, not evidence of model quality. A content outline includes the
whole graphic and decorative border, excluding background and neighbouring
symbols; independent J/10 outlines need not share the grid field dimensions.
Geometry agreement is measured against the saved points, separately from content
preservation. Incorrect matched geometry and full-photo false detections must
remain visible; partial whole-photo metrics stay unavailable. File-only visual
protection reflects capture time, not later blind sessions. Make a fresh capture
before exporting another gallery; the HTML renderer performs no current DB lookup.
