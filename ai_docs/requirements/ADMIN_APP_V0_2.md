---
title: Admin application requirements for version 0.2
status: accepted
last_updated: 2026-07-31
---

# Wymagania panelu Admin — wersja 0.2

## Cel zmiany

Panel ma przestać być jedną długą stroną technicznych modułów. Administrator
pracuje w jednym kontekście gry albo w osobnym kontekście wydania Android, a
szczegóły datasetów, wersji i jobów są zachowane przez backend, lecz pokazywane
tylko tam, gdzie są potrzebne do wykonania zadania.

Ten dokument opisuje planowany UX `0.2`. Nierozstrzygnięte semantyki usuwania,
retencji, własności plików i wyboru folderu znajdują się w
`project/OPEN_QUESTIONS.md` i nie
blokują wydania `0.1`.

## Główna nawigacja

Na górze znajdują się dwa kafelki trybu:

1. `Zarządzanie grami`,
2. `Wersje Android`.

Przełączenie kafelka zmienia workspace, a nie tylko przewija długą stronę.
Stan powinien być możliwy do odtworzenia po odświeżeniu za pomocą URL albo
równoważnego deterministycznego mechanizmu.

## Zarządzanie grami

### Reguły sekcji

- `Gry` jest zawsze widoczne i zastępuje nazwę `Katalog gier`.
- gdy nie wybrano gry, ekran pokazuje wyłącznie sekcję `Gry`; nagłówki sekcji
  zależnych pojawiają się dopiero po wybraniu albo odtworzeniu aktywnej gry,
- Pozostałe sekcje są accordionem: jednocześnie rozwinięta jest najwyżej jedna.
- Zwinięta sekcja pokazuje tytuł, krótki opis, stan gotowości i ewentualną
  blokadę.
- Rozwinięcie kolejnej sekcji zwija poprzednią bez niekontrolowanego skoku
  scrolla; nagłówek aktywnej sekcji pozostaje w widoku.
- Sekcje zależne od gry nie mają własnego selecta gry.
- Kolejność pracy: `Gry` → `Import layoutów` → `Symbole` → `Reguły` →
  `Zatwierdzanie plansz`.

Import znajduje się przed symbolami, ponieważ propozycje symboli i ich grafiki
powstają z zaimportowanych zdjęć. Sekcja zablokowana pokazuje dokładny brakujący
krok zamiast pustego formularza.

### Gry

- lista pokazuje liczbę gier oraz filtr `Aktywne`, `Szkice`,
  `Zarchiwizowane`,
- wybrana gra ma jednoznaczne podświetlenie i jest jedynym kontekstem sekcji
  poniżej,
- usunięty zostaje opis o wszystkich rekordach i stabilnym kodzie z nagłówka;
  walidacja stabilnego kodu nadal obowiązuje w formularzu i API,
- `Archiwizuj` pozostaje operacją odwracalną,
- `Usuń` jest osobną operacją wysokiego wpływu i będzie dostępne dopiero po
  rozstrzygnięciu Q-022; nie może po cichu kasować zależnych danych lub audytu.

### Import layoutów

- administrator wskazuje katalog zdjęć na lokalnym dysku; `examples/imgs` nie
  jest ścieżką specjalną,
- import działa wyłącznie na obrazach; nie ma importu layoutów z Excela,
- nowy import może utworzyć pierwszy zestaw albo uzupełnić brakujące sekwencje,
- ponowne napotkanie już istniejącej sekwencji nie tworzy drugiej pozycji,
- gdy wiele obrazów przedstawia tę samą sekwencję, pipeline wybiera najlepsze
  źródło według jawnych metryk jakości i zachowuje pochodzenie decyzji,
- w `0.2` oczekiwana liczba jest domyślnie równa 500 000,
- status `Brakujące layouty: X` otwiera modal z bounded/stronicowaną listą
  brakujących zakresów i numerów,
- `Doładuj layouty` wznawia ten sam logiczny zbiór i dodaje wyłącznie brakujące
  dane,
- `Usuń layouty` jest potwierdzoną operacją wysokiego wpływu zależną od polityki
  Q-032 i nie może usuwać źródła aktywnego wydania,
- po pierwszym poprawnym imporcie odblokowują się `Symbole` i
  `Zatwierdzanie plansz`.

Techniczna wersja datasetu, staging, walidacja i raport integralności nadal
istnieją. Nie są osobną sekcją użytkownika; stanowią wnętrze `Import layoutów`.

### Symbole

- przed uruchomieniem administrator podaje oczekiwaną liczbę symboli,
- pipeline wybiera reprezentatywne klastry/cropy z części importu i tworzy
  dokładnie oczekiwaną liczbę propozycji,
- każdy symbol jest kafelkiem z proponowaną grafiką i edytowalną nazwą,
- nie ma podstawowego przepływu `Nowy symbol` ani ręcznego budowania całego
  rekordu symbolu,
- po przetworzeniu większej liczby layoutów kliknięcie grafiki otwiera modal z
  10 czytelnymi kandydatami,
- `Załaduj kolejne grafiki` pobiera następne kandydatury bez duplikowania już
  pokazanych,
- edytowalna grafika ma hover z ikoną edycji, widoczny focus klawiatury i
  cursor pointer; niedostępny wybór nie udaje klikalnego,
- zapis zachowuje stabilny `mobileCode`; zmienia etykietę i wskazanie obrazu
  referencyjnego, nie historię pochodzenia cropów.

### Reguły

- sekcja używa aktywnej gry i nie ma własnego selecta,
- użytkownik widzi jeden bieżący workspace reguł, paylines i payoutów,
- historia wersji nie zajmuje głównego widoku, ale backend nadal tworzy
  niezmienne wersje potrzebne do odtworzenia APK,
- UI nie edytuje opublikowanej wersji w miejscu: zapis zmian tworzy nowy draft,
  a publikacja nową wersję wewnętrzną,
- po zmianie reguł dostępna jest jawna akcja `Przelicz layouty`, która uruchamia
  wersjonowany precomputing dla całego aktywnego datasetu,
- nowe wydanie Android nie może użyć niekompletnego albo nieaktualnego payoutu.

### Zatwierdzanie plansz

- zastępuje osobne pozycje `Manual Review` i dotychczasowe wejścia do review,
- korzysta z aktywnej gry i ostatniego aktywnego importu albo pozwala jawnie
  wybrać import w obrębie tej gry,
- bez layoutów pokazuje komunikat i akcję prowadzącą do `Import layoutów`,
- otwiera istniejącą osobną aplikację Reviewer; nie kopiuje jej rozbudowanego
  ekranu do Admina,
- lokalne i zdalne sesje, kod, revoke oraz audyt pozostają zgodne z v0.1.

## Wersje Android

- administrator wybiera aktywne gry wchodzące do jednego wydania,
- utworzenie wydania uruchamia potrzebne walidacje, precomputing, snapshot i
  build jako jeden obserwowalny workflow,
- techniczne joby są prezentowane kontekstowo przy wydaniu lub imporcie, a nie
  jako podstawowa długa sekcja panelu,
- zwijana sekcja historii pokazuje wersję, stan, czas, gry, checksumy oraz APK,
- nieudane kroki pokazują bezpieczny błąd i możliwość ponowienia właściwego
  etapu,
- `Usuń` przy wydaniu podlega Q-023: rekomendowane jest usuwanie artefaktu APK
  po potwierdzeniu przy zachowaniu rekordu, manifestu, checksum i audytu,
- historia jobów i ciężkich artefaktów podlega jawnej polityce retencji Q-024;
  automatyczne kasowanie całego audytu jest zabronione.

## Niezmienne granice architektury

- wybór gry w UI nie zastępuje `gameId` w kontrakcie API,
- `sequence_number` pozostaje domenową kolejnością i nie może wynikać z UUID,
- dataset oraz rules version pozostają niezmienne po publikacji,
- usunięcie sekcji z UI nie usuwa wymaganych encji domenowych,
- mobile nadal otrzymuje tylko rekordy, grafiki symboli i precomputed payout,
  bez zdjęć źródłowych,
- Admin/API/PostgreSQL pozostają loopback; publiczny jest wyłącznie ograniczony
  Reviewer,
- operacje kasowania, publikacji i przeliczania zachowują intencję, dokładny cel,
  idempotencję i append-only audyt.
