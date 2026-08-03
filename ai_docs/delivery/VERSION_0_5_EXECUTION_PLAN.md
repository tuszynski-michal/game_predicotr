---
title: Version 0.5 execution plan
status: accepted
last_updated: 2026-08-02
---

# Plan zakresu wersji 0.5

## Cel

Rozpocząć pracę na dużych rzeczywistych datasetach po zaakceptowaniu selektora
v0.4. Wersja 0.5 wykorzystuje checksumowany output M7.0 jako wejście do pełnego
pipeline'u, rozwija jakość modelu na rosnących kohortach i domyka skalę,
wielogrowe wydanie oraz hardening.

## Warunki rozpoczęcia

- TASK-0151–0157 są ukończone,
- raport TASK-0157 zezwala na użycie selektora,
- właściciel zaakceptował niedestrukcyjny output, manual fallback i handoff,
- pełny import nadal respektuje `massImportAllowed = false`, dopóki nie przejdą
  właściwe bramki jakości,
- chronione decyzje `accepted`, `corrected` i `rejected` pozostają niezmienne.

## Zakres wysokiego poziomu

- TASK-0143–0150 i M6.6: skumulowane kohorty, trening, bramka ONNX, jawna
  aktywacja i ponowna inferencja wyłącznie dla `pending`,
- TASK-0076: kontrolowana publikacja pełnego dużego importu,
- dojście do docelowej kompletności, domyślnie około 500 000 layoutów na grę,
- dodawanie i testowanie kolejnych gier,
- wielogrowy snapshot oraz prywatne wydanie Android,
- końcowe benchmarki matching, Targetu, importu, storage i wydania na dużych
  rzeczywistych danych,
- TASK-0080–0089: podpis, backup/restore, recovery, kompatybilność,
  dystrybucja, rollback i disaster recovery,
- rozszerzona macierz urządzeń oraz końcowy odbiór właściciela.

## Zasady

- pełny pipeline otrzymuje wyłącznie zweryfikowany manifest selekcji v0.4,
- żaden trening ani reprocessing nie zmienia decyzji człowieka,
- importy, modele, datasety, reguły, snapshoty i APK pozostają wersjonowane oraz
  checksum-bound,
- jedna ciężka operacja działa naraz, dopóki pomiary nie uzasadnią kolejki,
- chmura, mikroserwisy, Redis i Celery nie są dodawane bez dowodu potrzeby.

## Bramka 0.5

- co najmniej jedna gra przechodzi pełny rzeczywisty import i walidację,
- kolejne gry nie wymagają kopiowania logiki domenowej,
- pełna skala mieści się w zaakceptowanych budżetach czasu, pamięci i miejsca,
- ograniczony i pełnocyklowy Target przechodzą testy dużych zbiorów,
- backup zostaje rzeczywiście odtworzony, a rollback sprawdzony,
- wymagane urządzenia przechodzą regresję offline,
- właściciel akceptuje produkt i jawnie opisane ograniczenia.

## Zadania

Istniejące TASK-0143–0150, TASK-0076 oraz TASK-0080–0089 zachowują swoje numery
i kryteria. Nowe zadania dotyczące dodatkowych gier lub problemów ujawnionych
przez duże dane będą dopisywane do tego planu przed implementacją.
