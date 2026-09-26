---
title: Lokalne laboratorium wizji — galeria
status: active
last_updated: 2026-09-26
---

# Laboratorium wizji — galeria i anotacje

Galeria działa pod `http://127.0.0.1:3102`, a jej osobne API pod
`http://127.0.0.1:8102`. Korzysta ze snapshotu plików bez połączenia z bazą.
Wybierz grę i zdjęcie, następnie `Pokaż wynik baseline`, aby obejrzeć
propozycję siatki oraz cropy komórek. Obecny prototyp obsługuje 5 × 3;
wybór 3 × 3 daje jawne `unsupported`. `complete` oznacza status silnika,
nie ręczne zatwierdzenie poprawności. Edytor T03 zbiera osobne decyzje
człowieka; hybryda nie została jeszcze wytrenowana.

## Import dostarczonego folderu

Z katalogu repozytorium, w PowerShell:

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @(
  '-m', 'game_predictor_worker.vision_lab.snapshot',
  '"C:\Users\tuszy\Documents\new_traning_set"',
  '"C:\Users\tuszy\Documents\game_predictor_vision_data\snapshots"'
) -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill($true); throw 'Import timeout 120 s' }
if ($p.ExitCode -ne 0) { throw "Import exit $($p.ExitCode)" }
```

Wymaga istniejących zależności projektu. Importer wypisuje katalog
opublikowanego snapshotu. Zachowuje źródła i ich wystąpienia; identyczne
SHA-256 współdzielą kopię pliku. Ponowienie sprawdza istniejący snapshot.
Niezgodność pliku lub manifestu kończy się błędem bez nadpisania.
Nie wskazuj katalogu docelowego wewnątrz źródła ani odwrotnie.

Snapshot dostarczonego zbioru ma ID
`8a6035046a5746959c826489e2d7b0453f25b62ce04ccba80c52cd89fb38bce9`.
Obejmuje 1180 wystąpień i 1160 unikalnych obrazów. Folder `777` ma rolę
`comparison_only`. Żaden obraz nie otrzymuje automatycznie etykiety,
zatwierdzenia lub kwalifikacji treningowej. Prefiks nazwy przed `__` to
kandydat rodziny do późniejszej weryfikacji.

Galeria obsługuje również snapshot DB z
[eksportera T01](VISION_LAB_EXPORT.md). Format DB zachowuje swój manifest
i identyfikatory; import plikowy nie tworzy fikcyjnych identyfikatorów DB.

## Powtarzalne uruchomienie po restarcie

Najpierw wykonaj build UI przy zatrzymanym serwerze tej aplikacji:

```powershell
$p = Start-Process -FilePath 'node.exe' -ArgumentList @(
  'node_modules/next/dist/bin/next', 'build', 'apps/vision-lab'
) -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill($true); throw 'Build timeout 120 s' }
if ($p.ExitCode -ne 0) { throw "Build exit $($p.ExitCode)" }
```

Potem uruchom procesy z jawną ścieżką snapshotu. Polecenia działają w nowym
PowerShell bez zmiennych ustawionych w poprzedniej sesji:

```powershell
$repo = (Get-Location).Path
$logs = Join-Path $repo 'artifacts\vision-lab'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$snapshot = 'C:\Users\tuszy\Documents\game_predictor_vision_data\snapshots\8a6035046a5746959c826489e2d7b0453f25b62ce04ccba80c52cd89fb38bce9'
$annotations = 'C:\Users\tuszy\Documents\game_predictor_vision_data\annotations\8a6035046a5746959c826489e2d7b0453f25b62ce04ccba80c52cd89fb38bce9'
$labApi = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @(
  '-m', 'game_predictor_worker.vision_lab', '--snapshot', ('"' + $snapshot + '"'),
  '--annotations', ('"' + $annotations + '"')
) -WorkingDirectory $repo -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $logs 'api.stdout.log') `
  -RedirectStandardError (Join-Path $logs 'api.stderr.log')
$labUi = Start-Process -FilePath 'node.exe' -ArgumentList @(
  'node_modules/next/dist/bin/next', 'start', 'apps/vision-lab',
  '--hostname', '127.0.0.1', '--port', '3102'
) -WorkingDirectory $repo -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $logs 'ui.stdout.log') `
  -RedirectStandardError (Join-Path $logs 'ui.stderr.log')
"API PID: $($labApi.Id); UI PID: $($labUi.Id)"
foreach ($url in @('http://127.0.0.1:8102/sources?limit=1', 'http://127.0.0.1:3102')) {
  $ready = $false
  for ($attempt = 0; $attempt -lt 5; $attempt++) {
    try {
      $null = Invoke-WebRequest -Uri $url -TimeoutSec 1
      $ready = $true
      break
    } catch { Start-Sleep -Milliseconds 200 }
  }
  if (-not $ready) { throw "Brak gotowości: $url; sprawdź PID i logi przed ponowieniem" }
}
```

Sprawdź wcześniej, czy porty są wolne. Jeśli proces zgłasza zajęty port,
zatrzymaj uruchamianie i ustal właściciela; nie kończ cudzej usługi ani nie
uruchamiaj drugiej kopii. Zapisz wypisane PID-y. Do zatrzymania własnych
procesów w tej samej sesji służy `$labApi.Kill($true)` i `$labUi.Kill($true)`;
w nowej sesji najpierw potwierdź tożsamość procesu, bo system może ponownie
użyć numeru PID. Serwery nie są dodawane do autostartu systemu.

Przy zmianie kodu backendu uruchom ponownie własne API; przy zmianie UI
zatrzymaj własny UI, wykonaj build i uruchom go ponownie. Nie wykonuj buildu
współbieżnie z serwerem developerskim zapisującym tę samą `.next`.

## Granice i błędy

- Brak wykrytej siatki oraz niepewne propozycje wymagają późniejszej oceny.
- Wadliwy obraz ma własny błąd; pozostałe pozycje galerii pozostają dostępne.
- Niespójny snapshot lub błąd dostępu do plików blokuje zależną operację.
- Cropy są podglądem w pamięci procesu. Po restarcie ponów analizę zdjęcia.
- Galeria nie uruchamia treningu ani nie aktywuje modelu. Edytor zapisuje
  wyłącznie jawne decyzje użytkownika; zwykły podgląd niczego nie zatwierdza.
- Raport zakresu danych i ograniczonego smoke:
  [VISION_LAB_STAGE_A_ACCEPTANCE.md](../quality/VISION_LAB_STAGE_A_ACCEPTANCE.md).

## Anotacje T03 — osobne od niezmiennego snapshotu

API wymaga jawnego `--annotations` (alternatywnie `VISION_LAB_ANNOTATIONS`).
Nie wskazuj wnętrza katalogu snapshotu. Bez tej konfiguracji galeria nadal
działa, lecz zapis anotacji jest niedostępny. Po uruchomieniu wybierz zdjęcie,
topologię i pozycję planszy. Wczytaj propozycję albo zapis, a następnie popraw
narożniki lub wszystkie węzły. Wprowadź osobę podejmującą decyzję.

- Szkic nie jest zatwierdzeniem.
- Zatwierdzenie lokalizacji dotyczy obecności i narożników; interpolowane
  węzły nie stają się przez to pełną referencją.
- Pełna siatka wymaga świadomej kontroli każdego węzła i granic komórek.
- Nie oznaczaj sugestii agenta ani wyniku modelu jako decyzji człowieka.
- Po konflikcie odczytaj aktualny stan i sprawdź zapis przed nową decyzją.

Panel rodzin pozwala zaznaczać powiązane zdjęcia także między stronami
galerii. Nazwy i prefiksy nie dowodzą pochodzenia; ten sam układ może mieć
różne nazwy, kadry i kompresję. Wspólna grupa obejmuje rodzinę nagrania,
pochodne i powtórzenia. Zapis nierozstrzygniętej grupy nie kwalifikuje jej
do treningu. Nie potwierdzaj niezależności, jeśli jej nie znasz.

Backup można utworzyć przyciskiem w panelu. Odtworzenie jest wyłącznie do
nowego katalogu, bez nadpisania obecnego zbioru. Narzędzie
`python -m game_predictor_worker.vision_lab.annotation_cli --help` opisuje
operacje `backup`, `restore` i `freeze`; identyfikator backupu zwraca UI.
Zamrożenie splitu wymaga zweryfikowanych rodzin, zatwierdzeń i osobnego
zestawu pomiarowego. Nie używaj go do obejścia brakujących danych.

Stan operacyjny i niespełnione bramki etapu B opisuje
[raport B](../quality/VISION_LAB_STAGE_B_ACCEPTANCE.md).
