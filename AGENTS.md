# AGENTS.md

## Cel dokumentu

Nadrzędne zasady pracy dla Codex oraz innych agentów AI w tym repozytorium.
`ai_docs/` jest źródłem prawdy dla zakresu produktu, architektury i etapu prac.
Procedury jednego momentu pracy są w skillach (`.claude/skills/`, kopie Codex w
`.agents/skills/` i `.codex/skills/`). Skill nie osłabia reguł tego pliku; przy
sprzeczności obowiązuje ten plik.

## Obowiązkowa kolejność czytania

Przed rozpoczęciem każdego zadania przeczytaj:

1. `ai_docs/README.md`,
2. `ai_docs/process/CURRENT_STATE.md` (okno kroczące ≤ 30 000 B, format w
   nagłówku; pełne sekcje `done` są w archiwum),
3. `ai_docs/process/DECISION_LOG.md` (indeks 30 najnowszych decyzji; starszych
   szukaj `rg` w nim i w `ai_docs/process/decisions/DECISION_INDEX_ARCHIVE.md`,
   pełny wpis otwieraj przez kotwicę),
4. dokument wymagań dotyczący zmienianego obszaru,
5. dokument architektury dotyczący zmienianego obszaru,
6. aktywne zadanie bezpośrednio w `ai_docs/tasks/`, jeśli istnieje.

Poza tym otwieraj tylko dokumenty z `Relevant docs` aktywnego zadania. Nie
wczytuj `ai_docs/tasks/completed/` ani `ai_docs/archive/`, chyba że zadanie
jawnie się do nich odwołuje. Pełne wpisy decyzji (`ai_docs/process/decisions/`) i
archiwa stanu otwieraj tylko, gdy wskazuje je `Relevant docs` albo indeks i
okno nie wystarczają do oceny sprzeczności; w archiwach szukaj (`rg`), nie
czytaj ich w całości.

## Zasady nadrzędne

- Przed tworzeniem, aktualizacją lub wykonywaniem planu przeczytaj w całości
  `ai_docs/process/PLAN_STANDARD.md` i zastosuj jego kontrolę jakości oraz
  `ai_docs/process/TASK_TEMPLATE.md`; sam link nie zastępuje odczytu.
- Ostatnią sekcją każdego planu musi być `Przypisanie modeli do zadań` z tabelą
  `Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review`: wiersz na
  task z dokładnym dostępnym modelem i wspieranym reasoning, bez „ten sam
  model” (reguły: `PLAN_STANDARD.md`).
- Z użytkownikiem rozmawiaj i przedstawiaj plany po polsku, chyba że poprosi
  inaczej. Dokumenty pisz w ich języku; nie tłumacz przy okazji
  identyfikatorów, kodu ani istniejącej dokumentacji.
- Czat pisz w stylu `caveman lite` (skill `caveman`, poziom `lite`): zwięzłe
  pełne zdania, bez wstępów, grzeczności, asekuracji i narracji przed
  narzędziami. Kod, komendy, cytaty błędów, pliki (dokumenty, taski, `Outcome`)
  i commity pisz normalnie. Wyjdź ze stylu przy ostrzeżeniach
  bezpieczeństwa, potwierdzaniu operacji nieodwracalnych, wieloetapowych
  instrukcjach podatnych na błędny odczyt i na prośbę („stop caveman”, „normal
  mode”).
- Nie rozszerzaj zakresu bez wyraźnej potrzeby. Domyślnie implementuj wyłącznie
  task wskazany przez użytkownika.
- Wyraźne polecenie uruchomienia etapu zaakceptowanego planu obejmuje wszystkie
  jego taski w kolejności planu oraz delegowanie wykonawców i audytorów według
  tabeli modeli; sama tabela nie jest zgodą na delegowanie. W planie bez etapów
  zatrzymaj się po tasku, chyba że użytkownik wyraźnie polecił cały plan.
- Przed kodowaniem ponownie przeczytaj aktywny task i jego fragmenty
  zaakceptowanego planu; sprzeczność zgłoś przed implementacją.
- Nie podejmuj ukrytych decyzji produktowych; zapisz je jako pytanie, założenie
  albo decyzję.
- `sequence_number` jest częścią domeny (deterministyczna kolejność układów), a
  nie technicznym identyfikatorem. Nie uruchamiaj kalkulacji targetu, dopóki
  pozycja sekwencji nie jest jednoznacznie ustalona.
- Obrazy przechowuj jako ścieżkę i metadane, nie jako duże obiekty binarne w
  głównych tabelach domenowych.
- Zmiany schematu bazy wykonuj wyłącznie przez migracje Alembic.
- Kontrakt API definiuje backend i OpenAPI; frontend nie może utrzymywać ręcznie
  rozbieżnych typów. Zmiana API wymaga jednego pionu: backend, OpenAPI,
  wygenerowany klient, wrapper klienta i test żądania.
- Komendy i instrukcje lokalne muszą działać na Windows PowerShell, chyba że
  zadanie mówi inaczej.
- Nie wykonuj destrukcyjnych operacji na danych bez wyraźnej zgody użytkownika.
- Nie dodawaj Redis/Celery, mikroserwisów ani chmury, dopóki pomiary nie pokażą
  takiej potrzeby.

## Budżet tokenów i zgoda na kosztowne prace

Zasady obowiązują wszystkich agentów, w tym subagentów, wykonawców i audytorów.

- Przed długą lub bardzo złożoną zmianą, która może zużyć około 10% lub więcej
  pakietu użytkownika, ostrzeż go (zakres, powód złożoności, czas, szacunek
  zużycia, jeśli wiarygodny; bez zmyślonych procentów) i uzyskaj wyraźną zgodę;
  do tego czasu nie zaczynaj kosztownej implementacji, delegowania, audytów ani
  szerokich testów. Brak szacunku nie zwalnia z ostrzeżenia.
- Koszt obejmuje agenta, subagentów, audyty, ponowne odczyty i kontrole. Nie
  dziel zadania, aby obejść zgodę. „Kontynuuj”, „dokończ” ani „pracuj
  samodzielnie” bez wcześniejszego ostrzeżenia nie są zgodą; zatwierdzony
  zakres nie upoważnia do nieograniczonego zużycia.
- Gdy koszt lub czas istotnie wzrośnie, zatrzymaj kosztowną część, podaj wynik i
  pozostały zakres, uzyskaj zgodę na kontynuację. Przestrzegaj limitów
  użytkownika; nie powtarzaj bez potrzeby audytów i testów z aktualnym wynikiem.

### Oszczędzanie kontekstu

Pilot TASK-0939 (do czasu pomiaru): kodu szukaj od
`ai_docs/architecture/CODE_MAP.md`, potem `rg` na `CODE_MAP_SYMBOLS.md`, a plik
otwieraj z `offset`/`limit` (plik ponad 200 KB tylko tak; hook `PreToolUse`).
Szeroką eksplorację deleguj subagentowi `repo-explorer` (tańszy model; zwraca
ścieżkę, symbol, linie i 1–3 zdania, nie zrzuty plików). Do promptów subagentów i
audytorów nie wklejaj całych dokumentów procesu; podaj ścieżkę i zakres. Task
zmieniający moduły lub publiczne symbole regeneruje mapę
(`scripts/generate_code_map.py`) w swoim commicie. Z włączonym MCP Serena
preferuj `find_symbol` i `find_referencing_symbols`; Serena i Graphify
(`ai_docs/guides/TOKEN_TOOLING.md`) trafiają tu na stałe dopiero po werdykcie
„zostaje” pilota.

## Kontrola lokalnych usług API i Admin

- API i Admin uruchamia, zatrzymuje i restartuje użytkownik we własnych
  terminalach. Agent robi to tylko na osobne, wyraźne polecenie w bieżącym
  zadaniu; polecenie naprawy, diagnozy lub testów nie jest taką zgodą, także na
  przejęcie portów lub ukrytą instancję w tle. Zgoda na restart nie przechodzi
  na kolejne zadania.
- Gdy poprawka wymaga restartu, podaj użytkownikowi komendę. Status procesu i
  portu sprawdzaj bez zmiany stanu; nie kończ cudzych procesów.

## Trwałość rozwiązań

- Usuwaj przyczynę trwale: naprawa działa w nowym procesie, terminalu i po
  restarcie komputera. Zmiana bieżącego `PATH`, zabicie procesu, jednorazowa
  komenda lub stan w pamięci to obejście sesyjne, nie naprawa.
- Konieczne obejście sesyjne oznacz jawnie i dodaj trwałą konfigurację, kod,
  migrację, test lub instrukcję operatorską usuwającą przyczynę.
- Weryfikuj trwałość z nowego procesu albo odczytem zapisanej konfiguracji; bez
  tego nie raportuj problemu jako definitywnie naprawionego i zapisz ryzyko.

## Cykl wykonania zadania

### Przed kodowaniem

1. Potwierdź zakres zadania na podstawie dokumentacji.
2. Wypisz pliki, które prawdopodobnie zostaną zmienione.
3. Sprawdź otwarte pytania blokujące.
4. Bezpieczne założenie zapisz w zadaniu i `CURRENT_STATE.md`.
5. Założenie zmieniające model domenowy albo architekturę zapisz w
   `DECISION_LOG.md` według reguł jego nagłówka; przenosząc wiersze ponad 30 do
   `DECISION_INDEX_ARCHIVE.md`, zmień tylko ścieżkę linku na
   `DECISION_LOG_2026.md#…`.

### W czasie kodowania

- Jeden spójny pion funkcjonalny naraz; testy razem z kodem. Małe moduły,
  jawne nazwy domenowe, logika domenowa oddzielona od HTTP, UI i ORM, algorytmy
  jako czyste, deterministyczne funkcje.
- Gdy nowe UI wymaga rozszerzenia API, zgłoś to użytkownikowi przed zmianą i
  rozszerz zgodnie istniejący kontrakt zamiast tworzyć równoległy endpoint.
- Wspólny komponent zachowuje domyślne zachowanie istniejących konsumentów: nowe
  opcje są opcjonalne, a poprzedni workflow musi dostać test regresyjny.

### Testy, benchmarki i regresje

- Kolejność: testy zmienionego pionu, jego lint i typecheck, potem szersze testy
  i build.
- Benchmarki, testy obciążeniowe, wielomilionowe fixture'y i sztuczne dane tylko
  na wyraźne polecenie; najpierw analiza albo ograniczony test na istniejących
  danych.
- Nie osłabiaj ani nie usuwaj testu dla zielonego wyniku; zmieniaj go tylko przy
  świadomej zmianie kontraktu. Naprawa regresji dostaje test odtwarzający
  przypadek (także restart, utraconą odpowiedź, konflikt rewizji, wznowienie).
- Niezwiązany wcześniejszy błąd nie rozszerza zakresu: potwierdź jakość
  zmienionych modułów, opisz blocker i zostaw go poza commitem.

### Trwałe workflowy i operacje danych

- Workflowy na jobach, manifestach, stagingu lub IndexedDB weryfikuj po
  restarcie procesu i utracie odpowiedzi API; sukces w jednej sesji nie dowodzi
  trwałości.
- Implementacja mechanizmu destrukcyjnego nie jest zgodą na jego wykonanie.
  Migracje destrukcyjne, GC, cleanupy i usuwanie danych wymagają osobnego
  preview i jawnego potwierdzenia.

### Limity czasu i procesy długotrwałe

- Każda skończona komenda musi mieć jawny timeout, domyślnie ≤ 120 s; dłuższy
  tylko dla znanego builda lub benchmarku po uprzedzeniu użytkownika oraz dla
  audytu krzyżowego (≤ 600 s, według skilla audytu).
- Serwery, watchery i procesy bez końca uruchamiaj jako osobny, kontrolowany
  proces (nie foreground), zapisz PID, gotowość sprawdzaj pollingiem ≤ 10 s.
- Komendę bez nowego wyniku przez 60 s (poza kontrolowanym buildem lub
  benchmarkiem) przerwij, sprawdź proces i zgłoś przyczynę przed ponowieniem
  inną metodą. Każdy polling (port, proces, job, urządzenie) ma limit prób i
  krótkie timeouty odczytów.
- Po przerwaniu lub timeoutcie sprawdź osierocone procesy; nie uruchamiaj
  drugiej kopii usługi przed ustaleniem stanu pierwszej.

### Wersjonowanie commitów

Każdy ukończony task, a także niezależna poprawka błędu przed taskiem, ma osobny
commit `vX.Y.N - {opis}`; `N` jest następny po najnowszym wersjonowanym commicie
bieżącego brancha w `git log` (nie z nazwy brancha ani pamięci). Numeru nie
wolno ponownie użyć ani pominąć bez jawnej decyzji użytkownika. Kontrole commita
i zapis wersji z hashem opisuje skill `task-close`.

### Brudny worktree i zakres commita

Zmiany sprzed taska należą do użytkownika, chyba że ich pochodzenie jest
jednoznacznie znane: nie usuwaj ich, nie formatuj masowo, nie commituj. Do
indeksu dodawaj wyłącznie pliki i hunki taska (sposób: skill `task-close`).

### Po kodowaniu

Zamykając każdy task, użyj skilla `task-close` (`scripts/close_task.py`); prowadzi
kroki 3–5, commit i zapis hasha.

1. Uruchom formatowanie, lint, testy i kontrolę typów zmienionych części.
2. Zaktualizuj dokumentację, jeżeli zmieniło się zachowanie, API, model danych
   lub decyzja.
3. Zaktualizuj `CURRENT_STATE.md` według reguły okna i sprawdź
   `npm run docs:check`.
4. Uzupełnij `Outcome` zadania.
5. Przenieś zadanie `done` do `ai_docs/tasks/completed/`.
6. Raport końcowy: zmiany, testy, czego nie wykonano, następne kroki, ryzyka.
7. Porównaj rezultat punkt po punkcie z Definition of Done taska i planem.
8. Po raporcie zatrzymaj się, chyba że użytkownik wyraźnie uruchomił cały etap
   albo cały plan bez etapów; wtedy po audycie (jeśli wymagany), commicie,
   `Outcome` i `CURRENT_STATE.md` każdego taska kontynuuj do końca zakresu.
   Zatrzymaj się na końcu etapu albo przy sprzeczności wymagań, koniecznej
   decyzji, niedostępnym modelu/reasoning, otwartych P0/P1 po jednej rundzie
   poprawek (P2 odnotowane w `Outcome` nie zatrzymują) lub przed operacją czy
   kosztem poza zatwierdzonym zakresem. Push, aktywacja modelu i wdrożenie
   nigdy nie są automatyczne.

### Scalanie do gałęzi integracyjnej

Integruj do `main`, chyba że użytkownik wskaże inną gałąź; pracuj na roboczej.
Scal cały zakres po kontrolach, dokumentacji, commitach, wyraźnej
akceptacji wyniku i zgodzie na merge. Pytaj raz o zakres; akceptacja planu,
polecenie implementacji ani milczenie nie są zgodą. Zgoda obejmuje push
do origin i obowiązkowe usunięcie worktree tej pracy (jeśli istnieje)
i lokalnej gałęzi, bez kolejnego pytania. Po merge i pushu sprawdź commity
w `main`. Chroń główny checkout, cudze zmiany i niescalone
commity; blocker sprzątania zgłoś, bez wymuszania. P0/P1 lub niewykonana
wymagana migracja blokują merge. Procedura: `merge-to-main`.

## Audyt krzyżowy

Audyt jest wymagany tylko, gdy wskazuje go kolumna `Dodatkowy review` planu;
operator może z niego zrezygnować dla planu lub taska (zapis w `Outcome`).
Audytuje model z innej rodziny niż wykonawca (pracę Claude Codex, pracę Codex
Claude), tylko do odczytu, przed commitem; wykonawca nie audytuje własnej pracy.
Otwarte P0/P1 blokują commit; jedna runda audytu i jedna runda poprawek, bez
pętli. Procedurę, audytora zastępczego, limity czasu i format raportu opisują
skille `audit-task` (Claude Code) i `claude-audit` (Codex). Poświadczeń CLI
agent nie wpisuje.

## Hierarchia źródeł prawdy

Przy sprzeczności obowiązuje kolejność:

1. zaakceptowane decyzje w `ai_docs/process/DECISION_LOG.md` (pełne wpisy w `ai_docs/process/decisions/`),
2. wymagania w `ai_docs/requirements/`,
3. architektura w `ai_docs/architecture/`,
4. aktywne zadanie,
5. komentarze w kodzie,
6. istniejąca implementacja.

Gdy implementacja jest sprzeczna z dokumentacją, nie zakładaj, że kod ma rację; zgłoś rozbieżność.

## Standard jakości

Zadanie nie jest ukończone tylko dlatego, że aplikacja się uruchamia. Obowiązuje `ai_docs/process/DEFINITION_OF_DONE.md`.
