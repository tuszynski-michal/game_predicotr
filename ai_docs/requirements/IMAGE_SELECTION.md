---
title: Fast representative image selection
status: accepted
release: "0.4"
last_updated: 2026-08-02
---

# Selekcja reprezentatywnych zdjęć

## Cel biznesowy

Przed właściwym `Importem layoutów` należy zredukować katalog 10 000–30 000
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
- Moduł stanowi zakres wersji 0.4 i przygotowuje kontrolowane wejście do pracy
  na dużych danych wersji 0.5. Nie zmienia historycznej bramki trzech
  workspace'ów wersji 0.2.

## Wejście i kolejność

- Użytkownik wybiera folder standardowym selektorem katalogu przeglądarki,
  zgodnym z działającym wyborem w `Imporcie layoutów`.
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
7. utrzymywanie kilku najlepszych jakościowo kandydatów zamiast obrazów w RAM,
8. dokładniejsza weryfikacja wyłącznie najlepszych kandydatów przy zamknięciu
   grupy.

Zmiana grupy jest wykrywana z łącznego dowodu geometrii, fingerprintu oraz OCR.
Sam niepewny OCR nie może połączyć dwóch różnych ekranów ani nadać zakresu.
Wątpliwość kończy się `manual_required`, nie fałszywym auto-wyborem.

## Ocena jakości i wybór

- Automatyczny reprezentant musi pokazywać cały oczekiwany zestaw plansz dla
  grupy, bez istotnego zasłonięcia i obcięcia.
- Ranking obejmuje co najmniej kompletność geometrii, ostrość, ekspozycję,
  clipping świateł, refleksy, perspektywę, margines ekranu i confidence zakresu.
- Oczekiwana liczba widocznych plansz wynika z konsensusu dobrych zdjęć grupy;
  zapobiega to uznaniu zasłoniętych ośmiu plansz za poprawną stronę końcową.
- Wybór jest deterministyczny. Remis rozstrzyga wcześniejszy `order_index`, a
  następnie checksum SHA-256.
- Run przechowuje pełne metryki, powody odrzucenia oraz wersję selektora.
- Użytkownik widzi liczbę plików przeskanowanych, rozpoznane zakresy,
  automatyczne wybory, odrzucone zdjęcia, duplikaty i grupy wymagające decyzji.

## Zestaw wynikowy i bezpieczeństwo plików

- Moduł nigdy nie usuwa, nie przenosi ani nie zmienia plików w folderze
  wskazanym przez użytkownika.
- Wybrane zdjęcia są kopiowane do kontrolowanego katalogu wyniku i wiązane z
  checksumowanym manifestem.
- Nazwa ma postać
  `seq_<start:06>-<end:06>__<sha256-prefix>.jpg`, na przykład
  `seq_000001-000009__a1b2c3d4.jpg`.
- Zakresy zaczynają się od dodatniego numeru; nazwa `seq_0-9` nie może tworzyć
  niedozwolonego domenowo `sequence_number = 0`.
- Manifest przechowuje oryginalną względną nazwę, checksumę, kolejność,
  rozpoznany zakres, metryki jakości, sposób `automatic | manual`, wersję
  algorytmu i ścieżkę kopii wynikowej.
- Baza przechowuje ścieżki, checksumy i metadane, nie duże obrazy BLOB.
- Tymczasowe kopie uploadu nie są folderem źródłowym użytkownika. Po atomowym
  zapisaniu kompletnego wyniku mogą zostać usunięte; przy błędzie pozostają do
  retry, a przy anulowaniu są usuwane na jawne polecenie użytkownika.

## Manualne uzupełnienie

Jeżeli grupa nie ma bezpiecznego automatycznego reprezentanta, po zakończeniu
skanu otwierana jest kolejka decyzji w modalu.

Header modala pokazuje:

- `zatwierdzone / wszystkie wymagające decyzji`,
- rozpoznany zakres, na przykład `400–408`, albo `Nieustalony zakres #N`,
- przyciski poprzedni/następny,
- mały przycisk `Zatwierdź`.

Zachowanie klawiatury:

- `ArrowLeft` i `ArrowRight` wyłącznie nawigują między brakującymi grupami,
- `Enter` zatwierdza poprawnie wskazane zdjęcie,
- strzałki nie zapisują decyzji,
- zatwierdzoną pozycję można później ponownie otworzyć i zmienić.

Body używa standardowego selektora pojedynczego pliku JPEG. Wybrany plik jest
kopiowany do właściwego katalogu wyniku. Dla nierozpoznanej grupy użytkownik
podaje dodatni początek i koniec zakresu; bez tego manifest nie może zostać
zatwierdzony ani przekazany do właściwego importu.

## Integracja z Importem layoutów

- Tylko run bez nierozwiązanych grup może zostać przekazany dalej.
- Handoff tworzy serwerowo poświadczone źródło wejściowe dla istniejącego
  `image_directory` importu i zachowuje identyfikator runu, manifest oraz
  checksumy wybranych zdjęć.
- Użytkownik nadal jawnie uruchamia `Rozpocznij import`; selekcja nie uruchamia
  automatycznie ciężkiego pipeline'u.
- Retry właściwego importu nie powtarza selekcji, jeżeli jej manifest i pliki
  nadal przechodzą weryfikację checksum.
- Wyniki selekcji nie tworzą layoutów, symboli, review ani datasetu.

## Wydajność i bramka jakości

- Skan jest strumieniowy i nie przechowuje pełnych obrazów całego katalogu w
  pamięci.
- Pełny OCR plansz, cropy komórek i symbol inference są zabronione w selektorze.
- Liczba kosztowniejszych weryfikacji jest bounded liczbą grup i top-k, a nie
  liczbą wszystkich zdjęć.
- Provisionalny budżet na komputerze właściciela wynosi maksymalnie 15 minut dla
  10 000 oraz 45 minut dla 30 000 zdjęć. TASK-0157 może obniżyć budżet po
  pomiarach, ale nie może zaakceptować procesu trwającego wiele godzin.
- Peak RSS workera ma pozostać bounded i zmierzony; brak wyniku benchmarku
  blokuje użycie modułu na pełnym katalogu.
- Golden grup nie dopuszcza fałszywego scalenia dwóch zakresów. Niepewne
  przypadki mogą zwiększać manual review, ale nie mogą dawać błędnego
  automatycznego reprezentanta.

## Poza zakresem

- usuwanie lub reorganizowanie folderu użytkownika,
- rozpoznawanie symboli i tworzenie cropów komórek,
- trenowanie modelu podczas selekcji,
- wymaganie ciągłości zakresów pomiędzy grupami,
- Redis, Celery, usługa chmurowa lub osobny mikroserwis,
- automatyczne rozpoczęcie pełnego importu bez decyzji użytkownika.
