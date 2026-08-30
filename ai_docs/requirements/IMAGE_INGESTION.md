---
title: Image ingestion requirements
status: accepted
last_updated: 2026-08-23
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
- kontrakt `image-normalization-v2-in-memory-source-v1` stosuje wartości
  Orientation 1–8 przez `ImageOps.exif_transpose`,
- wynik jest czystą macierzą RGB utrzymywaną wyłącznie w ograniczonym cache
  bieżącego wykonania; stage result zapisuje wymiary, orientację i checksumę
  pikseli, ale nie pełnowymiarowy PNG,
- przygotowanie kopii roboczych w przestrzeniach kolorów potrzebnych algorytmom,
- opcjonalna korekta jasności i kontrastu wyłącznie w kopii,
- zachowanie oryginału bez modyfikacji,
- ponowna weryfikacja discovery manifestu i SHA-256 przed dekodowaniem,
- managed original pozostaje niezmiennym źródłem ponownego dekodowania,
- diagnostyka zawiera źródłowy SHA-256, checksumę pikseli, wymiary, tryb,
  orientację, transformację i wersję adaptera,
- limit 50 000 000 pikseli na źródło ze stabilnym błędem.

Historyczny kontrakt v1 pozostaje odtwarzalny. Jeśli jego PNG został bezpiecznie
usunięty, retry odbudowuje dokładne bajty z managed original i wymaga zgodności
z checksumą stage result; drift kończy się fail-closed.

#### Wirtualne renderowanie komórek 0.10

- `CanonicalSourceLoader` utrzymuje najwyżej jedno bieżące źródło i nie może
  dekodować tego samego managed original ponownie w obrębie wykonania;
- źródłowy SHA-256, wymiary po EXIF oraz checksum pikseli muszą zgadzać się z
  przypiętą proweniencją przed użyciem geometrii;
- `virtual-cell-renderer-source-direct-v1` najpierw waliduje wszystkie komórki
  źródła, a następnie wykonuje dokładnie jeden source-direct resampling na
  komórkę; nie materializuje pośredniej planszy ani trwałego cropa;
- wynik zawiera RGB, logiczny klucz komórki, content-addressed render spec,
  wersję extractora i checksumę dokładnych pikseli;
- wariant bezpośredni musi pozostać pikselowo zgodny z historycznym v19 przy
  tej samej geometrii, paddingu, interpolacji i rozmiarze wyjścia;
- warianty native-bbox i rectified-board są wyłącznie diagnostyczne i nie mogą
  zostać wybrane przez produkcyjny pipeline bez nowej wersji oraz bramki;
- job przypina niezmienny snapshot rolloutu gry. `legacy` zachowuje
  `legacy_file`, `structured_shadow` dual-write'uje wynik virtual bez zmiany
  decyzji legacy, `structured_review` zatrzymuje źródło przed inferencją, a
  `structured_default` zapisuje lekkie rekordy `virtual_source` bez PNG;
- wariant virtual renderuje najwyżej 135 komórek jednego źródła w pamięci i
  wykonuje jedno zbiorcze wywołanie ONNX. Restart musi odtworzyć identyczny
  render spec i checksumę pikseli z managed original.

Render spec v2 emituje równolegle historyczne `logical-cell-v1` i
`render-id-v1` oraz nowe `logical-cell-v2` i `render-id-v2`. Klucze v1 pozostają
bitowo niezmienione na potrzeby replayu. V2 wiąże komórkę z wystąpieniem
`importJobId + fileExecutionKey`, fingerprintem przypiętej topologii, slotem
planszy i pozycją komórki. Identyczne bajty zaimportowane w dwóch jobach nie
mogą więc otrzymać tej samej domenowej tożsamości v2. Automatyczny pipeline i
ręczny source-direct preview/save muszą wyprowadzać wystąpienie z dokładnie tej
samej pary identyfikatorów. Checksum JPEG-a pozostaje dowodem integralności i
deduplikacji treści, a nie tożsamością wystąpienia.

Nowe zapisy po TASK-0327 używają render specu v3. Spec musi jawnie zawierać
pełny payload occurrence, fingerprintowany snapshot topologii, wersję
geometrii, checksumę znormalizowanego RGB i wersję polityki checksummy pikseli.
Logical-cell v1/v2 oraz render identity v1/v2 muszą być możliwe do niezależnego
przeliczenia z tych pól. Rozbieżność jest błędem fail-closed także wtedy, gdy
sam zmieniony JSON ma ponownie poprawnie obliczoną checksumę.

`renderSpecChecksumSha256` i `renderedPixelChecksumSha256` są rozłączne:
pierwsza wiąże przepis i proweniencję, druga dokładne wymiary i bajty RGB.
Checksuma wyniku nie należy do checksummowanego specu. Konsument najpierw
waliduje spec oraz źródło, następnie regeneruje piksele i osobno porównuje ich
checksumę. Historyczne specy pozostają odtwarzalne bez przepisywania.

### 2.2. Globalna inicjalizacja geometrii 0.10

`structured-opencv-global-initialization-v1` przyjmuje wyłącznie kanoniczny
RGB po jednym EXIF transpose oraz kontrakt zakresu `seq_*`. Aktywne pozycje są
zawsze prefiksem `0..N-1`; nieaktywne pozycje nie mogą zostać zsyntetyzowane.

Jeżeli gra ma profil zatwierdzonych stron, inicjalizacja wykorzystuje ORB na
obrazie 50%, RANSAC oraz deterministyczny wybór anchora według liczby inlierów,
ich udziału, błędu reprojekcji i checksummy źródła. Bez profilu używa trzech
niezależnych dowodów: czerwonych ramek, gradientów grayscale oraz odcinków LSD,
a następnie dopasowuje oczekiwany układ aktywnych slotów. Brak kompletnego
dowodu zwraca `needs_manual_review`, bez częściowego wyniku.

Globalna homografia i `initialQuad` są wyłącznie początkowym ROI dla lokalnego
dopasowania każdej planszy. Nie są finalną geometrią, nie pozwalają uruchomić
croppera ani inferencji symboli i nie zastępują bramek TASK-0311. Wynik wiąże
źródło, topologię, profil, wersję konfiguracji oraz metryki checksumą, ale nie
tworzy bitmapy. TASK-0310 nie podłącza silnika do pipeline'u produkcyjnego.

### 2.3. Niezależne lokalne dopasowanie plansz 0.10

`structured-opencv-independent-board-refinement-v1` konsumuje początkowe ROI
TASK-0310 osobno dla każdego aktywnego slotu. ROI jest prostowane wyłącznie w
pamięci i wyłącznie do analizy linii. LSD grupuje sześć pionowych oraz cztery
poziome granice siatki 5 × 3, a odpornie dopasowana homografia idealnej siatki
jest następnie rzutowana do źródła. Finalny quad nie musi być prostokątem,
rombem ani mieć kątów prostych w przestrzeni zdjęcia.

Automatyczny wynik wymaga jednocześnie kompletu czterech granic z dowodem linii
lub czerwonej ramki, co najmniej 5/6 pionów, 3/4 poziomów, 18/24 wspartych
przecięć, p95 reprojekcji nie większego niż 2,5 px na obrazie 50%, pełnego
source support wszystkich padded cell quads, zgodności z inicjalizacją,
row-major oraz braku niedozwolonego nakładania plansz. Jedna brakująca linia
wewnętrzna może zostać wyprowadzona tylko przy kompletnych granicach
zewnętrznych; nie może przesunąć indeksów siatki.

Confidence geometrii składa się jawnie z globalnej rejestracji, pokrycia linii
i przecięć, regularności odstępów, reprojekcji, dowodu ramki, kolejności slotu
oraz source support. Nie przyjmuje etykiet ani confidence klasyfikatora symboli.
Próg co najmniej `0,85` wraz ze wszystkimi hard gates daje `automatic`, zakres
`0,65–0,85` albo miękka niezgodność daje `needs_manual_review`, a niższy wynik
lub dowolny hard failure daje `needs_manual_correction` ze stabilnymi reason
codes. TASK-0312 podłącza wynik do pipeline'u wyłącznie przez przypięty tryb
gry; legacy pozostaje dokładnie odtwarzalne, shadow nie zmienia wyniku
domenowego, review nie uruchamia inferencji, a default nie renderuje slotu bez
finalnej geometrii.

### 2.4. Produkcyjny rollout geometrii i assetów 0.10

- `image_geometry_rollout_states` jest odczytywany przy tworzeniu joba, a jego
  snapshot wraz z checksumą trafia do input payloadu. Zmiana trybu gry nie
  może zmienić istniejącego joba.
- Fingerprint `legacy` pozostaje byte-for-byte historyczny. Dla trybu 0.10
  fingerprint wiąże legacy fingerprint z checksumą snapshotu rolloutu.
- `structured_shadow` wykonuje legacy jako primary, a Structured OpenCV,
  virtual renderer i predykcje zapisuje jako shadow provenance.
- `structured_review` zapisuje źródłową geometrię i deferrals, lecz nie tworzy
  automatycznych plansz ani nie wywołuje modelu symboli.
- `structured_default` projektuje tylko sloty z disposition `automatic`,
  zapisuje source geometry revision, virtual observations oraz prediction
  revision i nie tworzy board/cell PNG.
- Zapis rozpoznania ponownie sprawdza bieżącego kanonicznego właściciela
  `game + sequence_number`; wynik człowieka wygrywa, a nowe źródło jest jedynie
  alternatywą. Replay identycznych checkpointów jest idempotentny.

Cutover jest fail-closed i używa wyłącznie kompletnego raportu board-level.
Próbka musi obejmować minimum 100 ręcznie sprawdzonych źródeł, 500 aktywnych
plansz, pięć bucketów jakości/kąta, wszystkie historyczne false-success i
failures oraz holdout rozłączny od strojenia. Wynik co najmniej 98% jako jedyny
pozwala wybrać `structured_default` / `virtual_default`; 95–98% pozostaje w
`structured_review` / `virtual_shadow`, a wynik poniżej 95% utrzymuje
`legacy` / `legacy_files`. Brak raportu albo niegotowa walidacja proweniencji
nie zmienia bieżącego trybu i nie jest traktowana jak wynik poniżej 95%.

Odbiór TASK-0318 nie znalazł kompletnego raportu 0.10, dlatego nie promuje
żadnej gry ani domyślnego silnika. Stare cropy, aliasy Reviewera i ścieżki
legacy pozostają wymaganym rollbackiem. Szczegóły dowodów i procedura są w
`ai_docs/quality/V0_10_VIRTUAL_GEOMETRY_CUTOVER.md`.

### 2.5. Eksperymentalny fallback keypoint

TASK-0319 udostępnia wyłącznie shadow-only `KeypointGeometryEngine`. Bezpośrednia
decyzja właściciela pozwoliła zbudować eksperyment mimo braku wyniku `<95%`, ale
nie zastępuje bramki cutoveru TASK-0318 i nie pozwala aktywować modelu. Model
zwraca cztery heatmapy narożników dla każdego z dziewięciu slotów oraz osobną
obecność slotów. Poświadczony zakres `seq_*` pozostaje źródłem aktywnej maski;
predykcja nie może dodać nieaktywnego slotu.

Trening przyjmuje wyłącznie niezmienny manifest ręcznie zatwierdzonych quadów.
Split jest deterministyczny i rozłączny po `sourceFamilyId`, a managed JPEG jest
ponownie sprawdzany przez ścieżkę, SHA-256, format oraz wymiary po EXIF. Eksport
ONNX jest związany checksumą i może działać tylko przez lokalny CPU adapter.
Predykowane quady są wyłącznie inicjalizacją: finalny wynik musi przejść przez
ten sam niezależny refiner linii, source support, row-major, overlap oraz
pozostałe hard gates co Structured OpenCV. Niepełna obecność, słaby narożnik
albo niepoprawny quad kończą się fail-closed.

Manifest release'u ma zawsze `shadowOnly=true` i `activationAllowed=false`.
TASK-0319 nie dodaje trybu w bazie, nie podpina modelu do produkcyjnego
pipeline'u, nie uruchamia treningu na danych użytkownika i nie wprowadza
segmentacji, Ultralytics ani GPU.

### 2.6. Read-only feasibility przed dalszym cutoverem

Przed kolejnym rozszerzeniem Structured OpenCV obowiązuje ograniczony,
niedestrukcyjny spike na 30–50 rzeczywistych zdjęciach. Korpus powinien
obejmować co najmniej dwie gry, pełne i częściowe strony, zróżnicowany kąt,
jasność, rozmycie, odblaski i zasłonięcia oraz co najmniej trzy historyczne
false-success. Brak pokrycia nie może być interpretowany jako GO albo NO-GO;
raport otrzymuje wtedy jawny status `insufficient_corpus`.

Runner weryfikuje manifest i SHA-256 JPEG-ów, nie czyta ani nie zapisuje bazy,
nie zmienia canonical ownership i zapisuje wyłącznie regenerowalne JSON-y,
overlaye oraz contact sheets do wskazanego katalogu raportu. Dla każdego slotu
porównuje oddzielnie inicjalizację globalną, projekcję znanego układu, wynik
hybrydowy, lokalne doprecyzowanie startujące z ręcznej geometrii oraz dostępny
wynik historycznego detektora. LSD jest tylko jednym z dowodów; raportuje się
również Hough, profile gradientów, ramkę zewnętrzną, regularność 5×3 i
pomocnicze pokrycie centrów symboli.

Pierwszy przebieg TASK-0323 objął 43 zdjęcia i 387 plansz jednej gry. Projekcja
znanego układu miała 323/324 prowizorycznie poprawnych quadów, a lokalne
doprecyzowanie z oracle 380/382, jednak wszystkie wyniki zostały odrzucone
przez bieżące hard gates, przede wszystkim wymagające kompletu linii
wewnętrznych. Generyczna inicjalizacja bez profilu nie dostarczyła finalnych
quadów. Wynik uzasadnia dalszy read-only eksperyment oparty na ramce zewnętrznej,
znanym układzie i regularności, ale nie zezwala na rollout ani zmianę progów
produkcyjnych. Pełny raport i ograniczenia korpusu opisuje
`ai_docs/quality/STRUCTURED_GEOMETRY_FEASIBILITY_SPIKE_V1.md`.

Konfiguracja kandydata
`structured-opencv-geometry-config-v2-multi-evidence-experimental-v1` jest
wyłącznie kontraktem kolejnego read-only pomiaru. Dobiera skalę analizy
adaptacyjnie, zachowując minimalny rozmiar lokalnego ROI, a tolerancję
reprojekcji wyraża jako ułamek przekątnej komórki. Ramka zewnętrzna, znany
układ, regularność, LSD, Hough, profile gradientów i centra symboli pozostają
osobnymi, checksummowanymi sygnałami. Brak LSD nie jest samodzielnym veto przy
mocnej ramce, znanym układzie i regularności; samo LSD również nie może
utworzyć automatycznego wyniku. Homografia, source support, alignment,
row-major i brak overlapu pozostają twardymi bramkami.

Wartości v2 mają status `experimental_measurement_only`, wymagają rozłącznych
źródeł strojenia i oceny oraz mają `activationAllowed=false`. Opcjonalny profil
gry jest częścią checksummy konfiguracji. W `structured_shadow` pełny payload
configu i jego check­suma są przypinane do niezmiennego snapshotu joba. Worker
zapisuje osobny, checksummowany `structuredGeometryCandidateV2`, związany ze
źródłem, znormalizowanymi pikselami i wynikiem Structured OpenCV v1. Kandydat
używa finalnego quada v1 wyłącznie jako ROI pomiarowego i nie może sterować
cropami, inferencją, review, canonical ownership ani treningiem. Historyczne
snapshoty v1 i fingerprint `legacy` pozostają bitowo niezmienione. Integracja
shadow nie zezwala na rollout; rozszerzony korpus D-266 nadal jest wymagany
przed decyzją aktywacyjną.

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

Domyślny cropper `board-cell-crops-v18-source-direct-validated-v1` pozostaje
niezmieniony do czasu odbioru następcy. TASK-0249 wprowadza najpierw nieaktywny
kontrakt `BoardCellGeometryManifestV1` dla
`board-cell-geometry-v19-multi-point-source-direct-v1`:

- geometria komórek jest osobnym artefaktem od `PageGeometryManifestV1`;
  poprawne położenie dziewięciu plansz nie jest automatycznie dowodem poprawnych
  granic 15 komórek,
- cztery punkty `latticeBoundsQuad` oznaczają TL/TR/BR/BL zewnętrznych granic
  siatki symboli 5 × 3 w pikselach źródła,
- perspektywiczny quad musi być wypukły i uporządkowany, ale boki nie muszą być
  prostopadłe ani równoległe na zdjęciu,
- 15 `cellQuads` ma dokładną kolejność row-major i jest deterministycznie
  wyprowadzane z tego samego transformu projektowego; rozbieżność blokuje
  manifest,
- geometria automatyczna musi zachować wersje locatora, homografii i progów,
  co najmniej 10 wiarygodnych centrów, 9 inlierów oraz pokrycie 3 wierszy i
  5 kolumn; geometria ręczna zamiast syntetycznych metryk przechowuje checksumę
  decyzji,
- manifest jest kanoniczny i content-addressed. Zmiana źródła, etykiety,
  kolejności, granic albo proweniencji zmienia checksumę.

Rzeczywisty descriptor `board-cell-geometry-v19-real-corpus.json` przypina 27
zaakceptowanych przez właściciela geometrii: trzy dla każdej z dziewięciu
pozycji, z dwóch rodzin źródeł. Weryfikuje checksumy źródłowego manifestu,
goldena i JPEG-ów.

Estymator `board-cell-geometry-v19-multi-point-source-direct-v1`
wykrywa komponenty na całej płaszczyźnie planszy, buduje ograniczony zbiór
hipotez wspólnych osi 5 × 3 i dopiero po jednoznacznym przypisaniu dopasowuje
homografię guarded RANSAC. Przejście wymaga co najmniej 10 przypisań, 10
wiarygodnych centrów, 9 inlierów, wszystkich wierszy i kolumn oraz P95
residualu nie większego niż 10 px. Zewnętrzne granice siatki i wszystkie 15
komórek są następnie projektowane do pikseli źródła; estymator nie tworzy cropu
ani pośredniego obrazu planszy.

Regresja rzeczywistego corpusu przechodzi automatycznie `25/27` plansz z
maksymalnym średnim błędem czterech narożników `6,25 px`. Dwie plansze z
częściową okluzją pozostają fail-closed: jedna ma 8 inlierów, a druga tylko 9
globalnych przypisań. Estymator działa w pełnym adapterze v20 opisanym poniżej.
Historyczne joby v18 pozostają odtwarzalne, ale nie są tworzone przez bieżący
workflow importu.

Checkpoint `board-cell-geometry-v19-real-page-audit-v1` wybiera 100 stron
deterministycznie przez ranking SHA-256, sprawdza źródłowe checksumy i uruchamia
estymator dla wszystkich 900 plansz. Raport jest content-addressed i nie zapisuje
bezwzględnej ścieżki źródła. Audyt próbki z 20 sierpnia 2026 zaakceptował
wszystkie 888 wyemitowanych geometrii bez przesunięcia o wiersz/kolumnę i bez
symbolu poza komórką. Pozostałe 12 plansz było kontrolowanymi fallbackami bez
quadów komórek. Ten checkpoint jest bramką osobno aktywowanego pending-only
recropu; nie przełącza pełnego pipeline'u importu.

Cropper
`board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1` konsumuje
wyłącznie kompletny, zwalidowany `BoardCellGeometryEntry`. W kanonicznym slocie
`100 × 100` stosuje stały inset `10 px`, projektuje padded quad do źródła i
wykonuje jeden `warpPerspective` bezpośrednio z oryginalnego RGB do rozmiaru
wejścia przypiętego modelu. Nie materializuje planszy `500 × 300`, nie wykonuje
drugiego `resize` i nie używa border replication. Cały komplet 15 komórek,
evidence, wymiary i położenie padded quadów jest sprawdzany przed pierwszym
resamplingiem; błąd daje `needs_review` bez częściowych cropów. Konfiguracja
paddingu, interpolacji, geometrii, brzegu i rozmiaru wyjścia jest objęta
fingerprintem. Historyczny tryb v18 pozostaje odtwarzalny, natomiast bieżący
adapter v20 używa croppera v19 w każdym nowym pełnym imporcie.

Ręczny podgląd `manual-board-cell-geometry-v19-preview-v1` konsumuje te same
cztery granice `latticeBoundsQuad`, wyprowadza 15 komórek tym samym kontraktem
i uruchamia dokładnie ten cropper v19 dla rozmiaru modelu `64 × 64`. Odpowiedź
HTTP jest contact sheetem `5 × 3` z finalnych cropów; nie jest kanoniczną
planszą `500 × 300`, nie zapisuje artefaktów i nie aktywuje v19 w produkcyjnym
pipeline. Cztery uchwyty krawędziowe UI są wyłącznie pochodne i nie stanowią
wejścia geometrii.

Ręczny zapis `manual-board-cell-geometry-v19-append-only-v1` ponownie wykonuje
ten sam walidowany preview i utrwala wyłącznie jego 15 finalnych cropów
source-direct. Każdy zapis tworzy nowy namespace rewizji; pliki i rekordy
wcześniejszej rewizji nie są nadpisywane. Checksum decyzji obejmuje checksumę i
tożsamość źródła, source-order, pozycję planszy, numer sekwencji,
`latticeBoundsQuad`, wersje geometrii i croppera, oczekiwane rewizje, checksumę
komendy oraz aktora. Historyczny `manual-review-geometry-v1` pozostaje
odtwarzalny, lecz nie obsługuje aktywnego edytora v19.

Zapis zachowuje istniejący source-native obraz referencyjny bez tworzenia
pośredniej planszy `500 × 300`, tworzy nowe `cropSampleId` dla 15 nowych
checksum i zatwierdza utworzoną rewizję geometrii. Zatwierdzone etykiety
pozostają logicznie zatwierdzone, lecz ich poprzednia tożsamość cropa nie jest
automatycznie przepisywana na nowe piksele. Nowy crop nie kwalifikuje się do
treningu do czasu jawnej ponownej weryfikacji. Pole oznaczone wcześniej jako
`grid_issue` wraca po recropie jako `pending`; komplet pozostałych etykiet może
ponownie domknąć planszę przez atomowy koordynator decyzji.
Nie aktywuje estymatora v19 dla pipeline'u ani pending-only recropu innych
plansz.

Jawny pending-only adapter `pending-board-cell-recrop-v19-v1` jest odrębną
operacją od zapisu ręcznego i pełnego importu. Job przypina checksumę
zaakceptowanego audytu 100 stron oraz wersje i fingerprinty locatora,
homografii, progów, estymatora, geometrii i croppera. Historyczny job schema v1
pozostaje odtwarzalny; nowe uruchomienie używa schema v2.

Adapter bierze istniejący zweryfikowany quad planszy i nie uruchamia ponownie
discovery, detektora strony ani OCR numerów. Tylko kompletne evidence 3 × 5
może utworzyć 15 source-direct cropów i append-only rewizję geometrii. Brak
pełnej geometrii pozostawia planszę w review bez częściowych plików.

Przed integracją następcy pełnego pipeline'u istnieje osobny trwały kontrakt
`BoardCellProcessingManifestV1`. Manifest jest content-addressed i przypina
poświadczony numer, źródło, oczekiwane rewizje oraz wersje i fingerprinty
pipeline'u, estymatora i croppera. Nie zawiera obrazu ani 15 predykcji.

Niewiarygodny wynik geometrii zapisuje się w
`image_board_geometry_pending` z jednym z zamkniętych powodów:
`insufficient_centers`, `incomplete_lattice`, `residual_too_high` albo
`source_unavailable`. Stan `pending` może przejść wyłącznie do `resolved` albo
`superseded`. Równoległa decyzja człowieka lub zmiana przypiętej rewizji zawsze
prowadzi do `superseded`; automat nie nadpisuje decyzji. Sam kontrakt nie
aktywuje v19 w pełnym imporcie i nie zmienia historycznego v18.

Przypięty kontrakt pełnego importu
`board-cell-processing-v20-verified-v19-v1` integruje ten fallback z workerem
i jest domyślnym pipeline'em nowych importów. Żądanie startu domyślnie używa
`boardCellProcessingMode=verified_v19`; klient Admina przekazuje tę wartość
jawnie, a brak pola w API również wybiera v19.
Snapshot przypina wersje i fingerprinty estymatora, progów, croppera oraz
niezmienny manifest cross-staging benchmarku. Fingerprint joba obejmuje cały
snapshot, więc wyników v18 i v20 nie można współdzielić przypadkiem.
Nowe snapshoty przypinają także `gridRows`, `gridColumns` i
`topologyRulesVersionId`. Automatyczny adapter
`board-cell-processing-v20-verified-v19-v1` deklaruje wyłącznie obsługę 3 × 5
i odrzuca inną topologię stabilnym `IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED`.
Wspólny source-direct cropper oraz ręczna geometria dzielą quad generycznie na
`rows × columns` w kolejności row-major; nie tworzą pośredniej bitmapy planszy.
Historyczne snapshoty bez topologii pozostają interpretowane jako 3 × 5 i
zachowują dotychczasowe fingerprinty.

Przed etapem `board_crops` executor zapisuje osobny, niezmienny wynik
`board_cell_geometry`. Dla każdej z dziewięciu plansz dozwolony jest wyłącznie
jeden z wyników: kompletna zweryfikowana geometria 15 komórek albo `deferred`
bez quadów komórek. Cropper v19 zwraca następnie dokładnie 15 source-direct
cropów albo zero. Po błędzie nie wolno uruchomić historycznego v18 jako
fallbacku ani wywołać modelu symboli dla tej planszy. Udane pozycje tej samej
strony mogą kontynuować inferencję i review.

Deferrals są odtwarzane z niezmiennych stage results po restarcie workera oraz
przy job-local rehydration współdzielonego file execution. Exact replay jest
idempotentny, a kontrola rewizji zachowuje zasadę human-wins. Historyczny
benchmark `93,78%` pozostaje audytowalny, lecz właściciel podjął odrębną
decyzję operacyjną o domyślnym użyciu v19 do czasu jej odwołania.

Admin pokazuje v20/v19 dla aktywnego, gotowego browser stagingu po przygotowaniu
raportu i geometrii strony. Każdy nowy staging zaczyna w `verified_v19`, bez
staging-local potwierdzenia. Komenda startu zawsze zawiera ten tryb, a odpowiedź
idempotentnego startu jest uznawana za sukces tylko wtedy, gdy niezmienny
snapshot joba odpowiada v20/v19. Historyczne v18 nie są automatycznym fallbackiem.

Historia importów plansz pokazuje przy każdym jobie przypięty silnik cięcia:
`v18 — tryb historyczny` albo `v20 — geometria i cropy v19`. Etykieta pochodzi
wyłącznie z niezmiennego snapshotu joba; nie zgaduje wersji selektora zdjęć,
jeżeli nie została ona zapisana w payloadzie importu.

Trwały deferred może zostać rozwiązany ręcznie bez ponownego uruchamiania
pipeline'u. Komenda czterech narożników jest związana z checksumą manifestu,
źródła, oczekiwanymi rewizjami oraz snapshotem modelu symboli przypiętym do
źródłowego importu. Podgląd używa croppera v19 i nie zapisuje danych. Zapis
tworzy atomowo jedną zwykłą planszę, dokładnie 15 obserwacji row-major,
append-only rewizję geometrii oraz jeden `pending` item istniejącej kolejki
review. Niepełna geometria albo błąd inferencji nie może utworzyć częściowej
projekcji.

Exact retry tej samej komendy jest idempotentny i nie wykonuje ponownie
inferencji ani zapisu cropów. Ponowne użycie klucza dla zmienionej komendy,
manifestu, źródła, modelu albo rewizji kończy się stabilnym konfliktem.
Istniejąca plansza lub późniejsza decyzja człowieka zawsze wygrywa, a deferred
przechodzi do `superseded`. Ręczne rozwiązanie nie zmienia poświadczonego
numeru `seq_*`, aktywnego modelu ani przypiętego silnika joba.

Benchmark 300 stron osiągnął historycznie `93,78%` pokrycia przy wcześniejszej
bramce `98%`; raport, checksumy dowodowe oraz ograniczenia są opisane w
`ai_docs/quality/BOARD_CELL_GEOMETRY_V19_ROLLOUT.md`. Pomimo tej bramki
właściciel wybrał stały domyślny v19 do jawnego odwołania.

Kwalifikacja początkowa obejmuje tylko `pending`, ale nie jest wystarczającą
ochroną zapisu. Bezpośrednio przed zmianą projekcji worker pod blokadą ponownie
sprawdza status itemu, rewizję resolution, rewizję i całą geometrię planszy,
źródło, pozycję, numer oraz checksumy. Równoległa decyzja człowieka albo
korekta wygrywa; `accepted`, `corrected`, `rejected` i istniejąca ręczna lub
automatyczna geometria v19 nie są zmieniane. Operacja nie zmienia modelu,
katalogu symboli, stagingu ani statusu review.

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

Od v0.7.5 polityka `page-geometry-preflight-v2-auto-anchor` wykonuje najwyżej
dwa dodatkowe przebiegi wyłącznie dla nierozpoznanych źródeł. W każdym
przebiegu może dodać najwyżej 21 perspektyw rozłożonych po naturalnej kolejności
stagingu. Auto-kotwicą może zostać tylko kompletna geometria 3 × 3, która
przeszła zaostrzoną bramkę: co najmniej 60 inlierów, udział 0,35, p95 do
1,75 px, średnie pokrycie czerwonej krawędzi 0,82 i co najmniej 0,65 dla każdej
planszy. Wynik ponowienia nadal musi przejść wszystkie pierwotne twarde progi;
polityka nie syntetyzuje quadów ani nie obniża bramki końcowej.

Ukończony manifest może zawierać zarówno `registered`, jak i
`review_required`. Import kopiuje i przekazuje do croppera wyłącznie źródła
`registered`. Pozostałe źródła są bezpiecznie odroczone i mogą zostać ponowione
po rozszerzeniu profilu lub poprawione ręcznie na końcu pracy. Niepełna
geometria nigdy nie trafia do OCR, cropów ani inferencji symboli. Kanoniczne
numery pozostają pominięte niezależnie od statusu geometrii.

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

Podgląd komórek `virtual_source` dla lokalnego Admina nie materializuje cropów
ani obrazu całej planszy. Endpoint może wyrenderować najwyżej 100 aktualnych
komórek do jednego checksumowanego atlasu WebP, po czym zapisuje go wyłącznie w
krótkotrwałym cache'u pochodnym. Każdy request wiąże rewizję komórki, rewizję
geometrii, checksumę render specu i rendered-pixel SHA-256; zmiana dowolnego z
tych elementów odmawia odczytu, zamiast serwować poprzedni podgląd.

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

Dla importu posiadającego operacyjną kolejkę review `waiting_for_review`
oznacza co najmniej jedną pozycję `pending`. Rozwiązanie ostatniej pozycji
ustawia `completed`; jawne ponowne otwarcie planszy przywraca
`waiting_for_review`. Pusta kolejka nie jest automatycznie uznawana za
ukończony import.

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
- wznowienie najpierw opróżnia wyłącznie trwałe checkpointy `processing`; już
  zapisany checkpoint `waiting_for_review` jest dowodem ukończonej projekcji i
  nie może być ponownie rehydratowany ani zapisywany tylko po to, aby
  potwierdzić nadal oczekującą decyzję,
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
Inwentarz może odczytywać wyłącznie zarządzane przestrzenie `staging`,
`originals`, `working`, `crops`, `training`, `models` i `exports`, nie podąża
za dowiązaniami symbolicznymi i raportuje liczbę pominiętych dowiązań.
Automatyczne usuwanie jest wyłączone dla każdej przestrzeni. `originals` i
`models` mają politykę `preserve`; pozostałe dane są wersjonowane, ale również
nie mogą zostać usunięte przez TASK-0073.

TASK-0306 zastępuje ogólną blokadę usuwania precyzyjną polityką retencji dla
danych odtwarzalnych. Kwalifikacja wymaga niezmiennego manifestu, upływu 24 h
od ostatniej zależności i braku joba `created`/`processing`. `originals`,
referencjonowane cropy, modele, kohorty, snapshoty, release'y, audyt, eksporty
i ręczna selekcja nadal nie podlegają automatycznemu usuwaniu. Browserowy
staging może zostać zakwalifikowany dopiero po kompletnym, checksumowanym
handoffie wszystkich JPEG-ów do managed originals i zakończeniu zależnych
preflightów/importów.

Pełny pomiar przestrzeni nazw jest wykonywany przez bounded job
`storage_inventory` w general lane i zapisywany jako snapshot. Wejście do
panelu nie uruchamia synchronicznego skanu drzewa plików. Panel pokazuje
ostatni pomiar i jawnie rozróżnia tryb obserwacji od aktywnego automatycznego
usuwania.
Do zakończenia pierwszego odbioru ustawienie
`GAME_PREDICTOR_STORAGE_GC_OBSERVE_ONLY` domyślnie ma wartość `false`; capacity
guard nadal blokuje ryzykowne zapisy, ale nie uruchamia destrukcyjnego GC.

Terminalne wykonania pipeline'u mogą po 24 godzinach utracić ciężkie,
odtwarzalne payloady etapów `board_cell_geometry`, `board_crops`,
`sequence_ocr` i `symbol_inference`. Przed usunięciem powstaje checksumowany
manifest zawierający źródło, fingerprint pipeline'u, wersje adapterów,
checksumy etapów i finalne identyfikatory wyników. Bieżące projekcje domenowe,
decyzje, eventy, canonical owner, cropy oraz managed original pozostają.
`board_detection` nie podlega tej kompakcji, dopóki jest źródłem operacyjnej
korekty i kalibracji geometrii. Rerun odtwarza brakujące późne etapy z managed
original i zachowanych etapów wejściowych.

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

Finalizacja zapisuje trwały stan `ready`, a start preflightu lub importu stan
`in_use`. Worker może zapisać `ingested` dopiero po skopiowaniu i ponownej
weryfikacji rozmiaru oraz SHA-256 każdego JPEG-a z manifestu — również źródeł,
które później zostaną pominięte jako kanoniczne lub odroczone przez geometrię.
Po tym handoffie staging może stać się kandydatem GC po 24 godzinach od
ostatniej aktywnej zależności. Historia importu i rerun korzystają wtedy z
niezmiennego manifestu managed originals, a nie z browserowej kopii.

Browserowy import plansz ma osobny limit
`GAME_PREDICTOR_BROWSER_LAYOUT_IMPORT_MAX_BYTES`, domyślnie 20 GiB. Nie dzieli
limitu 1 GiB przeznaczonego dla ręcznych plików CSV/JSONL ani limitu selekcji
zdjęć. Przed utworzeniem stagingu API nadal sprawdza deklarowaną liczbę i
rozmiar plików oraz zachowuje co najmniej 512 MiB wolnej przestrzeni dyskowej.

Przed utworzeniem joba Admin wywołuje preflight związany z `gameId` i checksumą
manifestu. Raport pokazuje nowe i kanonicznie użyte ponownie numery, pominięte
źródła, częściowe zakresy, alternatywne checksumy oraz pierwszy i ostatni
nierozwiązany numer. Dopiero jawna akcja startu przekazuje obie checksumy;
backend ponownie wykonuje preflight i odrzuca nieaktualny raport. Powtórzenie
tej samej akcji dla tego samego stagingu zwraca istniejący job (`created=false`)
i nie tworzy duplikatu.

Preflight porównuje także koniec każdego poświadczonego zakresu z
`games.expected_layout_count`. Końcowy plik może zawierać od jednej do
dziewięciu plansz, np. `seq_499996-500000.jpg`, ale numer większy od granicy gry
kończy się stabilnym `IMAGE_SEQUENCE_PREFLIGHT_OUT_OF_BOUNDS` przed utworzeniem
joba.

Pierwsze czyszczenie istniejących stagingów wymaga jawnego preview i akceptacji
Admina. Po włączeniu zatwierdzonej polityki automatycznej usuwalne są wyłącznie
stagingi z kompletnym handoffem; staging przypisany do innej gry jest ukryty
przed bieżącą grą i blokuje próbę startu. Po skopiowaniu oryginałów worker zachowuje obie tożsamości:
logiczny zakres do audytu oraz fizyczny plik do bezpiecznego kopiowania.
### Polityka silnika per gra

- Każda gra ma serwerowe, rewizjonowane ustawienie używane wyłącznie przy
  tworzeniu nowych importów.
- Dostępne są dwa bezpieczne presety: `verified_v19` oraz
  `structured_shadow`. Drugi zapisuje pomiar nowej geometrii, ale nie zmienia
  wyniku primary i nie aktywuje Geometry v2 produkcyjnie.
- Preflight zawiera nazwę i rewizję polityki. Zmiana ustawienia po preflighcie
  wymaga przygotowania nowego raportu.
- Raport jawnie zwraca `geometryPreflightRequired`. Dla `verified_v19` wartość
  pozostaje prawdziwa i start wymaga checksum-bound manifestu geometrii.
  `structured_shadow` ma bezpieczny cold-start bez historycznego profilu z
  zatwierdzonych plansz; nie uruchamia legacy preflightu i nie może przyjąć
  jego manifestu.
- Payload klienta nie może nadpisać polityki gry, a istniejące joby zachowują
  przypięte wcześniej snapshoty.
