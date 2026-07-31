---
title: Version 0.3 execution plan
status: accepted
last_updated: 2026-07-31
---

# Plan zakresu wersji 0.3

## Cel

Przejść z funkcjonalnie zweryfikowanego małego workflow `0.2` do rzeczywistych
danych, pełnej skali i obsługi kolejnych gier. Szczegółowe zadania powstaną po
odbiorze `0.1` i `0.2`, aby nie planować na podstawie niezweryfikowanego UX.

## Warunki rozpoczęcia

- właściciel zaakceptował testy mobilnej wersji `0.1`,
- właściciel zaakceptował testy workflow i Admina `0.2`,
- błędy obu wersji wymagane przed dalszym rozwojem zostały naprawione,
- ograniczenia pozostawione po `0.2` są jawnie zaakceptowane,
- istnieje plan danych, storage i urządzeń dla większego zakresu.

## Zamrożony zakres wysokiego poziomu

- import wszystkich dostępnych layoutów dla pierwszej gry,
- dojście do docelowej kompletności, domyślnie około 500 000 layoutów na grę,
- ponowna kalibracja jakości, retraining i bramka `massImportAllowed`,
- wykonanie TASK-0076 i zamknięcie pełnej bramki M7,
- dodawanie nowych gier oraz różniących się katalogów symboli i reguł,
- wielogrowy snapshot i wydanie Android,
- benchmarki pełnego Targetu, wyszukiwania, generowania i storage na skali,
- TASK-0080–0089: stały podpis, backup/restore, recovery, kompatybilność,
  dystrybucja, rollback i disaster recovery,
- rozszerzona regresja urządzeń ustalona przed rozpoczęciem bramki wydania.

## Zasady danych

- mały dataset `0.2` nie jest automatycznie promowany do danych produkcyjnych,
- decyzje człowieka mogą zostać zachowane tylko z pełnym pochodzeniem i po
  zgodności z nową grą/importem,
- pełny import pozostaje wznawialny, wersjonowany i checksum-bound,
- brakujące layouty, duplikaty i jakość źródeł są raportowane jawnie,
- wydanie mobilne zawiera rekordy, grafiki symboli i payouty, bez zdjęć źródłowych.

## Bramka 0.3

- co najmniej jedna gra przechodzi pełny rzeczywisty import i walidację,
- kolejne gry są obsługiwane bez kopiowania logiki domenowej,
- pełna skala mieści się w zaakceptowanych budżetach czasu, pamięci i miejsca,
- backup jest rzeczywiście odtworzony, a rollback przetestowany,
- wymagane urządzenia przechodzą regresję offline,
- właściciel akceptuje produkt i pozostałe ograniczenia.

## Jeszcze nierozpisane

Numery nowych zadań, dokładna liczba gier i finalna macierz urządzeń zostaną
ustalone dopiero po bramce wejścia. Istniejące TASK-0076 i TASK-0080–0089
zachowują swoje numery oraz wymagania.
