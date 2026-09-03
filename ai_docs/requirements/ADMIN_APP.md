---
title: Admin application requirements
status: accepted
last_updated: 2026-08-15
---

# Wymagania modułu administracyjnego

Ten dokument pozostaje źródłem obowiązującego zachowania wdrożonego do `0.1`.
Planowana reorganizacja nawigacji i workflow dla `0.2` znajduje się w
`ADMIN_APP_V0_2.md`; zaakceptowane decyzje tego planu nie zmieniają wdrożonego
kontraktu `0.1` przed rozpoczęciem zadań `0.2`.

## Forma aplikacji

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
panel zapisuje metadane ścieżki, a nie binarną zawartość pliku. Dla istniejącej
grafiki edycja symbolu udostępnia read-only podgląd w modalu. Podgląd pobiera
checksum-bound asset z Admin API, pokazuje stan ładowania i kontrolowany błąd;
nie zmienia wskazania grafiki ani pozostałych danych symbolu.

Joker nie ma własnej wypłaty. Jeżeli w przyszłości gra będzie miała więcej niż
jeden rodzaj symbolu specjalnego, jego semantyka wymaga osobnej reguły zamiast
ukrytego traktowania wszystkich symboli specjalnych identycznie.

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
- edytować, archiwizować lub usunąć nieopublikowany wzór.

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
Podniesienie minimum archiwizuje payouty poniżej nowego progu. Po użyciu
symbolu w wersji reguł nie można zmienić jego roli zwykły/joker w katalogu,
ponieważ unieważniłoby to wersjonowane minimum i wypłaty.

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
- joker, nieaktywny symbol oraz długość poza zakresem nie mają aktywnego
  payoutu.

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

Zapisane `?` w znalezionej planszy nie daje punktu, nie zwiększa liczby
dokładnych dopasowań ani sprzeczności. Znany symbol zapytania zestawiony z `?`
jest raportowany jako brak danych. Wyniki zachowują deterministyczną kolejność:
score, liczba exact, ważone alternatywy, mniej sprzeczności, zatwierdzony status,
`sequence_number` i UUID.

### Walidacja cięcia siatki 0.9

Docelowy workflow geometrii korzysta z jednej kolejki całej gry z widokami
`Do walidacji`, `Do poprawy` i `Wszystkie` oraz opcjonalnym zawężeniem do
importu. Każdy logiczny numer planszy występuje najwyżej raz: źródłem pozycji
jest bieżący właściciel szybkiej projekcji wyszukiwania, a nie suma stagingów.

Lista jest pobierana bounded keysetem. Szybkie zatwierdzenie zawsze dotyczy
dokładnej rewizji decyzji i geometrii, checksummy oraz wymiarów źródła i
przypiętej topologii. Zmiana któregokolwiek elementu po załadowaniu ekranu
powoduje czytelny konflikt i wymaga odświeżenia pozycji. Źródło obrazu jest
checksum-bound i nie ujawnia ścieżki systemowej.

Preview oraz zapis korekty otrzymują cztery narożniki w przestrzeni obrazu
źródłowego i topologię gry. Liczba zwracanych cropów wynika z `rows × columns`,
nie ze stałej 15. Autor decyzji pochodzi z lokalnego, uwierzytelnionego
kontekstu Admin API.

Lokalny Reviewer otwiera domyślnie ekran `Zatwierdzanie cięcia siatki` z jednym
oryginalnym obrazem i canvasowym overlayem. Filtry mają kolejność `Do
walidacji`, `Do poprawy`, `Wszystkie`. `Enter`, `F` i główny przycisk
zatwierdzają bieżącą geometrię i przechodzą do następnego rekordu. Korekta
pozwala wskazać kolejno LT, PT, PD i LD, przeciągać narożniki lub całą siatkę,
cofać punkt, resetować szkic oraz obejrzeć dynamiczne `rows × columns` cropy
przed atomowym zapisem i zatwierdzeniem rewizji. Ekran nie pozwala edytować
symboli i nie zapisuje JPEG-a z overlayem.

Nowy workflow jest obowiązującym lokalnym widokiem. Zdalna sesja Reviewera
zachowuje wąsko ograniczoną ścieżkę operacyjną i nie otrzymuje game-wide
endpointów administracyjnych. Lokalny Reviewer nie ma już przełącznika powrotu
do poprzedniego widoku; rollback polega na wyłączeniu nowych mutacji i
zachowaniu danych 0.9, nie na uruchomieniu starego lokalnego UI.

### Katalog symboli i grafiki referencyjne

Katalog symboli jest definiowany ręcznie dla każdej gry. Formularz utworzenia
wymaga wyłącznie nazwy i oznaczenia Jokera; Admin API pod blokadą gry nadaje
stabilny `code`, kolejny `mobileCode` i `displayOrder`. Edycja nazwy nie może
zmienić żadnego z tych identyfikatorów.

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

`Weryfikacja symboli` jest osobnym, wyłącznie lokalnym obszarem głównej
nawigacji Admina. Operator wybiera grę oraz zakres symbolu: wszystkie symbole,
jeden aktywny symbol albo nierozpoznane `?`, a także radio `Stan weryfikacji`:
`Wszystkie`, `Oczekujące` albo `Zatwierdzone`. Symbol docelowy akcji
`Zmień symbol` pozostaje niezależnym wyborem. Nie istnieje status cropa
`odrzucone`: `Zła siatka` i `Nieczytelny symbol` są odrębnymi problemami
jakościowymi obsługiwanymi przez ich dedykowane kolejki.
Widok korzysta z tego samego pojedynczego właściciela logicznego numeru co
operacyjne review: kanoniczna plansza `accepted/corrected` ma pierwszeństwo,
a bez niej widoczna jest wyłącznie najnowsza oczekująca plansza. Cropy ze
starszych, pokrywających się stagingów oznaczonych `superseded` nie są
prezentowane ani dostępne do masowych decyzji.
Gra oraz zakres symbolu są domyślnie niewybrane. Wejście do zakładki nie pobiera
strony cropów. Pierwsza strona o stałym rozmiarze 500 metadanych jest pobierana
automatycznie dopiero po wskazaniu kombinacji obu pól. Zmiana gry ponownie
czyści wybór symbolu; osobne akcje `Zatwierdź wybór` i `Zmień wybór` nie
występują. Globalne liczniki nie należą
do krytycznej ścieżki listy: są pobierane osobno dla gry i rewizji
katalogu. Wolny albo niedostępny licznik nie blokuje oglądania ani decyzji, a
spóźniona odpowiedź poprzedniej gry jest odrzucana. Zmiana ustawionej gry albo
symbolu czyści strony i wirtualny viewport. Jeśli istnieje jawne zaznaczenie,
operator najpierw potwierdza jego wyczyszczenie. Widok zachowuje jawne przyciski
poprzedniej/następnej strony, prefetchuje wyłącznie jedną kolejną stronę i trzyma
w pamięci najwyżej trzy najbliższe strony metadanych. Nie utrzymuje obrazów dla
całej strony: DOM zawiera tylko karty viewportu i małego overscanu. Admin
dzieli potwierdzoną stronę deterministycznie na atlasy po maksymalnie 100
kart, wspólne dla `legacy_file` i `virtual_source`. Dla 500 cropów powstaje
najwyżej pięć requestów obrazu: najpierw grupa zawierająca widoczny viewport,
potem pozostałe grupy w kolejności. Klucz atlasu obejmuje rewizje, checksumy,
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
więc operator może zbudować jeden job z kilku stron po 500 cropów. Czyści je
wyłącznie jawna akcja, zmiana filtra albo skuteczne przekazanie operacji.
Zmiana filtra przy zaznaczeniu wymaga potwierdzenia i czyści selection. Wysłana
operacja masowa przechodzi do tła: jej dokładne widoczne targety pozostają
wyszarzone ze spinnerem, ale operator może przejść na inną stronę i uruchomić
kolejną niezależną operację. Zablokowane pozostają wyłącznie targety już wysłane
oraz krótki foreground start/preview bieżącej decyzji.

Sticky toolbar pokazuje liczbę wybranych cropów oraz akcje `Zatwierdź`, `Zmień
symbol`, checkbox `Niewyraźny` i jednoliniowe akcje `Nieczytelny / Zła siatka`.
Checkbox `Niewyraźny` modyfikuje zatwierdzenie oraz zmianę symbolu: decyzja
atomowo zachowuje albo przypisuje wskazany symbol jako zatwierdzony, ale
wyklucza bieżący crop z kohort treningowych. Modyfikator jest resetowany po
zmianie gry albo zakresu symbolu. `Zła siatka` kieruje pole do kolejki korekty
geometrii, natomiast `Nieczytelny` pozostawia je poza kolejką geometrii i poza
kohortą treningową. Dwa ostatnie stany są w game-wide widoku
listy prezentowane jako `Nierozpoznany (?)`, a ich oryginalne przypisanie
pozostaje w danych i audycie. Karta pokazuje zwięzły
badge `Niewyraźny`, `Zła siatka · ?`, `Nieczytelny · ?`, `Nowy crop` albo `?`, gdy taki stan
dotyczy bieżących pikseli. W widoku `Zatwierdzone` badge zatwierdzonego cropa,
który nie spełnia aktualnych warunków kohorty treningowej, zawiera również
tekst `Poza uczeniem` oraz przyczynę: problem jakości albo brak aktualnie
zatwierdzonego, checksum-bound cropa. Podsumowanie pokazuje aktualną i całkowitą liczbę
stron oraz jednoznaczny zakres pozycji. Każda akcja najpierw pokazuje niezmienny preview
liczby cropów i plansz, a potem uruchamia idempotentną operację masową.
`Zatwierdź` działa wyłącznie dla jawnie zaznaczonych cropów; walidacja backendu
nadal odrzuca próbę zatwierdzenia nierozpoznanego przypisania.
Status operacji raportuje osobno wykonane, konfliktowe i błędne targety;
polling każdej operacji nie wysyła nakładających się requestów. Pełny sukces
usuwa jej targety z aktualnie wyświetlanej strony bez ponownego zapytania i bez
uzupełniania strony kolejnymi rekordami. Konflikt lub częściowy błąd pozostawia
targety widoczne, ponieważ zbiorcza odpowiedź nie wskazuje bezpiecznie ich
indywidualnego wyniku. Ponowna nawigacja naturalnie pobiera aktualny keyset.
Jedna jawnie zaznaczona karta jest wyjątkiem od workflow masowego: Admin wysyła
bezpośrednią, checksum-bound decyzję i nie tworzy joba. Po sukcesie czyści
zaznaczenie, pokazuje krótki komunikat i usuwa kartę bez uzupełniania strony;
po konflikcie przywraca kartę oraz pokazuje błąd. Dwa lub więcej jawnych cropów
z bieżącej strony nadal korzysta z preview i trwałego joba. Toast nie zasłania
toolbara: jest stały około 50 px od lewego i dolnego brzegu viewportu.

### Weryfikacja symbolu na planszy

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

Symbol można fizycznie usunąć wyłącznie, gdy nie ma zależności w regułach,
planszach, predykcjach, kohortach, iteracjach ani aktywacjach modeli. Modal
wyświetla dokładne liczniki blokujących zależności. Panel nie oferuje
automatycznego bootstrapu katalogu ani archiwizowania symbolu.

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
- działać jako osobna aplikacja przeglądarkowa `Reviewer`, a nie sekcja
  właściwego panelu administracyjnego,
- pokazywać gotowy staging plansz bieżącej gry jako etap poprzedzający import;
  staging nie jest elementem dropdownu ani pracą Reviewera, dopóki jawny job
  importu nie utworzy kolejki plansz,
- dla aktywnego gotowego stagingu z raportem pokazywać przypięty silnik
  `v20 — geometria i cropy v19`; każdy nowy import używa go bez dodatkowego
  potwierdzenia, a v18 jest dostępny wyłącznie jako etykieta i artefakt
  historycznych jobów,
- start przekazuje `boardCellProcessingMode=verified_v19` w checksum-bound
  komendzie i nie może prezentować sukcesu, jeżeli zwrócony job ma inny
  niezmienny snapshot; nieudana geometria nie wraca do v18, lecz tworzy trwałe
  odroczenie do końcowej korekty,
- mieć własny proces i adres; panel Admin wybiera grę oraz gotowy import, pokazuje
  dla niego liczniki wszystkich, oczekujących i zakończonych plansz, a przycisk
  `Utwórz link online` uruchamia brakujący produkcyjny Reviewer,
  kontrolowany tunel HTTPS i dopiero potem generuje ograniczoną sesję, link
  oraz unikalny kod wejścia,
- identyfikować import w dropdownie krótką datą i godziną, nazwą katalogu oraz
  krótkim statusem; techniczne ID wybranego joba jest widoczne osobno, a długa
  etykieta nie poszerza bez ograniczenia kontrolki,
- mieć osobny przycisk `Otwórz lokalnie`, który uruchamia produkcyjny Reviewer
  wyłącznie na `127.0.0.1`, otwiera wybraną grę oraz import i nie uruchamia
  tunelu, nie tworzy sesji ani nie wymaga kodu; ten tryb działa wyłącznie dla
  strony otwartej przez loopback; przygotowane synchronicznie okno ma otrzymać
  zwrócony URL przed pomocniczym odświeżeniem overview, a błąd nawigacji ma
  pozostawić właścicielowi widoczny link ręczny zamiast pustej karty
  `about:blank`,
- pokazywać jawny stan `online` / `wyłączone` / `problem` i udostępniać przycisk
  `Zatrzymaj udostępnianie`, który unieważnia wyłącznie sesję i assignment
  wybranego importu; współdzielony publiczny tunel pozostaje dostępny dla innych
  aktywnych prac online i kończy się dopiero po ostatniej, a decyzje zapisane
  wcześniej w audycie pozostają w bazie,
- dopuszczać najwyżej trzy różne aktywne importy online; tryb lokalny nie zajmuje
  tego limitu, a próba czwartego linku kończy się kontrolowanym komunikatem bez
  utworzenia sesji,
- pokazywać listę aktywnych prac wszystkich gotowych importów wybranej gry i
  pozwalać zakończyć dokładnie wskazane przypisanie; lista po odświeżeniu nie
  ujawnia kodu wejścia, bearer tokenu, fencing tokenu ani osobnego pola
  identyfikatora sesji; publiczny URL może zawierać jego opaque identyfikator,
- ujawniać kod wejścia wyłącznie bezpośrednio po utworzeniu nowej pracy online;
  idempotentne ponowienie zwraca istniejące przypisanie bez ponownego pokazania
  kodu,
- nigdy nie publikować serwera developerskiego Reviewera ani pełnego Admina;
  wykrycie procesu developerskiego na porcie Reviewera blokuje start z
  czytelnym komunikatem,
- przed pokazaniem danych przez publiczny origin wymagać poprawnego kodu.
  Lokalna wersja pozostaje dostępna wyłącznie przez loopback i korzysta z
  uprawnień lokalnego właściciela bez dodatkowego kodu,

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
2. Dodaje symbole `S1`–`S12` i oznacza joker.
3. Tworzy trzy poziome paylines przez modal siatki.
4. Nie może wybrać dwóch komórek w jednej kolumnie ani zapisać niepełnego wzorca.
5. Nie może zapisać duplikatu `row_path`.
6. Pozostawia dla większości symboli domyślne minimum 3, dla co najmniej jednego
   symbolu ustawia minimum 2 i uzupełnia wszystkie wymagane wartości kredytów.
7. Generuje lub importuje 1000 layoutów.
8. Widzi luki, błędy numeracji i duplikaty sygnatur.
9. Publikuje niezmienną wersję datasetu i reguł.
## Bezpieczne ustawienie silnika importu plansz

Panel importu pokazuje ustawienie przypisane do wybranej gry. Operator może
wybrać stabilny `v20 — geometria i cropy v19` albo pomiarowy silnik 0.10 w
trybie shadow. Zapis korzysta z rewizjonowanego preview, nie zmienia istniejących
jobów i czyści nieaktualny raport importu. Picker jest widoczny przed wyborem
folderu i gotowego stagingu, a upload pozostaje zablokowany do czasu odczytania
polityki gry. Zmiana silnika dla aktywnego stagingu automatycznie odtwarza jego
raport bez ponownego przesyłania JPEG-ów.

Dla obu bezpiecznych presetów Admin przygotowuje preflight geometrii przed
odblokowaniem startu. W nowej grze brak profilu nie jest błędem
technicznym: panel pokazuje źródła do korekty i instruuje operatora, aby
poprawił jedną reprezentatywną stronę. Zapis uruchamia następny preflight z tą
stroną jako kotwicą; tylko źródła z kompletną geometrią mogą zostać
zaimportowane.
