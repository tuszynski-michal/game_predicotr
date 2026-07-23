---
title: Proposed technology stack
status: proposed
last_updated: 2026-07-23
---

# Proponowany stos technologiczny

## Kryteria wyboru

- prosty dla React Developera,
- czytelny dla agentów AI,
- silne typowanie na granicach,
- dobry ekosystem dla Android i przetwarzania obrazu,
- minimalna liczba usług w pierwszej fazie,
- możliwość obsługi milionów prostych rekordów,
- wygodny development na Windows.

## Mobile

### React Native + Expo + TypeScript

Powody:

- wykorzystuje znajomość React i TypeScript,
- pozwala szybko uruchamiać aplikację na Android,
- Expo Router zapewnia prostą strukturę tras opartą na plikach,
- development build pozwala później dodawać biblioteki natywne bez przepisywania aplikacji.

### Biblioteki startowe

- Expo Router — routing,
- TanStack Query — stan serwerowy i cache,
- React `useReducer` — lokalny stan wprowadzania planszy,
- wygenerowany klient OpenAPI — komunikacja z API,
- wbudowane komponenty React Native i własne design tokens — bez ciężkiej biblioteki UI w MVP.

Nie używamy MUI w mobile, ponieważ jest biblioteką webową, a nie biblioteką React Native.

## Admin web

### Next.js + TypeScript

- użytkownik zna technologię,
- aplikacja działa na Windows w przeglądarce,
- łatwe formularze, podglądy i narzędzia administracyjne,
- wspólny workspace JS z mobile i kontraktami.

Startowo preferowane są proste komponenty i formularze. MUI może być użyte w adminie, jeżeli zostanie zaakceptowane jako standard UI.

## Backend

### Python + FastAPI

- pasuje do późniejszego przetwarzania obrazów,
- generuje specyfikację OpenAPI,
- ułatwia utrzymanie jednego kontraktu dla mobile i admina,
- pozwala oddzielić logikę domenową od endpointów.

### Warstwy backendu

```text
api        - routing, request/response
domain     - algorytmy i reguły
application- use cases i transakcje
storage    - SQLAlchemy repositories
schemas    - modele wejścia/wyjścia
```

### Narzędzia

- SQLAlchemy 2.x — ORM i zapytania,
- Alembic — migracje,
- Pydantic — walidacja kontraktów,
- pytest — testy,
- Ruff — lint i formatowanie,
- mypy lub Pyright — kontrola typów po ustaleniu standardu.

## Database

### PostgreSQL jako kanoniczna baza

PostgreSQL jest rekomendowany zamiast SQLite jako główna baza, ponieważ:

- liczba layoutów może wynosić od setek tysięcy do kilku milionów,
- potrzebne są indeksy po grze, numerze sekwencji i sygnaturze,
- admin i worker mogą działać równolegle,
- wymagane są transakcje, staging i raporty integralności.

SQLite może zostać użyty później jako read-only snapshot dla trybu offline mobile, ale nie jako jedyne źródło prawdy bez osobnej decyzji.

## Image processing

### Python + OpenCV

OpenCV służy do:

- korekty perspektywy,
- detekcji obszarów,
- wycinania siatki,
- normalizacji obrazu,
- porównywania cech.

OCR i klasyfikator symboli zostaną wybrane po analizie próbek. Nie należy blokować wcześniejszych etapów wyborem finalnego modelu ML.

## Monorepo

Proponowana struktura:

```text
apps/
  mobile/
  admin/
services/
  api/
  worker/
packages/
  api-client/
  shared-types/
infra/
  docker/
ai_docs/
```

- Yarn workspaces zarządza częścią TypeScript.
- Python ma osobny `pyproject.toml` w `services/api` i `services/worker` lub wspólny workspace Python, jeśli narzędzie zostanie zaakceptowane.
- PostgreSQL uruchamiany lokalnie przez Docker Compose.

## Świadomie odłożone technologie

Nie dodajemy w MVP:

- Redis,
- Celery,
- Kafka,
- Kubernetes,
- GraphQL,
- Electron,
- mikroserwisów,
- chmury i object storage.

Worker może początkowo działać jako komenda CLI z tabelą `import_jobs`. Kolejka zostanie dodana dopiero, gdy będzie realna potrzeba zdalnego lub równoległego przetwarzania.

## Wersjonowanie

Nie wpisujemy w wymaganiach sztywnych numerów frameworków. W momencie inicjalizacji należy:

1. wybrać aktualne stabilne i wzajemnie kompatybilne wersje,
2. zapisać je w lockfile,
3. odnotować decyzję w `DECISION_LOG.md`,
4. nie wykonywać automatycznych major upgrade'ów w trakcie milestone'u.
