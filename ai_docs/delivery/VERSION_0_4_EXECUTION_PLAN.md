---
title: Version 0.4 execution plan
status: accepted
last_updated: 2026-08-02
---

# Plan zakresu wersji 0.4

## Cel

Dostarczyć kompletny, osobny moduł `Selekcja zdjęć`, który redukuje katalog
10 000–30 000 podobnych ujęć do jednego bezpiecznego reprezentanta na zakres,
zanim w wersji 0.5 rozpocznie się pełny pipeline na dużych datasetach. Wersja
0.4 jest zamkniętym zakresem M7.0 i TASK-0151–0157.

## Warunki rozpoczęcia

- właściciel zaakceptował wymagane testy wcześniejszych wersji potrzebne do
  pracy nad Adminem i pipeline'em,
- błędy wymagane przed dalszym rozwojem zostały naprawione,
- istniejące obrazy mogą być użyte jako mały korpus golden oraz fixture,
- pełny import dużego datasetu pozostaje zablokowany do bramki 0.5.

## Zamrożony zakres wysokiego poziomu

- TASK-0151–0157, czyli M7.0: osobny workspace selekcji zdjęć, szybkie
  grupowanie duplikatów, quality gate, niedestrukcyjny output i handoff,
- czwarty workspace Admina `Selekcja zdjęć`, spójny z istniejącym wyglądem,
- kontrolowany upload dużego folderu bez ujawniania ścieżek absolutnych,
- wersjonowany `fast-image-selector-v1`, checkpointy, retry, cancel i statystyki,
- automatyczny wybór jednego JPEG-a per zakres i kolejka wyjątków manualnych,
- checksumowany manifest oraz jawne przekazanie wyniku do `Importu layoutów`,
- golden jakości i benchmark selektora dla 10 000 oraz 30 000 zdjęć,
- odbiór właściciela obejmujący workspace, modal, output i handoff.

## Zasady danych

- folder źródłowy selekcji pozostaje read-only,
- baza przechowuje ścieżki, checksumy i metadane, a nie obrazy BLOB,
- output jest content-addressed, niezmienny i atomowo publikowany,
- ręczny fallback dotyczy wyłącznie nierozstrzygniętych grup,
- wynik selekcji nie uruchamia pełnego pipeline'u bez jawnej akcji,
- dane testu 10k/30k mierzą wyłącznie selektor; nie są pełnym datasetem layoutów
  i nie odblokowują `massImportAllowed`.

## Bramka 0.4

- TASK-0151–0157 mają status `done` i spełniają Definition of Done,
- selekcja 10 000/30 000 zdjęć spełnia budżet czasu i nie scala błędnie
  różnych zakresów,
- niepewne przypadki trafiają do manual fallback zamiast do auto-selection,
- źródłowy folder pozostaje bajtowo i strukturalnie niezmieniony,
- restart, retry i cancel nie pozostawiają częściowego manifestu ani procesu,
- gotowy manifest może zostać jawnie przekazany do istniejącego importu,
- właściciel akceptuje workflow i raport TASK-0157 ze stanem
  `ready | optimize | reject`.

## Granica z wersją 0.5

Wersja 0.4 kończy się na zaakceptowanym selektorze i handoffie. Nie wykonuje
pełnego importu około 500 000 rzeczywistych layoutów, nie dodaje kolejnych gier,
nie uruchamia M6.6, TASK-0076 ani pełnego hardeningu M8. Te prace rozpoczynają
się w [wersji 0.5](VERSION_0_5_EXECUTION_PLAN.md), wykorzystując wynik M7.0 jako
kontrolowane wejście.

## Istniejące zadania

TASK-0151–0157 są kompletną listą zadań wersji 0.4. TASK-0143–0150, TASK-0076
oraz TASK-0080–0089 zachowują numery, ale należą do wersji 0.5. Liczba nowych
gier i finalna macierz urządzeń zostaną doprecyzowane dopiero przed bramką 0.5.
