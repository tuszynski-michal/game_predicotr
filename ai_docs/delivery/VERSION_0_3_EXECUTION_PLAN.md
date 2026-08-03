---
title: Version 0.3 execution plan
status: accepted
last_updated: 2026-08-02
---

# Plan zakresu wersji 0.3

## Cel

Uprościć i zagęścić interfejs aplikacji mobilnej oraz skrócić najczęstszy
przepływ: wybór gry → wprowadzenie lub przejście do layoutu → obliczenie Targetu
→ powrót do góry. Wersja 0.3 nie jest bramką pełnego rzeczywistego datasetu ani
końcowych testów dużych zbiorów. Ten zakres przechodzi do wersji 0.5; wersja
0.4 wcześniej dostarcza sam moduł selekcji reprezentatywnych zdjęć.

## Warunki rozpoczęcia

- właściciel zaakceptował wymagane testy wersji 0.1 i workflow 0.2,
- błędy obu wersji wymagane przed zmianą Mobile zostały naprawione albo jawnie
  zaakceptowane jako nieblokujące,
- artefakt 0.1 pozostaje zachowany i możliwy do ponownej instalacji,
- regresje znalezione podczas dalszych testów 0.1 i 0.2 są rejestrowane jawnie,
- zmiany nie naruszają całkowicie offline modelu aplikacji mobilnej.

## Zamrożony zakres

### Kompaktowy ekran wejściowy

- etykieta wersji ma format `ver {releaseVersion}`,
- z nagłówka znika tytuł `Sequence Target` i oznaczenie `OFFLINE`,
- wybór gry znajduje się bezpośrednio pod wersją,
- rząd akcji `Next`, `Undo`, `Reset` znajduje się na dole nagłówka, bezpośrednio
  nad planszą,
- z planszy znikają tytuł `Layout` i licznik `selected/total`,
- znika komunikat `Dane lokalne gotowe`,
- z Selection znikają tytuł i opis, a odstęp względem planszy jest minimalny.

### Nawigacja `Next`

- przycisk `Next` znajduje się z lewej strony `Undo`,
- dla jednoznacznie ustalonej pozycji przechodzi do kolejnego `sequence_number`,
  z zawinięciem końca sekwencji do jej początku,
- wczytuje pełny następny layout i ponownie oblicza wynik oraz Target dla
  aktualnie wybranego zasięgu,
- przejście jest jednym krokiem historii, więc `Undo` odtwarza planszę,
  jednoznaczną pozycję i wynik sprzed `Next`,
- nie uruchamia Targetu, jeżeli bieżąca pozycja sekwencji nie jest
  jednoznaczna; przycisk jest wtedy nieaktywny.

### Kompaktowy Selection

- kafelki zawijają się do kolejnych rzędów i nie wymagają przewijania poziomego,
- kafelek pokazuje tylko jedną, niepogrubioną etykietę,
- wybierana jest krótsza z `name_pl` i `name_en`; remis preferuje polską, a
  kompatybilnościowe `name` jest fallbackiem, gdy brak obu etykiet,
- etykieta jest jednowierszowa i kończy się wielokropkiem, gdy się nie mieści,
- wysokość i padding kafelka są zmniejszone bez pogorszenia minimalnego obszaru
  dotykowego i dostępności.

### Zasięg obliczeń Targetu

- użytkownik ustawia liczbę przyszłych spinów w kompaktowym polu liczbowym,
- wartość domyślna to `10 000`, minimalna `1 000`, maksymalna `500 000`; można
  wpisać dowolną liczbę całkowitą z tego zakresu,
- rzeczywista liczba ocenianych spinów wynosi
  `min(target_scan_limit, layout_count - 1)`, więc spin 0 nigdy nie trafia do
  własnej prognozy,
- zmiana wartości dla jednoznacznego layoutu anuluje lub unieważnia poprzedni
  wynik i uruchamia ponowne obliczenie,
- pełny cykl pozostaje możliwy przez ustawienie limitu co najmniej `N - 1`.

### Wynik i nawigacja strony

- osobna sekcja `Target obliczony` znika,
- sukces jest prezentowany jako `Układ znaleziony i obliczony` z numerem oraz
  layoutem w dotychczasowym formacie wyniku Targetu,
- status sukcesu jest zielony, duplikatu ostrzegawczo żółty/pomarańczowy, a
  błędu lub braku layoutu czerwony; kolor zawsze ma tekstowy lub ikonowy
  odpowiednik,
- opis problemu jest widoczny dla duplikatu, błędu i braku layoutu, ale nie dla
  sukcesu,
- część rozszerzona zawiera tylko `Koszt spinu`, `Koszt` i `Suma końcowa`,
- znika opis o jednoznacznym uruchamianiu pełnego cyklu oraz podpis o lokalnych
  maksimach,
- po dotarciu do sekcji wyników Targetu pojawia się pływający, dostępny
  przycisk powrotu na górę, umieszczony nad dolnym safe area i niezasłaniający
  tabeli.

## Kolejność zadań

1. **TASK-0135 — Compact mobile header and board shell**
   - wersja, wybór gry, rząd akcji oraz usunięcie zbędnych tytułów, liczników i
     statusu gotowości danych.
2. **TASK-0136 — Responsive compact Selection grid and labels**
   - migracja opcjonalnych nazw PL/EN, ich pola w istniejącym kontrakcie i
     formularzu symbolu, snapshot schema v3, zawijana siatka, deterministyczny
     wybór krótszej nazwy, ellipsis, rozmiary dotykowe i brak poziomego
     przewijania.
3. **TASK-0137 — Configurable bounded Target scan**
   - kontrakt limitu, input 1 000–500 000, domyślne 10 000, anulowanie i
     deterministyczne wyniki ograniczonego okna.
4. **TASK-0138 — Anchored Next navigation and recalculation**
   - jednoznaczny anchor sekwencji, zawijanie, ponowne obliczenie i atomowe
     Undo.
5. **TASK-0139 — Consolidated matching and Target result summary**
   - wspólny komunikat, statusy, kompaktowe szczegóły i usunięcie powtórzeń.
6. **TASK-0140 — Results-aware scroll-to-top control**
   - widoczność zależna od pozycji, safe area, dostępność i powrót na górę.
7. **TASK-0141 — Version 0.3 mobile regression and Pixel acceptance**
   - testy jednostkowe/integracyjne, statyczna weryfikacja APK i odbiór offline
     na Google Pixel 10 Pro XL.

Każde zadanie jest osobnym pionem. TASK-0137 i TASK-0138 zmieniają zachowanie
domenowe, dlatego wymagają testów bezpośrednio po implementacji; pozostałe
zmiany UI mogą zostać zebrane do jednego końcowego odbioru TASK-0141.

## Bramka 0.3

- ekran nie ma poziomego przewijania i pozostaje użyteczny w pionie na Pixelu,
- plansza oraz Selection zajmują mniej wysokości bez utraty czytelności i
  dostępności,
- `Next`, `Undo` i `Reset` zachowują deterministyczną pozycję sekwencji,
- limit Targetu respektuje zakres, wrap-around, koszt, payout i maksima tylko w
  ocenianym oknie,
- stan sukcesu, duplikatu, braku layoutu i błędu danych jest jednoznaczny bez
  polegania wyłącznie na kolorze,
- powrót na górę działa przy długiej tabeli,
- APK działa całkowicie offline na Google Pixel 10 Pro XL,
- właściciel akceptuje mobilny przepływ i jawne ograniczenia.

## Poza zakresem 0.3

- pełny rzeczywisty import około 500 000 layoutów,
- końcowe testy i benchmarki na dużych rzeczywistych zbiorach,
- nowe gry i wielogrowe wydanie,
- TASK-0076 oraz TASK-0080–0089,
- stały podpis, backup/restore, recovery, rollback i rozszerzona macierz
  urządzeń.

Powyższy zakres należy do
[wersji 0.5](VERSION_0_5_EXECUTION_PLAN.md).
