---
title: TASK-0347 — Czytelne liczniki ręcznej geometrii
status: done
version: 0.10
---

# TASK-0347 — Czytelne liczniki ręcznej geometrii

## Cel

Usunąć mylne wrażenie, że preflight zgubił część ręcznie zapisanych geometrii,
gdy partia zawiera zarówno nowe odroczone źródła, jak i ponowne korekty źródeł
już zarejestrowanych.

## Diagnoza

- Liczniki joba dotyczą zdjęć źródłowych, nie dziewięciu plansz na zdjęciu.
- Wszystkie zapisane override'y występowały w niezmiennych snapshotach jobów.
- Ponowna korekta już zarejestrowanego źródła poprawnie zmienia geometrię, ale
  nie może drugi raz zwiększyć liczby unikalnych zarejestrowanych zdjęć.

## Zakres

- nazwać liczniki zdjęciami źródłowymi;
- oznaczyć każdą pozycję jako odroczoną albo aktualizację już zarejestrowanej
  geometrii;
- po zapisie wyjaśnić oczekiwany wpływ na licznik;
- dodać test workera stosujący wszystkie override'y wieloelementowej partii.

## Outcome

Operator przed zapisem wie, czy źródło zwiększy licznik po następnym
preflighcie. Test regresyjny potwierdza, że trzy ręczne geometrie w jednym
snapshotcie dają trzy zarejestrowane źródła.
