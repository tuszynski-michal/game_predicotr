---
title: Mobile application requirements
status: proposed
last_updated: 2026-07-23
---

# Wymagania aplikacji mobilnej

## Platforma

- Główna platforma: Android.
- Interfejs projektowany przede wszystkim dla telefonu w orientacji pionowej.
- MVP może być uruchamiane przez Expo development build lub Expo Go, zależnie od użytych bibliotek.

## Ekran główny

Ekran składa się kolejno z sekcji:

1. Header
2. Layout
3. Selection
4. Target

## Header

### Elementy

- wybór gry,
- przycisk `Undo`,
- przycisk `Reset`.

### Zachowanie wyboru gry

- po zmianie gry aplikacja pobiera konfigurację planszy i symbole,
- istniejący wybór layoutu jest czyszczony,
- kontekst rozstrzygania duplikatów jest czyszczony,
- sekcja Target wraca do stanu początkowego.

### Undo

- usuwa ostatnio dodany symbol,
- działa tylko na historię bieżącego wprowadzania,
- nie zmienia wybranej gry,
- po cofnięciu ponownie uruchamia wyszukiwanie kandydatów,
- gdy brak symboli, jest nieaktywny.

### Reset

- czyści wszystkie pola planszy,
- czyści historię undo,
- czyści propozycję automatycznego uzupełnienia,
- czyści wynik i confirmation chain,
- zachowuje wybraną grę.

## Layout

### Prezentacja

- rozmiar planszy pochodzi z konfiguracji gry,
- najczęstszy i domyślny rozmiar to 3 rzędy × 5 kolumn,
- puste pole jest szarym kafelkiem,
- każde pole ma stabilną pozycję `row_index` i `column_index`,
- kolejność wprowadzania jest `row-major`.

### Stan danych

Przykład dla 3 × 5:

```ts
type BoardState = Array<SymbolId | null>; // długość 15, row-major
```

Indeks komórki:

```text
index = row_index * column_count + column_index
```

### Wprowadzanie

Kliknięcie symbolu w Selection:

1. znajduje pierwszą pustą komórkę,
2. wpisuje symbol,
3. zapisuje operację w historii undo,
4. uruchamia dopasowanie prefiksu.

Gdy plansza jest pełna, Selection może być nieaktywne do czasu Undo lub Reset.

## Automatyczna propozycja

Po każdej zmianie aplikacja wysyła bieżący prefiks do API.

### Warunki otwarcia modala

Modal jest otwierany, gdy:

- istnieje dokładnie jeden kandydat pozycji sekwencji,
- kandydat ma więcej symboli niż obecnie wprowadzono,
- propozycja nie została już odrzucona dla tego samego prefiksu.

### Zawartość modala

- wizualizacja pełnego proponowanego layoutu,
- numer sekwencji,
- przycisk `Akceptuj`,
- przycisk `Zamknij`.

### Akceptuj

- uzupełnia brakujące pola,
- zapisuje operację pozwalającą cofnąć automatyczne uzupełnienie jako jeden krok,
- ustawia jednoznaczny wynik,
- w przyszłej fazie uruchamia target forecast.

### Zamknij

- nie zmienia planszy,
- użytkownik może kontynuować ręczne wprowadzanie,
- modal nie otwiera się ponownie dla identycznego prefiksu, dopóki stan nie zostanie zmieniony.

## Wynik dopasowania layoutu

Dla pełnej planszy aplikacja obsługuje stany:

- `unique` — dokładnie jedna pozycja sekwencji,
- `ambiguous` — kilka pozycji ma identyczny layout,
- `not_found` — brak layoutu,
- `error` — błąd techniczny.

### Unique

Wyświetl:

```text
Układ: 256 700
```

### Ambiguous

- wyświetl liczbę kandydatów i ich numery, jeśli lista jest mała,
- nie uruchamiaj target forecast,
- poinformuj użytkownika, że musi podać następny layout,
- zachowaj kandydatów jako confirmation chain,
- po wprowadzeniu kolejnego layoutu dopasuj go do następników każdego kandydata.

### Not found

- wyświetl czytelny komunikat,
- pozwól poprawić dane przez Undo,
- nie usuwaj automatycznie wprowadzonej planszy.

## Selection

- lista zawiera około 10–12 symboli danej gry,
- MVP używa etykiet `S1`, `S2`, ...,
- docelowo używa obrazów symboli,
- lista może przewijać się poziomo,
- każdy kafelek ma dostępny tekst alternatywny/nazwę,
- symbol jokera jest wizualnie oznaczony.

## Target

### MVP

Sekcja wyświetla tylko stan dopasowania i numer układu. Nie liczy prognozy.

### Wersja docelowa

Sekcja jest aktywna tylko dla jednoznacznego `sequence_number`. Pokazuje:

- punkt startowy,
- koszt spinu,
- limit analizowanych spinów,
- pierwszy wynik dodatni,
- tabelę kolejnych high-water marks,
- stan końca sekwencji lub osiągnięcia limitu.

## Stany techniczne

Każda sekcja komunikująca się z API obsługuje:

- loading,
- empty,
- validation error,
- server error,
- retry.

## Kryteria akceptacyjne MVP

1. Użytkownik wybiera jedną z 3 gier.
2. Plansza zmienia rozmiar zgodnie z konfiguracją gry.
3. Symbole uzupełniają komórki w poprawnej kolejności.
4. Undo usuwa ostatnią operację.
5. Reset czyści layout i wynik.
6. API zwraca liczbę kandydatów dla częściowego layoutu.
7. Jeden kandydat otwiera modal propozycji.
8. Pełny jednoznaczny layout pokazuje `sequence_number`.
9. Pełny zduplikowany layout nie uruchamia targetu.
10. UI działa na typowym ekranie Android bez przewijania poziomego całej strony.
