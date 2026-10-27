---
title: Wyszukiwanie po maksymalnie czterech kolejnych układach
status: accepted
last_updated: 2026-10-24
---

# Wyszukiwanie po maksymalnie czterech kolejnych układach

Rewizja 3.1, zaakceptowana wraz z kosztem i całym wykonaniem 2026-10-24.

Zmiana operatora 2026-10-27 jest osobnym TASK-1098: przygotowanie wzorów
przed wyszukiwaniem oraz podgląd zdjęć dopasowania i dziesięciu kolejnych.
Zastępuje wcześniejszą bramkę dodawania wzoru po wyszukiwaniu; szczegóły,
testy i ograniczenia zawiera task. Nie ponawia zakresu audytów zadań A/B.
Zadanie A = TASK-1091, zadanie B = TASK-1092. Operator wyłączył migrację swojej
bazy, restarty i scalenie do main. Zgoda na koszt obejmuje dwa audyty
implementacji wskazane w tabeli (A high, B medium), niezależne od już
wykorzystanych prób audytu planu. Dalsza runda po utrzymanym P0/P1 wymaga
zatrzymania i decyzji operatora zgodnie z AGENTS.md.

2026-10-24 operator osobno zatwierdził koszt dodatkowego audytu poprawek B:
Claude Code `claude-opus-5-5` / `medium`, maksymalnie 480 s. Po PASS należy
zamknąć TASK-1092 i wykonać lokalny commit. Bez migracji bazy operatora,
restartów, scalenia do main i push. Jest to runda 2 audytu B, trzeci audyt
implementacji; nie zmienia limitu wykorzystanych audytów planu.

Wynik implementacji: TASK-1091 i TASK-1092 wykonane (v1.7.467–468).
Audyt A: timeout bez werdyktu; audyt B: R1 REVISE, R2 PASS bez P0/P1.
P2-3/P2-4 i ograniczenia odbioru zapisano w Outcome oraz
[raporcie odbioru](../quality/BOARD_SEARCH_SEQUENCE_IMPLEMENTATION_20261024.md).
Fizyczny Android, odbiór na usługach operatora i wdrożenie pozostają niewykonane.

2026-10-25 operator zlecił niezależną poprawkę P2-4 w TASK-1093 z testem
odtwarzającym i regresjami. P2-3 pozostaje odłożone; poprzednie raporty audytu
zachowują historyczny stan z 2026-10-24. Aktualizacja odbioru jest w raporcie powyżej.

Rewizja 3 otrzymała PASS w trzeciej próbie audytu Claude Code,
bez otwartych P0/P1. Następnie doprecyzowano dwie uwagi P2 z tego raportu
(niższy istniejący timeout i etykieta korekty z ciągu); tych dopisków nie
audytowano po raz czwarty. Przebieg i ograniczenia audytu planu:
[podsumowanie audytu](../quality/BOARD_SEARCH_SEQUENCE_PLAN_AUDIT_SUMMARY_20261024.md).

## Źródła i warunki wejścia

Relevant docs dla obu zadań: `AGENTS.md`, `ai_docs/process/PLAN_STANDARD.md`,
`ai_docs/process/TASK_TEMPLATE.md`, `ai_docs/process/DEFINITION_OF_DONE.md`,
`ai_docs/requirements/ADMIN_APP.md` (wyszukiwanie i udostępnianie),
`ai_docs/architecture/API_CONTRACT.md` (board-search, historia i korekty),
`ai_docs/architecture/CODE_MAP.md` oraz indeks decyzji D-570 (777a2), D-548
(panel udostępniania), D-472 (historia) i D-492 (korekty).

Stan obecny: pojedynczy wzór, ranking po gotowym dokumencie per
`game_id + sequence_number`, wspólne UI Admina i Reviewera, osobne proxy
pojedynczego linku i panelu. Nie ma aktywnego taska dotyczącego tego zakresu.
Taski A/B mają numery TASK-1091/1092 sprawdzone w lokalnych gałęziach i aktywnych
worktree; pliki według TASK_TEMPLATE. Implementacja z gałęzi od main,
`codex/board-search-sequence-implementation`, w osobnym worktree na D.

## Zachowanie

Wyszukiwarka dopasowuje od jednego do czterech kolejnych spinów. Funkcja działa w „Wyszukaj plansze” pojedynczej gry, w linku tej gry oraz w panelu gier otwieranym przez udostępnianie.

- Nad edytorem pojawiają się badże „Układ 1”–„Układ 4”. Kliknięcie przywraca wpisany wzór do edycji. Badże nie przechowują wybranych wyników.
- „Szukaj plansz” uwzględnia wszystkie przygotowane układy i aktualizuje wspólną listę dopasowań poniżej.
- „Dodaj układ” dopisuje pusty wzór na końcu, nigdy między badżami. Po zmianie operatora 2026-10-27 (TASK-1098) przycisk jest dostępny na ostatnim badżu po poprawnym wypełnieniu zestawu, także przed pierwszym wyszukiwaniem, gdy nie trwa żądanie ani obliczanie wygranej i liczba wzorów jest mniejsza niż 4.
- „Resetuj” czyści tylko aktywny wzór, zachowując jego miejsce w kolejności.
- „Nowe szukanie” usuwa cały lokalny zestaw i wyniki, pozostawiając pierwszy pusty edytor.
- Przełączanie badży nie zmienia wspólnego wyniku ani wygranych. Edycja wzoru pozostawia dotychczasowe wyniki widoczne z informacją „Wzór zmieniony — wyszukaj ponownie”.
- Puste końcowe wzory nie uczestniczą w dopasowaniu; pozycje badży pozostają zachowane. Puste miejsce między wypełnionymi układami wymaga uzupełnienia; aplikacja nie przesuwa kolejnych spinów. Wzór zawierający wyłącznie `?` jest niepoprawny, a nie pusty. „Szukaj plansz” działa tylko przy niepustym, poprawnym prefiksie bez luk; komunikat wskazuje badż wymagający uzupełnienia.
- „Przybliżona wygrana” korzysta z ostatniej planszy wybranego dopasowania. Zachowuje obecną zasadę liczenia następnych spinów po planszy startowej.

Przyciski, badże, odstępy, fokus i układ mobilny korzystają z istniejących stylów aplikacji.

## Zadanie A — Wspólne dopasowanie, API i historia

Rezultat: backend zwraca ranking całych ciągów, dostępny również przez udostępnianie.

- Rozszerzyć `BoardSearchService` i `SqlAlchemyBoardSearchProjectionRepository.search` o wyszukiwanie ciągu na istniejących fast documents. Porównywać pozycje według `sequence_number`, bez ograniczania kandydatów do osobnych list pierwszych 15 lub 100 wyników.
- Dla 2–4 wzorów przyjąć cykliczną kolejność, gdzie `L = games.expected_layout_count`, `s` to początek w `1..L`, a pozycja wzoru `i` wynosi `((s - 1 + i) % L) + 1`. `L` musi być dodatnie, a liczba wzorów nie większa niż `L`; nie porównujemy tej samej pozycji drugi raz w jednym ciągu. Dokumenty spoza `1..L` nie uczestniczą. Brak dokumentu którejkolwiek pozycji wyklucza ciąg, bez przeskakiwania luk.
- Zachować obecne wagi symboli, alternatywy i wyjątek `777a2`. Dla 2–4 wzorów mianownik `n` jest sumą długości zwalidowanych WZORÓW ZAPYTANIA po usunięciu `?`, niezależnie od kompletności dokumentów. Licznik `w` to suma surowych punktów; dla 777a2 zawiera także `unknown_count` każdego aliasu. Dokładna kolejność SQL: `round((sum(w) * (100.0 / sum(n))).cast(Numeric(10,6)), 1)`. Nie sumować ani nie uśredniać zaokrąglonych procentów pojedynczych plansz. Pokazywać również dopasowanie poszczególnych plansz.
- Dopuszczać ciąg mający dodatni dowód w przynajmniej jednej porównywanej pozycji. Remisy rozstrzygać kolejno przez liczbę dokładnych trafień, ważone alternatywy, mniej sprzeczności, więcej zatwierdzonych plansz i numer początku ciągu.
- Jeden wzór deleguje do istniejącej ścieżki; POST z jednym wzorem musi zwrócić te same plansze, oceny i kolejność co GET. Nie nakładać na tę ścieżkę nowych ograniczeń długości sekwencji.

### Algorytm i granice zasobów

Istniejące punkty zmiany: `services/api/src/game_predictor_api/domain/board_search.py`
(czysty ranking), `application/board_search.py` (`BoardSearchService`) i
`storage/board_search_projection_repository.py` (`SqlAlchemyBoardSearchProjectionRepository`,
`_search_score_expressions`). Dodać proponowaną czystą funkcję referencyjną
`rank_board_search_sequences`; nie przenosić logiki do HTTP lub React.

Jedno zapytanie rankingowe: alias fast document `d0` dla startów w `1..L`,
do 3 INNER JOIN tej samej tabeli po `(game_id, sequence_number)` wyliczonym
powyższym wzorem. Na każdym aliasie zastosować istniejące wyrażenia surowych
punktów i filtr `scope`; dodatni dowód to OR po aliasach. Zsumować surowe
punkty i liczniki, posortować po zaokrąglonym score, exact, ważonych
alternatywach, mismatch, liczbie zatwierdzonych dokumentów, numerze startu
i `review_item_id` dokumentu `d0`; LIMIT dopiero po rankingu. Czysta funkcja
referencyjna ma identyczny priorytet zatwierdzenia (accepted/corrected)
i końcowy tie-break. Nie materializować wszystkich
kandydatów w Pythonie. Dla jednego wzoru użyć istniejącego `search`.

Założona skala do projektu: około 88 tys. plansz według CURRENT_STATE, bez
deklarowania świeżego pomiaru. Praca SQL O(N × k × liczba pól), `k <= 4`;
do aplikacji trafia najwyżej 100 ciągów × 4 plansze. Zapytania o metadane
i znaczniki supergry wykonywać zbiorczo dla unikalnych pozycji z wyniku,
bez N+1; zachować spójny snapshot generacji supergry.

Dla nowego rankingu zapamiętać `current_setting('statement_timeout')`, otworzyć
SAVEPOINT (`session.begin_nested()`) i wewnątrz ustawić mniejszy z limitów:
10 s oraz poprzedni limit znormalizowany do milisekund, jeśli jest niezerowy
(0 oznacza brak limitu). Nie podnosić istniejącego krótszego timeoutu. Po sukcesie
przywrócić poprzednią wartość przed zwolnieniem SAVEPOINT. Timeout rankingu
(SQLSTATE 57014) wycofuje SAVEPOINT i przywraca transakcję oraz ustawienie.
Nie klasyfikować innych błędów SQL jako timeout. Zgłosić wyjątek z
`.code = BOARD_SEARCH_SEQUENCE_TIMEOUT`, mapowany na HTTP 503, bez wyników
częściowych i automatycznego retry. `logged()` zapisuje ten kod. Istniejący
`SqlAlchemyBoardSearchShareQueryLog.record` używa osobnej krótkiej sesji
i transakcji; nie zmieniać tej semantyki. Awaria samego logu nadal daje
`BOARD_SEARCH_SHARE_QUERY_LOG_UNAVAILABLE`.
Publiczny POST podlega autoryzacji, koszykowi JSON (120/min) i istniejącemu
`calculation_slot` (wspólnemu z kalkulatorem) na sesję. Limiter/slot zwraca
istniejące 429. UI zachowuje snapshot, pokazuje „Trwa inne obliczenie lub
przekroczono limit. Spróbuj ponownie za chwilę.” i oferuje ręczne ponowienie.
Nie dodawać nowej infrastruktury ani cache serwerowego. Test parytetu SQL/domena
uruchomić na małym zestawie w PostgreSQL `*_test`. Pomiar na danych operatora
oraz benchmarki pozostają poza tym zleceniem; nie raportować gwarancji wydajności.

### Kontrakt

- Zachować istniejące żądania GET. Proponowane POST: `/api/v1/admin/games/{gameId}/board-search` (`searchGameBoardSequence`) i `/api/v1/board-search-shares/search` (`searchBoardSearchShareSequence`). Body: `{patterns: [{cells: [{cellIndex, symbolCode}]}], scope, limit}`; `symbolCode` to kod lub null dla `?`, scope domyślnie `all_searchable`, limit 1–100 (API 100, UI 15).
- Walidować 1–4 wzory, maksymalnie 15 pól każdego, przynajmniej jeden znany symbol na wzór oraz istniejące reguły poprawności symboli.
- Proponowany `BoardSearchSequenceResponse`: `gameId`, `scope`, `patternCount`, `queryCellCount` (1–60), `superGameState`, `results`. Każdy wynik: `startSequenceNumber`, `endSequenceNumber`, `score` (obiekt z dotychczasowymi licznikami, tym razem do 60), `boards` (1–4 dotychczasowych wyników, w kolejności wzorów). Publiczny wariant pomija `gameId`, dodaje `searchContextId` i używa publicznych modeli dla każdego elementu `boards` — bez identyfikatorów wewnętrznych. Adapter UI może wewnętrznie używać dotychczasowej sztucznej tożsamości gry, nigdy jako klucza trwałości.
- Dostarczyć cały pion: backend, OpenAPI, wygenerowany klient, wrapper, adapter Reviewera i reguły proxy. Proponowana opcjonalna metoda `searchGameBoardSequence` w `BoardSearchDataSource` włącza nową funkcję. Bez niej workspace działa jak dotychczas. Jeden wzór w UI używa GET; większy zestaw POST.
- W obu proxy (`apps/reviewer/src/security/board-search-share-proxy.ts`, `board-search-panel-proxy.ts`) dopuścić wyłącznie wskazany POST z JSON bez query string, zachowując Origin/Sec-Fetch-Site, cookie, proxy-intent, pochodny token panelu i rekurencyjną filtrację odpowiedzi. Klasyfikacja trasy musi przesyłać body (obecne `kind: json` tego nie robi). Tylko dla tej trasy limit rzeczywiście odczytanych bajtów wynosi 32768; inne POST/PUT zachowują 4096. Czytać strumień do limitu, także bez Content-Length, w obu proxy i na wejściu API. Nie używać nieograniczonego `arrayBuffer()` na nowej trasie.
- Błędy: 413 przy przekroczeniu body, 415 przy złym Content-Type, 422 przy nieprawidłowym wzorze/liczbie wzorów (`BOARD_SEARCH_SEQUENCE_INVALID`) lub `L` (`BOARD_SEARCH_SEQUENCE_LENGTH_INVALID`); dotychczasowe 401/404/409 dla dostępu, gry i projekcji. Odpowiedź zawiera indeks błędnego wzoru. Błąd zapisu logu nadal zamyka odczyt przez 503, bez zwracania danych.
- Cache adaptera pozostaje wyłącznie w pamięci: klucz obejmuje typ żądania, uporządkowane wzory, scope i limit; wpis przechowuje także właściwy `searchContextId`. Nie cache'ować wyników ze znacznikami supergry lub nieaktualną generacją; korekta czyści cache. Zmiana gry/sesji wymienia adapter. Nowy wariant powinien zwracać context wraz z wynikiem, aby spóźnione żądanie nie podmieniało kontekstu aktywnego wyniku. Korekta używa jawnego context aktywnego wyniku; obecni konsumenci bez nowej opcji zachowują swoje zachowanie.
- Historia linku zapisuje cały ciąg. Reguły formatu, grupowania, replay i korekt opisano poniżej; stare wpisy pozostają czytelne bez backfillu.
- Obecny limit historii 4 KiB może nie pomieścić czterech pełnych wzorów. Migracja Alembic zwiększa limit żądania do 32 KiB; walidacja aplikacji pozostaje zgodna z constraintem. Ograniczenie nowego body wyszukiwania również wynosi 32 KiB.

### Historia, korekty i kompatybilność

Wpis `kind=search` pozostaje bez nowej wartości enumu. GET zapisuje jak dziś
`{cells,scope,limit}`. POST z jednym wzorem zapisuje taki sam format. POST
wielowzorowy zapisuje `{version:2,patterns:[{cells:["0:code","1:?"]},...],scope,limit}`;
komórki sortowane po indeksie, kolejność wzorów zachowana. `_REQUEST_KEYS`
dopuszcza oba formaty. Podsumowanie v2 (do 2 KiB) ma `resultCount`,
`patternCount`, `firstEndSequenceNumbers`: do 5 numerów końcowych plansz
pierwszych wyników rankingu. Legacy zachowuje `resultCount` i
`firstSequenceNumbers` bez zmiany znaczenia. `describeBoardSearchQueryEntry`
w `apps/admin/src/features/board-search/board-search-share-query-log-state.ts`
odczytuje nowy klucz dla v2 i opisuje go jako końce dopasowanych ciągów.
Test obejmuje oba formaty. Nie zapisywać pełnych wyników w podsumowaniu.

Jedna normalizacja rozróżnia legacy/single i v2. Dwa jawne adaptery tożsamości:
dla legacy `_pattern_key` nadal daje `json.dumps(cells, ensure_ascii=False)`,
a `pattern_fingerprint` nadal daje `correction_fingerprint(sorted(cells))`.
Te wyniki nie są zamienne; zachować dokładną serializację, sortowanie i hashe
istniejących korekt. Dla v2 oba adaptery korzystają z tego samego kanonicznego
obiektu `{version:2,patterns:[...komórki sortowane po indeksie...]}`; klucz
grupy jest deterministycznym JSON, fingerprint to `correction_fingerprint`
tego obiektu. Kolejność wzorów jest istotna. Grupowanie i `wholePattern`
używają klucza, a zapis/filtr korekt fingerprint. Nie wolno stosować fallbacku
`request.get('cells', [])` do v2. Scope/limit nadal nie są częścią tożsamości
wzoru. A+B i B+A oraz A+B i A+C muszą dawać różne grupy.

`searchSnapshot` korekty zachowuje pełny request z wersją. Korekta nadal
sprawdza przynależność `searchContextId` do tej samej sesji/gry i udanego
wyszukiwania. Zmienia się fingerprint wzoru, nie znaczenie pozycji korygowanej.
Parametr `sequenceNumber` to plansza edytowana. Rozdzielić kotwicę WYGRANYCH
od kontekstu KOREKTY: wygrane nadal liczymy po ostatniej planszy ciągu,
natomiast detal otwarty z dopasowanego ciągu dostaje kontekst korekty
`{startSequenceNumber: sequenceNumber}` (bez spinCount), jak obecny fallback
w `board-search-board-lines-modal.tsx:325`. `searchContextId` nadal wskazuje
pełne wspólne wyszukiwanie v2. Dla wcześniejszej planszy nie wysyłać końca
ciągu jako początku zakresu korekty. Otwarcie modalu i zapis korekty nie
zmieniają kotwicy kalkulatora. Dla plansz z tabeli wygranych zachować obecny
kontekst startu i spinCount tej tabeli.

Nie rozszerzać serwerowej reguły zakresu: `distance = (sequenceNumber -
startSequenceNumber) % L`, dopuszczone distance=0 albo distance<=spinCount.
UI korzysta z istniejącego kontekstu pojedynczej planszy zamiast dodawać
zakres wstecz do kontraktu. Kontekst zapytania potwierdza sesję i grę, nie
jest dowodem przynależności do top-N; uprawnienie linku już obejmuje korekty
tej gry. Admin bez linku używa `applySymbolCellReviewDecision` przez
`applyBoardCellCorrection`, sprawdza rewizję/crop, bez walidacji tego zakresu.
Zachować oba tory, operationId, receipt i retry utraconej odpowiedzi.

Istniejący GET listy korekt zachowuje `pattern`. Dodać opcjonalny
`searchEventId` (UUID): serwer pobiera request wydarzenia tej sesji i wylicza
fingerprint; równoczesne `pattern` i `searchEventId` dają 422. UI historii v2
korzysta z `searchEventId`, bez długiego wzoru w URL. Jedna normalizacja
identyfikuje powtórzenia niezależnie od ID konkretnego wydarzenia.

Admin: `board-search-replay-state.ts`, `board-search-share-query-log-state.ts`
i widoki logu/korekt odtwarzają komplet wzorów, pokazują wszystkie małe siatki
i oznaczają liczbę układów. Widok korekt wyświetla „Ciąg: N układów” na
podstawie `searchSnapshot.version = 2` i długości jego `patterns`, nigdy na
podstawie `startSequenceNumber`; legacy zachowuje obecny opis.
API Admina przekazuje tę pochodną informację addytywnym `patternCount`
(default 1); nie trzeba ujawniać pełnego snapshotu w liście korekt.
Replay v2 ustawia aktywny ostatni badż i uruchamia
POST; legacy nadal GET. Follow-up wygranej i modal szczegółów zachowują swoją
pozycję. Replay ma pierwszeństwo przed localStorage; po przejęciu jest
konsumowany raz i zapisuje nowy stan lokalny, bez równoległego auto-restore.

### Migracja i wdrożenie

Nowa migracja Alembic zmienia wyłącznie `ck_bss_query_request` z 4096 na 32768
w `public.board_search_share_query_events`; model ORM i walidacja JSON w
aplikacji mają ten sam limit. Obejmuje także `symbol_correction`, gdzie
`searchSnapshot` powiększa wpis. Test maksymalnych kodów (64 znaki, Unicode)
sprawdza cały wpis korekty wraz z metadanymi, nie samo body wyszukiwania.
Nie zmieniać istniejących rekordów. Downgrade najpierw sprawdza wpisy >4096:
jeżeli istnieją, odmawia obniżenia limitu bez ich usuwania lub skracania.

Nowa migracja będzie miała numer po aktualnym head Alembic. Test upgrade,
constraint i ochronnego downgrade wyłącznie w bazie testowej. Wdrożenie po
osobnych zgodach: operator zatrzymuje usługi; udostępnić mu plik migracji
z gałęzi do zastosowania na bazie przed przesunięciem main; potwierdzić
rewizję bazy; dopiero merge/push kodu i start usług przez operatora.
Nie uruchamiać nowego kodu na starej bazie, nie scalać przy brakującej migracji.
Rollback aplikacji nie oznacza automatycznego downgrade danych historii.
Jeżeli po migracji merge nie dochodzi do skutku, pozostawić usługi zatrzymane
i wykonać chroniony downgrade do poprzedniej rewizji z checkoutu zawierającego
nową migrację, po zgodzie operatora. Dopiero po sprawdzeniu poprzedniej
rewizji uruchomić stary kod. Wpisy >4096 blokują downgrade: nie usuwać ich
i nie uruchamiać Alembic ze starego main; przekazać blocker operatorowi.
Poszerzenie constraintu samo w sobie jest wstecznie zgodne, lecz nie usuwa
problemu nieznanej rewizji Alembic na main.

Odbiór A: testy rankingu, kontraktu, PostgreSQL, historii i publicznego dostępu.
Zadanie jest gotowe do zamknięcia dopiero po wymaganym audycie implementacji,
jeśli taki zostanie osobno zatwierdzony; bieżące audyty dotyczą wyłącznie planu.

## Zadanie B — Badże, trwałość i oba widoki

Zależność: ukończone zadanie A.

- Rozszerzyć wspólny `BoardSearchWorkspace` w `packages/board-search-ui`. Włączyć funkcję w Adminie i obu powierzchniach udostępniania. Panel zarządzania zachowuje dotychczasowe zachowanie.
- Oddzielić stan edytowanych wzorów od ostatniego wykonanego wyszukiwania. Odpowiedź spóźnionego żądania nie może nadpisać nowszego wyniku ani odtworzyć zestawu po „Nowe szukanie”.
- Wspólne wyniki pokazują zakres dopasowanego ciągu, łączny procent i oceny poszczególnych układów. Główny podgląd domyślnie przedstawia ostatnią planszę; zachować istniejące szczegóły, korekty i obsługę supergier.
- Zapisywać w wersjonowanym `localStorage` wzory, aktywny badż, ostatnie wykonane zapytanie i tożsamość wybranego dopasowania. Bez obrazów, sekretów i trwałego zapisywania odpowiedzi API.
- Klucz zapisu rozdziela grę Admina, sesję pojedynczego linku oraz panel i jego grę. Przełączenie gry nie miesza zestawów.
- Po ponownym otwarciu odtworzyć edytor, sprawdzić dostęp i ponowić ostatnie wyszukiwanie. Zachować wybrane dopasowanie, jeśli nadal istnieje; inaczej wybrać pierwsze i poinformować użytkownika.
- Błąd zapisu lokalnego pokazuje komunikat i pozwala kontynuować pracę w pamięci. Wygaśnięcie linku blokuje wyniki również po odtworzeniu lokalnego stanu.
- Błąd wyszukiwania zachowuje wpisane wzory i pozwala ponowić żądanie. Poprzednie wyniki pozostają wyraźnie opisane jako poprzednie.

### Stan, przywracanie i wybrane dopasowanie

Wspólny workspace przechowuje osobno `draftPatterns`, aktywny indeks,
`lastSubmittedPatterns`, wynik i jego context oraz `selectedStartSequenceNumber`.
Nowe poprawne wyszukiwanie wybiera pierwsze dopasowanie; ponowienie tego samego
zestawu po korekcie, zmiana limitu i restore zachowują wybrany start, jeśli
nadal jest w wynikach. Brak wyników czyści wybór i wygrane. Tożsamością ciągu
w obrębie gry jest start i liczba wzorów, nie indeks w karuzeli.

Badże sterują tylko edytorem. Karuzela steruje wspólnym wynikiem. Przy wyniku
pokazać jeden główny podgląd ostatniej planszy oraz numery/oceny pozostałych;
kliknięcie numeru otwiera istniejący modal szczegółów bez zmiany kotwicy wygranych.
`searchKey` wygranej obejmuje pełny ostatnio wysłany zestaw; zmiana badża nie
resetuje stawki/pinów, nowe wyszukiwanie zachowuje dotychczasowe reguły resetu.

Żądanie ma revision zestawu i scope oraz własny ID. „Nowe szukanie”, zmiana
scope i nowsze żądanie unieważniają poprzednią odpowiedź. Edycja w locie może
zachować odpowiedź wysłanego snapshotu jako poprzednią, nigdy jako wynik
zmienionego draftu. Zablokować korekty i nowe obliczenia do czasu odebrania
odpowiedzi nowego wyszukiwania; po błędzie można świadomie korzystać z jasno
oznaczonego starego snapshotu i jego context. Przełączenie badża nie wysyła żądań.

Przy włączonej funkcji sequence skoordynować search z kalkulatorem przez
proponowane opcjonalne `onBusyChange` i `suspended` w
`BoardSearchApproximateWin` (domyślnie dotychczasowe zachowanie). Busy oznacza
co najmniej jedno nadal trwające żądanie kalkulatora, także spóźnione.
„Szukaj plansz”/Enter i restore nie wysyłają żądania, gdy kalkulator jest busy;
przycisk pokazuje „Trwa obliczanie wygranej…”. Podczas search `suspended`
blokuje nowe wywołania/debounce kalkulatora. Samo anulowanie fetch nie
potwierdza zwolnienia slotu na serwerze. Obsługa 429 pozostaje potrzebna
przy wielu kartach i utracie odpowiedzi. W management nowe opcje są nieaktywne.

Proponowany lokalny rekord v1 zawiera scope, wzory (15 pozycji z rozróżnieniem
pustego null i jawnego `?`), aktywny indeks, tryb wprowadzania, ostatnie
wysłane wzory/limit i wybrany start. Nie zapisuje searchContextId, odpowiedzi,
zdjęć ani credential. Klucze: `board-search-sequence:v1:admin:<gameId>`,
`...:share:<sessionId>`, `...:panel:<panelId>:<sessionId>`.

Hydratacja jest jednokrotna po ustaleniu scope i dostępu; zapisy są wstrzymane
do jej zakończenia. Uszkodzona wersja/struktura daje pusty stan i komunikat,
bez crasha i bez automatycznego wysłania niepoprawnych danych. Zarchiwizowane
symbole blokują wysłanie wzoru do poprawienia, nie są po cichu usuwane.
W razie różnicy draft/lastSubmitted odtworzyć obie wartości; automatycznie
wyszukać tylko ostatnio wysłany zestaw i oznaczyć niezatwierdzone zmiany.
Nie wymieniać stanu działającej karty zdarzeniem storage z innej karty;
ostatni zapis wygrywa przy kolejnym otwarciu. localStorage działa per origin:
inny adres tunelu lub inna przeglądarka nie odzyskują tego zapisu.

Zapis przy każdej zmianie wzoru, aktywnego badża i wyboru; nie tylko przy
unmount. „Nowe szukanie” zapisuje od razu pusty stan i unieważnia restore.
Jeżeli zapis nie działa, komunikat informuje również, że poprzedni zestaw
może wrócić po odświeżeniu. Cofnij działa osobno dla aktywnego układu w sesji;
historia undo nie musi przetrwać restartu. Wygaśnięcie/401 usuwa widoczne
wyniki i cache; lokalny draft nie uprawnia do pobrania danych.

Odbiór B: interakcje, trwałość po nowym procesie przeglądarki, oba rodzaje
linku oraz regresja management. Sprawdzić cały zlecony przepływ; brak
fizycznego odbioru Androida raportować jako niewykonany, nie jako PASS.

## Weryfikacja i warunki wykonania

Planowane testy obejmują:

- 1, 2, 3 i 4 układy; próbę dodania piątego; częściowe wzory, `?`, niepoprawne symbole i duplikaty pól.
- Przypadek, w którym najlepszy wspólny ciąg nie mieści się w pierwszych 100 wynikach osobnych wyszukiwań.
- Remisy, sprzeczności, brakujące plansze, koniec sekwencji oraz wyjątek `777a2`.
- Przełączanie i poprawianie badży, reset pojedynczego wzoru, „Nowe szukanie”, błędy sieci i odpowiedzi przychodzące w niewłaściwej kolejności.
- Odtworzenie po odświeżeniu i ponownym uruchomieniu przeglądarki, izolację gier i linków oraz niedostępny lub uszkodzony zapis lokalny.
- Wygrane liczone od ostatniej planszy, historię starych i nowych zapytań, korekty, supergry i wygaśnięcie dostępu.
- Układ mobilny, klawiaturę i odbiór Androida; brak dostępnego urządzenia zostaje jawnym brakiem odbioru.

### Mapa wymaganie → zadanie → test

| Wymaganie | Zadanie | Planowane kryterium |
|---|---|---|
| 1–4 kolejne spiny, bez top-N | A | czysta domena i rzeczywisty PostgreSQL: najlepszy ciąg poza indywidualnym top100; wrap L→1, luka, k>L, approved_only |
| Poprawna ocena | A | SQL=domena; różne liczby znanych pól zapytań; braki dokumentu nie zmniejszają mianownika; granice zaokrągleń, 777a2, status/review_item_id przy remisie, POST1=GET |
| Dostęp w obu linkach | A/B | test żądania i oba proxy: body 4096–32768 przechodzi, >32768/stream bez Content-Length odrzucony; auth i rekursywne usuwanie ID |
| Historia i korekty | A/B | A+B ≠ B+A ≠ A+C; oba adaptery legacy bit w bit, zapisany stary fingerprint pasuje do filtra; wholePattern, searchEventId, firstEndSequenceNumbers, pełny replay; korekta pierwszej z 4 plansz z własnym startem bez spinCount (także wrap), wygrane nadal od ostatniej; błędny zakres nadal 409, legacy/Admin bez zmian; retry receipt po utracie odpowiedzi |
| Badże i reset | B | 4 wzory, fifth disabled, reset środka blokuje search, pusty koniec pomijany, same ? blokowane; badge bez zmiany wyniku/wygranej |
| Trwałość i race | B | odświeżenie/nowy proces, zły JSON, limit storage, replay>restore, spóźniona odpowiedź po reset/scope; dwie karty; wygasły link |
| Zgodność innych konsumentów | B | management bez metody sequence zachowuje zapis, draft, stawkę i istniejące interakcje |
| Timeout i współbieżność | A/B | wymuszony krótki statement_timeout tylko w *_test: rollback SAVEPOINT, przywrócone ustawienie, 503 bez wyników, log BOARD_SEARCH_SEQUENCE_TIMEOUT, następny SELECT działa; kalkulator blokuje search, search blokuje debounce; 429 innej karty ma komunikat i ręczne retry |
| Nieudane wdrożenie po migracji | A | downgrade do poprzedniej rewizji, blokada przy wpisie >4096, zero utraty danych |
| Doprecyzowania P2 z rundy 3 | A/B | PostgreSQL: niższy istniejący statement_timeout nie jest podnoszony i zostaje przywrócony; widok korekt Admina pokazuje „Ciąg: N układów” z searchSnapshot v2, a legacy zachowuje opis |

Proponowane nowe testy: `services/api/tests/test_board_search_sequence_domain.py`,
`test_board_search_sequence_api.py`, `integration/test_board_search_sequence_postgres.py`,
`packages/board-search-ui/test/board-search-sequence-state.test.mjs` oraz
`test-interactions/board-search-sequence.test.mjs`. Rozszerzyć istniejące testy
`test_board_search_share_query_log.py`, `test_board_search_share_public_api.py`,
`integration/test_board_search_share_corrections.py`, testy obu proxy Reviewera,
`board-search-replay` i `board-search-saved-selection`.

Komendy do wykonania dopiero podczas implementacji, z katalogu repo. Każdą
uruchomić przez `subprocess.run(..., timeout=120, check=True)` w `.venv\Scripts\python.exe`;
dłuższe grupy rozdzielić po plikach. Istniejące skrypty npm sprawdzone w package.json:

```powershell
# Przykład jawnego timeoutu; nowy plik jest dopiero proponowany:
.venv\Scripts\python.exe -c "import subprocess,sys; subprocess.run([sys.executable,'-m','pytest','services/api/tests/test_board_search_sequence_domain.py'],check=True,timeout=120)"
# Poniższe argv do analogicznego wrappera (na Windows npm przez cmd /c):
# cmd /c npm run test --workspace @game-predictor/board-search-ui
# cmd /c npm run test:interactions --workspace @game-predictor/board-search-ui
# cmd /c npm run test --workspace @game-predictor/admin-api-client
# cmd /c npm run test --workspace @game-predictor/reviewer
# cmd /c npm run typecheck --workspace @game-predictor/board-search-ui
# cmd /c npm run typecheck --workspace @game-predictor/admin
# cmd /c npm run typecheck --workspace @game-predictor/reviewer
# cmd /c npm run openapi:check
# cmd /c npm run docs:check
# cmd /c npm run code-map:check
```

Testy integracyjne na PostgreSQL `*_test` wymagają jawnego sprawdzenia nazwy
bazy w istniejącym fixture przed startem; nie używać bazy operatora. Ruff,
mypy, ESLint i Prettier ograniczyć do zmienionych plików/pakietów. Rozliczyć
wyniki w Outcome, nie utożsamiać statycznego audytu planu z zaliczeniem testów.
Nie dodawać benchmarku, dużych fixture'ów, restartów usług ani builda aplikacji
mobilnej. Odbiór UI obejmuje web na Androidzie, nie offline APK.

Zaktualizować wymagania, kontrakt, decyzję domenową i mapę kodu. Każde zadanie zamknąć przez `task-close`, z osobnym commitem i `Outcome`. Numery zadań i migracji przydzielić po sprawdzeniu kolizji.

Budżet bieżącego zlecenia: maksymalnie trzy próby AUDYTU PLANU przez Claude
Code, z poprawkami planu między próbami. Runda 1 została przerwana po 480 s
i liczy się do limitu; poprzednia próba połączenia z sandboxa nie rozpoczęła
pracy modelu. Po trzeciej próbie nierozwiązane uwagi albo brak końcowego
werdyktu wymagają raportu problemów i zgody przed czwartą. Audyty przyszłej
implementacji nie są wykonywane ani finansowane z tej zgody; ich zakres
wymaga ustalenia przy uruchomieniu implementacji. Otwarte P0/P1 blokują
uznanie planu za gotowy.

Implementacja wymaga wcześniejszej zgody na opisany koszt: pełny pion, testy i audyty, orientacyjnie kilka godzin pracy. Migracja bazy operatora, restarty, merge i push wymagają odrębnych zgód. Dotychczasowe cudze zmiany pozostają poza zakresem.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1091 — Ranking, API i historia | `gpt-6.1-sol` | `high` | Logika kolejności, ranking SQL, migracja i publiczny kontrakt. | Wymagany audyt implementacji: Claude Code `claude-opus-5-5`, `high`; koszt zaakceptowany 2026-10-24. |
| TASK-1092 — Badże, trwałość i odbiór | `gpt-6.1-sol` | `high` | Wspólny stan kilku widoków, trwałość i ochrona przed spóźnionymi odpowiedziami. | Wymagany audyt implementacji: Claude Code `claude-opus-5-5`, `medium`; koszt zaakceptowany 2026-10-24. |
| TASK-1098 — Układy przed szukaniem i nawigacja zdjęć | `gpt-6.1-sol` | `high` | Ograniczona zmiana wspólnego UI i testy interakcji, istniejący kontrakt odczytu. | Niewymagany dla tego niezależnego taska; eskalacja przy konieczności zmiany API. |

Claude Code CLI i model `claude-opus-5-5` potwierdzone uruchomieniem rundy 1;
CLI obsługuje `high` i `medium`. Bieżące audyty planu: `claude-opus-5-5` / `high`.
Brak dostępności przypisanej konfiguracji przy późniejszym wykonaniu zatrzymuje
zadanie; bez niejawnego zastępowania. Rekomendacje modeli nie są zgodą na start
implementacji ani delegowanie jej zadań.
