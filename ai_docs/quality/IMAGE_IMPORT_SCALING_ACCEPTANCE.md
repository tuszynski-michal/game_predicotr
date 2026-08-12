---
title: Iterative image import scaling acceptance
status: ready_for_owner_run
release: "0.5"
last_updated: 2026-08-09
---

# Odbiór skalowania iteracyjnego importu

## Cel

Pomiar jest obserwacyjny: nie zmienia algorytmu, profilu siatki ani modelu
symboli. Właściciel uruchamia kolejno partie 10, 100 i 1000 zdjęć. Partia 5000
jest wykonywana dopiero po akceptacji kosztu jednostkowego mniejszych prób.

## Pomiar

Po utworzeniu partii skopiuj identyfikator joba i w osobnym PowerShell uruchom:

```powershell
npm run image-import:measure -- -JobId <JOB_ID> -OutputPath artifacts/v05-import-scale/<LICZBA>.json
```

Skrypt ma jawny timeout, odczytuje trwały stan joba oraz co dwie sekundy mierzy
working set procesu general workera. Raport zawiera:

- liczbę zdjęć i stan końcowy,
- czas całkowity, sekundy na zdjęcie i zdjęcia na minutę,
- peak working set procesu workera,
- trwałe liczności etapów,
- bounded próbki postępu, etapu i pamięci.

Panel Import Layoutów pokazuje te same podstawowe czasy i throughput dla
ostatnich dziesięciu zakończonych partii również po restarcie interfejsu.

## Bramka

Wypełnij po pomiarze:

| Partia | Czas | s/zdjęcie | zdjęcia/min | peak RSS | Wynik |
|---:|---:|---:|---:|---:|---|
| 10 | — | — | — | — | oczekuje |
| 100 | — | — | — | — | oczekuje |
| 1000 | — | — | — | — | oczekuje |
| 5000 | — | — | — | — | odroczone |

Koszt jednostkowy nie powinien rosnąć systematycznie wraz z wielkością partii.
Różnice wynikające z cache, pierwszego uruchomienia OCR i małej próby należy
opisać, a nie ukrywać. Ostateczny budżet czasu pozostaje decyzją właściciela po
realnym pomiarze.
