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
  -> manual single-file completion
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
- zapisuje idempotentne decyzje manualne,
- publikuje handoff token wyłącznie dla kompletnego manifestu,
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
  UUID idempotencji, wybrany kandydat, zakres i checksumę payloadu.

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
- unselected staging może zostać usunięty dopiero po atomowym commitcie wyniku
  albo po jawnym anulowaniu; źródłowy folder użytkownika jest read-only,
- output manifest jest kanonicznym JSON bez ścieżek absolutnych.

## Algorytm `fast-image-selector-v1`

### Tani skan per plik

1. Weryfikacja JPEG i SHA-256.
2. EXIF transpose oraz miniatura z ograniczonym dłuższym bokiem.
3. Downscaled page/board lattice detection.
4. Metryki jakości: sharpness, exposure, highlight clipping, glare proxy,
   perspective, border margin, board visibility.
5. Fingerprint wyprostowanego obszaru ekranu.
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

Implementacja `fast-image-selector-v1` utrzymuje manifest w jednym module,
wylicza z jego kanonicznego JSON fingerprint
`dc968e65d94170ab5011ccc4d1474a01ef7f4f143bdf93f59700859f50b34982`
i używa tego samego fingerprintu przy tworzeniu runu przez API. Jawne porty
oddzielają loader miniatury, metryki jakości, lattice/fingerprint oraz OCR
zakresu. Samodzielny diagnostyczny przebieg CLI bez lokalnego modelu OCR używa
innej wersji adaptera i fingerprintu, dlatego nie może zostać pomylony z
produkcyjnym auto-wyborem.

Skan zapisuje metryki kandydata strumieniowo, zachowuje w pamięci tylko bieżącą
grupę, bounded pending guard i `topK = 3`, a checkpoint postępu powstaje co 32
pliki. Pojedynczy silny kandydat granicy może utworzyć oddzielną grupę, ale bez
zgodnej pełniejszej geometrii i pewnych kotwic zakresu kończy jako
`manual_required`; priorytetem pozostaje brak fałszywego scalenia.

## Kontrakty i idempotencja

- `selectorFingerprint` jest SHA-256 kanonicznego manifestu adapterów, progów i
  wersji algorytmu.
- `inputManifestSha256` obejmuje uporządkowane względne ścieżki, rozmiary i
  checksumy wszystkich wejść.
- `input_key` joba zależy od gry, obu fingerprintów i wersji kontraktu.
- Retry tego samego wejścia wznawia ten sam run i checkpoint.
- Zmiana pliku, kolejności albo wersji selektora tworzy nowy run.
- Ręczna decyzja używa UUID idempotencji i append-only eventu albo równoważnej
  wersjonowanej historii; retry nie tworzy drugiej kopii pliku. Korekta przed
  publikacją dodaje rewizję i aktualizuje projekcję oraz manifest roboczy.
- Po publikacji content-addressed output jest niezmienny. Dalsza korekta wymaga
  nowego runu i nie mutuje artefaktu, który mógł już zostać przekazany do importu.
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
PUT  /api/v1/admin/image-selections/{runId}/groups/{groupId}/manual-file
GET  /api/v1/admin/image-selections/{runId}/groups/{groupId}/manual-files/{candidateId}
POST /api/v1/admin/image-selections/{runId}/groups/{groupId}/approve
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
| skipped_existing_range
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
