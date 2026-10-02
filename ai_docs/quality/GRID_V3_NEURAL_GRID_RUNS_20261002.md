---
title: TASK-0802 — neural_grid, runy treningowe (V3-B)
status: draft
last_updated: 2026-10-02
---

# neural_grid — raport runów (TASK-0802)

## Stan

- Implementacja, presety A/B/C z fingerprintami, metryki i smoke: gotowe przed
  runem 1 (ten dokument w tej postaci powstał przed startem runu 1).
- Run 1 (preset A): uruchomiony jako odłączony proces protokołu runów — sekcja
  „Run 1”. Wynik, eksport ONNX, parity i czas CPU uzupełnia orkiestrator po
  zakończeniu runu (komendy w sekcji „Komendy”).
- Runy 2 (B) i 3 (C): nieuruchomione; decyzja orkiestratora po obejrzeniu
  wyniku poprzedniego runu (wolno pominąć run, nie wolno zmienić presetu).
- Przegląd etykiet operatora (600 plansz, TASK-0801) nie jest jeszcze wykonany;
  trening ruszył równolegle decyzją operatora. Błędy etykiet S/B ograniczają
  osiągalny wynik i są nieznane w chwili treningu.

## Dane

- Snapshot `production-geometry-snapshots\286f2e370aa84437c63fcffe202f01260d6ca13aee317eb8c11cac2ad0f2df59`
  (`production-geometry-split-v2`, format `production-geometry-snapshot-v1`).
- Czytane role: wyłącznie `training` (6 000 zdjęć / 54 000 plansz) i
  `development` (600 / 5 400). Strażnik `require_roles` odrzuca każdą inną rolę
  (`gold`, `final_test`, `unseen_game`, `validation`) przed otwarciem snapshotu.
  `samples.jsonl` zawiera wszystkie role w jednym pliku: linia jest haszowana
  (kontrola sumy z `manifest.json`), ale dekodowana jako JSON dopiero, gdy jej
  `imageId` według `split.json` należy do dozwolonej roli; obraz innej roli nie
  jest nigdy otwierany. Test sprawdza to na snapshocie, w którym linia złota nie
  jest poprawnym JSON-em.
- Kontrola integralności na starcie runu: SHA-256 `samples.jsonl`, `split.json`
  i każdego obrazu 6 600 zdjęć ról dozwolonych z manifestem snapshotu; ID
  snapshotu = nazwa katalogu = `manifest_id` żądania runu.
- Fakty o etykietach (odczyt ról dozwolonych): każde zdjęcie ma 9 plansz
  (9 oczekiwanych); żadna plansza nie ma niedostępnych komórek; 24 węzły każdej
  etykiety są dokładnie projekcyjnym obrazem siatki 6 × 4 z narożników (reszta
  maks. 0,0001 px). Rozmiary zdjęć: 1520 × 780–1074 i 1080 × 572–606.
- Pochodzenie etykiet developmentu: poziom B (2 700 plansz) =
  `structured_opencv_v1` (`structured-opencv-independent-board-refinement-v2-pinned-preflight-v1`),
  czyli wynik silnika produkcyjnego; poziom S (2 700) = `manual_v1`
  (`manual-source-geometry-v1`, 18 × `-required-v1`), czyli korekta po
  reweryfikacji.

## Architektura (zaimplementowana)

Silnik `neural_grid` (`vision_lab/neural_grid_inference.py`,
`NeuralGridEngine.detect`) implementuje `GeometryEngine` i zwraca
`GeometryResult` jak `baseline`/`hybrid`; każda plansza ma status
`needs_review` i powód `NEURAL_GRID_GATE_UNCALIBRATED` (bramkę kalibruje
TASK-0803). Liczba plansz wynika wyłącznie z detekcji.

1. **Ekran.** Zdjęcie skalowane `INTER_AREA` do dłuższego boku 768 px,
   dopełnione do wielokrotności 32 (w treningu płótno 768 × 576). Szkielet
   `torchvision mobilenet_v3_large` (cechy, **trening od zera** — wag ImageNet
   dla Large nie ma offline; w cache labu jest tylko `mobilenet_v3_small`, nie
   pobierano niczego) z FPN do kroku 4 (szer. 96). Głowice: mapa ciepła środków
   plansz (1 kanał, focal loss CenterNet, pik 1 w komórce środka, sigma = maks.
   1, 0,1 × krótszy wymiar planszy w komórkach) i regresja offsetów 4 narożników
   (TL, TR, BR, BL) od środka komórki (8 kanałów, / 64 px, L1 ważone Gaussem
   ≥ 0,5). Dekodowanie: maksimum 3 × 3, próg 0,3, top-k 64, NMS quadów IoU > 0,5
   — bez założenia liczby plansz.
2. **Plansza.** Wycinek wokół quada z marginesem 15% z każdej strony,
   prostowany homografią do 320 × 192 (quad na prostokącie wewnętrznym), z
   oryginalnej rozdzielczości. Osobny szkielet MobileNetV3-Large + FPN (krok 4,
   mapa 80 × 48); głowica 24 map węzłów dekodowana spatial soft-argmax do
   pikseli wycinka (strata: SmoothL1 współrzędnych × 0,125 + entropia krzyżowa do
   Gaussa sigma 1 komórka × 0,05) i maska widoczności 15 komórek (BCE × 0,5).
   Trening stopnia 2 na quadach etykiet z zaburzeniem (podobieństwo: skala ±6%,
   przesunięcie ±4% przekątnej, obrót ±2°; szum narożników N(0; 1,5% przekątnej)).
3. **Dopasowanie siatki.** Węzły z wycinka wracają do pikseli źródła
   odwrotną homografią; homografia siatki 6 × 4 → węzły: RANSAC OpenCV (próg
   0,02 przekątnej quada stopnia 1), potem najmniejsze kwadraty na inlierach i
   odświeżenie inlierów (≤ 2 iteracje). Wynik: 24 węzły dopasowanej siatki
   projekcyjnej, liczba inlierów, reszta RMS / przekątna (miara pewności dla
   TASK-0803; dostępna w `NeuralGridEngine.analyse`). Mniej niż 8 inlierów →
   najmniejsze kwadraty na 24 węzłach i powód `NEURAL_GRID_FIT_FAILED`.
- Parametry: ekran 3 331 673, plansza 3 264 407 (razem 6 596 080).
- Wejście ONNX: surowe RGB 0–255 float (normalizacja ImageNet w grafie);
  `screen.onnx` (`pixels` N × 3 × 32h × 32w → `heat`, `offsets`), `board.onnx`
  (`crops` N × 3 × 192 × 320 → `nodes`, `peak`, `visibility`), opset 18,
  eksport `torch.onnx.export(dynamo=True)` jak w T05.
- Augmentacje (`neural_grid_data.py`): perspektywa/podobieństwo (skala, obrót,
  przesunięcie, drgania narożników), barwa/nasycenie/jasność/kontrast, odblask
  (jasne plamy eliptyczne), zasłonięcie prostokątem (kolor lub szum) i
  kształtem „ręki” (dłoń + palce w kolorze skóry), rozmycie, szum, kompresja
  JPEG. Etykiety zasłoniętych plansz pozostają.
- Trening: AdamW, mieszana precyzja fp16 + GradScaler, przycinanie gradientu 5,
  rozgrzewka + kosinus według postępu rundy, wsad A/B 12 zdjęć × 4 wycinki,
  C 8 zdjęć × 9 wycinków; 6 procesów ładowania danych (dekodowanie JPEG z dysku,
  bez kopii snapshotu w RAM).
- Pamięć GPU (RTX 4050 Laptop 6 GB): A — maks. 4,67 GB alokacji / 5,76 GB
  rezerwacji w próbie 8 kroków, 5,08 GB alokacji w smoke; C przy 12 × 9 = 6,67 GB
  (przekracza VRAM, krok 2,27 s) — dlatego C ma wsad 8 × 9 (4,50 / 5,14 GB).
  Próba pamięci (skrypt poza repo, 8 kroków na rzeczywistych wsadach, bez runu i
  checkpointu) poprzedziła zamrożenie presetów.

## Metryki (D-483) — zamrożone przed treningiem

Definicja w kodzie: `neural_grid_protocol.METRIC_DEFINITION`
(`neural-grid-metrics-v1`), część każdego presetu (zmiana = inny fingerprint),
implementacja `neural_grid_metrics.py`.

- Dopasowanie predykcji do etykiet: przypisanie węgierskie maksymalizujące IoU
  quadów (narożniki = węzły 0, 5, 23, 18) wśród par z IoU ≥ 0,5; pary poniżej
  progu nie są dopasowane.
- Normalizacja: odległość węzłów 0 i 23 etykiety (przekątna TL–BR) — ta sama
  co w T05, więc jedna definicja obsługuje oba wymagania.
- Plansza poprawna: NME (średni błąd 24 węzłów / przekątna) ≤ 0,02 **i**
  maksymalny błąd węzła ≤ 0,05 przekątnej; plansza dopasowana, ale strukturalnie
  niepoprawna (`cell_quads`), nie jest poprawna.
- Fałszywa plansza: predykcja, której IoU z każdą etykietą < 0,5.
- Zdjęcie kompletne i poprawne (metryka nadrzędna): każda etykieta dopasowana i
  poprawna i brak fałszywej planszy. Dodatkowo raportowane: duplikaty
  (niedopasowana predykcja z IoU ≥ 0,5 z jakąś etykietą) i wariant ścisły bez
  duplikatów.
- Image-macro (druga miara, T05): na etykietę min(1, NME), brak albo plansza
  niepoprawna strukturalnie = 1, średnia na zdjęcie, średnia po zdjęciach;
  fałszywe plansze nie mają kosztu (jak w T05).
- Pomocnicze: odzysk plansz (poprawne / oczekiwane), czułość detekcji
  (dopasowane / oczekiwane), NME mediana i p95, maks. błąd węzła mediana i p95,
  fałszywe plansze i zdjęcia z nimi, wszystko także osobno dla poziomów S i B.
- Wybór checkpointu: wyłącznie development snapshotu v2, maksimum odsetka zdjęć
  kompletnych i poprawnych; remis → niższe image-macro; remis → wcześniejsza
  runda. Ewaluacja po każdej rundzie na pełnych 600 zdjęciach (smoke: 24).

## Presety (zamrożone przed runem 1)

Pliki `vision_lab/neural_grid_presets/{A,B,C}.json`; fingerprint = SHA-256
kanonicznego JSON-a, zapisany w `neural_grid_protocol.FROZEN_PRESET_FINGERPRINTS`.
Zmieniony plik nie przechodzi `load_preset` (test). Wspólne: ziarno 802001,
12 rund × 1 050 s treningu, limit runu 14 400 s, minimalna runda 120 s, rezerwa
końcowa 300 s, próg dekodowania 0,3, NMS 0,5, RANSAC 0,02.

| Preset | Fingerprint | Hipoteza (skrót) | Różnica względem A |
|---|---|---|---|
| A | `027b5db151b7094e06e69f6910d705a944312afe4341d37ebbc72c1782f0701d` | bazowy: mapa środków + offsety narożników i stopień 24 węzłów od zera, umiarkowane augmentacje, odzyskuje plansze pomijane przez produkcję i mieści węzły w tolerancji D-483 na większości zdjęć developmentu | — (LR 1e-3, rozgrzewka 3%, wsad 12 × 4, odblask p 0,25, zasłonięcia p 0,25, ręka p 0,2) |
| B | `658b3b529cb332016a15d953d7d2387d6adf35eeb9d5ad2b3660f341928b7da7` | ręka i odblask to znane błędy produkcji; mocniejsze zasłonięcia podnoszą odsetek zdjęć kompletnych kosztem niewielkiej utraty precyzji na czystych zdjęciach | odblask p 0,55 (do 3 plam, promień 0,05–0,25, siła 0,35–0,95), zasłonięcia p 0,6 (do 3, rozmiar 0,05–0,25), ręka p 0,5 (rozmiar 0,15–0,4) |
| C | `d54490696c341a18f7c0cf1c4ce0d2773ba935089de60de93ec46b4dd402b1e3` | wąskim gardłem progu NME 0,02 jest precyzja stopnia 2; trening na wszystkich planszach zdjęcia z niższym LR poprawia NME | 9 wycinków na zdjęcie, wsad 8 zdjęć, LR 5e-4, rozgrzewka 5% |

## Protokół runów i budżet D-481 (egzekwowane kodem)

- Run = `NeuralGridRunRequest` (rozszerza `StartRunRequest`: `preset`,
  `preset_fingerprint`; konfiguracja `NeuralGridConfiguration` z
  `max_seconds ≤ 14 400`) w istniejącym `RunManager` (`requestId`, fence,
  lease 60 s, checkpoint schema v2, `used_seconds` trwałe w `state.json`).
  `runs.py` dostał dwa opcjonalne parametry (`state_type`, `admit`); domyślne
  zachowanie i istniejące testy bez zmian. Publiczny kontrakt API labu
  (`TrainingConfiguration` ≤ 1 800 s) nie został zmieniony.
- Katalog runów: `C:\Users\tuszy\Documents\game_predictor_vision_data\neural-grid-runs\`
  (`state.json`, `settings.json`, `<run>/attempt-<n>/` z `worker.log`,
  `progress.json`, `losses.jsonl`, checkpointami `<sha>.pt` i raportem
  `<sha>.json`).
- Budżet: `admit_run` pod blokadą runów liczy wszystkie zapisane runy `train`
  modelu `neural-grid-v1` niezależnie od statusu (przerwany run nie oddaje
  budżetu): najwyżej 3, najwyżej jeden na preset. Wznowienie (`resume`) to nowa
  próba tego samego runu z pozostałym czasem. Smoke nie liczy się do budżetu,
  ale kontrakt wymusza ≤ 50 kroków (2 rundy × 20).
- Limit 4 h: (1) kontrakt `max_seconds ≤ 14 400`; (2) trener planuje długość
  rundy z trwałego `used_seconds` (pozostały czas − rezerwa / pozostałe rundy −
  szacowany czas ewaluacji i checkpointu) i kończy run `RUN_BUDGET_EXHAUSTED`
  zamiast zaczynać rundę krótszą niż 120 s; (3) `RunManager` odmawia heartbeatu,
  checkpointu i sukcesu po przekroczeniu; (4) watchdog procesu kończy go
  `os._exit(124)` dokładnie po pozostałym czasie. Czas liczony jest od claim
  (zegar ścienny, łącznie z ładowaniem danych), więc jest konserwatywny wobec
  „godzin GPU”.
- Brak GPU: `validate_runtime` (torch 2.12.1+cu130, CUDA 13.0) i
  `RUN_GPU_UNAVAILABLE` — bez treningu na CPU.

## Smoke (preset A, GPU)

- Run `be7e9a0a37e44573b58b34397e509583` (request
  `ng-smoke-a-20261002-1`): `succeeded`, 2 rundy × 20 kroków = 40 kroków,
  172,5 s łącznie (przygotowanie danych z kontrolą SHA 13,3 s; start procesów
  ładowania i pierwszy krok ok. 100 s). Strata łączna 16,92 (krok 1) → 3,08
  (krok 40); ekran 4,56 → 0,89, offsety 3,98 → 0,46, węzły 7,61 → 1,30.
  2,1–2,4 kroku/s (≈ 26–29 zdjęć/s), maks. 5,08 GB VRAM. Po 40 krokach sieć
  nie zwraca jeszcze plansz powyżej progu 0,3 (ewaluacja 24 zdjęć: 0 predykcji)
  — oczekiwane.
- Wznowienie: run `c075281a87fc4750bdc752be55b3b6f9` (request
  `ng-smoke-a-20261002-resume`) zabity (`stop --kill`, drzewo procesu) w
  rundzie 2 po checkpoincie rundy 1; po 60 s rekonsyliacja oznaczyła go
  `failed / RUN_LEASE_EXPIRED` (czas naliczony konserwatywnie); `resume`
  utworzył próbę 2, która wczytała checkpoint rundy 1 (krok globalny 20, strata
  na starcie 4,52 zamiast 16,9), dokończyła rundę 2 i zakończyła run
  `succeeded` (48 zarezerwowanych kroków ≤ 50). Po zabiciu nie został żaden
  proces potomny.
- Próba eksportu na checkpoincie smoke (skrypt poza repo, próg dekodowania
  obniżony do 0,02 tylko w kopii presetu, katalog tymczasowy): eksport obu
  grafów 38 s, parity na 4 zdjęciach / 43 planszach — maks. różnica surowa
  1,3e-7 (heat), 6,0e-7 (offsety), węzły źródła 0,089 px — PASS w tolerancji
  T05 (1e-4 / 0,1 px); ORT CPU ok. 0,17 s na zdjęcie z 10 detekcjami.
- Przewidywanie dla runu 4 h: 12 × 1 050 s = 12 600 s treningu ≈ 27 000
  kroków ≈ 330 000 zdjęć ≈ 55 epok zbioru treningowego (przy 2,2 kroku/s).

## Silnik produkcyjny jako odniesienie

- Poziom B: etykiety są z definicji wynikiem silnika produkcyjnego
  `structured_opencv_v1` (automatyczna geometria przyjęta po filtrze zgodności
  symboli). Ta sama miara dla produkcji na 300 zdjęciach B developmentu daje
  zawsze 100% zdjęć kompletnych i poprawnych i image-macro 0 (`reference`,
  sprawdzone). To nie jest pomiar jakości produkcji, tylko granica: na B sieć
  może co najwyżej odtworzyć produkcję, a każda „poprawa” względem rzeczywistej
  planszy liczy się jako błąd.
- Poziom S: etykiety to korekty (reweryfikacja / człowiek) wyniku produkcji;
  snapshot nie przechowuje zastąpionego wyniku produkcji, więc miary produkcji
  na S nie da się policzyć z danych labu (wymaga odczytu historii geometrii
  przez eksporter — zakres TASK-0804).
- Wniosek dla porównania: miary `neural_grid` na developmencie mierzą zgodność
  z „produkcją lub jej korektą”, nie z prawdą niezależną; przewagę nad
  produkcją można wykazać dopiero na zbiorze złotym (TASK-0804). Raportujemy
  wyniki osobno dla S i B.
- Laboratoryjny `baseline` (`screen_layout_v3`, punkt odniesienia T05) przechodzi
  przez ten sam ewaluator (`reference --screen-layout-limit N`); kosztuje ok.
  10,5 s CPU na zdjęcie (600 zdjęć ≈ 1,75 h). Próbka 3 zdjęć (tylko ilustracja,
  nie wynik): 27/27 dopasowanych, 24 poprawne, 1/3 zdjęć kompletnych, NME
  mediana 0,0151.

## Run 1 (preset A)

- Run `43933ac8d7d443c8b9079630a83de2e6`, request `ng-train-a-20261002`,
  start 2026-10-02 12:57:25 (claim ok. 12:57:30), próba 1, 12 rund, limit
  14 400 s. Katalog
  `C:\Users\tuszy\Documents\game_predictor_vision_data\neural-grid-runs\43933ac8d7d443c8b9079630a83de2e6\attempt-1\`.
- Procesy: worker PID 19808 (interpreter bazowy; launcher venv PID 2336, którego
  rodzic — CLI — już się zakończył, więc worker nie jest powiązany z sesją
  terminala) i 6 procesów ładowania danych.
- Potwierdzenie o 13:00:33: GPU 99%, 5,85 GB VRAM zajęte, 2,25 kroku/s, strata
  łączna 7,68 (krok 50) → 2,05 (100) → 1,33 (150); checkpoint startowy (runda 0)
  zapisany; runda 1 zaplanowana na 963 s (rezerwa na początkowe oszacowanie
  ewaluacji 180 s), kolejne do 1 050 s. Oczekiwany koniec ok. 16:40.
- Wynik (najlepsza runda, metryki developmentu, krzywe z `losses.jsonl` i
  historii rund, czas treningu): do uzupełnienia po zakończeniu.

## Run 2 (preset B), Run 3 (preset C)

Nieuruchomione.

## ONNX, parity, czas CPU

Do wykonania dla najlepszego checkpointu po runie (`export`, `timing`).

## Komendy

Wszystkie komendy z katalogu worktree, interpreter GPU z kodem worktree:

```powershell
$env:PYTHONPATH = 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src'
$py = 'C:\Users\tuszy\Documents\game_predicotr\.venv-vision-lab\Scripts\python.exe'
$m = 'game_predictor_worker.vision_lab.neural_grid_runs'
& $py -m $m status                                   # wszystkie runy + budżet
& $py -m $m status --run <run_id>                    # stan, runda, czas, postęp, ostatnia strata
& $py -m $m stop --run <run_id>                      # kooperacyjnie: runda kończy się wcześniej, ewaluacja + checkpoint, status cancelled
& $py -m $m stop --run <run_id> --kill               # natychmiast (proces sprawdzony po tożsamości); po 60 s failed/RUN_LEASE_EXPIRED
& $py -m $m resume --run <run_id>                    # nowa próba z ostatniego checkpointu, ten sam budżet
& $py -m $m evaluate --run <run_id>                  # development, najlepszy stan (GPU), JSON w <run>/evaluations/
& $py -m $m export --run <run_id> --parity-images 16 # ONNX najlepszego stanu + parity, katalog <run>/exports/
& $py -m $m timing --bundle <katalog_eksportu> --images 30 --threads 4
& $py -m $m reference --screen-layout-limit 600      # odniesienie produkcji (B) + baseline labu (CPU, ~1,75 h)
& $py -m $m start --preset B --purpose train --request-id ng-train-b-<data>   # run 2 tylko po decyzji orkiestratora
```

## Ryzyka i ograniczenia

- Trening od zera (brak wag ImageNet offline) — wolniejsza zbieżność niż z
  wagami wstępnymi; smoke potwierdza tylko spadek straty.
- Wszystkie zdjęcia treningowe mają 9 plansz i żadnej niedostępnej komórki:
  głowica widoczności uczy się stałej, a detekcja nie widziała zdjęć z mniejszą
  liczbą plansz poza tymi, które augmentacja częściowo wypycha z kadru.
- Development pochodzi z rodzin podobnych do treningu; etykiety B to wynik
  produkcji (sufit „zgodności z produkcją”).
- Próg NME 0,02 jest wymagający także dla produkcji/baseline labu (na próbce 3
  zdjęć baseline ma 1/3 zdjęć kompletnych).
- Parity w źródle zależy od dopasowania RANSAC: różnice surowe rzędu 1e-7 dały
  0,089 px na niewytrenowanym modelu, blisko progu 0,1 px; raport parity podaje
  też różnicę węzłów przed dopasowaniem.
- Płótno treningowe 768 × 576 zakłada zdjęcia poziome; zdjęcie pionowe
  działa w inferencji (dynamiczny rozmiar), ale nie było w treningu.
