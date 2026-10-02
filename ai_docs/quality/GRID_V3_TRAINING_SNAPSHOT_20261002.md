---
title: Snapshot treningowy geometrii produkcyjnej 777 i próbka przeglądu etykiet (TASK-0801)
status: accepted
last_updated: 2026-10-02
---

# Snapshot treningowy geometrii produkcyjnej 777 (TASK-0801)

## Cel i wynik

Raport opisuje zamrożony snapshot treningowy zbudowany jednorazowo z manifestu
kandydatów TASK-0800 (`production-geometry-777-20261002`, `candidates.jsonl`,
SHA-256 `0efe2a6a637f73515df9577b1fbaf8adf14b71242bf159cd10e88994cf1cfacd`,
499 460 wierszy, 55 499 zdjęć) według polityki podziału
`production-geometry-split-v1`, ziarno 801, oraz próbkę 600 plansz do przeglądu
etykiet przez operatora. Baza danych nie była czytana ani zapisywana; pliki zdjęć
czytano tylko do odczytu z `C:\Users\tuszy\Documents\game_predicotr\artifacts\data`.

- Snapshot: `C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry-snapshots\3ff448c620a71f3a28e467cfdfeb77c7e46325e73ca25eaabcb35a56e0b7727d\`
  (6 707 plików, 1 826 221 577 B; obrazy 1 727 878 802 B na 6 700 unikalnych SHA,
  `samples.jsonl` 96 MB).
- Format `production-geometry-snapshot-v1`: `images/<sha[:2]>/<sha>.jpg` (kopie bajt
  w bajt), `samples.jsonl`, `split.json`, `report.json`, `exclusions.jsonl`,
  `checks/visual-*.jpg`, `manifest.json` (SHA-256 każdego pliku i ID snapshotu).
- Próbka przeglądu: `C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry-snapshots\label-review-seed801\`
  (`sample.json` + 600 wycinków, 50,6 MB; `sampleId`
  `e25c5bee7d40dfc441cea5184373e5308a95793b5f236a9b86991e9b438d2121`). Decyzji
  operatora jeszcze nie ma — ocena należy do STOP V3-A.
- Czas budowy: 320,5 s (skan 26,2 s, plan z kontrolą SHA i dekodowaniem 54,3 s,
  odczyt wierszy 20,1 s, kopia i metryki 151,5 s). Przygotowanie próbki: 70,2 s.

Istniejący format `vision-lab-folder-v1` nie pomieści siatek produkcyjnych (nie ma
geometrii, ról ani podziału, a jego kontrola inwentarza dopuszcza tylko obrazy),
więc snapshot ma nowy wersjonowany schemat. Wzorzec publikacji jest ten sam co w
T01/T02 (`snapshot.py`): katalog tymczasowy, `fsync` plików, weryfikacja checksum,
jedna zmiana nazwy, ponowienie weryfikuje zamiast nadpisywać; ID snapshotu to
SHA-256 kanonicznej konfiguracji polityki, wejścia, definicji kontrastu i listy
`[zdjęcie, rola, SHA, rozszerzenie]`.

## Filtr zgodności symboli (próg zapisany w manifeście: 0,80)

Plansza przechodzi, gdy nie ma komórki bez decyzji człowieka z jakością predykcji
≤ 0,80 (`cellsBelowFilter == 0`). Zdjęcie przechodzi, gdy przechodzą wszystkie jego
plansze, liczba kandydatów równa się liczbie oczekiwanych plansz, nie ma planszy U,
a wszystkie plansze mają ten sam poziom S albo B. Zdjęcia złote nie są filtrowane.

| Wynik filtra (zdjęcia spoza zbioru złotego) | Zdjęć |
|---|---|
| Przechodzi, poziom S | 12 096 |
| Przechodzi, poziom B | 37 631 |
| Odrzucone: `SYMBOL_FILTER_BELOW_THRESHOLD` | 5 669 (S 3 177, B 2 492) |
| Odrzucone: `INCOMPLETE_BOARD_SET` | 1 (S) |
| Odrzucone: `UNCLASSIFIED_BOARD`, `MIXED_LABEL_LEVELS`, `INVALID_GEOMETRY_ROW` | 0 |

Każde odrzucone zdjęcie ma jeden powód (brak nakładania się powodów). Wszystkie
76 zdjęć z planszami U zawiera też plansze G, więc trafiły do zbioru złotego, nie do
odrzuceń.

## Podział `production-geometry-split-v1`

| Rola | Zdjęcia | S | B | G | Plansze |
|---|---|---|---|---|---|
| training | 6 000 | 3 000 | 3 000 | — | 54 000 (27 000 S + 27 000 B) |
| development | 600 | 300 | 300 | — | 5 400 (2 700 S + 2 700 B) |
| gold | 102 | 1 (bliźniak SHA) | — | 101 | 892 (459 G, 425 U, 8 S) |

- Wykluczenia integralności (brak pliku, inne SHA, błąd dekodowania, inny rozmiar po
  orientacji EXIF): **0**; `exclusions.jsonl` jest pusty. Ścieżki wykluczeń pokrywają
  testy.
- Rodziny developmentu (wybrane w kolejności z ziarna, aż pula po filtrze dała ≥ 300 S
  i ≥ 300 B): `c0932585` „379243- 352090 cut” (pula S 188 / B 2 781), `c4c066f8`
  „272017 - 275841 cut” (72 / 341), `c2547b09` „70363 - 93861 cut” (782 / 1 724).
  Rodzin trenujących: 21. 24 rodziny = 24 grupy (importy `7d10ae0a` i `f4ef3449` mają
  wspólny katalog, więc są jedną rodziną `9c7de0ca`; poza zbiorem złotym nie ma SHA
  łączącego rodziny).
- Limit udziału rodziny: 25% na poziom (750 z 3 000), więc ≤ 25% całego treningu.
  Limit nie zadziałał: największy udział ma `ef4be7d3` „149626 - 177561 cut”, 524
  zdjęcia = 8,73%.
- Trudność: kwantyle (tercyle) globalne po zdjęciach przechodzących filtr —
  skośność = największe odchylenie kąta narożnika od 90° spośród plansz zdjęcia
  (krawędzie 9,751° i 11,372°), skala = dolna mediana pola quada jako ułamek zdjęcia
  (0,01704 i 0,01881). Warstwa = rodzina × (tercyl skośności, tercyl skali); przydział
  proporcjonalny do dostępności (największe reszty), w warstwie kolejność
  `sha256(ziarno|cel|id)`.
- Braki warstw: 0 (`shortfalls` puste); każda warstwa miała dość zdjęć.

Liczba zdjęć według przedziału trudności (`skew0-area0` … `skew2-area2`):

| Rola / poziom | s0a0 | s0a1 | s0a2 | s1a0 | s1a1 | s1a2 | s2a0 | s2a1 | s2a2 |
|---|---|---|---|---|---|---|---|---|---|
| training S | 222 | 175 | 288 | 456 | 155 | 184 | 1 030 | 270 | 220 |
| training B | 125 | 428 | 555 | 222 | 367 | 400 | 562 | 167 | 174 |
| development S | 4 | 30 | 18 | 6 | 60 | 97 | 3 | 23 | 59 |
| development B | 7 | 68 | 38 | 7 | 110 | 20 | 4 | 38 | 8 |

Liczba zdjęć według rodziny (S/B treningu, S/B developmentu, zdjęcia złote):

| Rodzina (fragment nagrania) | ID | tr S | tr B | dev S | dev B | gold |
|---|---|---|---|---|---|---|
| 1-19809 cut | `0dbd07df` | 78 | 164 | 0 | 0 | 49 |
| 117829 - 128268 cut | `9c7de0ca` | 41 | 87 | 0 | 0 | 4 |
| 128269 - 149634 cut | `bafbe14a` | 382 | 67 | 0 | 0 | 1 |
| 149626 - 177561 cut | `ef4be7d3` | 459 | 65 | 0 | 0 | 19 |
| 177562 -200583 cut | `b69d4040` | 211 | 144 | 0 | 0 | 4 |
| 19810 - 45162 cut | `e22ca053` | 73 | 216 | 0 | 0 | 4 |
| 200575 - 222912 cut | `239e6fd6` | 84 | 188 | 0 | 0 | 2 |
| 222913 - 248184 cut | `45f84292` | 129 | 178 | 0 | 0 | 6 |
| 248176 - 272016 cut | `05d1b599` | 155 | 176 | 0 | 0 | 2 |
| 272017 - 275841 cut | `c4c066f8` | 0 | 0 | 21 | 21 | 0 |
| 302257 - 275698 cut (ponowne przetworzenie) | `a139379b` | 56 | 237 | 0 | 0 | 0 |
| 326980 - 302257 cut | `3e3f510a` | 44 | 230 | 0 | 0 | 0 |
| 352090 - 326980 cut | `ccf38bd4` | 51 | 232 | 0 | 0 | 0 |
| 379243- 352090 cut | `c0932585` | 0 | 0 | 54 | 172 | 0 |
| 387684 - 379242 cut | `a219649a` | 9 | 79 | 0 | 0 | 0 |
| 412605 - 387693 cut | `5eafd373` | 323 | 74 | 0 | 0 | 2 |
| 437742 - 412605 cut | `a0f63bd9` | 297 | 82 | 0 | 0 | 0 |
| 45163 - 70371 cut | `0935f4ba` | 175 | 178 | 0 | 0 | 6 |
| 453744 - 437743 cut | `d580af96` | 129 | 69 | 0 | 0 | 0 |
| 477054 - 453753 cut | `02f69f96` | 115 | 177 | 0 | 0 | 0 |
| 500000 - 477063 cut | `dd693718` | 106 | 160 | 0 | 0 | 1 |
| 70363 - 93861 cut | `c2547b09` | 0 | 0 | 225 | 107 | 0 |
| 93853 -117828 cut | `97f16dfb` | 82 | 197 | 0 | 0 | 0 |
| missing cut (kontynuacja z ręczną korektą) | `299e7c72` | 1 | 0 | 0 | 0 | 2 |

### Zbiór złoty

- 102 zdjęcia: 101 z co najmniej jedną planszą G (459 plansz G — jedyne cele oceny,
  `evaluationTarget = true`) i 1 zdjęcie `84d27063…` z 8 planszami S, które ma ten sam
  SHA co zdjęcie złote `41dab52a…` (`goldBasis = sha_twin_of_gold`, bez celów oceny).
  Druga para SHA (`206645fa…`, `f7b4a70a…`) jest w całości złota. 425 plansz U i 8 S
  jest zapisanych jako „bez etykiety oceny”.
- **Wszystkie 102 zdjęcia złote (459 plansz G) leżą w rodzinach widzianych w
  treningu** (`familySeenInTraining = true`): wylosowane rodziny developmentu nie
  zawierają żadnego zdjęcia G. Podzbiór „rodzina niewidziana w treningu” jest więc
  pusty; TASK-0804 nie może raportować osobno złota z rodzin niewidzianych bez zmiany
  wyboru rodzin (decyzja operatora, np. inne ziarno albo reguła wymuszająca rodzinę
  z G w developmencie).

### Rozłączność i determinizm

- Kontrola w kodzie przed publikacją (`assert_disjoint`) i niezależny skrypt na
  opublikowanym `samples.jsonl`: 0 wspólnych zdjęć między rolami, 0 wspólnych SHA
  development/trening, 0 SHA złotych w treningu lub developmencie, 0 wspólnych grup
  rodzin development/trening, 0 zdjęć treningu/developmentu łamiących filtr lub
  regułę jednostki (każde ma 9 plansz jednego poziomu S albo B, każda z
  `cellsBelowFilter = 0`).
- Numery sekwencji: każdy z 499 460 numerów występuje na jednym zdjęciu, więc między
  rodzinami nie ma powiązań przez ten sam układ.
- Determinizm: podgląd przed budową i budowa dały ten sam ID
  `3ff448c6…727d`; test jednostkowy buduje snapshot dwa razy w różnych katalogach i
  porównuje bajty `manifest.json`; ponowne uruchomienie budowy weryfikuje istniejący
  katalog i nie zmienia żadnego pliku (test porównuje czasy modyfikacji i treść).
  `verify_snapshot` na opublikowanym katalogu: 6 706 sum kontrolnych zgodnych (9,4 s).

## Orientacja EXIF i kontrola wizualna

Węzły są w przestrzeni `exif-normalized-rgb-pixels-v1`; obrazy są kopiowane w
orientacji zapisanej w źródle, a `samples.jsonl` zapisuje `exifOrientation`. Kontrola
integralności porównuje rozmiar po `ImageOps.exif_transpose` z `orientedWidth` /
`orientedHeight` manifestu (0 niezgodności). Wszystkie 6 702 zdjęcia mają orientację 1;
ścieżkę orientacji 6 (obrót, zachowanie bajtów, wykrycie niezgodnego rozmiaru)
sprawdza test na syntetycznym JPEG. Test na rzeczywistych plikach
(`VISION_LAB_PRODUCTION_SNAPSHOT=<snapshot>`) przeszedł dla 25 zdjęć: SHA, orientacja,
rozmiar i węzły w granicach obrazu. Kontrola wizualna: `checks/visual-training.jpg`
(zdjęcie treningowe, 9 siatek) i `checks/visual-gold.jpg` (zdjęcie złote) — wszystkie
siatki 5 × 3 leżą na planszach, linie przechodzą między symbolami. Węzłów poza obrazem
w snapshocie: 0.

## Metryka „niski kontrast”

`rmsContrast` = odchylenie standardowe (populacyjne) 8-bitowej luminancji (PIL `L`,
ITU-R 601-2) zorientowanego zdjęcia wewnątrz wielokąta quada planszy, podzielone przez
255; dodatkowo `imageRmsContrast` całego zdjęcia. `lowContrast` = `rmsContrast` poniżej
10. percentyla (dolna statystyka pozycyjna) wszystkich plansz treningu i developmentu
snapshotu: próg 0,133142. Plansze z `lowContrast`: trening 5 428, development 512,
złoto 94.

## Przegląd etykiet (600 plansz)

- Populacja: zdjęcia przechodzące filtr z całego manifestu (S 12 096, B 37 631), bez
  zdjęć złotych i ich bliźniaków SHA. Próbka: 300 zdjęć S i 300 B w kolejności
  `sha256(801|label-review|poziom|id)`, po jednej planszy na zdjęcie (wybór planszy
  z ziarna). Kolejność wyświetlania miesza oba poziomy; strona nie pokazuje poziomu
  (przegląd ślepy). Wykluczenia integralności w próbce: 0.
- Wycinek: plansza z marginesem 25% dłuższego boku, dłuższy bok przeskalowany do
  960 px (LANCZOS); siatkę 5 × 3 rysuje strona (klawisz `H` ją ukrywa).
- Narzędzie jest samodzielne (`vision_lab/label_review.py`), bo istniejący przegląd
  zdjęć T03d działa na stanie anotacji labu (źródła snapshotu folderu, anotacje,
  zaakceptowane rewizje plansz); pokazanie w nim siatek produkcyjnych wymagałoby
  przebudowy modelu danych labu. Serwer słucha wyłącznie na `127.0.0.1:8103`,
  sprawdza nagłówki `Host`/`Origin`, zapis wymaga JSON i własnego `Origin`.
- Zapis: `history.jsonl` (dopisywanie z `fsync`, źródło prawdy; urwana ostatnia linia
  jest odrzucana przy starcie) i `decisions.json` (zapis atomowy); kontrola rewizji
  odrzuca zapis z nieaktualnej karty (409).
- Raport: `summary.json` — odsetek „zła” = zła / (dobra + zła) per poziom z
  przedziałem Wilsona 95%; „nie da się ocenić” i brak decyzji są liczone osobno.
- Sprawdzenie end-to-end (2026-10-02): strona otwarta w przeglądarce, klawisz `Z`
  zapisał decyzję „zła” dla pozycji 0001 (rewizja 1), `←` i `U` ją cofnęły
  (rewizja 2); po zatrzymaniu serwera `report` odtworzył stan z historii (rewizja 2,
  0 decyzji). Pliki testowe (`history.jsonl`, `decisions.json`, `summary.json`)
  usunięto; katalog zawiera tylko `sample.json` i `crops/`.

## Ryzyka i ograniczenia

- Rodzina to fragment („cut”) jednego długiego nagrania; sąsiednie fragmenty
  (np. development „379243- 352090” i trening „352090 - 326980”) dzielą moment
  przejścia, więc ich brzegi są wizualnie podobne mimo rozłącznych SHA i numerów
  sekwencji.
- Złoto w całości leży w rodzinach treningu (patrz wyżej); poziom G jest niejednorodny
  (261 z 459 plansz to podstawa `human_saved_revision_via_legacy_conversion`).
- Etykiety S i B mogą powielać błędy reweryfikacji i silnika; o przydatności
  rozstrzyga przegląd 600 plansz (STOP V3-A).
- Metryka niskiego kontrastu jest względna (percentyl snapshotu), nie absolutna.

## Weryfikacja

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "production_split or production_snapshot or label_review or no_production_storage_imports"
.\.venv\Scripts\python.exe -m ruff check services scripts
$env:VISION_LAB_PRODUCTION_SNAPSHOT = 'C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry-snapshots\3ff448c620a71f3a28e467cfdfeb77c7e46325e73ca25eaabcb35a56e0b7727d'
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_lab_production_snapshot.py -q -p no:cacheprovider -k real_files
```

Wyniki: 37 passed, 1 skipped (test rzeczywistych plików bez zmiennej; z nią 1 passed);
selekcja obejmuje też istniejący `test_production_snapshot.py` aplikacji mobilnej i
test izolacji labu. `ruff check` zgłasza tylko wcześniejsze E501 w
`services/worker/tests/test_page_geometry_preflight.py` (poza zakresem). `mypy --strict`
na nowych modułach i skrypcie: brak błędów.
