---
title: Version 0.4 execution plan
status: accepted
last_updated: 2026-08-05
---

# Plan zakresu wersji 0.4

## Cel

Dostarczyć kompletny, osobny moduł `Selekcja zdjęć`, który redukuje katalog
10 000–30 000 podobnych ujęć do jednego bezpiecznego reprezentanta na zakres,
zanim w wersji 0.5 rozpocznie się pełny pipeline na dużych datasetach. Wersja
0.4 jest zamkniętym zakresem M7.0 oraz stabilizacji TASK-0158–0177 wynikającej
z rzeczywistych prób właściciela.

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

- TASK-0151–0157 oraz wymagane korekty TASK-0158–0177 mają status `done` i
  spełniają Definition of Done,
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

TASK-0151–0157 definiują pierwotny zakres M7.0. TASK-0158–0171 są korektami
wydajności i jakości wynikającymi z realnego korpusu. TASK-0172–0175 rozdzieliły
i zabezpieczyły dwa execution lane. TASK-0176 uzupełnia budżety zasobów oraz
widoczność lane w Adminie, a TASK-0177 przeprowadzi rzeczywisty test równoległej
Selekcji i Importu. TASK-0143–0150, TASK-0076 oraz TASK-0080–0089 zachowują
numery, ale należą do wersji 0.5. Liczba nowych gier i finalna macierz urządzeń
zostaną doprecyzowane dopiero przed bramką 0.5.

## Stabilizacja v10 — plan accuracy-first

1. TASK-0178 — audyt regresji v9 i zamrożenie zakresu selekcji.
2. TASK-0179 — scoring całej grupy i top-12 bez early exit.
3. TASK-0180 — pełna weryfikacja shortlisty, OCR z bezpiecznym marginesem i
   konsensus wielu klatek.
4. TASK-0181 — rosnący/malejący porządek oraz opcjonalna kotwica pierwszego
   numeru.
5. TASK-0182 — historyczne nazwy `seq_<od>-<do>.jpg` i progresywny endpoint.
6. TASK-0183 — wybór dwóch katalogów przed startem i zapis każdej ukończonej
   grupy w trakcie runu.
7. TASK-0184 — optymalizacja końcowego I/O bez zmiany jakości.
8. TASK-0185 — regresje automatyczne i krótki poglądowy smoke bez kosztownego
   benchmarku 5000.
9. TASK-0186 — ręczny odbiór właściciela na około 5000 i 32 000 zdjęć.

### Stabilizacja v10.1 — redukcja kosztu bez powrotu do first usable

1. TASK-0188 — usunąć wymuszanie ciągłości zakresów i dodać regresję skoku.
2. TASK-0189 — rozdzielić ocenę reprezentanta od dowodu numeru.
3. TASK-0190 — uruchomić szybki OCR trzech kotwic na stabilnej geometrii.
4. TASK-0191 — dodać adaptacyjny konsensus klatek `2 -> 4 -> 8 -> 12`.
5. TASK-0192 — dodać progresywny fallback cropów `18 -> 36 -> 72`.
6. TASK-0193 — zmierzyć deterministyczną równoległość pełnej weryfikacji i
   aktywować ją tylko przy identycznym wyniku.
7. TASK-0194 — powtórzyć profil tych samych 200 zdjęć, porównać reprezentanty i
   zapisać decyzję przed ręcznym runem 5000/32 000.

Baseline v10 wynosi 377,530649 s dla 200 zdjęć i 9 grup. Pierwsza bramka v10.1
oczekuje 60–70% krótszego czasu bez pogorszenia wyboru; cel 70–85% jest
aspiracyjny i wymaga akceptacji właściciela. Pełny run nie jest uruchamiany
przed TASK-0194.

Pełny benchmark 40 000 nie jest bramką automatyczną tej korekty. Właściciel
ocenia czas i jakość realnych runów; orientacyjnie dopuszcza 3–5 razy dłuższy
czas niż v9 w zamian za poprawę wyboru zdjęcia.
