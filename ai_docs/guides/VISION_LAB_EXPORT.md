---
title: Eksport snapshotu do laboratorium wizji
status: active
last_updated: 2026-10-02
---

# Eksport snapshotu do laboratorium wizji

`scripts/vision_lab_export.py` jest osobnym narzędziem głównego środowiska.
Wymaga pliku wejściowego JSON, lokalnej bazy PostgreSQL skonfigurowanej przez
`GAME_PREDICTOR_DATABASE_URL` i dostępu do magazynu zarządzanych obrazów.
Nie zmienia bazy. Nie uruchamiaj go na danych użytkownika bez przygotowanego
manifestu wskazującego dokładne źródła.

Manifest v1 ma tę postać:

```json
{
  "schemaVersion": 1,
  "datasetName": "pilot-wizji",
  "entries": [
    {
      "gameId": "00000000-0000-0000-0000-000000000001",
      "sourceImageId": "00000000-0000-0000-0000-000000000002",
      "expectedSourceSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "sourceFamilyId": "nagranie-1",
      "role": "data"
    }
  ]
}
```

`role` przyjmuje `data`, `comparison_only` dla historycznego 777 albo
`777_v2_declared` dla jawnie zadeklarowanego 777 V2. Sama deklaracja V2 nie
kwalifikuje źródła do treningu; kontrola konfliktów i podział są w T03.
Manifest ma od 1 do 1000 różnych źródeł. Eksport kończy się błędem, jeśli
źródło nie należy do wskazanej gry lub jego SHA-256 się różni.

Przykład polecenia w PowerShell po przygotowaniu manifestu:

```powershell
$outputRoot = 'C:\Users\tuszy\Documents\game_predictor_vision_data\snapshots'
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @(
  'scripts\vision_lab_export.py', '.\manifest.json',
  '--artifact-root', '.\artifacts', '--output-root', $outputRoot
) -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'Eksport przekroczył 120 s' }
if ($p.ExitCode -ne 0) { throw "Eksport zakończył się kodem $($p.ExitCode)" }
```

Eksporter zamraża ID i fingerprint każdego wiersza, a następnie odczytuje
je partiami w nowych transakcjach `REPEATABLE READ READ ONLY`. Zmiana wiersza,
generacji magazynu gry, brak rekordu lub niezgodność pliku zatrzymuje cały
eksport. Katalog tymczasowy nie jest snapshotem. Po sprawdzeniu plików
eksporter wykonuje atomową zmianę nazwy na tym samym wolumenie.

Gotowy katalog ma nazwę równą `snapshotId`. `manifest.json` zawiera
checksumy wszystkich plików. `frozen_identity.json` przechowuje ID i
fingerprinty wierszy. `records/<gameId>/*.jsonl` zawiera pełne wiersze
powiązanych tabel (od migracji `0136`, TASK-0793, wiersze
`image_symbol_review_cells` nie mają pola `render_spec`; specyfikacja renderu
wirtualnego cropa jest w `board_render_manifests.jsonl` dla
`(recognized_board_id, geometry_revision, cellIndex)` komórki, powiązana
sumą `render_spec_checksum_sha256`), `images/` kopie źródeł, a `assets/` kopie istniejących
plansz i cropów z rewizji. `approved_labels.json` jest konserwatywną projekcją
aktualnych zatwierdzeń przypiętych do tego samego cropa i geometrii,
aktywnego symbolu oraz obecnego właściciela sekwencji. Projekcja obejmuje
tylko zweryfikowane kopie cropów plikowych; wirtualne cropy pozostają w
surowych rekordach do czasu odtworzenia ich renderingu w laboratorium;
surowe zdarzenia review pozostają w `records/`.

`historical_comparisons.json` przechowuje osobno początkową rewizję
`selective_board_review_v1_1` i późniejsze ręczne rewizje. Początkowa
rewizja jest `null`, jeśli brak jej dowodu w danych; eksporter nie odtwarza
jej z późniejszej korekty. Dowód V1.1 wymaga zachowanej rewizji geometrii
źródła o odpowiednim silniku i sumie kontrolnej, z geometrią tego samego
slotu oraz numeru sekwencji. Eksporter wybiera najwcześniejszą pasującą
rewizję źródła; bieżący wskaźnik planszy może już wskazywać korektę ręczną.
Ponowienie z identycznym stanem weryfikuje
wszystkie pliki gotowego snapshotu. Konflikt albo uszkodzenie kończy się
błędem bez nadpisania istniejącego katalogu.

## Eksport geometrii produkcyjnej (TASK-0800)

`scripts/vision_lab_geometry_export.py` jest osobnym skryptem obok
`vision_lab_export.py`, bo ma inny kontrakt: nie przyjmuje manifestu wejściowego
(do 1000 źródeł), nie kopiuje obrazów i nie zamraża tożsamości wierszy. Czyta
całą grę (domyślnie o nazwie `777`) tylko do odczytu i zapisuje manifest
kandydatów treningowych geometrii oraz raport liczności. Używa tej samej roli
właściciela i tego samego wiązania gry co `vision_lab_export.py` (importuje jego
`_read_transaction`); laboratorium nadal nie importuje `storage` ani `psycopg`.

```powershell
$root = 'C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry'
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @(
  'scripts\vision_lab_geometry_export.py', '--output-root', $root,
  '--export-id', 'production-geometry-777-20261002'
) -PassThru -NoNewWindow
if (-not $p.WaitForExit(900000)) { $p.Kill(); throw 'Eksport przekroczył 900 s' }
if ($p.ExitCode -ne 0) { throw "Eksport zakończył się kodem $($p.ExitCode)" }
```

Parametry: `--game-id` albo `--game-name` (domyślnie `777`), `--batch-images`
(domyślnie 100 zdjęć na transakcję), `--workers` (domyślnie 4 równoległe
transakcje odczytu; wyniki są zapisywane w kolejności partii), `--max-images`
(próba na początku listy), `--resume`. Pełny eksport 777 trwa ok. 8 minut i
zajmuje ok. 1,6 GB (jeden wiersz na planszę); nie uruchamiaj go równolegle z
testami PostgreSQL (limit 8 GB maszyny wirtualnej Dockera).

Każda partia to osobna transakcja `REPEATABLE READ READ ONLY` związana z grą i
przypięta do generacji magazynu; eksporter sprawdza `SHOW transaction_read_only`.
Lista zdjęć `geometry_complete` jest wyznaczana raz i zapisana w
`image_ids.txt`. Praca idzie do `.partial-<exportId>`, a po zakończeniu katalog
jest atomowo przemianowywany na `<exportId>`. Przerwany eksport wznawia się flagą
`--resume`: postęp (`progress.json`) zapisuje rozmiary plików po każdej partii,
a wznowienie obcina pliki do zapisanych rozmiarów, więc wiersze się nie dublują.
Wznowiony eksport czyta kolejne partie w innych transakcjach niż pierwsza część
(brak jednej migawki całej gry); raport zapisuje liczbę wznowień.

Pliki wyniku:

- `candidates.jsonl` — jeden wiersz (`production-geometry-candidate-v1`) na żywą
  planszę zdjęcia `geometry_complete`: identyfikatory gry, zdjęcia, planszy i
  importu, `sourceChecksumSha256`, `sourceRelativePath`, wymiary zorientowane,
  `positionIndex`, `sequenceNumber`, `expectedBoardsOnImage`,
  `candidateBoardsOnImage`, `label` (poziom G/S/B/U, podstawa, aktor
  zatwierdzenia, rewizje i ich autorzy), `engine`, `geometry` (quad planszy,
  24 węzły wierszami w pikselach `exif-normalized-rgb-pixels-v1`, pochodzenie
  quada, odchyłka od manifestu renderu), `partial` (maska niedostępnych
  komórek, kwalifikacja), `family`, `symbolSignals` i `difficulty`;
- `exclusions.jsonl` — plansze zdjęć `geometry_complete`, których nie da się
  wyliczyć zgodnie z manifestem renderu, z powodem;
- `report.json` — liczności per poziom, aktor, podstawę, silnik, rodzinę i
  trudność, powody wykluczeń oraz uzgodnienie z liczbą żywych plansz bramki;
- `export_manifest.json` (sumy SHA-256 plików), `progress.json`, `image_ids.txt`.

Reguły:

- Węzły: 24 węzły siatki 5 × 3 (`vision_lab/production_geometry.py`), wiersz po
  wierszu (węzeł `wiersz * 6 + kolumna`), to rzut projekcyjny punktów
  `(kolumna / 5, wiersz / 3)` jednostkowego kwadratu na quad planszy
  (lewy górny, prawy górny, prawy dolny, lewy dolny) — ta sama funkcja, którą
  renderer wyznacza quady komórek. Eksporter bierze pierwszy zapisany quad
  (rewizja planszy `corners`, `symbolGridQuad` rewizji źródła, `symbolGridQuad`
  planszy, `finalQuad`), z którego węzły odtwarzają quady wszystkich komórek
  manifestu renderu z dokładnością 0,01 px; komórki nieobecne w manifestie muszą
  leżeć w masce niedostępnych komórek planszy. Inaczej plansza jest wykluczona
  (`NODES_DO_NOT_MATCH_RENDER_MANIFEST`, `MANIFEST_CELLS_MISSING_WITHOUT_UNAVAILABLE_MASK`,
  `BOARD_QUAD_MISSING`, `BOARD_QUAD_DEGENERATE`, `RENDER_MANIFEST_MISSING`,
  `RENDER_MANIFEST_MALFORMED`, `TOPOLOGY_NOT_5X3`, `POSITION_OUTSIDE_ACTIVE_SLOTS`,
  `BOARD_INTEGRITY_ERROR`). Plansze `rejected` nie są kandydatami ani
  wykluczeniami; zdjęcia `geometry_incomplete`, `geometry_exception` i poza
  bramką są tylko liczone w raporcie.
- Poziom etykiety i jego podstawa są opisane w raporcie jakości
  `ai_docs/quality/GRID_V3_PRODUCTION_GEOMETRY_INVENTORY_20261002.md`; aktor,
  którego nie da się sklasyfikować, daje poziom `U` z podstawą, nie zgadnięty
  poziom.
- Rodzina źródła: obrazy źródłowe są adresowane treścią
  (`originals/xx/<sha>.jpg`), więc nazwa pliku nagrania nie jest zapisana. Rodzina
  to katalog wyboru z zadania importu (`source_directory`, ostatni człon), a przy
  jego braku zadanie importu; dwa zadania z tym samym katalogiem są jedną rodziną.
  `sourceDisplayName` zadania opisuje fragment nagrania (np. „1-19809 cut”).
- Sygnały dla filtra symboli (jak w raporcie kompletności z TASK-0806, próg
  `<= 0,80`): `cells`, `humanDecidedCells` (komórki `approved`),
  `lowQualityCells`, `minLowQualityConfidence`, `minPredictionConfidence`,
  `cellsBelowFilter` (komórki bez decyzji człowieka z predykcją `<= 0,80` albo
  bez predykcji). Metryka „niski kontrast” wymaga pikseli i należy do TASK-0801.

## Pierwotny wynik silnika produkcyjnego (TASK-0804)

Tryb `--production-originals-for <katalog snapshotu>` tego samego skryptu nie
eksportuje kandydatów, tylko plik `production-originals.jsonl` dla zdjęć ról
podanych w `--originals-roles` (domyślnie `development,gold`; identyfikatory z
`split.json` snapshotu). Dla każdego zdjęcia: ostatnia automatyczna rewizja
geometrii źródła `structured_opencv_v1` sprzed pierwszej rewizji `manual`
(reguła w `production_geometry.select_production_original`), jej status,
autor i linia rewizji, 24 węzły każdej planszy z `symbolGridQuad`
(`exif-normalized-rgb-pixels-v1`) albo jawny brak
(`PRODUCTION_ORIGINAL_BOARD_WITHOUT_GRID`), oraz kontrola z manifestem renderu
wyciętym z tej rewizji przy rewizji planszy 0. Zdjęcie bez takiej rewizji ma
`status = missing` i powód (`PRODUCTION_ORIGINAL_NO_AUTOMATIC_REVISION`,
`PRODUCTION_ORIGINAL_IMAGE_NOT_FOUND`, `PRODUCTION_ORIGINAL_SOURCE_MISMATCH`).
Odczyt w partiach w krótkich transakcjach `REPEATABLE READ READ ONLY`;
katalog wyniku (`production-originals.jsonl`, `input_image_ids.txt`,
`report.json`, `export_manifest.json` z SHA-256) jest publikowany jedną zmianą
nazwy, istniejący identyfikator eksportu jest odrzucany.

```powershell
.\.venv\Scripts\python.exe scripts\vision_lab_geometry_export.py --output-root $root `
  --export-id production-originals-777-20261004 `
  --production-originals-for <lab>\production-geometry-snapshots\<snapshot> --originals-roles development,gold
```
