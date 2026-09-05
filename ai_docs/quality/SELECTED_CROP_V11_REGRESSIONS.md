# Selected crop v11 — referencje i baseline TASK-0468

## Metoda i ograniczenia

Stan: implementacja eksperymentalna 0469–0471 gotowa; odbiór 0472 NIE przeszedł.
V11 pozostaje nieaktywny. Produkcyjny wariant i katalogi operatora bez zmian.

Siedem oryginalnych JPEG-ów (63 plansze i 63 numery) obejrzano w kanonicznej
orientacji. Ręcznie oznaczono zachowawcze bboxy i dopuszczalne przedziały linii.
To referencje poziomego pasa, nie dokładne etykiety narożników do uczenia geometrii.
Tolerancja adnotacji wynosi 8 px; ocena nie udaje dokładności pojedynczego piksela.
Oznaczenia nie pochodzą z wyniku detektora. Zasłonięte fragmenty plansz mają
zachowawcze obwiednie; kompletność oznacza obecność całego panelu w kadrze,
nie brak dłoni i odblasków. Nie wolno używać tych bboxów do omijania detekcji.

Źródła pozostają na dysku operatora, bez dodatkowych kopii JPEG w repozytorium.
Fixture zawiera SHA-256 każdego oryginału. Runner odrzuca brak lub zmianę pliku,
nie pomija go po cichu. Zwykłe testy sprawdzają oracle i zmierzone snapshoty;
pełne odtworzenie detektora wymaga uruchomienia runnera na oryginałach.

Development: katalogi `70363 - 93861` i `303319 -326700` (5 zdjęć).
Holdout: `45163 - 70371` i `200575 - 222912` (2 zdjęcia).
Znana wcześniej próbka 314713 pozostaje development. Żaden katalog ani SHA
nie występuje w obu częściach. Dwa zdjęcia holdout nie uzasadniają deklaracji
90% skuteczności na nowych katalogach. Przed odbiorem 0472 rozszerzyć niezależną
część odbiorczą, pozostając w limicie 120 zdjęć; nie stroić na holdout.

## Wynik v10 na oryginałach

Read-only runner stosuje identyczną ścieżkę jak obecny skrypt katalogowy:
Sharp EXIF rotate raz, RGBA 512 px szerokości, produkcyjny detektor v10.
Nie renderuje ani nie zapisuje cropów. Przebieg 7 zdjęć ukończył się w ok. 1 s
(czas polecenia, nie benchmark ani gwarancja czasu całego katalogu).

| Zakres | Zmierzony top/bottom | Klasa v10 | Problem względem referencji |
|---|---|---|---|
| 79903–79911 | 502 / 1824 | high_confidence | obudowa pozostaje pod planszami |
| 80074–80082 | 0 / 538 | high_confidence | crop reklamy; wszystkie plansze usunięte |
| 80299–80307 | 34 / 1099 | conservative | pozostawiona reklama oraz nadmiar dołu |
| 70363–70371 | 652 / 1224 | high_confidence | góra poprawna, nadmiar dołu |
| 314713–314721 | 454 / 1152 | high_confidence | pochylenie zachowane, nadmiar dołu |
| 50410–50418 | 568 / 1167 | high_confidence | nadmiar dołu |
| 200575–200583 | 403 / 1824 | high_confidence | obudowa pozostaje pod małym panelem |

6/7 oznaczono jako high_confidence, chociaż 0/7 spełnia obie linie referencji.
To celowo dobrany mały zbiór regresyjny, NIE estymacja odsetka błędów katalogu.
Nie wolno zamieniać liczby zapisanych JPEG-ów ani klasy detektora w miarę jakości.

## Powiązanie z załącznikami

- Oryginały 79903 i 80299 odnaleziono i sprawdzono wizualnie.
- Przypadek samej reklamy 80074 odnaleziono poprzez manifest cut (0–538).
  Odtwarza identyczny rodzaj błędu; nie potwierdzono, że jest dokładnie klatką
  drugiego załącznika, który nie pokazuje nazwy ani plansz.
- Oryginału `50550 murine_000124.jpg` nie znaleziono po nazwie w Documents i E:.
  Lokalny `seq_50410-50418.jpg` to owoce, NIE gra literowa z załącznika.
  Nie podstawiono go pod inny wygląd gry. Odbiór szaty literowej pozostaje
  niepotwierdzony; wymagany właściwy oryginał przed deklaracją jej jakości.

## Odtworzenie

```powershell
node --experimental-strip-types scripts/evaluate_selected_crop_quality.mjs "C:\Users\user\Documents\777"
node --experimental-strip-types --test packages/manual-image-selection-core/test/selected-crop-quality.test.mjs
```

Runner ma deadline 120 s, nie uruchamia procesów potomnych i nie zapisuje danych.
Weryfikuje SHA, wymiary i zgodność zmierzonego baseline'u. Po zmianie domyślnego
detektora wymaga jawnego adaptera historycznego; nie może nazwać wyniku v11 wynikiem v10.

## Dalsza kolejność zaakceptowanego planu

- 0469: osobny lokalny v11; struktura luminancji, maks. 96 kandydatów, pełne
  dziewięć obszarów, analiza 960 i jeden retry 1600 dłuższego boku; bez OCR/koloru
  jako dowodu i bez syntetycznych brakujących plansz.
- 0470: ekstrema plansz i numerów, bufor max(4 px, 15% mediany wysokości) plus
  niepewność; detected/needs_manual_crop/failed, pełny obraz przy niepewności,
  obowiązkowa korekta niezależna od zaznaczeń. Brak sztucznego confidence.
- 0471: wspólny detektor i polityka Admin/skrypt, worker, proweniencja, trwały
  journal i checksum-bound recovery; ochrona decyzji i historycznych wyników.
- 0472: niezależny odbiór, zero odcięć i cropów reklamy, minimum 90% poprawnych
  automatów wśród czytelnych kompletnych źródeł; raport osobno dla wyglądów gry.
  Przekroczenie bramek blokuje aktywację, nie uzasadnia obniżenia ochrony.

Każdy task osobno; użytkownik zlecił całą serię ze stopem przy nieudanej bramce.
Bez zmian OCR, geometrii v0.10,
aktywnych jobów i istniejących importów. Przeliczenie/usunięcie katalogów dopiero
po osobnym preview i potwierdzeniu. Próbki v11 muszą pochodzić z produkcyjnego kodu.

## TASK-0472 — końcowa bramka 2026-09-05: NIEPRZEJŚCIE

Uruchomiono read-only `scripts/check_selected_crop_v11_acceptance.mjs` z katalogiem
`C:\Users\user\Documents\777` i argumentem `holdout`. Runner weryfikuje SHA źródeł,
wykorzystuje wspólny renderCropSource i sprawdza wymiary wygenerowanego JPEG-a.
Nie zapisuje cropów w katalogach. Polityka i pełny fingerprint są drukowane w raporcie.

| Źródło | Automatyczna akceptacja | Przyczyna | Poziomy | Czas v11 |
| --- | --- | --- | --- | --- |
| 50410–50418 | nie | incomplete_layout | 960 / 1600 | 1712 ms |
| 200575–200583 | nie | incomplete_layout | 960 / 1600 | 1797 ms |

Oba wyniki zachowują pełne 1080×1920 i wymagają ręcznej korekty. Poprawne
automaty: 0/2 = 0% wobec wymaganych 90%. Błędne automaty: 0, lecz brak akceptacji
nie dowodzi skuteczności ochrony na reprezentatywnym materiale. Bramka odrzucona.

Łączny czas v11 3509 ms, mediana raportowana przez runner 1712 ms, p95 1797 ms;
przy dwóch próbkach nie są to wiarygodne estymatory czasu katalogu. Max RSS procesu
168532 KiB obejmuje także baseline. Pomiar współbieżny z buildem Admina, więc
nie jest kontrolowanym porównaniem wydajności. Odbiór gry literowej niepotwierdzony.

Nie stroimy progów na holdout. Następna diagnoza powinna zbadać brakujące/łączone
kandydatury plansz; nie wolno zastępować brakującego dowodu syntetycznymi obszarami.
Zatrzymano rollout zgodnie z poleceniem użytkownika; CROP_V11_RELEASE_ENABLED=false.
