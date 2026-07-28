---
title: Current project state
status: active
last_updated: 2026-07-28
---

# Current State

## Phase

`M5.2 discovery and EXIF normalization completed under D-051/D-052; M5.1 and G3 remain open`

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
  check nie wykazał driftu, a oryginalne checksumy pozostały zgodne.

## In progress

- `TASK-0051 — Representative image corpus and golden annotations`: rozpoczęto
  inwentaryzację korpusu i dialog na podstawie D-049; Q-015 jest zamknięte,
  a Q-016/Q-017, pełne adnotacje geometrii i akceptacja progów pozostają otwarte,
- 12 istniejących zdjęć jest materiałem prototypowym według D-050, a nie pełnym
  reprezentatywnym korpusem 20–100 zdjęć ani zaliczoną bramką G5.1.

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

## Open but not blocking next milestones

- Q-016–Q-017: stabilność ekranu i dostępność etykiet treningowych,
- Q-019: jeden czy wielu administratorów,
- Q-020: zakres dozwolonej analizy aplikacji referencyjnej,
- finalne modele OCR/ML po benchmarku,
- ostateczna nazwa sekcji `Result` albo `Target`.

Żaden z tych punktów nie zmienia zakresu planszy 3 × 5 ani mock danych M1.

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

Przed TASK-0054 odpowiedzieć na Q-016 o stabilności układu strony między grami
i ekranami; ta odpowiedź określa, czy geometria może zakładać jedną siatkę
3 × 3. Następnie TASK-0054 wymaga kolejnego jawnego polecenia i nie oznacza
zaliczenia G5.1. Równolegle TASK-0041/TASK-0042 oraz G3 pozostają zablokowane na
fizycznych raportach Pixela i Samsunga.

## Do not start yet

- masowego przetwarzania zdjęć,
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
