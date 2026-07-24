---
title: Admin API and mobile data contracts
status: accepted
last_updated: 2026-07-24
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

## Payline

### POST `/api/v1/admin/rules-versions/{rulesVersionId}/paylines`

API przyjmuje indeksy wierszy 0-based. Admin UI odpowiada za prezentację 1-based.

```json
{
  "code": "line-v",
  "name": "V",
  "rowPath": [0, 1, 2, 1, 0],
  "displayOrder": 10
}
```

Walidacja:

- długość dokładnie równa liczbie kolumn,
- każda wartość wskazuje istniejący wiersz,
- brak zduplikowanego `rowPath` w wersji.

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

## Payout rule

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
- długość poniżej 3 lub większą niż liczba kolumn,
- ujemną wypłatę,
- duplikat `(rulesVersionId, symbolId, matchLength)`.

## Dataset validation

### POST `/api/v1/admin/dataset-versions/{datasetVersionId}/validation-jobs`

```json
{
  "checks": [
    "cell_count",
    "symbol_membership",
    "continuous_sequence",
    "duplicate_signatures"
  ]
}
```

Response:

```json
{
  "jobId": "uuid",
  "status": "created"
}
```

Duplikaty sygnatur są raportem, nie automatycznym błędem publikacji. Luki i duplikaty numeru sekwencji blokują publikację.

## Job status

### GET `/api/v1/admin/jobs/{jobId}`

```json
{
  "id": "uuid",
  "jobType": "snapshot",
  "status": "processing",
  "progress": {
    "current": 250000,
    "total": 500000,
    "stage": "writing_layouts"
  },
  "error": null,
  "createdAt": "2026-07-24T10:00:00Z",
  "startedAt": "2026-07-24T10:00:03Z",
  "finishedAt": null
}
```

### POST `/api/v1/admin/jobs/{jobId}/cancel`

Zgłasza prośbę anulowania. Worker zatrzymuje się w bezpiecznym punkcie i nie oznacza niepełnego artefaktu jako gotowy.

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
  "algorithmVersion": "1",
  "snapshot": {
    "schemaVersion": 1,
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
