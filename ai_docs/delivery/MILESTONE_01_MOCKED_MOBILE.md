---
title: Milestone 01 - offline mocked mobile vertical slice
status: accepted
last_updated: 2026-07-24
---

# Milestone 01 — działający offline pion mobilny na mock data

## Cel

Zbudować samodzielnie instalowalne APK Android, które bez sieci identyfikuje layout i oblicza pełny Target na danych dołączonych do aplikacji.

## Sposób realizacji

M1 jest za duży na jedno zadanie implementacyjne. Obowiązujący podział na
M1.1–M1.6, zależności i bramki jakości znajdują się w
[MILESTONE_01_EXECUTION_PLAN.md](MILESTONE_01_EXECUTION_PLAN.md).

Ten dokument jest właścicielem zakresu produktu i końcowych kryteriów akceptacji
M1. Execution Plan jest właścicielem kolejności prac i granic poszczególnych
zadań.

## Zakres

### Repozytorium

Minimalny pion obejmuje:

```text
apps/mobile
services/worker lub scripts/snapshot
packages/shared-ts
ai_docs
```

Admin API i PostgreSQL powstają w M2. M1 może użyć deterministycznego generatora i lokalnego narzędzia build-time do utworzenia fixture SQLite.

### Snapshot

- 3 gry,
- 1000 layoutów na grę,
- konfiguracja planszy i symboli,
- indeks exact/prefix,
- gotowy payout każdego layoutu,
- wersja schematu, datasetu, reguł i algorytmu,
- checksum oraz test integralności,
- baza dołączona do APK i materializowana/otwierana lokalnie zgodnie z wymaganiami `expo-sqlite`,
- wersja lub checksum w nazwie aktywnej kopii, aby aktualizacja APK nie użyła
  starego snapshotu.

### Mobile

- wybór gry,
- plansza 3 × 5,
- wybór symboli,
- undo,
- reset,
- lokalny partial prefix matching,
- modal unique candidate,
- local exact matching,
- stany `unique`, `duplicate`, `not_found`, `local_data_error`,
- pełny Target `N - 1`,
- tabela dodatnich lokalnych maksimów na dole,
- wirtualizowane renderowanie,
- ekran diagnostyczny lub informacja o wersji snapshotu.

### Logika build-time

- deterministyczny generator mock danych,
- walidator ciągłości numerów,
- payout evaluation według testowych reguł,
- generator SQLite,
- golden report pozwalający porównać forecast mobile z oczekiwanym wynikiem.

## Mock configuration

### Games

- `game-1`: 3 × 5, 10 symboli,
- `game-2`: 3 × 5, 12 symboli,
- `game-3`: 3 × 5, 11 symboli, w tym jeden joker.

Każda gra ma `spin_cost = 10`, o ile fixture nie opisuje jawnie innego przypadku testowego.

### Layout generation

- deterministyczny generator,
- seed zapisany w kodzie i manifeście,
- `sequence_number` 1..1000 bez luk,
- 5–10 kontrolowanych przypadków zduplikowanej sygnatury na grę,
- co najmniej jeden unikalny layout, którego prefiks staje się unikalny przed końcem planszy,
- dane zapewniają przypadki forecastu: brak plusa, pojedynczy szczyt, kilka szczytów, późniejszy niższy szczyt i plateau,
- generator jest idempotentny.

### Paylines

Fixture zawiera co najmniej:

```text
[0,0,0,0,0]
[1,1,1,1,1]
[2,2,2,2,2]
[0,1,2,1,0]
[2,1,0,1,2]
```

Nie występuje `CONSECUTIVE_COLUMNS_ANY_ROW`.

### Payout rules

Wartości są testowe, np.:

```text
S1: 3 = 100, 4 = 300, 5 = 900
S2: 3 = 150, 4 = 450, 5 = 1350
S3: 3 = 200, 4 = 600, 5 = 1800
```

Pozostałe symbole otrzymują jawne fixture. Joker nie ma własnego payoutu.

## Granularność zadań

- Nie wolno realizować pełnego M1 w jednym tasku.
- Jedno zadanie obejmuje jeden wynik z mapy w Execution Plan.
- Plik zadania powstaje bezpośrednio przed rozpoczęciem danego zakresu.
- Następny podetap zaczyna się dopiero po przejściu bramki poprzedniego.
- Pierwszym zadaniem implementacyjnym będzie wyłącznie
  `TASK-0002 — Monorepo and offline SQLite spike`.

## Kryteria akceptacyjne

### Uruchomienie

- jedna instrukcja instaluje zależności i generuje snapshot,
- jedna jawna komenda buduje instalowalne APK,
- APK uruchamia się bez komputera deweloperskiego,
- tryb samolotowy lub całkowity brak sieci nie zmienia funkcjonalności,
- nie trzeba konfigurować adresu API,
- finalne APK nie deklaruje uprawnienia `INTERNET`.

### Dane

- snapshot zawiera dokładnie 3 gry,
- każda gra ma dokładnie 1000 layoutów,
- numery są ciągłe 1..1000,
- istnieje 5–10 kontrolowanych przypadków duplikatów treści na grę,
- payout każdego layoutu jest gotowy,
- manifest i checksum przechodzą walidację,
- aktualizacja do APK z nową wersją fixture aktywuje nowy snapshot.

### Mobile behavior

- symbole są wprowadzane `row-major`,
- Undo i Reset działają,
- zmiana gry czyści stan,
- unikalny prefiks otwiera modal bez pętli po zamknięciu,
- akceptacja uzupełnia brakujące pola jako jeden krok undo,
- pełny unique pokazuje numer i uruchamia Target,
- duplicate nie pokazuje Target i nie zachowuje kontekstu po Reset,
- not found pozwala poprawić layout,
- dla 1000 layoutów ocenianych jest dokładnie 999 spinów z poprawnym zawijaniem,
- spin 0 nie ma kosztu ani payoutu,
- każdy kolejny spin dodaje payout i odejmuje koszt,
- zero nie jest wynikiem dodatnim,
- tabela pokazuje dodatnie lokalne maksima, także późniejszy niższy szczyt,
- plateau wskazuje pierwszy spin,
- tabela jest na dole i pozostaje płynnie przewijalna.

### Kompatybilność

- test manualny przechodzi na Google Pixel 10 Pro XL,
- test manualny przechodzi na Samsung Galaxy S21 Ultra,
- układ nie wymaga poziomego przewijania całej strony,
- ważne komunikaty nie polegają wyłącznie na kolorze.

### Jakość

- testy matching obejmują 0, 1 i wiele wyników,
- testy payout obejmują długości 3/4/5, joker, przecięcie paylines i sumowanie,
- testy Target obejmują cykl, koszt, kumulację i lokalne szczyty,
- test reducer obejmuje ręczne i automatyczne uzupełnienie,
- test repozytorium potwierdza indeksy i integralność SQLite,
- lint, format, typecheck i testy przechodzą,
- rozmiar APK/snapshotu oraz czasy kluczowych operacji są zapisane w Outcome,
- instalacja nowej wersji nie używa po cichu SQLite ze starego wydania.

## Poza zakresem

- prawdziwe obrazy symboli,
- panel administracyjny,
- FastAPI i PostgreSQL,
- import rzeczywistych datasetów,
- OCR, OpenCV i trening modelu,
- auth,
- synchronizacja i backend mobilny,
- publiczna dystrybucja.

## Demo

1. Zainstaluj APK na telefonie.
2. Wyłącz sieć.
3. Wybierz `game-1`.
4. Wprowadź prefiks przygotowanego unikalnego layoutu.
5. Zaakceptuj modal i zobacz numer sekwencji.
6. Przewiń do tabeli i porównaj lokalne szczyty z golden fixture.
7. Wykonaj Reset.
8. Wprowadź zduplikowany layout.
9. Zobacz komunikat `duplicate` i brak prognozy.
10. Wykonaj Reset i wprowadź kolejny layout jako nowe wyszukiwanie.
