---
title: Milestone 07.0 fast representative image selection execution plan
status: accepted
release: "0.4"
last_updated: 2026-08-02
---

# M7.0 — Selekcja reprezentatywnych zdjęć

## Cel

Dostarczyć osobny moduł, który redukuje folder 10 000–30 000 kolejnych zdjęć do
jednego bezpiecznego reprezentanta na unikalny zakres sekwencji, zanim zostanie
uruchomiony kosztowny `Import layoutów`.

## Pozycja w planie

- M7.0 należy do wersji 0.4 i może być implementowany po zamknięciu odbioru 0.2.
- Nie wymaga zakończenia treningu M6.6, ponieważ nie klasyfikuje symboli.
- Handoff do pełnego pipeline'u i masowe użycie wymagają późniejszych bramek
  M6.6 oraz M7, rozpoczynanych w wersji 0.5.
- TASK-0076 należy do wersji 0.5 i nie może rozpocząć pełnego importu przed
  przejściem TASK-0157.

## Kolejność zadań

| Kolejność | Zadanie | Rezultat |
|---:|---|---|
| 1 | TASK-0151 | model domenowy, migracja i typowany kontrakt runu |
| 2 | TASK-0152 | czwarty workspace oraz skalowalny upload folderu |
| 3 | TASK-0153 | szybkie grupowanie, quality gate i wybór automatyczny |
| 4 | TASK-0154 | niezmienny output, nazwy, manifest i handoff do importu |
| 5 | TASK-0155 | kolejka manualna i wybór pojedynczego zdjęcia |
| 6 | TASK-0156 | joby, checkpointy, retry, anulowanie i diagnostyka |
| 7 | TASK-0157 | benchmark 10k/30k, golden jakości i odbiór właściciela |

## Piony wykonawcze

### M7.0.1 — Fundament

TASK-0151–0152 tworzą schemat, API, generowany klient, upload i pusty workspace.
Nie implementują jeszcze automatycznej decyzji jakościowej.

### M7.0.2 — Automatyczna selekcja

TASK-0153 implementuje `fast-image-selector-v1` na małym korpusie golden.
Wynik nie może jeszcze uruchamiać pełnego importu, dopóki nie powstanie
checksumowany output TASK-0154.

### M7.0.3 — Domknięcie użytkowe

TASK-0154–0155 dodają wynik, handoff i manualne rozstrzygnięcia. Oryginały
użytkownika pozostają nietknięte.

### M7.0.4 — Operacje i skala

TASK-0156–0157 domykają niezawodność, statystyki i mierzalną bramkę wydajności.

## Bramka M7.0

- workspace pokazuje aktywną grę, upload, postęp, wynik i kolejkę manualną,
- skok zakresów nie jest traktowany jako luka,
- późniejszy duplikat zakończonego zakresu nie tworzy drugiego outputu,
- zasłonięte, przycięte i nierozpoznane zdjęcia nie są automatycznie wybierane,
- output ma jedno zdjęcie na zakres, bez modyfikacji folderu wejściowego,
- manualny modal działa myszą i klawiaturą zgodnie z wymaganiami,
- handoff uruchamia istniejący import dopiero po jawnej akcji,
- restart workera wznawia run bez powtarzania zakończonych grup,
- test 10 000 mieści się w 15 minutach, a 30 000 w 45 minutach na komputerze
  właściciela albo zadanie wraca do optymalizacji,
- benchmark nie pozostawia osieroconego procesu i ma własny twardy timeout.

## Zakres świadomie odłożony

- automatyczne uczenie progów z decyzji manualnych,
- wiele równoległych workerów,
- przechowywanie źródeł w chmurze,
- obsługa formatów innych niż JPEG,
- automatyczne kasowanie historycznych wyników selekcji,
- pełny import 500 000 layoutów przed bramką M6.6/M7 i rozpoczęciem wersji 0.5.
