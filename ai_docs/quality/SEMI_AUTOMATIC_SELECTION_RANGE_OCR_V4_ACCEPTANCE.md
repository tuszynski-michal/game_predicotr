# Odbiór range-only OCR v4.1

Data odbioru: 2026-09-01

Wariant: `semi-automatic-range-only-ocr-v4-middle-row-triple-v2`

## Decyzja

Rollout nie został zaakceptowany. Wariant pozostaje wyłączony i nie staje się
domyślnym recognizerem nowych runów. Exact proof oraz wybór reprezentanta są
bezpieczne, a cele wydajnościowe zostały przekroczone, ale zamrożony golden set
nie osiągnął minimalnego coverage ani przechwycenia grup.

Nie obniżono progów confidence, nie dodano fuzzy matching i nie wykorzystano
nazwy pliku, indeksu źródła ani sąsiednich zdjęć do ustalania zakresu.

## Korpusy

- Tuning: 30 checksum-bound źródeł, rozłącznych z golden i challenge.
- Golden: 100 checksum-bound surowych JPEG-ów z dziesięciu części rzeczywistego
  katalogu; 99 czytelnych i jedna animowana klatka przejściowa oznaczona
  `ambiguous`.
- Challenge: 19 dostarczonych źródeł zakresu `21169–21177`; 16 czytelnych i
  trzy nieczytelne przez motion blur.
- Wydajność: 1000 surowych źródeł od offsetu 0 oraz 1000 od offsetu 9000.

Zestawy wydajnościowe nie mają ground truth dla wszystkich klatek. Dlatego nie
raportują `falseExactCount` ani frame coverage. Ręcznie sprawdzono natomiast
wszystkie 120 automatycznie wybranych reprezentantów.

## Wyniki jakości

| Zestaw | Exact | False exact | Exact precision | Readable coverage | Group capture | Wybrane | Selected precision | Own proof |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Challenge 19 | 10 | 0 | 100% | 62,5% | 100% | 1 | 100% | 100% |
| Golden 100 | 26 | 0 | 100% | 26,3% | 35,3% | 6 | 100% | 100% |
| Trudne 1000 | 365 | n/d | n/d | n/d | n/d | 66 | 100% | 100% |
| Łatwiejsze 1000 | 234 | n/d | n/d | n/d | n/d | 54 | 100% | 100% |

W challenge wszystkie trzy nieczytelne klatki zwróciły `unknown`. Wszystkie 120
reprezentantów z prób 1000 miało widoczny własny middle-row triple, należało do
raportowanego zakresu i znajdowało się przy środku dostępnego evidence span.

## Bramki

| Bramka | Wynik |
|---|---|
| Zero false exact na challenge | PASS |
| Zero false exact na golden | PASS |
| Selected range precision 100% | PASS |
| Selected own proof 100% | PASS |
| Readable frame coverage co najmniej 50% | **FAIL — 26,3%** |
| Range group capture co najmniej 90% | **FAIL — 35,3%** |
| Trudna próba co najmniej 2 źródła/s | PASS — 4,83 źródła/s |
| Łatwiejsza próba co najmniej 3 źródła/s | PASS — 5,05 źródła/s |
| Mediana 1000 nie większa niż 110% próbki 100 | PASS — 105,5% / 101,8% |

## Wydajność

| Metryka | Golden 100 | Trudne 1000 | Łatwiejsze 1000 |
|---|---:|---:|---:|
| Scan | 18,87 s | 206,86 s | 197,95 s |
| Źródła/s | 5,30 | 4,83 | 5,05 |
| Mediana/źródło | 201,2 ms | 212,3 ms | 204,8 ms |
| p95/źródło | 245,6 ms | 247,0 ms | 232,1 ms |
| Peak RSS | 429 MiB | 555 MiB | 581 MiB |
| OCR calls | 16 | 164 | 165 |
| OCR internal batches | 30 | 306 | 304 |
| OCR crops | 228 | 2496 | 2499 |
| Średnie wypełnienie batcha | 84,4% | 90,6% | 91,3% |
| Odrzucone przed OCR | 30,0% | 17,4% | 17,3% |

Dla trudnej próby główne składniki czasu wyniosły: odczyt źródeł 0,45 s,
decode 20,29 s, EXIF 31,23 s, rotation 0,17 s, łączny locator wraz z
thumbnail/crop/readability 44,15 s, preprocessing Paddle 0,52 s, inferencja
Paddle 106,06 s i grouping 0,01 s. Checkpoint read-only harnessu nie zapisuje
stanu i wynosi 0 s. Największym pojedynczym kosztem jest inferencja OCR.

Harness nie rozdziela jeszcze wewnętrznego czasu locatora na thumbnail,
readability i crop extraction. Łączna wartość jest wiarygodna, lecz bardziej
szczegółowa optymalizacja wymaga osobnej, behavior-neutral telemetrii.

## Skalowanie i projekcja 42 000 zdjęć

- Trudna próba: około 8688 s, czyli 2 h 24 min 48 s samego skanu.
- Łatwiejsza próba: około 8314 s, czyli 2 h 18 min 34 s samego skanu.
- Do projekcji należy doliczyć jednorazową inicjalizację modelu, kalibrację,
  checkpointy produkcyjnego runu i finalizację grup.

Mediana trudnej próby stanowi 105,5% mediany próbki 100, a łatwiejszej 101,8%.
Koszt rośnie liniowo z liczbą źródeł; nie zaobserwowano wzrostu parabolicznego.

## Przyczyna nieudanego coverage

Na golden secie dominowały:

- `NO_EXPECTED_RANGE_MATCH`: 34 źródła — locator często wskazał strukturalnie
  poprawny, lecz niewłaściwy rząd etykiet;
- `UNKNOWN_LATTICE`: 20;
- `CROP_POSSIBLY_CLIPPED`: 8;
- `LOW_OCR_CONFIDENCE`: 8;
- `AMBIGUOUS_LATTICE`: 2;
- `INCONSISTENT_TRIPLE`: 2.

To problem lokalizacji rzędu i kompletności cropa, nie dowód, że należy
osłabiać exact proof. Kolejna iteracja powinna być dostrajana wyłącznie na
oddzielnym tuning secie, poprawić identyfikację rzeczywistego środkowego rzędu
i crop padding, a następnie użyć nowego fingerprintu i nowego, wcześniej
niewidzianego holdoutu. Obecny frozen golden pozostaje niezmiennym dowodem
nieudanego odbioru tej wersji.

## Invarianty

- Nie uruchomiono board detection, geometrii, croppera plansz ani symbol
  inference.
- Nie zapisano źródłowych JPEG-ów ani cropów.
- V1–v3 i ich fingerprinty nie zostały zmienione.
- V4.1 pozostaje za istniejącą flagą i nie jest włączone domyślnie.
- Raporty 1000 nie przedstawiają braku ground truth jako zerowej liczby
  błędów; jakość tych prób opiera się wyłącznie na ręcznej kontroli wybranych
  reprezentantów.

## Artefakty

- `middle-row-range-ocr-v4-tuning.json`
- `middle-row-range-ocr-v4-golden.json`
- `middle-row-range-ocr-v4-challenge.json`
- `middle-row-range-ocr-v4-*-report.json`
- `middle-row-range-ocr-v4-*-selected-review.json`

Wszystkie manifesty źródeł i ręczne protokoły są checksum-bound. Pełne raporty
zachowują fingerprint runtime'u, modelu Paddle, checksummy źródeł, reason codes,
liczniki i czasy.
