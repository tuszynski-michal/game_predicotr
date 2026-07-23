---
title: Initial API contract
status: proposed
last_updated: 2026-07-23
---

# Wstępny kontrakt API

Prefix: `/api/v1`

Format błędów powinien być spójny:

```json
{
  "code": "LAYOUT_NOT_FOUND",
  "message": "Nie znaleziono układu.",
  "details": {}
}
```

## Health

### GET `/health`

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

## Games

### GET `/games`

Zwraca aktywne gry dostępne dla mobile.

```json
{
  "items": [
    {
      "id": "uuid",
      "code": "game-1",
      "name": "Game 1",
      "rows": 3,
      "columns": 5,
      "spinCost": 10,
      "datasetVersion": 1,
      "rulesVersion": 1
    }
  ]
}
```

### GET `/games/{gameId}/symbols`

```json
{
  "items": [
    {
      "id": "uuid",
      "code": "S1",
      "name": "Symbol 1",
      "imageUrl": null,
      "isWildcard": false,
      "displayOrder": 1
    }
  ]
}
```

## Matching

### POST `/games/{gameId}/layouts/match`

Request:

```json
{
  "cells": ["symbol-uuid", "symbol-uuid", null, null],
  "confirmation": null
}
```

`cells` zawsze ma długość `rows * columns`.

Response dla częściowego layoutu:

```json
{
  "status": "partial",
  "candidateCount": 12,
  "proposal": null
}
```

Response dla jednego kandydata:

```json
{
  "status": "unique_candidate",
  "candidateCount": 1,
  "proposal": {
    "sequenceNumber": 155,
    "cells": ["...pełny layout..."]
  }
}
```

Response dla pełnego jednoznacznego layoutu:

```json
{
  "status": "unique",
  "candidateCount": 1,
  "match": {
    "sequenceNumber": 155,
    "cells": ["..."]
  }
}
```

Response dla duplikatu:

```json
{
  "status": "ambiguous",
  "candidateCount": 2,
  "confirmationToken": "opaque-token",
  "candidates": [100, 20000]
}
```

Dla bardzo dużej liczby kandydatów API może nie zwracać pełnej listy, tylko próbkę i zakres.

### POST `/games/{gameId}/layouts/confirm-next`

Request:

```json
{
  "confirmationToken": "opaque-token",
  "cells": ["...kolejny pełny layout..."]
}
```

Response:

```json
{
  "status": "resolved",
  "originSequenceNumber": 100,
  "matchedOffset": 1
}
```

albo kolejny `ambiguous` z nowym tokenem.

Token powinien kodować lub wskazywać stan po stronie serwera bez zaufania do numerów przesyłanych przez klienta.

## Forecast

### POST `/games/{gameId}/targets/calculate`

Nie jest implementowane w Milestone 01.

Request:

```json
{
  "startSequenceNumber": 155,
  "limit": 100000
}
```

Response:

```json
{
  "startSequenceNumber": 155,
  "evaluatedSpins": 2500,
  "stopReason": "limit_or_end",
  "spinCost": 10,
  "firstPositive": {
    "spin": 10,
    "sequenceNumber": 165,
    "netCredits": 20
  },
  "highWaterMarks": [
    {
      "spin": 10,
      "sequenceNumber": 165,
      "payout": 60,
      "cumulativePayout": 120,
      "cumulativeCost": 100,
      "netCredits": 20
    }
  ],
  "datasetVersion": 1,
  "rulesVersion": 1,
  "algorithmVersion": "1"
}
```

## Admin endpoints

CRUD admina powinien być dodawany pionami funkcjonalnymi, nie cały naraz. Początkowe grupy:

```text
/admin/games
/admin/games/{gameId}/symbols
/admin/games/{gameId}/patterns
/admin/games/{gameId}/payout-rules
/admin/games/{gameId}/layouts
/admin/import-jobs
/admin/review-items
/admin/dataset-versions
```

## Zasady kontraktu

- API używa UUID jako technicznych identyfikatorów, ale pokazuje `sequenceNumber` jako wartość domenową.
- Kredyty są liczbami całkowitymi.
- Daty są ISO 8601 UTC.
- Nazwy JSON są camelCase; Python może używać snake_case wewnętrznie.
- Wszystkie odpowiedzi i błędy są opisane w OpenAPI.
- Klient TypeScript jest generowany, nie przepisywany ręcznie.
