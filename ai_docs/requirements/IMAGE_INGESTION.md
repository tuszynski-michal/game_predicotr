---
title: Image ingestion requirements
status: accepted
last_updated: 2026-08-02
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

Przed dużym importem M7.0 może wykonać osobny preselektor opisany w
`requirements/IMAGE_SELECTION.md`. Preselektor redukuje wiele kolejnych ujęć
tego samego ekranu do jednego checksumowanego reprezentanta i nie uruchamia
cropów komórek ani klasyfikacji symboli. Nie zmienia kontraktu pełnego pipeline'u;
jego output jest poświadczonym źródłem wejściowym dla etapu discovery.

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

Pełny pipeline M7 używa kontraktu `image-pipeline-manifest-v1` i dokładnie
uporządkowanych etapów:

```text
discovery → normalization → board_detection → board_crops → sequence_ocr
→ symbol_inference → manual_review → validation
```

Manifest zapisuje wersję każdego adaptera, modelu, preprocessingu, kalibracji
i confidence policy oraz względne ścieżki POSIX i SHA-256 wszystkich artefaktów
modelowych i raportów dowodowych. `pipelineFingerprint` jest SHA-256
kanonicznych bajtów samego manifestu — bez timestampu, ścieżek absolutnych i
danych hosta. Wynik jednego pliku identyfikuje `fileExecutionKey` wyprowadzony z
SHA-256 źródła i `pipelineFingerprint`. Zmiana modelu, checksumy albo dowolnej
wersji pipeline'u tworzy nową tożsamość wyniku i nie nadpisuje poprzedniej.

Obecny OCR i klasyfikator symboli są `manual_review_only`. Dlatego manifest v1
wymusza etap `manual_review`, wyłączone auto-accept/auto-reject oraz stan
`waiting_for_review` po `symbol_inference`. Dopiero kompletna atomowa decyzja
planszy pozwala przejść do `validation`.

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

Po zatwierdzeniu folderu każdy obsługiwany oryginał jest kopiowany do
kontrolowanego `data/originals` pod tożsamością content-addressed. Manifest
zachowuje pierwotną ścieżkę względną, checksumę i wynik kopiowania. Pipeline nie
zależy później od obecności folderu użytkownika.

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

Produkcyjna ścieżka v0.6 zastępuje pośredni raster planszy kontraktem
`board-cell-crops-v17-source-direct-model-input-v1`:

- `500 × 300` jest wyłącznie logiczną płaszczyzną geometrii i nie jest
  materializowanym wejściem modelu ani podglądem Reviewera,
- podgląd planszy jest osiowym wycinkiem z obrazu po korekcie EXIF, zachowanym
  w natywnej skali pikseli bez obrotu, prostowania i zmiany rozmiaru,
- każdy z 15 quadów komórek jest projektowany bezpośrednio z obrazu źródłowego
  do przypiętego rozmiaru wejścia modelu w dokładnie jednym resamplingu,
- inferencja nie skaluje ponownie cropu o już prawidłowym rozmiarze; skalowanie
  pozostaje wyłącznie fallbackiem zgodności dla historycznych artefaktów,
- geometria przechowuje `sourceContextBounds`, `displayAssetKind` oraz
  `cellOutputSize`, aby Reviewer i audyt nie zgadywały pochodzenia obrazu.

Detektor `page-board-detector-v3-unique-partial-grid-v1` może odzyskać brakujące
pozycje siatki 3 × 3 tylko wtedy, gdy istnieje dokładnie jedna poprawna hipoteza
dziewięciu plansz. Zero albo więcej niż jedna hipoteza kończy się fail-closed i
wymaga review; pipeline nie wybiera arbitralnie geometrii.

### Zweryfikowana geometria pełnej strony dla importu `seq_*`

Od v0.6.49 browserowy import z poświadczonym zakresem nie może przekazać do
croppera wyniku częściowego, syntetycznego ani z zerowym dowodem czerwonej
ramki. Przed importem powstaje osobny, wznawialny preflight
`page-board-detector-v4-verified-registration-v1`. Rejestruje on stronę do
jednej z maksymalnie siedmiu ręcznie zweryfikowanych stron-wzorców przez
ORB/RANSAC na obrazie 50%, a następnie przenosi dziewięć niezależnych quadów na
oryginał i lokalnie dosuwa je wyłącznie do czerwonych ramek.

Polityka deskryptora `orb-1000-1500-3000-fallback-v1` najpierw używa 1000
cech. Dopiero gdy ta próba nie przejdzie pełnej bramki, ta sama strona jest
ponawiana z 1500, a następnie z 3000 cechami; wyższy budżet jest więc kosztem
wyłącznie dla wyjątkowych, czytelnych stron o małej liczbie punktów ORB.
Każda próba zachowuje identyczne progi RANSAC i dowodu czerwonej ramki, a wynik
zapisuje użyty budżet oraz wersję polityki w manifeście geometrii.

Wynik jest używalny tylko wtedy, gdy ma wszystkie dziewięć wypukłych,
niepokrywających się quadów w kolejności row-major, co najmniej 35 inlierów,
udział 0,23, p95 reprojekcji nie większe niż 2,5 px oraz pokrycie czerwonej
krawędzi co najmniej 0,70 średnio i 0,45 dla każdej planszy. Wynik preflightu
jest niezmiennym, content-addressed `PageGeometryManifestV1` przypiętym do
joba. Nieudana strona trafia do `Korekty geometrii strony`, a nie do OCR,
symboli ani technicznego `board_detection failed`.

Korekta zapisuje dziewięć finalnych quadów dla checksumy źródła jako append-only
rewizję. Operator najpierw przesuwa cztery uchwyty strony, zachowując strukturę
3 × 3, i może wyjątkowo poprawić pojedynczy quad. Ponowny preflight używa
snapshotu tych override'ów; zatwierdzone numery i ich cropy nie są tym zmieniane.

### 5. Odczyt sequence number

#### Import poświadczonych zakresów `seq_*`

Folder przygotowany przez lokalną selekcję może zawierać nazwy
`seq_<start>-<end>.jpg` albo `.jpeg`. Po wykryciu takiego trybu worker waliduje
każdą nazwę, zakres `1–9` plansz oraz brak duplikatów i nakładania. Zakresy są
sortowane numerycznie po `start`; luki są raportowane, ale nie blokują importu.
Źródłem prawdy jest nazwa pliku, a managed manifest zachowuje
`sequenceRangeStart`, `sequenceRangeEnd` i `sequenceRangeSource=filename`.

Adapter `sequence-number-from-attested-range-v1` nie uruchamia OCR numerów.
Przypisuje numery row-major (`start+0 … start+8`) wyłącznie przy dokładnej,
uporządkowanej liczbie wykrytych plansz. Częściowa geometria trafia do korekty
bez przesuwania pozostałych numerów. Oryginał oraz source-native cropy pozostają
niezmienione.

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
- użytkownik może opcjonalnie zaakceptować lub poprawić numer w review;
  alternatywnie pozostawia brak i doładowuje kolejne zdjęcia, a system nigdy
  nie wymusza ręcznego numerowania całego importu,
- baseline na numerach 1–387 osiąga `247/387 = 63.8243%`; na 31 held-out
  source images wynik to `179/279 = 64.1577%`. Nie spełnia zaakceptowanego
  progu 98% wymaganego do auto-accept.

Benchmark `m5-image-benchmark-v2` potwierdza, że surowy crop z tym samym
modelem jest gorszy (`217/387 = 56.0724%`), więc preprocessing jasnego komponentu
pozostaje lepszym baseline'em. Nie jest to jednak finalny wybór modelu.
Detekcja oczekiwanego zestawu plansz wynosi 100% na 43 zdjęciach. Pełny wynik,
timing i katalog błędów znajdują się w
`ai_docs/quality/m5-image-benchmark-report.json`.

W produkcyjnej ścieżce v0.6 surowy wynik OCR pozostaje niezmienny w polach
`rawText` i `ocrNormalizedNumber`. Dla kompletnej strony dziewięciu pozycji
adapter `sequence-number-ocr-v2-page-continuity-v1` może osobno wyprowadzić
numer domenowy z bazy strony, jeżeli co najmniej trzy odczyty zgodnie wskazują
tę samą bazę i przewaga nad konkurencyjną bazą wynosi co najmniej dwa głosy.
Brak takiego jednoznacznego konsensusu nie uruchamia inferencji ciągłości.

### Status prototypu po D-062

- discovery i normalizacja są zachowywanymi kontraktami,
- geometria strony i pozycje plansz są zaakceptowane dla wariantu do dziewięciu
  plansz 3 × 3; automatyczne quady są wejściem do wersjonowanych profili
  kalibracji,
- podział planszy na komórki v1 i detektorowy wariant v2 pozostają w
  kwarantannie,
- `board-cell-crops-v2-calibrated-v1` jest historyczne i nie może zasilać
  treningu: P95 `1.8337 px` został policzony na tych samych 27 planszach, które
  były anchorami profili, a rzeczywiste review wykazało złe cropy kolejnych
  plansz,
- następna wersja używa lokalnej ramki każdej planszy oraz korekty wyłącznie z
  tego samego source image; brak profilu obrazu daje `needs_review`,
- bramka generalizacji musi używać plansz i pozycji niewykorzystanych do
  kalibracji oraz osobno raportować anchor fit,
- kontrakt OCR zostaje wymienny, a bieżący model działa w trybie
  `manual_review_only`,
- każdy wynik OCR jest sugestią do manual review; nie ma auto-accept,
- continuity może zgłosić problem, ale nigdy nie tworzy zatwierdzonego numeru,
- M6 może korzystać wyłącznie ze skalibrowanych cropów i wraca do eksportu
  etykiet przez TASK-0097; nie zależy to od automatycznej akceptacji OCR.

### 6. Podział na komórki

- wariant D-059 używa wymiarów 3 × 5,
- rozpocznij od quadu detektora wyznaczonego osobno dla każdej planszy,
  zlokalizuj środki symboli w 15 slotach i zastosuj strzeżoną korektę afiniczną,
- skorygowany quad przekształć homografią do RGB 500 × 300, a następnie podziel
  na piętnaście logicznych slotów 100 × 100,
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
- historyczne 18 profili `source_group + board_position` nie może być używane
  produkcyjnie, ponieważ ich clamp po `sequence_number` przenosi perspektywę
  między różnymi zdjęciami,
- profile exact source-image z D-062 pozostają dowodem i artefaktem
  historycznym, ale nie są produkcyjnym źródłem granic pozostałych pozycji,
- strict symbol-aware refinement działa niezależnie per plansza; brak
  wymaganej liczby inlierów albo nieprawdopodobny transform blokuje stronę,
- tylko odrzucone obserwacje są korygowane ręcznie; benchmark TASK-0101
  skierował do tej kolejki 6 z 387 plansz,
- automatyczne zastosowanie wymaga zaakceptowanego przeglądu kompletnej strony.

Po odrzuceniu osiowego wariantu v9 kandydat korekcyjny musi zachować
perspektywę quadu detektora i wyznaczać homografię z całej znanej siatki
symboli 5 × 3. Cztery wirtualne narożniki wynikają ze wszystkich inlierów
RANSAC, nie tylko z czterech skrajnych symboli. Brak pełnego pokrycia rzędów
lub kolumn, przekroczenie residualu, nieprawdopodobna siatka albo brak
źródłowych pikseli wymaganych przez finalny padding blokują automatyczne
cięcie. Przed pełnym korpusem obowiązuje mała bramka regresji na wskazanych
błędach i czystych kontrolach.

W aktualnym kandydacie globalne komponenty symboli muszą zostać przypisane do
5 × 3 przed refinementem lokalnym. Płaszczyzna 500 × 300 służy do detekcji i
estymacji, ale nie ogranicza dostępnych pikseli zdjęcia źródłowego. Finalny
fixed padding jest projektowany bezpośrednio na znormalizowane źródło i może
zostać przyjęty tylko wtedy, gdy wszystkie cztery narożniki każdej komórki są
w jego granicach oraz support fraction wynosi dokładnie `1.0`.

Regresja v13 przechodzi dla `29`, `4`, `6`, `7`, `26`, `30` i 12 kontroli.
Brak kompletnego przypisania na kontrolach `3` i `11` nadal blokuje pełny
korpus, publikację cropów i trening. Nie wolno zastępować tej blokady
obniżeniem progów homografii ani syntetycznym uzupełnianiem pikseli.

V14 może ponowić analizę na `boundingBox` z paddingiem `6% × 4%` wyłącznie po
jednym z trzech błędów globalnego locatora: braku komponentów, nieudanym
przypisaniu osi albo zbyt małej liczbie przypisań. Bounding box nie może stać
się finalną geometrią komórek; retry musi ponownie przejść pełne globalne
przypisanie, guardy homografii i preflight realnego źródła. Ograniczona bramka
v14 przechodzi technicznie `20/20`, lecz pełny korpus, publikacja cropów i
trening pozostają zablokowane do jawnej akceptacji wizualnej galerii przez
właściciela.

Po akceptacji ograniczonej galerii pełny preflight musi nadal przejść
`387/387` plansz i `5805/5805` komórek. Wynik `373/387` z 14 kontrolowanymi
fallbackami nie jest częściowym sukcesem produkcyjnym: zapisane artefakty
pozostają diagnostyczne, a publikacja i trening są zablokowane do usunięcia
wszystkich 14 blokad oraz końcowego page-level review.

Zgodnie z D-067 te 14 fallbacków można naprawić jako exact-observation:
właściciel ustawia cztery narożniki pełnej siatki symboli 5 × 3 i potwierdza
podgląd wszystkich 15 komórek. Korekta jest przypisana do checksum obrazu oraz
pozycji planszy, nie zmienia numeru sekwencji i nie obniża progów automatycznych.
Trening pozostaje zablokowany do ponownego pełnego wyniku `387/387`.

Końcowy merge nie przelicza ponownie zaakceptowanych wyników automatycznych.
Weryfikuje checksumy i ponownie wykorzystuje 373 niezmienne plansze v14, a
generuje wyłącznie 14 zaakceptowanych exact-observation override'ów. Wynik
techniczny musi mieć `387/387`, `5805/5805`, `0` fallbacków i przejść drugi
przebieg reprodukowalności przed końcowym przeglądem stron.

### 7. Klasyfikacja symbolu

1. produkcyjny `symbol-crop-inventory-v3` weryfikuje zaakceptowany raport v16,
   osobną akceptację właściciela, pełny łańcuch checksum oraz wszystkie
   materializowane plansze i komórki; tworzy stabilną tożsamość obserwacji bez
   przypisywania klasy,
2. administrator dostarcza jawnie przejrzane decyzje
   `reviewed-cell-labels-v1` dla symboli tej samej gry,
3. `labeled-symbol-dataset-v1` eksportuje tylko decyzje `accepted`, deduplikuje
   identyczne binaria i zachowuje wszystkie wystąpienia; historyczny inwentarz
   v1 jest odrzucany, a manifest zachowuje pełną proweniencję kalibracji,
4. trening używa osobnych zdjęć źródłowych dla zbioru treningowego i walidacyjnego,
5. klasyfikator zwraca `symbol_id`, confidence i maksymalnie cztery
   uporządkowane alternatywy,
6. inferencja produkcyjna używa wersjonowanego modelu ONNX,
7. niski confidence trafia do manual review.

Docelowy punkt startowy do walidacji to około 100 wycinków na symbol z wielu
zdjęć. Nie zakładamy samodzielnego odkrycia poprawnych klas bez zatwierdzonych
etykiet. Numery 1–387 i 5805 cropów nie są jeszcze etykietami symboli, a dane
fixture M1/M4 nie mogą ich zastąpić.

Pierwszy bootstrap obejmuje ręczne zatwierdzenie pełnych layoutów z różnych
zdjęć i pozycji, orientacyjnie 15–30 layoutów, a nie 5805 osobnych ekranów.
Lokalne narzędzie TASK-0097 grupuje `symbol-crop-inventory-v3` po stabilnym
`boardId`, pokazuje kanoniczną planszę i wszystkie piętnaście cropów row-major.
Decyzja pojedynczej komórki zapisuje się atomowo w
`reviewed-cell-labels-v1`; częściowa plansza pozostaje `pending` i wznawia się
po restarcie. Plansza jest kompletna dopiero po jawnej decyzji dla wszystkich
15 komórek.
Trening nie mutuje modelu po każdym kliknięciu. Każda iteracja ma jawny
dataset, konfigurację, seed, model version i raport held-out. Po pierwszej
wersji modelu review priorytetyzuje niepewne albo reprezentatywne przypadki.
Auto-accept pozostaje wyłączone do zaakceptowanej kalibracji confidence.

Kalibracja TASK-0063 dopasowuje jedną temperaturę wyłącznie na source-disjoint
validation i używa testu tylko do końcowego pomiaru. Próg auto-accept wymaga
jednocześnie dojrzałego statusu modelu, osiągniętego celu liczności datasetu,
co najmniej 95% precision na minimum 20 próbkach validation oraz co najmniej
90% precision na minimum 3 próbkach każdej klasy. Brak dowodu wyłącza
auto-accept; niskie confidence nigdy nie odrzuca próbki automatycznie.
Aktualny model bootstrapowy nie spełnia tych bramek, dlatego każda predykcja
pozostaje decyzją człowieka.

Bootstrap katalogu `0.2` porównuje liczbę proponowanych klastrów z oczekiwaną
liczbą symboli. Różnica blokuje automatyczne utworzenie katalogu i pokazuje
użytkownikowi kandydatów do scalenia, rozdzielenia albo przypisania. System nie
interpretuje samodzielnie dodatkowego klastra jako nowego symbolu ani niedoboru
jako potwierdzonego scalenia.

Implementacja TASK-0125 używa rzeczywistych cropów i wersjonowanych predykcji
produkcyjnego klasyfikatora jako deterministycznych grup startowych. Nie czyta
`examples/imgs` i nie tworzy syntetycznych grafik. Najwyższe confidence z
deterministycznym tie-breakiem wybiera reprezentanta grupy; pełny run zachowuje
checksumę źródła. Ręczne rozstrzygnięcie jest wymagane przed utworzeniem
katalogu, jeżeli liczba grup różni się od oczekiwanej.

Kolejny batch active-learning zawiera całe pending layouty 5 × 3. Ranking
łączy niepewność pięciu najbardziej niepewnych komórek, różnorodność rozkładu
predykcji, nowe zdjęcie źródłowe i niedoreprezentowaną przewidywaną klasę.
Do wyczerpania źródeł wybiera najwyżej jedną planszę z jednego zdjęcia.
Kolejka nie zapisuje ani nie zmienia `reviewed-cell-labels-v1`.

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

Jeżeli kilka źródeł przedstawia ten sam `sequence_number`, pipeline zapisuje
uporządkowany ranking jakości obejmujący co najmniej ostrość, kompletność
symboli i geometrię. Najlepszy kandydat jest domyślny, ale Reviewer pozwala
ręcznie wybrać inne źródło; decyzja zachowuje aktora, metryki i pochodzenie.

Dla symboli podstawowym ekranem bootstrapu jest pełny layout 5 × 3 z siatką,
15 przewidywaniami, confidence i skrótami. Niepewne komórki są wyróżnione,
ale administrator może poprawić każdą komórkę. Osobny tryb geometrii pozwala
skorygować cztery narożniki ramy i sprawdzić wynikową siatkę perspektywiczną
przed etykietowaniem; decyzji symbolu nie zapisuje się dla cropu z
niezaakceptowaną geometrią.

Edytor geometrii pokazuje wyłącznie viewport jednej wybranej planszy z
kontrolowanym marginesem, a nie całą stronę zawierającą wiele layoutów.
Viewport jest tylko projekcją UI: cztery narożniki nadal są przechowywane we
współrzędnych oryginalnego zdjęcia, a preview i zapis ponownie wycinają planszę
bezpośrednio z tego oryginału. Dzięki marginesowi reviewer może przesunąć
narożnik poza poprzedni błędny crop i odzyskać ucięte piksele symbolu.

Przed pierwszym modelem pole `prediction/confidence` jest jawnie nieobecne.
Bootstrap nie zgaduje klas: administrator wybiera komórkę na pełnej planszy,
przypisuje znany symbol, odrzuca ją albo cofa decyzję. Filtry i licznik plansz
działają na stanach `pending`, `accepted` oraz `rejected`, a skok po
`sequence_number` nie zmienia decyzji.

Operacyjny import może pozostać w trybie pełnego nadzoru człowieka niezależnie
od jakości auto-accept. Każda accepted/corrected plansza zamraża zaakceptowany
numer, geometrię i dokładnie 15 symboli. Kolejna wersja modelu może obliczyć
nowe sugestie tylko dla elementów nierozwiązanych; nie może nadpisać decyzji
człowieka ani istniejącego stagingu.

Szczegółowy kontrakt skumulowanych kohort, treningu, aktywacji i ponownej
inferencji definiuje `requirements/SUPERVISED_MODEL_IMPROVEMENT.md`. Statusy
`accepted`, `corrected` i `rejected` są chronione; automatyczna nowa predykcja
jest dozwolona wyłącznie dla aktualnego `pending`.

Zmiana geometrii zaakceptowanej albo oczekującej planszy tworzy nowy
wersjonowany zestaw cropów. Etykiety związane ze starym `cropSampleId` nie są
przenoszone niejawnie, a plansza wraca do review. Zaakceptowane korekty
geometrii można później zebrać w osobny, niezmienny materiał do ulepszenia
profilu, ale zastosowanie nowego profilu wymaga jawnej wersji pipeline'u.
Samo zapisanie jednej lub wielu korekt nie trenuje modelu online i nie zmienia
wyniku cięcia kolejnych layoutów w trwającym imporcie.

### 9. Walidacja i commit

Dane są najpierw zapisywane do tabel stagingowych. Utworzenie wersji datasetu wymaga:

- poprawnej liczby komórek,
- symboli należących do gry,
- zaakceptowanych numerów,
- ciągłego `sequence_number` bez luk i duplikatów numerów,
- raportu zduplikowanych sygnatur layoutu,
- idempotentnego importu,
- braku nierozwiązanych elementów blokujących.

W pełni ręcznie zweryfikowany, ciągły zakres może zostać opublikowany przy
`massImportAllowed = false`, ponieważ każdy layout ma decyzję człowieka. Flaga
nadal blokuje automatyczną publikację nierozwiązanych lub auto-zaakceptowanych
elementów i nie jest obchodzona przez samą obecność predykcji.

Kompletność jest liczona względem dodatniego `expected_layout_count` gry,
domyślnie 500 000, ale konfigurowalnego dla małego testu 0.2. Raport musi podać
dokładne liczniki, lecz może zwrócić najwyżej 100 pierwszych brakujących
numerów. Nie wolno tworzyć syntetycznych layoutów tylko po to, aby zamknąć luki.

Jeżeli kilka zaakceptowanych plansz wskazuje ten sam numer, system zachowuje
wszystkie źródła i wybiera jedno deterministycznie na podstawie jawnych metryk
jakości. Operator może wskazać inne źródło albo cofnąć override. Ręczna
korekta numeru domenowego nie zmienia surowej odpowiedzi OCR, a wybrane źródło
zachowuje checksumę, ścieżkę i identyfikatory importu oraz planszy.

## Stan i etapy zadania

```text
status: created | processing | waiting_for_review | completed | failed | cancelled
stage: discovery | normalization | board_detection | board_crops | sequence_ocr
     | symbol_inference | manual_review | validation
```

Status należy do wspólnego automatu jobs. Etap opisuje wyłącznie aktualną część
pipeline'u importu i może zostać rozszerzony bez zmiany cyklu życia.

## Wznawianie

- postęp jest zapisywany co plik lub małą partię,
- błąd jednego zdjęcia nie przerywa całego importu,
- ponowne uruchomienie nie tworzy duplikatów,
- `pipelineFingerprint`, SHA-256 źródła i `fileExecutionKey` są zapisywane z
  checkpointem i wynikiem,
- `completedStages` jest wyłącznie uporządkowanym prefiksem manifestu; retry
  może powtórzyć ten sam checkpoint albo ukończyć jeden następny etap,
- pełna agregacja statystyk wszystkich plików jest dozwolona tylko na wejściu i
  końcowej granicy wykonania handlera; postęp pomiędzy nimi wynika przyrostowo z
  trwałych przejść statusu pojedynczego pliku,
- liczba pełnych agregacji jednego wykonania handlera jest stała i nie rośnie z
  liczbą zdjęć ani etapów,
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

Od M7.3 katalog `data/` jest jedynym zarządzanym rootem image storage.
Inwentarz może odczytywać wyłącznie sześć powyższych przestrzeni, nie podąża
za dowiązaniami symbolicznymi i raportuje liczbę pominiętych dowiązań.
Automatyczne usuwanie jest wyłączone dla każdej przestrzeni. `originals` i
`models` mają politykę `preserve`; pozostałe dane są wersjonowane, ale również
nie mogą zostać usunięte przez TASK-0073.

Wyjątkiem jest jawny reset danych layoutów gry z TASK-0133. Po pokazaniu
pełnego preview i mocnym potwierdzeniu może usunąć zarządzane oryginały oraz
pochodne artefakty należące do resetowanej gry. Fizyczny plik content-addressed
pozostaje, jeżeli ma choć jedną referencję z innej gry. Reset nie przeszukuje
ani nie usuwa plików z pierwotnego folderu użytkownika.

Diagnostyka joba może zostać wyeksportowana jako kanoniczny JSON bez obrazów,
sekretów, stack trace i ścieżek absolutnych. Eksport zawiera dokładne agregaty
oraz uporządkowaną próbkę najwyżej 10 000 błędnych plików z jawnym znacznikiem
obcięcia. Jest zapisywany content-addressed pod
`data/exports/image-jobs/<jobId>/<sha256>/diagnostics.json`, nie jest
nadpisywany, a pobranie ponownie sprawdza SHA-256.

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

Terminalny image import można ponowić bez ponownego uploadu, klonując jego
immutable manifest managed originals do nowego joba. Ponowienie przypina
aktualne wersje pipeline'u, profilu siatki i modelu, ale nie usuwa poprzednich
projekcji ani źródeł; usuwanie nadal wymaga osobnej, jawnie potwierdzonej
operacji resetu.

Model symboli został zatwierdzony w D-088 jako
`production-spatial-symbol-cnn-v1`. Jego automatyczna akceptacja obowiązuje
wyłącznie od checksum-bound progu `0.88850097`; poniżej progu wynik pozostaje
sugestią do manual review. Panel może pokazać najwyżej cztery alternatywy.
Finalny wybór OCR pozostaje otwarty, dlatego automatyczny import całych
layoutów nadal jest zablokowany.

### Przyrostowe importy `seq_*`

Po decyzji `accepted` albo `corrected` numer sekwencji jest kanoniczny w
obrębie gry. Import pliku `seq_<start>-<end>.jpg` korzysta z snapshotu tej
projekcji: kompletne zakresy są pomijane, częściowe generują wyłącznie brakujące
plansze, a inne źródło tego samego numeru pozostaje alternatywą audytową.
Kolejka review jest niezależna od pojedynczego joba i porządkuje oczekujące
numery rosnąco.

Uczenie symboli może działać na istniejących, kompletnych cropach. Jawne
`Przelicz oczekujące` zapisuje nowe rewizje sugestii tylko dla pozycji nadal
`pending`; decyzje człowieka, geometria i staging są chronione transakcją.

### Browser staging i start importu `seq_*`

Browser-native upload layoutów jest dwuetapowy. Finalizacja tworzy trwały
staging z `_browser_manifest.json`; gotowy staging nie wygasa po restarcie API
i może zostać wznowiony z listy Admina. Nie wolno traktować fizycznych nazw
`00000001.jpg` jako nazw domenowych. API i worker odczytują z manifestu
`relativePath` (`seq_<start>-<end>.jpg`) oraz osobne `storedFileName`.

Przed utworzeniem joba Admin wywołuje preflight związany z `gameId` i checksumą
manifestu. Raport pokazuje nowe i kanonicznie użyte ponownie numery, pominięte
źródła, częściowe zakresy, alternatywne checksumy oraz pierwszy i ostatni
nierozwiązany numer. Dopiero jawna akcja startu przekazuje obie checksumy;
backend ponownie wykonuje preflight i odrzuca nieaktualny raport. Powtórzenie
tej samej akcji dla tego samego stagingu zwraca istniejący job (`created=false`)
i nie tworzy duplikatu.

Staging z `purpose=layout_import` może zostać usunięty wyłącznie jawną akcją
Admina. Staging przypisany do innej gry jest ukryty przed bieżącą grą i blokuje
próbę startu. Po skopiowaniu oryginałów worker zachowuje obie tożsamości:
logiczny zakres do audytu oraz fizyczny plik do bezpiecznego kopiowania.
