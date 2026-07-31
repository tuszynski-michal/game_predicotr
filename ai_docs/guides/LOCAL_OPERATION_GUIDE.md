---
title: Local operation guide
status: active
last_updated: 2026-07-30
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

## Najkrótsza procedura na kolejny dzień pracy

1. Uruchom Docker Desktop.
2. Otwórz PowerShell w katalogu repozytorium.
3. Uruchom bazę i migracje:

```powershell
npm run db:up
npm run db:migrate
```

4. Uruchom osobne okna PowerShell:

| Okno | Komenda | Kiedy jest potrzebne |
|---|---|---|
| 1 | `npm run api:dev` | zawsze dla Admina i Reviewera |
| 2 | `npm run admin:dev` | podczas pracy w panelu Admin |
| 3 | `npm run worker:poll` | gdy mają być wykonywane jobs |
| 4 | `npm run reviewer:dev` | podczas zatwierdzania plansz |

5. Otwórz Admin pod `http://127.0.0.1:3000/`.
6. Reviewer otwieraj wyłącznie przez link i kod utworzone w sekcji
   `Zatwierdzanie`.

## Jednorazowe przygotowanie Windows

Repozytorium wymaga Node `>=22.13 <25`, npm `>=11 <12`, Python 3.12,
Microsoft OpenJDK 17, Android SDK 36, ADB oraz Docker Desktop z Linux
containers.

W tym workspace lokalny toolchain znajduje się w ignorowanym katalogu
`.tooling`. Zapisz jego ścieżki i zmienne na stałe dla bieżącego użytkownika:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\configure_windows_user_environment.ps1 -ConfigurePowerShellExecutionPolicy
```

Skrypt zapisuje:

- ścieżki Node.js i npm,
- `JAVA_HOME`,
- `ANDROID_HOME` i `ANDROID_SDK_ROOT`,
- `GAME_PREDICTOR_GRADLE_USER_HOME`,
- wpisy `PATH` dla Node, Javy, ADB, Android command-line tools i Docker CLI.

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

Jobs w stanie `created` wymagają workera. Uruchom go w osobnym oknie:

```powershell
npm run worker:poll
```

Do jednorazowego pobrania najwyżej jednego joba służy:

```powershell
npm run worker:once
```

Nie uruchamiaj równolegle kilku workerów ani kilku buildów Android.

### Jak używać panelu Admin

Minimalna kolejność przygotowania danych i wydania:

1. `Gry` — utwórz albo wybierz grę.
2. `Symbole` — dodaj symbole, ich `mobileCode`, nazwę i oznaczenie jokera.
3. `Reguły` — utwórz draft, ustaw wymiary oraz koszt spinu, dodaj paylines i
   payouty, a potem opublikuj kompletną wersję.
4. `Datasety` albo `Import layoutów` — wygeneruj fixture lub zleć import,
   walidację i publikację danych.
5. `Jobs` — obserwuj status i etap. Dla zadań asynchronicznych worker musi
   działać.
6. `Zatwierdzanie` — utwórz lokalną sesję osobnej aplikacji Reviewer.
7. `Wydania Android` — wybierz opublikowany dataset i zgodne reguły, utwórz
   nowe wydanie oraz uruchom build.

Nie archiwizuj źródeł używanych przez przygotowywane wydanie. Zmiana reguł lub
danych nie aktualizuje aplikacji już zainstalowanej na telefonie — wymaga
nowego wydania APK z wyższym `VersionCode`.

## Uruchomienie aplikacji Reviewer

Reviewer wymaga działających PostgreSQL, API i własnego procesu Next.js. Panel
Admin jest potrzebny do utworzenia sesji.

W osobnym oknie PowerShell uruchom:

```powershell
npm run reviewer:dev
```

Następnie:

1. w Adminie otwórz `Zatwierdzanie`,
2. wybierz aktywną grę i jej import zdjęć,
3. kliknij `Utwórz link i kod`,
4. otwórz wygenerowany link pod portem `3001`,
5. wpisz kod pokazany osobno w panelu.

Kod jest pokazywany tylko przy tworzeniu sesji. Obecna sesja jest ważna przez
8 godzin, ale znajduje się w pamięci procesu API — restart API unieważnia ją
wcześniej. W takim przypadku utwórz nowy link i kod.

Obecny Reviewer działa wyłącznie na tym komputerze (`127.0.0.1`). Nie
przekierowuj portów routera i nie wysyłaj tego linku przez Internet. Zdalny
dostęp wymaga osobnego hardeningu, HTTPS przez zaakceptowany tunel albo VPN
oraz TASK-0113–0115.

## Zbudowanie mobilnego APK z bieżącego snapshotu

Ta procedura buduje snapshot znajdujący się aktualnie w
`apps\mobile\assets\snapshot`. Jeżeli dane zostały zmienione w Adminie, użyj
workflow `Wydania Android`, aby najpierw wygenerować nowy snapshot i APK.

Sprawdź środowisko i zależności:

```powershell
npm run windows:environment:check
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
- job pozostaje `created` — uruchom `npm run worker:poll`.
- build Android trwa długo — nie uruchamiaj drugiego builda. Poczekaj na
  zakończenie kontrolowanego procesu Gradle albo sprawdź jego ostatni błąd.

## Czasowy link HTTPS do zdalnego Reviewera

Ten tryb publikuje tylko aplikację Reviewer. Admin, API, PostgreSQL i worker
pozostają na `127.0.0.1`. Nie konfiguruj przekierowania portów routera.

Jednorazowo zainstaluj oficjalny `cloudflared`:

```powershell
npm run reviewer:remote:setup
```

Uruchom lokalnie PostgreSQL, migracje, API oraz Reviewer zgodnie z wcześniejszą
częścią instrukcji. Następnie:

```powershell
npm run reviewer:remote:start
npm run reviewer:remote:status
```

`start` czeka maksymalnie 10 sekund, uruchamia proces w tle i pokazuje losowy
adres `https://...trycloudflare.com`. Teraz w lokalnym Adminie wybierz grę oraz
import i kliknij `Utwórz link i kod`. Nowa sesja automatycznie użyje aktywnego
publicznego originu.

Wyślij link i kod dwoma osobnymi kanałami. Odbiorca nie instaluje klienta VPN:
otwiera link w przeglądarce i podaje kod. Kod ma najwyżej pięć prób, a sesja
wygasa najpóźniej po 24 godzinach.

Po zakończeniu:

1. kliknij `Unieważnij sesję` w Adminie,
2. zatrzymaj ingress:

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
