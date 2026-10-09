---
title: Admin application requirements
status: accepted
last_updated: 2026-10-09
---

# Wymagania modułu administracyjnego

Ten dokument pozostaje źródłem obowiązującego zachowania wdrożonego do `0.1`.
Planowana reorganizacja nawigacji i workflow dla `0.2` znajduje się w
`ADMIN_APP_V0_2.md`; zaakceptowane decyzje tego planu nie zmieniają wdrożonego
kontraktu `0.1` przed rozpoczęciem zadań `0.2`.

## Forma aplikacji

### Porównanie siatek V3 — TASK-0805

Domyślnie wyłączony panel shadow umożliwia jawne uruchomienie porównania dla
co najwyżej 20 wybranych, zmaterializowanych zdjęć gry z profilem sieci.
Nie zastępuje preflightu źródeł w stagingu. Lista zachowuje numerację i
pokazuje status joba, błędy, wersję modelu oraz aktualność wyniku.

Na tym samym zdjęciu panel pokazuje obecną siatkę i pełne węzły propozycji.
Oznaczenia tekstowe uzupełniają kolory. Brak planszy, dodatkowe wykrycia i
pola częściowe lub poza obrazem są jawne. Mumie mają komunikat o braku
kalibracji. Każda propozycja wymaga ręcznego przeglądu.

Bieżący slot z dostępną propozycją można otworzyć w istniejącej lokalnej
korekcie Reviewera. Edytor oparty na narożnikach opisuje odtworzoną siatkę
jako szkic do korekty; nie udaje zachowania wszystkich węzłów sieci.
Wybór symboli, skróty i natychmiastowy podgląd zachowują TASK-0841/D-488.
Nieaktualny wynik pozostaje widoczny, ale nie udostępnia propozycji do zapisu.
Start, podgląd i odczyt shadow nie zatwierdzają żadnych siatek ani symboli.

### Usuwanie starej gry przed partycjonowaniem — TASK-0516

Utrzymaniowa komenda usuwania `777 v0.1` jest odrębna od zwykłych akcji Admina.
Domyślnie wykonuje wyłącznie preview. Wykonanie wymaga zgodnego fingerprintu,
potwierdzenia dokładnej tożsamości gry i sprawdzonego lokalnego archiwum układów
do wyszukiwania na czacie. Porównuje jego zawartość i symbole z PostgreSQL przed
pierwszym usunięciem. Nie dotyka katalogu operatora `Documents/777`.

Postęp przedstawia wyłącznie zatwierdzone porcje, bieżący etap i rzeczywiste
liczby usuniętych rekordów. Nie pokazuje procentu opartego na nieznanym totalu.
Awaria pozostawia wznawialny checkpoint i trwałą blokadę zapisów usuwanej gry;
nie blokuje w ten sposób innych gier. `database_done` oznacza zakończenie części
bazodanowej, nie wykonanie GC plików. Implementacja nie autoryzuje wykonania
operacji na danych. Szczegóły: `../process/RESUMABLE_LEGACY_DELETION.md`.

Panel jest lokalną aplikacją webową uruchamianą na Windows. Korzysta z lokalnego Admin API i PostgreSQL. Nie jest usługą, z którą łączy się aplikacja mobilna.

Lokalny Admin nie ma pozornego ekranu logowania dla jednego właściciela
Windows. Wszystkie mutacje wysyłają stały sygnał intencji `local-owner`, a API
sprawdza loopback i `Origin`. Operacje wysokiego wpływu wysyłają dodatkowo
potwierdzenie oraz dokładny cel; bez nich API nie zmienia danych. Zdalny
Reviewer nie otrzymuje tych uprawnień i zachowuje własną ograniczoną sesję.

## Zakres funkcjonalny

### Games

Administrator może:

- utworzyć grę,
- ustawić kod, nazwę i status,
- ustawić liczbę rzędów i kolumn za pomocą dwóch pól liczbowych,
- ustawić koszt jednego spinu,
- aktywować lub archiwizować grę.

Karta gry pokazuje wersję i generację magazynu. Podczas `migrating`, `deleting`
lub `blocked` wyświetla jawny tryb tylko do odczytu i blokuje mutacje katalogu;
wybór gry i bezpieczne odczyty pozostają dostępne. Backend pozostaje źródłem
prawdy i niezależnie od UI odrzuca zapis objęty maintenance.

Przy tworzeniu i edycji gry panel wybiera format strony: pełną stronę z ramką
albo format wymagający doprecyzowania. Karta katalogu pokazuje bieżący status
wspólnej geometrii, konkretną przyczynę i, gdy jest bezpiecznie dostępny,
numer profilu shared. Panel nie prosi o kolor ramki, lokalną kotwicę ani obraz;
gotowość do preflightu nadal wymaga ręcznej weryfikacji pierwszego importu.

Pole „Format strony” oferuje także profile silnika siatek „777 v2” i „Mumie”
(TASK-0830). Profil wskazuje zamrożony model `neural_grid` w zarządzanym
katalogu modeli; dla gotowości geometrii działa jak pełna strona z ramką. Pod
polem panel opisuje model wybranego profilu, informuje, że profil 777 v2 służy
także przyszłym wersjom gry 777, i pokazuje stan modelu z API (dostępny, brak
plików, niezgodny SHA-256). Karta gry na liście pokazuje format strony, a dla
profilu także stan jego modelu. Brak modelu nie blokuje zapisu gry.

Formularz tworzenia i edycji gry ma select „Supergra” (TASK-0931, D-535) z
opcją „Brak” i rodzajami supergry z rejestru w kodzie
(`GET /api/v1/admin/super-game-kinds`); pierwszym rodzajem jest „Wild super spins”.
Admin nie trzyma własnej kopii listy: do czasu wczytania rejestru albo przy
błędzie API select pokazuje „Brak” i bieżącą wartość gry, a pod polem
komunikat błędu. Karta gry pokazuje `Supergra: <etykieta>`. Gra 777 zostaje
bez supergry. Rodzaju nie można zmienić na „Brak”, dopóki którykolwiek symbol
gry ma rolę „Uruchamia supergrę” (`SUPER_GAME_KIND_IN_USE`).

Po greenfield cutoverze nowa gra jest dostępna do dalszej konfiguracji dopiero,
gdy API zakończy obowiązkowy provisioning V2 i zwróci
`storageWriteAvailable=true`. Brak registry jest pokazywany jako `blocked`, a
nie jako gotowy legacy magazyn. Pusty katalog jest poprawnym stanem ekranu i
nie blokuje globalnych workflowów niezależnych od gry.

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
- oznaczyć symbol jako Wild,
- oznaczyć symbol jako „Uruchamia supergrę” i wybrać próg 3, 4 albo 5 sztuk,
- ustawić kolejność wyświetlania,
- aktywować lub archiwizować symbol.

Panel wymaga najpierw wyboru gry i pokazuje jej symbole w kanonicznej kolejności
API. `mobileCode` oraz stabilny kod są edytowalne wyłącznie podczas tworzenia.
Aktywny symbol można zarchiwizować tylko osobną akcją z potwierdzeniem; rekord
pozostaje na liście i może zostać ponownie aktywowany przez edycję. Ścieżka
obrazu referencyjnego jest opcjonalną względną ścieżką POSIX. W tej iteracji
panel zapisuje metadane ścieżki, a nie binarną zawartość pliku. Dla istniejącej
grafiki edycja symbolu udostępnia read-only podgląd w modalu. Podgląd pobiera
checksum-bound asset z Admin API, pokazuje stan ładowania i kontrolowany błąd;
nie zmienia wskazania grafiki ani pozostałych danych symbolu.

Formularz symbolu ma checkbox „Wild” (dawniej „Joker”; kolumna
`symbols.is_wildcard` bez zmian) oraz checkbox „Uruchamia supergrę”
(TASK-0931, D-535). Zaznaczenie drugiego odsłania select „Trzy symbole /
Cztery symbole / Pięć symboli” (`superGameTriggerCount` 3/4/5); odznaczenie
zapisuje `null`. Checkbox „Uruchamia supergrę” jest aktywny tylko wtedy, gdy
gra ma rodzaj supergry inny niż „Brak”; w przeciwnym razie panel podpowiada
wybór rodzaju w zakładce Gry, a API zwraca `SUPER_GAME_KIND_REQUIRED`. Już
zapisaną rolę zawsze można usunąć. Karta symbolu pokazuje znaczniki „Wild” i
„Uruchamia supergrę: trzy symbole” (odpowiednio dla progu). Symbol może mieć
obie role jednocześnie (Mumia w grze Mumie).

Wild bez roli „Uruchamia supergrę” nie ma własnej wypłaty. Symbol
uruchamiający supergrę ma wypłaty za liczbę sztuk na planszy (niezależnie od
linii) i nie ma minimum liniowego. Kolejne rodzaje symboli specjalnych
wymagają osobnej, jawnej reguły zamiast ukrytego traktowania wszystkich
symboli specjalnych identycznie.

### Paylines

Jedynym obsługiwanym typem wzorca jest `PAYLINE`.

Administrator może:

- kliknąć `Dodaj wzór`,
- zobaczyć w modalu pustą siatkę o wymiarach gry,
- podać stabilny kod wzorca; opisowa nazwa nie jest osobnym polem i przy
  tworzeniu przyjmuje wartość kodu,
- zaznaczyć kafelek, który zostaje podświetlony lub oznaczony,
- wybrać najwyżej jedną komórkę w każdej kolumnie,
- zapisać wzór dopiero po wybraniu dokładnie jednej komórki we wszystkich kolumnach,
- zobaczyć istniejące wzorce w tabeli, po jednym wzorze w wierszu,
- edytować, archiwizować lub usunąć nieopublikowany wzór. „Archiwizuj”
  wyłącza wzorzec, ale zostawia jego kod i ścieżkę zajęte; „Usuń” (D-477) po
  potwierdzeniu „Usuń trwale” kasuje go z wersji roboczej i pozwala dodać nowy
  wzorzec z tym samym kodem albo ścieżką.

Walidacja:

- `row_path` ma dokładnie tyle elementów, ile gra ma kolumn,
- każda wartość wskazuje istniejący wiersz,
- UI pokazuje wiersze od 1, a API normalizuje je do indeksów od 0,
- identyczny `row_path` nie może zostać dodany dwa razy do tej samej wersji reguł,
- nie można wybrać dwóch komórek w jednej kolumnie.

Administrator nie ustawia ręcznie kolejności prezentacji. Nowy wzorzec trafia
za istniejące wzorce wersji; kolejność służy wyłącznie deterministycznemu
wyświetlaniu i nie wpływa na obliczenie wypłat.

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

Pierwszy zapis utrwala konfigurację symbolu w konkretnej wersji reguł.
Podniesienie minimum archiwizuje payouty poniżej nowego progu. Role symbolu
(Wild, „Uruchamia supergrę”) można zmieniać, dopóki symbol nie występuje w
opublikowanej (lub zarchiwizowanej) wersji reguł; potem API zwraca
`SYMBOL_RULES_IDENTITY_IN_USE`, ponieważ zmiana unieważniłaby wersjonowane
minimum i wypłaty (TASK-0931, D-535). Gdy symbol w ten sposób zyskuje rolę
Wild albo „Uruchamia supergrę”, jego minimum w wersjach roboczych zostaje w tej
samej transakcji wyczyszczone (`null`); payouty zostają bez zmian, a raport
gotowości pokazuje ewentualne niezgodności.

Dla symbolu z rolą „Uruchamia supergrę” zakładka payoutów pokazuje pola
„N sztuk na planszy” dla N od 2 do `rows × columns` zamiast pól „N kolejnych
symboli” i nie pokazuje minimum. Każde pole jest opcjonalne (puste = brak
wypłaty dla tej liczby, zapis wyłącza wcześniejszą wypłatę), a wypełnione
wartości muszą ściśle rosnąć wraz z liczbą sztuk. Istniejące wypłaty Mumii
3/4/5 → 20/200/2000 pozostają i oznaczają liczbę sztuk na planszy.

Nie można opublikować wersji z brakującą wartością, aktywną regułą poniżej
minimum albo dwoma aktywnymi wpisami dla tej samej wersji reguł, symbolu i
długości. Wartości jednego symbolu muszą rosnąć wraz z długością.

Payout nie jest własnością payline. Te same wartości symbol/długość obowiązują na każdej aktywnej payline.
Każda wygrana musi zaczynać się w pierwszej kolumnie payline; panel nie
konfiguruje kolumny startowej.

### Publikacja wersji reguł

Panel udostępnia dla draftu raport gotowości obejmujący wszystkie blokady, a
nie tylko pierwszy błąd. Publikacja jest dostępna dopiero po spełnieniu
następujących warunków:

- istnieje co najmniej jedna aktywna payline,
- istnieje co najmniej jeden aktywny zwykły symbol,
- każdy aktywny zwykły symbol ma kompletny payout dla każdej długości od
  własnego minimum do liczby kolumn,
- payouty symbolu rosną ściśle wraz z długością,
- Wild bez roli „Uruchamia supergrę”, nieaktywny symbol oraz długość poza
  zakresem nie mają aktywnego payoutu,
- symbol z rolą „Uruchamia supergrę” wymaga gry z rodzajem supergry innym niż
  „Brak” (`SUPER_GAME_KIND_REQUIRED`), nie ma minimum
  (`SUPER_GAME_TRIGGER_MINIMUM_NOT_ALLOWED`), a jego wypłaty za sztuki mają
  liczby `2..rows × columns` i ściśle rosną; nie jest wymagana wypłata dla
  każdej liczby i symbol nie liczy się jako aktywny zwykły symbol.

Przed publikacją administrator potwierdza, że wersja stanie się niezmienna.
Panel blokuje podwójne wysłanie żądania. Po publikacji wymiary, koszt spinu,
paylines, konfiguracje symboli i payouty są tylko do odczytu. Opublikowaną
wersję można jawnie zarchiwizować; archiwizacja zachowuje czas publikacji i nie
usuwa rekordu.

### Layout data

Administrator może:

- wygenerować deterministyczny staging 1000 layoutów z podanym seedem i
  opublikowaną wersją reguł,
- zaimportować dane przygotowane przez worker,
- wybrać opublikowaną wersję reguł tej samej gry i uruchomić walidację
  zakończonego surowego importu,
- sprawdzić liczbę rekordów i zakres `sequence_number`,
- znaleźć luki i duplikaty numerów,
- sprawdzić duplikaty sygnatur layoutu,
- podejrzeć layout jako planszę,
- odrzucić lub usunąć nieopublikowany import po jawnym potwierdzeniu,
- utworzyć niezmienną wersję datasetu po przejściu walidacji.

Mock generator używa wymiarów oraz aktywnych symboli wskazanej opublikowanej
wersji reguł. Panel pokazuje seed, wersję generatora, liczbę layoutów i status
stagingu. Powtórzenie z tym samym seedem tworzy nowy numer wersji datasetu, ale
identyczny logiczny ciąg layoutów.

Raport integralności pokazuje deklarowaną i rzeczywistą liczbę rekordów, zakres
sekwencji, każdą blokadę oraz grupy duplikatów sygnatur z numerami pozycji.
Przy dużej liczbie problemów panel może pokazać ograniczoną próbkę, ale zawsze
wyświetla dokładny licznik i informację o obcięciu. Statusy `OK`, `Ostrzeżenie`
i `Blokada` są przekazywane tekstem, nie tylko kolorem.

Warunki publikacji datasetu:

- dokładnie jedna pozycja dla każdego numeru w ciągłym zakresie,
- brak luk i duplikatów `sequence_number`,
- każda komórka zawiera symbol należący do gry,
- duplikaty treści layoutu są dozwolone i raportowane,
- kolejność layoutów jest deterministyczna.

Podgląd jest stronicowany w stabilnej kolejności `sequence_number` i pokazuje
komórki row-major jako siatkę o wymiarach wersji. Przed publikacją panel ponownie
pokazuje raport i wymaga jawnego potwierdzenia niezmienności. Publikacja ponownie
waliduje dane po stronie serwera pod blokadą transakcyjną, a po sukcesie
pokazuje numer wersji, liczbę layoutów i `sourceJobId`. Przycisk jest dostępny
wyłącznie dla raportu bez blokad i nie pozwala na podwójny submit.
Idempotentne ponowienie zwraca tę samą wersję. Opublikowaną wersję można jawnie
zarchiwizować; archiwizacja zachowuje `published_at` i wszystkie layouty.

Odrzucenie nieopublikowanego importu jest osobną operacją destrukcyjną. Panel
pokazuje pełne identyfikatory joba walidacji i powiązanego joba importu, wymaga
przepisania dokładnego identyfikatora importu oraz osobnego kliknięcia
potwierdzającego. Operacja usuwa surowe i wszystkie znormalizowane wiersze tego
importu, ale zachowuje joby jako audyt. Backend blokuje odrzucenie, gdy staging
jest używany przez dataset albo przez aktywną walidację.

### Jobs

Administrator widzi zadania typu:

- import,
- walidacja,
- obliczanie payoutów,
- generowanie snapshotu SQLite,
- przygotowanie APK.

Dla zadania widzi:

- status,
- opis pracy zamiast samego technicznego typu, np. `Ładowanie zdjęć`,
  `Wyznaczanie siatki i cięcie plansz`, `Rozpoznawanie symboli` albo
  `Tworzenie geometrii siatek`; opis odzwierciedla bieżący etap, a nie zmienia
  typu ani semantyki joba,
- dla importu katalogowego oraz walidacji geometrii: zakres źródłowy z nazwy
  stagingu, np. `19810–45162`, zamiast technicznego identyfikatora gry w
  kompaktowym podsumowaniu; gdy źródło nie ma poprawnej nazwy zakresu, panel
  zachowuje bezpieczny kontekst joba bez ujawniania ścieżki lokalnej; starsze
  joby mogą użyć wyłącznie nazwy ostatniego katalogu, jeżeli ma format zakresu,
- etap i postęp,
- dla preflightu geometrii osobny postęp bieżącej fazy: pierwszy przebieg,
  dodatkowe dopasowanie z numerem przebiegu albo zapis manifestu; zakończenie
  pierwszego przebiegu nie może pokazywać fałszywego `100%` całego joba,
- dla aktywnego joba czytelny stan świeżości heartbeat: aktywna praca,
  oczekiwanie na pierwszy sygnał albo ostrzeżenie o nieświeżym workerze,
- liczbę elementów poprawnych, błędnych i wymagających review,
- czas rozpoczęcia i zakończenia,
- wersję kodu/modelu,
- log błędów,
- możliwość wznowienia bez dublowania wyników.

Wspólne statusy to `created`, `processing`, `waiting_for_review`, `completed`,
`failed` i `cancelled`. Nazwa etapu workflow jest osobnym polem. Anulowanie
przed startem kończy job od razu, a anulowanie podczas pracy staje się żądaniem
obsługiwanym przez worker w bezpiecznym punkcie.

Pierwszy ekran operatorski pokazuje 50 najnowszych rekordów i pozwala filtrować
je po statusie oraz typie. Dla `created` i `processing` odświeża listę co 2
sekundy bez nakładania requestów; poza aktywną pracą pozostawia ręczny przycisk
odświeżenia. Nieznany `progress.total` nie ukrywa bieżącego licznika. Cancel
wymaga potwierdzenia, a processing z `cancelRequestedAt` pokazuje tekstowo
oczekiwanie na bezpieczny checkpoint. Retry jest dostępne dla `failed` i
`waiting_for_review` i aktualizuje ten sam rekord na liście.

Dla importu `image_directory` rozwinięte szczegóły pokazują dokładne agregaty
plików, grupowanie etapów, czas, throughput i ograniczoną listę plików.
Administrator może ponowić dokładnie nieudany etap jednego pliku.

Ten sam widok pokazuje read-only inwentarz przestrzeni
`originals/working/crops/training/models/exports`, liczbę plików i rozmiar oraz
jednoznaczny komunikat, że automatyczne usuwanie jest wyłączone. Panel nie ma
akcji kasowania. Administrator może utworzyć lub ponownie wykorzystać
niezmienny eksport diagnostyczny joba, zobaczyć jego SHA-256, rozmiar, liczbę
wyeksportowanych błędów i znacznik obcięcia oraz pobrać plik po ponownej
weryfikacji checksumy. Loading, pusty stan, błąd i blokada podwójnego submitu
są jawne.

### Manual review

Dla niepewnego elementu administrator otrzymuje:

- podgląd oryginalnego zdjęcia,
- podgląd pełnej wyprostowanej planszy 5 × 3, siatki i wybranego kafelka,
- przewidywany symbol lub numer,
- confidence score,
- listę alternatyw,
- możliwość zatwierdzenia, poprawienia albo odrzucenia.

Bootstrap etykiet symboli działa na poziomie całego layoutu. Panel pokazuje
piętnaście komórek, pozwala przypisywać symbole skrótami, zatwierdzić layout i
wyróżnia komórki niepewne. Jeżeli granice są błędne, administrator przechodzi
do osobnego trybu geometrii i przesuwa cztery narożniki zewnętrznych granic
siatki symboli 5 × 3 na zdjęciu, a nie narożniki czerwonej ramki. Cztery
dodatkowe uchwyty krawędziowe są wyprowadzane z głównego quadu i nie zmieniają
zapisywanej semantyki. Podgląd pokazuje ukośną siatkę oraz wszystkie 15
finalnych cropów source-direct.
Edytor pokazuje zakres profilu `(source_group, board_position)`, jego anchory,
wersję oraz zachowanie exact/interpolation/clamp przed zapisaniem nowej,
niezmiennej wersji profilu kalibracji.

Lokalny bootstrap przed wdrożeniem docelowych `review_items` pokazuje obok
siebie kanoniczną planszę 500 × 300, siatkę 15 cropów i paletę symboli.
Administrator może filtrować plansze niedokończone, kompletne lub zawierające
odrzucenie, przejść bezpośrednio do `sequence_number` i wznowić częściową
planszę po restarcie. Każda komórka ma widoczny stan; zapis nie może
automatycznie przypisać symbolu na podstawie OCR albo podobieństwa obrazu.

Decyzja użytkownika jest zachowywana jako oznaczony przykład możliwy do
wykorzystania przy kolejnych wersjach klasyfikatora. Model nie uczy się
niejawnie po pojedynczym kliknięciu: ponowne uczenie tworzy nową wersję
datasetu i modelu, a auto-accept wymaga osobno zaakceptowanego progu.

Docelowy ekran `review_items` pozwala administratorowi wybrać niezmienny batch,
filtrować status i przechodzić
po kolejce w `selection_rank` i dla każdej planszy widzi oryginał,
wyprostowaną planszę, wszystkie 15 cropów row-major, przewidywany symbol,
confidence, entropy i maksymalnie trzy alternatywy historycznego batcha M6.
Brak lokalnego obrazu
pokazuje kontrolowany placeholder, ale nie ukrywa metadanych.

Zapis decyzji obejmuje zawsze całą planszę. Administrator potwierdza geometrię,
zatwierdza 15 predykcji albo zmienia wybrane symbole z aktywnego katalogu.
Odrzucenie wymaga powodu i nie tworzy próbek. Panel pokazuje numer bieżącej
rewizji, pełną historię decyzji i kontrolowany konflikt po zmianie elementu w
innym żądaniu. Eksport oznaczonego feedbacku jest dostępny dopiero po
rozwiązaniu całego batcha; ponowienie tego samego stanu nie tworzy duplikatu,
a zmieniony stan tworzy nową wersję.

### Wyszukiwanie plansz z niepełnym wzorem

Edytor wzoru pozwala wskazać aktywny symbol, pozostawić pole puste albo jawnie
oznaczyć je jako `?`. Puste pole i `?` są dla rankingu równoważnym brakiem
dowodu: pozostają widoczne w lokalnym wzorze i historii `Cofnij`, ale nie są
wysyłane jako znana pozycja i nie wchodzą do denominatora. Wzór zawierający
wyłącznie puste pola lub `?` nie może uruchomić wyszukiwania.

Operator wybiera kolejność automatycznego przechodzenia pól: kolumnami albo
wierszami. Domyślnie edytor przechodzi pierwszą kolumnę z góry na dół, a potem
kolejne kolumny. Zmiana kolejności zachowuje zawartość wzoru i wybiera pierwsze
wolne pole w nowym porządku. Wizualny układ oraz kanoniczne indeksy komórek
pozostają row-major niezależnie od sposobu wprowadzania.

Paletę obsługuje też klawiatura (TASK-0657): `1`–`9` wstawia aktywny symbol o
tym numerze (kolejność `displayOrder` z katalogu gry, numer widoczny na
przycisku), `0` albo `?` wstawia nieznany `?`, `Backspace` wykonuje `Cofnij`, a
`Enter` uruchamia wyszukiwanie. Skróty nie działają podczas pisania w polu
tekstowym (np. „Liczba wyników”) ani z Ctrl/Alt/Meta; `Enter` na kontrolce
poza edytorem wzoru (np. w wynikach) zachowuje natywne działanie.

Zapisane `?` w znalezionej planszy nie daje punktu, nie zwiększa liczby
dokładnych dopasowań ani sprzeczności. Znany symbol zapytania zestawiony z `?`
jest raportowany jako brak danych. Wyniki zachowują deterministyczną kolejność:
score, liczba exact, ważone alternatywy, mniej sprzeczności, zatwierdzony status,
`sequence_number` i stabilna tożsamość źródła.

Dowód planszy oczekującej (D-462, TASK-0722): komórka zweryfikowana w
`Weryfikacji symboli` jest pewnym symbolem bez alternatyw od chwili zapisu
decyzji — pojedynczej albo z joba masowego — niezależnie od pozostałych
komórek i od zatwierdzenia planszy, siatki lub zdjęcia. Komórka ze zgłoszonym
problemem (`Zła siatka`, oczekujący `Nieczytelny`, `Poza kadrem`) oraz
zatwierdzone `?` są brakiem dowodu. Zatwierdzenie dotyczące innych pikseli
niż bieżące nie jest dowodem do ponownej weryfikacji. Pozostałe komórki
korzystają z predykcji modelu. Tę samą projekcję czyta „Przybliżona wygrana”.

Gra może zostać przełączona na zamrożone archiwum wyszukiwania dopiero po
pełnym, checksumowanym backfillu. Wynik archiwalny zachowuje ten sam ranking i
obraz całej planszy, ale nie ujawnia ani nie wymaga identyfikatora review,
recognized board, importu lub joba. Admin wybiera adres obrazu według jawnego
`assetMode`; checksum-bound odczyt archiwalny nie może wrócić do assetu
operacyjnego jako fallback. Częściowe albo nieudane archiwum blokuje odczyt tej
gry zamiast mieszać dwa źródła.

**D-479 (TASK-0784) — obowiązuje ponad starszymi opisami tej sekcji.**
Wyszukiwanie zawsze obejmuje wszystkie plansze; radio „Zakres wyszukiwania”
nie istnieje. Nagłówek wyników pokazuje dopasowanie i numer planszy, bez
statusu. W „Przybliżonej wygranej” tytułem sekcji jest „Plansza startowa #N
· X spinów”; nie ma kafelków podsumowania (rozpoznane wypłaty, koszt spinów,
bilans, maksymalny wkład) ani wiersza „Reguły v… · koszt spinu”. „Bilans”
nazywa się „kasa na czysto”, „wypłata” — „wygrana” (termin „linie wypłat”
zostaje). Etykieta punktu wykresu i lista przypiętych punktów podają: spiny,
kasę na czysto, wkład (na czerwono) i „kasę na maszynie” = wkład + kasa na
czysto. Okno „Pokaż planszę” ma do 1180 px szerokości; zdjęcie planszy w nim ma
najwyżej 800 px (TASK-0788), obok jest legenda linii.

**TASK-0786 — obowiązuje ponad starszymi opisami wykresu.** Etykiety punktów
(najechanego i przypiętych) są rysowane na obszarze danych wykresu, nie w
pasie nad nim: obok punktu — z lewej albo prawej, nad albo pod — tam, gdzie
nie zasłaniają linii wykresu ani innej etykiety; z punktem łączy je
przerywana linia. Gdy obok brakuje miejsca, etykieta trafia dalej od punktu.
Obszar danych zajmuje całą wysokość wykresu. Można przypiąć najwyżej 6
punktów.

**TASK-0787 — tooltip wykresu (zmienia powyższe).** Etykieta punktu ma trzy
linie, bez pogrubień, jedną czcionką: „378 spinów” po lewej i „wkład: X” na
czerwono po prawej (jedna linia), niżej „Kasa na czysto: X” i „Kredyty maszyna: N”.
„Kredyty maszyna” (dawniej „Kasa na maszynie”, wkład + kasa na czysto) są zawsze w
pełnych kredytach, niezależnie od wybranej jednostki. „Wygrana” i „Kasa na
czysto” w tabeli i w etykiecie są zaokrąglane do pełnych złotych (kredyty nie
mają części dziesiętnych); wkład zachowuje grosze.

Liczba zwracanych wyników jest jawnym parametrem operatora: input „Liczba
wyników” nad panelem, domyślnie 15 (D-476), w zakresie 1–100 (istniejący
limit techniczny endpointu). Zakres wyszukiwania („Wszystkie plansze” /
„Tylko zatwierdzone”) jest pokazywany w sekcji wyników, pod nagłówkiem
karuzeli; jego zmiana przy widocznych wynikach powtarza wyszukiwanie tego
samego wzoru i zachowuje wybraną planszę, jeżeli nadal jest w wynikach. Zmiana liczby wyników nigdy nie zmienia dopasowania,
rankingu ani zakresu wygranej opisanego niżej — to dwa niezależne parametry.
Jeżeli wybrana plansza pozostaje w nowych wynikach, wybór jest zachowywany;
w przeciwnym razie operator jednoznacznie wraca do pierwszego wyniku.

Oznaczenie supergry (TASK-0935, D-535): plansza, która w opublikowanej
generacji serii jest triggerem albo spinem serii, ma na karcie wyniku i w
wierszu przybliżonej wygranej złote wyróżnienie i etykietę „Supergra: trigger”,
„Supergra: spin k/długość, symbol X” albo, dopóki serii brak super symbolu,
„Supergra: super symbol do zdefiniowania”; uzupełniają ją uwagi o serii
niepełnej i o triggerze opartym na predykcji. Gdy serie są przeliczane
(`superGameState.fresh = false`), cały wynik — także pusty i plansze bez
oznaczenia — pokazuje ostrzeżenie „Serie w trakcie przeliczania”. Tylko w
lokalnym Adminie oznaczenie ma link do widoku serii w sekcji „Supergry”
(„Zdefiniuj super symbol” dla serii bez symbolu, w pozostałych „Pokaż serię”,
otwierany w nowej karcie); panel zarządzania i Reviewer pokazują wyłącznie
etykietę, bez linku i bez identyfikatora serii. Gra bez rodzaju supergry nie ma
oznaczeń ani ostrzeżenia.

### Przybliżona wygrana

Pod podglądem aktualnie wybranej znalezionej planszy dostępna jest rozwijana
podsekcja „Przybliżona wygrana”. Liczy ostrożne, dolnoograniczone
oszacowanie payoutu dla `N` kolejnych pozycji sekwencji po wybranej planszy
`S` (zakres `S+1…S+N`; `S` nigdy nie wchodzi do wyniku), używając tego
samego kalkulatora payoutu co wydania mobilne (`payout-v3-unknown-prefix-stop`;
dla gry z symbolem uruchamiającym supergrę `payout-v4-wild-count`)
i tej samej definicji pełnego cyklu z zawijaniem co mobilna prognoza celu.

**Wersja reguł (D-535, TASK-0932).** W lokalnym Adminie obok kontrolek
zakresu stoi select „Wersja reguł”: „Najnowsza opublikowana” (domyślnie)
oraz wersje `draft` i opublikowane gry, np. „v2 · draft”, „v1 ·
opublikowana” (wersje zarchiwizowane są pominięte). Wybór wersji `draft`
pokazuje notę „Podgląd wersji roboczej” i liczy zakres z tej wersji bez jej
publikowania; wybór nie jest zapamiętywany. Okno „Pokaż planszę” otwarte z
wiersza liczy tą samą wersją i ma ten sam select; zmiana wersji w oknie
pokazuje odczyt planszy dla wybranej wersji z dopiskiem „Dla wybranej wersji
reguł” zamiast porównania z tabelą. Udostępniony panel online i panel
zarządzania nie mają tego selectu. W wierszu tabeli wypłata za sztuki symbolu
uruchamiającego jest pokazana jako dopisek „w tym sztuki: Mumia ×3 → 20”
(już wliczona do wypłaty wiersza).

**Supergra w prognozie (D-537, TASK-0936).** Spin serii supergry jest
darmowy: wiersz ma dopisek „darmowy spin”, a koszt spinów sumuje koszt
każdej pozycji (0 w serii, koszt reguł poza nią, także na planszy
wyzwalającej). Wiersz z wynikiem prowizorycznym (seria bez super symbolu,
plansza serii z nieznanym polem, a w czasie przeliczania serii każda
plansza gry) ma wyróżniony
dopisek „prowizoryczny”; nad tabelą komunikat „Wyniki prowizoryczne
(supergra): N plansz, razem X” wyjaśnia, że nie są wliczone do wypłat ani
bilansu i mogą wzrosnąć albo zmaleć. Okno „Pokaż planszę” dla planszy serii
pokazuje kolumny rozwiniętego super symbolu (fioletowe pola z nazwą symbolu)
i sekcję „Supergra: rozwinięcie” z wierszem w rodzaju „Rozwinięcie K ×3
kolumny → 10 × 5 linii = 50”; linie rysuje z planszy rozwiniętej, sztuki
podświetla na planszy oryginalnej, a w nagłówku dopisuje „prowizoryczny” i
„darmowy spin”. Panel zarządzania pokazuje te same dopiski, komunikat
prowizoryczny pod bilansem zapisanego wyniku i rodzaj „Prowizoryczna
(supergra)” w tabeli.
„Zakres wygranej” (domyślnie 2 500, maksymalnie 100 000) jest niezależny od
„Liczby wyników”.

Sekcja jest statyczna jak wyniki wyszukiwania (D-476): nie zwija się i
liczy od razu dla aktualnie wybranej planszy, gdy tylko pojawią się wyniki;
zmiana wybranej planszy albo zatwierdzonego zakresu automatycznie odświeża
wynik, przy czym żądanie wychodzi dopiero, gdy wybór ustali się na ok. 0,4 s
(szybkie przeglądanie karuzeli nie wysyła żądania na każdą planszę). Zmiana
zakresu wymaga zatwierdzenia (Enter albo utrata fokusu) — samo wpisywanie
cyfr nie wysyła żądania. Spóźniona odpowiedź dla wcześniej wybranej planszy
nigdy nie nadpisuje wyniku aktualnie wybranej. Bez wybranego wyniku
wyszukiwania kalkulacja się nie uruchamia.

Kontrolki „Zakres wygranej”, „Stawka” i „Jednostka” stoją w jednym wierszu
nad wynikiem. Jednostka jest domyślnie w złotych i jest pamiętana w
przeglądarce. Stawka nie jest pamiętana: po każdym wyszukaniu nowego wzoru
lista stawek wraca do „wybierz stawkę”, a podsumowanie, wykres i tabela są
ukryte do czasu jej wyboru (kalkulacja biegnie w tle, więc wynik pojawia
się od razu po wyborze). Zmiana planszy w obrębie tego samego wzoru,
zmiana zakresu, limitu albo zakresu wyszukiwania zachowują stawkę.
Odtworzenie z dziennika udostępnień (D-472) wybiera stawkę bazową; stawka
odbiorcy jest widoczna na wykresie w dzienniku linku (D-487), ale odtworzenie
jej nie przenosi. Przy koszcie spinu 0 stawki nie ma i wynik jest
pokazywany bez wyboru.

Wynik rozróżnia dla każdej pozycji zakresu trzy rozłączne kategorie:
kompletna (wszystkie 15 symboli znanych), częściowa (co najmniej jeden
nieznany) i brakująca (brak zapisanej planszy dla tej pozycji sekwencji).
Dla planszy częściowej payout jest naliczany tylko wtedy, gdy widoczny
prefiks od lewej strony gwarantuje tę wypłatę niezależnie od nieznanego
zakończenia (potwierdzone minimum); plansza pozostaje „częściowa” nawet po
naliczeniu takiej wypłaty. Brakująca pozycja dolicza koszt spinu i zero
rozpoznanej wypłaty — nigdy nie jest pomijana ani nie skraca zakresu. Symbol
na planszy spoza aktywnych symboli opublikowanej wersji reguł przerywa całą
kalkulację zakresu jako błąd, zamiast po cichu pominąć jedną planszę.

Podsumowanie pokazuje osobno: rozpoznane wypłaty, koszt spinów (suma
kosztu wszystkich spinów zakresu, również brakujących), bilans
(wypłaty minus koszt) — nigdy nie nazywane „zyskiem” — oraz „Maksymalny
wkład” (TASK-0776): ile gotówki trzeba mieć, zaczynając od zera, aby opłacić
spiny aż do najniższego punktu bilansu w zakresie. Każdy spin jest płacony
przed swoją wypłatą, więc dołek przed wypłatą to bilans narastający minus ta
wypłata; liczy się też koniec zakresu, a wkład nigdy nie jest mniejszy niż
koszt jednego spinu. Kafelek podaje numer spinu najniższego bilansu i skaluje
się ze stawką oraz jednostką jak pozostałe kwoty (D-470). Tabela wyników
zawiera wyłącznie spiny z dodatnią wypłatą w kolumnach: Spin, Plansza,
Wypłata, Bilans narastająco i kolumnie akcji bez widocznego nagłówka
(przycisk „Pokaż planszę”, D-470, TASK-0764) — również wtedy, gdy bilans
narastający pozostaje ujemny; wypłata planszy częściowej jest oznaczona jako potwierdzone
minimum. Wszystkie wiersze jednej odpowiedzi mieszczą się w pionowo
przewijalnym obszarze o wysokości około 20 wierszy (D-476); nagłówki kolumn
pozostają widoczne podczas przewijania, a interfejs nie ma paginacji ani
stopki zmiany strony. Suwak „Minimalna wypłata w tabeli” (od zera do najwyższej wypłaty
bieżącej odpowiedzi, z widoczną wartością) filtruje lokalnie wyłącznie
widoczne wiersze tabeli: nie wysyła żądania i nie zmienia podsumowania ani
wykresu. Nad suwakiem i tabelą jest wykres SVG narastającego bilansu
(rozpoznane wypłaty minus koszt wszystkich spinów) względem numeru spinu
(D-476: wykres przed tabelą). Zaczyna się od
zera, między wypłatami pokazuje spadek bilansu o koszt spinów (punkt tuż
przed każdą wypłatą), kończy się na ostatnim spinie zakresu bilansem z
podsumowania i ma przerywaną linię zera, gdy bilans ją przecina. Wykres ma
siatkę poziomą i pionową z „okrągłymi” podziałkami (kroki 1/2/5 × 10ⁿ)
opisanymi na osiach; oś Y sięga do skrajnych podziałek obejmujących minimum
i maksimum bilansu, a opisy podziałek zastępują osobne etykiety minimum i
maksimum (TASK-0761). Najechanie
na wykres pokazuje etykietę najbliższego punktu wypłaty albo końca zakresu z
liczbą spinów i bilansem z jednostką („kredytów” albo „zł”, TASK-0774;
tak samo lista przypiętych punktów) oraz trzecią wartością „Wkład”
(TASK-0778): kwotą potrzebną od zera, by opłacić spiny do tego punktu, czyli
najgłębszym dołkiem bilansu od pierwszego spinu do punktu (reguła kafelka
„Maksymalny wkład” ograniczona do odcinka); etykieta leży w pasie nad obszarem danych i łączy
się z punktem kropkowaną pionową linią, więc nie zasłania linii bilansu.
Kliknięcie przypina najbliższy punkt: jego etykieta zostaje widoczna na
stałe w tym samym pasie. Ponowne kliknięcie punktu albo „×” na etykiecie
odpina go, „Wyczyść punkty” odpina wszystkie. Można przypiąć najwyżej 8
punktów; kolejne kliknięcie pokazuje komunikat i nie usuwa starszego
punktu. Etykiety nie nachodzą na siebie: gdy brakuje miejsca nad punktem,
etykieta przesuwa się w bok, a linia prowadząca się łamie. Wykres obsługuje
klawiaturę: strzałki wybierają punkt, Enter albo spacja przypina lub odpina.
Przypięcia znikają, gdy wynik dotyczy innej planszy albo zakresu. Puste wyniki (brak jakiejkolwiek dodatniej
wypłaty) nadal pokazują poprawne podsumowanie i kompletność danych, z
zastrzeżeniem że przy niepełnych danych nie można wykluczyć niewykrytej
wygranej; wykres pokazuje wtedy komunikat zamiast sztucznych danych. Liczniki
kompletności (kompletne/częściowe/brakujące) sumują się do liczby ocenianych
pozycji, niezależnie od liczby zdjęć czy rewizji jednej planszy.

Kalkulacja jest operacją wyłącznie do odczytu: nie zapisuje oszacowań jako
rozpoznanych symboli, zatwierdzeń ani danych treningowych, nie pobiera
zdjęć ani nie uruchamia ponownego rozpoznawania. Nie ma cache serwerowego —
każde żądanie jest liczone od nowa z bieżącej projekcji wyszukiwania. Klient
zachowuje wynik tylko dopóki sekcja pozostaje otwarta dla tego samego wyboru;
zwinięcie sekcji odrzuca wynik (także spóźnioną odpowiedź), więc ponowne
otwarcie zawsze liczy od nowa i uwzględnia symbole zweryfikowane w
międzyczasie (D-462, TASK-0722).

**Stawka i jednostka (D-470, TASK-0762).** Nagłówek wyniku (poza
nagłówkiem zwijania sekcji) ma kontrolki
„Stawka” (1,20 zł, 2 zł, 4 zł, 6 zł, 10 zł, 20 zł) i „Jednostka” (kredyty
albo złote). `1 zł = 10 kredytów`; stawką bazową jest koszt spinu
opublikowanych reguł (dziś 100 kredytów = 10 zł); stawka bazowa spoza listy
pojawia się jako dodatkowa opcja „bazowa”. Wybrana stawka skaluje
wypłaty i koszt spinu mnożnikiem `stawka / stawka bazowa`, np. 1 000
kredytów wypłaty przy stawce 10 zł to 600 kredytów (60 zł) przy stawce
6 zł. Przeliczenie obejmuje podsumowanie, koszt spinu w nagłówku, kolumny
tabeli, próg suwaka, osie i etykiety wykresu oraz legendę modala planszy.
Jest wykonywane lokalnie, bez żądania do API, na liczbach całkowitych z
jednym zaokrągleniem do grosza na wartości końcowej. Nagłówek pokazuje
mnożnik. Domyślnie obowiązuje stawka bazowa i jednostka „kredyty”, więc
ekran bez zmiany ustawień wygląda jak wcześniej. Wybór jest zapamiętany w
przeglądarce jako preferencja widoku. Próg suwaka jest zachowywany przy
zmianie stawki i jednostki. Koszt spinu równy zero wyłącza wybór stawki z
komunikatem; jednostka „złote” pozostaje dostępna w kursie `kredyty / 10`.

**Podgląd planszy z liniami (D-470, TASK-0763–0764).** Przycisk w kolumnie
akcji otwiera modal z przyciętym widokiem wybranej planszy i narysowanymi
wygrywającymi liniami. Linie i ich wypłaty pochodzą z tego samego
ewaluatora i tej samej opublikowanej wersji reguł co wiersz tabeli: każda
linia liczy się wyłącznie od lewej krawędzi i kończy na pierwszej nieznanej
komórce, więc plansza przycięta z lewej strony nie pokazuje żadnej linii,
a nieznane pola są oznaczone `?`. Każda linia ma stały kolor według
kolejności linii wypłat; pola z Wildem mają dodatkowy znacznik. Legenda
ma przełącznik widoczności dla każdej linii osobno oraz „Pokaż wszystkie”
i „Ukryj wszystkie”, a każdy wpis podaje nazwę linii, symbol, długość,
liczbę pól Wild i wypłatę w wybranej stawce i jednostce. Dla gry z symbolem
uruchamiającym supergrę (`payout-v4-wild-count`) legenda ma sekcję „Sztuki
na planszy” z wierszami „Mumia ×3 → 20”, a policzone pola są podświetlone
na planszy; nieznane pole (`?`) nie jest liczone jako sztuka. Gdy suma
wypłat linii i sztuk różni się od
wypłaty wiersza albo wynik dotyczy innej wersji reguł, modal pokazuje
komunikat i „Przelicz ponownie” zamiast niespójnego rysunku; przycisk
zamyka modal i liczy zakres od nowa. Błąd pobrania planszy pokazuje
komunikat z „Spróbuj ponownie”. Brak zdjęcia albo siatki pól nie blokuje modala:
pokazuje schemat 3 × 5 z ikon symboli z tymi samymi liniami.

**Nieaktualny odczyt planszy (TASK-0773).** Gdy siatka planszy zmieniła się
po zapisaniu jej odczytu w wyszukiwarce, modal nie pokazuje błędu: rysuje
linie i wypłatę ze starego odczytu (tak samo liczy tabela) na schemacie 3 × 5
z ostrzeżeniem i przyciskiem „Odśwież odczyt tej planszy”. Odświeżenie
przebudowuje odczyt tej jednej planszy z bieżącej siatki i symboli (bez
zmiany decyzji ludzi); potem wraca zdjęcie i poprawianie pól, a zamknięcie
okna przelicza tabelę.

**Poprawianie symbolu pola (D-473, D-492, TASK-0772/0845).** Dla bieżącej
planszy operacyjnej `pending`, `accepted` lub `corrected` z kompletem 15 pól
modal ma tryb „Popraw symbole”: kliknięcie pola otwiera paletę symboli gry
oraz „Nieczytelny” i „Zła siatka”. Wybór zapisuje decyzję człowieka dla pola
tak samo jak „Weryfikacja symboli” (ten sam symbol zatwierdza pole, inny je
przepisuje) i od razu zmienia linie w oknie. „Nieczytelny” czyni pole `?`,
więc linia oparta na błędnie rozpoznanym symbolu kończy się przed nim.
Konflikt z równoległą zmianą pokazuje komunikat i odświeża planszę. Po
zapisanej zmianie zamknięcie okna przelicza tabelę i bilans. Plansze
archiwalne i nieaktualne nie mają edycji. Poza tym trybem modal jest
wyłącznie do odczytu.

### Udostępnianie wyszukiwania online

**D-471 (etap B planu `BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`; panel
TASK-0769, aplikacja odbiorcy w Reviewerze TASK-0768).** Przycisk
„Udostępnij online” w nagłówku sekcji „Wyszukaj plansze” tworzy link do kopii tej sekcji razem z „Przybliżoną wygraną” dla
bieżącej gry. Operator podaje etykietę i czas dostępu (1 h, 4 h, 8 h albo
24 h; domyślnie 8 h). Po utworzeniu widzi link i 8-znakowy kod wejścia
(`XXXX-XXXX`), może je skopiować osobno i zatrzymać sesję z potwierdzeniem.
Link nie zawiera kodu. Kod jest przechowywany wyłącznie lokalnie w
przeglądarce Admina do wygaśnięcia albo zatrzymania sesji; w innej
przeglądarce panel pokazuje link bez kodu. Panel listuje aktywne linki gry
(ostatnie otwarcie, czas wygaśnięcia) i osobno zakończone (wygasłe,
zatrzymane, zablokowane po 5 błędnych kodach). Utworzenie linku uruchamia
publiczny adres Reviewera; gdy się nie uda, panel pokazuje czytelny błąd i
nie tworzy linku.

Odbiorca po podaniu kodu ma te same funkcje co operator: liczbę wyników,
zakres wyszukiwania, paletę symboli, edycję wzoru, karuzelę wyników,
„Przybliżoną wygraną” z tabelą, wykresem, stawką i modalem linii. Dostęp
obejmuje jedną grę i poprawianie jej bieżących symboli (D-492). Obrazy są przycięte do planszy
i zmniejszone. Odbiorca nie widzi panelu udostępniania ani identyfikatorów
wewnętrznych. Po wygaśnięciu albo zatrzymaniu sesji aplikacja pokazuje
czytelny ekran zakończenia.

**Korekty odbiorcy i przegląd operatora (D-492, TASK-0845).** Przycisk
„Popraw symbole” w tym samym modalu działa dla planszy startowej i plansz
przeglądanych dalej w zakresie do 100 000 spinów. Decyzja od razu zmienia
bieżące wyszukiwanie i wypłaty. Obowiązują dotychczasowe reguły decyzji
człowieka, w tym kwalifikacji danych; przegląd operatora nie odkłada zmiany
i nie uruchamia treningu. Bramka informuje o zapisie poprawek.

Dziennik wybranego linku pokazuje liczniki wszystkich poprawionych plansz
i tych do przeglądu, także obok grupowanego wzoru wyszukiwania. Osobna lista
ma filtry „Do przeglądu”, „Wszystkie” i „Przejrzane”, strony po 25, numer
planszy, liczbę pól, czas, stawkę z chwili korekty oraz oznaczenie planszy
startowej lub dalszej. Nie pobiera całego zakresu. „Sprawdź poprawki” od
razu otwiera lokalny edytor właściwej planszy, wyróżnia zmienione pola i
pokazuje historię symboli oraz stanów przed/po. Operator może poprawić dane.

„Oznacz jako przejrzane” zamyka przegląd dopiero po wczytaniu historii
wszystkich pól i sprawdzeniu aktualnej rewizji oraz stanu całej planszy.
Zamknięcie modala nie zatwierdza przeglądu. Nowsza korekta daje konflikt
albo ponownie umieszcza planszę na liście. Potwierdzenie już zatwierdzonego
symbolu bez zmiany stanu nie tworzy nowej pracy; zatwierdzenie oczekującego
pola jest zmianą. Usunięcie wyszukiwania lub revoke zachowuje historię.
Po utracie odpowiedzi odbiorca może jawnie sprawdzić ostatni zapis, także
po odświeżeniu karty, z dokładnym identyfikatorem tej samej operacji.

**Dziennik zapytań i odtworzenie (D-472, TASK-0771).** Każde zapytanie
odbiorcy o dane (wyszukiwanie, przybliżona wygrana, szczegóły planszy) jest
zapisywane z czasem, parametrami i skrótem wyniku, bez adresu IP. Bramka
kodu informuje odbiorcę o zapisie. W panelu udostępniania operator rozwija
„Dziennik zapytań” wybranego linku (aktywnego albo zakończonego) i widzi
same wyszukiwania (D-478), od najnowszego, po 10 („Starsze wyszukiwania”):
godzinę, wzór jako planszę 3 × 5 z grafikami symboli (około jednej trzeciej
szerokości wpisu) oraz — jeżeli odbiorca po tym wyszukiwaniu uruchomił
„Przybliżoną wygraną” — wykres bilansu tej planszy i zakresu na resztę
szerokości, liczony w Adminie w stawce bazowej i złotych. Wpisy przybliżonej
wygranej i szczegółów planszy nie są osobnymi pozycjami, a linia opisu
(zakres, limit, wyniki) nie jest pokazywana. „Usuń” z potwierdzeniem „Usuń
wpis” trwale kasuje wyszukiwanie razem z jego późniejszymi zapytaniami,
bez historii korekt i przeglądu (D-492). Przycisk „Odtwórz w
wyszukiwarce” otwiera „Wyszukaj plansze” tej gry z tym samym wzorem, zakresem
i liczbą wyników (także pola `?`) i od razu uruchamia wyszukiwanie; adres
Admina zawiera wtedy jednorazowo `?boardSearchReplay=<id wpisu>`, a wpis
innej gry przełącza na tę grę. Dla wpisu przybliżonej
wygranej odtworzenie używa najbliższego wcześniejszego wyszukiwania tej
sesji, wybiera planszę startową i zakres spinów i rozwija „Przybliżoną
wygraną”; dla szczegółów planszy dodatkowo otwiera modal. Symbol, który nie
jest już aktywny, trafia do wzoru jako `?` z ostrzeżeniem. Stawka i jednostka
odbiorcy: stawka jest zapisana w groszach wraz z zakresem (D-487) oraz korektą
(D-492), a jednostka wyświetlania pozostaje lokalna.

### Korekta cięcia siatki

**D-462 (TASK-0726):** lokalny Reviewer na porcie 3001 jest jednym ekranem
ręcznej korekty cięcia siatki. Zastąpił workflow „Walidacji cięcia siatki 0.9”
(widoki `Do walidacji`, `Do poprawy`, `Wszystkie`, całe zdjęcie z dziewięcioma
planszami i `Zatwierdź całe zdjęcie`). Nie ma osobnego zatwierdzania
poprawności planszy, zdjęcia, siatki ani kompletu symboli.

Kolejka jest jedna (`GET .../grid-reviews?view=correction`, `API_CONTRACT.md`):
plansze, których geometrii algorytm nie wyznaczył albo ją odrzucił
(odroczona geometria `pending`), oraz plansze z co najmniej jedną komórką
zgłoszoną w `Weryfikacji symboli` jako `Zła siatka`. Jeden slot planszy
występuje raz niezależnie od liczby zgłoszeń; zgłoszenie jednej planszy nie
kieruje do korekty innych plansz tego samego zdjęcia. Kolejka jest zawężona do
importu wybranego w Adminie.

Ekran pokazuje dokładnie jedną planszę i jej siatkę: wycinek oryginału wokół
planszy z czterema narożnikami, numer planszy, pozycję na stronie oraz powód
(odroczenie algorytmu albo zgłoszone pola, wyróżnione także w podglądzie
cropów). Operator przeciąga narożniki albo całą siatkę, ogląda aktualny
podgląd 15 cropów, zapisuje i automatycznie przechodzi do następnej planszy.
Licznik `Do korekty` oraz przyciski `Poprzednia` / `Pomiń na razie` służą
wyłącznie nawigacji. `Niepełna plansza` jest dostępna dla slotów odroczonych i
plansz `virtual_source`; plansza z zapisaną kwalifikacją geometrii otwiera się
z nią i zapis ją zachowuje (także `complete`).

Pod kolejką ekran ma sekcję `Ostatnie korekty` (TASK-0948): lista ostatnich
zapisów korekty importu (godzina lokalna, sekwencja, pozycja, rodzaj `slot` /
`plansza`, autor). `Cofnij` jest dostępne tylko dla korekt oznaczonych przez
API jako `revertable`; pozostałe pokazują komunikat blokady. `Cofnij` otwiera
potwierdzenie z podglądem skutków, a `Potwierdź cofnięcie` wysyła jedno
żądanie z nowym kluczem idempotencji i tokenami CAS z podglądu. Po sukcesie
odświeżają się kolejka i lista; błąd 409 pokazuje komunikat i odświeża listę.
Lista odświeża się też po każdym zapisie korekty.

Odrzucanie przyciętych plansz (TASK-0949, W7/W8): w „Korekta cięcia siatki”
nad edytorem oraz na ekranie operacyjnym pozycji jest przycisk
`Odrzuć planszę`. Otwiera okno z wyborem powodu („Plansza przycięta”,
„Rozmyta”, „Inny” z obowiązkowym opisem), skutkami (zdjęcie zostaje
niekompletne i czeka na zdjęcie zastępcze albo wyjątek operatora, pozostałe
plansze nie są cięte; weryfikacje symboli już zapisane na planszy zostają w
historii, ale plansza wypada z wyszukiwarki; kanonicznego właściciela
sekwencji nie można odrzucić) i potwierdzeniem `Potwierdź odrzucenie`. Slot
odroczony jest odrzucany trasą slotu, istniejąca plansza trasą rozstrzygnięcia
pozycji. Okno trzyma jeden klucz idempotencji na otwarcie; po utraconej
odpowiedzi zamraża wybór i pozwala powtórzyć to samo żądanie. Odpowiedź 4xx
z kodem (np. `BOARD_REJECT_CANONICAL`) zamyka okno, pokazuje komunikat i
odświeża kolejkę. Odrzucenie trafia na listę „Ostatnie korekty” (rodzaj
`odrzucony slot` / `odrzucona plansza` z powodem) i można je cofnąć, dopóki
sekwencji nie przejmie inna plansza (`GEOMETRY_REVERT_REPLACED`).

Zapis geometrii kończy zadanie korekty. Usuwa zgłoszenia `Zła siatka` tej
planszy; komórki o zmienionym wycinku wracają do zwykłej `Weryfikacji symboli`
z dotychczasową etykietą jako podpowiedzią, a komórki o niezmienionych
pikselach zachowują weryfikację (D-462 R5/R6). Zapis dotyczy wyłącznie tej
jednej planszy.

**D-488 (TASK-0820–0822):** podgląd pokazuje jeden zestaw 15 kafelków.
Kafelek z pikselami (także pole częściowo widoczne) jest klikalny; pod
podglądem jest paleta aktywnych symboli gry w kolejności katalogu. Kafelek
pokazuje podpowiedź symbolu — dla planszy zgłoszonej symbol zapisany w bazie,
dla planszy odroczonej predykcję modelu dla bieżącego cięcia — albo symbol
wybrany przez operatora. Zapis siatki zatwierdza wyłącznie pola z wybranym
symbolem (decyzja człowieka dla nowego cropa, w tej samej transakcji co
geometria); pozostałe pola trafiają do `Weryfikacji symboli` jak dotąd. Pole
bez pikseli nie jest klikalne. Błąd zapisu symboli wycofuje cały zapis.

**D-522 (TASK-0885):** zapis ręcznie zatwierdzonej, przypisanej planszy sieci
z pełną siatką 24 punktów tworzy jej bieżące cropy również wtedy, gdy inne
plansze zdjęcia nadal czekają na korektę. Zatwierdza tylko wskazane symbole.
Zdjęcie zachowuje stan niekompletny; pozostałe propozycje nie są zatwierdzane.
Starsza korekta czterech narożników zachowuje bramkę całego zdjęcia D-484.

**D-523 (TASK-0886):** import z polityką `neural-auto-crop-v1` udostępnia
pełne, jednoznacznie przypisane siatki w zbiorczej `Weryfikacji symboli`
bez obowiązkowego zatwierdzania geometrii każdej planszy. Render zachowuje
wszystkie 24 węzły. Brakujący lub ucięty slot sam trafia do korekty;
nie blokuje pełnych sąsiadów ani nie przesuwa numerów sekwencji.
Przycisk `Zatwierdź` jest dostępny dla zaznaczeń z obrazem w profilu Mumii,
z istniejącym podglądem i operacją zbiorczą. Pola bez obrazu są wyłączone.
Pozostałe gry zachowują dotychczasowe zachowanie paska akcji.
Operator oznacza błędny crop jako `Zła siatka`, a dobry crop ze złym
symbolem poprawia w weryfikacji. Predykcja nie jest etykietą treningową.
Ponowne przetwarzanie zachowuje bieżące ręczne siatki i decyzje symboli.
Przygotowanie bez aktywnego zadania dostaje jedną próbę trwałego wznowienia
po wejściu do panelu i przycisk `Wznów przygotowanie`; błąd pozostaje widoczny.

**TASK-0840 (Poprawki z audytu siatek):** osobna kolejka lokalnego Reviewera
pod `http://127.0.0.1:3001/?mode=local&gameId=<gameId>&queue=grid-audit`
(tylko host pętli zwrotnej na porcie 3001, bez kodu i bez tunelu, zakres:
cała gra). Pokazuje plansze z zaimportowanej listy audytu siatek (TASK-0831)
w kolejności listy — najpierw te z decyzjami symboli — po jednej, na tym samym
ekranie korekty. Siatka sieci `neural_grid` jest wczytana jako propozycja
(żółta siatka z narożnikami, „Przywróć sugestię” wraca do niej), a obecna
zapisana siatka jest cienkim czerwonym konturem. Narożniki propozycji poza
zdjęciem są przycinane do krawędzi, chyba że plansza jest już niepełna.
Zapis jest zwykłym zapisem korekty planszy (nowa rewizja geometrii, wycinki,
D-462 R5/R6, symbole wskazane na kafelkach D-488, bramka kompletności).
Kolejka nie ma stanu w bazie: poprawiona plansza znika, bo ma nowszą rewizję
geometrii (także po restarcie); plansza zmieniona po audycie jest
„nieaktualna” i nie dostaje propozycji. `Pomiń na razie` działa w bieżącej
sesji. Licznik pokazuje plansze do poprawy, poprawione, z decyzjami symboli i
nieaktualne. Masowe oznaczanie „Zła siatka” nie jest potrzebne.

**TASK-0841:** plansza audytu automatycznie generuje podgląd bez czekania na
wczytanie pełnego zdjęcia w edytorze. Po podglądzie i katalogu zaznacza
pierwsze pole mające piksele; operator może od razu wybrać jego symbol.
Kliknięcie innego kafelka zmienia edytowane pole. Paleta pokazuje skróty z
kolejności katalogu: `1–8`, `0`, litery; `9` jest zarezerwowane dla „Nie wiem”.
Dla 777: `1` Wiśnia, `5` Śliwka, `6` Arbuz. Zaznaczenie pola niczego nie
przypisuje. Wybór symbolu nie wymaga ruszania siatki ani „Ponów podgląd”.
Od D-493 zapis audytu potwierdza także widoczne, wstępnie wybrane propozycje
przez istniejącą korektę D-488.
Zwykła korekta zachowuje dotychczasowe skróty i ręczne zaznaczanie pola.

**D-491 (TASK-0844):** symbole pod żółtą siatką audytu są nowymi propozycjami
biblioteki wzorców dla dokładnie tego cięcia. Stare zatwierdzone etykiety
nie są w tej kolejce podpowiedziami. Brak wyniku ma jawny komunikat.
Przesunięcie narożników lub zmiana kwalifikacji ukrywa wynik poprzedniego
cięcia. Rozpoznawanie i wyświetlanie nie zapisuje geometrii ani decyzji
człowieka. Regułę pustych niepewnych pól i osobnego wyboru każdego symbolu
zastępuje D-493.

**D-493 (TASK-0846):** audyt wstępnie wybiera nowe propozycje symboli dla
bieżącego cięcia, także najlepszy kandydat przy braku jednomyślności.
Niepewny kandydat ma znak `?` i opis „niepewna propozycja”. Operator przegląda
wszystkie pola i zmienia błędne wybory. „Nie wiem” zapisuje nieczytelność;
„Usuń wybór” blokuje ponowny wybór propozycji przy powtórzeniu podglądu i
pozostawia pole do późniejszej weryfikacji. Ręczne wybory mają pierwszeństwo.
Przesunięcie siatki lub zmiana kwalifikacji usuwa automatyczne wybory starego
cięcia. Brak pikseli lub kandydata pozostaje bez wyboru. Dopiero kliknięcie
zapisu zatwierdza wszystkie widoczne wybory, również niezmienione propozycje.
Zwykła korekta zachowuje podpowiedzi wymagające osobnego wyboru operatora.

**D-494 (TASK-0847):** propozycja audytu pochodzi z głowicy istniejącej sieci
na oryginalnym RGB zgodnym z treningiem. Sieć wykorzystuje przestrzenny układ
kształtu, detali i barwy; nie jest to reguła wyboru po kolorze. Dotychczasowa
biblioteka dodatkowo potwierdza wynik przy jednomyślnej zgodności klasy.
W pozostałych przypadkach propozycja ma `?` i wymaga przeglądu operatora.
Wagi modelu i zatwierdzone symbole pozostają bez zmian. Metoda dotyczy tylko
kolejki audytu, a zapis i pierwszeństwo ręcznych wyborów działają jak D-493.
Podgląd działa przy opóźnionym katalogu, lecz zapis audytu czeka na katalog
i propozycje. Błąd katalogu ma jawny komunikat i wymaga odświeżenia przed
zatwierdzaniem symboli; błąd samych propozycji pozwala na ręczne wskazanie.

Admin nazywa sekcję uruchamiającą Reviewer „Korekta cięcia siatki” i pokazuje
liczbę plansz do korekty dla wybranego importu oraz liczbę geometrii
odroczonych przez algorytm. „Otwórz lokalnie” jest aktywne tylko przy
niepustej kolejce; pusta kolejka ma jawny komunikat. Lokalny origin Reviewera korzysta ze scope-bound ścieżek listy
kolejki, źródła oraz podglądu i zapisu geometrii jednej planszy; ścieżki
dawnej walidacji (zatwierdzanie planszy i zdjęcia, zapis całego zdjęcia)
usunął TASK-0727. Inny port oraz każdy origin LAN/publiczny pozostają
odrzucone. Zdalna sesja Reviewera nie otrzymuje tych ścieżek.

### Katalog symboli i grafiki referencyjne

Katalog symboli jest definiowany ręcznie dla każdej gry. Formularz utworzenia
wymaga wyłącznie nazwy, oznaczenia Wild i opcjonalnej roli „Uruchamia
supergrę” z progiem 3/4/5; Admin API pod blokadą gry nadaje
stabilny `code`, kolejny `mobileCode` i początkowy `displayOrder`. Edycja
nazwy nie może zmienić `code` ani `mobileCode`.

Operator zmienia kolejność symboli przyciskami „↑/↓” w wierszu katalogu
(TASK-0782). Przesunięcie zamienia symbol z sąsiadem i przenumerowuje całą
listę na `0..n-1`, zapisując `displayOrder` przez `PATCH` symbolu tylko dla
zmienionych pozycji. Zapisy są sekwencyjne i nieatomowe; po błędzie panel
pokazuje komunikat i wczytuje rzeczywistą kolejność z API. Kolejność steruje
skrótami cyfrowymi weryfikacji symboli i wyszukiwarki plansz oraz kolejnością
symboli w kolejnym snapshocie mobilnym; nie zmienia kodów, sygnatur, reguł ani
sumy wypłat.

Kafel symbolu bez zatwierdzonej grafiki pokazuje `?`. Kliknięcie kafla zawsze
otwiera picker cropów, który pokazuje aktualne cropy komórek zatwierdzone przez
człowieka — pojedynczo albo wraz z całą planszą. Crop musi wskazywać aktywny
symbol tej samej gry, nie mieć problemu jakości i mieć identyczną zatwierdzoną
oraz bieżącą tożsamość. Nie pokazuje pełnej planszy, confidence modelu,
predykcji, oczekujących, odrzuconych, superseded ani cropów zmienionych po
zatwierdzeniu. Propozycje są stronicowane po maksymalnie 20 i uporządkowane:
ręcznie poprawiona geometria, numer sekwencji, indeks komórki, UUID obserwacji.

Wybór cropa jest checksum-bound i zapisuje trwałą, content-addressed referencję.
Legacy zachowuje niezmienione bajty, a crop v0.10 jest jednokrotnie
materializowany jako pełny PNG. Stary `image_path` bez takiej proweniencji nie
jest aktywną grafiką. Brak zatwierdzonych wystąpień pokazuje komunikat
„Najpierw zatwierdź crop zawierający ten symbol”.

### Weryfikacja symboli

**D-462 — weryfikacja per komórka (reguła docelowa, wdrażana w etapie A).**
Weryfikowana jest pojedyncza komórka, nie plansza ani zdjęcie. Od TASK-0722
zatwierdzona komórka wchodzi do `Wyszukaj planszę` i „Przybliżonej wygranej”
zaraz po zapisie decyzji, niezależnie od stanu pozostałych komórek, problemów
cięcia innych pól oraz zatwierdzenia planszy, siatki lub zdjęcia. Od
TASK-0723 komplet zweryfikowanych komórek planszy z pełną widocznością i
jednoznaczną sekwencją domyka ją automatycznie — bez osobnego zatwierdzenia —
i dopiero wtedy plansza trafia do layoutów, snapshotu i targetu. Zgłoszenie
`Zła siatka` cofa weryfikację wyłącznie tej komórki. Od TASK-0724 zapis nowej
geometrii usuwa zgłoszenia `Zła siatka` tej planszy i wymaga ponownej
weryfikacji wyłącznie komórek o zmienionych pikselach; ich dotychczasowa
etykieta jest widoczna jako podpowiedź, a komórki o niezmienionych pikselach
pozostają zweryfikowane. Szczegóły: `DECISION_LOG.md` D-462.

**D-451 / TASK-0710:** wybór grupy obejmuje także `Poza zdjęciem`.
To grupa logicznych pól bez obrazu i bez przypisanego symbolu; po ręcznym
przypisaniu pole pojawia się wyłącznie pod wybranym symbolem oraz we Wszystkich.
Kafelek pokazuje „Brak obrazu pola”, numer planszy i pozycję. Badge „Poza
zdjęciem” albo „Częściowy obraz” pozostaje niezależnie od decyzji; oznaczenia
Nieczytelny/Zła siatka/Niewyraźny są zachowane obok widoczności.
Zaznaczanie, skróty wyboru symbolu, Enter i Nieczytelny obejmują również pola
bez obrazu. Nie można dla nich zatwierdzić cropa ani ustawić grafiki symbolu;
nie uruchamiają podglądów atlasu ani filtrowania pewności predykcji.

Przycisk `Źródło` ma postać kompaktowego badge przy prawym dolnym rogu (TASK-0713).
Oznaczenia źródła, jakości i numeru mają cienką ramkę, mocno przezroczyste
tło i minimalny odstęp od krawędzi, aby nie zasłaniały wycinka. Przycisk otwiera
wyłącznie do odczytu całe zdjęcie z zapisaną siatką i wyróżnionym polem,
także poza granicami zdjęcia. Podgląd sprawdza właściciela
i rewizję geometrii oraz checksumę zdjęcia; zmiana rewizji wymaga odświeżenia.
Pierwszeństwo mają zapisane footprinty komórek, następnie aktualna siatka.
Brak geometrii nie tworzy zastępczej siatki. Zamknięcie nie zapisuje decyzji.

W imporcie „Niepełne zdjęcie” opisuje kompletność źródła, a nie liczbę
dostępnych pozycji Weryfikacji symboli. Historyczne braki mogą wymagać
uzupełnienia. Stan stagingu oddzielnie wskazuje import, odroczoną korektę
geometrii i późniejszą weryfikację symboli; błąd przetwarzania nie jest
przedstawiany jako ukończona weryfikacja.

`Weryfikacja symboli` jest osobnym, wyłącznie lokalnym obszarem głównej
nawigacji Admina. Operator wybiera grę oraz zakres symbolu: wszystkie symbole,
jeden aktywny symbol albo nierozpoznane `?`, a także radio `Stan weryfikacji`:
`Wszystkie`, `Oczekujące`, `Zatwierdzone` albo `Kohorta aktywnego modelu`.
Radio `Pewność rozpoznania` wybiera `Wszystkie`, `Dokładnie 100%`,
`80–<100%`, `60–<80%` albo `Poniżej 60%`. Pierwszy wariant nie zawęża listy,
a pozostałe tworzą rozłączne przedziały: odpowiednio `1.0`, od `0.8` do
wartości niższej niż `1.0`, od `0.6` do wartości niższej niż `0.8` oraz
wartości niższe niż `0.6`; wybór zmienia keyset, liczniki i jawne targety
kolejnej operacji.
Opcje `Stan weryfikacji`, `Pewność rozpoznania` i `Źródło predykcji` mają
po jednym pasku bez zawijania. Każda grupa wykorzystuje pełną szerokość;
na wąskim ekranie jej pasek przewija się poziomo we własnym kontenerze.
`Filtry szczegółowe` (trzy grupy radio) oraz `Data zmiany komórki` są
niezależnie zwijane i początkowo rozwinięte. Zwijanie zachowuje aktywne
warunki, roboczą datę, cropy i zaznaczenie; nie odczytuje danych ani nie
wykonuje decyzji. Nagłówki pokazują liczbę aktywnych filtrów i aktywny zakres
dat także po zwinięciu. Przyciski mają aria-expanded/controls; Enter na nich
obsługuje sekcję i nie uruchamia zapisu symbolu. Pełny ekran zachowuje stan
zwinięcia, a zwolnioną wysokość otrzymuje lista cropów.
W pełnym ekranie na wąskim urządzeniu wysoki panel filtrów można przewijać
pionowo wewnątrz panelu, aby wszystkie jego kontrolki pozostały dostępne.
Po wybraniu gry może dodatkowo ograniczyć cropy do jednego katalogu importu
obrazów albo pozostawić `Wszystkie katalogi`. Selektor pokazuje bezpieczną
etykietę jobu, nie ścieżkę lokalnego źródła; zmiana gry czyści ten filtr.
Wybór katalogu zmienia keyset, liczniki i scope wszystkich kolejnych operacji
masowych, więc nie może objąć cropów innego importu.
Ostatni wariant pokazuje wyłącznie bieżące, zatwierdzone cropy należące do
niezmiennej kohorty modelu wskazanego przez najnowszą aktywację wybranej gry.
Crop zmieniony od zamrożenia kohorty jest wykluczony; brak aktywnego modelu daje
pusty wynik, bez podstawienia najnowszej nieaktywnej kohorty. Symbol docelowy akcji
`Symbol do zatwierdzenia` pozostaje niezależnym wyborem. Nie istnieje status cropa
`odrzucone`: `Zła siatka` i `Nieczytelny symbol` są odrębnymi problemami
jakościowymi obsługiwanymi przez ich dedykowane kolejki.
Widok korzysta z tego samego pojedynczego właściciela logicznego numeru co
operacyjne review: kanoniczna plansza `accepted/corrected` ma pierwszeństwo,
a bez niej widoczna jest wyłącznie najnowsza oczekująca plansza. Cropy ze
starszych, pokrywających się stagingów oznaczonych `superseded` nie są
prezentowane ani dostępne do masowych decyzji.
Gra oraz zakres symbolu są domyślnie niewybrane. Wejście do zakładki nie pobiera
strony cropów. Operator wybiera rozmiar strony `500`, `1000`, `2000` albo
`2500` metadanych; domyślnie jest to `500`. Pierwsza strona jest pobierana
automatycznie dopiero po wskazaniu kombinacji obu pól. Zmiana gry ponownie
czyści wybór symbolu; osobne akcje `Zatwierdź wybór` i `Zmień wybór` nie
występują. Globalne liczniki nie należą
do krytycznej ścieżki listy: są pobierane osobno dla gry i rewizji
katalogu. Wolny albo niedostępny licznik nie blokuje oglądania ani decyzji, a
spóźniona odpowiedź poprzedniej gry jest odrzucana. Workspace utrzymuje po
jednym aktywnym odczycie strony, prefetchu i liczników. Zmiana gry, symbolu,
stanu, katalogu importu, confidence, rozmiaru strony albo kursora aktywnie anuluje nieaktualne
requesty; identyfikator requestu i zakres filtra pozostają dodatkową ochroną
przed klientem ignorującym sygnał. Świadome anulowanie nie jest prezentowane
jako awaria połączenia. Backend ogranicza pojedyncze zapytanie strony do 5
sekund, a liczników do 15 sekund. Przekroczenie limitu zwraca kontrolowany błąd
i nie może bezterminowo zajmować połączenia z pulą. Rozłączenie klienta jest
odczytywane jako właściwy komunikat ASGI `http.disconnect`, również za lokalnym
middleware. Odczyt listy albo liczników utrwala request-scoped sygnał
anulowania i przerywa odpowiadające mu zapytanie PostgreSQL z executora
niezależnego od puli query. Kolejne etapy sprawdzają sygnał przed SQL, a
fizyczny cancel jest ponawiany do końca query. Request kończy pracę wątku i
operacji cancel przed zwolnieniem własnej sesji, także po powtórnym anulowaniu.
W magazynie V2 podstawowe liczniki całej gry, pojedynczego symbolu i `?` są
utrzymywane transakcyjnie razem z bieżącą projekcją komórek. Delta zawsze wynika
ze stanu przed i po zapisie, dlatego retry i operacja zbiorcza nie mogą naliczyć
tej samej zmiany ponownie. Podczas checkpointowanej rekonstrukcji API zwraca
jawną niedostępność licznika, nigdy pozorne zero. Confidence i aktywna kohorta
pozostają dokładnymi, ograniczonymi czasowo zapytaniami po indeksach. Magazyn
legacy zachowuje dotychczasową ścieżkę agregatu SQL.
Zmiana ustawionej gry,
symbolu albo rozmiaru strony czyści strony, miniatury, zaznaczenie i wirtualny
viewport. Jeśli istnieje jawne zaznaczenie,
operator najpierw potwierdza jego wyczyszczenie. Widok zachowuje jawne przyciski
poprzedniej/następnej strony, prefetchuje wyłącznie jedną kolejną stronę i trzyma
w pamięci najwyżej trzy najbliższe strony metadanych. Nie utrzymuje obrazów dla
całej strony: DOM zawiera tylko karty viewportu i małego overscanu. Admin
pokazuje na dole także pole jednoznacznego numeru strony. Po wskazaniu liczby z
zakresu znanego z licznika przechodzi do tej strony po cursorach; pobiera tylko
metadane stron potrzebnych do dojścia, nie zmienia filtrów ani zaznaczenia i nie
rozszerza okna trzech stron cache.
Admin dzieli potwierdzoną stronę deterministycznie na atlasy po maksymalnie 100
kart, wspólne dla `legacy_file` i `virtual_source`. Dla 500 cropów powstaje
najwyżej pięć requestów obrazu, a dla 2500 — najwyżej 25: najpierw grupa
zawierająca widoczny viewport, potem pozostałe grupy w kolejności. Klucz atlasu obejmuje rewizje, checksumy,
tryby assetów i wersję renderera, dlatego powrót na stronę korzysta z tego
samego content-addressed cache, a zmiana cropa nie może pokazać starego tile'a.
Podsumowanie pokazuje numer strony i jej jednoznaczny zakres pozycji natychmiast
po pobraniu metadanych, a następnie uzupełnia niezależnie pełne liczniki. Zakres zależy od
zatwierdzonego limitu (np. `1–50`, `51–100`) oraz pełne liczniki zatwierdzonych i oczekujących cropów
wybranej gry. Zakres ostatniej strony kończy się na rzeczywistej liczbie
wyników.
Karta ma dokładnie 100 × 100 px i pokazuje wyłącznie crop symbolu. Crop
wypełnia cały tile bez dopisywanego czarnego płótna, a cienkie obramowanie jest
nakładane na krawędź grafiki i nie zmniejsza jej powierzchni. Nazwa,
numer planszy, pozycja i stan review nie zajmują miejsca w siatce. Po wysłaniu
decyzji karta jest nieaktywna, przygaszona i pokazuje centralny spinner; poprawnie
przypisany do innego symbolu crop znika przed odświeżeniem strony z serwera.
Numer planszy jest ponadto stale widoczny jako mały, kontrastowy overlay przy
dolnej krawędzi samej grafiki. Nie powiększa kafelka ani nie przesuwa cropa;
może użyć półprzezroczystego tła wyłącznie dla czytelności.
Karta pokazuje tile 100 × 100 px ze wspólnego atlasu WebP, nie pełny crop ani
base64 w odpowiedzi listy. Przeglądarka utrwala atlas przez content-addressed
cache `immutable`.

Widok nie ma przełącznika rendererów. Każda karta korzysta z bieżącej,
checksum-bound tożsamości assetu zapisanej na komórce: `legacy_file` dla
historycznego importu albo `virtual_source` dla produkcyjnego v0.10. Shadow nie
jest źródłem decyzji i nie może być pokazany jako aktywny crop.
Do czasu gotowości projekcji gra pokazuje
kontrolowany stan przebudowy, a nie mylący pusty wynik. Stan pokazuje
oczekiwane/przetworzone plansze i komórki, ID joba, diagnostykę oraz jawne akcje
  `Przygotuj weryfikację symboli` albo `Wznów przygotowanie`. Polling jednego joba
  nie nakłada requestów, a po `ready` automatycznie otwiera bounded listę cropów.
  Po osiągnięciu `ready` stale dostępna akcja `Uzupełnij brakujące symbole`
  uruchamia idempotentną reconciliację projekcji. Uzupełnia wyłącznie brakujące
  lub nieaktualne metadane cropów; nie uruchamia ponownie cięcia ani inferencji.
  Jeżeli general worker jest zajęty, dotychczasowa gotowa lista pozostaje
  dostępna, a przycisk pokazuje oczekiwanie w kolejce. Stan `rebuilding` zaczyna
  się dopiero po faktycznym przejęciu joba przez worker. Reconciliacja utworzona
  z kompletnej projekcji zachowuje odczyt oraz mutacje istniejących cropów także
  podczas przetwarzania; początkowy lub niekompletny backfill pozostaje
  fail-closed.
Zaznaczanie i masowe operacje działają bez pobierania całego wyniku do
przeglądarki. Operator może zaznaczać pojedyncze karty albo całą bieżącą stronę
jawnie do 10 000 pozycji. Game-wide widok nie udostępnia akcji `Zaznacz wyniki
filtra`, ponieważ jego zakres może zawierać jednocześnie zwykłe, nierozpoznane i
odrzucone jakościowo cropy o różnych dozwolonych mutacjach.
Jawne zaznaczenie pozostaje aktywne przy przejściu między keysetowymi stronami,
więc operator może zbudować jeden job z kilku stron wybranego rozmiaru. Czyści je
wyłącznie jawna akcja, zmiana filtra albo skuteczne przekazanie operacji.
Karta odznaczona kliknięciem ma czerwone obramowanie do czasu ponownego
zaznaczenia, wyczyszczenia zaznaczenia, zmiany filtra albo przekazania operacji;
jest to wyłącznie lokalna wskazówka wizualna i nie zmienia targetów joba.
Zmiana filtra przy zaznaczeniu wymaga potwierdzenia i czyści selection. Wysłana
operacja masowa przechodzi do tła: jej dokładne widoczne targety pozostają
wyszarzone ze spinnerem, ale operator może przejść na inną stronę i uruchomić
kolejną niezależną operację. Zablokowane pozostają wyłącznie targety już wysłane
oraz krótki foreground start/preview bieżącej decyzji.
Limit 10 000 jawnych pól dotyczy jednej komendy, nie sumy operacji w tle.
`Zaznacz stronę` pomija pola aktywnych i zakończonych operacji, zablokowane do
odświeżenia. Gdy cała strona jest zablokowana, przycisk jest nieaktywny.

**TASK-0709 / D-451:** istniejący filtr `symbolId` obejmuje także `outside`.
Pozycja bez obrazu i bez symbolu należy do „Poza zdjęciem”, także z oznaczeniem
Nieczytelny. Po przypisaniu należy wyłącznie do grupy symbolu oraz Wszystkich.
`sourceVisibility` (`full`, `partial`, `outside`) jest niezależne od decyzji;
przypisane `partial_visibility` pozostaje w grupie symbolu. Outside nie ma
predykcji ani pewności; jego zakres pomija filtr pewności. Wariant `assetMode=none`
zwraca jawne null dla identyfikatorów obrazu. Zmiana symbolu, Nieczytelny i Zła
siatka zachowują kontrolę rewizji pozycji i geometrii; zatwierdzanie obrazu,
Niewyraźny i wybór grafiki wymagają rzeczywistych pikseli. Oznaczenie Nieczytelny
może być rozwiązane jako logiczny symbol lub unknown bez zatwierdzenia cropa.
Niepełne źródło pozostaje `pending_partial` po decyzjach dotyczących symboli.
Podgląd istniejącego szczegółu planszy zwraca 0–15 rzeczywistych cropów oraz
pełne zdjęcie i geometrię; logiczna kolejka weryfikacji nadal ma 15 pozycji.

Sticky toolbar pokazuje liczbę wybranych cropów, selektor `Symbol do
zatwierdzenia` i jeden podstawowy przycisk `Zapisz i zatwierdź` (D-528).
Operator jawnie wybiera aktywny symbol. Brak celu lub zaznaczenia blokuje zapis.
Wskazanie tego samego symbolu zatwierdza oczekujące pole, a innego atomowo
poprawia i zatwierdza przypisanie. Oba przypadki korzystają z istniejącego
`reassign`, również dla gier innych niż Mumie. Nie ma osobnych przycisków
`Zatwierdź` i `Zastosuj zmianę`. Zmiana filtra czyści wybór celu.
Każde poprawne wywołanie `Zapisz i zatwierdź`, także przez `Enter`, natychmiast
czyści `Symbol do zatwierdzenia` po przechwyceniu celu decyzji. Kolejny zapis
wymaga ponownego wyboru. Dotyczy pojedynczej decyzji, niewyraźnych i logicznych
pól oraz przygotowania podglądu masowego. Polecenie podglądu/job zachowuje
przechwycony symbol; błąd albo anulowanie nie przywraca poprzedniego wyboru.
Toolbar zachowuje checkbox `Niewyraźny` i akcje `Nieczytelny / Zła siatka`.
Checkbox `Niewyraźny` modyfikuje zapis i zatwierdzenie: decyzja
atomowo zachowuje albo przypisuje wskazany symbol jako zatwierdzony, ale
wyklucza bieżący crop z kohort treningowych. Modyfikator jest resetowany po
zmianie gry albo zakresu symbolu. `Zła siatka` kieruje pole do kolejki korekty
geometrii, natomiast `Nieczytelny` pozostawia je poza kolejką geometrii i poza
kohortą treningową. Dwa ostatnie stany są w game-wide widoku
listy prezentowane jako `Nierozpoznany (?)`, a ich oryginalne przypisanie
pozostaje w danych i audycie. Komórka, której kadr wychodzi poza źródłowe
zdjęcie (1–3 z 4 rogów quada), jest renderowana z brakującą częścią czarną
i wymuszona jako nierozpoznana niezależnie od predykcji modelu
(`quality_issue = partial_visibility`, D-434/D-435/D-436) — operator nie
może jej ustawić ani usunąć ręcznie, wynika wyłącznie z geometrii planszy.
Karta pokazuje zwięzły
badge `Niewyraźny`, `Zła siatka · ?`, `Nieczytelny · ?`, `Poza kadrem · ?`,
`Nowy crop` albo `?`, gdy taki stan
dotyczy bieżących pikseli. W widoku `Zatwierdzone` badge zatwierdzonego cropa,
który nie spełnia aktualnych warunków kohorty treningowej, zawiera również
tekst `Poza uczeniem` oraz przyczynę: problem jakości (w tym `Poza kadrem`)
albo brak aktualnie
zatwierdzonego, checksum-bound cropa. Podsumowanie pokazuje aktualną i całkowitą liczbę
stron oraz jednoznaczny zakres pozycji. Każda akcja najpierw pokazuje niezmienny preview
liczby cropów i plansz, a potem uruchamia idempotentną operację masową.
`Zapisz i zatwierdź` działa wyłącznie dla jawnie zaznaczonych pól; walidacja
backendu wymaga aktywnego realnego symbolu. Zapis logiczny outside zachowuje
brak obrazka i nie tworzy przykładu treningowego.
Status operacji raportuje osobno wykonane, konfliktowe i błędne targety;
polling każdej operacji nie wysyła nakładających się requestów. Po końcowym
wyniku Admin nie odświeża automatycznie bieżącej strony ani jej atlasów:
zachowuje pozycję operatora, a dokładne wysłane targety pozostają przygaszone
i nieaktywne. Operator może jawnie wybrać `Odśwież cropy`, aby pobrać aktualny
stan ograniczonej strony, unieważnić jej cache oraz odblokować te targety.
Jeżeli odczyt strony utknie lub wymaga ponowienia, akcja `Ponów pobieranie
cropów` anuluje wyłącznie ten odczyt i zachowuje aktywną stronę, atlas oraz
lokalne zaznaczenia; widok nie zasłania poprzednio pobranych cropów podczas
ponowienia.
Nie zakłada, że każda decyzja usuwa pole z grupy:
outside bez przypisania po Nieczytelny pozostaje w Poza zdjęciem, a pole
przypisane w tej samej grupie lub Wszystkich nadal jest widoczne. Backend
wyznacza aktualną jakość, przynależność i rewizję także po częściowym wyniku.
Pamięciowa mapa tile obejmuje
wyłącznie aktywną stronę i jest czyszczona natychmiast przy zmianie strony,
filtra albo gry; odtwarzalny cache HTTP/serwera pozostaje niezależny.
Jedna jawnie zaznaczona karta jest wyjątkiem od workflow masowego: Admin wysyła
bezpośrednią, checksum-bound decyzję i nie tworzy joba. Po sukcesie czyści
zaznaczenie, pokazuje krótki komunikat i odczytuje bieżącą stronę. Po konflikcie
lub utracie odpowiedzi również odczytuje stan, zamiast zgadywać wynik zapisu.
Dwa lub więcej jawnych cropów
z bieżącej strony nadal korzysta z preview i trwałego joba. Toast nie zasłania
toolbara: jest stały około 50 px od lewego i dolnego brzegu viewportu.

Przycisk `Pełny ekran` w bloku filtrów przełącza widok w nakładkę na cały
viewport (TASK-0656): filtry, toolbar i podsumowanie pozostają stałe u góry,
wirtualna siatka wypełnia resztę wysokości i jest jedynym przewijanym
elementem, a paginacja zostaje na dole. `Esc` albo `Zamknij pełny ekran`
przywraca zwykły układ. Poza polami tekstowymi i selectami działają skróty:
`1`–`9` oraz `0` dla dziesiątego symbolu wybiera `Symbol do zatwierdzenia`
(aktywne symbole w kolejności `displayOrder` z katalogu gry, numer jest
widoczny przy nazwie w selekcie; TASK-0930), `Enter` wykonuje `Zapisz i zatwierdź` dla zaznaczonych cropów (z uwzględnieniem
`Niewyraźny`) albo potwierdza otwarty preview operacji masowej, a `Esc`
zamyka preview.

Przycisk `Ustaw jako grafikę symbolu` (TASK-0692) jest aktywny, gdy zaznaczony
jest dokładnie jeden crop. Jeżeli w `Symbol do zatwierdzenia` wybrano symbol, crop jest
najpierw przypisany do niego i zatwierdzony (`reassign`); w przeciwnym razie
zatwierdzany jest bieżący symbol (`approve`). Następnie crop zostaje grafiką
symbolu — tą samą, którą ustawia picker w sekcji `Symbole`, widoczną w
miniaturze `Symbole` i palecie `Wyszukaj plansze`. Opcja `Niewyraźny` blokuje
akcję. Jeżeli zatwierdzenie się udało, a ustawienie grafiki nie, komunikat
mówi to wprost, a zatwierdzenie zostaje. Użycie grafiki w wydaniu mobilnym
jest osobnym, niewykonanym jeszcze zakresem.

### Weryfikacja symbolu na planszy

Miniatury wirtualne przekazują aktualne `renderSpecChecksumSha256` z detailu
obok checksummy cropa. Dla plikowych cropów pole jest null i zachowuje się
dotychczasowy adres. Nie wolno omijać walidacji tożsamości renderowania.

Sekcja w obrębie wybranej gry rozwiązuje cropy oznaczone jako nieczytelne w
kontekście całej logicznej planszy. Domyślny widok `Do ustalenia` zawiera tylko
bieżących właścicieli mających co najmniej jedno `unreadable + pending`;
`Wszystkie nieczytelne` zachowuje audyt również po rozwiązaniu pól. Kolejka jest
bounded i keysetowa, a wiele problematycznych komórek nadal tworzy jedną pozycję
planszy.

Plansza renderuje dokładnie `rows × columns` z przypiętej topologii i pokazuje
crop, pozycję, bieżącą etykietę oraz jakość każdej komórki. W widoku `Do
ustalenia` operator może zmienić **każde** pole bieżącej planszy: wybiera
aktywny symbol albo prezentowaną w UI akcję `?`, a następnie używa jednego
przycisku `Zapisz i zatwierdź planszę`. UI wysyła pełny snapshot topologii;
backend zapisuje go atomowo, więc nie może powstać częściowo poprawiona
plansza. Zapis jest związany z rewizją komórki i geometrii, crop sample ID oraz
SHA-256. Podczas zapisu pozostałe akcje są zablokowane, a konflikt wymaga
ponownego pobrania bieżącej planszy. Widok `Wszystkie nieczytelne` ma charakter
audytowy: przełączenie resetuje keyset i pobiera jego własną kolejkę, ale
rozstrzygnięte plansze pozostają w nim tylko do odczytu.

Rozwiązanie zachowuje `quality_issue = unreadable`, dlatego crop pozostaje poza
treningiem niezależnie od wybranej etykiety. Wybranie `?` również dla wcześniej
zwykłego cropa oznacza go jako `unreadable`, dzięki czemu nie trafia do
treningu. Ostatnia decyzja może domknąć planszę jako `corrected`; `?` jest
wyłącznie reprezentacją UI wyniku bez przypisanego symbolu i nie tworzy symbolu
katalogowego. Bieżące API zachowuje zgodność przez payload `{kind: unknown}`
oraz legacy `NULL`, natomiast przyszły write model używa jawnego outcome v2.
Snapshot v4 materializuje taki wynik jako sentinel `mobileCode = 0`, podczas
gdy UI nadal pokazuje `?`; kanoniczny właściciel i pełny audyt decyzji pozostają
zachowane.

Nieczytelność jest związana z bieżącymi pikselami, a nie z etykietą. Dlatego
również późniejsze `Zatwierdź` lub `Zmień symbol` w zwykłej `Weryfikacji
symboli` zachowuje `quality_issue = unreadable`; jawna zmiana nazwy nie może
przypadkiem ponownie dopuścić cropa do treningu. W pełnym widoku planszy każde
takie pole ma widoczny badge `Nieczytelny` i lekką szarą warstwę na obrazie,
także gdy operator przypisał mu konkretny symbol.

Symbol można fizycznie usunąć wyłącznie, gdy nie ma zależności w regułach,
planszach, predykcjach, kohortach, iteracjach ani aktywacjach modeli. Modal
wyświetla dokładne liczniki blokujących zależności. Panel nie oferuje
automatycznego bootstrapu katalogu ani archiwizowania symbolu.

### Sekcja „Brakujące plansze” w Import plansz (D-437)

Zastępuje dawną kartę „Kompletność zaakceptowanych plansz” (liczącą tylko
zatwierdzone plansze) i osobną listę „Ostatnie importy tej gry”. Definicja
„planszy dodanej” jest decyzją D-437 (`DECISION_LOG.md`): numer w zakresie
`1..expectedLayoutCount` jest dodany, gdy ma kanoniczną sekwencję albo żywy
(`pending`/`accepted`/`corrected`) element review z ukończonym cięciem na 15
komórek — zatwierdzenie symboli nie jest do tego wymagane. Sekcja korzysta z
`GET .../board-import-coverage/{gameId}`.

Zachowanie:

- liczniki `Oczekiwane`/`Dodane`/`Brakujące` liczą zawsze cały zakres
  `1..expectedLayoutCount`; podlinia cytuje `w tym zatwierdzone` (ten sam
  licznik co stary raport kompletności, który zostaje bez zmian pod
  `dataset-completeness`) i wskazuje, że cel pochodzi z ustawień gry
  (Katalog gier),
- linia „Powody” pokazuje niezerowe liczniki siedmiu przyczyn braku, w
  kolejności priorytetu: `import_in_progress`, `waiting_for_geometry`,
  `partial_source`, `failed`, `rejected`, `unknown`, `no_source`,
- baner z informacją o pociętych planszach bez ustalonego numeru, zdjęciach z
  błędem bez znanego zakresu, aktywnych jobach importu i aktywnych źródłach
  bez zakresu pojawia się tylko, gdy któryś z tych liczników jest dodatni,
- filtr ma dwa stany, `Brakujące` (domyślny) i `Dodane` — bez wariantu
  „Wszystkie”; wyszukiwanie przyjmuje pojedynczy numer albo zakres
  (`a-b`/`a–b`, tolerancyjne na spacje) i zawęża zarówno liczniki okna, jak i
  listę segmentów,
- lista pokazuje kolejne segmenty (przedziały o tym samym stanie), maksymalnie
  100 na stronę, ze stronicowaniem keyset po numerze sekwencji,
- odświeżanie następuje przy wejściu na ekran, po każdym `Odśwież status`
  panelu (przez rosnący `refreshToken`), po zmianie filtra/zakresu i co 15 s
  automatycznie, ale wyłącznie gdy trwa aktywny import tej gry,
- ekran rozróżnia siedem stanów: ładowanie, błąd pobrania (z przyciskiem
  ponowienia; poprzednie dane zostają widoczne z osobnym ostrzeżeniem o
  nieaktualności), nieznany cel kompletności (bez liczników), brak
  jakiegokolwiek importu, wszystko dodane, pusty wynik filtra/zakresu i
  zwykła lista.

Akcje ponownego przetwarzania importu („Przetwórz ponownie z oryginałów”,
„Przetwórz w v1.0”, „Kontynuuj z ręczną korektą”) oraz podgląd siatek
(`ImportGeometryReviewSummary`) zostają bez zmian logiki, przeniesione do
domyślnie zwiniętego bloku „Ponowne przetwarzanie importów” z pięcioma
najnowszymi importami gry. Diagnostyka techniczna per job (wersja silnika
cięcia, manifest geometrii stron, test ochronny, wersja modelu symboli,
wynik pipeline'u) została usunięta z tego widoku; pozostaje dostępna w
zakładce Joby.

### Diagnostyka siatek zdjęć w Korekcie cięcia siatki (D-484, D-525, TASK-0890)

Jednostką geometrii jest zdjęcie źródłowe (D-484). Diagnostyka znajduje się
w „Korekcie cięcia siatki”, pod uruchomieniem Reviewera. Nie jest częścią
„Importu plansz”; raport brakujących numerów plansz zostaje w imporcie.
Pokazuje, ile zdjęć gry ma komplet poprawnych siatek, a ile nie, i listuje
zdjęcia niekompletne. Od TASK-0807 jest kolejką siatek bramki D-484:
zakładka domyślna „Kolejka siatek” pokazuje zdjęcia ze stanem zapisanym w
bazie `geometry_incomplete` (`completenessStatus`), a „Wyjątki operatora” —
zdjęcia `geometry_exception`. Siatki poprawia się w istniejącej korekcie siatek
(Reviewer, przycisk „Popraw siatki w Reviewerze” otwiera lokalnego Reviewera
dla importu zdjęcia). Korzysta z `GET .../geometry-completeness/{gameId}`,
`.../incomplete-images`, `.../low-quality-boards` oraz
`POST`/`DELETE .../images/{sourceImageId}/exception`.

Opis wyjaśnia, że w V3 (D-523) poprawne pełne siatki są cięte automatycznie
niezależnie od innych slotów zdjęcia. Niekompletność całego zdjęcia nie
oznacza niedostępności wszystkich jego cropów. Przeniesienie UI nie zmienia
kwalifikacji kolejki, danych ani kontraktu API. Zmiana gry resetuje diagnostykę.

Definicje (zapisane w czystej funkcji `domain/image_geometry_completeness.py`,
ten sam przepis liczy SQL raportu):

- oczekiwane pozycje zdjęcia to `active_board_slots` jego najnowszej rewizji
  geometrii źródła; numer sekwencji pozycji `p` to `sequence_range_start + p`;
  plansze poza tymi pozycjami (np. ze starszej, dłuższej rewizji) nie liczą się,
- „żywa plansza” to `recognized_boards.status <> 'rejected'`; plansza odrzucona
  nie jest dowodem poprawnej siatki, więc pozycja z samą planszą odrzuconą nie
  ma żywej planszy. „Żywy element review” to `image_review_items.status` w
  `pending | accepted | corrected`,
- pozycja (pierwsza pasująca reguła): `superseded` — brak żywej planszy, a numer
  sekwencji pozycji ma żywy element review na innym zdjęciu tej samej gry
  (numer żywy tylko w innej grze nie wystarcza); `deferred` — brak żywej
  planszy i otwarty (`pending`) wiersz odroczonej geometrii (z kodem powodu);
  `missing` — brak żywej planszy, pozostałe przypadki; dla żywej planszy: `ok`,
  gdy jest kompletna, a jej geometria jest zatwierdzona przez człowieka
  (`approved_geometry_revision = geometry_revision`) albo rewizja źródła, na
  którą plansza wskazuje, ma status `accepted`; `uncertain` — kompletna plansza
  bez żadnego z tych dowodów; `partial` — plansza `pending_partial`,
- zdjęcie (pierwsza pasująca reguła): `superseded` — ma rewizję źródła i
  wszystkie oczekiwane pozycje są `superseded`, albo nie ma żadnej żywej planszy,
  a inne zdjęcie tej gry z tym samym `checksum_sha256` ma żywe plansze;
  `import_failed` — brak żywej planszy i plik importu zdjęcia ma
  `workflow_status = 'failed'` (kod z `image_import_job_files.error_code`);
  `no_source_geometry` — brak jakiejkolwiek rewizji geometrii źródła (oczekiwana
  liczba plansz jest nieznana); `complete` — każda pozycja `ok` albo
  `superseded`, co najmniej jedna `ok`; inaczej `incomplete_missing` (jest
  pozycja `missing`/`deferred`), `incomplete_partial` albo
  `incomplete_uncertain` (pozycje `superseded` są tam pomijane). Zdjęcia
  `superseded` i `complete` nie są niekompletne; `import_failed` i
  `no_source_geometry` mają własne liczniki i filtry, a lista domyślna („Wszystkie”)
  obejmuje stany `incomplete_*`, `import_failed` i `no_source_geometry`.
  Zdjęć w statusie `processing` nie pomijamy: wchodzą do liczników i do linii
  „w tym N zdjęć w przetwarzaniu” (o ile nie są `superseded`).

Zachowanie:

- liczniki: zdjęcia w grze, niekompletne w grze i — po wybraniu przełącznika
  „Wybrany import” — niekompletne w imporcie, osobny licznik zdjęć „Zastąpione
  nowszym importem”; linia stanów zdjęć (brakuje plansz / plansza częściowa /
  siatka niepotwierdzona / import nieudany / bez geometrii źródła) i linia
  „Plansze bez poprawnej siatki” z podziałem pozycji na stany i powody
  odroczenia; pozycje i zdjęcia `superseded` nie są brakami, więc mają własną
  linię („Zastąpione nowszym importem, więc nie są brakami”) i nie wchodzą do
  liczby niekompletnych ani do listy domyślnej,
- filtr stanu zdjęcia (`Wszystkie`, pięć stanów wymagających uwagi i
  „Zastąpione nowszym importem”, żeby zdjęcia zastąpione dało się obejrzeć) i
  lista po 25 zdjęć z przyciskiem „Pokaż więcej zdjęć”, kursor keyset po
  `(relativePath, sourceImageId)`,
- każde zdjęcie pokazuje ścieżkę, status zdjęcia, zakres numerów, oczekiwaną
  liczbę plansz, kod błędu pliku importu (`importErrorCode`, gdy plik się nie
  powiódł) oraz SVG o wymiarach zdjęcia (`exif-normalized-rgb-pixels-v1`)
  z naniesionymi siatkami plansz: kolor zielony `ok`, żółty `uncertain` i
  `partial`, czerwony linią przerywaną pozycje bez poprawnej siatki, szary
  pozycje `superseded`; pozycje bez czworokąta są dodatkowo opisane tekstem „bez
  siatki”. Czworokąt pochodzi z rewizji, z której plansza została pocięta (a dla
  pozycji bez żywej planszy z rewizji bieżącej); nic nie jest zgadywane,
- przycisk „Pokaż zdjęcie pod siatkami” jest dostępny dla każdego zdjęcia gry,
  także bez żadnej planszy czy rewizji geometrii: pobiera plik endpointem
  `getImageGeometryCompletenessSourceAsset` kluczowanym `sourceImageId`
  (zdjęcie bez wymiarów lub siatek pokazuje się jako zwykły obraz),
- „Plansze z niską jakością symboli” to osobne, jawnie uruchamiane zapytanie
  (przycisk; nigdy przy ładowaniu ani w odświeżaniu): plansze, na których co
  najmniej `minCells` (domyślnie 5) widocznych pól bez decyzji człowieka
  (`review_state = pending`) ma pewność predykcji `≤ maxConfidence` (domyślnie
  80 %). Zakres to wybrany import albo cała gra; przekroczenie limitu 10 s daje
  jawny błąd z podpowiedzią zawężenia do importu, nigdy pusty wynik,
- odświeżanie: przy wejściu, po `Odśwież kolejkę` w korekcie (`refreshToken`) i po
  zmianie zakresu/filtra; co 15 s odświeżane są wyłącznie liczniki i tylko gdy
  trwa aktywny import tej gry.

Bramka (TASK-0807):

- liczniki bramki ze stanu w bazie: „Kolejka siatek (wstrzymane)”, „Wyjątki
  operatora”, „Plansze wstrzymane przed cięciem” z powodem
  `SOURCE_IMAGE_GEOMETRY_INCOMPLETE` i „Nieocenione przez bramkę” (zdjęcia
  sprzed backfillu, które działają jak przed wdrożeniem bramki),
- każde zdjęcie listy pokazuje stan bramki z bazy, powód wstrzymania i — dla
  wyjątku — powód, autora i czas; zakładki stanów wyliczanych w locie
  („Wszystkie niekompletne” i stany zdjęcia) zostają do diagnozy,
- „Dopuść wyjątkiem…” (tylko dla zdjęcia `geometry_incomplete`) wymaga powodu
  (1–1000 znaków) i jest operacją wysokiego wpływu; po zapisie plansze `ok` i
  częściowe z zatwierdzoną kwalifikacją są cięte od razu. „Wycofaj wyjątek”
  (po potwierdzeniu) przywraca kolejkę bez usuwania komórek; po decyzji
  człowieka na komórkach zdjęcia API odmawia z czytelnym komunikatem,
- filtr działa w zapisie, nie w UI: plansze wstrzymane nie mają komórek
  weryfikacji ani dowodów symboli w wyszukiwarce, a lista tylko je pokazuje.

### Minimalistyczne stanowisko zatwierdzania

Operacyjne review dużego importu używa `image_review_items`, a nie ograniczonego
batcha active-learning. Ekran jest zoptymalizowany pod szybkie sprawdzanie
pełnych plansz i ma:

- pokazywać w dropdownie `Gotowy import plansz` wyłącznie importy mające
  nierozwiązane pozycje (`waiting_for_review`); zakończone importy pozostają
  audytowalne w `Jobach`, ale nie zaśmiecają operacyjnego wyboru,
- dla nakładających się importów pozostawić w review wyłącznie najnowszą
  oczekującą planszę danego numeru; zatwierdzona albo poprawiona plansza
  kanoniczna jest chroniona i nie wraca do review po kolejnym imporcie,
- prezentować gotowe stagingi w `Import plansz` według liczbowego początku
  zakresu z nazwy katalogu; nazwy bez prefiksu `<liczba>-` są umieszczane za
  zakresami w stabilnej kolejności,
- przy liczbie plików, rozmiarze i skrócie ID stagingu pokazywać jego najwyższy
  trwały etap: `załadowano folder`, `przygotowano preflight`, `przygotowano
  siatkę` albo `gotowy`; ostatni stan oznacza, że zgodny import zakończył cięcie
  zdjęć na symbole i oczekuje na review albo został już zakończony,
- działać jako osobna aplikacja przeglądarkowa `Reviewer`, a nie sekcja
  właściwego panelu administracyjnego,
- pokazywać gotowy staging plansz bieżącej gry jako etap poprzedzający import;
  staging nie jest elementem dropdownu ani pracą Reviewera, dopóki jawny job
  importu nie utworzy kolejki plansz,
- dla aktywnego gotowego stagingu z raportem pokazywać wirtualną politykę gry
  (`structured_default` albo `structured_lattice_v3`); od D-467 (TASK-0790)
  v20/v19 i v18 są wyłącznie etykietami historycznych jobów i nie są opcją
  nowego importu,
- start przekazuje bieżącą politykę w checksum-bound komendzie i nie może
  prezentować sukcesu, jeżeli zwrócony job nie ma wirtualnego snapshotu tej
  samej rewizji; nieudana geometria tworzy trwałe odroczenie do końcowej
  korekty, rozwiązywane ścieżką wirtualną,
- mieć własny proces i lokalny adres; panel Admin wybiera grę oraz gotowy
  import i pokazuje dla niego liczniki wszystkich, oczekujących i zakończonych
  plansz,
- identyfikować import w dropdownie krótką datą i godziną, nazwą katalogu oraz
  krótkim statusem; techniczne ID wybranego joba jest widoczne osobno, a długa
  etykieta nie poszerza bez ograniczenia kontrolki,
- mieć jeden przycisk `Otwórz lokalnie`, który bez tworzenia assignmentu,
  sesji, kodu ani tunelu uruchamia albo ponownie wykorzystuje proces Reviewera
  przez stały endpoint `reviewer-local/start`; dopiero po potwierdzeniu gotowego
  targetu loopback na porcie `3001` ponawia nawigację przygotowanego okna na
  wybraną grę i import; sekcja nie pokazuje kontrolek online, stanu ingressu,
  aktywnych prac ani akcji kończenia pracy,
- działać wyłącznie ze strony Admina otwartej przez loopback; zablokowane nowe
  okno pozostawia właścicielowi widoczny, ręczny link do dokładnie tego samego
  lokalnego scope'u,

- kompaktowy header z grą, `sequence_number`, pozycją w kolejce, statusem,
  przełącznikiem `Widok planszy` / `Plansze kompletne`, nawigacją i małym
  przyciskiem `Zatwierdź`,
- wybór gry oraz import joba; każdy odczyt i zapis pozostaje ograniczony do
  wybranego kontekstu,
- zwartą siatkę 5 × 3 z kwadratowymi cropami i widocznymi etykietami symboli;
  siatka nie rozciąga się na całą szerokość i mieści się bez przewijania w
  obsługiwanym widoku desktopowym co najmniej 1366 × 768,
- wybraną komórkę z bieżącą etykietą i tooltipem 3–4 najbardziej
  prawdopodobnych symboli,
- obok siatki wycięty obraz dokładnie jednej bieżącej planszy 5 × 3; główny
  ekran nie pokazuje całego zdjęcia źródłowego zawierającego do dziewięciu
  plansz,
- widoczną legendę skrótów symboli.

Aktywna sesja utrzymuje jedną deterministyczną kolejność wszystkich plansz
wybranego importu, niezależnie od ich bieżącego statusu. Statusy i przełącznik
widoku mogą zmieniać prezentowane liczniki, ale nie mogą usuwać
accepted/corrected z nawigacji sesji. Strzałki lewo/prawo przechodzą po tej
pełnej kolejności; strzałka w lewo musi wrócić również do planszy zatwierdzonej
chwilę wcześniej.

Reviewer ma dodatkowy przełącznik `Wszystkie / Do poprawy siatki`. Drugi widok
jest wyłącznie listą pending plansz, których bieżąca geometria ma co najmniej
jedną komórkę oznaczoną jako zła siatka. Nie tworzy osobnej flagi planszy,
nie dubluje planszy z wieloma oznaczeniami i nie wykonuje automatycznej korekty.
Po zapisaniu nowej geometrii plansza znika z tego widoku, ponieważ wszystkie
15 bieżących komórek wraca do stanu oczekującego bez flagi problemu. Kursory
obu widoków są rozłączne.

Status gotowego importu jest domykany razem z trwałą kolejką review. Import z
co najmniej jedną planszą pozostaje `waiting_for_review`, dopóki licznik
`pending` jest dodatni, i przechodzi do `completed` po rozwiązaniu ostatniej
pozycji. Jawna korekta geometrii, która ponownie otwiera choć jedną planszę,
przywraca `waiting_for_review`. Oba statusy pozostają dostępne w selectcie, aby
ukończony import można było przeglądać audytowo.

Przy pierwszym wejściu albo pełnym odświeżeniu aplikacja ustawia bieżącą
pozycję na pierwszej planszy `pending`. Jeżeli nie istnieje żadna plansza
`pending`, zaczyna od pierwszej planszy importu. Nie oznacza to pobrania pełnej
kolejki do klienta: każda bieżąca plansza i sąsiad są nadal pobierane bounded,
z limitem jednej planszy. Reviewer utrzymuje najwyżej cztery takie odpowiedzi:
jedną poprzednią, bieżącą i dwie następne. Metadane oraz zasoby obrazu
poprzednika i dwóch następców są prefetchowane, a przejście po gotowym sąsiedzie
nie pokazuje pełnoekranowego stanu ładowania. Przesunięcie okna usuwa dalsze
pozycje ze stanu React; nie wolno materializować całego importu.

Symbole są mapowane według stabilnej kolejności katalogu gry: klawisze
`1`–`9`, `0` dla dziesiątego, a następne pozycje kolejno do klawiszy w
wierszach `QWERTY`. Pojedyncze `Enter` albo kliknięcie `Zatwierdź` wykonuje
zapis bez dodatkowego modala, a po poprawnym zapisie przesuwa bieżącą pozycję
do następnej planszy w pełnej kolejności. Skróty nie działają podczas pisania
w polu, w innym dialogu ani podczas trwającego zapisu. Idempotency key i
blokada trwającego żądania nadal chronią przed podwójnym zdarzeniem.

Klucz idempotencji jednej niezmienionej komendy jest zachowywany także po
niejednoznacznym błędzie transportu. Pojedyncza próba ma ograniczony czas
oczekiwania; pierwszy timeout powoduje dokładnie jedno automatyczne ponowienie
tej samej pełnej komendy z tym samym kluczem. Drugi timeout odblokowuje UI i
informuje, że decyzja mogła zostać utrwalona, zamiast pozostawiać przycisk
`Zatwierdź` bezterminowo wyłączony. Ponowienie może więc odzyskać poprawnie
utrwaloną decyzję zamiast wysłać nową komendę na starej rewizji. Pomyślny zapis
zwraca trwały `queueVersion` i dokładne liczniki po całej transakcji, w tym po
ewentualnym zastąpieniu innych źródeł. Reviewer nie wyprowadza tych liczników z
lokalnej tablicy. Przeładowanie bieżącej planszy jest wymagane tylko przy
konflikcie jej rewizji lub geometrii; zmiana sąsiedniej pozycji albo samych
liczników nie jest konfliktem komendy. Konflikt rewizji podczas zapisu pełnej
decyzji automatycznie pobiera autorytatywną, aktualną rewizję tej planszy i
czyści klucz nieaktualnej komendy. Reviewer nie pozostawia operatora na
niezapisywalnym snapshotcie ani nie ponawia tej komendy na nowej rewizji. Jeżeli
inna sesja zdążyła już zapisać decyzję, jej wynik pozostaje widoczny i nie jest
po cichu nadpisywany.

Jeżeli inny reviewer wcześniej zapisze kanoniczną decyzję dla tej samej gry i
numeru, bieżąca oczekująca pozycja otrzymuje kontrolowany status `superseded`.
Reviewer pokazuje ten status i osobny licznik, nie traktuje go jako technicznego
błędu zapisu i nie pozwala korektą geometrii ponownie otworzyć przegranego
źródła. Kanoniczny właściciel oraz oba źródła pozostają audytowalne.

Plansza accepted/corrected pozostaje dostępna w widoku `Plansze kompletne` i
może zostać ponownie edytowana. Zmiana tworzy kolejną rewizję append-only;
wcześniejsza decyzja nie jest usuwana. Późniejsza inferencja albo trening nigdy
nie nadpisuje decyzji człowieka i może aktualizować sugestie wyłącznie dla
nierozwiązanych plansz.

Pełne zdjęcie źródłowe pozostaje dostępne wyłącznie w kontekście korekty
geometrii. Przycisk `Edytuj siatkę` w prawym górnym rogu otwiera osobny tryb
czterech narożników granic siatki symboli na oryginalnym obrazie. Podgląd
pokazuje projektową siatkę 5 × 3 oraz wszystkie 15 finalnych cropów bez
pośredniego rastra planszy. Zapis geometrii tworzy nowe wersje plików
i checksum, ponownie otwiera etykiety zależne od zmienionych `cropSampleId` i
zachowuje wcześniejszą geometrię w audycie. Korekty mogą później służyć do
zbudowania nowej wersji profilu cięcia, ale nigdy nie są automatycznie
propagowane na inne plansze.

Po zaakceptowaniu bramki geometrii panel jakości udostępnia osobną, jawną
akcję `Przelicz oczekujące`. Przed startem pokazuje wszystkie plansze
`pending`, liczbę faktycznie wymagającą v19, liczbę już zapisaną w v19,
chronione decyzje i przypięte wersje geometrii/croppera. Przycisk jest
nieaktywny, gdy `recalculableBoardCount = 0`, oraz blokuje drugi submit podczas
tworzenia joba. Operacja nie obiecuje automatycznego rozwiązania: plansze bez
pełnej geometrii 3 × 5 pozostają do ręcznej korekty.

Przycisk zapisu jest dostępny dopiero po wygenerowaniu podglądu odpowiadającego
bieżącym czterem punktom. Każde przesunięcie uchwytu unieważnia poprzedni
podgląd. W trakcie zapisu drugi submit i zamknięcie dialogu są zablokowane, a
konflikt rewizji wymaga przeładowania bieżącej planszy. Udany zapis nie
przechodzi do następnej pozycji: zastępuje bieżący item odpowiedzią backendu i
pokazuje go jako ponownie oczekujący na weryfikację symboli.

Obsługa narożników musi pozostać zgodna z widoczną treścią obrazu również po
skalowaniu i dodaniu pustych pasów przez `object-fit: contain`; próg trafienia
jest stały w pikselach ekranu, a nie w pikselach źródła. Po zapisie Reviewer
natychmiast zastępuje bieżący item projekcją zwróconą przez backend i pobiera
planszę oraz cropy spod adresów wersjonowanych ich checksumami. Nie wolno
pokazać starego assetu z cache jako wyniku nowej rewizji geometrii.

Odroczona geometria komórek ma osobny, jawny tryb końcowego fallbacku. Admin
pokazuje jej licznik dla wybranego importu i pozwala otworzyć Reviewer również
wtedy, gdy zwykła kolejka ma `total = 0`, ale istnieje co najmniej jeden
`image_board_geometry_pending` w stanie `pending`. Reviewer pobiera najwyżej
jeden taki wyjątek, a lokalna historia nawigacji nie może materializować całej
kolejki ani jej obrazów.

Ekran fallbacku pobiera checksum-bound źródło i kontekst przypięty do manifestu
oraz rewizji. Operator przesuwa dokładnie cztery narożniki perspektywicznej
siatki 5 × 3 i przed zapisem musi wygenerować aktualny podgląd wszystkich 15
cropów source-direct. Każda zmiana narożników unieważnia podgląd. Niejednoznaczny
błąd transportu zachowuje klucz idempotencji niezmienionej komendy, natomiast
konflikt, superseded albo rozstrzygnięcie przez inną sesję powodują bezpieczne
przeładowanie bez nadpisania wyniku człowieka. Skuteczny zapis usuwa wyjątek z
domyślnej kolejki `pending`, przechodzi do następnego wyjątku i tworzy zwykły
item do zatwierdzenia symboli w istniejącej kolejce; nie powstaje druga trwała
kolejka plansz.

Gdy fizyczne zdjęcie przycina planszę, checkbox „Niepełna plansza” (TASK-0693)
odblokowuje szary obszar poza realnymi pikselami — operator przeciąga tam
narożniki, żeby poprawnie ekstrapolować siatkę, i jawnie zaznacza, których z 15
pól naprawdę nie ma na zdjęciu. Zaznaczone pola pomijają rygor pełnego pokrycia
źródła wyłącznie dla siebie (reszta planszy nadal wymaga kompletnych cropów)
i po zapisie dostają wymuszony symbol „?” zamiast trafiać do modelu; plansza
jest wykluczona z uczenia geometrii (`geometryQualification`,
`completenessStatus=pending_partial`), tak jak w pozostałych dwóch edytorach
geometrii. Board zostaje `asset_mode=legacy_file` — ta ścieżka nie generuje
wirtualnych, częściowo widocznych cropów jak `virtual_source`.

W tym samym edytorze operator może przesunąć widok źródła wyłącznie po jawnym
zaznaczeniu checkboxa „Aktywne przesuwanie”, chwytając tło canvasu poza
uchwytami narożników, oraz użyć akcji „Wycentruj widok na siatce”. Checkbox
jest domyślnie wyłączony dla każdej wczytanej planszy, więc zwykły gest poza
uchwytem nie porusza zdjęcia. Ruch zmienia wyłącznie lokalny viewport
prezentacji: cztery narożniki, kwalifikacja, podgląd, klucz idempotencji i zapis
pozostają w niezmienionych współrzędnych oryginalnego zdjęcia. Viewport jest
ponownie centrowany także po zmianie narożnika, aby aktualna siatka nie znikała
poza canvasem. W trybie „Niepełna plansza” może obejmować obszar poza zdjęciem,
widoczny jako szare tło. Nie tworzy to brakujących pikseli. Według D-451
pozycja rzeczywiście poza kadrem zachowuje trwałe `outside` i bez przypisania
trafia do grupy „Poza zdjęciem”. Ręczne przypisanie przenosi ją do grupy
symbolu, zachowując brak obrazu i badge.

Po jawnym poleceniu właściciela, przykładowo po 1000 albo 3000 zweryfikowanych
planszach, panel pozwala zamrozić nową kohortę feedbacku. Sam licznik nie
uruchamia treningu. Nowy model używa niezmiennego eksportu i nie zmienia
accepted/corrected. W pełni ręcznie zweryfikowany, ciągły zakres może przejść
do stagingu i standardowej walidacji także wtedy, gdy automatyczny masowy
import pozostaje wyłączony.

### Lokalna sesja i przyszły zdalny dostęp do review

Rozdzielenie aplikacji `Reviewer`, wybór gry/importu, link i kod wejścia są
częścią lokalnego M6.5. Kod nie znajduje się w linku, a sesja wygasa. Na tym
etapie API i obie aplikacje pozostają na loopback, dlatego nie wolno udostępniać
tego linku osobie spoza komputera ani przekierowywać portu routera.

Zdalne review jest odłożonym zakresem M8.7, a nie warunkiem lokalnego ekranu.
Administrator docelowo wybiera grę i tworzy odwoływalną, ograniczoną czasowo
sesję. Otrzymuje link oraz osobno przekazywany kod. Recenzent po poprawnej
weryfikacji ma wyłącznie dostęp do odczytu obrazów i zapisu decyzji wskazanej
gry; nie otrzymuje CRUD konfiguracji, jobów, eksportów ani wydań Android.

Kod nie może być przechowywany jawnie, ma limit prób i czas ważności. Sesję
można unieważnić, każda decyzja zapisuje aktora i sesję, a konflikt dwóch
recenzentów używa istniejącej kontroli rewizji. Zdalny tryb wymaga HTTPS przez
jawnie wybrany tunel albo VPN. Domyślny loopback pozostaje włączony, a surowe
przekierowanie portu routera nie jest wspieraną instrukcją.

### Aktualizacja zdalnego dostępu v0.1

Powyższy akapit o „przyszłym” M8.7 opisuje wcześniejszy baseline. W v0.1
zdalny tryb jest wdrożony przez jawnie uruchamiany Cloudflare Quick Tunnel do
samej aplikacji Reviewer. API, Admin i PostgreSQL nadal bindują loopback, a
publiczny same-origin proxy ma zamkniętą allowlistę.

Sesja jest trwała, ma maksymalnie pięć prób kodu, wydaje rotowany token,
wygasa i może zostać natychmiast unieważniona w Adminie. Recenzent widzi tylko
jedną grę/import i nie ma tras do konfiguracji, job mutations, eksportów ani
wydań. Surowe przekierowanie portu routera pozostaje zabronione.

Publiczny lifecycle jest obsługiwany z panelu: start jest idempotentny i ma
ograniczony czas oczekiwania, a stop usuwa stan tunelu. Tryb CLI
`reviewer:remote:start/status/stop` pozostaje awaryjnym odpowiednikiem tych
samych kontrolowanych operacji.

### Sekcja „Supergry” (TASK-0934, D-535, D-536)

Zakładka gry (`?workspace=games&game=<id>&section=super-games`) widoczna tylko
dla gier z rodzajem supergry innym niż `none`; dla gry `none` zakładki nie ma,
a adres z `section=super-games` jest czyszczony do braku sekcji. Opcjonalny
parametr `series=<seriesId>` otwiera od razu widok serii (używa go
wyszukiwanie plansz z TASK-0935) i jest odczytywany oraz zapisywany w adresie
wyłącznie w tej sekcji. Dane pochodzą z tras `…/super-game-series`
(`API_CONTRACT.md`); Admin nie liczy serii sam.

Lista serii:

- stronicowanie kursorem (50 na stronę, „Wczytaj kolejne”) i trzy filtry:
  kompletność (`complete`/`incomplete`), wiarygodność przebiegu
  (`verified`/`unverified`) oraz super symbol (z symbolem / do
  zdefiniowania); zmiana filtru zaczyna listę od nowa, a spóźniona odpowiedź
  poprzedniego filtru jest ignorowana,
- licznik „serii bez super symbolu” liczy się osobnym zapytaniem
  `defined=false&limit=200`, niezależnie od filtrów listy; przy pełnej stronie
  pokazuje dolne ograniczenie (`200+`),
- przycisk „Przelicz serie” wywołuje `deriveSuperGameSeries` i pokazuje toast
  z numerem joba (osobny komunikat, gdy job był już zakolejkowany),
- gdy `superGameState.fresh = false`, nad listą i widokiem serii jest baner
  „Serie w trakcie przeliczania…”; Admin co 5 s czyta `…/state` i po
  powrocie do `fresh = true` odświeża listę oraz otwartą serię,
- każdy wiersz ma trzy niezależne oznaczenia: kompletność (`Kompletna` /
  `Niekompletna`), symbol (`Symbol: <nazwa>` / `Do zdefiniowania`) i
  wiarygodność przebiegu (`Przebieg zweryfikowany` / `Przebieg
  niezweryfikowany`, gdy wyzwalacz lub retrigger opiera się na predykcji).

Widok serii:

- karuzela ma kartę dla każdej pozycji `trigger … start + length − 1`;
  pierwsza karta to plansza wyzwalająca, a pozycje serii (`start …
  start + length − 1`) są kolejnymi kartami. Pozycja bez planszy (znana luka
  albo za ostatnim układem gry) to pusta karta „brak planszy”, retriggery mają
  znacznik „Retrigger”. Pasek pozycji pozwala przejść do dowolnej karty,
  a ← / → i przyciski „Poprzednia” / „Następna” przesuwają o jedną,
- karta pokazuje kadr planszy (ten sam co wyniki wyszukiwania), układ symboli
  3×5 z wyróżnionymi komórkami symbolu uruchamiającego (komórki są też
  zaznaczone na kadrze, gdy API zwraca wielokąty komórek) oraz przycisk
  „Pokaż planszę z liniami”, który otwiera okno linii z wyszukiwania plansz.
  Symbole komórek są czytane z wersji reguł: najnowszy draft, a przy jego
  braku najnowsza opublikowana,
- panel „Super symbol” ma select wyłącznie ze zwykłymi symbolami (aktywne, nie
  Wild, nie uruchamiające supergrę) w kolejności katalogu, z numerem skrótu
  przy opcji: `1`–`9`, a `0` wybiera dziesiąty symbol listy. `Enter` zapisuje,
  `Esc` odrzuca wybór, a „Wyczyść symbol” ustawia `null` (zapis po `Enter`
  albo „Zapisz”). Skróty nie działają w polach tekstowych i selectach, z
  klawiszami Ctrl/Alt/Meta/Shift ani przy otwartym oknie linii; `Enter` na
  sfokusowanym przycisku wykonuje ten przycisk,
- zapis wysyła `expectedRevision` równe rewizji widocznej na ekranie. Sukces
  ustawia symbol i podbija rewizję, a kompletność i wiarygodność przebiegu
  zostają bez zmian. Konflikt rewizji (409) niczego nie zapisuje: Admin
  pokazuje komunikat, czyta serię od nowa i porzuca nieaktualny wybór.
  Odmowa API (Wild, symbol uruchamiający albo zarchiwizowany, 422) jest
  pokazywana w komunikacie, bez zmiany serii. Wybór symbolu uruchamiającego
  jest zablokowany po stronie Admina, zanim zapytanie zostanie wysłane.

### Mobile releases

Panel zawiera sekcję lub przycisk przygotowania wersji Android.

Administrator:

1. wybiera wersję datasetu i reguł dla każdej dołączanej gry,
2. uruchamia walidację kompletności,
3. uruchamia obliczanie payoutu każdego layoutu,
4. generuje niezmienny snapshot SQLite,
5. uruchamia przygotowanie wersjonowanego APK,
6. widzi status zadania, wersję, checksumy i ścieżki artefaktów,
7. może pobrać gotowy APK i skopiować względną ścieżkę jego katalogu do ręcznej
   instalacji. Otwarcie katalogu odbywa się ręcznie po stronie Windows; panel
   przeglądarkowy nie wykonuje dowolnej komendy systemowej.

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
2. Dodaje symbole `S1`–`S12` i oznacza Wild.
3. Tworzy trzy poziome paylines przez modal siatki.
4. Nie może wybrać dwóch komórek w jednej kolumnie ani zapisać niepełnego wzorca.
5. Nie może zapisać duplikatu `row_path`.
6. Pozostawia dla większości symboli domyślne minimum 3, dla co najmniej jednego
   symbolu ustawia minimum 2 i uzupełnia wszystkie wymagane wartości kredytów.
7. Generuje lub importuje 1000 layoutów.
8. Widzi luki, błędy numeracji i duplikaty sygnatur.
9. Publikuje niezmienną wersję datasetu i reguł.
## Bezpieczne ustawienie silnika importu plansz

**Aktualna prezentacja TASK-0887:** dla profilu `grid_profile_mumie_v1`
panel pokazuje **V3 — sieć neuronowa (Mumie)**, zgodnie z rzeczywistą ścieżką
neural. W pozostałych grach zachowuje V1.1, także dla istniejących siódemek.
V1.0/V1.2 i jawne wymuszenie V1.0 z oryginałów są ukryte w nowych wyborach,
z informacją o wycofaniu do późniejszego usunięcia. Odczyt historycznych
raportów, przypięte wersje i zwykłe ponowienie pozostają. Nie usunięto
silników backendu, danych ani pozostałych sekcji zarządzania grą.
Szczegóły rzeczywistego przepływu: `guides/MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md`.
Proponowane zmiany ekranów: `requirements/APP_V3_FUNCTIONAL_INVENTORY.md`.
Poniższy opis presetów v20/shadow jest historyczny i nie określa aktualnego
pickera V3/V1.1.

Panel importu pokazuje ustawienie przypisane do wybranej gry. Operator może
wybrać stabilny `v20 — geometria i cropy v19` albo pomiarowy silnik 0.10 w
trybie shadow. Zapis korzysta z rewizjonowanego preview, nie zmienia istniejących
jobów i czyści nieaktualny raport importu. Picker jest widoczny przed wyborem
folderu i gotowego stagingu, a upload pozostaje zablokowany do czasu odczytania
polityki gry. Zmiana silnika dla aktywnego stagingu automatycznie odtwarza jego
raport bez ponownego przesyłania JPEG-ów.

Dla obu bezpiecznych presetów Admin wymaga preflightu geometrii przed
odblokowaniem startu, ale nie uruchamia go podczas uploadu ani otwierania
raportu. Te akcje wyłącznie pokazują raport i wymagania; dopiero jawne
`Przygotuj geometrię stron` tworzy albo przywraca idempotentny job. W nowej grze brak profilu nie jest błędem
technicznym: panel pokazuje źródła do korekty i instruuje operatora, aby
poprawił jedną reprezentatywną stronę. Zapis uruchamia następny preflight z tą
stroną jako kotwicą; tylko źródła z kompletną geometrią mogą zostać
zaimportowane.

Ponowne otwarcie raportu odzyskuje najnowszy job z poprawnym, znanym snapshotem
wybranego wariantu. Ukończony manifest nadal odblokowuje import po późniejszej
zmianie profilu uczenia wynikającej z korekt innych stagingów. Przycisk
odświeżenia jest jawną prośbą o nowy snapshot; sam odczyt nie tworzy duplikatu.

Przed startem Admin pokazuje, czy źródłem geometrii jest dokładny manifest czy
blokada, skróconą checksumę i identyfikator preflightu, pokrycie źródeł,
fingerprint profilu strony, wersję silnika komórek oraz stan testu ochronnego.
Dla dużego importu wynik ma początkowo jawny stan „oczekuje”, ponieważ jest
liczony przez worker po bezpiecznym ingestowaniu oryginałów, ale przed
materializacją domenową.

Historia joba pokazuje zaliczony albo zablokowany raport z osobnymi
skutecznościami 3×3 i 3×5. Launcher Reviewera nie sumuje tych domen: osobno
wyświetla geometrię plansz ze stron 3×3 oraz kolejkę „Niepełne siatki symboli
3×5 do ręcznej korekty”.
# Wyjątki bramki geometrii przed importem

Zablokowany duży import udostępnia kolejkę dokładnych plansz z raportu v2.
Admin może pobrać wyłącznie zdjęcie należące do tej kolejki; API przy odczycie
ponownie weryfikuje rozmiar i SHA-256 względem niezmiennego stagingu.

Operator wybiera dla jednego lub kilku slotów tego samego zdjęcia korektę
pełną, planszę częściową albo odrzucenie. Częściowość nie jest sugerowana
automatycznie. API zwraca bieżące rewizje i liczbę nierozliczonych plansz, a
akcja zamknięcia manifestu pozostaje niedostępna logicznie, dopóki licznik nie
wynosi zero.
# Pochodzenie geometrii w korekcie strony

Ekran korekty musi jawnie rozróżniać wykrytą geometrię, ręczny zapis i roboczy
szablon. Przy braku wyniku automatu i braku `automaticPageProposal` pokazuje
„Nie wykryto geometrii — ustaw plansze ręcznie”; domyślne prostokąty są
wyłącznie pomocą edycyjną. Krótki powód jest widoczny bez rozwijania, a
dostępne pomiary zapisanej próby znajdują się w szczegółach. Historyczny
manifest bez diagnostyki pokazuje informację o jej braku i nadal pozwala
zapisać ręczne 36 narożników.

Gdy manifest ma `automaticPageProposal` (D-439, TASK-0633), roboczy szablon
startuje wypełniony tą propozycją zamiast pustym prostokątem 8% od krawędzi —
komunikat zmienia się na „Wstępna geometria z automatycznej propozycji —
sprawdź wszystkie plansze przed zapisem”, z listą plansz „poza kadrem” (numery
1–9) i, jeśli niepusta, „do sprawdzenia”. Plansza, której propozycja wychodzi
poza zdjęcie, dostaje automatycznie zaznaczone „Niepełna plansza”
(`pending_partial`); operator odznacza to przed zapisem, jeśli po korekcie
mieści się w kadrze. Kolejność pierwszeństwa źródeł startowej geometrii: szkic
`localStorage` → istniejący ręczny override lub wynik automatu →
`automaticPageProposal` → pusty szablon. Wariant V1.2
(`contrast_frame_grid_v1_2`) nigdy nie dostaje propozycji — używa własnej
logiki ramek pochodnych. Przycisk „Reset” przywraca dokładnie ten sam stan
startowy, w tym flagę „Niepełna plansza” pochodzącą z propozycji, a nie pusty
szablon.

Wybraną planszę można przesunąć jako całość (D-439, TASK-0634): drugie
kliknięcie w już wybraną planszę (pierwsze tylko ją wybiera) uruchamia
przeciąganie, które przesuwa wszystkie 4 narożniki o ten sam wektor —
kształt planszy się nie zmienia, w przeciwieństwie do przeciągania
pojedynczego narożnika. Wektor przesunięcia jest ograniczany tak, żeby
żaden narożnik nie wyszedł poza dozwolony obszar: granice zdjęcia dla
zwykłej planszy, ten sam rozszerzony zakres ±~7%, co przeciąganie
narożnika, gdy którakolwiek plansza na stronie jest oznaczona „Niepełna”.
Przeciąganie pojedynczego narożnika (uchwyty renderowane nad planszą)
działa bez zmian.
