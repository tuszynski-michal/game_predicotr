---
title: Admin configuration vertical slice acceptance
status: done
last_updated: 2026-07-27
---

# TASK-0028 — Admin configuration vertical slice acceptance

## Status

`done`

## Goal

Udowodnić powtarzalnym scenariuszem od pustej bazy, że lokalny panel i Admin API
realizują kompletną pierwszą iterację M2, oraz zamknąć milestone czytelnymi
instrukcjami uruchomienia i bezpiecznego resetu.

## Context

Podetapy M2.1–M2.4 dostarczyły osobne piony gier, symboli, reguł, payoutów i
datasetów. Ostatnie zadanie M2 nie rozszerza domeny; scala dotychczasowe
kontrakty w jeden test akceptacyjny przez prawdziwe HTTP API i fizyczny
PostgreSQL.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- izolowany test od pustej bazy PostgreSQL przez publiczne endpointy Admin API,
- gra 3 × 5 z kosztem spinu 10,
- 12 symboli, w tym joker, minimum 2 dla jednego zwykłego symbolu i domyślne 3
  dla pozostałych,
- trzy poziome paylines, odrzucenie niepełnej i zduplikowanej ścieżki,
- kompletne, ściśle rosnące payouty i publikacja reguł,
- deterministyczny mock 1000 layoutów, raport duplikatów, podgląd i publikacja,
- końcowe potwierdzenie dwóch opublikowanych wersji bez ręcznej mutacji SQL,
- osobna komenda akceptacji M2,
- aktualne instrukcje uruchomienia i jawnie potwierdzanego resetu lokalnej bazy.

## Out of scope

- nowe endpointy lub tabele domenowe,
- import zdjęć i validation job dużej skali,
- snapshot SQLite, release mobile i budowanie APK,
- zmiany aplikacji Android,
- implementacja pierwszego zadania M3.

## Acceptance criteria

- [x] Scenariusz zaczyna od pustych list i tworzy komplet danych przez HTTP.
- [x] Niepełna payline i duplikat `rowPath` są odrzucane stabilnymi kodami.
- [x] Gotowość reguł jest sprawdzona przed atomową publikacją.
- [x] Opublikowanych reguł nie można później zmienić.
- [x] Mock zawiera 1000 layoutów i sześć widocznych grup duplikatów.
- [x] Podgląd zwraca planszę 3 × 5 w kolejności sekwencji.
- [x] Publikacja kończy się jedną opublikowaną wersją reguł i jedną datasetu.
- [x] Komenda akceptacji działa na odrębnej, automatycznie usuwanej bazie.
- [x] Reset developerski wymaga jawnego przełącznika i dotyczy tylko dokładnie
      wskazanej lokalnej bazy `game_predictor`.
- [x] README opisuje bootstrap, uruchomienie, akceptację, zatrzymanie i reset.
- [x] Pełna jakość, produkcyjny build panelu i fizyczny PostgreSQL przechodzą.

## Technical notes

- Test używa `TestClient` z prawdziwymi zależnościami repozytoriów i osobnymi
  transakcjami requestów.
- Bezpośrednie SQL służy wyłącznie utworzeniu/usunięciu izolowanej bazy testowej
  i migracjom Alembic; dane domenowe powstają tylko przez API.
- Reset nie usuwa volume ani kontenera i nie może działać bez
  `-ConfirmReset`.
- Nie jest potrzebna nowa decyzja architektoniczna ani migracja.

## Expected files

- `services/api/tests/integration/test_m2_admin_acceptance.py`
- `scripts/verify_m2_acceptance.ps1`
- `scripts/reset_local_admin_database.ps1`
- `package.json`
- `README.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run quality
npm run admin:build
npm run m2:acceptance
npm run db:baseline:verify
```

## Risks / open questions

- Brak pytań blokujących. Reset jest celowo destrukcyjny dla developerskich
  danych i dlatego nie zostanie wykonany automatycznie w ramach zadania.

## Outcome

Zadanie ukończone 2026-07-27. Końcowa bramka G2 została zaliczona, a M2
zamknięty.

### Changed

- Dodano pełny test akceptacyjny przez TestClient, prawdziwe zależności
  repozytoriów, migracje Alembic i izolowany PostgreSQL.
- Scenariusz tworzy 12 symboli, trzy poziome linie, 34 payout rules, publikuje
  reguły, generuje 1000 layoutów, sprawdza sześć grup duplikatów, podgląd oraz
  publikację datasetu.
- Dodano osobną komendę `m2:acceptance`.
- Dodano bezpieczny reset developerski wymagający `-ConfirmReset`, dokładnej
  bazy `game_predictor` i połączenia loopback.
- Uporządkowano README lokalnej platformy administracyjnej.

### Verification results

- `npm run quality`: format, drift OpenAPI/klienta, lint, typy, 129 testów
  Python przeszło; 3 fizyczne testy są jawnie pomijane w standardowym przebiegu.
  Przeszły również 63 testy mobile, 44 panelu, 23 wspólnej domeny i 7 klienta.
- `npm run admin:build`: produkcyjny build Next.js przeszedł.
- `npm run m2:acceptance`: 1 pełny scenariusz HTTP/PostgreSQL przeszedł.
- `npm run db:baseline:verify`: 3 izolowane testy PostgreSQL przeszły.
- Reset bez `-ConfirmReset` oraz reset skierowany na inną nazwę bazy zostały
  odrzucone przed Dockerem i Alembic.

### Not completed

- Nie wykonano destrukcyjnego resetu bazy developerskiej.
- Nie rozpoczęto M3, trwałych jobs, precomputingu ani pipeline'u APK.

### Documentation updates

- Zaktualizowano README, strategię testów, roadmapę, plan M2 i
  `CURRENT_STATE.md`.
- Nowa decyzja architektoniczna nie była potrzebna.

### Recommended next task

- po kolejnym poleceniu właściciela:
  `TASK-0029 — Job state machine and Admin API`.
