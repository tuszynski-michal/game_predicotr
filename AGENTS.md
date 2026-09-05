# AGENTS.md

## Cel dokumentu

Ten plik zawiera nadrzędne zasady pracy dla Codex oraz innych agentów AI w tym repozytorium. Dokumentacja w katalogu `ai_docs/` jest źródłem prawdy dla zakresu produktu, architektury i aktualnego etapu prac.

## Obowiązkowa kolejność czytania

Przed rozpoczęciem każdego zadania przeczytaj:

1. `ai_docs/README.md`
2. `ai_docs/process/CURRENT_STATE.md`
3. dokument wymagań dotyczący zmienianego obszaru,
4. dokument architektury dotyczący zmienianego obszaru,
5. aktywne zadanie znajdujące się bezpośrednio w `ai_docs/tasks/`, jeśli
   istnieje.

Nie czytaj całej dokumentacji bez potrzeby. Otwieraj dokumenty wskazane w sekcji `Relevant docs` aktywnego zadania.
Nie wczytuj `ai_docs/tasks/completed/` ani `ai_docs/archive/`, chyba że aktywne
zadanie odwołuje się do nich jawnie.

## Zasady nadrzędne

- Nie rozszerzaj zakresu zadania bez wyraźnej potrzeby.
- Implementuj wyłącznie task wskazany przez użytkownika. Nie rozpoczynaj
  kolejnego taska, nawet jeżeli jego zależności są gotowe, bez osobnego
  polecenia użytkownika.
- Przed kodowaniem ponownie przeczytaj aktywny task oraz odpowiadające mu
  fragmenty zaakceptowanego planu. Jeżeli zakres taska i plan są sprzeczne,
  zgłoś konflikt przed implementacją.
- Nie podejmuj ukrytych decyzji produktowych. Zapisz je jako pytanie, założenie albo decyzję.
- Zachowuj deterministyczną kolejność układów. `sequence_number` jest częścią domeny, a nie technicznym identyfikatorem.
- Nie uruchamiaj kalkulacji targetu, dopóki pozycja sekwencji nie jest jednoznacznie ustalona.
- Nie zapisuj obrazów jako dużych obiektów binarnych w głównych tabelach domenowych. Przechowuj ścieżkę i metadane.
- Zmiany schematu bazy wykonuj wyłącznie przez migracje Alembic.
- Kontrakt API jest definiowany przez backend i OpenAPI. Frontend nie może utrzymywać ręcznie rozbieżnych typów odpowiedzi.
- Komendy i instrukcje lokalne muszą działać na Windows PowerShell, chyba że zadanie mówi inaczej.
- Nie wykonuj destrukcyjnych operacji na danych bez wyraźnej zgody użytkownika.
- Nie dodawaj kolejki Redis/Celery, mikroserwisów ani chmury, dopóki pomiary nie pokażą takiej potrzeby.

## Trwałość rozwiązań

- Rozwiązując problem, usuwaj jego przyczynę w sposób globalny i trwały dla
  repozytorium albo środowiska użytkownika. Naprawa ma działać również w nowym
  procesie, nowym terminalu i po ponownym uruchomieniu komputera.
- Zmiana wyłącznie bieżącego `PATH`, ręczne zakończenie procesu, jednorazowa
  komenda lub modyfikacja stanu tylko w pamięci jest obejściem sesyjnym, a nie
  ukończoną naprawą.
- Jeżeli obejście sesyjne jest konieczne do odblokowania pracy, oznacz je jawnie,
  a następnie dodaj trwałą konfigurację, kod, migrację, test lub instrukcję
  operatorską eliminującą przyczynę.
- Weryfikuj trwałość z nowego procesu albo przez odczyt konfiguracji zapisanej
  dla użytkownika/systemu. Jeżeli nie można potwierdzić zachowania po restarcie,
  nie raportuj problemu jako definitywnie naprawionego i zapisz pozostałe ryzyko.

## Cykl wykonania zadania

### Wersjonowanie commitów

- Każdy ukończony task otrzymuje osobny commit. Niezależna poprawka błędu
  wykonana przed taskiem również wymaga osobnego commita.
- Numer następnego commita wyznacz z najnowszego wersjonowanego commita w
  bieżącym torze. Każdy kolejny commit zwiększa patch o jeden.
- Numer patch jest przypisany do kolejności commitów, nie do liczby zadań w
  commicie. Nie wolno ponownie użyć ani pominąć numeru bez jawnej decyzji
  użytkownika.
- Komunikat commita zaczyna się od pełnej bieżącej wersji `vX.Y.N`; po niej może
  zawierać krótki opis zakresu.
- Przed commitem sprawdź `git diff --cached --check`, staged statystykę i listę
  staged plików. Po commicie sprawdź `git show --stat` oraz pozostały
  `git status`.

### Brudny worktree i zakres commita

- Zmiany obecne przed rozpoczęciem taska należą do użytkownika, chyba że ich
  pochodzenie jest jednoznacznie znane. Nie usuwaj ich, nie formatuj masowo i
  nie dołączaj automatycznie do commita.
- Jeżeli plik zawiera zarówno zmiany użytkownika, jak i bieżącego taska, dodaj
  do indeksu wyłącznie właściwe hunki. Nie commituj całego pliku tylko dlatego,
  że task zmienił jego fragment.
- Zmiana API wymaga jednego spójnego pionu: backendu, OpenAPI, wygenerowanego
  klienta, wrappera klienta i testu żądania. Nie utrzymuj ręcznie rozbieżnych
  typów.

### Przed kodowaniem

1. Potwierdź zakres zadania na podstawie dokumentacji.
2. Wypisz pliki, które prawdopodobnie zostaną zmienione.
3. Sprawdź otwarte pytania blokujące.
4. Jeżeli można bezpiecznie przyjąć założenie, zapisz je w zadaniu i `CURRENT_STATE.md`.
5. Jeżeli założenie zmienia model domenowy albo architekturę, dodaj wpis do `DECISION_LOG.md`.

### W czasie kodowania

- Realizuj jeden spójny pion funkcjonalny naraz.
- Dodawaj testy razem z kodem.
- Używaj małych, czytelnych modułów i jawnych nazw domenowych.
- Oddzielaj logikę domenową od transportu HTTP, UI i ORM.
- Dla algorytmów używaj czystych funkcji z deterministycznymi wejściami i wyjściami.
- Gdy nowe UI wymaga rozszerzenia istniejącego API, zgłoś tę konieczność
  użytkownikowi przed zmianą i wybierz zgodne rozszerzenie istniejącego
  kontraktu zamiast tworzyć równoległy endpoint lub model bez potrzeby.
- Przy wydzielaniu wspólnego komponentu zachowaj domyślne zachowanie jego
  istniejących konsumentów. Nowe opcje są opcjonalne, a poprzedni workflow musi
  dostać test regresyjny.

### Testy, benchmarki i regresje

- Najpierw uruchamiaj testy skoncentrowane na zmienionym pionie, następnie jego
  lint i typecheck, a dopiero potem szersze testy i build.
- Nie uruchamiaj benchmarków, testów obciążeniowych, wielomilionowych fixture'ów
  ani sztucznych danych bez wyraźnego polecenia użytkownika. Najpierw stosuj
  analizę teoretyczną albo ograniczony test na istniejących danych.
- Nie osłabiaj ani nie usuwaj testu wyłącznie po to, aby uzyskać zielony wynik.
  Test można zmienić tylko, jeżeli świadomie zmienił się jego kontrakt.
- Naprawa regresji otrzymuje test odtwarzający zgłoszony przypadek, w tym
  restart, utraconą odpowiedź, konflikt rewizji albo wznowienie, jeżeli taki
  scenariusz był przyczyną błędu.
- Jeżeli pełna kontrola wykrywa wcześniejszy, niezwiązany błąd, nie rozszerzaj
  automatycznie zakresu. Potwierdź jakość zmienionych modułów, opisz blocker i
  pozostaw go poza commitem.

### Trwałe workflowy i operacje danych

- Dla workflowów opartych na jobach, manifestach, stagingu lub IndexedDB
  weryfikuj zachowanie po restarcie procesu oraz po utracie odpowiedzi API.
  Sukces wyłącznie w bieżącej sesji nie jest dowodem trwałości.
- Implementacja mechanizmu destrukcyjnego nie jest zgodą na jego wykonanie na
  danych użytkownika. Migracje destrukcyjne, GC, cleanupy i usuwanie danych
  wymagają osobnego preview i jawnego potwierdzenia.

### Limity czasu i procesy długotrwałe

- Każda komenda skończona musi mieć jawny timeout proporcjonalny do oczekiwanego
  czasu wykonania. Nie uruchamiaj komendy bez limitu czasu.
- Domyślny timeout pojedynczego kroku wynosi maksymalnie 120 sekund. Dłuższy
  limit jest dozwolony wyłącznie dla znanego builda lub benchmarku, po
  wcześniejszym poinformowaniu użytkownika o przewidywanym czasie.
- Serwerów developerskich, watcherów i innych procesów bez naturalnego końca
  nie uruchamiaj jako blokującej komendy foreground. Uruchom je jako osobny,
  kontrolowany proces, zapisz PID i sprawdzaj gotowość krótkim pollingiem z
  limitem maksymalnie 10 sekund.
- Jeżeli komenda nie zwraca nowego wyniku przez 60 sekund i nie jest
  kontrolowanym buildem albo benchmarkiem, przerwij ją, sprawdź stan procesu i
  zgłoś przyczynę przed ponowieniem inną metodą.
- Nie używaj nieograniczonego oczekiwania na port, proces, job ani urządzenie.
  Każdy polling musi mieć limit prób i krótkie timeouty pojedynczych odczytów.
- Po przerwaniu albo timeoutcie sprawdź, czy nie pozostał osierocony proces.
  Nie uruchamiaj drugiej kopii tej samej usługi, dopóki nie ustalisz stanu
  pierwszej.

### Po kodowaniu

1. Uruchom formatowanie, lint, testy i kontrolę typów dla zmienionych części.
2. Zaktualizuj dokumentację, jeżeli zmieniło się zachowanie, API, model danych lub decyzja.
3. Zaktualizuj `ai_docs/process/CURRENT_STATE.md`.
4. Uzupełnij sekcję `Outcome` aktywnego zadania.
5. Po zakończeniu zadania przenieś plik ze statusem `done` do
   `ai_docs/tasks/completed/`.
6. W raporcie końcowym podaj:
   - co zmieniono,
   - jakie testy uruchomiono,
   - czego nie wykonano,
   - jakie są następne kroki lub ryzyka.
7. Porównaj rezultat punkt po punkcie z Definition of Done taska oraz jego
   zaakceptowanym planem.
8. Po raporcie zatrzymaj się. Kontynuuj wyłącznie po osobnym poleceniu
   użytkownika wskazującym następny task.

## Hierarchia źródeł prawdy

W przypadku sprzeczności obowiązuje kolejność:

1. zaakceptowane decyzje w `ai_docs/process/DECISION_LOG.md`,
2. wymagania w `ai_docs/requirements/`,
3. architektura w `ai_docs/architecture/`,
4. aktywne zadanie,
5. komentarze w kodzie,
6. istniejąca implementacja.

Jeżeli implementacja jest sprzeczna z dokumentacją, nie zakładaj automatycznie, że kod ma rację. Zgłoś rozbieżność.

## Standard jakości

Zadanie nie jest ukończone tylko dlatego, że aplikacja się uruchamia. Obowiązuje `ai_docs/process/DEFINITION_OF_DONE.md`.
