---
title: Milestone 01 - mocked mobile vertical slice
status: proposed
last_updated: 2026-07-23
---

# Milestone 01 — działający pion mobilny na mock data

## Cel

Uruchomić na Windows kompletny, mały system: Android mobile → FastAPI → PostgreSQL. System identyfikuje layout, ale nie oblicza jeszcze target forecast.

## Zakres

### Repozytorium

```text
apps/mobile
services/api
infra/docker
packages/api-client
ai_docs
```

Admin może zostać zainicjalizowany dopiero w M2, aby nie zwiększać zakresu.

### Backend

- health endpoint,
- lista gier,
- lista symboli,
- partial prefix matching,
- exact matching,
- ambiguous response,
- confirmation-next,
- seedy danych,
- migracje.

### Database

- games,
- symbols,
- dataset_versions,
- layouts,
- minimalne indeksy,
- 3 × 1000 layoutów.

### Mobile

- select gry,
- plansza,
- symbol selection,
- undo,
- reset,
- modal unique candidate,
- status full match,
- komunikat ambiguous,
- obsługa loading/error.

## Mock configuration

### Games

- `game-1`: 3 × 5, 10 symboli,
- `game-2`: 3 × 5, 12 symboli,
- `game-3`: 3 × 5, 11 symboli, w tym jeden joker oznaczony tylko wizualnie.

### Layout generation

- deterministyczny generator,
- seed zapisany w kodzie seedera,
- `sequence_number` 1..1000,
- co najmniej 3 pary zduplikowanych sygnatur na grę,
- co najmniej jeden unikalny layout, którego prefiks staje się unikalny przed końcem planszy,
- seeder jest idempotentny.

### Przykładowe reguły danych do przyszłego testu

Można utworzyć, ale nie trzeba jeszcze wykorzystywać w kalkulacji:

- 3 poziome paylines: `[0,0,0,0,0]`, `[1,1,1,1,1]`, `[2,2,2,2,2]`,
- przykładowy symbol S1: 3 = 100, 4 = 300, 5 = 900,
- S2: 3 = 150, 4 = 450, 5 = 1350,
- S3: 3 = 200, 4 = 600, 5 = 1800.

Wartości są testowe, nie są wymaganiem biznesowym.

## Proponowane zadania

1. Bootstrap repo i narzędzi.
2. Docker Compose dla PostgreSQL.
3. FastAPI skeleton + health.
4. Modele i migracje.
5. Seeder 3 gier.
6. Games/symbols API.
7. Matching domain service + testy.
8. Matching endpoints.
9. Generowanie klienta OpenAPI.
10. Mobile skeleton.
11. Layout reducer + testy.
12. UI header/layout/selection.
13. Integracja matching + modal.
14. Duplicate confirmation flow.
15. Testy end-to-end smoke i dokumentacja uruchomienia.

Każdy punkt powinien stać się osobnym plikiem zadania przed implementacją.

## Kryteria akceptacyjne

### Uruchomienie

- jedna instrukcja uruchamia PostgreSQL,
- backend startuje bez ręcznej edycji kodu,
- telefon w tej samej sieci łączy się z API,
- konfiguracja adresu API jest przez environment.

### Dane

- baza zawiera dokładnie 3 aktywne gry,
- każda gra ma 1000 layoutów,
- numery są ciągłe 1..1000,
- istnieją kontrolowane duplikaty.

### Mobile behavior

- poprawna kolejność wprowadzania,
- Undo i Reset działają,
- zmiana gry czyści stan,
- unikalny prefiks otwiera modal,
- zamknięcie modala nie powoduje pętli,
- akceptacja wypełnia brakujące pola,
- pełny unique pokazuje numer,
- ambiguous nie pokazuje targetu,
- not found pozwala poprawić layout.

### Jakość

- testy domenowe dopasowania obejmują 0, 1 i wiele wyników,
- test reducer obejmuje ręczne i automatyczne uzupełnienie,
- OpenAPI jest aktualne,
- brak ręcznie zduplikowanych typów odpowiedzi,
- brak krytycznych błędów lint/typecheck/test.

## Poza zakresem

- prawdziwe obrazy symboli,
- payout evaluation,
- target forecast,
- admin UI,
- OCR i OpenCV,
- auth,
- offline dataset.

## Demo

Scenariusz demonstracyjny:

1. uruchom bazę i API,
2. uruchom mobile,
3. wybierz game-1,
4. wprowadź prefiks przygotowanego unikalnego layoutu,
5. zaakceptuj modal,
6. zobacz numer sekwencji,
7. reset,
8. wprowadź zduplikowany layout,
9. zobacz komunikat ambiguous,
10. podaj następny layout i rozstrzygnij pozycję.
