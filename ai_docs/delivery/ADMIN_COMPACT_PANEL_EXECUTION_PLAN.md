---
title: Minimalistyczny Panel Administracyjny — plan wykonania
status: accepted
last_updated: 2026-10-08
---

# Minimalistyczny Panel Administracyjny — D-536

## Zlecenie i kontynuacja

Operator zaakceptował cały zakres TASK-0940–0943, osobny worktree oraz zapis
planu i tasków w repozytorium. Zgoda obejmuje wykonanie całego planu w kolejności,
testy izolowane, osobne commity i ręczne audyty Claude przed każdym commitem
taska. Operator otrzymał oszacowanie 3–6 godzin pracy, poza oczekiwaniem na audyty;
nie było wiarygodnego oszacowania liczby tokenów ani procentu pakietu i zaakceptował
ten koszt. Nowy wykonawca nie pyta ponownie o zgodę na ten sam zakres. Istotny
wzrost kosztu wymaga ostrzeżenia zgodnie z AGENTS.md.

Stan startowy: `v1.1-vision-lab-hybrid-geometry`, commit
`3bc6c64bcf8a5f07baf48df4800949097ffed19a` (`v1.7.271`). Worktree:
`C:\Users\tuszy\.codex\worktrees\admin-compact-panel\game_predicotr`, gałąź
`codex/admin-compact-panel`. Nie przenosimy niezacommitowanych zmian operatora
z głównego checkoutu. Plan i aktywny task są wystarczającym briefem dla Claude
Code po utracie historii rozmowy. Aktualny punkt wznowienia jest w CURRENT_STATE.

Nie ma zgody na push, merge, wdrożenie, zmiany danych operatora ani uruchamianie,
zatrzymywanie lub restart API/Admin. Implementacja usuwania nie upoważnia do
usunięcia danych. Migrację na bazie operatora poprzedzają backup, preview i
osobne potwierdzenie. Weryfikacja korzysta wyłącznie z jednorazowej bazy testowej.

## Potwierdzony stan obecny

- `packages/board-search-ui/src/management/management-workspace.tsx` zawiera
  wspólną hierarchię, formularze, archiwizację i edycję przypisań. Cienki wrapper
  `apps/admin/src/features/management/management-workspace.tsx` wstrzykuje klienta
  oraz lokalny panel linków; Reviewer montuje ją przez `management-gate.tsx`.
- `management-cards.tsx`: `ManagementMiniChart` i rozbudowane karty stawek;
  `management-game-workspace.tsx` zarządza szkicem, odzyskiwaniem operacji i
  odświeżaniem najwyżej dwóch wyników. `management-result-view.tsx` pobiera cały
  zamrożony wynik i dzieli tabelę po stronie klienta na strony po 50 wierszy.
- `management-slot-state.ts`: `managementSavedSelection` odtwarza zapisany start.
  `BoardSearchWorkspace` ma już opcjonalne porty fixed stake, saved selection,
  pins i Save. `ApproximateWinBalanceChart` ma wariant `compact`, osie i wspólne
  helpery `approximateWinPointAtSpin`, `approximateWinStakeToPoint` oraz
  `approximateWinMachineCashAtPoint` w `board-search-approximate-win-state.ts`.
- `ManagementMachineCommand` dziś zawiera name/archived; gry zapisuje oddzielny
  endpoint assignments. `ManagementPinnedPoint` ma spin/balance/available, bez
  wkładu i stanu maszyny. Summary ma już `startSymbolCodes` i ≤256 chart points.
- `management_repository.py`: begin_operation zwraca receipt przed sprawdzeniem
  rewizji; punkt/maszyna są blokowane. Result versions deduplikują się po
  game/content digest i są blokowane advisory lock w `_version`.
- Journal ma point_id NOT NULL i FK RESTRICT. Sloty i journal dowolnej maszyny
  mogą współdzielić result version. Trigger immutable obejmuje operacje,
  journal, search contexts, result versions i niezależny session audit.
- Manifest to `management-control-plane-v2`; głowa Alembica i strażnik startu
  to `0151_super_game_roles`. Proxy Reviewera przenosi ciała GET/POST/PUT,
  nie implementuje DELETE. Walidacja gameIds ma istniejący limit 200.

## Docelowy przepływ i reguły produktu

Widoki: **Punkty → maszyny punktu → gry/stawki maszyny → wyszukiwanie/układ**.
Home „Punkty” jest stale dostępny. W punkcie pokazujemy „Cofnij do punktów” i
„Dodaj maszynę” u góry. Nie renderujemy maszyn wszystkich punktów pod listą.

Punkty i maszyny mają kafelki maksymalnie 320px, od początku zajmujące jedną
z czterech kolumn na dużym ekranie. Siatka: szerokość kontenera ≥1000px: 4
kolumny, ≥750px: 3, ≥500px: 2, poniżej: 1; jeden element nie rozciąga się do
pełnej szerokości. Minimalistyczna nazwa i konieczna informacja stanu. Cała
powierzchnia kafelka jest przyciskiem wyboru. Ołówek i kosz są rodzeństwem tego
przycisku, nigdy zagnieżdżonym button. Cele dotykowe ≥44px. Wybrana maszyna i
stawka mają wyraźny stan zaznaczenia także dla klawiatury.

Punkt i maszyna powstają/edytują się w modalu. Maszyna zapisuje nazwę i przypisane
gry atomowo. UI używa „Edytuj” i „Usuń”, bez archiwizowania i ukrywania. Historyczne
archived pozostają kompatybilne w API i są dostępne w zwiniętej sekcji do usunięcia.
Nie dodajemy przywracania. Gry, które przestały być active, pozostają przypisane
do jawnego odpięcia; nie można przypisać nowej nieaktywnej gry.

Usunięcie punktu usuwa jego maszyny, przypisania, sloty, konteksty i journal;
maszyna usuwa swój zakres; odpięcie gry usuwa tylko zakres maszyna/gra. Znosi to
retencję historii tego zakresu, również śladu korekt w management journal.
Rzeczywiste globalne korekty symboli, katalog gier, plansze, reguły, obrazy oraz
pozostałe dzienniki aplikacji pozostają. Usuwać może lokalny administrator oraz
odbiorca ważnego linku panelu: operator świadomie zaakceptował ryzyko tej
możliwości. Jedynym śladem delete jest minimalny receipt operacji; nie tworzymy
osobnej historii kasowania ani osieroconego journalu.

Sześć stawek: 20/10/6/4/2/1,20 PLN. Karta pokazuje stawkę i czy zapisano układ;
miniatury symboli 20–24px pochodzą z istniejącego katalogu raz na grę, z kodem/
„?” jako fallback. Kliknięcie stawki otwiera wyszukiwanie: dla istniejącego
zapisu wstrzykujemy start, query, zakres i piny, bez automatycznego wyboru
pierwszego trafienia. Całe kafelki wyników w wariancie kompaktowym są klikalne.

Nowy układ/reset zmienia tylko szkic. Stary zapis znika dopiero po jawnej
operacji zastąpienia albo usunięcia bieżącego zapisu. Korekty symboli zachowują
natychmiastowy, globalny zapis; reset szkicu nie cofa tych korekt.

| Stan | Akcja | Zapis i potwierdzenie |
|---|---|---|
| Niekompletny szkic | Save disabled | brak żądania |
| Pusty slot, gotowy szkic | Zapisz układ | istniejący PUT + CAS |
| Zapis, czysty szkic | Nowy układ / Usuń zapisany układ | pierwszy tylko lokalnie; Clear po potwierdzeniu |
| Zapis, brudny szkic tego startu | Zapisz zmiany | PUT + CAS |
| Nowy start gotowy do zastąpienia | Zastąp układ | potwierdzenie, PUT + CAS |

Szybki wynik ma wiersze **Spin | Wkład | Wygrana netto | Na maszynie**, w kredytach,
z obecnych funkcji podpisujących wykres. Wkład jest wymaganym kapitałem do dojścia
do punktu według istniejącej semantyki wykresu, nie sumą stawek. Spin zero ma
wartości zero. Niedostępny pin nie otrzymuje wymyślonych wartości zero.
0–6 pinów, także spin zero i przegrane. Wykres dopiero po rozwinięciu „Wybierz
punkty na wykresie”: osie spin/PLN, zero i jednoznaczne etykiety. Bez wykresu
na kafelkach i zwykłym podglądzie. Pełna tabela i dziennik są zwinięte.

## Kontrakt bezpiecznych mutacji — TASK-0940

Rozszerzamy istniejące API, nie tworzymy równoległego modelu. Jeden pion obejmuje
domenę/backend, OpenAPI, wygenerowany klient, wrappery, lokalny/publiczny adapter,
proxy i request tests. Panel nie ma własnego kalkulatora.

`ManagementMachineCommand`: opcjonalne gameIds i previewToken; brak gameIds
pozostawia przypisania. Pusta lista jest jawnym odpięciem i wymaga preview,
jeżeli usuwa istniejące przypisania, również legacy `attached=false`.
Utworzenie nowej maszyny bez gier oraz zapis pustej już maszyny nie kasują
żadnego zakresu i nie wymagają preview.
Endpoint assignments zostaje, korzysta z tego samego mechanizmu, z jedną pozycją
journal na komendę, nie dwiema przy atomowej edycji. archived zostaje w kontrakcie.

Nowe suffixy obu istniejących prefiksów lokalnego/publicznego:
- POST points/{pointId}/delete-preview i POST points/{pointId}/delete;
- POST points/{pointId}/machines/{machineId}/delete-preview i /delete;
- POST machines/{machineId}/update-preview dla końcowego żądanego przypisania.

Potwierdzenie w JSON: operationId, expectedRevision, previewToken, confirmed=true.
POST pozwala zachować body w proxy. Token nigdy w URL, logach, journalu ani
receipcie. Preview wiąże aktora, cel i kanoniczne żądane body. Aktor publiczny
zawiera UUID sesji, nie tylko nazwę linku. Losowy token 256bit, w DB tylko SHA256,
TTL 10 minut. Nowa tabela management_mutation_previews jest mutowalna/shared
w manifeście v3. Nowy preview usuwa najwyżej 100 najstarszych wygasłych preview
tego samego aktora, bez crona i bez GC domenowego.

Fingerprint obejmuje strukturę: ID i rewizje maszyn/przypisań/slotów oraz
count + max(created_at) journalu i kontekstów zakresu. Nie materializujemy ID
całej historii. Agregaty nadal mają koszt skanowania indeksu. Preview zawiera
liczby usuwanych obiektów. Zmiana slotu przez refresh także unieważnia token.
Brak preview przy odpięciu daje 409 MANAGEMENT_PREVIEW_REQUIRED; niezgodny,
wygasły lub zmieniony zakres zwraca jawny konflikt preview, bez zapisu i bez
porzucania szkicu. Brak encji: 404; zła rewizja/UUID operacji: dotychczasowe 409.

Kolejność blokad: publiczna sesja → UUID operacji → preview → punkt → maszyny
posortowane po UUID → gry posortowane po UUID → advisory locks digestów wyników
posortowane. Wszyscy writerzy muszą utrzymywać tę kolejność i blokady przodków.
W tej samej transakcji pobieramy referencje kandydatów zapytaniami set-based,
następnie kasujemy: journal zakresu → sloty → search contexts → result versions
bez żadnej pozostałej referencji slotu/journalu w całym systemie → assignments
→ machines → point. Lock digestu identyczny z `_version` chroni dedup race.
Nie kasujemy management_session_audit ani danych należących do gry.

Kontrolowana funkcja PostgreSQL SECURITY DEFINER należy do właściciela schematu,
używa kwalifikowanych nazw, stałego bezpiecznego search_path i statycznego SQL.
REVOKE EXECUTE FROM PUBLIC; jawny grant app przez provisioning ról. Trigger
immutable pozostaje SECURITY INVOKER: bypass wymaga jednocześnie efektywnego
current_user będącego właścicielem tabeli oraz transakcyjnego trybu maintenance.
Sam GUC nie wystarcza: aplikacja może ustawić dowolny custom GUC. Właściciel bez
flagi także jest blokowany. Tryby purge/migration-backfill mają whitelist
TG_TABLE_NAME/TG_OP, nie zmieniają operation_id/actor/checksum/created_at.
Zakazane DISABLE TRIGGER, TRUNCATE i szerokie cascade. Session audit pozostaje
niezmienny. Provisioning --check weryfikuje właściciela, search_path/security,
granty PUBLIC/app i brak członkostwa app w owner; manifest v3 zawiera preview.

Receipty dostają pola action/point/machine/game bez FK do kasowanych obiektów.
Stare receipty zakresu tracą response payload i otrzymują znacznik target_deleted.
begin_operation najpierw sprawdza aktora/checksum, potem daje jawne
409 MANAGEMENT_TARGET_DELETED dla dokładnego retry; nigdy nie odtwarza encji.
**Receipty pure delete zawsze zostają**, również po późniejszym usunięciu rodzica;
retry udanego delete zwraca ten sam sukces. Receipt destrukcyjnego update powstaje
po redakcji poprzednich. Deletion receipt ma tylko scope/counts, bez nazw i historii.
flush i finalne revalidate sesji następują przed commitem i odpowiedzią.

Migracja backfill ustala scope dawnych receiptów deterministycznie z journalu,
kontekstu lub response. Nie każdy receipt ma journal (np. niezmieniona korekta).
Tylko niewyznaczalny zakres otrzymuje legacy_redacted i exact retry409
MANAGEMENT_LEGACY_RECEIPT_REDACTED. Przed zastosowaniem migracji read-only preview
liczy wszystkie kategorie, także tę wyjątkową. Backfill używa trybu migration
tego samego triggera. To zmiana danych wymagająca osobnej zgody operatora.

`ManagementPinnedPoint` zyskuje nullable requiredStakeCredits/machineCashCredits.
Save/Refresh oblicza je z zamrożonego wyniku, według tych samych wspólnych
helperów co wykres (golden fixtures Python/TS). Stare piny uzupełnia read-only
fallback wyłącznie przy absent/null polach, maksymalnie 6 pinów × 6 slotów
wybranej maszyny/gry; payloady czytane sekwencyjnie po stronie serwera. Bez
bieżących reguł, rekalkulacji, zapisu GET ani edycji immutable payloadu.
Zwykły frontend bierze szybkie wiersze z pinów, nie pobiera pełnego wyniku.

## Nawigacja i ochrona szkicu — TASK-0941

URL parametry mpPoint/mpMachine/mpGame/mpStake zachowują pozostałe parametry.
mpStake odtwarza tylko zaznaczenie, nigdy nie otwiera edytora ani szkicu.
Niepoprawny UUID lub nieistniejący obiekt jest usuwany replaceState; powrót do
najbliższego poprawnego rodzica bez sztucznego komunikatu błędu. Pending command
ma pierwszeństwo dla odzyskiwania swojego scope, bez automatycznego ponawiania.

Ostatnia gra: localStorage per namespace/UUID maszyny, osobno local owner i
konkretna publiczna sesja. Scroll każdego poziomu per tab. Home, back, popstate,
zmiana gry i zamknięcie modala chronią dirty draft. Snapshot: mount, powrót na
listę, focus, sukces mutacji, notfound/conflict. Własny autorefresh slotów pauzuje
podczas potwierdzania delete. Zmiana z innego okna unieważnia preview zamiast
kasować nowy stan. Błąd zapisania modala pozostawia wpisaną nazwę/gry.
Panel linków zostaje wyłącznie w lokalnym nagłówku jako zwijana sekcja.

## Reużycie i stawki — TASK-0942

Wspólne BoardSearchWorkspace, ApproximateWinBalanceChart i approximateWin*
dostają opcjonalny wariant kompaktowy. Nie kopiujemy wyszukiwarki, wykresu,
modali ani wyliczeń. Dotychczasowe propsy zachowują default. Regresje zwykłego
Admin search i share jednej gry muszą pozostać zielone. W panelu pełny wynik
ładuje dopiero otwarty edytor, tabela lub historia; zwykły podgląd używa pinów.
Obsolete responses, CAS conflict, exact UUID recovery i utrata sesji nie
porzucają szkicu ani nie przenoszą go do innej maszyny/aktora. Historyczne
wartości pozostają zamrożone. Nie zmieniamy deterministycznego sequence_number.

## Niezależny tor i integracja z Mumiami

TASK-0933–0936 **nie blokują** startu panelu. Rezerwujemy TASK-0940–0943 i D-536
widocznym wpisem w repo. Panel proponuje pełny unikalny revision ID
`0152_management_compact_panel`, parent `0151_super_game_roles`. Numer sam
w sobie nie wyznacza tożsamości Alembica; dwa różne dzieci wspólnego rodzica
tworzą dwie głowy. Przed materializacją/integracją sprawdzamy aktualny tip,
numery TASK/D i wersje commitów.

0942 jest ostatnim z trzech tasków implementacyjnych. Bezpośrednio przed nim
sprawdzamy main: jeśli TASK-0935/0936 weszły, aktualizujemy panel na ich stan
przed edycją wspólnych komponentów. Jeśli nie, wykonujemy panel; integrator
drugiej gałęzi Mumii dostosuje się do wspólnych zmian. Nie rebase'ujemy cudzej
gałęzi. Właściciel drugiego merge rozwiązuje konflikt DDL i dodaje migrację
scalającą jak 0147, sprawdza jedną głowę, strażnik schematu, provisioning oraz
regeneruje OpenAPI/klienta i testuje oba przepływy. Nie zmieniamy już
zastosowanych revision IDs. Nie ma zgody na automatyczny merge/push.

Obecne helpery zakładają stały spinCost; jeżeli zmienny koszt Mumii pojawi się
przed/po panelu, wspólna infrastruktura wyliczeń i metadane pinów zostają
dostosowane wraz z golden fixtures (normalny koszt + darmowe spiny). Bez
oddzielnego kalkulatora panelu i bez reinterpretowania historycznych wersji.
Worktree izoluje pliki, nie bazę ani porty.

## Zadania i kryteria odbioru

| Wymaganie | Task | Kryterium / test |
|---|---|---|
| Atomowa nazwa + gry | 0940, 0941 | jedno żądanie/transakcja/journal; modal zachowuje błąd |
| Delete punkt/maszyna/detach online | 0940, 0941 | preview, counts, CAS, retry, minimalny receipt |
| Integralność historii i dedup | 0940 | współdzielony wynik przeżywa; rollback całej mutacji |
| Ochrona bazy | 0940 | app+GUC direct delete odrzucony; owner bez GUC odrzucony |
| Bezpieczeństwo capability | 0940, 0943 | revoke/session change przed commit blokuje; token nie wycieka |
| 4 kolumny bez rozciągania | 0941, 0943 | 1/4 tiles; desktop1440/1920 i390px; max320, touch44 |
| Punkty → maszyny → stawki | 0941, 0943 | Home/back/URL/focus/usunięcie z innego okna |
| Pełna klikalność i ikony | 0941, 0942 | klawiatura, brak nestedbutton, ikony bez nawigacji |
| Piny i szybkie liczby | 0940, 0942 | złote przypadki, zero/przegrany/niedostępny, bez full payload |
| Reset/zapis/zastąpienie | 0942 | stary zapis do potwierdzenia; dirtyguard/CAS/lostresponse |
| Miniatury i zwijanie | 0942, 0943 | 20–24px, brak zbędnego wykresu; tabela/journal collapsed |
| Domyślni konsumenci | 0942, 0943 | istniejące search/share/regression testy |
| Trwałość i kontynuacja | wszystkie | nowe procesy i izolowana DB; plan/task/Outcome/audyt/commit |

1. [TASK-0940](../tasks/completed/0940-management-atomic-edit-and-delete.md): backend,
   kontrakt, role/migracja, pin metadata, pion klient/proxy, regresje API.
2. [TASK-0941](../tasks/0941-management-compact-navigation.md): wspólna hierarchia,
   kafelki/modale i bezpieczna nawigacja/preview usuwania.
3. [TASK-0942](../tasks/0942-management-compact-stakes.md): kompaktowe stawki,
   edytor, szybkie wiersze, wykres na żądanie, default regressions.
4. [TASK-0943](../tasks/0943-management-compact-acceptance.md): zintegrowany odbiór,
   skalowane fixture'y i instrukcja operatorska/traceability.

Taski są wykonywane kolejno. Po każdym: testy, dokumentacja, Outcome, ręczny
audyt Claude, jedna runda poprawek, osobny commit, wersja/hash w Outcome i
CURRENT_STATE, przeniesienie done do completed. PASS planu nie jest audytem
implementacji. Brak raportu taska lub otwarte P0/P1 zatrzymuje przejście dalej.
P2 naprawić lub zapisać ryzyko. Nowy audyt tylko na polecenie albo gdy poprawka
zmienia zachowanie objęte P0/P1. Raporty według AUDIT_REPORT_TEMPLATE.

## Weryfikacja, ryzyka i wyłączenia

Komendy i limity w plikach tasków; najpierw testy pionu, lint/typecheck,
potem regresje/build. Test klienta buduje dist wyłącznie w izolowanym worktree.
Nie uruchamiamy benchmarków ani milionowych fixture'ów. Skala odbioru: 40
punktów, do40 maszyn/punkt, gameIds≤200; fixture ograniczony, bez obciążania
bazy operatora. Nowy proces potwierdza trwałość, rollback oznacza rollback
transakcji, nie downgrade danych. Odtworzenie po hard delete to zweryfikowany
backup binarny do osobnej bazy. Audyty modelowe nie zastępują fizycznego
odbioru operatora, live ingress i jego restartu komputera/usług.

Aktualizujemy wymagania/architekturę MANAGEMENT_PANEL, MANAGEMENT_PANEL_OPERATIONS,
TRACEABILITY, D-536 i adnotację D-533. Zakaz historii delete/global corrections
jest ograniczony do zakresu panelu; nie rozszerzamy tego zadania na usuwanie
katalogu gier ani zmianę wszystkich archiwizacji w aplikacji. Taka zmiana
wymaga osobnego przeglądu ich modeli i zgód danych. Brak Redis/Celery, nowych
serwisów, hostingu czy kopiowania wyszukiwarki.

Dowody audytów planu: `ai_docs/quality/ADMIN_COMPACT_PANEL_PLAN_AUDIT_ROUND_1.md`
(REVISE) oraz ROUND_2 (PASS z uwagami). Uwagi rozstrzygnięte powyżej: publiczne
delete zaakceptowane, ślad tylko receipt, pure delete wyłączone z redakcji,
POST zamiast DELETE, bez zależności startowej od Mumii, backfill preview,
bounded cleanup/fallback/agregaty, rola owner+GUC, URL bez szkicu, izolowane dist.
Modele Codex potwierdzone w katalogu bieżącego środowiska; modele Claude
operator potwierdził do audytu zewnętrznego. Claude Code jest dostępny w pakiecie
Claude Desktop, lecz osobny proces zgłasza brak logowania. Samodzielne wysyłanie
audytów jest autoryzowane; możliwość headless dispatch pozostaje niezweryfikowana.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0940 | gpt-6.1-sol | high | Transakcje, role, redakcja receiptów, integralność i spójny kontrakt API. | Obowiązkowy ręczny claude-fable-5-1 / high przed commitem. |
| TASK-0941 | gpt-6-sol | medium | Konkretny układ wspólnych komponentów; istniejące guardy i kontrakt. | Obowiązkowy ręczny claude-opus-5-5 / medium przed commitem. |
| TASK-0942 | gpt-6.1-sol | high | Stan szkicu, wspólne obliczenia i ochrona search/share podczas integracji. | Obowiązkowy ręczny claude-fable-5-1 / high przed commitem. |
| TASK-0943 | gpt-6-sol | medium | Odbiór ustalonego przepływu, ograniczone fixture'y i dokumentacja. | Obowiązkowy ręczny claude-opus-5-5 / medium przed commitem. |
