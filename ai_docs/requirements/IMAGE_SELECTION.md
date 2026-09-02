---
title: Fast representative image selection
status: accepted
release: "0.4"
last_updated: 2026-08-15
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
- Anulowany job `image_selection` może zostać trwale usunięty wyłącznie jawną,
  mocno potwierdzoną akcją w workspace `Joby`. Operacja usuwa rekordy runu i
  zarządzane pliki manualne, lecz nigdy nie dotyka zewnętrznego katalogu
  wynikowego. Staging źródłowy jest usuwany tylko wtedy, gdy nie korzysta z
  niego żaden inny run; handoff do importu i opublikowany manifest blokują
  usunięcie.
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
- Folder wskazany przed uploadem nowej partii pozostaje nieprzypisanym folderem
  oczekującym. Nie może uruchomić eksportu aktualnie wyświetlanego historycznego
  runu ani zostać zapisany pod jego identyfikatorem. Powiązanie z `runId`
  następuje dopiero po pomyślnym utworzeniu albo idempotentnym odzyskaniu runu.
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

### Rozdzielone kolejki review i odrzucenie — 2026-08-11

- `manual_required` oznacza wyłącznie znany zakres bez bezpiecznego
  reprezentanta. Taka grupa trafia do akcji `Wybierz zdjęcie`.
- `range_required` oznacza wybrany automatycznie, wystarczająco czytelny JPEG,
  dla którego nie rozpoznano zakresu. Taka grupa trafia do osobnej akcji
  `Ustal grupę`; użytkownik wpisuje zakres, ale nie wybiera ponownie zdjęcia.
- `skipped_unreadable` jest terminalnym wynikiem dla grupy złożonej wyłącznie z
  bardzo rozmazanych, zasłoniętych lub niewidocznych obrazów. Nie trafia do
  żadnej kolejki i nie tworzy pliku wynikowego.
- Użytkownik może odrzucić element z obu kolejek. `rejected_by_user` nie tworzy
  pliku, nie blokuje publikacji i zachowuje źródłowy stan
  `manual_required | range_required`, aby akcja `Przywróć do kolejki`
  odtwarzała dokładny poprzedni etap.
- Potwierdzenie zakresu zachowuje automatycznie wybrany JPEG, przechodzi do
  `range_confirmed` i podlega tej samej kontroli unikalności zakresu co wybór
  automatyczny lub manualny.
- Potwierdzenie zakresu, odrzucenie i przywrócenie są idempotentne i zapisują
  append-only decyzję. Odrzucenie/przywrócenie nie wymaga dostępu do katalogu
  wynikowego; operacja tworząca wybrany JPEG nadal wymaga trwałego zapisu.

### Reprezentant od środka grupy v10.6 — 2026-08-11

- Wszystkie JPEG-i nadal przechodzą tani skan jakości i grupowania. Pełniejsze
  sprawdzanie reprezentanta zaczyna się od pięciu kolejnych zdjęć położonych
  centralnie w zakończonej grupie.
- Z centralnej piątki wybierany jest najlepszy czytelny JPEG. Dopiero gdy żaden
  nie przechodzi łagodnej bramki, selektor sprawdza trzy pierwsze i trzy
  ostatnie zdjęcia grupy, z deterministycznym usunięciem duplikatów dla krótkiej
  grupy.
- Lekki blur jest akceptowalny. Manifest v10.6 obniża miękkie minima do
  `sharpness >= 0.05`, `board_visibility >= 0.12` i `overall_score >= 0.16`;
  błąd dekodowania lub brak widocznego ekranu nadal blokuje wybór.
- Jeżeli próbki centralne i brzegowe są słabe, selektor może użyć najlepszego
  czytelnego rekordu z globalnej top-12 taniego skanu. Jeżeli również on nie
  istnieje, grupa kończy się `skipped_unreadable` bez OCR i outputu.
- Czytelny automatyczny JPEG nie jest odrzucany tylko z powodu braku numerów.
  Otrzymuje `range_required` i trafia wyłącznie do `Ustal grupę`.

### Zakres z czterech kolejnych etykiet v10.7 — 2026-08-11

- Dla ekranu z dziewięcioma layoutami pełny zakres może wynikać z dowolnych
  czterech kolejnych numerów, jeżeli każdy ma pewność co najmniej `0.72` i
  położenia tworzą cztery kolejne komórki siatki row-major.
- Przykładowo liczby `1, 2, 3, 4` w pozycjach 0–3 oraz `5, 6, 7, 8` w pozycjach
  4–7 jednoznacznie oznaczają zakres `1–9`. Reguła działa analogicznie dla
  numerów wielocyfrowych i nie zależy od poprzedniej grupy.
- Pozycje muszą zostać wyznaczone z lokalnych trzech wierszy i trzech kolumn
  widocznych etykiet. Sam ciąg liczb bez pełnej lokalizacji w siatce nie jest
  wystarczającym dowodem, ponieważ mógłby przesunąć początek o wielokrotność 3.
- Remis dwóch zakresów, mniej niż cztery kolejne liczby, niezgodna geometria lub
  niska pewność kończą się bez zakresu. Cursor ani oczekiwana ciągłość nie
  rozstrzygają remisu.
- OCR jednego JPEG-a działa progresywnie `9 -> 18 -> 36` cropów i kończy się po
  pierwszym jednoznacznym dowodzie. Nie rozszerza się już do 72 cropów w v10.7.

### Pozycyjnie zakotwiczone rozpoznawanie v10.8 — 2026-08-11

- Nowy run używa `fast-image-selector-v10.8`. Historyczne wyniki i fingerprinty
  v10.7 oraz starszych wersji nie zmieniają zachowania.
- Detektor może odtworzyć dziewięć pozycji siatki z co najmniej pięciu
  widocznych czerwonych ramek obejmujących wszystkie trzy wiersze i kolumny.
  Łagodniejsze progi czerwieni dotyczą wyłącznie weryfikacji selekcji zdjęć.
- Cztery kolejne, pozycyjnie zakotwiczone etykiety o confidence co najmniej
  `0.72` wystarczają do wyprowadzenia zakresu. Błędne albo puste odczyty poza
  wybranym oknem nie blokują poprawnej hipotezy; dwa różne kompletne okna nadal
  kończą się fail-closed.
- Ogólny fallback bez bezpiecznej kotwicy zachowuje silny dowód co najmniej
  siedmiu etykiet i kończy progresję po `9` lub `18` cropach. Nie wolno w nim
  wyprowadzać zakresu z czterech niezakotwiczonych liczb.
- Co najmniej pięć z dziewięciu layoutów musi przejść łagodną kontrolę ostrości.
  Większościowo bardzo rozmazana siatka otrzymuje `QUALITY_LAYOUT_BLUR` i nie
  tworzy automatycznego ani ręcznego wyboru obrazu.
- Nierozpoznane podgrupy pomiędzy dwoma bezpośrednio kolejnymi, lokalnie
  potwierdzonymi zakresami są fragmentami przejścia i kończą się bez outputu.
  Jeżeli sąsiednie zakresy pozostawiają dokładnie jedną lukę dziewięciu pozycji,
  rozproszone podgrupy mogą zostać scalone do jednego wyniku tej dokładnej luki.
  Właścicielem wyniku zostaje podgrupa zawierająca najlepszy JPEG; pozostałe
  podgrupy otrzymują ten sam zakres, `skipped_existing_range` oraz odnośnik do
  właściciela. Zdjęcie zachowuje pierwotną podgrupę i nie może zostać przepięte
  wyłącznie w celu technicznego scalenia.
  Większy albo niepodzielny skok pozostaje nierozstrzygnięty.
- Bramka akceptacji nadal wymaga ręcznej oceny około 5000 zdjęć, zera błędnych
  zakresów i reprezentantów oraz dopiero potem pełnego przebiegu 42 403.

### Częściowa kotwica layoutów v10.9 — 2026-08-11

- Nowy run używa `fast-image-selector-v10.9`; v10.8 i wszystkie wcześniejsze
  fingerprinty zachowują historyczne zachowanie.
- Kotwica może powstać z co najmniej trzech widocznych czerwonych ramek, jeżeli
  obejmują co najmniej dwa wiersze i dwie kolumny. Detektor zachowuje wyłącznie
  ograniczone hipotezy zgodne z rozmiarem, kierunkiem, brakiem nakładania i
  położeniem siatki. Konflikt hipotez kończy się fail-closed.
- OCR najpierw czyta etykiety faktycznie wykrytych ramek. Cztery zgodne pozycje
  przy confidence `>= 0.72` albo trzy zgodne pozycje przy `>= 0.82` stanowią
  silny dowód jednego JPEG-a.
- Dwie zgodne pozycje przy confidence `>= 0.90` są tylko słabym dowodem. Zakres
  może zostać przyjęty dopiero po takim samym wyniku z drugiego, odrębnego JPEG-a
  o innym checksumie. Dwa różne zakresy nigdy nie są rozstrzygane z cursora.
- OCR może następnie sprawdzić brakujące pozycje odtworzonej siatki. Silny dowód
  z odtworzonymi pozycjami musi nadal zawierać co najmniej dwie etykiety z ramek
  rzeczywiście widocznych; zabezpiecza to przed zgodnym błędem syntetycznych
  cropów.
- Surowy i przetworzony wariant tego samego cropa są rozstrzygane w kontekście
  całej siatki. Konflikt dwóch równie silnych zakresów pozostaje bez decyzji.
- Nierozstrzygnięty fragment pomiędzy dwiema grupami tego samego dokładnego
  zakresu jest duplikatem `skipped_existing_range` i nie tworzy outputu.
- Bez bezpiecznej częściowej kotwicy pozostaje historyczny fallback siedmiu
  etykiet `9/18`. Progi grupowania, kolejność `środek -> brzegi`, rozdzielone
  kolejki review oraz reguła `skipped_unreadable` nie zmieniają się.
- Przed pełnym runem obowiązuje próba pierwszych 1440 zdjęć. Dopiero wynik z
  zerem błędnych zakresów i review pozwala uruchomić wszystkie 42 403 źródła.

### Bezpieczna siatka etykiet v10.10 — 2026-08-13

- Nowy run używa `fast-image-selector-v10.10`; v10.9 oraz wszystkie wcześniejsze
  fingerprinty zachowują historyczne zachowanie i nie mogą być wznawiane jako
  nowy silnik.
- Ogólny fallback obejmuje etykiety wszystkich trzech rzędów widocznego ekranu.
  Osie `3 × 3` są dopasowywane wyłącznie z komponentów o położeniu, szerokości i
  proporcjach zgodnych z etykietami numerów; wąskie symbole i tabela wypłat nie
  mogą wyznaczać rzędów siatki.
- Cztery kolejne liczby o confidence `>= 0.72` wystarczają tylko wtedy, gdy
  tworzą cztery kolejne pozycje row-major i przechodzą kontrolę odstępów w osi X
  i Y. Remis albo niezgodna geometria pozostają `range_required`.
- Częściowa kotwica musi zawierać co najmniej jedną faktycznie wykrytą planszę w
  górnym rzędzie. Rekonstrukcja złożona wyłącznie ze środkowego i dolnego rzędu
  nie może automatycznie przesunąć zakresu o trzy numery; przechodzi do
  niezależnej siatki etykiet.
- Dwie etykiety nie są w v10.10 samodzielnym dowodem zakresu. Trzy etykiety mogą
  pozostać silnym dowodem wyłącznie w bezpiecznej, rzeczywiście zakotwiczonej
  siatce.
- Jeśli operator podał pierwszy numer zbioru, automatyczny zakres musi należeć
  do tej samej siatki dziewięcioelementowej. Niezgodny zakres jest odrzucany z
  `RANGE_OWNER_ALIGNMENT_MISMATCH`; wartość nie jest poprawiana ani zgadywana.
- Jedna grupa wyglądu może zostać rozdzielona na więcej niż jeden wynik tylko,
  gdy jej własne kandydaty zawierają silne, bezpośrednio kolejne zakresy w
  zgodnej kolejności źródłowej. Każdy wynik zachowuje własnego JPEG-a; brakujący
  zakres bez rozpoznanego kandydata nie jest syntetyzowany.
- Przed pełnym runem obowiązuje regresja wskazanych JPEG-ów i profil pierwszych
  1440 zdjęć z kontrolą błędnych przesunięć, duplikatów i ciągłości.

### Pochodne odzyskiwanie zakresów v10.11 — 2026-08-13

- Historyczny run nie jest mutowany podczas naprawy. Użytkownik otrzymuje nowy
  run oznaczony jako pochodny, ze wskazaniem wersji silnika i runu źródłowego.
- Naprawa grup `range_required` nie może ufać dotychczasowej granicy grupy ani
  wybranemu reprezentantowi. Analizuje wszystkich zachowanych kandydatów w
  pierwotnej kolejności i potrafi scalić false split, rozdzielić false merge
  oraz wymienić błędnego reprezentanta.
- Reprezentant może otrzymać zakres wyłącznie na podstawie własnego zgodnego
  dowodu. Zdjęcie bardzo rozmazane jest odrzucane; czytelne, ale nadal
  niejednoznaczne pozostaje dostępne w galerii `Ustal grupę`.
- Niezależna siatka etykiet ma pierwszeństwo przed niejednoznaczną częściową
  geometrią. Mocny konflikt pozostaje fail-closed, a słaby konsensus wymaga
  różnych checksum, zgodnych pozycji i braku konkurencyjnej hipotezy.
- Przed zapisaniem runu pochodnego system wykonuje pełny dry-run bloków
  problematycznych i raportuje proponowane scalenia, podziały, wymiany
  reprezentanta, konflikty oraz pozostałe przypadki ręczne.
- W ręcznym ustalaniu grupy domyślnie podaje się tylko pierwszy numer, z końcem
  `start + 8`. Jawny tryb krótkiej grupy końcowej pozwala podać ostatni numer.
  Użytkownik może zmienić zdjęcie albo odrzucić grupę.
- Otwarcie modala nie może wykonywać pełnego uzgodnienia folderu. Zapis decyzji
  czeka tylko na bieżący JPEG; pełne uzgodnienie jest oddzielną operacją z
  widocznym postępem.

### Dwucyfrowy konsensus v10.12 — 2026-08-14

- Pełny dry-run v10.11 na 748 historycznych grupach jest bramką jakości, a nie
  zgodą na utworzenie runu. Wynik z 283 czytelnymi grupami nadal wymagającymi
  zakresu i konfliktem zduplikowanego zakresu blokuje publikację.
- Dwie etykiety mogą tworzyć wyłącznie słaby dowód zakresu, jeżeli obie mają
  pewność co najmniej `0.90`, zajmują różne pozycje tej samej siatki i wskazują
  jedną, niekonkurencyjną hipotezę początku. Remis lub druga hipoteza pozostają
  fail-closed.
- Pojedynczy JPEG z dwoma etykietami nigdy nie wystarcza do automatycznego
  wyboru. Ten sam zakres muszą niezależnie potwierdzić co najmniej dwa JPEG-i o
  różnych checksumach; konflikt z silnym dowodem pozostaje `range_required`.
- Projekcja recovery globalnie uzgadnia zakresy zaproponowane przez niezależne
  bloki. Jeden deterministyczny właściciel zachowuje wynik, a pozostałe kopie
  stają się `skipped_existing_range`. Istniejąca decyzja użytkownika ma
  pierwszeństwo; konflikt dwóch decyzji użytkownika nadal blokuje dry-run.
- V10.11 i jego fingerprint pozostają niezmienne oraz rozwiązywalne dla runów
  historycznych. Nowe wykonania używają osobnego manifestu v10.12.

### Pełna liczność sekwencji v10.13 — 2026-08-14

- Nowy run utworzony z folderu o ścisłej nazwie `pierwszy - ostatni` zapisuje
  oba końce inkluzywnego przedziału. Pierwszy numer musi zgadzać się z kierunkiem
  i wartością podaną przez operatora; niespójna nazwa kończy się jawnym błędem.
- Rerun istniejącego stagingu może jawnie podać oba końce przedziału. Jest to
  wymagane dla historycznego runu bez `last_sequence_number`, aby nowy run miał
  twardą oczekiwaną liczność zamiast niepełnego kontraktu odziedziczonego ze
  starej wersji.
- Liczba logicznych grup wynosi
  `ceil((abs(last_sequence_number - first_sequence_number) + 1) / 9)`.
  Każda pełna grupa obejmuje dziewięć kolejnych layoutów, a wyłącznie ostatnia
  grupa może być krótsza.
- Gotowy wynik musi mieć dokładnie jednego logicznego właściciela każdej pozycji
  tej siatki. Dodatkowe fizyczne fragmenty mogą istnieć tylko jako
  `skipped_existing_range` z odwołaniem do właściciela; luka, duplikat właściciela
  albo zakres poza siatką blokują publikację.
- Każdy logiczny właściciel musi wskazywać co najmniej jeden rzeczywisty JPEG
  obecny w niezmiennym manifeście wejściowym. Grupa bez wybranego zdjęcia może
  pozostać manualna tylko wtedy, gdy ma niepustą galerię review; pusta grupa albo
  checksum spoza manifestu blokują dry-run i utworzenie recovery.
- Istniejącej decyzji użytkownika nie wolno pominąć ani przenieść do innego
  zakresu. Konflikt decyzji z pełnym przedziałem pozostaje fail-closed.
- Historyczny fragment o dużej liczbie źródeł nie może zostać uznany za prosty
  duplikat tylko po pozycji. Taki potencjalny false merge oraz automatyczny
  zakres poza globalną siatką muszą ponownie przejść segmentację i wybór JPEG-a.
- Pełna liczność może przypisać numer bez OCR dopiero po udowodnieniu ciągłej
  projekcji i istnienia bezpiecznego reprezentanta. Rozmazanie, zasłonięcie,
  błąd geometrii albo konflikt zakresu nadal kierują zdjęcie do review.
  Kandydat z własnym rozpoznanym zakresem innym niż oczekiwany nie może zostać
  automatycznie przepisany; algorytm wybiera zgodnego lub nierozstrzygniętego
  reprezentanta, a przy ich braku pozostawia grupę manualną.
- V10.12 oraz starsze fingerprinty pozostają niezmienne. V10.13 może ponownie
  wykorzystać cache weryfikacji v10.12, ponieważ adapter obrazu i OCR nie uległ
  zmianie; nowy wpis jest następnie zapisywany pod fingerprintem v10.13.
- Końcowa projekcja pełnego runu jest zapisywana atomowo. System najpierw zwalnia
  zakresy modyfikowalnych automatycznych właścicieli oraz wszystkie stare sloty
  wybranych kandydatów w niechronionych grupach, potem zapisuje całą uzgodnioną
  projekcję i przed zatwierdzeniem transakcji ponownie sprawdza liczbę
  właścicieli, liczbę duplikatów, dokładną kolejność siatki oraz jednego właściwego
  reprezentanta każdej gotowej grupy. Pole `selected_candidate` jest
  autorytatywne; historyczna decyzja innego elementu `top_candidates` nie może
  ponownie wybrać starego JPEG-a. Decyzje użytkownika nie są zwalniane ani
  degradowane.
- Błąd zapisu projekcji ma stabilny kod
  `IMAGE_SELECTION_PROJECTION_PERSISTENCE_CONFLICT`; nie może zostać ukryty jako
  ogólny `JOB_EXECUTION_FAILED` ani pozostawić częściowo przepisanych zakresów.
- Końcowy checkpoint zapisuje dokładne liczniki bieżącej projekcji po
  uzgodnieniu, a nie z surowych grup zapisanych podczas skanowania. Ogólne
  liczniki postępu joba pozostają monotoniczną historią wykonania: retry ani
  zmiana klasyfikacji nie mogą ich zmniejszyć. UI i raport stanu selekcji muszą
  używać dokładnych liczników projekcji z payloadu checkpointu.
- Monitor operatorski przy `waiting_for_review` albo `completed` odczytuje
  wszystkie grupy ponownie od początku. Eksportuje `auto_selected`,
  `manually_selected` i `range_confirmed`, uzupełnia wybory zmienione za bieżącym
  kursorem oraz usuwa wyłącznie nieaktualne pliki własnego kontraktu
  `seq_<start>-<end>.jpg` z izolowanego katalogu wynikowego.
- Raport operatorski schema v3 zapisuje oczekiwaną i rzeczywistą liczbę grup
  logicznych, liczbę duplikatów, dokładne liczniki statusów, brakujące,
  powtórzone i pozasiatkowe zakresy oraz osobne bramki pokrycia projekcji i
  plików. Job `failed` albo `cancelled` jest tylko audytowany i nie naprawia
  katalogu wynikowego; następny etap może ruszyć wyłącznie po przejściu obu
  bramek przez `waiting_for_review` albo `completed`.

### Partycjonowanie przed reconciliacją v10.14 — 2026-08-15

- Pełny run z jawnym początkiem i końcem sekwencji musi utworzyć co najmniej
  tyle fizycznych fragmentów, ile wynosi oczekiwana liczba logicznych grup.
- Maksymalna liczba źródeł w jednym fragmencie wynosi
  `max(1, floor(source_count / expected_group_count))`. Granice wykryte przez
  analizę obrazu nadal mogą zakończyć fragment wcześniej.
- Nadmiarowe fragmenty są dozwolone i końcowy reconciler może oznaczyć je jako
  duplikaty. Każdy logiczny właściciel nadal musi jednak wskazywać rzeczywisty
  JPEG z niezmiennego manifestu wejściowego.
- Jeśli źródeł jest mniej niż oczekiwanych grup, job kończy się jawnym błędem
  `IMAGE_SELECTION_SOURCE_CARDINALITY_UNDERFLOW`; system nie tworzy pustych ani
  syntetycznych właścicieli.
- Manifest i fingerprint v10.13 pozostają niezmienne. Reguła partycjonowania
  należy do osobnego selektora v10.14, który może ponownie wykorzystać zgodny
  cache weryfikacji v10.13 lub v10.12.

### Adaptacyjne partycjonowanie v10.15 — 2026-08-16

- V10.15 zachowuje bramkę liczności v10.14, ale limit bieżącego fragmentu
  wylicza z liczby pozostałych źródeł i pozostałych wymaganych grup:
  `ceil(remaining_source_count / remaining_group_count)`.
- Naturalna granica obrazu nadal może zakończyć fragment wcześniej. Następny
  limit jest wtedy przeliczany, aby wcześniejszy podział nie wymuszał lawiny
  nadmiarowych fragmentów i weryfikacji OCR.
- Dla wejścia bez wykrytych granic reguła musi utworzyć dokładnie oczekiwaną
  liczbę fizycznych fragmentów, o rozmiarach różniących się najwyżej o jeden.
  Wznowienie z tego samego checkpointu musi dawać identyczną projekcję.
- Niedobór rzeczywistych źródeł nadal kończy się
  `IMAGE_SELECTION_SOURCE_CARDINALITY_UNDERFLOW`. Reconciler, ochrona decyzji
  użytkownika i bramki pokrycia pozostają bez zmian.
- Czas dwóch godzin nie jest sztywną bramką akceptacji. Pomiar ma wykazać
  istotne odzyskanie różnicy wydajności względem porównywalnego, zimnego runu
  v10.13 bez cofnięcia naprawy granic v10.14.

### Etapowy OCR v10.16 — 2026-08-16

- V10.16 najpierw weryfikuje środkowych kandydatów na poziomach `1`, `2`, `4`
  i ogranicza szeroką siatkę etykiet do poziomu `12`.
- Szybka ścieżka może zakończyć grupę automatycznie wyłącznie wtedy, gdy co
  najmniej dwa różne checksumy JPEG wskazują ten sam, zgodny z właścicielem
  zakres na podstawie mocnego dowodu. Dwucyfrowy dowód słaby nie wystarcza.
- Konflikt tras OCR, dwa różne zakresy albo brak konsensusu blokują szybki
  wynik. System wykonuje wtedy niezmienioną pełną weryfikację z poziomami
  kandydatów `12` i `18` oraz dotychczasowymi bramkami v10.14/v10.15.
- Reprezentant szybkiego automatu musi mieć własny mocny odczyt zgodny z
  zakresem grupy. Nie wolno pożyczyć zakresu lepiej wyglądającemu JPEG-owi bez
  takiego dowodu.
- Telemetria osobno raportuje próby, sukcesy, konflikty i fallback szybkiego
  etapu. Wynik szybkiego etapu nie jest zapisywany jako pełny cache; pełny
  fallback może nadal korzystać ze zgodnych wpisów historycznych.

### Próbkowanie pięciu wnętrz grupy v10.17 — 2026-08-16

- V10.17 nie sprawdza kolejnych pięciu zdjęć wokół środka ani pierwszych i
  ostatnich zdjęć grupy. Używa maksymalnie pięciu pozycji: `50%`, `35%`, `65%`,
  `15%`, `85%`, w tej kolejności etapów.
- Pozycja procentowa jest zaokrąglana deterministycznie do najbliższego numeru
  zdjęcia z połówką w górę. Dla 30 zdjęć są to numery `15, 11, 20, 5, 26`.
  Powtórzone pozycje w małej grupie są usuwane bez zmiany kolejności.
- OCR działa etapami `1 → 3 → 5`: najpierw środek, następnie para wewnętrzna,
  a na końcu para z 15% i 85%. Automat nadal wymaga dwóch różnych checksumów z
  tym samym mocnym zakresem; pojedyncze środkowe zdjęcie nie może samodzielnie
  ustalić zakresu.
- Po potwierdzeniu zakresu wybierany jest pierwszy czytelny, nierozmazany
  kandydat w kolejności próbkowania. Dzięki temu środek ma pierwszeństwo, ale
  zdjęcie niespełniające bramek jakości nie blokuje wyboru dalszych próbek.
- Każdy z maksymalnie pięciu kandydatów przechodzi jeden progresywny verifier:
  poziom 12, a przy braku wyniku poziom 18. Kandydat nie może być ponownie
  weryfikowany wyłącznie po to, aby wybrać reprezentanta.
- Siedem próbek nie jest aktywne. Może zostać dodane wyłącznie jako osobna,
  wersjonowana polityka po pomiarze wykazującym, że pięć pozycji daje zbyt małą
  skuteczność. Pierwsze i ostatnie zdjęcie pozostają wykluczone.

### Jednoklatkowe zakończenie po mocnym środku v10.18 — 2026-08-16

- V10.18 zachowuje kwantyle `50%, 35%, 65%, 15%, 85%`, ale mocny,
  jednoznaczny odczyt pierwszego czytelnego i nierozmazanego JPEG-a może
  samodzielnie zakończyć grupę automatem.
- Wynik jednoklatkowy musi przejść pełną bramkę reprezentanta: widoczny layout,
  zgodna liczba plansz, brak twardego blur, okluzji, błędu skanu i konfliktu
  zakresu. Dowód `RANGE_OCR_FUZZY_CANDIDATE` nie wystarcza.
- Jeżeli środek nie przejdzie bramki, selektor sprawdza razem `35%` i `65%`.
  Dopiero brak mocnego użytecznego wyniku w tej trójce uruchamia `15%` i `85%`.
- Po zaakceptowaniu mocnego wyniku pozostałe kwantyle nie przechodzą ani OCR,
  ani pełnej oceny reprezentanta. Tani skan całej grupy i kontrola granic nadal
  pozostają obowiązkowe.
- Dwa różne mocne zakresy wykryte w tym samym wykonanym poziomie są konfliktem
  fail-closed. Zakres spoza zadeklarowanej siatki właściciela również nie może
  uruchomić early exit.

### Proof-first zakres i audyt v10.19 — 2026-08-17

- `auto_selected` wymaga, aby zapisany reprezentant sam dostarczył mocny dowód
  dokładnie swojego kanonicznego zakresu. Kolejność, deklarowana liczba grup i
  sąsiednie zakresy nie mogą utworzyć ani zastąpić odczytu OCR.
- Mocny dowód obejmuje co najmniej trzy różne pozycje plansz, w tym jedną parę
  sąsiadującą. Wszystkie obserwacje muszą mieć tę samą bazę
  `sequenceNumber - positionIndex`; dla trasy trzyetykietowej confidence każdej
  użytej etykiety wynosi co najmniej `0,82`.
- Dwie etykiety, wynik fuzzy, zakres z liczności, luka oraz kotwica właściciela
  są wyłącznie sugestią do ręcznego audytu. Grupa pozostaje `range_required`
  bez kanonicznego `rangeStart/rangeEnd`.
- Wykrycie tylko części dziewięciu plansz nie blokuje automatu, jeżeli trzy
  prawidłowo umiejscowione etykiety i jakość wybranego JPEG-a spełniają bramki.
  Nie wolno syntetyzować niewidocznych etykiet jako odczytów.
- Reconciler może oznaczyć drugi mocno udowodniony identyczny zakres jako
  duplikat, lecz nie może wypełniać luk kolejnymi numerami. `skipped_unreadable`
  oraz `rejected_by_user` nie tworzą zielonego pokrycia wynikowego.
- UI pokazuje oddzielnie sugestię zakresu i kanoniczny zakres. Dla oglądanego
  kandydata prezentuje pozycje, odczytane numery, confidence i informację, czy
  dowód jest mocny; zmiana zdjęcia aktualizuje tylko sugestię formularza.
- Raport rozdziela automaty z dowodem, ręcznie potwierdzone grupy, zakresy
  oczekujące, duplikaty i rzeczywiście brakujące zakresy. Stan
  `waiting_for_review` nie jest błędem procesu, ale nie może udawać pełnej
  ciągłości.
- V10.19 zachowuje etapy kwantylowe `50% → 35%+65% → 15%+85%`, wyłącza
  bezproduktywny poziom OCR 18 i kończy grupę po pierwszym czytelnym kandydacie
  z mocnym dowodem. Pierwsze i ostatnie zdjęcie nadal nie są próbkami.

### Sekwencyjnie walidowany zakres v10.20 — 2026-08-18

- Deklarowany pełny przedział ustala oczekiwane kolejne zakresy dziewięciu
  layoutów. Oczekiwany zakres jest wyłącznie hipotezą, którą musi potwierdzić
  OCR pozycyjny tego samego JPEG-a; nie wolno przypisać go z samego kursora.
- Poza mocnym dowodem v10.19 automat może zaakceptować dwa dokładne odczyty
  pozycyjne z pełnej geometrii plansz. Dla częściowego widoku v10.20 wymaga co
  najmniej trzech pozycji z confidence `>= 0,82`, obejmujących dwie kolumny i
  dwa wiersze; co najmniej jeden odczyt musi być dokładny, a pozostałe mogą
  różnić się od oczekiwanej liczby najwyżej jednym znakiem OCR.
- Mocny niezależny odczyt innego zakresu, konflikt tras, rozmazanie, okluzja
  albo błąd geometrii blokują promocję. Oczekiwany zakres jest zawsze dokładnie
  następnym slotem z pełnych granic; nie tworzy się przesuniętych startów `±1`.
  Jedna obserwacja lub brak wymaganego pokrycia pozostawiają `range_required`.
- Fizycznych fragmentów może być przejściowo więcej niż oczekiwanych zakresów.
  Po zablokowaniu wszystkich logicznych właścicieli nadmiarowe fragmenty są
  oznaczane `skipped_existing_range`, więc liczba właścicieli pozostaje równa
  liczbie slotów z deklarowanego zakresu.
  `range_required` jest osobną kolejką i nie jest doliczany do `automat + wybór
  zdjęcia`. Po ręcznym wskazaniu brakującego zakresu staje się jego właścicielem;
  wskazanie zakresu istniejącego zapisuje `duplicate_range` i
  `skipped_existing_range` bez drugiego outputu.
- Checkpoint oraz API raportują `manual` wyłącznie dla `manual_required` i
  `rangeRequired` wyłącznie dla `range_required`. Ogólny `review` może być ich
  sumą, ale UI i raport operatorski muszą pokazywać je osobno.
- V10.20 ma adapter `visible-sequence-label-range-v18` i fingerprint
  `5b979eb826bbf943047bff41a98e293ecf9f3cb46ba95044b606edd32a33bd86`.
  Manifest i fingerprint v10.19 pozostają niezmienne.

## Półautomatyczny wybór zdjęć v1 — kontrakt zakresu

Półautomatyczny wybór jest niezależnym od gry workflowem przygotowującym
katalog `seq_<start>-<end>.jpg`. Nie zastępuje historycznej automatycznej
selekcji v10 ani lokalnej ręcznej selekcji.

Jego automat odpowiada wyłącznie na pytanie, czy bieżący JPEG samodzielnie i
jednoznacznie dowodzi dokładnego oczekiwanego zakresu. Nie wykonuje detekcji
plansz, geometrii, homografii, croppera, klasyfikacji symboli ani oceny jakości
plansz. Ostrość, ekspozycja, okluzja albo jakość symboli nie mogą odrzucić
zdjęcia z mocnym lokalnym dowodem zakresu; ich ewentualna ocena należy do
późniejszego, ręcznego review.

Zakresy mają wersjonowaną konwencję `seq-inclusive-v1`: numery dodatnie,
inkluzywne, nazwa zawsze rosnąca, pełny zakres obecnie do dziewięciu plansz i
końcowy zakres krótszy, gdy wymaga tego deklarowana granica. Rozmiar pełnego
zakresu jest kontraktem możliwości modułu, a nie topologią gry. Dla `1–19809`
ostatnim poprawnym zakresem jest `19801–19809`; `19800–19809` ma dziesięć
plansz i nie jest poprawną nazwą.

Wynik bramki jest jednym z: `exact_range`, `range_unreadable`,
`range_ambiguous`, `outside_requested_range`, `not_expected_range` albo
`source_error`. Tylko `exact_range` może wejść do późniejszego grupowania.
Brak pewnego dowodu jest prawidłową luką do ręcznego uzupełnienia, a nie
podstawą do zgadywania zakresu z sąsiednich zdjęć.

Adapter `semi-automatic-range-only-ocr-v1` przyjmuje wyłącznie zdekodowany
obraz RGB oraz checksummowaną tożsamość źródła. Istniejący proof-first
recognizer jest wywoływany dokładnie raz z pustą kolekcją plansz, dlatego w tym
workflow nie może uruchomić tras zależnych od detekcji lub geometrii. Wynik
`exact_range` wymaga mocnego, pozycyjnego dowodu lokalnego; sama wysoka pewność
OCR nie wystarcza. Końcowy krótszy zakres jest akceptowany wyłącznie wtedy,
gdy co najmniej trzy dowody pozycyjne mieszczą się w jego rzeczywistej długości.

Nowe runy używają `semi-automatic-range-only-ocr-v2`. V2 zachowuje tę samą
bramkę dowodu, lecz ma własny filtr rzeczywistych etykiet: X `0.20–0.82`, Y
`0.24–0.48`, minimalna szerokość `0.025` obrazu i minimalny aspect ratio
`1.20`. Kandydaci są OCR-owani progresywnie `12 → 24 → 36`, wyłącznie dla
nowej części poziomu, w batchach do dziewięciu cropów. Analiza kończy się
wcześniej po jednoznacznym dowodzie. V2 nie korzysta ze stałego viewportu
pozycji ani z expected range; układ pozycji wynika z dynamicznej lokalnej
siatki etykiet jednego JPEG-a.

Historyczny v1 pozostaje niezmienny i musi być wybierany dla runu utrwalonego z
jego fingerprintem. Nieznany fingerprint jest błędem fail-closed. Jedna, dwie,
sprzeczne albo niewystarczająco mocne etykiety pozostają luką, nawet jeśli
surowa hipoteza OCR wskazuje jakiś zakres.

Odbiór v2 na checksummowanych próbach 10/100 musi pozostać zapisany wraz z
fingerprintem recognizera, czasem, poziomem zakończenia i potwierdzeniem braku
wywołań ciężkiego pipeline'u. Spełnienie bramki odbioru nie włącza feature
flagi; rollout pozostaje osobną decyzją operatora.

Nowe runy po TASK-0364 używają `semi-automatic-range-only-ocr-v3`. Każda
wykonana próba zachowuje bez zmian kandydatów `12/24/36` oraz proof v2, ale
OCR nie jest uruchamiany na każdym podobnym JPEG-u. Tani deskryptor wyglądu
wyzwala próbę na mocnej zmianie, a niezależny bounded interval wymusza ją co
najwyżej pięć źródeł. Wygląd nie jest dowodem zakresu: pominięty JPEG ma wynik
`unproven`, nie może zostać reprezentantem ani odziedziczyć numeru od sąsiada.
Historyczne runy v1/v2 nadal wykonują swój zapisany kontrakt bez schedulera.

Komponent przygotowany w TASK-0368 definiuje przyszły wariant
`semi-automatic-range-only-ocr-v4-middle-row-triple-v2`. V4.1 lokalizuje
wyłącznie trzy pełne etykiety środkowego rzędu po jednokrotnej kanonizacji EXIF.
Stałe ROI X `0.20–0.82` i Y `0.24–0.48` jest wersjonowanym pierwszym przebiegiem;
jeżeli nie daje kompletnej, jednoznacznej siatki, locator może rozszerzyć tylko
dolną granicę do `0.60`. Rozszerzenie nadal kończy się `unknown`, gdy lekki
afiniczny układ 3×3 pozostaje niejednoznaczny.

Każdy wynik v4.1 jest albo lokalnym `exact`, albo jawnym `unknown`. `Exact`
wymaga trzech kolejnych, numerycznych odczytów z kompletnych i czytelnych cropów
źródłowej rozdzielczości, progów confidence oraz dopasowania do dokładnie jednego
wpisu `ExpectedRangeTable`. Nazwa pliku, katalog, source index, sąsiednie zdjęcia
i fuzzy correction nie mogą dostarczyć ani uzupełnić dowodu. Częściowa końcowa
strona jest rozpoznawalna tylko wtedy, gdy zawiera cały środkowy rząd.

TASK-0369 podłącza v4.1 do produkcyjnego recognition-only Paddle i trwałego
runtime'u joba, ale nadal nie przełącza na niego nowych runów. Batch źródeł ma
wartość `6`, wybraną jako najlepszy wynik bounded pomiaru `1/3/6/12`; każde
źródło wnosi najwyżej trzy cropy, a wewnętrzny batch Paddle pozostaje równy
dziewięć. Orientacja `auto | 0 | 90 | 180 | 270`, run-level prior, grouping,
pełny prefiks oraz diagnostyka są przypięte fingerprintem i checkpointem.

`Unknown` może leżeć pomiędzy dwoma exact proof tego samego zakresu, lecz nigdy
nie zostaje kandydatem i nie rozszerza granic evidence span. Reprezentantem jest
exact proof najbliższy środkowi tego span; jako tie-break służą czytelność,
minimalne confidence OCR i niższy source index. Rollout i próby 10/100/1000
pozostają w TASK-0370. V1–v3 i ich fingerprinty zachowują dotychczasowe
zachowanie.

Odbiór TASK-0370 nie dopuścił v4.1 do rolloutu. Challenge zachował zero false
exact, `62,5%` readable coverage i `100%` group capture, lecz zamrożony golden
set osiągnął tylko `26,3%` readable coverage oraz `35,3%` group capture przy
zerowej liczbie false exact. Cele szybkości zostały przekroczone (`4,83` i
`5,05` źródła/s), a wszystkie 120 reprezentantów prób 1000 przeszły ręczną
kontrolę. Bezpieczeństwo proof pozostaje niezmienne; nowy run nadal używa v3,
dopóki kolejny fingerprint nie przejdzie nowego, wcześniej niewidzianego
holdoutu.

Wariant v5 `semi-automatic-range-only-ocr-v5-row-first-v1` jest podłączony do
trwałego joba wyłącznie przez własny fingerprint. Każde źródło jest
kanonizowane zgodnie z EXIF dokładnie raz; v5 nie wykonuje dodatkowego OCR do
kalibracji obrotu. Locator może zwrócić niezależne wiersze, ale auto-wybór
wymaga dwóch zgodnych, kompletnych wierszy tego samego JPEG-a. Jeden wiersz,
konflikt widocznych wierszy albo nieczytelny crop daje lukę.

Skan v5 zachowuje source batch `6`, dzieli recognition-only Paddle na batche
nie większe niż dziewięć cropów i zapisuje checkpoint dopiero po pełnym batchu
źródeł. Wznowienie używa utrwalonego fingerprintu runtime'u, observation key i
polityki grupowania v5; nie może przełączyć runu v1–v4.1 ani dublować
zatwierdzonego prefiksu. Wariant nie jest jeszcze domyślny ani nie uruchamia
geometrii, board/cell croppera lub inferencji symboli.

Odbiór checksum-bound TASK-0374 odrzucił rollout v5 bez zmiany jego kontraktu.
Na challenge `19` oraz frozen golden `100` wariant nie utworzył żadnego
`exact`, więc zachował zero false exact, lecz nie spełnił bramek coverage ani
group capture. Dominujący reason code `COMPLETE_ROW_UNVERIFIED` wskazuje, że
rozpoznawanie etykiet po lokalizacji nie potwierdza pełnych rzędów; nie jest to
uprawnienie do obniżenia proof. V5 pozostaje wyłączony, a następna iteracja
musi powstać pod nowym fingerprintem i przejść wcześniej niewidziany holdout.

Jedyny skalibrowany parametr przekazywany do późniejszego grupowania to
maksymalna liczba kolejnych źródeł bez dowodu. Polityka
`real-corpus-unproven-gap-v1` wyznacza ją deterministycznie z checksumowanego
korpusu rzeczywistych zdjęć; bieżąca wartość wynosi `160`. Parametr nie nadaje
zakresu żadnemu zdjęciu i nie zmienia braku dowodu w automat.

### Rzeczywisty korpus regresji OCR zakresów — TASK-0402

Każda przyszła wersja recognition-only OCR zakresu musi przejść przez mały,
checksummowany korpus rzeczywistych ekranów bez widocznej nazwy `seq_*` ani
tekstu panelu Admina. Korpus zawiera trzy samodzielnie czytelne zakresy
`28–36`, `55–63` i `64–72` oraz klatkę przejściową z dwoma zakresami. Pierwsze
trzy przypadki są bramką coverage, a przejście ma kontrakt bezpieczeństwa:
nigdy nie może otrzymać automatycznego `exact`.

Runner korpusu może wywołać wyłącznie dekodowanie, kanonizację EXIF,
lokalizację etykiet, preprocessing i recognition-only OCR. Detekcja plansz,
geometria, board/cell cropper i inferencja symboli są poza kontraktem oraz
muszą pozostać niewywołane. Korpus jest diagnostyką regresji, nie zastępuje
niezależnego holdoutu ani nie autoryzuje rollout'u nowego fingerprintu.

### Pięć anchorów etykiet zakresu v6 — TASK-0404

Nowy, jeszcze niepodłączony do runtime'u lokalizator
`five-anchor-range-label-locator-v6` znajduje po jednokrotnej kanonizacji EXIF
pięć source-direct cropów w stabilnej kolejności: `top_left`, `top_right`,
`center`, `bottom_left`, `bottom_right`. Każdy crop ma bezwzględne współrzędne
w przestrzeni `exif-transposed-rgb-v1`, informację o kompletności oraz tryb
`component_refined` albo `viewport_fallback`.

Anchor lokalizuje wyłącznie kandydat do późniejszego recognition-only OCR;
sam nie odczytuje liczb, nie zna nazwy, folderu, indeksu źródła ani oczekiwanego
zakresu i nie stanowi dowodu automatycznego przypisania. Brak kompletnego zestawu
pięciu bounded cropów zwraca reason-coded `unknown`, bez interpolowania pozycji.
Komponent nie importuje ani nie uruchamia detekcji plansz, geometrii, croppera
plansz/komórek lub klasyfikatora symboli. Historyczne runy v1–v5 oraz ich
fingerprinty pozostają bez zmian.

### Proof pięciu anchorów v6 — TASK-0405

`semi-automatic-range-only-ocr-v6-five-anchor-v1` sprawdza rozpoznania ze
wszystkich pięciu cropów wobec przypiętych slotów pełnej strony 3×3:
`0`, `2`, `4`, `6`, `8`. Nie odczytuje obrazu ani nie wywołuje OCR — dostaje
wyłącznie tekst, confidence oraz kompletność/czytelność source-direct cropa.

Wynik `exact` wymaga co najmniej trzech zgodnych wartości o wysokiej pewności,
w tym `center`, jednego anchoru górnego i jednego dolnego. Każdy dodatkowy,
czytelny i wysokiej pewności numer niezgodny z tym samym zakresem blokuje wynik.
Pusty albo słaby pozostały anchor nie wnosi dowodu i nie jest uzupełniany; jeśli
przez to nie ma trzech rozpiętych potwierdzeń, wynik jest reason-coded `unknown`.
Przycięty, nieczytelny lub nienumeryczny crop oraz każdy conflict także pozostają
`unknown`; nie ma fuzzy repair, wyprowadzania z nazwy pliku ani z sąsiednich
obrazów. Częściowa strona zawsze pozostaje manualna. Wariant jest domenowym
kontraktem przyszłego runtime'u i nie zmienia fingerprintów v1–v5.

### Runtime OCR pięciu anchorów v6 — TASK-0406

`five-anchor-range-runtime-v1` realizuje zamknięty łańcuch: kanonizacja EXIF
raz → lokalizator pięciu source-direct cropów → lokalna bramka czytelności →
recognition-only Paddle → proof v6. Jedna partia obejmuje najwyżej sześć źródeł,
a jeden wewnętrzny batch Paddle najwyżej dziewięć cropów. Crop, który nie
przejdzie lokalnej bramki ostrości, kontrastu i krawędzi, nie uruchamia Paddle i
kończy się `unknown`; nie jest poprawiany albo interpolowany.

Runtime ma własny fingerprint i observation key powiązany z runem, źródłem i
fingerprintem. Zwraca tylko `RangeEvidenceResult` w kolejności wejścia. Nie
tworzy joba, checkpointu, grupy, plików `seq_*`, geometrii ani symboli. Nie jest
jeszcze rejestrowany jako opcja produkcyjnego runu; v1–v5 pozostają bez zmian.

### Jawny wariant trwałego runu pięciu anchorów v6 — TASK-0407

`five_anchor_v6` jest zamkniętym, eksperymentalnym wariantem wyłącznie dla
workflowu `selection`. API przyjmuje nazwę wariantu, nigdy dowolny fingerprint;
capabilities zwraca nazwę, etykietę, fingerprint, stan domyślny i
eksperymentalny. `default_v3` pozostaje wyborem domyślnym, a
`filename_verification` przyjmuje wyłącznie swój historyczny recognizer v2.

Run `five_anchor_v6` zapisuje fingerprint runtime'u v6 i niezależny fingerprint
polityki grupowania/wyboru środka. Oba są częścią tożsamości idempotencji:
identyczne żądanie v6 zwraca ten sam run, lecz ten sam staging uruchomiony na v3
i v6 tworzy dwa rozłączne runy. Wznowienie odczytuje zapisany fingerprint,
checkpoint i batch size; nie może przełączyć runtime'u ani przejąć zachowania
v1–v5.

Po source-local `exact` grupowanie obejmuje wyłącznie zdjęcia z własnym proofem
v6, toleruje reason-coded `unknown` zgodnie z przypiętą polityką i wybiera środek
spanu exact evidence. Nazwa pliku, indeks źródła ani sąsiednie zdjęcie nie są
dowodem zakresu. Wariant nie jest automatycznie rolloutowany ani wykonywany na
danych użytkownika przez samo wdrożenie.

## Trwały globalny run półautomatycznej selekcji — TASK-0352

- Workflow nie należy do gry: staging, run i job mają `gameId = null`.
- Browser staging ma osobny purpose `semi_automatic_selection`, naturalną
  kolejność względnych ścieżek oraz niezmienną checksummę finalnego manifestu.
  Purpose gry, zmiana manifestu, zmiana JPEG-a albo błędna check­summa assetu
  blokują odczyt fail-closed.
- Start wymaga pełnych granic sekwencji i kierunku. Tworzy z góry wszystkie
  oczekiwane zakresy `seq-inclusive-v1`, w tym krótszy zakres końcowy.
- Idempotencja obejmuje upload, manifest, fingerprint źródła, granice,
  kierunek, recognizer i politykę grupowania. Identyczne żądanie zwraca ten sam
  run; zmiana któregokolwiek wejścia tworzy inną tożsamość.
- Run i jego oczekiwane zakresy są trwałe. API udostępnia capabilities,
  start/status, keysetową listę zakresów, diagnostykę, checksum-bound asset,
  pause/resume/cancel oraz potwierdzenie lokalnego outputu.
- Potwierdzenie outputu wymaga bieżącej rewizji, checksummy wybranego źródła i
  identycznej checksummy zapisanych bajtów. Aktualizacja zakresu i liczników
  runu jest jedną transakcją.
- Funkcja jest domyślnie wyłączona przez
  `GAME_PREDICTOR_ENABLE_SEMI_AUTOMATIC_IMAGE_SELECTION=false`. Endpoint
  capabilities jest jedynym źródłem tej możliwości dla przyszłego UI.
- Job używa istniejącego lane selekcji zdjęć i nie może zostać przejęty przez
  general lane.

## Historia weryfikacji zakresów nazw plików — TASK-0393

- Run zachowuje ten sam techniczny job i lane, lecz trwałe pole
  `workflowMode` rozróżnia `selection` od `filename_verification`. Migracja
  klasyfikuje historyczne runy po zamkniętej liście fingerprintów recognizera;
  nie zmienia aktywnego joba ani jego checkpointu.
- Panel listuje runy `filename_verification` od najnowszego, po 20 pozycji.
  Reload wybiera najpierw zapamiętany run, następnie aktywny, a potem ostatni
  ukończony. Polling dotyczy dokładnie jednego wybranego runu.
- Po terminalnym sukcesie podejrzane (`mismatch`, `unreadable`,
  `invalid_filename`) źródło ma trwałą, checksum-bound decyzję `keep` albo
  `reject`. Domyślny widok pokazuje tylko nierozpatrzone; widok pełny zachowuje
  audyt pozostawionych i usuniętych pozycji.
- Podgląd korzysta z checksum-bound assetu stagingowego, nie z lokalnego
  katalogu. Uchwyt `seq_*`, kursor i oczekujące potwierdzenie delete należą do
  lokalnego stanu IndexedDB per run. Katalog jest wymagany dopiero przed
  usunięciem i musi pasować liczbą, naturalną kolejnością oraz fingerprintem
  stagingu.
- `reject` najpierw wykonuje istniejące journalowane usunięcie lokalne, po
  czym idempotentnie utrwala decyzję serwerową. Utrata odpowiedzi nie wykonuje
  drugiego delete: klient wznawia wyłącznie potwierdzenie API.
- Runy failed i cancelled pozostają widoczne diagnostycznie, ale nie udostępniają
  decyzji review. Automat nigdy sam nie usuwa plików.

## Domknięcie OCR weryfikacji nazw — TASK-0394

- `filename_verification` kończy skan klasyfikacją pojedynczego pliku jako
  `verified`, `unreadable`, `mismatch` albo `invalid_filename`; nie wybiera
  reprezentanta, nie wywołuje `apply_selection` i nie tworzy `seq_*`.
- Podczas OCR licznik review joba pozostaje równy zero. Dopiero atomowy,
  terminalny checkpoint zapisuje liczbę pozycji wymagających decyzji, dlatego
  progres joba nigdy nie maleje.
- Retry failed runu resetuje wyłącznie techniczne liczniki joba. Zachowuje
  checksummowany strumień obserwacji i kończy analizę bez ponownego OCR.
- Admin udostępnia przycisk `Wznów analizę` dla failed runu; komunikat jasno
  deklaruje wznowienie z zapisanych obserwacji OCR.

## Terminalny cleanup weryfikacji nazw — TASK-0395

- Run `filename_verification` po wyniku z samymi `verified` albo po ostatniej
  decyzji dla pozycji `unreadable`, `mismatch` lub `invalid_filename` przechodzi
  przez trwały stan `cleanup_pending` do `completed`. Manualna decyzja dla
  automatycznie zgodnego pliku jest odrzucana przez backend.
- W tym samym przypiętym jobie cleanup najpierw rezerwuje staging, a potem
  usuwa wyłącznie zasoby tego runu: browserowy staging, observations OCR,
  grupy, checkpointy, raporty robocze, rekordy zakresów i decyzji review.
  Nie dotyka lokalnego folderu `seq_*`, katalogu operatora, danych ręcznej
  selekcji, innych importów, cropów, modeli ani danych gry.
- Przed usunięciem i przed finalizacją cleanup ponownie sprawdza aktywne oraz
  obce referencje. Konflikt pozostawia zasoby bez zmian, przechodzi do
  `cleanup_blocked` z diagnostyką i daje się wznowić bez OCR ani utraty decyzji.
  Katalogi robocze są atomowo przenoszone do managed trash na tym samym
  woluminie, więc restart pomiędzy etapami jest idempotentny.
- Po sukcesie historia przechowuje wyłącznie lekki, nieedytowalny run: czasy,
  liczbę plików, liczniki `verified`, ręcznie pozostawionych i odrzuconych oraz
  `completed · dane robocze usunięte`. Szczegóły obrazów nie są już dostępne.

## Deterministyczny silnik wyboru zakresu — TASK-0353

- Każdy JPEG jest dekodowany lekko, ale do range-only OCR trafia najwyżej raz w
  jednym runie. V1/v2 badają wszystkie źródła; v3 zapisuje pominięte podobne
  źródła jako `unproven`. Obserwacje są przetwarzane strumieniowo w naturalnej
  kolejności; zakończony prefiks jest wznawiany z checkpointu bez ponownego OCR.
- Grupę może otworzyć i podtrzymać wyłącznie `exact_range`. Brak dowodu może
  rozszerzyć bieżący przedział źródeł maksymalnie o skalibrowane `160` pozycji,
  ale nigdy nie jest kandydatem do wyboru i nie przypisuje zakresu z sąsiadów.
- Izolowany układ `A/B/A` pozostaje grupą A z audytowalnym odstającym dowodem.
  `A/B/B` potwierdza przejście do B, a `A/B/C` oraz `A/B/EOF` zachowują mocny
  dowód B jako singleton. Duplikaty i zakresy poza kolejnością są raportowane,
  lecz pierwszy zapis oczekiwanego zakresu nie jest nadpisywany.
- Reprezentantem grupy jest JPEG z dokładnym dowodem tego samego zakresu,
  najbliższy środkowi przedziału źródeł. Remis rozstrzygają kolejno wyższa
  pewność, niższy `sourceIndex` i wcześniejsza naturalna ścieżka.
- Pełny audyt jest zapisywany jako `observations.jsonl`, `groups.jsonl`,
  atomowy `checkpoint.json` oraz checksummowany `selection-report.json` pod
  `data/exports/semi-automatic-selection/<runId>/`. Brak lub zmiana
  zatwierdzonego prefiksu diagnostyki blokuje wznowienie fail-closed.
- Zakończenie analizy ustawia run na `analysis_complete`, a job na
  `waiting_for_review`. Zapis lokalnego katalogu wynikowego nadal należy do
  TASK-0354.

## Lokalny output półautomatycznej selekcji — TASK-0354

- Automatycznie wybrany JPEG jest kopiowany do katalogu operatora pod nazwą
  `seq_<start>-<end>.jpg` bez zmiany bajtów. Przed zapisem i po ponownym
  odczycie celu musi zgadzać się SHA-256 oraz rozmiar źródła.
- `semi-automatic-image-selection-output-v1.json` wiąże katalog z dokładnym
  runem, manifestem źródeł, granicami, fingerprintami algorytmów, wyborami,
  lukami, konfliktami, checkpointem oraz co najwyżej jedną operacją oczekującą.
- Istniejący plik o identycznej checksumie jest chronionym, idempotentnym
  sukcesem. Inna zawartość jest konfliktem i nie może zostać automatycznie
  nadpisana ani potwierdzona do API.
- Potwierdzenie outputu jest wysyłane dopiero po lokalnym read-backu i zawiera
  oczekiwaną rewizję zakresu, checksummę źródła oraz checksummę outputu.
- Po restarcie brak celu wycofuje tylko pending operation, zgodny cel ją
  finalizuje, a zmieniony cel zapisuje konflikt. Ukończone wybory nie wymagają
  ponownego pobierania JPEG-a.
- IndexedDB przechowuje wyłącznie uchwyty katalogów, checksummę manifestu i
  mały stan widoku. Bloby ani bajty JPEG-ów nie są tam zapisywane.

## Konfiguracja i postęp półautomatycznej selekcji — TASK-0355

- Admin udostępnia osobną, niezależną od gry zakładkę `Półautomatyczny wybór
  zdjęć`. Nie jest ona sekcją wybranej gry i nie wymaga `gameId`.
- Konfigurator przyjmuje dwa lokalne katalogi: rekurencyjnie skanowane źródło
  JPEG oraz katalog docelowy przyszłego outputu. Widoczny wybór katalogów,
  granic sekwencji i kierunku poprzedza każdy upload.
- Pierwsza i ostatnia plansza są dodatnie i rosnące. Liczba oczekiwanych
  zakresów jest wyliczana wyłącznie z `fullRangeSize` przekazanego przez
  capabilities API; ostatni zakres może być krótszy.
- Upload używa globalnego stagingu `semi_automatic_selection` i pokazuje
  potwierdzone przez API pliki oraz bajty. Błąd pojedynczego pliku umożliwia
  bounded retry albo jawne anulowanie stagingu.
- Widok odpyta jeden aktywny run bez nakładających się requestów, pokazuje
  etap, procent, źródła, skan, wybory, luki, konflikty i błędy oraz udostępnia
  pause/resume/cancel na istniejących endpointach.
- Capabilities API jest jedynym źródłem flagi serwerowej. Gdy moduł jest
  wyłączony, konfiguracja i mutacje są nieaktywne; frontend nie może obejść
  blokady serwera.
- TASK-0355 nie udostępnia jeszcze przeglądu oczekiwanych zakresów ani ręcznej
  edycji źródeł; te tryby należą do TASK-0356.

## Przegląd i ręczna edycja źródeł — TASK-0356

- Przed pierwszym review Admin pobiera wszystkie oczekiwane zakresy
  keysetowo i synchronizuje automatyczne wybory z lokalnym katalogiem.
  Niepełny, obcy albo nieciągły snapshot jest blokowany przed mutacją plików.
- `REVIEW MODE` nawiguje po zablokowanych zakresach. `←` i `→` zmieniają
  zakres, a `F` otwiera edycję jego źródła. Zakres bez wyboru przechodzi od
  razu do `EDIT SOURCE MODE`.
- `EDIT SOURCE MODE` nie zmienia aktywnego zakresu. `←` i `→` przeglądają
  źródłowe JPEG-i, `Enter` albo `F` zapisuje bieżący JPEG, a `Escape` anuluje
  edycję. Skróty nie przejmują zdarzeń z kontrolek formularza.
- Istniejący wybór otwiera dokładny `sourceIndex`. Luka rozpoczyna od indeksu
  poprzedniego wyboru powiększonego o jeden, z fallbackiem `0` i ograniczeniem
  do końca katalogu.
- Ręczne dodanie albo zastąpienie zapisuje oryginalne bajty i wymaga zgodności
  SHA-256, rozmiaru, rewizji zakresu oraz tożsamości źródła ze stagingiem.
  Istniejący obcy plik nie jest nadpisywany. Lokalny journal umożliwia recovery
  po przerwaniu przed acknowledgement API.
