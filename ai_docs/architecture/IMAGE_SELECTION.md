---
title: Fast representative image selection architecture
status: accepted
release: "0.4"
last_updated: 2026-08-05
---

# Architektura selekcji reprezentatywnych zdjęć

## Decyzja

Selekcja jest osobnym bounded contextem i czwartym workspace'em Admina. Używa
istniejącego Next.js, FastAPI, PostgreSQL, pojedynczego workera Python oraz
lokalnego storage. Nie jest flagą pełnego `image_directory` pipeline'u.

Rozdzielenie zapobiega czterem problemom:

1. szybki run nie zajmuje tabel i storage cropami odrzuconych duplikatów,
2. retry i anulowanie nie mieszają wyników selekcji z review layoutów,
3. jakość oraz czas selektora można mierzyć niezależnie od modelu symboli,
4. jeden zaakceptowany manifest może być wielokrotnie użyty jako kontrolowane
   wejście właściwego importu.

## Przepływ

```text
folder JPEG
  -> browser staging
  -> manifest + natural order
  -> reduced JPEG appearance scan
  -> sequential visual group detector
  -> first-usable representative OR best decodable fallback
  -> optional manual photo OR explicit skip as missing_image
  -> immutable selected manifest
  -> explicit handoff
  -> existing Import layoutów: OCR + geometry + sequence ranges + crops
```

## Granice komponentów

### Admin web

- renderuje czwarty workspace `Selekcja zdjęć`,
- korzysta ze wspólnego game context i parametrów URL,
- reużywa kontrolowany folder input do 100 000 JPEG-ów oraz postęp uploadu,
- przed synchronicznym przygotowaniem dużej listy plików oddaje przeglądarce
  dwie klatki renderowania, aby użytkownik zobaczył jawny loader,
- pokazuje postęp joba, agregaty i kolejkę manualną,
- nie wykonuje quality scoring ani OCR w przeglądarce,
- przekazuje do `Importu layoutów` wyłącznie zakończony run.

### Admin API

- poświadcza upload oraz jego przeznaczenie `photo_selection`,
- zapisuje stałe metadane uploadu w małym `_upload_state.json`, a każdy
  ukończony plik jako pojedynczy kanoniczny rekord append-only w
  `_upload_files.jsonl`; odtworzenie po restarcie odczytuje dziennik, natomiast
  historyczny stan schema v1 jest jednokrotnie migrowany bez utraty postępu,
- odpowiedź `PUT` pojedynczego pliku zawiera tylko sumaryczne liczniki plików i
  bajtów. Pełna lista indeksów jest zwracana wyłącznie przez jawny endpoint
  begin/get potrzebny do wznowienia,
- odrzuca dopiero `100 001` i więcej plików w jednym runie; niezależny limit
  bajtów i rezerwa wolnego miejsca pozostają bez zmian,
- tworzy run i job typu `image_selection`,
- udostępnia bounded listy grup i kandydatów,
- zapisuje idempotentne decyzje manualne `selected_image | missing_image`,
- publikuje handoff token dla rozwiązanych grup; `missing_image` nie ma pliku i
  może nie mieć zakresu, ale nie blokuje przekazania pozostałych reprezentantów,
- udostępnia checksumowaną listę outputu oraz pojedyncze JPEG-i do
  browser-native eksportu do folderu użytkownika,
- nigdy nie przyjmuje dowolnej ścieżki absolutnej ani komendy systemowej.

### Worker

- przetwarza pliki w deterministycznej kolejności i małym batchu,
- wykonuje decoder-side reduced JPEG, lekki deskryptor wyglądu i tanie metryki
  jakości przez bounded ordered prefetch; liczba workerów wynika z benchmarku,
  futures mogą kończyć się poza kolejnością, ale state machine konsumuje je po
  `order_index`,
- zapisuje checkpoint co plik lub bounded partię,
- utrzymuje tylko miniaturę bieżącego pliku, opis grupy, pierwszego użytecznego
  kandydata i najwyżej jeden fallback,
- nie wywołuje `PageBoardDetector`, OCR, homografii, `BoardCellCropper` ani
  symbol ONNX,
- kończy jako `waiting_for_review`, gdy istnieją grupy manualne, albo
  `completed`, gdy manifest jest kompletny,
- używa istniejącego `execution_slot = 1`, lease, heartbeat, cancel i retry.

### PostgreSQL

Encje:

- `image_selection_runs` — game, job, input manifest, selector fingerprint,
  ordering policy, output manifest i lifecycle projekcji,
- `image_selection_groups` — kolejność wystąpienia, opcjonalny zakres nadany
  dopiero przez późniejszy import, fingerprint wyglądu, stan i kandydat,
- `image_selection_candidates` — order index, ścieżka, checksum, wymiary,
  metryki jakości, confidence, reason codes i decyzja,
- `image_selection_manual_decisions` — append-only rewizje ręcznych decyzji,
  UUID idempotencji, resolution, opcjonalny wybrany kandydat, opcjonalny zakres
  historycznych runów i checksumę payloadu.

Duże obrazy pozostają w plikach. Dokładny schemat, constrainty i migracja
Alembic są opisane w `DATA_MODEL.md`.

### File storage

- wejście przebywa w job-owned browser staging poza kanonicznym `data/`,
- dla browser stagingu `sourceSelectionId` jest równy `uploadId`, więc worker
  może odtworzyć kontrolowany root bez utrwalania ścieżki absolutnej klienta,
- wybrane zdjęcia i manifest trafiają pod
  `data/exports/image-selections/<manifestSha256>/`; kanoniczny manifest zawiera
  `runId`, a JPEG-i znajdują się w podkatalogu `images/`,
- ręcznie wskazane pliki przed publikacją trafiają pod krótką, bezpieczną na
  Windows ścieżkę `data/working/is-manual/<runPrefix>/<groupPrefix>/<checksumPrefix>.jpg`;
  pełny UUID, checksum i proweniencja pozostają w PostgreSQL,
- bieżące ręczne wybory zapisuje kanoniczny, atomowo podmieniany
  `manual-decisions.json`; jest to manifest roboczy, a nie finalny output,
- pliki wynikowe są niezmienne i sprawdzane checksumą,
- nazwa kopii v9 ma postać `selection_<groupOrder>.jpg`; po
  publikacji przeglądarka może skopiować zweryfikowany zestaw do folderu
  wskazanego przez użytkownika, bez przekazywania backendowi dowolnej ścieżki,
- historyczne outputy v2–v8 zachowują nazwy `seq_<start>-<end>.jpg`; nie są
  przepisywane ani migrowane,
- unselected staging może zostać usunięty dopiero po atomowym commitcie wyniku
  albo po jawnym anulowaniu; źródłowy folder użytkownika jest read-only,
- output manifest jest kanonicznym JSON bez ścieżek absolutnych.

## Wersjonowany algorytm `fast-image-selector`

### Docelowy `fast-image-selector-v9`

V9 rozdziela szybką redukcję zdjęć od właściwego rozpoznawania danych. Selekcja
nie ustala `sequence_number` i nie używa OCR ani dokładnej geometrii. Jej
wynikiem jest naturalnie uporządkowana lista wizualnych grup oraz jeden JPEG na
grupę. `Import layoutów` później odpowiada za numery, plansze, homografię, cropy
i deduplikację zakresów.

Lekki skan per plik:

1. weryfikuje kontrolowane źródło i dekoduje JPEG bezpośrednio w zmniejszonej
   rozdzielczości przez wersjonowany adapter Pillow/libjpeg `draft()` przed
   `load()` i utworzeniem tablicy RGB; roboczy dłuższy bok pozostaje równy
   960 px, ponieważ warianty 384 i 480 nie przeszły realnego goldena granic,
2. stosuje EXIF transpose,
3. z centralnego obszaru plansz buduje deskryptor z ciągłej,
   znormalizowanej sygnatury DCT, histogramu HSV oraz uproszczonego edge
   signature. Wersjonowany wektor zawiera 144 współczynniki DCT 12×12,
   20 koszyków H/S/V oraz 13 wartości siatki i orientacji krawędzi. DCT jest
   porównywane wycentrowaną odległością cosinusową; jego wagi, crop i progi
   należą do manifestu,
4. mierzy ostrość, ekspozycję, clipping i podstawową widoczność,
5. nie uruchamia `PageBoardDetector`, OCR, homografii ani croppera.

State machine porównuje obserwację z bezpośrednim poprzednikiem oraz bounded
opisem bieżącej grupy. Granica wymaga dwóch kolejnych zgodnych obserwacji
zmiany. Pojedynczy refleks, zasłonięcie albo klatka przejściowa nie tworzy nowej
grupy. Algorytm nie zna oczekiwanego następnego zakresu ani minimalnej długości
serii.

Opis grupy jest rolling centroidem o stałym wymiarze, aktualizowanym online bez
przechowywania wcześniejszych obrazów lub wszystkich deskryptorów. Kandydat
granicy musi przekroczyć wersjonowany próg zarówno względem bezpośredniego
poprzednika, jak i centroidu. Odrzucona pojedyncza klatka przejściowa nie może
przesunąć centroidu przed oceną powrotu do bieżącego ekranu.

Dla grupy utrzymywane są tylko:

- rolling appearance descriptor,
- pierwsza obserwacja spełniająca miękki próg czytelności,
- najwyżej jeden najlepszy dekodowalny fallback,
- bounded pending guard granicy.

Wersjonowana polityka reprezentanta v9 wymaga `overall_score >= 0.30`,
`sharpness >= 0.10`, `exposure >= 0.20`, `highlight_retention >= 0.50` oraz
`board_visibility >= 0.25`. Progi są miękkie: ich niespełnienie nie usuwa
grupy. Stan otwartej grupy zachowuje najwyżej dwa rekordy kandydatów: pierwsze
użyteczne źródło i jeden najlepszy fallback. Przed znalezieniem pierwszego
użytecznego źródła zachowywany jest wyłącznie jeden najlepszy fallback.

Po zamknięciu grupy wybierany jest pierwszy użyteczny obraz bez dodatkowej
pełnej weryfikacji. Jeżeli próg nie został spełniony, publikowany jest najlepszy
dekodowalny fallback z `QUALITY_BEST_AVAILABLE`. Niepewnego podobieństwa dwóch
niekolejnych grup nie używa się do usunięcia obrazu; pewną deduplikację wykona
Import po odczytaniu zakresu.

`groupOrder` jest identyfikatorem kolejności źródeł i nie może być traktowany
jako numer layoutu. V9 publikuje `selection_<groupOrder>.jpg` oraz manifest bez
wymaganego zakresu. Historyczne runy pozostają odtwarzalne po swoich
fingerprintach.

Bieżący przedaktywacyjny manifest v9 ma fingerprint
`eaca91fd6f6c169f25436a81b1059810152899953d3eecdef980391df7124afb`, a
adapter lekkiego skanu fingerprint
`408bd8574526e07d055958734ce6136288beff5a54cf1dcd9f76f6291edea396`.
Verifier pełnego kandydata nie jest wywoływany; kandydat bez błędu dekodowania
lub integralności staje się `auto_selected`, a fallback otrzymuje jawne
`QUALITY_BEST_AVAILABLE`. Grupa zawierająca wyłącznie niedekodowalne pliki
pozostaje `manual_required`.

### Historyczny pipeline v2–v8

#### Tani skan per plik

1. Weryfikacja JPEG i SHA-256.
2. EXIF transpose oraz miniatura z ograniczonym dłuższym bokiem.
3. Downscaled page/board lattice detection.
4. Metryki jakości: sharpness, exposure, highlight clipping, glare proxy,
   perspective, border margin, board visibility.
5. Niezależny od zmiennej liczby wykrytych czerwonych ramek fingerprint HSV
   obszaru ekranu.
6. Decyzja, czy potrzebny jest sparse OCR kotwic zakresu.

#### Granice grup

State machine nie przewiduje następnego numeru. Nową grupę otwiera dopiero
łączny dowód:

- spadek podobieństwa fingerprintu,
- zmiana geometrii/lattice,
- zgodny, wystarczająco pewny nowy zakres OCR,
- albo bounded guard sample potwierdzający zmianę.

Pojedynczy słaby sygnał nie zamyka grupy. Po utrwaleniu reprezentanta późniejszy
powrót tego samego zakresu otrzymuje `skipped_existing_range`. Zakres jeszcze
nierozwiązany może przyjąć lepszego kandydata z późniejszego wystąpienia.

#### Identyfikacja zakresu

- OCR działa na numerach pierwszej, ostatniej i opcjonalnie środkowej wykrytej
  planszy, batchowo dla kandydata.
- `fast-image-selector-v2` ma fail-closed fallback pełnej rozdzielczości:
  wykrywa jasne etykiety numerów bez zależności od czerwonych ramek i uznaje
  zakres dziewięciu plansz dopiero przy co najmniej sześciu zgodnych punktach
  siatki, obecnym pierwszym i ostatnim numerze, trzech wierszach, trzech
  kolumnach oraz jednoznacznej homografii RANSAC.
- `fast-image-selector-v5` używa osobnej, digit-aware wersji fallbacku. Szerszy
  bounded region obejmuje dolny rząd etykiet, a limity komponentów dopuszczają
  numery do co najmniej sześciu cyfr. Przed OCR pozostaje najwyżej 36
  kandydatów. Pełny verifier może dodatkowo odzyskać brakującą pozycję siatki;
  tani skan i historyczne runy v2–v4 zachowują dotychczasowe zachowanie.
- Zakres jest poprawny tylko dla dodatnich wartości w rosnącej kolejności,
  zgodnych z liczbą wykrytych pozycji.
- Finalna strona może zawierać 1–9 plansz.
- Brak zgodnego zakresu zachowuje grupę jako `unknown`; nie tworzy numerów.

#### Ranking i bramki bezpieczeństwa

- Dla grupy przechowywane są metadane najwyżej `topK`, domyślnie 3. V8 zachowuje
  najwcześniejszą obserwację spełniającą wersjonowany próg `firstUsablePolicy`
  oraz najlepsze jakościowo kandydaty zapasowe.
- Pełniejsza walidacja selektora działa tylko na top-k. V8 sprawdza ten bounded
  zbiór w kolejności źródłowej i kończy po pierwszym jednoznacznym zakresie.
- Błędy dekodowania/skanu oraz konflikt zakresu są twardymi bramkami. Ostrość,
  zasłonięcie, kompletność plansz i pozostałe progi jakości obrazu są miękkimi
  sygnałami rankingu, jeżeli adapter potwierdził jeden zakres numerów albo
  zakres wynika dokładnie z bounded luki.
- Gdy żaden kandydat nie przechodzi wszystkich miękkich progów, v4 wybiera
  najlepszy dostępny dostatecznie ostry obraz, zachowuje ostrzeżenia jakości i
  dodaje `QUALITY_BEST_AVAILABLE`.
- Po zamknięciu grup v4 wykonuje przebieg O(g). Tylko jedna nierozpoznana grupa
  pomiędzy dwoma wybranymi zakresami może otrzymać dodatnią lukę o rozmiarze
  1–9 oraz `RANGE_INFERRED_FROM_BOUNDED_GAP`. Dwie grupy w luce, większy skok
  albo brak kotwicy pozostają manualne.
- V6 rozszerza ten sam bezpieczny mechanizm na blok kilku kolejnych grup.
  Przypisanie jest all-or-nothing i zachodzi wyłącznie, gdy luka pomiędzy
  kotwicami ma dokładnie `liczba grup × 9` elementów oraz każda grupa ma
  dekodowalny kandydat best-available. Po zapisaniu prawej kotwicy odzyskane
  projekcje są emitowane ponownie przed kolejnym checkpointem, więc licznik
  manualny maleje również podczas skanowania.
- Odzyskana grupa zachowuje ostrzeżenia jakości i geometrii w audycie, ale
  otrzymuje najlepszego dekodowalnego kandydata jako `selected_automatic`.
  Dzięki temu publisher i późniejszy Import layoutów podejmują próbę cięcia;
  selektor nie udaje, że geometria zdjęcia była poprawna.
- Błędne scalenie zakresów jest krytyczniejsze niż dodatkowy manual review;
  bounded inference nie przewiduje ogólnej ciągłości numeracji.

Wagi, progi, rozmiar miniatury i guard interval są częścią wersjonowanego
manifestu selektora. Nie mogą być ukrytymi stałymi rozproszonymi po UI i CLI.

Historyczna implementacja `fast-image-selector-v8` utrzymuje manifest w jednym
module i wylicza z jego kanonicznego JSON fingerprint używany przez API
`9dc754cca7e7e7afe23e8a25c8574e0ef4ed5f7fd5829a24984c25f4c256f42d`
przy tworzeniu kolejnych runów. V8 zachowuje adapter, reguły granic i
bounded-gap inference v7, ale zmienia strategię reprezentanta na `first usable`:
po pierwszej pełnej weryfikacji dającej jednoznaczny zakres nie uruchamia OCR dla
pozostałych zdjęć grupy. Typowy koszt pełnej weryfikacji wynosi `grupy × 1`, a
pesymistyczny nadal nie przekracza `grupy × topK`.

Polityka `firstUsablePolicy` jest częścią kanonicznego manifestu v8: tani skan
zachowuje pierwszą obserwację z `overall_score >= 0.30`, `sharpness >= 0.10` i
bez błędu skanu, a pozostałe miejsca top-k przeznacza na najlepsze fallbacki.
Historyczny v7 zachowuje fingerprint
`21d634e0657c2e53564157901d3873747d0c642bf7d30141449c990646fd0d55`
oraz wcześniejsze zachowanie przy wznowieniu trwałego runu.

Adapter `visible-sequence-label-range-v3` wykrywa również przyciemnione i ciepło
zabarwione etykiety. Nadal wymaga zgodnej przestrzennie siatki, obu skrajnych
numerów, reprezentacji wszystkich trzech rzędów i kolumn oraz homografii RANSAC.
Po potwierdzeniu zakresu v7 nie odrzuca reprezentanta z powodu częściowego
zasłonięcia, rozmycia albo słabych plansz. Wybiera najwyżej sklasyfikowany
dekodowalny plik i pozostawia ostrzeżenia w audycie, aby widoczne layouty mogły
przejść do cięcia, a brakujące komórki zostały uzupełnione ręcznie.

V5 porównuje kandydat granicy z bezpośrednio poprzednią obserwacją. Zmiana musi
zostać potwierdzona przez drugą kolejną obserwację, a podczas stopniowego
przejścia pending guard jest utrzymywany, jeżeli nowe klatki pozostają różne od
większości bieżącej grupy. `topK` służy do rankingu reprezentanta, nie jako veto
dla rzeczywistej zmiany strony.

V3 porównuje nową obserwację z bounded zbiorem najlepszych reprezentantów oraz
ostatnią obserwacją grupy. Dzięki temu stopniowa zmiana perspektywy pozostaje w
jednej grupie, ale nagła, potwierdzona zmiana strony nadal otwiera następną.
Sygnatura geometrii jest dowodem wyłącznie wtedy, gdy istnieje po obu stronach i
ma zgodny wymiar; pusty lattice oznacza brak dowodu, a nie maksymalną odległość.

Niezmienny `fast-image-selector-v2` o fingerprintcie
`6da6fb8a247b41827a87437e6936cc4c449e06a0bbd24acd8b3159d576c1ce8e`
oraz v3 o fingerprintcie
`5c9dd9762e243e8c44210e300ba214f4186bc5724fc60d34f50afccf5ea51636`
oraz v4 o fingerprintcie
`2e327902cb38cade250df019b4589ea0364512358d1cb3cb20e5525c390c8e37`
oraz v5 o fingerprintcie
`ff75216bcd71f7f2484fef2c2868eda639152ba7efd98e00f23e08a89585e3fb`
oraz v6 o fingerprintcie
`22b0d13545c087b53e197dd20edaf214fbebd99b51036cd84dc624c76577bf1e`
oraz v7 o fingerprintcie
`21d634e0657c2e53564157901d3873747d0c642bf7d30141449c990646fd0d55`
pozostają w rejestrze kompatybilności. Worker rozwiązuje manifest po fingerprintcie
trwałego runu, dlatego rozpoczęty run v2/v3/v4/v5/v6/v7 może zostać wznowiony po
restarcie bez zmiany algorytmu. Do aktywacji v9 rejestr zachowuje również v8.
Jawne porty historycznego pipeline'u oddzielają
loader miniatury, metryki jakości, lattice/fingerprint oraz OCR zakresu.
Samodzielny diagnostyczny przebieg CLI bez lokalnego modelu OCR używa innej
wersji adaptera i fingerprintu, dlatego nie może zostać pomylony z produkcyjnym
auto-wyborem.

Skan zapisuje metryki kandydata strumieniowo, zachowuje w pamięci tylko bieżącą
grupę, jej ostatnią obserwację, bounded pending guard i `topK = 3`, a checkpoint
postępu powstaje co 32 pliki. Pojedynczy silny kandydat granicy nie tworzy
oddzielnej grupy.
Niepotwierdzona zmiana jest traktowana jako klatka przejściowa i dołączana do
dotychczasowej grupy, a guard rozpoczyna potwierdzanie ponownie od następnego
kandydata. Priorytetem pozostaje brak fałszywego scalenia.

## Kontrakty i idempotencja

- `selectorFingerprint` jest SHA-256 kanonicznego manifestu adapterów, progów i
  wersji algorytmu.
- `inputManifestSha256` obejmuje uporządkowane względne ścieżki, rozmiary i
  checksumy wszystkich wejść.
- `input_key` joba zależy od gry, obu fingerprintów i wersji kontraktu.
- Retry tego samego wejścia wznawia ten sam run i checkpoint.
- Zmiana pliku, kolejności albo wersji selektora tworzy nowy run. Jedno
  niezmienne `sourceSelectionId` może mieć wiele runów o różnych fingerprintach
  selektora; idempotencja pozostaje na trójce gra + manifest wejścia +
  fingerprint selektora.
- Endpoint rerunu przyjmuje identyfikator historycznego runu, wyprowadza z niego
  `sourceSelectionId` i checksum manifestu, a następnie sprawdza kontrolowany
  katalog `browser-selections/<sourceSelectionId>` przed użyciem aktualnego
  fingerprintu. Nie przyjmuje od UI ścieżki ani checksumy i nie kopiuje obrazów.
- Gdy idempotentna tożsamość wskazuje run `cancelled` albo `failed`, endpoint
  blokuje jego job, wykonuje przejście do `created`, czyści terminalny błąd,
  `finishedAt` i żądanie anulowania, ale zachowuje postęp oraz checkpoint.
  Run aktywny lub ukończony nie jest ponownie kolejkowany.
- Ręczna decyzja używa UUID idempotencji i append-only eventu albo równoważnej
  wersjonowanej historii; retry nie tworzy drugiej kopii pliku. Korekta przed
  publikacją dodaje rewizję i aktualizuje projekcję oraz manifest roboczy.
- Po publikacji content-addressed output jest niezmienny. Dalsza korekta wymaga
  nowego runu i nie mutuje artefaktu, który mógł już zostać przekazany do importu.
- `missing_image` jest terminalnym, trwałym stanem grupy. Publisher pomija
  kopiowanie JPEG-a dla takiej grupy. V9 nie ustala zakresu, dlatego UI pokazuje
  techniczny `groupOrder`, liczbę źródeł i ich nazwy, bez przedstawiania tego
  numeru jako numeru layoutu. Historyczny zakres v2–v8 może pozostać widoczny.
- Publisher zapisuje JPEG-i i kanoniczny `manifest.json` do izolowanego
  `.pending`, wykonuje ponowny odczyt checksum i wymiarów, a następnie publikuje
  cały katalog jednym rename w tym samym filesystemie. Awaria przed rename nie
  tworzy widocznego częściowego outputu.
- Handoff weryfikuje checksumę manifestu, wszystkie wybrane pliki, proweniencję
  runu oraz zgodność trwałych decyzji grup przed wydaniem krótkotrwałego tokenu.
  Zakres jest opcjonalny i dla v9 zostanie ustalony przez właściwy import.
- Identyfikator logicznego źródła handoffu jest równy `runId`; ponowienie nie
  tworzy innego źródła, nawet jeżeli po skonsumowaniu poprzedniego tokenu trzeba
  wydać nowy token sesyjny.

## Trwałe wykonanie i diagnostyka

- Produkcyjny handler `image_selection` działa w istniejącym lokalnym workerze
  z pojedynczym `execution_slot = 1`; każda projekcja grupy i finalnego outputu
  jest chroniona tym samym tokenem fencing co lease joba.
- Checkpoint JSON przechowuje tylko potwierdzony `nextOrderIndex`, bounded stan
  otwartej grupy, pending guard, top-k i liczniki. Pełne grupy oraz kandydaci
  pozostają w PostgreSQL.
- Projekcja grup jest zapisywana przed checkpointem. Jeżeli proces zakończy się
  pomiędzy tymi operacjami, retry uzgadnia projekcję do
  `finalizedGroupCount` ostatniego checkpointu i deterministycznie powtarza
  najwyżej niepotwierdzoną partię. Nigdy nie powtarza potwierdzonych plików.
- Checkpoint skanu powstaje najwyżej co 32 pliki, a podczas publikacji co 16
  kopii oraz na końcu. Żądanie cancel jest dzięki temu obsługiwane w bounded
  safe poincie; staging źródłowy nie jest usuwany.
- Błąd odczytu pojedynczego JPEG-a staje się obserwacją z reason code i zerową
  jakością. Zwiększa licznik błędów, ale nie kończy całego runu.
- `waiting_for_review` zwalnia lease i ciężki slot. Po manualnym uzupełnieniu
  ten sam job wraca do checkpointu; ogólny licznik review pozostaje monotoniczny,
  a `progress.imageSelection.manual` pokazuje bieżącą liczbę nierozwiązanych grup.
- API serializuje równoległe decyzje manualne blokadą rekordu joba `FOR UPDATE`.
  Transakcja ostatniej decyzji sprawdza brak grup `collecting` i
  `manual_required`, po czym idempotentnie wykonuje przejście
  `waiting_for_review -> created`. Joby `failed` nie są wznawiane automatycznie.
- Prefetch nie jest zapisywany w checkpointcie. Cancel albo crash może
  spowodować ponowne policzenie najwyżej ośmiu rozpoczętych, lecz jeszcze
  nieskonsumowanych tanich obserwacji; nie może pominąć źródła ani zmienić
  zatwierdzonego `nextOrderIndex`.
- Odtwarzalny cache lekkich obserwacji znajduje się wyłącznie pod
  `data/cache/image-selection-scan/`. Klucz logiczny to
  `sourceChecksumSha256 + scanAdapterFingerprint`, a krótka struktura katalogów
  używa ich wspólnego SHA-256, aby nie przekraczać limitów ścieżek Windows.
  Kanoniczny JSON nie zawiera obrazu ani ścieżki źródła. Przy cache hit
  obserwacja zostaje związana z bieżącym rekordem źródła, a selektor nadal
  konsumuje ją według `order_index`.
- `scanAdapterFingerprint` obejmuje wersję i parametry reduced decode,
  deskryptora/geometry adaptera oraz metryk jakości. Nie obejmuje progów granic,
  top-k, rozmiaru batcha ani polityki reprezentanta, dlatego zgodna zmiana
  domenowego grupowania może przeliczyć decyzje bez ponownego dekodowania.
- Zapis cache używa unikalnego pliku `.part`, `fsync` i atomowego replace.
  Uszkodzony lub częściowy wpis daje miss; błąd zapisu cache nie przerywa joba.
  Checkpoint i projekcja PostgreSQL pozostają jedynym źródłem prawdy postępu.
- Cleanup jest operacją operatorską, nigdy automatycznym skutkiem retry.
  Bezpiecznie można usunąć wyłącznie cały katalog
  `data/cache/image-selection-scan/` przy zatrzymanym workerze; nie wolno łączyć
  tej operacji z kasowaniem `browser-selections`, manualnych źródeł ani finalnego
  outputu. Cache odbuduje się liniowo, po jednym bounded JSON-ie na unikalną parę
  checksumy i adaptera.
- Bounded diagnostyka nie zawiera obrazów ani ścieżek absolutnych. Kanoniczny
  JSON jest adresowany checksumą pod
  `data/exports/is-job-diagnostics/<sha256>.json`; API ujawnia tylko checksumę.
- Czas browser uploadu jest zapisany przy finalizacji stagingu. Czas obliczeń
  jest sumowany wyłącznie dla aktywnych prób workera, bez czasu oczekiwania na
  ręczne review.

## Plan API

Istniejący upload folderu zostanie uogólniony wewnętrznie, zachowując zgodność
endpointów importu. Nowe kontrakty:

```text
POST /api/v1/admin/image-selections
GET  /api/v1/admin/image-selections/{runId}
GET  /api/v1/admin/image-selections/{runId}/groups
GET  /api/v1/admin/image-selections/{runId}/groups/{groupId}/candidates
GET  /api/v1/admin/image-selections/{runId}/output
GET  /api/v1/admin/image-selections/{runId}/output/{fileName}
PUT  /api/v1/admin/image-selections/{runId}/groups/{groupId}/manual-file
GET  /api/v1/admin/image-selections/{runId}/groups/{groupId}/manual-files/{candidateId}
POST /api/v1/admin/image-selections/{runId}/groups/{groupId}/approve
POST /api/v1/admin/image-selections/{runId}/groups/{groupId}/continue-without-image
POST /api/v1/admin/image-selections/{runId}/handoff
```

Upload ręcznego JPEG-a używa nagłówka `X-Image-File-Name`. Nagłówek jest częścią
jawnej listy CORS lokalnego Admin API, dzięki czemu przeglądarkowy preflight
`PUT` dociera do endpointu zamiast kończyć się przed zapisem pliku.

Dokładne request/response i stabilne błędy TASK-0151–0155 są w OpenAPI.
Frontend korzysta wyłącznie z generowanego klienta.
Endpoint kandydatów jest ograniczony do 100 rekordów, domyślnie 20, zwraca
oryginalne nazwy względne oraz `sourceCount` grupy. Modal pobiera go wyłącznie
dla bieżącego zestawu, więc identyfikacja źródeł nie ładuje całej kolejki do
pamięci. V9 nie proponuje zakresu ani luki; operacja zbiorcza zapisuje
`missing_image` bez zakresu. Historyczne endpointy v2–v8 pozostają zgodne
wstecznie.

## Stany

Job używa wspólnego lifecycle:

```text
created -> processing -> waiting_for_review -> completed
                         \-> failed/cancelled
```

Etapy selektora:

```text
staging -> scanning -> grouping -> verifying -> manual_review
        -> writing_manifest -> ready_for_import
```

Grupa używa:

```text
collecting | auto_selected | manual_required | manually_selected
| missing_image | skipped_existing_range
```

## Wydajność

- V9 wykonuje O(n) reduced decode, lekkich deskryptorów i metryk jakości.
- Produkcyjna ścieżka selekcji wykonuje zero OCR, zero `PageBoardDetector`, zero
  homografii i zero cropów niezależnie od `n` oraz liczby grup.
- Bounded zewnętrzny pool skanu działa z jednym wewnętrznym wątkiem OpenCV;
  faktyczna liczba workerów jest wybierana po benchmarku 1/2/4, aby uniknąć
  nadsubskrypcji CPU. Pomiar i aktywacja liczby workerów należą do wspólnej
  bramki TASK-0171; wcześniejsze zadania nie uruchamiają konkurencyjnego profilu
  podczas aktywnego historycznego joba.
- V9 nie wykonuje top-k full verification. Dla grupy zachowuje pierwszego
  użytecznego kandydata i jeden fallback.
- Wersjonowany cache po checksumie i fingerprintcie lekkiego adaptera może
  usunąć dekodowanie przy zgodnym rerunie, ale nie wpływa na wynik domenowy.
  Checkpoint i diagnostyka raportują `hitCount`, `missCount`,
  `invalidEntryCount`, `writeErrorCount`, `writtenBytes` oraz
  `estimatedSavedSeconds`.
- Rekordy kandydatów zapisują się bounded partiami; obrazy nie trafiają do RAM
  ani PostgreSQL jako kolekcja.
- Benchmark mierzy upload osobno od obliczeń, aby wolny dysk lub kopiowanie nie
  ukrywały kosztu selektora.
- Przed pełnym profilem obowiązuje realny profil 500–1000 oraz 3000 zdjęć.
  Bramka końcowa mierzy pełny przebieg 40 000 zdjęć, bounded peak RSS, zero false
  merge oraz zerowe liczniki kosztownych adapterów należących do Importu
  layoutów. Czas i throughput są raportowane bez sztywnego limitu; właściciel
  podejmuje końcową decyzję akceptacyjną.

## Odrzucone warianty

### Usuwanie lub przenoszenie źródeł

Odrzucone z powodu ryzyka utraty danych, błędnej klasyfikacji i braku
odtwarzalności. Kopia wynikowa jest tania wobec kosztu ponownego zebrania zdjęć.

### Dodatkowy checkbox w `Imporcie layoutów`

Odrzucony, ponieważ miesza dwa różne lifecycle, metryki, retry i znaczenie
wyniku. Użytkownik nie widziałby, czy obserwuje szybki wybór, czy pełny pipeline.

### Pełny obecny pipeline dla każdego zdjęcia

Odrzucony ze względu na koszt 10–30 tys. źródeł i tworzenie niepotrzebnych
cropów oraz review dla duplikatów.

### Model chmurowy lub nowy mikroserwis

Odrzucony. Obecny lokalny stos ma potrzebne biblioteki, a problem wymaga najpierw
benchmarku algorytmu i I/O, nie nowej infrastruktury.
