---
title: Admin application requirements for version 0.2
status: accepted
last_updated: 2026-07-31
---

# Wymagania panelu Admin — wersja 0.2

## Cel zmiany

Panel ma przestać być jedną długą stroną technicznych modułów. Administrator
pracuje w jednym kontekście gry, w osobnym kontekście wydania Android albo w
prostym monitorze jobów. Szczegóły datasetów i wersji pozostają zachowane przez
backend, lecz są pokazywane tylko tam, gdzie są potrzebne do wykonania zadania.

Ten dokument opisuje zaakceptowany UX `0.2`. Semantyki usuwania, retencji,
własności plików i wyboru folderu zostały rozstrzygnięte w Q-022–Q-032 oraz
D-102–D-112.

## Stan początkowy i skala testów

- prace funkcjonalne `0.2` rozpoczynają się od pustego, zmigrowanego
  PostgreSQL przygotowanego w TASK-0120,
- reset nie obejmuje chronionej paczki wydania `0.1`, klucza podpisującego ani
  źródłowych zdjęć poza bazą,
- workflow `0.2` jest testowany na jednej grze i małym kontrolowanym zbiorze,
- pełne 500 000 rzeczywistych layoutów, dodatkowe gry i wielogrowe wydanie
  należą do `0.3`.

## Główna nawigacja

Na górze znajdują się trzy kafelki trybu:

1. `Zarządzanie grami`,
2. `Wersje Android`,
3. `Joby`.

Przełączenie kafelka zmienia workspace, a nie tylko przewija długą stronę.
Stan powinien być możliwy do odtworzenia po odświeżeniu za pomocą URL albo
równoważnego deterministycznego mechanizmu.

## Joby

- `Joby` jest osobnym, trzecim workspace’em i nie jest accordionem wewnątrz
  zarządzania grą ani wydań Android,
- lista pokazuje co najmniej typ, kontekst/identyfikator, aktualny status,
  czytelny postęp, czas utworzenia i krótki błąd dla niepowodzenia,
- prosty filtr statusu pozwala wybrać `Wszystkie` albo jeden ze statusów
  zwracanych przez kontrakt API,
- kliknięcie joba może rozwinąć istniejące szczegóły diagnostyczne, ale `0.2`
  nie dodaje zaawansowanego wyszukiwania, retencji ani cleanupu jobów,
- operacja uruchamiająca job pokazuje jego identyfikator i może prowadzić do
  zakładki `Joby`; pełna lista i obserwacja postępu nie zaśmiecają ekranu
  źródłowego.

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
- fizyczne `Usuń` nie jest dostępne w `0.2`; docelowo będzie osobną operacją
  wysokiego wpływu kasującą grę wraz z należącymi do niej rekordami,
- kontrakt kaskadowego usuwania, jego dokładny zakres oraz zabezpieczenia
  powstaną w osobnym zadaniu późniejszej wersji.

### Import layoutów

- administrator używa przycisku `Wybierz folder`, który przez kontrolowany
  lokalny backend otwiera standardowe okno wyboru folderu Windows;
  `examples/imgs` nie jest ścieżką specjalną,
- po wyborze backend sprawdza dostępność katalogu i obecność obsługiwanych
  plików przed utworzeniem importu,
- import działa wyłącznie na obrazach; nie ma importu layoutów z Excela,
- nowy import może utworzyć pierwszy zestaw albo uzupełnić brakujące sekwencje,
- ponowne napotkanie już istniejącej sekwencji nie tworzy drugiej pozycji,
- gdy wiele obrazów przedstawia tę samą sekwencję, pipeline wybiera najlepsze
  źródło według jawnych metryk jakości i zachowuje pochodzenie decyzji; Reviewer
  pozwala obejrzeć kandydatów oraz ręcznie zmienić wybór,
- oryginalne pliki są kopiowane do kontrolowanego content-addressed storage;
  rekord zachowuje checksumę i pochodzenie z wybranego folderu,
- oczekiwana liczba layoutów jest prostą konfiguracją, domyślnie `500 000`; w
  `0.2` testowy dataset jawnie ustawia mniejszą wartość,
- status `Brakujące layouty: X` otwiera modal z bounded/stronicowaną listą
  brakujących zakresów i numerów,
- `Doładuj layouty` wznawia ten sam logiczny zbiór i dodaje wyłącznie brakujące
  dane,
- przy niepewnym OCR administrator może opcjonalnie wpisać lub poprawić numer
  sekwencji albo doładować nowe/lepsze zdjęcia; ręczny numer nie jest wymagany,
- `Wyczyść layouty i dane powiązane` przywraca wybraną grę do stanu sprzed
  importu: zachowuje rekord gry, ale usuwa wszystkie jej dane i pliki powstałe
  w workflow layoutów, w tym zależne wydania,
- przed resetem UI pokazuje dokładne liczniki rekordów i artefaktów, wymaga
  wpisania identyfikatora gry oraz mocnego potwierdzenia; współdzielony blob
  pozostaje do zaniku ostatniej referencji,
- po pierwszym poprawnym imporcie odblokowują się `Symbole` i
  `Zatwierdzanie plansz`.

Techniczna wersja datasetu, staging, walidacja i raport integralności nadal
istnieją. Nie są osobną sekcją użytkownika; stanowią wnętrze `Import layoutów`.

### Symbole

- przed uruchomieniem administrator podaje oczekiwaną liczbę symboli,
- pipeline wybiera reprezentatywne klastry/cropy z części importu i tworzy
  propozycje względem oczekiwanej liczby,
- jeżeli liczba klastrów jest inna, katalog nie powstaje automatycznie:
  użytkownik rozstrzyga, które klastry scalić, rozdzielić albo przypisać,
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

- administrator przygotowuje wydanie dla jednej aktywnej gry testowej; wybór
  wielu gier jest świadomie odłożony do `0.3`,
- utworzenie wydania uruchamia potrzebne walidacje, precomputing, snapshot i
  build jako jeden obserwowalny workflow,
- utworzenie technicznego joba jest sygnalizowane przy wydaniu lub imporcie,
  ale jego pełny postęp i szczegóły są prezentowane w osobnej zakładce `Joby`,
- zwijana sekcja historii pokazuje wersję, stan, czas, gry, checksumy oraz APK,
- nieudane kroki pokazują bezpieczny błąd i możliwość ponowienia właściwego
  etapu,
- `Usuń` przy wydaniu po mocnym potwierdzeniu usuwa cały rekord wydania, APK,
  snapshot, manifest, checksumy i dedykowane artefakty; operacja nie zapewnia
  powrotu do tej wersji,
- po usunięciu pozostaje wyłącznie minimalny append-only wpis audytowy samej
  operacji, a nie dostępna historia wydania,
- joby nie mają w `0.2` automatycznej retencji ani dodatkowego cleanupu;
  automatyczne kasowanie audytu jest zabronione.

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
