---
title: M1 Android device acceptance protocol
status: active
last_updated: 2026-07-24
---

# M1 Android device acceptance

## Cel

Protokół potwierdza działanie prywatnego APK bez Metro i bez sieci na Google
Pixel 10 Pro XL oraz Samsung Galaxy S21 Ultra. Wyniku nie należy oznaczać jako
zaliczony bez fizycznego wykonania kroków.

Lokalny artefakt `0.1.0 (1)` przeszedł audyt pakietu 2026-07-24. Jego rozmiar,
checksumy, certyfikat i aktualny status urządzeń zapisano w
`m1-release-verification.json`. Ten wynik nie zastępuje poniższych testów
fizycznych.

> **Protokół wstrzymany:** artefakt i poniższe golden payout/Target powstały
> dla payout-v1. Po D-019 najpierw trzeba wdrożyć ciąg od pierwszej kolumny,
> minimum długości per symbol, przeliczyć fixture oraz wpisać nowe golden
> values. Do tego czasu nie należy oznaczać żadnego testu urządzenia jako
> zaliczonego.

## Przygotowanie

1. Włącz debugowanie USB i podłącz dokładnie jeden telefon.
2. Potwierdź autoryzację komputera na telefonie.
3. Włącz tryb samolotowy; Wi-Fi i transmisja komórkowa mają pozostać wyłączone.
4. Zbuduj i zweryfikuj APK:

```powershell
npm run quality
npm run android:build:offline -- --VersionName 0.1.0 --VersionCode 1
npm run android:verify:offline
```

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
S3, S2, S8, S7, S1,
S5, S6, S4, S9, S5,
S4, S4, S10, S6, S9
```

Historyczne oczekiwane wartości payout-v1, do przeliczenia dla payout-v2:

- exact unique: `Układ: 99`,
- ocenione spiny: `999`,
- łączny payout: `310`,
- łączny koszt: `9990`,
- wynik końcowy: `-9680`,
- wiersz spin `1`, layout `100`, wynik netto `190`,
- wiersz spin `12`, layout `111`, wynik netto `180`,
- brak osobnego wiersza dla plateau spin `13`.

Jeżeli unikalny prefiks otworzy modal, zaakceptuj uzupełnienie i potwierdź, że
Undo cofa je jako jeden krok.

### Duplicate — sequence 101 i 995

```text
S3, S9, S5, S3, S4,
S5, S5, S3, S2, S5,
S8, S8, S2, S5, S8
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

1. kontrolowanego drugiego snapshotu z inną `releaseVersion` i checksumą,
2. APK podpisanego tym samym lokalnym keystore,
3. wyższego `versionCode`,
4. instalacji z `Stage Update` bez odinstalowania aplikacji:

```powershell
npm run android:build:offline -- --VersionName 0.1.1 --VersionCode 2
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
| Identyfikacja modelu i wersji Android | blocked by payout-v2 | blocked by payout-v2 |
| Instalacja poprawionego APK | blocked by payout-v2 | blocked by payout-v2 |
| Start bez Metro | blocked by payout-v2 | blocked by payout-v2 |
| Tryb samolotowy | blocked by payout-v2 | blocked by payout-v2 |
| Unique 99 i przeliczony golden Target | blocked by payout-v2 | blocked by payout-v2 |
| Duplicate 101/995 | blocked by payout-v2 | blocked by payout-v2 |
| Not found i Undo | blocked by payout-v2 | blocked by payout-v2 |
| Reset i zmiana gry | blocked by payout-v2 | blocked by payout-v2 |
| Płynność tabeli | blocked by payout-v2 | blocked by payout-v2 |
| Aktualizacja poprawionego snapshotu | blocked by payout-v2 | blocked by payout-v2 |

Uwagi, czasy i wynik końcowy należy uzupełnić dopiero po wykonaniu testu.
