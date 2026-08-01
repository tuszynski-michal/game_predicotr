---
title: Version 0.4 execution plan
status: accepted
last_updated: 2026-08-01
---

# Plan zakresu wersji 0.4

## Cel

Przejść z zaakceptowanego workflow i dostosowanego interfejsu mobilnego do
rzeczywistych danych, pełnej skali i obsługi kolejnych gier. Wersja 0.4 jest
bramką końcowych testów dużych zbiorów, wydajności i pełnego hardeningu.

## Warunki rozpoczęcia

- właściciel zaakceptował wymagane testy wersji 0.1, 0.2 i 0.3,
- błędy wymagane przed dalszym rozwojem zostały naprawione,
- ograniczenia pozostawione po 0.3 są jawnie zaakceptowane,
- istnieje plan danych, storage i urządzeń dla większego zakresu.

## Zamrożony zakres wysokiego poziomu

- import wszystkich dostępnych layoutów dla pierwszej gry,
- dojście do docelowej kompletności, domyślnie około 500 000 layoutów na grę,
- ponowna kalibracja jakości, retraining i bramka `massImportAllowed`,
- TASK-0143–0150, czyli M6.6: skumulowane kohorty zweryfikowane przez człowieka,
  trening kandydatów, kontrolowana aktywacja i przeliczenie tylko `pending`,
- wykonanie TASK-0076 i zamknięcie pełnej bramki M7,
- dodawanie nowych gier oraz różniących się katalogów symboli i reguł,
- wielogrowy snapshot i wydanie Android,
- końcowe benchmarki pełnego Targetu, wyszukiwania, generowania i storage na
  dużych rzeczywistych zbiorach,
- TASK-0080–0089: stały podpis, backup/restore, recovery, kompatybilność,
  dystrybucja, rollback i disaster recovery,
- rozszerzona regresja urządzeń ustalona przed rozpoczęciem bramki wydania.

## Zasady danych

- mały dataset 0.2 nie jest automatycznie promowany do danych produkcyjnych,
- decyzje człowieka mogą zostać zachowane tylko z pełnym pochodzeniem i po
  zgodności z nową grą/importem,
- pełny import pozostaje wznawialny, wersjonowany i checksum-bound,
- brakujące layouty, duplikaty i jakość źródeł są raportowane jawnie,
- wydanie mobilne zawiera rekordy, grafiki symboli i payouty, bez zdjęć
  źródłowych.

## Bramka 0.4

- co najmniej jedna gra przechodzi pełny rzeczywisty import i walidację,
- kolejne gry są obsługiwane bez kopiowania logiki domenowej,
- pełna skala mieści się w zaakceptowanych budżetach czasu, pamięci i miejsca,
- ograniczony i pełnocyklowy Target przechodzą końcowe testy dużych zbiorów,
- backup jest rzeczywiście odtworzony, a rollback przetestowany,
- wymagane urządzenia przechodzą regresję offline,
- właściciel akceptuje produkt i pozostałe ograniczenia.

## Tor M6.6 przed pełnym importem

Plan `MILESTONE_06_6_EXECUTION_PLAN.md` jest obowiązkową bramką jakości modelu
symboli przed TASK-0076. Decyzje `accepted`, `corrected` i `rejected` nie mogą
zostać zmienione przez trening, aktywację ani ponowną inferencję. Nowe wersje
modelu tworzą sugestie wyłącznie dla `pending`, a nowe importy przypinają model
aktywny w chwili utworzenia joba.

## Istniejące zadania

TASK-0076, TASK-0080–0089 oraz TASK-0143–0150 zachowują swoje numery i
wymagania. Liczba nowych gier i finalna macierz urządzeń zostaną doprecyzowane
po bramce wejścia do 0.4.
