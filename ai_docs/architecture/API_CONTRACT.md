---
title: Admin API and mobile data contracts
status: accepted
last_updated: 2026-08-02
---

# Kontrakty API i danych mobilnych

## Granica systemu

HTTP API służy wyłącznie lokalnemu panelowi administracyjnemu. Aplikacja Android nie wywołuje żadnego endpointu i nie potrzebuje serwera do matching ani Target.

Prefix Admin API:

```text
/api/v1/admin
```

Każda mutacja pod tym prefiksem wymaga mechanizmu OpenAPI
`LocalAdminIntent`, realizowanego nagłówkiem
`X-Admin-Intent: local-owner`. Operacje wysokiego wpływu wymagają ponadto
`X-Admin-Confirmation: confirmed` oraz `X-Admin-Target` zgodnego z dokładnym
celem w ścieżce lub stałym celem operacji. Brak loopback, obcy `Origin`, brak
intencji albo niezgodny cel zwracają stabilne kody odpowiednio
`ADMIN_LOOPBACK_REQUIRED`, `ADMIN_ORIGIN_FORBIDDEN`, `ADMIN_INTENT_REQUIRED`
lub `ADMIN_CONFIRMATION_REQUIRED` bez wykonania domenowej mutacji.

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
/image-selections
/image-imports
/import-jobs
/layout-import-validations
/review-batches
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

Tworzenie symbolu przyjmuje `mobileCode`, stabilny `code`, wymagany fallback
`name`, opcjonalne etykiety `namePl` i `nameEn`, `imagePath`, `isWildcard`,
`displayOrder` oraz `status`. `mobileCode` i `code`
nie są edytowalne. `imagePath` jest względną ścieżką metadanych, nie zawartością
binarną. Lista jest deterministycznie uporządkowana po `displayOrder`,
`mobileCode` i technicznym UUID. `DELETE` ustawia `status = archived`.
Puste po trimowaniu etykiety lokalizowane są odrzucane. W `PATCH` pominięte
pole zachowuje poprzednią wartość, natomiast jawne `null` usuwa etykietę.

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
POST  /api/v1/admin/rules-versions/{rulesVersionId}/draft
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

POST `/draft` rozpoczyna edycję opublikowanej konfiguracji. Jeśli gra ma już
draft, operacja zwraca najnowszy istniejący draft i nie tworzy kolejnej wersji.
W przeciwnym razie tworzy `max(version) + 1` oraz kopiuje w jednej transakcji:

- wymiary i koszt spinu,
- wszystkie paylines wraz ze stanem aktywności,
- konfiguracje symboli,
- payout rules wraz ze stanem aktywności.

Kopiowane rekordy podrzędne otrzymują nowe identyfikatory, a opublikowane źródło
pozostaje niezmienne. Wywołanie dla draftu zwraca ten draft. Wersja
zarchiwizowana nie może być źródłem i zwraca `RULES_VERSION_NOT_PUBLISHED`.
Główny workspace Admina wybiera najnowszy draft, a przy jego braku najnowszą
opublikowaną wersję; techniczna historia nie jest częścią tego widoku.

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

## Selekcja reprezentatywnych zdjęć M7.0

Nowy kontrakt jest game-scoped i korzysta z browser selection poświadczonego
purpose `photo_selection`. Nie przyjmuje ścieżki absolutnej użytkownika.

```text
POST /api/v1/admin/image-selections
GET  /api/v1/admin/image-selections/{runId}
GET  /api/v1/admin/image-selections/{runId}/groups
```

TASK-0151 zamraża pierwsze trzy endpointy. POST przyjmuje:

```json
{
  "gameId": "uuid",
  "sourceSelectionId": "uuid",
  "inputManifestSha256": "64 lowercase hex",
  "selectorFingerprint": "64 lowercase hex",
  "contractVersion": 1
}
```

Odpowiedź zawiera `run` wraz z typowanym jobem `image_selection` oraz
`created`. Idempotency key to
`(gameId, inputManifestSha256, selectorFingerprint)`, dlatego ponowienie zwraca
ten sam run z `created = false`. `orderingPolicy` jest ustawiane wyłącznie przez
serwer na `natural_relative_path_v1`. W TASK-0151 `sourceSelectionId` jest tylko
trwałą referencją; TASK-0152 wiąże ją z finalizowanym browser stagingiem i
egzekwuje purpose `photo_selection`, zanim worker uzyska dostęp do plików.

GET runu zwraca lifecycle przez zagnieżdżony `job`. GET grup przyjmuje opcjonalny
`status`, kursor `afterGroupOrder` (domyślnie `-1`) i `limit` 1–100 (domyślnie
25). Odpowiedź ma `items` oraz opcjonalny `nextAfterGroupOrder`. Endpoint nie
zwraca pełnej listy kandydatów.

Aktualny kontrakt tworzenia runu v10.4 wymaga również dodatniego pola
`firstSequenceNumber`. Historyczne rekordy odpowiedzi zachowują pole nullable,
ponieważ runy v9–v10.3 mogły powstać bez kotwicy. Ponowne użycie istniejącego
stagingu ma endpoint:

```text
POST /api/v1/admin/image-selections/{runId}/rerun
```

Opcjonalne body `{ "firstSequenceNumber": 7300 }` nadpisuje lub uzupełnia
kotwicę źródłowego runu. Dla selektora v10.4 brak wartości zarówno w body, jak i
w źródłowym runie zwraca `IMAGE_SELECTION_FIRST_SEQUENCE_REQUIRED`; nie powstaje
job. Dla historycznego fingerprintu nullable pozostaje dozwolone.

Stabilne błędy dostarczone w TASK-0151:

```text
GAME_NOT_FOUND
IMAGE_SELECTION_NOT_FOUND
IMAGE_SELECTION_CONFIGURATION_INVALID
IMAGE_SELECTION_RANGE_INVALID
IMAGE_SELECTION_PATH_UNSAFE
IMAGE_SELECTION_PERSISTENCE_CONFLICT
```

TASK-0154–0155 rozszerzają kontrakt o:

```text
PUT  /api/v1/admin/image-selections/{runId}/groups/{groupId}/manual-file
GET  /api/v1/admin/image-selections/{runId}/groups/{groupId}/manual-files/{candidateId}
POST /api/v1/admin/image-selections/{runId}/groups/{groupId}/approve
POST /api/v1/admin/image-selections/{runId}/groups/{groupId}/discard-duplicate
POST /api/v1/admin/image-selections/{runId}/handoff
```

`PUT .../manual-file` przyjmuje bajty jednego JPEG-a jako
`application/octet-stream`, a bezpieczna nazwa prezentacyjna trafia w nagłówku
`X-Image-File-Name`. Limit wynosi 50 MB. Odpowiedź zwraca utworzonego albo
odnalezionego po checksumie kandydata. `GET .../manual-files/{candidateId}`
zwraca poświadczony podgląd `image/jpeg` wyłącznie w obrębie runu i grupy.

`POST .../approve` przyjmuje:

```json
{
  "candidateId": "uuid",
  "idempotencyKey": "uuid",
  "rangeStart": 1,
  "rangeEnd": 9
}
```

Zakres jest obowiązkowy i dodatni także wtedy, gdy automat nie ustalił numerów.
Idempotency key powtórzony z identycznym payloadem zwraca tę samą rewizję;
zmiana payloadu pod tym samym kluczem jest konfliktem. Kolejna korekta używa
nowego UUID i tworzy append-only rewizję. Handoff działa wyłącznie dla
kompletnego checksumowanego manifestu i zwraca poświadczone źródło do
istniejącego `POST /image-imports`; nie uruchamia sam ciężkiego pipeline'u.

`POST .../discard-duplicate` używa body `idempotencyKey`, `rangeStart` i
`rangeEnd`. Zwraca ten sam typ co zatwierdzenie manualne, z decyzją
`duplicate_range` i grupą `skipped_existing_range`. API nie wykonuje operacji,
jeżeli inna rozwiązana grupa runu nie ma identycznego zakresu; stabilny kod
błędu to `IMAGE_SELECTION_DUPLICATE_RANGE_NOT_FOUND`.

TASK-0154 zamraża odpowiedź handoffu:

```json
{
  "runId": "uuid",
  "gameId": "uuid",
  "selectionId": "uuid równy runId",
  "selectionToken": "krótkotrwały sekret",
  "supportedFileCount": 123,
  "expiresAt": "2026-08-03T12:15:00Z",
  "targetSection": "imports"
}
```

Przed odpowiedzią API ponownie liczy checksumę kanonicznego manifestu, każdego
JPEG-a, jego rozmiar i wymiary oraz porównuje zakresy z trwałymi grupami runu.
`collecting`, `manual_required`, brak grupy albo rozjazd pliku blokują handoff.
Ponowienie aktywnego handoffu zwraca ten sam token, a logiczne źródło zachowuje
`selectionId = runId`. Panel przechodzi do `Importu layoutów`, lecz dopiero
osobne kliknięcie `Rozpocznij import` konsumuje token i tworzy job.

Manifest outputu `curated-image-selection-output-v2` identyfikuje wpis przez
`groupOrder`, przechowuje oryginalną ścieżkę, checksumy, metryki jakości,
`reasonCodes` i `selectionMethod`. `rangeStart` oraz `rangeEnd` są parą
opcjonalną. Bez zakresu publiczna nazwa ma postać `selection_<groupOrder>.jpg`;
rozpoznany albo historyczny zakres zachowuje `seq_<start>-<end>.jpg`. Endpoint
`GET .../output` zwraca oba warianty, a `GET .../output/{fileName}` ponownie
weryfikuje manifest i JPEG. Verifier nadal czyta niezmienne manifesty v1.

Handoff porównuje wybrane trwałe grupy po `groupOrder` i opcjonalnej parze
zakresu, a nie wymaga zbioru rozpoznanych zakresów. `supportedFileCount` oznacza
liczbę wybranych grup mających JPEG. Import `image_directory` otrzymuje te same
checksumowane pliki; dopiero jego istniejący OCR i geometria ustalają
`sequence_number` oraz wykrywają duplikaty zakresu.

Stabilne rodziny błędów:

```text
IMAGE_SELECTION_SOURCE_PURPOSE_INVALID
IMAGE_SELECTION_GROUP_NOT_FOUND
IMAGE_SELECTION_RANGE_CONFLICT
IMAGE_SELECTION_MANUAL_FILE_INVALID
IMAGE_SELECTION_RANGE_REQUIRED
IMAGE_SELECTION_CANDIDATE_NOT_FOUND
IMAGE_SELECTION_CANDIDATE_MISMATCH
IMAGE_SELECTION_GROUP_NOT_MANUAL
IMAGE_SELECTION_IDEMPOTENCY_CONFLICT
IMAGE_SELECTION_ALREADY_PUBLISHED
IMAGE_SELECTION_MANUAL_FILE_MISSING
IMAGE_SELECTION_MANUAL_FILE_CHANGED
IMAGE_SELECTION_STORAGE_UNAVAILABLE
IMAGE_SELECTION_NOT_READY
IMAGE_SELECTION_MANIFEST_MISMATCH
```

Schematy TASK-0151–0155 są generowane z backendu do klienta.
Dokument architektury `IMAGE_SELECTION.md` definiuje lifecycle oraz
idempotencję.

## Kontrolowany import folderu zdjęć

### POST `/api/v1/admin/image-imports/browser-selections`

Rozpoczyna kontrolowany upload folderu wybranego standardowym selektorem
przeglądarki. Przyjmuje nazwę prezentacyjną katalogu, dokładną liczbę JPEG-ów i
ich łączny rozmiar. Zwraca `uploadId` oraz liczniki postępu. Nie przyjmuje
lokalnej ścieżki bezwzględnej i nie uruchamia procesu systemowego.

### PUT `/api/v1/admin/image-imports/browser-selections/{uploadId}/files/{fileIndex}`

Przesyła jeden plik jako `application/octet-stream`. Nagłówek
`X-Image-Relative-Path` zawiera wyłącznie względną nazwę pochodzącą z wyboru
przeglądarki. API odrzuca traversal, rozszerzenia inne niż JPEG, pustą lub
nieczytelną zawartość, powtórzony indeks i przekroczenie zadeklarowanego
rozmiaru. Odpowiedź zwraca aktualny postęp liczby plików i bajtów.

### POST `/api/v1/admin/image-imports/browser-selections/{uploadId}/finalize`

Finalizacja wymaga dokładnej zgodności przesłanej liczby plików i bajtów.
Zwraca losowy, jednorazowy `selectionToken` ważny 15 minut. Token jest
przechowywany tylko w pamięci API i po restarcie wygasa. Staging znajduje się w
kontrolowanym `import_root/browser-selections`; wygasłe i anulowane wybory są
sprzątane.

### DELETE `/api/v1/admin/image-imports/browser-selections/{uploadId}`

Anuluje upload i usuwa jego kontrolowany staging. Operacja jest idempotentna z
perspektywy klienta.

### POST `/api/v1/admin/image-imports/folder-selection` (legacy)

Starszy loopback-only kontrakt otwierający dialog Windows pozostaje tymczasowo
dla zgodności technicznej. Admin `0.2` go nie wywołuje; głównym kontraktem jest
przeglądarkowy upload opisany wyżej.

### POST `/api/v1/admin/image-imports`

Przyjmuje wyłącznie `gameId` oraz `selectionToken`. Backend ponownie sprawdza
folder, konsumuje token po udanym zapisie i tworzy job `import` z
`importKind = image_directory`, `sourceSelectionId`, zatwierdzonym
`sourceDirectory`, bezpieczną nazwą folderu oraz `pipelineFingerprint`.
Źródło pochodzące z selektora zapisuje dodatkowo `imageSelectionRunId`, dzięki
czemu pełny pipeline zachowuje proweniencję niezmiennego outputu.
Przeglądarka nie może utworzyć image importu przez przesłanie własnej ścieżki.

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

- `image_selection`: `sourceSelectionId`, `inputManifestSha256`,
  `selectorFingerprint`, `contractVersion = 1`,
- `import` request: `sourcePath`, `contractVersion = 1`,
- `validate` datasetu: `datasetVersionId`,
- `validate` layout importu: `validationKind = layout_import`, `importJobId`,
  `rulesVersionId`,
- `payout`: `datasetVersionId`, `rulesVersionId`, `algorithmVersion`,
- `snapshot`: `mobileReleaseId`,
- `android_build`: `mobileReleaseId`.

Payload `image_selection` jest widoczny w odpowiedziach wspólnego monitora
jobów, ale nie może być utworzony przez ogólne `POST /jobs`; enqueue należy do
dedykowanego `POST /image-selections`, a poświadczenie stagingu do TASK-0152.

Dla `payout` API wykonuje wyłącznie szybki preflight i zapis joba; samo
przeliczanie nadal wykonuje worker. Akceptowana jest tylko wersja algorytmu
`payout-v2` oraz dokładna kombinacja:

- opublikowany, niepusty dataset, dla którego `layoutCount` jest równy
  `expectedLayoutCount`,
- opublikowane reguły,
- ta sama gra i identyczne wymiary datasetu oraz reguł.

Niespełnienie warunków nie tworzy joba. Stabilne kody to
`UNSUPPORTED_PAYOUT_ALGORITHM`, `DATASET_VERSION_NOT_FOUND`,
`RULES_VERSION_NOT_FOUND`, `PAYOUT_GAME_MISMATCH`,
`PAYOUT_DATASET_NOT_PUBLISHED`, `PAYOUT_RULES_NOT_PUBLISHED`,
`PAYOUT_DIMENSIONS_MISMATCH`, `PAYOUT_DATASET_EMPTY` oraz
`PAYOUT_DATASET_INCOMPLETE`. Aktywny i ukończony stan jest odczytywany przez
zwykłe endpointy jobów; awaria jest wznawiana przez `POST /jobs/{jobId}/retry`
na tym samym rekordzie i checkpointcie.

Powtórzenie identycznego typu, gry i payloadu zwraca
`409 JOB_INPUT_ALREADY_EXISTS` z `existingJobId`. API nie wykonuje workflow
w requestcie.

### DELETE `/api/v1/admin/jobs/{jobId}`

Trwale usuwa wyłącznie job `image_selection` w statusie `cancelled`. Operacja
wymaga lokalnych nagłówków wysokiego ryzyka z dokładnym celem `job:{jobId}`.
Przed zmianą bazy API blokuje rekord joba i sprawdza jego pojedynczy run.
Zwraca `409`, jeżeli job ma inny typ lub status, run został przekazany do
iteracyjnego importu, ma opublikowany manifest albo nie można bezpiecznie
przenieść zarządzanych artefaktów do kwarantanny.

Usuwane są decyzje manualne, kandydaci, grupy, run i job. Katalog manualny runu
oraz niewspółdzielony browser staging są najpierw atomowo przenoszone do
kwarantanny; rollback bazy przywraca je, a commit kończy fizyczne usunięcie.
Staging używany przez więcej niż jeden run pozostaje. Folder wynikowy wybrany
przez użytkownika w przeglądarce nie jest częścią zarządzanego storage i nigdy
nie jest usuwany.

Odpowiedź zawiera `jobId`, `runId`, `managedRunFilesDeleted`,
`sourceStagingDeleted` oraz `sharedSourceStagingPreserved`.

Dla `import` klient wskazuje wyłącznie względny POSIX `sourcePath` pod
`GAME_PREDICTOR_IMPORT_ROOT`. Nie może przekazać ścieżki absolutnej, formatu,
rozmiaru ani checksumy. API przed utworzeniem joba:

1. rozwiązuje ścieżkę bez możliwości wyjścia poza skonfigurowany katalog,
2. wymaga zwykłego, niepustego `.csv` albo `.jsonl` w limicie bajtów,
3. sprawdza nagłówek i pierwszy rekord `layout-import-v1`,
4. liczy SHA-256 strumieniowo i odrzuca zmianę pliku podczas odczytu.

Utrwalony i zwracany `inputPayload` importu ma postać:

```json
{
  "schemaVersion": 1,
  "importKind": "layout_file",
  "sourcePath": "game-1/layouts.csv",
  "sourceChecksum": "pełny-mały-hex-sha256",
  "sourceSizeBytes": 123456,
  "fileFormat": "csv",
  "contractVersion": 1
}
```

`input_key` dla layout importu obejmuje grę, checksum, format i wersję kontraktu,
ale nie nazwę pliku. Identyczne bajty pod inną nazwą nadal zwracają
`JOB_INPUT_ALREADY_EXISTS`. Błędy ścieżki/formatu/rozmiaru mają stabilne kody
`INVALID_IMPORT_SOURCE_PATH`, `IMPORT_SOURCE_NOT_FOUND`,
`IMPORT_SOURCE_NOT_FILE`, `IMPORT_SOURCE_FORMAT_UNSUPPORTED`,
`IMPORT_SOURCE_EMPTY`, `IMPORT_SOURCE_TOO_LARGE` i
`IMPORT_SOURCE_CHANGED`. Błąd preview zachowuje kod TASK-0043 oraz
`details.lineNumber`.

Po przejęciu joba worker używa istniejących publicznych pól postępu:

- `stage = staging_import_rows` podczas odczytu i `staged_import_rows` po
  końcowej rewalidacji,
- `progress.current/total` oznacza przetworzone i wszystkie bajty
  poświadczonego źródła,
- `progress.succeeded/failed` oznacza parserowo poprawne i błędne niepuste
  rekordy,
- `progress.review = 0`; walidacja domenowa i review nie należą do TASK-0045.

Wewnętrzny checkpoint, offset, numer linii i `prefix_chain` nie są zwracane
przez API. `completed` oznacza zakończony surowy staging, a nie gotowy lub
opublikowany dataset. Wiersze z błędem są zachowywane do dalszego raportowania
i nie zatrzymują odczytu kolejnych rekordów.

Walidacja zakończonego surowego importu używa:

```json
{
  "jobType": "validate",
  "gameId": "uuid",
  "inputPayload": {
    "schemaVersion": 1,
    "validationKind": "layout_import",
    "importJobId": "uuid",
    "rulesVersionId": "uuid"
  }
}
```

Import musi mieć status `completed`, a reguły status `published`; oba zasoby
muszą należeć do `gameId`. Stabilne błędy utworzenia to
`LAYOUT_IMPORT_JOB_NOT_FOUND`, `LAYOUT_IMPORT_NOT_COMPLETED`,
`LAYOUT_IMPORT_GAME_MISMATCH`, `RULES_VERSION_NOT_FOUND`,
`RULES_VERSION_NOT_PUBLISHED` i `LAYOUT_IMPORT_RULES_GAME_MISMATCH`.

Dla tego wariantu `progress.current/total` oznacza zwalidowane i wszystkie
surowe niepuste rekordy, `succeeded/failed` — końcowe poprawne i błędne wiersze,
a `stage` przyjmuje `validating_import_rows` lub `validated_import_rows`.
Powtórzenie tej samej pary import/reguły zwraca `JOB_INPUT_ALREADY_EXISTS`.

## Raport znormalizowanego importu layoutów

### GET `/api/v1/admin/layout-import-validations/{validationJobId}/integrity-report`

Endpoint działa wyłącznie dla zakończonego joba `validate` z
`validationKind = layout_import`. Zwraca dokładne agregaty pełnego stagingu i
bounded diagnostykę:

```json
{
  "validationJobId": "uuid",
  "importJobId": "uuid",
  "rulesVersionId": "uuid",
  "rows": 3,
  "columns": 5,
  "readyForPublication": false,
  "expectedRowCount": 500000,
  "actualRowCount": 500000,
  "validRowCount": 499998,
  "invalidRowCount": 2,
  "minSequenceNumber": 1,
  "maxSequenceNumber": 500000,
  "uniqueSequenceCount": 499997,
  "missingSequenceCount": 3,
  "missingSequenceNumbers": [25, 26, 300],
  "missingSequenceNumbersTruncated": false,
  "duplicateSequenceGroupCount": 1,
  "duplicateSequenceAffectedRowCount": 2,
  "duplicateSequenceExcessRowCount": 1,
  "duplicateSequences": [
    {
      "sequenceNumber": 20,
      "occurrenceCount": 2,
      "lineNumbers": [20, 21],
      "truncated": false
    }
  ],
  "duplicateSequencesTruncated": false,
  "duplicateSignatureGroupCount": 1,
  "duplicateSignatureAffectedRowCount": 2,
  "duplicateSignatureExcessRowCount": 1,
  "duplicateSignatures": [
    {
      "signature": "0102...",
      "occurrenceCount": 2,
      "sequenceNumbers": [100, 200],
      "lineNumbers": [100, 200],
      "sequenceNumbersTruncated": false,
      "lineNumbersTruncated": false
    }
  ],
  "duplicateSignaturesTruncated": false,
  "errorCodeCounts": [
    {
      "code": "import_symbol_not_in_rules",
      "count": 2
    }
  ]
}
```

`checks` ma stabilną kolejność i kody:

```text
NORMALIZED_ROW_COUNT_MISMATCH
NO_VALID_IMPORT_ROWS
INVALID_IMPORT_ROW
MISSING_SEQUENCE_NUMBER
DUPLICATE_SEQUENCE_NUMBER
DUPLICATE_SIGNATURE
```

Pierwsze pięć kodów ma status `blocking`, gdy wykryją problem. Duplikat
sygnatury ma status `warning`. Wiersze błędne nie wypełniają pozycji ciągu
poprawnych layoutów. Liczniki są dokładne; próbki zawierają najwyżej 100 grup
lub wartości.

### GET `/api/v1/admin/layout-import-validations/{validationJobId}/rows`

Query:

```text
after_line_number=0
limit=25
status=all|valid|invalid
error_code=<stabilny kod opcjonalny>
```

`after_line_number` ma minimum `0`, a `limit` zakres `1..100`. Lista jest
uporządkowana rosnąco po fizycznym `lineNumber`, ponieważ staging może jeszcze
zawierać zduplikowane `sequenceNumber`. Odpowiedź zawiera wymiary wersji reguł,
`cells/signature` poprawnego wiersza albo bezpieczny kod i opis błędu.
`nextAfterLineNumber` jest ustawiony tylko, gdy istnieje następna strona.

Stabilne błędy obu endpointów:

```text
LAYOUT_IMPORT_VALIDATION_NOT_FOUND
LAYOUT_IMPORT_VALIDATION_KIND_MISMATCH
LAYOUT_IMPORT_VALIDATION_NOT_COMPLETED
LAYOUT_IMPORT_VALIDATION_METADATA_INVALID
INVALID_LAYOUT_IMPORT_ROW_FILTER
```

### DELETE `/api/v1/admin/layout-import-validations/{validationJobId}/staging`

Jawnie odrzuca nieopublikowany staging wskazanego zakończonego joba walidacji.
Backend sam odczytuje `importJobId`, usuwa najpierw wszystkie znormalizowane
wiersze powiązane z tym importem, a następnie surowe wiersze. Job importu i joby
walidacji pozostają trwałym audytem.

```json
{
  "validationJobId": "uuid",
  "importJobId": "uuid",
  "deletedNormalizedRowCount": 500000,
  "deletedRawRowCount": 500000
}
```

Operacja jest idempotentna względem już pustego stagingu. Aktywna walidacja albo
dataset wskazujący job importu lub dowolnej jego walidacji zwraca `409`:

```text
LAYOUT_IMPORT_STAGING_VALIDATION_ACTIVE
LAYOUT_IMPORT_STAGING_IN_USE
```

Panel nie przekazuje `importJobId` do endpointu; pokazuje go użytkownikowi i
wymaga przepisania jako potwierdzenia dokładnego celu przed wysłaniem żądania.

### POST `/api/v1/admin/layout-import-validations/{validationJobId}/publish`

Publikuje zakończony, poprawny staging jako nową niezmienną wersję datasetu.
Endpoint ponownie oblicza raport pod blokadą joba importu, wszystkich jego
walidacji, wersji reguł i gry. `dataset_versions` i pełny setowy
`INSERT ... SELECT` do `layouts` należą do jednej transakcji.

Odpowiedź ma istniejący kontrakt `DatasetVersionResponse`:

```json
{
  "id": "uuid",
  "gameId": "uuid",
  "version": 4,
  "rows": 3,
  "columns": 5,
  "signatureCellWidth": 2,
  "layoutCount": 500000,
  "status": "published",
  "generationSeed": 0,
  "generatorVersion": "layout-import-v1",
  "sourceJobId": "validation-job-uuid",
  "createdAt": "2026-07-28T12:00:00Z",
  "publishedAt": "2026-07-28T12:00:00Z"
}
```

`sourceJobId` jest unikalny. Retry tej samej walidacji zwraca dokładnie tę samą
wersję, również gdy pierwsza odpowiedź została utracona. Duplikaty sygnatur są
dozwolone; pozostałe blokady raportu zwracają `409`.

Stabilne konflikty publikacji:

```text
LAYOUT_IMPORT_PUBLICATION_SOURCE_INVALID
LAYOUT_IMPORT_RULES_NOT_PUBLISHED
LAYOUT_IMPORT_NOT_READY_FOR_PUBLICATION
LAYOUT_IMPORT_PUBLICATION_ROW_COUNT_CHANGED
```

Publikacja nie usuwa stagingu i nie uruchamia automatycznie payoutów ani
pipeline’u Android.

### GET `/api/v1/admin/jobs`

Zwraca najwyżej 200 najnowszych rekordów. Obsługuje filtry `status`,
`job_type`, `game_id` oraz bounded `limit`, domyślnie 50.

### GET `/api/v1/admin/worker-lanes`

Zwraca zawsze dwa rekordy w kolejności `general`, `image_selection`, niezależnie
od obecności jobów oraz filtra listy. Status `running | degraded | stopped`
wynika z heartbeat procesu. Odpowiedź nie ujawnia PID, `workerId`, komendy ani
lokalnych ścieżek:

```json
[
  {
    "lane": "general",
    "state": "running",
    "workerVersion": "worker-v10-general",
    "threadBudget": 2,
    "startedAt": "2026-08-05T12:00:00Z",
    "heartbeatAt": "2026-08-05T12:00:05Z"
  },
  {
    "lane": "image_selection",
    "state": "stopped",
    "workerVersion": null,
    "threadBudget": null,
    "startedAt": null,
    "heartbeatAt": null
  }
]
```

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
  "attemptCount": 1,
  "heartbeatAt": "2026-07-24T10:03:00Z",
  "leaseExpiresAt": "2026-07-24T10:04:00Z",
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

### POST `/api/v1/admin/jobs/{jobId}/retry`

Przenosi ten sam rekord z `failed` albo `waiting_for_review` do `created`.
Zachowuje wejście, checkpoint, postęp i `attemptCount`, nie tworzy duplikatu.
Kolejny claim zwiększa `attemptCount`. Pozostałe statusy zwracają
`409 INVALID_JOB_STATUS_TRANSITION`.

`heartbeatAt` i `leaseExpiresAt` są dostępne do diagnostyki aktywnego joba i są
`null` poza `processing`. Wewnętrzne `leaseToken`, `leaseOwner` oraz
`checkpointPayload` nigdy nie są zwracane przez Admin API.

Dla joba `image_selection` obiekt `progress` zawiera dodatkowe pole
`imageSelection`:

```json
{
  "groups": 12,
  "selected": 9,
  "manual": 2,
  "skipped": 1,
  "errors": 3,
  "verifications": 30,
  "uploadDurationSeconds": 15.5,
  "processingDurationSeconds": 8.25,
  "diagnosticChecksumSha256": "sha256"
}
```

`manual` oznacza bieżącą liczbę nierozwiązanych grup, natomiast wspólny licznik
`review` pozostaje monotoniczny. Czas uploadu i czas obliczeń są mierzone
oddzielnie; `processingDurationSeconds` nie obejmuje oczekiwania użytkownika w
`waiting_for_review`. Diagnostyka ujawnia tylko checksumę bounded manifestu,
bez ścieżki serwera, obrazów i danych wrażliwych. Pole `imageSelection` nie jest
zwracane dla pozostałych typów jobów.

Job `import` z `importKind = image_directory` zwraca w `inputPayload` także
`sourceSelectionId`, zatwierdzone `sourceDirectory`, `sourceDisplayName` i
poświadczony `pipelineFingerprint`. Pola źródła są opcjonalne wyłącznie przy
odczycie historycznych jobów utworzonych przed TASK-0123; nowy endpoint zawsze
je zapisuje. Szczegóły operacyjne takiego joba mają osobny kontrakt:

### GET `/api/v1/admin/image-jobs/{jobId}/operations`

Zwraca trwałe aggregate `total`, `current`, `succeeded`, `failed`, `review`
i `waiting`, czas od `startedAt` do `finishedAt` albo ostatniej trwałej
aktualizacji oraz `filesPerMinute = current * 60 / elapsedSeconds`. Parametr
`file_limit` jest ograniczony do 1–200, domyślnie 100. Lista plików zachowuje
`orderIndex` i zawiera `fileExecutionKey`, względną ścieżkę, status,
`nextStage`, `failedStage`, bezpieczny błąd, `retryCount` oraz znacznik review.
`hasMoreFiles` jawnie informuje o obcięciu listy.

### POST `/api/v1/admin/image-jobs/{jobId}/files/{fileExecutionKey}/retry`

Body ma postać `{"expectedStage":"normalization"}`. Endpoint akceptuje tylko
failed job-local checkpoint, którego `failedStage` i `nextStage` są równe
`expectedStage`. Czyści błąd tego powiązania, zwiększa licznik retry i zachowuje
ten sam file key, wcześniejsze immutable stage results oraz checkpoint. Job
`failed` albo `waiting_for_review` jest wznawiany jako ten sam rekord
`created`; aktywny lub terminalny job zwraca konflikt. Odpowiedzią jest
odświeżony kontrakt operations.

### GET `/api/v1/admin/image-storage`

Zwraca read-only inwentarz dokładnie sześciu przestrzeni pod zarządzanym rootem
`data`: nazwę, `retentionPolicy`, `protected`, `exists`, `fileCount`,
`sizeBytes` i `ignoredSymlinkCount`. Odpowiedź zawiera sumy oraz
`automaticDeletion = false`. Endpoint nie przyjmuje ścieżki i nie wykonuje
operacji destrukcyjnej.

### POST `/api/v1/admin/image-jobs/{jobId}/diagnostic-exports`

Tworzy kanoniczny manifest `image-job-diagnostics-v1` z dokładnymi agregatami
i najwyżej 10 000 uporządkowanych błędów. Odpowiedź `201` zawiera `created`
oraz metadane eksportu: job, SHA-256, względną ścieżkę, rozmiar, czas źródłowego
stanu, dokładny i wyeksportowany licznik błędów oraz `truncated`. Identyczny
stan zwraca ten sam plik i `created = false`.

### GET `/api/v1/admin/image-jobs/{jobId}/diagnostic-exports`

Zwraca historyczne, poprawne checksumowo manifesty najpierw od najnowszego
stanu źródłowego. Uszkodzony manifest kończy żądanie stabilnym konfliktem,
zamiast być pominięty albo pobrany.

### GET `/api/v1/admin/image-jobs/{jobId}/diagnostic-exports/{checksumSha256}/download`

Ponownie sprawdza, czy ścieżka pozostaje w zarządzanym root, czy manifest jest
kanoniczny i czy pełny SHA-256 odpowiada wersji. Zwraca niezmienione bajty jako
`application/octet-stream` z nazwą pliku `.json`; panel pobiera je jako `Blob`.

Wspólny automat:

```text
created -> processing -> completed
                    \-> failed
                    \-> waiting_for_review -> created
created/waiting_for_review -> cancelled
processing + cancelRequestedAt -> cancelled (worker safe point)
failed/waiting_for_review -> created (explicit retry)
```

`stage` nie zmienia automatu. Błędne przejście ma kod
`INVALID_JOB_STATUS_TRANSITION`.

## Review batches and items

TASK-0064 imports the checksum-bound output of
`whole-layout-active-learning-v1`. Import is atomic and idempotent by the
canonical SHA-256 of the entire source report. Reusing the checksum for a
different game or payload fails closed.

```text
GET  /api/v1/admin/review-batches
POST /api/v1/admin/review-batches
GET  /api/v1/admin/review-batches/{reviewBatchId}
GET  /api/v1/admin/review-batches/{reviewBatchId}/items
GET  /api/v1/admin/review-items/{reviewItemId}
GET  /api/v1/admin/review-items/{reviewItemId}/assets/source
GET  /api/v1/admin/review-items/{reviewItemId}/assets/board
GET  /api/v1/admin/review-items/{reviewItemId}/assets/cells/{cellIndex}
POST /api/v1/admin/review-items/{reviewItemId}/resolution
GET  /api/v1/admin/review-items/{reviewItemId}/resolutions
POST /api/v1/admin/review-batches/{reviewBatchId}/feedback-exports
GET  /api/v1/admin/review-batches/{reviewBatchId}/feedback-exports
GET  /api/v1/admin/review-feedback-exports/{feedbackExportId}
```

`POST /review-batches` accepts `gameId`, `sourceReportSha256` and the exact
typed TASK-0063 report. The backend validates its canonical checksum, active
symbol catalog, relative POSIX paths, provenance hashes, unique board/source
identity, contiguous selection ranks and exactly 15 row-major cells per
board. The response contains `created`; a safe retry returns the existing
batch with `created = false`.

The item list uses the deterministic `selectionRank` cursor:
`after_selection_rank >= 0`, `1 <= limit <= 100`, with an optional
`status = pending | accepted | corrected | rejected`. Each item exposes an
immutable `snapshot` containing the whole 5 × 3 board, source context,
prediction confidence and up to three alternatives per cell. Image binaries
are not embedded in JSON and are never stored in PostgreSQL.

TASK-0065 adds three item-scoped read-only image responses. The client never
submits a path: `source`, `board` and bounded `cellIndex` identify metadata
already stored on the item. The source file must be found below
`GAME_PREDICTOR_REVIEW_SOURCE_ROOT` by its exact SHA-256. Board and cell files
must resolve below `GAME_PREDICTOR_REVIEW_CROP_ROOT` using the validated
relative POSIX paths from the immutable snapshot. Missing, ambiguous, unsafe
or unsupported files fail closed with a stable review error. Successful image
responses are private and immutable.

`POST /resolution` resolves the complete board. The body contains an
`idempotencyKey`, `expectedRevision`, action `accepted | corrected | rejected`,
the local administrator identity and explicit geometry confirmation.
Accepted/corrected commands carry exactly 15 row-major labels bound to the
immutable `sampleId`; accepted labels must equal predictions, while corrected
labels must contain at least one change and every symbol must remain active in
the batch game. Rejection requires a reason and cannot carry labels.

The exact retry returns `created = false`. Reusing a key for another canonical
payload or submitting a stale revision returns `409`. Every successful change
increments `resolutionRevision`, updates the current item projection and
appends an immutable event returned by `GET /resolutions`.

Feedback export is blocked while any item is pending. It excludes rejected
items and freezes 15 samples per accepted/corrected board with model, source,
crop and resolution provenance. An unchanged source-state retry returns the
same export; changed resolutions create the next game-local version. Payload
and source state have independent SHA-256 checksums, and no image binary is
stored in PostgreSQL.

## Operational image review workbench

M6.5 używa job-local `image_review_items`, a nie bounded batchy
active-learning. TASK-0106 wdrożył osobną grupę Admin API:

```text
GET  /api/v1/admin/image-review-items
GET  /api/v1/admin/image-review-items/{reviewItemId}
GET  /api/v1/admin/image-review-items/{reviewItemId}/assets/source
GET  /api/v1/admin/image-review-items/{reviewItemId}/assets/board
GET  /api/v1/admin/image-review-items/{reviewItemId}/assets/cells/{cellIndex}
POST /api/v1/admin/image-review-items/{reviewItemId}/resolution
GET  /api/v1/admin/image-review-items/{reviewItemId}/resolution-events
POST /api/v1/admin/image-review-items/{reviewItemId}/geometry-preview
POST /api/v1/admin/image-review-items/{reviewItemId}/geometry-revisions
```

TASK-0124 rozszerza grupę o kontrolę kompletności i wybór źródła:

```text
GET  /api/v1/admin/image-review-items/dataset-completeness/{gameId}
GET  /api/v1/admin/image-review-items/sequence-sources/{gameId}/{sequenceNumber}
POST /api/v1/admin/image-review-items/sequence-sources/{gameId}/{sequenceNumber}/override
```

Raport kompletności porównuje zaakceptowane numery z zakresem
`1..expectedLayoutCount`. Zwraca dokładne liczniki zaakceptowanych plansz,
unikalnych sekwencji, luk, nadmiarowych źródeł i numerów poza zakresem oraz
maksymalnie 100 pierwszych brakujących numerów z flagą obcięcia.

Lista źródeł zwraca stabilny ranking zaakceptowanych plansz tej samej sekwencji,
jawne metryki jakości, provenance, automatyczny rank i aktualny wybór. Komenda
override przyjmuje `reviewItemId` albo `null` do powrotu do wyboru
automatycznego oraz `selectedBy`. Każda zmiana tworzy kolejną rewizję audytu;
nie usuwa automatycznego rankingu ani historycznej decyzji.

TASK-0125 dodaje game-scoped bootstrap symboli:

```text
GET  /api/v1/admin/games/{gameId}/symbol-bootstrap
POST /api/v1/admin/games/{gameId}/symbol-bootstrap
POST /api/v1/admin/games/{gameId}/symbol-bootstrap/{bootstrapId}/resolution
```

Start przyjmuje `expectedSymbolCount` i `createdBy`. Odpowiedź zawiera checksum
stanu cropów, wykrytą liczbę grup, provenance kandydatów i status. Zgodna liczba
grup daje `applied`; różnica daje `conflict` bez utworzenia symboli. Resolution
musi zdefiniować dokładnie oczekiwaną liczbę symboli, użyć wszystkich
kandydatów i zachować unikalne stabilne kody oraz `mobileCode`.

TASK-0126 rozszerza katalog o checksum-bound wybór grafiki reprezentatywnej:

```text
GET  /api/v1/admin/games/{gameId}/symbols/{symbolId}/image/asset
GET  /api/v1/admin/games/{gameId}/symbols/{symbolId}/image-candidates
GET  /api/v1/admin/games/{gameId}/symbols/{symbolId}/image-candidates/{observationId}/asset
POST /api/v1/admin/games/{gameId}/symbols/{symbolId}/image-candidates/{observationId}/selection
```

Lista zwraca maksymalnie 10 rzeczywistych cropów grupy symbolu w kolejności
confidence malejąco, checksum i UUID obserwacji. Opaque `afterCursor` jest
związany z `gameId` i `symbolId`; nie można użyć go w innym katalogu. Klient
nie otrzymuje ścieżki pliku kandydata. Endpoint assetu ponownie ustala
obserwację w dokładnym zakresie symbolu, ogranicza plik do
`<artifact-root>/data`, dopuszcza wyłącznie PNG/JPEG i porównuje SHA-256.

Selection przyjmuje tylko nową `name`; target grafiki wynika z identyfikatora
obserwacji w URL. Zapis aktualizuje atomowo nazwę i `image_path`, ale nie może
zmienić `code`, `mobileCode`, kolejności ani provenance bootstrapu. Bieżąca
grafika kafelka jest odczytywana osobnym endpointem przez jej zachowaną
obserwację i checksumę, a nie przez ścieżkę podaną przez przeglądarkę.

TASK-0110 dodał osobną, jawną operację zamrożenia:

```text
POST /api/v1/admin/image-review-cohort-exports
GET  /api/v1/admin/image-review-cohort-exports
```

Lista wymaga `gameId` i `importJobId`, używa bounded cursor i przyjmuje widok
`all | pending | completed`. `completed` obejmuje accepted/corrected, ale
elementy pozostają edytowalne. Osobna aplikacja Reviewer używa `all` jako
aktywnej kolejki nawigacyjnej; `pending/completed` pozostają projekcjami
statusów i liczników, a nie filtrem usuwającym element z bieżącej sesji po
zapisie. Kolejność jest deterministyczna po zaakceptowanym `sequenceNumber`, a
przed jego akceptacją po stabilnej pozycji źródła i planszy. Odpowiedź zawiera
cursor poprzedni/następny oraz liczniki, ale nie całą kolejkę.

Detail zawiera snapshot źródła, bieżącą geometrię, dokładnie 15 komórek,
aktualną etykietę oraz predykcję z confidence i maksymalnie czterema
alternatywami. Binarne obrazy pozostają w item-scoped endpointach i są
rozwiązywane pod zarządzanymi rootami po checksumie.

Resolution ma UUID idempotencji, expected revision, aktora, zaakceptowany
numer, dokładną rewizję geometrii i 15 par `cropSampleId/symbolCode`.
Accepted/corrected tworzy append-only event i idempotentny staging row;
rejected wymaga powodu. Edycja kompletnej planszy używa tego samego kontraktu i
tworzy kolejną rewizję.

Kursor jest opaque i związany z `gameId`, `importJobId` oraz wybraną projekcją.
W aktywnej projekcji `all` zapis accepted/corrected nie usuwa elementu, więc
wcześniejszy kursor nadal może do niego wrócić. Rozmiar strony jest ograniczony
do 50, a Reviewer zawsze żąda `limit = 1`. Pełny import nigdy nie jest
zwracany jako jedna odpowiedź.

Bez kursora wejściowego lub po reloadzie lista `all` wskazuje pierwszą planszę
`pending`; jeśli nie ma żadnej pending, wskazuje pierwszą planszę importu.
Pomyślny zapis resolution zwraca albo pozwala jednoznacznie pobrać następny
kursor w projekcji `all`, bez ponownego filtrowania bieżącego itemu. Na końcu
kolejki pozostaje jawny brak następnego kursora; poprzedni działa również dla
accepted/corrected. Bazowa geometria pipeline'u ma rewizję `0`, a
`cropSampleId` v1 jest deterministycznym SHA-256 tożsamości planszy, pozycji,
wersji croppera, ścieżki i checksumy cropu. Endpointy assetów rozwiązują
wyłącznie względne ścieżki pod `<artifact-root>/data`, blokują traversal i
sprawdzają checksumę przed wysłaniem pliku.

Geometry revision przyjmuje cztery narożniki w przestrzeni oryginalnego obrazu
oraz expected geometry i resolution revision. Preview zwraca PNG kanonicznej
planszy 500 × 300 i nie zapisuje pliku ani rewizji. Zapis wymaga dodatkowo UUID
idempotencji i aktora; backend/worker generuje nową planszę i dokładnie 15
cropów, zapisuje ścieżki oraz checksumy i ponownie otwiera review item. Klient
nie przesyła ścieżek systemowych ani gotowych plików wyjściowych.

Cohort export jest checksum-bound. Exact retry zwraca istniejącą wersję, a
zmiana którejkolwiek decyzji tworzy nową. Sam eksport nie uruchamia treningu
ani nie zmienia modelu. `POST` przyjmuje wyłącznie `createdBy`, `gameId` i
`importJobId`; nie przyjmuje progu, ścieżki ani komendy treningowej. `GET`
zwraca najwyżej 100 wersji, domyślnie 50, w kolejności malejącej.

Eksport może zamrozić jawnie wybraną iterację mimo pozostających pending,
ponieważ właściciel może pracować etapami po 1000/3000 planszach. Payload
zawiera jednak próbki wyłącznie z kompletnych accepted/corrected. Liczniki
pending/rejected są utrwalone jako dowód stanu; nierozwiązane elementy, luki
lub duplikaty nadal blokują późniejszą publikację całego zakresu.

TASK-0112 dodaje lokalną bramę wejścia do osobnej aplikacji Reviewer:

```text
POST /api/v1/admin/reviewer-sessions
POST /api/v1/reviewer/sessions/{sessionId}/unlock
```

Utworzenie wymaga `gameId`, `importJobId` i ograniczonego czasu życia. Odpowiedź
zawiera losowy identyfikator sesji, link bez sekretu, osobno kod i czas
wygaśnięcia. Kod jest ujawniany tylko w tej odpowiedzi; proces API przechowuje
salt i hash PBKDF2. Unlock zwraca wyłącznie scope gry/importu i odrzuca błędny,
nieistniejący albo wygasły kod stabilnym błędem.

Sesje TASK-0112 są procesowe i działają wyłącznie na loopback. Restart API je
unieważnia. Nie mają jeszcze limitu prób, trwałego audytu, odwołania ani tokenu
autoryzującego każde kolejne żądanie, dlatego nie wolno ich wystawiać w
Internecie. M8.7 rozszerzy tę granicę w TASK-0113–0115 o trwałą, odwoływalną
autoryzację, ochronę brute force i HTTPS; pełne endpointy administracyjne
pozostaną niedostępne.

### Aktualny kontrakt zdalnej sesji Reviewer (TASK-0113–0115)

Powyższy opis procesowej sesji TASK-0112 jest historycznym baseline i zostaje
zastąpiony przez trwały kontrakt:

```text
POST /api/v1/admin/reviewer-sessions
POST /api/v1/admin/reviewer-sessions/{sessionId}/revoke
POST /api/v1/reviewer/sessions/{sessionId}/unlock
GET  /api/v1/reviewer/context/games
GET  /api/v1/reviewer/context/jobs
GET  /api/v1/reviewer/context/games/{gameId}/symbols
```

Utworzenie wymaga `gameId`, image `importJobId` należącego do tej gry i TTL od
5 minut do 24 godzin. Import musi mieć status `waiting_for_review` albo
`completed` oraz zawierać co najmniej jedną planszę review. Backend sprawdza te
warunki ponownie przy tworzeniu sesji; pusty, niedokończony albo obcy scope
zwraca `REVIEWER_SCOPE_INVALID`. Odpowiedź zawiera identyfikator, link bez sekretu,
jednorazowo ujawniony kod i czas wygaśnięcia. PostgreSQL przechowuje tylko
salt/hash PBKDF2 kodu i hash opaque tokenu.

Unlock rotuje bearer token. Piąta błędna próba blokuje sesję, a revoke
natychmiast usuwa token. Publiczny proxy przejmuje token do `HttpOnly`,
`SameSite=Strict` cookie i nie udostępnia go JavaScriptowi. Każdy operacyjny
odczyt i zapis porównuje scope tokenu z `gameId/importJobId`; backend zastępuje
aktora wartością `reviewer-session:<UUID>`.

Same-origin proxy nie udostępnia CRUD, job mutations, kohort/eksportów,
storage ani mobile releases. Brak bearer nadal oznacza lokalne wywołanie Admin
API na loopback; takie żądanie nie ma publicznej trasy.

### Kontrolowany lifecycle publicznego ingressu

Lokalny Admin steruje wyłącznie jednym z góry zdefiniowanym celem
`remote-reviewer`:

```text
GET  /api/v1/admin/reviewer-ingress
POST /api/v1/admin/reviewer-ingress/start
POST /api/v1/admin/reviewer-ingress/stop
```

Obie mutacje wymagają jawnego payloadu:

```json
{
  "confirmed": true,
  "target": "remote-reviewer"
}
```

Nie można przekazać komendy, pliku wykonywalnego, argumentów powłoki, portu ani
docelowego URL. Backend uruchamia wyłącznie przypięte skrypty start/status/stop
z ograniczonym timeoutem do 60 sekund. Start zapewnia produkcyjny Reviewer na loopback,
blokuje wykryty serwer developerski, uruchamia outbound-only Quick Tunnel i
zwraca stan, publiczny origin, lokalny target, czas startu i gotowość Reviewera.

`state` przyjmuje `running`, `stopped`, `stale` albo `degraded`. Stop jest
idempotentny i usuwa publiczny origin. Endpointy są częścią Admin API na
loopback i nie znajdują się na allowliście publicznego proxy Reviewera.

Panel wykonuje start przed `POST /admin/reviewer-sessions`, dzięki czemu nowa
sesja otrzymuje aktywny publiczny origin. `Zatrzymaj udostępnianie` najpierw
próbuje unieważnić bieżącą sesję, ale zamyka tunel również wtedy, gdy revoke
zwróci błąd; zapisane decyzje oraz audyt nie są usuwane.

## Admin API M6.6 — jakość modelu symboli

Endpointy kohorty z TASK-0143 oraz game-scoped podsumowanie gotowości z
TASK-0144 są dostępne w backendzie, wygenerowanym kliencie i panelu Admina.
Pozostałe endpointy TASK-0145–0149 są nadal planowane. Nie są częścią panelu
wersji 0.2.

### GET `/api/v1/admin/games/{gameId}/model-quality`

Zwraca aktywny model (albo jawne `null` przed wdrożeniem rejestru), liczby
zweryfikowanych plansz ogółem i pozycje zmienione od ostatniej kohorty,
pokrycie wszystkich aktywnych symboli, liczbę źródeł, progi doradcze 100/1000,
ostatnią kohortę, ostrzeżenia i flagę `canFreeze`. Delta porównuje checksumy
pełnych pozycji, dlatego zmieniona etykieta jest nowym elementem również wtedy,
gdy liczba plansz się nie zmieniła. Aktywny job `created` albo `processing` tej
samej gry ustawia `activeHeavyJob = true` i czasowo blokuje freeze. Ostrzeżenie
o małym pokryciu klasy pojawia się poniżej 10 cropów symbolu, a ostrzeżenie o
małej różnorodności źródeł poniżej 3 zdjęć; oba progi są doradcze i nie blokują
operacji.

### GET `/api/v1/admin/games/{game_id}/verified-training-cohorts/preview`

Zwraca dokładne liczniki elementów kwalifikujących, wykluczonych i chronionych,
checksum preview oraz ostrzeżenia o małym pokryciu. Liczniki rozdzielają
`resolvedLayoutCount`, `pendingItemCount`, `rejectedItemCount`,
`incompleteItemCount` i `protectedItemCount`. Progi 100 i 1000 są informacją,
nie warunkiem endpointu.

### POST `/api/v1/admin/games/{game_id}/verified-training-cohorts`

Body zawiera `idempotencyKey`, `createdBy` i
`expectedManifestChecksumSha256` pochodzące z jawnie potwierdzonego preview.
Komenda zamraża pełną, skumulowaną kohortę jednej gry. Zmiana stanu po preview
zwraca `VERIFIED_TRAINING_COHORT_PREVIEW_STALE`, a aktywna ciężka operacja tej
gry zwraca `VERIFIED_TRAINING_COHORT_HEAVY_JOB_ACTIVE`. Identyczny stan zwraca
istniejącą kohortę, a zmiana stanu tworzy kolejną iterację. Nie uruchamia
treningu i nie zmienia review.

### POST `/api/v1/admin/games/{gameId}/symbol-model-iterations`

Tworzy trwały job treningowy dla wskazanej kohorty i wersjonowanej konfiguracji.
Body zawiera `cohortId`, `idempotencyKey` i opcjonalną konfigurację treningu.
Odpowiedź zawiera zagnieżdżone `job`, `iteration` oraz flagę `created`; request
nie wykonuje treningu w procesie API. Powtórzenie identycznej komendy zwraca ten
sam job i iterację, a drugi aktywny trening tej samej gry zwraca konflikt.

### GET `/api/v1/admin/games/{gameId}/symbol-model-iterations`

Zwraca bounded historię wersji, statusy, checksumy checkpointów, ostatnią
ukończoną epokę i metryki cząstkowe.

Lista zawiera również checksumy manifestu i raportu kandydata, wersjonowaną
konfigurację bramki, `gateMetrics` oraz stabilne `rejectionReasons`.

### GET `/api/v1/admin/games/{gameId}/symbol-model-iterations/{iterationId}`

W TASK-0146 zwraca przypiętą kohortę, konfigurację, fingerprint, stan datasetu,
checkpoint, epokę i metryki cząstkowe. Pełne metryki kandydata, porównanie z
aktywnym modelem i stan bramki zostaną rozszerzone w TASK-0147. Endpoint nie
zwraca absolutnych ścieżek ani danych obrazu.

Od TASK-0147 endpoint zwraca pełne metryki kandydata, opcjonalne porównanie z
aktywną bazą, parity PyTorch–ONNX i wynik smoke CPU. Ścieżki artefaktów są
względne wobec zarządzanego storage; API nie ujawnia ścieżek absolutnych.

### GET `/api/v1/admin/games/{gameId}/symbol-model-iterations/{iterationId}/activation-preview`

Parametr `action = activate | rollback` zwraca dokładną checksumę manifestu
kandydata i bieżący `currentModelIterationId`. Preview nie zmienia rejestru.

### POST `/api/v1/admin/games/{gameId}/symbol-model-iterations/{iterationId}/activate`

Body zawiera `expectedManifestChecksumSha256`,
`expectedCurrentModelIterationId`, `idempotencyKey`, `actor` i opcjonalny
`reason`. Komenda aktywuje wyłącznie kompletny `candidate_ready`, którego
manifest i bieżący aktywny model są zgodne z preview. Dokładne ponowienie zwraca
`created = false`; ponowne użycie klucza dla innej komendy zwraca konflikt.
Aktywacja nie wpływa na model przypięty do trwającego importu.

### POST `/api/v1/admin/games/{gameId}/symbol-model-iterations/{iterationId}/rollback`

Tworzy nowe zdarzenie aktywacji wcześniej poprawnej wersji. Nie nadpisuje
historii i nie przelicza danych. Target rollbacku musiał już wcześniej być
aktywny dla tej samej gry i nadal mieć kompletny, checksum-bound manifest.

### GET `/api/v1/admin/games/{gameId}/symbol-model-iterations/registry/activations`

Zwraca ograniczoną historię aktywacji i rollbacków w malejącej kolejności
`activationNumber`. Rekord zawiera poprzednią i nową iterację, akcję, aktora,
powód, klucz idempotencji i czas. Bieżący model to iteracja z najwyższym
`activationNumber`.

### GET `/api/v1/admin/games/{gameId}/pending-reinference-preview`

Zwraca liczbę aktualnych `pending`, chronionych decyzji człowieka i elementów
wykluczonych z powodu cropu lub geometrii.

### POST `/api/v1/admin/games/{gameId}/pending-reinference-jobs`

Tworzy wznawialny job przypięty do konkretnej aktywnej wersji. Backend i worker
ponownie sprawdzają status oraz rewizję przy zapisie. `accepted`, `corrected` i
`rejected` są pomijane nawet wtedy, gdy zostały rozwiązane już po starcie joba.
Wyniki są append-only rewizjami predykcji.

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
  "id": "uuid",
  "version": "m1.0.1",
  "status": "draft",
  "algorithmVersion": "payout-v2",
  "snapshotSchemaVersion": 2,
  "snapshot": null,
  "apk": null,
  "buildJobId": null,
  "createdAt": "2026-07-27T12:00:00Z",
  "readyAt": null,
  "games": [
    {
      "gameId": "uuid",
      "gameCode": "game-1",
      "datasetVersionId": "uuid",
      "datasetVersion": 1,
      "rulesVersionId": "uuid",
      "rulesVersion": 1,
      "rows": 3,
      "columns": 5,
      "layoutCount": 500000
    }
  ]
}
```

Backend ustala `algorithmVersion = payout-v2` i `snapshotSchemaVersion = 2`;
klient nie może podać dowolnego algorytmu ani schematu. Wersja jest globalnie
unikalnym, bezpiecznym segmentem ścieżki. Request zawiera od 1 do 15 unikalnych
gier. Dataset i reguły muszą być opublikowane, należeć do wskazanej aktywnej
gry i mieć zgodne wymiary.

Admin 0.2 wysyła dokładnie jedną grę testową i natychmiast po poprawnym POST
wywołuje endpoint builda. Zakres 1–15 w API pozostaje bez zmian jako kontrakt
backendowy dla późniejszego wydania wielogrowego 0.5. Jeżeli drugi request nie
powiedzie się, utworzony draft pozostaje dostępny do jawnego wznowienia.

### GET `/api/v1/admin/mobile-releases`

Zwraca wszystkie historyczne wydania od najnowszego. Każdy element ma ten sam
kształt co odpowiedź POST i endpoint szczegółów. Gry są uporządkowane po
stabilnym `gameCode`.

### POST `/api/v1/admin/mobile-releases/{releaseId}/build`

Uruchamia jeden workflow:

1. atomowa rewalidacja niezmiennego wyboru i przejście `draft → building`,
2. precomputing brakujących payoutów,
3. generowanie i niezależna weryfikacja SQLite,
4. kontrolowany lokalny Android Release build dla `arm64-v8a`,
5. weryfikacja offline APK i dokładnego SQLite,
6. zapis względnych ścieżek, checksum i przejście do `ready`.

Response:

```json
{
  "jobId": "uuid",
  "status": "created"
}
```

Response `201` oznacza wyłącznie utworzenie joba. Request nie wykonuje payoutów,
SQLite ani Gradle. Drugi start tego samego release zwraca
`409 MOBILE_RELEASE_BUILD_ALREADY_STARTED`; retry wykonuje się przez
`POST /admin/jobs/{jobId}/retry` na tym samym jobie.

### GET `/api/v1/admin/mobile-releases/{releaseId}`

```json
{
  "id": "uuid",
  "version": "m1.0.1",
  "status": "ready",
  "algorithmVersion": "payout-v2",
  "snapshotSchemaVersion": 2,
  "snapshot": {
    "schemaVersion": 2,
    "relativePath": "snapshots/m1.0.1/<logical-sha256>/snapshot.db",
    "checksum": "pełny-mały-hex-sha256"
  },
  "apk": {
    "relativePath": "android-releases/m1.0.1/app-release-<apk-sha256>.apk",
    "checksum": "pełny-mały-hex-sha256"
  },
  "buildJobId": "uuid",
  "createdAt": "2026-07-27T12:00:00Z",
  "readyAt": "2026-07-27T12:30:00Z",
  "games": [
    {
      "gameId": "uuid",
      "gameCode": "game-1",
      "datasetVersionId": "uuid",
      "datasetVersion": 1,
      "rulesVersionId": "uuid",
      "rulesVersion": 1,
      "rows": 3,
      "columns": 5,
      "layoutCount": 500000
    }
  ]
}
```

API zwraca ścieżkę do lokalnego artefaktu, ale nie instaluje APK na telefonie.
`ready` powstaje dopiero po ostatnim bezpiecznym checkpointcie, gdy job nadal
jest aktywny i nie ma żądania anulowania. Błąd albo anulowanie ustawia release
na `failed`; zweryfikowany snapshot może pozostać przypięty do bezpiecznego
wznowienia, ale częściowy APK nie jest publikowany w rekordzie release.

### GET `/api/v1/admin/mobile-releases/{releaseId}/apk`

Zwraca `application/vnd.android.package-archive` wyłącznie dla release
`ready`. Klient przekazuje tylko identyfikator wydania. API rozwiązuje zapisaną
ścieżkę względem własnego `GAME_PREDICTOR_ARTIFACT_ROOT`, odrzuca wyjście poza
katalog, brak pliku, symlink i rozszerzenie inne niż `.apk`, a przed odpowiedzią
ponownie porównuje SHA-256 z niezmiennym rekordem release.

Endpoint nie przyjmuje ścieżki, nazwy pliku ani komendy. `draft`, `building`,
`failed` i `archived` nie udostępniają pliku; zmieniony albo brakujący artefakt
zwraca stabilny konflikt zamiast danych.

Stabilne błędy utworzenia wydania:

```text
INVALID_RELEASE_VERSION
INVALID_RELEASE_GAME_COUNT
DUPLICATE_RELEASE_GAME
MOBILE_RELEASE_VERSION_ALREADY_EXISTS
MOBILE_RELEASE_NOT_FOUND
RELEASE_SOURCE_NOT_FOUND
RELEASE_SOURCE_GAME_MISMATCH
RELEASE_GAME_NOT_ACTIVE
RELEASE_DATASET_NOT_PUBLISHED
RELEASE_RULES_NOT_PUBLISHED
RELEASE_SOURCE_DIMENSIONS_MISMATCH
RELEASE_DATASET_EMPTY
MOBILE_RELEASE_APK_NOT_READY
MOBILE_RELEASE_APK_UNAVAILABLE
MOBILE_RELEASE_APK_CHECKSUM_MISMATCH
```

## Kontrolowane usuwanie danych roboczych

### GET `/api/v1/admin/mobile-releases/{releaseId}/deletion-preview`

### GET `/api/v1/admin/games/{gameId}/layout-data-reset-preview`

Oba endpointy są read-only. Zwracają aktualny cel, liczniki zależności, jawne
ścieżki zarządzanych artefaktów, liczbę zachowanych artefaktów współdzielonych,
blokady oraz SHA-256 kanonicznego stanu:

```json
{
  "kind": "game_layout_data",
  "targetId": "uuid",
  "targetLabel": "Game One (game-1)",
  "confirmationTarget": "uuid",
  "counts": [
    { "name": "layouts", "count": 250 },
    { "name": "jobs_preserved", "count": 3 }
  ],
  "artifactPaths": ["data/originals/ab/checksum.jpg"],
  "retainedSharedArtifactCount": 1,
  "blockers": [],
  "previewToken": "pełny-mały-hex-sha256"
}
```

Preview nie usuwa danych. Aktywny job, build, sesja Reviewera albo współdzielone
wydanie jest zwracane jako blokada; UI nie może wtedy wykonać operacji.

### DELETE `/api/v1/admin/mobile-releases/{releaseId}`

### DELETE `/api/v1/admin/games/{gameId}/layout-data`

Request obu endpointów:

```json
{
  "previewToken": "pełny-mały-hex-sha256",
  "confirmationTarget": "uuid",
  "confirmed": true
}
```

Oprócz body wymagane są standardowa lokalna intencja oraz dokładny nagłówek
`X-Admin-Target`: odpowiednio `mobile-release:{releaseId}` albo
`game-layout-data:{gameId}`. Serwer pod blokadą ponownie wylicza preview; zmiana
stanu daje konflikt zamiast wykonania na starym zakresie.

Usunięcie wydania usuwa rekord, powiązania oraz dedykowany katalog snapshotu i
APK. Reset gry zachowuje rekord `games`, joby i współdzielony cache przetwarzania,
ale usuwa game-scoped importy, obrazy robocze, review, symbole, reguły, datasety,
layouty, payouty, sesje Reviewera i zależne wydania. Źródłowy folder wybrany przez
użytkownika oraz artefakty nadal wskazywane przez inną grę nie są usuwane.

Odpowiedź zawiera `deletedCounts`, `deletedArtifactCount`,
`retainedSharedArtifactCount` oraz `alreadyCompleted`. Retry tego samego
potwierdzonego tokenu po utracie odpowiedzi zwraca zapisany wynik z
`alreadyCompleted = true`.

Stabilne błędy cleanupu:

```text
CLEANUP_TARGET_NOT_FOUND
CLEANUP_CONFIRMATION_MISMATCH
CLEANUP_PREVIEW_STALE
CLEANUP_BLOCKED
CLEANUP_ARTIFACT_DELETE_FAILED
CLEANUP_ARTIFACT_PATH_UNSAFE
```

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

`ImageSelectionRunResponse` zwraca również `selectorVersion`. Backend wyznacza
wartość z zapisanego `selectorFingerprint` przez rejestr niezmiennych manifestów;
dla nieznanego historycznego fingerprintu zwraca `unknown`. Panel używa pola do
opisania pozycji w historii runów, ale fingerprint pozostaje techniczną
tożsamością zachowania selektora.
