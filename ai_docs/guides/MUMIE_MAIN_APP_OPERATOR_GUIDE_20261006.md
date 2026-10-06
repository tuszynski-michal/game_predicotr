---
title: Mumie — upload, korekta i wspólne uczenie
status: live_pilot
last_updated: 2026-10-06
---

# Mumie w głównej aplikacji

Pilot TASK-0879–0884 działa w głównym checkoutcie na gałęzi
v1.1-vision-lab-hybrid-geometry. Admin jest na porcie3000, Reviewer na3001.
Port3102 pozostaje laboratorium. Model Mumii jest aktywny.

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
2. Wybierz grupę symbolu albo nierozpoznane cropy. Zaznacz poprawne wycinki
   zbiorczo i zatwierdź je. Błędnym przypisz właściwy symbol.
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

Zdjęcia kontrolne, także ponownie zapisane pliki z tymi samymi pikselami,
pozostają poza treningiem. Nowe iteracje gwarantują podział po całych
zdjęciach. System nie ma jeszcze trwałego identyfikatora nagrania dla nowych
uploadów; raport pokazuje tę granicę.

Uczenie sieci cięcia ma osobny eksport zatwierdzonych 24 punktów i snapshot.
Istniejąca akcja **Ulepsz cięcie siatki** buduje profil kalibracji; nie jest
treningiem nowej wersji sieci neural_grid_v1. Iterację tej sieci uruchamia
wykonawca na osobnym snapshotcie i przedstawia osobny raport.

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
