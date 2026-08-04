---
title: Fast representative image selection architecture
status: accepted
release: "0.4"
last_updated: 2026-08-03
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
  -> cheap thumbnail scan
  -> sequential group detector
  -> top-k verification
  -> automatic representative OR manual_required
  -> optional manual photo/range OR explicit skip as missing_image
  -> immutable selected manifest
  -> explicit handoff
  -> existing Import layoutów
```

## Granice komponentów

### Admin web

- renderuje czwarty workspace `Selekcja zdjęć`,
- korzysta ze wspólnego game context i parametrów URL,
- reużywa kontrolowany folder input oraz postęp uploadu,
- pokazuje postęp joba, agregaty i kolejkę manualną,
- nie wykonuje quality scoring ani OCR w przeglądarce,
- przekazuje do `Importu layoutów` wyłącznie zakończony run.

### Admin API

- poświadcza upload oraz jego przeznaczenie `photo_selection`,
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
- zapisuje checkpoint co plik lub bounded partię,
- utrzymuje tylko miniaturę bieżącego pliku i top-k metadanych grupy,
- nie wywołuje `BoardCellCropper` ani symbol ONNX,
- kończy jako `waiting_for_review`, gdy istnieją grupy manualne, albo
  `completed`, gdy manifest jest kompletny,
- używa istniejącego `execution_slot = 1`, lease, heartbeat, cancel i retry.

### PostgreSQL

Encje:

- `image_selection_runs` — game, job, input manifest, selector fingerprint,
  ordering policy, output manifest i lifecycle projekcji,
- `image_selection_groups` — kolejność wystąpienia, rozpoznany zakres lub brak,
  fingerprint, konsensus liczby plansz, stan oraz wybrany kandydat,
- `image_selection_candidates` — order index, ścieżka, checksum, wymiary,
  metryki jakości, confidence, reason codes i decyzja,
- `image_selection_manual_decisions` — append-only rewizje ręcznych decyzji,
  UUID idempotencji, resolution, opcjonalny wybrany kandydat, obowiązkowy zakres
  i checksumę payloadu.

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
- przyjazna nazwa kopii wynikowej ma postać `seq_<start>-<end>.jpg`; po
  publikacji przeglądarka może skopiować zweryfikowany zestaw do folderu
  wskazanego przez użytkownika, bez przekazywania backendowi dowolnej ścieżki,
- nazwa publiczna jest wyprowadzana z zakresu zapisanego w manifestcie, a nie z
  wewnętrznej nazwy managed file. Dzięki temu wcześniejsze content-addressed
  pliki z paddingiem i checksumą pozostają czytelne bez migracji lub zmiany
  niezmiennego outputu,
- unselected staging może zostać usunięty dopiero po atomowym commitcie wyniku
  albo po jawnym anulowaniu; źródłowy folder użytkownika jest read-only,
- output manifest jest kanonicznym JSON bez ścieżek absolutnych.

## Wersjonowany algorytm `fast-image-selector`

### Tani skan per plik

1. Weryfikacja JPEG i SHA-256.
2. EXIF transpose oraz miniatura z ograniczonym dłuższym bokiem.
3. Downscaled page/board lattice detection.
4. Metryki jakości: sharpness, exposure, highlight clipping, glare proxy,
   perspective, border margin, board visibility.
5. Niezależny od zmiennej liczby wykrytych czerwonych ramek fingerprint HSV
   obszaru ekranu.
6. Decyzja, czy potrzebny jest sparse OCR kotwic zakresu.

### Granice grup

State machine nie przewiduje następnego numeru. Nową grupę otwiera dopiero
łączny dowód:

- spadek podobieństwa fingerprintu,
- zmiana geometrii/lattice,
- zgodny, wystarczająco pewny nowy zakres OCR,
- albo bounded guard sample potwierdzający zmianę.

Pojedynczy słaby sygnał nie zamyka grupy. Po utrwaleniu reprezentanta późniejszy
powrót tego samego zakresu otrzymuje `skipped_existing_range`. Zakres jeszcze
nierozwiązany może przyjąć lepszego kandydata z późniejszego wystąpienia.

### Identyfikacja zakresu

- OCR działa na numerach pierwszej, ostatniej i opcjonalnie środkowej wykrytej
  planszy, batchowo dla kandydata.
- `fast-image-selector-v2` ma fail-closed fallback pełnej rozdzielczości:
  wykrywa jasne etykiety numerów bez zależności od czerwonych ramek i uznaje
  zakres dziewięciu plansz dopiero przy co najmniej sześciu zgodnych punktach
  siatki, obecnym pierwszym i ostatnim numerze, trzech wierszach, trzech
  kolumnach oraz jednoznacznej homografii RANSAC.
- Zakres jest poprawny tylko dla dodatnich wartości w rosnącej kolejności,
  zgodnych z liczbą wykrytych pozycji.
- Finalna strona może zawierać 1–9 plansz.
- Brak zgodnego zakresu zachowuje grupę jako `unknown`; nie tworzy numerów.

### Ranking i fail-closed

- Dla grupy przechowywane są metadane najwyżej `topK`, domyślnie 3.
- Pełniejsza walidacja selektora działa tylko na top-k.
- Reprezentant automatyczny wymaga progu kompletności, jakości i confidence
  zakresu.
- Błędne scalenie zakresów jest krytyczniejsze niż dodatkowy manual review.
  Każda niejednoznaczność daje `manual_required`.

Wagi, progi, rozmiar miniatury i guard interval są częścią wersjonowanego
manifestu selektora. Nie mogą być ukrytymi stałymi rozproszonymi po UI i CLI.

Aktualna implementacja `fast-image-selector-v2` utrzymuje manifest w jednym
module, wylicza z jego kanonicznego JSON fingerprint
`6da6fb8a247b41827a87437e6936cc4c449e06a0bbd24acd8b3159d576c1ce8e`
i używa tego samego fingerprintu przy tworzeniu runu przez API. Jawne porty
oddzielają loader miniatury, metryki jakości, lattice/fingerprint oraz OCR
zakresu. Samodzielny diagnostyczny przebieg CLI bez lokalnego modelu OCR używa
innej wersji adaptera i fingerprintu, dlatego nie może zostać pomylony z
produkcyjnym auto-wyborem.

Skan zapisuje metryki kandydata strumieniowo, zachowuje w pamięci tylko bieżącą
grupę, bounded pending guard i `topK = 3`, a checkpoint postępu powstaje co 32
pliki. Pojedynczy silny kandydat granicy nie tworzy oddzielnej grupy.
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
- Ręczna decyzja używa UUID idempotencji i append-only eventu albo równoważnej
  wersjonowanej historii; retry nie tworzy drugiej kopii pliku. Korekta przed
  publikacją dodaje rewizję i aktualizuje projekcję oraz manifest roboczy.
- Po publikacji content-addressed output jest niezmienny. Dalsza korekta wymaga
  nowego runu i nie mutuje artefaktu, który mógł już zostać przekazany do importu.
- `missing_image` jest terminalnym, trwałym stanem grupy. Publisher pomija
  kopiowanie JPEG-a dla takiej grupy. Jeżeli zakres jest znany, pozostaje
  widoczny jako `Brak zdjęcia dla layoutów X–Y`; jeżeli OCR nie ustalił zakresu,
  oba pola pozostają `null`, a UI pokazuje `Nierozpoznany zestaw zdjęć` bez
  technicznego numeru grupy.
- Publisher zapisuje JPEG-i i kanoniczny `manifest.json` do izolowanego
  `.pending`, wykonuje ponowny odczyt checksum i wymiarów, a następnie publikuje
  cały katalog jednym rename w tym samym filesystemie. Awaria przed rename nie
  tworzy widocznego częściowego outputu.
- Handoff weryfikuje checksumę manifestu, wszystkie wybrane pliki, proweniencję
  runu oraz zgodność zakresów z trwałymi decyzjami grup przed wydaniem
  krótkotrwałego tokenu do właściwego importu.
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
GET  /api/v1/admin/image-selections/{runId}/output
GET  /api/v1/admin/image-selections/{runId}/output/{fileName}
PUT  /api/v1/admin/image-selections/{runId}/groups/{groupId}/manual-file
GET  /api/v1/admin/image-selections/{runId}/groups/{groupId}/manual-files/{candidateId}
POST /api/v1/admin/image-selections/{runId}/groups/{groupId}/approve
POST /api/v1/admin/image-selections/{runId}/groups/{groupId}/continue-without-image
POST /api/v1/admin/image-selections/{runId}/handoff
```

Dokładne request/response i stabilne błędy TASK-0151–0155 są w OpenAPI.
Frontend korzysta wyłącznie z generowanego klienta.

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

- O(n) odczytów miniatur i metryk jakości.
- OCR oraz dokładniejsza weryfikacja są O(g × topK), gdzie `g` to liczba grup,
  a nie liczba wszystkich zdjęć.
- Rekordy kandydatów zapisują się bounded partiami; obrazy nie trafiają do RAM
  ani PostgreSQL jako kolekcja.
- Benchmark mierzy upload osobno od obliczeń, aby wolny dysk lub kopiowanie nie
  ukrywały kosztu selektora.
- Bramka 10k/30k, peak RSS, OCR invocation count, precision grupowania i
  manual-review rate jest obowiązkowa przed pełnym użyciem.

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
