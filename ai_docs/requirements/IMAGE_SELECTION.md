---
title: Fast representative image selection
status: accepted
release: "0.4"
last_updated: 2026-08-05
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
- Joby selekcji są konsumowane przez dedykowany lokalny worker lane. Ogólny
  worker obsługujący `Import layoutów` nie może przejąć `image_selection`, więc
  oba procesy mogą działać równolegle bez zmiany URL panelu ani API.
- Gotowy run udostępnia akcję `Przekaż do Importu layoutów`, która wykorzystuje
  istniejący właściwy pipeline bez ponownego wybierania całego folderu.
- Historyczny run zachowuje powiązanie z niezmiennym stagingiem. Użytkownik może
  uruchomić najnowszą wersję selektora dla tych samych załadowanych zdjęć bez
  ponownego uploadu; akcja tworzy osobny wersjonowany run i nie modyfikuje
  wcześniejszego wyniku ani decyzji ręcznych.
- Dropdown roboczy pokazuje runy aktywne oraz użyteczne: `created`, `processing`,
  `completed` i pełne `waiting_for_review`. Runy `cancelled`, `failed` oraz
  terminalne z niepełnym postępem pozostają w audycie jobów, ale nie wracają do
  selektora zapisanej partii.
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

Każdy plik przechodzi naprawdę lekki, bounded skan. Jego jedynym celem jest
wykrycie kolejnych wizualnie różnych ekranów i wybór jednego zdjęcia z każdej
serii. Skan:

1. odczytuje JPEG bezpośrednio w zmniejszonej rozdzielczości oraz stosuje EXIF,
2. oblicza lekki deskryptor wyglądu z perceptual hash, histogramu HSV i
   uproszczonej informacji o krawędziach,
3. mierzy tylko tanie sygnały wyboru: ostrość, ekspozycję, przepalenie i
   podstawową widoczność centralnego ekranu,
4. porównuje kolejne obserwacje w naturalnym `order_index`,
5. potwierdza zmianę ekranu co najmniej dwiema kolejnymi obserwacjami,
6. utrzymuje pierwszego dostatecznie czytelnego kandydata i najwyżej jeden
   jakościowy fallback zamiast obrazów w RAM,
7. wybiera pierwszego użytecznego reprezentanta, a przy jego braku najlepszy
   dekodowalny obraz z ostrzeżeniem.

W `Selekcji zdjęć` zabronione są OCR numerów, detekcja plansz, homografia,
wyprostowanie strony, cropy komórek i klasyfikacja symboli. Kąt kamery, refleks
albo płynna zmiana ekspozycji nie mogą same tworzyć serii krótkich grup.
Algorytm porównuje bezpośredniego poprzednika oraz bounded opis bieżącej grupy,
ale nie przewiduje następnego numeru ani stałej długości serii.

Selekcja nie ustala zakresu `sequence_number`. Kolejność grupy jest technicznym
`groupOrder`, a nie numerem layoutu. OCR, dokładna geometria, zakresy i
deduplikacja po numerach należą wyłącznie do późniejszego `Importu layoutów`.

## Ocena jakości i wybór

- Uszkodzony albo niedekodowalny plik oraz twardy błąd integralności blokują
  wybór tego pliku, lecz nie kończą całego runu.
- Ostrość, ekspozycja, clipping i podstawowa widoczność są miękkimi sygnałami
  rankingu. Nie służą do odrzucenia całej grupy.
- Selekcja wybiera pierwsze dostatecznie czytelne zdjęcie. Nie przegląda całej
  serii tylko po to, aby znaleźć marginalnie lepszy kadr.
- Gdy żaden obraz nie spełnia miękkiego progu, system wybiera najlepszy
  dekodowalny kandydat i dodaje `QUALITY_BEST_AVAILABLE`.
- Wybór jest deterministyczny. Remis rozstrzyga wcześniejszy `order_index`, a
  następnie checksum SHA-256.
- Run przechowuje lekkie metryki, powody ostrzeżeń i wersję selektora.
- Niepewnego, niekolejnego podobieństwa nie używa się do trwałego usunięcia
  późniejszej grupy. Import może bezpiecznie odrzucić duplikat dopiero po
  odczytaniu rzeczywistego zakresu.
- Użytkownik widzi liczbę przeskanowanych plików, wybrane grupy, błędy JPEG,
  ewentualne dodatkowe podziały i redukcję wejścia dla Importu layoutów.

## Zestaw wynikowy i bezpieczeństwo plików

- Moduł nigdy nie usuwa, nie przenosi ani nie zmienia plików w folderze
  wskazanym przez użytkownika.
- Wybrane zdjęcia są kopiowane do kontrolowanego katalogu wyniku i wiązane z
  checksumowanym manifestem.
- Przed OCR nazwa ma postać `selection_<groupOrder>.jpg`. Nie może zawierać
  zgadywanego zakresu ani przedstawiać `groupOrder` jako `sequence_number`.
- Po rozpoznaniu zakresu przez `Import layoutów` właściwy pipeline może nadać
  nazwę lub mapowanie `seq_<start>-<end>` bez mutowania historycznego outputu
  selekcji.
- Manifest przechowuje oryginalną względną nazwę, checksumę, kolejność,
  opcjonalny późniejszy zakres, metryki jakości, sposób `automatic | manual`,
  wersję algorytmu i ścieżkę kopii wynikowej.
- Baza przechowuje ścieżki, checksumy i metadane, nie duże obrazy BLOB.
- Po publikacji użytkownik może wskazać standardowym pickerem przeglądarki
  folder docelowy i skopiować do niego wszystkie zweryfikowane zdjęcia.
  Kontrolowany, content-addressed katalog serwera pozostaje źródłem handoffu i
  nie zależy od dostępu przeglądarki do wybranego folderu.
- Uchwyt folderu wynikowego jest zapamiętywany lokalnie per gra i run. Po
  ponownym otwarciu przeglądarka żąda odnowienia uprawnienia, jeżeli jest to
  konieczne, a przed ręcznym review uzgadnia wszystkie zakończone grupy.
- Ręczna decyzja może przejść do następnej grupy dopiero po zapisaniu JPEG-a w
  folderze wynikowym. Błąd dysku pozostawia widoczne ponowienie tej samej
  idempotentnej decyzji.
- Tymczasowe kopie uploadu nie są folderem źródłowym użytkownika. Po atomowym
  zapisaniu kompletnego wyniku mogą zostać usunięte; przy błędzie pozostają do
  retry, a przy anulowaniu są usuwane na jawne polecenie użytkownika.

## Manualne uzupełnienie

Standardowy run wybiera reprezentanta dla każdej grupy zawierającej co najmniej
jeden dekodowalny JPEG. Manualne uzupełnienie pozostaje awaryjne dla grup bez
użytecznego pliku albo świadomej korekty użytkownika, nie jako obowiązkowy etap
rozpoznawania numerów.

Header modala pokazuje:

- `zatwierdzone / wszystkie wymagające decyzji`,
- techniczną kolejność grupy, bez przedstawiania jej jako numeru layoutu,
- deterministyczny numer zestawu, liczbę zdjęć źródłowych oraz nazwy zapisanych
  kandydatów, aby użytkownik mógł odnaleźć właściwą serię w swoim folderze,
- przyciski poprzedni/następny,
- mały przycisk `Zatwierdź`.

Zachowanie klawiatury:

- `ArrowLeft` i `ArrowRight` wyłącznie nawigują między brakującymi grupami,
- `Enter` zatwierdza wskazany JPEG albo jawny brak zdjęcia,
- strzałki nie zapisują decyzji,
- zatwierdzoną pozycję można później ponownie otworzyć i zmienić.

Body udostępnia standardowy selektor pojedynczego pliku JPEG jako opcjonalne
uzupełnienie. Wybrany plik jest kopiowany do właściwego katalogu wyniku, ale
jego brak nie blokuje zakończenia selekcji ani przekazania pozostałych zdjęć do
importu. Główna akcja `Kontynuuj z wybranymi zdjęciami` oznacza wszystkie
nierozwiązane grupy jako `missing_image` i wznawia publikację pewnych wyborów.
UI pokazuje `Grupa wyboru N`, liczbę źródeł i nazwy plików-kandydatów. Numer
grupy identyfikuje kolejność źródeł, ale nie jest numerem layoutu ani zakresem.
Selekcja nie proponuje zakresu na podstawie sąsiadów. Numerację i ewentualne
luki rozstrzyga `Import layoutów` po uruchomieniu właściwego OCR.

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
- Manifest wejściowy może nie zawierać zakresów. `Import layoutów` jest źródłem
  prawdy dla OCR numerów, geometrii plansz, cropów oraz deduplikacji zakresu.
- Użytkownik nadal jawnie uruchamia `Rozpocznij import`; selekcja nie uruchamia
  automatycznie ciężkiego pipeline'u.
- Retry właściwego importu nie powtarza selekcji, jeżeli jej manifest i pliki
  nadal przechodzą weryfikację checksum.
- Wyniki selekcji nie tworzą layoutów, symboli, review ani datasetu.

## Wydajność i bramka jakości

- Nowe runy od aktywacji 2026-08-05 używają `fast-image-selector-v9` o
  fingerprintcie
  `eaca91fd6f6c169f25436a81b1059810152899953d3eecdef980391df7124afb`.
  Istniejące runy zachowują zapisany fingerprint v2–v8 i są wznawiane przez
  odpowiadający mu niezmienny manifest.
- Lekki skan dekoduje JPEG bezpośrednio w zmniejszonej rozdzielczości i nie
  uruchamia geometrii ani OCR.
- Granica serii jest oceniana z wyglądu kolejnych obserwacji oraz bounded
  dwuklatkowego potwierdzenia. Zmiana kąta nie może sama utworzyć wielu grup.
- Priorytetem jest zero fałszywych scaleń różnych ekranów. Dodatkowy false split
  jest bezpieczniejszy niż utrata unikalnego zdjęcia i zostanie później
  rozwiązany przez Import po pewnym zakresie.
- Ponowne przeliczenie istniejącego stagingu weryfikuje checksum jego manifestu
  przed utworzeniem joba. Dla tej samej gry, manifestu i fingerprintu jest
  idempotentne; nowa wersja selektora tworzy nowy run bez kopiowania zdjęć.
- Jeżeli run aktualnego fingerprintu ma status `cancelled` albo `failed`, ta
  sama akcja ponownie ustawia jego job w kolejce i zachowuje trwały checkpoint.
  Nie może tylko przywrócić terminalnej karty bez uruchomienia pracy.
- Skan jest strumieniowy i nie przechowuje pełnych obrazów całego katalogu w
  pamięci.
- Najwyżej jeden job selekcji działa jednocześnie. Jego lane jest niezależny od
  pojedynczego lane ogólnych jobów; rozdzielenie usuwa blokowanie kolejki, ale
  nie gwarantuje braku konkurencji o CPU, RAM i dysk.
- Workspace `Joby` pokazuje niezależnie stan procesu general i selekcji także
  przy pustych kolejkach. Status wynika z trwałego heartbeat procesu, nie z
  obecności joba, i rozróżnia `działa`, `brak świeżego sygnału` oraz
  `zatrzymany`.
- Supervisor nadaje obu procesom jawne budżety wątków. W 0.4 są to limity
  współbieżności bibliotek i prefetch, a nie gwarancja dokładnego procentu CPU.
- Produkcyjny worker może równolegle obliczać bounded okno lekkich obserwacji,
  ale wyniki są konsumowane dokładnie według naturalnego `order_index`.
  Liczba scan workers oraz wewnętrznych wątków OpenCV wynika z benchmarku i nie
  może powodować zagnieżdżonej nadsubskrypcji CPU.
- OCR, `PageBoardDetector`, homografia, cropy komórek i symbol inference mają
  dokładnie zero wywołań w selektorze.
- Wersjonowany cache lekkiej obserwacji może przyspieszać retry i rerun, ale nie
  jest źródłem prawdy i nie zastępuje końcowej weryfikacji checksumy wybranego
  pliku.
- Cache jest kluczowany checksumą JPEG-a i fingerprintem wyłącznie tych
  adapterów oraz parametrów, które tworzą lekką obserwację. Zmiana zasad
  grupowania może wykorzystać zgodny wpis, natomiast zmiana dekodera,
  deskryptora, metryk jakości lub pliku zawsze powoduje miss.
- Wpis zawiera wyłącznie bounded metryki i deskryptor. Nie zawiera obrazu,
  ścieżki źródłowej, OCR ani geometrii właściwego Importu layoutów. Uszkodzony
  wpis jest pomijany i atomowo odbudowywany bez przerywania selekcji.
- Diagnostyka runu raportuje hit, miss, nieprawidłowe wpisy, błędy zapisu oraz
  szacowany czas zaoszczędzony na podstawie czasu pierwszego skanu.
- Krótkie profile realnego pierwszego przebiegu raportują throughput i regresje,
  zanim zostanie uruchomiona pełna próba 40 000 zdjęć.
- Finalna bramka nie ma z góry ustalonego limitu czasu. System zapisuje pełny
  czas, throughput, peak RSS i jakość wyniku dla 40 000 zdjęć, a właściciel
  decyduje, czy wynik jest satysfakcjonujący i czy można zamknąć bramkę.
- Limit wejścia 100 000 jest kontraktem funkcjonalnym. Profil 100 000 nie jest
  częścią odbioru 0.4; pierwszy rzeczywisty przebieg właściciela dostarcza
  obserwację operacyjną bez rozszerzania zaliczonej bramki benchmarkowej 30 000.
- Peak RSS workera ma pozostać bounded i zmierzony; brak wyniku benchmarku
  blokuje użycie modułu na pełnym katalogu.
- Golden grup nie dopuszcza fałszywego scalenia dwóch różnych kolejnych
  ekranów. Nie mierzy dokładności zakresu, ponieważ zakres nie jest wynikiem
  selekcji v9.

## Poza zakresem

- usuwanie lub reorganizowanie folderu użytkownika,
- rozpoznawanie symboli i tworzenie cropów komórek,
- trenowanie modelu podczas selekcji,
- wymaganie ciągłości zakresów pomiędzy grupami,
- Redis, Celery, usługa chmurowa lub osobny mikroserwis,
- automatyczne rozpoczęcie pełnego importu bez decyzji użytkownika.

## Korekta jakościowa v10 — 2026-08-08

Poniższe reguły zastępują sprzeczne założenia v9 dotyczące pierwszego
„wystarczającego” zdjęcia i zerowego OCR:

- selekcja nadal nie rozpoznaje symboli i nie tworzy cropów komórek; te prace
  należą do późniejszego `Importu layoutów`,
- każde zdjęcie grupy otrzymuje lekki scoring, a maksymalnie 12 najlepszych
  kandydatów przechodzi dokładną ocenę pełnej rozdzielczości,
- wybór następuje dopiero po przejrzeniu całej grupy; early exit po pierwszym
  akceptowalnym zdjęciu jest zabroniony,
- jakość i poprawność numeru mają pierwszeństwo przed czasem wykonania,
- przed startem użytkownik wybiera katalog wejściowy, katalog wynikowy,
  kierunek `rosnąco | malejąco` oraz opcjonalny pierwszy numer,
- bez numeru początkowego pierwszy zakres jest rozpoznawany automatycznie; po
  ustaleniu kotwicy kolejne zakresy wynikają z porządku bez luk,
- zdjęcia pozostają w naturalnym porządku folderu także dla kierunku malejącego;
  odwracana jest wyłącznie interpretacja numerów,
- każdy zatwierdzony automatycznie wynik jest zapisywany do wybranego katalogu
  podczas trwania runu, a nie dopiero po jego końcu,
- nazwa pliku ma historyczny format `seq_<od>-<do>.jpg`, np.
  `seq_1-9.jpg`; zakres w nazwie zawsze jest kanonicznie rosnący,
- istniejący plik o innej zawartości nie może zostać nadpisany,
- pomiar 500/5000 jest poglądowy. Odbiór jakości i czasu wykonuje właściciel
  ręcznie najpierw na około 5000, a następnie około 32 000 zdjęć. Czas 3–5 razy
  dłuższy od v9 jest dopuszczalny, jeżeli jakość wyboru jest wyższa.

## Korekta wydajnościowa v10.1 — 2026-08-08

### Korekta spójności i ręcznego odzyskiwania — 2026-08-09

- Zakres zapisany w nazwie `seq_<start>-<end>.jpg` musi być zgodny z numerami
  widocznymi na wybranym reprezentancie. Dowodu OCR z jednej klatki nie wolno
  bez dodatkowej kontroli przypisać reprezentantowi przedstawiającemu inny
  ekran.
- Jeżeli grupa zawiera zdjęcia co najmniej dwóch zakresów, selektor dzieli ją
  ponownie albo oznacza konflikt do ręcznej decyzji. Nie może wyeksportować
  pliku z pewną, ale niezgodną nazwą.
- Dopuszczalna jest niewielka utrata automatycznego recall lub dodatkowy
  `manual_required`, jeżeli daje istotny zysk czasu. Niedopuszczalny pozostaje
  automatyczny wybór zdjęcia z błędnym zakresem.
- Automatyczna selekcja może ograniczać kosztowne próby po spełnieniu
  mierzalnej bramki jakości, ale zawsze analizuje pełną grupę lekkim scoringiem
  i zachowuje najlepszych kandydatów do ręcznego wyboru.
- Workspace przechowuje historię runów dla aktywnej gry. Użytkownik może wrócić
  do zakończonego, anulowanego albo oczekującego na review joba i kontynuować
  jego ręczne braki bez ponownego uploadu.
- Dla nowych runów ręczny review zachowuje lekkie metadane każdego zdjęcia
  należącego do zakończonej grupy i pokazuje całą grupę jako lazy-load
  miniatury. JPEG pozostaje pojedynczym plikiem w stagingu; baza nie przechowuje
  jego kopii. Kliknięcie miniatury otwiera pełny podgląd, a `Zatwierdź` wybiera
  istniejący plik bez ręcznego szukania go w katalogu źródłowym.
- Lista miniaturek ma własny, widoczny obszar przewijania, aby wszystkie
  zachowane zdjęcia grupy pozostały dostępne także na niższym ekranie. Wybrany
  JPEG można otworzyć na całym ekranie i przełączyć między dopasowaniem a jednym
  poziomem powiększenia do kontroli numerów oraz layoutów.
- Po wczytaniu galerii modal wskazuje domyślnego kandydata, ale nie zapisuje go
  bez świadomej akcji użytkownika. Dla grup do 20 zdjęć wskazuje środkowy JPEG,
  a dla większych grup dziesiąty JPEG w deterministycznej kolejności galerii.
- `Enter`, strzałka w prawo i przycisk `Zatwierdź` zapisują aktualnie wskazany
  JPEG idempotentnie i przechodzą do następnej nierozwiązanej grupy. Strzałka w
  lewo jedynie wraca. Podczas ładowania domyślnego kandydata nie wolno omyłkowo
  zapisać decyzji `bez zdjęcia`.
- Nagłówek ręcznej galerii raportuje osobno liczbę wybranych zdjęć, pominiętych
  grup i grup pozostałych do decyzji. Ponowne otwarcie modala zaczyna od
  pierwszej nierozwiązanej grupy; wcześniejsze wybory i pominięcia pozostają
  dostępne do korekty.
- Każdy run z automatycznie wybranymi grupami udostępnia osobną akcję
  `Weryfikuj wybory algorytmu`. Korzysta ona z tej samej przewijanej galerii,
  pełnego podglądu i zoomu, pokazuje wszystkie zachowane zdjęcia grupy oraz
  jednoznacznie oznacza reprezentanta wskazanego przez algorytm.
- Weryfikacja automatycznych wyborów jest na tym etapie trybem tylko do odczytu.
  Kliknięcie innej miniatury służy porównaniu, ale nie zmienia decyzji runu,
  pliku wynikowego ani katalogu eksportu. Strzałki przechodzą między grupami.
- Historyczny run utworzony przed tą korektą może mieć zachowane wyłącznie
  top-12. Modal pokazuje wtedy licznik `zachowane / wszystkie` i jasną informację
  o ograniczeniu; opcjonalny upload pojedynczego JPEG-a pozostaje drogą
  uzupełnienia takiej grupy.
- Header galerii pokazuje run, numer grupy, rozpoznany albo nierozpoznany zakres,
  liczbę źródeł oraz postęp `rozwiązane / wymagające decyzji`.
- Ręczne wskazanie pliku spoza zachowanej shortlisty pozostaje opcjonalnym
  fallbackiem.
- Zatwierdzony ręcznie kandydat jest natychmiast i idempotentnie dopisywany do
  katalogu wynikowego powiązanego z danym runem. Powrót do joba uzupełnia luki,
  nie kopiuje ponownie istniejących plików i nigdy ich po cichu nie nadpisuje.
- Liczba pominiętych grup jest raportowana oddzielnie od liczby pominiętych
  zdjęć. Każda grupa `manual_required` lub `missing_image` pozostaje dostępna w
  historii joba, aby można było wrócić do niej po zakończeniu automatycznej
  selekcji i uzupełnić katalog wynikowy.
- Status `skipped_existing_range` oznacza duplikat rozpoznanego zakresu, a nie
  brak zdjęcia. UI pokazuje osobno: duplikaty, grupy bez dowodu zakresu, konflikty
  zakresu oraz pliki niedekodowalne.

### Korekta recall v10.3 — 2026-08-10

- Automatyczna nazwa nadal wymaga, aby ten sam wynikowy JPEG rozpoznał dokładnie
  zakres grupy z confidence co najmniej `0.90`. Konsensusu innego zdjęcia nie
  wolno bezwarunkowo przenosić na reprezentanta.
- Jeżeli własny odczyt JPEG-a jest dokładnie zgodny z konsensusem, niepełna
  geometria, niepełny kadr, ekspozycja albo różnica liczby wykrytych plansz są
  miękkim problemem jakości. Selektor wybiera najlepszy taki JPEG zamiast
  kierować całą grupę do ręcznego review.
- Inny zakres, brak wiarygodnego odczytu, konflikt zakresów, rozmycie, okluzja
  oraz techniczny błąd skanu lub weryfikacji pozostają twardą blokadą
  automatycznego eksportu.
- Wynik wybrany przez miękką bramkę zachowuje kod powodu
  `RANGE_COHERENT_BEST_AVAILABLE`, aby jakość można było audytować i później
  poprawiać bez podważania poprawności nazwy.
- Historyczne runy v10.2 nie zmieniają decyzji. Nowe zachowanie ma osobną wersję
  i fingerprint; wymaga przeładowania procesu workera przed utworzeniem runu.

### Hybrydowa selekcja v10.4 — 2026-08-11

- Każdy nowy run v10.4 wymaga dodatniego `first_sequence_number`. Pole pozostaje
  opcjonalne w historycznym modelu danych, aby starsze runy zachowały swoje
  zachowanie, ale panel, API, skrypt live i tryb standalone nie mogą utworzyć
  nowego przebiegu v10.4 bez tej kotwicy.
- Kotwica ustala zakres pierwszej grupy. Dalsze grupy nadal wymagają lokalnego
  dowodu OCR albo jednoznacznej, ograniczonej luki; nie wolno przesuwać wszystkich
  kolejnych nazw wyłącznie na podstawie kursora.
- Deskryptor grupowania obejmuje centralny obszar siatki layoutów. Klasyfikacja
  zmiany ekranu porównuje kandydatów z ostatnim stabilnym obrazem starej grupy;
  bufor nowych klatek nie musi być wzajemnie podobny, ponieważ zmiana perspektywy
  nie może dołączać pierwszego zdjęcia następnego ekranu do poprzedniej grupy.
- Domyślny OCR dopasowuje siatkę `3×3` etykiet i wykonuje najwyżej jeden batch
  dziewięciu cropów na analizowany JPEG. Maksymalnie dwa najlepsze JPEG-i grupy
  dostarczają dowodu zakresu, więc zwykła grupa wykonuje najwyżej 18 cropów OCR.
  Historyczne poziomy `18/36/72` nie należą do ścieżki v10.4.
- Jedna błędna albo brakująca cyfra może zostać skorygowana wyłącznie wtedy, gdy
  pozostałe etykiety tworzą jednoznaczną, rosnącą siatkę w porządku wierszowym.
  Remis hipotez albo konflikt dwóch zdjęć kończy się `manual_required`.
- Wszystkie zdjęcia zamkniętej grupy przechodzą tani scoring. Nie ma early exit;
  reprezentantem zostaje najlepszy czytelny JPEG z całej grupy. Pełna geometria
  nie jest warunkiem wyboru, ale blur, okluzja, brak widocznego layoutu, konflikt
  zakresu i błąd techniczny pozostają twardymi blokadami automatycznego zapisu.
- v10.4 ma osobny niezmienny fingerprint. Historyczne v9–v10.3 pozostają
  rozwiązywalne po swoich fingerprintach i nie zmieniają wyników po wdrożeniu.

### Zachowane wymagania wydajnościowe v10.1

Profil pierwszych 200 rzeczywistych zdjęć wykazał, że pełny scoring grupy jest
tani, natomiast 99 pełnych weryfikacji uruchomiło 792 batche i 7128 cropów OCR.
Optymalizacja nie może wrócić do `first usable` ani pominąć zdjęć grupy.

- każde zdjęcie nadal przechodzi lekki scoring, a top-12 pozostaje bounded
  shortlistą całej zakończonej grupy,
- jakość reprezentanta jest rozstrzygana niezależnie od źródła dowodu numeru;
  zdjęcie z najlepszymi planszami nie musi być klatką, z której odczytano zakres,
- pełna geometria ma poprzedzać OCR i umożliwiać szybki odczyt trzech kotwic,
- OCR kandydatów działa adaptacyjnie: potwierdza zakres na małej liczbie
  najlepszych klatek i rozszerza pracę do top-12 wyłącznie przy braku pewności
  albo konflikcie,
- fallback widocznych etykiet działa progresywnie `18 -> 36 -> 72`; trudny
  przypadek zachowuje obecną pełną ścieżkę,
- brak pojedynczej etykiety brzegowej nie może automatycznie unieważniać
  lokalnego dowodu całej siatki. Adapter może odzyskać zakres wyłącznie z co
  najmniej siedmiu zgodnych punktów RANSAC, gdy widoczna jest przynajmniej jedna
  etykieta brzegowa i punkty obejmują wszystkie trzy wiersze oraz kolumny,
- remis hipotez, brak etykiety brzegowej lub niepełne pokrycie siatki nadal
  kończy się `manual_required`; poprzednia grupa nie może dostarczać brakującego
  numeru,
- rozpoznany zakres nie może być zastępowany przewidywanym kolejnym zakresem.
  Skok, np. `19–27 -> 400–408`, jest poprawny i musi pozostać rozpoznany,
- w v10.1–v10.3 `first_sequence_number` może kotwiczyć pierwszy ekran; w v10.4
  jest obowiązkowy, lecz w żadnej wersji nie narzuca ciągłości dalszych grup,
- pierwsza bramka zakłada skrócenie czasu o 60–70% bez pogorszenia jakości.
  Dalszy cel 70–85% jest dopuszczalny dopiero po porównaniu reprezentantów,
- pomiar na tych samych pierwszych 200 zdjęciach poprzedza manualny run 5000 i
  32 000. Trudne grupy mogą nadal użyć pełnego kosztu v10.
- optymalizacja pełnej geometrii musi zachowywać dokładnie ten sam obraz
  wejściowy, krok wyszukiwania, tie-break i wynik. Skalowanie albo cropowanie
  jest niedopuszczalne, jeżeli zmienia rezultat detektora; równoważne sumy
  integralne maski binarnej mogą zastąpić wielokrotne skanowanie tych samych
  prostokątnych okien.

### Ręczne odrzucenie zduplikowanego zakresu — 2026-08-11

- Konflikt `IMAGE_SELECTION_RANGE_CONFLICT` nie może pozostawiać grupy bez
  dostępnej decyzji. Modal udostępnia jawną akcję `Odrzuć jako duplikat`.
- Backend akceptuje odrzucenie tylko wtedy, gdy inna rozwiązana grupa tego
  samego runu ma dokładnie ten sam `range_start` i `range_end`.
- Odrzucona grupa otrzymuje terminalny status `skipped_existing_range`, znika z
  kolejki ręcznej i nie zapisuje ani nie nadpisuje JPEG-a wynikowego.
- Decyzja jest idempotentna i audytowana jako `duplicate_range`. Nie wolno
  automatycznie odrzucać grupy po samym konflikcie, ponieważ wpisany zakres może
  wymagać korekty użytkownika.
- Po odpowiedzi `IMAGE_SELECTION_RANGE_CONFLICT` modal pokazuje akcję
  `Odrzuć duplikat i dalej` bezpośrednio przy błędzie. Główny przycisk oraz
  ponowne `Enter` lub `→` wykonują tę samą jawną decyzję. Pierwsza próba nie
  odrzuca grupy automatycznie; zmiana zakresu anuluje propozycję odrzucenia.

### Korekta jakościowa v10.5 — 2026-08-11

- v10.4 nie spełniła odbioru na rzeczywistych 42 403 zdjęciach: 3 388 z 3 840
  grup, czyli 88,23%, wymagało ręcznej decyzji, a dominującą przyczyną był brak
  hipotezy grid OCR mimo czytelnych etykiet.
- Nowe runy używają szerokiego deskryptora wyglądu v10.3. Zachowany zostaje
  bufor v10.4, który nie pozwala pierwszym klatkom kolejnego ekranu pozostać w
  poprzedniej grupie.
- Zakres rozpoznaje adapter niezależnych etykiet brzegowych v10.3. Kandydaci są
  sprawdzani progresywnie `1 -> 2 -> 4`, a cropy jednego JPEG-a `18 -> 36 -> 72`.
- Jeden dokładny, lokalnie spójny odczyt kończy wyszukiwanie. Odczyt fuzzy jest
  używany wyłącznie po zgodności dwóch niezależnych JPEG-ów.
- Pełna klasyczna geometria nie jest wykonywana w Selekcji Zdjęć. Wszystkie
  obrazy grupy nadal otrzymują tani scoring, a reprezentant musi sam potwierdzić
  zakres grupy przed automatycznym zapisem.
- Twarde blokady pozostają bez zmian: konflikt lub inny zakres, blur, okluzja,
  brak dekodowalnego JPEG-a i błąd techniczny.
- Bramka v10.5 wymaga minimum 95% grup ze znanym zakresem, maksimum 35% grup
  manualnych i projekcji pełnego przebiegu 42 403 zdjęć do pięciu godzin.
