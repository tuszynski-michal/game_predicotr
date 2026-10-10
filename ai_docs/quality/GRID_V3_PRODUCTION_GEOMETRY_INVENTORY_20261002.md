---
title: Inwentaryzacja geometrii produkcyjnej 777 dla treningu siatek V3 (TASK-0800)
status: accepted
last_updated: 2026-10-02
---

# Inwentaryzacja geometrii produkcyjnej 777 (TASK-0800)

## Cel i zakres

Raport opisuje wynik eksportu tylko do odczytu `scripts/vision_lab_geometry_export.py`
dla gry 777 (`bfc4f949-5c14-4850-b02a-db99610bcfa5`, schemat `game_data_v2`,
head Alembic `0139_source_image_geometry_completeness`). Eksport tylko opisuje dane:
wybór próbek, kopia obrazów, podział i filtr zgodności symboli to TASK-0801.
Reguły eksportera i format wyniku opisuje `ai_docs/guides/VISION_LAB_EXPORT.md`.

- Wynik: `C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry\production-geometry-777-20261002\`
  (`candidates.jsonl` 1 587 136 303 B, `exclusions.jsonl` pusty, `report.json`,
  `export_manifest.json`, `image_ids.txt`, `progress.json`); suma SHA-256
  `candidates.jsonl`: `0efe2a6a637f73515df9577b1fbaf8adf14b71242bf159cd10e88994cf1cfacd`.
- Czas: ok. 8 min 14 s (489,9 s pracy eksportera), 555 partii po 100 zdjęć, 4
  równoległe krótkie transakcje `REPEATABLE READ READ ONLY`, bez wznowień.
- Odczyt: transakcje sprawdzone przez `SHOW transaction_read_only = on`; eksport
  nie wykonał żadnego zapisu ani migracji, nie tworzył tabel tymczasowych w bazie
  deweloperskiej i nie kopiował obrazów.

## Uzgodnienie liczności z zapytaniami kontrolnymi

Zapytania kontrolne (niezależny SQL, osobna implementacja reguły poziomów) wykonano
o 09:08:53–09:09:15 UTC, kilka sekund po zakończeniu eksportu (09:08:47 UTC);
wszystkie liczby poniżej zgadzają się co do jednej planszy, więc baza nie zmieniła się w tym czasie.

| Wielkość | Eksport | Kontrola SQL |
|---|---|---|
| Zdjęcia `geometry_complete` / `geometry_incomplete` / poza bramką (`NULL`) | 55 499 / 60 / 1 253 | 55 499 / 60 / 1 253 |
| Żywe plansze na zdjęciach `geometry_complete` | 499 460 (kandydaci 499 460 + wykluczone 0) | 499 460 na 55 499 zdjęciach |
| Żywe plansze na zdjęciach `geometry_incomplete` | 540 (pominięte) | 540 |
| Plansze `rejected` łącznie / na zdjęciach `geometry_complete` | 10 390 / 4 | 10 390 / 4 |
| Wszystkie plansze gry | 510 390 | 510 390 |
| Poziom B / G / S / U | 361 103 / 459 / 137 473 / 425 | 361 103 / 459 / 137 473 / 425 |
| Zdjęcia z co najmniej jedną planszą B / G / S / U | 40 123 / 101 / 15 275 / 76 | 40 123 / 101 / 15 275 / 76 |
| Aktor zatwierdzenia: `system:grid-reverify-777-v1` | 137 437 | 137 437 |
| `local-admin` | 198 | 198 |
| `system:import-qualified-manual-geometry` | 36 | 36 |
| Plansze z geometrią zapisaną przez `reviewer-operator` (bez zatwierdzenia) | 261 | 261 |
| Plansze częściowe (`pending_partial`) | 0 | 0 |
| Plansze według liczby plansz na zdjęciu 9 / 8 / 7 / 5 / 2 / 1 | 55 492 / 2 / 1 / 1 / 1 / 2 | 55 492 / 2 / 1 / 1 / 1 / 2 |
| Rodziny (katalogi wyboru) / zadania importu | 24 / 25 | 24 / 25 |
| Brak manifestu renderu / manifest nie 5 × 3 | 0 / 0 | 0 / 0 |
| Sygnały symboli (B): plansze bez komórki ≤ 0,80 | 358 123 | 358 123 |
| Sygnały symboli (G / S / U): j.w. | 401 / 133 475 / 414 | 401 / 133 475 / 414 |
| Plansze, gdzie wszystkie komórki mają decyzję człowieka (S) | 2 | 2 |
| Plansze z co najmniej jedną komórką z decyzją człowieka (B / G / S / U) | 25 241 / 250 / 11 881 / 168 | 25 241 / 250 / 11 881 / 168 |

Dodatkowo: 600 losowych wierszy (nasienie 800) porównano po zapisie z manifestami
renderu w bazie, używając węzłów zaokrąglonych do 4 miejsc; największy błąd narożnika
komórki wyniósł 7,0e-5 px. Test jednostkowy porównuje węzły z niezależną homografią
`cv2.getPerspectiveTransform`.

Różnica względem liczb planu: plansz jest teraz 510 390 (plan podawał 510 416), a
zatwierdzonych (`geometry_approved_by` niepuste, żywe) 138 184; po odjęciu 513 plansz
`system:import-qualified-manual-geometry` na 57 zdjęciach `geometry_incomplete`
(408 pełnych i 105 `pending_partial`) do eksportu wchodzi 137 671 zatwierdzonych.

## Reguła poziomu etykiety (zaimplementowana)

Źródłem są kolumny `recognized_boards` (`geometry_revision`,
`approved_geometry_revision`, `geometry_approved_by`), autor rewizji geometrii
planszy (`image_board_geometry_revisions.corrected_by` dla bieżącej rewizji i
wcześniejszych) oraz rewizja geometrii źródła, z której plansza pochodzi
(`geometry_source`, `status`, `created_by`). „Zatwierdzona” znaczy
`approved_geometry_revision = geometry_revision` (zatwierdzenie bieżącej geometrii).

| Poziom | Podstawa (`label.basis`) | Warunek | Plansz | Zdjęć |
|---|---|---|---|---|
| G | `human_approval` | zatwierdzenie bieżącej geometrii przez `local-admin` lub `reviewer-operator` | 198 (`local-admin`; 135 po zapisie rewizji 1, 63 po zatwierdzeniu geometrii silnika w rewizji 0) | 22 |
| G | `human_saved_revision_via_legacy_conversion` | bieżąca rewizja pochodzi z `system:legacy-board-conversion-v1`, a wcześniejszą rewizję zapisał `reviewer-operator`; brak zapisu zatwierdzenia | 261 | 79 |
| G | `human_saved_revision_unapproved` | bieżącą rewizję zapisał człowiek, bez zatwierdzenia | 0 | 0 |
| S | `system_reverify` | zatwierdzenie `system:grid-reverify-777-v1` | 137 437 | 15 271 |
| S | `system_import_qualified_manual_geometry` | zatwierdzenie `system:import-qualified-manual-geometry` (jawnie sklasyfikowany aktor systemowy) | 36 | 4 |
| B | `engine_accepted_unapproved` | rewizja 0, źródło `auto` zaakceptowane (`status = accepted`, autor `system:image-pipeline-*`), brak zatwierdzenia | 361 103 | 40 123 |
| U | `manual_source_geometry_without_authorship` | rewizja 0, ręczna geometria źródła utworzona przez `system:legacy-board-conversion-v1`, brak zatwierdzenia i brak rewizji planszy | 425 | 76 |

Nieznany aktor zatwierdzenia (`unknown_system_approver`, `unknown_approver`), nieznany
autor rewizji, zatwierdzenie starszej rewizji, niezaakceptowana geometria silnika i
nieznane pochodzenie trafiają do poziomu `U` z podstawą — nic nie jest zgadywane.
W danych występuje tylko podstawa `manual_source_geometry_without_authorship` (425).

Uwagi do oceny w TASK-0801:

- Poziom G nie jest czysty: 261 z 459 plansz G to geometria zapisana przez
  Reviewera i przeniesiona konwersją legacy, bez zapisu zatwierdzenia; pole
  `label.basis` pozwala je wydzielić. Plan liczył 461 rezolucji Reviewera, ale 197
  z nich to plansze `rejected`, a 3 leżą na zdjęciach `geometry_incomplete`.
- Wszystkie 425 plansz `U` leżą na 76 zdjęciach, które mają też plansze G
  (`G+U`): to rodzeństwo plansz po konwersji legacy; ich autorstwa nie da się
  ustalić z danych, więc nie wchodzą ani do G, ani do S.
- Poziom S (137 473) to w 99,97% jedna reweryfikacja hybrydowa; D-480 mówi, że
  może powielać jej błędy.

## Jak wyliczane jest 24 węzły i jak sprawdzana jest zgodność z manifestem

Węzły to rzut projekcyjny punktów `(kolumna / 5, wiersz / 3)` jednostkowego kwadratu
na quad planszy (lewy górny, prawy górny, prawy dolny, lewy dolny), zapisane wiersz
po wierszu (węzeł `wiersz * 6 + kolumna`); to ta sama funkcja, którą renderer wylicza
quady komórek. Które zapisane cztery punkty są quadem siatki, rozstrzyga manifest
renderu planszy: eksporter próbuje kolejno `corners` rewizji planszy, `symbolGridQuad`
rewizji źródła, `symbolGridQuad` planszy i `finalQuad`, i przyjmuje pierwszy, z
którego węzły odtwarzają quady wszystkich komórek manifestu z dokładnością 0,01 px.

- Użyte pochodzenie quada: `board_revision_corners` 137 833 plansz (ręczne rewizje
  planszy), `source_revision_symbol_grid_quad` 361 627 plansz (silnik i importowana
  geometria ręczna).
- Odchyłka od manifestu we wszystkich 499 460 wierszach wynosi 0,0 px (identyczna
  funkcja, kwantyle w `report.json`).
- Plansz, dla których spójność nie zachodzi: 0 (żadnego wykluczenia). Ścieżki
  wykluczeń (niezgodne węzły, brak manifestu, topologia nie 5 × 3, zdegenerowany
  quad, komórki manifestu poza maską niedostępnych) są pokryte testami
  jednostkowymi i testem PostgreSQL, ale dane produkcyjne ich nie wywołały.
- Ścieżka planszy częściowej (maska niedostępnych komórek, brakujące komórki
  manifestu) jest przetestowana, lecz w eksporcie nie ma plansz częściowych: wszystkie
  108 żywych plansz `pending_partial` leży na 60 zdjęciach `geometry_incomplete`.
- Jedna plansza ma węzły poza obrazem (`boardsWithNodesOutsideImage` = 1).

## Rodzina źródła

Obrazy źródłowe są adresowane treścią (`originals/xx/<sha>.jpg`), więc katalog ani
nazwa pliku nagrania nie są zapisane per obraz. Rodziną jest katalog wyboru z
zadania importu (`jobs.input_payload.source_directory`, ostatni człon), a przy jego
braku zadanie importu; `sourceDisplayName` zadania opisuje fragment nagrania
(„1-19809 cut”). Wynik: 25 zadań importu, 24 rodziny (zadania `7d10ae0a…` i
`f4ef3449…` importowały ten sam katalog; to znany duplikat z TASK-0811, nie do
usunięcia — 1 154 z 1 160 zdjęć `7d10ae0a…` jest poza bramką, a `f4ef3449…` ma 1 156
zdjęć `geometry_complete`). Ograniczenie: „katalog nagrania” w sensie pojedynczego pliku wideo nie
jest rozpoznawalny z danych importu; rodzina to ciągły fragment („cut”) nagrania, a
dalsze grupowanie po SHA i numerach sekwencji robi podział w TASK-0801. Dodatkowo
2 sumy SHA występują na 4 zdjęciach (zdjęcia o tym samym SHA w różnych zadaniach);
jedna para ma poziomy G+U, druga G+S.

Plansz na rodzinę i poziom zapisuje `report.json` (`families`); poziom G występuje w
13 z 24 rodzin. Najwięcej G i U mają `selection:0dbd07df…` („1-19809 cut”: 247 G, 194 U)
i `selection:ef4be7d3…` („149626 - 177561 cut”: 99 G, 72 U).

## Rozkłady (cały manifest)

- Plansz na zdjęciu: 55 492 zdjęcia po 9; 6 zdjęć ma mniej (8, 8, 7, 2, 1, 1 —
  pozostałe pozycje to superseded D-485) i 1 zdjęcie ma 5 oczekiwanych plansz.
- Slot na stronie 3 × 3: każdy z 9 slotów ma ok. 55 495 plansz; skrajna kolumna
  (0 lub 2) ma 66,7% plansz, skrajny wiersz (0 lub 2) 66,7%.
- Pole quada: 0,9–4,0% powierzchni zdjęcia (mediana 1,8%; 1520 × 1074 to najczęstszy
  rozmiar: 86 742 plansz); pole w pikselach 6 511–44 411 (mediana 18 522).
- Perspektywa: stosunek przeciwległych krawędzi poziomych p50 1,017, p99 1,053
  (maks. 1,377), pionowych p50 1,036, p99 1,119 (maks. 1,334); największe odchylenie
  kąta od 90°: p50 4,6°, p95 11,2°, p99 13,7°, maks. 27,7°. Rozkłady per poziom są
  zbliżone (G ma nieco mniejsze plansze: mediana pola 1,64% wobec 1,79% dla B).
- Kontrast: pole „niski kontrast” wymaga pikseli — do uzupełnienia w TASK-0801.

## Sygnały dla filtra symboli (definicja z raportu kompletności TASK-0806, próg ≤ 0,80)

| Poziom | Plansz | Z komórkami | Bez komórki ≤ 0,80 (gotowe do filtra) | Z ≥ 1 komórką z decyzją człowieka | Wszystkie komórki z decyzją człowieka |
|---|---|---|---|---|---|
| B | 361 103 | 361 103 | 358 123 (99,18%) | 25 241 | 0 |
| G | 459 | 459 | 401 (87,36%) | 250 | 0 |
| S | 137 473 | 137 473 | 133 475 (97,09%) | 11 881 | 2 |
| U | 425 | 425 | 414 (97,41%) | 168 | 0 |

Najniższa predykcja na planszy (`minPredictionConfidence`) ≤ 0,8 ma 13 451 plansz B,
12 631 S, 75 G i 25 U (≤ 0,5: 1 394 / 1 714 / 13 / 3). Wszystkie plansze mają
wiersze komórek, nie ma plansz bez komórek. Reguła „komórka bez decyzji człowieka z
predykcją ≤ 0,80” (`cellsBelowFilter`) i „komórka ≤ 0,80 oczekująca” (`lowQualityCells`)
są policzone osobno w każdym wierszu, żeby TASK-0801 mógł ustalić próg przed
pomiarem.

## Wnioski dla TASK-0801

- Do oceny (G) jest 459 plansz na 101 zdjęciach: 22 zdjęcia mają wszystkie 9 plansz G
  (to 198 plansz zatwierdzonych przez `local-admin`), 3 zdjęcia mają tylko część plansz
  G, a 76 zdjęć łączy G (Reviewer, 261 plansz) z planszami U (425). Metryka nadrzędna
  „zdjęcie kompletne i poprawne” ma więc pełną referencję G tylko na 22 zdjęciach.
- S i B pokrywają całe zdjęcia: 15 275 zdjęć ma wyłącznie plansze S (15 273 z
  wszystkimi 9 planszami S), 40 123 zdjęcia wyłącznie B (40 122 z 9 planszami B);
  mieszane są tylko zdjęcia G+U.
- Przeciek: jedna rodzina to jeden katalog wyboru; podział po rodzinach daje 24
  grupy, a zbiór złoty G leży w 13 z nich. Zdjęcia o tym samym SHA (2 pary) trzeba
  zgrupować.
- Zdjęć ze wszystkimi komórkami z decyzją człowieka praktycznie brak (2 plansze
  S); filtr zgodności symboli musi się opierać na predykcjach (97,1% plansz S i 99,2%
  plansz B nie ma komórki bez decyzji człowieka z predykcją ≤ 0,80).

## Weryfikacja

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "production_geometry or no_production_storage_imports"
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_vision_lab_geometry_export_postgres.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check services scripts
```

Wyniki: 30 testów worker (29 węzłów i poziomów + test izolacji laboratorium), 4 testy
PostgreSQL (poziomy, wykluczenia, uzgodnienie, brak przecieku drugiej gry, wznowienie
bez dublowania, transakcja bez zapisu). `ruff check` zgłasza jedno wcześniejsze
E501 w `services/worker/tests/test_page_geometry_preflight.py` (poza zakresem).
