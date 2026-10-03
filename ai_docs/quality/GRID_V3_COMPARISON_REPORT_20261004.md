---
title: TASK-0804 — V3-C, raport porównawczy silników siatek 5 × 3 i rekomendacja
status: accepted
last_updated: 2026-10-04
---

# Raport porównawczy silników siatek V3 (TASK-0804, STOP V3-C)

## Wynik w skrócie

- **Sieć `neural_grid` jest wyraźnie lepsza od pierwotnego wyniku silnika
  produkcyjnego tam, gdzie produkcja zawodzi**: na zbiorze złotym 777 sieć ma
  96,5–97,2% poprawnych plansz G, produkcja 41,4% (produkcja nie zwraca
  siatki dla 269 z 459 plansz G; żadna zwrócona przez nią plansza G nie jest
  błędna). Na zdjęciach S developmentu (zdjęcia, które produkcja oznaczyła do
  przeglądu) sieć daje 82–85% zdjęć kompletnych i poprawnych, produkcja 0%.
- **Błędy sieci są „tuż za tolerancją”**: wszystkie 17 błędnych plansz G
  (suma po trzech modelach) ma NME 0,016–0,026 przy maks. błędzie węzła
  ≤ 0,05; 16 z 17 leży w skrajnej kolumnie strony. Fałszywe plansze sieci na
  `gold` (3–4) to w całości błędy etykiet U (przeskok o rząd odziedziczony z
  wyniku produkcji).
- **`hybrid_v3` z odniesieniem = pierwotny wynik produkcji jest bezpieczny, ale
  nie zwiększa pokrycia**: 0 błędnych plansz `confident` (development 0 / 5 054,
  `gold` 0 / 190), lecz zdjęcia `confident` to podzbiór zdjęć, które produkcja
  sama zaakceptowała (development 294 z 300, `gold` 14 z 14). Na zdjęciach S
  pokrycie wynosi 0 / 298.
- **Holdouty innych gier** (częściowe siatki labu): Reels 29/30 plansz
  poprawnych dla każdego modelu, Treasure 30/30; zdjęcie kompletne i fałszywe
  plansze nie są tam mierzalne. Holdout Mumii: 36/36 dla wszystkich modeli,
  model po iteracji 3 ma niższy błąd węzłów (NME mediana 0,0029 wobec 0,0067).
- **Rekomendacja: promować do trybu shadow (V3-D, TASK-0805) z modelem runu 1
  i z ograniczeniami** opisanymi w sekcji „Rekomendacja”, równolegle zebrać
  dane z listy braków.

## Zamrożenie przed odczytem holdoutów

Tabelę zapisano w tym raporcie **przed** pierwszym odczytem `gold`, Reels
(`final_test`), Treasure (`unseen_game`) i holdoutu Mumii. Po odczycie nie
zmieniono modeli, progów ani metryki; żaden wybór modelu nie korzysta z
wyników holdoutów.

| Silnik | Tożsamość (zamrożona) |
|---|---|
| produkcja (`structured_opencv_v1`, wynik pierwotny) | `production-geometry\production-originals-777-20261004\production-originals.jsonl`, SHA-256 `5db76167…99e32eb` |
| `neural_grid` run 1 (preset A) | run `43933ac8…e2e6`, runda 3, eksport `exports\2cd19738367121e6-round3`, wagi `19b8d138…80f9` |
| `neural_grid` run 2 (preset B) | run `ff03b1d7…f31d`, runda 9, eksport `exports\d623eebfc876c7f3-round9` (TASK-0804), wagi `619b33de…7b262` |
| `neural_grid` iteracja 3 (doszkalanie na Mumiach, D-490) | run `5bc98156…aedc`, eksport `exports\iteration03-f896da7196431be2`, wagi `473d7738…613a1` |
| `hybrid_v3` | bramka `hybrid-v3-gate-v1`; sieć = run 1; odniesienie = pierwotny wynik produkcji; progi `RUN1_DEVELOPMENT_THRESHOLDS` z TASK-0803 (IoU 0,90; węzły 0,04; reszta 0,005), bez ponownej kalibracji |

Metryka: `neural-grid-metrics-v1` (D-483, kod bez zmian). Inferencja sieci:
ONNX Runtime `CPUExecutionProvider`, 4 wątki. Przedziały: Wilson 95% dla
odsetków, bootstrap po zdjęciach (2 000 losowań, ziarno 804) dla image-macro
i kwantyli NME.

### Rejestr jednorazowych odczytów

Holdouty czyta wyłącznie `grid_v3_sealed read --confirm-single-read`. Odczyt
jest zapisywany w `grid-v3-comparison\sealed\ledger.json` **przed** otwarciem
etykiet; drugi odczyt tego samego holdoutu którymkolwiek z tych samych modeli
jest odrzucany (`GRID_V3_SEALED_READ_REPEATED`, także po awarii), chyba że
podano `--force-reason` (zapisywany). Stan rejestru (SHA-256
`a347b352…e2da67`):

| Odczyt | Holdout | Status | Wymuszony |
|---|---|---|---|
| `gold-001` | `gold` (snapshot v2) | completed | nie |
| `final_test-002` | Reels (D-456) | completed | nie |
| `unseen_game-003` | Treasure (D-456) | completed | nie |
| `mumie_holdout-004` | 4 zdjęcia holdoutu Mumii (D-490) | completed | nie |
| `gold-001-inspection-005` | `gold` — tylko rysunki przeglądowe z zapisanych wyników odczytu 001, bez inferencji i bez przeliczania metryk (taksonomia) | inspected | — |

Każdy holdout został przeliczony przez zamrożone modele dokładnie raz;
progi `hybrid_v3` nie były kalibrowane po odczycie. Przed odczytem cały
potok (ładowanie, ocena, rysunki) przećwiczono komendą `rehearse` na
danych nieodłożonych (development v2, partycja development D-456, zdjęcia
treningowe Mumii).

Strażnik treningu i kalibracji (`require_roles`) nadal odrzuca `gold`,
`final_test`, `unseen_game`; moduły treningu, kalibracji, doszkalania i
porównania nie importują modułu odczytu (test `ast`).

## Pierwotny wynik silnika produkcyjnego (zakres 2)

Eksporter TASK-0800 (`scripts/vision_lab_geometry_export.py
--production-originals-for <snapshot>`) zapisał dla zdjęć ról `development` i
`gold` snapshotu v2 ostatnią automatyczną rewizję geometrii źródła
`structured_opencv_v1` sprzed pierwszej rewizji ręcznej, z 24 węzłami każdej
planszy (`symbolGridQuad` → siatka projekcyjna, ta sama funkcja co renderer).
Odczyt: krótkie transakcje `REPEATABLE READ READ ONLY`
(`transaction_read_only = on`), 3,0 s, head `0139`. Baza nie była zapisywana.

| Rola | Zdjęć | Z pierwotnym wynikiem | Status pierwotnej rewizji | Plansz bez siatki |
|---|---|---|---|---|
| development | 600 | 598 | 300 `accepted` (B, rewizja bieżąca), 298 `needs_review` (S, zastąpione rewizją 1 reweryfikacji) | 318 (na wszystkich 298 zdjęciach S) |
| gold | 102 | 102 | 14 `accepted` (7 bieżących, 7 zastąpionych), 88 `needs_review` | 274 z 918 wpisów |

- Bez pierwotnego wyniku (`PRODUCTION_ORIGINAL_NO_AUTOMATIC_REVISION`): 2 zdjęcia
  development — `1486c4a9-b8f7-4e8f-9293-6ff4c49a1c9c` i
  `b1ad0d0b-2026-4305-bfd7-092ae615c30c`; jedyna rewizja to `manual_v1`
  `manual-source-geometry-required-v1` utworzona przez
  `system:image-pipeline-v0.10` (silnik nie dał automatycznej geometrii).
  Produkcja i `hybrid_v3` są na development mierzone na 598 zdjęciach; sieci na
  600 (tabela „na zdjęciach z wynikiem produkcji” poniżej daje porównanie na
  tych samych 598).
- Kontrola niezależna: 2 763 plansze mają manifest renderu wycięty z pierwotnej
  rewizji przy rewizji planszy 0; węzły odtwarzają go z odchyłką 0,0 px.
- `processing_time_ms` pierwotnych rewizji jest pusty dla wszystkich 700 —
  czasu produkcji nie da się podać z danych.

## Development (600 zdjęć, D-483) — zbiór wyboru modeli i kalibracji bramki

**Development nie jest niezależnym pomiarem**: wybierano na nim rundy runów
1–3 i progi `hybrid_v3`. Etykiety B = wynik produkcji (produkcja ma na B 100%
z definicji), etykiety S = korekta reweryfikacji.

| Silnik | Zdjęć | Kompletne i poprawne | Image-macro | Odzysk plansz | NME med. / p95 | Fałszywe |
|---|---|---|---|---|---|---|
| produkcja (pierwotny) | 598 | 300 = 50,2% [46,2–54,2] | 0,0598 [0,0549–0,0647] | 5 064 / 5 382 = 94,1% [93,4–94,7] | 0,0000 / 0,0024 | 0 |
| run 1 | 600 | 554 = 92,3% [89,9–94,2] | 0,0029 [0,0027–0,0030] | 5 349 / 5 400 = 99,1% [98,8–99,3] | 0,0020 / 0,0086 | 0 |
| run 2 | 600 | 553 = 92,2% [89,7–94,1] | 0,0027 [0,0025–0,0028] | 5 347 / 5 400 = 99,0% [98,7–99,3] | 0,0018 / 0,0086 | 0 |
| iteracja 3 | 600 | 546 = 91,0% [88,4–93,0] | 0,0028 [0,0026–0,0029] | 5 341 / 5 400 = 98,9% [98,6–99,2] | 0,0019 / 0,0088 | 0 |
| `hybrid_v3` (siatki wyjściowe) | 598 | 556 = 93,0% [90,6–94,8] | 0,0028 [0,0027–0,0029] | 5 335 / 5 382 = 99,1% [98,8–99,3] | 0,0020 / 0,0080 | 0 |

| Poziom | produkcja | run 1 | run 2 | iteracja 3 |
|---|---|---|---|---|
| B: kompletne i poprawne | 300/300 (z definicji) | 298/300 | 300/300 | 299/300 |
| S: kompletne i poprawne | 0/298 [0–1,3%] | 256/300 = 85,3% [80,9–88,9] | 253/300 = 84,3% | 247/300 = 82,3% |
| S: odzysk plansz | 2 364 / 2 682 = 88,1% (318 plansz bez siatki; każda zwrócona plansza poprawna) | 98,2% | 98,0% | 97,9% |

Na tych samych 598 zdjęciach (z wynikiem produkcji) run 1 ma 552 = 92,3%,
run 2 551, iteracja 3 544. Wyniki ONNX CPU zgadzają się z ewaluacjami GPU
(run 1: 554/600 jak w TASK-0802; run 2: 553/600 = 92,17%, `evaluate` z
TASK-0804).

**Bramka `hybrid_v3` na development (realny tryb shadow):**

| | Zdjęcia `confident` | Plansze `confident` błędne | Zdjęcia `confident` z błędną planszą |
|---|---|---|---|
| razem | 294 / 598 = 49,2% [45,2–53,2] | 0 / 5 054 [0–0,08%] | 0 / 294 [0–1,3%] |
| B | 294 / 300 = 98,0% | 0 / 2 694 | 0 |
| S | 0 / 298 [0–1,3%] | — | — |

Wszystkie 294 zdjęcia `confident` należą do 300 zdjęć, które produkcja sama
zaakceptowała. Powody na S: każda plansza bez siatki produkcji daje
`HYBRID_V3_REFERENCE_ONLY` + `HYBRID_V3_NETWORK_ONLY` (318 plansz), więc
zdjęcie S nigdy nie jest `confident`. W TASK-0803 (odniesienie = etykieta-korekta)
pokrycie S wynosiło 82,7% — przy odniesieniu = pierwotny wynik produkcji
spada do 0%.

## Zbiór złoty 777 (`gold`, odczyt `gold-001`)

101 zdjęć z co najmniej jedną planszą G (459 plansz G = jedyne oceniane);
plansze U tych zdjęć (425) są znane, ale nieoceniane — predykcja na planszy U nie jest
ani punktowana, ani fałszywa. Zdjęcie bliźniacze SHA bez planszy G nie jest
oceniane. Miara „zdjęcie kompletne” tylko na **22 zdjęciach, w których
wszystkie plansze są G** (wszystkie w rodzinach niewidzianych). Każde zdjęcie
`gold` ma pierwotny wynik produkcji.

| Silnik | Odzysk plansz G | Image-macro | NME med. / p95 | Fałszywe (zdjęcia) | 22 zdjęcia all-G: kompletne i poprawne |
|---|---|---|---|---|---|
| produkcja (pierwotny) | 190 / 459 = 41,4% [37,0–46,0] | 0,7912 [0,7109–0,8648] | 0,0015 / 0,0026 | 0 | 14 / 22 = 63,6% [43,0–80,3] |
| run 1 | 443 / 459 = 96,5% [94,4–97,8] | 0,0113 [0,0103–0,0123] | 0,0087 / 0,0186 | 3 (3) | 21 / 22 = 95,5% [78,2–99,2] |
| run 2 | 443 / 459 = 96,5% [94,4–97,8] | 0,0113 [0,0102–0,0123] | 0,0085 / 0,0186 | 4 (4) | 21 / 22 = 95,5% [78,2–99,2] |
| iteracja 3 | 446 / 459 = 97,2% [95,2–98,3] | 0,0111 [0,0100–0,0121] | 0,0084 / 0,0184 | 3 (3) | 22 / 22 = 100% [85,1–100] |
| `hybrid_v3` (siatki wyjściowe) | 443 / 459 = 96,5% | 0,0113 | 0,0087 / 0,0186 | 3 (3) | 21 / 22 = 95,5% |

| Rodziny | Plansz G | produkcja | run 1 | run 2 | iteracja 3 |
|---|---|---|---|---|---|
| widziane w treningu (50 zdjęć) | 210 | 0 / 210 = 0% [0–1,8] | 199 = 94,8% [90,9–97,1] | 199 = 94,8% | 201 = 95,7% [92,1–97,7] |
| niewidziane (51 zdjęć) | 249 | 190 = 76,3% [70,7–81,2] | 244 = 98,0% [95,4–99,1] | 244 = 98,0% | 245 = 98,4% [95,9–99,4] |

NME mediana sieci: rodziny widziane 0,0114–0,0120, niewidziane 0,0026–0,0028.

**`hybrid_v3` na `gold`:** zdjęcia `confident` 14 / 101 = 13,9% [8,4–21,9]
(widziane 0 / 50, niewidziane 14 / 51 = 27,5%); błędne plansze `confident`
0 / 190 [0–2,0%]; zdjęcia `confident` z błędną planszą 0 / 14 [0–21,5%].
Te 14 zdjęć to dokładnie 14 zdjęć zaakceptowanych przez produkcję (0 z nich ma
błędną planszę G). Powody plansz: `REFERENCE_ONLY` 275, `NETWORK_ONLY` 274,
`BOARD_INVALID` 271, `NODE_DISAGREEMENT` 20, `QUAD_DISAGREEMENT` 10 (część na
planszach U z przeskokiem o rząd — patrz taksonomia).

**Uwaga o stronniczości zbioru złotego (ważne dla odczytu):**

- 261 plansz G (podstawa `human_saved_revision_via_legacy_conversion`, w tym
  wszystkie 210 w rodzinach widzianych) istnieje, **bo produkcja ich nie
  narysowała** — Reviewer dorysował brakujące plansze. Produkcja ma na nich 0%
  z konstrukcji.
- 198 plansz G `human_approval` (22 zdjęcia all-G): produkcja 190 poprawnych,
  8 bez siatki; 63 z nich to zatwierdzony wynik silnika (NME < 0,0001), więc
  produkcja jest tam poprawna z konstrukcji.
- Zbiór złoty nie mierzy więc „jakości produkcji na typowym zdjęciu”, tylko
  zachowanie silników na zdjęciach, które produkcja oddała do przeglądu.

## Holdouty innych gier (D-456) — tylko plansze z etykietą

Etykiety: zamrożony manifest D-456 (`manifests\1e7cc3a7….json`, skrót =
nazwa pliku), obrazy z katalogu labu `0cdc0770…`, porównane z magazynem
anotacji (kopia bajtów pod krótką blokadą, rewizja 481): 30 / 30 siatek
niezmienionych w obu holdoutach, 0 nowych plansz poza manifestem.
**Siatki są częściowe** (3 plansze na zdjęcie, 10 zdjęć), więc miary „zdjęcie
kompletne i poprawne” i „fałszywe plansze” **nie są mierzalne**; mierzone są
odzysk plansz z etykietą, NME i poprawność planszy. Każdy model zwraca 9 plansz
na każdym zdjęciu obu gier. Silnik produkcyjny i `hybrid_v3`: nie mierzone
(dla gier labu nie ma wyniku produkcji; `hybrid_v3` wymaga odniesienia
produkcyjnego).

| Holdout | Model | Plansze poprawne | Image-macro (etykiety) | NME med. / p95 |
|---|---|---|---|---|
| Reels (`final_test`) | run 1 | 29 / 30 = 96,7% [83,3–99,4] | 0,0112 | 0,0120 [0,0095–0,0131] / 0,0169 |
| | run 2 | 29 / 30 = 96,7% [83,3–99,4] | 0,0105 | 0,0108 [0,0088–0,0121] / 0,0164 |
| | iteracja 3 | 29 / 30 = 96,7% [83,3–99,4] | 0,0108 | 0,0111 [0,0094–0,0122] / 0,0166 |
| Treasure (`unseen_game`) | run 1 | 30 / 30 = 100% [88,6–100] | 0,0108 | 0,0108 [0,0100–0,0127] / 0,0157 |
| | run 2 | 30 / 30 = 100% [88,6–100] | 0,0108 | 0,0103 [0,0093–0,0117] / 0,0169 |
| | iteracja 3 | 30 / 30 = 100% [88,6–100] | 0,0101 | 0,0103 [0,0092–0,0109] / 0,0146 |

Jedyna błędna plansza Reels to ta sama plansza dla wszystkich modeli (zdjęcie
`89addd6e…`, plansza 0): NME 0,021–0,025, maks. błąd 0,033–0,038 — tuż za
tolerancją.

**Odniesienie (nie holdout):** te same modele na partycji development D-456
(ręczne siatki labu, 32 zdjęcia, 90 plansz; wynik
`grid-v3-comparison\reference-not-sealed\rehearsal\lab-development`): 777 —
29/30 plansz (NME mediana 0,011–0,012), Blazing 28/30 (0,011–0,012), **Gang
5–7/30** (NME mediana 0,029–0,035). NME ok. 0,011 na ręcznych siatkach labu
występuje też dla 777, więc wyższe NME na Reels/Treasure niż na development 777
(0,002) wynika co najmniej częściowo z konwencji i precyzji siatek labu, a
nie z gry. Gang pokazuje, że „gra niewidziana” nie jest jednorodna.

### Mumie — 4 zdjęcia holdoutu D-490

| Model | Kompletne i poprawne | Plansze | Image-macro | NME med. / p95 |
|---|---|---|---|---|
| run 1 | 4 / 4 [51,0–100] | 36 / 36 | 0,0068 [0,0061–0,0075] | 0,0067 / 0,0111 |
| run 2 | 4 / 4 | 36 / 36 | 0,0073 [0,0067–0,0082] | 0,0071 / 0,0113 |
| iteracja 3 | 4 / 4 | 36 / 36 | 0,0033 [0,0015–0,0051] | 0,0029 / 0,0070 |

Zastrzeżenia: holdout Mumii był używany w runie 3 do wyboru stanu każdej
iteracji (reguła presetu E), a jego siatki powstały z propozycji sieci
poprawianych przez operatora — to nie jest niezależny test modelu po
iteracji 3. Snapshot: `finetune-D\s\51409179…` (rewizja magazynu 481).

## Taksonomia błędów na `gold` (obejrzane)

Obrazy porównawcze: `grid-v3-comparison\sealed\gold\cases\` — 269 wycinków
(każda plansza G, którą którykolwiek silnik ma błędną albo pustą: etykieta
zielona, silnik w swoim kolorze, opis NME/stanu) i
`sealed\gold-001-inspection-005\` — 87 przeglądów całych zdjęć (zielony: G,
żółty: U/S, czerwony: produkcja, błękitny: iteracja 3). Kategorię przypisano
po obejrzeniu; plansza ma jedną kategorię główną.

**A. Plansze G bez siatki produkcji** — obejrzane 76 z 269 na 32 zdjęciach:

| Kategoria | Plansz | Przykłady (przegląd zdjęcia) |
|---|---|---|
| ręka (palec/dłoń na planszy albo przy strzałce `>` planszy 5) | 21 | `2781a2be-772` (5), `4f28a2ed-c87` (5), `ae604e68-2e3` (5), `0c3bb0e9-ecb` (2, rozmyta dłoń zasłania planszę), `f7b4a70a-ae2` (5, 8) |
| skrajna kolumna (krawędź ekranu, strzałka `<` przy planszy 3) | 30 | `206645fa-2a3` (0, 3), `3f891d20-c9c` (3), `42bddc16-ac9` (2, 3), `89b9f3a6-4bb` (3), `100a460e-0c2` (2) |
| niski kontrast / rozmycie (górny rząd na zielonym tle ekranu, rozmycie ruchu) | 17 | `022e6e9a-e29` (0, 1, 2), `1a82ae96-99f` (0, 1, 2), `c8c281df-d41` (0, 1, 2) |
| odblask / podświetlenie | 1 | `546aa0f9-80a` (8, jasna zielona plama) |
| przeskok okresu | 0 | — (produkcja zostawia planszę pustą, nie przesuniętą; przesunięcia — punkt C) |
| plansza częściowa | 0 | — (zbiór złoty nie ma plansz częściowych) |
| błąd etykiety G | 0 | nie stwierdzono |
| brak widocznej przyczyny (środkowa kolumna, zdjęcie z ręką gdzie indziej) | 7 | `02f471c2-1be` (1, 4, 7), `34b29697-4ee` (1) |

Na wszystkich 269 brakach produkcji 212 (78,8%) leży w skrajnej kolumnie strony
(udział skrajnych kolumn wśród wszystkich plansz: 66,7%), najwięcej w prawej
(pozycje 2/5/8: 58/54/39).

**B. Błędne plansze G sieci** — wszystkie 17 (suma po run 1, run 2,
iteracji 3), wycinki `sealed\gold\cases\<zdjęcie>-<etykieta>.jpg`, np.
`02af0783-f23-1`, `3677a990-1c0-0`, `76094768-a5f-0`, `a64c08bc-e7b-2`,
`3f891d20-c9c-3`:

| Kategoria | Plansz | Opis |
|---|---|---|
| precyzja tuż za tolerancją | 17 | dopasowane, NME 0,016–0,026, maks. błąd ≤ 0,05; 16 w skrajnej kolumnie (pozycja 0: 10, 3: 4, 2: 2), 12 w rodzinach widzianych (rozmyte, ciemne nagranie); produkcja nie ma siatki na żadnej z nich; przy tej rozdzielczości nie da się rozstrzygnąć, czy dokładniejsza jest etykieta, czy sieć |
| ręka / odblask / przeskok okresu / plansza częściowa | 0 | sieć nie zgubiła żadnej planszy G (odzysk detekcji 100%) |

**C. Fałszywe plansze sieci = błędy etykiet U** — 4 zdjęcia (`3aa225a9-b41`,
`c7cd13b0-bc5`, `e1c9e85a-9a3`; run 2 dodatkowo `ae604e68-2e3`): etykieta U
planszy górnego rzędu jest **przesunięta o jeden rząd w dół** (obejmuje numer
sekwencji) i pokrywa się z takim samym przesunięciem w pierwotnym wyniku
produkcji; sieć trafia w rzeczywistą planszę, więc metryka liczy ją jako
fałszywą. Takie przesunięcia (przeskok okresu w produkcji, zatwierdzone jako
U) widać na 7 planszach U 6 obejrzanych zdjęć: 6 przesuniętych o rząd w dół
(`3aa225a9` 0, `c7cd13b0` 0, `e1c9e85a` 0 i 1, `ae604e68` 2, `4f28a2ed` 2) i 1
o kolumnę w prawo (`546aa0f9` 2; potwierdzone powiększeniem przeglądu). To ciche błędy
produkcji, których metryka `gold` nie widzi (plansze U nie są oceniane).

## Koszt czasu (ONNX CPU, 4 wątki, 30 zdjęć development)

| Model | Inferencja na zdjęcie: mediana / p95 | w tym ekran | Dekodowanie JPEG |
|---|---|---|---|
| run 1 | 0,177 / 0,189 s | 0,077 s | 0,011 s |
| run 2 | 0,173 / 0,183 s | 0,077 s | 0,010 s |
| iteracja 3 | 0,173 / 0,184 s | 0,076 s | 0,009 s |
| `hybrid_v3` | sieć run 1 + bramka 0,021 / 0,028 s | — | — |
| produkcja | nie mierzono (`processing_time_ms` pierwotnych rewizji jest pusty; silnika produkcyjnego nie uruchamiano w labie) | | |

Wynik: `grid-v3-comparison\timing\cpu-timing-30.json`.

## Rekomendacja

**Promować do trybu shadow (V3-D, TASK-0805), z modelem runu 1, w zakresie
ograniczonym:**

1. **Model:** run 1 (`2cd19738…-round3`) — wybrany na development przed
   odczytem holdoutów (92,3%, najwyższy wynik developmentu) i jedyny, dla
   którego skalibrowano progi `hybrid_v3`. Holdouty nie rozróżniają modeli
   (przedziały się pokrywają); iteracja 3 jest modelem dla Mumii (D-490), nie
   dla 777, i ma na development 91,0%.
2. **Rola `hybrid_v3` w shadow:** weryfikacja wyniku produkcji. Plansza
   `confident` oznacza zgodność produkcji i sieci; na development i `gold` nie
   było ani jednej błędnej planszy `confident` (0 / 5 054 i 0 / 190). Bramka
   **nie dodaje pokrycia** ponad akceptację produkcji — to jej ograniczenie z
   konstrukcji (plansza tylko z sieci nigdy nie jest `confident`).
3. **Rola sieci w shadow:** źródło propozycji siatek dla zdjęć, które produkcja
   oddaje do przeglądu (u nas S i `gold`): sieć odzyskuje tam 96–98% plansz,
   produkcja 41–88%. Propozycja sieci wymaga akceptacji człowieka (jak w
   przepływie labu D-490); automatyczne przyjęcie planszy tylko z sieci nie jest
   uzasadnione tym raportem.
4. **Bez promocji do produkcji** i bez automatycznego cięcia symboli z siatek
   sieci (zgodność symboli po cięciu nie była mierzona).

### Lista braków (dane do zebrania)

1. **Bramka dla plansz tylko z sieci** — osobna kalibracja (np. reszta
   dopasowania, IoU z quadem ekranu) na niezależnie oznaczonych zdjęciach S;
   dziś jedyna droga do `confident` wymaga planszy produkcji.
2. **Niezależna próbka zdjęć zaakceptowanych przez produkcję** z etykietą G
   (np. 100 losowych zdjęć B) — zbiór złoty jest wybrany z porażek produkcji i
   nie mierzy cichych błędów produkcji (przeskoki o rząd widoczne na planszach
   U).
3. **Weryfikacja 17 plansz „tuż za tolerancją”** przez operatora (która
   siatka jest dokładniejsza) i decyzja o tolerancji NME 0,02 dla skrajnych
   kolumn.
4. **Komplet siatek Reels i Treasure** (wszystkie plansze kilku zdjęć) — bez
   tego nie ma miary nadrzędnej D-483 ani fałszywych plansz dla gier
   niewidzianych.
5. **Gang** — 5–7 / 30 plansz poprawnych na partycji development D-456;
   potrzebne zdjęcia Gang w treningu (D-490 odłożyło Gang i Blazing).
6. **Zgodność symboli po cięciu** (plan V3-C) — nie mierzona w TASK-0804
   (symbole poza zakresem taska); wymaga etapu symboli D-489.
7. **Czas silnika produkcyjnego** — `processing_time_ms` nie jest zapisywany;
   porównanie kosztu wymaga pomiaru w pipeline.
8. **Rola walidacyjna** — snapshot v2 ma tylko `training`, `development` i
   `gold`; plan wspomina „zamrożoną walidację”, której nie ma.

## Co wynik znaczy, a czego nie

- Znaczy: na zdjęciach, które produkcja oddaje do przeglądu (S, `gold`), sieć
  odtwarza siatki człowieka/reweryfikacji w tolerancji D-483 w 96–99% plansz,
  a jej błędy są małe; bramka `hybrid_v3` nie przepuściła błędu.
- Nie znaczy: (1) development to zbiór wyboru i kalibracji; (2) `gold` jest
  stronniczy (plansze G powstały tam, gdzie produkcja zawiodła, albo są
  zatwierdzonym wynikiem produkcji); (3) etykiety S mają znany odsetek błędów
  (2,0% ścisły); (4) holdouty innych gier mają po 30 plansz, częściowe siatki i
  inną konwencję rysowania; (5) holdout Mumii służył do wyboru stanu runu 3;
  (6) produkcja na innych grach i zgodność symboli nie były mierzone.

## Pliki wyników

Katalog `C:\Users\tuszy\Documents\game_predictor_vision_data\`:

- `production-geometry\production-originals-777-20261004\` — pierwotne wyniki
  produkcji (`production-originals.jsonl`, `report.json`, `export_manifest.json`).
- `neural-grid-runs\ff03b1d7…\evaluations\d623eebfc876c7f3-best-development.json`
  i `exports\d623eebfc876c7f3-round9\` — ocena i eksport runu 2.
- `grid-v3-comparison\development\` — `network-{run1,run2,iter3}.json`,
  `summary.json` (SHA-256 `6c72f3d3…6949`), `photos.json`.
- `grid-v3-comparison\sealed\{gold,final_test,unseen_game,mumie_holdout}\` —
  `summary.json`, `photos.json`, `networks.json`, `cases.json`, `cases\`;
  `sealed\ledger.json`; `sealed\gold-001-inspection-005\`.
- `grid-v3-comparison\timing\cpu-timing-30.json`;
  `grid-v3-comparison\reference-not-sealed\` (próba potoku na danych
  nieodłożonych, w tym partycja development D-456).

## Odtworzenie

```powershell
$env:PYTHONPATH = 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src'
$py = 'C:\Users\tuszy\Documents\game_predicotr\.venv-vision-lab\Scripts\python.exe'
# run 2 (zakres 1)
& $py -m game_predictor_worker.vision_lab.neural_grid_runs evaluate --run ff03b1d7c489448483f23e73dd03f31d
& $py -m game_predictor_worker.vision_lab.neural_grid_runs export --run ff03b1d7c489448483f23e73dd03f31d --parity-images 16
# pierwotny wynik produkcji (zakres 2; baza tylko do odczytu)
.\.venv\Scripts\python.exe scripts\vision_lab_geometry_export.py --output-root <lab>\production-geometry `
  --export-id production-originals-777-20261004 --production-originals-for <snapshot v2> --originals-roles development,gold
# development (zakres 3)
$m = 'game_predictor_worker.vision_lab.grid_v3_comparison'
& $py -m $m development --model run1; & $py -m $m development --model run2; & $py -m $m development --model iter3
& $py -m $m report
& $py -m $m timing --images 30 --threads 4
# holdouty (jednorazowo; ponowienie jest odrzucane przez rejestr)
$s = 'game_predictor_worker.vision_lab.grid_v3_sealed'
& $py -m $s rehearse --output <katalog próbny>
& $py -m $s read --holdout gold --confirm-single-read
& $py -m $s read --holdout final_test --confirm-single-read
& $py -m $s read --holdout unseen_game --confirm-single-read
& $py -m $s read --holdout mumie_holdout --confirm-single-read
& $py -m $s status
```
