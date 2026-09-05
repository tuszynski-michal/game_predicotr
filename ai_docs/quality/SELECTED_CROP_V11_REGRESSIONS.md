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

## Poprawka TASK-0472 — drugi odbiór nadal NIEPRZEJŚCIOWY

Zmiany: usunięcie halo dylatacji z bboxów, odróżnienie zawierania od duplikatu,
krawędzie bez minimalnej luminancji, promienie 2/3/4/5/6 oraz walidacja kształtu
etykiety przed rankingiem. Przy krawędzi źródła halo pozostaje konserwatywne.
Konfiguracja i `number-bands-v2-validated-before-ranking` zmieniają fingerprint.
Budżet 960/1600, 96 kandydatów, pełne dziewięć plansz i obowiązek ręcznej korekty
pozostają. Stare dwa przypadki dają teraz 2/2 poprawnych automatów; są to regresje,
nie nowy niezależny odbiór.

Przed uruchomieniem detektora wybrano medianowy plik z pierwszych dziesięciu
numerycznie posortowanych katalogów nieużytych w pierwotnym corpusie.
`selected-crop-v11-independent.mjs` zawiera SHA, wizualnie oznaczone ekstrema
wszystkich plansz/numerów i przedziały linii w przestrzeni podglądu 360×640
(tolerancja przedziałów 2 px). To oracle poziomego pasa, nie narożników plansz.
Nie zmieniano go po zobaczeniu wyniku. Zdjęcia obejmują różne pochylenia,
zasłonięcia i źródła 1080×1920 oraz 1520×2704; nadal tylko szatę owocową.

| Źródło | Wynik |
| --- | --- |
| 9901–9909 | manual: incomplete_layout |
| 32482–32490 | poprawny automat |
| 105841–105849 | poprawny automat |
| 123049–123057 | poprawny automat |
| 138943–138951 | poprawny automat |
| 163576–163584 | automat z nadmiarem tła pod planszami |
| 189073–189081 | manual: number_regions_missing |
| 235549–235557 | poprawny automat |
| 260092–260100 | manual: incomplete_layout |
| 273925–273933 | manual: incomplete_layout |

Wynik 5/10 = 50%, 1 niedokładny automat, 4 manual. Zero odcięć plansz lub numerów
w tej próbie, ale bramka >=90% poprawnych automatów oraz zero niedokładnych nie
przeszła. Błędny crop ma dolną linię 270.77 px podglądu zamiast maksimum 267+2;
nie rozszerzono referencji, by go zaliczyć. V11 nadal NIEAKTYWNY.

Pierwszy pomiar około 0.28–1.05 s/zdjęcie (render JPEG w pamięci, bez zapisu).
Nie jest to pomiar wydajności całego katalogu ani innych gier. Powtórny odczyt
potwierdził identyczne decyzje. Replay v10 pozostał zgodny dla 7/7 źródeł.

Odtworzenie: `node --experimental-strip-types scripts/check_crop_v11_independent.mjs
"C:\Users\user\Documents\777"` (jedna linia). Skrypt nie zapisuje wynikowych JPEG-ów.
Nowy zbiór jest już ujawniony; nie wolno używać go do strojenia, a następnie
ponownie nazywać niezależnym. Odbiór gry literowej nadal niepotwierdzony.
Kontrole: 100 testów core/runner/Admin, oba typechecki, format i build Admina OK.
Nie wykonywano live QA ani pełnych testów pozostałych pionów aplikacji.

## Iteracja v0.10.185 — wynik rozwojowy 90%, niezależny odbiór nieprzejściowy

Nowa ścieżka łączenia krawędzi ma aspekty 1/2, a analiza numerów uwzględnia
nachylenie rzędu, pełne białe wiersze cyfr i powrót obwiedni do pikseli źródła.
Bufor wzrósł z początkowych 15% do 20%. Konfigurację zamrożono przed odczytem
wyników nowej próby. Znany corpus 10 zdjęć dał 9 poprawnych automatów i jeden
manual (189073), bez błędnych automatów. Jest to wynik rozwojowy, nie holdout.

Nowa próba to medianowe JPEG-i ze WSZYSTKICH siedmiu pozostałych niewykorzystanych
katalogów. Nie odrzucono żadnego po zobaczeniu wyniku. Referencje poziomego pasa
oznaczono wizualnie przed wykonaniem detektora w podglądach 360×640 i utrwalono
z SHA w `selected-crop-v11-third.mjs`. Ten sam oracle, tolerancja 2 px wyłącznie
dla przedziałów linii; zachowanie chronionej zawartości sprawdzane oddzielnie.

| Źródło | Wynik | Linie w podglądzie 360×640 |
| --- | --- | --- |
| 359632–359640 | poprawny | 171 / 333.67 |
| 383716–383724 | dół ponad chronioną referencją | 167.57 / 326.39 |
| 400141–400149 | poprawny | 164.02 / 319.29 |
| 425170–425178 | poprawny | 150.77 / 315.74 |
| 445744–445752 | poprawny | 150.77 / 322.37 |
| 465400–465408 | poprawny | 161.42 / 324.02 |
| 488530–488538 | manual: incomplete_layout | pełne źródło |

Wynik 5/7 = 71.43%, jeden niepoprawny automat, jeden manual. Chroniony dół dla
383716 wynosi 330; nie zmieniono referencji, żeby zaliczyć wynik 326.39.
Brak cropa samej reklamy nie wystarcza do przejścia bramki. Release pozostaje false.
Pomiar na tym materiale 0.61–2.88 s/zdjęcie, około 9.96 s łącznie; obejmuje render
w pamięci, bez zapisu cropów, i nie stanowi obietnicy czasu dużego katalogu.

Odtworzenie (jedna komenda):
`node --experimental-strip-types scripts/check_crop_v11_independent.mjs "C:\Users\user\Documents\777" third`.
Wyniki trafiają na stdout. Obrazy w katalogach źródłowych i cut nie są zmieniane.
Nowy zbiór jest odtąd ujawniony. Odbiór innej gry nadal niepotwierdzony.

Kontrole: 101 testów core/runner/Admin contract, oba typechecki oraz format OK.
Nie wykonano live QA ani pełnych testów niezwiązanych obszarów aplikacji.
