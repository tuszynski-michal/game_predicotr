---
title: Admin application requirements
status: accepted
last_updated: 2026-07-27
---

# Wymagania modułu administracyjnego

## Forma aplikacji

Panel jest lokalną aplikacją webową uruchamianą na Windows. Korzysta z lokalnego Admin API i PostgreSQL. Nie jest usługą, z którą łączy się aplikacja mobilna.

## Zakres funkcjonalny

### Games

Administrator może:

- utworzyć grę,
- ustawić kod, nazwę i status,
- ustawić liczbę rzędów i kolumn za pomocą dwóch pól liczbowych,
- ustawić koszt jednego spinu,
- aktywować lub archiwizować grę.

Liczba rzędów i kolumn musi być dodatnia. W M1 konfiguracja testowa ma 3 rzędy i 5 kolumn. Zmiana wymiarów po utworzeniu danych wymaga nowej wersji reguł i datasetu; nie jest zwykłą edycją opublikowanej wersji.

Pierwszy pion interfejsu pokazuje osobne stany ładowania, pustego katalogu i
błędu lokalnego API z możliwością ponowienia. Kod gry jest edytowalny wyłącznie
podczas tworzenia rekordu. Archiwizacja wymaga jawnego potwierdzenia, pozostawia
rekord na liście i przekazuje wynik tekstem, nie tylko kolorem.

### Symbols

Administrator może:

- dodać symbol do gry,
- nadać stabilny kod i nazwę,
- dodać lokalny obraz referencyjny,
- oznaczyć symbol jako joker,
- ustawić kolejność wyświetlania,
- aktywować lub archiwizować symbol.

Panel wymaga najpierw wyboru gry i pokazuje jej symbole w kanonicznej kolejności
API. `mobileCode` oraz stabilny kod są edytowalne wyłącznie podczas tworzenia.
Aktywny symbol można zarchiwizować tylko osobną akcją z potwierdzeniem; rekord
pozostaje na liście i może zostać ponownie aktywowany przez edycję. Ścieżka
obrazu referencyjnego jest opcjonalną względną ścieżką POSIX. W tej iteracji
panel zapisuje metadane ścieżki, a nie binarną zawartość pliku.

Joker nie ma własnej wypłaty. Jeżeli w przyszłości gra będzie miała więcej niż
jeden rodzaj symbolu specjalnego, jego semantyka wymaga osobnej reguły zamiast
ukrytego traktowania wszystkich symboli specjalnych identycznie.

### Paylines

Jedynym obsługiwanym typem wzorca jest `PAYLINE`.

Administrator może:

- kliknąć `Dodaj wzór`,
- zobaczyć w modalu pustą siatkę o wymiarach gry,
- zaznaczyć kafelek, który zostaje podświetlony lub oznaczony,
- wybrać najwyżej jedną komórkę w każdej kolumnie,
- zapisać wzór dopiero po wybraniu dokładnie jednej komórki we wszystkich kolumnach,
- zobaczyć istniejące wzorce w tabeli, po jednym wzorze w wierszu,
- edytować, archiwizować lub usunąć nieopublikowany wzór.

Walidacja:

- `row_path` ma dokładnie tyle elementów, ile gra ma kolumn,
- każda wartość wskazuje istniejący wiersz,
- UI pokazuje wiersze od 1, a API normalizuje je do indeksów od 0,
- identyczny `row_path` nie może zostać dodany dwa razy do tej samej wersji reguł,
- nie można wybrać dwóch komórek w jednej kolumnie.

Dokładny wygląd modala i tabeli zostanie ustalony przy projektowaniu UI, ale powyższy kontrakt zachowania jest obowiązkowy.

### Payout rules

Administrator konfiguruje dla każdego zwykłego symbolu w wersji reguł:

- minimalną liczbę kolejnych symboli potrzebną do wygranej,
- wartość wygranej w kredytach osobno dla każdej długości od minimum do liczby
  kolumn,
- status aktywności reguł.

Domyślne `minimum_match_length` wynosi 3. Administrator może ustawić wartość od
2 do liczby kolumn; dzięki temu wybrane symbole mogą wygrywać już w pierwszej i
drugiej kolumnie. Dla pozostałych symboli może pozostać domyślne minimum 3.

Po wybraniu minimum panel pokazuje pola kredytów dla każdej wymaganej długości.
Przykład dla planszy 5-kolumnowej:

- minimum 2 wymaga payoutów dla długości 2, 3, 4 i 5,
- minimum 3 wymaga payoutów dla długości 3, 4 i 5.

Nie można opublikować wersji z brakującą wartością, aktywną regułą poniżej
minimum albo dwoma aktywnymi wpisami dla tej samej wersji reguł, symbolu i
długości. Wartości jednego symbolu muszą rosnąć wraz z długością.

Payout nie jest własnością payline. Te same wartości symbol/długość obowiązują na każdej aktywnej payline.
Każda wygrana musi zaczynać się w pierwszej kolumnie payline; panel nie
konfiguruje kolumny startowej.

### Layout data

Administrator może:

- wygenerować dane testowe,
- zaimportować dane przygotowane przez worker,
- sprawdzić liczbę rekordów i zakres `sequence_number`,
- znaleźć luki i duplikaty numerów,
- sprawdzić duplikaty sygnatur layoutu,
- podejrzeć layout jako planszę,
- odrzucić lub usunąć nieopublikowany import po jawnym potwierdzeniu,
- utworzyć niezmienną wersję datasetu po przejściu walidacji.

Warunki publikacji datasetu:

- dokładnie jedna pozycja dla każdego numeru w ciągłym zakresie,
- brak luk i duplikatów `sequence_number`,
- każda komórka zawiera symbol należący do gry,
- duplikaty treści layoutu są dozwolone i raportowane,
- kolejność layoutów jest deterministyczna.

### Jobs

Administrator widzi zadania typu:

- import,
- walidacja,
- obliczanie payoutów,
- generowanie snapshotu SQLite,
- przygotowanie APK.

Dla zadania widzi:

- status,
- etap i postęp,
- liczbę elementów poprawnych, błędnych i wymagających review,
- czas rozpoczęcia i zakończenia,
- wersję kodu/modelu,
- log błędów,
- możliwość wznowienia bez dublowania wyników.

### Manual review

Dla niepewnego elementu administrator otrzymuje:

- podgląd oryginalnego zdjęcia,
- podgląd wyciętej planszy i kafelka,
- przewidywany symbol lub numer,
- confidence score,
- listę alternatyw,
- możliwość zatwierdzenia, poprawienia albo odrzucenia.

Decyzja użytkownika jest zachowywana jako oznaczony przykład możliwy do wykorzystania przy kolejnych wersjach klasyfikatora.

### Mobile releases

Panel zawiera sekcję lub przycisk przygotowania wersji Android.

Administrator:

1. wybiera wersję datasetu i reguł dla każdej dołączanej gry,
2. uruchamia walidację kompletności,
3. uruchamia obliczanie payoutu każdego layoutu,
4. generuje niezmienny snapshot SQLite,
5. uruchamia przygotowanie wersjonowanego APK,
6. widzi status zadania, wersję, checksumy i ścieżki artefaktów,
7. może pobrać lub otworzyć katalog gotowego APK do ręcznej instalacji.

Wydanie:

- nie nadpisuje poprzedniego bez śladu,
- zapisuje wersje datasetów, reguł i algorytmu,
- zapisuje checksum snapshotu i APK,
- nie jest oznaczane jako gotowe, jeżeli walidacja lub build zakończyły się błędem,
- nie wysyła automatycznie APK do urządzeń ani sklepu.

Konkretny mechanizm uruchomienia Android build jest szczegółem architektury i może zostać zmieniony bez zmiany zachowania panelu.

## Pierwsza iteracja panelu

Pierwsza iteracja może ograniczyć się do:

- CRUD gier i symboli,
- edytora paylines,
- konfiguracji payoutów,
- generowania i walidacji mock layoutów,
- utworzenia wersji datasetu i reguł.

Import zdjęć i automatyczny build APK mogą być realizowane w kolejnych pionach funkcjonalnych, ale ich kontrakty są częścią docelowego panelu.

## Kryteria akceptacyjne pierwszej iteracji

1. Administrator tworzy grę 3 × 5 i ustawia koszt spinu.
2. Dodaje symbole `S1`–`S12` i oznacza joker.
3. Tworzy trzy poziome paylines przez modal siatki.
4. Nie może wybrać dwóch komórek w jednej kolumnie ani zapisać niepełnego wzorca.
5. Nie może zapisać duplikatu `row_path`.
6. Pozostawia dla większości symboli domyślne minimum 3, dla co najmniej jednego
   symbolu ustawia minimum 2 i uzupełnia wszystkie wymagane wartości kredytów.
7. Generuje lub importuje 1000 layoutów.
8. Widzi luki, błędy numeracji i duplikaty sygnatur.
9. Publikuje niezmienną wersję datasetu i reguł.
