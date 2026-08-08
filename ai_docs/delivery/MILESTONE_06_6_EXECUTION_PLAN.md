---
title: Milestone 06.6 execution plan
status: accepted
last_updated: 2026-08-02
---

# M6.6 — Iterative supervised model improvement

## Cel

Zamknąć kontrolowaną pętlę: ręczna weryfikacja → skumulowana kohorta → trening
kandydata → bramka jakości → jawna aktywacja → lepsze sugestie dla nowych i
wyłącznie oczekujących plansz.

Milestone należy do toru przygotowania danych wersji 0.5. Rozpoczyna się po
zaakceptowaniu selektora 0.4 i musi zostać ukończony przed odblokowaniem pełnego
automatycznego importu i `massImportAllowed`.

## Twarda granica

Żaden task tego milestone'u nie może automatycznie przeliczyć, zmienić ani
nadpisać planszy rozstrzygniętej przez użytkownika. `accepted`, `corrected` i
`rejected` są chronione. Ponowna inferencja dotyczy tylko aktualnego `pending`.

## Podetapy i zadania

### M6.6.1 — Kontrakt danych treningowych

- **TASK-0143** — cumulative verified training cohort contract — `done`.

Rezultat: game-scoped, checksum-bound kohorta i ochrona decyzji człowieka na
poziomie modelu danych oraz testów.

### M6.6.2 — Workspace jakości i zamrożenie kohorty

- **TASK-0144** — model quality workspace and cohort freeze — `done`.

Rezultat: użytkownik widzi gotowość danych oraz jawnie rozpoczyna iterację;
progi 100/1000 pozostają wskazówką.

### M6.6.3 — Deterministyczny dataset

- **TASK-0145** — source-aware cumulative training dataset — `done`.

Rezultat: odtwarzalny, skumulowany podział bez przecieku między zdjęciami.

### M6.6.4 — Trwały trening lokalny

- **TASK-0146** — durable symbol model training job — `done`.

Rezultat: lokalny trening od początku ma checkpointy, postęp, retry i nie
dotyka danych review.

### M6.6.5 — Kandydat i bramka regresji

- **TASK-0147** — candidate ONNX, calibration and regression gate — `done`.

Rezultat: kandydat ma komplet artefaktów i porównanie z aktywnym modelem, lecz
nie aktywuje się automatycznie.

### M6.6.6 — Rejestr i kontrolowana aktywacja

- **TASK-0148** — model registry and controlled activation — `done`.

Rezultat: jedna aktywna wersja per gra, audytowalna aktywacja i rollback oraz
przypinanie wersji do nowych importów.

### M6.6.7 — Bezpieczne ponowne sugestie

- **TASK-0149** — pending-only re-inference and import pinning.

Rezultat: nowy model może utworzyć rewizje sugestii wyłącznie dla `pending`;
element rozwiązany w trakcie joba zostaje pominięty.

### M6.6.8 — Odbiór pełnej pętli

- **TASK-0150** — iterative supervised loop acceptance.

Rezultat: dwie iteracje i nowy import potwierdzają jakość, odtwarzalność oraz
zerową zmianę decyzji człowieka.

## Kolejność

```text
TASK-0143 -> TASK-0144 -> TASK-0145 -> TASK-0146
          -> TASK-0147 -> TASK-0148 -> TASK-0149 -> TASK-0150
```

TASK-0144 może rozpocząć statyczny UI po ustaleniu kontraktu TASK-0143, ale
integracyjna akceptacja pozostaje sekwencyjna.

## Warunki wejścia

- zakończony odbiór Admina 0.2 dla importu i Reviewera,
- co najmniej jedna gra z pełnymi rozstrzygnięciami manual review,
- działający produkcyjny pipeline cropów i inferencji,
- znany aktywny model bazowy oraz odtwarzalne narzędzia treningu,
- brak trwającego resetu danych gry.

## Bramka M6.6

- kohorta jest niezmienna i odtwarzalna z manifestu,
- split nie przecieka między pochodnymi tego samego zdjęcia,
- training job przeżywa kontrolowany restart i retry,
- kandydat przechodzi ONNX parity, kalibrację i regresję,
- aktywacja jest jawna, per gra i odwracalna,
- trwający import zachowuje przypiętą wersję modelu,
- nowy import używa nowo aktywowanej wersji,
- ponowna inferencja zapisuje tylko nowe rewizje `pending`,
- checksumy wszystkich rozstrzygnięć człowieka są identyczne przed i po dwóch
  iteracjach,
- właściciel akceptuje panel jakości oraz raport ograniczeń modelu.

## Poza zakresem

- automatyczne uczenie i aktywacja,
- poprawa OCR i geometrii,
- publiczny serwer treningowy,
- Redis/Celery lub mikroserwisy,
- pełny import 500 000 rzeczywistych layoutów; wykorzysta on zatwierdzony
  mechanizm dopiero po bramce M6.6.
