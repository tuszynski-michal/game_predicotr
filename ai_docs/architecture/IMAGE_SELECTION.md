---
title: Fast representative image selection architecture
status: accepted
release: "0.4"
last_updated: 2026-08-05
---

# Architektura selekcji reprezentatywnych zdjęć

## Decyzja

Selekcja jest osobnym bounded contextem i czwartym workspace'em Admina. Używa
istniejącego Next.js, FastAPI, PostgreSQL, wspólnego kodu workera Python oraz
lokalnego storage. Produkcyjnie ma osobny proces i execution lane, ale nie jest
osobnym mikroserwisem ani flagą pełnego `image_directory` pipeline'u.

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
- używa dedykowanego `execution_slot = 2` oraz wspólnych mechanizmów lease,
  heartbeat, cancel i retry; general worker używa slotu 1 i nie rejestruje
  handlera `image_selection`.

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

Od 2026-08-05 aktywnym manifestem nowych runów jest
`fast-image-selector-v9` o fingerprintcie
`eaca91fd6f6c169f25436a81b1059810152899953d3eecdef980391df7124afb`.
API i worker korzystają z jednego `DEFAULT_SELECTOR_MANIFEST`. Zmiana nie
przepisuje istniejących runów: ich zapisany fingerprint nadal rozwiązuje
niezmienny manifest v2–v8. Aktywacja poprzedza pełny pomiar 40 000 zdjęć na
jawne polecenie właściciela; decyzja odbiorowa TASK-0171 nadal pozostaje
`accepted | optimize` po zakończeniu runu.

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
- Opcjonalne `firstSequenceNumber` i `lastSequenceNumber` nadpisują historyczne
  granice rerunu. Jawny koniec jest częścią tożsamości runu i payloadu joba;
  umożliwia bezpieczne objęcie v10.13 pełną licznością stagingu utworzonego przed
  migracją 0043.
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

- Produkcyjny handler `image_selection` działa w dedykowanym lokalnym procesie
  tego samego pakietu workera z `execution_slot = 2`. Import i pozostałe joby
  używają procesu general oraz `execution_slot = 1`. Atomowy claim filtruje typy
  jobów przed pobraniem, a unikalność slotu pozwala na jeden aktywny job w każdym
  lane. Każda projekcja grupy i finalnego outputu nadal jest chroniona tym samym
  tokenem fencing co lease joba.
- Każdy proces rejestruje osobny `instance_token` w
  `worker_lane_runtime` i odnawia heartbeat w małym wątku diagnostycznym również
  wtedy, gdy kolejka jest pusta albo handler długo pracuje. Rejestracja nowej
  instancji atomowo odcina heartbeat starego tokenu. API wylicza `running` dla
  sygnału nie starszego niż 15 sekund, `degraded` do 60 sekund, a następnie
  `stopped`; jawne zakończenie od razu daje `stopped`.
- Niezależnie od diagnostycznego heartbeat lane, każdy claimed job ma osobny
  keepalive lease uruchomiony przez wspólny runtime workera. Odnawia on fenced
  lease co najwyżej co 15 sekund również wtedy, gdy pojedynczy batch dekodowania,
  OCR albo treningu trwa dłużej niż checkpoint. Błąd keepalive jest traktowany
  jak utrata lease; handler nie może wtedy wykonać terminalnego zapisu.
- Supervisor ustawia per proces budżet wątków dla OpenMP, OpenBLAS, MKL,
  NumExpr i Accelerate oraz limit współbieżności CLI. General domyślnie używa
  budżetu 2. Selekcja ma cztery zewnętrzne `scan_workers`, ale biblioteki
  natywne wewnątrz każdego skanu pozostają jednowątkowe, aby nie tworzyć
  zagnieżdżonej nadsubskrypcji. Jest to przenośny limit współbieżności, nie
  twardy limit procentu CPU systemu operacyjnego.
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
POST /api/v1/admin/image-selections/{runId}/groups/{groupId}/discard-duplicate
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

`POST .../discard-duplicate` przyjmuje UUID idempotencji oraz kompletny zakres.
Serwis, pod blokadą joba, potwierdza istnienie innej rozwiązanej grupy z
identycznym zakresem. Następnie zapisuje append-only decyzję `duplicate_range`
i projektuje grupę do istniejącego statusu `skipped_existing_range`. Operacja
nie wskazuje kandydata i nie dotyka pliku wynikowego należącego do pierwszej
grupy. Brak właściciela zakresu zwraca stabilny konflikt
`IMAGE_SELECTION_DUPLICATE_RANGE_NOT_FOUND`.

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

## Architektura selektora v10

V10 zachowuje strumieniowe grupowanie i cache deskryptorów v9, ale usuwa jego
politykę `first usable`. `_OpenGroup` ocenia cały zakres źródeł i utrzymuje
deterministyczne top-12 według metryk obszaru ekranu. Dopiero po zamknięciu
grupy wykonywane są pełna geometria oraz OCR numerów dla shortlisty. Wynik OCR
jest agregowany pomiędzy klatkami, a ranking końcowy uwzględnia zgodność z
konsensusem, kompletność kadru, margines, ostrość i wynik jakości.

Run przechowuje `sequence_direction` i opcjonalny `first_sequence_number`.
Kotwica porządku jest częścią tożsamości runu. Dla kolejnych grup selektor
wyznacza zakres bez luk, natomiast rozpoznanie starego, już ukończonego zakresu
oznacza duplikat i nie przesuwa kursora. Kierunek malejący nie zmienia kolejności
plików i nadal zapisuje kanoniczny zakres niższy–wyższy.

Progresywny zapis ma dwie granice:

1. worker zapisuje decyzję grupy trwale w PostgreSQL,
2. Admin pobiera wybrany JPEG przez bounded endpoint grupy i natychmiast zapisuje
   go przez File System Access API do wskazanego przed startem katalogu.

Panel prowadzi ledger zapisanych `group_order` w bieżącej sesji. Replay jest
idempotentny: identyczny plik zostaje pominięty, a kolizja innej zawartości
zatrzymuje zapis bez nadpisania. Końcowy publisher nadal tworzy checksumowany
manifest do handoffu, lecz na tym samym woluminie używa hardlinku, a kopiuje
plik tylko gdy hardlink jest niedostępny.

Nowy endpoint progresywny:

```text
GET /api/v1/admin/image-selections/{runId}/groups/{groupId}/selected-file
```

Pełny OCR plansz, cięcie komórek i rozpoznawanie symboli pozostają poza tym
modułem.

## Architektura selektora v10.1

V10.1 zachowuje grupowanie, pełny lekki scoring i top-12 v10, ale rozdziela dwa
wyniki pełnej weryfikacji:

1. `representative assessment` ocenia geometrię, kompletność kadru i metryki
   obrazu służące wyłącznie do wyboru JPEG-a,
2. `range evidence` odczytuje numery z jednej lub kilku klatek i ustala zakres
   grupy niezależnie od wybranego reprezentanta.

Stabilna detekcja 1–9 plansz na pełnej rozdzielczości dostarcza rzeczywisty
`board_count` także wtedy, gdy tani appearance scan celowo go nie oblicza.
Verifier najpierw próbuje jednego batcha OCR kotwic: pierwszej, środkowej i
ostatniej etykiety. Dopiero niepowodzenie kotwic uruchamia fallback etykiet.
Próg tej ścieżki jest częścią fingerprintu manifestu w
`fullGeometryPolicy`: liczba plansz `1–9` i minimalna confidence `0.64`.
Telemetria rozróżnia próby, sukcesy i błędy ścieżek `anchoredOcr*` oraz
`fallbackOcr*`; liczniki nie uczestniczą w decyzji domenowej.

Kandydaci zakresu są pobierani deterministycznie według rankingu jakości.
Domyślne poziomy dowodu to `2 -> 4 -> 8 -> 12`. Zgodne, wysokiej pewności
odczyty dwóch niezależnych klatek kończą wyłącznie zbieranie dowodów numeru;
nie kończą skanowania grupy i nie zmieniają rankingu reprezentanta. Konflikt,
niska pewność albo brak odczytu rozszerza poziom. Fallback jednej klatki
przetwarza kandydatów etykiet partiami `18 -> 36 -> 72` i zatrzymuje się tylko
po spełnieniu istniejącej pełnej bramki przestrzennej.
Poziomy należą do fingerprintowanej `progressiveVisibleLabelFallbackPolicy`.
Każdy kolejny poziom wykonuje OCR tylko dla nowych cropów, zachowując wyniki
wcześniejszych partii. Maksymalny poziom używa tego samego deterministycznego
zbioru 72 etykiet co historyczny adapter v4. Telemetria rozdziela próby i
rozstrzygnięcia poziomów oraz raportuje całkowitą liczbę cropów fallbacku.
Adapter `visible-sequence-label-range-v6` rozszerza wyłącznie lokalną bramkę
przestrzenną fallbacku. Dopuszcza brak jednej lub dwóch etykiet, jeżeli RANSAC
potwierdza co najmniej siedem punktów, widoczny jest początek albo koniec
zakresu, a inliery obejmują wszystkie trzy wiersze i kolumny siatki. Hipotezy o
równym wyniku pozostają niejednoznaczne. Adapter nie zna poprzedniego zakresu i
nie używa cursora ciągłości.
Po potwierdzeniu zakresu pozostałe elementy top-12 przechodzą nadal pełną ocenę
reprezentanta, ale bez OCR. Poziomy i wymagane dwa zgodne odczyty są częścią
`adaptiveRangeConsensusPolicy` w fingerprintcie manifestu. Telemetria zapisuje
liczbę klatek dowodowych oraz powód `confirmed`, `conflict_exhausted` albo
`no_consensus_exhausted` jako osobne liczniki.

Wyniki zadań równoległych są zbierane w pierwotnej kolejności shortlisty.
Opcjonalna równoległość pełnej weryfikacji może używać wyłącznie osobnych
instancji lokalnego predictora i musi przejść test identyczności wyniku 1 vs 2
workery. Nie wolno współdzielić jednego mutowalnego predictora Paddle pomiędzy
wątkami.
Implementacja potrafi dzielić każdy poziom adaptacyjny na najwyżej dwie
szeregowe partycje. Każda partycja ma własny predictor, recognizery i detector,
a wynik jest składany według indeksu wejściowego. Pomiar TASK-0194 wykazał na
komputerze właściciela konkurencję Paddle/OpenCV: dwa verifiery były wolniejsze
od jednego. Produkcyjny budżet lane równy cztery używa dlatego trzech scan
workers i jednego verification workera. Adapter dwóch izolowanych verifierów
pozostaje nieaktywną opcją do ponownej bramki na innym sprzęcie. Telemetria
`parallelVerification*` nie uczestniczy w decyzji domenowej.

Powtarzalna bramka `scripts/run_image_selection_verifier_gate.py` uruchamia oba
warianty sekwencyjnie na tym samym wycinku i tym samym aktywnym manifeście.
Porównanie obejmuje pełną kanoniczną decyzję grupy, nie tylko czas. Dwa
verifiery mogą zostać zalecone dopiero przy identycznym wyniku i poprawie czasu
o co najmniej 10%. Sam skrypt nie zmienia konfiguracji produkcyjnej.

Zakres jest wynikiem dowodu OCR albo jawnej kotwicy pierwszej grupy. Cursor nie
może nadpisywać poprawnego odczytu kolejnej grupy ani wypełniać skoku bez
dowodu. `seq_<start>-<end>.jpg` używa zakresu grupy, choć sam wybrany JPEG może
pochodzić z innej klatki niż dowód OCR.

Aktywny manifest zachowuje wersję algorytmu `fast-image-selector-v10.1`, lecz
ma nowy fingerprint
`286b652ea8f19e3afb73017b54f096c0eb5dff828f0020f0b7454e9e42b76f40` i range
adapter v6. Fingerprint poprzedniego progresywnego adaptera v5 pozostaje
rozwiązywalny, więc wznowienie historycznego runu nie zmienia jego zachowania.

Refinement klasycznego detektora nie tworzy osobnej boolowskiej maski i nie
skanuje jej dla każdego przesunięcia okna. Jedna suma integralna binarnej maski
zwraca dokładne liczby pikseli border/interior w czasie O(1). Wzór scoringu,
krok dwóch pikseli, kolejność kandydatów i tie-break pozostają bez zmian.
Ponieważ wynik detektora jest kanonicznie identyczny, optymalizacja wykonawcza
nie tworzy nowego selector fingerprintu. Próby skalowania oraz cropowania
wejścia zostały odrzucone po regresji na realnych zdjęciach.

## Architektura korekty v10.2

Przypadek realny `seq_18406-18414.jpg`, którego JPEG przedstawia zakres
`18415-18423`, ujawnił false merge grupy. Dwie wcześniejsze klatki dostarczyły
konsensus OCR `18406-18414`, natomiast niezależny ranking reprezentanta wybrał
późniejszą klatkę następnego ekranu. Eksporter poprawnie zapisał niespójną
decyzję domenową; nie był źródłem błędu.

V10.2 zachowuje rozdzielenie dowodu zakresu i oceny obrazu, ale wprowadza
`representative-range coherence gate`:

1. dowód zakresu zachowuje proweniencję kandydatów,
2. finalny reprezentant przechodzi pojedynczą kontrolę zakresu,
3. zgodny zakres pozwala na automatyczny eksport,
4. inny zakres uruchamia deterministyczny podział mieszanej grupy, jeżeli
   istnieje stabilna granica w kolejności źródeł,
5. brak jednoznacznego podziału kończy się `manual_required`, nigdy błędną nazwą.

Kontrola finalnego reprezentanta jest bounded do jednego obrazu na grupę.
Wariant szybszy może ograniczyć liczbę dodatkowych dowodów i zwiększyć liczbę
manualnych przypadków, lecz nie może ominąć kontroli spójności pliku i nazwy.

API otrzymuje stronicowaną historię runów gry oraz bezpieczny endpoint JPEG-a
kandydata. Endpoint weryfikuje `runId + groupId + candidateId` i serwuje tylko
plik znajdujący się w zarządzanym stagingu albo storage manualnym. Nie ujawnia
ścieżki absolutnej.

Admin utrzymuje wybrany `runId` w URL/stanie workspace'u. Sekcja historii
pokazuje status, czasy, liczby grup i nierozwiązanych decyzji. Modal review
pobiera do 500 metadanych źródeł grupy, renderuje lekkie miniatury z lazy-load,
otwiera jeden pełny obraz na żądanie i zapisuje decyzję istniejącym kontraktem
idempotencji. Worker zapisuje dla nowych grup rekord `manualGalleryOnly` dla
każdej lekkiej obserwacji. Rekord wskazuje istniejący plik stagingu i nie zawiera
BLOB-a. Przy odtwarzaniu domenowego stanu selektora rekordy te są filtrowane,
więc galeria nie zmienia shortlisty, wznowienia ani wyniku algorytmu.

Kandydat domenowy ma jednego właściciela w obrębie runu, zgodnie z unikalnym
`run_id + order_index`. Jeżeli późniejsza grupa dostarcza reprezentanta, który
rozstrzyga wcześniejszą grupę `manual_required`, kandydat przechodzi do tej
wcześniejszej grupy, a późniejszy wpis `skipped_existing_range` nie utrzymuje
drugiej kopii `top_candidates`. Tymczasowy wpis `manualGalleryOnly` może zostać
promowany do finalnej grupy tylko dla identycznego `order_index` i checksumu.
Inny checksum albo dwa pełne wyniki domenowe nadal oznaczają błąd trwałości.

Runy historyczne mogą zawierać wyłącznie top-12, ponieważ wcześniejszy worker nie
utrwalał pełnego członkostwa grupy. API zwraca `sourceCount`, a UI pokazuje
`items.length / sourceCount`; ręczny upload JPEG-a pozostaje kompatybilnym
fallbackiem.

## Architektura korekty v10.3

V10.3 zachowuje `representative-range coherence gate` v10.2, ale rozdziela
twarde błędy nazwy od miękkich błędów jakości obrazu. Zakres grupy nadal wynika
z adaptacyjnego konsensusu. Reprezentant może zostać wybrany automatycznie tylko
wtedy, gdy jego własny OCR zwraca dokładnie ten sam `start/end` z confidence
`>= 0.90`.

Standardowa ścieżka nadal preferuje kandydatów z kompletną geometrią. Jeżeli ich
brakuje, selektor przechodzi po deterministycznym rankingu pozostałych top-12 i
może wybrać najlepszy JPEG z miękką niezgodnością geometrii, kadru, ekspozycji
lub liczby plansz. Wybrany rekord otrzymuje
`RANGE_COHERENT_BEST_AVAILABLE`. Twarde blokady obejmują inny albo nieznany
zakres, `RANGE_CONFLICT`, okluzję, blur oraz techniczny błąd skanu lub pełnej
weryfikacji.

V10.3 nie zmienia tabel ani API. Nowa wersja algorytmu jest częścią manifestu i
tworzy nowy fingerprint. Resolver zachowuje manifest v10.2, dlatego rozpoczęty
run zawsze kończy się na zachowaniu, z którym został utworzony.

## Architektura hybrydowa v10.4

Manifest `fast-image-selector-v10.4` zachowuje strumieniowy skan całego folderu,
pełny lekki scoring grupy i bounded top-12, ale zmienia trzy kosztowne miejsca:

1. deskryptor grupowania jest liczony dla ROI siatki layoutów, a dwuklatkowy
   bufor granicy potwierdza zmianę względem stabilnej klatki starej grupy;
2. `GridFirstVisibleSequenceLabelRangeRecognizer` dopasowuje dziewięć pozycji
   etykiet i wysyła je jako jeden batch OCR dla JPEG-a;
3. `BoundedGridCandidateVerifier` uruchamia OCR dla najwyżej dwóch najlepszych
   kandydatów, natomiast pozostałe zdjęcia otrzymują wyłącznie tanią ocenę
   reprezentanta.

Konsensus zakresu rozróżnia dokładne odczyty i fuzzy odczyty z maksymalnie jedną
edycją znaku, ale korekta jest dozwolona tylko przez jednoznaczną arytmetyczną
siatkę `3×3`. Konflikt nie jest rozstrzygany cursorem. Jawna kotwica
`first_sequence_number` ustala pierwszy ekran, a kolejne zakresy mogą użyć
wyłącznie lokalnego dowodu lub dokładnie domkniętej, ograniczonej luki.

Wybór JPEG-a jest niezależnym krokiem po analizie całej grupy. Ranking nie ma
early exit i może wybrać obraz bez kompletnej geometrii, jeżeli jest to najlepszy
czytelny widok. Twarde powody — blur, okluzja, brak widocznej planszy, konflikt
zakresu oraz błąd skanu lub OCR — kierują grupę do review zamiast tworzyć
ryzykowny plik `seq_<start>-<end>.jpg`.

Nowy run v10.4 wymaga dodatniej kotwicy w Adminie, API, skrypcie live i CLI.
Kolumna bazy pozostaje nullable dla odtwarzalności historycznych runów. Worker
ponownie sprawdza kontrakt po pobraniu joba, więc stary klient nie może ominąć
bramki API. Manifest v10.4 ma fingerprint
`8e913c923036ba7aa3f448d1049a37676d133b603103d0b641912ef17004ee7e`;
resolver nadal zawiera wszystkie poprzednie fingerprinty.

Katalog wynikowy jest uchwytem File System Access API zapisanym w IndexedDB per
`gameId + runId`. Po ponownym otwarciu Admin sprawdza lub odnawia uprawnienie
`readwrite`; gdy uchwyt jest niedostępny, użytkownik wskazuje katalog ponownie.
Ledger `runId + groupOrder + checksum` umożliwia pełne uzgodnienie historycznego
runu. Zgodne checksumy są pomijane, a kolizja zatrzymuje operację.

Uchwyt wybrany w pierwszym kroku tworzenia nowej partii jest przechowywany
oddzielnie jako `pending` i nie ma jeszcze `runId`. Dopiero poprawna odpowiedź
create-run atomowo zmienia go w aktywne powiązanie `runId + directory` oraz
zapisuje w IndexedDB. Progresywny i ręczny eksport sprawdzają zgodność `runId`
powiązania przed każdym zapisem, dlatego zmiana aktywnego runu ani nieudany lub
anulowany upload nie mogą skierować historycznych decyzji do folderu nowej
partii.

Progresywny eksporter używa kursora `afterGroupOrder`; po wznowieniu wykonuje
jedno pełne uzgodnienie, a następnie pobiera wyłącznie nowe grupy. Ręczne
uzupełnienie wcześniejszej luki omija monotonny polling: callback zatwierdzenia
zapisuje dokładnie zmienioną grupę bezpośrednio do wybranego folderu i dopiero
po powodzeniu pozwala modalowi przejść dalej. Jeżeli run
miał już manifest wynikowy, backend unieważnia go, wznawia ten sam zakończony job
jako rewizję i publikuje nowy checksumowany manifest bez zmiany historii decyzji.

## Architektura odzyskiwania jakości v10.5

Manifest `fast-image-selector-v10.5` wraca do szerokiego
`opencv-appearance-descriptor-v2`, lecz pozostaje w bounded state machine v10.4.
Zmiana ekranu nadal wymaga dwóch klatek odbiegających od stabilnej większości
poprzedniej grupy, dzięki czemu pierwszy JPEG nowego ekranu rozpoczyna nową
grupę, ale pojedynczy refleks nie tworzy false splitu.

`BoundedGridCandidateVerifier` działa w v10.5 jako lekki port weryfikacji zakresu
i otrzymuje `IndependentEndpointVisibleSequenceLabelRangeRecognizer`. Nie
uruchamia `ClassicalPageBoardDetector`. Engine sprawdza kandydatów jakościowych
na poziomach `1, 2, 4`; recognizer wewnątrz JPEG-a rozszerza cropy
`18, 36, 72`. Dokładny dowód kończy pracę po jednym kandydacie, natomiast fuzzy
staje się zakresem grupy dopiero po dwóch zgodnych odczytach.

Ranking jakości obejmuje wszystkie zdjęcia grupy. Jeżeli jego zwycięzca nie był
źródłem dowodu, przechodzi jedną lekką kontrolę spójności zakresu. Brak zgodności
powoduje wybór najlepszego czytelnego kandydata, który potwierdza zakres, albo
`manual_required`; zakresu nie wolno przenosić na niesprawdzony JPEG.

Resolver fingerprintów przechowuje v10.4 i starsze manifesty. Odpowiedź runu
zawiera `selectorVersion` obliczane przez backend z fingerprintu. Nie wymaga to
migracji bazy ani mapowania wersji w frontendzie.

## Architektura rozdzielonych kolejek review

Projekcja grupy rozdziela dwie niezależne niepewności. Brak bezpiecznego JPEG-a
przy znanym zakresie ma stan `manual_required`; bezpieczny automatyczny JPEG bez
zakresu ma stan `range_required`. Dzięki temu użytkownik nie wykonuje ponownie
wyboru obrazu tylko dlatego, że OCR etykiet nie podał numerów.

Potwierdzenie zakresu nie zmienia `selected_automatic` kandydata i ustawia
`range_confirmed`. Odrzucenie z obu kolejek ustawia `rejected_by_user` oraz
`rejection_origin_status`; przywrócenie kasuje pochodzenie i odtwarza dokładnie
`manual_required` albo `range_required`. Decyzje `range_confirmed`,
`rejected_group` i `restored_group` są niezmiennymi wpisami audytu.

Admin pobiera grupy jednym stronicowanym przebiegiem i dzieli je lokalnie na
trzy listy: reprezentant, zakres i odrzucone. `skipped_unreadable` nie pojawia
się w żadnym modalu. Zapis do File System Access API jest wymagany tylko po
decyzji tworzącej wybrany output (`manually_selected` albo `range_confirmed`),
nie przy odrzucaniu lub przywracaniu samego stanu grupy.

## Architektura próbkowania v10.6

V10.6 zachowuje szeroki deskryptor wyglądu i dwuklatkowy bufor granicy v10.5.
Stan otwartej grupy nadal przechowuje najwyżej top-12 obserwacji, rolling
centroid i ostatni indeks źródła. Nie zapisuje pełnych obrazów ani wszystkich
deskryptorów.

Po zamknięciu grupy engine wylicza centralne okno pięciu indeksów. Brakujące
obserwacje odtwarza przez checksumowany cache taniego skanu, więc produkcyjnie
nie dekoduje ponownie JPEG-a. Jeżeli centralne okno nie ma czytelnej klatki,
analogicznie pobiera trzy indeksy z początku i trzy z końca. Dopiero potem może
użyć czytelnej top-12 z całej grupy.

OCR uruchamia się wyłącznie dla czytelnego wycinka. Brak lokalnego dowodu
zakresu nie unieważnia reprezentanta: grupa otrzymuje `range_required` wraz z
`selected_automatic`. Brak jakiejkolwiek czytelnej obserwacji kończy grupę jako
`skipped_unreadable` przed wywołaniem verifiera.

## Architektura czteroelementowego okna v10.7

`ContiguousWindowVisibleSequenceLabelRangeRecognizer` rozszerza historyczny
adapter niezależnych etykiet. Najpierw zachowuje silniejszy dowód siedmiu lub
więcej pozycji v10.5. Gdy ten dowód jest niekompletny, buduje trzy stabilne piki
osi X i Y ze wszystkich wykrytych komponentów etykiet, także tych, których OCR
nie odczytał, i mapuje czytelne liczby na pozycje `0..8`.

Hipoteza `start = number - position` jest akceptowana, jeżeli cztery kolejne
pozycje mają cztery kolejne liczby, co najmniej dwa zgodne odstępy poziome i
zgodny odstęp pionowy. Confidence wynika z minimum i średniej pewności czterech
odczytów i przekracza próg exact dopiero przy lokalnie spójnym oknie. Równe
hipotezy zwracają `RANGE_LABEL_CONTIGUOUS_WINDOW_AMBIGUOUS`.

Manifest v10.7 zmienia wyłącznie wersjonowany adapter zakresu i poziomy
progresji OCR na `9, 18, 36`; zachowuje próbkowanie reprezentanta v10.6,
grupowanie v10.5 i resolver wszystkich historycznych fingerprintów.

## Architektura pozycyjnej kotwicy v10.8

`BoundedGridCandidateVerifier` wykonuje tani detektor czerwonych ramek z
selekcyjnymi progami saturacji i jasności zapisanymi w manifeście. Pełne dziewięć
pozycji może zostać odtworzone z części ramek, lecz kotwica jest bezpieczna tylko
przy co najmniej pięciu obserwowanych pozycjach obejmujących wszystkie osie.
Detektor nie wykonuje cropów symboli ani komórek i nie zmienia głównego pipeline'u
geometrii.

`LayoutAnchoredVisibleSequenceLabelRangeRecognizer` wycina dziewięć etykiet na
podstawie quadów layoutów i wykonuje jeden batch OCR. Hipoteza korzysta wyłącznie
z czterech kolejnych pozycji. Inne wysokie, lecz błędne odczyty nie są globalnym
wetem, ponieważ nie należą do kompletnego okna; więcej niż jedna kompletna
hipoteza pozostaje niejednoznaczna. Gdy kotwica jest niedostępna, adapter może
użyć wyłącznie historycznego, silnego RANSAC siedmiu etykiet na poziomach `9/18`.

Kontrola jakości liczy ostrość wnętrza każdego odtworzonego layoutu. Mniej niż
pięć ostrych pozycji z pełnej siatki daje twardy powód `QUALITY_LAYOUT_BLUR`.
Lekko rozmazane, ale nadal użyteczne layouty pozostają dopuszczone.

Po strumieniowym domknięciu grup engine wykonuje bounded korektę fragmentacji.
`range_required` pomiędzy bezpośrednio kolejnymi potwierdzonymi zakresami staje
się `skipped_unreadable` z powodem `RANGE_REDUNDANT_TRANSITION_FRAGMENT`. Jedna
dokładna luka dziewięciu numerów może scalić wiele fragmentów: grupa, do której
źródłowo należy najlepszy czytelny JPEG, zachowuje kandydata i przejmuje zakres,
a pozostałe stają się `skipped_existing_range`. Korekta nie wypełnia większego
skoku, nie używa przewidywanego kursora i nie publikuje więcej niż jednego
JPEG-a na zakres. Kandydat nie może być technicznie przepinany pomiędzy grupami.
Każdy pominięty fragment zachowuje własne rekordy kandydatów jako odrzucone i
wskazuje `duplicate_of_group_order` właściciela dokładnego zakresu.

Manifest v10.8 ma osobny fingerprint, progresję OCR `9/18`, center-first pięciu
zdjęć oraz fallback trzech z każdego brzegu. Resolver zachowuje wszystkie
historyczne manifesty.

## Architektura częściowej kotwicy v10.9

`ClassicalPageBoardDetector` zachowuje niezmienioną ścieżkę v10.8. Dopiero jawna
flaga manifestu v10.9 uruchamia bounded dopasowanie afiniczne hipotez `3×3` z
trzech lub więcej ramek. Każda hipoteza musi wyjaśniać wszystkie użyte kontury,
obejmować dwie osie, mieścić się w obrazie i nie nakładać pól. Zbliżone hipotezy
są przekazywane razem do OCR; wyraźnie gorsze po wsparciu czerwonej ramki i
położeniu strony są odrzucane. Geometria sama nie wybiera zakresu.

`PartialLayoutAnchoredVisibleSequenceLabelRangeRecognizer` deduplikuje cropy po
quadzie i czyta najpierw pozycje z rzeczywistą ramką. Zachowuje konkurencyjne
odczyty surowego i przetworzonego cropa, a następnie ocenia je jako hipotezy
całej pozycyjnej siatki. Nie wybiera już zachłannie jednego wariantu dla każdej
liczby, co usuwa systematyczną zamianę pierwszej cyfry bez ukrywania konfliktu.
Brakujące pozycje są czytane dopiero wtedy, gdy obserwowane ramki nie dały
silnego dowodu; słaby dowód dwóch etykiet może dzięki temu zostać podniesiony do
silnego po dołączeniu pozycji odtworzonych.

Poziomy dowodu są jawne w manifeście: cztery kolejne etykiety od `0.72`, trzy
zgodne pozycje od `0.82` oraz dwie zgodne pozycje od `0.90`. Ostatni poziom
zwraca `RANGE_OCR_FUZZY_CANDIDATE` z confidence `0.82`; engine podnosi go do
zakresu grupy wyłącznie po zgodzie dwóch weryfikacji o różnych checksumach.
Silne hipotezy korzystające z pozycji syntetycznych muszą zawierać co najmniej
dwie rzeczywiście obserwowane etykiety. Remis zakresów ma pierwszeństwo przed
fallbackiem i kończy się bez decyzji.

Mały nierozstrzygnięty fragment ograniczony z obu stron tym samym dokładnym
zakresem jest w v10.9 klasyfikowany jako `skipped_existing_range`. Nie tworzy
pliku wynikowego i wskazuje poprzednią grupę jako właściciela duplikatu; v10.8
zachowuje historyczną klasyfikację takiego fragmentu.

Manifest v10.9 zmienia fingerprint pełnej selekcji, ale zachowuje adapter taniego
skanu v10.8. Cache skanu jest więc współdzielony, natomiast cache weryfikacji
pozostaje rozdzielony fingerprintem selektora. Nie ma zmiany schematu bazy,
OpenAPI ani typów Admina.

## Architektura bezpiecznej siatki etykiet v10.10

`LabelLatticeSafeVisibleSequenceLabelRangeRecognizer` zachowuje częściową
kotwicę v10.9, lecz odrzuca ją, gdy żadna rzeczywiście wykryta ramka nie należy
do górnego rzędu. Eliminuje to przypadek, w którym detektor dopasował
syntetyczny górny rząd do tabeli wypłat, a dwa poprawne odczyty z niższych
rzędów wyprowadziły zakres przesunięty o trzy.

Niezależny fallback działa progresywnie na 12, a następnie najwyżej 18 cropach.
Priorytet obejmuje zakres pionowy od górnych etykiet pierwszego rzędu do etykiet
trzeciego. Dopasowanie trzech osi odrzuca kandydatów bez minimalnej szerokości i
proporcji etykiety, dzięki czemu symbole nie przejmują pików wierszy. Resolver
akceptuje wyłącznie czteroelementowe okno v10.7 z jednoznaczną geometrią.

Podany przez operatora `first_sequence_number` jest w v10.10 ograniczeniem
modulo liczby layoutów, a nie kursorem przewidującym następny ekran. OCR spoza
tej siatki jest usuwany z dowodu przed konsensusem. Engine może następnie
rozdzielić fałszywie szeroką grupę wyglądu, ale tylko gdy dwie lub więcej
silnych hipotez tworzy bezpośrednio kolejny ciąg i ich reprezentanci występują w
tej samej kolejności w źródle. Liczność pierwotnej grupy jest dzielona
deterministycznie na granicach pomiędzy indeksami reprezentantów; kandydat nie
jest współdzielony przez dwa wyniki.

V10.10 ma osobny adapter zakresu, manifest i fingerprint. Manifest v10.9 oraz
jego fabryka pozostają rozwiązywalne bez zmiany zachowania. Cache taniego skanu
pozostaje współdzielony, a cache weryfikacji jest izolowany fingerprintem.
Zmiana nie wymaga migracji bazy ani modyfikacji OpenAPI.

## Architektura pochodnego odzyskiwania v10.11

Run pochodny jest zwykłym runem selekcji korzystającym z istniejącego stagingu
i lane, ale zapisuje `source_run_id`, `source_snapshot_sha256` oraz tryb
`range_recovery`. Idempotencja obejmuje źródło, snapshot i fingerprint selektora.
Publikacja sprawdza, czy snapshot źródła nie zmienił się od utworzenia runu; w
przeciwnym razie wynik nie jest udostępniany jako aktualny.

Pewne grupy są kopiowane jako projekcja z jawnym `origin_group_id`. Maksymalne
bloki `range_required` otrzymują po dwie kotwice z każdej strony. Kotwice są
ponownie sprawdzane i przy konflikcie blok rozszerza się do dwóch zgodnych
kotwic albo granicy zbioru. Wszystkie kandydaty rozszerzonego bloku są
deduplikowane checksumą, sortowane po `order_index` i ponownie segmentowane;
stare `group_id`, granice i `selected_candidate_id` nie wpływają na wynik.

V10.11 najpierw ocenia niezależne, pozycyjne hipotezy siatki etykiet. Częściowa
geometria jest dowodem pomocniczym i nie może zawetować jednego silnego okna.
Słaby konsensus obejmuje co najmniej dwa różne JPEG-i, trzy różne pozycje i
cztery zgodne obserwacje. Jedna dokładnie ograniczona luka może potwierdzić
lokalny odczyt, ale ciągłość nie jest samodzielnym źródłem zakresu.

API tworzenia recovery zwraca run i job pochodny oraz statystyki snapshotu.
Potwierdzenie zakresu przyjmuje opcjonalny `candidateId`, aby w jednej
transakcji zmienić reprezentanta i zakres. Admin otwiera modal po przywróceniu
samego uchwytu folderu; pełny reconcile nie znajduje się na ścieżce krytycznej.

Worker oraz operatorski dry-run wywołują tę samą funkcję `evaluate_recovery`.
Każdy lokalny blok nadal otrzymuje globalny `first_sequence_number` do kontroli
zgodności modulo, ale wyłącza regułę kotwiczącą jego pierwszą grupę jako początek
całego runu. Po zakończeniu segmentacji osobna bramka cofa automatyczny wynik do
`range_required`, jeżeli wybrany JPEG nie ma własnego, zgodnego odczytu albo ma
powód `RANGE_OWNER_ANCHOR`/`RANGE_INFERRED_FROM_BOUNDED_GAP`.

Dry-run jest tylko do odczytu względem bazy i źródłowego runu. Odmawia startu
przed migracją 0042 oraz podczas aktywnego joba selekcji, ponownie sprawdza
snapshot po analizie i zapisuje atomowy raport
`image-selection-range-recovery-dry-run-v1`. Raport zawiera wszystkie bramki
strukturalne oraz deterministyczną, warstwową próbę 100 wyników. Utworzenie runu
recovery pozostaje zablokowane, dopóki właściciel nie dostarczy pełnego audytu
tej próby z zerem błędnych zakresów.

## Korekta dwucyfrowego konsensusu v10.12

Dry-run v10.11 wykazał, że niezależna siatka odrzucała 282 grupy jako
`RANGE_LABEL_LATTICE_INCOMPLETE`, chociaż zakotwiczona ścieżka znajdowała w
części z nich bezpieczne pary etykiet. `TwoLabelConsensusVisibleSequenceLabelRangeRecognizer`
dziedziczy kolejność tras i bramki konfliktów v10.11, ale dodaje słabą hipotezę
z dwóch różnych pozycji o minimalnej pewności `0.90`. Hipoteza musi jednoznacznie
wyznaczać ten sam początek; równorzędne rozwiązania są odrzucane.

Adapter nie publikuje zakresu na podstawie jednego zdjęcia. Engine zachowuje
bramkę `_hybrid_group_range`, która dla słabego dowodu wymaga zgodności co
najmniej dwóch różnych checksum JPEG. Mocna, sprzeczna hipoteza nadal ma
pierwszeństwo fail-closed. Pozwala to wykorzystać czytelne pary liczb bez
powrotu do zgadywania z kursora albo z samej ciągłości.

`assemble_recovery_projection` wykonuje po złożeniu wszystkich lokalnych bloków
globalne uzgodnienie zakresów. Dla powtórzonego zakresu wybiera jednego
deterministycznego właściciela, preferując jedyną chronioną decyzję użytkownika,
a inne wyniki oznacza `skipped_existing_range` z odwołaniem do właściciela.
Co najmniej dwie chronione decyzje o tym samym zakresie pozostają konfliktem
strukturalnym, aby dry-run nie ukrywał niespójności danych.

V10.12 ma osobny manifest i fingerprint
`d1f482ef3b52f62d478e9bcd3c06777d0e62eb118bb639a854fbb2cb594b0727`.
Cache taniego skanu pozostaje współdzielony, a cache pełnej weryfikacji jest
izolowany fingerprintem. Resolver i fingerprint v10.11 pozostają niezmienne.

## Uzgadnianie pełnej liczności v10.13

`SequenceBounds` modeluje inkluzywny przedział, kierunek i stały rozmiar grupy
równy dziewięć. Liczba oczekiwanych grup jest zaokrąglana w górę, dzięki czemu
przedział `229913–248184` ma 2031 grup, z ostatnią `248183–248184`. API zapisuje
`last_sequence_number` w runie i payloadzie joba; migracja 0043 rozszerza nim
również klucze idempotencji pełnego runu i recovery. Historyczne runy zachowują
wartość zerową i wymagają jawnego końca przy pierwszej naprawie. Kontrakt rerunu
przenosi ten koniec razem z opcjonalną nową kotwicą początku; kontrolowany runner
zapisuje oba parametry w PID state i raporcie operatorskim.

Przed recovery algorytm rozwiązuje monotoniczne przypisanie 2295 fizycznych
fragmentów do 2201 pozycji siatki. Programowanie dynamiczne ma dokładnie dwie
operacje: zachowanie fragmentu jako kolejnego właściciela albo pominięcie go
jako duplikatu. Liczba pominięć jest z góry wyznaczona przez różnicę liczności.
Chroniona decyzja użytkownika może tylko pozostać właścicielem swojego dokładnego
zakresu. Koszt preferuje istniejący zgodny zakres oraz dotychczasowy duplikat;
duży fragment nie jest pomijalny, ponieważ może zawierać false merge.

Fragment zachowany na innej pozycji niż jego poprzedni automatyczny zakres oraz
wcześniej nadmiarowo pominięty fragment stają się wejściem `range_required`.
Recovery ponownie analizuje ich kandydatów, wyznacza granice i reprezentanta.
Po złożeniu bloków ten sam typ przypisania działa jako końcowy reconciler:
ustawia dokładne zakresy siatki, wiąże każdy nadmiarowy fragment z właścicielem
i sprawdza liczbę oraz ciągłość wszystkich właścicieli.

Operatorski dry-run wykonuje dodatkową bramkę pokrycia obrazami. Dla grup
przebudowanych źródłem dowodu jest wybrany kandydat, lista kandydatów albo
odtworzona galeria; dla grup nietkniętych wolno użyć zachowanej galerii grupy
źródłowej. Checksum każdego dowodu musi występować w manifeście stagingu.
`skipped_existing_range` nie jest osobnym logicznym właścicielem. Raport zapisuje
liczbę właścicieli ze zdjęciem, grup pustych i referencji spoza manifestu.

Powód `RANGE_CARDINALITY_INFERRED` oznacza, że numer wynika z udowodnionej
pozycji w kompletnej sekwencji, a nie z pojedynczego OCR. Nie omija on bramek
jakości reprezentanta: konflikt, rozmycie, zasłonięcie i błąd geometrii
pozostają manualne. Własny rozpoznany zakres kandydata musi być zgodny z
oczekiwanym; zakresu sprzecznego nie wolno nadpisać inferencją liczności. Pełny
run wykonuje końcowe uzgodnienie przed review i eksportem; recovery stosuje je
po globalnym złożeniu przebudowanych bloków.

Końcowe uzgodnienie pełnego runu używa osobnej operacji repozytorium
`persist_reconciled_groups`. W jednej fenced transakcji PostgreSQL blokowany jest
run i wszystkie jego grupy. Pierwsza faza zmienia wyłącznie modyfikowalne
`auto_selected` na neutralne `range_required` bez zakresu, aby zwolnić wpisy
częściowego indeksu `uq_image_selection_groups_selected_range`; po `flush` druga
faza zapisuje wszystkie docelowe statusy i zakresy. Chronione decyzje
`manually_selected`, `missing_image`, `range_confirmed` i `rejected_by_user`
pozostają nietknięte przez fazę zwalniania. Przed commitem repozytorium porównuje
każdy rekord z projekcją i ponownie egzekwuje dokładną liczność oraz uporządkowaną
siatkę `SequenceBounds`. `IntegrityError` tej operacji jest mapowany na
`IMAGE_SELECTION_PROJECTION_PERSISTENCE_CONFLICT` i powoduje rollback całej
transakcji.

Po udanym zapisie sink zastępuje swój surowy widok grup uzgodnioną projekcją.
Dzięki temu checkpoint `manual_review` albo `writing_manifest` raportuje tę samą
liczbę właścicieli i duplikatów, którą odczyta API, zamiast stanu sprzed
reconciliacji.

Progresywny eksport nadal przesuwa monotoniczny `groupOrder`, ale nie jest
źródłem prawdy dla stanu końcowego. Dla `waiting_for_review` i `completed`
runner pobiera wszystkie strony od `afterGroupOrder=-1`, buduje kanoniczny zbiór
plików dla trzech gotowych statusów, weryfikuje lub atomowo zastępuje zawartość i
usuwa wyłącznie osierocone pliki pasujące do `seq_<start>-<end>.jpg`. Następnie
raport schema v3 niezależnie sprawdza pokrycie logicznej siatki i pokrycie
gotowych grup plikami. Stan `failed`/`cancelled` uruchamia ten sam audyt bez
jakiejkolwiek mutacji katalogu.

V10.13 zachowuje adaptery obrazu oraz OCR v10.12, ma jednak osobny manifest i
fingerprint `b52b09737bf59eae712f7757c8e368fbfaf52e56f351889fbd3aa873a3d5fd30`.
Cache może odczytać zgodny wynik weryfikacji v10.12 i promować go pod nowy klucz;
telemetria raportuje takie trafienia osobno.

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
