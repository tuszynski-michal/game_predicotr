---
title: Milestone 02 execution plan
status: accepted
last_updated: 2026-07-27
---

# Plan wykonania Milestone 02 — Admin configuration

## Cel

Zastąpić ręcznie utrzymywane fixture M1 lokalnym, wersjonowanym panelem
administracyjnym opartym na Next.js, FastAPI i PostgreSQL. Wynikiem M2 są
opublikowane, niezmienne wersje reguł i mock datasetów, ale jeszcze bez
automatycznego procesu budowania APK.

`ROADMAP.md` jest właścicielem granic milestone’u, a ten dokument jest
właścicielem kolejności podetapów, rezerwacji zadań i bramek jakości M2.

## Relevant docs

- `requirements/ADMIN_APP.md`
- `requirements/ALGORITHMS.md`
- `architecture/SYSTEM_ARCHITECTURE.md`
- `architecture/DATA_MODEL.md`
- `architecture/API_CONTRACT.md`
- `architecture/TECH_STACK.md`
- `quality/TEST_STRATEGY.md`
- D-003–D-007, D-014 i D-019 w `process/DECISION_LOG.md`

## Warunki wejścia

- M1 przechodzi końcową bramkę G6.
- Kontrakty domenowe M1 są stabilne i mają golden tests.
- PostgreSQL, FastAPI i Next.js nie zostały wcześniej dodane poza zadaniem M2.

Warunki wejścia są spełnione od 2026-07-26. G6 zostało zaakceptowane przez
właściciela z jawnym przeniesieniem pomiarów urządzeniowych i próby zmienionego
snapshotu do M3 zgodnie z D-020.

M2 nie wymaga odpowiedzi na Q-019, jeżeli panel pozostaje lokalnym narzędziem
jednego właściciela bez finalnej warstwy autoryzacji. Decyzję bezpieczeństwa
zamyka M8.

## Zasady realizacji

- podetap rozpoczyna się po bramce poprzedniego i poleceniu właściciela,
- plik zadania powstaje dopiero bezpośrednio przed jego rozpoczęciem,
- wszystkie zmiany PostgreSQL używają migracji Alembic,
- OpenAPI jest źródłem klienta TypeScript panelu,
- mobile nie otrzymuje połączenia z API ani PostgreSQL,
- payout ocenia wyłącznie prefiks payline od pierwszej kolumny zgodnie z D-019.

## M2.1 — Lokalna platforma administracyjna i kontrakt

### Zakres

- lokalny PostgreSQL w Docker Compose,
- fundament FastAPI z podziałem `api/application/domain/storage/schemas`,
- konfiguracja Alembic i pusta migracja baseline bez tabel domenowych,
- fundament Next.js z TypeScript strict,
- OpenAPI jako źródło klienta panelu,
- jawne komendy Windows dla uruchomienia, testów i migracji.

### Zadania

- `TASK-0015 — Admin platform foundations and local configuration`
  — ukończone 2026-07-26
- `TASK-0016 — PostgreSQL Compose and Alembic baseline`
  — ukończone 2026-07-26
- `TASK-0017 — OpenAPI contract and generated admin client`
  — ukończone 2026-07-26

`TASK-0015` tworzy oba szkielety aplikacyjne: `services/api` dla FastAPI oraz
`apps/admin` dla Next.js. Nie dodaje jeszcze CRUD domenowego. `TASK-0016`
odpowiada za PostgreSQL, konfigurację Alembic i odwracalny baseline bez tabel
domenowych. Tabele powstają dopiero z odpowiadającym im pionem przez kolejne
migracje. `TASK-0017` zamyka kontrakt OpenAPI oraz generowanie klienta panelu.

### Bramka G2.1

- jedna udokumentowana sekwencja uruchamia PostgreSQL, API i panel lokalnie,
- `alembic upgrade head` inicjalizuje historię migracji od pustej bazy, a
  baseline ma sprawdzoną ścieżkę cofnięcia,
- health check API działa,
- OpenAPI generuje klienta TypeScript bez ręcznie skopiowanych typów,
- mobile nie otrzymuje zależności od API ani PostgreSQL,
- format, lint, typecheck i testy obu ekosystemów przechodzą.

Bramka G2.1 została zaliczona 2026-07-26. Fizyczny PostgreSQL przeszedł
odwracalny cykl migracji, kontrakt OpenAPI i klient nie wykazują driftu, pełne
`npm run quality` przechodzi, a produkcyjny build panelu został zweryfikowany.

## M2.2 — Gry i symbole

### Zakres

- domena, repozytoria i CRUD gier,
- stabilne kody gry i symbolu,
- nazwa oraz status gry,
- CRUD symboli, kolejność, joker i lokalny obraz referencyjny,
- archiwizacja zamiast usuwania historycznie użytego symbolu,
- ekrany listy, formularza i stanów błędu w panelu.

### Zadania

- `TASK-0018 — Games and symbols domain, repository and API`
  — ukończone 2026-07-26
- `TASK-0019 — Admin shell and games identity UI`
  — ukończone 2026-07-26
- `TASK-0020 — Symbols UI, reference assets and archival rules`
  — ukończone 2026-07-27

### Bramka G2.2

- administrator tworzy grę ze stabilnym kodem, nazwą i statusem,
- dodaje `S1`–`S12`, ustawia kolejność i oznacza właściwy symbol jako joker
  w obrębie gry,
- duplikaty stabilnych kodów są blokowane w domenie i bazie,
- symbol użyty w wersjonowanych danych nie jest fizycznie usuwany,
- błędy API mają stabilny kod i czytelny stan UI,
- testy repozytorium używają testowego PostgreSQL.

Na końcu M2.2 gra ma tożsamość i katalog symboli, ale nie jest jeszcze gotowa do
layoutów. Wymiary oraz koszt spinu są własnością pierwszej wersji reguł i
powstają w M2.3.

Bramka G2.2 została zaliczona 2026-07-27. CRUD i fizyczne constraints
PostgreSQL, typowane operacje klienta oraz UI gier i symboli przeszły testy,
produkcyjny build i lokalny smoke HTTP. Publiczne akcje archiwizacji nie usuwają
rekordów.

## M2.3 — Wersje reguł, paylines i payout rules

### Zakres

- draft/published/archived dla `rules_version`,
- wersjonowane wymiary i koszt spinu,
- pola wymiarów i kosztu spinu w UI draftu wersji reguł,
- walidacja zgodności symboli z wersją,
- modal edytora payline oparty na siatce gry,
- tabela istniejących paylines,
- wersjonowane `minimum_match_length` każdego zwykłego symbolu, domyślnie 3,
- payout rules dla każdej długości od minimum symbolu do liczby kolumn,
- publikacja niezmiennej wersji reguł.

### Zadania

- `TASK-0021 — Rules versions domain, API and dimensions UI`
  — ukończone 2026-07-27
- `TASK-0022 — Payline grid editor and duplicate validation`
  — ukończone 2026-07-27
- `TASK-0023 — Per-symbol minimum and payout rules API/UI`
  — ukończone 2026-07-27
- `TASK-0024 — Immutable rules publication workflow`
  — ukończone 2026-07-27

### Bramka G2.3

Status: `passed` (2026-07-27).

- administrator tworzy dla gry draft wersji reguł 3 × 5 i ustawia koszt spinu,
- `row_path` ma dokładnie jedną istniejącą komórkę w każdej kolumnie,
- UI pokazuje wiersze 1-based, a API zapisuje 0-based,
- nie można zapisać niepełnej ani zduplikowanej payline,
- joker nie może otrzymać payout rule,
- zwykły symbol ma próg w zakresie `2..columns`, a joker nie ma progu,
- panel domyślnie ustawia próg 3 i pozwala wybranym symbolom ustawić próg 2,
- duplikat `(rules_version, symbol, match_length)` jest blokowany,
- publikacja wymaga kompletu ściśle rosnących payoutów od progu do końca
  payline,
- opublikowana wersja jest niezmienna,
- ciąg zaczynający się po pierwszej kolumnie nie jest wygraną.

## M2.4 — Mock datasety, walidacja i publikacja

### Zakres

- przeniesienie deterministycznego generatora M1 do kontrolowanego procesu
  administracyjnego,
- staging layoutów,
- zwarta reprezentacja `cells` i stałoszeroka sygnatura,
- raport luk, duplikatów numeru i duplikatów sygnatur,
- podgląd layoutu jako planszy,
- publikacja niezmiennej wersji datasetu.

### Zadania

- `TASK-0025 — Mock dataset generation and staging`
  — ukończone 2026-07-27
- `TASK-0026 — Sequence and duplicate validation reports`
  — ukończone 2026-07-27
- `TASK-0027 — Dataset preview and immutable publication`

### Bramka G2.4

- panel generuje 1000 layoutów dla gry 3 × 5,
- `sequence_number` jest ciągły i unikalny w wersji,
- duplikaty sygnatur są widoczne, ale nie blokują publikacji,
- luka, duplikat numeru, obcy symbol lub zła liczba komórek blokują publikację,
- powtórzenie generatora z tym samym seedem daje ten sam logiczny dataset,
- publikacja jest transakcyjna i nie modyfikuje wersji po fakcie.

## M2.5 — Zintegrowany odbiór panelu

### Zakres

- pełny scenariusz administratora,
- spójne loading/empty/error/success,
- testy kontraktowe API–klient,
- instrukcja lokalnego uruchomienia i resetu środowiska developerskiego.

### Zadanie

- `TASK-0028 — Admin configuration vertical slice acceptance`

### Bramka G2

- administrator tworzy grę, symbole, paylines i wypłaty,
- publikuje wersję reguł i mock dataset,
- kryteria pierwszej iteracji z `ADMIN_APP.md` są spełnione,
- OpenAPI, migracje i klient są zgodne,
- nie istnieje jeszcze automatyczny release pipeline ani import zdjęć,
- demonstracja przechodzi od pustej bazy do dwóch opublikowanych wersji bez
  ręcznej zmiany danych SQL.

## Mapa zadań M2

| Podetap | Zadania | Liczba |
|---|---:|---:|
| M2.1 Platforma i kontrakt | TASK-0015–0017 | 3 |
| M2.2 Gry i symbole | TASK-0018–0020 | 3 |
| M2.3 Reguły, paylines i payout | TASK-0021–0024 | 4 |
| M2.4 Mock datasety | TASK-0025–0027 | 3 |
| M2.5 Odbiór panelu | TASK-0028 | 1 |
| **Razem M2** | **TASK-0015–0028** | **14** |

## Następny milestone

Po przejściu G2 i poleceniu właściciela obowiązuje
`MILESTONE_03_EXECUTION_PLAN.md`.
