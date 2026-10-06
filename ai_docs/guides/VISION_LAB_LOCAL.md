---
title: Lokalne laboratorium wizji — galeria
status: active
last_updated: 2026-10-02
---

# Laboratorium wizji — galeria i anotacje

Galeria działa pod `http://127.0.0.1:3102`, a jej osobne API pod
`http://127.0.0.1:8102`. Korzysta ze snapshotu plików bez połączenia z bazą.
Wybierz grę i zdjęcie, następnie `Pokaż wynik baseline`, aby obejrzeć
propozycję siatki oraz cropy komórek. Obecny prototyp obsługuje 5 × 3;
wybór 3 × 3 daje jawne `unsupported`. `complete` oznacza status silnika,
nie ręczne zatwierdzenie poprawności. Edytor T03 zbiera osobne decyzje
człowieka. Pilot hybrydy T05 jest dostępny jako jawny wybór; nie zastępuje
domyślnego baseline, ponieważ wynik walidacji nie wykazał poprawy.

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

W istniejącym snapshocie nazwy źródłowych katalogów pozostają niezmienne.
Panel pokazuje nazwy gier z katalogu `game_predictor_traning_set`:
`777`, `blazing`, `gang`, `mumie`, `reels`, `treasure`. To wyłącznie etykiety
widoczne w laboratorium; identyfikatory gier, źródeł, zapisane siatki,
podział danych i nazwy plików nie są przepisywane.

## Powtarzalne uruchomienie po restarcie

### Mumie: etykietowanie zatwierdzonych siatek (TASK-0851)

Aktualny edytor: `http://127.0.0.1:3102/symbols`. Wybierz grę `mumie`.
W „Symbole całej planszy” wybierz zdjęcie i planszę. Komórki są dostępne od
razu; wybierz klasę w każdym polu i zapisz wszystkie 15 pól. Siatki nie trzeba
przesuwać. Alternatywnie w poczekalni zaznacz do 30 wycinków tego samego symbolu,
wybierz klasę i przypisz zaznaczone. Nie zmieniaj zatwierdzonego słownika bez
potrzeby. Sam odczyt nie nadaje etykiet.

Nowa referencja ma 31 zdjęć, 279 plansz i 4185 komórek. Nie importuje ich do
głównej gry. Dawny split pozostaje stale, wszystkie bramki treningu pozostają
aktywne. Potwierdzenie różnych nagrań dla dwóch testowych folderów nie nadaje
verified pozostałym rodzinom. Super i ramka pozostają osobnym etapem.

Trwała konfiguracja tej sesji:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-dataset-version-20261005\runtime.json`.
W nowym PowerShell uruchom kontrolowany launcher (ponowiony Start nie tworzy
drugiej kopii). Start zwraca PID; gotowość sprawdź osobno przez Status:

```powershell
& 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\scripts\vision_lab_symbol_review.ps1' `
  -Action Start -Config 'C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-dataset-version-20261005\runtime.json'
& 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\scripts\vision_lab_symbol_review.ps1' `
  -Action Status -Config 'C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-dataset-version-20261005\runtime.json'
```

Stop z tą samą konfiguracją kończy tylko zapisane, zgodne procesy. Zmiana
geometrii lub słownika blokuje referencję i wymaga nowego jawnego preview;
nie usuwaj splitu i nie ponawiaj legacy rebase. Historyczne instrukcje startu
bez `--symbol-dataset-version` zachowują dotychczasową blokadę stale.

### Ogólny start laboratorium

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
$snapshot = 'C:\Users\tuszy\Documents\game_predictor_vision_data\snapshots\0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2'
$annotations = 'C:\Users\tuszy\Documents\game_predictor_vision_data\annotations\0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2'
$labApi = Start-Process -FilePath '.\.venv-vision-lab\Scripts\python.exe' -ArgumentList @(
  '-m', 'game_predictor_worker.vision_lab', '--snapshot', ('"' + $snapshot + '"'),
  '--annotations', ('"' + $annotations + '"'),
  '--symbols', 'C:\Users\tuszy\Documents\game_predictor_vision_data\symbols\0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2',
  '--manifests', 'C:\Users\tuszy\Documents\game_predictor_vision_data\manifests',
  '--runs', 'C:\Users\tuszy\Documents\game_predictor_vision_data\runs',
  '--training-python', ('"' + (Join-Path $repo '.venv-vision-lab\Scripts\python.exe') + '"')
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

Aktualny zestaw po addytywnym imporcie 2026-09-27 ma 1466 wystąpień
(993 stare i 473 nowe) oraz 1440 unikalnych SHA. Snapshot i nowy store mają
identyfikator `0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2`.
Ścieżki startu powyżej wskazują ten zestaw. Zachowano 180 siatek, 63 akceptacje
i całą historię; nowe zdjęcia nie zostały automatycznie zatwierdzone.
Operacja rebase jest wykonana — nie trzeba jej powtarzać przed startem.
Nie uruchomiono usług automatycznie. [Raport i backup](../quality/VISION_LAB_ADDITIVE_DATA_20260927.md).

Poprzedni import folderu z 2026-09-26 zawiera 993 zdjęcia i ma ID
`82c3c29dd35e17a1df74da249fd8687f86db6be0b781e0bb1a64f1dbbc1962c9`.
Pozostaje zachowany wraz ze swoim store, podobnie jak jeszcze starszy zestaw
1180 zdjęć. Nie uruchamiaj dwóch API zapisujących do różnych kopii podczas pracy.
Poniższa procedura opisuje mechanizm i wcześniejsze przejście 1180 → 993;
jej przykładowych historycznych argumentów nie używaj jako aktualizacji nowego zestawu.

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

W edytorze wybierz numer pozycji albo rozwiń nagłówkiem domyślnie zwinięty
przegląd całego zdjęcia i wybierz obrys. Wczytany zostanie dokładny zapis z jego topologią i cropami.
Pozycje 1–9 są dostępne zawsze, a istniejące dalsze zapisy także pojawiają się
na liście. Brak zapisu wymaga kliknięcia „Nowa propozycja z narożników”.
Topologię pustej pozycji zmienisz bez powrotu do pozycji 1. Wczytanie zapisanej
planszy odtwarza jej topologię bez konwersji.

„Zatwierdź pełną siatkę” potwierdza wszystkie węzły samym jawnym kliknięciem,
bez dodatkowego checkboxa. Po zatwierdzeniu lokalizacji lub pełnej siatki
pozycji 1–8 otwiera się kolejna pozycja tego samego zdjęcia: istniejący zapis
albo niezapisana propozycja. Szkic i pozycja 9 pozostają na miejscu.
Zmiana widoku porzuca niezapisaną pracę bez pytania i bez zapisu. Po utracie odpowiedzi
„Ponów identyczne żądanie” bezpiecznie odtwarza wynik; „Odśwież po konflikcie”
zastępuje edycję aktualnym zapisem bez dodatkowego potwierdzenia.

Powiadomienia pojawiają się w lewym dolnym rogu: sukces zielony, błąd czerwony,
ostrzeżenie pomarańczowe, informacja neutralna. Kliknięcie treści usuwa
komunikat; „Kopiuj” kopiuje samą wiadomość bez zamykania. „Skopiowano”
pojawia się dopiero po sukcesie; brak dostępu do schowka pokazuje błąd
wewnątrz powiadomienia i pozwala ponowić. Wszystkie toasty pozostają 4 s; hover,
focus i ukryta karta wstrzymują zegar. Zamknięcie komunikatu nie usuwa retry.
Raport pomiarów nadal pozostaje w panelu rodzin jako dane.

### Przegląd zdjęcia i poprawki T03d

Przycisk „Szybki przegląd” przy górze otwiera wyłącznie pełne zdjęcie ze
wszystkimi zapisanymi siatkami. Obejmuje wybraną grę albo wszystkie; pomija
zdjęcia bez pełnej obecnej siatki oraz już zaakceptowane lub wymagające poprawy.
„Zatwierdź” i „Odrzuć” zapisują świadomą decyzję, potem pokazują następne.
Odrzucenie nie zmienia siatek ani nie zgłasza każdej planszy osobno: zdjęcie
trafia do „Do poprawy”. W zwykłym edytorze popraw tylko błędne pozycje i
zaakceptuj całe zdjęcie po sprawdzeniu. Sam zapis poprawki nie usuwa odrzucenia.
Przy błędzie zapisu zdjęcie pozostaje do identycznego ponowienia lub jawnego
odświeżenia; do rozstrzygnięcia Powrót jest zablokowany. Po ponownym wejściu
do trybu zapisane decyzje są pomijane. Żadne zdjęcie nie zatwierdza się samo.

Panel „Przegląd całego zdjęcia” pokazuje zapisane pozycje oraz ich statusy.
Numery obrysów pozwalają wybrać dokładną zapisaną siatkę i jej cropy.
Pomarańczowy znak `!` oznacza „Do poprawy”, `↻` — „Do ponownego
sprawdzenia”, a `◀` wskazuje wybraną pozycję. Zaznacz wyłącznie błędne
plansze, opcjonalnie dodaj uwagę i kliknij „Oznacz wybrane: Do poprawy”.
Pozostałe geometrie i ich zatwierdzenia nie zmieniają się. Błędne zgłoszenie
można jawnie wycofać przyciskiem „Wycofaj błędne oznaczenie”.

Zapis poprawianej planszy pozostaje na tej pozycji i zmienia jej status na
„Do ponownego sprawdzenia”; sam szkic lub lokalizacja nie wystarcza do
zamknięcia poprawki. Sprawdź węzły i zatwierdź pełną siatkę. Nieoznaczone
pozycje nadal korzystają ze zwykłego przechodzenia do następnej pozycji.
Na końcu kliknij „Akceptuj całe zdjęcie”: nie trzeba oddzielnie zamykać
każdego „Do ponownego sprawdzenia”, lecz nierozwiązane „Do poprawy” blokuje
akceptację. Wymagana jest przynajmniej jedna pełna obecna siatka, nie dziewięć.
Szkice i lokalizacje nie są przy tej okazji promowane.

Akceptacja dotyczy bieżących zapisanych wersji całego zdjęcia i jego źródła.
Dodanie lub zmiana geometrii na tym zdjęciu unieważnia akceptację; praca na
innym zdjęciu jej nie unieważnia. Starsze zdjęcia domyślnie są nieprzejrzane.
Filtry „Do przeglądu”, „Do poprawy” i „Zaakceptowane” wraz z licznikami
obejmują całą grę. Akceptacja jest dodatkową bramką kwalifikacji/splitu,
nie dowodem gotowości treningowej i nie zmienia roli `777`.

Nawigacja nie pyta o niezapisaną geometrię, wybór ani uwagę; lokalna praca
może zostać porzucona bez zapisu. Opuszczenie karty także nie wyświetla pytania.
Trwający lub niepotwierdzony zapis nadal blokuje nawigację w aplikacji.
Przy niepewnym wyniku zapisu panel zachowuje identyczne żądanie do
ponowienia; nie wysyłaj nowej decyzji, zanim wynik nie zostanie rozstrzygnięty.
Stan przeglądu, historia i potwierdzenia są trwałe oraz objęte backupem.

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

## Kwalifikacja geometrii historycznego 777 (D-453)

Na aktualnym store z sekcji startu wykonano T03h: rewizja 260,
11 zdjęć / 30 pełnych ręcznych siatek ma jawną kwalifikację geometry-only.
Nie jest to wykonany trening ani zatwierdzenie symboli. Backup, integralność
i retry opisuje [raport operacji](../quality/VISION_LAB_ADDITIVE_DATA_20260927.md).
Nie powtarzaj kwalifikacji z nowym request_id bez nowej decyzji; wcześniejsze
żądanie pozostaje identycznym, idempotentnym retry.

T03e udostępnia `python -m game_predictor_worker.vision_lab.qualify_geometry`
z wymaganymi `--snapshot`, `--annotations`, `--request` (plik JSON).
Bez `--apply` jest to wyłącznie odczytowy preview, bez pliku blokady.
Request ma request_id, expected_revision, actor, dokładny game_id,
purpose `geometry`, policy_version `historical-777-lab-geometry-v1`,
decision_reference `D-453` i bindings: source_id, source_sha256 oraz
expected_board_revisions całego zdjęcia. Wartości pochodzą z aktualnego
katalogu i stanu, nie z domysłów o nazwach. `--apply` ponownie sprawdza
cały batch i zapisuje jedną rewizję przez istniejący magazyn anotacji.
Przed realnym apply sprawdź preview i wykonaj backup. Ponowienie po utracie
odpowiedzi używa identycznego requestu/request_id; zmieniony payload daje konflikt.

Zaplanuj import i rebase nowych zdjęć **przed** realnym apply kwalifikacji:
obecny rebase jawnie odrzuca stan z kwalifikacjami lub ich historią.
Backup/restore zachowuje je w nowym katalogu bez nadpisania istniejącego.
Nowy kod nie wykonuje sam operacji na danych ani nie przepina usług.

Kwalifikacja obejmuje tylko pełne ręczne targety geometrii z aktualnie
zaakceptowanych zdjęć historycznego folderu 777. Role, symbole i zdjęcia
pozostają niezmienione. Późniejszy freeze musi jawnie podać purpose geometry
oraz spełnić bramki rodzin, pomiaru i rozłączności. Pominięcie purpose
zachowuje dawny tryb, bez dopuszczenia 777. Zmiany geometrii/review wymagają
aktualnych decyzji; raz oznaczony stale split nie odzyskuje ważności przez retry.

## Jawna kohorta geometrii

Istniejący POST /splits przy purpose geometry przyjmuje opcjonalną listę
geometry_source_ids: jawnie wybrane, unikalne ID źródeł (maksymalnie 10000).
Pominięcie listy zachowuje dotychczasowe reguły. Wybrane źródła muszą mieć
zaakceptowane zdjęcie i pełne ręczne geometrie. Nie zatwierdzaj nieanotowanych
aliasów tylko po to, aby włączyć poprawny target: pozostają w grafie ochrony
przed przeciekiem, bez assignmentu ani skopiowanej zgody.

Pełna rodzina i powiązania każdego wybranego źródła nadal wymagają verified
oraz dozwolonej roli lub własnej kwalifikacji D-453. Pomiar wybiera źródła
z kohorty, wymaga trudności wszystkich członków ich komponentów i dwóch
niezależnych grup na warstwę. Powiązanie z grą niewidzianą nadal blokuje
przeciek. Sam wybór kohorty nie potwierdza pochodzenia ani gotowości treningu.

Wynik zapisuje kohortę, pełne leakage_components i fingerprints także grup
wykluczonych; targety oraz assignments obejmują wyłącznie wybrane źródła.
Źródła poza listą mają NOT_IN_GEOMETRY_COHORT. Zmiana powiązań lub utrata
skuteczności kwalifikacji członka użytej grupy daje stale. Retry po utracie
odpowiedzi musi zachować identyczną listę i jej kolejność. Nowe request_id
nie pozwala nadpisać istniejącego splitu. Nie ma nowego ekranu wyboru kohorty;
rzeczywisty freeze wymaga uprzedniego odczytowego preview i bramek T03.

## Błędne przykłady i ponowny trening

Można wrócić do zdjęcia, poprawić wybrane siatki, zatwierdzić pełną geometrię
i ponownie zaakceptować zdjęcie. Nie trzeba zmieniać poprawnych plansz.
Edycja unieważnia zgodę na poprzednią wersję zdjęcia; kwalifikacja 777 związana
z wcześniejszą mapą rewizji wymaga nowej decyzji. Istniejący zamrożony podział
staje się nieaktualny (`stale`) i nie odzyskuje ważności przez ponowienie żądania.

Należy rozróżniać dwa przypadki:

- Wznowienie po przerwaniu kontynuuje ten sam trening, na tych samych danych
  i konfiguracji. Planowany checkpoint v2 z T04 przechowuje również optimizer,
  scheduler i stan losowania. Nie jest to sposób podmiany błędnych przykładów.
- Trening po poprawieniu danych wymaga nowej wersji zbioru, nowej wersji
  zamrożonego podziału z zachowaniem dotychczasowych ról rodzin i historii
  użycia oraz nowego runu. Nie losuj ponownie podziału po obejrzeniu wyników.
  Stare dane, podział oraz wyniki
  pozostają do porównania. Samo usunięcie przykładu z listy nie usuwa jego
  wcześniejszego wpływu na wagi. Czysty trening lub start sprzed użycia błędu
  nie dziedziczy tego konkretnego wpływu; dalsze dostrajanie nie daje takiej
  gwarancji.

Stan obecny: laboratorium ma edycję, historię, backupy oraz backend runów T04.
Konkretny trener modelu i trening pilota należą do T05. Nie ma kompletnego
workflow nowej wersji po korekcie zamrożonego zbioru. Drugi freeze tego samego magazynu
jest odrzucany (`SPLIT_ALREADY_FROZEN`); restore zachowuje stary split, a rebase
go nie przenosi. Nie kasuj ręcznie tych pól ani nie nadpisuj checkpointów.
Przed implementacją ponownego treningu trzeba domknąć jawny kontrakt wersji.
Korekta materiału wykorzystanego wcześniej do oceny nie jest nowym,
niezależnym testem modelu; raport musi zachować tę informację.

## Izolowane środowisko treningowe T04

Z katalogu repo uruchamiaj osobno poniższe kroki PowerShell. Każdy ma limit
120 sekund; po timeout skrypt kończy wyłącznie swój instalator wraz z dziećmi.
Ponowienie wykorzystuje pobrane pakiety. Główna `.venv` pozostaje bez zmian.

```powershell
pwsh -NoProfile -File scripts/setup_vision_lab.ps1 -Step Create
pwsh -NoProfile -File scripts/setup_vision_lab.ps1 -Step Cuda
pwsh -NoProfile -File scripts/setup_vision_lab.ps1 -Step Dependencies
pwsh -NoProfile -File scripts/setup_vision_lab.ps1 -Step Project
pwsh -NoProfile -File scripts/setup_vision_lab.ps1 -Step Check
```

Pakiety i ich zależności przypina `constraints-vision-lab.txt`, a projekt
instaluje się editable z `--no-deps`. Check uruchamia nowy proces, sprawdza
PyTorch 2.12.1+cu130, torchvision 0.27.1+cu130, CUDA 13.0, GPU i krótkie
obliczenie oraz brak DB/Paddle. Brak CUDA nie przełącza treningu po cichu na CPU.

Do istniejącego polecenia serwera labu można dodać `--manifests <LAB/manifests>`,
`--runs <LAB/runs>` i `--training-python <repo/.venv-vision-lab/Scripts/python.exe>`.
Równoważne zmienne to VISION_LAB_MANIFESTS, VISION_LAB_RUNS i VISION_LAB_PYTHON;
snapshot i anotacje zachowują dotychczasowe opcje. Nie uruchamiaj drugiego API
na zajętym porcie. Brak konfiguracji daje 503, brak zarejestrowanego modelu
T05 — RUN_MODEL_NOT_AVAILABLE. Klient podaje manifest_id, nigdy ścieżkę.

Checkpointy i raporty pozostają pod `<runs>/<run_id>/attempt-N/`. Cancel jest
trwałą intencją, respektowaną na końcu epoki; limit czasu obejmuje też walidację
i eksport. Po twardym zakończeniu ostatnia epoka pozostaje do jawnego retry.
Restart ani odczyt API nie uruchamiają runu automatycznie. Żywy proces przy
starym heartbeat pozostaje running z diagnostyką; nie zabijaj obcego procesu.
Konserwatywne naliczenie czasu po awarii może wyczerpać pozostały limit.

Przed treningiem można wykonać ograniczony odczyt
`scripts/check_vision_lab_manifest.py --snapshot <snapshot> --annotations <store> --manifest <manifest.json>`
w izolowanym interpreterze. Kontrola raportuje dev/validation i rewizję,
nie uruchamia runu, nie dekoduje zdjęć ani nie zapisuje decyzji operatora.

## Jawna hybryda D-457

Wagi `mobilenet_v3_small-047dcff4.pth` pochodzą z
`https://download.pytorch.org/models/mobilenet_v3_small-047dcff4.pth`.
Izolowany cache to `<LAB>/cache`; wymagany pełny SHA256:
`047dcff4addef86ea5bc2eff13c9614dc11f47ab1160d0a71a25e7db994f4e1f`.
Brak albo zmiana wag/presetu blokuje run, bez pobierania w tle i bez losowego fallbacku.
Skrypt `freeze_vision_lab_hybrid_protocol.py --cache <LAB/cache> --manifest-id <id>`
rejestruje preset create-only i wypisuje dokładne dwa requesty do audytu;
nie uruchamia treningu. Nie zmieniaj ani nie nadpisuj zamrożonego presetu.

Odczytowy `preflight_vision_lab_hybrid.ps1` przyjmuje LabRoot, SnapshotId,
ManifestId, Partition, Offset i Limit. Partie są ograniczone do115s oraz60s
bez postępu. Raport podaje matching/missed/errors/czas dla każdego źródła,
wersję protokołu i checksum niezmienionego stanu. Nie dotyka holdoutów ani zgód.
Timeout jest błędem operacyjnym, nie etykietą złej geometrii.

Przed prawdziwymi runami potrzebny jest odbiór kodu, protokołu, coverage i
requestów. Smoke i train startują niezależnie z tych samych pretrained wag;
train nie przejmuje stanu smoke. Samo otwarcie galerii niczego nie trenuje.
Po sukcesie wybierz zdjęcie, kliknij „Odśwież dostępne modele”, a następnie
jawnie wybierz hybrydę. Domyślny wybór nadal to Baseline. Epoka i niekalibrowana
bramka są widoczne w selektorze; wszystkie propozycje wymagają przeglądu.
Brak modeli przed treningiem jest prawidłowym stanem. Modelowe żądania dla
holdoutów są blokowane; nie zmieniaj podziału, by obejść ten warunek.

## Etykiety symboli — kontrakt T06a

Narzędzia T06a są dostępne pod `http://127.0.0.1:3102/symbols` oraz przez
link „Etykiety symboli” na stronie geometrii. Wynik testów opisuje TASK-0671.
Magazyn symboli jest oddzielny od zapisanych siatek. Konfiguracja
`--symbols <LAB/symbols/snapshot-id>` lub `VISION_LAB_SYMBOLS` jest jawna;
bez niej trasy symboli zwracają `SYMBOL_DIRECTORY_NOT_CONFIGURED`, a edytor
geometrii działa jak wcześniej. Nie wskazuj katalogu snapshotu, anotacji,
manifestów lub runów ani ich nadrzędnego katalogu.

Kolejność pracy: utwórz słownik wybranej gry, zapisz wersję, zatwierdź
słownik, następnie oceń symbole na zapisanej planszy. Sam zapis wersji słownika
nie zatwierdza jej ani obrazów. Nieznany symbol, nieczytelny obraz i błędna
siatka to osobne stany review, nie klasy treningowe. Zmiana zatwierdzonego
słownika lub geometrii wymaga ponownej zgody na zależne etykiety.

W słowniku kliknij „Dodaj klasę” i wpisz tylko nazwę, np. „Cytryna”.
ID i kod powstają automatycznie. Poprawienie literówki zachowuje tożsamość
symbolu; inny rodzaj symbolu dodaj jako nową pozycję. Istniejące wpisy nie
wymagają ponownego tworzenia. Zapis i zatwierdzenie wersji są nadal osobne.

Sekcja „Symbole całej planszy” zastępuje wybór pojedynczej komórki. Wybierz
zdjęcie i zapisaną pełną planszę. U góry zobaczysz planszę z siatką, poniżej
15 dokładnych cropów i małe selecty ułożone 5 × 3. Numery czytaj rzędami,
od lewej do prawej. Dla geometrii 3 × 3 panel pokazuje 9 pól.
Ustaw symbol albo jawny stan dla każdego pola, następnie zapisz całą planszę.
Aktualne zapisane wybory są wczytywane; możesz zmienić tylko błędne.
Zapis utrwala komplet atomowo. Przy niepotwierdzonym wyniku użyj ponowienia
identycznego zapisu; nie zmieniaj wyborów przed rozstrzygnięciem żądania.
Zmiana zdjęcia lub planszy poza zapisem porzuca niezapisane wybory, bez autosave.

Sekcja „Poczekalnia cropów” na tej samej stronie zbiera nieprzypisane pola
z już zatwierdzonych zdjęć i pełnych siatek wybranej gry. Miniatury można
przeglądać przed utworzeniem słownika, ale przypisanie wymaga jego
zatwierdzonej wersji. Utwórz w istniejącym „Słowniku gry” symbol, np.
„Cytryna”, i zatwierdź słownik. W poczekalni zaznacz jeden lub kilka cropów,
wybierz ten symbol i kliknij „Przypisz zaznaczone”. Można też zaznaczyć
wszystkie widoczne cropy; jedna strona i jeden zapis obejmują najwyżej 30.
Przed zapisem sprawdź każdą miniaturę: zbiorcze przypisanie nadaje wszystkim
zaznaczonym ten sam symbol. Status „Do ponownej oceny” oznacza nieaktualną
wcześniejszą decyzję, a nie nowy rodzaj symbolu. Cofnięcie wcześniejszej
decyzji wraca do „Nieprzypisane”. Poczekalnia jest widokiem pochodnym;
nie tworzy kopii obrazów ani drugiej grupy symboli. Możesz nadal opisywać
całą planszę w dotychczasowym edytorze. Nowe zdjęcia trzeba dodać osobnym
workflow; ta sekcja korzysta tylko z materiału obecnego snapshotu.

Poprawna etykieta nie oznacza jeszcze dopuszczenia do treningu. T06b wymaga
osobnej kontroli pochodzenia i podziału symboli. Historyczne 777 oraz gry
zamrożone jako holdout nie otrzymują zgody symbolowej przez wcześniejsze
zatwierdzenie siatek. Nie obchodź komunikatu blokady przez zmianę roli.

## Snapshot treningowy geometrii produkcyjnej i przegląd etykiet (TASK-0801)

Snapshot buduje skrypt `scripts/vision_lab_production_snapshot.py` z manifestu
kandydatów TASK-0800 (`VISION_LAB_EXPORT.md`). Skrypt nie łączy się z bazą, a
zdjęcia czyta tylko do odczytu z `<artifact-root>\data`. Najpierw podgląd (nic nie
kopiuje ani nie zapisuje; liczności, rozmiar kopii, blokady), potem budowa:

```powershell
$candidates = 'C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry\production-geometry-777-20261002\candidates.jsonl'
$artifacts = 'C:\Users\tuszy\Documents\game_predicotr\artifacts'
$out = 'C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry-snapshots'
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @(
  'scripts/vision_lab_production_snapshot.py', 'preview', '--candidates', ('"' + $candidates + '"'),
  '--artifact-root', ('"' + $artifacts + '"'), '--output-root', ('"' + $out + '"'), '--seed', '801'
) -PassThru -NoNewWindow
if (-not $p.WaitForExit(300000)) { $p.Kill($true); throw 'Preview timeout 300 s' }
```

Zamiana `preview` na `build` (limit 900 s) kopiuje zdjęcia po kontroli SHA-256 i
publikuje atomowo `<output-root>\<snapshotId>`. Kod wyjścia 2 oznacza blokadę
(za mało zdjęć w roli, pusta pula, udział rodziny ponad limit albo kopia ponad
`--max-copy-gib`, domyślnie 3); wtedy nic nie jest kopiowane. Ponowne uruchomienie
z tym samym ziarnem i wejściem daje ten sam ID, weryfikuje opublikowany katalog i
niczego w nim nie zmienia. Opublikowany snapshot z 2026-10-02:
`3ff448c620a71f3a28e467cfdfeb77c7e46325e73ca25eaabcb35a56e0b7727d` (6 000 trening,
600 development, 102 zdjęcia złote); liczności i reguły podziału opisuje
`ai_docs/quality/GRID_V3_TRAINING_SNAPSHOT_20261002.md`. Nie zmieniaj plików w
katalogu snapshotu: kontrola sum kontrolnych odrzuci go.

Polityka podziału: `--policy production-geometry-split-v1` (domyślna) albo
`--policy production-geometry-split-v2` (TASK-0813). v2 przed wyborem developmentu
wyłącza z treningu całe rodziny z planszami G (malejąco po planszach G na 1 000
zdjęć po filtrze, dopóki wyłączone mają < 30% plansz G i utrata puli treningowej
≤ 20%), więc część zbioru złotego leży w rodzinach niewidzianych w treningu
(`familySeenInTraining = false`). Gdy progi się wykluczają, skrypt kończy się błędem
`HELDOUT_GOLD_THRESHOLDS_IRRECONCILABLE` i niczego nie kopiuje; pusta część
niewidziana blokuje budowę (`HELDOUT_GOLD_SUBSET_EMPTY`). Opublikowany snapshot v2
z 2026-10-02 (ziarno 801):
`286f2e370aa84437c63fcffe202f01260d6ca13aee317eb8c11cac2ad0f2df59` (6 000 trening,
600 development, 102 zdjęcia złote, z nich 249 plansz G w rodzinach niewidzianych).
Tylko v2 ma niepusty podzbiór złota z rodzin niewidzianych; snapshot v1 pozostaje
bez zmian.

Przegląd etykiet: 600 plansz (300 S i 300 B, ziarno 801) przygotowano w
`C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry-snapshots\label-review-seed801`
(polecenie `label-review` tego samego skryptu z `--output`). Uruchom stronę
przeglądu jako kontrolowany proces w tle:

```powershell
$review = 'C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry-snapshots\label-review-seed801'
$labReview = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @(
  '-m', 'game_predictor_worker.vision_lab.label_review', 'serve', '--review', ('"' + $review + '"')
) -WindowStyle Hidden -PassThru
"Review PID: $($labReview.Id)"
```

Otwórz `http://127.0.0.1:8103`. Klawisze: `G`/`1` dobra, `Z`/`2` zła, `N`/`3` nie
da się ocenić, `→` pomiń, `←` wstecz, `U` cofnij decyzję bieżącej planszy, `H`
ukryj/pokaż siatkę, `S` podsumowanie. Oceniaj, czy siatka 5 × 3 leży na planszy
(linie między symbolami, wszystkie 15 pól na właściwych symbolach); strona nie
pokazuje poziomu S/B. Każda decyzja trafia od razu do `history.jsonl` i
`decisions.json` w katalogu przeglądu, więc zamknięcie strony lub procesu niczego
nie traci, a ponowne uruchomienie wraca do pierwszej nieocenionej planszy. Port
8103 musi być wolny; serwer słucha tylko na `127.0.0.1`. Zatrzymanie w tej samej
sesji: `Stop-Process -Id $labReview.Id`, a następnie sprawdź
`Get-CimInstance Win32_Process -Filter "Name='python.exe'"` pod kątem procesu
potomnego `label_review` (launcher venv uruchamia drugi proces Pythona).

Raport odsetka błędów (zapisuje `summary.json`; odsetek „zła” wśród dobra + zła per
poziom z przedziałem Wilsona 95%):

```powershell
.\.venv\Scripts\python.exe -m game_predictor_worker.vision_lab.label_review report --review $review
```

Runda druga przeglądu (TASK-0814): ponowna ocena plansz „zła” (opcjonalnie także „nie
da się ocenić”) z trzecią oceną „lekko nacięta”. Dane rundy leżą w tym samym
katalogu przeglądu w osobnych plikach (`round2.json`, `round2-history.jsonl`,
`round2-decisions.json`, `round2-summary.json`); pliki pierwszej rundy (`sample.json`,
`crops/`, `history.jsonl`, `decisions.json`) są tylko czytane. Zestaw pozycji
zamraża `round2-prepare` na podstawie `history.jsonl` w chwili przygotowania;
ponowne przygotowanie kończy się błędem `LABEL_REVIEW_ROUND2_EXISTS`, a `--force`
odkłada stare pliki rundy jako `*.superseded-<czas UTC>` (nic nie kasuje).

```powershell
$py = '.\.venv\Scripts\python.exe'; $m = 'game_predictor_worker.vision_lab.label_review'
& $py -m $m round2-prepare --review $review                          # tylko „zła”
& $py -m $m round2-prepare --review $review --include bad-unreadable # „zła” i „nie da się ocenić”
$round2 = Start-Process -FilePath $py -ArgumentList @(
  '-m', $m, 'round2-serve', '--review', ('"' + $review + '"'), '--port', '8104'
) -WindowStyle Hidden -PassThru
& $py -m $m round2-report --review $review                           # raport łączony
```

Strona `http://127.0.0.1:8104` (tylko `127.0.0.1`): `G`/`1` dobra, `L`/`2` lekko
nacięta, `Z`/`3` zła, `N`/`4` nie da się ocenić, `→` pomiń, `←` wstecz, `U` cofnij,
`H` siatka, `S` podsumowanie. Reguła: dobra — linie w przerwach między symbolami albo
minimalnie zahaczają o brzeg; lekko nacięta — symbol w pełni rozpoznawalny, ale linia
wyraźnie go nacina; zła — przesunięcie lub przechył siatki, część sąsiedniego symbolu w
komórce, zła liczba kolumn lub rzędów, nie ta plansza. Raport łączony (`round2-summary.json`):
dla pozycji z rundą drugą obowiązuje jej ocena (nieocenione jeszcze w rundzie drugiej
zachowują zamrożoną ocenę pierwszej), dla pozostałych bieżąca ocena pierwszej rundy.
Per poziom: odsetek luźny = zła / (dobra + lekko nacięta + zła), odsetek ścisły =
(zła + lekko nacięta) / (dobra + lekko nacięta + zła), „nie da się ocenić” i pozycje bez
oceny poza mianownikiem, przedziały Wilsona 95% dla obu odsetków oraz liczba pozycji
pierwszej rundy bez oceny (`firstRoundUndecided`).

## Sieć `neural_grid` — runy treningowe (TASK-0802)

Silnik `neural_grid` (dwa stopnie: ekran 768 px → quady plansz, plansza 320 × 192
→ 24 węzły + dopasowanie siatki projekcyjnej) trenuje się wyłącznie przez trwały
protokół runów w osobnym katalogu
`C:\Users\tuszy\Documents\game_predictor_vision_data\neural-grid-runs` i wyłącznie
interpreterem GPU `.venv-vision-lab` (brak GPU = `RUN_GPU_UNAVAILABLE`, bez treningu
na CPU). Kod czyta z snapshotu v2 tylko role `training` i `development`; każda inna
rola (`gold`, `final_test`, `unseen_game`) kończy się błędem
`NEURAL_GRID_ROLE_FORBIDDEN` przed otwarciem snapshotu. Presety A/B/C leżą w
`services/worker/src/game_predictor_worker/vision_lab/neural_grid_presets/` i są
zamrożone fingerprintem w `neural_grid_protocol.py`; zmieniony plik presetu nie
przejdzie walidacji (nowy preset = nowa zgoda).

Budżet D-481 pilnuje kod: najwyżej 3 runy `train` (po jednym na preset), każdy
najwyżej 14 400 s liczone od startu procesu; przerwany run nie oddaje budżetu,
`resume` kontynuuje ten sam run z pozostałym czasem. Smoke (≤ 50 kroków) nie
liczy się do budżetu. Tylko jeden run naraz (`RUN_BUSY`); nie uruchamiaj treningu
równolegle z ciężkimi operacjami bazy ani testami PG (limit 8 GB VM WSL). Worker
prosi Windows o brak uśpienia bezczynności na czas swojego życia; zamknięcie
pokrywy albo ręczne uśpienie zawiesza run, a czas biegnie dalej.

```powershell
$env:PYTHONPATH = 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src'
$py = 'C:\Users\tuszy\Documents\game_predicotr\.venv-vision-lab\Scripts\python.exe'
$m = 'game_predictor_worker.vision_lab.neural_grid_runs'
& $py -m $m status                                  # runy, budżet, postęp, ostatnia strata
& $py -m $m start --preset A --purpose smoke --request-id ng-smoke-a-<data>
& $py -m $m start --preset B --purpose train --request-id ng-train-b-<data>   # tylko za zgodą
& $py -m $m stop --run <run_id>                     # kooperacyjnie (koniec rundy, ewaluacja, checkpoint)
& $py -m $m stop --run <run_id> --kill              # natychmiast; po 60 s failed/RUN_LEASE_EXPIRED
& $py -m $m resume --run <run_id>                   # wznowienie z ostatniego checkpointu
& $py -m $m evaluate --run <run_id>                 # development, najlepszy stan, GPU
& $py -m $m export --run <run_id> --parity-images 16
& $py -m $m timing --bundle <run_root>\<run_id>\exports\<katalog> --images 30 --threads 4
& $py -m $m reference --screen-layout-limit 600     # odniesienie produkcji + baseline labu (CPU ~1,75 h)
```

`start` uruchamia odłączony proces workera (ukryta konsola, osobna grupa procesów),
który przeżywa zamknięcie terminala; log, postęp (`progress.json`) i straty
(`losses.jsonl`) są w `<run_root>\<run_id>\attempt-<n>\`. `evaluate` i `export`
odmawiają pracy, gdy jakiś run jest aktywny. Po przeniesieniu kodu do głównego
checkoutu ustaw `PYTHONPATH` na `services\worker\src` tego checkoutu; ścieżka kodu
dla wznowień jest zapisana w `settings.json` katalogu runów (`pythonpath`). Wyniki,
metryki i presety opisuje `ai_docs/quality/GRID_V3_NEURAL_GRID_RUNS_20261002.md`.
## Bramka `hybrid_v3` — kalibracja (TASK-0803)

`hybrid_v3` (`vision_lab/hybrid_v3_engine.py`, logika w `hybrid_v3_gate.py`) łączy
siatki odniesienia (wejście zdjęcia: w aplikacji wynik silnika produkcyjnego, w labie
etykiety snapshotu) z siatkami `neural_grid` pod kontraktem `GeometryEngine`. Plansza
jest `confident` (`status: complete`) tylko przy zgodności quadów i węzłów obu źródeł;
każda inna dostaje `needs_review` z powodem `HYBRID_V3_*`; plansza tylko z sieci nigdy
nie jest pewna. Zdjęcie jest pewne tylko, gdy wszystkie plansze są pewne i liczby plansz
obu źródeł są równe (pierwszy powód wyniku: `HYBRID_V3_PHOTO_CONFIDENT` albo
`HYBRID_V3_PHOTO_NEEDS_REVIEW`). Wynik służy wyłącznie do review/shadow (D-461).

Kalibracja progów czyta tylko rolę `development` (inna rola, także `training`, kończy
się `RoleForbiddenError` przed otwarciem snapshotu), używa eksportu ONNX na CPU i zapisuje
wyniki w nowym katalogu obok runu; siatka progów i reguła wyboru są stałymi w
`hybrid_v3_calibration.py`. Nie wymaga GPU i może działać równolegle z treningiem (4 wątki
CPU, ok. 2,5 min na 600 zdjęć).

```powershell
$env:PYTHONPATH = 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src'
$r = 'C:\Users\tuszy\Documents\game_predictor_vision_data\neural-grid-runs\<run_id>'
.\.venv\Scripts\python.exe -m game_predictor_worker.vision_lab.hybrid_v3_calibration `
  --bundle "$r\exports\<katalog_eksportu>" --output "$r\hybrid-v3-calibration" --threads 4 `
  --evaluation "$r\evaluations\<plik_ewaluacji>.json"   # --reuse-network: bez ponownej inferencji
```

Wynik, krzywą pokrycie–błąd i znaczenie liczb opisuje
`ai_docs/quality/GRID_V3_HYBRID_GATE_20261002.md`. Progi wybrane dla runu 1 są w
`hybrid_v3_engine.RUN1_DEVELOPMENT_THRESHOLDS`; inny model wymaga nowej kalibracji.

## Kompletne zdjęcia Mumie, Blazing i Gang z propozycjami sieci (TASK-0824, D-490)

Osobna strona `http://127.0.0.1:8105` (tylko `127.0.0.1`) służy do przeglądu zdjęć
gier Mumie, Blazing i Gang z propozycjami siatek sieci `neural_grid` runu 1. Zapis
idzie wyłącznie do istniejącego magazynu anotacji labu (blokada, rewizja CAS,
potwierdzenia, historia); nie ma równoległego magazynu. Reels i Treasure są
wyłączone (strażnik w kolejce, w generatorze propozycji, na stronie i w zapisie).

Start i zatrzymanie z katalogu repozytorium (jedna komenda, proces w tle):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\vision_lab_assisted_annotation.ps1 -Action Start
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\vision_lab_assisted_annotation.ps1 -Action Stop
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\vision_lab_assisted_annotation.ps1 -Action Status
```

Start czeka najwyżej 60 s na gotowość i wypisuje adres; zajęty port 8105 albo
działająca już strona nie uruchamia drugiej kopii. Stop kończy wyłącznie procesy tej
strony na tym porcie (także proces potomny launchera venv). Logi:
`<LAB>\assisted-annotation\logs`. Nie uruchamiaj równolegle API labu 8102 piszącego do
tego samego magazynu — zapis jest chroniony blokadą, ale druga strona zgłosi
„Magazyn anotacji zajęty” albo konflikt rewizji.

Kolejka: najpierw Mumie, potem Blazing i Gang. Obejmuje zdjęcia folderu
`game_predictor_traning_set\{mumie,blazing,gang}` (dopasowane po SHA-256 do źródeł
katalogu labu; identyfikatory i rodziny pochodzą z katalogu) oraz wcześniej
anotowane zdjęcia labu tych gier. Propozycje leżą w niezmiennym artefakcie
`<LAB>\assisted-annotation\proposals\<id>\proposals.json` (suma kontrolna, wersja
modelu, katalog eksportu ONNX) i **nie są etykietami**. Ponowne wygenerowanie
(`python -m game_predictor_worker.vision_lab.assisted_annotation proposals ...`,
CPU, najwyżej 4 wątki, ok. 0,3 s na zdjęcie) odmawia nadpisania istniejącego zbioru.

Na zdjęciu: pomarańczowa przerywana siatka to propozycja sieci, zielona —
zaakceptowana, ciemnozielona z literą `L` — wcześniejsza praca w labie
(zablokowana; zmiana tylko w edytorze T03), żółta — cofnięta akceptacja, różowa —
zmieniona albo nowa. Liczba na planszy to numer pozycji 1–9 (rzędami, od lewej);
dla propozycji i nowych plansz jest wyliczany z układu, a przy „?” albo kolizji
ustaw go klawiszem `1`–`9`. Propozycja pokrywająca zapisaną planszę jest ukryta.

| Klawisz | Działanie |
|---|---|
| `A` / `Enter` | akceptuj zaznaczoną planszę (zapis pełnej siatki) |
| `Tab` / `Shift+Tab` | następna / poprzednia plansza |
| przeciągnięcie narożnika | korekta; siatka 5 × 3 liczona projekcyjnie z 4 narożników |
| `1`–`9` | numer pozycji nowej planszy lub propozycji |
| `N` | nowa plansza: kliknij 4 narożniki w kolejności LG, PG, PD, LD (`Esc` przerywa) |
| `X` / `Delete` | odrzuć propozycję / usuń planszę zaakceptowaną w tym przepływie |
| `R` | cofnij akceptację planszy |
| `U` / `Ctrl+Z` | cofnij ostatnie przesunięcie narożnika |
| `C`, liczba, `Enter` | potwierdź liczbę plansz i zatwierdź zdjęcie |
| `Spacja` / `PageDown`, `PageUp` | następne / poprzednie zdjęcie |
| `J` | następne niekompletne zdjęcie |
| `Z` | powiększenie zaznaczonej planszy / całe zdjęcie |
| `H` | ukryj / pokaż siatki |
| `O` | pokaż odrzucone propozycje (`X` na odrzuconej przywraca) |
| `Y` | ponów identyczne żądanie po utracie odpowiedzi |

Pochodzenie każdej zaakceptowanej siatki jest zapisane: propozycja bez zmian,
propozycja poprawiona (z identyfikatorem i sumą propozycji oraz przesunięciem
narożników) albo narysowana ręcznie; plansze sprzed tego przepływu mają pochodzenie
„wcześniejsza praca w labie”. Zdjęcie jest **kompletne** dopiero po wpisaniu liczby
plansz równej liczbie zaakceptowanych siatek, gdy żadna plansza nie ma cofniętej
akceptacji (D-484). Zatwierdzenie wiąże rewizje wszystkich plansz i obejmuje
akceptację zdjęcia T03d; cofnięcie akceptacji, usunięcie, dodanie planszy albo zmiana
w edytorze T03 cofa kompletność. Plansza częściowo poza kadrem nie przejdzie zapisu
(`GEOMETRY_OUTSIDE_SOURCE`) — takie zdjęcie pomiń (`Spacja`), wyjątek D-484 wymaga
osobnej decyzji. Dodanie planszy do wcześniej zaakceptowanego zdjęcia labu unieważnia
jego akceptację T03d do czasu zatwierdzenia kompletu.

Każda decyzja jest od razu trwała; zamknięcie przeglądarki lub zatrzymanie strony
traci tylko niezaakceptowane przesunięcia narożników. Strona wraca do ostatniego
zdjęcia. Nagłówek pokazuje licznik kompletnych zdjęć na grę, czas aktywny na
bieżącym zdjęciu (przerwy powyżej 30 s nie są liczone), średni czas na kompletne
zdjęcie i średnią z pierwszych 10. Uwaga: pierwszy zapis w magazynie oznacza
zamrożony podział pilota D-456 jako `split_stale` (zachowanie magazynu przy każdej
zmianie geometrii); podział, manifesty i wyniki T05 pozostają bez zmian, lecz runy
labu na manifeście D-456 zwrócą `RUN_DATA_DRIFT`.

Eksport kompletnych zdjęć dla snapshotu treningowego runu 3:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\vision_lab_assisted_annotation.ps1 -Action Export
```

Tworzy (bez nadpisywania) `<LAB>\assisted-annotation\exports\<export_id>\` z
`complete-photos.jsonl` (zdjęcie → plansze w kolejności czytania → 24 węzły, quad,
pozycja, pochodzenie, rewizje, gra, rodzina, SHA-256 źródła, wymiary po EXIF) i
`manifest.json` (sumy kontrolne, liczności na grę, rewizja magazynu, zbiór
propozycji). Ten sam stan daje ten sam identyfikator. Funkcja
`assisted_annotation.write_reader_snapshot` zamienia wiersze na katalog w formacie
`production-geometry-snapshot-v1` czytany przez `neural_grid_data.load_samples`;
podział na trening i odłożoną ocenę należy do następnego zadania.

### Automatyczne zamykanie, tylko Mumie, nowe propozycje (TASK-0825)

- **Zamykanie samoczynne.** Po akceptacji (`A`) planszy strona zamyka zdjęcie, gdy
  operator zaakceptował wszystkie jego plansze: każda zapisana plansza ma pełną
  akceptację (bez cofniętej akceptacji i bez szkicu), każda pokazana propozycja jest
  odrzucona, użyta albo przykryta zapisaną planszą, a co najmniej jedna plansza
  została zaakceptowana w tym narzędziu. Liczba plansz = liczba zaakceptowanych;
  strona przechodzi do następnego niekompletnego zdjęcia. Strona nie zamyka zdjęcia,
  gdy trzyma niezapisaną nową albo przesuniętą planszę. `C` zostaje jako korekta
  (np. po cofnięciu akceptacji `R`).
- **Jednorazowe zamknięcie wcześniejszej pracy** (zdjęcia z kompletem akceptacji bez
  potwierdzonej liczby): najpierw podgląd, potem zapis.

  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\vision_lab_assisted_annotation.ps1 -Action CloseFinished
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\vision_lab_assisted_annotation.ps1 -Action CloseFinished -Apply
  ```

  Każde zdjęcie jest sprawdzane na bieżącym stanie tuż przed zapisem (praca operatora
  w tym czasie nie zostanie nadpisana); autor zapisu `operator-auto-close`. Zdjęcia
  wyłącznie z wcześniejszą pracą labu (`ASSISTED_NO_WORKFLOW_ACCEPTANCE`) nie są
  zamykane.
- **Tylko Mumie.** Skrypt domyślnie uruchamia stronę, status, eksport i zamykanie z
  `-Games mumie`: kolejka i liczniki obejmują tylko Mumie, nagłówek pokazuje „ukryte:
  Blazing, Gang”. Dane tych gier pozostają w magazynie i propozycjach bez zmian
  (`-Games mumie,blazing,gang` przywraca pełną kolejkę).
- **Nowe propozycje po doszkoleniu.** Katalog propozycji może zawierać kilka zbiorów:
  zbiór bazowy runu 1 i zbiory iteracji doszkalania (pole `generation`). Działająca
  strona wczytuje nowy zbiór przy następnym odświeżeniu kolejki lub zdjęcia (bez
  restartu); dla zdjęcia pokazuje najnowszy zbiór, który je obejmuje (pod nazwą pliku:
  „propozycje po doszkoleniu, iteracja N” albo „propozycje runu 1”). Zaakceptowane
  wcześniej plansze zachowują identyfikator swojego zbioru.

## Iteracyjne doszkalanie `neural_grid` na Mumiach — run 3 (TASK-0825, D-490)

Run 3 budżetu D-481 to jeden run z presetem D (doszkalanie najlepszego stanu runu 1)
podzielony na iteracje. Jedna komenda wykonuje iterację: eksport zamkniętych zdjęć
Mumii → trwały przydział holdoutu (co piąte zdjęcie) → snapshot iteracji →
doszkolenie na GPU (odłączony worker, 300–900 s treningu) → ocena (holdout Mumii,
600 zdjęć development 777) → eksport ONNX → nowe propozycje dla zdjęć jeszcze
niezamkniętych → raport. Wszystkie iteracje razem mieszczą się w 14 400 s (kod
odmawia iteracji, gdy budżet się kończy); czwartego runu nie da się uruchomić.

```powershell
$env:PYTHONPATH = 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src'
$py = 'C:\Users\tuszy\Documents\game_predicotr\.venv-vision-lab\Scripts\python.exe'
$f = 'game_predictor_worker.vision_lab.neural_grid_finetune'
& $py -m $f status            # budżet runu 3, holdout, wyniki iteracji
& $py -m $f iterate           # jedna iteracja; po przerwaniu ta sama komenda wznawia
& $py -m $f iterate --smoke --root <katalog_tymczasowy> --annotations <kopia_magazynu> --proposals <kopia_propozycji>
```

Reguły od iteracji 2 (preset E, D-490): przyjęte po obejrzeniu iteracji 1 presetu D.
Kandydat jest dopuszczalny, gdy na 600 zdjęciach development 777 (a) zdjęcia poziomu B
są kompletne i poprawne nie gorzej niż run 1 − 0,5 pkt proc. (run 1: 298/300), (b)
image-macro nie jest gorsze niż w runie 1 i (c) wykrycie plansz = 100% przy 0
fałszywych; spośród dopuszczalnych wygrywa najniższe image-macro holdoutu Mumii.
Przełączenie jest automatyczne — nie ma osobnej komendy: pierwsze `iterate` iteracji 2
zapisuje zmianę reguł w ledgerze. To ten sam run i ten sam budżet (czas iteracji 1
zostaje zużyty, czwartego runu nie ma); `status` pokazuje `rules_revisions` i
`next_iteration_rules_preset`.

Wymagania przed iteracją: żaden inny run nie jest aktywny (`RUN_BUSY`), są nowe
zamknięte zdjęcia Mumii (inaczej `NEURAL_GRID_FINETUNE_NO_NEW_PHOTOS`; wyjątek:
poprzednia iteracja nie wybrała nowego stanu — wtedy te same zdjęcia są użyte
ponownie i raport to odnotowuje). Strona
anotacji może działać w tym czasie: eksport czyta magazyn przez krótką blokadę, a nowy
zbiór propozycji strona wczyta sama. Wyniki: `neural-grid-runs\finetune-D\iterations\NN\report.md`
(po polsku) i `report.json`; ledger z przydziałem holdoutu:
`neural-grid-runs\finetune-D\ledger.json`; eksport ONNX iteracji:
`neural-grid-runs\<run>\exports\iterationNN-<checkpoint>`. Szczegóły presetu, budżetu i
pomiaru: `ai_docs/quality/GRID_V3_NEURAL_GRID_RUNS_20261002.md`, sekcja „Run 3”.
