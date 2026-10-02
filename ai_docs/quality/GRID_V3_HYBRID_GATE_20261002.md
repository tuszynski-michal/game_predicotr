---
title: TASK-0803 — hybrid_v3, bramka zgodności i kalibracja progów (V3-B)
status: draft
last_updated: 2026-10-02
---

# hybrid_v3 — bramka zgodności i kalibracja (TASK-0803)

## Stan

- Sekcje „Bramka”, „Siatka progów” i „Reguła wyboru” zapisano **przed**
  uruchomieniem kalibracji (kod: `vision_lab/hybrid_v3_gate.py`,
  `vision_lab/hybrid_v3_calibration.py`, stałe `THRESHOLD_GRID` i
  `SELECTION_RULE`).
- Wyniki kalibracji: sekcja „Wynik kalibracji” (uzupełniona po jednorazowym
  przebiegu).

## Bramka (`hybrid-v3-gate-v1`)

Wejście jednego zdjęcia: siatki odniesienia (lista plansz: 24 węzły i pozycja;
w aplikacji — wynik silnika produkcyjnego dla tego samego zdjęcia, TASK-0805; w
labie — etykiety snapshotu) i siatki `neural_grid` (24 węzły dopasowanej siatki,
reszta dopasowania RMS / przekątna quada, liczba inlierów, porażka dopasowania).
Bramka nie uruchamia żadnego silnika i nie zakłada liczby plansz.

1. **Parowanie.** Przypisanie węgierskie maksymalizujące IoU quadów narożnych
   (węzły 0, 5, 23, 18) wśród par z IoU ≥ 0,5 (próg dopasowania D-483). Para
   poniżej skalibrowanego progu IoU jest niezgodnością quadów, nie dwiema
   osobnymi planszami.
2. **Zgodność węzłów.** Największa odległość odpowiadających sobie węzłów obu
   siatek / przekątna TL–BR odniesienia (normalizacja D-483) ≤ tolerancja.
3. **Stan planszy.** `confident` tylko dla pary, w której obie siatki są
   strukturalnie poprawne (`cell_quads`), dopasowanie sieci się udało, quady i
   węzły są zgodne. Każda inna plansza: `needs_review` z wszystkimi pasującymi
   powodami z zamkniętej listy:

   | Kod | Znaczenie |
   |---|---|
   | `HYBRID_V3_QUAD_DISAGREEMENT` | para o IoU quadów poniżej progu (np. przeskok o kolumnę) |
   | `HYBRID_V3_NODE_DISAGREEMENT` | para o największym błędzie węzła powyżej tolerancji |
   | `HYBRID_V3_NETWORK_ONLY` | plansza tylko z sieci (także duplikat detekcji) — nigdy `confident` |
   | `HYBRID_V3_REFERENCE_ONLY` | plansza tylko z odniesienia (sieć jej nie zwróciła) |
   | `HYBRID_V3_NETWORK_FIT_WEAK` | dopasowanie siatki sieci nieudane (`NEURAL_GRID_FIT_FAILED`: < 8 inlierów RANSAC), brak siatki albo reszta nieskończona; reguła stała, nie kalibrowana |
   | `HYBRID_V3_BOARD_INVALID` | siatka którejkolwiek strony strukturalnie niepoprawna albo brak siatki odniesienia |

4. **Wybór węzłów (zapisany przed pomiarem).** Przy zgodzie: węzły sieci, gdy
   reszta dopasowania < próg, inaczej węzły odniesienia. Plansza
   `needs_review` zachowuje węzły odniesienia, gdy je ma, inaczej węzły sieci.
5. **Zdjęcie (D-484).** `confident` tylko wtedy, gdy ma co najmniej jedną
   planszę, wszystkie plansze są `confident` i liczba plansz obu źródeł jest
   równa. Powody zdjęcia: `HYBRID_V3_BOARD_COUNT_MISMATCH`,
   `HYBRID_V3_BOARD_NEEDS_REVIEW`, `HYBRID_V3_NO_BOARDS`.

Kontrakt `GeometryEngine` (`HybridV3Engine.detect`): plansza `confident` →
`status: complete` bez powodów; `needs_review` → `status: needs_review` z
powodami; plansza bez siatki → `status: unreadable` z powodami. Pierwszy powód
wyniku to `HYBRID_V3_PHOTO_CONFIDENT` albo `HYBRID_V3_PHOTO_NEEDS_REVIEW` (dalej
powody zdjęcia). Kolejność plansz: odczyt wierszami jak w `neural_grid`. Wynik
jest wyłącznie review/shadow (D-461).

## Siatka progów (zapisana przed pomiarem)

4 × 7 × 3 = 84 punkty:

| Próg | Wartości |
|---|---|
| IoU quadów (`min_quad_iou`) | 0,80; 0,85; 0,90; 0,95 |
| Tolerancja węzłów (`max_node_error`, maks. błąd węzła / przekątna) | 0,005; 0,0075; 0,01; 0,015; 0,02; 0,03; 0,04 |
| Reszta dopasowania (`max_fit_residual`, wybór węzłów) | 0,0025; 0,005; 0,01 |

Tolerancja węzłów sięga 0,04 (ponad przykładowe 0,02 z taska), bo bramka
porównuje **największy** błąd węzła, a nie średni: do 0,02 każda plansza
`confident` jest z konstrukcji poprawna względem odniesienia według D-483,
dopiero wyższe progi sprawdzają, czy ograniczenie błędu realnie działa.

## Reguła wyboru progów (zapisana przed pomiarem)

- Zbiór: wyłącznie rola `development` snapshotu v2 (600 zdjęć: 300 B, 300 S)
  — **zbiór kalibracyjny, nie niezależny pomiar** (należy do TASK-0804).
- Odniesienie: etykiety snapshotu. B: etykieta = wynik silnika produkcyjnego
  (realistyczny tryb shadow). S: etykieta = korekta; tryb „sieć kontra
  etykieta-korekta”, raportowany osobno.
- Sieć: eksport ONNX runu 1 (`43933ac8…e2e6`, `exports\2cd19738…-round3`), ONNX
  Runtime CPU, 4 wątki.
- Błąd planszy `confident`: siatka sieci **albo** siatka wyjściowa nie jest
  poprawna względem etykiety według D-483 (strukturalnie poprawna, NME ≤ 0,02,
  maks. błąd węzła ≤ 0,05 przekątnej). Siatka sieci wchodzi do definicji, bo w
  labie odniesienie jest etykietą — wybór węzłów odniesienia ukrywałby błąd z
  konstrukcji. Raportowany jest też sam błąd siatki wyjściowej.
- Warunek: błędne plansze `confident` / plansze `confident` ≤ 0,5% osobno dla
  B, dla S i dla całości (brak plansz `confident` = 0 błędów).
- Cel: największy odsetek zdjęć `confident` wśród wszystkich 600 zdjęć.
- Remisy kolejno: mniej błędnych plansz `confident`; wyższy próg IoU; niższa
  tolerancja węzłów; próg reszty najbliższy 0,005 (a priori — lab nie umie
  rozstrzygnąć, które węzły są lepsze, bo odniesienie jest etykietą).
- Brak punktu spełniającego warunek: progi nie są wybierane, raport to mówi.

## Wynik kalibracji

### Przebieg

- 2026-10-02, jeden przebieg na 600 zdjęciach development (300 B, 300 S,
  5 400 plansz etykiet), ONNX Runtime `CPUExecutionProvider`, 4 wątki, bez
  GPU (równolegle trwał run 2 treningu na GPU). Inferencja 146,9 s ściany;
  `analyse` mediana 0,244 s, p95 0,270 s na zdjęcie (wolniej niż 0,18 s z
  `cpu-timing-30.json`, bo CPU dzielił proces ładowania danych treningu).
  Brak błędów dekodowania.
- Wyniki: katalog
  `neural-grid-runs\43933ac8d7d443c8b9079630a83de2e6\hybrid-v3-calibration\`
  — `network-development.json` (wyjście sieci na zdjęcie, tożsamość eksportu i
  snapshotu; SHA-256 `9a281978…01af3`) i `calibration.json` (krzywa 84 punktów,
  wybór, stany zdjęć i plansz; SHA-256 `10d532a5…08db1a`).
- Determinizm: ponowne przeliczenie siatki z zapisanego wyjścia sieci
  (`--reuse-network`, inny katalog) dało bajtowo identyczny `calibration.json`.
- Kontrola zgodności ONNX z ewaluacją runu 1 (PyTorch, GPU): na wyjściu ONNX
  ta sama metryka D-483 (kod bez zmian) daje 51 „błędnych” plansz etykiet (B 2,
  S 49) — dokładnie te same 51 par (zdjęcie, plansza) co ewaluacja runu 1.

### Wybrane progi

Wszystkie 84 punkty siatki spełniają warunek 0,5%. Wybrany punkt
(`hybrid_v3_engine.RUN1_DEVELOPMENT_THRESHOLDS`):

| Próg | Wartość |
|---|---|
| IoU quadów | **0,90** (0,80 i 0,85 dają identyczny wynik; remis → wyższy) |
| Tolerancja węzłów | **0,04** przekątnej (górna krawędź siatki) |
| Reszta dopasowania | **0,005** (remis wszystkich trzech poziomów → najbliższy 0,005) |

| Zbiór | Zdjęcia `confident` | Plansze `confident` | Błędne plansze `confident` | Zdjęcia `confident` z błędną planszą |
|---|---|---|---|---|
| razem | 542 / 600 (90,3%) | 5 335 / 5 400 (98,8%) | 7 (0,13%; Wilson 95%: 0,06–0,27%) | 7 / 542 (1,3%; 0,6–2,6%) |
| B | 294 / 300 (98,0%) | 2 694 / 2 700 (99,8%) | 0 (0%; 0–0,14%) | 0 / 294 (0–1,3%) |
| S | 248 / 300 (82,7%) | 2 641 / 2 700 (97,8%) | 7 (0,27%; 0,13–0,55%) | 7 / 248 (2,8%; 1,4–5,7%) |

Wszystkie 5 335 plansz `confident` dostają węzły sieci (reszta dopasowania
sieci na developmencie: mediana 0,00084, maks. 0,0027 — poniżej każdego progu
poza 0,0025, przy którym jedna plansza bierze węzły odniesienia). Błąd siatki
wyjściowej = błąd konserwatywny (7) w każdym punkcie, w którym wybrano węzły
sieci.

### Krzywa pokrycie–błąd

Reszta 0,005 (pozostałe poziomy reszty dają te same liczby zdjęć, plansz i
błędów). IoU 0,80, 0,85 i 0,90 dają identyczne wiersze; IoU 0,95 osobno.

| Tolerancja węzłów | IoU 0,80–0,90: zdjęcia `confident` (B / S) | błędne plansze `confident` (S) | IoU 0,95: zdjęcia `confident` (B / S) | błędne (S) |
|---|---|---|---|---|
| 0,005 | 19 = 3,2% (19 / 0) | 0 | 19 = 3,2% (19 / 0) | 0 |
| 0,0075 | 132 = 22,0% (130 / 2) | 0 | 132 = 22,0% (130 / 2) | 0 |
| 0,01 | 206 = 34,3% (194 / 12) | 0 | 206 = 34,3% (194 / 12) | 0 |
| 0,015 | 324 = 54,0% (269 / 55) | 0 | 322 = 53,7% (267 / 55) | 0 |
| 0,02 | 372 = 62,0% (280 / 92) | 0 | 361 = 60,2% (277 / 84) | 0 |
| 0,03 | 472 = 78,7% (294 / 178) | 0 | 421 = 70,2% (289 / 132) | 0 |
| **0,04** | **542 = 90,3% (294 / 248)** | **7** | 432 = 72,0% (289 / 143) | 0 |

Rozkład par sieć–odniesienie (5 400 par, każda plansza etykiety sparowana):
maks. błąd węzła mediana 0,0044, p95 0,021, p99 0,043, maks. 0,203; IoU quadów
mediana 0,991, p5 0,957, min. 0,532. Pokrycie rośnie aż do krawędzi siatki
(0,03 → 0,04: +70 zdjęć S, +7 błędnych plansz); punkt powyżej 0,04 nie był
w siatce zapisanej przed pomiarem i nie został sprawdzony.

### Powody `needs_review` (wybrane progi)

| Powód | B | S | Razem |
|---|---|---|---|
| `HYBRID_V3_NODE_DISAGREEMENT` (plansze) | 6 | 59 | 65 |
| `HYBRID_V3_QUAD_DISAGREEMENT` (plansze; zawsze razem z węzłami) | 0 | 21 | 21 |
| `HYBRID_V3_NETWORK_ONLY` | 0 | 0 | 0 |
| `HYBRID_V3_REFERENCE_ONLY` | 0 | 0 | 0 |
| `HYBRID_V3_NETWORK_FIT_WEAK` | 0 | 0 | 0 |
| `HYBRID_V3_BOARD_INVALID` | 0 | 0 | 0 |
| plansze `needs_review` | 6 | 59 | 65 |
| `HYBRID_V3_BOARD_NEEDS_REVIEW` (zdjęcia) | 6 | 52 | 58 |
| `HYBRID_V3_BOARD_COUNT_MISMATCH` (zdjęcia) | 0 | 0 | 0 |
| `HYBRID_V3_NO_BOARDS` (zdjęcia) | 0 | 0 | 0 |

Na developmencie sieć zwraca dokładnie 9 plansz na każdym zdjęciu i każda
paruje się z etykietą, więc powody „tylko z sieci”, „tylko z odniesienia”,
„słabe dopasowanie” i „nieważna” nie wystąpiły — są sprawdzone tylko testami
syntetycznymi.

### B — tryb shadow (odniesienie = wynik silnika produkcyjnego)

- 294 / 300 zdjęć `confident`, 0 błędnych plansz `confident`. To mierzy
  **zgodność i pokrycie**, nie poprawność: odniesienie jest jednocześnie
  etykietą, więc „błąd” oznacza tylko, że sieć odbiega od produkcji ponad
  tolerancję D-483.
- 6 plansz B do przeglądu (6 zdjęć): 2 to plansze „błędne” według metryki
  runu 1, 4 mają NME ≤ 0,02, ale maks. błąd węzła > 0,04.

### S — sieć kontra etykieta-korekta (nie silnik produkcyjny)

- Pierwotny wynik silnika produkcyjnego dla zdjęć S nie istnieje w snapshocie;
  to **nie jest** porównanie z silnikiem produkcyjnym, tylko z korektą.
- 49 plansz S „błędnych” według metryki (te same 49 w ewaluacji runu 1 i w
  ONNX): bramka kieruje **42** do przeglądu (21 z niezgodnością quadów i
  węzłów, 21 tylko węzłów) i przepuszcza **7** jako `confident` (7 różnych
  zdjęć; maks. błąd węzła 0,036–0,040, IoU 0,905–0,922, NME > 0,02 — plansze
  „tuż za tolerancją”). Te 7 to całe 7 błędnych plansz `confident`.
- Dodatkowo 17 plansz S poprawnych według metryki trafia do przeglądu
  (maks. błąd węzła > 0,04 przy NME ≤ 0,02).
- Przegląd wizualny po runie 1 (14 plansz z tej puli) nie znalazł planszy, w
  której etykieta S byłaby lepsza od sieci, a dwie etykiety były przesunięte o
  kolumnę lub rząd. „Błąd względem etykiety” na S jest więc w dużej części
  błędem etykiety, nie sieci; 7 przepuszczonych plansz nie było oglądanych.

### Co wynik znaczy, a czego nie

- Znaczy: na 600 zdjęciach development, przy odniesieniu = etykieta, bramka z
  progami (0,90; 0,04; 0,005) oznacza 90,3% zdjęć jako pewne, a wśród pewnych
  plansz 0,13% nie spełnia tolerancji D-483 względem etykiety (B 0%, S 0,27%).
- Nie znaczy: (1) to nie jest niezależny pomiar — progi wybrano na tych samych
  danych (zbiór kalibracyjny); pomiar należy do TASK-0804 (walidacja, zbiór
  złoty); (2) na B nie mierzy jakości produkcji ani sieci, tylko ich zgodność;
  (3) na S nie mierzy zachowania bramki wobec silnika produkcyjnego — w
  aplikacji odniesieniem na S będzie pierwotny (gorszy) wynik produkcji, więc
  niezgodności będzie więcej, a pokrycie niższe; (4) warunek 0,5% dotyczy
  plansz — na poziomie zdjęcia (jednostka D-484) 1,3% zdjęć pewnych ma planszę
  poza tolerancją względem etykiety (S 2,8%); (5) próg reszty dopasowania nie
  jest skalibrowany: na tych danych żaden poziom nie zmienia wyniku, a lab nie
  rozstrzyga, czy węzły sieci czy produkcji są dokładniejsze; (6) progi są
  związane z modelem runu 1 — inny model (run 2/3) wymaga nowej kalibracji;
  (7) wybór na krawędzi siatki (0,04) oznacza, że optimum reguły może leżeć
  wyżej.

### Pierwotne wyniki silnika produkcyjnego dla zdjęć S (propozycja, niewykonane)

W bazie gry 777 korekta S zapisała nową rewizję geometrii źródła; poprzednia
rewizja (wynik `structured_opencv_v1` sprzed reweryfikacji lub korekty
człowieka) pozostaje jako starsza rewizja tego samego źródła. Propozycja dla
TASK-0804 (pomiar) albo TASK-0805 (shadow):

1. Rozszerzyć eksporter TASK-0800 o opcjonalny plik
   `production-originals.jsonl` (osobny od `samples.jsonl`, z sumą SHA-256 w
   `manifest.json`): dla zdjęcia S — najstarsza rewizja geometrii z
   `method = structured_opencv_v1` (lub najnowsza rewizja automatyczna sprzed
   pierwszej rewizji `manual_v1`), jej identyfikator i wersja silnika, 24 węzły
   każdej planszy w tej samej przestrzeni współrzędnych
   (`exif-normalized-rgb-pixels-v1`), plansze bez siatki jako jawny brak.
   Zdjęcie bez takiej rewizji: jawny powód (np. `PRODUCTION_ORIGINAL_MISSING`),
   nie pominięcie.
2. Nowy snapshot (nowy identyfikator; snapshot v2 nietknięty), te same role i
   ten sam podział; loader czyta plik tylko za strażnikiem ról.
3. Kalibracja/pomiar `hybrid_v3` na S z odniesieniem = pierwotny wynik, a
   błąd liczony względem etykiety-korekty — wtedy S mierzy realny tryb
   shadow. W TASK-0805 odniesieniem jest bieżący wynik produkcji dla tego samego
   SHA zdjęcia, więc problem znika dla nowych zdjęć.

## Odtworzenie

```powershell
$env:PYTHONPATH = 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src'
$r = 'C:\Users\tuszy\Documents\game_predictor_vision_data\neural-grid-runs\43933ac8d7d443c8b9079630a83de2e6'
.\.venv\Scripts\python.exe -m game_predictor_worker.vision_lab.hybrid_v3_calibration `
  --bundle "$r\exports\2cd19738367121e6-round3" --output "$r\hybrid-v3-calibration" --threads 4 `
  --evaluation "$r\evaluations\2cd19738367121e6-best-development.json" [--reuse-network]
```
