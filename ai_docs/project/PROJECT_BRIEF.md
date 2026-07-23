---
title: Project brief
status: proposed
last_updated: 2026-07-23
---

# Project brief

## Nazwa robocza

`Sequence Target Analyzer`

Nazwa jest tymczasowa i nie wpływa na identyfikatory domenowe.

## Problem

Użytkownik zna wizualny układ symboli z gry i chce:

1. odnaleźć dokładną pozycję tego układu w deterministycznej sekwencji,
2. rozstrzygnąć niejednoznaczność, gdy ten sam układ występuje więcej niż raz,
3. obliczyć przyszłe wyniki kredytowe dla kolejnych pozycji sekwencji,
4. zarządzać grami, symbolami, regułami wygranych i danymi wejściowymi,
5. docelowo importować duże zbiory układów ze zdjęć.

## Użytkownicy

### Użytkownik aplikacji mobilnej

- wybiera grę,
- wprowadza symbole planszy,
- identyfikuje pozycję sekwencji,
- sprawdza prognozę targetu.

### Administrator danych

- zarządza grami i symbolami,
- definiuje reguły wygranych,
- importuje lub generuje układy,
- przegląda błędy rozpoznawania zdjęć,
- zatwierdza dane przed publikacją.

## Główne moduły

1. **Mobile Client** — aplikacja Android do ręcznego wprowadzania planszy i prezentacji wyniku.
2. **Admin Web** — aplikacja uruchamiana w przeglądarce na Windows.
3. **API** — spójny dostęp do danych oraz logiki aplikacyjnej.
4. **Database** — kanoniczne dane gier, sekwencji, symboli i reguł.
5. **Import Worker** — oddzielny proces do masowego przetwarzania zdjęć.

## Zakres pierwszej wersji działającej

Pierwsza wersja ma:

- obsługiwać 3 gry,
- zawierać po 1000 zamockowanych układów dla każdej gry,
- posiadać planszę domyślnie 3 × 5,
- pozwalać wybierać symbole tekstowe `S1`, `S2`, ...,
- obsługiwać undo i reset,
- wyszukiwać pasujące układy podczas wprowadzania,
- proponować automatyczne uzupełnienie, gdy pozostaje jeden kandydat,
- zwracać numer sekwencji dla kompletnej planszy,
- wykrywać duplikaty układu,
- nie zawierać jeszcze docelowej prognozy kredytowej ani rozpoznawania zdjęć.

## Poza zakresem pierwszej wersji

- automatyczne rozpoznawanie zdjęć,
- OCR numerów układów,
- uczenie modelu klasyfikacji symboli,
- pełny edytor reguł wygranych,
- publikacja w Google Play,
- synchronizacja offline,
- autoryzacja produkcyjna,
- infrastruktura chmurowa.

## Najważniejsze ograniczenia

- środowisko deweloperskie: Windows,
- główny klient: Android,
- frontend: TypeScript i React,
- backend: Python,
- kolejność danych jest krytyczna,
- ten sam layout może wystąpić wiele razy,
- liczba rekordów może osiągnąć miliony,
- import zdjęć musi być wznawialny i odporny na pojedyncze błędy.

## Ryzyka domenowe

1. Nie jest jeszcze rozstrzygnięte, czy 500 000 oznacza zdjęcia, układy na grę, czy oba warianty. Jeżeli jedno zdjęcie zawiera 9 układów, 500 000 zdjęć oznacza do 4 500 000 rozpoznanych układów.
2. Opis zawiera co najmniej dwa typy reguł wygranej: konkretną linię pozycji oraz dowolny rząd w kolejnych kolumnach.
3. Nie jest ustalone, czy aplikacja mobilna ma działać bez połączenia z backendem.
4. Reguły jokera i liczenia wielu kombinacji nie są jeszcze kompletne.

## Kryterium sukcesu fazy architektonicznej

Można rozpocząć implementację, gdy zaakceptowane są:

- model wdrożenia online/offline,
- znaczenie liczby 500 000,
- semantyka numeru sekwencji,
- typy reguł wygranych,
- definicja targetu i sposobu prezentacji rekordów rosnących.
