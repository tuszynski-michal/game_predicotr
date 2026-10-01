---
title: Remote Reviewer threat model
status: accepted
last_updated: 2026-09-30
---

# Model zagrożeń zdalnego Reviewera

## Granica i przepływ

W trybie zdalnej ręcznej selekcji od v0.7.51 publiczny host jest wyłącznie
bramką dostępu. Folder źródłowy, uchwyt wynikowy, decyzje, zoom, scroll i
wybrane JPEG-i pozostają na urządzeniu operatora. API tworzy techniczne,
path-free binding pod artifact root tylko po to, aby zachować istniejący model
sesji i revoke; binding nie jest katalogiem wyniku i nie przyjmuje danych
operatora.

Operator jawnie wybiera katalog nadrzędny z prawem `readwrite`; Reviewer tworzy
`<źródło> wybrane` i weryfikuje własne pliki checksumą. Przeglądarka nie
udostępnia aplikacji ścieżki absolutnej ani rodzica uchwytu źródłowego. Uchwyt i
postęp są w IndexedDB operatora, a zoom i scroll w jego localStorage. Po
restarcie permission może wymagać ponownej zgody. Brak File System Access API
blokuje zapis fail-closed.

Publiczne endpointy historycznego control plane/transferu pozostają objęte
allowlistą i testami bezpieczeństwa, ale nowy workspace ich nie wywołuje.
Usunięcie ich wymaga osobnego zadania migracyjnego; samo ich istnienie nie
upoważnia klienta do wznowienia transferu JPEG-ów na host.

```mermaid
flowchart LR
    U["Zdalny recenzent"] -->|"HTTPS + link bez sekretu"| T["Cloudflare Quick Tunnel"]
    T -->|"outbound tunnel"| R["Reviewer Next.js\n127.0.0.1:3001"]
    R -->|"allowlista + Bearer z HttpOnly cookie"| A["FastAPI\n127.0.0.1:8000"]
    A --> P[("PostgreSQL\n127.0.0.1")]
    A --> F[("obrazy pod artifact root")]
    X["Admin / worker / release API"] -. "brak trasy publicznej" .- T
```

Publiczny origin kończy się w aplikacji Reviewer. Nie tunelujemy portu API,
Admina, PostgreSQL ani workera. Next.js przekazuje wyłącznie jawnie
dozwolone odczyty kontekstu jednej sesji, operacyjne review, assety, korektę
geometrii i decyzję planszy. Wszystkie pozostałe ścieżki zwracają `403`.

Od TASK-0790 (D-467) korekta odroczonej planszy (`geometry-preview`,
`manual-resolution`) ma tę samą trasę, metodę, allowlistę i autoryzację
zakresu sesji (`authorize_scope`, aktor `reviewer-session:<id>`), ale API
zapisuje wynik ścieżką wirtualną: renderuje komórki w pamięci z niezmiennego
źródła i nie tworzy plików cropów. Koszt jednego żądania to dekodowanie
jednego źródła i inferencja 15 komórek przypiętym modelem, jak dotąd.

Od TASK-0796 (D-467 S6) to samo dotyczy korekty geometrii bieżącej planszy
(`image-review-items/{id}/geometry-preview` i `.../geometry-revisions`):
trasy, metody, allowlista proxy, kontrakt wejścia i autoryzacja sesji są bez
zmian, ale API deleguje do `VirtualGridGeometryService` (render w pamięci,
rewizja `virtual_source` z manifestem renderu, replay po `idempotencyKey`).
Ścieżka zapisu plików cropów v19 nie istnieje, więc żądanie przez tunel nie
może już utworzyć pliku pod artifact root. Koszt żądania to dekodowanie jednego
źródła i render 15 komórek (bez inferencji modelu dla istniejącej planszy).
Endpoint `.../assets/cells/{cellIndex}` pozostaje na allowliście dla zgodności
kontraktu, ale dla planszy wirtualnej zawsze odpowiada
`404 IMAGE_REVIEW_VIRTUAL_ASSET_UNAVAILABLE` (żaden plik nie jest czytany).

Zdalna ręczna selekcja współdzieli ten sam proces i tunel, ale nie tę samą
powierzchnię uprawnień. `/manual-selection` używa wyłącznie `/selection-api`,
osobnego cookie `gp_remote_selection_token` i stałej intencji proxy
`reviewer-v1`. Po TASK 11 zamknięta allowlista obejmuje unlock, context,
heartbeat, takeover oraz dokładne route tworzenia kolekcji/partii, stronicowanej
rejestracji metadanych, operacji, state delta, status transferu i jeden
checksum-bound binarny `PUT` na plik. Materializacja jest wykonywana wyłącznie
przez lokalny general worker i nie ma publicznego route. TASK 15 dodaje wyłącznie
GET preview i POST finalize dokładnej partii; allowlista nie obejmuje reopen,
zapisu manifestu ani dowolnej operacji Admina. Cookie starego Reviewera nie autoryzuje
selekcji, a cookie selekcji nie autoryzuje `/review-api`.

Tryb `Otwórz lokalnie` jest odrębną granicą operatorską. Nie uruchamia
Cloudflare ani sesji z kodem, a Reviewer odblokowuje wskazany scope tylko przy
żądaniu strony z nagłówkiem `Host` równym loopback na porcie 3001. Następnie
przeglądarka łączy się bezpośrednio z Admin API na `127.0.0.1`; zdalny komputer
interpretuje taki adres jako własny loopback i nie uzyskuje dostępu do API
właściciela. Publiczny host z parametrami trybu lokalnego pozostaje za bramką
sesji i kodu.

### Udostępniona wyszukiwarka plansz (D-471, D-472, D-475)

Trzecia powierzchnia tego samego procesu i tunelu: `/board-search?share=<id>`
z proxy `/board-search-api`. Jest wyłącznie do odczytu i obejmuje jedną grę
wybraną przy tworzeniu linku w Adminie. Odbiorca ma własne cookie
`gp_board_search_token` (`HttpOnly`, `Secure`, `SameSite=Strict`,
`Path=/board-search-api`) i stałą intencję proxy `reviewer-board-search-v1`
(nagłówek `X-Board-Search-Share-Proxy`). Zamknięta allowlista to: unlock
kodem, kontekst, symbole, obraz symbolu z sumą, wyszukiwanie, przybliżona
wygrana, szczegóły planszy i przycięty widok planszy — wyłącznie `GET` poza
unlockiem, z dokładnymi parametrami. Brak poprawiania pól, odświeżania
odczytu, pełnych zdjęć, tras Admina i odczytu dziennika zapytań. Cookie
udostępnienia nie autoryzuje `/review-api` ani `/selection-api`, a ich cookie
nie autoryzują `/board-search-api` (testy w obu kierunkach). API bierze grę
wyłącznie z sesji; parametr gry w zapytaniu jest odrzucany.

Każde wykonane zapytanie o dane (wyszukiwanie, zakres, szczegóły planszy)
zostawia jeden wpis dziennika; żądanie odrzucone przy walidacji parametrów
(`422`, bez odczytu danych) nie jest zapytaniem i nie jest zapisywane (czas, parametry, skrót wyniku, kod wyniku) bez adresu
IP i nagłówków. Wpis jest zatwierdzany przed wysłaniem danych; jeżeli nie da
się go zapisać, odbiorca dostaje `503` bez danych. Bramka kodu informuje o
zapisie przed podaniem kodu. Dziennik czyta tylko właściciel w Adminie na
loopbacku.

## Chronione zasoby i aktorzy

- prywatne obrazy źródłowe, plansze i cropy,
- etykiety symboli, statusy i audyt decyzji,
- kod wejścia, bearer token i identyfikator sesji,
- integralność zakresu `(gameId, importJobId)`,
- trwałe przypisanie pracy `local/online` ograniczone do tego samego scope'u,
- administrator tworzący i odwołujący sesję,
- zdalny recenzent podejmujący decyzje jako `reviewer-session:<UUID>`,
- dostawca tunelu transportujący zaszyfrowany ruch.

## Zagrożenia i zabezpieczenia

| Zagrożenie | Zabezpieczenie |
|---|---|
| wyciek samego linku | link nie zawiera kodu ani tokenu; dane są pobierane dopiero po unlock |
| brute force kodu | losowy alfabet bez mylących znaków, PBKDF2-SHA256, maksymalnie 5 prób i trwała blokada |
| wyciek bazy | kod i token występują tylko jako hash; kod zdalnej ręcznej selekcji może istnieć wyłącznie lokalnie w `localStorage` Admina do TTL albo revoke |
| replay tokenu | token jest losowy, rotowany przy unlock, wygasa nie później niż sesja i jest natychmiast usuwany przy revoke |
| dostęp do innej gry/importu | każdy review read/write porównuje scope tokenu z parametrami żądania |
| dostęp administracyjny | publiczny proxy ma allowlistę; CRUD, eksporty, job mutations i wydania nie mają trasy |
| spoofing aktora | backend zastępuje `resolvedBy/correctedBy` identyfikatorem sesji |
| konflikt dwóch kart | istniejące UUID idempotencji i optimistic revision pozostają obowiązkowe |
| kradzież tokenu w JS | token trafia do `HttpOnly`, `SameSite=Strict` cookie proxy; nie trafia do URL ani localStorage |
| clickjacking/XSS | CSP, `frame-ancestors 'none'`, `X-Frame-Options: DENY`, brak zewnętrznych skryptów |
| utrata Internetu lub komputera | zapis atomowy; po powrocie recenzent wznawia kolejkę, a tunel można odtworzyć z nowym URL |
| logi z sekretami | skrypty zapisują wyłącznie publiczny URL/PID; kod i bearer nie są logowane |
| równoległy start z dwóch procesów API | nazwany mutex Windows serializuje start/status/stop dla repozytorium; stan jest publikowany dopiero po health checku |
| ponowne użycie PID albo stary plik stanu | pełna tożsamość procesu obejmuje PID, czas startu, executable i losowy instance id; niezgodny proces nie jest zatrzymywany |
| zatrzymanie nowszej instancji przez spóźnione żądanie | wewnętrzny compare-and-stop wymaga zgodnego instance id i pozostawia nowszą instancję bez zmian |
| blokada wspólnego pliku logu lub wyniku | każda próba startu i każde wywołanie kontrolera API używa unikalnej ścieżki |
| CSRF z obcego originu | mutacje `/selection-api` wymagają zgodnego `Origin`, `Sec-Fetch-Site: same-origin`, Strict cookie i JSON |
| nadużycie proxy jako ogólnego transportu | dokładna metoda/path allowlista, query tylko dla state delta/statusu, brak Authorization, control 128 KiB i jeden binarny PUT do 32 MiB z wymaganymi nagłówkami |
| złośliwy lub podmieniony JPEG | zgodność size/mtime z manifestem i checksumy z potwierdzonym SELECT, streaming do `.part`, limity per-file/session/concurrency, magic/format/full decode przed `verified` |
| zerwanie transferu lub utrata odpowiedzi | `.part` nie jest wynikiem, klient zachowuje transferId i przed retry pyta o status; zgodny artefakt po restarcie jest ponownie hashowany i dekodowany |
| crash między verified, tempem materializacji, publikacją i commitem | trwała host action z lease/fencing, same-volume temp, fsync, checksumowany journal i bounded reconciliation prowadzą do jednego synced wyniku albo kontrolowanego konfliktu |
| restart po rename `.verified`, ale przed commitem bazy | reconciler ponownie sprawdza regular file, rozmiar i SHA-256, a CAS po `updated_at` publikuje dokładnie jeden stan i jedną akcję |
| potraktowanie osieroconego `.part` jako wyniku | `.part` nigdy nie jest adoptowany; próba kończy się kontrolowanym `failed`, bajty pozostają tylko w niedestrukcyjnym preview GC |
| wyciek danych przez recovery/status | publiczny delta i lokalny recovery detail zawierają wyłącznie liczniki, heartbeat i stabilne findings; logi/audyt redagują credential-like keys oraz pełne ścieżki Windows |
| przypadkowe usunięcie podczas diagnostyki | GC ma wyłącznie agregatowy preview z `deletionEnabled=false`; brak endpointu i kodu wykonującego delete |
| nadpisanie obcego lub zmienionego `seq_*` | wyłączne utworzenie finalnej nazwy; adopcja tylko przy zgodnym journalu identity i checksumie, inaczej fail-closed bez replace/delete |
| stale generation po spóźnionym uploadzie | ponowna blokada pliku/transferu/partii i sprawdzenie desired state, generation i checksumy przed filesystemem oraz przed commitem |
| reparse/TOCTOU podczas materializacji | pinned final handles bez `FILE_SHARE_DELETE`, dokładna host-internal ścieżka verified, regular-file/reparse checks źródła, tempu, journalu i celu |
| odznaczenie po publikacji własnego pliku | generacyjny tombstone anuluje starsze transfery, superseduje materializację i uruchamia priorytetową akcję `remove` przed kolejną materializacją |
| usunięcie obcego albo zmienionego `seq_*` | usunięcie wymaga zgodnego materialization journalu i checksumy; pinned-handle rename przenosi tylko zweryfikowany własny plik do host-internal kwarantanny |
| crash podczas odznaczania | checksumowany removal journal rozróżnia prepared/quarantined, a retry adoptuje tylko zgodny półstan; kwarantanna pozostaje odwracalna i bez GC |
| spóźniona generacja po deselect/reselect | lease fencing, blokada wiersza, generation recheck i priorytet `remove` uniemożliwiają materializację N po zastosowaniu N+1 |
| awaria ingressu podczas revoke | revoke nie odczytuje ani nie zatrzymuje ingressu; token i lease są czyszczone niezależnie |
| replay albo utrata odpowiedzi operacji | trwały outbox, dokładne `operationId + checksum`, monotoniczny client sequence/revision/generation i zwrot zapisanego outcome bez ponownej mutacji |
| wysłanie operacji bez writer lease | autoryzacja writer ownership i mutacja odbywają się w tej samej transakcji; po expiry dozwolony jest wyłącznie exact retry istniejącego outcome |
| zalanie control plane | limit 1200 żądań na minutę per sesja oraz stabilny błąd `REMOTE_SELECTION_CONTROL_RATE_LIMITED`; rotacja client ID nie odnawia budżetu |
| podmiana źródeł po rozpoczęciu pracy | pełny checksum manifestu jest weryfikowany przed aktywacją; aktywny manifest jest niezmienny |
| przedwczesna albo powtórzona finalizacja | rewizyjny preview, transakcyjna blokada i kontrola wszystkich operacji/transferów/akcji/pliku; retry adoptuje tylko identyczny journal |
| podmiana finalnego manifestu | publikacja wymaga host ownership i poprzedniej checksummy; obcy lub zmieniony JSON daje konflikt bez nadpisania |
| zdalne ponowne otwarcie wyniku | reopen istnieje tylko pod lokalnym Admin API, wymaga exact targetu, rewizji i checksummy; `/selection-api` go odrzuca |

Host base zdalnej selekcji jest wybierany wyłącznie przez stały lokalny picker.
Publiczny request nie zawiera ścieżki. Każdy komponent collection/batch jest
walidowany jako pojedyncza nazwa Windows, a finalne katalogi są otwierane przez
uchwyty bez `FILE_SHARE_DELETE`. Reparse point/junction w istniejącym łańcuchu,
zmiana final path, case/Unicode collision oraz obcy lub uszkodzony ownership
marker kończą operację fail-closed. Uchwyt bazy, collection i batch pozostaje
otwarty przez utworzenie atomowego markera, ograniczając okno TOCTOU.

Materializacja otwiera ten sam zweryfikowany mapping, przypina verified source i
istniejący albo właśnie opublikowany target bez `FILE_SHARE_DELETE`. Pliki
robocze i journale znajdują się wyłącznie pod
`.game-predictor/remote-selection-v1/materializations/<file>/<generation>`.
Journal wiąże action/session/batch/file/transfer/generation/output/checksum;
niezgodny lub zbyt duży journal jest konfliktem. Kod nie usuwa obcego targetu,
nie nadpisuje go i nie usuwa żadnej ścieżki poza własnym working artifactem.

Odznaczenie używa osobnego journalu pod
`.game-predictor/remote-selection-v1/quarantine/<file>/<generation>/<action>`.
Executor blokuje immutable mapping partii, weryfikuje tożsamość wcześniejszej
materializacji i jej checksumę, a następnie zmienia nazwę przez przypięty uchwyt
Windows. Przejściowy konflikt antywirusa/indeksera ma krótki, ograniczony retry
na tym samym uchwycie; każdy inny błąd pozostaje fail-closed. Kwarantanna nie
jest czyszczona przed rozstrzygnięciem polityki retencji.

Zdalna ręczna selekcja ma osobny purpose i nie używa scope
`gameId/importJobId` istniejącego Reviewera. Kod jest zwracany wyłącznie przy
lokalnym create, ma maksymalnie pięć trwałych prób i jest przechowywany przez
API jako PBKDF2-SHA256. Panel Admina może przechować jego surową wartość
wyłącznie lokalnie w `localStorage` profilu właściciela, dokładnie do `expiresAt`
albo revoke; nie wysyła jej ponownie, nie loguje i nie udostępnia jej przez
listę API. Unlock rotuje losowy token zapisany wyłącznie jako SHA-256;
publiczna odpowiedź ustawia go w cookie `HttpOnly`, `Secure`,
`SameSite=Strict`, `Path=/selection-api` i nie zawiera bearer w JSON. Revoke i
piąta błędna próba atomowo usuwają token oraz writer lease.

Jedna sesja ma jeden 45-sekundowy writer lease. Klient przesyła wyłącznie
`clientInstanceId`; fencing token nie opuszcza bazy. Aktywny lease innego
klienta daje tryb read-only, heartbeat nie przyjmuje fencing tokenu, a takeover
przed expiry kończy się konfliktem. Audyt zapisuje wynik i licznik prób, ale
odrzuca kod, token, salt, lease token i ścieżkę hosta.

Control plane nie przyjmuje host base path ani bajtów obrazu. UUID kolekcji,
partii, pliku i operacji są sprawdzane względem purpose-scoped sesji. Rejestracja
źródła jest ograniczona do 500 metadanych na request; aktywacja następuje tylko
po zgodności liczby, indeksów i checksumy pełnego manifestu. State delta ma
limit 100, a mutacje i rate limit zwracają stabilne kody bez sekretów i ścieżek.

Dedykowany CSP `/manual-selection` i `/selection-api` zezwala na transport tylko
do własnego originu; nie zawiera loopback FastAPI. Route ogólne Reviewera nadal
mają dotychczasową politykę, ale matcher nie nakłada jej na nową powierzchnię.
Nieprawidłowa wartość feature flagi kończy się fail-closed. Wyłączenie flagi
usuwa shell i proxy bez usuwania trwałej sesji lub audytu.

`reviewer_work_assignments` nie rozszerza granicy dostępu. Tabela przechowuje
scope, typ pracy, identyfikator sesji online, fencing token lease, heartbeat i
historię zamknięcia. Nie zawiera kodu, bearer tokenu, publicznego URL ani
parametrów procesu. Złożony FK nie pozwala przypiąć sesji innej gry/importu, a
aktywny assignment nadal nie zastępuje autoryzacji przez
`reviewer_access_sessions`. Zamknięcie jednego assignmentu unieważnia wyłącznie
jego sesję i nie zatrzymuje współdzielonego ingressu, jeżeli istnieje inny
aktywny scope online. Globalny limit trzech online assignmentów i decyzja
`stop-if-unused` są serializowane transakcyjnym advisory lockiem. Ostatni stop
używa `instanceId`, dlatego spóźniona operacja nie zamknie nowszej instancji.
Wygasłe lease'y są domykane jako `lease_expired`, a ich scoped sesje odwoływane
przed ponownym użyciem capacity.

Admin API TASK 18 nie ujawnia w liście assignments kodu wejścia, bearer tokenu,
fencing tokenu ani osobnego pola identyfikatora sesji. Publiczny URL może
zawierać opaque identyfikator sesji, ale nie jest on sekretem. Kod występuje wyłącznie w odpowiedzi
na pierwsze utworzenie online; idempotentne ponowienie zwraca `null`. Frontend
nie przechowuje sekretu w trwałym storage. Open i close wymagają dokładnego
lokalnego high-impact targetu, a heartbeat nie przyjmuje lease tokenu od
przeglądarki. Legacy globalne endpointy ingressu nie są używane przez zwykły
przepływ sekcji zatwierdzania.

## Bramka bezpieczeństwa udostępnionej wyszukiwarki (TASK-0770)

Lista kontrolna odbioru etapu B (dowody to testy w repozytorium):

| Kontrola | Dowód |
|---|---|
| allowlista proxy równa publicznym trasom OpenAPI, trasy Admina niedostępne | `apps/reviewer/test/board-search-share-security-gate.test.mjs`, `board-search-share-proxy.test.mjs` |
| izolacja celu sesji: gra tylko z sesji, token innej sesji czyta tylko swoją grę, parametr gry odrzucony | `services/api/tests/test_board_search_share_public_api.py` |
| cookie i pochodzenie: atrybuty cookie, `Sec-Fetch-Site`/`Origin` dla unlock, rozdział cookie trzech powierzchni | `board-search-share-proxy.test.mjs`, `test-interactions/review-api-share-cookie.test.mjs` |
| kod i token: PBKDF2, kod zwracany raz, rotacja tokenu, blokada po 5 błędach, unieważnienie i wygaśnięcie | `test_board_search_share_access.py`, integracja PostgreSQL |
| limity: 120 JSON/min, 600 obrazów/min, 30 kalkulacji/min i jedna naraz, 5 aktywnych linków | `test_board_search_share_public_api.py` (wartości domyślne, 429 dla JSON, obrazów i zakresu, jedna kalkulacja naraz), `test_board_search_share_access*.py` |
| redakcja odpowiedzi: brak identyfikatorów przeglądu, planszy, importu, rekordów pól, ścieżek i sekretów (API i drugi filtr w proxy); `gameId` i `rulesVersionId` w odpowiedziach zakresu i szczegółów są dozwolone (nie są sekretami) | rekurencyjne testy kluczy w API i proxy, test schematów OpenAPI |
| stabilne błędy HTTP (`401/403/404/409/422/429/503`) | testy API tras publicznych i administracyjnych |
| dziennik zapytań: jeden wpis na wykonane zapytanie z pełnym wzorem (także `?`), wpis błędu, fail-closed, brak IP i nagłówków, brak publicznego odczytu | testy API, integracja PostgreSQL, test bramki OpenAPI |
| informacja dla odbiorcy o zapisie zapytań przed kodem | bramka kodu Reviewera (odbiór ręczny) |
| lokalny build produkcyjny Reviewera: osobny CSP bez adresu API, trasy spoza allowlisty `403` | odbiór na `next start` (TASK-0770) |

Poza bramką (wymaga osobnej zgody operatora): uruchomienie publicznego
Quick Tunnel i test z drugiego urządzenia.

## Bramka bezpieczeństwa TASK-0289

Formalna bramka ma osiem obowiązkowych kontroli: zamkniętą allowlistę zgodną z
OpenAPI, izolację purpose/sesji, cookie i CSRF, rate/quota, bezpieczeństwo
Windows/reparse/TOCTOU, redakcję, stabilne błędy HTTP oraz lokalny production
build z izolowanym stanem klientów. Maszynowy raport znajduje się w
`ai_docs/quality/remote-manual-selection-security-gate-v1.json`; jego kanoniczna
treść ma SHA-256
`8386c3676422ecb3d98994c854bb7c447f5c5452592990485f7bd9af3e4b4360`.

Audyt TASK-0289 zamknął cztery findings: brak obowiązkowego Fetch Metadata dla
mutacji, zaufanie do caller-controlled forwarded host, brak rekurencyjnej
kontroli publicznego JSON/audytu oraz ominięcie rate limitu przez exact replay.
Nie pozostał otwarty finding `critical` ani `high`. Publiczny Quick Tunnel,
pentest strony trzeciej i rollout skali są nadal poza bramką i należą do TASK 18.

## Retencja i prywatność

Sesja ma TTL od 5 minut do 24 godzin. Administrator przekazuje link i kod
osobnymi kanałami, a po zakończeniu unieważnia sesję i zatrzymuje tunel. Quick
Tunnel jest trybem czasowym do prywatnych testów pracy dyplomowej, a nie
usługą always-on ani trwałym hostingiem. Nie należy udostępniać linku szerszej
grupie ani pozostawiać tunelu uruchomionego bez aktywnej sesji.

## Awaria i reakcja na incydent

1. W panelu Admin kliknij `Unieważnij sesję`.
2. Kliknij `Zatrzymaj udostępnianie`; awaryjnie uruchom
   `npm run reviewer:remote:stop`.
3. Sprawdź `npm run reviewer:remote:status`; oczekiwany stan to `stopped`.
4. Utwórz nową sesję i nowy link dopiero po ustaleniu przyczyny.
5. Audyt `reviewer_access_audit_events` zachowuje utworzenie, błędne próby,
   unlock, blokadę i revoke bez sekretów.

### Incydent z linkiem udostępnionej wyszukiwarki

1. W Adminie w „Wyszukaj plansze” → „Udostępnij online” kliknij `Zatrzymaj`
   przy linku (działa także bez działającego tunelu); odbiorca traci dostęp
   przy następnym żądaniu.
2. Jeżeli nie ma innych aktywnych udostępnień, zatrzymaj tunel
   (`npm run reviewer:remote:stop`).
3. Awaryjnie ustaw `GAME_PREDICTOR_BOARD_SEARCH_SHARE_ENABLED=false` dla API i
   Reviewera i uruchom je ponownie: tworzenie, odblokowanie i dostęp są
   wtedy wyłączone (lista i zatrzymanie linków działają).
4. `board_search_share_audit_events` zachowuje utworzenie, błędne kody,
   blokadę, odblokowania i zatrzymanie bez sekretów, a
   `board_search_share_query_events` — co odbiorca oglądał.

## Zaakceptowany transport

W v0.1 używany jest Cloudflare Quick Tunnel: outbound-only, losowy adres HTTPS
`trycloudflare.com`, bez przekierowania portów, domeny i konta odbiorcy.
Oficjalna dokumentacja określa Quick Tunnels jako rozwiązanie
development/testing bez SLA, dlatego stały publiczny adres wymaga później
named tunnel i osobnej decyzji operacyjnej.

- <https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/>
- <https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/>
