---
title: Mumie — upload, korekta i wspólne uczenie
status: prepared
last_updated: 2026-10-06
---

# Mumie w głównej aplikacji

Instrukcja dotyczy pilota TASK-0879–0884. Kod jest przygotowany w worktree
grid-engine-v3. Korzystanie z nowych funkcji w głównym Admin wymaga wdrożenia
opisanego w MUMIE_MAIN_APP_DEPLOYMENT_PREVIEW_20261006.md.

## Pierwsza partia

1. Otwórz Admin: http://127.0.0.1:3000 i istniejącą grę Mumie.
2. W imporcie folderu wybierz:
   C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-main-app-pilot-20261006\pilot-upload-100.
   To 100 zdjęć z trzech różnych nagrań. Nazwy i zawartość są zachowane.
   Import obejmuje cały wybrany folder; nie ma automatycznego ograniczenia do 100.
3. Sprawdź proponowane zakresy. Nazwa z pięcioma planszami daje pięć pozycji.
   Nie potwierdzaj zakresu wykraczającego poza koniec gry.
4. Po imporcie otwórz kolejkę korekty siatek w Reviewer.
   Propozycje wymagają oceny, nawet jeśli wyglądają poprawnie.

Pierwszy test plików wykrył 897 poprawnych strukturalnie propozycji wobec 900
pozycji wynikających z nazw. Nie potwierdza to poprawności wszystkich siatek
ani symboli. 99 zdjęć ma uporządkowane propozycje przypisania. Jedno wymaga
ręcznego przypisania pozycji oraz potwierdzenia końcowego zakresu.

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

Przy przerwaniu połączenia ponów oczekującą operację albo odśwież stan zadania.
Zapisany receipt i checkpoint pozwalają odtworzyć operację bez tworzenia
duplikatu. Nie zakładaj nowego importu tej samej partii, zanim sprawdzisz
poprzednie zadanie.
