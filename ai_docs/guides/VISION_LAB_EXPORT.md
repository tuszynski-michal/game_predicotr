---
title: Eksport snapshotu do laboratorium wizji
status: active
last_updated: 2026-09-25
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
powiązanych tabel, `images/` kopie źródeł, a `assets/` kopie istniejących
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
