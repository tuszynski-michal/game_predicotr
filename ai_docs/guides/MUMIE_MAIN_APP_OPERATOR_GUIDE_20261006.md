---
title: Mumie — upload, korekta i wspólne uczenie
status: live_pilot
last_updated: 2026-10-07
---

# Mumie w głównej aplikacji

Pilot TASK-0879–0884 działa w głównym checkoutcie na gałęzi
v1.1-vision-lab-hybrid-geometry. Admin jest na porcie3000, Reviewer na3001.
Port3102 pozostaje laboratorium. Model Mumii jest aktywny.

## Nowy folder — krok po kroku

1. Otwórz [Admin na 3000](http://127.0.0.1:3000), wybierz
   **Zarządzanie grami → Szkice → Mumie → Import plansz**.
   Mumie są obecnie szkicem; nie zobaczysz ich w filtrze samych aktywnych gier.
2. Panel pokazuje **V3 — sieć neuronowa (Mumie)**. Nie wybieraj starego
   wariantu geometrii. V1.1 zostaje dla siódemek; V1.0/V1.2 są wycofane
   z nowych wyborów. Wgrany folder nie zmienia silnika historycznego importu.
3. Kliknij **Wybierz folder**. Wskaż katalog z JPEG-ami `seq_*`, najlepiej
   kolejne około **500 zdjęć**. To zdjęcia źródłowe, nie 500 pojedynczych
   plansz; zdjęcie może zawierać kilka plansz. Aplikacja przesyła cały folder.
   Jeśli folder ma więcej zdjęć, przygotuj mniejszy katalog partii.
4. Folder znajdziesz w sekcji **Przesłane foldery**. Po przesłaniu otwiera
   się raport; dla wcześniej przesłanego folderu wybierz **Pokaż raport**.
   Jeśli raport się nie przygotuje, folder pozostaje na liście: wybierz
   **Odśwież raport**. Błąd pobrania listy ponów przez **Odśwież status**;
   zdjęć nie trzeba przesyłać drugi raz. W V3 nie ma klasycznego wyboru
   „Dopasowanie geometrii zdjęcia”. Sprawdź grę, liczbę plików i zakresy. Kliknij
   **Przygotuj geometrię stron**. To preflight sieci: wykrywa plansze,
   ich podział i przypisanie do numerów. Sam raport/preflight nie tworzy
   jeszcze komórek symboli w grze.
5. Poczekaj na ukończenie; **Odśwież preflight geometrii** odczytuje zapisany
   stan. Jeśli zadanie się nie powiedzie, użyj **Ponów preflight**.
   Po gotowym manifeście kliknij **Rozpocznij import Mumii**.
   **Podgląd propozycji sieci i numeracji zdjęć** nie jest listą obowiązkowych
   poprawek. Licznik obejmuje propozycje bez ręcznej akceptacji, także poprawne
   pełne siatki. Nie musisz otwierać ani zatwierdzać każdej z nich.
6. Import zachowuje numery plansz, przygotowuje pełne siatki 3×5, wycinki
   15 komórek i propozycje symboli z aktywnego modelu. Te etapy wykonuje
   worker; nie musisz osobno uruchamiać każdego cięcia ani zatwierdzać
   geometrii każdej poprawnej planszy.
7. Brakujące/niepełne siatki poprawiaj w **Korekcie cięcia siatki**.
   Niejednoznaczne przypisanie numerów albo ucięty zakres poprawiaj w
   **Podglądzie propozycji sieci i numeracji zdjęć** w raporcie folderu. Właściwe sloty
   nie zmieniają swoich numerów przez brak sąsiada. Poprawne pełne cropy
   trafiają dalej niezależnie od korekty pozostałych.
8. Otwórz **Weryfikacja symboli**, wybierz **Mumie**, ustaw do **2000**
   cropów na stronę. Zatwierdzaj wiele poprawnych cropów naraz, a błędnym
   przypisuj właściwy symbol. **Zła siatka** zgłasza problem cięcia.

**Import** uruchamia rozpoznawanie aktywnym modelem. **Trening** jest osobną
akcją z zebranych zatwierdzeń; nowy folder nie wymaga uczenia od początku.
Status importu `waiting_for_review` może oznaczać oczekującą zbiorczą
weryfikację symboli, a nie obowiązek ręcznego zatwierdzania każdej siatki.

**Diagnostykę siatek zdjęć** znajdziesz w **Korekcie cięcia siatki**, pod
przyciskiem otwarcia Reviewera. Wybierz całą grę albo konkretny import,
sprawdź zdjęcia i użyj **Popraw siatki w Reviewerze**. **Odśwież kolejkę**
odczytuje bieżący stan. Import zawiera nadal raport brakujących numerów.
Raport geometrii całego zdjęcia zachowuje historyczne reguły: przy V3
„Siatka niepotwierdzona” nie oznacza, że wszystkie cropy są niedostępne.
Dostępność sprawdzaj w **Weryfikacji symboli**.

Preflight folderu **1 - 23175 cut** z2575 zdjęć wykonała sieć Run3, eksport
**iteration03-f896da7196431be2**. Wszystkie23175 przypisanych siatek spełniają
warunki obecnej polityki automatycznego cięcia. Dawny licznik ręcznej korekty
2575 wynikał z oznaczenia niekalibrowanych propozycji, nie z wykrycia2575
błędnych zdjęć. Jest to kwalifikacja struktury, nie pomiar dokładności względem
ręcznej prawdy. Import przygotuje cropy i symbole do oceny zbiorczej.

## Pierwsza partia

Pierwsze100 zdjęć z trzech nagrań zostało już wgrane. Nie wgrywaj tej partii
ponownie. Zachowano wszystkie oryginały;99 zdjęć daje891 propozycji plansz.
TASK-0886 odzyskał tę partię istniejącym ponownym przetwarzaniem:
891 bieżących plansz, 13 365 cropów i gotowe liczniki weryfikacji.
Pełne, jednoznacznie przypisane siatki są cięte automatycznie.
Nie musisz zatwierdzać każdej planszy, żeby rozpocząć ocenę symboli.

1. Otwórz [główny Admin](http://127.0.0.1:3000), **Weryfikacja symboli**,
   i wybierz grę **Mumie**.
   Ustaw **Na stronę: 2000**, jeśli potrzebujesz większego wyboru.
2. Wybierz grupę symbolu albo nierozpoznane cropy. Zaznacz wycinki i wybierz
   **Symbol do zatwierdzenia**, następnie **Zapisz i zatwierdź**. Ten sam
   symbol zatwierdzi poprawne wycinki; inny poprawi je i zatwierdzi. Nie trzeba
   tymczasowo zmieniać poprawnej klasy. Skróty `1`–`9` wybierają symbol,
   a `Enter` wykonuje ten sam zapis. Po kliknięciu wybór symbolu jest czyszczony;
   przed kolejnym zapisem wybierz go ponownie. Większa grupa zachowuje podgląd
   operacji z wybranym symbolem, także po wyczyszczeniu selektora.
3. Crop źle wycięty oznacz jako **Zła siatka**. Tylko takie zgłoszenia oraz
   brakujące lub ucięte sloty wymagają **Korekty cięcia siatki**.
4. Zapisane decyzje pozostają widoczne na stronie do odświeżenia. Kolejna
   partia i trening nie wymagają ponownego oceniania tych samych cropów.

Przygotowanie weryfikacji jest trwałym zadaniem. Stan bez aktywnego zadania
jest automatycznie wznawiany raz po wejściu do panelu; dostępny jest też
przycisk **Wznów przygotowanie**. Błąd nie jest pokazywany jako wieczny postęp.

Pierwszy test strukturalny wykrył897 propozycji wobec900 pozycji z nazw.
Właściwy import zachowuje891 aktywnych slotów dla99 jednoznacznych źródeł.
Plik seq_499996-500004.jpg pozostaje w korekcie źródła, ponieważ nominalny
zakres wychodzi poza500000. Wymaga ręcznego przypisania detekcji i potwierdzenia
końcowego zakresu. Nie utworzono dla niego fikcyjnej planszy ani targetu.

## Jak poprawiać

- **Dobre cięcie, zły symbol:** kliknij widoczną komórkę i wybierz symbol albo
  użyj numeru pokazanego przy katalogu. Nie zmieniaj siatki i nie ponawiaj
  podglądu, jeśli crop jest dobry.
- **Złe cięcie:** popraw węzły podziału, sprawdź podgląd, zapisz i zatwierdź.
  Korekta zachowuje również punkty wewnętrzne, nie tylko cztery rogi.
- **Brak wykrytej planszy:** przypisz widoczne detekcje do właściwych pozycji.
  Brakująca pozycja pozostaje brakująca; następne numery nie przesuwają się.
- **Ucięte zdjęcie:** zaznaczaj tylko to, co rzeczywiście widać.
  Częściowo widoczną komórkę można ocenić. Pole poza zdjęciem nie dostaje
  fikcyjnego obrazka treningowego.
- **Nieczytelny symbol:** oznacz go jako nieczytelny.
  Złota ramka nie zmienia bazowej etykiety symbolu.

Skróty aktualnego katalogu:1=10,2=J,3=Q,4=K,5=A,6=Sarkofag,7=Ra,
8=Faraon,9=Sfinks,0=Mumia. Zapisz po ocenie planszy. Samo kliknięcie symbolu
zmienia szkic; szkic wraca po odświeżeniu, ale nie jest zatwierdzoną etykietą.

Zapis wskazanego symbolu na zatwierdzanej siatce sieci działa od razu dla
tej planszy. Nie trzeba wcześniej poprawiać wszystkich plansz tego zdjęcia.
Pełne sąsiednie sloty są dostępne w zbiorczej weryfikacji bez akceptacji
geometrii; brakujące lub częściowe pozostają w korekcie. TASK-0885 usuwa
błąd braku cropa zgłoszony przy polu4 planszy1405.

Po ponownym cięciu zatwierdź nowe piksele symboli. Poprzednie zatwierdzenie
dotyczy poprzedniego cropa. Zapis samego symbolu zachowuje poprawną geometrię.

## Uczenie z wielu uploadów

1. Zbieraj zatwierdzone poprawki z różnych zdjęć. Nie trzeba trenować po każdym
   uploadzie ani ponownie oznaczać tych samych symboli dla nowego folderu.
2. W obszarze jakości modelu uruchom **Ulepsz rozpoznawanie**. System pokaże
   wspólną pulę kwalifikujących przykładów i brakujące pokrycie symboli.
3. Jeśli podział nie ma wystarczającego pokrycia klas, kontynuuj korektę
   kolejnych zdjęć. Upload i korekta nadal działają.
4. Trening zamraża wybraną pulę i tworzy nowego kandydata. Ocena i aktywacja
   kolejnej wersji są osobnymi akcjami.

Do panelu uczenia wejdziesz przez **Zarządzanie grami → Mumie → Jakość
rozpoznawania**. Uruchamiaj **Ulepsz rozpoznawanie** po zebraniu różnorodnych
poprawek z jednej lub kilku partii, gdy preview nie zgłasza braków klas
w niezależnych częściach podziału. Nie ma wymogu „30 od nowa” dla każdego
folderu. Wybieraj trudne i różne przykłady: ucięcie, perspektywa, jasność,
złote ramki i pomyłki klas; same niemal identyczne cropy dają mniej informacji.
Sprawdź raport kandydata i regresje przed **Aktywuj ostatniego kandydata**.
Nowy model obowiązuje kolejne importy. Dla wcześniej oczekujących symboli
użyj **Przelicz oczekujące plansze**; ręczne decyzje są chronione.

Wgranie ani zgłoszenie błędu nie aktualizuje wag sieci natychmiast. Poprawka
zapisuje przykład do następnego treningu. Zatwierdzaj to, co potrafisz ocenić;
predykcja modelu sama nie staje się prawdziwą etykietą do uczenia.

Zdjęcia kontrolne, także ponownie zapisane pliki z tymi samymi pikselami,
pozostają poza treningiem. Nowe iteracje gwarantują podział po całych
zdjęciach. System nie ma jeszcze trwałego identyfikatora nagrania dla nowych
uploadów; raport pokazuje tę granicę.

Uczenie sieci cięcia ma osobny eksport zatwierdzonych 24 punktów i snapshot.
Istniejąca akcja **Ulepsz cięcie siatki** buduje profil kalibracji; nie jest
treningiem nowej wersji sieci neural_grid_v1. Iterację tej sieci uruchamia
wykonawca na osobnym snapshotcie i przedstawia osobny raport.

Użytkownik wskazał osobną zakładkę **Laboratorium** dla wszystkich gier.
Ma połączyć trening obu rodzajów modeli z korektami w głównej bazie i
rejestrować tam wersje kandydujące po treningu. Nie jest jeszcze wdrożona;
szczegóły potrzeb zapisano w APP_V3_FUNCTIONAL_INVENTORY.md, MODEL-09.
Rejestracja wyniku nie oznacza automatycznej aktywacji nowego modelu.

## Zwiększanie partii

Po sprawdzeniu obecnych 100 zdjęć wgraj partię około 500, następnie 2000.
Większa partia służy zbieraniu różnorodnych poprawek i ocenie realnych błędów.
Nie oznacza automatycznego zatwierdzenia wszystkich predykcji.

Nowy folder wybierzesz w **Mumie → Import plansz → Wybierz folder**.
Import obejmuje cały wybrany folder; aplikacja nie obcina go automatycznie
do100 zdjęć. Nie trzeba ponownie instalować modelu ani trenować po uploadzie.

Przy przerwaniu połączenia ponów oczekującą operację albo odśwież stan zadania.
Zapisany receipt i checkpoint pozwalają odtworzyć operację bez tworzenia
duplikatu. Nie zakładaj nowego importu tej samej partii, zanim sprawdzisz
poprzednie zadanie.

## Granice pilota

Model daje podpowiedzi, które mogą być błędne. Odbiór techniczny nie jest
pomiarem poprawności symboli całego nagrania. Super i wybór symbolu na10 gier
pozostają osobnym zadaniem. Nie opublikowano reguł wypłat ani kosztu spinu;
szkic3×5 służy przypięciu wymiarów przy imporcie, bez kalkulacji targetów.
