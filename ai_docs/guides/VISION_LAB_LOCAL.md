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

Pierwszy, zachowany historyczny snapshot dostarczonego zbioru ma ID
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
$snapshot = 'C:\Users\tuszy\Documents\game_predictor_vision_data\snapshots\82c3c29dd35e17a1df74da249fd8687f86db6be0b781e0bb1a64f1dbbc1962c9'
$annotations = 'C:\Users\tuszy\Documents\game_predictor_vision_data\annotations\82c3c29dd35e17a1df74da249fd8687f86db6be0b781e0bb1a64f1dbbc1962c9'
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

## Aktualizacja zdjęć i zachowanie anotacji (T03c)

Aktualny import folderu z 2026-09-26 zawiera 993 zdjęcia i ma ID
`82c3c29dd35e17a1df74da249fd8687f86db6be0b781e0bb1a64f1dbbc1962c9`.
Ścieżki w instrukcji uruchomienia powyżej wskazują ten snapshot i odpowiadający
mu katalog anotacji. Przy pierwszym przejściu użyj poniższej procedury przed
startem API. Stary snapshot 1180 zdjęć i jego katalog anotacji pozostają kopią
historyczną; nie uruchamiaj dwóch API zapisujących do różnych kopii podczas pracy.

1. Uruchom istniejący importer folderu (sekcja Import), zachowując źródła i stare
   snapshoty. Zapisz zwróconą ścieżkę nowego snapshotu.
2. Uruchom poniższy preflight. Nie zmienia anotacji ani nie tworzy celu.
3. Po wyniku `ready` zatrzymaj własny proces API laboratorium (8102), aby objąć
   ostatnie decyzje użytkownika. Powtórz polecenie z dodanym `--apply`; narzędzie
   ponownie sprawdzi aktualny stan. Odmowa wskazuje zmienione źródło lub konflikt;
   nie omijaj jej ręczną edycją identyfikatorów.
4. Uruchom API na nowych ścieżkach z sekcji powyżej i odśwież galerię. Sprawdź
   rewizję, pełne siatki, autorów i liczniki. Zwykły restart API/Admina aplikacji
   nie zastępuje restartu osobnego laboratorium.

```powershell
$rebaseArgs = @(
  '-m', 'game_predictor_worker.vision_lab.rebase_annotations',
  '--old-snapshot', 'C:\Users\tuszy\Documents\game_predictor_vision_data\snapshots\8a6035046a5746959c826489e2d7b0453f25b62ce04ccba80c52cd89fb38bce9',
  '--new-snapshot', 'C:\Users\tuszy\Documents\game_predictor_vision_data\snapshots\82c3c29dd35e17a1df74da249fd8687f86db6be0b781e0bb1a64f1dbbc1962c9',
  '--annotations', 'C:\Users\tuszy\Documents\game_predictor_vision_data\annotations\8a6035046a5746959c826489e2d7b0453f25b62ce04ccba80c52cd89fb38bce9',
  '--destination', 'C:\Users\tuszy\Documents\game_predictor_vision_data\annotations\82c3c29dd35e17a1df74da249fd8687f86db6be0b781e0bb1a64f1dbbc1962c9'
)
# Preflight; po jego ocenie i zatrzymaniu API dodaj do argumentów '--apply'.
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList $rebaseArgs -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill($true); throw 'Rebase timeout 120 s' }
if ($p.ExitCode -ne 0) { throw "Rebase exit $($p.ExitCode)" }
```

Raport `rebase-report.json` w nowym katalogu zawiera digest starego i nowego
katalogu/payloadu, rewizję i listę wszystkich zachowanych referencji. Stan i raport
publikowane są atomowo. Identyczne retry zwraca `already_applied`; jeśli na celu
pojawiły się nowe decyzje, ponowienie zwraca konflikt i niczego nie nadpisuje.
Również historia musi odwoływać się do niezmienionych zdjęć. Rodziny lub split
są w tej wersji blokadą wymagającą osobnego rozwiązania. Operacja nie zmienia
roli 777 ani kwalifikacji treningowej.

## Granice i błędy galerii

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
narożniki lub wszystkie węzły. Nowe decyzje geometrii mają stałego aktora
`operator`; historyczni autorzy pozostają zachowani.

Galeria pokazuje osobno pełne obecne siatki, lokalizacje i szkice. Filtry
„Bez zapisów”, „Rozpoczęte” i „Z pełną siatką” obejmują całą grę przed
paginacją. Ostatni oznacza co najmniej jedną pełną siatkę, nie kompletne
zdjęcie ani gotowość do treningu. „Odśwież statusy” pobiera trwały stan.

W edytorze wybierz numer pozycji albo obrys w rozwijanym przeglądzie całego
zdjęcia. Wczytany zostanie dokładny zapis z jego topologią i cropami.
Pozycje 1–9 są dostępne zawsze, a istniejące dalsze zapisy także pojawiają się
na liście. Brak zapisu wymaga kliknięcia „Nowa propozycja z narożników”.
Topologię pustej pozycji zmienisz bez powrotu do pozycji 1. Wczytanie zapisanej
planszy odtwarza jej topologię bez konwersji.

„Zatwierdź pełną siatkę” potwierdza wszystkie węzły samym jawnym kliknięciem,
bez dodatkowego checkboxa. Po zatwierdzeniu lokalizacji lub pełnej siatki
pozycji 1–8 otwiera się kolejna pozycja tego samego zdjęcia: istniejący zapis
albo niezapisana propozycja. Szkic i pozycja 9 pozostają na miejscu.
Zmiana widoku wymaga odrzucenia niezapisanej pracy. Po utracie odpowiedzi
„Ponów identyczne żądanie” bezpiecznie odtwarza wynik; „Odśwież po konflikcie”
wymaga decyzji o zastąpieniu edycji aktualnym zapisem.

Powiadomienia pojawiają się w lewym dolnym rogu: sukces zielony, błąd czerwony,
ostrzeżenie pomarańczowe, informacja neutralna. Kliknięcie lub „Zamknij” usuwa
komunikat. Sukces/informacja pozostają 120 s, błąd/ostrzeżenie 180 s; hover,
focus i ukryta karta wstrzymują zegar. Zamknięcie komunikatu nie usuwa retry.
Raport pomiarów nadal pozostaje w panelu rodzin jako dane.

T03a: duży edytor ma po prawej zwarte cropy bieżącej siatki. Przeciągnij
uchwyt i puść: kadr dopasuje się do siatki z marginesem, a cropy odświeżą się
automatycznie. Podczas przeciągania kadr pozostaje nieruchomy. „Pokaż całe
zdjęcie” przywraca pełny widok bez zmiany geometrii. „Ponów podgląd” odświeża
cropy po błędzie lub restarcie API. Żadna z tych czynności nie zapisuje
anotacji ani zatwierdzenia. Błędna siatka pokazuje komunikat zamiast starych
cropów. W wąskim oknie cropy znajdują się pod edytorem.

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
