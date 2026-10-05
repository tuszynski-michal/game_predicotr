---
title: Mumie — rzeczywista partia600 zdjęć
status: complete
last_updated: 2026-10-05
---

# Wynik rzeczywistej inferencji

Przetworzono600 równomiernie wybranych zdjęć z2052 plików drugiego folderu
cut, bez duplikatów i bez źródeł z komponentów D-498/treningu/walidacji
lub chronionych. Manifest `9068f31aa03efc7fde3c724e11aa3d78c149ba9b98d489928f935a0379199dac`.
Root: `C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-folder-test-20261005\symbol-batch-600`.
Przegląd: `http://127.0.0.1:8108/symbol-batch-600/review.html`.

## Liczności i rzeczywiste ograniczenia

5396 oczekiwanych/pokazanych plansz i80940 pól. Sieć wykryła5397 plansz;
jeden nadmiarowy kandydat ostatniego zdjęcia pominięty. Nazwa pliku
499996–500004 przekracza koniec folderu500000, a obraz zawiera5 plansz.
Konflikt jest jawny, bez zmiany pliku operatora i bez przypisania sekwencji.
W wybranej600 nie wystąpiło pole poza zdjęciem; trzy takie pola są objęte
testem regresyjnym i nie otrzymują fikcyjnego obrazu ani przewidywania.

15626 rozpoznań ma niepewność modelową (19.31%);3494 disagreement (4.32%).
15695 pól wymaga review po uwzględnieniu konfliktu zakresu. Wszystkie10 klas
otrzymały propozycje. To pokrycie i zgodność, **nie accuracy**: brak niezależnych
etykiet dla tej partii. Żadnego zatwierdzenia człowieka nie utworzono.

Kontaktowe kadry i przegląd pierwszego/ostatniego zdjęcia ujawniły poważną
słabość podświetlonych J/K i zielonych linii wygranej: modele wskazują Q/Mumię
lub inne klasy. Siatki tych przykładów obejmują właściwe pola. Trening na339
próbkach nie rozwiązał całej zmienności wyglądu; wynik83/84 małej walidacji
nie przenosi się automatycznie na większy zestaw. Zaplanowano jedną ograniczoną
parę v2 bez nowych automatycznych etykiet (TASK-0857), następnie realne
ograniczenie będzie wymagać dodatkowych świadomych etykiet trudnych wariantów.

## Weryfikacja

-17 nowych testów +11 regresji modeli:28 PASS. Ruff/lint/format/mypy PASS.
- Dokładny preprocess RGB/gray zgodny z treningiem; brak zmiany kalibracji.
- Full-component exclusion, source/model drift, conflicting publish, corrupted
  visual, missing/excess boards, partial crop i fresh-process replay PASS.
- Rzeczywiste600 wykonano porcjami25 z timeout115s/porcję i trwałym markerem.
  Kontrolowany driver ukończony; oba jego PID zakończone, bez osieroconego workera.
- Gallery HTTP200 i browser smoke:600 zdjęć,60 niepewnych cropów oraz30
  rozłożonych kontroli klas. Szczegół każdego zdjęcia zawiera całe zdjęcie i pola.
- Ponowna kontrola wszystkich wyników/galerii w świeżym procesie oraz SHA
  geometrii rev591, symboli rev63 i historii runów potwierdza brak zmian.

## Odbiór zakresu

Każde kryterium TASK-0856 i planu pokryte kodem, testem albo rzeczywistym
artefaktem. Samodzielny odrębny przegląd nie wykazał nierozwiązanych P0–P2.
Nie wykonano DB, etykietowania za człowieka, aktywacji, Super ani wdrożenia.
Osobny commit v1.7.202; pełny hash w Outcome i CURRENT_STATE po commicie.
