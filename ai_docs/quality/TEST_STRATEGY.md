---
title: Test strategy
status: proposed
last_updated: 2026-07-23
---

# Strategia testów

## Zasada

Największe ryzyko znajduje się w logice domenowej i integralności kolejności, dlatego testy algorytmów są ważniejsze niż snapshoty UI.

## Backend unit tests

### Matching

- pusty prefiks,
- prefiks z 0 kandydatów,
- prefiks z 1 kandydatem,
- prefiks z wieloma kandydatami,
- exact unique,
- exact duplicate,
- nieprawidłowy symbol,
- nieprawidłowa długość tablicy,
- confirmation chain rozstrzygnięty po 1 i kilku layoutach,
- confirmation chain kończący się 0 kandydatów.

### Payouts

Po wdrożeniu M3:

- linia prosta,
- V,
- długość 2/3/4/5,
- przerwanie dopasowania,
- joker na początku/w środku/końcu,
- kilka symboli i kilka linii,
- brak podwójnego naliczania,
- audytowalne matched cells.

### Forecast

Po wdrożeniu M4:

- pierwszy wynik dodatni,
- spadek po dodatnim wyniku,
- kolejny high-water mark,
- brak dodatniego wyniku,
- koniec sekwencji,
- limit 100 000,
- brak numeru pośrodku zakresu,
- deterministyczny wynik.

## Repository/integration tests

Uruchamiane na testowym PostgreSQL:

- unikalność sequence_number,
- dozwolone duplikaty signature,
- wydajne exact lookup,
- transakcja publikacji datasetu,
- idempotentny seeder,
- staging nie jest widoczny dla publicznego API.

## API tests

- poprawne statusy HTTP,
- schema odpowiedzi zgodna z OpenAPI,
- mapowanie błędów domenowych,
- brak przecieku wewnętrznych stack trace,
- limit rozmiaru wejścia.

## Mobile tests

### Reducer/unit

- append symbol,
- undo pojedynczego symbolu,
- undo automatycznego uzupełnienia jako jednej operacji,
- reset,
- zmiana gry,
- pełna plansza,
- odrzucona propozycja prefiksu.

### Component/integration

- kolejność komórek,
- disabled states,
- modal accept/close,
- loading/error/retry,
- ambiguous message,
- target hidden for ambiguous.

### E2E smoke

Na późniejszym etapie jeden stabilny scenariusz na emulatorze lub urządzeniu. Nie budujemy rozbudowanej automatyzacji E2E przed ustabilizowaniem UI.

## Image pipeline tests

- golden images z oczekiwanymi bounding boxes,
- zdjęcia obrócone,
- perspektywa,
- słabe światło,
- brak jednego layoutu,
- OCR z błędem,
- błędna klasyfikacja trafia do review,
- wznowienie po przerwaniu,
- idempotencja.

## Test data

- stałe seedy,
- jawne przypadki duplikatów,
- mały fixture do unit tests,
- średni dataset do integration,
- reprezentatywny benchmark co najmniej 500 000 layoutów przed M4/M8.

## Performance budgets — propozycja

Do zatwierdzenia po pierwszym benchmarku:

- exact match p95 < 200 ms w środowisku lokalnym,
- partial match p95 < 300 ms dla typowego prefiksu,
- forecast 100 000 layoutów < 5 s lokalnie lub asynchroniczna prezentacja postępu,
- import nie zużywa całej pamięci; przetwarzanie partiami.

Budżety są celami roboczymi, nie gwarancją przed wykonaniem pomiarów.
