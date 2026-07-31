---
title: Mobile application requirements
status: accepted
last_updated: 2026-07-30
---

# Wymagania aplikacji mobilnej

## Platforma i dystrybucja

- Główna platforma: Android.
- Interfejs jest projektowany przede wszystkim dla telefonu w orientacji pionowej.
- Aplikacja działa całkowicie offline już w M1.
- Aplikacja nie łączy się z Internetem, siecią lokalną, panelem ani backendem.
- Finalne APK M1 nie deklaruje uprawnienia Android `INTERNET`.
- Konfiguracja, sygnatury layoutów i obliczone payouty są dołączone do wersji APK w snapshotcie SQLite.
- Zmiana danych lub reguł wymaga utworzenia nowego wydania i ręcznego zainstalowania APK.
- Dystrybucja jest prywatna, na maksymalnie 3–5 urządzeniach; publikacja w sklepie nie jest wymagana.
- Pierwsze urządzenia akceptacyjne: Google Pixel 10 Pro XL i Samsung Galaxy S21 Ultra.

Development build może być używany w czasie tworzenia, ale kryterium M1 spełnia samodzielnie instalowalne APK działające bez komputera deweloperskiego.

## Cykl życia snapshotu

- Każde APK wskazuje dokładnie jedną wersję wydania i checksum snapshotu.
- Snapshot jest materializowany pod nazwą zawierającą wersję lub checksumę,
  dlatego aktualizacja aplikacji nie może otworzyć starej kopii tylko dlatego,
  że istnieje już w katalogu danych.
- Przed aktywacją aplikacja waliduje wersję schematu i podstawowe metadata.
- Przy niezgodności aplikacja pokazuje `local_data_error` i nie wykonuje
  matching ani Target.
- M1 nie przechowuje trwałych danych użytkownika wymagających migracji.
  Wprowadzana plansza i wynik są stanem sesji.
- Poprzednia nieaktywna kopia snapshotu może zostać usunięta dopiero po
  prawidłowej aktywacji nowej.

## Ekran główny

Ekran składa się kolejno z sekcji:

1. Header
2. Layout
3. Selection
4. Result / Target
5. tabela dodatnich lokalnych maksimów na samym dole

Ostateczna etykieta użytkowa `Result` albo `Target` zostanie ustalona przy projekcie UI. W dokumentacji domenowej używana jest nazwa `Target`.

## Header

### Elementy

- wybór gry,
- przycisk `Undo`,
- przycisk `Reset`,
- widoczna wersja wydania lub danych w ekranie informacji/diagnostyki.

### Zachowanie wyboru gry

- konfiguracja planszy, symbole i lokalny indeks wyszukiwania są odczytywane ze snapshotu,
- istniejący wybór layoutu jest czyszczony,
- wynik dopasowania i prognoza są czyszczone,
- sekcja Target wraca do stanu początkowego.

### Undo

- usuwa ostatnio dodany symbol,
- działa tylko na historię bieżącego wprowadzania,
- nie zmienia wybranej gry,
- po cofnięciu ponownie uruchamia lokalne wyszukiwanie kandydatów,
- gdy brak symboli, jest nieaktywny,
- automatyczne uzupełnienie można cofnąć jako jedną operację.

### Reset

- czyści wszystkie pola planszy,
- czyści historię undo,
- czyści odrzuconą propozycję automatycznego uzupełnienia,
- czyści wynik dopasowania, prognozę i tabelę,
- zachowuje wybraną grę,
- po wykryciu duplikatu rozpoczyna całkowicie nowe wyszukiwanie.

## Layout

### Prezentacja

- rozmiar planszy pochodzi z konfiguracji gry,
- M1 używa 3 rzędów × 5 kolumn,
- puste pole jest szarym kafelkiem,
- każde pole ma stabilną pozycję `row_index` i `column_index`,
- kolejność wprowadzania i serializacji jest `row-major`.

### Stan danych

Przykład dla 3 × 5:

```ts
type BoardState = Array<SymbolCode | null>; // długość 15, row-major
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
4. uruchamia lokalne dopasowanie prefiksu.

Gdy plansza jest pełna, Selection jest nieaktywne do czasu Undo lub Reset.

## Automatyczna propozycja

Po każdej zmianie aplikacja wyszukuje prefiks w lokalnym snapshotcie.

### Warunki otwarcia modala

Modal jest otwierany, gdy:

- istnieje dokładnie jeden kandydat pozycji sekwencji albo wszystkie pozostałe
  pozycje mają jedną identyczną pełną sygnaturę layoutu,
- kandydat ma więcej symboli niż obecnie wprowadzono,
- propozycja nie została już odrzucona dla tego samego prefiksu.

Grupa kilku pozycji z jedną pełną sygnaturą może podpowiedzieć brakujące symbole,
ale nadal pozostaje wynikiem `duplicate`. Podpowiedź nie może wybierać jednego
`sequence_number`, uruchamiać Target ani ukrywać liczby wystąpień.

### Zawartość modala

- wizualizacja pełnego proponowanego layoutu,
- numer sekwencji dla pojedynczego kandydata albo jawna informacja o grupie
  duplikatów bez arbitralnego numeru,
- przycisk `Akceptuj`,
- przycisk `Zamknij`.

### Akceptuj

- uzupełnia brakujące pola,
- zapisuje automatyczne uzupełnienie jako jeden krok undo,
- uruchamia dokładne dopasowanie kompletnego layoutu,
- uruchamia Target tylko wtedy, gdy pełne dopasowanie jest jednoznaczne.

### Zamknij

- nie zmienia planszy,
- użytkownik może kontynuować ręczne wprowadzanie,
- modal nie otwiera się ponownie dla identycznego prefiksu, dopóki stan nie zostanie zmieniony.

## Wynik dopasowania layoutu

Dla pełnej planszy aplikacja obsługuje stany:

- `unique` — dokładnie jedna pozycja sekwencji,
- `duplicate` — kilka pozycji ma identyczny layout,
- `not_found` — brak layoutu,
- `local_data_error` — snapshot jest niekompletny albo uszkodzony.

### Unique

Wyświetl numer, np.:

```text
Układ: 256 700
```

Następnie uruchom prognozę dla pełnego cyklu.

### Duplicate

- wyświetl czytelny komunikat, że layout ma duplikat,
- opcjonalnie wyświetl liczbę wystąpień i ich numery, jeżeli lista jest mała,
- nie wybieraj arbitralnie żadnego `sequence_number`,
- nie uruchamiaj Target,
- wskaż procedurę: `Reset`, zmiana gry/układu w obserwowanym źródle i wprowadzenie kolejnego layoutu,
- nie zachowuj kontekstu poprzednich kandydatów po Reset.

### Not found

- wyświetl czytelny komunikat,
- pozwól poprawić dane przez Undo,
- nie usuwaj automatycznie wprowadzonej planszy.

## Selection

- lista zawiera symbole danej gry,
- M1 używa etykiet `S1`, `S2`, ...,
- docelowo używa lokalnych obrazów symboli,
- lista może przewijać się poziomo,
- każdy kafelek ma nazwę dostępną dla czytnika ekranu,
- joker jest wizualnie oznaczony.

## Target

Sekcja jest aktywna wyłącznie dla jednoznacznego `sequence_number`.

### Zasady

- rozpoznany layout jest spinem 0 bez kosztu i payoutu,
- pierwszy oceniany spin to następny layout w cyklicznej sekwencji,
- każdy oceniany spin zwiększa koszt skumulowany o `spin_cost`,
- każdy payout po drodze zwiększa `cumulative_payout`, także gdy wynik netto pozostaje ujemny,
- `net_credits = cumulative_payout - cumulative_cost`,
- wynik dodatni oznacza wyłącznie `net_credits > 0`,
- analiza kończy się na layoucie bezpośrednio poprzedzającym spin 0,
- dla `N` layoutów ocenianych jest `N - 1` spinów.

### Tabela

Tabela jest umieszczona na dole ekranu, poniżej wprowadzania i podsumowania. Pokazuje każde dodatnie lokalne maksimum wyniku netto, nie tylko rekord globalny.

Minimalne kolumny:

- numer spinu względem spin 0,
- `sequence_number` layoutu,
- payout bieżącego spinu,
- skumulowany payout,
- skumulowany koszt,
- wynik netto.

Podczas płaskiego maksimum wybierany jest pierwszy spin. Wiersze są uporządkowane rosnąco według numeru spinu.

Tabela może być długa, dlatego:

- renderowanie listy jest wirtualizowane,
- cały ekran przewija się pionowo jako jedna lista, a sekcje wejściowe są jej
  nagłówkiem,
- nie zagnieżdżaj pionowej listy wirtualizowanej w zwykłym `ScrollView`,
- UI nie tworzy jednocześnie komponentu dla każdego wiersza,
- obliczenia nie blokują trwale wątku interfejsu.

## Stany techniczne

Mobile obsługuje lokalnie:

- inicjalizację snapshotu,
- pusty stan,
- błąd walidacji wejścia,
- uszkodzony lub niezgodny snapshot,
- postęp dłuższego skanu,
- anulowanie lub ponowienie obliczenia.

Nie występują stany błędu serwera ani ponawianie połączenia sieciowego.

## Kryteria akceptacyjne M1

1. Użytkownik wybiera jedną z 3 gier.
2. Każda gra ma planszę 3 × 5 i 1000 zamockowanych layoutów.
3. Symbole uzupełniają komórki w kolejności `row-major`.
4. Undo cofa ostatnią operację, a Reset czyści layout i wynik.
5. Lokalne wyszukiwanie zwraca liczbę kandydatów dla częściowego layoutu.
6. Jeden kandydat otwiera modal propozycji.
7. Pełny jednoznaczny layout pokazuje `sequence_number`.
8. Pełny zduplikowany layout pokazuje błąd, nie uruchamia Target i po Reset nie zachowuje kontekstu.
9. Target ocenia dokładnie 999 spinów dla zbioru 1000 layoutów, z zawinięciem sekwencji.
10. Koszt każdego spinu i wszystkie payouty po drodze są poprawnie kumulowane.
11. Tabela zawiera dodatnie lokalne maksima, w tym późniejsze niższe maksimum; zero nie jest wynikiem dodatnim.
12. Pierwszy element plateau jest wybierany jako wiersz maksimum.
13. Tabela znajduje się na dole i jest płynnie przewijalna.
14. APK działa bez sieci na Google Pixel 10 Pro XL i Samsung Galaxy S21 Ultra.
15. UI nie wymaga poziomego przewijania całej strony.
16. Aktualizacja APK z inną wersją danych używa nowego snapshotu.
17. Finalny manifest APK nie zawiera uprawnienia `INTERNET`.
