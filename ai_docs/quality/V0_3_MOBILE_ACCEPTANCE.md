---
title: Version 0.3 Mobile acceptance on Google Pixel 10 Pro XL
status: active
last_updated: 2026-08-01
---

# Odbiór Mobile 0.3 na Google Pixel 10 Pro XL

## Cel i zakres

Ten protokół zamyka TASK-0141 na jednym Google Pixel 10 Pro XL. Potwierdza
aktualizację in-place, całkowicie offline działanie oraz zintegrowany przepływ
TASK-0135–0140. Samsung i test pełnych rzeczywistych danych należą do 0.4.

## Kandydat

- APK: `artifacts/v03-ready-for-pixel/Game-Predictor-0.3.0-v7-Pixel.apk`
- pakiet: `com.gamepredictor.mobile`
- wersja Android: `0.3.0 (7)`
- SHA-256 APK:
  `80dfb99fa85c466689d69901f0aea57d3fdf03d425c46fd71bb0f883569e1332`
- snapshot: schema 3, `m1-fixture.2`, 3 gry × 1000 layoutów,
- SHA-256 snapshotu:
  `bc583c2b36417a43de593a13848d64976b53cf408f6916a40a470f732185751c`.

Statyczny audyt potwierdził podpis, `arm64-v8a`, bundle JavaScript, zgodny
snapshot i brak deklaracji uprawnienia `INTERNET`.

## Instalacja kontrolowana

1. Podłącz dokładnie jeden odblokowany Pixel i zaakceptuj USB debugging.
2. Włącz tryb samolotowy oraz wyłącz Wi-Fi.
3. W katalogu repozytorium uruchom:

```powershell
adb devices -l
npm run android:device:accept -- `
  -ApkPath 'artifacts\v03-ready-for-pixel\Game-Predictor-0.3.0-v7-Pixel.apk' `
  -ExpectedModelPattern '^Pixel 10 Pro XL$' `
  -Stage Update `
  -RequireAirplaneMode `
  -ExpectedReleaseVersion 'm1-fixture.2' `
  -ExpectedSnapshotSha256 'bc583c2b36417a43de593a13848d64976b53cf408f6916a40a470f732185751c'
```

Nie odinstalowuj wcześniejszej aplikacji. Skrypt ma potwierdzić wyższy
`VersionCode`, zachowany `firstInstallTime`, start launchera i poprawny snapshot.

## Scenariusze manualne offline

### 1. Kompaktowy ekran

- nagłówek pokazuje `ver m1-fixture.2`, wybór gry, a następnie `Next`, `Undo`,
  `Reset`,
- nie ma `Sequence Target`, `OFFLINE`, tytułu `Layout`, licznika planszy,
  `Dane lokalne gotowe` ani nagłówka Selection,
- symbole zawijają się do kilku rzędów, mają jedną krótką nazwę i nie tworzą
  poziomego przewijania strony,
- plansza, kafelki i przyciski nie nachodzą na systemowy safe area.

### 2. Unique, Target i limit

W `Game 1` naciśnij `Reset`, a potem wprowadź:

```text
5, 8, 5, 6, 2,
2, 4, 4, 6, 3,
1, 4, 3, 10, 4
```

- aplikacja odnajduje layout `#99`,
- jedna karta pokazuje `Układ znaleziony i obliczony`,
- szczegóły zawierają tylko `Koszt spinu`, `Koszt` i `Suma końcowa`,
- pole limitu przyjmuje wartości `1 000` i `500 000`, a odrzuca `999` oraz
  `500 001`; dla fixture'a 1000 layoutów oba poprawne limity celowo oceniają
  pełne `999` przyszłych spinów,
- tabela zawiera spin 1/layout 100/netto 190 oraz spin 12/layout 111/netto 180.

### 3. Next i Undo

- na rozpoznanym layoucie `#99` naciśnij `Next`,
- aplikacja ładuje layout `#100` i ponownie oblicza Target,
- naciśnij `Undo`: plansza i wynik wracają atomowo do layoutu `#99`,
- ponowne `Next` znów prowadzi do `#100`.

### 4. Duplicate i Reset

Naciśnij `Reset`, a następnie `8, 4, 1`. Zaakceptuj podpowiedź wspólnego układu.

- wynik pozostaje ostrzeżeniem `duplicate` dla pozycji 101 i 995,
- Target nie uruchamia się i `Next` jest nieaktywne,
- `Reset` usuwa kontekst duplikatu.

### 5. Not found

Wypełnij planszę piętnastoma symbolami `1`.

- karta pokazuje czerwony stan `Nie znaleziono layoutu` z opisem,
- Target i `Next` nie uruchamiają się,
- `Undo` pozwala poprawić ostatnią komórkę.

### 6. Długa tabela i powrót na górę

- wróć do layoutu `#99` i przewiń do `Wyniki Target`,
- przycisk strzałki pojawia się dopiero przy sekcji wyników,
- ostatnie wiersze tabeli nie są zasłonięte,
- przewijanie pozostaje płynne i bez poziomego overflow,
- naciśnięcie strzałki przewija ekran do wersji, wyboru gry i planszy.

### 7. Restart offline

- pozostaw tryb samolotowy i wyłączone Wi-Fi,
- zamknij aplikację z listy ostatnich aplikacji i uruchom ją ponownie,
- aplikacja inicjalizuje snapshot bez komputera, Metro, API i Internetu.

## Wynik

| Kontrola | Status |
|---|---|
| Automatyczna regresja i statyczny audyt | passed 2026-08-01 |
| Aktualizacja in-place na Pixelu | pending |
| Kompaktowy ekran i Selection | pending |
| Unique, Target i limit | pending |
| Next i atomowe Undo | pending |
| Duplicate, not found i Reset | pending |
| Długa tabela i powrót na górę | pending |
| Restart całkowicie offline | pending |
| Akceptacja właściciela | pending |

TASK-0141 pozostaje `in_progress`, dopóki właściciel nie potwierdzi wszystkich
scenariuszy urządzeniowych albo nie opisze regresji do naprawy.
