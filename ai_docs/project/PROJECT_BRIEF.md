---
title: Project brief
status: accepted
last_updated: 2026-07-31
---

# Project brief

## Nazwa robocza

`Sequence Target Analyzer`

Nazwa jest tymczasowa i nie wpływa na identyfikatory domenowe.

## Problem

Użytkownik zna wizualny układ symboli z gry i chce:

1. odnaleźć dokładną pozycję tego układu w deterministycznej sekwencji,
2. wykryć niejednoznaczność, gdy ten sam układ występuje więcej niż raz,
3. obliczyć wyniki kredytowe dla pełnego przyszłego cyklu,
4. zobaczyć dodatnie lokalne maksima wyniku netto,
5. zarządzać grami, symbolami, paylines, wypłatami i danymi wejściowymi,
6. przygotowywać wersjonowane, instalowalne wydania Android,
7. docelowo importować duże zbiory układów ze zdjęć.

## Użytkownicy

### Użytkownik aplikacji mobilnej

- wybiera grę,
- wprowadza symbole planszy,
- identyfikuje pozycję sekwencji,
- obsługuje informację o duplikacie przez reset i wprowadzenie kolejnego layoutu,
- sprawdza pełną prognozę targetu bez połączenia z siecią.

### Administrator danych

- zarządza grami, wymiarami plansz i symbolami,
- definiuje paylines oraz wypłaty dla symboli i długości dopasowania,
- importuje lub generuje layouty,
- przegląda błędy rozpoznawania zdjęć,
- publikuje wersjonowany snapshot danych,
- uruchamia przygotowanie instalowalnego wydania Android.

### Recenzent danych

- zatwierdza albo poprawia pełne plansze 5 × 3 wskazanej gry,
- sprawdza cropy w kontekście oryginalnego zdjęcia,
- może poprawić geometrię i wrócić do wcześniejszej planszy,
- nie zarządza regułami, jobami, publikacją ani wydaniami Android,
- początkowo pracuje lokalnie; opcjonalny zdalny dostęp wymaga ograniczonej
  sesji M8.7.

## Główne moduły

1. **Mobile Client** — całkowicie offline aplikacja Android z lokalnym snapshotem SQLite.
2. **Admin Web** — lokalna aplikacja uruchamiana w przeglądarce na Windows.
3. **Admin API** — lokalny backend dla panelu administracyjnego; nie jest zależnością aplikacji mobilnej.
4. **Canonical Database** — lokalny PostgreSQL z kanonicznymi danymi administracyjnymi.
5. **Worker / CLI** — oddzielny lokalny proces dla importu, walidacji, obliczania payoutów, generowania snapshotu i przygotowania wydania.
6. **Release artifacts** — niezmienny snapshot SQLite oraz APK przygotowane dla konkretnej wersji danych i reguł.

## Docelowa skala

- około 12–15 gier, z możliwością dodania kolejnych,
- do około 500 000 uporządkowanych layoutów na grę,
- około 7,5 miliona layoutów przy 15 grach,
- do aplikacji mobilnej trafiają rekordy domenowe i obliczony payout, bez zdjęć źródłowych,
- rozmiar aplikacji do kilku GB jest akceptowalny; nie jest wymagana agresywna kompresja kosztem poprawności lub prostoty.

## Zakres pierwszej wersji działającej — M1

Pierwsza wersja ma:

- obsługiwać 3 gry,
- zawierać po 1000 zamockowanych layoutów dla każdej gry,
- posiadać planszę 3 × 5,
- pozwalać wybierać symbole tekstowe `S1`, `S2`, ...,
- obsługiwać undo i reset,
- wyszukiwać pasujące layouty lokalnie podczas wprowadzania,
- proponować automatyczne uzupełnienie, gdy pozostaje jeden kandydat,
- zwracać `sequence_number` dla kompletnej planszy,
- wykrywać duplikaty layoutu i blokować prognozę,
- obliczać payout według zamockowanych paylines i wartości,
- liczyć pełny cykl od layoutu następującego po spinie startowym do layoutu bezpośrednio go poprzedzającego,
- pokazywać dodatnie lokalne maksima wyniku netto w tabeli na dole ekranu,
- działać całkowicie offline z danymi dołączonymi do APK,
- dać się ręcznie zainstalować i przetestować co najmniej na Google Pixel 10 Pro XL oraz Samsung Galaxy S21 Ultra.

## Poza zakresem M1

- panel administracyjny i kanoniczna baza PostgreSQL,
- automatyczne rozpoznawanie zdjęć i OCR,
- uczenie produkcyjnego modelu klasyfikacji symboli,
- pełny proces importu i ręcznej korekty,
- generowanie APK z poziomu panelu administracyjnego,
- publikacja w Google Play,
- synchronizacja mobilna, chmura i publiczna infrastruktura,
- produkcyjna autoryzacja wielu administratorów.

## Strategia wydań 0.1 i 0.2

- `0.1` jest kompletną wersją demonstracyjną dla Google Pixel 10 Pro XL:
  jedna gra, rzeczywiste grafiki symboli, chroniony podzbiór ponad 100
  zatwierdzonych plansz i deterministyczne dopełnienie do dokładnie 500 000
  layoutów. Dane dopełniające służą testom zachowania i wydajności, a nie są
  deklarowane jako wynik rozpoznania 500 000 rzeczywistych układów.
- `0.2` upraszcza Admina do prowadzonego workflow, dodaje docelowy import z
  folderu i budowanie katalogu symboli, a następnie domyka publikację
  rzeczywistych danych, stały podpis, backup/restore, recovery, rollback i
  uzgodnioną macierz urządzeń.
- Szczegółowe zakresy są zapisane w `delivery/VERSION_0_1_RELEASE_PLAN.md` i
  `delivery/VERSION_0_2_EXECUTION_PLAN.md`.

## Najważniejsze ograniczenia

- środowisko deweloperskie i administracyjne: Windows,
- główny klient: Android,
- aplikacja mobilna nigdy nie łączy się z Internetem, LAN ani backendem,
- wdrożenie prywatne na maksymalnie 3–5 urządzeniach,
- zmiana danych lub reguł wymaga przygotowania i ręcznego zainstalowania nowego APK,
- frontend: TypeScript w trybie strict i React,
- backend administracyjny oraz przetwarzanie danych: Python,
- `sequence_number` jest krytyczną, ciągłą wartością domenową,
- duplikaty treści layoutu są dozwolone, ale muszą zostać jawnie wykryte,
- import zdjęć musi być wznawialny i odporny na pojedyncze błędy.

## Najważniejsze ryzyka

1. Trzeba zmierzyć rozmiar i czas lokalnego wyszukiwania oraz pełnego skanu dla 500 000 layoutów na grę.
2. Jakość zdjęć obejmuje perspektywę, krzywiznę ekranu, moiré, odbicia, rozmycie i zasłonięcia; stos technologiczny rozpoznawania pozostaje wymienny do czasu benchmarku.
3. Generowanie wersjonowanego snapshotu i APK musi być deterministyczne, audytowalne oraz możliwe do ponowienia.
4. Zmiana wersjonowanego minimum długości symbolu lub wartości kredytów wymaga
   ponownego precomputingu wszystkich payoutów i nowego wydania mobilnego.
5. Ostateczna liczba i jakość oznaczonych zdjęć może ograniczyć automatyzację importu.

## Kryterium sukcesu fazy architektonicznej

Faza jest ukończona po zapisaniu decyzji o:

- całkowicie offline modelu mobilnym,
- skali do 500 000 layoutów na grę,
- cyklicznej i ciągłej sekwencji,
- jednym typie wzorca `PAYLINE`,
- zasadach payoutu, jokera, sumowania i duplikatów,
- definicji pełnego cyklu oraz dodatniego lokalnego maksimum,
- monorepo i stosie technologicznym,
- oddzieleniu kanonicznego PostgreSQL od mobilnego snapshotu SQLite,
- wersjonowanym procesie przygotowania APK.
