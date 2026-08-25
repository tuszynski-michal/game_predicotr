---
title: TASK-0290 — Benchmark i kontrolowany rollout zdalnej ręcznej selekcji
status: in_progress
last_updated: 2026-08-24
---

# TASK-0290 — Benchmark i kontrolowany rollout zdalnej ręcznej selekcji

## Status

`in_progress`

## Goal

Udostępnić audytowalny harness etapów 1–5, który zatrzymuje rollout po każdej
niespełnionej bramce oraz dokumentuje realne wyniki bez sekretów, ścieżek hosta
ani kopiowania JPEG-ów do repozytorium.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`

## Scope

- wersjonowany, content-addressed parser, walidator i agregator raportów,
- deterministyczny lokalny etap 1 z fault injection i zgodnością
  decision/host-files/output-v1/trace-v1,
- jawne checkpointy 10/500/1000/8000/15000 operacji,
- metryki UX/API/transferu/host queue, retry, konflikty i rozkład rozmiarów,
- fail-closed zależność etapów, raporty bez sekretów/absolutnych ścieżek,
- runbook pilotażu, feature flag oraz rollbacku,
- automatyczne testy kontraktu raportu i lokalnego harnessu;
  scenariusze wieloprofilowe, LAN i Quick Tunnel jako jawne kroki operatorskie.

## Out of scope

- automatyczne uruchamianie testów 8 000 lub 15 000 bez osobnej zgody właściciela,
- test publicznym Quick Tunnel podczas implementacji,
- nowy protokół chunkowanego transferu (TASK 19),
- zmiana algorytmu selekcji zdjęć albo osłabienie bramki bezpieczeństwa TASK-0289.

## Acceptance criteria

- [ ] Każdy etap ma kanoniczny, content-addressed raport i zamkniętą walidację.
- [ ] Raport blokuje przejście etapu po utracie, duplikacie, konflikcie, błędzie
  kolejki, niezgodności manifestu/JPEG/JSON lub braku wymaganej metryki.
- [ ] Etap 1 wykonuje select/deselect/undo/retry/restart/finalize na
  deterministycznym fixture bez duplikatów finalnych plików.
- [ ] Etapy 2–5 mają jednoznaczne limity, zgody i checklistę środowiska.
- [ ] Runbook opisuje feature flag, monitoring, rollback, revoke i recovery.
- [ ] Raport nigdy nie zawiera kodu dostępu, tokenu, cookie ani absolutnej ścieżki.
- [ ] Etap 4/5 nie może zostać uruchomiony ani zaliczony przypadkiem.

## Progress

### v0.7.42 — kontrakt raportu, runbook i lokalna bramka etapu 1

- Dodano `remote-manual-selection-rollout-v1`: kanoniczny, checksumowany raport
  z bramką kolejności etapów, metrykami UI/API/transferu/kolejki, czasem,
  throughputem, CPU/pamięcią i fail-closed kontrolą integralności.
- Deterministyczny etap 1 wykonuje select/deselect/undo, exact retry,
  stale-generation, finalizację i recovery bez publicznego endpointu.
- Przeszły: testy kontraktu raportu oraz PowerShellowy etap 1 i jego
  weryfikacja kanoniczności. Nie wykonano etapów 2–5, LAN ani Quick Tunnel.
- Etapy 4 i 5 wymagają jednocześnie jawnej zgody właściciela w obserwacji i
  parametrów `-AllowLarge` oraz `-OwnerApproval`; skrypt nie uruchamia sesji,
  tunelu ani transferu.

### v0.7.43 — lokalna podbramka etapu 2 i bezpieczne ponowienie transferu

- Etap 2 ma zakres 100–500 operacji i osobną bramkę środowiskową. Lokalny
  harness przetwarza 100 JPEG-ów przez produkcyjny control plane, streaming,
  materializację, finalizację i rzeczywisty tymczasowy filesystem.
- Fault injection obejmuje exact retry operacji, przerwany transfer hosta,
  rekonstrukcję usługi po pięćdziesiątej decyzji oraz revoke. Wynik zachowuje
  status `blocked`, ponieważ nie wykonano jeszcze rzeczywistego UI, dwóch
  profili, LAN, restartu API ani zmiany URL tunelu.
- Harness wykrył błąd finalizacji po udanym ponowieniu przerwanego transferu.
  Udana zweryfikowana próba anuluje teraz starsze nieudane próby tego samego
  pliku i generacji, nie usuwając ich audytowego wpisu ani nie osłabiając
  rewizyjnej bariery finalizacji.
- Lokalna podbramka zakończyła 100 operacji, 100 materializacji i zgodność
  100 plików z output/trace bez utraty, duplikatu i błędu checksummy. Raport:
  `artifacts/remote-manual-selection-rollout/stage-2-local.json` (lokalny,
  ignorowany przez Git).

### v0.7.44 — poprawka pickera źródła ujawniona przez próbę UI

- Rzeczywista próba operatorska wykryła, że identyfikator przekazany do
  `showDirectoryPicker()` przekraczał limit 32 znaków Chromium i blokował wybór
  folderu przed indeksowaniem.
- Reviewer używa teraz krótkiego, stabilnego identyfikatora
  `gp-remote-source-v1`, dzięki czemu zachowuje pamięć ostatniego folderu i nie
  narusza limitu API.
- Test regresyjny sprawdza długość, stabilną wartość i dozwolony alfabet. Pełne
  testy Reviewera, lint oraz typecheck pozostają zielone; istniejące ostrzeżenie
  `no-img-element` nie dotyczy tej zmiany.

### v0.7.45 — poprawne wywołanie natywnego fetch w Chromium

- Próba po wybraniu źródła wykryła `Illegal invocation`: natywny
  `window.fetch` był przechowywany w klasie transportu i wywoływany z instancją
  transportu jako odbiorcą zamiast z globalnym obiektem przeglądarki.
- Zarówno control plane tworzenia kolekcji/partii, jak i transport wybranych
  JPEG-ów wiążą teraz wywołanie z `globalThis`.
- Osobne testy regresyjne wymuszają właściwy receiver dla obu transportów.
  Pełne 109 testów Reviewera, typecheck i lint przechodzą; wcześniejsze
  ostrzeżenie `no-img-element` pozostaje poza zakresem tej poprawki.

### v0.7.46 — parytet widoku i trwały pionowy scroll

- Zdalny workspace wykorzystuje teraz klasy nagłówka, toolbara, nawigacji,
  płótna zdjęcia i akcji lokalnej ręcznej selekcji zamiast osobnego zestawu
  natywnie wyglądających kontrolek.
- Viewport ukrywa poziomy overflow i centruje powiększone zdjęcie. Pionowy scroll
  jest zapamiętywany przed zmianą indeksu i odtwarzany przez animation frame
  dopiero po załadowaniu obrazu oraz obliczeniu nowego rozmiaru.
- Usunięto natywny suwak zoomu; przyciski `−/+`, select skoku, fullscreen i
  przyciski decyzji używają tego samego systemu co Admin. Dwa testy kontraktu UI
  pilnują parytetu klas, braku poziomego scrolla i kolejności restore.
- Pełne 111 testów Reviewera, typecheck, lint i formatowanie przechodzą;
  wcześniejsze ostrzeżenie `no-img-element` pozostaje poza zakresem.

### v0.7.47 — brak utraty decyzji i bariera finalizacji

- Rzeczywista partia 100 plików zakończyła się z `2 selected / 2 synced`, choć
  operator wykonał cztery szybkie zatwierdzenia. PostgreSQL zawierał wyłącznie
  dwa polecenia `select`, co potwierdziło utratę jeszcze przed transferem.
- Interaktywne decyzje są szeregowane, a zapis operacji współdzieli kolejkę z
  telemetrycznym `viewed`, dzięki czemu numery klienta i rewizje nie ścigają
  się. Polecenie dla nieaktualnego podglądu jest jawnie odrzucane zamiast
  zastosowania do kolejnego zdjęcia.
- Żądanie synchronizacji otrzymane podczas aktywnego przebiegu wymusza następny
  przebieg. Preview i wykonanie finalizacji czekają za kolejką interakcji,
  sprawdzają pusty lokalny outbox i ponownie pobierają aktualny preview hosta.
- Cofnięcie przywraca kursor do źródłowego zdjęcia cofanej decyzji, więc skutek
  jest natychmiast widoczny. Testy obejmują cztery szybkie operacje, coalescing
  synchronizacji, cursor undo i lokalną barierę finalizacji.

### v0.7.48 — odporny bootstrap mobilny

- Próba na telefonie przez Quick Tunnel zatrzymała się na `Sprawdzanie sesji…`,
  mimo że publiczny endpoint context odpowiadał. Bootstrap nie zakłada już, że
  mobilny `sessionStorage` i `crypto.randomUUID` są zawsze dostępne.
- Id klienta ma session-only fallback w pamięci i ręczne UUID v4 oparte na
  `getRandomValues`. Wszystkie trzy operacje bramki dostępu używają wspólnego
  limitu 12 sekund, więc niedziałający ingress kończy się jawnym komunikatem i
  formularzem zamiast bezterminowego ekranu ładowania.

### v0.7.49 — transfer po szybkim `F` i obie osie viewportu

- Rzeczywista partia `1b041c96…` miała `9 selected`, ale `0 transferów` i
  `0 synced`. Aktywny skan transferów mógł po nowej decyzji ponownie ustawić
  wysoki kursor i bezpowrotnie ominąć wcześniejszy ordinal.
- Kursor jest aktualizowany compare-and-set względem początku skanu. Przewinięcie
  wstecz przez nową decyzję wygrywa ze starszym przebiegiem, a ponowne otwarcie
  workspace'u skanuje od początku i odzyskuje już potwierdzone wybory.
- Poziomy scroll wraca dla powiększonego obrazu. Obie osie są przechwytywane
  przed każdą zmianą zdjęcia i odtwarzane po decode oraz obliczeniu wymiarów.

### v0.7.50 — odzyskanie zegara klienta i uproszczony viewport

- Rzeczywista partia miała na hoście zastosowane sekwencje `1–14`, a karta
  próbowała wysłać pod zużytym numerem inną operację. Przyczyną było pominięcie
  `lastClientSequence` podczas reconciliacji oraz utożsamienie dwóch kart o
  skopiowanym `clientInstanceId`.
- Delta aktualizuje teraz oba zegary klienta. `CLIENT_SEQUENCE_REPLAY` uruchamia
  jeden bezpieczny rebase całego niepotwierdzonego outboxu, bez usuwania decyzji
  i bez zmiany `operationId`. Osobny `tabInstanceId` wymusza jednego lokalnego
  writera również po skopiowaniu karty.
- Panel liczników z prawej strony usunięto. Podgląd zajmuje pełną szerokość,
  legenda jest pod zdjęciem, a pod nagłówkiem dostępu pozostają przyciski
  synchronizacji i gotowości. Zoom ma jawnie nieograniczone wymiary obrazu,
  a obie osie scrolla wracają po dwóch klatkach layoutu.

### v0.7.51 — operator-local wynik i rzeczywisty parytet viewportu

- Po powtarzających się rozjazdach decyzji i transferów właściciel wybrał
  prostszy model: link jest bramką dostępu, natomiast JPEG-i, decyzje, kursor,
  zoom, scroll i manifest pozostają wyłącznie na urządzeniu operatora.
- Operator wybiera folder źródłowy oraz katalog nadrzędny. Reviewer tworzy
  `<źródło> wybrane`, zapisuje tam oryginalne bajty `seq_*` i nie uruchamia
  control outboxu, transfer scheduler ani host finalization.
- Ujawniono brak bazowych stylów lokalnego selektora w aplikacji Reviewer.
  Zostały przeniesione reguły viewportu, canvasu, toolbara, nawigacji i
  fullscreen; dzięki temu wspólna funkcja dopasowania faktycznie zmienia wymiar
  obrazu, a obie osie scrolla można odtworzyć po zmianie JPEG-a.
- Historyczne etapy transferowe TASK-0290 pozostają audytowalne, ale ich dalszy
  rollout jest wstrzymany. Nowy odbiór powinien mierzyć operator-local zapis na
  drugim komputerze i recovery permission po restarcie.

### v0.7.52 — niezawodny pomiar JPEG-a dla zoomu

- Rzeczywista próba operator-local potwierdziła zapis plików, ale ujawniła, że
  mobilny Reviewer mógł zmieniać licznik zoomu bez zmiany wymiaru JPEG-a.
- Zdalny workspace używa teraz zwykłego zdarzenia `onLoad`, tak jak działający
  selektor lokalny, oraz dodatkowo odczytuje naturalne wymiary już
  zdekodowanego/cachowanego obrazu po renderze. Zoom nie zależy już od
  pojedynczego zdarzenia capture.

### v0.7.53 — panel sesji bez historycznych partii hosta

- Usunięto z aktywnego panelu hosta tabelę partii, limit 100 oraz akcje recovery
  i reopen. W trybie operator-local host nie otrzymuje decyzji ani JPEG-ów i nie
  tworzy partii, więc sekcja przedstawiała nieaktywny wariant transferowy.
- Trwałe historyczne API i dane pozostają audytowalne, ale nie są prezentowane
  jako część bieżącego workflow operatora.

### v0.7.54 — ograniczony widok najnowszych sesji

- Admin pobiera i pokazuje wyłącznie dziesięć najnowszych sesji, sortowanych
  deterministycznie malejąco po dacie utworzenia i identyfikatorze.
- Starsze sesje pozostają w audycie i nie są automatycznie usuwane ani
  unieważniane; ograniczenie dotyczy wyłącznie aktywnego panelu właściciela.

### v0.7.55 — zachowanie scrolla po zatwierdzeniu

- Zatwierdzenie operator-local nie resetuje już wymiarów tego samego podglądu
  podczas drugiego odświeżenia lokalnego okna danych. Podgląd jest resetowany
  wyłącznie wtedy, gdy zmienił się ordinal albo Object URL JPEG-a.
- Dzięki temu po `Enter`, `F` i przycisku zapisu obie osie są odtwarzane tak samo
  jak po nawigacji strzałkami; zapis pliku i manifestu pozostaje niezmieniony.

### v0.7.56 — bezpieczny folder wynikowy i wznowienie z manifestu

- Folder `<źródło> wybrane` musi być pusty albo zawierać kompletny manifest i
  dokładnie wskazane w nim JPEG-i. Niepusty folder bez manifestu, obcy plik lub
  brak wyniku wskazanego przez decyzję blokuje selekcję przed pierwszym zapisem.
- Manifest operator-local przechowuje checksumę manifestu źródła, liczbę
  JPEG-ów, pierwszy zakres i kierunek. Poprawny wynik odtwarza kursor, następny
  zakres i decyzje także po utworzeniu nowego linku; losowe `fileId` są mapowane
  na ponownie zaindeksowane źródło według ordinalu i ścieżki.
- Testy obejmują pusty folder, obce dane, kompletny wynik, wznowienie między
  access sessions i blokadę innego źródła.

### v0.7.57 — scroll przypięty do docelowego zdjęcia

- Poprzednia flaga oczekującego odtworzenia była ustawiana przed asynchronicznym
  zapisem JPEG-a. Render `busy` starego podglądu uruchamiał efekt i zerował ją,
  zanim kursor przeszedł na następne zdjęcie.
- Odtworzenie przechowuje teraz ordinal docelowego JPEG-a. Jest uzbrajane
  dopiero po trwałym wyznaczeniu następnego kursora i może zostać skonsumowane
  wyłącznie przez podgląd tego ordinalu po wyliczeniu jego wymiarów.
- Test regresyjny pilnuje kolejności `capture → durable decision → arm target →
  render target` oraz zachowania obu osi.

### v0.7.58 — moment przechwycenia zgodny z lokalnym selektorem

- Przechwycenie pozycji zostało przeniesione z początku asynchronicznej operacji
  na moment po trwałym zapisie decyzji, bezpośrednio przed `setBatch`, dokładnie
  jak w działającym lokalnym selektorze. `skip` nie uzbraja przejścia, ponieważ
  nie zmienia zdjęcia.
- Rzeczywisty komponent przetestowano w przeglądarce na dużym JPEG-u przy zoomie
  200%. W desktopowym viewportcie `scrollTop=300` pozostał równy 300, a przy
  viewportcie telefonu 390×844 `scrollTop=388,8` pozostał równy 388,8 po zapisie
  i przejściu na kolejny obraz.
- Tymczasowy ekran testowy i proces na porcie 3011 zostały usunięte po pomiarze;
  nie stanowią części produktu ani commita.

### v0.7.59 — stabilny canvas podczas zmiany JPEG-a

- Operator potwierdził w Chrome na macOS, że reset dotyczy wewnętrznego
  `scrollTop` zdjęcia wyłącznie po Enter/F/kliknięciu zatwierdzenia, nie przy
  zwykłej nawigacji i nie dla dokumentu. Hipoteza scrolla strony została
  odrzucona i nie weszła do produktu.
- Pozycja obu osi jest przechwytywana synchronicznie w chwili komendy
  zatwierdzenia, przed zapisem pliku i przejściem w `busy`. Oczekujące
  odtworzenie blokuje zdarzeniom scrolla nadpisanie snapshotu.
- Canvas nie jest już zastępowany tekstem ładowania podczas zmiany ordinalu i
  nie zeruje wymiarów. Poprzedni podgląd utrzymuje przestrzeń scrolla do chwili
  zdekodowania następnego JPEG-a.
- Odtworzenie wymaga teraz równocześnie docelowego ordinalu, URL-a, wymiarów i
  `decoded=true`; wykonuje trzy kolejne przejścia layoutu. Skrót zatwierdzenia
  również nie przyjmuje niezdekodowanego zdjęcia.
- Test regresyjny blokuje ponowne dodanie `setNaturalImageSize(null)` i
  warunkowe usuwanie canvasu przy samej niezgodności ordinalu.

### v0.7.60 — aktualny build jako część readiness Reviewera

- Rzeczywisty test wykazał, że port 3001 nadal obsługiwał produkcyjny proces
  uruchomiony przed buildami `v0.7.57–v0.7.59`. Kontroler uznawał dowolny
  produkcyjny CSP za gotowość i ponownie używał starego JavaScriptu.
- Readiness porównuje teraz `.next/BUILD_ID` z identyfikatorem obecnym w HTML
  działającego Reviewera. Niezgodny produkcyjny listener Node jest zatrzymywany
  przed uruchomieniem aktualnego builda; proces developerski nadal jest
  blokowany bez automatycznego zatrzymania.
- Po starcie stan lifecycle zapisuje rzeczywisty proces nasłuchujący na
  `127.0.0.1:3001`, nie wrapper `npm.cmd`, dzięki czemu kolejna wymiana może
  zweryfikować PID, czas startu i executable.
- Test pełnego komponentu z opóźnionym zapisem pliku i decyzji utrzymał
  `scrollTop=420` przed zapisem, podczas niego i po przejściu na następny JPEG.
  Tymczasowa trasa oraz Reviewer na porcie 3011 zostały usunięte po pomiarze.

### v0.7.61 — bezpieczny restart wyniku operator-local

- Uchwyt katalogu nadrzędnego wyniku jest utrwalany razem z sesją operatora.
  Usunięty folder `<źródło> wybrane` jest odtwarzany po powrocie do karty, a
  batch wraca do pierwszego zdjęcia, pierwszego zakresu i pustej listy decyzji.
- Jawny przycisk `Restart selekcji` wymaga potwierdzenia i zapisuje nowy pusty
  manifest. Istniejący folder może zostać usunięty wyłącznie po walidacji
  źródła, kompletności manifestu oraz checksum wszystkich zarządzanych JPEG-ów;
  obce dane pozostają nietknięte i blokują restart.
- Celowane testy folderu, IndexedDB i kontraktu UI oraz pełny zestaw Reviewera,
  typecheck i lint są zielone; lint zachowuje jedno wcześniejsze ostrzeżenie dla
  source-native elementu `<img>`.

### v0.7.62 — filtr najnowszych sesji hosta

- Lista `Najnowsze sesje` ma dwa jawne widoki: `Aktywne` dla `draft/active`
  oraz `Zakończone` dla `completed/expired/revoked`. Domyślny jest widok
  aktywny, a zmiana filtra wybiera pierwszą najnowszą widoczną sesję.
- Admin pobiera maksymalnie 100 lekkich metadanych i pokazuje najwyżej 10
  najnowszych wpisów wybranej kategorii, dzięki czemu nowe zakończone rekordy
  nie wypychają nadal aktywnych sesji.
- Pełne 250 testów Admina, typecheck, lint i produkcyjny build przechodzą; lint
  zachowuje dwa wcześniejsze ostrzeżenia dla source-native `<img>`.

### v0.7.63 — recovery po usunięciu lokalnego katalogu

- `NotFoundError` z odczytu źródła, zapisu JPEG-a, manifestu, cofania albo
  kontroli po powrocie do karty uruchamia jeden wspólny recovery.
- IndexedDB atomowo zeruje decyzje, kursor i następny zakres, odłącza source,
  output oraz output-parent handles i pozostawia zachowany manifest metadanych
  wyłącznie do ścisłej walidacji ponownie wskazanego źródła.
- UI nie próbuje pracować na martwym uchwycie. Wymaga ponownego wyboru folderu
  zdjęć, następnie katalogu zapisu, i dopiero wtedy pozwala utworzyć pusty
  manifest oraz rozpocząć od pierwszego zdjęcia.
- Konflikty checksum, obce pliki i niezgodny manifest nadal są fail-closed i nie
  uruchamiają automatycznego resetu.

### v0.7.64 — potwierdzenie aktywnego modelu symboli

- Odczyt lokalnego rejestru potwierdził, że najnowsza iteracja `#3`
  `47b6aa0d-2cea-4765-97f0-ee1f86cfc056` ma status `candidate_ready` i jest
  już aktywna od 2026-08-19.
- Nie utworzono drugiego zdarzenia aktywacji: API prawidłowo zwraca
  `SYMBOL_MODEL_ALREADY_ACTIVE`. Historyczny odrzucony kandydat v19 pozostaje
  oddzielnym artefaktem audytowym.

### v0.7.71 — prosty konfigurator i modal bezpiecznego resetu

- Zdalny ekran operator-local pokazuje od początku osobne akcje wyboru zdjęć i
  katalogu zapisu. Katalog nadrzędny można wskazać przed źródłem; po jego
  indeksowaniu Reviewer tworzy albo waliduje `<źródło> wybrane`.
- Poprawny manifest z checksumami wynikowych JPEG-ów jest weryfikowany przed
  adopcją przez nowy link, po czym odtwarzane są zdjęcie, zakres i decyzje.
- Restart używa własnego modala z liczbą usuwanych zdjęć. Modal blokuje skróty
  oraz nawigację; zatwierdzony reset nadal usuwa tylko zweryfikowany własny
  wynik i zapisuje nowy pusty manifest.

### v0.7.72 — nie-destrykcyjny powrót do konfiguratora

- Aktywny operator-local workspace ma obok restartu `Ekran startowy`. Przycisk
  wraca do obu pickerów katalogów bez kasowania batcha, manifestu, decyzji,
  kursora ani numeracji; jawne `Wróć do selekcji` otwiera ten sam workspace.

### v0.7.74 — przełączanie katalogów bez utraty batcha

- Konfigurator rozpoznaje istniejący lokalny batch po nazwie źródła i
  checksummie manifestu, dzięki czemu ponowne wskazanie tej samej pary folderów
  odtwarza kursor oraz zakres. Inny katalog jest nowym przełączeniem, nie
  błędem `REMOTE_SELECTION_SOURCE_CHANGED`; aktywny relink poza ekranem
  startowym pozostaje rygorystyczny.
- Wynik zawierający decyzje nie może zostać przypadkowo podmieniony pustym
  folderem: przełączenie wymaga zgodnego, weryfikowalnego manifestu.

## Open checkpoint before a public pilot

Architektura w sekcji 21 opisuje feature flag jako domyślnie nieaktywną do
odbioru, ale obecne `API_CONTRACT.md`, `LOCAL_OPERATION_GUIDE.md` i konfiguracja
procesów opisują/wdrażają domyślnie włączoną flagę. TASK-0290 nie zmienia tej
wcześniejszej decyzji operacyjnej. Przed etapem z Quick Tunnel właściciel musi
jednoznacznie rozstrzygnąć domyślną politykę flagi oraz potwierdzić ją w nowym
procesie API i Reviewera.

## Outcome

TASK pozostaje otwarty dla benchmarku i checkpointów rolloutowych. Zmiana v0.7.71
nie uruchamia Quick Tunnel, transferu ani dodatkowych etapów benchmarku.
