---
title: TASK-0220 Consensus-backed representative recall
status: done
version: 0.5
last_updated: 2026-08-10
---

# TASK-0220 — Consensus-backed representative recall

## Goal

Zmniejszyć nadmierną liczbę grup `manual_required` w selektorze v10.2 bez
przywracania błędu, w którym JPEG otrzymywał nazwę innego zakresu.

## Problem

Produkcjny run 32 079 zdjęć pokazał około 37% grup ręcznych. Analiza zapisanych
kandydatów wykazała, że dla każdej dotychczasowej grupy ręcznej istniał co
najmniej jeden JPEG z własnym odczytem dokładnie zgodnym z zakresem grupy i
confidence co najmniej `0.90`. V10.2 blokował te zdjęcia z powodu niepełnej
geometrii lub niezgodnej liczby wykrytych plansz, mimo poprawnej nazwy.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`

## Scope

- dodać fingerprintowany selektor `fast-image-selector-v10.3`,
- zachować v10.2 dla wznowień historycznych,
- pozwolić na wybór najlepszego miękkiego kandydata, jeżeli ten sam JPEG
  samodzielnie potwierdza dokładny zakres z confidence `>= 0.90`,
- nadal blokować konflikt zakresu, inny zakres, nieczytelny numer, rozmycie,
  okluzję oraz techniczny błąd skanu/weryfikacji,
- nie zmieniać działającego runu v10.2,
- po jego zakończeniu przeładować worker i dopiero wtedy uruchomić następny
  zbiór 42 403 zdjęć na v10.3.

## Verification

- regresja v10.2 false merge,
- nowy test miękkiej geometrii z dokładnie zgodnym zakresem,
- test niezgodnego zakresu pozostającego bez automatycznego wyboru,
- pełne testy selektora i adapterów,
- Ruff i zawężony mypy,
- kontrola fingerprintu i rozwiązywalności manifestów historycznych.

## Outcome

Dodano immutable manifest `fast-image-selector-v10.3` o fingerprintcie
`b5210620e3127fa4addebcb158d4e717df7d89ed08c6d09f354756bf18cab7e4`.
V10.3 zachowuje kontrolę zgodności nazwy v10.2: wynikowy JPEG musi własnym OCR
potwierdzić dokładnie zakres grupy z confidence co najmniej `0.90`. Miękkie
problemy geometrii, kadru, ekspozycji i liczby plansz nie blokują już najlepszego
dostępnego źródła; twarde konflikty, inny/nieznany zakres, blur, okluzja i błędy
techniczne pozostają w review.

Analiza read-only bieżącego runu wykazała dokładnie zgodne dowody OCR dla
wszystkich 573 zbadanych wtedy grup ręcznych, które blokowały głównie niepełna
geometria i `RANGE_BOARD_COUNT_MISMATCH`. Jest to szacunek recall, nie mutacja
trwającego runu v10.2. Historyczne manifesty nadal są rozwiązywalne.

Weryfikacja: 124/124 testów selektora, adapterów i joba; Ruff check i format
check; mypy manifestu i silnika. Skupiony mypy z `job.py` ujawnił wyłącznie
istniejący problem pakietowania `game_predictor_api` jako biblioteki bez
`py.typed`; moduł joba ma osobne testy wykonawcze. Duży run v10.2 nie został
przerwany ani przełączony w locie. Przeładowanie usług i uruchomienie 42 403
zdjęć na v10.3 pozostają kontrolowanym krokiem po terminalnym stanie bieżącego
runu i jego monitora eksportu.
