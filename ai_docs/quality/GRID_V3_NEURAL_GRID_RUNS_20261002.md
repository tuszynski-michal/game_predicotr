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

## Run 3 (preset D): iteracyjne doszkalanie na Mumiach (TASK-0825, D-490)

Zmiana zakresu D-490 z 2026-10-02: trzeci run budżetu D-481 nie jest presetem C
ani treningiem od wag ImageNet, tylko serią krótkich doszkoleń najlepszego stanu
runu 1 na zdjęciach Mumii akceptowanych porcjami przez operatora. Preset D i jego
fingerprint zapisano w repozytorium przed pierwszą iteracją; presety A/B/C i ich
runy są nietknięte.

### Preset D (zamrożony przed pierwszą iteracją)

Plik `vision_lab/neural_grid_presets/D.json`, fingerprint
`b94a9627df4c2d0886b43776f1a80b406de5d124c36c997ada2b5f93c5d1cbd9`
(`FROZEN_PRESET_FINGERPRINTS["D"]`).

| Parametr | Wartość | Uzasadnienie |
|---|---|---|
| wagi startowe | eksport runu 1 `exports/2cd19738367121e6-round3/weights.pt`, SHA-256 `19b8d138…80f9`, runda 3, checkpoint `2cd19738…83fe8` | najlepszy stan runu 1 (development 554/600 = 92,33%); suma i pochodzenie sprawdzane przed startem iteracji 1; bez pobierania wag |
| architektura, ekran, plansza, dopasowanie, próg dekodowania | jak A/B | te same wagi i ten sam silnik ONNX |
| augmentacje | pełne B | notatka techniczna zadania; ręka i odblask to znane błędy |
| LR, rozgrzewka, koniec | 1e-4, 5%, 10% LR (kosinus w obrębie iteracji) | rząd 1e-4 przy 10–100 zdjęciach ogranicza przeuczenie; każda iteracja ma nowy AdamW |
| wsad | 12 zdjęć: 4 Mumie + 8 z roli `training` 777 (losowanie ze zwracaniem), 4 wycinki plansz na zdjęcie | rozmiar jak A/B (RTX 4050 6 GB); przewaga 777 w każdym wsadzie chroni przed zapomnieniem 777 |
| czas treningu iteracji | 60 s × liczba zdjęć treningowych Mumii, w granicach 300–900 s | do 15 min; przy 8 zdjęciach 480 s — mniej powtórzeń tych samych zdjęć, więcej iteracji z budżetu |
| kandydaci | 3 równe odcinki; po każdym ocena 600 zdjęć development 777 i holdoutu Mumii | wybór stanu bez osobnego zbioru walidacyjnego |
| wybór stanu | dopuszczalny: development 777 nie niżej niż run 1 − 0,5 pkt proc. (≥ 91,83%); spośród dopuszczalnych maksimum odsetka zdjęć kompletnych i poprawnych holdoutu Mumii (remis: niższe image-macro holdoutu, wyższy development, wcześniejszy kandydat); holdout < 3 zdjęć → ostatni dopuszczalny; brak dopuszczalnego → stan poprzedni bez zmian (bez eksportu i propozycji) | notatka techniczna zadania |
| holdout | co piąte zakończone zdjęcie według klucza `sha256('TASK-0825-mumie-holdout-v1:' + SHA-256 źródła)` | deterministyczny, niezależny od kolejności klikania, trwały |
| harmonogram | najwyżej 16 iteracji, limit runu 14 400 s, rezerwa 60 s, szacowany narzut iteracji 420 s, minimalny trening iteracji 240 s | 14 400 / 900 = 16 |
| ziarno | 825001 (+ numer iteracji) | |

### Protokół i budżet (egzekwowane kodem)

- Run 3 to **jeden** run `RunManager` z presetem D w katalogu
  `neural-grid-runs` (ten sam co runy 1 i 2). `admit_run` liczy go jak każdy run
  `train`: po A, B i D nie da się założyć czwartego runu (`NEURAL_GRID_RUN_BUDGET_EXHAUSTED`),
  a drugi run D jest odrzucany (`NEURAL_GRID_PRESET_ALREADY_RUN`).
- Iteracja = próba (attempt) tego runu: iteracja 1 tworzy run, każda następna jest
  wznowieniem (`retry_run`). `used_seconds` przechodzi między próbami bez zmian, więc
  limit 14 400 s obejmuje wszystkie iteracje razem: kontrakt runu, planowanie czasu
  iteracji z trwałego `used_seconds` (komenda odmawia nowej iteracji, gdy po narzucie
  zostaje mniej niż 240 s treningu), odmowa heartbeatu/checkpointu po limicie w
  `RunManager` i watchdog procesu. Czas liczy się od claim (zegar ścienny, z
  ładowaniem danych i oceną).
- Zakończona iteracja kończy próbę statusem `cancelled` z
  `NEURAL_GRID_ITERATION_COMPLETE` i zostawia własny checkpoint (`checkpoint_epoch` =
  numer iteracji, `bestState` = wybrany kandydat, historia wszystkich iteracji) oraz
  własny raport próby. Ostatnia dopuszczalna iteracja (16.) kończy run `succeeded`.
- Przerwanie: proces zabity w trakcie treningu → po 60 s `failed/RUN_LEASE_EXPIRED`
  (czas naliczony konserwatywnie, bez zwrotu); ponowne `iterate` wznawia tę samą
  iterację od checkpointu poprzedniej (nowa próba), nie planuje nowej. Ponowne
  `iterate` po wytrenowaniu nie trenuje drugi raz — kontynuuje od eksportu,
  propozycji albo raportu (stan w `neural-grid-runs\finetune-D\ledger.json`).
- Smoke (`--smoke`): osobny ledger `finetune-D-smoke`, run `smoke` (≤ 50 kroków:
  2 kandydatów × 20 kroków, ocena 24 zdjęć development), nie liczy się do budżetu.

### Dane iteracji i holdout Mumii

- Tylko zamknięte zdjęcia Mumii z magazynu anotacji (D-484). Eksport czyta stan przez
  krótką blokadę magazynu (kopia bajtów pod blokadą, parsowanie po zwolnieniu) — strona
  operatora pracuje dalej.
- Przydział ról: nowe zamknięte zdjęcia są numerowane po wszystkich wcześniejszych w
  kolejności klucza; co piąty numer to `holdout`. Przydział zapisany w ledgerze nie
  zmienia się (także po ponownym otwarciu zdjęcia). Holdout trafia do snapshotu
  iteracji wyłącznie z rolą `development`; worker odmawia treningu, gdy zdjęcie z
  rejestru holdoutu jest wśród zdjęć treningowych (`NEURAL_GRID_HOLDOUT_IN_TRAINING`).
- 777: snapshot v2 przez strażnik ról (`training` do mieszania, `development` do
  oceny); rola `gold` nie jest czytana. Reels i Treasure nie są czytane.
- Komenda odmawia iteracji bez zmian w danych (`NEURAL_GRID_FINETUNE_NO_NEW_PHOTOS`),
  żeby nie wydawać budżetu na te same zdjęcia — chyba że poprzednia iteracja nie
  wybrała nowego stanu (jej zdjęcia nie zostały wyuczone); wtedy plan zapisuje
  `same_data` (patrz „Preset E”).

### Pomiar po iteracji (raport `iterations\NN\report.json` i `report.md`)

1. Holdout Mumii: metryki D-483 względem siatek operatora dla stanu przed iteracją i
   wybranego stanu (z ostrzeżeniem przy < 3 zdjęciach).
2. Development 777 (600 zdjęć): wybrany stan, różnica w pkt proc. względem runu 1
   (92,33%), dopuszczalny spadek 0,5 pkt proc.
3. Trafność propozycji ostatniej porcji (zdjęcia zamknięte od poprzedniej iteracji):
   udział plansz przyjętych bez zmian, poprawionych i narysowanych ręcznie, podział na
   zbiory propozycji (model, który je wygenerował), przesunięcie narożników przy
   poprawkach, czas aktywny na zdjęcie.
4. Wszyscy kandydaci iteracji, reguła wyboru, czas treningu, kroki, zużyty i pozostały
   budżet, ścieżki eksportu ONNX i nowego zbioru propozycji.

Nowe propozycje są osobnym, niezmiennym zbiorem (`generation` = numer iteracji,
`supersedes`, `model` z runem, iteracją i sumą wag) tylko dla zdjęć Mumii jeszcze
niezamkniętych. Strona pokazuje dla każdego zdjęcia najnowszy zbiór, który je
obejmuje; zaakceptowane plansze zachowują identyfikator swojego zbioru (identyfikatory
propozycji nowych zbiorów mają prefiks zbioru).

### Komendy

```powershell
$env:PYTHONPATH = 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src'
$py = 'C:\Users\tuszy\Documents\game_predicotr\.venv-vision-lab\Scripts\python.exe'
$f = 'game_predictor_worker.vision_lab.neural_grid_finetune'
& $py -m $f status                 # ledger, budżet runu 3, holdout, iteracje
& $py -m $f iterate                # jedna iteracja (czeka na trening; ponowienie = wznowienie)
& $py -m $f iterate --no-wait      # tylko start treningu; dokończenie: iterate jeszcze raz
```

### Preset E: reguły od iteracji 2 (zmiana D-490 po iteracji 1)

Reguły przyjęto **po obejrzeniu wyniku iteracji 1 presetu D** (zgoda operatora
2026-10-02, akapit „Zmiana reguł doszkalania po iteracji 1” w D-490); raport każdej
iteracji pod presetem E mówi to wprost. Plik `vision_lab/neural_grid_presets/E.json`,
fingerprint `f8f8559be24eae43f483380ad87b81715480ce16983ee27a9c91938e5765a7bc`
(`FROZEN_PRESET_FINGERPRINTS["E"]`). E jest identyczny z D (dane, mieszanie wsadów,
augmentacje, optymalizacja, harmonogram, budżet, wagi startowe, ziarno — kod sprawdza
to funkcją `training_equivalent`) poza sekcją `finetune.guard_777` (wersja
`neural-grid-finetune-v2`) i opisem hipotezy. Presety A–D, ich fingerprinty i
zamrożone metryki D-483 są bez zmian.

| Reguła | Wartość |
|---|---|
| (a) poziom B development 777 | odsetek zdjęć kompletnych i poprawnych ≥ run 1 − 0,5 pkt proc.; run 1: 298/300 = 99,33% (`2cd19738367121e6-best-development.json`, `summary.by_level.B`), próg 98,83% (≥ 297/300) |
| (b) image-macro development 777 (600 zdjęć) | ≤ 0,0028703064783595768 (run 1, ta sama wartość co `development_image_macro` w D) |
| (c) wykrycie i fałszywe plansze | `detection_recall` = 1,0 i `false_boards` = 0 na 600 zdjęciach |
| wybór spośród dopuszczalnych | najniższe image-macro holdoutu Mumii; remis → niższe image-macro development 777 → wcześniejszy kandydat |
| mały holdout (< 3 zdjęć) | ta sama reguła (nie „ostatni dopuszczalny”); raport oznacza małą próbę |
| brak dopuszczalnego | stan poprzedni bez zmian (`previous_state_kept_777_guard_e`) |

Ciągłość budżetu (egzekwowane kodem):

- E nie jest presetem żadnego runu: `build_request("E")` zwraca
  `NEURAL_GRID_RULES_PRESET_NOT_A_RUN`, a kontrakt żądania runu przyjmuje tylko A–D.
  Run 3 pozostaje runem `5bc981568c3f42bd96f6f9238e57aedc` z presetem D; iteracja 2
  jest kolejną próbą (`retry_run`) tego runu, więc `used_seconds` (682 s po iteracji
  1) przechodzi bez zmian, limit 14 400 s obejmuje wszystkie iteracje, a `admit_run`
  dalej odmawia czwartego runu.
- Pierwsze `iterate` planujące iterację ≥ 2 zapisuje w ledgerze `rules_revisions`
  (E i jego fingerprint, zastępowany D i jego fingerprint, `from_iteration` 2, run,
  D-490). Plan iteracji (`plan.json`, pole `rules`) i historia checkpointu niosą
  reguły; worker ładuje E przez zamrożony fingerprint i odmawia, gdy fingerprint się
  nie zgadza (`NEURAL_GRID_RULES_PRESET_MISMATCH`) albo E zmieniałby trening
  (`NEURAL_GRID_RULES_PRESET_TRAINING_MISMATCH`). Plany bez pola `rules` (iteracja 1)
  zostają przy regułach D; katalog i raport iteracji 1 nie są przebudowywane.
- Te same dane: gdy poprzednia iteracja nie wybrała nowego stanu (`model_unchanged`),
  komenda nie odmawia (`NEURAL_GRID_FINETUNE_NO_NEW_PHOTOS`) i trenuje na tych samych
  zdjęciach; plan i raport zapisują `same_data` z powodem
  `previous_iteration_selected_no_state`. Iteracja 2 startuje z wybranego stanu
  iteracji 1, czyli z wag runu 1 (`init.previous_selected_candidate` = `null`).

Raport iteracji pod E (`report.json`/`report.md`): sekcja „Reguły wyboru: preset E” z
notą o przyjęciu reguł po iteracji 1, progami strażnika i tabelą kandydatów: zdjęcia
poziomu B, image-macro 777, wykrycie, fałszywe plansze, niespełnione warunki,
image-macro i mediana NME holdoutu Mumii przed iteracją → po kandydacie.

Sprawdzenie na liczbach iteracji 1 (tylko odczyt; poziom B nie jest zapisany w
`report.json` iteracji, tylko w historii checkpointu próby 1): wszyscy trzej kandydaci
mieli poziom B 300/300, image-macro 0,002783 / 0,002710 / 0,002726 (≤ 0,0028703),
wykrycie 100% i 0 fałszywych, więc strażnik E dopuściłby wszystkich; wybór według
image-macro holdoutu (0,005399 / 0,005115 / 0,005065) wskazałby kandydata 3 (holdout 2
zdjęcia — mała próba).

### Wyniki

**Smoke (GPU, 2026-10-02 20:26–20:33, po zakończeniu runu 2; katalogi tymczasowe,
kopia magazynu z rewizji 378, kopia zbioru propozycji).** Run smoke
`cf04f19d779c459ab87727be5e844350` (poza budżetem): 10 zamkniętych zdjęć Mumii → 8
treningowych, 2 holdout; wagi startowe z eksportu runu 1 (suma sprawdzona); 2 × 20 =
40 kroków (zarezerwowane ≤ 50), 174 s z claim (start procesów ładowania ok. 100 s,
potem 2,46 kroku/s); strata łączna 0,47 → 0,31; checkpoint iteracji 1
(`checkpoint_epoch` 1), próba zakończona `cancelled/NEURAL_GRID_ITERATION_COMPLETE`.
Eksport ONNX wybranego stanu: parity PASS (8 zdjęć, 72 plansze, surowe ≤ 1,1e-6,
węzły 0,0011 px). Nowy zbiór propozycji `generation` 1 dla 226 niezamkniętych zdjęć
Mumii w 55 s (CPU, 4 wątki), identyfikatory z prefiksem zbioru. Raport: holdout 2/2
przed i po (image-macro 0,0063 → 0,0059); development 777 na 24 zdjęciach smoke 22/24
(nieporównywalne z 600 zdjęciami runu 1); trafność propozycji runu 1 na 10 zdjęciach
(90 plansz): 14% bez zmian, 86% poprawionych (przesunięcie narożnika: mediana 5,0 px,
p95 9,3 px), 0% ręcznie; czas aktywny średnio 165 s/zdjęcie. Strona na 8106 z kopią
(tylko Mumie) pokazała nowy zbiór dla zdjęć niezamkniętych i zbiór bazowy dla
zamkniętych.

Wniosek z pomiaru trafności: operator poprawia prawie każdą propozycję runu 1 o kilka
pikseli — właśnie tę miarę ma obniżać doszkalanie.

**Iteracja 1 (preset D, run `5bc981568c3f42bd96f6f9238e57aedc`, próba 1).** 10
zamkniętych zdjęć Mumii (8 treningowych, 2 holdout), 3 kandydatów, 481 s treningu,
682 s zużyte z 14 400 s. Development 777: 549/600, 546/600, 546/600 (91,5% / 91,0% /
91,0%) przy progu 91,83% — wszyscy odrzuceni przez strażnik D, stan runu 1 bez zmian,
bez eksportu i propozycji. Holdout Mumii: image-macro 0,00634 przed, 0,00540 / 0,00511
/ 0,00506 u kandydatów; mediana NME 0,0067 → 0,0048 / 0,0046 / 0,0045. Po tym wyniku
operator przyjął reguły presetu E (sekcja wyżej). Iteracja 2: nieuruchomiona.

**Preset F (reguły od iteracji 4, D-490).** W iteracji 3 (`finetune-D/iterations/03/report.md`)
wszyscy trzej kandydaci byli na holdoucie Mumii (4 zdjęcia) gorsi od stanu, z którego
iteracja wystartowała (image-macro 0,00274 → 0,00330 / 0,00337 / 0,00336), a preset E mimo
to wybrał kandydata 1, bo wybierał najniższe image-macro spośród dopuszczalnych, nie
porównując go ze stanem początkowym. Nowy zamrożony preset reguł `neural_grid_presets/F.json`
(fingerprint `821bcdca5b9dcaedcb245f7097fb9101f903852d4448744ccfd72c91b0d59d72`) jest
identyczny z E (ten sam strażnik 777, ten sam trening), z jedną różnicą: kandydat jest
wybierany tylko wtedy, gdy jego image-macro holdoutu jest ściśle niższe niż image-macro
stanu początkowego tej samej iteracji (`holdout_before`); w przeciwnym razie zostaje
poprzedni stan (`previous_state_kept_no_holdout_improvement`), bez eksportu ONNX i bez
nowych propozycji, a raport to zapisuje. Gdy brak pomiaru „przed”, stan też zostaje. Przy
mniej niż 3 zdjęciach holdoutu obowiązuje ta sama reguła, a raport oznacza małą próbę. F
obowiązuje od iteracji 4 tego samego runu i budżetu (tak jak przełączenie D→E): pierwsza
iteracja pod F zapisuje w ledgerze wpis `rules_revisions` z oboma fingerprintami (F
zastępuje E), powodem i `from_iteration` 4; F, tak jak E, nie może być presetem runu.
Iteracje 1–3, ich katalogi i raporty oraz presety A–E (fingerprinty i zachowanie) są bez
zmian. Dotąd żadna iteracja pod F nie została uruchomiona.
