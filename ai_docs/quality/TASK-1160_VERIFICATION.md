---
title: Odbiór pełnego przepływu wykrywania plansz
status: accepted
last_updated: 2026-11-04
---

# TASK-1160 — Odbiór T0–T6 i przygotowanie wdrożenia

Baza T6: `bc00e2a736a6f5a51a9d2bd590d96d280a95d23a`, v1.7.564.
Wykonawca: gpt-6.1-sol/high. T0–T5 mają wcześniejsze niezależne Opus PASS.
T6 uzupełnia brakujące testy i instrukcję operatora; nie zmienia kodu produkcyjnego,
API, schematu, ról lub modelu. Rzeczywisty root-run Opus5.5/high R1 zakończył się
PASS bez P0/P1, z5 uwagami P2 do testów. Jedną rundę ich uzupełnień wykonawcy
opisano osobno poniżej; nie przypisujemy jej zaliczenia niezależnemu audytorowi.

## Co faktycznie potwierdzono

### Częściowe A w rzeczywistym handlerze grid-only

`test_grid_only_v4_real_handler_keeps_every_partial_a_target_and_raw_quality`
wykonuje GridModelEvaluationJobHandler dla dwóch gier. Każda ma5 częściowych A,
5 częściowych REG oraz1 częściowe B; każde zdjęcie zawiera3 opisane cele w fizycznych
slotach0/4/8. Oryginały i snapshoty są plikami JPEG/JSON; GridBoardDataset,
GridAssessmentDataset, CalibrationObserver, FullBoardCalibrationRun, phase sealing,
frozen target reader i końcowy strict report/evidence reader są rzeczywiste.
Źródła i ludzkie etykiety są kontrolowanymi fixtures, bez danych operatora.
Istniejący Store scenariusza zastępuje tylko katalog/DB metadata; engine zastępuje NN.
Nie zastępujemy `_photos`, pomiaru, obserwatora lub kwalifikacji wyniku.

Produkcja zapisuje po15 A targets każdej gry w VALIDATION detail. Dokładny zbiór
source/pixelSHA/slot/GT_SHA przechodzi `FrozenAssessmentReferences.require_targets(A)`
przed deduplikacją; usunięcie jednego celu jest odrzucane. B nie trafia do A.
Raw-quality report-v3 zachowuje PASS w read-v5, a automaticCalibration jest jawnie
unqualified z niedoborem niezależnego B. Partial dane nie dostają full-photo/FP claims.
Nowy handler z utrwalonego checkpointu nie wywołuje engine ponownie i zachowuje
report SHA. Osobny proces odczytuje te same snapshoty, cele i calibration seals;
asercja ścieżki modułu wymusza kod tego worktree, zamiast editable importów z main.

### Rzeczywisty observation_sink ratunku

`test_actual_rescue_observation_sink_matches_a_routing_and_runtime_evidence`
wykorzystuje istniejący A evaluator i real TRAIN/A source/snapshot readers.
Kontrolowane detections wybierają A-admitted board_only. Real TrainingExposure,
selection/recipe, `require_rescue_evidence`, `require_rescue_pin`, execute_path,
RescueAttemptStore i `run_with_rescue` pozostają aktywne.

Metadane parity i qualified operation pin są jawnymi syntetycznymi świadkami
kontraktu. Test nie eksportuje ONNX, nie mierzy nowej parity ani kwalifikacji B/REG;
rzeczywista tiny-ONNX parity T3 jest użyta przez odwołanie do jej wcześniejszego PASS.
Nie powstaje rzeczywisty model ani raport jakości operatora.

Rzeczywisty sink z wywołania runtime, bez ręcznego składania z assessment attrs,
trafia do runtime_evidence i przechodzi calibrated_result_blockers dla poprawionego
celu. Wynik/preset/routing są zgodne z A i assessment. Zmieniony selectedPath,
routing lub archived board preset nie daje dowodu. Powtórzenie korzysta z receiptów
bez nowych wywołań; alias innych slotów pozostawia sink pusty i nie przejmuje ratunku.
Użyto rzeczywistych no-replace hard links NTFS; nie mockowano store lub os.link.

### Downgrade0181

Istniejący disposable test migracji został rozszerzony o pusty downgrade0181→0180,
reupgrade oraz odmowę po historii v4 i po użyciu z validation_purpose. Nadal sprawdza
stare proof JSON bytes, capability permissions, purpose conflict, legacy B fence
i diagnostic registration/closure. Wynik nowego wykonania jest podany niżej;
wcześniejszy T4 PASS sam nie był dowodem nowego guardu. Nie zmieniono migracji.

## Wyniki wykonanych kontroli T6

Logi znajdują się w ignorowanym `artifacts/task1160/`. Liczby są wynikami osobnych
wywołań i mogą się nakładać; nie sumujemy ich jako unikalnych testów. Każdy child
command miał timeout120s; cold reader w teście miał dodatkowo timeout30s.

| Kontrola | Wynik | Dowód |
|---|---|---|
| Dwa composed testy po pierwszym formatowaniu |2 PASS,13.93s|`composed-final.txt`|
| Sam actual sink z rzeczywistymi dowiązaniami |1 PASS,6.68s|`sink-second.txt`|
| Przed R1: composed zestaw z dodatkowym preset drift |2 PASS,14.43s; wrapper20.12s|`composed-complete.txt`|
| Przed R1: disposable0181 downgrade/reupgrade/guard i dotychczasowe fences |1 PASS,21.01s; wrapper25.77s|`pg-downgrade-final.txt`|
| Read-only kontrola cleanup3 własnych baz/ról/sesji |0/0/0 pozostających|`pg-cleanup.json`, `pg-cleanup.txt`|
| Ruff lint/format dwóch zmienionych plików testów |PASS|`ruff-final.txt`, `ruff-format-final.txt`|
| Regeneracja mapy i code-map:check |PASS|`map-generate.txt`, `map-check.txt`|
| docs:check i whitespace |PASS; startup44553/45000B,11/11 budżetów|`docs-check.txt`, `diff-check.txt`|
| Po R1: composed, przerwanie po VALIDATION/REG i actual sink |3 PASS,31.77s; wrapper39.03s|`post-audit-composed.txt`|
| Po R1: diagnostic-only i pozostałe guardy0181 |1 PASS,25.57s; wrapper32.88s|`post-audit-pg.txt`|
| Po R1: READ ONLY cleanup4 własnych baz/ról/sesji |0/0/0 pozostających|`post-audit-pg-cleanup.json`|
| Po R1: Ruff/format, docs/map/whitespace |PASS; startup44553B,11/11 budżetów|`post-audit-ruff-final.txt`, `post-audit-format-check.txt`, `post-audit-docs.txt`, `post-audit-map.txt`, `post-audit-diff.txt`|

Pierwsze uruchomienie pytest nie utworzyło katalogu w domyślnym chronionym temp.
Użyto nowych, własnych --basetemp w artifacts. Pierwszy cold reader odziedziczył
root-main editable imports; test otrzymał jawny worktree PYTHONPATH i asercję
`module.__file__`. Pierwszy sink zatrzymało WinError5 dla os.link w ograniczonym
środowisku; pojedynczy test przeszedł po dopuszczeniu lokalnego zapisu testowego,
bez zmian ACL, globalnego config lub mechanizmu zapisu.

Pierwsze PG setup ujawniło losowy kod starej rodziny rozpoczynający się cyfrą.
Pierwsza poprawka prefiksem z myślnikiem również nie spełniała istniejącego CHECK;
po odczycie właścicielskiej migracji0156 fixture otrzymał `purpose_`+hex, zgodnie
z `^[a-z][a-z0-9_]{0,63}$`. To korekta danych fixture, nie osłabienie constraintu.
Nieudane setupy nie potwierdzają nowego downgrade guardu ani nie są liczone jako PASS.
Wszystkie3 utworzone disposable journals zakończyły się `cleaned`. Osobna READ ONLY
kontrola pg_database/pg_roles/pg_stat_activity po nazwie i OID potwierdziła brak
pozostawionych baz, obu ról capability/runtime oraz sesji. Nie wykonano dodatkowego
cleanup lub żadnej operacji na bazie operatora.

T6 nie zmienia produkcyjnego Python/TypeScript. Brak nowego global mypy lub standard
workspace tsc PASS. Reuse scoped types i końcowych buildów T5 jest właściwy, ponieważ
ich app/shared-UI/SDK źródła pozostają niezmienione; testy i instrukcja nie zmieniają API.

Dokładne dwa polecenia pytest wykonano z katalogu worktree przez ograniczony
`artifacts/task1160/run_check.py` (timeout120s, UTF-8 log). Odpowiednik PowerShell
poniżej używa nowego katalogu na każde uruchomienie; flagę PG przywraca po kontroli:

```powershell
$t6Python = (Resolve-Path .venv/Scripts/python.exe).Path
$t6Temp = Join-Path (Get-Location) ('artifacts/t1160-' + [Guid]::NewGuid().ToString('N'))
& $t6Python -c 'import subprocess,sys; subprocess.run(sys.argv[1:],timeout=120,check=True)' `
    $t6Python -m pytest -q services/worker/tests/test_full_board_acceptance.py "--basetemp=$t6Temp"
$t6PriorPostgres = $env:GAME_PREDICTOR_RUN_POSTGRES_TESTS
try {
    $env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
    $t6PgTemp = Join-Path (Get-Location) ('artifacts/t1160-pg-' + [Guid]::NewGuid().ToString('N'))
    & $t6Python -c 'import subprocess,sys; subprocess.run(sys.argv[1:],timeout=120,check=True)' `
        $t6Python -m pytest -q services/api/tests/integration/test_validation_purpose_migration_postgres.py "--basetemp=$t6PgTemp"
} finally { $env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = $t6PriorPostgres }
```

To odtworzenie testów w kontrolowanym środowisku ze zgodą na disposable PG i NTFS
hard links, nie instrukcja ponownego wykonywania zaliczonych kontroli w tym tasku.
PG fixture tworzy wyłącznie własne bazy z bezpiecznym nonce i sprząta je w finally.

## Ponownie użyte dowody T0–T5

| Obszar | Commit i właścicielski dowód | Zakres potwierdzenia |
|---|---|---|
| T0 bezpieczna akceptacja |`0a7ef2d3`, root acceptance notes|Wspólne FIT_FAILED/OUTLIERS, source/slot guards, API/worker i stare polityki; zapisany462205 nie przechodzi automatu|
| T1 rzeczywiste wejście i readiness |`887d8a3b`, root acceptance notes|Strict v1 RGB/tensor replay;197GT/134foto/full0 to dawny pomiar, bez nowego skanu|
| T2 model/nowa gra |`337affe8`, hash-record `6325a057`, root acceptance notes|Exact per-game qualification, capabilities i pin+policy retry, bez dziedziczenia jakości innej gry|
| T3 detector/rescue |`f78c5b5a`, [TASK-1157](TASK-1157_VERIFICATION.md)|Real tiny CPU optimizer/ONNX/parity, full TRAIN/A i partial REG, crash/lost-response1+1, stare SQL/guard0180|
| T4 niezależna kalibracja |`c7ed8afe`, [TASK-1158](TASK-1158_VERIFICATION.md)|Exact frozen targets, raw/auto oddzielnie, B sealing/REG currentness, actual PG prewrite i cold IMPORT/VALIDATE pin+policy, diagnostic staging|
| T5 pełne wpięcie i human consumer |`bc00e2a7`, [TASK-1159](TASK-1159_VERIFICATION.md)|Typed current/frozen/null status, v4 parent/freeze/training/eval/cold reader PG, guarded geometry0→9/full9/9, legacy retry, UI/SDK i strict diagnostics|

T5 końcowe pełne isolated builds po poprawkach R1 zastąpiły wcześniejsze receipts:
Admin51.22s, boundSourceSHA256
`05828ae635086f8b08bc971c8a3d4521e46906f22d9043934e2211d772e14917`;
Reviewer32.39s, boundSourceSHA256
`b4bcd84b2ff5dfff9f06b32cfe965383a42b4cc7d672b0c7ae4fabaca704ed0b`.
Oba zachowują pełny strict config/CSP i lokalny SDK worktree, z opisaną w T5 zmianą
lokalizacji wyjścia i aliasów. To dwa pełne finalne isolated PASS; nie są standard
workspace Admin/Reviewer PASS. T6 nie powtarza tych buildów.
T5 root-run focused Opus R2 jest PASS bez otwartych P0/P1; literalne audyty nie są zmieniane.

## Rzeczywisty artefakt porównania i ograniczenia danych

`D:/game_predicotr/artifacts/full-board-detection/task1159-historical-20261104/comparison.html`
porównuje zapisane historyczne base158a740f i candidate3ed60010 na tych samych
150 planszach/101 źródłach. To prezentacja wcześniejszych predykcji, nie model
wytrenowany lub oceniony w T3–T6. Brak current human GT; prawdziwe input records są
tylko dwa, dla462205. Pozostałe diagnostyki pozostają unavailable, bez zgadywania.

HTML573046B ma SHA256
`200830420af36e95e7a40e374516088b0262d5b9634ecc72a8997577d117b801`.
Manifest60776B ma SHA256
`6cce1d49376c9d352b7fdc1fd439048cb227445edfd37a2d8419ff94bf3e6eb6`.
Root wcześniej potwierdził containment/size/SHA wszystkich319 zadeklarowanych plików.
T6 potwierdził niezmieniony manifest SHA i używa tego receipt, bez ponownego
skanowania zdjęć lub generowania HTML. Te prywatne artefakty nie wchodzą do audytu.

Nie wykonano browser visual review ani fizycznego Android review. IAB zablokował
local-file URL; nie użyto serwera, innej przeglądarki, CDP lub screenshot harness,
aby ominąć zakaz. Dotychczasowe static/DOM/interactions i isolated builds pozostają
dowodami w swoim ograniczonym zakresie.

## Standard liczników i oceny

Każdy wynik ma game/model/policy/snapshot/role/provenance i mianownik. Brak aktualnego
GT lub pomiaru to n/a z powodem, nigdy zero lub PASS.

| Miara | Odczyt |
|---|---|
| Wszystkie opisane propozycje |targets, candidateBad i raw board/error metrics; zatrzymane wyniki pozostają w populacji|
| Automat |candidateCorrectAutomatic, candidateIncorrectAutomatic, acceptedCropped, acceptedUnknownCoverage|
| Baza |baselinePreT0CorrectAutomatic oraz oddzielnie baselineT0CorrectAutomatic dla tych samych predykcji; to porównanie polityk, nie rerun starego programu|
| Udział zatrzymania |(targets−candidateCorrectAutomatic−candidateIncorrectAutomatic)/targets; przy targets0 n/a; nie jest liczbą rzeczywistych decyzji człowieka|
| Populacja |exact frozen membership przed dedup; potem sources, targets, baselineBad/GoodSources, overlap/union i syntheticTargets|
| Całe zdjęcia/FP/duplicates |Tylko przy kompletnym human GT; partial scope pozostaje labelled_targets bez wholePhotoClaims|
| Czas/koszt |Czas faktycznych testów i liczba calls/charged receipts, bez nowej miary kosztu NN lub benchmarku|

B i REG osobno wymagają po30 dedup dobrych i30 złych źródeł bazy per gra, bez
synthetic controls. Stratyfikacja bazy jest zamrożona przed progami; naprawa błędu
nie usuwa bad stratum. Mixed overlap i zależności są jawne; to nie60 niezależnych
sesji ani gwarancja statystyczna. W obu rolach acceptedCropped=0,
acceptedUnknownCoverage=0 i wzrost poprawnego automatu względem bazy z polityką T0
są wymagane. Odrzucenie wszystkiego nie spełnia wzrostu. candidateIncorrectAutomatic
pozostaje osobną miarą, bez dodanego nieuzgodnionego progu. Istniejące raw-quality
no-regression/gain bramki całego wymaganego zakresu gier pozostają bez zmian.

## Wymaganie planu i Definition of Done

| Wymaganie | Dowód i ograniczenie |
|---|---|
| FIT_FAILED/OUTLIERS i pominięty rząd |T0/T4 guards + T6 actual sink; sygnały nie gwarantują wykrycia każdego pominięcia, brak dowodu oznacza korektę|
| Rzeczywiste wejście, sąsiad/niejednoznaczny slot |T1/T5 strict diagnostic i renderer; T3 routing/slot proof oraz nowy actual sink/alias test|
| Detektor z korekt, partial dane zachowane |T3 optimizer/reader/PG i T5 shared-v4 PG; T6 partial-A handler i cold strict readers|
| Nowa gra i brak przecieku B/REG |T2 capability/game pin, T4 purpose/closure/frozen target PG; registration nadal staged|
| Ręczna korekta i historia |T5 actual guarded command→reader/full9/9 oraz CAS/retry; T4 cold IMPORT/VALIDATE, T6 replay bez nowych calls|
| Porównanie wszystkich propozycji i autogate |T4 raw/automatic osobno, T6 exact handler + standard liczników; rzeczywista poprawa NN niewykonana|
| Wdrożenie i rollback |[Instrukcja operatora](../guides/V3_GRID_FINE_TUNING_OPERATOR.md#6-pełne-plansze-przygotowanie-wdrożenia-t0t6):0180→0181, capabilities/skew, staged registration przed B/REG, NTFS i history guards|
| DoD kod/kontrakt/dane |Wyłącznie testy/dokumentacja, bez nowego API/schema/produkcji; format/lint/map/docs; brak ukrytej decyzji domenowej|
| DoD trwałość |T3 crash i T4/T5 cold PG reuse; T6 cold file-backed reader i actual rescue cache/replay, bez power-loss/GC obietnicy|
| DoD UX |T5 interactions/strict types/build reuse; Android i browser visual niewykonane z przyczyn powyżej|
| DoD audyt/Outcome/commit |Actual Opus R1 PASS; root zaakceptował post-R1 test/doc strengthening. task-close i oddzielny record-hash prowadzą końcowy zapis wersji|

## Pozostałe ryzyka i niewykonane operacje

Nie było rzeczywistego treningu, inferencji, skanu operatora, niezależnego B/REG,
operator DB/role writes, registration, migracji usług, publikacji/aktywacji/default,
merge/push. Ostatnie T1 liczby197GT/134foto/full0 pozostają historyczne.
T2/T3/T4 zaakceptowane P2 pozostają: synchronous inspection/sidecar, niearchiwowany
powód, alias scope i NTFS/power-loss/GC oraz brak dowodu niezależności sesji.
Nie wprowadzamy cache lub kolejnej audit/fix pętli. Wymagane osobne zgody i kolejność
0181/diagnostic registration/model rollback znajdują się w istniejącym guide.

## Audyt R1 i jedna runda uzupełnienia testów

Literalny [Opus R1](TASK-1160_AUDIT_claude-opus-5-5.md) jest **PASS** bez P0/P1,
z5 uwagami P2. Oryginalny raport i snapshot pozostają niezmienione. Poniższe
uzupełnienia to praca wykonawcy po audycie, a nie dodatkowy werdykt Opus:

1. P2-1: parametr VALIDATION/REGRESSION powoduje rzeczywiste przerwanie po zapisie
   checkpointu danej jednostki, przed automaticCalibration/final. Resume przechodzi
   przez real prepare_b/finish/readers. Zapisane wcześniej detail/plan/B bytes są
   niezmienione, ukończone źródła nie dostają kolejnych wywołań, a końcowe final bytes
   i report SHA są identyczne z nieprzerwanym przebiegiem tego samego jobu na kopii
   tych samych źródeł. Potem exact lost-response replay dodaje zero wywołań.
2. P2-2: osobny savepoint zapisuje zgodny z ledgerem diagnostic_comparison use
   bez v4 history lub niepustego validation_purpose; asercja wyklucza oba maskujące
   warunki. Real downgrade0181 odmawia, potem savepoint jest wycofany. Nie zmieniono
   migracji, triggerów ani SQL fences. Pozostałe dwa warunki również przechodzą test.
3. P2-3: cold reader sprawdza __file__ zarówno modułu API, jak i worker dataset,
   wymuszając worktree. Nie zmienia globalnego środowiska lub editable instalacji.
4. P2-4: partial raw metrics sprawdzają duplicate_predictions=null dla bazy/kandydata;
   publiczne counts B/REG mają scope=labelled_targets, a istniejący final sidecar
   result ma assessmentScope=labelled_targets i wholePhotoClaims=false. Nie dodano
   nowych pól do raportu tylko po to, aby dopasować test.
5. P2-5: spy przekazuje argumenty do prawdziwego input_support i dowodzi geometry=None
   dla slotu0 bez ratunku; rescueDisagreement jest notApplicable i nie ma pozornej
   blokady brakującego ratunku. Replay daje identyczne evidence tego slotu. Obliczenia,
   proof validators i store nadal działają naprawdę.

Końcowe wyniki3 PASS oraz1 PG PASS podano powyżej. Nowa własna baza i trzy wcześniejsze
journals mają cleanup0/0/0 potwierdzone odrębnym READ ONLY odczytem. Po zaliczeniu
poprawiono tylko kolejność importu Ruff; nie zmieniono zachowania testów lub produktu.
Zgodnie z procesem P2-only test strengthening bez zmiany produktu nie uruchamia
kolejnej pętli Opus. Root przeczytał całą deltę18236B w częściach, sprawdził SHA
patcha/manifestu,4 current SHA i niezmieniony literalny audyt, po czym zaakceptował
uzupełnienia. Nie jest to drugi werdykt Opus.

Zamknięcie prowadzi task-close z osobnym wersjonowanym commitem i kolejnym metadata
record-hash. Źródłem końcowej wersji i pełnego hasha jest Outcome
[ukończonego taska](../tasks/completed/1160-full-board-acceptance.md).
