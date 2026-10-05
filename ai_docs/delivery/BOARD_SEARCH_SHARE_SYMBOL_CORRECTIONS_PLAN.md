---
title: Korekty symboli przez link wyszukiwarki i przegląd operatora
status: accepted
last_updated: 2026-10-05
---

# Korekty symboli przez link wyszukiwarki i przegląd operatora

## Stan obecny

Plan zaakceptowany 2026-10-05 przez odpowiedzi operatora na Q1 i Q2.
Implementacja TASK-0845 obejmuje natychmiastowe zastosowanie poprawek oraz
edycję plansz oczekujących i zatwierdzonych. Poniższy stan obecny opisuje
punkt wejścia przed implementacją.

- `packages/board-search-ui/src/board-search-board-lines-modal.tsx` —
  `BoardSearchBoardLinesModal` ma tryb „Popraw symbole”.
- `packages/board-search-ui/src/board-search-board-cell-correction.ts` —
  `applyBoardCellCorrection` używa `applySymbolCellReviewDecision`.
- `application/board_search_board_detail.py` —
  `BoardSearchBoardDetailService.detail` udostępnia komórki tylko aktualnej
  planszy `pending`. Pełny prefiks ścieżek Python w tym planie to
  `services/api/src/game_predictor_api/`.
- `application/image_symbol_review_mutations.py` —
  `SymbolCellReviewMutationCommand` wiąże zapis z rewizją oraz tożsamością
  cropa. `storage/image_symbol_review_repository.py` —
  `SqlAlchemySymbolCellReviewMutationRepository.apply_board_mutations`
  blokuje bieżącego właściciela sekwencji i aktualizuje audyt oraz projekcję.
  Commit wykonuje dependency w `main.py`.
- `api/board_search_share_public.py` oraz
  `apps/reviewer/src/security/board-search-share-proxy.ts` realizują D-471:
  publiczny link jest tylko do odczytu. Szczegóły nie zawierają komórek.
- `apps/reviewer/src/features/board-search-share/board-search-share-data-source.ts`
  — `createBoardSearchShareDataSource` nie udostępnia mutacji. Cache szczegółów
  jest powiązany z fingerprintem ostatniego zakresu.
- `apps/admin/src/features/board-search/board-search-share-query-log.tsx` —
  `BoardSearchShareQueryLog` listuje wzory grupowane przez API. Wykres pochodzi
  z ostatniego zakresu danej grupy. D-487 zapisuje stawkę odbiorcy.
- `application/board_search_share_queries.py` —
  `BoardSearchShareQueryLogService` łączy zapytania na podstawie kolejności
  czasowej. To nie wystarcza do przypisywania korekt w kilku kartach.
- `storage/board_search_share_query_repository.py` usuwa wyszukiwanie wraz
  z wpisami następczymi. Historia korekt musi przeżyć takie usunięcie.
- Head migracji w analizowanym checkoutcie: `0140_grid_engine_profiles`.
  Nową migrację należy numerować po ponownym sprawdzeniu heada.

## Cel i wymagania operatora

Odbiorca linku otwiera planszę, poprawia symbole i zapisuje dane online.
Operator szybko odnajduje każdą zmodyfikowaną planszę i otwiera jej edytor
jednym kliknięciem, aby sprawdzić poprawność zmiany.

1. Przycisk „Popraw symbole” jest dostępny również przez link online.
2. Zapis jest trwały i korzysta z jednej logiki decyzji symboli.
3. W dzienniku wyszukiwania, obok numeru planszy i stawki, widać korekty.
4. Lista obejmuje także plansze otwarte dalej w zakresie do 100 000 spinów.
   Nie ogranicza się do pierwszych pięciu wyników zapisanych w skrócie zapytania.
5. Kliknięcie „Sprawdź poprawki” otwiera modal konkretnej planszy bez
   odtwarzania wyszukiwania ani liczenia całego zakresu.

## Zaakceptowane decyzje operatora

### Q1 — moment zastosowania zmiany

Operator potwierdził: poprawka od razu zmienia bieżące dane wyszukiwarki i wypłat;
jednocześnie otrzymuje osobny stan „Do przeglądu operatora”. To odpowiada
opisowi zapisu online tak jak w lokalnym edytorze. Przegląd operatora nie
jest nowym stanem weryfikacji komórki i nie zastępuje istniejącego canonical flow.

Nie wprowadza się osobnego modelu propozycji symboli.

### Q2 — plansze już zatwierdzone

Operator potwierdził edycję również zatwierdzonych plansz. D-492 zmienia
D-473 dla lokalnego i zdalnego modala. Bieżące operacyjne plansze `pending`,
`accepted` i `corrected` z kompletem aktualnych komórek są edytowalne.
Istniejący writer komórek ponownie agreguje rodzica i aktualizuje canonical
po zmianie symbolu; zgłoszenie nieczytelności lub złej siatki ponownie otwiera
planszę istniejącym flow. Archiwum pozostaje bez edycji.

## Rekomendowany przepływ UI

- Odbiorca: modal → „Popraw symbole” → pole → symbol → potwierdzenie zapisu.
  Działa z karuzeli wyników i z dowolnego wiersza przybliżonej wygranej.
- Wpis wyszukiwania: numer planszy startowej, istniejąca stawka i oznaczenie
  „Poprawiono X plansz · Y do przeglądu”. Korekty startowej planszy i dalszych
  plansz są rozróżniane; liczniki uwzględniają wszystkie powtórzenia wzoru.
- Obok dziennika: lista „Poprawione plansze” w wybranym linku; domyślny filtr
  „Do przeglądu”, pozostałe „Wszystkie” i „Przejrzane”. Lista ma numer planszy,
  czas ostatniej korekty, etykietę linku, liczbę zmienionych pól i stawkę
  zapisaną przy korekcie albo „stawka nieznana”.
- Jeden wiersz oznacza jedną planszę, nawet po wielu korektach pól. Lista
  obejmuje także korekty bez istniejącego wpisu wyszukiwania.
- „Sprawdź poprawki” otwiera `BoardSearchBoardLinesModal` z `row=null`,
  bieżącymi danymi planszy i wyróżnieniem pól zmienionych od ostatniego
  przeglądu. Obok pola widać historię „przed → po”. Operator może poprawić
  symbol przez lokalny zapis.
- Jawny przycisk „Oznacz jako przejrzane” domyka przegląd. Zamknięcie okna
  nie oznacza akceptacji. Zapis operatora i domknięcie przeglądu to osobne
  działania; awaria drugiego nie ukrywa pozycji wymagającej przeglądu.
- Zmiana odbiorcy podczas przeglądu daje konflikt. Nowa korekta po
  zatwierdzeniu wraca do „Do przeglądu”.

## Kontrakt, odpowiedzialności i trwałość

Poniższe nowe nazwy są propozycjami, nie istniejącymi elementami kodu.

1. Rozszerzyć istniejącą powierzchnię `board-search-shares` o zapis jednej
   komórki planszy przez numer sekwencji i indeks komórki. Nie wystawiać
   tras Admina ani ogólnych tras weryfikacji. Gra i aktor
   `board-search-share:<session UUID>` pochodzą z uwierzytelnionej sesji.
2. Publiczny kontrakt komórki zawiera indeks, stan i zewnętrzny klucz rewizji
   wiążący aktualnego właściciela, geometrię i crop. Nie ujawnia identyfikatorów
   review/importu ani ścieżek. Klucz ma być nieodwracalnym fingerprintem;
   nie wolno stosować Base64 z wewnętrznymi identyfikatorami.
3. Request proponowanej operacji `correctBoardSearchShareCell`:
   numer planszy i indeks w ścieżce; w JSON `operationId`,
   `expectedCellVersion`, wybór symbolu albo dozwolonego stanu oraz
   kontekst wyszukiwania i aktualnej stawki. Backend mapuje pozycję na
   bieżącą komórkę pod blokadą i deleguje do istniejącej domenowej mutacji.
   Dozwolone akcje należy utrzymać zgodne z lokalnym edytorem.
4. W `BoardSearchDataSource` dodać opcjonalny port korekty przez pozycję
   planszy. Zachować istniejący port `applySymbolCellReviewDecision` Admina.
   Nie tworzyć fikcyjnych UUID review ani drugiego edytora Reviewera.
5. Udane wyszukiwanie powinno zwracać identyfikator własnego kontekstu.
   Klient przekazuje go jawnie z informacją o wybranej planszy startowej
   i zakresie. Backend sprawdza przynależność kontekstu do tej samej sesji
   oraz zakresu gry. Kilka kart nie może przypisywać korekt przez
   „najbliższe wcześniejsze wyszukiwanie”. Bez kontekstu korekta pozostaje
   widoczna w osobnej liście.
6. Nowy dziennik korekt ma być metadanymi udostępnienia, nie drugim źródłem
   etykiet. Źródłem symboli pozostają bieżące komórki i ich istniejący audyt.
   Wpis przechowuje sesję, grę, numer sekwencji, tożsamość właściciela i cropa,
   indeks, czas, identyfikator operacji, stany przed/po oraz snapshot kontekstu.
   Snapshot zawiera stawkę w momencie zapisu; późniejsza zmiana stawki wykresu
   nie zmienia historii korekty. Obrazów nie zapisuje się w tabeli.
7. Mutacja symbolu, istniejący event komórki, aktualizacja projekcji oraz
   zapis metadanych korekty muszą należeć do tej samej transakcji i sesji DB.
   Nie używać osobnej transakcji `SqlAlchemyBoardSearchShareQueryLog` do
   audytu zapisu. Błąd audytu wycofuje także zmianę symbolu.
8. Unikalność `(session_id, operation_id)` zapewnia dokładny retry.
   Identyczny request zwraca zapisany wynik, a inne body z tym samym UUID
   daje konflikt. Po utracie odpowiedzi klient zachowuje tę samą operację,
   także po odświeżeniu karty. Niewysłane poprawki nie są automatycznie
   wykonywane po ponownym odblokowaniu inną sesją.
9. Osobny odczyt przeglądu grupuje zdarzenia korekt planszy. Liczba zapisanych
   korekt jest monotoniczną rewizją; event przeglądu zapisuje granicę ostatniej
   przejrzanej korekty. „Przejrzane” wymaga oczekiwanej
   rewizji. Powrót do poprzedniego symbolu nadal zostawia historię zmian;
   wybór tego samego symbolu bez zmiany semantycznej nie zwiększa licznika
   poprawionych pól ani nie tworzy nowej pracy operatora.
   Zatwierdzenie oczekującego pola jest zmianą stanu. Rewizja zwiększa się
   pod blokadą linku, niezależnie od kolejności zegara; przegląd sprawdza
   również fingerprint wszystkich aktualnych komórek.
10. Usunięcie wyszukiwania z dziennika nie usuwa korekt. Identyfikator wpisu
    pozostaje historyczną referencją bez FK; snapshot i kolejka pozostają. Zatrzymanie lub
    wygaśnięcie linku również nie usuwa historii ani pracy operatora.
11. Wykorzystać istniejącą tabelę metadanych
    `public.board_search_share_query_events`: migracja rozszerza CHECK rodzaju
    o `symbol_correction` i `correction_review` oraz dodaje częściowe indeksy
    idempotencji i odczytu per plansza/wzór. Nie zmienia się ownership magazynu
    ani FK gry/sesji. Usuwanie zapytań wyklucza te dwa trwałe rodzaje zdarzeń.
    Nie tworzyć drugiej tabeli symboli ani zmieniać zamrożonych manifestów.
    Downgrade odmawia przy istniejącej historii korekt.

## Granice i błędy

- Autoryzacja, aktywność sesji, scope gry i rate limit obowiązują przed
  odczytem/zapisem, także przy retry. Ponownie sprawdzić uprawnienia pod
  blokadą sesji przed commitem, aby revoke/rotacja nie dopuściły starego tokenu.
- Proxy dopuszcza tylko dokładną nową metodę i ścieżkę, JSON do 4 KiB oraz
  zgodny `Origin` i `Sec-Fetch-Site: same-origin` dla mutacji. Cookie pozostaje
  `HttpOnly`, `Secure`, `SameSite=Strict`. Odrzucić nadmiarowe pola JSON.
- Konflikt właściciela, rewizji lub pikseli: `409`, bez zapisu; odczytać świeżą
  planszę i wymagać ponownego wyboru. Nie powtarzać automatycznie decyzji na
  innych pikselach. Archiwum, brak komórek i nieaktualny dokument pozostają
  bez edycji, z czytelnym powodem.
- Błąd bazy/audytu: `503`, żadnego częściowego zastosowania. Retry po utracie
  odpowiedzi używa identyfikatora operacji. Brak dostępu: `401`; obcy kontekst
  albo niedostępna plansza nie ujawniają danych innej gry.
- Lista ma strony po 25, maksymalnie 50, kursor po czasie i ID. Szczegóły,
  historia pól i modal są pobierane leniwie. Otwarcie listy nie liczy wypłat
  ani nie pobiera 100 000 plansz. Zapytania o liczniki działają w bazie.
- Po korekcie unieważnić cache wyszukiwania i szczegółów odbiorcy; modal
  odświeża linie, a zamknięcie ponawia wyszukiwanie i potrzebną kalkulację.
  Lista operatora ma loading/empty/error i ręczne odświeżenie.

## TASK-0845 — pełny pion korekt symboli linku i przeglądu

### Goal

Odbiorca trwale poprawia symbole w dozwolonych planszach, a operator
odnajduje i przegląda każdą zmianę z jednego dziennika linku.

### Dependencies / entry conditions

Odpowiedzi Q1/Q2 zaakceptowane; spójny plan i task, odczyt D-471/D-473/D-492,
ponowne sprawdzenie aktualnego kodu i heada Alembic. Implementacja stanowi
jeden task i jeden commit; nie dzielić udostępnienia zapisu od audytu.

### Scope

Publiczny zapis, atomowy audyt, lokalna kolejka i domknięcie przeglądu,
wspólny modal, wygenerowany klient, regresje oraz dokumentacja właścicielska.

### Acceptance criteria

- [x] Odbiorca poprawia planszę startową i inną planszę w dozwolonym zakresie.
- [x] Zmiana i ślad audytu są atomowe, odporne na restart i utratę odpowiedzi.
- [x] Dziennik pokazuje korekty obok wyszukiwania i stawki, także po grupowaniu.
- [x] Osobna lista obejmuje wszystkie zmienione plansze linku i działa bez wykresu.
- [x] Jeden klik otwiera edytor właściwej planszy z historią zmienionych pól.
- [x] Operator potwierdza przegląd konkretnej rewizji; nowsza zmiana zostaje otwarta.
- [x] Usunięcie wyszukiwania i revoke nie kasują korekt.
- [x] Izolacja gry, cookie, CSRF, allowlista, limit i redakcja przechodzą testy.
- [x] Q1/Q2, API, model danych, threat model, Outcome i CURRENT_STATE są spójne.

### Expected files

Istniejące wskazane wyżej moduły oraz `api/board_search_shares.py`,
`schemas/board_search_shares.py`, `storage/models.py`, `main.py`,
`packages/admin-api-client/src/index.ts`, OpenAPI i wygenerowane pliki klienta.
UI dziennika może wymagać także `apps/admin/src/app/globals.css`.

Proponowane nowe moduły: `application/board_search_share_corrections.py`,
`storage/board_search_share_correction_repository.py`, odpowiednia migracja,
`apps/admin/src/features/board-search/board-search-share-corrections.tsx`.
Nie kopiować domenowej logiki mutacji komórki.

### Test cases i mapa wymagań

| Wymaganie | Test / kryterium |
|---|---|
| Zapis symbolu przez link | Nowy test HTTP rzeczywistej mutacji; właściwa gra, pozycja i aktor sesji. |
| Plansza poza startem | Start N, poprawka N+99 999 w zakresie 100 000; widoczna na osobnej liście. |
| Trwałość | Nowy proces/sesja DB odczytuje korektę; retry po commit bez odpowiedzi nie dopisuje eventu. |
| Atomowość | Wymuszona awaria zapisu audytu wycofuje symbol, projekcję i rewizję. |
| Dziennik/stawka | Startowa i dalsza plansza, wiele korekt, powtórzenia wzoru; stawka zachowana w czasie korekty. |
| Kilka kart | A/B wyszukują różne wzory; korekta A jest przypisana do A mimo późniejszego wyszukiwania B. |
| Przegląd | Klik otwiera modal; lokalna korekta działa; nowa korekta podczas domykania powoduje konflikt. |
| Historia | Usunięcie zapytania/revoke zachowuje kolejkę; ponowna zmiana otwiera przejrzaną planszę. |
| Regresja modala | Obecny Admin bez nowego portu zachowuje lokalną korektę i odświeżanie. |
| Bezpieczeństwo | Obca gra/sesja/kontekst, brak Origin/Fetch Metadata, stary token, nadmiar JSON, obce trasy. |
| Skala | Analiza indeksów i ograniczony odczyt istniejących danych; bez benchmarku ani fixture 100 000 rekordów. |

### Verification

Polecenia wynikają z package.json i istniejących testów. Każde wykonanie
z własnym timeoutem do 120 s; build ma limit 120 s, przed dłuższym wymagany
komunikat zgodny z AGENTS.md. Najpierw testy skoncentrowane, następnie lint,
format i typecheck, potem szersze testy odpowiednich workspace oraz buildy.

```powershell
# Repo root; wszystkie poniższe to kontrole planowane.
.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_share_public_api.py services/api/tests/test_board_search_share_query_log.py
.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_board_search_share_repository.py
# Dodać test integracyjny zapisu korekt na odrębnej bazie testowej.
npm run test --workspace @game-predictor/board-search-ui
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run test --workspace @game-predictor/reviewer
npm run test:geometry --workspace @game-predictor/admin
npm run test --workspace @game-predictor/admin-api-client
.venv\Scripts\python.exe scripts/export_admin_openapi.py --check
npm run check:generated --workspace @game-predictor/admin-api-client
npm run admin:build
npm run reviewer:build
```

Nowe testy muszą wejść do standardowych discovery suites. Lint i typecheck
ograniczyć najpierw do zmienionych plików/workspace. Żadnego z tych testów
nie uruchomiono podczas analizy. Odbiór UI wymaga desktopa oraz Androida;
publiczny tunel i zapis na danych operatora dopiero na osobne zlecenie.

## Ryzyka i zakres wyłączony

Q1/Q2 rozstrzygnięte 2026-10-05. Wariant natychmiastowy oznacza,
że wyszukiwania korzystają z korekty przed przeglądem operatora. Stan tego
przeglądu nie może sugerować, że dane nadal są tylko propozycją.

Nie zmieniać polityki kwalifikacji do treningu ani biblioteki wzorców.
W wariancie natychmiastowym stosować istniejące
reguły decyzji człowieka i jawnie opisać ten skutek w wymaganiach.

Poza zakresem: zmiana geometrii, dane archiwalne, zwiększenie limitu 100 000,
nowe konto/logowanie, chmura, retencja i usuwanie korekt, automatyczny trening,
migracja na bazie użytkownika, restart usług, push, merge i wdrożenie.

## Przypisanie modeli do zadań

Dostępność potwierdzona w metadanych bieżącego środowiska 2026-10-05.
Tabela nie upoważnia do uruchomienia agentów ani zmiany modelu rozmowy.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0845 — pełny pion korekt symboli linku i przeglądu | gpt-6.1-sol | high | Zapis przez publiczną powierzchnię, transakcja audytu, konkurencja i współdzielone UI wymagają kontroli całego przepływu. Q1/Q2 potwierdzone; writer istniejących komórek obsługuje ponowną agregację zatwierdzonej planszy. | Zalecany niezależny review bezpieczeństwa i atomowości: gpt-6-astra, high; uruchomienie wymaga wyraźnego zlecenia delegowania. |
