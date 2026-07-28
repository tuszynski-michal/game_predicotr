---
title: Image ingestion requirements
status: proposed
last_updated: 2026-07-28
---

# Import i rozpoznawanie zdjęć

## Cel

Przetworzyć duży katalog zdjęć wykonanych telefonem, wyodrębnić z każdego zdjęcia do 9 layoutów, odczytać ich numery oraz rozpoznać symbole w komórkach. Zdjęcia i wycinki pozostają po stronie administracyjnej i nigdy nie trafiają do snapshotu mobilnego.

## Materiał przeanalizowany 2026-07-28

Przeanalizowano 12 zdjęć JPEG 960 × 1280 z jednej gry i sesji. Szczegóły
plików, SHA-256 oraz tagi warunków znajdują się w
`ai_docs/quality/m5-corpus-manifest.json`.

Widoczne cechy:

- 9 mini-layoutów w układzie 3 × 3,
- każdy mini-layout ma siatkę 3 × 5,
- ciągłe numery 1–108 są umieszczone pod layoutami,
- czerwone ramki mogą pomóc w detekcji geometrii,
- zdjęcia zawierają perspektywę, zakrzywienie ekranu, moiré, rozmycie, refleksy i zmiany koloru,
- dłoń oraz elementy nawigacji występują głównie poza komórkami.

Zgodnie z D-050 te 12 próbek wystarcza do pracy kontraktowej i pierwszego
prototypu detekcji geometrii. Jedna gra, sesja i rozdzielczość nie wystarczają
jednak do zatwierdzenia jakości OCR, klasyfikatora ani reprezentatywności G5.
Oryginały pozostają lokalne i ignorowane przez Git.

## Ważne założenie

Import nie jest pojedynczym endpointem HTTP. Jest długotrwałym, wznawialnym pipeline'em uruchamianym przez osobny lokalny proces Python. Worker nie korzysta z chmury i nie pobiera modeli podczas przetwarzania.

## Zaakceptowany stos prototypu

- Python,
- Pillow do wejścia/wyjścia i metadanych,
- `opencv-python-headless` oraz NumPy do geometrii, korekty perspektywy i wycinania,
- oficjalny model recognition-only `en_PP-OCRv5_mobile_rec` uruchamiany
  bezpośrednio przez lokalny CPU runtime PaddlePaddle i dekoder cyfr,
- PyTorch i torchvision do treningu klasyfikatora symboli,
- ONNX Runtime do lokalnej inferencji wersji produkcyjnej.

Detekcja geometrii, OCR i klasyfikacja symboli mają osobne, wersjonowane interfejsy. Biblioteka lub model może zostać wymieniony po benchmarku bez zmiany tabel stagingowych, manual review i procesu publikacji.

Na początku nie wprowadzamy:

- jednego modelu rozpoznającego całe zdjęcie,
- zależności od chmurowego OCR lub VLM,
- YOLO bez dowodu, że geometria klasyczna jest niewystarczająca,
- template matchingu jako jedynego finalnego klasyfikatora.

## Etapy pipeline'u

### 1. Discovery

- skanowanie wskazanego folderu,
- kontrakt `image-discovery-v1` obsługuje początkowo JPEG `.jpg/.jpeg`; inne
  rozszerzenia obrazów mają stabilny błąd `IMAGE_SOURCE_FORMAT_UNSUPPORTED`,
- zapis ścieżki względnej, rozmiaru, czasu modyfikacji i checksum,
- pomijanie plików już przetworzonych tą wersją pipeline'u,
- grupowanie identycznych bajtów pod wieloma nazwami według SHA-256,
- deterministyczny manifest bez ścieżki absolutnej i czasu wygenerowania,
- brak zapisu w katalogu źródłowym; manifest i późniejsze artefakty muszą
  znajdować się poza nim.

Pliki niebędące obrazami są ignorowane. Uszkodzony JPEG, niezgodna sygnatura,
nieczytelny plik i ścieżka wychodząca poza root mają osobne stabilne kody.
Tożsamość i pomijanie znanego wejścia zależą od SHA-256, nie od nazwy ani mtime.

### 2. Normalizacja

- odczyt orientacji EXIF,
- kontrakt `image-normalization-v1` stosuje wartości Orientation 1–8 przez
  `ImageOps.exif_transpose`; brak tagu zapisuje jawne `null`,
- wynik jest czystym RGB PNG bez EXIF i bez kolejnej stratnej kompresji,
- przygotowanie kopii roboczych w przestrzeniach kolorów potrzebnych algorytmom,
- opcjonalna korekta jasności i kontrastu wyłącznie w kopii,
- zachowanie oryginału bez modyfikacji,
- ponowna weryfikacja discovery manifestu i SHA-256 przed dekodowaniem,
- content-addressed, niezmienne artefakty poza katalogiem źródłowym,
- diagnostyka zawierająca źródłowy/wynikowy SHA-256, wymiary, tryb, orientację,
  transformację, ścieżkę względną i wersje pipeline/Pillow,
- limit 50 000 000 pikseli na źródło ze stabilnym błędem.

Retry zwraca istniejący artefakt tylko po porównaniu pełnych bajtów. Odmienna
zawartość pod tą samą ścieżką jest kolizją i nie zostaje nadpisana.

### 3. Detekcja strony i layoutów

- kontrakt `page-board-detector-v1` przyjmuje znormalizowany RGB PNG,
- wspierany wariant obejmuje dokładnie dziewięć czerwonych ramek w siatce
  3 × 3; wynik zachowuje kolejność row-major i indeksy 0–8,
- klasyczny detektor HSV/contour zapisuje narożniki strony i każdej planszy,
  bounding box, confidence z jawnymi składnikami oraz informację o kontrolowanej
  korekcie kandydata względem regularnej siatki,
- brak dziewięciu kandydatów, nadmiar, nieregularność, złe wyrównanie albo
  nakładanie daje `needs_review` ze stabilnym powodem; pipeline nie dopełnia
  i nie przesuwa indeksów po cichu,
- content-addressed overlay diagnostyczny powstaje poza źródłami i
  znormalizowanymi plikami.

Ze względu na krzywiznę wyświetlacza każdy mini-layout powinien być prostowany indywidualnie. Jedna globalna transformacja perspektywy może nie wystarczyć.

Powyższy wariant jest prototypem ograniczonym przez D-053. Wynik 12/12 na
bieżących zdjęciach potwierdza działanie na obserwowanym ekranie, ale bez
niezależnych adnotacji narożników nie stanowi pomiaru accuracy ani zaliczenia
G5.3.

### 4. Wycięcie layoutów

Kontrakt `board-cell-crops-v1` działa tylko na kompletnym wyniku
`page-board-detector-v1` dla wariantu D-053:

- każdy quad jest walidowany i prostowany indywidualnie do RGB 500 × 300,
- indeks planszy pozostaje 0-based i row-major z TASK-0054,
- raport zapisuje źródłowy quad, macierz transformacji, ścieżkę względną,
  checksum i wersję croppera,
- wynik niekompletny, zła kolejność albo niepoprawny quad daje `needs_review`
  bez częściowych wycinków,
- plansza i overlay siatki są content-addressed oraz niezmienne.

### 5. Odczyt sequence number

- kontrakt `sequence-number-ocr-v1` wyprowadza deterministyczny quad z dolnej
  krawędzi każdego layoutu i tworzy crop RGB 192 × 64,
- wersjonowany preprocessing `bright-component-tight-v1` usuwa górną krawędź
  ramki, wybiera jasne komponenty i zachowuje również surowy crop,
- adapter `SequenceNumberRecognizer` otrzymuje pojedynczy wiersz obrazu; jego
  pierwsza implementacja używa lokalnego `en_PP-OCRv5_mobile_rec`, PaddlePaddle
  CPU i CTC ograniczonego do blank oraz cyfr `0–9`,
- raport zapisuje surowy tekst, wartość znormalizowaną, confidence, wersję
  runtime/modelu, checksumy oraz względne ścieżki obu cropów,
- wartość znormalizowana powstaje tylko wtedy, gdy cały raw text składa się z
  cyfr; confidence pozostaje prawdopodobieństwem klas zwróconym przez model,
- ciągłość wszystkich pozycji w kolejności korpusu flaguje nierozpoznanie,
  duplikat, lukę albo konflikt, ale nigdy nie zmienia raw text ani normalized
  number,
- baseline na niezależnych numerach 1–108 osiąga `68/108 = 62.9630%`,
  `58/108` pozycji wymaga review, a `51/108` ma konflikt ciągłości; wynik jest
  pomiarem prototypu poniżej proponowanego progu 98%, nie zaliczeniem G5.4.

Benchmark `m5-image-benchmark-v1` potwierdza, że surowy crop z tym samym
modelem jest gorszy (`46/108 = 42.5926%`), więc preprocessing jasnego komponentu
pozostaje lepszym baseline'em. Nie jest to jednak finalny wybór modelu.
Detekcja strony i dziewięciu plansz wynosi 100% na obecnych 12 zdjęciach, ale
bez niezależnych golden narożników nie wolno deklarować accuracy geometrii.
Pełny wynik, timing i katalog 40 błędów znajdują się w
`ai_docs/quality/m5-image-benchmark-report.json`.

### Status prototypu po D-056

- discovery i normalizacja są zachowywanymi kontraktami,
- geometria oraz cropy pozostają eksperymentalne i ograniczone do wariantu
  dziewięciu plansz 3 × 3,
- kontrakt OCR zostaje wymienny, ale bieżący model/preprocessing wymaga reworku,
- każdy obecny wynik OCR jest sugestią do manual review; nie ma auto-accept,
- continuity może zgłosić problem, ale nigdy nie tworzy zatwierdzonego numeru,
- automatyczny import/publikacja zdjęć pozostają wyłączone; M4 jest dostępnym
  bezpiecznym workflow ręcznym.

### 6. Podział na komórki

- wariant D-053 używa wymiarów 3 × 5,
- od wyprostowanej planszy odetnij po 5%, czyli 25 px poziomo i 15 px pionowo,
- podziel wewnętrzny obszar 450 × 270 na 15 komórek RGB 90 × 90,
- wiersz i kolumna są 0-based; kolejność zapisu jest row-major,
- każda komórka ma względną ścieżkę i SHA-256 w raporcie,
- wycinki są cache roboczym prototypu; nie są jeszcze datasetem treningowym ani
  rekordami opublikowanego datasetu.

### 7. Klasyfikacja symbolu

1. administrator dostarcza oznaczone przykłady każdego symbolu,
2. trening używa osobnych zdjęć źródłowych dla zbioru treningowego i walidacyjnego,
3. klasyfikator zwraca `symbol_id`, confidence i kilka alternatyw,
4. inferencja produkcyjna używa wersjonowanego modelu ONNX,
5. niski confidence trafia do manual review.

Docelowy punkt startowy do walidacji to około 100 wycinków na symbol z wielu zdjęć. Nie zakładamy samodzielnego odkrycia poprawnych klas bez zatwierdzonych etykiet.

### 8. Manual review

Element trafia do review, jeżeli:

- nie wykryto strony lub layoutu,
- geometria ma niski confidence,
- OCR numeru jest niepewny albo narusza ciągłość,
- numer koliduje z istniejącym,
- symbol ma confidence poniżej progu,
- siatka jest uszkodzona,
- layout ma nieprawidłową liczbę komórek.

Administrator zatwierdza, poprawia albo odrzuca element. Korekta symbolu może zostać wyeksportowana jako oznaczony przykład.

### 9. Walidacja i commit

Dane są najpierw zapisywane do tabel stagingowych. Utworzenie wersji datasetu wymaga:

- poprawnej liczby komórek,
- symboli należących do gry,
- zaakceptowanych numerów,
- ciągłego `sequence_number` bez luk i duplikatów numerów,
- raportu zduplikowanych sygnatur layoutu,
- idempotentnego importu,
- braku nierozwiązanych elementów blokujących.

## Stan i etapy zadania

```text
status: created | processing | waiting_for_review | completed | failed | cancelled
stage: scanning | processing_images | validating
```

Status należy do wspólnego automatu jobs. Etap opisuje wyłącznie aktualną część
pipeline'u importu i może zostać rozszerzony bez zmiany cyklu życia.

## Wznawianie

- postęp jest zapisywany co plik lub małą partię,
- błąd jednego zdjęcia nie przerywa całego importu,
- ponowne uruchomienie nie tworzy duplikatów,
- wersja pipeline'u, OCR i klasyfikatora jest zapisywana z wynikiem,
- początkowo wykonywane jest najwyżej jedno ciężkie zadanie naraz.

## Przechowywanie plików

Lokalna struktura:

```text
data/
  originals/
  working/
  crops/
  training/
  models/
  exports/
```

Baza przechowuje ścieżki względne, checksumy i metadane. Nie przechowuje dużych zdjęć w głównych tabelach domenowych ani w mobilnym SQLite.

## Metryki jakości

- skuteczność detekcji strony,
- skuteczność detekcji 9 layoutów,
- błąd geometrii komórek,
- accuracy OCR numerów,
- accuracy klasyfikatora per symbol i macierz pomyłek,
- odsetek elementów manual review,
- czas na zdjęcie,
- liczba błędów trwałych,
- odtwarzalność wyniku dla tej samej wersji modeli.

## Walidacja technologii przed wdrożeniem masowym

1. Rozszerzyć prototypowy korpus 12 zdjęć do 20–100 reprezentatywnych zdjęć
   przed pełnym benchmarkiem G5.
2. Dodać niezależne pozycje/narożniki plansz i zweryfikować geometrię na pełnym
   zbiorze.
3. Zbudować oznaczony zbiór symboli i podzielić go według zdjęcia źródłowego.
4. Zaakceptować progi przed kolejną optymalizacją; confidence nie może być
   progiem auto-accept bez kalibracji na held-out source images.
5. Porównać wyspecjalizowane alternatywy OCR cyfr na rozłącznym podziale
   źródeł; obecne 12 zdjęć nie może być jednocześnie zbiorem strojenia i
   końcowej oceny.
6. Zatwierdzić finalne modele i ich wersje w osobnej decyzji architektonicznej.
