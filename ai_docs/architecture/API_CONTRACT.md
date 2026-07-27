---
title: Admin API and mobile data contracts
status: accepted
last_updated: 2026-07-27
---

# Kontrakty API i danych mobilnych

## Granica systemu

HTTP API służy wyłącznie lokalnemu panelowi administracyjnemu. Aplikacja Android nie wywołuje żadnego endpointu i nie potrzebuje serwera do matching ani Target.

Prefix Admin API:

```text
/api/v1/admin
```

Format błędu:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Nie można zapisać danych.",
  "details": {}
}
```

## Health

### GET `/api/v1/health`

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

## Admin API — grupy zasobów

```text
/games
/games/{gameId}/symbols
/games/{gameId}/rules-versions
/rules-versions/{rulesVersionId}/symbols/{symbolId}
/rules-versions/{rulesVersionId}/paylines
/rules-versions/{rulesVersionId}/payout-rules
/games/{gameId}/dataset-versions
/dataset-versions/{datasetVersionId}/layouts
/jobs
/import-jobs
/review-items
/mobile-releases
```

Pełne schematy CRUD powstają razem z pionem funkcjonalnym i są generowane do OpenAPI. Poniżej zapisano kontrakty o znaczeniu architektonicznym.

## Games i symbols

Operacje gier:

```text
GET    /api/v1/admin/games
POST   /api/v1/admin/games
GET    /api/v1/admin/games/{gameId}
PATCH  /api/v1/admin/games/{gameId}
DELETE /api/v1/admin/games/{gameId}
```

Tworzenie gry przyjmuje stabilny `code`, `name` i opcjonalny `status`
`draft | active | archived`. Aktualizacja nie przyjmuje kodu, ponieważ kod jest
tożsamością domenową. `DELETE` jest idempotentną archiwizacją i zwraca `204`;
rekord pozostaje w bazie.

Operacje symboli:

```text
GET    /api/v1/admin/games/{gameId}/symbols
POST   /api/v1/admin/games/{gameId}/symbols
GET    /api/v1/admin/games/{gameId}/symbols/{symbolId}
PATCH  /api/v1/admin/games/{gameId}/symbols/{symbolId}
DELETE /api/v1/admin/games/{gameId}/symbols/{symbolId}
```

Tworzenie symbolu przyjmuje `mobileCode`, stabilny `code`, `name`, opcjonalny
`imagePath`, `isWildcard`, `displayOrder` oraz `status`. `mobileCode` i `code`
nie są edytowalne. `imagePath` jest względną ścieżką metadanych, nie zawartością
binarną. Lista jest deterministycznie uporządkowana po `displayOrder`,
`mobileCode` i technicznym UUID. `DELETE` ustawia `status = archived`.

Stabilne konflikty i brak zasobu:

```text
GAME_NOT_FOUND
SYMBOL_NOT_FOUND
GAME_CODE_ALREADY_EXISTS
SYMBOL_CODE_ALREADY_EXISTS
SYMBOL_MOBILE_CODE_ALREADY_EXISTS
VALIDATION_ERROR
```

Konflikty unikalności zwracają `409`, brak zasobu `404`, a walidacja `422`.
Każda odpowiedź błędu ma wspólny kontrakt `code`, `message`, `details`.

## Rules versions

Operacje wersji reguł:

```text
GET   /api/v1/admin/games/{gameId}/rules-versions
POST  /api/v1/admin/games/{gameId}/rules-versions
GET   /api/v1/admin/rules-versions/{rulesVersionId}
PATCH /api/v1/admin/rules-versions/{rulesVersionId}
DELETE /api/v1/admin/rules-versions/{rulesVersionId}
GET   /api/v1/admin/rules-versions/{rulesVersionId}/publication-readiness
POST  /api/v1/admin/rules-versions/{rulesVersionId}/publish
```

Tworzenie przyjmuje dodatnie `rows`, dodatnie `columns` i nieujemny całkowity
`spinCost`. API nie przyjmuje numeru ani statusu: blokuje rekord gry, przydziela
`max(version) + 1` i tworzy `draft`. Lista jest uporządkowana malejąco po
numerze wersji. Odpowiedź zawiera:

```json
{
  "id": "uuid",
  "gameId": "uuid",
  "version": 1,
  "rows": 3,
  "columns": 5,
  "spinCost": 10,
  "status": "draft",
  "createdAt": "2026-07-27T12:00:00Z",
  "publishedAt": null
}
```

`PATCH` przyjmuje co najmniej jedno z pól `rows`, `columns`, `spinCost` i
działa wyłącznie dla statusu `draft`.

GET `publication-readiness` jest operacją read-only i zwraca pełny,
deterministycznie uporządkowany raport:

```json
{
  "rulesVersionId": "uuid",
  "ready": false,
  "issues": [
    {
      "code": "INCOMPLETE_PAYOUT_RULES",
      "message": "An ordinary symbol needs a payout for every supported length.",
      "details": {
        "symbolId": "uuid",
        "missingMatchLengths": [4, 5]
      }
    }
  ]
}
```

Gotowość wymaga co najmniej jednej aktywnej payline, jednej aktywnej
konfiguracji zwykłego symbolu oraz kompletnej, ściśle rosnącej macierzy
aktywnych payoutów od `minimumMatchLength` do `columns`. Aktywny payout jokera,
nieaktywnego symbolu albo długości poza zakresem blokuje publikację.

POST `publish` blokuje rekord wersji, ponownie wykonuje tę samą walidację i w
jednej transakcji ustawia `status = published` oraz serwerowy `publishedAt`.
Niepowodzenie zwraca `RULES_VERSION_NOT_READY` wraz z listą `issues` i nie
zmienia stanu. Ponowne wywołanie dla wersji innej niż draft zwraca
`RULES_VERSION_IMMUTABLE`.

DELETE jest idempotentną archiwizacją `published → archived`, zachowuje
`publishedAt` i zwraca `204`. Draft nie może zostać zarchiwizowany tą operacją.
Publikacja nie archiwizuje automatycznie wcześniejszej opublikowanej wersji tej
samej gry.

Stabilne błędy:

```text
GAME_NOT_FOUND
RULES_VERSION_NOT_FOUND
RULES_VERSION_IMMUTABLE
RULES_VERSION_NOT_READY
RULES_VERSION_NOT_PUBLISHED
VALIDATION_ERROR
```

Brak zasobu zwraca `404`, próba zmiany wersji innej niż draft `409`, a błędne
wymiary lub koszt `422`.

## Payline

Operacje paylines:

```text
GET    /api/v1/admin/rules-versions/{rulesVersionId}/paylines
POST   /api/v1/admin/rules-versions/{rulesVersionId}/paylines
GET    /api/v1/admin/rules-versions/{rulesVersionId}/paylines/{paylineId}
PATCH  /api/v1/admin/rules-versions/{rulesVersionId}/paylines/{paylineId}
DELETE /api/v1/admin/rules-versions/{rulesVersionId}/paylines/{paylineId}
```

### POST `/api/v1/admin/rules-versions/{rulesVersionId}/paylines`

API przyjmuje indeksy wierszy 0-based. Admin UI odpowiada za prezentację 1-based.

```json
{
  "code": "line-v",
  "name": "V",
  "rowPath": [0, 1, 2, 1, 0],
  "displayOrder": 10,
  "isActive": true
}
```

Walidacja:

- długość dokładnie równa liczbie kolumn,
- każda wartość wskazuje istniejący wiersz,
- brak zduplikowanego `rowPath` w wersji.

Lista jest uporządkowana po `displayOrder`, stabilnym `code` i UUID. PATCH nie
przyjmuje `code`, ale pozwala zmienić `name`, `rowPath`, `displayOrder` oraz
`isActive` wyłącznie w drafcie. DELETE jest idempotentną archiwizacją
`isActive = false`; nie zwalnia kodu ani `rowPath`. GET pozostaje dostępny dla
każdego statusu wersji.

Zmiana liczby kolumn draftu z istniejącą payline zwraca
`RULES_DIMENSIONS_IN_USE`. Zmniejszenie liczby rzędów zwraca ten sam konflikt,
jeżeli co najmniej jeden zapisany indeks przestałby istnieć.

Przykład błędu:

```json
{
  "code": "DUPLICATE_PAYLINE",
  "message": "Taki wzór już istnieje.",
  "details": {
    "existingPaylineId": "uuid"
  }
}
```

Pozostałe stabilne błędy:

```text
PAYLINE_NOT_FOUND
PAYLINE_CODE_ALREADY_EXISTS
RULES_VERSION_NOT_FOUND
RULES_VERSION_IMMUTABLE
RULES_DIMENSIONS_IN_USE
VALIDATION_ERROR
```

## Payout rule

### GET `/api/v1/admin/rules-versions/{rulesVersionId}/symbols`

Zwraca utrwalone konfiguracje symboli wersji w kanonicznej kolejności symboli.
Brakujący zwykły symbol jest prezentowany przez panel z domyślnym minimum 3,
ale staje się częścią wersjonowanej konfiguracji dopiero po zapisie.

### PATCH `/api/v1/admin/rules-versions/{rulesVersionId}/symbols/{symbolId}`

```json
{
  "minimumMatchLength": 2
}
```

API ustawia wersjonowany próg zwykłego symbolu. Domyślna wartość wynosi 3, a
dozwolony zakres to `2..columns`. Joker nie przyjmuje tego pola. Zmiana progu w
opublikowanej wersji jest zabroniona; w drafcie zmienia zestaw wymaganych
payout rules.

Payload zawiera również opcjonalne `isActive` z wartością domyślną `true`.
Pierwszy PATCH wykonuje upsert. Joker wymaga `minimumMatchLength = null`.
Podniesienie progu archiwizuje istniejące payout rules poniżej nowego minimum.

### GET `/api/v1/admin/rules-versions/{rulesVersionId}/payout-rules`

Zwraca aktywne i zarchiwizowane rekordy deterministycznie według symbolu i
długości.

### POST `/api/v1/admin/rules-versions/{rulesVersionId}/payout-rules`

```json
{
  "symbolId": "uuid",
  "matchLength": 3,
  "payoutCredits": 100
}
```

API blokuje:

- regułę jokera,
- długość poniżej `minimumMatchLength` symbolu lub większą niż liczba kolumn,
- ujemną wypłatę,
- duplikat `(rulesVersionId, symbolId, matchLength)`.

Operacje pojedynczego rekordu:

```text
GET    /api/v1/admin/rules-versions/{rulesVersionId}/payout-rules/{payoutRuleId}
PATCH  /api/v1/admin/rules-versions/{rulesVersionId}/payout-rules/{payoutRuleId}
DELETE /api/v1/admin/rules-versions/{rulesVersionId}/payout-rules/{payoutRuleId}
```

PATCH zmienia `payoutCredits` lub `isActive`. DELETE jest idempotentną
archiwizacją; rekord pozostaje zarezerwowany, a PATCH może go reaktywować.
Mutacje wersji innej niż draft zwracają `RULES_VERSION_IMMUTABLE`.

Stabilne błędy tego pionu:

```text
SYMBOL_NOT_FOUND
SYMBOL_NOT_IN_RULES_GAME
SYMBOL_RULES_IDENTITY_IN_USE
RULES_SYMBOL_NOT_CONFIGURED
WILDCARD_MINIMUM_NOT_ALLOWED
WILDCARD_PAYOUT_NOT_ALLOWED
INVALID_MINIMUM_MATCH_LENGTH
INVALID_PAYOUT_MATCH_LENGTH
INVALID_PAYOUT_CREDITS
PAYOUT_RULE_NOT_FOUND
PAYOUT_RULE_ALREADY_EXISTS
```

Publikacja wymaga dokładnie jednej wartości kredytów dla każdej długości od
`minimumMatchLength` do liczby kolumn i ściśle rosnących wartości dla danego
symbolu.

## Dataset validation

### Dataset staging

```text
GET  /api/v1/admin/games/{gameId}/dataset-versions
POST /api/v1/admin/games/{gameId}/dataset-versions/mock
GET  /api/v1/admin/dataset-versions/{datasetVersionId}
```

POST tworzy ograniczony mock administracyjny:

```json
{
  "rulesVersionId": "uuid",
  "seed": 71401
}
```

Wskazana wersja reguł musi być opublikowana, należeć do gry i zawierać co
najmniej dwa aktywne symbole. Jej wymiary oraz aktywne konfiguracje symboli
definiują planszę i alfabet generatora. Odpowiedź `201` zawiera staging:

```json
{
  "id": "uuid",
  "gameId": "uuid",
  "version": 1,
  "rows": 3,
  "columns": 5,
  "signatureCellWidth": 2,
  "layoutCount": 1000,
  "status": "staging",
  "generationSeed": 71401,
  "generatorVersion": "mock-v1",
  "sourceJobId": null,
  "createdAt": "2026-07-27T12:00:00Z",
  "publishedAt": null
}
```

Numer wersji przydziela serwer pod blokadą rekordu gry. Wersja i dokładnie 1000
layoutów zapisują się w jednej transakcji. Sześć ostatnich layoutów powtarza
kontrolowane treści wcześniejszych rekordów, ale każdy `sequenceNumber` w
zakresie `1..1000` pozostaje unikalny. Stabilne błędy:

```text
GAME_NOT_FOUND
RULES_VERSION_NOT_FOUND
RULES_VERSION_NOT_PUBLISHED
INSUFFICIENT_ACTIVE_SYMBOLS
INSUFFICIENT_LAYOUT_VARIANTS
INVALID_DATASET_DIMENSIONS
INVALID_GENERATION_SEED
DATASET_VERSION_NOT_FOUND
DATASET_STAGING_CONFLICT
```

Endpoint jest celowo ograniczony do mocka 1000 rekordów. Docelowa generacja
setek tysięcy layoutów nie odbywa się w requestcie HTTP. Generator mocka
akceptuje planszę o rozmiarze od 1 do 100 komórek; większy układ zwraca
`INVALID_DATASET_DIMENSIONS`.

### GET `/api/v1/admin/dataset-versions/{datasetVersionId}/validation-report`

Bounded dataset `mock-v1` jest sprawdzany synchronicznie tym samym
deterministycznym walidatorem, którego użyje publikacja:

```json
{
  "datasetVersionId": "uuid",
  "datasetVersion": 1,
  "readyForPublication": true,
  "declaredLayoutCount": 1000,
  "actualLayoutCount": 1000,
  "minSequenceNumber": 1,
  "maxSequenceNumber": 1000,
  "checks": [
    {
      "code": "MISSING_SEQUENCE_NUMBER",
      "status": "passed",
      "issueCount": 0,
      "message": "No sequence numbers are missing.",
      "sequenceNumbers": [],
      "mobileCodes": [],
      "truncated": false
    },
    {
      "code": "DUPLICATE_SIGNATURE",
      "status": "warning",
      "issueCount": 6,
      "message": "Duplicate layout signatures are allowed and were found.",
      "sequenceNumbers": [],
      "mobileCodes": [],
      "truncated": false
    }
  ],
  "duplicateSignatureGroupCount": 6,
  "duplicateSignatureAffectedLayoutCount": 12,
  "duplicateSignatureExcessLayoutCount": 6,
  "duplicateSignatures": [
    {
      "signature": "0102...",
      "occurrenceCount": 2,
      "sequenceNumbers": [101, 995],
      "truncated": false
    }
  ],
  "duplicateSignaturesTruncated": false
}
```

Checki mają stabilną kolejność i kody:

```text
LAYOUT_COUNT_MISMATCH
MISSING_SEQUENCE_NUMBER
OUT_OF_RANGE_SEQUENCE_NUMBER
DUPLICATE_SEQUENCE_NUMBER
INVALID_CELL_COUNT
FOREIGN_SYMBOL
SIGNATURE_MISMATCH
DUPLICATE_SIGNATURE
```

Pierwsze siedem kodów ma status `blocking`, gdy wykryją problem. Duplikat
sygnatury ma status `warning` i nie zmienia `readyForPublication` na `false`.
Dokładne liczniki obejmują cały dataset, a listy diagnostyczne są
deterministycznie ograniczone do pierwszych 100 elementów; `truncated`
informuje o obcięciu próbki.

Endpoint działa wyłącznie dla obecnego bounded `mock-v1`. Inny generator zwraca
`409 DATASET_VALIDATION_REQUIRES_JOB`. Docelowy
`POST /dataset-versions/{datasetVersionId}/validation-jobs` pozostaje
kontraktem dla importów i dużych datasetów wykonywanym przez worker; nie jest
częścią OpenAPI TASK-0026.

### Dataset preview

```text
GET /api/v1/admin/dataset-versions/{datasetVersionId}/layouts
    ?after_sequence_number=0&limit=25
```

`after_sequence_number` ma minimum `0`, a `limit` zakres `1..100`. Endpoint
używa keyset pagination i zwraca rekordy rosnąco po domenowym
`sequenceNumber`. `nextAfterSequenceNumber` jest numerem ostatniego rekordu
bieżącej strony tylko wtedy, gdy istnieje następna strona; w przeciwnym razie
ma wartość `null`.

```json
{
  "datasetVersionId": "uuid",
  "datasetVersion": 1,
  "rows": 3,
  "columns": 5,
  "items": [
    {
      "sequenceNumber": 1,
      "signature": "0102...",
      "cells": [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1],
      "sourceBoardId": null
    }
  ],
  "nextAfterSequenceNumber": 25
}
```

### Dataset publication

```text
POST   /api/v1/admin/dataset-versions/{datasetVersionId}/publish
DELETE /api/v1/admin/dataset-versions/{datasetVersionId}
```

POST blokuje rekord `dataset_versions`, wymaga statusu `staging`, uruchamia
ponownie ten sam walidator co raport i atomowo ustawia `published` oraz
serwerowy `publishedAt`. Ostrzeżenie `DUPLICATE_SIGNATURE` nie blokuje
publikacji. Każda blokada zwraca `409 DATASET_VERSION_NOT_READY` z listą
problemów, bez zmiany statusu i timestampu. Stabilne błędy lifecycle:

```text
DATASET_VERSION_NOT_FOUND
DATASET_VERSION_NOT_STAGING
DATASET_VERSION_NOT_READY
DATASET_PUBLICATION_REQUIRES_JOB
DATASET_VERSION_NOT_PUBLISHED
```

DELETE jest idempotentną archiwizacją wersji opublikowanej i zwraca `204`.
Zachowuje `publishedAt` i wszystkie layouty. Wersji stagingowej nie archiwizuje
ten endpoint; odrzucanie importu pozostaje osobną operacją workflow importu.

## Job status

### POST `/api/v1/admin/jobs`

Zapisuje zadanie do późniejszego wykonania przez worker i zwraca `201`. Request
jest dyskryminowany przez `jobType`; każdy `inputPayload` ma
`schemaVersion: 1`.

```json
{
  "jobType": "payout",
  "gameId": "uuid",
  "inputPayload": {
    "schemaVersion": 1,
    "datasetVersionId": "uuid",
    "rulesVersionId": "uuid",
    "algorithmVersion": "payout-v2"
  }
}
```

Typowane payloady:

- `import`: `sourcePath`, `pipelineVersion`,
- `validate`: `datasetVersionId`,
- `payout`: `datasetVersionId`, `rulesVersionId`, `algorithmVersion`,
- `snapshot`: `mobileReleaseId`,
- `android_build`: `mobileReleaseId`.

Powtórzenie identycznego typu, gry i payloadu zwraca
`409 JOB_INPUT_ALREADY_EXISTS` z `existingJobId`. API nie wykonuje workflow
w requestcie.

### GET `/api/v1/admin/jobs`

Zwraca najwyżej 200 najnowszych rekordów. Obsługuje filtry `status`,
`job_type`, `game_id` oraz bounded `limit`, domyślnie 50.

### GET `/api/v1/admin/jobs/{jobId}`

```json
{
  "id": "uuid",
  "jobType": "snapshot",
  "gameId": null,
  "status": "processing",
  "inputPayload": {
    "schemaVersion": 1,
    "mobileReleaseId": "uuid"
  },
  "progress": {
    "current": 250000,
    "total": 500000,
    "stage": "writing_layouts",
    "succeeded": 249990,
    "failed": 4,
    "review": 6
  },
  "error": null,
  "workerVersion": "worker-v1",
  "createdAt": "2026-07-24T10:00:00Z",
  "updatedAt": "2026-07-24T10:03:00Z",
  "startedAt": "2026-07-24T10:00:03Z",
  "finishedAt": null,
  "cancelRequestedAt": null
}
```

### POST `/api/v1/admin/jobs/{jobId}/cancel`

`created` i `waiting_for_review` przechodzą od razu do `cancelled`. Dla
`processing` endpoint tylko ustawia `cancelRequestedAt`; worker zatrzymuje się
w bezpiecznym punkcie i dopiero wtedy zapisuje `cancelled`. Powtórzenie dla
`cancelled` jest idempotentne. `completed` i `failed` zwracają
`409 JOB_NOT_CANCELLABLE`.

Wspólny automat:

```text
created -> processing -> completed
                    \-> failed
                    \-> waiting_for_review -> created
created/waiting_for_review -> cancelled
processing + cancelRequestedAt -> cancelled (worker safe point)
```

`stage` nie zmienia automatu. Błędne przejście ma kod
`INVALID_JOB_STATUS_TRANSITION`.

## Mobile release

### POST `/api/v1/admin/mobile-releases`

```json
{
  "version": "m1.0.1",
  "games": [
    {
      "gameId": "uuid",
      "datasetVersionId": "uuid",
      "rulesVersionId": "uuid"
    }
  ]
}
```

Response:

```json
{
  "releaseId": "uuid",
  "status": "draft"
}
```

### POST `/api/v1/admin/mobile-releases/{releaseId}/build`

Uruchamia jeden workflow:

1. walidacja wersji,
2. precomputing brakujących payoutów,
3. generowanie i weryfikacja SQLite,
4. lokalny Android build,
5. zapis checksum.

Response:

```json
{
  "jobId": "uuid",
  "status": "created"
}
```

### GET `/api/v1/admin/mobile-releases/{releaseId}`

```json
{
  "id": "uuid",
  "version": "m1.0.1",
  "status": "ready",
  "algorithmVersion": "payout-v2",
  "snapshot": {
    "schemaVersion": 2,
    "relativePath": "releases/m1.0.1/data.sqlite",
    "checksum": "sha256:..."
  },
  "apk": {
    "relativePath": "releases/m1.0.1/app-m1.0.1.apk",
    "checksum": "sha256:..."
  },
  "games": [
    {
      "gameCode": "game-1",
      "datasetVersion": 1,
      "rulesVersion": 1,
      "layoutCount": 500000
    }
  ]
}
```

API zwraca ścieżkę do lokalnego artefaktu, ale nie instaluje APK na telefonie.

## Kontrakt snapshotu mobilnego

Schemat SQLite znajduje się w `DATA_MODEL.md`. Przy starcie mobile waliduje:

- obsługiwaną `snapshot_schema_version`,
- obecność wersji wydania,
- zgodność liczby gier i layoutów z manifestem,
- checksumę, jeżeli sposób pakowania pozwala ją bezpiecznie zweryfikować.

Niekompatybilny snapshot powoduje stan `local_data_error`, a nie próbę połączenia z API.

## Kontrakty domenowe mobile

Typy są utrzymywane w TypeScript, ponieważ nie są odpowiedziami HTTP. Muszą odpowiadać testowanym portom domenowym i schematowi SQLite.

```ts
type MatchResult =
  | { status: "partial"; candidateCount: number }
  | {
      status: "unique_candidate";
      candidateCount: 1;
      proposal: {
        sequenceNumber: number;
        cells: readonly number[];
      };
    }
  | {
      status: "unique";
      sequenceNumber: number;
    }
  | {
      status: "duplicate";
      candidateCount: number;
      sequenceNumbers: readonly number[];
      listTruncated: boolean;
    }
  | { status: "not_found" }
  | { status: "local_data_error"; code: string };
```

Nie istnieje `confirmationToken`, `confirm-next` ani stan zachowany między resetami.

```ts
type PositiveLocalPeak = {
  spinNumber: number;
  sequenceNumber: number;
  spinPayout: number;
  cumulativePayout: number;
  cumulativeCost: number;
  netCredits: number;
};

type ForecastResult = {
  startSequenceNumber: number;
  evaluatedSpinCount: number;
  spinCost: number;
  finalCumulativePayout: number;
  finalCumulativeCost: number;
  finalNetCredits: number;
  positiveLocalPeaks: readonly PositiveLocalPeak[];
  mobileReleaseVersion: string;
  snapshotChecksum: string;
  datasetVersion: number;
  rulesVersion: number;
  algorithmVersion: string;
};
```

Nie występują pola `limit`, `firstPositive`, `highWaterMarks` ani `stopReason`. Poprawny wynik zawsze obejmuje `layoutCount - 1` spinów; przerwanie lub błąd integralności nie jest częściowym wynikiem końcowym.

## Zasady kontraktów

- UUID są technicznymi identyfikatorami Admin API; `sequenceNumber` pozostaje wartością domenową.
- Kredyty i payouty są liczbami całkowitymi.
- Daty Admin API są ISO 8601 UTC.
- JSON używa camelCase; Python może używać snake_case wewnętrznie.
- Wszystkie Admin API response i error schemas są w OpenAPI.
- Klient TypeScript panelu jest generowany, nie przepisywany ręcznie.
- Mobile nie współdzieli ręcznie skopiowanych typów odpowiedzi Admin API.
- Zmiana schematu PostgreSQL odbywa się tylko przez migrację Alembic.
- Zmiana schematu snapshotu zwiększa `snapshot_schema_version` i wymaga testu kompatybilności mobile.

## Generowany klient panelu

Backend FastAPI jest jedynym źródłem kontraktu HTTP. Deterministyczny eksport
OpenAPI 3.1 znajduje się w
`packages/admin-api-client/openapi/openapi.json`, a klient Fetch i typy
TypeScript są generowane do `packages/admin-api-client/src/generated/`.

Każda operacja ma stabilny `operationId`. Panel importuje prywatny workspace
`@game-predictor/admin-api-client` i nie deklaruje ręcznie typów odpowiedzi.
Kontrola jakości porównuje jednocześnie aktualny OpenAPI backendu, zapisany JSON
i ponownie wygenerowany kod:

```powershell
npm run openapi:generate
npm run openapi:check
```

Generowanie nie wymaga uruchomionego API ani połączenia sieciowego. Klient
pozostaje wyłącznie zależnością panelu; mobile nie importuje tego workspace.
