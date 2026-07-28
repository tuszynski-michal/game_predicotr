---
title: Milestone 04 execution plan
status: accepted
last_updated: 2026-07-28
---

# Plan wykonania Milestone 04 — Manual data import

## Cel

Przyjąć duże, zewnętrznie przygotowane pliki CSV/JSON do stagingu, zweryfikować
je, wznowić po przerwaniu i opublikować dataset bez zależności od OCR lub
klasyfikatora obrazów.

`ROADMAP.md` jest właścicielem granic milestone’u, a ten dokument jest
właścicielem kolejności podetapów, rezerwacji zadań i bramek jakości M4.

## Relevant docs

- `requirements/ADMIN_APP.md`
- `requirements/ALGORITHMS.md`
- `architecture/SYSTEM_ARCHITECTURE.md`
- `architecture/DATA_MODEL.md`
- `architecture/API_CONTRACT.md`
- `quality/TEST_STRATEGY.md`
- D-005–D-008 i D-014 w `process/DECISION_LOG.md`

## Warunki wejścia

- M3 przechodzi G3.
- Format `cells`, sygnatury i wersji datasetu jest stabilny.
- Job lifecycle oraz publikacja są wznawialne i idempotentne.

Na podstawie D-041 właściciel dopuścił warunkowe rozpoczęcie implementacji M4
przed zebraniem fizycznych dowodów G3. Nie oznacza to zaliczenia M3: TASK-0039,
TASK-0041 i TASK-0042 pozostają zablokowane, a pełny benchmark obu telefonów
oraz raport `passed` są obowiązkowe po M4 i przed M5.

## Zasady realizacji

- pliki trafiają najpierw do stagingu i nigdy bezpośrednio do wydania,
- import działa partiami i nie ładuje całego datasetu do pamięci,
- `sequence_number` pozostaje wartością domenową,
- duplikaty sygnatur są dozwolone, ale duplikaty numeru nie,
- operacje usuwające staging wymagają jawnego celu i potwierdzenia,
- OCR i przetwarzanie zdjęć pozostają poza zakresem M4.

## M4.1 — Kontrakt pliku i utworzenie importu

### Zakres

- wersjonowany format CSV i JSON,
- kodowanie, nagłówki, `sequence_number` i `cells`,
- limit rozmiaru i walidacja wejścia,
- checksum pliku i klucz idempotencji,
- bezpieczna ścieżka lokalna,
- podgląd pierwszych błędów bez publikacji.

### Zadania

- `TASK-0043 — CSV and JSON import contracts` — done 2026-07-27
- `TASK-0044 — Import job creation, checksums and path safety` — done 2026-07-27

### Bramka G4.1

- schemat pliku ma wersję i przykłady,
- nieznana wersja, zły nagłówek lub kodowanie daje stabilny błąd,
- ten sam plik i kontrakt nie tworzą drugiego importu bez jawnej intencji,
- API nie przyjmuje dowolnej ścieżki wychodzącej poza dozwolony katalog,
- podgląd nie modyfikuje opublikowanych danych.

G4.1 zaliczona 2026-07-27.

## M4.2 — Streaming, staging i wznowienie

### Zakres

- przetwarzanie w małych partiach,
- checkpoint pozycji pliku,
- normalizacja komórek i stałoszeroka sygnatura,
- walidacja symboli i liczby komórek,
- izolacja błędnych wierszy,
- wznowienie bez duplikowania stagingu.

### Zadania

- `TASK-0045 — Streaming parser and resumable staging` — done 2026-07-27
- `TASK-0046 — Layout normalization and row validation` — done 2026-07-27

### Bramka G4.2

- import nie ładuje całego pliku do pamięci,
- przerwanie w połowie i wznowienie daje ten sam staging co jeden przebieg,
- błędny wiersz ma numer, kod i bezpieczny opis,
- poprawne wiersze nie są tracone przez pojedynczy błąd,
- staging nie jest widoczny dla wydania mobilnego.

G4.2 zaliczona 2026-07-27.

## M4.3 — Raport integralności i UI

### Zakres

- zakres oraz luki `sequence_number`,
- duplikaty numeru,
- duplikaty sygnatur,
- obce symbole i błędne wymiary,
- podgląd layoutu,
- lista błędów, filtry i statystyki,
- jawne odrzucenie nieopublikowanego importu.

### Zadania

- `TASK-0047 — Import integrity and duplicate reports` — ukończono 2026-07-27
- `TASK-0048 — Manual import administration UI` — ukończono 2026-07-28

### Bramka G4.3

- luki i duplikaty numerów blokują publikację,
- duplikaty sygnatur są raportowane i dozwolone,
- podgląd planszy odpowiada kolejności `row-major`,
- usunięcie stagingu wymaga wskazania celu i potwierdzenia,
- raporty są odtwarzalne dla tego samego importu.

G4.3 zaliczona 2026-07-28.

## M4.4 — Publikacja i odbiór dużego importu

### Zakres

- transakcyjne utworzenie dataset version,
- idempotentne ponowienie publikacji,
- powiązanie z source job,
- uruchomienie istniejącego release pipeline,
- test na reprezentatywnym dużym pliku.

### Zadania

- `TASK-0049 — Transactional dataset publication from staging` — ukończono
  2026-07-28
- `TASK-0050 — Manual import scale and release acceptance` — ukończono
  2026-07-28

### Bramka G4

- duży CSV lub JSON przechodzi import, przerwę, wznowienie i walidację,
- wersja z błędem nie może zostać opublikowana,
- poprawna wersja jest niezmienna i ma ciągłą sekwencję,
- na jej podstawie powstaje zweryfikowany snapshot oraz APK,
- żaden etap nie używa OCR, zdjęć ani ręcznej edycji SQL,
- czasy, pamięć i liczba błędów są zapisane w Outcome.

G4 zaliczona warunkowo 2026-07-28. Reprezentatywny JSONL 500 000 rekordów
przeszedł kontrolowaną przerwę po checkpointcie, wznowienie tego samego joba,
walidację, idempotentną publikację, 500 000 payoutów oraz produkcyjny snapshot.
Po pierwszym błędzie uprawnień wygenerowanego katalogu Android dokładny,
niezmienny snapshot został wznowiony w kontrolowanym builderze i osadzony w
niezależnie zweryfikowanym APK bez uprawnienia `INTERNET`. Pełny raport,
łącznie z pierwszym błędem i recovery, znajduje się w
`quality/m4-import-acceptance-report.json`.

## Mapa zadań M4

| Podetap | Zadania | Liczba |
|---|---:|---:|
| M4.1 Kontrakt importu | TASK-0043–0044 | 2 |
| M4.2 Streaming i staging | TASK-0045–0046 | 2 |
| M4.3 Raporty i UI | TASK-0047–0048 | 2 |
| M4.4 Publikacja | TASK-0049–0050 | 2 |
| **Razem M4** | **TASK-0043–0050** | **8** |

## Następny krok

Zgodnie z D-041 po G4 trzeba wrócić do TASK-0041 i TASK-0042, zebrać fizyczne
benchmarki 500 000 layoutów na Pixelu i Samsungu oraz uzyskać raport G3
`passed`. Dopiero po G3 i zamknięciu Q-015–Q-017 można rozpocząć
`MILESTONE_05_EXECUTION_PLAN.md`.
