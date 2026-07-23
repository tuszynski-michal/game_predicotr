---
title: Admin application requirements
status: proposed
last_updated: 2026-07-23
---

# Wymagania modułu administracyjnego

## Forma aplikacji

Rekomendowana forma to aplikacja webowa uruchamiana na Windows pod adresem lokalnym. Pozwala wykorzystać React/Next.js i nie wymaga budowania osobnej aplikacji desktopowej.

## Zakres funkcjonalny

### Games

Administrator może:

- utworzyć grę,
- ustawić nazwę i status,
- ustawić liczbę rzędów i kolumn,
- ustawić koszt spinu,
- określić maksymalny limit prognozy,
- aktywować lub archiwizować grę.

Zmiana wymiarów planszy po zaimportowaniu danych wymaga osobnej migracji danych i nie powinna być zwykłą edycją formularza.

### Symbols

Administrator może:

- dodać symbol do gry,
- nadać kod i nazwę,
- dodać obraz referencyjny,
- oznaczyć symbol jako joker,
- ustawić kolejność wyświetlania,
- aktywować lub archiwizować symbol.

Wypłata nie jest prostą właściwością symbolu. Jest definiowana przez `payout rules` zależne od długości i typu wzorca.

### Win patterns

Administrator może tworzyć co najmniej dwa typy wzorców:

1. `PAYLINE` — konkretna ścieżka przez rzędy kolejnych kolumn.
2. `CONSECUTIVE_COLUMNS_ANY_ROW` — symbol w kolejnych kolumnach, bez stałej pozycji rzędu.

Dla `PAYLINE` edytor pokazuje planszę i pozwala wybrać jedną komórkę w każdej objętej kolumnie.

### Payout rules

Administrator ustawia:

- symbol,
- typ lub konkretny wzorzec,
- minimalną/liczoną długość: 2, 3, 4 lub 5,
- wartość wygranej w kredytach,
- status aktywności.

System waliduje brak sprzecznych reguł dla tej samej kombinacji kluczy.

### Layout data

Administrator może:

- wygenerować dane testowe,
- zaimportować dane z pliku przygotowanego przez worker,
- sprawdzić zakres `sequence_number`,
- znaleźć luki i duplikaty numerów,
- sprawdzić duplikaty sygnatur layoutu,
- podejrzeć layout jako planszę,
- usunąć import testowy przed publikacją.

### Import jobs

Administrator widzi:

- status zadania,
- liczbę plików znalezionych, przetworzonych i błędnych,
- liczbę rozpoznanych layoutów,
- liczbę pozycji wymagających review,
- czas rozpoczęcia i zakończenia,
- możliwość wznowienia przerwanego zadania.

### Manual review

Dla niepewnego elementu administrator otrzymuje:

- podgląd oryginalnego zdjęcia,
- podgląd wyciętej planszy i kafelka,
- przewidywany symbol lub numer,
- confidence score,
- listę możliwych symboli,
- możliwość zatwierdzenia, poprawienia albo odrzucenia.

Decyzja użytkownika powinna zostać zachowana jako oznaczony przykład, który można później wykorzystać do poprawy klasyfikatora.

### Publish dataset

Docelowo administrator publikuje wersjonowany zestaw danych. Publikacja:

- waliduje kompletność,
- blokuje modyfikację opublikowanej wersji,
- zapisuje wersję i czas publikacji,
- nie nadpisuje poprzedniej wersji bez śladu.

Mechanizm dystrybucji do mobile zależy od decyzji online/offline.

## Poza MVP admina

Pierwsza iteracja modułu admina może ograniczyć się do CRUD gier, symboli, paylines i mock layouts. Import zdjęć jest osobnym milestone'em.

## Kryteria akceptacyjne pierwszej iteracji

1. Administrator tworzy grę 3 × 5.
2. Dodaje symbole `S1`–`S12` i oznacza joker.
3. Tworzy trzy poziome paylines.
4. Ustawia wypłaty dla długości 3, 4 i 5.
5. Generuje lub importuje 1000 layoutów.
6. Widzi duplikaty sygnatur i błędy sekwencji.
7. Dane są dostępne przez API dla aplikacji mobilnej.
