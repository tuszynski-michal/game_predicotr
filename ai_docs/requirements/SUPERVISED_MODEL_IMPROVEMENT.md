---
title: Iterative supervised symbol model improvement requirements
status: accepted
last_updated: 2026-08-23
---

# Iteracyjne ulepszanie rozpoznawania symboli

## Cel

System ma wykorzystywać ręcznie zweryfikowane cropy symboli do kolejnych,
kontrolowanych wersji modelu rozpoznawania symboli. Właściciel może zatwierdzić
około 100 plansz, ulepszyć model, zatwierdzić kolejne 1000, ponownie ulepszyć
model, a następnie importować nowe zdjęcia z coraz lepszymi sugestiami.

Nie jest to uczenie online. Każda iteracja jest jawnym, lokalnym i
odtwarzalnym treningiem na skumulowanym, zamrożonym zbiorze.

## Nienaruszalna reguła decyzji człowieka

Automatyczna operacja nie może zmienić ani ponownie przeliczyć planszy, dla
której użytkownik zapisał rozstrzygnięcie `accepted`, `corrected` lub
`rejected`.

- każda komórka `approved` jest kanoniczną prawdą logiczną niezależnie od stanu
  pozostałych komórek planszy, ale do zbioru treningowego może wejść wyłącznie,
  gdy wskazuje aktywny realny symbol, nie ma problemu jakości, należy do
  aktualnego właściciela planszy, a bieżący crop i jego SHA-256 są zgodne z
  dokładną tożsamością cropa ostatnio zatwierdzonego przez człowieka,
- recrop zachowuje logiczną etykietę, lecz wyłącza nowe piksele z treningu do
  czasu osobnego zatwierdzenia bieżącego cropa; `unreadable` i domenowe `?` nie
  są przykładami treningowymi,
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

Raport browserowego importu może być odczytany przed pierwszym treningiem, aby
operator mógł ocenić zakresy i przygotować geometrię. Taki raport jawnie
pokazuje brak gotowego modelu i nie jest autoryzacją startu importu. Start
inferencji nadal wymaga wytrenowanego oraz aktywnego snapshotu zgodnego z
bieżącym katalogiem symboli danej gry; niezgodny globalny bootstrap nie może go
zastąpić.

## Kohorta treningowa

Użytkownik uruchamia akcję `Ulepsz rozpoznawanie`. System przed treningiem:

1. pokazuje liczbę zatwierdzonych cropów wybranych do ograniczonej kohorty,
2. pokazuje liczbę nowych cropów od ostatniej iteracji oraz pokrycie klas i
   źródeł,
3. zamraża jednoznaczną kohortę przez identyfikatory, rewizje i checksumy,
4. tworzy niezmienny manifest wejścia,
5. trenuje od początku na całej skumulowanej kohorcie danej gry.

Kohorta v3 wybiera deterministycznie różnorodne przykłady osobno dla każdego
aktywnego symbolu. Korekty człowieka mają pierwszeństwo, identyczne i bliskie
wizualnie cropy są redukowane bez macierzy porównań każdy-z-każdym. Cel wynosi
1000 próbek na symbol, a twarde maksimum 2000; większa liczba zatwierdzeń nie
powiększa bez końca kosztu jednej iteracji. Jedynym progiem startu pozostaje co
najmniej jeden kwalifikujący crop.

Manifest v3 zapisuje bieżącą oraz zatwierdzoną tożsamość cropa. Obie muszą mieć
ten sam sample ID, SHA-256 i rewizję geometrii. Preview raportuje osobno cropy
wykluczone jako unknown, unreadable, grid issue, zmienione po zatwierdzeniu albo
pozbawione poprawnego assetu. Historyczne manifesty v1/v2 pozostają obsługiwane
wyłącznie w celu reprodukcji istniejących iteracji.

## Podział danych i brak przecieku

- przykłady pochodzące z tego samego zdjęcia źródłowego albo jego pochodnych
  trafiają tylko do jednej części podziału,
- podział train/validation/test jest deterministyczny i zapisany w manifeście,
- polityka `source-family-balanced-split-v2` gwarantuje niezależne, niepuste
  zbiory przy co najmniej czterech źródłach; przypisania źródeł są zapisywane
  w konfiguracji i pozostają stabilne po rozszerzeniu kohorty,
- źródła muszą być wyprowadzane zarówno z historycznych pełnych plansz, jak i
  z pojedynczo zatwierdzonych cropów; pusty wymagany split blokuje dataset przed
  rozpoczęciem pierwszej epoki,
- zatwierdzony crop `virtual_source` jest pełnoprawnym źródłem treningowym bez
  konieczności tworzenia trwałego pliku cropa; kohorta musi zamrozić pełną
  checksum-bound proweniencję renderu, a builder przed treningiem odtwarza
  piksele z managed original i sprawdza ich checksumę RGB,
- brak źródła lub drift source geometry revision, render spec, zatwierdzonej
  proweniencji albo checksumy pikseli wyklucza próbkę fail-closed; nie wolno
  zastępować jej cropem legacy ani bieżącą geometrią,
- stały zestaw kontrolny nie może zostać włączony do treningu kolejnej wersji,
- raport pokazuje liczność per symbol, źródło i część podziału,
- brak wymaganej reprezentacji klasy blokuje promocję albo wymaga jawnego
  zaakceptowania ograniczenia przez właściciela.

## Read-only diagnoza residuali przed kolejną iteracją

Przed podjęciem decyzji o kolejnej iteracji można zamrozić osobną kohortę
diagnostyczną poprawnych cropów aktualnej wersji geometrii. Taka kohorta:

- zawiera wyłącznie kompletne `accepted/corrected`, dokładnie 15 komórek
  row-major i zweryfikowane checksumy źródeł oraz cropów,
- odrzuca starsze wersje croppera, niepewną geometrię i konflikt etykiety;
  wizualnie potwierdzony konflikt jest audytowalnym `OPEN`, a nie błędem modelu,
- stosuje deterministyczny, rozłączny split po rodzinie źródła,
- porównuje preprocessing treningowy z produkcyjnym wejściem ONNX dla każdej
  próbki,
- klasyfikuje każdy istotny residual jako M1, M2, P1 albo `OPEN` i kończy się
  jawną decyzją `retrain` albo `no-retrain`.

Diagnoza nie tworzy iteracji, nie uruchamia treningu i nie aktywuje modelu.
Decyzja `retrain` jest wyłącznie wejściem do osobnego, jawnego workflow.

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
- jeżeli istnieje kandydat `candidate_ready`, ale gra nie ma jeszcze aktywacji,
  nowy import i jawna reinferencja kończą się
  `SYMBOL_MODEL_ACTIVATION_REQUIRED`; bootstrap nie może wtedy po cichu
  zastąpić gotowego modelu gry,
- katalog klas aktywnego snapshotu musi być dokładnie zgodny z aktywnym
  katalogiem symboli gry; klasa spoza katalogu jest błędem integralności, a nie
  nierozpoznanym symbolem `?`,
- globalny bootstrap może zostać przypięty do nowego joba wyłącznie wtedy, gdy
  jego klasy są dokładnie zgodne z aktywnym katalogiem gry; w przeciwnym razie
  wymagany jest trening i jawna aktywacja modelu tej gry,
- poprzednia aktywna wersja pozostaje dostępna do kontrolowanego rollbacku.

### Historyczny kandydat v19 i bieżący aktywny model

Kohorta v19 obejmuje 321 kompletnych plansz, 4815 cropów, 41 rodzin źródeł i
sześć stagingów. Wytrenowany od początku kandydat poprawił accuracy całych
plansz o `5,8824 pp` i nie pogorszył recall żadnej klasy o więcej niż `1 pp`,
ale audyt 100 plansz wykrył jeden błąd `lemon -> orange` z confidence
`0,99999698`.

Ponieważ zaakceptowana bramka wymaga zera błędów o confidence co najmniej
`0,99`, ten historyczny kandydat ma status `rejected`. Nie wolno go aktywować
ani użyć do nowych importów. Odrzucenie jest wynikiem jakościowym, a nie
technicznym `failed`.

Nie jest to jednak bieżący aktywny snapshot gry. Późniejsza iteracja `#3`
`47b6aa0d-2cea-4765-97f0-ee1f86cfc056`, wytrenowana po stabilizacji splitu
`source-family-balanced-split-v2`, uzyskała `candidate_ready` i została
aktywowana 2026-08-19 jako aktywny model dla nowych jobów. Kolejna aktywacja
tego samego modelu jest idempotentnie odrzucana kodem
`SYMBOL_MODEL_ALREADY_ACTIVE`; aktywacja nowej iteracji nadal wymaga jawnej
decyzji i nowego niezmiennego raportu.

## Użycie nowego modelu

- nowy import przypina aktywną wersję modelu i jej checksumę w momencie
  tworzenia joba,
- aktywacja modelu podczas trwającego importu nie zmienia modelu używanego
  przez ten job,
- następny import używa już nowej aktywnej wersji,
- użytkownik może jawnie uruchomić `Przelicz oczekujące`, aby utworzyć nowe
  sugestie tylko dla nadal nierozwiązanych elementów,
- ponowna inferencja zapisuje nową rewizję predykcji; nie usuwa poprzedniej
  rewizji i nie zmienia rozstrzygnięć człowieka,
- ponowna inferencja obsługuje zarówno cropy plikowe, jak i bieżące cropy
  `virtual_source`; wirtualne piksele są odtwarzane z managed original dopiero
  po sprawdzeniu render spec, rewizji i checksummy, bez trwałego zapisu bitmapy.

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
