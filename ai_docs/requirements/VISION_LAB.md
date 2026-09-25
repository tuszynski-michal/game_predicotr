---
title: Laboratorium geometrii i symboli — wymagania
status: accepted
last_updated: 2026-09-25
---

# Laboratorium wizji

Lokalna galeria pokazuje dostarczone zdjęcia, siatki i cropy. Użytkownik może
poprawiać, zatwierdzać, trenować i porównywać modele. Obsługuje 5 × 3 i 3 × 3;
integracja z obecną aplikacją obejmuje wyłącznie 5 × 3. Pełne 3 × 3 wymaga
osobnego planu dla modelu danych, review i wyszukiwania. Model startuje
review/shadow, domyślnie wyłączony; D-261 dotyczy późniejszej aktywacji.

Historyczne 777 ma rolę `comparison_only`, bez treningu, kalibracji i wyboru
progów. Folder `777` jest historyczny do wykazania innego pochodzenia.
777 V2 wymaga deklaracji użytkownika dla nagrania/rodziny oraz kontroli
konfliktów checksum i podobieństwa. Brak trafienia podobieństwa nie jest
dowodem niezależności. Nierozstrzygnięte źródło pozostaje poza treningiem.

Oprócz zatwierdzenia DB dopuszcza się `lab_human_approved`: niezmienną
decyzję człowieka z grą, wersją słownika, obrazem źródłowym i SHA-256,
planszą, komórką, rewizją geometrii, dokładnym cropem i SHA-256, etykietą,
rewizją zatwierdzenia i czasem. Zmiana cropa lub geometrii wymaga ponownego
zatwierdzenia nowych pikseli przed treningiem. Predykcja nie jest decyzją.
Zapis laboratoryjny nie podszywa się pod DB review i nie zmienia istniejących
reguł kohorty bazodanowej. Gra bez DB ma lokalną tożsamość i ręcznie
zatwierdzony słownik; rejestracja kandydata wymaga jawnego mapowania do gry
i symboli aplikacji, bez automatycznego tworzenia rekordów.

Anotacja lokalizacji zatwierdza obecność, topologię i narożniki. Pełna
geometria zatwierdza wszystkie węzły i granice komórek. Anotacja symbolu
zatwierdza dokładny crop i klasę. Interpolowana siatka jest propozycją,
nie pełną referencją. `unknown`, nieczytelność i błąd siatki nie są zwykłymi
klasami. Pilot obejmuje do 40 zdjęć na grę z co najmniej 10 rodzin, jeśli są
dostępne, i 30 pełnych siatek na kombinację gra–topologia. Czas mierzy się
na pierwszych 10 zdjęciach. Braki i rozszerzenie zakresu są jawne.

Rodziny nagrań, duplikaty i pochodne obrazu nie przeciekają między train,
validation i test. Przed pierwszym treningiem geometrii zamraża się grę
niewidzianą; symbole tej gry mają osobny podział per gra. Pomiar oszczędności
czasu używa rozłącznych, losowo przydzielonych zdjęć baseline/hybryda;
referencję ocenia się bez informacji o silniku, a przerwa ponad 30 s kończy
aktywny odcinek. Redukcja o 30% jest celem, nie gwarancją.
