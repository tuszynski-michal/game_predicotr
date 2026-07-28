---
title: Milestone 05 execution plan
status: completed
last_updated: 2026-07-28
---

# Plan wykonania Milestone 05 — Image ingestion prototype

## Status

`completed_calibrated_manual_review_only_ocr` — TASK-0051–0058 oraz korekty
TASK-0092 i TASK-0094–0096 są ukończone. Detektorowy wariant v2 pozostaje
historycznym artefaktem w kwarantannie, natomiast skalibrowany cropper
`board-cell-crops-v2-calibrated-v1` osiągnął P95 linii `1.8337 px` wobec
budżetu `5 px`. G5.3 ponownie przeszła, a M6.1 jest odblokowane.

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
- D-006, D-010, D-014 i D-059 w `process/DECISION_LOG.md`

## Warunki wejścia

- M4 przechodzi G4.
- Właściciel odpowiada na Q-016–Q-017; wszystkie pytania zamknięto.
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
- oczekiwane obszary strony, 1–9 layoutów i numery,
- format golden annotations,
- mierzalne metryki oraz zaakceptowane progi,
- zasady przechowywania oryginałów i diagnostyki.

### Zadania

- `TASK-0051 — Representative image corpus and golden annotations` — done
  2026-07-28
- `TASK-0092 — M5 corpus, variable final page and OCR rework` — done
  2026-07-28

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
- oczekiwana siatka do 3 × 3, z krótszą wyłącznie ostatnią stroną,
- confidence oraz narożniki,
- indywidualna korekta perspektywy każdego mini-layoutu,
- podział planszy 3 × 5 z marginesem od ramki,
- niezależny golden granic komórek,
- wersjonowane profile kalibracji dla wyjątków,
- diagnostyczne overlaye i wycinki.

### Zadania

- `TASK-0054 — Page and 3x3 board detection` — done 2026-07-28
- `TASK-0055 — Per-board perspective correction and cell crops` — done
  2026-07-28; artefakty v1 zachowane historycznie, podział komórek odrzucony
- `TASK-0094 — Cell-grid golden annotations and crop quality gate` — done
  2026-07-28; 27/27 ręcznie skorygowanych quadów, baseline v1 odrzucony
- `TASK-0095 — Board cell cropper v2 and corpus regeneration` — done
  2026-07-28; 43 obrazów, 387 plansz i 5805 komórek, P95 linii `42.1563 px`,
  `trainingAllowed = false`
- `TASK-0096 — Grid calibration profiles and perspective editor` — done
  2026-07-28; 18 profili, 27 anchorów, 43 obrazy, 387 plansz i 5805 komórek,
  P95 linii `1.8337 px`, `trainingAllowed = true`

### Bramka G5.3

- metryki geometrii są policzone na całym golden corpus,
- błąd jednego layoutu nie przesuwa indeksów pozostałych po cichu,
- niski confidence tworzy jawny wynik wymagający review,
- wycinki mają udokumentowany układ i wersję pipeline’u,
- niezależny golden obejmuje obie grupy źródłowe i każdą z dziewięciu pozycji,
- P95 błędu linii croppera v2 wynosi najwyżej 5 px, a wszystkie zaakceptowane
  golden komórki zawierają jeden właściwy symbol bez przecięcia jego głównej
  sylwetki,
- profil kalibracji jest stosowany do zadeklarowanej grupy/pozycji, nie wymaga
  ręcznego ustawienia 387 layoutów i nie nadpisuje artefaktów,
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
  2026-07-28; po rozszerzeniu baseline `247/387 = 63.8243%`, dlatego adapter
  pozostaje `manual_review_only`

### Bramka G5.4

- accuracy OCR jest policzone na golden corpus,
- wynik przechowuje raw, normalized i confidence,
- konflikt numerów trafia do jawnego błędu/review,
- ciągłość nie zastępuje rozpoznanej wartości bez śladu,
- adapter OCR można wymienić bez zmiany stagingu.

Kontrakt i metryka są gotowe, ale zaakceptowany próg 98% dla auto-accept nie
został osiągnięty. G5.4 jest zaliczone wyłącznie dla ścieżki
`manual_review_only`: każdy numer wymaga potwierdzenia i nie wolno publikować
wartości tylko dlatego, że OCR zwrócił wynik.

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
  po korekcie rekomendacja `enter_m6`
- `TASK-0058 — Image prototype architecture decision` — done 2026-07-28;
  D-056 zachowała kontrakty i zablokowała auto-accept OCR
- `TASK-0092 — M5 corpus, variable final page and OCR rework` — done
  2026-07-28; D-057 otwiera M6

### Bramka G5

- korpus 20–100 zdjęć ma kompletny raport,
- geometria i OCR osiągają wcześniej zaakceptowane progi albo milestone kończy
  się decyzją `blocked/rework`, nie ukrytym obejściem,
- wersje bibliotek i algorytmów są zapisane,
- niepewne wyniki mają dane potrzebne przyszłemu manual review,
- finalny wybór adapterów trafia do Decision Log,
- nie rozpoczęto jeszcze treningu produkcyjnego klasyfikatora ani masowego
  importu.

Po TASK-0092 benchmark v2 obejmuje 43 zdjęcia i 387 layoutów. Detekcja
oczekiwanego zbioru pozycji, kompletność pozycji i zaakceptowane golden
narożniki mają wynik 100%; pipeline utworzył 5805 cell crops. Golden geometria
była zainicjalizowana przez detektor i zaakceptowana po wizualnym przeglądzie,
więc zerowy błąd narożników nie jest niezależnym ręcznym pomiarem.

OCR osiągnął 63.8243%, a held-out 64.1577%, zatem nie uzyskał prawa do
auto-accept. Przegląd właściciela ujawnił, że globalny inset v1 przecina
symbole. Korekta TASK-0094–0096 dodała niezależny golden, profile kalibracji
i osobny skalibrowany korpus. G5 ma status
`passed_calibrated_manual_review_only_ocr`; status OCR pozostaje
`manual_review_only`.

## Mapa zadań M5

| Podetap | Zadania | Liczba |
|---|---:|---:|
| M5.1 Korpus | TASK-0051, TASK-0092 (korekta) | 2 |
| M5.2 Discovery i normalizacja | TASK-0052–0053 | 2 |
| M5.3 Geometria i korekta siatki | TASK-0054–0055, TASK-0094–0096 | 5 |
| M5.4 OCR | TASK-0056 | 1 |
| M5.5 Benchmark i decyzja | TASK-0057–0058 | 2 |
| **Razem M5** | **TASK-0051–0058 + TASK-0092, TASK-0094–0096** | **12** |

## Następny milestone

M6.1 jest odblokowane. Obowiązuje `MILESTONE_06_EXECUTION_PLAN.md`;
pełnolayoutowy bootstrap TASK-0097 tworzy pierwsze rzeczywiste decyzje symboli,
po czym TASK-0059 dokończy eksport oznaczonego datasetu.
