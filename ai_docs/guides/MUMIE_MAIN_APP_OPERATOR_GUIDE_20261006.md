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
Import czeka na ocenę człowieka, bez błędów przetwarzania. Nie ma jeszcze
zatwierdzonych plansz — propozycje są w kolejce korekty.

1. Otwórz [kolejkę korekty Mumii](http://127.0.0.1:3001/?mode=local&gameId=fea55cc1-ebf4-4cee-b3ab-a520017ed1be&importJobId=f3ff4258-e561-4031-bc04-227c9dbf51b6).
   To kolejka tego importu. Dawny adres z queue=grid-audit otwiera inną listę.
2. W Admin: http://127.0.0.1:3000 wybierz **Szkice → Mumie → Korekta cięcia
   siatki → Otwórz lokalnie**, aby dojść do tej samej kolejki.
3. Sprawdź kilka plansz. Wycinki i podpowiedzi pojawiają się automatycznie.
   Propozycje wymagają oceny, nawet jeśli wyglądają poprawnie.
4. Zatwierdź wyłącznie zgodną siatkę oraz symbole, które rzeczywiście oceniłeś.

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
Pozostałe propozycje nadal wymagają osobnej oceny. Poprawka TASK-0885 usuwa
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

Po sprawdzeniu przepływu 100 zdjęć przygotujemy 500, następnie 2000.
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
