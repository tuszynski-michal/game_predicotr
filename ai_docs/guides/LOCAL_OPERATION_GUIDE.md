---
title: Local operation guide
status: active
last_updated: 2026-08-24
---

# Lokalne uruchamianie i instalacja

Instrukcja jest przeznaczona dla właściciela projektu i zakłada Windows
PowerShell oraz repozytorium:

```text
C:\Users\user\Documents\game_predicotr
```

Aplikacja mobilna działa całkowicie offline. Panel Admin, Admin API,
PostgreSQL, worker i Reviewer są lokalnymi narzędziami do przygotowywania
danych, ich weryfikacji oraz budowania APK. Telefon nie łączy się z żadnym z
tych procesów.

Audyt mutacji lokalnego Admina znajduje się w
`artifacts\admin-audit\local-admin-events.jsonl`. Plik jest append-only i należy
go objąć backupem razem z pozostałymi artefaktami. Nie edytuj go ręcznie;
zatrzymaj API przed kopiowaniem spójnej kopii operatorskiej.

## Najkrótsza procedura na kolejny dzień pracy

1. Uruchom Docker Desktop.
2. Otwórz PowerShell w katalogu repozytorium.
3. Uruchom bazę i migracje:

```powershell
npm run db:up
npm run db:migrate
```

4. Uruchom oba workery w kontrolowanym tle:

```powershell
npm run workers:start
```

5. Uruchom osobne okna PowerShell:

| Okno | Komenda | Kiedy jest potrzebne |
|---|---|---|
| 1 | `npm run api:dev` | zawsze dla Admina i Reviewera |
| 2 | `npm run admin:dev` | podczas pracy w panelu Admin |
| 3 | `npm run reviewer:dev` | podczas zatwierdzania plansz |

6. Otwórz Admin pod `http://127.0.0.1:3000/`.
7. Reviewer otwieraj wyłącznie przez link i kod utworzone w sekcji
   `Zatwierdzanie`.

## Jednorazowe przygotowanie Windows

Repozytorium wymaga Node `>=22.13 <25`, npm `>=11 <12`, Python 3.12,
Microsoft OpenJDK 17, Android SDK 36, ADB oraz Docker Desktop z Linux
containers.

W tym workspace lokalny toolchain znajduje się w ignorowanym katalogu
`.tooling`. Zapisz jego ścieżki i zmienne na stałe dla bieżącego użytkownika:

```powershell
npm run windows:environment:setup
```

Skrypt zapisuje:

- ścieżki Node.js i npm,
- `JAVA_HOME`,
- `ANDROID_HOME` i `ANDROID_SDK_ROOT`,
- `GAME_PREDICTOR_GRADLE_USER_HOME`,
- wpisy jednego kanonicznego `Path` dla Node, Javy, ADB, Android command-line
  tools i Docker CLI.

Windows traktuje nazwy `Path` i `PATH` jako tę samą zmienną. Repozytorium nie
wymaga dwóch wpisów i normalizuje odziedziczony proces do jednego `Path`.
Regresję uruchamiania procesu z przekierowanymi logami można sprawdzić przez:

```powershell
npm run windows:environment:smoke
```

Zamknij wszystkie stare okna PowerShell i otwórz nowe. Następnie sprawdź:

```powershell
node --version
npm --version
java -version
adb version
docker --version
npm run windows:environment:check
```

Aktualna konfiguracja referencyjna to Node `24.14.0`, npm `11.18.0`, JDK
`17.0.20`, Android Platform/Build Tools 36 oraz ADB `1.0.41`.

Jeżeli zależności repozytorium albo `.venv` nie istnieją, wykonaj bootstrap:

```powershell
npm install
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Polecenie `py -3.12` wymaga zainstalowanego Pythona 3.12. Jeżeli izolowanego
JDK/Android SDK brakuje, przygotuj go przed ponownym zapisaniem środowiska:

```powershell
npm run android:toolchain:setup
npm run windows:environment:setup
```

Domyślna konfiguracja aplikacji jest bezpieczna i działa bez kopiowania
[`.env.example`](../../.env.example). Plik ten jest listą opcjonalnych
zmiennych; repozytorium nie wczytuje go automatycznie do bieżącego PowerShell.

## Uruchomienie panelu Admin

Uruchom Docker Desktop. Następnie w katalogu repozytorium:

```powershell
npm run db:up
npm run db:migrate
npm run db:current
```

`db:up` czeka na healthcheck. Dane są zachowywane w wolumenie Dockera, więc
zwykłe zatrzymanie bazy ich nie usuwa.

W pierwszym oknie PowerShell uruchom API:

```powershell
npm run api:dev
```

Tryb `api:dev` obserwuje wyłącznie `services/api/src` i automatycznie przeładowuje
API po zmianie kodu Pythona. Dzięki temu uruchomiony Admin nie korzysta ze
starszego kontraktu endpointów. Po aktualizacji repozytorium ze starszej wersji
tego skryptu zatrzymaj istniejące API raz skrótem `Ctrl+C` i uruchom je ponownie;
od kolejnych zmian ręczny restart nie jest potrzebny.

Możesz potwierdzić jego gotowość w drugim oknie:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

W kolejnym oknie uruchom panel:

```powershell
npm run admin:dev
```

Otwórz `http://127.0.0.1:3000/`. Dokumentacja API jest dostępna lokalnie pod
`http://127.0.0.1:8000/docs`.

Ogólne joby w stanie `created`, w tym właściwy `Import layoutów`, wymagają
general workera. Ten sam general worker wykonuje także bounded host actions
zdalnej ręcznej selekcji przed próbą pobrania zwykłego joba; po restarcie
reconciliuje istniejące verified uploady i publikuje brakujące `seq_*`.
`Selekcja zdjęć` ma odrębny lane i drugi proces. Domyślna komenda uruchamia
obecnie wyłącznie general workera w kontrolowanym tle i natychmiast zwraca
terminal:

```powershell
npm run workers:start
```

Ponowne wywołanie nie tworzy duplikatów. Status konsoli zawiera PID, czas
startu, budżet wątków oraz osobne ścieżki logów każdego lane:

```powershell
npm run workers:status
```

Oba lane korzystają z tego samego API, PostgreSQL i panelu Admin, ale nie
blokują swoich kolejek. Można uruchomić tylko potrzebny proces. Przy pracy
równoległej konkurują o CPU, RAM i dysk, więc pojedynczy job może działać wolniej
niż wtedy, gdy jest jedynym obciążeniem komputera.

Profil `npm run workers:start` oznacza `general=7` oraz zatrzymany lane
image-selection. General nadal przejmuje tylko jeden job naraz; budżet siedmiu
przyspiesza adaptery mające własną bounded równoległość, w szczególności
rejestrację geometrii stron. Biblioteki natywne pozostają jednowątkowe wewnątrz
każdej strony, aby nie tworzyć zagnieżdżonej nadsubskrypcji.

Jeżeli automatyczna Selekcja zdjęć będzie ponownie potrzebna, uruchom historyczny
bezpieczny profil `general=2`, `image-selection=5`:

```powershell
npm run workers:start:all
```

Nie przekazuj tych parametrów przez `npm run workers:start -- ...`: npm na
Windows może usunąć nazwy argumentów i PowerShell zwiąże wartość `2` z
parametrem `Lane`.

Workspace `Joby` pokazuje oba procesy niezależnie jako `Działa`, `Brak świeżego
sygnału` albo `Zatrzymany`, również gdy nie ma żadnego joba w kolejce. Status
nie zastępuje postępu konkretnego joba.

Kontrolowane zatrzymanie obu procesów:

```powershell
npm run workers:stop
```

Po restarcie komputera procesy nie uruchamiają się automatycznie. Wystarczy
ponownie wykonać `npm run workers:start`; supervisor rozpozna nieaktywny stan z
poprzedniej sesji. Jawne zarządzanie historycznym lane selekcji pozostaje
dostępne:

```powershell
npm run workers:start -- -Lane general
npm run workers:stop -- -Lane general
npm run workers:start -- -Lane image-selection
npm run workers:stop -- -Lane image-selection
```

Ręczne komendy foreground pozostają dostępne diagnostycznie w osobnych
terminalach:

```powershell
npm run worker:poll
npm run worker:image-selection:poll
```

Nie łącz ręcznego procesu i supervisora dla tego samego lane. Supervisor może
bezpiecznie zatrzymać wyłącznie proces, który sam uruchomił i zapisał w
`.runtime\worker-lanes.json`.

Do jednorazowego pobrania najwyżej jednego joba służy:

```powershell
npm run worker:once
npm run worker:image-selection:once
```

Nie uruchamiaj dwóch kopii tego samego lane ani kilku buildów Android. Poprawny
układ równoległy to najwyżej jeden general worker i jeden image-selection
worker.

Domyślne limity host action materializacji to lease 60 sekund, 5 prób i 4
akcje w jednym cyklu workera. Można je zmienić trwale w środowisku procesu:

```powershell
[Environment]::SetEnvironmentVariable('GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_LEASE_SECONDS', '60', 'User')
[Environment]::SetEnvironmentVariable('GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ATTEMPTS', '5', 'User')
[Environment]::SetEnvironmentVariable('GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ACTIONS_PER_CYCLE', '4', 'User')
```

Po zmianie otwórz nowy PowerShell i zrestartuj general worker. Zatrzymanie
executora nie usuwa verified temp ani finalnych plików; kolejny start bezpiecznie
wznawia akcje queued/retry i wygasłe processing.

### Uruchomienie dużego runu Selekcji Zdjęć na bieżącym selektorze

Nowe runy używają `fast-image-selector-v10.14`. Po aktualizacji kodu zatrzymaj
procesy uruchomione na wcześniejszej wersji, ponieważ działający proces nie
zmienia manifestu w pamięci. W PowerShell przejdź do repozytorium:

```powershell
cd C:\Users\user\Documents\game_predicotr
npm run workers:stop
npm run db:up
npm run db:migrate
npm run workers:start
npm run workers:status
```

Komenda `workers:stop` może zgłosić, że nic nie działa — na świeżym starcie jest
to poprawne. Sprawdź aktywny manifest:

```powershell
.\.venv\Scripts\python.exe -c "from game_predictor_worker.images.selection.manifest import DEFAULT_SELECTOR_MANIFEST as m; print(m.algorithm_version); print(m.fingerprint)"
```

Oczekiwany wynik:

```text
fast-image-selector-v10.14
f74178fb612e636d3b7a501f4e0490d450f2bb69903e5dfdde47d9c5a24dc5a8
```

Pozostaw pierwszy terminal dla API:

```powershell
npm run api:dev
```

W drugim PowerShell uruchom Admin:

```powershell
cd C:\Users\user\Documents\game_predicotr
npm run admin:dev
```

Następnie otwórz `http://127.0.0.1:3000/`, wybierz grę i workspace
`Selekcja zdjęć`. Wskaż folder zawierający naturalnie uporządkowane JPEG-i,
poczekaj na zakończenie uploadu, wpisz dodatni numer pierwszego layoutu i
uruchom selekcję. Pełny run v10.14 wymaga jednoznacznych granic sekwencji; bez
kotwicy początku nie może zastosować bramki pełnej liczności.
Nie uruchamiaj w tym samym czasie Importu layoutów, jeżeli ten przebieg ma być
miarodajnym pomiarem bieżącego selektora. Postęp i stan procesu obserwuj w
workspace `Joby` albo przez:

```powershell
npm run workers:status
```

Nie zatrzymuj API ani image-selection workera do czasu osiągnięcia przez job
stanu terminalnego. Po zakończeniu pozostaw run i staging bez zmian — metryki,
liczbę grup oraz diagnostykę wykorzystamy do zamknięcia TASK-0171. Jeżeli
musisz przerwać próbę, użyj anulowania konkretnego joba w panelu; nie usuwaj
folderu uploadu ani bazy.

Rozpoczęty run zachowuje fingerprint selektora, z którym został utworzony.
Dlatego runu v10.2 nie przełącza się w locie na v10.3: należy pozwolić mu dojść
do stanu terminalnego, zakończyć jego monitor eksportu, a następnie przeładować
API i lane `image-selection` przed utworzeniem kolejnego runu. Historia oraz
galeria ręcznej selekcji wcześniejszego runu pozostają w bazie i są dostępne po
wybraniu tego runu w Adminie, o ile operator nie wyczyści danych gry lub
stagingu.

### Jak używać panelu Admin

Minimalna kolejność przygotowania danych i wydania:

1. W workspace `Zarządzanie grami` otwórz `Gry` i utwórz albo wybierz grę.
2. Otwórz `Import layoutów`, wybierz folder Windows i uruchom import zdjęć.
3. Otwórz `Symbole`, zatwierdź bootstrap i popraw nazwy lub obrazy symboli.
4. Otwórz `Reguły`, przygotuj bieżący draft, paylines, minima oraz payouty,
   opublikuj reguły i uruchom przeliczenie layoutów.
5. Otwórz `Zatwierdzanie`, wybierz gotowy import i utwórz sesję osobnej
   aplikacji Reviewer; przycisk może od razu wystawić ją przez czasowy HTTPS.
6. W osobnym workspace `Joby` obserwuj status i etap. Dla zadań
   asynchronicznych worker musi działać.
7. W osobnym workspace `Wersje Android` utwórz jedno kontrolowane wydanie dla
   aktywnej gry. Najnowsza zgodna para opublikowanego datasetu i reguł jest
   wybierana automatycznie.

Admin 0.2 nie pokazuje osobnych workspace'ów `Datasety` ani `Manual review`.
Pozostają one wewnętrznymi encjami workflow, a decyzje użytkownika prowadzą
przez import, reguły i osobną aplikację Reviewer.

### Wybór geometrii plansz v18/v20

Po przygotowaniu raportu i geometrii gotowego browser stagingu Admin pokazuje
tryb cięcia komórek dla tego stagingu:

- pozostaw `Historyczny v18`, aby utworzyć job z domyślnym
  `historical_v18`,
- wybierz `Zweryfikowany v19 (v20)` wyłącznie świadomie, potwierdź ostrzeżenie
  i uruchom job z `verified_v19`.

V20 nie jest obecnie trybem domyślnym. Benchmark osiągnął `93,78%` pokrycia
przy wymaganych `98%`. Trafienia spełniają bramki jakości, ale pozostałe
pozycje są odkładane do ręcznej korekty. V20 nigdy nie wraca po cichu do v18:
pozycja tworzy dokładnie 15 cropów albo trwały deferred bez inferencji.

Po zakończeniu importu wybierz ten sam import w `Zatwierdzaniu plansz`. Licznik
`Do korekty siatki` prowadzi do osobnego trybu Reviewera. Dla każdej pozycji:

1. ustaw cztery narożniki zewnętrznej siatki symboli 5 × 3,
2. wygeneruj podgląd wszystkich 15 cropów,
3. zapisz dopiero po sprawdzeniu, że żaden symbol nie jest ucięty ani przesunięty
   do sąsiedniego pola,
4. wróć do zwykłej kolejki i zatwierdź symbole utworzonej planszy.

Snapshot działającego joba jest niezmienny. Aby wycofać użycie v20, nie wznawiaj
ani nie przełączaj istniejącego joba. Utwórz kolejny job i wybierz
`historical_v18`. Nie usuwaj ręcznie rekordów deferred ani artefaktów v20.

Kandydat modelu symboli wytrenowany na cropach v19 został odrzucony przez
bramkę błędów wysokiej pewności. Nie wymaga ręcznego rollbacku, ponieważ nigdy
nie został aktywowany; nowe joby nadal przypinają dotychczasowy aktywny model.

Końcową techniczną bramkę 0.2 można powtórzyć bez użycia danych roboczych:

```powershell
npm.cmd run v02:admin:acceptance
```

Nie archiwizuj źródeł używanych przez przygotowywane wydanie. Zmiana reguł lub
danych nie aktualizuje aplikacji już zainstalowanej na telefonie — wymaga
nowego wydania APK z wyższym `VersionCode`.

## Uruchomienie aplikacji Reviewer

Do pracy wyłącznie lokalnej Reviewer wymaga działających PostgreSQL, API i
własnego procesu Next.js. Po zbudowaniu Reviewera panel może uruchamiać ten
proces samodzielnie. Jednorazowo po zmianie jego kodu wykonaj:

```powershell
npm run reviewer:build
```

Następnie:

1. w Adminie otwórz `Zatwierdzanie`,
2. wybierz aktywną grę i jej import zdjęć,
3. kliknij `Otwórz lokalnie`,
4. Reviewer uruchomi się pod `http://127.0.0.1:3001` i od razu otworzy wybrany
   import bez tunelu oraz kodu w widoku `Zatwierdzanie cięcia siatki`.

Lokalny widok geometrii jest obowiązującym workflowem i nie ma zmiennej
przywracającej poprzedni ekran. Sekcja nie tworzy linków online, assignmentów,
sesji ani kodów dostępu. Przycisk najpierw uruchamia albo weryfikuje lokalny
proces przez `reviewer-local/start`, a po jego gotowości ponownie otwiera
dokładny URL wybranej gry i importu. Dzięki ponownej nawigacji karta nie
pozostaje na `ERR_CONNECTION_REFUSED`, gdy port 3001 był zatrzymany przed
kliknięciem.

Po aktualizacji do 0.9 wykonaj migracje i resumowalny backfill przy wyłączonych
API, workerze, Adminie i Reviewerze:

```powershell
.venv\Scripts\python.exe scripts\report_v09_storage_cleanup.py --label before --output .runtime\v09-storage-cleanup-before.json
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe scripts\backfill_v09_schema.py --game-id <GAME_UUID> --batch-size 200
.venv\Scripts\python.exe scripts\report_v09_storage_cleanup.py --label after --output .runtime\v09-storage-cleanup-after.json
```

Backfill zapisuje checkpoint w `.runtime` i można go bezpiecznie wznowić.
Nie uruchamiaj `VACUUM FULL` jako części aktualizacji.

## Kontrola zajętości i pierwsze czyszczenie storage

Po migracji do `0081` nowe importy nie utrwalają pełnowymiarowych
`normalized.png`. Panel Admina `Pamięć i czyszczenie` pokazuje ostatni trwały
inwentarz; zwykłe otwarcie strony nie skanuje milionów plików. Przycisk
`Odśwież inwentarz` uruchamia bounded job w general lane. Skan zapisuje wynik
po każdej przestrzeni nazw i po restarcie wznawia się od następnej.

Pierwszy kontrolowany cleanup z 29 sierpnia 2026 wykonano i odebrano. Tryb
obserwacyjny pozostaje dostępny do diagnostyki lub kolejnego ręcznego rollout'u:

```powershell
$env:GAME_PREDICTOR_STORAGE_GC_OBSERVE_ONLY = 'true'
npm run api:dev
```

W panelu wybierz `Przygotuj raport czyszczenia`. Raport jest dry-runem: zawiera
dokładne ścieżki, rozmiary, mtime, klasy, powody ochrony, checksumę manifestu i
token, ale niczego nie usuwa. Dopiero jawne `Usuń bezpieczne dane` uruchamia
wznawialny job GC. Kandydat zmieniony po raporcie otrzymuje konflikt i nie jest
usuwany. `data/originals`, referencjonowane cropy, modele, kohorty, snapshoty,
release'y, eksporty audytowe i dane ręcznej selekcji nie są kandydatami.

Browserowy staging może zostać usunięty dopiero po checksumowanym handoffie
wszystkich JPEG-ów do managed originals i po 24 godzinach od ostatniej
zależności. Historyczny staging bez trwałego stanu lifecycle jest widoczny w
raporcie jako chroniony; nie naprawiaj tego przez ręczne kasowanie katalogu.

Odtwarzalne payloady PostgreSQL mają oddzielny, również checksum-bound dry-run:

```powershell
.venv\Scripts\python.exe scripts\compact_image_pipeline_state.py preview --retention-hours 24
```

Polecenie zwraca ścieżkę manifestu, checksumę i token. Wykonanie jest dozwolone
wyłącznie po sprawdzeniu raportu oraz świadomym podaniu wszystkich wartości:

```powershell
.venv\Scripts\python.exe scripts\compact_image_pipeline_state.py start `
  --manifest-relative-path <MANIFEST> `
  --manifest-checksum-sha256 <SHA256> `
  --preview-token <TOKEN> `
  --confirm DELETE_REPRODUCIBLE_PIPELINE_PAYLOADS
```

Kompakcja usuwa tylko odtwarzalne późne payloady i uruchamia
`VACUUM (ANALYZE)`. Zwolnione strony stają się dostępne do ponownego użycia
przez PostgreSQL, ale rozmiar pliku VHDX nie musi się zmniejszyć. `VACUUM FULL`,
zatrzymanie Dockera i kompaktowanie `docker_data.vhdx` nie są częścią GC i
wymagają osobnej, jawnej operacji operatorskiej.

Po odbiorze pierwszego cleanupu automatyczne GC jest domyślnie aktywne.
`GAME_PREDICTOR_STORAGE_GC_OBSERVE_ONLY=true` służy do jego jawnego,
tymczasowego wyłączenia. Poniżej 60 GiB system tworzy jeden idempotentny GC;
poniżej rezerwy 30 GiB blokuje nowe operacje zapisujące obrazy. Brak
bezpiecznych kandydatów pozostawia blokadę i wymaga decyzji użytkownika —
system nie rozszerza wtedy automatycznie zakresu usuwania.

Podczas rozwoju można nadal jawnie uruchomić `npm run reviewer:dev`; przycisk
lokalny wykorzysta gotowy proces na porcie 3001. Przycisk
`Utwórz link i wystaw online` zachowuje osobny zdalny workflow: uruchamia tunel,
tworzy sesję i pokazuje link oraz jednorazowy kod.

Kod jest pokazywany tylko przy tworzeniu sesji online. Taka sesja jest trwała,
ważna przez 8 godzin, ma limit pięciu błędnych prób i może zostać unieważniona.

Nie wysyłaj lokalnego adresu `127.0.0.1`. Zdalny dostęp używa wyłącznie
kontrolowanego trybu HTTPS opisanego niżej; nie przekierowuj portów routera.

## Zbudowanie mobilnego APK z bieżącego snapshotu

Ta procedura buduje snapshot znajdujący się aktualnie w
`apps\mobile\assets\snapshot`. Jeżeli dane zostały zmienione w Adminie, użyj
workflow `Wydania Android`, aby najpierw wygenerować nowy snapshot i APK.

Sprawdź środowisko i zależności:

```powershell
npm run windows:environment:check
```

Kontrola obejmuje również zmienne użytkownika Windows i wpisy `PATH` zapisane
trwale w profilu. Dzięki temu wynik `passed` obowiązuje także dla nowego
terminala i po ponownym uruchomieniu komputera, a nie tylko dla bieżącej sesji.
Jeżeli kontrola zgłosi brak trwałej konfiguracji, wykonaj:

```powershell
npm run windows:environment:setup
```

Jeżeli katalog `node_modules` nie istnieje, wykonaj wcześniej `npm install`.

Sprawdź wersję już zainstalowaną na podłączonym telefonie:

```powershell
adb shell dumpsys package com.gamepredictor.mobile | Select-String 'versionCode|versionName'
```

Ustaw nowy numer. `VersionCode` musi być większy od zainstalowanego:

```powershell
$versionName = '0.1.3'
$versionCode = 4
npm run android:build:offline -- --VersionName $versionName --VersionCode $versionCode
```

Skrypt używa jednego workera Gradle, wyłącza równoległy build, ogranicza natywny
CMake do dwóch zadań i uruchamia kompilator Kotlin w procesie Gradle, aby nie
pozostawiać drugiego daemona zajmującego pamięć. Te ustawienia generuje również
plugin Expo, więc nie znikają po odtworzeniu katalogu `android`. Expo prebuild ma
domyślny limit 5 minut, a Gradle 30 minut.
Build kończy target aplikacji `:app:assembleRelease`; nie publikuje osobnych
artefaktów AAR zależności.
Po przekroczeniu limitu całe drzewo danego builda jest kończone, więc nie wolno
uruchamiać drugiej kopii bez sprawdzenia komunikatu pierwszej. Pełne czyszczenie
projektu natywnego wykonuj tylko jawnie z `-CleanNativeProject`, gdy zmieniła się
konfiguracja natywna albo zwykły prebuild zgłosi kontrolowany błąd.

Build Release tworzy albo sprawdza prywatne dane podpisu w
`.tooling\android-signing`. Wykonaj ich bezpieczną kopię poza repozytorium.
Utrata klucza uniemożliwi aktualizację już zainstalowanej aplikacji bez jej
odinstalowania.

Gotowy plik:

```text
apps\mobile\android\app\build\outputs\apk\release\app-release.apk
```

Przed instalacją wykonaj statyczny audyt pakietu:

```powershell
npm run android:verify:offline
```

Audyt sprawdza między innymi podpis, architekturę `arm64-v8a`, bundle
JavaScript, checksum SQLite oraz brak uprawnienia Android `INTERNET`.

## APK utworzone przez panel Admin

W sekcji `Wydania Android`:

1. wybierz opublikowane i zgodne źródła,
2. utwórz nowe wydanie z nowym `VersionCode`,
3. uruchom build,
4. pozostaw `npm run worker:poll` do końca zadania,
5. instaluj dopiero wydanie o statusie gotowym, z zapisanym SHA-256,
6. pobierz APK przez kontrolowany przycisk panelu albo użyj pokazanej względnej
   ścieżki artefaktu.

Panel nie instaluje APK na telefonie. Każdy plik nadal instalujesz ręcznie
przez ADB.

## Podłączenie Google Pixel 10 Pro XL

Na telefonie:

1. `Settings` → `About phone`.
2. Naciśnij siedem razy `Build number`.
3. Wróć do `Settings` → `System` → `Developer options`.
4. Włącz `USB debugging`.
5. Podłącz kabel USB.
6. Odblokuj telefon i zaakceptuj `Allow USB debugging`.

Na komputerze:

```powershell
adb devices -l
```

Telefon musi mieć status `device`, nie `unauthorized`. Do kontrolowanego testu
podłącz dokładnie jedno urządzenie. Gdy podłączonych jest więcej, dodawaj do
komend `adb` parametr `-s SERIAL`.

## Pierwsza instalacja albo aktualizacja APK

Ustaw ścieżkę do wybranego, zweryfikowanego APK:

```powershell
$apkPath = 'apps\mobile\android\app\build\outputs\apk\release\app-release.apk'
```

Pierwsza instalacja:

```powershell
adb install $apkPath
```

Aktualizacja bez kasowania danych:

```powershell
adb install -r $apkPath
```

Nie odinstalowuj aplikacji przed testem aktualizacji. Odinstalowanie usuwa
lokalne dane i nie potwierdza zgodności podpisu ani prawidłowej aktualizacji
in-place.

Aplikacja jest widoczna jako `Sequence Target Analyzer`. Możesz uruchomić ją
ikoną albo:

```powershell
adb shell monkey -p com.gamepredictor.mobile -c android.intent.category.LAUNCHER 1
```

Do odbioru wersji `0.1` używany jest Google Pixel 10 Pro XL. Test offline:

1. uruchom aplikację raz po instalacji,
2. włącz tryb samolotowy,
3. wyłącz Wi-Fi,
4. zamknij i ponownie uruchom aplikację,
5. przejdź przez matching, podpowiedź duplikatu, exact duplicate, Undo/Reset i
   Target.

Gdy wracasz do formalnego testu aktualizacji i dokładnie jeden telefon jest
podłączony, możesz użyć kontrolowanego instalatora:

```powershell
npm run android:device:accept -- -ExpectedModelPattern '^Pixel 10 Pro XL$' -Stage Update -RequireAirplaneMode
```

Skrypt instaluje i uruchamia APK, sprawdza wyższy `VersionCode` oraz zachowanie
`firstInstallTime` i zapisuje raport urządzenia. Ręczne scenariusze znajdują
się w
[M1_DEVICE_ACCEPTANCE.md](../quality/M1_DEVICE_ACCEPTANCE.md).

Po każdej zmianie kodu mobile lub danych SQLite przeznaczonej do testu
samodzielnego trzeba zbudować nowe APK i wykonać `adb install -r`. Zmiany
panelu Admin, API albo Reviewera nie wymagają instalowania APK — wystarczy
restart odpowiedniego procesu lub odświeżenie przeglądarki.

## Pełny reset lokalnej bazy Admina

Reset jest nieodwracalną operacją roboczą. Najpierw zatrzymaj API i workera oraz
wykonaj dump danych, które mogą być jeszcze potrzebne. Następnie uruchom:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/reset_local_admin_database.ps1 -ConfirmReset
```

Skrypt akceptuje wyłącznie bazę `game_predictor` na lokalnym loopbacku. Usuwa
cały schemat `public`, tworzy pusty schemat i wykonuje migracje Alembic od zera.
Nie używa historycznych downgrade'ów, dlatego reset nie zależy od zawartości
starych rekordów. Nie usuwa zdjęć źródłowych, APK, snapshotów SQLite, klucza
podpisu ani innych plików z repozytorium.

## Zatrzymywanie usług

- API, Admin, worker i Reviewer: `Ctrl+C` w ich oknach PowerShell.
- PostgreSQL bez usuwania danych:

```powershell
npm run db:down
```

Nie używaj `db:reset:local` ani nie usuwaj wolumenu Dockera bez świadomej
decyzji i kopii danych.

## Najczęstsze problemy

- `node`, `npm`, `java`, `adb` lub `docker` nie są rozpoznawane — zamknij stare
  okno PowerShell, otwórz nowe i uruchom
  `npm run windows:environment:check`.
- `unauthorized` w `adb devices` — odblokuj telefon i zaakceptuj klucz RSA.
- `more than one device/emulator` — odłącz pozostałe urządzenie albo użyj
  `adb -s SERIAL ...`.
- `INSTALL_FAILED_VERSION_DOWNGRADE` — zbuduj APK z większym `VersionCode`.
- `INSTALL_FAILED_UPDATE_INCOMPATIBLE` — APK ma inny podpis. Nie odinstalowuj
  aplikacji, jeżeli chcesz zachować aktualizację in-place; użyj właściwego,
  zachowanego klucza.
- panel nie widzi danych — sprawdź Docker Desktop, `npm run db:up`, migracje,
  działające API i wynik endpointu health.
- Reviewer nie pokazuje importu — potrzebna jest aktywna gra oraz job
  `image_directory` dla tej gry.
- Reviewer odrzuca kod po restarcie API — utwórz nową sesję w Adminie.
- ogólny job pozostaje `created` — uruchom `npm run worker:poll`;
  job `image_selection` wymaga `npm run worker:image-selection:poll`.
- build Android trwa długo — nie uruchamiaj drugiego builda. Poczekaj na
  zakończenie kontrolowanego procesu Gradle albo sprawdź jego ostatni błąd.

## Czasowy link HTTPS do zdalnej ręcznej selekcji

Ten tryb dotyczy wyłącznie purpose-scoped zdalnej ręcznej selekcji zdjęć.
Nie udostępnia ekranu `Zatwierdzanie cięcia siatki`, który jest wyłącznie
lokalny. Admin, API, PostgreSQL i worker pozostają na `127.0.0.1`. Nie
konfiguruj przekierowania portów routera.

Jednorazowo zainstaluj oficjalny `cloudflared` i zbuduj produkcyjnego Reviewera:

```powershell
npm run reviewer:remote:setup
npm run reviewer:build
```

Uruchom PostgreSQL, migracje, API i Admin. Nie uruchamiaj `reviewer:dev`,
ponieważ serwer developerski nie może zostać wystawiony online. Capability i
link twórz wyłącznie w sekcji zdalnej ręcznej selekcji zdjęć.

Praca lokalna uruchamia lub wykorzystuje gotowego Reviewera na loopback i nie
zajmuje limitu online. Maksymalnie trzy różne importy mogą być jednocześnie
udostępnione online; każdy ma własny kod, sesję i przycisk zakończenia, ale
wszystkie wykorzystują jeden produkcyjny Reviewer oraz jeden Quick Tunnel.
Przycisk online uruchamia brakujące procesy, czeka na gotowość i tworzy scoped
sesję. Nie wykonuje builda w żądaniu. Jeżeli zobaczysz komunikat o trybie
developerskim, zatrzymaj okno z `reviewer:dev` i kliknij ponownie. Zimny start
ma twardy limit 60 sekund; zdrowy warm ingress jest używany ponownie bez nowego
procesu i bez zmiany publicznego originu. Proces uruchomiony przez
`npm run api:dev` automatycznie przeładowuje zmiany API.
Po ręcznym `npm run reviewer:build` kontroler porównuje aktualny `.next/BUILD_ID`
z identyfikatorem serwowanym przez proces na porcie 3001. Starszy produkcyjny
Reviewer zostaje zastąpiony przed ponownym użyciem linku; sam Quick Tunnel może
pozostać aktywny. Proces developerski lub listener, którego nie można bezpiecznie
zidentyfikować jako Node Reviewera, kończy operację jawnym błędem zamiast być
automatycznie zatrzymywany.
Awaryjny odpowiednik CLI:

```powershell
npm run reviewer:remote:start
npm run reviewer:remote:status
```

Kontroler sprawdza teraz połączenie TCP do
`api.trycloudflare.com:443` przed uruchomieniem tunelu. Jeżeli API działa w
procesie z zablokowanym internetem, panel zwraca od razu komunikat o niedostępnym
endpointcie zamiast czekać 30 sekund na nieistniejący URL. W takim przypadku
uruchom ponownie `npm run api:dev` w zwykłym PowerShellu Windows z dostępem do
wychodzącego HTTPS; restart komputera nie jest potrzebny. Firewall może
blokować Admin i API od strony sieci przychodzącej, ale proces API musi móc
nawiązać wychodzące połączenie HTTPS dla jawnie uruchamianego Quick Tunnel.

Nowy losowy hostname Quick Tunnel może przez kilka sekund być ukryty przez
lokalny negatywny cache DNS. Kontroler sprawdza ograniczenie kolejno przez
lokalny resolver, `1.1.1.1`, `8.8.8.8` i Cloudflare DNS-over-HTTPS. Jeżeli
adres jest już widoczny tylko w publicznym DNS, health check używa curl
`--resolve`: połączenie nadal wymaga zgodnego hostname'u, SNI i certyfikatu TLS.
Nie trzeba ręcznie czyścić cache DNS ani ponawiać startu z drugiego terminala.

`start` uruchamia proces w tle i pokazuje losowy adres
`https://...trycloudflare.com`. Nowa sesja automatycznie użyje aktywnego
publicznego originu.

Kontrolery `reviewer:remote:start`, `reviewer:remote:status`,
`reviewer:remote:stop` oraz lokalny start używają tego samego nazwanego mutexu
Windows. Równoległe wywołania są serializowane i mają ograniczony czas
oczekiwania. Stan w `.runtime/` jest publikowany atomowo dopiero po potwierdzeniu
gotowości procesu i zawiera PID, czas startu, executable oraz losowy identyfikator
instancji. Dzięki temu stary plik stanu albo PID ponownie użyty przez inny proces
nie powoduje jego zatrzymania. Nie usuwaj ręcznie pliku stanu podczas aktywnego
startu; `status` zgłosi niepełny lub niezgodny stan jako `stale`.

Każda próba startu zapisuje osobne pliki w
`.runtime/reviewer-lifecycle-logs/`, więc równoległy albo kolejny start nie
próbuje ponownie otworzyć jednego używanego pliku logu. Pliki wynikowe poleceń
API są również unikalne i znajdują się w
`.runtime/reviewer-ingress-controller-results/`. Oba katalogi są danymi
diagnostycznymi runtime i nie zawierają kodu sesji ani bearer tokenu.

Wyślij link i kod dwoma osobnymi kanałami. Odbiorca nie instaluje klienta VPN:
otwiera link w przeglądarce i podaje kod. Kod ma najwyżej pięć prób, a sesja
wygasa najpóźniej po 24 godzinach.

Po zakończeniu użyj `Zakończ pracę` przy właściwym imporcie. Panel unieważnia
tylko sesję tego assignmentu. Pozostałe linki działają nadal, a Quick Tunnel
jest zatrzymywany dopiero po zamknięciu ostatniej aktywnej pracy online. Praca
lokalna może pozostać aktywna, ponieważ nie publikuje portu. Po odświeżeniu
Admin odtwarza assignmenty z PostgreSQL, lecz ze względów bezpieczeństwa nie
pokazuje ponownie jednorazowego kodu. Decyzje plansz i audyt pozostają w
PostgreSQL. Awaryjny globalny stop jest przeznaczony wyłącznie do sytuacji, w
której nie ma już aktywnych prac online:

```powershell
npm run reviewer:remote:stop
npm run reviewer:remote:status
```

Ostatnia komenda powinna zwrócić `stopped`. Ponowny start wygeneruje inny URL,
więc trzeba utworzyć i przekazać nowy link. Stan procesu znajduje się w
ignorowanym katalogu `.runtime/`, a log nie zawiera kodu ani tokenu.

Quick Tunnel jest przeznaczony do czasowych testów/developmentu i nie ma SLA.
Stały adres wymaga później named tunnel i osobnej decyzji. Pełny test odbiorczy
TASK-0115 wykonuje się z urządzenia poza domową siecią: unlock, odczyt tylko
wskazanej gry/importu, jeden zapis, revoke oraz próby wejścia na zabronione
ścieżki Admina.

Lokalny endpoint wyboru bazy i purpose-scoped route sesji zdalnej ręcznej
selekcji zdjęć są domyślnie włączone. Awaryjny rollback bez zmiany bazy,
audytu i istniejących markerów:

```powershell
$env:GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED = 'false'
npm run api:dev
```

Po restarcie API wszystkie te route znikają z OpenAPI. Ponowne ustawienie
`true` przywraca je. Capability utworzone przed restartem procesu API są celowo
nieważne; cookie aktywnej sesji pozostaje ważne do TTL, rotacji lub revoke,
ponieważ binding, hash-only credentials, stan lease i audyt są trwałe w
PostgreSQL.

TASK-0282 dodaje binarny transfer wybranego JPEG-a. Domyślne, trwałe limity
procesu API można zmienić przed jego uruchomieniem:

```powershell
$env:GAME_PREDICTOR_REMOTE_SELECTION_MAX_FILE_BYTES = '33554432'
$env:GAME_PREDICTOR_REMOTE_SELECTION_MAX_SESSION_BYTES = '21474836480'
$env:GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_SESSION_TRANSFERS = '4'
$env:GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_GLOBAL_TRANSFERS = '8'
$env:GAME_PREDICTOR_REMOTE_SELECTION_UPLOAD_TIMEOUT_SECONDS = '120'
npm run api:dev
```

Zmiana limitu pliku w API powyżej 32 MiB wymaga osobnej zgodnej zmiany limitu
proxy Reviewera; obecna wersja celowo blokuje większe publiczne body wcześniej.
Transfer kończy się na prywatnym stanie `verified`. Brak finalnego `seq_*` jest
oczekiwany do czasu TASK 11.

Od TASK-0279 utworzenie purpose-scoped sesji zdalnej selekcji automatycznie
wykorzystuje ten sam produkcyjny Reviewer i Quick Tunnel. Publiczny link ma
postać `/manual-selection?session=<UUID>` i nie zawiera kodu ani tokenu. Po
restarcie tunelu odśwież detail/listę sesji w Adminie: ten sam identyfikator
sesji otrzyma bieżący origin. Nie uruchamiaj drugiej kopii Reviewera ani tunelu.

Shell TASK 7 obsługuje kod, context, heartbeat i takeover. Nie pokazuje jeszcze
folderu ani zdjęć — workspace i synchronizacja należą do TASK 8. Revoke działa
również wtedy, gdy kontroler tunelu jest niedostępny, i celowo nie zatrzymuje
wspólnego ingressu. Awaryjne wyłączenie całej powierzchni:

```powershell
$env:GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED = 'false'
npm run api:dev
```

Zatrzymaj wcześniej uruchomiony Reviewer i uruchom go ponownie z procesu API,
który dziedziczy tę flagę. Po ponownym uruchomieniu API i Reviewera
`/manual-selection` zwraca 404, proxy
nie przekazuje żądań, a starsze linki zatwierdzania plansz pozostają bez zmian.
