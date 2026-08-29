---
title: Mobile application requirements
status: accepted
last_updated: 2026-08-01
---

# Wymagania aplikacji mobilnej

## Platforma i dystrybucja

- Główna platforma: Android.
- Interfejs jest projektowany przede wszystkim dla telefonu w orientacji pionowej.
- Aplikacja działa całkowicie offline już w M1.
- Aplikacja nie łączy się z Internetem, siecią lokalną, panelem ani backendem.
- Finalne APK M1 nie deklaruje uprawnienia Android `INTERNET`.
- Konfiguracja, sygnatury layoutów i obliczone payouty są dołączone do wersji APK w snapshotcie SQLite.
- Snapshot schema v4 może zawierać w layoucie kod `0`; aplikacja renderuje go
  jako `?`, ale nie pozwala użytkownikowi wprowadzić kodu `0` jako symbolu.
- Aktualny klient przyjmuje schema v3 i v4. Release v4 nie może być przekazany
  klientowi, który deklaruje wyłącznie zgodność z v3.
- Zmiana danych lub reguł wymaga utworzenia nowego wydania i ręcznego zainstalowania APK.
- Dystrybucja jest prywatna, na maksymalnie 3–5 urządzeniach; publikacja w sklepie nie jest wymagana.
- Wersja `0.1` wymaga odbioru na Google Pixel 10 Pro XL. Samsung Galaxy S21
  Ultra pozostaje urządzeniem kompatybilności dla późniejszego etapu i nie
  blokuje wydania `0.1`.

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
4. skonsolidowany wynik dopasowania i Targetu
5. tabela dodatnich lokalnych maksimów na samym dole

W dokumentacji domenowej obliczenie pozostaje nazywane `Target`. Od wersji 0.3
UI nie tworzy osobnej karty `Target obliczony`; wynik jednoznaczny ma nagłówek
`Układ znaleziony i obliczony`.

## Header

### Elementy

Od wersji 0.3 elementy są ułożone pionowo w następującej kolejności:

1. kompaktowa etykieta `ver {releaseVersion}` bez osobnego tytułu aplikacji i
   bez tekstu `OFFLINE`,
2. wybór gry,
3. rząd akcji `Next`, `Undo`, `Reset` na dole nagłówka, bezpośrednio nad
   planszą.

Informacja o trybie offline pozostaje właściwością wydania i diagnostyki, ale
nie zajmuje miejsca w głównym nagłówku.

### Zachowanie wyboru gry

- konfiguracja planszy, symbole i lokalny indeks wyszukiwania są odczytywane ze snapshotu,
- istniejący wybór layoutu jest czyszczony,
- wynik dopasowania i prognoza są czyszczone,
- sekcja Target wraca do stanu początkowego.

### Undo

- cofa ostatnią operację zmiany planszy,
- ręcznie dodany symbol jest jednym krokiem,
- automatyczne uzupełnienie lub przejście `Next` jest jednym atomowym krokiem,
- nie zmienia wybranej gry,
- po cofnięciu ponownie uruchamia lokalne wyszukiwanie kandydatów,
- gdy brak symboli, jest nieaktywny,
- automatyczne uzupełnienie można cofnąć jako jedną operację.

### Next

- znajduje się z lewej strony `Undo`,
- jest aktywny tylko wtedy, gdy aplikacja ma jednoznaczny anchor
  `sequence_number`,
- ładuje layout o kolejnym `sequence_number`; po ostatnim rekordzie przechodzi
  do pierwszego,
- jawnie załadowana kolejna pozycja pozostaje jednoznaczna nawet wtedy, gdy jej
  sygnatura występuje także w innych pozycjach sekwencji,
- taki layout jest prezentowany jako znana pozycja sesji, a nie jako nowy,
  nierozstrzygnięty wynik ręcznego exact matchingu,
- po zmianie uruchamia dopasowanie i Target dla aktualnego limitu skanu,
- nie wybiera arbitralnej pozycji w stanie `duplicate`, `not_found` ani
  `local_data_error`, jeżeli wcześniej nie ustalono jednoznacznego anchora,
- cała operacja jest jednym krokiem `Undo` i odtwarza także poprzedni wynik.

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
- od wersji 0.3 plansza nie ma osobnego tytułu `Layout` ani licznika
  `selected/total`,
- plansza znajduje się bezpośrednio pod nagłówkiem, bez komunikatu
  `Dane lokalne gotowe`,
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

- poniższe reguły dotyczą layoutu dopasowanego z danych wprowadzonych ręcznie,
  gdy aplikacja nie ma wcześniejszego jednoznacznego anchora; duplikat
  sygnatury jawnie załadowanej przez `Next` nie usuwa znanej pozycji sesji,
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
- od wersji 0.3 sekcja nie ma osobnego tytułu ani opisu,
- kafelki zawijają się do kolejnych rzędów; sekcja nie przewija się poziomo,
- każdy kafelek pokazuje jedną, niepogrubioną nazwę,
- aplikacja wybiera krótszą z niepustych `name_pl` i `name_en`; przy remisie
  wybiera polską, a przy braku obu używa kompatybilnościowego `name`,
- nazwa jest jednowierszowa, a nadmiar tekstu kończy się wielokropkiem,
- padding i wysokość są ograniczone, lecz dotykowy obszar aktywny zachowuje co
  najmniej 44 × 44 punkty logiczne,
- odstęp pomiędzy planszą a Selection jest minimalny,
- każdy kafelek ma nazwę dostępną dla czytnika ekranu,
- joker jest wizualnie oznaczony.

## Target

Sekcja jest aktywna wyłącznie dla jednoznacznego `sequence_number`.

### Zasięg obliczeń od wersji 0.3

- użytkownik ustawia `target_scan_limit` w kompaktowym polu liczbowym,
- wartość domyślna wynosi `10 000`, minimalna `1 000`, maksymalna `500 000`, a
  pole przyjmuje każdą liczbę całkowitą z tego zakresu,
- pole liczbowe jest używane zamiast liniowego suwaka, ponieważ szeroki zakres
  wymaga dokładnego wyboru i nie powinien zwiększać wysokości ekranu,
- efektywny zasięg wynosi `min(target_scan_limit, layout_count - 1)`,
- pełny cykl nadal jest dostępny, gdy limit jest równy lub większy od `N - 1`,
- zmiana limitu anuluje lub unieważnia poprzedni skan; dla jednoznacznej
  pozycji uruchamia nowe obliczenie,
- wynik i tabela dotyczą wyłącznie aktualnie ocenionego okna przyszłych spinów.

### Zasady

- rozpoznany layout jest spinem 0 bez kosztu i payoutu,
- pierwszy oceniany spin to następny layout w cyklicznej sekwencji,
- każdy oceniany spin zwiększa koszt skumulowany o `spin_cost`,
- każdy payout po drodze zwiększa `cumulative_payout`, także gdy wynik netto pozostaje ujemny,
- `net_credits = cumulative_payout - cumulative_cost`,
- wynik dodatni oznacza wyłącznie `net_credits > 0`,
- pełny cykl kończy się na layoucie bezpośrednio poprzedzającym spin 0,
- dla pełnego cyklu `N` layoutów ocenianych jest `N - 1` spinów; ograniczony
  skan kończy się wcześniej po osiągnięciu efektywnego limitu.

### Podsumowanie wyniku od wersji 0.3

- nie istnieje osobna karta `Target obliczony`,
- sukces ma nagłówek `Układ znaleziony i obliczony` oraz pokazuje numer i layout
  w formacie używanym wcześniej przez wynik Targetu,
- sukces ma zielony status bez dodatkowego opisu o uruchamianiu cyklu,
- duplikat ma status żółty lub pomarańczowy i opis problemu,
- brak layoutu i `local_data_error` mają status czerwony i opis problemu,
- status ma tekst lub ikonę dostępną dla technologii asystujących; sam kolor
  nie jest jedynym nośnikiem informacji,
- rozwinięte szczegóły zawierają tylko `Koszt spinu`, `Koszt` oraz
  `Suma końcowa`; etykieta `Wynik końcowy` zostaje zastąpiona,
- znika podpis wyjaśniający, że lokalne maksima znajdują się w tabeli.

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

### Powrót na górę

- po dotarciu do sekcji wyników Targetu pojawia się pływający przycisk powrotu
  na górę,
- przycisk pozostaje nad dolnym safe area, nie zasłania istotnej treści ani
  elementów tabeli,
- ma dostępną nazwę i odpowiedni obszar dotykowy,
- po użyciu przewija główną listę ekranu do początku.

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
14. APK wersji `0.1` działa bez sieci na Google Pixel 10 Pro XL.
15. UI nie wymaga poziomego przewijania całej strony.
16. Aktualizacja APK z inną wersją danych używa nowego snapshotu.
17. Finalny manifest APK nie zawiera uprawnienia `INTERNET`.

## Kryteria akceptacyjne wersji 0.3

1. Nagłówek pokazuje `ver {releaseVersion}`, wybór gry oraz rząd
   `Next`, `Undo`, `Reset` w ustalonej kolejności.
2. Nie są renderowane: `Sequence Target`, `OFFLINE`, `Layout`, licznik
   `selected/total`, `Dane lokalne gotowe` ani nagłówek/opis Selection.
3. `Next` przechodzi do kolejnego rekordu z zawinięciem, przelicza wynik i można
   go cofnąć jednym `Undo`.
4. `Next` nie uruchamia Targetu bez jednoznacznego anchora sekwencji.
5. Kafelki Selection zawijają się, mają jedną krótszą etykietę z ellipsis i nie
   wymagają poziomego przewijania.
6. Limit Targetu akceptuje 1 000–500 000, domyślnie wynosi 10 000 i nigdy nie
   obejmuje spin 0.
7. Zmiana limitu ponownie oblicza wynik dla jednoznacznego layoutu, a koszt,
   payout i maksima dotyczą dokładnie nowego okna.
8. Wynik unikalny, duplikat, brak layoutu i błąd danych mają skonsolidowaną,
   dostępną prezentację o właściwej semantyce kolorów.
9. Rozwinięte podsumowanie zawiera tylko `Koszt spinu`, `Koszt` i
   `Suma końcowa`.
10. Przy długich wynikach przycisk powrotu na górę pojawia się we właściwym
    miejscu i działa bez zasłaniania tabeli.
11. Główny ekran nie ma poziomego overflow i pozostaje użyteczny w orientacji
    pionowej na Google Pixel 10 Pro XL.
12. APK nadal nie deklaruje `INTERNET` i wykonuje cały przepływ offline.
