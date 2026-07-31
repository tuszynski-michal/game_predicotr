---
title: M1 Android device acceptance protocol
status: active
last_updated: 2026-07-31
---

# M1 Android device acceptance

## Cel

Protokół potwierdza działanie prywatnego APK bez Metro i bez sieci na Google
Pixel 10 Pro XL oraz Samsung Galaxy S21 Ultra. Wyniku nie należy oznaczać jako
zaliczony bez fizycznego wykonania kroków.

Lokalny artefakt `0.1.2 (3)` z payout-v2 i `m1-fixture.2` przeszedł audyt
pakietu 2026-07-25. Jego rozmiar, checksumy, certyfikat i aktualny status
urządzeń zapisano w `m1-release-verification.json`. Jest gotowym kandydatem do
poniższych testów fizycznych, ale statyczny wynik nie zastępuje testów na
telefonach. Nazwany plik do instalacji znajduje się w
`.tooling/releases/sequence-target-analyzer-0.1.2-m1-fixture.2.apk`.

Pierwszy odbiór Samsunga wykrył zatrzymany loader po ukończonej inicjalizacji
SQLite. Poprawkę zabezpieczono testem regresji, a `0.1.2 (3)` zainstalowano
in-place na `SM-G998B` z Androidem 15. Właściciel wykonał następnie pełne
scenariusze manualne offline na poprawionej wersji na Samsungu i Pixelu.

## Przygotowanie

1. Włącz debugowanie USB i podłącz dokładnie jeden telefon.
2. Potwierdź autoryzację komputera na telefonie.
3. Włącz tryb samolotowy; Wi-Fi i transmisja komórkowa mają pozostać wyłączone.
4. Zbuduj i zweryfikuj APK:

```powershell
npm run quality
$env:GAME_PREDICTOR_GRADLE_USER_HOME = 'C:\gp-gradle'
npm run android:build:offline -- --VersionName 0.1.2 --VersionCode 3
npm run android:verify:offline
```

Fizycznie krótki cache Gradle jest wymagany w bieżącej lokalizacji repozytorium,
ponieważ CMake/Ninja na Windows nadal podlega limitowi `MAX_PATH`.

5. Zainstaluj, uruchom i zapisz automatyczne pomiary:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_android_device_acceptance.ps1 `
  -ExpectedModelPattern "Pixel 10 Pro XL" `
  -RequireAirplaneMode
```

Dla Samsunga użyj `-ExpectedModelPattern "SM-G998"`; dokładny wariant modelu
zostanie zapisany w lokalnym raporcie `.tooling/device-acceptance`.

## Kontrolowane układy game-1

Wprowadzaj symbole w kolejności row-major, od lewej do prawej i od góry do
dołu.

### Unique i golden Target — sequence 99

```text
S5, S8, S5, S6, S2,
S2, S4, S4, S6, S3,
S1, S4, S3, S10, S4
```

Oczekiwane wartości payout-v2:

- exact unique: `Układ: 99`,
- ocenione spiny: `999`,
- łączny payout: `310`,
- łączny koszt: `9990`,
- wynik końcowy: `-9680`,
- wiersz spin `1`, layout `100`, wynik netto `190`,
- wiersz spin `12`, layout `111`, wynik netto `180`,
- brak osobnego wiersza dla plateau spin `13`.

### Unikalny prefiks — sequence 111

Wprowadź `S1, S1`. Snapshot powinien wskazać jednego kandydata i otworzyć modal
z pełnym layoutem `111`. Zaakceptuj uzupełnienie i potwierdź, że Undo cofa je
jako jeden krok.

### Duplicate — sequence 101 i 995

```text
S8, S4, S1, S1, S1,
S5, S6, S3, S8, S4,
S6, S2, S6, S10, S8
```

Oczekiwane:

- komunikat `Duplikat layoutu`,
- liczba wystąpień `2`,
- pozycje `101, 995`,
- brak podsumowania i tabeli Target,
- Reset usuwa kontekst duplikatu.

### Not found

Wypełnij wszystkie 15 pól symbolem `S1`.

Oczekiwane:

- komunikat `Nie znaleziono layoutu`,
- plansza pozostaje widoczna,
- Undo pozwala poprawić ostatni symbol,
- Target nie jest uruchamiany.

## Kontrola przewijania i kompatybilności

- cały ekran przewija się pionowo bez poziomego przesuwania strony,
- poziomo przewija się wyłącznie Selection,
- tabela znajduje się pod podsumowaniem,
- przewijanie nie zatrzymuje aplikacji ani nie pozostawia pustych wierszy,
- tekst, przyciski i plansza nie nachodzą na wycięcie ani paski systemowe,
- obrót urządzenia nie jest wymagany; aplikacja działa w orientacji portrait.

## Aktualizacja snapshotu

Aktualizacja wymaga:

1. kontrolowanego kolejnego snapshotu z inną `releaseVersion` i checksumą,
2. APK podpisanego tym samym lokalnym keystore,
3. wyższego `versionCode`,
4. instalacji z `Stage Update` bez odinstalowania aplikacji:

```powershell
$env:GAME_PREDICTOR_GRADLE_USER_HOME = 'C:\gp-gradle'
npm run android:build:offline -- --VersionName 0.1.3 --VersionCode 4
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_android_device_acceptance.ps1 `
  -ExpectedModelPattern "Pixel 10 Pro XL" `
  -Stage Update `
  -RequireAirplaneMode
```

Po aktualizacji ekran musi pokazać nową wersję snapshotu. Samo podniesienie
`versionCode` bez zmiany snapshotu nie zalicza tego punktu.

## Wyniki

| Kontrola | Pixel 10 Pro XL | Galaxy S21 Ultra |
|---|---|---|
| Identyfikacja modelu i wersji Android | passed: Pixel 10 Pro XL, Android 16 | passed: SM-G998B, Android 15 |
| Instalacja poprawionego APK | passed: initial 0.1.2 | passed: update 0.1.1 → 0.1.2 |
| Start bez Metro | passed: 1,1 s | passed: 0,74 s |
| Tryb samolotowy | passed | owner accepted offline proof: Wi-Fi off, no SIM |
| Unique 99 i przeliczony golden Target | passed offline | passed offline |
| Duplicate 101/995 | passed offline | passed offline |
| Not found i Undo | passed offline | passed offline |
| Reset i zmiana gry | passed offline | passed offline |
| Płynność tabeli | passed offline; czas niezmierzony | passed offline; czas niezmierzony |
| Aktualizacja poprawionego snapshotu | deferred to M3.4 | update in-place passed; changed snapshot deferred to M3.4 |

Wynik scenariuszy manualnych został potwierdzony przez właściciela 2026-07-25.
Nie podano liczbowych czasów matching, Target ani przewijania; nie należy ich
estymować.

### Odbiór wersji 0.1.4 na Pixelu

Właściciel potwierdził 2026-07-31 na Google Pixel 10 Pro XL dwa scenariusze
wersji `0.1.4 (5)`:

- prefiks `8, 4, 1` pokazał wspólny layout dwóch duplikatów; po akceptacji stan
  pozostał `duplicate`, bez pozycji sekwencji i bez uruchomienia Target,
- pełny układ `5, 8, 5, 6, 2, 2, 4, 4, 6, 3, 1, 4, 3, 10, 4` odnalazł layout
  `#99`, uruchomił pełny Target, a przewijanie tabeli do końca było płynne.

Ten odbiór domyka ręczny punkt płynności Pixela w raporcie M3.5 i wymagany
odbiór urządzeniowy wersji `0.1`. Samsung pozostaje późniejszym testem
kompatybilności i nie blokuje wersji `0.1`.

## Wynik końcowy

Właściciel zaakceptował G6 i M1 2026-07-26, ponieważ aplikacja działała zgodnie
z planem offline na obu urządzeniach, a aktualizacja in-place została poprawnie
zainstalowana. Zgodnie z D-020 celowo zmieniony snapshot oraz dokładne pomiary
urządzeniowe zostaną zweryfikowane po M2 w M3, na rzeczywistym pipeline’ie
wersjonowanych wydań. Te dwa punkty pozostają jawnie niewykonane w M1.
