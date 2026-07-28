---
title: Image ingestion requirements
status: accepted
last_updated: 2026-07-28
---

# Import i rozpoznawanie zdjęć

## Cel

Przetworzyć duży katalog zdjęć wykonanych telefonem, wyodrębnić z każdego zdjęcia do 9 layoutów, odczytać ich numery oraz rozpoznać symbole w komórkach. Zdjęcia i wycinki pozostają po stronie administracyjnej i nigdy nie trafiają do snapshotu mobilnego.

## Materiał przeanalizowany 2026-07-28

Przeanalizowano 43 zdjęcia JPEG w rozdzielczościach 960 × 1280 i 720 × 1280,
obejmujące 387 layoutów jednej gry w dwóch grupach źródłowych. Szczegóły
plików, SHA-256 oraz tagi warunków znajdują się w
`ai_docs/quality/m5-corpus-manifest.json`.

Widoczne cechy:

- do 9 mini-layoutów w układzie 3 × 3,
- każdy mini-layout ma siatkę 3 × 5,
- ciągłe numery 1–387 są umieszczone pod layoutami,
- czerwone ramki mogą pomóc w detekcji geometrii,
- zdjęcia zawierają perspektywę, zakrzywienie ekranu, moiré, rozmycie, refleksy i zmiany koloru,
- dłoń oraz elementy nawigacji występują głównie poza komórkami.

Zgodnie z D-057 korpus spełnia liczbowy warunek M5 i zawiera przejrzane
adnotacje geometrii. Nadal obejmuje jedną grę, dlatego uogólnienie na inne
motywy będzie osobno walidowane. Oryginały pozostają lokalne i ignorowane
przez Git.

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

- kontrakt `page-board-detector-v2` przyjmuje znormalizowany RGB PNG,
- wspierany wariant obejmuje od 1 do 9 czerwonych ramek w siatce 3 × 3;
  wynik zachowuje kolejność row-major i indeksy `0..expectedBoardCount-1`,
- pełna strona wymaga dziewięciu ramek; tylko jawnie wskazana ostatnia strona
  znanego ciągu może mieć 1–8 pozycji,
- klasyczny detektor HSV/contour zapisuje narożniki strony i każdej planszy,
  bounding box, confidence z jawnymi składnikami oraz informację o kontrolowanej
  korekcie kandydata względem regularnej siatki,
- kontrolowany grid recovery wymaga jawnego `expectedBoardCount` i dowodu
  czerwonej ramki; nie tworzy pozycji bez dowodu,
- brak oczekiwanej liczby, nieregularność albo niepoprawna geometria daje
  `needs_review`; pipeline nie przesuwa indeksów po cichu,
- content-addressed overlay diagnostyczny powstaje poza źródłami i
  znormalizowanymi plikami.

Ze względu na krzywiznę wyświetlacza każdy mini-layout powinien być prostowany indywidualnie. Jedna globalna transformacja perspektywy może nie wystarczyć.

Wynik 43/43 stron i 387/387 przejrzanych pozycji spełnia zaakceptowane progi
geometrii dla obserwowanej rodziny ekranu.

### 4. Wycięcie layoutów

`board-cell-crops-v1` pozostaje niezmiennym artefaktem historycznym, ale nie
może zasilać etykietowania ani treningu. Przegląd właściciela wykazał, że
globalne odcięcie 25 px po bokach i 15 px pionowo przed podziałem przesuwa
granice względem symboli i przecina część z nich.

Korekta używa kontraktu `board-cell-crops-v2` na kompletnym wyniku
`page-board-detector-v2` zawierającym oczekiwane 1–9 pozycji:

- każdy quad jest walidowany i prostowany indywidualnie do RGB 500 × 300,
- indeks planszy pozostaje 0-based i row-major z TASK-0054,
- raport zapisuje źródłowy quad, macierz transformacji, ścieżkę względną,
  checksum i wersję croppera,
- wynik niekompletny względem oczekiwania, zła kolejność albo niepoprawny quad daje `needs_review`
  bez częściowych wycinków,
- plansza i overlay siatki są content-addressed oraz niezmienne.

Przed zaakceptowaniem v2 obowiązuje niezależny golden granic komórek. Golden
obejmuje reprezentatywne plansze z obu grup źródłowych i wszystkich dziewięciu
pozycji ekranu. Nie może być wygenerowany wyłącznie przez testowany cropper.

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
- baseline na numerach 1–387 osiąga `247/387 = 63.8243%`; na 31 held-out
  source images wynik to `179/279 = 64.1577%`. Nie spełnia zaakceptowanego
  progu 98% wymaganego do auto-accept.

Benchmark `m5-image-benchmark-v2` potwierdza, że surowy crop z tym samym
modelem jest gorszy (`217/387 = 56.0724%`), więc preprocessing jasnego komponentu
pozostaje lepszym baseline'em. Nie jest to jednak finalny wybór modelu.
Detekcja oczekiwanego zestawu plansz wynosi 100% na 43 zdjęciach. Pełny wynik,
timing i katalog błędów znajdują się w
`ai_docs/quality/m5-image-benchmark-report.json`.

### Status prototypu po D-061

- discovery i normalizacja są zachowywanymi kontraktami,
- geometria strony i pozycje plansz są zaakceptowane dla wariantu do dziewięciu
  plansz 3 × 3; automatyczne quady są wejściem do wersjonowanych profili
  kalibracji,
- podział planszy na komórki v1 i detektorowy wariant v2 pozostają w
  kwarantannie,
- `board-cell-crops-v2-calibrated-v1` przeszedł niezależną bramkę na 27
  planszach i 405 komórkach z P95 linii `1.8337 px`; pełny korpus obejmuje
  43 obrazy, 387 plansz i 5805 komórek,
- kontrakt OCR zostaje wymienny, a bieżący model działa w trybie
  `manual_review_only`,
- każdy wynik OCR jest sugestią do manual review; nie ma auto-accept,
- continuity może zgłosić problem, ale nigdy nie tworzy zatwierdzonego numeru,
- M6 może korzystać wyłącznie ze skalibrowanych cropów i wraca do eksportu
  etykiet przez TASK-0097; nie zależy to od automatycznej akceptacji OCR.

### 6. Podział na komórki

- wariant D-059 używa wymiarów 3 × 5,
- źródłowy quad rzeczywistej ramy planszy przekształć homografią do RGB
  500 × 300, a następnie podziel na piętnaście logicznych slotów 100 × 100,
- wersjonowany inset jest stosowany osobno wewnątrz każdego slotu; bazowy
  kandydat 5 px z każdej strony daje crop RGB 90 × 90,
- globalny margines zmieniający krok siatki jest zabroniony,
- wiersz i kolumna są 0-based; kolejność zapisu jest row-major,
- każda komórka ma względną ścieżkę i SHA-256 w raporcie,
- wycinki są cache roboczym prototypu; nie są jeszcze datasetem treningowym ani
  rekordami opublikowanego datasetu.

Niezależny golden i kalibracja:

- lokalny edytor pokazuje oryginalne zdjęcie, cztery regulowane narożniki ramy,
  ukośną siatkę perspektywiczną 5 × 3, kanoniczny podgląd 500 × 300 i wszystkie
  15 cropów,
- korekta zapisuje źródłowy quad w wersjonowanym goldenie lub profilu
  kalibracji i nie nadpisuje historycznego artefaktu,
- dokładnie 18 profili obejmuje pary grupy źródłowej i pozycji planszy 0–8;
  27 zaakceptowanych quadów jest niezmiennymi anchorami,
- profil zapisuje korektę narożników w lokalnej bazie quadu detektora; dla
  `sequence_number` pomiędzy anchorami stosuje interpolację liniową, a poza
  zakresem najbliższy anchor bez ekstrapolacji,
- profil jest stosowany na poziomie grupy źródłowej i pozycji planszy; ręczna
  korekta każdego z 387 layoutów jest ostatecznym wyjątkiem,
- automatyczne zastosowanie profilu wymaga przejścia tego samego niezależnego
  goldenu.

### 7. Klasyfikacja symbolu

1. `symbol-crop-inventory-v2` weryfikuje wyłącznie zaakceptowane skalibrowane
   cropy v2, profil oraz pełny łańcuch checksum i tworzy stabilną tożsamość
   obserwacji bez przypisywania klasy,
2. administrator dostarcza jawnie przejrzane decyzje
   `reviewed-cell-labels-v1` dla symboli tej samej gry,
3. `labeled-symbol-dataset-v1` eksportuje tylko decyzje `accepted`, deduplikuje
   identyczne binaria i zachowuje wszystkie wystąpienia,
4. trening używa osobnych zdjęć źródłowych dla zbioru treningowego i walidacyjnego,
5. klasyfikator zwraca `symbol_id`, confidence i kilka alternatyw,
6. inferencja produkcyjna używa wersjonowanego modelu ONNX,
7. niski confidence trafia do manual review.

Docelowy punkt startowy do walidacji to około 100 wycinków na symbol z wielu
zdjęć. Nie zakładamy samodzielnego odkrycia poprawnych klas bez zatwierdzonych
etykiet. Numery 1–387 i 5805 cropów nie są jeszcze etykietami symboli, a dane
fixture M1/M4 nie mogą ich zastąpić.

Pierwszy bootstrap obejmuje ręczne zatwierdzenie pełnych layoutów z różnych
zdjęć i pozycji, orientacyjnie 15–30 layoutów, a nie 5805 osobnych ekranów.
Trening nie mutuje modelu po każdym kliknięciu. Każda iteracja ma jawny
dataset, konfigurację, seed, model version i raport held-out. Po pierwszej
wersji modelu review priorytetyzuje niepewne albo reprezentatywne przypadki.
Auto-accept pozostaje wyłączone do zaakceptowanej kalibracji confidence.

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

Dla symboli podstawowym ekranem bootstrapu jest pełny layout 5 × 3 z siatką,
15 przewidywaniami, confidence i skrótami. Niepewne komórki są wyróżnione,
ale administrator może poprawić każdą komórkę. Osobny tryb geometrii pozwala
skorygować cztery narożniki ramy i sprawdzić wynikową siatkę perspektywiczną
przed etykietowaniem; decyzji symbolu nie zapisuje się dla cropu z
niezaakceptowaną geometrią.

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
- skuteczność detekcji oczekiwanego zestawu 1–9 layoutów,
- błąd geometrii komórek,
- accuracy OCR numerów,
- accuracy klasyfikatora per symbol i macierz pomyłek,
- odsetek elementów manual review,
- czas na zdjęcie,
- liczba błędów trwałych,
- odtwarzalność wyniku dla tej samej wersji modeli.

## Walidacja technologii przed wdrożeniem masowym

1. Utrzymywać zaakceptowany korpus 43 zdjęć i rozszerzać go przy pojawieniu się
   nowych gier lub nowych wariantów ekranu.
2. Traktować golden narożników jako wynik wspomaganego algorytmicznie
   przeglądu wizualnego; przed deklaracją generalizacji wykonać niezależny
   pomiar na nowych wariantach.
3. W M6 zbudować oznaczony zbiór symboli z automatycznych cropów i podzielić
   go według zdjęcia źródłowego. Właściciel zatwierdza lub poprawia etykiety,
   ale nie wycina obrazów ręcznie.
4. Zachować zaakceptowane progi przed kolejną optymalizacją; confidence nie może być
   progiem auto-accept bez kalibracji na held-out source images.
5. Porównać wyspecjalizowane alternatywy OCR cyfr na rozłącznym podziale
   źródeł; bieżący OCR pozostaje `manual_review_only`.
6. Zatwierdzić finalne modele i ich wersje w osobnej decyzji architektonicznej.
