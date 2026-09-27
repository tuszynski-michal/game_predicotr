---
title: TASK-0670 — T05 — hybryda
status: done
last_updated: 2026-09-27
---

# TASK-0670 — T05 — hybryda

## Status

`done`

## Goal

Wytrenować pierwszą hybrydę i pokazać jej checkpoint w galerii.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

T04 done, zamrożone podziały i zatwierdzony budżet eksperymentu. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

D-456 ogranicza pierwszy rzeczywisty trening do 5 × 3: development 90 siatek,
validation 30. Final_test Reels i unseen Treasure są zamrożone i nie służą
strojeniu ani wyborowi checkpointu. Wynik pilota nie ocenia 3 × 3 ani czasu
pracy. Testy kontraktu 3 × 3 pozostają, bez deklaracji wyuczonej jakości.

## Recommended execution

`gpt-6-sol`, reasoning `high`; osobny audyt `gpt-6-astra`, reasoning `medium`. Model geometrii i bramki pewności wymagają oceny błędów na obrazach. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T05 — hybryda)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447)

## Scope

MobileNetV3-Small, lokalizacja narożników, perspektywa, opcjonalne dopasowanie, wspólne bramki, ONNX; do 50 kroków próbnych i jeden trening max 20 epok/30 min.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [x] Porównanie na development, pierwszy poprawny checkpoint w galerii, zgodność ONNX, błędne węzły wymagają korekty.
- [x] Audyt przypisanym modelem nie pozostawia P0–P2; Outcome i CURRENT_STATE, osobny commit v1.7.30 zapisane poniżej.

## Technical notes

### Kontrakt pilota przed implementacją (D-457)

1. `hybrid-mobilenet-v1` poprawia propozycje istniejącego obrazowego
   BaselineEngine, zamiast uczyć pełnoobrazowy regresor dziewięciu plansz
   z zaledwie 32 zdjęć. Preprocessing `baseline-crop-rgb224-v1`: EXIF-RGB,
   quad propozycji, bbox z marginesem 20% szerokości/wysokości z każdej strony,
   clipped do źródła, letterbox224 i ImageNet mean/std. Affine jest jawne.
   Ręczne węzły nigdy nie wyznaczają wejściowego cropu. Zachować position_index
   propozycji; zero dopełniania do9. Baseline9 jest wyłącznie generatorem
   kandydatów, nie dowodem obecności. Brak propozycji daje NO_PROPOSAL/review,
   nigdy automatyczne absent. Model nie odzyska niezgłoszonej planszy;
   raport musi policzyć także te braki.
2. MobileNetV3-Small IMAGENET1K_V1 z torchvision0.27.1, wagi
   mobilenet_v3_small-047dcff4.pth (~9,8 MiB), jednorazowe ograniczone pobranie
   z oficjalnego źródła torchvision do cache LAB. Zapis pełnego SHA przed
   runem, bez cichego losowego fallbacku. Backbone i BatchNorm zamrożone;
   uczony head Linear576→128, Hardswish, Linear128→8. Ostatnia warstwa zerowa:
   początkowy delta=0. Wyjście to osiem przesunięć TL/TR/BR/BL względem
   propozycji, w znormalizowanych współrzędnych cropu.
3. Homografia z czterech narożników daje24 węzły5×3. Gate sprawdza skończoność,
   orientację/convex, pola, bounds, przecięcia i kolejność komórek. Błędnej
   geometrii nie przekazywać do croppera. Pilot3×3 zwraca unsupported,
   zachowując test wspólnego kontraktu16węzłów poza nauczoną jakością.
   Nieprojektowe ręczne siatki mogą dawać residual, który trzeba ujawnić.
4. Matching treningowy/walidacyjny: ten sam board_index i IoU quadów>=0,25.
   Stała ustalona przed wynikami. Tylko jawne zatwierdzone targety w loss;
   pozostałe kandydaty unknown, nie negative. Brak zatwierdzonych negatives
   oznacza brak presence-head/BCE i brak kalibrowanej pewności. Raport zawsze
   podaje used/missed względem pełnych90/30, bez cichego usunięcia trudnych.
5. SmoothL1 beta0,02 na8 normalizowanych cornercoords, średnia matched.
   Batch8, AdamW lr0,001, weight_decay0,0001, bez schedulera/tuningu.
   Seed20260927, generator/RNG checkpointowane przez T04. Deterministyczny
   tryb CUDA, cuDNN bez benchmark i CUBLAS_WORKSPACE_CONFIG=:4096:8 przed
   inicjalizacją CUDA; ustawienia należą do protokołu. Exact resume dotyczy
   zgodnego runtime/sprzętu, nie różnych GPU lub wersji bibliotek. Development:
   seeded brightness/contrast±10% i scale±5% z identyczną transformacją
   wejścia/propozycji/targetu; bez flip/rotacji zmieniającej pozycję planszy.
   Validation bez augmentacji. Cały rozstrzygnięty protokół, SHA wag,
   wersja generatora i preprocessingu należą do checkpointu oraz raportu;
   zmiana protokołu wymaga nowej wersji, nie nadpisania model_version.
6. Wybór best tylko na validation: dla każdej z30 zatwierdzonych siatek
   średni błąd24węzłów podzielony przez przekątną GTquad, capped1; brak
   propozycji/matcha lub nieważna predykcja ma koszt1. Średnia po siatkach
   zdjęcia, potem po11zdjęciach (image-macro). Najmniejszy wynik, remis daje
   wcześniejszą epokę. Epoch0 jest referencją, besttrained wybiera się tylko
   z ukończonych epok>=1. Raport także rawNME median/p95 dla validmatches,
   coverage, invalid/missed i porównanie development z rzeczywistymi24węzłami
   baseline. Zero-delta homografia jest osobną referencją init/epoch0,
   nie zastępuje metryki nieprojektowych wewnętrznych węzłów baseline. Brak
   poprawy jawny. Nie raportować precision/FPR przy niepełnych anotacjach.
7. Dwa runy RunManager: smoke jedna epoka, max50kroków; train max20epok/1800s.
   Retry nie zwraca budżetu. Bez dodatkowych prób/tuningu. Preflight tylko
   development/validation: propozycje i matching. Brak użytecznych par
   zatrzymuje trening z dowodem; bez zmiany architektury w ciemno.
   Smoke i train startują niezależnie: te same pretrainedSHA i seed20260927,
   świeży head z zerową ostatnią warstwą, nowy optimizer/RNG/best_state.
   Train nie dziedziczy żadnych uczonych wag ani stanu smoke. Wynik smoke
   służy wyłącznie kontroli technicznej, nie do strojenia protokołu.
   Limit1800s obejmuje także walidację, eksport, parity i publikację.
   Brak czasu zachowuje ostatni checkpoint i oznacza STOP z raportem;
   bez drugiego runu, zwrotu budżetu ani uznania failed/cancelled za succeeded.
8. Gate pozostaje uncalibrated: każdy poprawny geometrycznie kandydat ma
   needs_review i HYBRID_GATE_UNCALIBRATED. Confidence null/nieobecne,
   żadnego autoapprove. Geometryczne stałe i NME nie udają kalibracji.
9. Resume-checkpoint to ostatnia ukończona epoka; best_state oddzielnie
   przechowuje bestmodel/epoch/score. ONNX eksportuje best_state, input
   [B,3,224,224]→delta[B,8], opset18 i dynamicbatch. Inferencja ONNX nie
   importuje PyTorch. Parity dev/val: maxabs delta<=1e-4 i sourcecorners<=0,1px;
   niespełnienie blokuje publikację. ONNX/bestweights są immutable artefaktami
   próby publikowanymi przez małe rozszerzenie RunManager z freshvalidation,
   SHA i fencing. Sukces oraz odczyt weryfikują wszystkie wskaźniki.
   Checksummed raport wiąże manifest/split/config/model/preprocess/proposals/
   pretrainedSHA/ONNX/bestepoch/parity, nie tylko dowolne ścieżki w metrics.
10. Rozszerzyć istniejące POST /geometry o opcjonalny run_id. Brak pola
    zachowuje baseline. run_id+preview_board jest błędem. Dopuszczać tylko
    ukończony checksummed run hybrydy i aktualny zgodny manifest. Holdout
    final/unseen daje HOLDOUT_NOT_RELEASED przed Catalog.image; inne źródło
    spoza development/validation daje SOURCE_NOT_IN_TRAINING_PARTITIONS.
    Galeria: selector baseline/ukończony model z bestepoch i informacją
    uncalibrated; baseline domyślny, dotychczasowe manual preview bez zmian.
    Komunikaty w istniejących toastach. Cały pion backend/OpenAPI/generated/
    wrapper/proxy/request tests, bez równoległego modelu odpowiedzi.
11. Kanoniczny preset protokołu ma protocol_digest=SHA256(canonicalJSON),
    obejmujący architekturę, pełny SHA pretrained, wersję generatora,
    preprocessing, stałe hiperparametry, loss, augmentacje, matching,
    scoring/tie-break, gate i ONNX. Reszta konfiguracji runu (epochs/batch/lr/
    budżet/purpose/seed) pozostaje osobno w istniejącym fingerprintcie.
    StartRunRequest dostaje opcjonalny protocol_digest; model hybrydy wymaga
    zgodnego digestu zamkniętego lokalnego presetu i rzeczywistego SHA wag.
    None jest jawnie pomijane w kanonicznym payloadzie, aby stare receipts
    i binding checkpointów T04 pozostały identyczne. Ten sam canonicalrequest
    służy start/replay/runfingerprint/checkpoint_binding. Zgodność protocolu
    i lokalnych wag jest sprawdzana przed create/claim/retry, zapisem
    checkpointu/artefaktów/raportu oraz przy inferencji. Niezgodność daje
    RUN_PROTOCOL_MISMATCH przed uczeniem, bez cichego zamiennika. Pełny preset
    i digest są również zapisane w checkpointach oraz checksummed raporcie.

Kontrakt ma końcowy PASS audytu pre-code Astra medium po trzech
doprecyzowaniach P2 (protocol binding, niezależność smoke/train, budżet).
Rozszerzenie API
zostało jawnie zapowiedziane operatorowi. Nie wymaga zmiany DB ani aktywacji
modelu produkcyjnego. Nieznane wyniki pokrycia/jakości ustalimy na istniejących
dev/val; nie są to powody do dodatkowego treningu poza budżetem.

Pilot D-456 ma niepełne anotacje zdjęć: 90 zatwierdzonych plansz na 32
zdjęciach development. Brak zatwierdzenia pozycji NIE oznacza nieobecności
planszy. Nie wolno używać nieoznaczonych pozycji jako negatywnych targetów
presence ani karać za wykrycie nieoznaczonej prawdziwej planszy. Jeżeli model
ma head presence, loss maskuje nieznane pozycje; negatywna etykieta wymaga
jawnego zatwierdzenia absent. Metryki jawnie podają, że dotyczą zatwierdzonych
geometrii, nie kompletnej detekcji wszystkich plansz. Model nie może pobierać
ręcznych węzłów jako wejścia podczas inferencji — służą wyłącznie do targetu
i oceny. Przed implementacją skonkretyzować inferencję/format wyjścia modelu,
preprocessing, maski i wybór checkpointu na validation w tym tasku, z audytem.

Zachowaj kontrakty z planu i właścicieli istniejących decyzji. Błędy wejścia oznaczaj per źródło lub próbka, a błąd integralności i infrastruktury zatrzymuje zależny run. Nie promuj predykcji do ręcznego zatwierdzenia. Istotne odstępstwo wymaga aktualizacji planu przed implementacją.

## Expected files

- Istniejące: vision_lab/geometry.py::BaselineEngine,
  contracts.py::DetectRequest, api.py, catalog.py,
  runs.py::RunManager, run_contracts.py, training_adapter.py::TRAINERS,
  training_core/checkpoint.py, apps/vision-lab/src/app/page.tsx oraz
  packages/vision-lab-api-client (OpenAPI/generated/wrapper/test).
- Proponowane: vision_lab/hybrid_model.py, hybrid_training.py,
  hybrid_inference.py, hybrid_onnx.py, geometry_gate.py, test_vision_lab_hybrid.py.
- Istniejące `services/worker/src/game_predictor_worker/images/keypoint_geometry/onnx_adapter.py` (wzorzec). Nowe (proponowane) `services/worker/src/game_predictor_worker/vision_lab/hybrid.py::HybridGeometryEngine`, `.../geometry_gate.py::validate_grid`, `services/worker/tests/test_vision_lab_hybrid.py`.

## Test cases

- Zmiana ręcznych etykiet nie zmienia wejściowego cropu; inferencja nie
  otrzymuje targetów. Unknown nie tworzy negative-loss;0/1/3kandydatów bez9padding.
- Maski i holdoutguard, również HTTP, przed dekodowaniem. Degeneracja,
  bounds i24węzły; checkpointbeststate i deterministyczne wznowienie.
- Parity ONNX, fenced publikacja, naruszone SHA, odczyt po restarcie,
  selector modelu i niezmienione baseline/manual preview; UI w przeglądarce.
- Protocol mismatch i zmiana pretrainedSHA blokują przed uczeniem/publikacją;
  pominięty protocol_digest zachowuje stare receipt/binding identycznie.
  Train nie dziedziczy smoke; deadline podczas eksportu nie daje sukcesu.
- Zamrożone wagi i bufory BatchNorm po model.train/krokach; CUDA resume w
  zgodnym runtime. Oryginalne wewnętrzne węzły baseline oceniane niezależnie
  od interpolacji tych samych czterech narożników.
- Perspektywa/zasłonięcie/niekompletna plansza; 5 × 3 i 3 × 3; PyTorch–ONNX na tej samej próbce; niepewna siatka nie przechodzi gate.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_hybrid.py') -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'pytest timeout 120s' }
if ($p.ExitCode -ne 0) { throw "pytest exit $($p.ExitCode)" }
```

Po teście wykonaj lint/typecheck zmienionych modułów i wymagane kontrole kontraktu, każdą jako skończony proces z limitem maksymalnie 120 s. Testy tu są planowane, niezaliczone; zaliczenie wymaga kryteriów powyżej i braku regresji.

## Risks / open questions

- Zmiana schematu danych, zakresu zdjęć lub kosztu poza planem wymaga jawnej aktualizacji przed zależnym działaniem.

## Outcome

T05 odebrany technicznie; STOP B. Wykonawca Sol high, osobny audyt Astra
medium pre-code/code/request/artefakty PASS bezP0–P2. Dokładnie dwa realne
runy: smoke8b883801a9164eeb9d72474943adf3c1 (1ep/10steps/434,93s) oraz
train34adda69c29847f389cb92e487d75ca8 (20ep/200steps/568,53s).
Checkpoint20/best1, freshprocess SHA i ONNXparity PASS. RootUI: model
widoczny i zwraca needs_review na DEV777, bez zapisów anotacji. StateSHA
084bc39…/rev268 pozostały identyczne także poUI.

DEVscore0,153640529 vsbaseline0,156461470; VAL0,046985619 vs0,046131665.
Walidacja gorsza o1,85% względnie: nie promować, baseline pozostaje domyślny.
Pełne mianowniki90/30, missing15/1, invalid0/0. Raport, SHA, wszystkie
wyniki i punktowy DoD: quality/VISION_LAB_HYBRID_20260927.md.
Osobny commit `v1.7.30` / `4072dd53a260677e60a24c49f870e7ef1a58c093`.
Staged check/stat/list i show/stat/status PASS;38 własnych plików,
bez cudzych zmian. Pełny hash zapisany po commicie.

Historia przygotowania:

T04 done: v1.7.29 / c8ae5bb711128d1eed5286ed029a7e9dbc35f40a,
końcowy audyt Astra medium PASS. Powyższy kontrakt techniczny Sol high,
zapisany przez root, ma PASS audytu pre-code Astra medium bez P0–P2.
Rozpoczyna się implementacja i preflight dev/val. Przed rzeczywistymi runami
wymagany jest audyt kodu oraz dokładnych requestów/protokołu/coverage;
po runach audyt artefaktów. Kod T05 w trakcie odbioru; brak rzeczywistych
runów treningowych. Root preflight validation:11 unikalnych zdjęć,
29/30 matched,144,844s, bez zmiany rev268/SHA stanu, bez dekodowania
holdoutów. Logi artifacts/vision-lab/t05-preflight-validation-{0,3,6,9}.stdout.json
wiążą ten sam protocol_digest cee25e97bdbeb43d262a05cb306abfdeb288613ac101e722dedbd580e8ed3425.
Jeden niedopasowany target pozostaje w mianowniku. Development w toku.
Root UI read-only: zapisane777 seq10873-10881, selector Baseline domyślny,
przegląd zapisanych plansz zwinięty; bez zapisów/zgód operatora.

### Changed

- MobileNetV3Small refinement propozycji baseline, frozen backbone/BN,
  jawny preprocessing i protocol binding, uczony head narożników,
  homografia24węzłów i gate wymagający review. Unknown nie jest absent.
- Trwałe best_state obok checkpointu resume, fenced ONNX/bestweights/report,
  checksumy i inferencja ORT bez importu torch. Pełny pion API/run_id/
  OpenAPI/klient/selector w galerii, baseline nadal domyślny.
- Izolowane skrypty preflight, freeze protokołu, CUDAresume, ONNX i
  syntetycznej integracji. Poprawione mylące copy kwalifikacji777.

### Verification results

- Wykonawca:16 nowych testów,46 powiązanych backend,36 UI,9 client,
  Ruff/format/mypy34, oba TypeScript/lint/OpenAPI, PSparser,
  productionbuild i diffcheck PASS. Niezależnie30backend/9client/36UI PASS.
- CUDA exact resume, frozenBN, ONNX parity i pełna mała syntetyczna
  integracja trwałego registered-trainer PASS;0 operatorimages/0LABruns.
- Pełny preflight32DEV/90targetów/75matched,11VAL/30/29. Kompletność i
  unikalność źródeł względem manifestu potwierdzona niezależnie.
  Stanrev268 bez zmian; holdouty nietknięte. Historyczne4logiDEV zachowują
  pierwotne digesty, z niezmienionym matchingiem/preprocessingiem.
- Końcowy code/request/preflight audit Astra medium PASS bezP0–P2.
  Jeden smoke8b883801a9164eeb9d72474943adf3c1 uruchomiony poGO.
  Oba realne runy i końcowy audyt artefaktów PASS; rootUI modelu PASS,
  ONNXdelta1,49e-7/corner0,00012207px. Podsumowanie i SHA powyżej/wraporcie.

### Not completed

- Brak aktywacji, push/merge, strojenia na holdoutach, oceny symboli,
  jakości3×3, pełnego protokołu rodzin/czasu i testu fizycznego Androida.
  Pełny restart systemu nie był wykonywany; trwałość sprawdzana nowymi
  procesami i odczytem zapisanego stanu.

### Documentation updates

- D-457, wymagania/architektura/guide lokalny, plan, CURRENT_STATE oraz
  quality/VISION_LAB_HYBRID_20260927.md.

### Recommended next task

- STOP B; nie uruchamiać automatycznie C ani kolejnego treningu.
  Kolejny etap planu: T06–T09 po jawnej zgodzie. Brak dowodu poprawy
  hybrydy; zachować baseline i zamknięte holdouty. Nie potrzeba teraz
  dodatkowych siatek bez konkretnego planu wynikającego z analizy błędów.
