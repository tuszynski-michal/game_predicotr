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

- Przed tworzeniem, aktualizacją lub wykonywaniem planu przeczytaj w całości
  `ai_docs/process/PLAN_STANDARD.md`. Zastosuj jego kontrolę jakości oraz
  `ai_docs/process/TASK_TEMPLATE.md`; sam link nie zastępuje odczytu.
- Z użytkownikiem komunikuj się i przedstawiaj plany po polsku, chyba że
  poprosi inaczej. Instrukcje zapisuj w języku edytowanego dokumentu; nie
  tłumacz przy okazji identyfikatorów, kodu ani istniejącej dokumentacji.
- Odpowiedzi w czacie pisz w stylu `caveman lite`, aby ograniczyć zużycie
  tokenów: bez wstępów, grzeczności, powtórzeń i asekuracji; pełne, zwięzłe
  zdania; jedna myśl na zdanie; bez narracji przed wywołaniami narzędzi. Styl
  dotyczy tylko rozmowy z użytkownikiem i pozostaje po polsku. Kod, komendy,
  identyfikatory, cytowane błędy, dokumentację, komunikaty commitów, treść
  tasków, `Outcome` i wpisy `DECISION_LOG.md` pisz normalnym stylem. Wyjdź ze
  stylu przy ostrzeżeniach bezpieczeństwa, potwierdzaniu operacji
  nieodwracalnych i wieloetapowych instrukcjach, w których skrót groziłby
  błędnym odczytem, a także na prośbę „stop caveman” lub „normal mode”.
  Agent z dostępnym skillem `caveman` uruchamia go z poziomem `lite`.
- Ostatnią sekcją każdego planu musi być `Przypisanie modeli do zadań` z
  kompletną tabelą `Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy
review`. Każdy task ma własny wiersz z dokładnym dostępnym modelem i
  wspieranym poziomem rozumowania; nie wolno zastępować wpisu odwołaniem typu
  „ten sam model”. Szczegółowe reguły doboru i zgodności określa
  `ai_docs/process/PLAN_STANDARD.md`.

- Nie rozszerzaj zakresu zadania bez wyraźnej potrzeby.
- Domyślnie implementuj wyłącznie task wskazany przez użytkownika. Wyraźne
  polecenie uruchomienia etapu zaakceptowanego planu obejmuje wszystkie jego
  taski w kolejności planu oraz delegowanie wykonawców i audytorów według
  tabeli modeli. Sama tabela nie jest zgodą na delegowanie. Dla planu bez
  etapów obowiązuje zatrzymanie po tasku, chyba że użytkownik wyraźnie
  polecił wykonanie całego planu.
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

## Budżet tokenów i zgoda na kosztowne prace

- Zasada obowiązuje Codex, Claude Code i wszystkich innych agentów pracujących
  w repozytorium, w tym subagentów, wykonawców oraz audytorów.
- Przed rozpoczęciem długiej lub bardzo złożonej zmiany, która może zużyć
  około 10% lub więcej pakietu użytkownika, agent musi ostrzec użytkownika
  i uzyskać jego wyraźną zgodę na taki koszt. Do czasu odpowiedzi nie rozpoczyna
  kosztownej implementacji, delegowania, audytów ani szerokich testów.
- Ostrzeżenie musi zawierać zakres, powód złożoności, przewidywany czas oraz
  szacunek zużycia tokenów lub pakietu, jeśli jest wiarygodnie dostępny.
  Nie podawaj zmyślonych procentów. Gdy nie można wiarygodnie oszacować kosztu,
  długą lub bardzo złożoną pracę również poprzedź ostrzeżeniem i zgodą użytkownika.
- Koszt obejmuje łącznie pracę głównego agenta, subagentów, audyty, ponowne
  odczyty dokumentacji i powtarzane kontrole. Nie dziel zadania na mniejsze
  kroki w celu obejścia obowiązku uzyskania zgody.
- Ogólne polecenia „kontynuuj”, „dokończ” lub „pracuj samodzielnie” nie zastępują
  zgody na duże zużycie pakietu, jeśli użytkownik nie został wcześniej ostrzeżony
  o przewidywanym koszcie. Zatwierdzony zakres nie upoważnia do nieograniczonego
  zużycia tokenów.
- Jeżeli w trakcie pracy przewidywany koszt lub czas istotnie wzrośnie,
  zatrzymaj kosztowną część, podaj dotychczasowy wynik i pozostały zakres,
  a następnie uzyskaj zgodę na kontynuację. Przestrzegaj limitów czasu i budżetu
  wskazanych przez użytkownika. Wykorzystuj aktualne wyniki weryfikacji zamiast
  niepotrzebnie powtarzać audyty i testy.

## Kontrola lokalnych usług API i Admin

- API i Admin uruchamia, zatrzymuje i restartuje ręcznie użytkownik, we własnych
  terminalach. Agent nie wykonuje tych operacji bez osobnego, wyraźnego
  polecenia użytkownika w bieżącym zadaniu.
- Polecenie naprawy, diagnozy lub testowania nie jest zgodą na uruchomienie
  API/Admin, przejęcie ich portów ani pozostawienie ukrytej instancji w tle.
  Wcześniejsza zgoda na restart nie obowiązuje automatycznie w kolejnych zadaniach.
- Jeżeli poprawka wymaga restartu, przekaż użytkownikowi właściwą komendę
  i pozostaw jej wykonanie użytkownikowi. Status procesu i zajętość portu można
  sprawdzać bez zmiany stanu; nie kończ cudzych procesów.

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
- Dla pierwszego commita w bieżącym torze sprawdź historię aktualnego brancha
  (`git log`) i ustal wersję na podstawie najnowszego wersjonowanego commita na
  tym branchu. Nie zakładaj wersji z nazwy brancha ani nie używaj przykładowej
  lub zapamiętanej wersji, takiej jak `v1.1`.
- Każdy następny commit zwiększa patch o jeden względem poprzedniego commita w
  tym torze. Po każdym commicie zapisz jego pełną wersję i hash w sekcji
  `Outcome` aktywnego zadania oraz w `ai_docs/process/CURRENT_STATE.md`.
  Przy kontynuacji odczytaj ten zapis i potwierdź go z historią bieżącego
  brancha; w razie rozbieżności obowiązuje rzeczywisty commit na branchu.
- Numer patch jest przypisany do kolejności commitów, nie do liczby zadań w
  commicie. Nie wolno ponownie użyć ani pominąć numeru bez jawnej decyzji
  użytkownika.
- Komunikat commita ma format `vX.Y.N - {opis}`: zaczyna się od pełnej bieżącej
  wersji ustalonej dla brancha, po której następuje krótki opis zakresu.
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
8. Po raporcie zatrzymaj się, chyba że użytkownik wyraźnie uruchomił cały
   etap albo cały plan bez etapów. Wtedy po audycie, osobnym commicie,
   Outcome i aktualizacji CURRENT_STATE.md każdego taska kontynuuj do końca
   zleconego zakresu. Zatrzymaj się na końcu etapu albo przy sprzeczności
   wymagań, koniecznej decyzji, niedostępnym modelu/reasoning, otwartych uwagach
   audytu P0/P1 po jednej rundzie poprawek (uwagi P2 odnotowane w `Outcome`
   nie zatrzymują; zasady w sekcji „Audyt krzyżowy”) lub przed operacją czy
   kosztem poza zatwierdzonym zakresem. Nie wykonuj automatycznego push,
   merge, aktywacji modelu ani wdrożenia.

## Audyt krzyżowy

- Zmiany taska audytuje model z innej rodziny niż wykonawca: pracę Claude
  audytuje Codex, a pracę Codex audytuje Claude. Wykonawca nie audytuje
  własnej pracy. Audyt jest wymagany po każdym tasku, który wskazuje go w
  kolumnie `Dodatkowy review` zaakceptowanego planu, przed commitem.
- Do czasu, gdy oba CLI (`codex`, `claude`) są zainstalowane i zalogowane przez
  operatora, audytorem jest niezależny subagent Claude z innym modelem niż
  wykonawca, w świeżym kontekście i wyłącznie do odczytu. Zastępstwo musi być
  jawnie odnotowane w `Outcome` taska i zgodne z kolumną `Dodatkowy review`
  planu; brak dostępnego modelu zatrzymuje task zgodnie z `PLAN_STANDARD.md`.
- Brief audytu buduje `scripts/audit_task.ps1` (skill `audit-task` w Claude
  Code, lustrzany skill `claude-audit` w Codex). Skrypt składa plik taska,
  fragment planu, `git diff <base>...HEAD` wraz ze zmianami niezacommitowanymi
  (domyślnie `-Base HEAD`, czyli audyt przed commitem; `-Paths` ogranicza
  diff do plików taska) i linie weryfikacji z `Outcome`, zapisuje brief w
  `artifacts/audits/` (katalog ignorowany przez git), a gdy CLI audytora jest
  dostępne, uruchamia je w trybie tylko do odczytu z limitem czasu. Bez CLI
  skrypt kończy się na briefie, a audyt wykonuje się ręcznie lub zastępczym
  subagentem.
- Wyjątek od domyślnego limitu 120 s z sekcji „Limity czasu i procesy
  długotrwałe”: uruchomienie audytu może mieć timeout narzędzia do 600 s,
  przy czym własny `-TimeoutSec` skryptu musi być niższy (zalecane 480 s,
  bo po jego upływie skrypt potrzebuje jeszcze około 25 s na sprzątanie).
  Alternatywnie uruchom skrypt jako kontrolowany proces w tle i monitoruj go.
- Audytor nie zmienia plików. Przegląd jest statyczny: ocenia zgodność z
  zakresem, kryteriami akceptacji, planem i regułami tego pliku, a nie
  rozszerza zakresu.
- Raport leży w `ai_docs/quality/TASK-NNNN_AUDIT_<model>.md`, jest pisany
  normalną prozą po polsku i ma format z
  `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`: werdykt `PASS` albo `REVISE`,
  znaleziska P0–P2 z `plik:linia`, listy zamkniętych i otwartych uwag,
  proponowane testy oraz oświadczenie „przegląd statyczny, bez zmian w
  plikach”. Raport wchodzi do commita taska.
- Otwarte uwagi P0 i P1 blokują commit. Uwagi P2 wykonawca naprawia albo
  odnotowuje w `Outcome` jako zaakceptowane ryzyko z uzasadnieniem.
- Obowiązuje jedna runda audytu i jedna runda poprawek. Ponowny audyt
  wykonuje się wyłącznie na żądanie operatora albo gdy poprawka zmieniła
  zachowanie objęte uwagą P0/P1; nie powstaje automatyczna pętla. Jeżeli po
  poprawkach uwaga P0/P1 pozostaje otwarta, zatrzymaj task i zgłoś to
  operatorowi zgodnie z punktem 8 sekcji „Po kodowaniu”.
- Domyślny audyt jest **szybki** (decyzja operatora 2026-10-09): audytor to `gpt-6-astra` na poziomie `medium` (poziom `high` tylko dla tasków zmieniających schemat bazy, migracje, wypłaty albo dane dowodowe), brief ograniczony `-Paths` do plików taska, a raport skupia się na P0 i P1; uwag P2 podaje najwyżej pięć najważniejszych. Audytor zastępczy Claude stosuje ten sam zakres i poziom `medium`, chyba że tabela planu wymaga `high`. Jedna runda audytu, jedna runda poprawek, bez pętli; brak odpowiedzi audytora w limicie czasu nie zatrzymuje taska, tylko jest odnotowany w `Outcome`.
- Po commicie taska lead dopisuje wersję i pełny hash commita do sekcji taska w
  `CURRENT_STATE.md` i do `Outcome` (w kolejnym commicie dokumentacyjnym lub
  razem z następnym taskiem); audytor sprawdza obecność tego zapisu.
- Codex CLI uruchamiany przez skrypt używa `node.exe` z `codex.js` (shim `.cmd`
  nie przenosi cudzysłowów) oraz nadpisań `windows.sandbox="unelevated"` i
  `model_reasoning_effort` (parametry `-CodexWindowsSandbox`, `-Effort`), bo
  piaskownica `elevated` zarejestrowana przez aplikację ChatGPT nie działa z CLI.
- Poświadczeń CLI nie wpisuje agent: instalację i logowanie wykonuje operator.

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
