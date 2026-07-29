---
title: Milestone 07 execution plan
status: accepted
last_updated: 2026-07-24
---

# Plan wykonania Milestone 07 — Large-scale resumable image import

## Cel

Połączyć zatwierdzone adaptery M5–M6 z trwałym job lifecycle, stagingiem M4 i
publikacją M3 w jeden wersjonowany, wznawialny pipeline dużych katalogów zdjęć.

`ROADMAP.md` jest właścicielem granic milestone’u, a ten dokument jest
właścicielem kolejności podetapów, rezerwacji zadań i bramek jakości M7.

## Relevant docs

- `requirements/IMAGE_INGESTION.md`
- `requirements/ADMIN_APP.md`
- `architecture/SYSTEM_ARCHITECTURE.md`
- `architecture/DATA_MODEL.md`
- `architecture/API_CONTRACT.md`
- `quality/TEST_STRATEGY.md`
- D-005, D-006, D-010 i D-014 w `process/DECISION_LOG.md`

## Warunki wejścia

- M6 przechodzi G6.
- Format stagingu M4 i release pipeline M3 są stabilne.
- Wszystkie modele i progi mają zaakceptowane wersje.

## Zasady realizacji

- początkowo wykonywany jest najwyżej jeden ciężki job naraz,
- pipeline zapisuje checkpointy i jest idempotentny per plik oraz wersja,
- błąd jednego zdjęcia nie zatrzymuje całego katalogu,
- oryginały i opublikowane wersje nie są usuwane automatycznie,
- kolejka lub nowy adapter wymagają wyników benchmarku i Decision Log,
- plik zadania powstaje bezpośrednio przed rozpoczęciem zakresu.

## M7.1 — Kontrakt i orkiestracja pipeline’u

### Zakres

- wersjonowany manifest wejścia, pipeline’u, OCR i modelu,
- etapy oraz checkpointy,
- bezpieczne wznowienie i anulowanie,
- idempotency keys per plik i wersja pipeline’u,
- jedna ciężka praca naraz,
- stan `waiting_for_review`.

### Zadania

- `TASK-0068 — Versioned image pipeline contract` — done 2026-07-29;
  kanoniczny manifest, fingerprint całego pipeline'u, idempotency key per plik
  oraz persistence-neutral checkpoint wymuszający manual review,
- `TASK-0069 — Batch orchestration, checkpoints and cancellation` — done
  2026-07-29; globalne file executions, job associations, fenced checkpoint,
  restart, cancellation i review-after-diagnostics,

### Bramka G7.1

- restart procesu nie traci postępu,
- anulowanie nie publikuje częściowego datasetu,
- ten sam plik/wariant nie tworzy podwójnych wyników,
- zmiana modelu tworzy nowy wynik, a nie nadpisuje starego bez śladu,
- review zatrzymuje publikację, ale nie blokuje diagnostyki pozostałych plików.

Status: `passed` 2026-07-29. Fizyczny test PostgreSQL jest gotowy, lecz przy
odbiorze pozostał jawnym skipem z powodu niedostępnego lokalnego portu 5432;
kontrakt, migracja offline, symulacje restart/cancellation i wspólny runtime
przeszły.

## M7.2 — Integracja etapów i izolacja błędów

### Zakres

- discovery, normalizacja, geometria, OCR i ONNX w jobie,
- zapis recognized boards i review items,
- staging zatwierdzonych layoutów,
- retry pojedynczego pliku/etapu,
- błąd jednego zdjęcia bez zatrzymania całego katalogu,
- walidacja ciągłości między zdjęciami.

### Zadania

- `TASK-0070 — End-to-end image processing into staging` — done 2026-07-29;
  wersjonowany composer sześciu adapterów, trwałe source/board/cell/review oraz
  staging wyłącznie po atomowej decyzji planszy,
- `TASK-0071 — Failure isolation, retry and idempotency` — done 2026-07-29;
  błąd izolowany per plik, retry dokładnego etapu, rehydratacja globalnych
  wyników do job-local review oraz append-only decyzje i ponowne otwarcie
  konfliktów numeracji,

### Bramka G7.2

- każdy layout ma ślad do zdjęcia i wersji pipeline’u,
- pojedynczy błąd ma stabilny kod i nie przesuwa sekwencji po cichu,
- retry nie duplikuje crops, boards ani staging rows,
- nierozwiązany konflikt numeru trafia do review,
- staging zawiera wyłącznie zaakceptowane wartości.

## M7.3 — Operacje, statystyki i storage

### Zakres

- panel postępu per etap,
- statystyki correct/error/review,
- wznowienie i anulowanie z UI,
- czas i throughput,
- wersjonowane ścieżki originals/working/crops/models/exports,
- kontrola retencji bez automatycznej destrukcji danych,
- diagnostyczny eksport błędów.

### Zadania

- `TASK-0072 — Image job operations and statistics UI`
- `TASK-0073 — File storage lifecycle and diagnostic exports`

### Bramka G7.3

- panel nie wymaga czytania surowych logów do oceny stanu,
- liczby w UI zgadzają się z trwałymi rekordami,
- ścieżki są względne i pozostają w dozwolonych katalogach,
- żaden oryginał ani zaakceptowana wersja nie jest usuwana bez jawnej operacji,
- eksport diagnostyczny nie zawiera sekretów ani niełamanych ścieżek.

## M7.4 — Testy obciążeniowe i jakość operacyjna

### Zakres

- reprezentatywny duży katalog,
- obciążenie PostgreSQL i storage,
- pamięć, CPU, czas na zdjęcie i throughput,
- odsetek review i trwałych błędów,
- próby restartu, awarii i wznowienia,
- ocena potrzeby kolejki lub zmiany adaptera.

### Zadania

- `TASK-0074 — Large import database and storage load tests`
- `TASK-0075 — Import quality, recovery and review throughput benchmark`

### Bramka G7.4

- pipeline nie ładuje całego katalogu do pamięci,
- restart i wznowienie są przetestowane w kilku etapach,
- baza i storage mają zapisane pomiary oraz wąskie gardła,
- liczba review jest zgodna z zaakceptowanymi progami operacyjnymi,
- dodatkowa kolejka nie jest wprowadzana bez wyników tego benchmarku.

## M7.5 — Publikacja dużej wersji danych

### Zakres

- zamknięcie review,
- pełna walidacja numerów, symboli i komórek,
- publikacja niezmiennego datasetu,
- precomputing payoutów,
- snapshot i APK,
- końcowa decyzja o pozostaniu przy jednym workerze.

### Zadania

- `TASK-0076 — Large image dataset publication and mobile release`
- `TASK-0077 — Queue and pipeline architecture decision`

### Bramka G7

- duży katalog przechodzi processing, review, restart i publikację,
- nie ma luk ani duplikatów `sequence_number`,
- duplikaty sygnatur są raportowane zgodnie z domeną,
- release pipeline tworzy zweryfikowany APK z opublikowanego datasetu,
- wszystkie wejścia, modele, korekty i artefakty mają wersje,
- pozostanie przy jednym workerze albo zmiana architektury jest uzasadniona
  pomiarami i zapisana w Decision Log.

## Mapa zadań M7

| Podetap | Zadania | Liczba |
|---|---:|---:|
| M7.1 Orkiestracja | TASK-0068–0069 | 2 |
| M7.2 Integracja etapów | TASK-0070–0071 | 2 |
| M7.3 Operacje i storage | TASK-0072–0073 | 2 |
| M7.4 Obciążenie i jakość | TASK-0074–0075 | 2 |
| M7.5 Publikacja | TASK-0076–0077 | 2 |
| **Razem M7** | **TASK-0068–0077** | **10** |

## Następny milestone

Po przejściu G7 i zamknięciu Q-019 obowiązuje
`MILESTONE_08_EXECUTION_PLAN.md`.
