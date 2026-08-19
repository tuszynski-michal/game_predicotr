---
title: Iterative supervised symbol model improvement requirements
status: accepted
last_updated: 2026-08-09
---

# Iteracyjne ulepszanie rozpoznawania symboli

## Cel

System ma wykorzystywać ręcznie zweryfikowane plansze do kolejnych,
kontrolowanych wersji modelu rozpoznawania symboli. Właściciel może zatwierdzić
około 100 plansz, ulepszyć model, zatwierdzić kolejne 1000, ponownie ulepszyć
model, a następnie importować nowe zdjęcia z coraz lepszymi sugestiami.

Nie jest to uczenie online. Każda iteracja jest jawnym, lokalnym i
odtwarzalnym treningiem na skumulowanym, zamrożonym zbiorze.

## Nienaruszalna reguła decyzji człowieka

Automatyczna operacja nie może zmienić ani ponownie przeliczyć planszy, dla
której użytkownik zapisał rozstrzygnięcie `accepted`, `corrected` lub
`rejected`.

- `accepted` i `corrected` są kanoniczną prawdą oraz mogą wejść do zbioru
  treningowego, jeżeli zawierają zaakceptowaną geometrię i dokładnie komplet
  etykiet komórek,
- `rejected` pozostaje niezmienną decyzją człowieka, ale nie jest przykładem
  treningowym,
- wyłącznie element `pending` może otrzymać nową rewizję predykcji,
- ponowne otwarcie rozstrzygniętego elementu wymaga osobnej, jawnej akcji
  użytkownika i zdarzenia audytowego; dopiero po zmianie stanu na `pending`
  element może otrzymać nowe sugestie,
- trening, aktywacja modelu i przeliczenie oczekujących nie modyfikują
  historycznych zdarzeń review, zatwierdzonych etykiet, geometrii ani stagingu.

## Zakres per gra

Model, kohorta treningowa, metryki i aktywna wersja są przypisane do jednej
gry. Dane różnych gier nie są łączone bez nowej decyzji architektonicznej,
ponieważ gry mogą mieć inne katalogi symboli i inne warunki obrazu.

## Kohorta treningowa

Użytkownik uruchamia akcję `Ulepsz rozpoznawanie`. System przed treningiem:

1. pokazuje liczbę pełnych plansz zweryfikowanych przez człowieka,
2. pokazuje liczbę nowych plansz od ostatniej iteracji oraz pokrycie klas i
   źródeł,
3. zamraża jednoznaczną kohortę przez identyfikatory, rewizje i checksumy,
4. tworzy niezmienny manifest wejścia,
5. trenuje od początku na całej skumulowanej kohorcie danej gry.

Wartości 100 i 1000 plansz są progami doradczymi w UI, a nie automatycznym
wyzwalaczem. Użytkownik może rozpocząć iterację przy innej liczbie, jeżeli
raport gotowości jawnie pokazuje ryzyko małej lub niezrównoważonej próby.
Jedynym progiem liczności jest co najmniej jedna kompletna plansza; 5, 10, 63
lub 100 plansz pozwala uruchomić trening.

## Podział danych i brak przecieku

- przykłady pochodzące z tego samego zdjęcia źródłowego albo jego pochodnych
  trafiają tylko do jednej części podziału,
- podział train/validation/test jest deterministyczny i zapisany w manifeście,
- polityka `source-family-balanced-split-v2` gwarantuje niezależne, niepuste
  zbiory przy co najmniej czterech źródłach; przypisania źródeł są zapisywane
  w konfiguracji i pozostają stabilne po rozszerzeniu kohorty,
- stały zestaw kontrolny nie może zostać włączony do treningu kolejnej wersji,
- raport pokazuje liczność per symbol, źródło i część podziału,
- brak wymaganej reprezentacji klasy blokuje promocję albo wymaga jawnego
  zaakceptowania ograniczenia przez właściciela.

## Cykl życia wersji modelu

```text
draft -> training -> evaluating -> candidate_ready -> active
                         |                 |
                         v                 v
                       failed           rejected
```

- trening tworzy nową wersję kandydującą i nigdy nie nadpisuje poprzedniego
  modelu,
- kandydat przechodzi eksport ONNX, zgodność inferencji, kalibrację confidence
  oraz porównanie ze stabilnym zestawem kontrolnym,
- model nie staje się aktywny automatycznie po treningu,
- aktywacja wymaga jawnego potwierdzenia użytkownika po pokazaniu porównania z
  bieżącym modelem,
- poprzednia aktywna wersja pozostaje dostępna do kontrolowanego rollbacku.

## Użycie nowego modelu

- nowy import przypina aktywną wersję modelu i jej checksumę w momencie
  tworzenia joba,
- aktywacja modelu podczas trwającego importu nie zmienia modelu używanego
  przez ten job,
- następny import używa już nowej aktywnej wersji,
- użytkownik może jawnie uruchomić `Przelicz oczekujące`, aby utworzyć nowe
  sugestie tylko dla nadal nierozwiązanych elementów,
- ponowna inferencja zapisuje nową rewizję predykcji; nie usuwa poprzedniej
  rewizji i nie zmienia rozstrzygnięć człowieka.

## Panel jakości rozpoznawania

Panel Admina dla aktywnej gry pokazuje co najmniej:

- aktywną wersję modelu i jej checksumę,
- liczbę zweryfikowanych plansz ogółem i od ostatniej iteracji,
- liczność danych per symbol i liczbę zdjęć źródłowych,
- status treningu i postęp etapów,
- porównanie kandydata z aktywnym modelem, w tym accuracy, macro recall,
  wyniki per symbol i macierz pomyłek,
- akcje `Ulepsz rozpoznawanie`, `Aktywuj`, `Odrzuć`, `Przelicz oczekujące` i
  kontrolowany rollback,
- licznik elementów, które zostaną przeliczone, oraz licznik chronionych
  decyzji człowieka, które zostaną pominięte.

## Błędy i wznawianie

- ciężkie etapy działają jako trwały job z checkpointami, postępem i
  możliwością retry,
- początkowo działa najwyżej jeden ciężki trening lub masowa inferencja naraz;
  niezależny run Selekcji Zdjęć nie jest błędnie interpretowany jako trwający
  trening modelu symboli,
- błąd treningu nie zmienia aktywnego modelu,
- błąd przeliczenia części oczekujących zachowuje poprzednie predykcje i
  pozwala wznowić operację idempotentnie,
- zapis nowej predykcji sprawdza aktualny status, rewizję i checksumę cropu;
  element rozstrzygnięty w międzyczasie jest pomijany.

## Poza zakresem tego pionu

- automatyczne uczenie po każdym zatwierdzeniu,
- nadpisywanie decyzji człowieka,
- uczenie na odrzuconych lub niekompletnych planszach,
- automatyczna aktywacja kandydata,
- wspólny model wielu gier,
- poprawa geometrii plansz i OCR numerów sekwencji; te elementy wymagają
  osobnych wersji pipeline'u i osobnych bramek jakości,
- chmura, Redis/Celery i zewnętrzny serwis treningowy.

## Rozszerzenie geometrii w wersji 0.5

Uczenie symboli pozostaje niezależne od kalibracji siatki. Wersja 0.5 dodaje
osobny, opisany w ITERATIVE_IMAGE_IMPORT.md, wersjonowany profil korekt
geometrii. Nie jest to uczenie online i nie zmienia istniejących decyzji review.
Aktywowany profil działa wyłącznie w nowych partiach importu. Automatyczne
przeliczenie wcześniejszych pending jest w bieżącym zakresie odroczone.

## Kryterium produktu

Po dwóch lub więcej iteracjach system potrafi wykazać, że każdy model powstał z
konkretnej, niezmiennej kohorty, nowy import użył przypiętej aktywnej wersji, a
żadna automatyczna operacja nie zmieniła choćby jednej decyzji zapisanej przez
użytkownika.
