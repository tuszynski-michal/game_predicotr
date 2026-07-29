---
title: Current project state
status: active
last_updated: 2026-07-29
---

# Current State

## Phase

`M6.2 completed — G6.2 passed; TASK-0064 next`

## Completed

- właściciel odpowiedział na Q-001–Q-014 i doprecyzował Q-018,
- zaakceptowano decyzje D-001–D-014,
- ustalono całkowicie offline mobile od M1,
- ustalono skalę do około 500 000 layoutów na grę i 12–15 gier,
- ustalono ciągłą, cykliczną sekwencję i procedurę duplikatu bez confirmation chain,
- ustalono wyłącznie wzorce `PAYLINE`, joker, sumowanie i longest match,
- D-019 zastąpiła wcześniejszy start w dowolnej kolumnie: zwycięski ciąg jest
  prefiksem od pierwszej kolumny, a każdy zwykły symbol ma wersjonowane minimum
  długości, domyślnie 3 i konfigurowalne od 2 do liczby kolumn,
- ustalono spin 0, koszt każdego kolejnego spinu i kumulację wszystkich payoutów,
- Target obejmuje `layout_count - 1` spinów i pokazuje dodatnie lokalne maksima,
- zaakceptowano precomputing payoutów, SQLite w APK i lokalny proces wydania,
- przeanalizowano trzy przykładowe zdjęcia i zaakceptowano wymienny stos prototypu,
- zsynchronizowano wymagania, architekturę, model danych, kontrakty, roadmapę i testy,
- podzielono M1 na sześć podetapów z osobnymi bramkami jakości,
- ustalono wersjonowaną aktywację snapshotu po aktualizacji APK,
- zweryfikowany APK M1 `0.1.2 (3)` z payout-v2 nie deklaruje uprawnienia
  Android `INTERNET` i jest gotowym kandydatem do odbioru na urządzeniach,
- usunięto artefakty instalacyjne pakietu dokumentacji, a materiały historyczne
  przeniesiono do `ai_docs/archive/` i `ai_docs/tasks/completed/`,
- ukończono `TASK-0002`: monorepo npm, TypeScript strict, Python 3.12 tooling,
  minimalny snapshot SQLite, kontrolowany `local_data_error` i ekran
  diagnostyczny,
- zbudowano na Windows samodzielne, testowo podpisane APK `arm64-v8a` z bundlem
  JavaScript i dokładnie zweryfikowanym snapshotem SQLite,
- zaakceptowano D-013 opisującą toolchain, package manager, `applicationId`
  oraz lokalny workflow Android,
- ukończono `TASK-0003`: zgodne kontrakty domenowe TypeScript/Python,
  stałoszeroki codec sygnatury, walidację planszy/paylines/payout rules i
  współdzielone fixture,
- zaakceptowano D-015 definiującą tekstowy codec v1, jawne
  `signature_cell_width` i zakres dodatnich kodów `smallint`,
- ukończono `TASK-0004`: czysty build-time payout engine, joker, longest
  match, sumowanie paylines, strukturalny audit i golden cases,
- D-016 pierwotnie definiowała granicę pięciu kolumn payout-v1 i strukturalną
  interpretację jokera; semantykę payout-v1 zastąpiła D-019, a strukturalny
  audyt pozostał obowiązujący,
- ukończono `TASK-0005`: pełny cykl Target `N - 1`, kumulację payoutów i
  kosztów, dodatnie lokalne maksima, plateau i golden cases,
- zaakceptowano D-017 definiującą granicę uporządkowanego strumienia Target i
  jednoprzebiegowe wykrywanie szczytów,
- pierwotnie ukończono podetap M1.2 i bramkę G2 dla payout-v1; korektę D-019 i
  ponowną walidację wykonano w TASK-0090,
- pierwotnie ukończono `TASK-0006`: deterministyczne fixture dla 3 gier po
  1000 layoutów, osobne seedy, precomputed payout, 6 par duplikatów na grę,
  unikalne prefiksy i ręcznie policzone golden pełnego Target; aktualną wersję
  opisuje późniejszy wpis TASK-0090,
- dodano walidator kolejności, komórek, sygnatur, payoutów, duplikatów,
  prefiksów i golden totals,
- ukończono `TASK-0007`: finalny SQLite schema version `2`, manifest, logiczna
  checksum, SHA-256 pliku, constraints i indeks sygnatur,
- zastąpiono diagnostyczny `m1-spike.db` przez deterministyczny
  `m1-snapshot.db` zawierający 3 gry, 33 symbole i 3000 layoutów,
- zaakceptowano D-018 definiującą finalny kontrakt SQLite M1; aktualną checksumę
  artefaktu opisuje późniejszy wpis TASK-0090,
- ukończono `TASK-0008`: mobilny adapter jednego otwartego SQLite dla katalogu
  gier, exact/prefix matching i pełnego cyklicznego strumienia `N - 1`,
- testy na finalnym snapshotcie potwierdzają unique, duplicate, not found,
  puste i wieloznaczne prefiksy, zawinięcie cyklu oraz użycie indeksów,
- benchmark fixture 1000 layoutów zapisał p95 `0.1627 ms` dla exact,
  `0.1655 ms` dla prefix i `3.1932 ms` dla pełnego cyklu; baza ma `274432`
  bajty i część repozytoryjna otworzyła ją raz,
- pierwotnie ukończono podetap M1.3 i bramkę G3; adapter oraz benchmark
  pozostają technicznie aktualne, a generator, payouty, snapshot, manifest i
  checksumy odtworzono po D-019 w TASK-0090,
- ukończono `TASK-0009`: czysty reducer planszy, row-major Layout, wybór gry,
  Selection symboli, Undo, Reset i przygotowanie auto-uzupełnienia jako jednego
  kroku historii,
- główny ekran po walidacji snapshotu korzysta z prawdziwego katalogu trzech
  gier; kafelki i przyciski mają jawne stany oraz etykiety dostępności,
- ukończono `TASK-0010`: prefix matching po każdej zmianie niepustej planszy,
  dokładny licznik kandydatów, modal jednego pełnego layoutu i akceptacja jako
  jeden krok Undo,
- odrzucony prefiks nie otwiera modala w pętli, a wyniki starszych zapytań są
  ignorowane po Append, Undo, Reset albo zmianie gry,
- ukończono `TASK-0011`: exact matching wyłącznie dla pełnej planszy oraz jawne
  stany unique, duplicate, not found, loading i błędu lokalnych danych,
- pełna plansza wyłącza prefix lookup; duplikat nie wybiera arbitralnej pozycji,
  a Undo, Reset i zmiana gry usuwają nieaktualny wynik,
- ukończono podetap M1.4 i bramkę G4: kompletny matching działa lokalnie bez
  Target, komponenty nie znają SQLite, a stan jest przekazywany tekstem, nie
  tylko kolorem,
- ukończono `TASK-0012`: exact unique uruchamia jeden cykliczny odczyt `N - 1`
  i istniejący Target engine z metadanymi zweryfikowanego snapshotu,
- UI pokazuje loading, Retry, kontrolowany błąd i podsumowanie pełnego cyklu;
  duplicate, not found oraz niepełna plansza nie odczytują payoutów,
- test integracyjny kształtu M1 potwierdza `999` ocenionych spinów dla `1000`
  layoutów, brak spin 0 w strumieniu i koszt końcowy `9990`,
- ukończono `TASK-0013`: główny ekran jest jednym `FlatList`, a kompletne
  wiersze dodatnich lokalnych maksimów znajdują się pod podsumowaniem Target,
- golden UI pokazuje dla 999 spinów szczyty `190` i późniejszy niższy `180`,
  zachowuje pierwszy spin plateau oraz nie tworzy wiersza dla zera,
- test długiej listy potwierdza okno renderowania zamiast jednoczesnego
  montowania 100 wierszy,
- pierwotnie ukończono podetap M1.5 i bramkę G5; przepływ oraz wirtualizacja
  pozostają, a golden Target przeliczono dla payout-v2 w TASK-0090,
- zbudowano i zweryfikowano prywatnie podpisane APK M1 `0.1.0 (1)` dla
  `arm64-v8a`; artefakt ma `42 140 070` bajtów i SHA-256
  `1eb8da0ba87a19f42975e46a192af190cf5e51905b97126204c8495ffe2bc0a3`,
- finalny manifest APK nie deklaruje `android.permission.INTERNET`, release nie
  jest debuggable i używa certyfikatu `Game Predictor Private Release`,
- dodano trwały ignorowany signing key, parametry wersji, release verifier,
  skrypt odbioru urządzenia i manualny protokół testów Pixel/Samsung,
- lokalna część TASK-0014 dla aktualnego artefaktu przeszła pełną bramkę
  jakości (63 mobile, 23 shared, 53 Python), walidację snapshotu i niezależny
  audyt APK,
- ukończono `TASK-0090`: kontrakty TypeScript/Python modelują wersjonowane
  minimum długości per zwykły symbol, a payout engine liczy wyłącznie ciągły
  prefiks zaczynający się w pierwszej kolumnie,
- golden payout-v2 pokrywają minima 2 i 3, późny start, lukę, longest match,
  jokera, ciąg samych jokerów, współdzielone komórki oraz planszę szerszą niż
  pięć kolumn,
- wygenerowano spójne `m1-fixture-v2`, dataset/rules version `2`,
  `algorithm_version = payout-v2` i mobilny snapshot `m1-fixture.2`; fingerprint
  fixture to `2b8345577ec949f102ae21992cef197e5c5756e184d43815a5dd527d25eb2b79`,
  a SHA-256 SQLite to
  `4365a33d066a354d212693cd9169dac102b7cb1c164df6693f655e8690e9224a`,
- przeliczone golden Target zachowują kontrolowane wyniki: game-1 od sequence
  99 ma payout `310`, koszt `9990`, net `-9680` i szczyty `190`, `180`,
- zbudowano i statycznie zweryfikowano prywatnie podpisane APK `0.1.2 (3)` dla
  `arm64-v8a` z `m1-fixture.2` i `payout-v2`; artefakt ma `42 143 594` bajty,
  SHA-256
  `906d2969fccbc629d849d5368673ca7ed897949d52b9b60bcb712a08457af0f0`
  oraz bazę SQLite o SHA-256
  `4365a33d066a354d212693cd9169dac102b7cb1c164df6693f655e8690e9224a`,
- pierwszy odbiór Samsunga wykrył zatrzymany loader po poprawnej inicjalizacji
  SQLite; stan i weryfikację przeniesiono do komponentu potomnego
  `SQLiteProvider`, a test regresji potwierdza przejście do workspace,
- Samsung `SM-G998B` z Androidem 15 zaktualizował aplikację in-place z
  `0.1.1 (2)` do `0.1.2 (3)`; instalacja trwała `28,39 s`, a start procesu
  `0,74 s`,
- Pixel 10 Pro XL z Androidem 16 zainstalował `0.1.2 (3)` przy włączonym trybie
  samolotowym i wyłączonym Wi-Fi; instalacja trwała `15,78 s`, a start procesu
  `1,1 s`,
- właściciel przeszedł offline na Samsungu i Pixelu scenariusze unique 99 z
  golden Target, duplicate 101/995, not found z Undo, Reset, zmianę gry oraz
  przewijanie tabeli; wszystkie zakończyły się poprawnie,
- właściciel zaakceptował M1 i G6 2026-07-26; zgodnie z D-020 test aktywacji
  celowo zmienionego snapshotu i dokładne pomiary urządzeniowe przeniesiono do
  M3.4–M3.5,
- ukończono `TASK-0014`: samodzielny APK, audyt offline, podpis, aktualizacja
  in-place i scenariusze na Pixel 10 Pro XL oraz Galaxy S21 Ultra,
- ukończono `TASK-0015`: lokalny Next.js `apps/admin`, FastAPI `services/api`,
  walidowaną konfigurację loopback, endpoint `/api/v1/health`, testy i komendy
  Windows; panel produkcyjny odpowiada HTTP 200, a API `ok / 0.1.0`,
- zaakceptowano D-021 definiującą przypięty baseline M2 i zakaz przypadkowego
  wystawienia panelu/API poza loopback,
- zaimplementowano techniczną część `TASK-0016`: PostgreSQL
  `18.4-alpine3.24`, loopback Compose, trwały volume, SQLAlchemy/Psycopg,
  walidowany URL oraz pusty baseline Alembic `0001_empty_baseline`,
- statyczne testy TASK-0016 potwierdzają jeden head, SQL upgrade/downgrade,
  brak tabel domenowych i izolację bazy `game_predictor_baseline_test`; pełne
  `npm run quality` przechodzi z 71 testami Python i jednym jawnym skipem
  wymagającym Docker Desktop,
- zaakceptowano D-022 definiującą lokalny PostgreSQL i cykl migracji,
- ukończono `TASK-0016`: Docker Desktop/WSL uruchamia przypięty PostgreSQL
  18.4, kontener osiąga stan `Healthy`, a izolowany fizyczny test
  `upgrade → downgrade → upgrade` przechodzi bez dotykania bazy
  deweloperskiej ani usuwania trwałego volume,
- ukończono `TASK-0017`: FastAPI jest kanonicznym źródłem OpenAPI 3.1,
  deterministyczny artefakt generuje typowany klient Fetch dla panelu, a
  kontrola driftu kontraktu i kodu jest częścią `npm run quality`,
- zaakceptowano D-023 definiującą `@hey-api/openapi-ts 0.99.0`, brak ręcznie
  utrzymywanych typów odpowiedzi oraz wyłączenie aplikacji mobilnej z klienta
  Admin API,
- zaliczono bramkę G2.1: lokalne fundamenty Next.js, FastAPI, PostgreSQL,
  Alembic i generowanego kontraktu przeszły pełną bramkę jakości oraz
  produkcyjny build panelu,
- ukończono `TASK-0018`: domena, repozytorium i Admin API udostępniają CRUD gier
  i symboli, a migracja `0002_games_symbols` chroni stabilne kody, zakres
  `mobile_code`, relację symbol–gra i unikalność w PostgreSQL,
- wygenerowany klient panelu zawiera typowane operacje gier i symboli, a fizyczne
  testy PostgreSQL zaliczyły migracje, repozytorium i konflikty constraints,
- zaakceptowano D-024: stabilne kody są nieedytowalne, a publiczne `DELETE`
  zawsze oznacza archiwizację bez fizycznego usuwania,
- ukończono `TASK-0019`: responsywny shell panelu i katalog gier obsługują
  listowanie, tworzenie, edycję nazwy/statusu oraz archiwizację po jawnym
  potwierdzeniu przez typowany klient Admin API,
- panel rozróżnia loading, empty, error i success, blokuje wielokrotny zapis,
  pozostawia zarchiwizowane rekordy na liście i nie wyprzedza zakresu wymiarów,
  kosztu spinu ani symboli,
- generator klienta używa importów bez rozszerzenia zgodnych z
  `moduleResolution: Bundler`; kontrola driftu, 11 testów panelu i produkcyjny
  build Next.js przechodzą,
- uruchomiony lokalnie panel odpowiedział HTTP 200, API zgłosiło `ok`, katalog
  zwrócił poprawną pustą listę, a preflight CORS zaakceptował
  `http://127.0.0.1:3000`,
- ukończono `TASK-0020`: panel wybiera grę i udostępnia pełny katalog symboli
  z `mobileCode`, stabilnym kodem, nazwą, jokerem, kolejnością, statusem oraz
  względną ścieżką obrazu referencyjnego,
- formularz blokuje zmianę `mobileCode` i kodu po utworzeniu, waliduje zakresy
  liczbowe oraz bezpieczną ścieżkę POSIX, a archiwizacja wymaga potwierdzenia i
  pozostawia symbol na liście,
- mały workspace odświeża selektor symboli po zmianie katalogu gier bez
  globalnego store; odpowiedzi i błędy nadal przechodzą wyłącznie przez
  generowany klient Admin API,
- TASK-0020 przeszedł 19 testów panelu, produkcyjny build Next.js, 2 fizyczne
  testy integracyjne PostgreSQL i lokalny smoke HTTP 200 dla obu sekcji,
- zaliczono bramkę G2.2; gra ma tożsamość i katalog symboli, ale wymiary, koszt
  spinu i wersje reguł pozostają zgodnie z planem w M2.3,
- ukończono `TASK-0021`: migracja `0003_rules_versions`, domena, repozytorium i
  Admin API udostępniają serwerowo numerowane wersje reguł ze statusami
  `draft/published/archived`, wersjonowanymi wymiarami i kosztem spinu,
- tworzenie blokuje rekord gry i przydziela `max(version) + 1`, lista pokazuje
  najnowszą wersję pierwszą, a aktualizacja chroni wersje inne niż draft,
- wygenerowany klient i panel pozwalają wybrać grę, utworzyć draft 3 × 5 / 10,
  przeglądać historię oraz edytować wymiary i koszt wyłącznie draftu,
- TASK-0021 przeszedł pełną bramkę jakości, produkcyjny build Next.js i 2
  fizyczne testy PostgreSQL obejmujące rollback migracji oraz repozytorium,
- zaakceptowano D-025 definiującą serwerową numerację i mutację wyłącznie draftu;
  kolejne TASK-0022–TASK-0024 domknęły paylines, konfigurację symboli i publikację,
- ukończono `TASK-0022`: migracja `0004_paylines`, domena, repozytorium i Admin
  API obsługują listowanie, tworzenie, edycję, archiwizację i ponowną aktywację
  wzorców draftu wersji reguł,
- `row_path` ma po jednym indeksie 0-based dla każdej kolumny; domena i baza
  blokują błędną długość, nieistniejący wiersz, zduplikowaną ścieżkę oraz zmianę
  wymiarów unieważniającą zapisany wzorzec,
- panel pokazuje wzorce w tabeli i udostępnia modalną siatkę 1-based, która
  pozwala wybrać najwyżej jedną komórkę w każdej kolumnie oraz zapisać dopiero
  kompletną linię,
- TASK-0022 przeszedł pełną bramkę jakości: 102 testy Python, 63 mobile, 29
  panelu, 23 wspólnej domeny i 4 klienta API, produkcyjny build Next.js oraz 2
  fizyczne testy PostgreSQL,
- zaakceptowano D-026 definiującą stabilny kod payline, archiwizację bez
  zwalniania `row_path` oraz bezpieczne zmiany wymiarów draftu,
- ukończono `TASK-0023`: migracja `0005_symbol_payouts`, domena, repozytorium i
  Admin API obsługują wersjonowane minima symboli oraz CRUD payout rules,
- zwykły symbol ma próg `2..columns`, joker próg `null` i nie może otrzymać
  payoutu; podniesienie minimum archiwizuje reguły poniżej progu, a rola
  zwykły/joker staje się niezmienna po użyciu w wersji reguł,
- panel udostępnia osobny modal „Payouty”, domyślne minimum 3, dynamiczne pola
  wszystkich wymaganych długości oraz walidację kompletnego, ściśle rosnącego
  zestawu przed zapisem,
- TASK-0023 przeszedł pełną bramkę jakości: 108 testów Python, 63 mobile, 34
  panelu, 23 wspólnej domeny i 5 klienta API, produkcyjny build Next.js oraz 2
  fizyczne testy PostgreSQL,
- zaakceptowano D-027 definiującą upsert konfiguracji symbolu, archiwizację
  payoutów bez zwalniania tożsamości i przejściową niekompletność draftu,
- ukończono `TASK-0024`: jeden deterministyczny walidator zasila raport
  gotowości i atomową publikację wersji reguł, a każda mutacja draftu oraz
  publikacja blokują rekord `rules_versions`,
- publikacja wymaga aktywnej payline, aktywnego zwykłego symbolu oraz kompletnej,
  ściśle rosnącej macierzy payoutów; niegotowy draft nie zmienia statusu ani
  `published_at`,
- panel pokazuje wszystkie blokady w modalu, wymaga jawnego potwierdzenia,
  blokuje podwójny submit oraz pozwala idempotentnie archiwizować opublikowaną
  wersję bez utraty czasu publikacji,
- TASK-0024 przeszedł pełną bramkę jakości: 113 testów Python, 63 mobile, 36
  panelu, 23 wspólnej domeny i 6 klienta API, produkcyjny build Next.js oraz 2
  fizyczne testy PostgreSQL,
- zaakceptowano D-028 definiującą aktywne konfiguracje symboli jako skład wersji,
  wspólną walidację preflight/publish, blokadę rekordu i jawne przejście
  `published → archived`,
- zaliczono bramkę G2.3; M2.3 jest zamknięty, a kolejnym zakresem jest M2.4,
- ukończono `TASK-0025`: migracja `0006_dataset_staging`, domena, repozytorium
  i Admin API tworzą atomowo stagingową wersję z dokładnie 1000 layoutów,
- generator używa wymiarów i aktywnych symboli opublikowanej wersji reguł,
  zapisuje seed, wersję generatora oraz szerokość codeca i dla tych samych
  wejść odtwarza identyczne `sequence_number/cells/signature`,
- sześć ostatnich rekordów kontrolowanie powtarza treść wcześniejszych układów
  bez naruszania unikalności numerów sekwencji; ich raportowanie pozostaje
  zakresem TASK-0026,
- panel pozwala wybrać grę, opublikowaną wersję reguł i seed oraz pokazuje
  historię wersji stagingowych z pełnymi stanami interfejsu,
- TASK-0025 przeszedł pełną bramkę jakości: 121 testów Python, 63 mobile, 40
  panelu, 23 wspólnej domeny i 7 klienta API, produkcyjny build Next.js oraz 2
  fizyczne testy PostgreSQL obejmujące atomowy zapis 2000 layoutów i cykl
  migracji,
- zaakceptowano D-029 definiującą synchroniczny wyjątek dla ograniczonego mocka
  1000 rekordów; generacja docelowej skali pozostaje operacją workera,
- ukończono `TASK-0026`: jeden czysty, deterministyczny walidator raportuje
  zgodność liczby layoutów, ciągłość i unikalność sekwencji, liczbę komórek,
  przynależność symboli oraz zgodność sygnatur,
- duplikaty sygnatur są posortowanym ostrzeżeniem i nie blokują gotowości;
  mock `mock-v1` daje sześć grup `(101,995)`–`(106,1000)`, 12 layoutów w
  grupach i 6 nadmiarowych wystąpień,
- raport zachowuje dokładne liczniki, a deterministyczne próbki numerów i kodów
  ogranicza do 100 elementów z jawnym `truncated`,
- panel uruchamia raport z blokadą podwójnego żądania, pokazuje loading, błąd,
  tekstowe statusy `OK/Ostrzeżenie/Blokada`, metryki i tabelę grup duplikatów,
- TASK-0026 przeszedł pełną bramkę jakości: 125 testów Python, 63 mobile, 42
  panelu, 23 wspólnej domeny i 7 klienta API, produkcyjny build Next.js oraz 2
  fizyczne testy PostgreSQL z kontrolowanym uszkodzeniem i rollbackiem stagingu,
- zaakceptowano D-030: raport synchroniczny jest ograniczony do bounded
  `mock-v1`, a importy i duże datasety zachowują ścieżkę validation job workera,
- ukończono `TASK-0027`: layouty są stronicowane stabilnym kursorem
  `sequence_number` i prezentowane w panelu jako siatka row-major z nazwami
  symboli,
- publikacja datasetu blokuje rekord wersji, ponownie uruchamia wspólny
  walidator i atomowo ustawia `published/published_at`; sześć ostrzeżeń o
  duplikatach mocka nie blokuje publikacji, a kontrolowane uszkodzenie pozostawia
  wersję stagingową,
- archiwizacja jest idempotentna, zachowuje czas publikacji i wszystkie layouty;
  fizyczny PostgreSQL potwierdził również stabilne strony bez nakładania,
- TASK-0027 przeszedł pełną bramkę jakości: 129 testów Python, 63 mobile, 44
  panelu, 23 wspólnej domeny i 7 klienta API, produkcyjny build Next.js oraz 2
  fizyczne testy PostgreSQL,
- zaakceptowano D-031 definiującą keyset pagination, walidację pod blokadą i
  jawny lifecycle `staging → published → archived`,
- zaliczono bramkę G2.4; M2.4 jest zamknięty, a kolejnym zakresem jest M2.5,
- ukończono `TASK-0028`: izolowany scenariusz od pustej bazy przez publiczne
  Admin API tworzy grę 3 × 5, 12 symboli z jokerem, trzy poziome paylines,
  kompletne macierze payoutów, opublikowane reguły i opublikowany mock 1000
  layoutów,
- scenariusz potwierdza stabilne błędy niepełnej i zduplikowanej payline,
  niezmienność reguł, sześć grup duplikatów datasetu oraz podgląd planszy 3 × 5,
- dodano `npm run m2:acceptance` na automatycznie usuwanej bazie
  `game_predictor_m2_acceptance_test` oraz jawnie potwierdzany
  `db:reset:local`, który odrzuca brak potwierdzenia, inną nazwę bazy i
  połączenie spoza loopback,
- README opisuje kompletny bootstrap, start, odbiór, zatrzymanie i reset
  lokalnej platformy bez usuwania volume,
- TASK-0028 przeszedł pełną bramkę jakości: 129 standardowych testów Python,
  63 mobile, 44 panelu, 23 wspólnej domeny i 7 klienta API, produkcyjny build
  Next.js, osobny odbiór M2 oraz 3 fizyczne testy PostgreSQL,
- zaliczono końcową bramkę G2; M2 jest ukończony 2026-07-27, a warunek wejścia
  do M3 został spełniony,
- ukończono `TASK-0029`: dodano wspólny automat stanów jobs, osobny `stage`,
  postęp, liczniki wyników, błędy, dwuetapowe anulowanie i unikalny hash
  typowanego wejścia,
- migracja `0007_jobs` tworzy trwałe JSONB payloady, enumy, constraints,
  indeksy oraz FK źródłowego joba datasetu; jest jedynym headem Alembic,
- Admin API udostępnia create/list/get/cancel dla pięciu payloadów
  `schemaVersion = 1`, a OpenAPI i klient TypeScript zostały zregenerowane,
- zaakceptowano D-032 rozdzielającą uniwersalny lifecycle od etapów workflow;
  lease, heartbeat i ograniczenie jednego wykonania pozostają w TASK-0030,
- TASK-0029 przeszedł pełną bramkę jakości: 139 standardowych testów Python,
  63 mobile, 44 panelu, 23 wspólnej domeny i 8 klienta API, produkcyjny build
  Next.js oraz 3 fizyczne testy PostgreSQL,
- ukończono `TASK-0030`: migracja `0008_job_leases` dodaje wersjonowany
  checkpoint, licznik prób, singletonowy slot oraz komplet pól lease; constraint
  PostgreSQL dopuszcza najwyżej jeden rekord `processing`,
- lokalny worker przejmuje najstarszy job, wykonuje handler poza transakcją,
  odnawia heartbeat, zapisuje checkpoint z postępem, respektuje anulowanie i
  odzyskuje ten sam rekord po wygaśnięciu lease,
- fencing token blokuje zapis starego workera, jawne retry zachowuje job oraz
  checkpoint, a Admin API i generowany klient udostępniają `retryJob` oraz
  bezpieczne pola obserwowalności bez ujawniania tokenu,
- zaakceptowano D-033 i dodano komendy `worker:once`/`worker:poll`; konkretne
  handlery import/payout/snapshot/build pozostają zakresem kolejnych pionów,
- TASK-0030 przeszedł pełną bramkę jakości: 150 standardowych testów Python,
  63 mobile, 44 panelu, 23 wspólnej domeny i 8 klienta API, produkcyjny build
  Next.js oraz 4 fizyczne testy PostgreSQL,
- ukończono `TASK-0031`: panel ma sekcję Jobs z listą 50 najnowszych zadań,
  filtrami statusu i typu, osobnym stage, postępem określonym i nieokreślonym,
  licznikami, attempt, lease, heartbeat, wersją workera, czasami oraz stabilnym
  kodem i bezpiecznym komunikatem błędu,
- ręczne odświeżenie i polling co 2 sekundy nie nakładają requestów; polling
  działa wyłącznie dla `created/processing`, cancel wymaga dwuetapowego
  potwierdzenia i pokazuje oczekiwanie na safe point, a retry aktualizuje ten sam
  rekord bez podwójnego submit,
- test przeglądarkowy objął aktywny job, błąd, review, nieznany total, cancel,
  retry i widok 390 px; wykryty poziomy overflow usunięto przez bezpieczną
  minimalną szerokość kolumny siatki,
- TASK-0031 przeszedł pełną bramkę jakości: 150 testów Python, 63 mobile, 51
  panelu, 23 wspólnej domeny i 8 klienta API oraz produkcyjny build Next.js;
  zaliczono bramkę G3.1 i zamknięto M3.1,
- ukończono `TASK-0032`: migracja `0009_layout_payouts` dodaje wersjonowane
  wyniki z kluczem dataset/rules/sequence/algorithm, FK do layoutu i reguł,
  nieujemnym payoutem `bigint`, ścieżką audytu oraz czasem obliczenia,
- worker `worker-v2` rejestruje handler `payout-v2`, który wymaga opublikowanego
  datasetu i reguł tej samej gry oraz wymiarów, mapuje aktywną konfigurację do
  czystego engine i czyta layouty keysetowo w partiach po 1000,
- deterministyczny JSONL partii jest atomowo podmieniany przed idempotentnym
  upsertem PostgreSQL, a checkpoint powstaje dopiero po trwałym zapisie;
  wznowienie nie tworzy duplikatów i zachowuje matches, komórki, jokery oraz
  strukturalne interpretacje,
- zaakceptowano D-034 definiującą kolejność audit → upsert → checkpoint oraz
  wspólną ścieżkę JSONL dla wyników jednej partii,
- TASK-0032 przeszedł pełną bramkę jakości: 162 testy Python, 63 mobile, 51
  panelu, 23 wspólnej domeny i 8 klienta API; dodatkowo pełne 5 fizycznych
  testów PostgreSQL przeszło,
- ukończono `TASK-0033`: dokładna bramka dataset/rules/algorithm raportuje
  status źródeł, zgodność gry i wymiarów, liczbę payoutów, brak audytu oraz
  bounded próbkę 100 brakujących sekwencji bez ładowania pełnego datasetu,
- wyniki historycznego datasetu, rules lub algorytmu nie maskują braków, a
  strumieniowy walidator JSONL odtwarza nagłówek, totals, matches, komórki,
  jokery i ich interpretacje,
- testy potwierdzają bezpieczne ponowienie partii po upsercie przed checkpointem,
  wznowienie od checkpointu i zgodność wszystkich utrwalonych wyników z golden
  payout-v2; zaakceptowano D-035,
- TASK-0033 przeszedł pełną bramkę jakości: 170 standardowych testów Python, 63
  mobile, 51 panelu, 23 wspólnej domeny i 8 klienta API oraz 5 fizycznych testów
  PostgreSQL; zaliczono G3.2 i zamknięto M3.2,
- ukończono `TASK-0034`: produkcyjny generator SQLite schema v2 przyjmuje jawne
  wybory dataset/rules/algorithm, wymaga gotowości M3.2 i zapisuje wyłącznie
  metadata, games, symbols oraz layouts,
- gry i mobilne identyfikatory są deterministyczne po stabilnym kodzie, symbole
  po `mobile_code`, a layouty z dokładnym payoutem są pobierane keysetowo i
  zapisywane bounded partiami bez pełnej materializacji,
- logiczny SHA-256 powstaje podczas zapisu; kompletny plik jest publikowany bez
  nadpisywania celu, a testy potwierdzają identyczne bajty niezależnie od
  kolejności wyborów i odrzucenie częściowego strumienia,
- zaakceptowano D-036; TASK-0034 przeszedł pełną bramkę jakości: 179
  standardowych testów Python, 63 mobile, 51 panelu, 23 wspólnej domeny i 8
  klienta API oraz 6 fizycznych testów PostgreSQL,
- ukończono `TASK-0035`: manifest produkcyjny schema v1 zapisuje globalne
  wersje, checksumy i liczniki oraz kanoniczne identyfikatory dataset/rules
  każdej gry bez pól fixture,
- katalog z dokładnie `snapshot.db` i `manifest.json` jest budowany w stagingu,
  walidowany read-only i atomowo publikowany pod niezmienną ścieżką
  `snapshots/<releaseVersion>/<logicalContentSha256>/`,
- walidator sprawdza manifest, schema, metadata, FK, indeks, ciągłość sekwencji,
  symbole, sygnatury i payouty oraz strumieniowo rekonstruuje logiczny checksum;
  retry używa istniejącego artefaktu wyłącznie po ponownej pełnej walidacji,
- zaakceptowano D-037; TASK-0035 przeszedł pełną bramkę jakości: 195
  standardowych testów Python, 63 mobile, 51 panelu, 23 wspólnej domeny i 8
  klienta API oraz 6 fizycznych testów PostgreSQL; zaliczono G3.3 i zamknięto
  M3.3,
- ukończono `TASK-0036`: migracja `0010_mobile_releases`, domena, repozytorium
  i Admin API zapisują niezmienny draft wydania z 1–15 dokładnymi wyborami
  dataset/rules oraz serwerowym `payout-v2` i SQLite schema `2`,
- źródła są blokowane i atomowo zapisywane; muszą być opublikowane, należeć do
  tej samej aktywnej gry, mieć zgodne wymiary i dodatnią liczbę layoutów, a
  wersja release jest globalnie unikalnym bezpiecznym segmentem ścieżki,
- OpenAPI i publiczny klient TypeScript udostępniają create/list/detail z
  kanoniczną kolejnością gier i pełnymi UUID oraz numerami wersji,
- zaakceptowano D-038; TASK-0036 przeszedł pełną bramkę jakości: 212
  standardowych testów Python, 63 mobile, 51 panelu, 23 wspólnej domeny i 9
  klienta API oraz 7 fizycznych testów PostgreSQL,
- ukończono `TASK-0037`: endpoint build atomowo tworzy jeden nadrzędny job
  `android_build`, rewaliduje dokładne źródła i przechodzi z `draft` do
  `building`,
- worker `worker-v2` wykonuje w jednym resumowalnym przebiegu payouty per gra,
  produkcyjny snapshot, pełną weryfikację SQLite, kontrolowany Release build
  `arm64-v8a` i audyt offline APK; checkpoint schema v1 nie tworzy child-jobów,
- release zapisuje względne, niezmienne ścieżki i SHA-256, a `ready` wymaga
  aktywnego nieanulowanego joba oraz obu zweryfikowanych artefaktów; błąd albo
  anulowanie daje `failed`,
- aplikacja mobilna obsługuje produkcyjny manifest M3 schema v1 bez pól fixture,
  zachowując przejściową zgodność z fixture M1; OpenAPI i publiczny klient
  udostępniają build release,
- zaakceptowano D-039; TASK-0037 przeszedł pełną bramkę jakości: 219
  standardowych testów Python, 64 mobile, 51 panelu, 23 wspólnej domeny i 9
  klienta API oraz 7 fizycznych testów PostgreSQL,
- ukończono `TASK-0038`: panel tworzy niezmienny draft z 1–15 aktywnymi grami i
  zgodnymi opublikowanymi datasetami/regułami, uruchamia kontrolowany build oraz
  monitoruje dokładnie jeden przypięty job z retry,
- historia pokazuje pełny skład, statusy, ścieżki i SHA-256, a gotowy APK jest
  pobierany przez wygenerowany klient i kontrolowany endpoint rewalidujący plik
  względem wspólnego `artifact_root`; panel nie przyjmuje ścieżki ani komendy,
- zaakceptowano D-040; TASK-0038 przeszedł pełną bramkę jakości: 221
  standardowych testów Python, 64 mobile, 57 panelu, 23 wspólnej domeny i 9
  klienta API, produkcyjny build Next.js oraz 7 fizycznych testów PostgreSQL,
- ukończono `TASK-0091`: usunięto nieaktualne instrukcje po TASK-0090,
  zsynchronizowano przykłady fixture/API/toolchain i uporządkowano własność
  fundamentów Next.js, Alembic baseline oraz wersjonowanych wymiarów w planie
  M2 bez zmiany warunku wejścia G6,
- ukończono `TASK-0040`: generator `m35-benchmark-v1` utworzył dokładnie
  500 000 ciągłych layoutów jednej gry 3 × 5, sześć kontrolowanych grup
  duplikatów, pełne payouty `payout-v2` i produkcyjny snapshot SQLite,
- niezależny walidator odtworzył partiami po 1000 każdą sygnaturę i payout;
  snapshot ma `41025536` bajtów, logiczny SHA-256
  `1b03171b268be8ee370151fc1033a7e64cb644d21610a2d4145be0d4e7492d89`,
  a liniowa estymacja dla 15 gier wynosi `586.875 MiB`,
- rozpisano M2–M8 w siedmiu osobnych planach na 34 podetapy i 75
  zarezerwowanych zadań (`TASK-0015–TASK-0089`) z osobnymi bramkami jakości;
  nie utworzono ani nie
  rozpoczęto przyszłych plików zadań,
- właściciel potwierdził ręcznie poprawne działanie układów normalnych,
  duplikatów i pozostałych funkcji na zainstalowanym kandydacie M3.4,
- zaakceptowano D-041: implementacja M4 może ruszyć warunkowo, natomiast
  benchmarki Pixel/Samsung i formalne G3 muszą zostać domknięte po M4 i przed
  M5,
- ukończono `TASK-0043`: `layout-import-v1` definiuje ścisłe UTF-8 bez BOM,
  dokładny CSV oraz strumieniowy JSON Lines, dodatni domenowy numer sekwencji,
  tablicę komórek row-major i stabilne kody błędów,
- zaakceptowano D-042; przykłady CSV/JSONL są wykonywalnymi fixture testów, a
  czysta walidacja kontraktu nie zna ścieżek, API, ORM, wymiarów gry ani
  katalogu symboli,
- ukończono `TASK-0044`: API tworzy job importu wyłącznie dla niepustego
  lokalnego CSV/JSONL znajdującego się pod skonfigurowanym `import_root`,
  kanonizuje ścieżkę i blokuje traversal, ścieżki absolutne oraz wyjście przez
  symlink/junction,
- serwer wykonuje ograniczony preview kontraktu, liczy SHA-256 partiami,
  wykrywa zmianę pliku podczas inspekcji i utrwala poświadczony format, rozmiar,
  checksumę, wersję kontraktu oraz ścieżkę względną,
- idempotencja importu zależy od gry, treści, formatu i wersji kontraktu, więc
  kopia tych samych bajtów pod inną nazwą nie tworzy drugiego joba,
- zaakceptowano D-043, zsynchronizowano OpenAPI i klient TypeScript oraz
  zaliczono bramkę G4.1 bez zmiany schematu PostgreSQL,
- ukończono `TASK-0045`: migracja `0011_layout_import_staging` dodaje surowe
  wiersze importu izolowane kluczem `(job_id, line_number)`, fizyczny offset
  oraz dokładnie jeden wariant poprawnego rekordu albo bezpiecznego błędu,
- worker `worker-v3` rejestruje handler `import`, ponownie atestuje źródło,
  czyta CSV/JSONL bounded liniami i partiami po 1000, wykonuje idempotentny
  upsert, a dopiero potem zapisuje checkpoint bajtów i liczników,
- łańcuch checksumy fizycznego prefiksu oraz odcięcie nietrwałego ogona
  zabezpieczają restart także po awarii między upsertem a checkpointem; końcowy
  SHA-256 musi nadal odpowiadać jobowi,
- zaakceptowano D-044; pełne testy API/workera dały `324 passed`, wszystkie
  dziewięć izolowanych integracji PostgreSQL przeszło, a surowy staging nadal
  nie jest datasetem ani źródłem release.
- ukończono `TASK-0046`: osobny wariant joba
  `validate/layout_import` wiąże zakończony surowy import z opublikowaną wersją
  reguł tej samej gry, bez zmiany dotychczasowego datasetowego `validate`,
- migracja `0012_layout_import_normalization` dodaje znormalizowany staging
  keyed przez `(validation_job_id, line_number)`, z FK do surowej linii,
  zachowaniem błędów parsera i domeny oraz nieunikalnymi indeksami numeru i
  sygnatury,
- worker `worker-v4` pobiera surowe rekordy bounded partiami po 1000, waliduje
  `rows * columns` i aktywny alfabet, wyprowadza szerokość z całej wersji reguł,
  koduje signature codec v1, wykonuje upsert przed checkpointem i bezpiecznie
  powtarza partię po awarii,
- zaakceptowano D-045; staging walidacji nadal nie tworzy
  `dataset_versions/layouts` ani źródła release, dzięki czemu TASK-0047 może
  raportować luki oraz duplikaty przed publikacją,
- TASK-0046 przeszedł `329 passed` standardowych testów Python, `10 passed`
  fizycznych integracji PostgreSQL, Ruff, mypy dla 104 modułów, kontrolę
  OpenAPI/generowanego klienta, typecheck panelu i klienta oraz 11 testów
  klienta TypeScript; zaliczono G4.2.
- ukończono `TASK-0047`: zakończony staging walidacji ma read-only raport
  integralności z dokładnymi agregatami liczby wierszy, poprawnych i błędnych
  wariantów, ciągu od `1`, luk, duplikatów numerów, duplikatów sygnatur i kodów
  błędów,
- błędny wiersz jest blokadą i nie wypełnia luki; duplikat numeru blokuje,
  natomiast duplikat sygnatury pozostaje dozwolonym ostrzeżeniem,
- próbki diagnostyczne są deterministyczne i ograniczone do 100 elementów, a
  podgląd stagingu używa keyset po fizycznym `line_number` oraz filtrów statusu
  i kodu błędu,
- Admin API udostępnia `integrity-report` i `rows`; OpenAPI oraz klient
  TypeScript zostały zregenerowane, a panel nie utrzymuje ręcznych typów,
- zaakceptowano D-046; raport nie tworzy tabeli cache ani datasetu, używa
  agregatów SQL i bounded przedziałów luk bez generowania zakresu do
  największego numeru,
- TASK-0047 przeszedł `346 passed, 1 skipped` w pełnym zestawie Python z
  włączonymi `11 passed` integracjami PostgreSQL, Ruff, pełny mypy dla 109
  modułów, kontrolę OpenAPI/generowanego klienta oraz 12 testów klienta
  TypeScript.
- ukończono `TASK-0048`: panel ma osobną sekcję ręcznego importu, tworzy typowane
  joby importu i walidacji, wybiera wyłącznie ukończone walidacje
  `layout_import` oraz pokazuje dokładne statystyki, tekstowe blokady i
  dozwolone ostrzeżenia raportu TASK-0047,
- podgląd wierszy używa filtrów statusu i stabilnego kodu błędu, bounded keyset
  po `line_number` oraz planszy row-major z etykietami symboli; próbki luk i
  duplikatów jawnie informują o obcięciu,
- odrzucenie stagingu wymaga osobnego dialogu i przepisania pełnego
  `importJobId`; backend usuwa wszystkie znormalizowane wiersze importu przed
  surowymi, pozostawia joby jako audyt oraz blokuje aktywną walidację i staging
  używany przez dataset,
- zaakceptowano D-047; operacja odrzucenia nie wymaga migracji, jest
  idempotentna dla pustego stagingu i zachowuje granicę publikacji TASK-0049,
- TASK-0048 przeszedł `336 passed, 12 skipped` w standardowym zestawie Python
  oraz `11 passed` w pełnej fizycznej macierzy PostgreSQL, Ruff, mypy dla 109
  modułów, kontrolę
  OpenAPI/generowanego klienta, 12 testów klienta, 64 testy panelu,
  produkcyjny build Next.js oraz browser smoke bez błędów konsoli i poziomego
  overflow przy szerokości 390 px; zaliczono G4.3.
- ukończono `TASK-0049`: zakończona walidacja `layout_import` bez blokad może
  atomowo utworzyć opublikowany, niezmienny dataset przez setowy
  `INSERT ... SELECT`, bez materializowania layoutów w procesie API,
- publikacja blokuje wspólny job importu, wszystkie jego walidacje, wersję
  reguł i grę, ponownie liczy raport TASK-0047 oraz sprawdza liczbę skopiowanych
  rekordów przed ustawieniem `published`,
- `source_job_id = validation_job_id` jest chroniony częściowym indeksem
  unikalnym migracji `0013_layout_import_publication`; retry zwraca tę samą
  wersję, a opublikowany staging nie może zostać odrzucony,
- panel pokazuje przycisk wyłącznie dla raportu bez blokad, wymaga potwierdzenia
  niezmienności, blokuje podwójny submit i pokazuje wersję, liczbę layoutów oraz
  provenance po sukcesie,
- zaakceptowano D-048; TASK-0049 przeszedł `340 passed, 12 skipped` w
  standardowym zestawie Python, `11 passed` w pełnej fizycznej macierzy
  PostgreSQL, 12 testów klienta, 65 testów panelu, Ruff, mypy dla 109 modułów,
  kontrolę OpenAPI/generowanego klienta, typecheck, ESLint i produkcyjny build
  Next.js.
- ukończono `TASK-0050`: deterministyczny generator utworzył strumieniowy
  JSONL `layout-import-v1` z 500 000 rekordów, sześcioma kontrolowanymi grupami
  duplikatów sygnatur, SHA-256
  `214ff8b99c74b24e1781a6b70b0add738588c15c9e85d3df745e14a73ec49d8d`
  i rozmiarem `42 340 054` bajtów,
- pierwszy przebieg dużego importu został przerwany po trwałym checkpointcie
  linii 1000; retry tego samego joba zakończył 500 000 rekordów z
  `attemptCount = 2`, bez błędów i bez nadmiarowego stagingu,
- walidacja 500 000 rekordów potwierdziła ciąg `1..500000`, dokładnie
  `499 994` unikalne sygnatury i sześć dozwolonych grup duplikatów; osobny
  wariant z luką `10` i duplikatem `9` zwrócił stabilną blokadę publikacji,
- idempotentna publikacja zwróciła ten sam dataset przy retry, a pipeline
  obliczył dokładnie 500 000 payoutów i utworzył niezależnie zweryfikowany
  snapshot `41 246 720` bajtów o SHA-256
  `103eeb52c9e0e5ef2212073bbff645b67d92285645bdea35425b96307b1b6ade`,
- pierwszy Android build ujawnił `EPERM` przy destrukcyjnym czyszczeniu
  wygenerowanego katalogu; po zmianie czyszczenia na jawny opt-in kontrolowany
  builder wznowił dokładny niezmienny snapshot i utworzył prywatnie podpisany
  APK `47 409 574` bajtów o SHA-256
  `63945624cc3c19686e02f7ce2d83d435bc7f41a157473c4381d88920fb79a972`,
- niezależny audyt finalnego APK potwierdził `arm64-v8a`, release bez debug,
  podpis `Game Predictor Private Release`, standalone bundle, dokładny SQLite
  oraz brak uprawnienia `INTERNET`,
- pełny przebieg wraz z recovery trwał `3931.5769 s`; największy zmierzony peak
  RSS wyniósł `482 725 888` bajtów, a szczegółowe czasy, przyrosty pamięci,
  liczniki i historia pierwszego błędu są w
  `ai_docs/quality/m4-import-acceptance-report.json`,
- TASK-0050 przeszedł pełne `npm run quality`: 65 testów panelu, 66 mobile,
  12 klienta, 23 shared, `346 passed, 12 skipped` Python, Ruff, mypy dla 113
  modułów, PowerShell syntax, OpenAPI, typecheck i walidacje M1; osobna fizyczna
  macierz PostgreSQL zakończyła się `11 passed`,
- zaliczono G4 warunkowo na podstawie D-041; M4 nie użyło OCR, zdjęć ani
  ręcznych mutacji SQL, ale nie zalicza to nadal brakującego G3 na telefonach.
- właściciel przekazał 12 zdjęć JPEG 960 × 1280 z jednej gry i sesji oraz
  potwierdził, że obecnie nie ma dalszego materiału; D-050 dopuszcza ich
  lokalne użycie jako prototypowego korpusu bez redystrybucji,
- manifest `m5-prototype-corpus-v1` zapisuje stabilne identyfikatory, ścieżki
  względne, SHA-256, rozmiary, warunki i ciągłe zakresy sekwencji 1–108;
  oryginalne obrazy pozostają ignorowane przez Git,
- przygotowano schema golden annotations, adnotacje samych sekwencji,
  proponowane — jeszcze niezaakceptowane — progi jakości oraz walidator
  checksum, wymiarów JPEG, podziału źródeł, zakresów i kompletnej geometrii,
- TASK-0051 ma `5 passed`, Ruff i mypy bez błędów; rzeczywisty walidator
  potwierdza 12 obrazów i `2 057 855` bajtów oraz poprawnie zwraca
  `readyForGeometryBenchmark = false`,
- ukończono `TASK-0052`: read-only scanner `image-discovery-v1` tworzy
  deterministyczny manifest ścieżek względnych, SHA-256, rozmiarów, mtime,
  wymiarów, aliasów identycznej treści i stabilnych problemów źródłowych,
- rzeczywisty discovery ma 12 plików, 12 unikalnych obrazów, zero duplikatów
  treści i zero problemów; SHA-256 manifestu to
  `45ac57f91fefa7c75bb8d281bf5936e59ff94c13345279dbc48ef9ae436801d8`,
- ponowny check manifestu przeszedł bez driftu, porównanie z korpusem rozpoznało
  wszystkie 12 checksum jako znane, a kontrola korpusu potwierdziła niezmienione
  oryginały; weryfikacja TASK-0052 zakończyła się `11 passed`, Ruff i mypy,
- ukończono `TASK-0053`: `image-normalization-v1` z Pillow 12.3.0 ponownie
  weryfikuje discovery/SHA-256, stosuje EXIF Orientation 1–8 i zapisuje
  content-addressed RGB PNG oraz diagnostykę bez nadpisywania kolizji,
- syntetyczne golden tests potwierdzają wszystkie osiem orientacji, brak tagu,
  drift, limit pikseli i idempotencję; rzeczywisty korpus dał 12/12 wyników,
  zero problemów i raport SHA-256
  `7521e3dbee351918b0dca058905d640d518a2f0fee4ee9bed3a788c96f910352`,
- 12 roboczych PNG ma łącznie `15 983 691` bajtów, wszystkie są RGB 960 × 1280
  bez Orientation; 24 binarne/diagnostyczne artefakty pozostają lokalne i
  ignorowane przez Git,
- weryfikacja M5.2 zakończyła się `25 passed`, Ruff, mypy i `pip check`; ponowny
  check nie wykazał driftu, a oryginalne checksumy pozostały zgodne,
- ukończono `TASK-0054`: port `PageBoardDetector` i klasyczna implementacja
  `page-board-detector-v1` wykrywają dokładnie dziewięć czerwonych ramek 3 × 3,
  zachowują indeksy row-major i zwracają jawne `needs_review` dla braku,
  nadmiaru albo nieregularnej geometrii,
- rzeczywisty korpus dał 12/12 wyników `detected`, 108 plansz i 9 jawnych
  korekt `refinedFromGrid`; confidence obrazu mieści się w zakresie
  `0.597210–0.747265`, a 12 lokalnych overlayów ma łącznie `15 711 444` bajtów,
- SHA-256 deterministycznego raportu geometrii to
  `2e12e180a8d0f27704e1973f04632937c7a71b113185fa161e2a47b0d22741ca`;
  ponowny `--check --require-detected` nie wykazał driftu,
- 32 testy discovery/normalizacji/geometrii, Ruff, format Ruff, mypy i
  `pip check` przechodzą; wizualna kontrola overlayów potwierdza położenie
  plansz, ale bez niezależnych golden narożników nie deklarujemy accuracy ani
  przejścia G5.3,
- ukończono `TASK-0055`: port `BoardCellCropper` prostuje indywidualnie każdy
  quad do RGB 500 × 300 i po jawnym marginesie dzieli planszę na 15 komórek
  RGB 90 × 90 z indeksami 0-based row-major,
- rzeczywisty korpus dał 12/12 wyników `cropped`, 108 plansz, 108 overlayów
  oraz 1620 komórek; 1836 lokalnych plików ma łącznie `56 325 183` bajty,
- SHA-256 deterministycznego raportu cropów to
  `01756c63ed3f8d6837193908cf0f03c8f4f243a2ead74fa2e9a3b3e5d7a55b4e`;
  retry `--check --require-cropped` nie wykazał driftu,
- 42 testy całego pionu obrazów, Ruff, format Ruff, mypy i `pip check`
  przechodzą; trzy reprezentatywne overlaye sprawdzono wizualnie, ale bez
  niezależnych golden nadal nie deklarujemy accuracy ani przejścia G5.3.
- ukończono `TASK-0056`: wymienny port `SequenceNumberRecognizer`, lokalny
  adapter PaddlePaddle CPU i kontrakt `sequence-number-ocr-v1` zapisują surowy
  crop, wycięty jasny komponent, raw text, normalized number, confidence,
  wersje i checksumy bez pobierania modelu w runtime,
- oficjalny `en_PP-OCRv5_mobile_rec` osiągnął na 108 niezależnie opisanych
  numerach `68/108 = 62.9630%`; `58` pozycji wymaga review, `51` narusza
  ciągłość, a raport ma SHA-256
  `bae6f8129115e45d4085ac75d8990d6ef06691db8847153e71afee69e7247d0b`,
- retry pełnego przebiegu dał identyczny raport i 216 referencjonowanych,
  content-addressed artefaktów; walidacja ciągłości nie nadpisuje raw ani
  normalized, a brak modelu kończy się stabilnym błędem,
- 47 testów całego pionu obrazów, Ruff, mypy i `pip check` przechodzi. Wynik
  62.9630% jest uczciwym baseline'em poniżej proponowanego progu 98%, dlatego
  G5.4 pozostaje niezaliczona i wymaga decyzji po TASK-0057.
- ukończono `TASK-0057`: `m5-image-benchmark-v1` wiąże checksumami wszystkie
  raporty M5, mierzy jakość, trzy próbki czasu, rozmiary referencjonowanych
  artefaktów, condition tags, długości numerów i pełny katalog błędów,
- detekcja strony oraz kompletu dziewięciu plansz wyniosła 100% na 12 zdjęciach;
  accuracy pozycji i P95 narożników mają `not_measurable`, ponieważ brakuje ich
  niezależnych golden annotations,
- baseline OCR zachował `68/108 = 62.9630%`, a kontrola tego samego modelu na
  surowym cropie osiągnęła `46/108 = 42.5926%`; preprocessing pomaga, lecz oba
  wyniki pozostają poniżej proponowanego 98%,
- P95 na pełny korpus wyniósł: discovery `21.1432 ms`, normalizacja
  `1738.6188 ms`, geometria `4016.3138 ms`, cropy `16473.5893 ms`, baseline
  OCR `3874.1724 ms` i kontrola OCR `5240.3376 ms`,
- raport benchmarku ma SHA-256
  `89c2335b64fdf957f9af8cbc65c008cb7706cb7119fd36af7ac8b7c8a8a2f408`;
  rekomendacja to `rework`, a G5 pozostaje niezaliczone,
- weryfikacja TASK-0057 obejmuje 50 testów pionu obrazów, Ruff, mypy,
  `pip check`, pełny pomiar oraz deterministyczny `--check`.
- ukończono `TASK-0058` i zaakceptowano D-056: zachowano lokalny worker,
  checksumy, content-addressed artefakty oraz wersjonowane kontrakty M5,
- discovery/normalizacja mają status `retain`; geometria i cropy
  `experimental` dla jednego wariantu 3 × 3; port/raport OCR `retain`, lecz
  bieżący model z preprocessingiem ma status `rework`,
- pięć błędów OCR z confidence `>= 0.8` blokuje jakikolwiek auto-accept;
  każdy bieżący numer jest wyłącznie sugestią do manual review, continuity go
  nie poprawia, a M4 pozostaje bezpiecznym workflow danych,
- ukończono korektę `TASK-0092`: zaakceptowany korpus v2 zawiera 43 zdjęcia
  w dwóch grupach źródłowych, 387 layoutów i ciągłe numery 1–387,
- Q-016/Q-017 są zamknięte: ostatnia strona może mieć 1–8 pozycji bez luk,
  a właściciel nie wycina obrazów ręcznie; worker utworzył 387 board crops i
  5805 cell crops,
- `page-board-detector-v2` wykrył 43/43 strony i komplet 387 oczekiwanych
  pozycji; wszystkie overlaye golden geometrii przejrzano wizualnie,
- OCR osiągnął `247/387 = 63.8243%`, a na held-out
  `179/279 = 64.1577%`; pozostaje `manual_review_only` i nie może
  samodzielnie zatwierdzić `sequence_number`,
- benchmark `m5-image-benchmark-v2` zakończył się decyzją `enter_m6` i
  statusem `measured_passed_manual_review_only_ocr`,
- zaakceptowano D-057: M5 i TASK-0051 są ukończone, G5 ma status
  `passed_manual_review_only_ocr`, a M6 może korzystać z automatycznych cropów
  i przejrzanych etykiet,
- zaakceptowano D-058 i zaimplementowano kontrakty
  `symbol-crop-inventory-v1`, `reviewed-cell-labels-v1` oraz
  `labeled-symbol-dataset-v1`; inwentarz sprawdził 5805/5805 cropów i ma
  SHA-256 `8c6e0a0459d47df9e685fffc60b91ffa6be4e867aa7f937517af78a17fddb9c6`,
- ukończono korekcyjne `TASK-0093`: lokalny serwer bootstrap review działa
  wyłącznie na loopback, bezpiecznie serwuje zweryfikowane cropy i zapisuje
  wznawialny `reviewed-cell-labels-v1`,
- interfejs review pokazuje postęp i filtry, obsługuje accepted/rejected,
  cofnięcie, pomijanie, skróty oraz deduplikację identycznych cropów; browser
  smoke potwierdził zapis i wznowienie na rzeczywistym inwentarzu 5805 próbek,
- testy TASK-0093 obejmują 22 przypadki dataset/review/HTTP; Ruff, mypy i
  formatowanie zmienionego zakresu przechodzą,
- pierwsza rzeczywista sesja etykietowania ujawniła, że linie
  `board-cell-crops-v1` przecinają symbole; inspekcja potwierdziła globalny
  inset 25/15 px i krok 90 px zamiast logicznych slotów 100 × 100,
- zaakceptowano D-059: v1 pozostaje historyczne i nie może zasilać treningu;
  M5.3 wraca do niezależnego goldenu, croppera v2 i profili kalibracji, a
  uczenie będzie batchowe z pełnolayoutowym review.
- ukończono `TASK-0094`: właściciel ręcznie skorygował i zaakceptował 27/27
  źródłowych quadów plansz; wszystkie wpisy mają `human-adjusted`, potwierdzony
  wpływ v1 i brak wpisów oczekujących,
- finalny `cell-grid-golden-v1` ma SHA-256
  `a25b1753f8d3c74e13827c6803b82921e36e68f9c3eb3d1bccae88ce6d96c533`;
  obejmuje po trzy plansze dla każdej z dziewięciu pozycji i obie grupy
  źródłowe,
- deterministyczny raport bazowy v1 wygenerowano dwukrotnie z identycznym
  SHA-256
  `a62532ba30d90a861c374f63f7f9d7406f7b9d50d13313760336d09ecb8df9d5`;
  odrzuca v1 z P95 błędu linii `47.0748 px`, 27 dotkniętymi planszami i 395
  obserwacjami komórek, więc dane v1 nadal nie mogą zasilać treningu.
- ukończono `TASK-0095`: cropper v2 zachowuje planszę RGB `500 × 300`, dzieli
  ją na piętnaście logicznych slotów `100 × 100` i stosuje lokalny inset `5 px`,
  tworząc deterministyczne wycinki RGB `90 × 90`,
- pełny korpus v2 zawiera 43 obrazy, 387 plansz i 5805 komórek; osobna
  przestrzeń `board-cell-crops-v2` nie zmieniła historycznego v1, które nadal
  ma 6579 plików i 196994964 bajty,
- raport generacji v2 jest stabilny pod SHA-256
  `d7d55fccd35e2760ae269cc4c7a25b5afc8271cbb640f1e940ef79af2ae486cc`,
  a niezależny raport jakości pod SHA-256
  `d66b129c759abe140979d48f85a93804c33a37ff07050301d7259721bbd43e8d`,
- pomiar 27 zaakceptowanych plansz i 405 artefaktów dał P50 linii
  `20.5613 px`, P95 `42.1563 px` i maksimum `91.88 px`; wynik pozostaje
  `quarantined_calibration_required`, `trainingAllowed = false` i wskazuje
  TASK-0096, ponieważ nie spełnia budżetu P95 `5 px`,
- TASK-0095 przeszedł Ruff, mypy dla 141 plików, 283 testy workera, walidację
  obu JSON Schema oraz powtórny deterministyczny przebieg.
- ukończono `TASK-0096`: opublikowano dokładnie 18 profili kalibracji dla obu
  grup źródłowych i pozycji 0–8; wszystkie 27 zaakceptowanych quadów jest
  niezmiennymi anchorami interpolowanymi po domenowym `sequence_number`,
- osobny `board-cell-crops-v2-calibrated-v1` zawiera 43 obrazy, 387 plansz,
  5805 komórek i zero wyników wymagających review; każdy board zapisuje profil,
  jego wersję, sekwencje anchorów i wagę interpolacji,
- niezależna bramka 27 plansz i 405 komórek przeszła z P95 linii `1.8337 px`
  wobec budżetu `5 px` oraz `trainingAllowed = true`,
- deterministyczne SHA-256 wynoszą:
  `6928c0cb6909c9106d9f4e1a9bd153500eec56f0b96be3d7f8b6cc2a06ec6242`
  dla profili,
  `cefe1a54ea912cac6d8a7cc9dff74d432c3cd56898b91e6213abff5af3a4787b`
  dla cropów i
  `8e53f463a42897265bc36cd82b56c72dbd6f05fd128e18de7fc066e09f0470eb`
  dla jakości,
- v1 zachował 6579 plików i 196994964 bajty, a detektorowy v2 zachował raport
  `d66b129c759abe140979d48f85a93804c33a37ff07050301d7259721bbd43e8d`
  oraz P95 `42.1563 px`; oba pozostają historyczne i w kwarantannie,
- TASK-0096 przeszedł 290 testów workera, Ruff, mypy dla 145 plików, trzy JSON
  Schema, pełny deterministyczny przebieg oraz wizualny browser smoke edytora;
  zaakceptowano D-061 i ponownie zaliczono G5.3.
- techniczna część `TASK-0097` tworzy `symbol-crop-inventory-v2` wyłącznie z
  zaakceptowanego `board-cell-crops-v2-calibrated-v1`; inwentarz obejmuje
  387 plansz i 5805 komórek, ma SHA-256
  `5687f80bf74004cdf6bcb7d35633a4916a7326ff1ffdbee4e9a82cf958e32f89`,
- każda komórka ma stabilne `observationId` niezależne od bajtów oraz
  `cropSampleId` zależne od croppera, profilu i checksumy; pełny łańcuch
  korpus → golden → profile → cropy → jakość jest sprawdzany przed review,
- lokalny ekran pokazuje rzeczywistą planszę 500 × 300 i piętnaście cropów,
  zapisuje atomowo częściowe decyzje, wznawia je, filtruje status plansz i
  przechodzi po `sequence_number`; browser smoke potwierdził 15 komórek oraz
  skok do sekwencji 387 bez błędu,
- istniejąca konfiguracja `blazing-hot-7-deluxe` i ośmiu symboli została
  bezpiecznie wznowiona, ale nadal zawiera zero decyzji; żaden symbol nie został
  przypisany automatycznie,
- techniczna część TASK-0097 przeszła deterministyczny `inventory --check`,
  296 testów workera, Ruff, mypy dla 146 plików, Prettier, diff check oraz
  rzeczywisty browser smoke; zadanie pozostaje aktywne wyłącznie na ręczne
  oznaczenie pierwszych 15–30 plansz,
- rozpoczęto TASK-0059 na zaakceptowanym inwentarzu v2: eksporter odrzuca
  objęte kwarantanną v1 i wymaga `trainingAllowed = true`, kompletnej planszy
  5 × 3 oraz skalibrowanego croppera,
- manifest eksportu zachowuje pełne pochodzenie korpusu, adnotacji, cropów,
  profili i raportu jakości oraz identyfikatory `observationId`,
  `cropSampleId` i `boardId`,
- kontrolny eksport ma status `waiting_for_labels`, 5805 pozycji pending,
  zero zaakceptowanych próbek i SHA-256
  `e2545da59e34b0ef0a33080579a9b85b39d40c5f00bd22e21731ca8b7f05f865`;
  nie utworzono fikcyjnych etykiet ani assetów.
- rzeczywiste etykietowanie ujawniło błąd generalizacji profili D-061:
  sekwencje 2 i 3 na pierwszym zdjęciu użyły odległych kotwic sekwencji 74 i
  66, a deklarowany P95 `1.8337 px` został policzony na 27 anchorach użytych do
  kalibracji zamiast na rozłącznych planszach,
- właściciel zapisał 56 jawnych decyzji symboli dla sekwencji 1, 7, 8, 9 i 12;
  plik został zachowany bez zmian i skopiowany do checksumowanej kwarantanny
  przed zmianą geometrii,
- zaakceptowano D-062 i rozpoczęto TASK-0098: lokalna baza każdej ramki będzie
  kalibrowana jedną kotwicą z tego samego zdjęcia, a brak kotwicy nie może
  korzystać z fallbacku innego obrazu,
- diagnostyka pierwszego zdjęcia potwierdziła, że lokalny `boundingBox` plus
  jedna istniejąca korekta zdjęcia zachowuje pełne symbole plansz 1–3; 27 z 43
  obrazów ma już po jednej kotwicy, 16 wymaga review,
- TASK-0098 ma działający `board-cell-crops-v3-local-calibrated-v1`: 27
  zakotwiczonych obrazów wygenerowało 243 plansze i 3645 komórek, a 16
  pozostałych obrazów zachowało jawny status `needs_review`,
- deterministyczna kolejka korekcyjna ma 25 plansz: 16 brakujących kotwic
  obrazu oraz 9 rozłącznych plansz held-out obejmujących pozycje 0–8; edytor
  pokazuje ukośną siatkę, wynik homografii i 15 komórek bez konieczności
  ręcznej korekty wszystkich 387 plansz,
- testy lokalnej kalibracji, istniejących cropów i poprzedniej kalibracji
  przeszły `23 passed`; Ruff i mypy dla zmienionych modułów również przeszły,
- właściciel ukończył kolejkę TASK-0098 `25/25`; 18 plansz nadal miało
  oznaczone przecięcia symboli, łącznie 188 komórek, a problem wystąpił na
  wszystkich 9 planszach held-out,
- TASK-0100 zakończył się akceptacją właściciela: symbol-aware refinement
  obniżył medianę residualu held-out z `6.6964 px` do `2.0441 px`,
- pełny benchmark TASK-0101 wykazał, że geometria startowa musi pochodzić z
  detektora każdej planszy osobno; wariant przenoszący jedną korektę ramy na
  inne pozycje tej samej strony został odrzucony po kontroli wizualnej,
- ścisły wariant detector-per-board wyznaczył `381/387` plansz, a dokładnie
  sześć sekwencji `11`, `33`, `123`, `172`, `266`, `337` skierował do
  fail-closed review; właściciel poprawił i zaakceptował wszystkie sześć,
- finalny namespace
  `board-cell-crops-v7-reviewed-symbol-aware-affine-v1` zawiera 43/43 strony,
  387 plansz i 5805 komórek: 381 wyników automatycznych, 6 jawnych ręcznych
  override i 0 stron `needs_review`; raport ma SHA-256
  `0950ac493af010d198cace691f78f3aa454100acaff246845a2fca2c5f8d0a55`,
- deterministyczny rerun odtworzył ten sam raport; schema, Ruff, mypy i 28
  właściwych testów workera przeszły, ale właściciel odrzucił końcową galerię:
  wskazał 92 unikalne złe sekwencje na 36 obrazach i dodatkowe lżejsze
  przecięcia; v7 pozostaje w kwarantannie z `trainingAllowed = false`,
- sekwencja 316 potwierdziła błąd założenia: pełny detector `boundingBox`
  zawiera symbole, lecz quad z ekstremów czerwonej maski zwęża planszę, a
  per-slot refiner dopasowuje już ucięte fragmenty. Kolejna korekta ma użyć
  pełnej lokalnej ramki oraz siatki lokalnych środków/per-cell crops, nie
  następnej wspólnej transformacji afinicznej,
- spike `local-symbol-mesh-spike-v1` zbudował lokalne, lekko nakładające się
  komórki dla 92 jawnie odrzuconych sekwencji, ale właściciel zgłosił dalsze
  słabe przypadki i nie zaakceptował tego wariantu,
- diagnostyczne szerokie wycinki z rozszerzonej ramki zachowały symbole, lecz
  wpuszczały fragmenty sąsiednich komórek, dlatego nie mogą zasilać treningu,
- `expanded-frame-centered-symbol-mesh-spike-v4` używa rozszerzonej lokalnej
  ramki, stałego kontekstu wokół środka i wyznacza pierwszy rząd z dwóch
  stabilniejszych dolnych rzędów,
- preflight odrzuconych przypadków przeszedł automatycznie dla `91/92`, a
  pełny preflight dla `385/387`; sekwencje `192` i `235` zatrzymały się
  fail-closed z powodu niewiarygodnej skrajnej kolumny,
- raport pełnego preflightu ma SHA-256
  `6d91b5bec672794c89929d3fb9509ce395c4eb9e88adb3b91dd623d101edc8be`;
  drugi przebieg odtworzył identyczny raport, 17 testów, Ruff, mypy i diff
  check przechodzą; inżynierski przegląd próbek jest pozytywny, lecz pełna
  bramka właściciela nadal czeka i `trainingAllowed = false`,
- właściciel przerwał dalszy przegląd v4 po sekwencji 30 i wskazał 16 błędnych
  layoutów: `4`, `6`, `7`, `8`, `9`, `10`, `12`, `15`, `18`, `21`, `22`,
  `24`, `26`, `27`, `29`, `30`; lista komórek jest zapisana w
  `m5-v4-owner-visual-feedback-round1.json`,
- follow-up v5–v8 potwierdził, że samo poszerzanie cropu wymienia ucięcie na
  wyciek sąsiedniego symbolu albo elementu interfejsu; w sekwencji 4 strzałka
  nawigacyjna styka się z symbolem skrajnej kolumny,
- wycinek zawierający około 30% symbolu nie jest dopuszczalny do treningu ani
  auto-accept; potrzebna jest bramka jakości per komórka i kwarantanna
  clipped/occluded/interface-contaminated zamiast dalszego ręcznego oglądania
  wszystkich 5805 cropów.

## Recent M5/M6 execution history

- aktywny TASK-0101 ma odrzucone v4 oraz eksperymentalne v5–v8; następnym
  pionem jest automatyczna jakość per komórka, która dopuści wyłącznie pełne
  symbole i ograniczy ręczne review do kwarantanny,
- kalibracja pierwszej bramki pikselowej na dokładnych cropach v4 wykryła
  `41/55` jawnie wskazanych błędnych komórek, ale przepuściła 14; dodatkowo
  odrzuciła `82/185` komórek niewskazanych w tych samych layoutach, dlatego
  sama regulacja progów nie jest bezpiecznym rozwiązaniem produkcyjnym,
- kandydat `expanded-wide-frame-bright-lattice-symbol-mesh-spike-v9`
  wyznacza pięć kolumn wspólnie z kompaktowych jasnych komponentów całej
  planszy zamiast ufać pięciu niezależnym slotom; bez fallbacku przetworzył
  16 problematycznych i 14 kontrolnych layoutów round 1,
- bootstrapowa bramka
  `cell-crop-quality-gate-v2-inner-columns-bootstrap` zawsze kwarantannuje
  kolumny skrajne z powodu sąsiednich kontrolek interfejsu, a niezależną
  analizę pikselową stosuje do kolumn 2–4; w dwóch małych zestawach dopuściła
  odpowiednio `108/240` i `99/210` komórek,
- właściciel odrzucił v9 na sekwencji 29: detektor zachował nachylony quad,
  lecz v10 zamieniło go na osiowy rozszerzony bounding box, a mesh syntetycznie
  wyliczył pierwszy rząd; problem jest strukturalny i nie będzie naprawiany
  dalszym strojeniem progów,
- zaakceptowany plan korekty ma trzy kroki: projektowe rozszerzenie quadu
  detektora, homografię RANSAC dopasowaną do globalnej siatki 15 symboli oraz
  fixed-padding gate na `29`, `4`, `6`, `7`, `26`, `30` i kontrolach,
- krok 1 jest zaimplementowany jako
  `expanded-detector-projective-quad-v1` /
  `board-cell-crops-v11-projective-frame-preflight-v1`; sekwencja 29 zachowuje
  nachylenie i rozszerza quad detektora z
  `[(402,336),(652,328),(645,448),(410,430)]` do
  `[(386,329),(679,317),(669,459),(396,436)]`,
- diagnostyka kroku 1 ma SHA-256
  `e7ce5f70f86fc159d65c38df4f833e60741a87997e946bf9c81d5cfbfd72d2b1`;
  10 testów, Ruff, mypy i diff check przechodzą, a widoczna na niej
  prowizoryczna siatka logiczna została zastąpiona w kroku 2,
- krok 2 jest zaimplementowany jako niezależny
  `symbol-lattice-homography-ransac-v1`; dopasowuje jedną projektową
  homografię do całego zbioru wiarygodnych środków, wymaga co najmniej
  10 kandydatów, 9 inlierów, pokrycia 3 × 5, P95 najwyżej `10 px` oraz
  wypukłej, ograniczonej i prawdopodobnie rozstawionej wirtualnej siatki,
- sekwencja 29 ma `14/15` wiarygodnych kandydatów i 13 inlierów obejmujących
  wszystkie rzędy i kolumny; P95 wynosi `7.6869 px`, a błędny środek pierwszego
  rzędu nie steruje czterema wirtualnymi narożnikami,
- deterministyczna diagnostyka kroku 2 ma SHA-256
  `4e4d1f56f13e24458bca6e86c4a05810d30e39c242bc2543c8b196acc76585d4`;
  jej raport odtwarza się byte-for-byte, 4 nowe testy pokrywają realną regresję,
  uszkodzone narożniki oraz fail-closed coverage i granice,
- krok 2 nie prostuje ani nie publikuje komórek; dolny lewy wirtualny narożnik
  sekwencji 29 wykracza o około `10.7 px` poza diagnostyczną ramkę, dlatego
  krok 3 musiał dowieść, że stały padding korzysta wyłącznie z dostępnych pikseli,
- krok 3 powstał jako nieprodukcyjny
  `board-cell-crops-v12-projective-lattice-fixed-padding-preflight-v1`;
  rectyfikuje przez homografię, stosuje stały inset `10 px` w kanonicznej
  komórce i wymaga support fraction `1.0` bez replikacji obramowania,
- sekwencja 29 została uruchomiona osobno jako pierwsza i przeszła dla 15/15
  komórek; raport ma SHA-256
  `3593ffabd587db86c58a251f3bbf0567a6149a86c746f22ac04e82a3c173a579`,
- dopiero potem uruchomiono `4`, `6`, `7`, `26`, `30` oraz 14 kontroli;
  technicznie powstały cropy dla `13/20`, a fail-closed zatrzymał sekwencje
  `7`, `30`, `3`, `11`, `16`, `17`, `28`,
- raport ograniczonej regresji ma SHA-256
  `57fc69a64a4223fe5815978a1c803024217a96c2879f68fe3b69d9545d56b378`;
  `--check` odtworzył bajty, a `--require-pass` poprawnie zwrócił kod `1`,
- inżynierska kontrola kart odrzuca również technicznie przepuszczone `4`
  i `26`, ponieważ symbole pierwszej kolumny nadal są przecięte; support mask
  dowodzi obecności pikseli, ale nie poprawności środka symbolu,
- bramka v12 ujawniła, że obecny lokalizator nadal proponuje środki
  per przybliżony slot i może spójnie wybrać ramę albo fragment w całej
  kolumnie; homografia nie naprawia błędnego przypisania wejściowych punktów,
- korekta v13 dodaje
  `global-bright-component-lattice-assignment-v1`: komponenty powstają na
  całej planszy, pięć baz kolumn i trzy bazy rzędów są ustalane wspólnie,
  a dopiero potem najwyżej jeden kandydat jest przypisywany do slotu 5 × 3;
  brak globalnego wsparcia obniża confidence i nie pozwala lokalnej czerwonej
  ramce sterować homografią,
- homografia
  `symbol-lattice-homography-ransac-v2-global-assignment-v1` zachowuje progi
  liczby punktów, inlierów, coverage i residualu; rozszerzony guard dotyczy
  wyłącznie sztucznej płaszczyzny analizy, ponieważ finalne komórki są
  projektowane i weryfikowane na prawdziwym obrazie źródłowym,
- cropper
  `board-cell-crops-v13-global-lattice-source-aware-fixed-padding-preflight-v1`
  składa transform `ideal -> analysis -> normalized source`, stosuje niezmienny
  inset `10 px` i wymaga `1.0` support fraction z realnego źródła bez
  border replication,
- sekwencja 29 przeszła osobną bramkę `15/15`; deterministyczny raport ma
  SHA-256
  `22ac9ab8d31a355e4b5b36f39c2b33f777a5efe258e1c042ed77b5273ce17ea1`,
- ograniczona regresja v13 utworzyła w pełni wspierane cropy dla `18/20`;
  wszystkie zgłoszone `4`, `6`, `7`, `26`, `30` przeszły i ich karty zostały
  sprawdzone inżyniersko, natomiast kontrole `3` i `11` pozostały fail-closed
  odpowiednio z `GLOBAL_SYMBOL_LATTICE_AXIS_ASSIGNMENT_FAILED` oraz
  `GLOBAL_SYMBOL_LATTICE_INSUFFICIENT_ASSIGNMENTS`,
- raport v13 ma SHA-256
  `210b8d93c254be6c14d7bafcf7869ee1806f51ec92cabc7c11f66234ac2540f7`;
  oba raporty v13 odtwarzają się byte-for-byte, a historyczne raporty v12
  zachowały oryginalne checksumy,
- szerszy drugi wycinek analityczny nie odzyskał bezpiecznie `3` ani `11`;
  dlatego v13 pozostaje niezmiennym dowodem `18/20`,
- v14 dodaje bounding-box analysis fallback z paddingiem `6% × 4%`, ale
  wyłącznie po trzech błędach globalnego locatora; prostokąt służy tylko do
  ponownego znalezienia symboli, a nie jako finalna geometria komórek,
- kontrola `3` po fallbacku ma 12 inlierów i P95 `4.3133 px`, kontrola `11`
  ma 12 inlierów i P95 `4.3328 px`; obie tworzą 15 komórek z support fraction
  `1.0`,
- ograniczona bramka v14 przechodzi technicznie `20/20`; tylko `3` i `11`
  użyły fallbacku, a pozostałe 18 kart ma dokładnie te same checksumy co v13,
- raport seq29 v14 ma SHA-256
  `545b81c00224aa59f263c17da6ff633ad59e2381048592f875f87a587ba29682`,
  raport bounded v14 ma SHA-256
  `13dfac7e47a200f3a7aec237f4b71ed0032d0a3e969698e6e68239fb20baf1cb`;
  oba przechodzą `--check --require-pass`,
- właściciel zaakceptował ograniczoną galerię v14 2026-07-29; część cropów jest
  lekko przycięta, ale wszystkie ocenione symbole pozostały czytelne,
- pełny preflight v14 sprawdził 43 zdjęcia i 387 plansz w `5 min 13 s`;
  `373/387` plansz utworzyło `5595/5805` niezmiennych komórek z support
  fraction `1.0`, a 14 plansz pozostało fail-closed,
- odrzucone sekwencje to `33`, `38`, `123`, `163`, `203`, `237`, `254`, `255`,
  `325`, `333`, `334`, `335`, `346`, `379`; nie obniżono progów i nie
  wprowadzono syntetycznych pikseli,
- pełny raport v14 ma SHA-256
  `026e12ac32802c1561552b338ddb80df51a00088a7e6c1cd57b2652a756d97a5`
  i status `failed`; pełny korpus, publikacja oraz trening pozostają
  zablokowane, a `trainingAllowed = false`,
- właściciel przejrzał pierwsze kilkadziesiąt poprawnie poprowadzonych kart
  pełnego preflightu i ocenił je jako poprawne; nie jest to jeszcze odbiór
  wszystkich 373 plansz,
- diagnostyka v3 grupuje 14 odrzuconych sekwencji i 22 unikalne sąsiednie
  kontrole w 36 kartach; raport o SHA-256
  `2aeb17991e7b7fc207de097db4d893e69a093ccfc759b1ec25eb251c1526f256`
  odtwarza się byte-for-byte,
- właściciel zaakceptował `14/14` exact-observation quadów dla fallbacków v14,
- pierwszy pełny v15 został odrzucony, ponieważ kontrola reprodukowalności
  wykryła immutable collision na automatycznej sekwencji `49`; nie jest
  źródłem danych i jego wygenerowane artefakty zostały usunięte,
- v16 weryfikuje i zachowuje bajtowo 373 zaakceptowane plansze v14, a
  materializuje ponownie tylko 14 zaakceptowanych ręcznych quadów,
- pełny v16 ma 43 obrazy, `387/387` plansz, `5805/5805` komórek, support
  fraction `1.0`, 14 manual overrides i zero fallbacków,
- natychmiastowy `--check --require-pass` odtworzył każdy artefakt oraz raport
  v16 o SHA-256
  `c336a872388d35a4bb28a15626565906cd105345577919f0c6a3b251841ac5b9`,
- TASK-0099 jest zarezerwowane na bezpieczne top-3 sugestie po zaakceptowaniu
  nowej geometrii,
- TASK-0059 i TASK-0097 zachowują historyczną implementację v2, ale dalsze
  decyzje i eksport zostały przepięte na osobny inwentarz v3,
- właściciel zaakceptował kompletny v16 i zezwolił na przejście dalej;
  `m5-reviewed-manual-merge-v16-owner-acceptance.json` wiąże decyzję z dokładnym
  raportem SHA-256
  `c336a872388d35a4bb28a15626565906cd105345577919f0c6a3b251841ac5b9`,
- TASK-0101 jest zakończony; `symbol-crop-inventory-v3` zweryfikował 43 obrazy,
  387 plansz i 5805 komórek, ma SHA-256
  `55a10739391843f0bc7b17814a209a3fca69ba93ff7fc4a68702008a521d77c1`,
- TASK-0097 został wznowiony na osobnym stanie `m6-symbol-review-v16`: zachowuje
  osiem symboli i startuje z zerem decyzji; historyczny plik v2 z 56 decyzjami
  pozostał niezmieniony, SHA-256
  `55b8edecb0dc90da6b49d181f9ecaa91b9c5abc96131352fd384fa79f9d9a10c`,
- kontrolny eksport v3 ma status `waiting_for_labels`, 5805 pozycji pending i
  zero zaakceptowanych próbek; nie uruchomiono treningu.
- właściciel oznaczył 416 komórek na v16: 24 plansze są kompletne, materiał
  obejmuje 18 zdjęć źródłowych, oba source sessions i wszystkie osiem symboli;
  cztery dodatkowe plansze zachowują wznawialny stan 14/15,
- TASK-0097 jest ukończony; serwer review zatrzymano po zamrożeniu źródła
  decyzji o SHA-256
  `2be1a4171aeee7bc75165c6f993b3aeb3cb3155163ac60f36e1a4a0a2047a61c`,
- TASK-0059 jest ukończony; rzeczywisty eksport ma status `ready`, 416 próbek,
  416 content-addressed assetów, 5389 pozycji pending, zero odrzuconych i
  SHA-256
  `ed1f9e327fd808da592eafd8be3fcbf88add59d2cfd576fb06cabfb71ad2201a`,
- drugi przebieg eksportu z `--check --require-samples` przeszedł byte-for-byte;
  trening nie został jeszcze uruchomiony.
- ukończono TASK-0060: deterministyczny source-aware split ma `269/74/73`
  próbek z `10/4/4` zdjęć dla train/validation/test, wszystkie osiem symboli
  występuje w każdym zbiorze, a przeciek źródeł i assetów wynosi zero,
- raport `m6-symbol-dataset-split-report.json` ma SHA-256
  `214bb9eeddfc996e47a9582c0e582a098b865aff430d14102e28e0c4e5ab2ec0`
  i odtwarza się byte-for-byte; wszystkie symbole pozostają poniżej
  orientacyjnego celu 100 próbek, więc pierwszy model ma charakter bootstrapowy.
- ukończono TASK-0061: deterministyczny `small-symbol-cnn-v1` ma 24 104
  parametry, używa PyTorch `2.12.1` CPU, wybrał epokę 22 wyłącznie po validation
  i odtworzył logiczny checkpoint w drugim pełnym przebiegu,
- validation accuracy/macro-recall wynosi `59.4595% / 61.4469%`, a test
  `63.0137% / 62.7128%`; `star`, `watermelon` i `plum` pozostają słabe, dlatego
  model ma status `bootstrap` i nie zezwala na auto-accept,
- raport `m6-symbol-classifier-baseline-report.json` ma SHA-256
  `9098dcbcad4698a9f95910e09f19d05fae9edcad4957a15c56fef9e0efaa4e55`,
  a logiczny checksum stanu to
  `0edab6bbb738d908c4e902a347c982407549c159829c80fc3010c314a6c1aea2`.
- ukończono TASK-0099: loopbackowy whole-layout review pokazuje do trzech
  jawnych sugestii z dystansem cosinusowym i confidence klasyfikatora, osobno
  pokazuje historyczną etykietę po `observationId` oraz nigdy nie zapisuje
  decyzji bez kliknięcia albo skrótu właściciela,
- indeks referencyjny jest zamrożony na 269 zaakceptowanych próbkach train;
  self-match i całe to samo zdjęcie źródłowe są zawsze wykluczane, a próg
  `0,9975` daje `no_suggestion` dla słabszego dopasowania,
- source-disjoint validation ma coverage `75.6757%`, top-1 accuracy przy tym
  coverage `76.7857%`, top-3 `94.6429%` i zero source leakage; raport
  `m6-symbol-suggestion-validation-report.json` ma SHA-256
  `7bd77eeade0a5fd68d74c0394520aa2063ab6c2d6f21d7944cb52374eb6b290e`.
- ukończono TASK-0062: aktualny eksporter `torch.export` utworzył lokalny ONNX
  opset 18 o rozmiarze `115133` bajtów i SHA-256
  `e03f66f2ab092b6049920fee6fb2839900a95eb94af42fbd5ef7e35c473b5fb8`,
- adapter wymusza `CPUExecutionProvider`, weryfikuje checksumę oraz kontrakt
  `N × 3 × 64 × 64 -> N × 8`; inferencja nie korzysta z sieci,
- parytet wszystkich 416 train/validation/test ma zero zmian top-1, maksymalny
  błąd logits `2.861e-6` i prawdopodobieństw `4.172e-7` przy tolerancji `1e-5`;
  drugi eksport i `--check` odtworzyły artefakt oraz raport o SHA-256
  `6f4596ae8ae938b7e9e89dac05e1a888ac4e53fe1d780dcc9325abfac33ad98c`.
- ukończono TASK-0063: deterministyczna temperatura `1.0338382913` została
  dopasowana wyłącznie na 74 próbkach validation; test 73 próbek zmierzono
  dopiero po zamrożeniu parametru, bez zmiany top-1,
- validation NLL zmalał z `0.94285158` do `0.94251763`, a test NLL z
  `0.87164029` do `0.87065020`; ECE nie poprawił się, co pozostaje jawnym
  dowodem, że skalowanie temperatury nie rozwiązuje słabości modelu,
- najlepszy obserwowany próg validation `0.89329293` miał precision `1.0`,
  lecz tylko 9 próbek i nie spełnił bramki minimum 20 oraz pokrycia klas;
  status bootstrapowy i nieosiągnięty cel danych również blokują auto-accept,
  a auto-reject jest wyłączony,
- zweryfikowano checksumy wszystkich 5389 pending cropów; 359 plansz miało
  pełne 15/15 pending komórek, 4 częściowe plansze wyłączono z selekcji,
- `whole-layout-active-learning-v1` wybrał 30 plansz z 30 różnych zdjęć;
  raport kalibracji ma SHA-256
  `a2359efed1e2dc2d73fc383d9e260c88f4a19838a74af3dd165362692601bff7`,
  a raport selekcji
  `2ab9a79a6d1c81b8d08abe0defc447510f0cfe4df1909c9aa8da77d79e6115d2`,
- drugi pełny przebieg `--check` odtworzył oba raporty bajtowo; G6.2 zaliczono
  z polityką manual-review-only.

## In progress

- brak aktywnego zadania; następny jest TASK-0064.

## Blocked

- `TASK-0039 — Release failure and immutability integration tests`: automatyczna
  macierz awarii/retry, fizyczny PostgreSQL i niezmienność są gotowe. Rzeczywisty
  workflow utworzył gotowe wydanie `m3.4.3`; prywatnie podpisany APK arm64 nie
  deklaruje `INTERNET` i zawiera dokładny snapshot. Aktualizacja na Samsungu i
  ręczne scenariusze funkcjonalne przeszły; pozostaje sformalizowanie dowodu
  wersji/checksumy i raportu release wymaganego przez TASK-0042.
- `TASK-0041 — SQLite, mobile and worker performance benchmark`: zweryfikowane
  APK `m35-benchmark.1 (4)` jest gotowe, ale ADB nie widzi telefonu; brakuje
  fizycznych raportów z Pixela i Samsunga.
- `TASK-0042 — Benchmark decision and release pipeline acceptance`: raport
  `m35-acceptance-report.json` przechodzi dataset, SQLite, worker i kontrolę
  zależności, ale ma status `blocked`, pięć grup brakujących dowodów oraz
  decyzję `pending_device_evidence`. Ponowna ocena 2026-07-28 po zbudowaniu
  benchmarkowego APK zachowała cztery kontrole `passed`, pięć `missing`, a
  `--require-pass` poprawnie zwróciło kod `1`. Nie ma podstaw do zmiany adaptera
  ani do zaliczenia G3.

## Open questions

- Q-019: jeden czy wielu administratorów,
- Q-020: zakres dozwolonej analizy aplikacji referencyjnej,
- finalne modele OCR/ML po benchmarku,
- ostateczna nazwa sekcji `Result` albo `Target`.

Q-019, Q-020, finalny model OCR/ML i nazwa sekcji nie blokują TASK-0097.

## M1 execution structure

Obowiązuje
`delivery/MILESTONE_01_EXECUTION_PLAN.md`:

1. M1.1 — fundament i offline SQLite spike,
2. M1.2 — kontrakty oraz algorytmy,
3. M1.3 — generator, snapshot i repozytorium,
4. M1.4 — UI matching,
5. M1.5 — Target i tabela,
6. M1.6 — release APK i testy urządzeń.

Każdy podetap musi przejść własną bramkę przed rozpoczęciem następnego.

## M2–M8 execution structure

Obowiązują osobne plany:

- `delivery/MILESTONE_02_EXECUTION_PLAN.md`,
- `delivery/MILESTONE_03_EXECUTION_PLAN.md`,
- `delivery/MILESTONE_04_EXECUTION_PLAN.md`,
- `delivery/MILESTONE_05_EXECUTION_PLAN.md`,
- `delivery/MILESTONE_06_EXECUTION_PLAN.md`,
- `delivery/MILESTONE_07_EXECUTION_PLAN.md`,
- `delivery/MILESTONE_08_EXECUTION_PLAN.md`.

Plan zachowuje kolejność roadmapy:

1. M2 — konfiguracja administracyjna,
2. M3 — wersjonowany pipeline wydań mobile,
3. M4 — ręczny import danych,
4. M5 — prototyp image ingestion,
5. M6 — klasyfikator symboli i manual review,
6. M7 — masowy wznawialny import zdjęć,
7. M8 — prywatna dystrybucja i hardening.

Rezerwacja numeru zadania nie tworzy aktywnego tasku. Następny plik powstaje
zawsze bezpośrednio przed rozpoczęciem danego zakresu.

## Next recommended task

Rozpocząć TASK-0064: dodać trwałe `review_item` i Admin API dla pełnego
manual-review flow, korzystając z niezmiennego raportu selekcji TASK-0063.
Predykcja, confidence i alternatywy pozostają dowodem pomocniczym, a nie
decyzją. Równolegle
TASK-0041/TASK-0042 oraz G3 pozostają zablokowane na fizycznych raportach
Pixela i Samsunga.

## Do not start yet

- masowego przetwarzania zdjęć,
- etykietowania symboli i treningu na `board-cell-crops-v1` albo
  detektorowym `board-cell-crops-v2` lub wycofanym
  `board-cell-crops-v2-calibrated-v1`,
- finalnego wyboru OCR/ML,
- Celery/Redis, mikroserwisów i chmury,
- synchronizacji danych mobilnych,
- publicznego deploymentu lub publikacji w Google Play.

## Handoff notes

Dokumentacja opisuje zaakceptowany model produktu i architektury. M1 nie ma
pytania produktowego blokującego dalszą implementację. Toolchain M1.1 jest
opisany w D-013 i `TECH_STACK.md`.

Kolejność, granice i bramki M2–M8 są zapisane w D-014 oraz osobnym planie
wykonania każdego milestone’u, dzięki czemu przyszłe sesje czytają tylko
właściwy etap i nie muszą odtwarzać podziału z historii rozmowy.

Techniczna część pipeline’u M1.6 przeszła: prywatnie podpisany APK `0.1.2 (3)`
z payout-v2 zawiera standalone bundle oraz SQLite `m1-fixture.2` o checksumie
zgodnej z manifestem i nie deklaruje uprawnienia `INTERNET`. Aktualizacja
in-place na Galaxy S21 Ultra oraz instalacja w ścisłym trybie offline na Pixel
10 Pro XL przeszły. Pełne scenariusze domenowe zostały następnie zaliczone
offline na obu urządzeniach. Właściciel zaakceptował M1; kontrolowana
aktualizacja do zmienionego snapshotu i dokładne pomiary są jawnym zakresem
M3.4–M3.5 zgodnie z D-020.

Benchmark M1 dla 1000 layoutów znajduje się w
`ai_docs/quality/m1-repository-benchmark.json`. Benchmark 500 000 layoutów na
Androidzie pozostaje bramką M3 przed uznaniem rozwiązania SQLite/TypeScript za
wystarczające dla docelowej skali.
