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
- rozpoznany zakres nie może być zastępowany przewidywanym kolejnym zakresem.
  Skok, np. `19–27 -> 400–408`, jest poprawny i musi pozostać rozpoznany,
- `first_sequence_number` może kotwiczyć pierwszy ekran, ale nie narzuca
  ciągłości dalszych grup,
- pierwsza bramka zakłada skrócenie czasu o 60–70% bez pogorszenia jakości.
  Dalszy cel 70–85% jest dopuszczalny dopiero po porównaniu reprezentantów,
- pomiar na tych samych pierwszych 200 zdjęciach poprzedza manualny run 5000 i
  32 000. Trudne grupy mogą nadal użyć pełnego kosztu v10.
