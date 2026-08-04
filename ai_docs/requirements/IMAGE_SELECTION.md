---
title: Fast representative image selection
status: accepted
release: "0.4"
last_updated: 2026-08-04
---

# Selekcja reprezentatywnych zdjęć

## Cel biznesowy

Przed właściwym `Importem layoutów` należy zredukować katalog do 100 000
zdjęć zawierających wiele ujęć tych samych ekranów do jednego użytecznego
zdjęcia na rozpoznany zakres sekwencji. Pełny pipeline geometrii, OCR wszystkich
plansz, cropów komórek i klasyfikacji symboli ma działać wyłącznie na wyniku
selekcji, a nie na wszystkich duplikatach wejściowych.

Przy 50–100 ujęciach jednego ekranu oczekiwane ograniczenie liczby wejść
pełnego pipeline'u wynosi około 50–100 razy. Moduł nie zastępuje właściwego
importu ani Reviewera; przygotowuje dla nich mniejszy, bezpieczny zestaw.

## Miejsce w produkcie

- Panel Admin otrzymuje czwarty główny workspace `Selekcja zdjęć`.
- Workspace korzysta z tego samego aktywnego kontekstu gry co pozostałe części
  Admina i zachowuje stan w URL.
- Selekcja jest osobnym jobem oraz osobnym stanem domenowym. Nie jest dodatkowym
  etapem widocznym wewnątrz `Importu layoutów`.
- Gotowy run udostępnia akcję `Przekaż do Importu layoutów`, która wykorzystuje
  istniejący właściwy pipeline bez ponownego wybierania całego folderu.
- Historyczny run zachowuje powiązanie z niezmiennym stagingiem. Użytkownik może
  uruchomić najnowszą wersję selektora dla tych samych załadowanych zdjęć bez
  ponownego uploadu; akcja tworzy osobny wersjonowany run i nie modyfikuje
  wcześniejszego wyniku ani decyzji ręcznych.
- Moduł stanowi zakres wersji 0.4 i przygotowuje kontrolowane wejście do pracy
  na dużych danych wersji 0.5. Nie zmienia historycznej bramki trzech
  workspace'ów wersji 0.2.

## Wejście i kolejność

- Użytkownik wybiera folder standardowym selektorem katalogu przeglądarki,
  zgodnym z działającym wyborem w `Imporcie layoutów`.
- Jeden run przyjmuje od 1 do 100 000 plików JPEG. Po wyborze folderu panel
  natychmiast pokazuje stan przygotowania listy, zanim rozpocznie się upload.
- Trwały stan uploadu ma rosnąć liniowo: metadane ukończonego pliku są
  dopisywane raz do dziennika, a odpowiedź pojedynczego uploadu zawiera tylko
  liczniki. System nie może przepisywać ani odsyłać całego dotychczasowego
  inventory po każdym zdjęciu.
- Obsługiwane są początkowo JPEG `.jpg` i `.jpeg`.
- Pliki są porządkowane deterministycznie według naturalnej kolejności
  względnej ścieżki, z uwzględnieniem liczbowych fragmentów nazwy; indeks
  wejścia zostaje zapisany w manifeście.
- Typowy ciąg 50–100 kolejnych plików przedstawia ten sam ekran, ale algorytm
  nie może wymagać stałej długości grupy.
- Zakresy ekranów nie muszą być ciągłe. Po `19–27` może wystąpić `400–408` i
  taki skok jest poprawną nową grupą.
- Algorytm nie szuka „oczekiwanego następnego” zakresu po całym folderze.
- Późniejsze zdjęcie zakresu, dla którego reprezentant został już wybrany, jest
  pomijane. Jeżeli wcześniejsza grupa nie dała reprezentanta, późniejsze dobre
  ujęcie tego samego zakresu może ją uzupełnić.
- Końcowy ekran może zawierać mniej niż dziewięć plansz. Zakres wynika z
  rzeczywiście rozpoznanych dodatnich `sequence_number`, a nie ze stałego kroku.

## Szybki proces automatyczny

Każdy plik przechodzi tani, bounded skan, który nie tworzy cropów 15 komórek i
nie uruchamia klasyfikatora symboli:

1. odczyt JPEG, EXIF i miniatury roboczej,
2. kontrola ostrości, ekspozycji, refleksów, zasłonięcia i obcięcia ekranu,
3. lekka detekcja plansz oraz spójności ich siatki,
4. wizualny fingerprint wyprostowanego ekranu,
5. punktowy/batchowy OCR numerów kotwiczących tylko wtedy, gdy trzeba ustalić
   zakres albo potwierdzić zmianę grupy,
6. przypisanie pliku do bieżącej grupy lub rozpoczęcie dowolnego nowego zakresu,
7. utrzymywanie pierwszego dostatecznie czytelnego kandydata oraz najwyżej kilku
   jakościowych kandydatów zapasowych zamiast obrazów w RAM,
8. dokładniejsza weryfikacja kandydatów w kolejności źródłowej przy zamknięciu
   grupy i zatrzymanie jej natychmiast po pierwszym jednoznacznym zakresie.

Zmiana grupy jest wykrywana z łącznego dowodu geometrii, fingerprintu oraz OCR.
Fingerprint jest porównywany zarówno ze stabilnymi reprezentantami grupy, jak i
z ostatnim kolejnym zdjęciem. Stopniowa zmiana kąta lub oświetlenia nie może sama
tworzyć serii krótkich grup. Brak wykrytej geometrii oznacza brak dowodu
geometrycznego, a nie maksymalną zmianę geometrii.
Sam niepewny OCR nie może połączyć dwóch różnych ekranów ani samodzielnie nadać
zakresu. Wyjątkiem jest pojedyncza nierozpoznana grupa w jednoznacznej luce
maksymalnie dziewięciu layoutów pomiędzy dwoma pewnymi zakresami. W takim
przypadku selektor może wyprowadzić brakujący zakres z obu sąsiadów.

## Ocena jakości i wybór

- Uszkodzony albo niedekodowalny plik, błąd skanu oraz sprzeczny zakres pozostają
  twardą blokadą automatycznego wyboru. Zasłonięcie, rozmycie i słaba jakość
  plansz są sygnałami rankingowymi, nie powodem odrzucenia najlepszego
  dostępnego zdjęcia, jeżeli zakres numerów jest jednoznacznie czytelny albo
  wynika dokładnie z ograniczonej luki między pewnymi kotwicami.
- Progi jakości, takie jak ekspozycja, refleksy, perspektywa i margines, są
  sygnałami rankingu i ograniczonego fallbacku. V8 celowo wybiera pierwsze
  dostatecznie czytelne zdjęcie z jednoznacznym zakresem; nie wykonuje OCR
  kolejnych zdjęć tylko po to, aby znaleźć nieznacznie lepszy obraz. Do
  następnego zachowanego kandydata przechodzi dopiero, gdy poprzedni nie daje
  zakresu albo kończy się twardym błędem.
- Ranking obejmuje co najmniej kompletność geometrii, ostrość, ekspozycję,
  clipping świateł, refleksy, perspektywę, margines ekranu i confidence zakresu.
- Oczekiwana liczba widocznych plansz wynika z konsensusu dobrych zdjęć grupy;
  zapobiega to uznaniu zasłoniętych ośmiu plansz za poprawną stronę końcową.
- Wybór jest deterministyczny. Remis rozstrzyga wcześniejszy `order_index`, a
  następnie checksum SHA-256.
- Run przechowuje pełne metryki, powody odrzucenia oraz wersję selektora.
- Wybór mimo ostrzeżeń jakości jest oznaczony `QUALITY_BEST_AVAILABLE`, a zakres
  wyprowadzony z jednej bounded luki — `RANGE_INFERRED_FROM_BOUNDED_GAP`.
- Przycięta rama, słaba ekspozycja, niepełna geometria i brak bezpośredniego OCR
  zakresu nie blokują próby dalszego cięcia, jeżeli dokładnie jedna grupa leży
  pomiędzy dwoma pewnymi zakresami, luka obejmuje najwyżej dziewięć layoutów, a
  istnieje dekodowalny kandydat. Selektor
  wybiera wtedy najlepsze dostępne zdjęcie i przekazuje je w wyniku z zakresem
  wyprowadzonym z obu sąsiadów.
- Użytkownik widzi liczbę plików przeskanowanych, rozpoznane zakresy,
  automatyczne wybory, odrzucone zdjęcia, duplikaty i grupy wymagające decyzji.
- Podczas skanowania licznik takich grup jest wstępny, ponieważ końcowe
  odzyskiwanie jednoznacznych luk może go zmniejszyć. UI nazywa go wtedy
  `Wstępnie nierozpoznane`; dopiero terminalny wynik używa nazwy
  `Nierozpoznane zestawy`.

## Zestaw wynikowy i bezpieczeństwo plików

- Moduł nigdy nie usuwa, nie przenosi ani nie zmienia plików w folderze
  wskazanym przez użytkownika.
- Wybrane zdjęcia są kopiowane do kontrolowanego katalogu wyniku i wiązane z
  checksumowanym manifestem.
- Nazwa ma prostą postać `seq_<start>-<end>.jpg`, na przykład
  `seq_1-9.jpg`. Unikalność zakresu w ramach runu gwarantuje domena, dlatego
  checksum nie jest potrzebny w nazwie przeznaczonej dla użytkownika.
- Zakresy zaczynają się od dodatniego numeru; nazwa `seq_0-9` nie może tworzyć
  niedozwolonego domenowo `sequence_number = 0`.
- Manifest przechowuje oryginalną względną nazwę, checksumę, kolejność,
  rozpoznany zakres, metryki jakości, sposób `automatic | manual`, wersję
  algorytmu i ścieżkę kopii wynikowej.
- Baza przechowuje ścieżki, checksumy i metadane, nie duże obrazy BLOB.
- Po publikacji użytkownik może wskazać standardowym pickerem przeglądarki
  folder docelowy i skopiować do niego wszystkie zweryfikowane zdjęcia.
  Kontrolowany, content-addressed katalog serwera pozostaje źródłem handoffu i
  nie zależy od dostępu przeglądarki do wybranego folderu.
- Tymczasowe kopie uploadu nie są folderem źródłowym użytkownika. Po atomowym
  zapisaniu kompletnego wyniku mogą zostać usunięte; przy błędzie pozostają do
  retry, a przy anulowaniu są usuwane na jawne polecenie użytkownika.

## Manualne uzupełnienie

Jeżeli grupa nie ma bezpiecznego automatycznego reprezentanta, po zakończeniu
skanu otwierana jest kolejka decyzji w modalu.

Header modala pokazuje:

- `zatwierdzone / wszystkie wymagające decyzji`,
- rozpoznany zakres, na przykład `400–408`, albo czytelne
  `Zakres layoutów nierozpoznany`,
- deterministyczny numer zestawu, liczbę zdjęć źródłowych oraz nazwy zapisanych
  kandydatów, aby użytkownik mógł odnaleźć właściwą serię w swoim folderze,
- przyciski poprzedni/następny,
- mały przycisk `Zatwierdź`.

Zachowanie klawiatury:

- `ArrowLeft` i `ArrowRight` wyłącznie nawigują między brakującymi grupami,
- `Enter` zatwierdza zakres; jeśli wskazano JPEG, zapisuje reprezentanta, a bez
  pliku zapisuje jawny brak zdjęcia,
- strzałki nie zapisują decyzji,
- zatwierdzoną pozycję można później ponownie otworzyć i zmienić.

Body udostępnia standardowy selektor pojedynczego pliku JPEG jako opcjonalne
uzupełnienie. Wybrany plik jest kopiowany do właściwego katalogu wyniku, ale
jego brak nie blokuje zakończenia selekcji ani przekazania pozostałych zdjęć do
importu. Główna akcja `Kontynuuj z wybranymi zdjęciami` oznacza wszystkie
nierozwiązane grupy jako `missing_image` i wznawia publikację pewnych wyborów.
Dla nierozpoznanej grupy zakres może pozostać pusty: system zapisuje wtedy
pominięty nierozpoznany zestaw i nie wymyśla numeracji layoutów. UI pokazuje
wtedy `Zakres layoutów nierozpoznany`, numer zestawu i nazwy plików-kandydatów;
numer zestawu identyfikuje kolejność źródeł, ale nie jest numerem layoutu.
Jeżeli zakres jest znany, UI pokazuje informację w formacie `Brak zdjęcia dla
layoutów 1–9`.
Panel może wstępnie uzupełnić zakres wyłącznie wtedy, gdy grupa leży między
dwoma rozpoznanymi zakresami, a luka jest dodatnia i obejmuje najwyżej dziewięć
layoutów, np. `64–72`, brak, `82–90` daje sugestię `73–81`. Użytkownik nadal
zatwierdza tę decyzję; większy skok ani więcej niż jedna nierozwiązana grupa w
tej samej luce nie tworzą sugestii. Zbiorcze `Kontynuuj z wybranymi zdjęciami`
nigdy nie utrwala sugestii — zapisuje brak zdjęcia bez zakresu.

Po zatwierdzeniu albo oznaczeniu braku zdjęcia dla ostatniej nierozwiązanej
grupy ten sam job w stanie
`waiting_for_review` jest automatycznie wznawiany od zapisanego checkpointu.
Użytkownik nie przechodzi do `Jobów` i nie klika ręcznie `Ponów`. Automatyczne
wznowienie nie dotyczy joba `failed`; taki błąd nadal wymaga jawnej decyzji.

## Integracja z Importem layoutów

- Run może zostać przekazany dalej po jawnej decyzji użytkownika o
  kontynuowaniu; nierozpoznane grupy stają się terminalnym `missing_image`, a
  wynik może świadomie zawierać wyłącznie pewne automatyczne lub ręczne wybory.
- Handoff tworzy serwerowo poświadczone źródło wejściowe dla istniejącego
  `image_directory` importu i zachowuje identyfikator runu, manifest oraz
  checksumy wybranych zdjęć.
- Użytkownik nadal jawnie uruchamia `Rozpocznij import`; selekcja nie uruchamia
  automatycznie ciężkiego pipeline'u.
- Retry właściwego importu nie powtarza selekcji, jeżeli jej manifest i pliki
  nadal przechodzą weryfikację checksum.
- Wyniki selekcji nie tworzą layoutów, symboli, review ani datasetu.

## Wydajność i bramka jakości

- Nowe runy używają `fast-image-selector-v8`. Granica serii jest oceniana na
  podstawie kolejnych obserwacji i bounded dwuklatkowego potwierdzenia; stary,
  podobny obraz zapisany w `topK` nie może zablokować późniejszej rzeczywistej
  zmiany strony.
- V6, v7 i v8 odzyskują również kilka kolejnych grup bez numerów pomiędzy
  dwiema pewnymi kotwicami, jeżeli cała luka ma dokładnie
  `liczba grup × 9` layoutów. Każda odzyskana grupa dostaje kolejny pełny zakres
  i najlepsze bezpieczne zdjęcie.
  Projekcja jest aktualizowana od razu po pojawieniu się prawej kotwicy, aby
  roboczy licznik bez numerów malał podczas skanowania.
- Produkcyjny fallback numerów obejmuje wszystkie trzy rzędy etykiet, dopuszcza
  numery wielocyfrowe do co najmniej sześciu cyfr i ogranicza liczbę kandydatów
  przed OCR. Zakres nadal jest zatwierdzany fail-closed przez zgodną siatkę i
  homografię RANSAC.
- Pełna weryfikacja v5 może użyć istniejącego, ograniczonego odzyskiwania siatki,
  gdy detektor widzi tylko część poprawnie rozmieszczonych plansz. Tani skan nie
  wykonuje tego odzyskiwania.
- V7 rozszerza detekcję jasnych etykiet o przyciemnione oraz ciepło zabarwione
  numery, nadal wymagając zgodnego układu przestrzennego i homografii RANSAC.
  Jeżeli numery zakresu są jednoznaczne, jakość plansz decyduje o rankingu, ale
  nie blokuje przekazania zdjęcia do późniejszego cięcia i ręcznego uzupełnienia.
- Ponowne przeliczenie istniejącego stagingu weryfikuje checksum jego manifestu
  przed utworzeniem joba. Dla tej samej gry, manifestu i fingerprintu jest
  idempotentne; nowa wersja selektora tworzy nowy run bez kopiowania zdjęć.
- Jeżeli run aktualnego fingerprintu ma status `cancelled` albo `failed`, ta
  sama akcja ponownie ustawia jego job w kolejce i zachowuje trwały checkpoint.
  Nie może tylko przywrócić terminalnej karty bez uruchomienia pracy.
- Skan jest strumieniowy i nie przechowuje pełnych obrazów całego katalogu w
  pamięci.
- Produkcyjny worker może równolegle obliczać tani skan małego bounded okna, ale
  obserwacje muszą być konsumowane dokładnie według naturalnego `order_index`.
  Domyślna konfiguracja to cztery wątki i najwyżej osiem zleconych zdjęć.
- Pełny OCR plansz, cropy komórek i symbol inference są zabronione w selektorze.
- Liczba kosztowniejszych weryfikacji jest bounded liczbą grup i top-k, a nie
  liczbą wszystkich zdjęć. Dla v8 typowy koszt wynosi jedną pełną weryfikację na
  grupę; `topK` pozostaje wyłącznie ograniczonym fallbackiem, gdy wcześniejsze
  zdjęcie nie daje jednoznacznego zakresu.
- Provisionalny budżet na komputerze właściciela wynosi maksymalnie 15 minut dla
  10 000 oraz 45 minut dla 30 000 zdjęć. TASK-0157 może obniżyć budżet po
  pomiarach, ale nie może zaakceptować procesu trwającego wiele godzin.
- Limit wejścia 100 000 jest kontraktem funkcjonalnym. Profil 100 000 nie jest
  częścią odbioru 0.4; pierwszy rzeczywisty przebieg właściciela dostarcza
  obserwację operacyjną bez rozszerzania zaliczonej bramki benchmarkowej 30 000.
- Peak RSS workera ma pozostać bounded i zmierzony; brak wyniku benchmarku
  blokuje użycie modułu na pełnym katalogu.
- Golden grup nie dopuszcza fałszywego scalenia dwóch zakresów. Wielogrupowa
  luka jest automatyczna tylko przy dokładnym podziale na pełne strony po 9.
  Niepasująca liczba layoutów, brak jednej z kotwic albo skok numeracji pozostają
  `manual_required`; system nie może deklarować fałszywych 100% rozpoznania.

## Poza zakresem

- usuwanie lub reorganizowanie folderu użytkownika,
- rozpoznawanie symboli i tworzenie cropów komórek,
- trenowanie modelu podczas selekcji,
- wymaganie ciągłości zakresów pomiędzy grupami,
- Redis, Celery, usługa chmurowa lub osobny mikroserwis,
- automatyczne rozpoczęcie pełnego importu bez decyzji użytkownika.
