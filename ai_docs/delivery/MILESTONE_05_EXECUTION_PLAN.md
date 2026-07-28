---
title: Milestone 05 execution plan
status: accepted
last_updated: 2026-07-28
---

# Plan wykonania Milestone 05 — Image ingestion prototype

## Status zamknięcia

`completed_with_rework` — TASK-0052–0058 są ukończone, TASK-0051 pozostaje
`blocked` na reprezentatywnym materiale i odpowiedziach Q-016/Q-017. G5 nie
przeszło, dlatego M6 nie może się rozpocząć. D-056 zachowuje kontrakty, lecz
kieruje geometrię do dalszej walidacji, a implementację OCR do reworku.

## Cel

Zweryfikować na 20–100 reprezentatywnych zdjęciach, czy klasyczna geometria,
indywidualne prostowanie mini-layoutów i ograniczony OCR cyfr dają mierzalny,
powtarzalny fundament. M5 nie jest jeszcze masowym importerem ani finalnym
klasyfikatorem symboli.

`ROADMAP.md` jest właścicielem granic milestone’u, a ten dokument jest
właścicielem kolejności podetapów, rezerwacji zadań i bramek jakości M5.

## Relevant docs

- `requirements/IMAGE_INGESTION.md`
- `requirements/ADMIN_APP.md`
- `architecture/SYSTEM_ARCHITECTURE.md`
- `architecture/DATA_MODEL.md`
- `architecture/TECH_STACK.md`
- `quality/TEST_STRATEGY.md`
- Q-015–Q-017 w `project/OPEN_QUESTIONS.md`
- D-006, D-010 i D-014 w `process/DECISION_LOG.md`

## Warunki wejścia

- M4 przechodzi G4.
- Właściciel odpowiada na Q-016–Q-017; Q-015 zamknięto decyzją D-050.
- Dostępny jest zatwierdzony korpus 20–100 zdjęć i zasady jego użycia.
- Zanim rozpocznie się implementacja, mierzalne progi dla geometrii i OCR
  zostają zapisane w zadaniu M5.1.

Na podstawie D-049 dopuszczono wcześniejsze rozpoczęcie wyłącznie TASK-0051
jako pracy nad korpusem, ground truth i progami. Nie zalicza to G3 i nie
pozwala rozpocząć automatycznego pipeline'u M5.2–M5.5 bez pozostałych wejść.

Na podstawie D-050 obecne 12 zdjęć z jednej sesji tworzy korpus prototypowy.
Można na nim rozwijać kontrakty i pierwszy prototyp, ale nie spełnia jeszcze
warunku reprezentatywnego korpusu 20–100 zdjęć ani bramki G5.1.

Na podstawie D-051 właściciel dopuścił rozpoczęcie read-only TASK-0052, aby
kolejne zdjęcia mogły być deterministycznie wykrywane i dołączane później.
Wyjątek nie obejmuje TASK-0053+, geometrii, OCR ani zaliczenia G5.1.

Na podstawie D-052 po ukończeniu discovery właściciel dopuścił TASK-0053,
ograniczone do EXIF, lokalnych kopii roboczych i diagnostyki. Nie otwiera to
TASK-0054+, geometrii, OCR ani bramki G5.1.

Na podstawie D-053 właściciel dopuścił TASK-0054 dla jedynego potwierdzonego
wariantu 3 × 3. Inne warianty muszą trafić do review; Q-016 i niezależne golden
annotations nadal blokują deklarację uniwersalności i przejście progu accuracy.

Analiza aplikacji referencyjnej nie jest częścią ścieżki krytycznej.
Jakiekolwiek prace wykraczające poza obserwację wymagają odpowiedzi na Q-020.

## Zasady realizacji

- oryginalne zdjęcia pozostają niezmienione,
- geometria, OCR i klasyfikacja mają osobne wersjonowane adaptery,
- worker nie pobiera modeli ani danych podczas przetwarzania,
- jedna słaba metryka nie jest ukrywana przez wynik zagregowany,
- ciężki detektor nie jest dodawany bez porównania z geometrią klasyczną,
- plik zadania powstaje bezpośrednio przed rozpoczęciem zakresu.

## M5.1 — Korpus i golden annotations

### Zakres

- inwentaryzacja rozdzielczości, orientacji i wariantów,
- podział materiału bez przecieku między źródłami,
- oczekiwane obszary strony, 9 layoutów i numery,
- format golden annotations,
- mierzalne metryki oraz zaakceptowane progi,
- zasady przechowywania oryginałów i diagnostyki.

### Zadanie

- `TASK-0051 — Representative image corpus and golden annotations` — blocked
  od 2026-07-28; manifest 12 zdjęć i adnotacje sekwencji są gotowe, brakuje
  dodatkowych zdjęć, pełnej geometrii i odpowiedzi Q-016/Q-017

### Bramka G5.1

- korpus obejmuje uzgodnione warianty i trudne przypadki,
- każde zdjęcie ma stabilny identyfikator/checksumę,
- golden annotations można zweryfikować niezależnie od algorytmu,
- progi oraz sposób liczenia metryk są zapisane przed optymalizacją,
- train/validation nie miesza wycinków z tego samego zdjęcia źródłowego.

## M5.2 — Discovery i normalizacja

### Zakres

- lokalne skanowanie folderu,
- wspierane formaty i metadata,
- checksumy oraz pomijanie znanego wejścia,
- EXIF, obrót i kopie robocze,
- brak modyfikacji oryginału,
- wersjonowane artefakty diagnostyczne.

### Zadania

- `TASK-0052 — Image discovery and source manifest` — done 2026-07-28
- `TASK-0053 — EXIF normalization and diagnostics` — done 2026-07-28

### Bramka G5.2

- ponowny przebieg daje ten sam manifest,
- oryginały pozostają niezmienione,
- uszkodzony lub niewspierany plik ma stabilny błąd,
- orientacja jest poprawna dla golden corpus,
- worker nie pobiera bibliotek, wag ani danych z sieci podczas przetwarzania.

## M5.3 — Geometria strony, layoutów i komórek

### Zakres

- detekcja obszaru ekranu i stabilnych cech,
- oczekiwana siatka 3 × 3,
- confidence oraz narożniki,
- indywidualna korekta perspektywy każdego mini-layoutu,
- podział planszy 3 × 5 z marginesem od ramki,
- diagnostyczne overlaye i wycinki.

### Zadania

- `TASK-0054 — Page and 3x3 board detection` — done 2026-07-28
- `TASK-0055 — Per-board perspective correction and cell crops` — done
  2026-07-28

### Bramka G5.3

- metryki geometrii są policzone na całym golden corpus,
- błąd jednego layoutu nie przesuwa indeksów pozostałych po cichu,
- niski confidence tworzy jawny wynik wymagający review,
- wycinki mają udokumentowany układ i wersję pipeline’u,
- nie wprowadzono ciężkiego detektora bez porównania z geometrią klasyczną.

## M5.4 — OCR numerów i walidacja ciągłości

### Zakres

- adapter OCR ograniczony do cyfr,
- crop numeru pod każdym layoutem,
- raw text, normalized number i confidence,
- wykorzystanie ciągłości jako walidacji,
- brak cichego poprawiania OCR na podstawie sąsiadów,
- raport konfliktów i luk.

### Zadanie

- `TASK-0056 — Sequence number OCR and continuity validation` — done
  2026-07-28; baseline `68/108 = 62.9630%`, G5.4 pozostaje niezaliczona

### Bramka G5.4

- accuracy OCR jest policzone na golden corpus,
- wynik przechowuje raw, normalized i confidence,
- konflikt numerów trafia do jawnego błędu/review,
- ciągłość nie zastępuje rozpoznanej wartości bez śladu,
- adapter OCR można wymienić bez zmiany stagingu.

Kontrakt i metryka są gotowe, ale proponowany próg 98% nie został osiągnięty.
TASK-0057 ma porównać przypadki błędów i koszt poprawy; nie wolno oznaczyć G5.4
jako `passed` wyłącznie dlatego, że wszystkie pozycje otrzymały raport.

## M5.5 — Benchmark i decyzja o stosie

### Zakres

- wspólny runner korpusu,
- metryki per etap i per typ zakłócenia,
- czas na zdjęcie i rozmiar artefaktów,
- katalog przypadków nieobsłużonych,
- porównanie alternatywy tylko dla etapu niespełniającego progu,
- decyzja o zaakceptowaniu lub zmianie stosu.

### Zadania

- `TASK-0057 — Geometry and OCR benchmark report` — done 2026-07-28;
  rekomendacja `rework`, G5 niezaliczone
- `TASK-0058 — Image prototype architecture decision` — done 2026-07-28;
  D-056 zachowuje kontrakty, blokuje auto-accept OCR i start M6

### Bramka G5

- korpus 20–100 zdjęć ma kompletny raport,
- geometria i OCR osiągają wcześniej zaakceptowane progi albo milestone kończy
  się decyzją `blocked/rework`, nie ukrytym obejściem,
- wersje bibliotek i algorytmów są zapisane,
- niepewne wyniki mają dane potrzebne przyszłemu manual review,
- finalny wybór adapterów trafia do Decision Log,
- nie rozpoczęto jeszcze treningu produkcyjnego klasyfikatora ani masowego
  importu.

TASK-0057 potwierdził 100% detekcji strony/kompletu plansz na obecnych 12
zdjęciach, ale nie mógł zmierzyć golden pozycji/narożników. OCR osiągnął
62.9630%, a kontrola na surowym cropie 42.5926%. Korpus jest poniżej minimum,
progi pozostają `proposed`, dlatego bramka G5 ma status `not_passed/rework`.
D-056 kończy implementacyjny prototyp M5, ale nie zmienia statusu bramki.

## Mapa zadań M5

| Podetap | Zadania | Liczba |
|---|---:|---:|
| M5.1 Korpus | TASK-0051 | 1 |
| M5.2 Discovery i normalizacja | TASK-0052–0053 | 2 |
| M5.3 Geometria | TASK-0054–0055 | 2 |
| M5.4 OCR | TASK-0056 | 1 |
| M5.5 Benchmark i decyzja | TASK-0057–0058 | 2 |
| **Razem M5** | **TASK-0051–0058** | **8** |

## Następny milestone

Po przejściu G5 i zapewnieniu oznaczonego zbioru symboli obowiązuje
`MILESTONE_06_EXECUTION_PLAN.md`.
