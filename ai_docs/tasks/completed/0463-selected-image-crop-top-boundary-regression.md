---
title: TASK-0463 Selected image crop top boundary regression
status: done
---

# TASK-0463 — Bezpieczna górna granica auto-cropa i zaznaczanie wszystkich

## Goal

Usunąć regresję, przez którą lokalny auto-crop pozostawia panel wypłat albo
ustawia górną granicę zbyt wysoko, oraz dodać jeden przełącznik zaznaczenia
wszystkich widocznych wyników do korekty.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- porównanie bieżącej polityki v5 z ostatnim bezpiecznym zachowaniem;
- wersjonowana korekta górnej i dolnej granicy bez zmiany historycznego replay;
- fail-safe: niepewny wynik trafia do `Do poprawy`, zamiast udawać dobry crop;
- przełącznik `Zaznacz wszystkie` / `Odznacz wszystkie` w kafelkowym review;
- testy rzeczywistych regresji, sesji, UI oraz aktualizacja dokumentacji.

## Definition of Done

- panel wypłat nie może być przyjęty jako początek obszaru plansz;
- granica nie może przeciąć górnego rzędu plansz;
- brak wiarygodnej granicy pozostawia szeroki, jawnie niepewny crop;
- historyczne polityki v4/v5 zachowują replay;
- zaznaczenie zbiorcze nie obejmuje błędnych lub niedostępnych wyników;
- testy, lint, typecheck i build zmienionego pionu są udokumentowane.

## Outcome

- Potwierdzono regresję polityki v5: poprawny wynik detektora niebieskiego
  panelu był odrzucany, gdy niezależny detektor wielokolumnowy zwracał
  `safe_wide`. W efekcie część zdjęć zachowywała niemal pełną wysokość.
- Dodano wersjonowaną politykę
  `selected-image-board-band-v6-wide-blue-board-panel`. Panel jest mierzony
  niezależnie w dziewięciu pionowych pasach i wymaga co najmniej pięciu
  zgodnych pasów obejmujących lewą, środkową i prawą część zdjęcia oraz
  ograniczonego rozrzutu granic.
- Zmniejszono górny zapas z 12% do 7,5% wysokości obrazu analitycznego.
  Detektor nadal pracuje na jednym podglądzie 512 px, bez OCR i dodatkowego
  przebiegu po pełnym obrazie. Brak wystarczających dowodów nadal daje
  jawny `safe_wide` przeznaczony do sprawdzenia.
- Zachowano akceptację zapisanej proweniencji v4 i v5. Istniejące wyniki nie
  są przeliczane automatycznie; migracja do v6 wymaga istniejącej jawnej akcji
  przeliczenia nieprzejrzanych i ręcznie niezmienionych wyników.
- Dodano pojedynczy przełącznik `Zaznacz wszystkie` / `Odznacz wszystkie`.
  Operacja dotyczy wyłącznie przygotowanych wyników widocznych w bieżącym
  filtrze, zachowuje wybory ukryte przez filtr i utrwala całość jednym zapisem
  małego stanu review.
- Dodano regresje dla słabego dowodu ogólnego, pochylonego panelu, bocznych
  świateł, przesłonięcia oraz deterministycznej masowej zmiany wyboru.
- Weryfikacja: 52/52 testów core, 408/408 testów Admina, skoncentrowany lint,
  typecheck core i Admina, Prettier dla zmienionego kodu oraz produkcyjny build
  Admina — zielone. Globalny `format:check` nadal zgłasza pięć istniejących,
  niezwiązanych plików Admina; żaden plik tego taska nie jest na tej liście.
- Nie przeliczano katalogów użytkownika, nie nadpisywano istniejących cropów,
  nie restartowano usług i nie zmieniano bazy danych.
