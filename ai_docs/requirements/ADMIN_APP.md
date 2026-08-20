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

### Minimalistyczne stanowisko zatwierdzania

Operacyjne review dużego importu używa `image_review_items`, a nie ograniczonego
batcha active-learning. Ekran jest zoptymalizowany pod szybkie sprawdzanie
pełnych plansz i ma:

- działać jako osobna aplikacja przeglądarkowa `Reviewer`, a nie sekcja
  właściwego panelu administracyjnego,
- mieć własny proces i adres; panel Admin wybiera grę oraz import, a przycisk
  `Utwórz link i wystaw online` uruchamia brakujący produkcyjny Reviewer,
  kontrolowany tunel HTTPS i dopiero potem generuje ograniczoną sesję, link
  oraz unikalny kod wejścia,
- mieć osobny przycisk `Otwórz lokalnie`, który uruchamia produkcyjny Reviewer
  wyłącznie na `127.0.0.1`, otwiera wybraną grę oraz import i nie uruchamia
  tunelu, nie tworzy sesji ani nie wymaga kodu; ten tryb działa wyłącznie dla
  strony otwartej przez loopback,
- pokazywać jawny stan `online` / `wyłączone` / `problem` i udostępniać przycisk
  `Zatrzymaj udostępnianie`, który unieważnia bieżącą sesję i zamyka publiczny
  tunel; decyzje zapisane wcześniej w audycie pozostają w bazie,
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

Przy pierwszym wejściu albo pełnym odświeżeniu aplikacja ustawia bieżącą
pozycję na pierwszej planszy `pending`. Jeżeli nie istnieje żadna plansza
`pending`, zaczyna od pierwszej planszy importu. Nie oznacza to pobrania pełnej
kolejki do klienta: każda bieżąca plansza i sąsiad są nadal pobierane bounded,
z limitem jednej planszy.

Symbole są mapowane według stabilnej kolejności katalogu gry: klawisze
`1`–`9`, `0` dla dziesiątego, a następne pozycje kolejno do klawiszy w
wierszach `QWERTY`. Pojedyncze `Enter` albo kliknięcie `Zatwierdź` wykonuje
zapis bez dodatkowego modala, a po poprawnym zapisie przesuwa bieżącą pozycję
do następnej planszy w pełnej kolejności. Skróty nie działają podczas pisania
w polu, w innym dialogu ani podczas trwającego zapisu. Idempotency key i
blokada trwającego żądania nadal chronią przed podwójnym zdarzeniem.

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
