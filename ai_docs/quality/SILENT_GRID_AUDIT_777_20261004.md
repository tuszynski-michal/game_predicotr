---
title: TASK-0831 — audyt cichych błędów siatek 777 siecią neural_grid (run 1)
status: draft
last_updated: 2026-10-04
---

# Audyt cichych błędów siatek 777 (TASK-0831)

## Wynik w skrócie

- Sieć `neural_grid` run 1 przeliczyła **wszystkie 55 499 zdjęć**
  `geometry_complete` gry 777 (499 460 żywych plansz), 0 pominiętych, 0 błędów
  odczytu. Baza nie była zapisywana.
- **3 629 z 499 460 plansz (0,73%, na 2 913 zdjęciach) ma parę w sieci, ale
  różni się od niej ponad tolerancję D-483**; do tego 5 plansz tylko w zapisie
  i 28 tylko w sieci. Z tych różnic **958 to przesunięcia okresu** (613 o
  kolumnę, 344 o rząd, 1 po przekątnej) na 853 zdjęciach.
- Przejrzałem 136 obrazów porównawczych (30 najwyższych pozycji rankingu i
  losowe próbki każdej grupy przesunięć). Wynik oględzin dzieli przesunięcia na
  dwie grupy:
  - **727 przesunięć (wszystkie poza jedną grupą niżej) — w każdej obejrzanej
    próbce błędny jest zapis** (89 / 89 obejrzanych, Wilson 95% 95,9–100%):
    zapisana siatka jest przesunięta o rząd w dół na numer sekwencji albo o
    kolumnę w pustą przestrzeń obok planszy, a sieć trafia w planszę. To ciche
    błędy silnika produkcyjnego. Dotyczą 627 zdjęć; 130 z tych plansz ma
    łącznie **253 komórki z decyzją człowieka** (te decyzje dotyczą złych
    wycinków).
  - **231 przesunięć o kolumnę na planszy w prawym górnym rogu strony (pozycja
    2), gdzie zapis leży o kolumnę na prawo od sieci — w każdej obejrzanej
    próbce błędna jest sieć** (13 / 13, Wilson 77–100%, w tym pozycja 20
    rankingu): sieć
    przesuwa siatkę w lewo, na zielone tło, pomijając ciemną skrajną kolumnę
    planszy; zapis jest poprawny. Tych plansz nie należy poprawiać.
- **Duże rozbieżności skali/obrotu** (NME > 0,05, 154 plansze na 128
  zdjęciach): w 14 z 17 obejrzanych błędny jest zapis (siatka przekrzywiona,
  przesunięta o pół rzędu/kolumny), 1 błąd sieci, 2 niejasne. 148 komórek z
  decyzją człowieka na 60 z tych plansz.
- **Drobne rozbieżności** (NME 0,02–0,04, „tuż za tolerancją”, 2 483 plansze)
  — obejrzane 6: przesunięcia o ułamek komórki, wycinki nadal zawierają
  symbole; nie zaliczam ich do błędów.
- **Oszacowanie cichych błędów siatek w 777:** ok. **700–730 plansz z
  przesunięciem okresu** (727 × [95,9–100%]) i **ok. 85–145 plansz z dużym
  przekrzywieniem** (154 × Wilson 14/17 = [59–94%] daje 91–144); razem rząd
  wielkości **790–870 plansz na ok. 740 zdjęciach** (0,16–0,17% plansz). Liczby z
  próbek, nie z obejrzenia każdej planszy — każdą pozycję operator rozstrzyga
  na stronie przeglądu.

## Dane wejściowe i przebieg

| Krok | Wynik | Czas |
|---|---|---|
| Nowy eksport geometrii tylko do odczytu (`scripts/vision_lab_geometry_export.py`, 2 równoległe transakcje `REPEATABLE READ READ ONLY`, `transactionReadOnlyVerified = true`, head `0139`, generacja magazynu 2) | 55 499 zdjęć, 499 460 plansz, 0 wykluczeń, uzgodnienie z bramką `matches = true`; poziomy B 361 103 / G 459 / S 137 473 / U 425 | 928 s (00:21:42–00:37:10 UTC) |
| Kompaktowanie (`silent_grid_audit saved`) | `saved.jsonl`, jedno zdjęcie na linię, rola w snapshocie v2 tylko z `split.json` | 43 s |
| Inferencja run 1 (`infer`, 2 shardy, torch CUDA, wagi `weights.pt` eksportu run 1 związane sumą `19b8d138…80f9`) | 55 499 / 55 499 zdjęć, 0 błędów, 15,8 zdjęć/s na shard | ok. 30 min (00:38–01:08 UTC) |
| Zgodność torch CUDA z ONNX CPU (`parity`, 24 zdjęcia, 216 plansz) | maks. różnica węzła 0,012 px, ta sama liczba plansz | — |
| Porównanie (`compare`) | `boards.jsonl`, `summary.json`, `suspects.json` | 80 s |
| Obrazy (`render`) | 1 233 obrazy | 39 s |
| Identyfikatory komórek (`refs`, osobne zapytanie tylko do odczytu) | 3 634 / 3 634 plansze, 0 zmian rewizji geometrii od eksportu | <5 s |

ONNX Runtime w `.venv-vision-lab` ma tylko `CPUExecutionProvider` (szacunek
CPU: ok. 2,6 h jednym procesem), dlatego inferencja szła tymi samymi wagami w
PyTorch na GPU przez istniejący `torch_engine` (ta sama ścieżka dekodowania co
ONNX). Inferencja jest wznawialna (urwana linia jest obcinana, przetworzone
zdjęcia pomijane, limit `--max-seconds` i plik `STOP`).

## Metoda porównania

Na każdym zdjęciu: parowanie D-483 (algorytm węgierski na IoU quadów ≥ 0,5),
NME i maksymalny błąd węzła względem przekątnej zapisanej siatki (kod
`neural_grid_metrics` bez zmian). Plansza poza tolerancją D-483 (NME ≤ 0,02 i
maks. ≤ 0,05) jest sprawdzana pod kątem przesunięcia okresu: siatka sieci jest
przesuwana o całe komórki (−2…2 kolumny, −2…2 rzędy, ekstrapolacja przez
homografię sieci) względem każdej planszy sieci o IoU ≥ 0,1. Przesunięcie
wyjaśnia rozbieżność, gdy przesunięta siatka sieci odtwarza zapis z NME ≤ 0,03
i maks. ≤ 0,08 oraz NME przesunięte ≤ połowa nieprzesuniętego. Klasy:
`column_shift`, `row_shift`, `diagonal_shift`, `scale_rotation` (dopasowana,
poza tolerancją, bez przesunięcia; z flagą `nearTolerance` dla NME ≤ 0,04 i
maks. ≤ 0,10), `saved_only`, `network_only`, `within_tolerance`. Klasyfikacja
jest symetryczna — mówi, że siatki się różnią, nie która jest dobra.
Ranking: NME bez przesunięcia malejąco (przesunięcie o rząd/kolumnę daje NME
ok. 0,13–0,20).

Kontrola na danych: NME plansz w tolerancji — mediana 0,0021, p95 0,0067, p99
0,0129. NME przesunięcia (jak dokładnie przesunięta sieć odtwarza zapis) —
mediana 0,013, p99 0,028.

## Liczności

### Plansze według klasy i poziomu etykiety

| Klasa | B | G | S | U | Razem | Zdjęć |
|---|---|---|---|---|---|---|
| `column_shift` | 18 | 0 | 593 | 2 | 613 | 602 |
| `row_shift` | 143 | 0 | 193 | 8 | 344 | 258 |
| `diagonal_shift` | 0 | 0 | 1 | 0 | 1 | 1 |
| `scale_rotation` | 292 | 16 | 2 356 | 7 | 2 671 | 2 211 |
| w tym `nearTolerance` | 284 | 16 | 2 176 | 7 | 2 483 | — |
| `saved_only` | 2 | 0 | 2 | 1 | 5 | 4 |
| `within_tolerance` | 360 648 | 443 | 134 328 | 407 | 495 826 | — |
| `network_only` (bez poziomu) | — | — | — | — | 28 | 7 |

52 579 z 55 499 zdjęć (94,7%) ma wszystkie plansze w tolerancji.

### Grupy po oględzinach

| Grupa | Plansz | Zdjęć | Poziom S / B / U | Komórki z decyzją człowieka (plansz) | Obejrzane | Wynik oględzin |
|---|---|---|---|---|---|---|
| przesunięcia poza grupą niżej | 727 | 627 | 574 / 145 / 8 | 253 (130) | 89 | 89 zapis zły |
| `column_shift` [1, 0] na pozycji 2 (prawy górny róg) | 231 | 231 | 213 / 16 / 2 | 78 (53) | 13 | 13 sieć zła, zapis dobry |
| `scale_rotation` NME > 0,05 | 154 | 128 | 152 / 2 / 0 | 148 (60) | 17 | 14 zapis zły, 1 sieć zła, 2 niejasne |
| `scale_rotation` NME 0,04–0,05 bez `nearTolerance` | 34 | 34 | 28 / 6 / 0 | 15 (12) | 0 | nieobejrzane |
| `scale_rotation` `nearTolerance` | 2 483 | 2 134 | 2 176 / 284 / 7 (+16 G) | 1 763 (1 062) | 6 | drobne, nie uznane za błąd |
| `saved_only` | 5 | 4 | 2 / 2 / 1 | 5 (2) | 5 | 3 sieć zgubiła planszę (zapis dobry), 1 zapis przesunięty i sieć bez planszy, 1 niejasny |
| `network_only` | 28 | 7 | — | — | 6 | 27 na zdjęciach, które mają mniej żywych plansz niż oczekiwanych (pozycje zastąpione, D-485) — brak planszy w zapisie, nie zła siatka; 1 na zdjęciu z 9 planszami (krawędź) |

Rozkład przesunięć według pozycji na stronie (wiersz, kolumna strony;
przesunięcie zapisu względem sieci):

| Pozycja | Przesunięcie | Plansz | Obejrzane | Opis |
|---|---|---|---|---|
| (0, 2) | kolumna +1 | 231 | 12 + 1 | sieć w lewo na zielonym tle — **błąd sieci** |
| (0, 2) | kolumna −1 / −2 | 276 / 1 | 12 + 1 | zapis w lewo, w przerwę między planszami — błąd zapisu |
| (0, 0), (1, 0) | kolumna +1 | 39 / 25 | 32 | zapis w prawo w pustą przestrzeń; skrajna lewa kolumna ciemna, często dłoń i strzałka `<` |
| (0, 0), (1, 0) | kolumna −1 | 1 / 3 | 4 | zapis w lewo, dłoń |
| (1, 2), (2, 2) | kolumna ±1 | 35 / 2 | 13 | zapis przesunięty, dłoń przy strzałce `>` |
| (0, 0), (0, 1), (0, 2) | rząd +1 | 92 / 134 / 111 | 19 | zapis o rząd w dół, na numerze sekwencji |
| inne | rząd ±1, przekątna | 8 | 8 | zapis przesunięty |

Rodziny z największą liczbą przesunięć: `149626 - 177561 cut` (231 kolumn, 78
rzędów), `437742 - 412605 cut` (141 kolumn), `412605 - 387693 cut` (108
kolumn), `177562 -200583 cut` (105 rzędów).

### Rola zdjęć w snapshocie v2

Przesunięcia: 641 + 188 na zdjęciach spoza snapshotu, 76 + 41 na zdjęciach
treningowych, 8 + 2 na `gold`, 2 na development (pierwsza liczba: grupa 727,
druga: grupa 231). 76 błędnych etykiet przesunięcia leżało w zbiorze
treningowym, a sieć i tak ich nie powtórzyła. Na 10 przesunięciach `gold` to
plansze U (zgodnie z raportem V3-C: przesunięte etykiety U).

## Obejrzane przypadki (oględziny, nie tylko miara)

Obejrzałem obrazy `cases\<itemId>.jpg` (czerwony = zapis, zielony = sieć) w
pełnej rozdzielczości lub w zestawieniach po 6:

- **Ranking 1–30:** 28 zapis zły (np. `p00001` −2 kolumny w przerwę,
  `p00002` przekątna obok dłoni, `p00005` zapis o rząd w górę i większy,
  `p00011` kolumna w prawo na zielone tło, `p00019` rząd w dół na numer
  `198505`, `p00026` przekrzywiony o rząd w dół), 2 sieć zła (`p00020`,
  `p00028` — sieć na prawej górnej planszy przesunięta w lewo).
- **Próbki grup przesunięć (77):** (0, 2) kolumna +1 — 12/12 sieć zła; (0, 2)
  kolumna −1 — 12/12 zapis zły; (1, 0) kolumna +1 — 6/6 zapis zły; (1, 2)
  kolumna −1 — 6/6 i +1 — 5/5 zapis zły; rzędy (0, 0), (0, 1), (0, 2) — 18/18
  zapis zły; grupy rzadkie (`p00046`, `p00060`, `p00132`, `p00397`,
  `p00035`, `p00308`, `p00625`, `p00863`, `p00805`, `p00809`, `p00865`,
  `p00829`, `p01000`, `p00382`, `p00076`, `p00270`, `p00186`, `p00040`) —
  18/18 zapis zły.
- **`scale_rotation` NME > 0,05 (12 losowych, poza 5 z rankingu 1–30):** 10 zapis zły (przekrzywienie,
  przesunięcie o pół rzędu/kolumny, np. `p01022`, `p01094`, `p00934`,
  `p00053`), 2 niejasne (`p01050`, `p01056` — niewielki obrót, sieć lepsza,
  ale wycinki mogą być akceptowalne).
- **`nearTolerance` (6, `p01131`–`p01137`):** różnice ułamka komórki; nie
  uznaję za błąd.
- **`saved_only` (5):** `s00003`, `s00004`, `s00005` — sieć nie wykryła
  planszy (rozmycie, niebieski ekran), zapis dobry; `s00001` — zapis
  przesunięty w lewo i sieć bez planszy; `s00002` — niejasne.
- **`network_only` (6 z 28):** plansze bez żywej planszy w zapisie (zdjęcia z
  1–8 żywymi planszami przy 9 oczekiwanych); `n00024` — plansza na krawędzi
  zdjęcia z 9 planszami.

Łącznie obejrzane 136 pozycji: **potwierdzony błąd zapisu 104** (89
przesunięć, 14 `scale_rotation`, `s00001`), błąd sieci 17 (13 przesunięć,
`p00028`, 3 `saved_only` jako plansze zgubione przez sieć), niejasne lub
drobne 9, `network_only` bez złej siatki 6. Pozostałe ok. 1 100 obrazów nie zostały obejrzane
pojedynczo — oszacowania dla grup opierają się na próbkach.

## Przegląd przez operatora

- Strona: **`http://127.0.0.1:8107/`** (uruchomiona, pętla zwrotna). Klawisze
  `1` sieć ma rację (zapis zły), `2` zapis ma rację, `3` nie wiem, `←`/`→`,
  `U` cofnij; filtr klasy. Każda ocena trafia do
  `review\history.jsonl` (fsync) i `review\decisions.json`; podsumowanie:
  `python -m game_predictor_worker.vision_lab.silent_grid_review report --audit <katalog>`.
- Uruchomienie po restarcie:

  ```powershell
  $env:PYTHONPATH = 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src'
  & 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe' -m game_predictor_worker.vision_lab.silent_grid_review serve `
    --audit 'C:\Users\tuszy\Documents\game_predictor_vision_data\silent-grid-audit\777-20261004' --port 8107
  ```

- Strona zawiera 1 233 pozycje: 1 200 najwyższych z rankingu (wszystkie 958
  przesunięć i wszystkie 154 `scale_rotation` z NME > 0,05, reszta to
  rozbieżności 0,04–0,05 i najwyższe `nearTolerance`), 5 `saved_only` i 28
  `network_only`. Pełna lista (3 634 pozycji z identyfikatorami) jest w
  `suspects.json`.
- **Korekta:** istniejące narzędzia nie przyjmują identyfikatora planszy w
  adresie. Droga dla planszy z listy: w Adminie, w Weryfikacji symboli, oznacz
  dowolną komórkę planszy „Zła siatka” (identyfikator bieżącej komórki podaje
  pole `gridIssueCellReviewId`, numer sekwencji i pozycja są w pozycji
  listy); plansza trafia wtedy do kolejki „Korekta cięcia siatki” w lokalnym
  Reviewerze (`http://127.0.0.1:3001/?mode=local&gameId=bfc4f949-5c14-4850-b02a-db99610bcfa5&importJobId=<importJobId>`,
  link na stronie przeglądu; ten sam ekran otwiera Admin, sekcja „Korekta
  cięcia siatki”). Zapis korekty unieważnia wycinki zmienionych pól i cofa je
  do Weryfikacji symboli (D-462, D-488). Pozycje grupy (0, 2) kolumna +1 to
  błędy sieci — nie poprawiać.

## Ograniczenia

- Wynik zależy od jednej sieci (run 1). Sieć ma systematyczny błąd na prawej
  górnej planszy przy ciemnej skrajnej kolumnie (231 przypadków), więc
  „rozbieżność” nie jest dowodem błędu zapisu — dlatego grupy rozdzielono po
  oględzinach.
- Audyt nie widzi błędów, które sieć i zapis popełniają tak samo (przesunięcie
  w tę samą stronę). 76 błędnych etykiet z treningu pokazuje, że sieć nie
  odtwarza przesunięć z danych uczących, ale nie wyklucza błędów wspólnych.
- Oszacowanie liczby błędów pochodzi z próbek (102 przesunięcia i 17 dużych
  `scale_rotation` obejrzanych), nie z
  przeglądu każdej pozycji.
- Zdjęcia roli `gold` snapshotu v2 (sealed holdout V3-C) weszły do audytu jako
  zwykłe dane produkcyjne z eksportu (59 pozycji, głównie plansze U i
  zastąpione pozycje); audyt nie służy do wyboru modelu ani progów i nie
  zmienia rejestru jednorazowych odczytów.
- `network_only` (27/28) wskazuje zdjęcia `geometry_complete` z mniejszą
  liczbą żywych plansz niż oczekiwana (pozycje zastąpione, D-485) — poza
  zakresem tego audytu.

## Pliki wyników

Katalog `C:\Users\tuszy\Documents\game_predictor_vision_data\silent-grid-audit\777-20261004\`:

- `geometry\` — eksport tylko do odczytu (`candidates.jsonl`, `report.json`,
  `export_manifest.json`, `image_ids.txt`), `export.log`;
- `saved.jsonl`, `network-0-of-2.jsonl`, `network-1-of-2.jsonl`,
  `network-identity.json`, `infer-status-*-of-2.json`, `parity.json`;
- `boards.jsonl` (każda plansza poza tolerancją i każda `network_only`, z
  węzłami obu siatek), `summary.json`, `suspects.json` (ranking z
  identyfikatorami korekty), `suspect-board-ids.txt`, `suspect-cells.tsv`;
- `cases\` (1 233 obrazy), `cases.json`, `review\` (oceny operatora).

## Odtworzenie

```powershell
$env:PYTHONPATH = 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src'
$py = 'C:\Users\tuszy\Documents\game_predicotr\.venv-vision-lab\Scripts\python.exe'
$a = 'C:\Users\tuszy\Documents\game_predictor_vision_data\silent-grid-audit\777-20261004'
$m = 'game_predictor_worker.vision_lab.silent_grid_audit'
# eksport tylko do odczytu (główne środowisko, PYTHONPATH z services\api\src)
.\.venv\Scripts\python.exe scripts\vision_lab_geometry_export.py --output-root $a --export-id geometry --workers 2
& $py -m $m saved --audit $a --candidates "$a\geometry\candidates.jsonl"
& $py -m $m infer --audit $a --artifact-root .\artifacts --runner torch-cuda --shard 0 --shards 2   # i --shard 1
& $py -m $m parity --audit $a --artifact-root .\artifacts --photos 24
& $py -m $m compare --audit $a
& $py -m $m render --audit $a --artifact-root .\artifacts --top 1200 --saved-only 5 --network-only 28
& $py -m $m board-ids --audit $a   # potem zapytanie tylko do odczytu o komórki -> suspect-cells.tsv
& $py -m $m refs --audit $a --tsv "$a\suspect-cells.tsv"
```
