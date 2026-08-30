---
title: Architecture decision log
status: active
last_updated: 2026-08-24
---

# Decision Log

Statusy: `proposed`, `accepted`, `rejected`, `superseded`.

## D-001 — Monorepo

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** jeden repository z `apps/mobile`, `apps/admin`, `services/api`, `services/worker`, `packages` i `ai_docs`.
- **Reason:** prostsze kontrakty, jedna dokumentacja i łatwiejsza praca Codex.
- **Consequences:** różne narzędzia JS/Python muszą mieć jasne komendy root-level.

## D-002 — Mobile technology

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** React Native + Expo + TypeScript.
- **Reason:** wykorzystanie doświadczenia React, szybki Android development, prosty routing.
- **Alternatives:** natywny Kotlin, Flutter, PWA.
- **Consequences:** aplikacja jest instalowana jako samodzielny APK z osadzonym
  datasetem offline; TypeScript działa w trybie `strict`, a typecheck jest
  obowiązkową kontrolą jakości.

## D-003 — Admin technology

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** Next.js jako lokalna aplikacja webowa.
- **Reason:** znajoma technologia i brak potrzeby utrzymywania aplikacji desktopowej.
- **Alternatives:** Electron/Tauri, panel w FastAPI templates.
- **Consequences:** panel działa lokalnie na Windows jako proces Node.js i
  komunikuje się wyłącznie z lokalnym backendem administracyjnym; nie wymaga
  chmury ani publicznego hostingu.

## D-004 — Backend

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** lokalny backend administracyjny w Pythonie i FastAPI, z logiką
  domenową oddzieloną od endpointów.
- **Reason:** Python dla obrazu, OpenAPI dla TypeScript, prosta testowalność.
- **Consequences:** backend nasłuchuje lokalnie i obsługuje panel admina,
  przygotowanie datasetów oraz sterowanie workerem; aplikacja mobilna nie łączy
  się z API.

## D-005 — Canonical database

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** PostgreSQL jako kanoniczne źródło prawdy panelu
  administracyjnego; SQLite jako niezmienny snapshot dołączany do wydania
  aplikacji mobilnej.
- **Reason:** skala, indeksy, równoległy admin/worker, staging i publikacja.
- **Alternatives:** SQLite only, embedded database, document database.
- **Consequences:** mobile nie łączy się z PostgreSQL ani API. Publikacja
  zatwierdzonego datasetu generuje SQLite wraz z payoutami, po czym tworzony
  jest nowy APK. PostgreSQL działa lokalnie na Windows przez Docker Compose.

## D-006 — Image jobs

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** osobny lokalny Python worker/CLI i trwałe rekordy zadań w
  PostgreSQL; bez Celery/Redis.
- **Reason:** długie zadania nie mogą blokować requestów, ale na starcie nie potrzebujemy rozproszonej kolejki.
- **Consequences:** import, walidacja, obliczanie payoutów, generowanie SQLite i
  budowanie APK działają poza procesem FastAPI, zapisują postęp małymi partiami
  oraz mogą zostać anulowane i wznowione. Początkowo wykonywane jest jedno
  ciężkie zadanie naraz.

## D-007 — Layout representation

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** jeden rekord na layout, zwarta tablica `cells` oraz
  deterministyczna sygnatura o jednoznacznej, stałej szerokości; bez osobnego
  rekordu na każdą komórkę.
- **Reason:** ograniczenie liczby wierszy przy milionach layoutów.
- **Consequences:** symbole otrzymują małe stabilne kody w ramach gry, a
  sygnatura zapisuje je w kolejności `row-major`. PostgreSQL może przechowywać
  dodatkowo `cells` jako tablicę małych liczb; snapshot SQLite zawiera tylko
  dane potrzebne mobile, w tym sygnaturę i precomputed payout.
- **Validation needed:** benchmark exact i prefix matching na 500 000 layoutów
  oraz pomiar rozmiaru. Pierwsza implementacja preferuje prostą sygnaturę
  stałej szerokości; może zostać zamieniona na BLOB bez zmiany interfejsu
  repozytorium, jeżeli pomiary to uzasadnią.

## D-008 — Duplicate layouts

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** sygnatura nie jest unikalna. Przy kilku pasujących numerach
  mobile zwraca stan `duplicate`, nie wybiera pozycji i nie uruchamia forecastu.
  Reset usuwa kontekst, a użytkownik wprowadza kolejny layout jako nowe,
  niezależne wyszukiwanie.
- **Reason:** duplikaty zawartości występują rzadko, podczas gdy
  `sequence_number` pozostaje unikalny i ciągły. Procedura użytkownika nie
  wymaga odtwarzania pierwotnej pozycji.
- **Consequences:** nie implementujemy confirmation chain, tokenów
  potwierdzających ani endpointu `confirm-next`. Panel admina pokazuje grupy
  duplikatów i ich numery. Nie wolno arbitralnie wybierać pierwszego
  wystąpienia.

## D-009 — Forecast presentation

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** forecast zaczyna się od layoutu następującego po `spin 0`,
  analizuje `layout_count - 1` przyszłych layoutów i kończy na layoucie
  bezpośrednio poprzedzającym punkt startowy. Tabela pokazuje dodatnie lokalne
  szczyty `net_credits`, a nie pierwszy dodatni wynik ani globalne high-water
  marks.
- **Reason:** użytkownika interesuje najkorzystniejszy moment każdego
  rosnącego odcinka wyniku, także gdy późniejszy lokalny szczyt jest niższy od
  wcześniejszego.
- **Consequences:** wszystkie payouty po drodze są kumulowane, każdy spin
  zwiększa koszt, a wynik netto to `cumulative_payout - cumulative_cost`.
  Podczas płaskiego szczytu wybierany jest pierwszy spin. Tabela jest
  uporządkowana według spinu, umieszczona na dole głównego ekranu i
  wirtualizowana. Koniec skończonego zakresu pełnego cyklu zamyka ostatni
  rosnący odcinek, więc ostatni oceniony spin może być jego szczytem. Pojęcia
  `first positive` i `high-water mark` są usuwane z kontraktu.

## D-010 — Image ingestion prototype stack

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** prototyp image ingestion używa Pythona, Pillow,
  `opencv-python-headless` i NumPy do geometrii oraz wycinania; PyTorch i
  torchvision do treningu klasyfikatora symboli; ONNX Runtime do produkcyjnej
  inferencji; PaddleOCR w ograniczonym trybie rozpoznawania cyfr jako pierwsza
  implementacja OCR.
- **Reason:** przykładowe zdjęcia mają stabilny układ 3 × 3 i plansze 3 × 5,
  ale zawierają perspektywę, zakrzywienie ekranu, moiré, rozmycie i refleksy.
  Pipeline hybrydowy jest prostszy do kontroli i audytu niż jeden duży model.
- **Consequences:** detekcja geometrii, OCR i klasyfikacja symboli mają osobne
  interfejsy oraz wersje. Konkretny model OCR lub klasyfikatora może zostać
  wymieniony po benchmarku bez zmiany kontraktów panelu, bazy i etapów
  pipeline'u. Wagi modeli są dostępne lokalnie; worker nie pobiera ich podczas
  przetwarzania.
- **Validation needed:** prototyp na 20–100 reprezentatywnych zdjęciach,
  pomiary jakości per etap oraz zatwierdzone progi manual review. Decyzja nie
  zatwierdza jeszcze finalnych modeli OCR/ML.

## D-011 — M1 execution structure

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** M1 pozostaje jednym milestone'em produktowym, ale jest
  realizowany jako sześć kolejnych podetapów M1.1–M1.6 z osobnymi zadaniami,
  demonstracyjnym wynikiem i bramką jakości.
- **Reason:** pełny M1 łączy niezależne ryzyka toolchainu, algorytmów,
  generowania danych, SQLite, UI i Android release. Jeden duży task utrudniłby
  testowanie, diagnozę i bezpieczne cofnięcie zmian.
- **Consequences:** implementacja zaczyna się wyłącznie od M1.1. Następny
  podetap nie rozpoczyna się przed przejściem bramki poprzedniego. Szczegóły
  znajdują się w `delivery/MILESTONE_01_EXECUTION_PLAN.md`.

## D-012 — Mobile snapshot activation

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** każde APK wskazuje dokładną release version i checksum
  niezmiennego snapshotu. Mobile materializuje bazę pod wersjonowaną nazwą,
  waliduje ją i aktywuje dokładnie tę wersję; nie może uznać starej lokalnej
  kopii za aktualną po instalacji nowego APK.
- **Reason:** Android zachowuje katalog danych przy aktualizacji aplikacji.
  Strategia „skopiuj bazę tylko przy pierwszym uruchomieniu” pozostawiłaby stare
  dane mimo instalacji nowej wersji.
- **Consequences:** M1 testuje aktualizację z pierwszego APK do drugiego.
  Nieaktywną kopię można usunąć po poprawnej aktywacji. Brak kompatybilnego
  snapshotu daje `local_data_error`; aplikacja nie wykonuje obliczeń na danych
  poprzedniej wersji.

## D-013 — M1 toolchain and local Android build

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** JavaScript workspace używa npm 11 i jednego
  `package-lock.json`. Mobile używa Expo SDK 57, React Native 0.86, React 19.2
  i TypeScript 6 w trybie strict. Python 3.12 używa lokalnego `.venv`,
  `pyproject.toml`, Ruff, mypy strict i pytest. Android ma stabilny
  `applicationId` `com.gamepredictor.mobile`.
- **Android toolchain:** lokalny skrypt Windows przygotowuje zweryfikowany
  Microsoft OpenJDK 17 oraz Android SDK Platform/Build Tools 36. Build wykonuje
  czysty Expo prebuild i przypięty Gradle wrapper. Domyślnym ABI prywatnych
  buildów urządzeniowych jest `arm64-v8a`.
- **Build commands:** `npm run android:build:debug` tworzy APK deweloperskie
  wymagające Metro. `npm run android:build:offline` tworzy samodzielne,
  testowo podpisane APK z bundlem JavaScript i SQLite.
  `npm run android:verify:offline` sprawdza package id, ABI, bundle i dokładną
  checksumę SQLite wewnątrz paczki.
- **Reason:** npm działa z natywnym mechanizmem Expo workspaces i eliminuje
  problem długich ścieżek CMake, który wystąpił przy strukturze zależności pnpm
  na Windows. Lokalny, wersjonowany workflow usuwa zależność od chmurowego
  builda i globalnej konfiguracji JDK/Android SDK.
- **Alternatives:** pnpm workspace, globalny Android Studio/JDK, EAS cloud
  build.
- **Consequences:** root commands zakładają Windows PowerShell i projektowe
  `.venv`. `package-lock.json` jest jedynym lockfile JavaScript. Major upgrades
  Expo/React Native/TypeScript wymagają osobnego zadania kompatybilności.
  Podpis produkcyjny, instalacja na urządzeniach i wymuszenie braku uprawnienia
  `INTERNET` pozostają bramką M1.6.

## D-014 — Execution structure for M2–M8

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** milestone’y M2–M8 są realizowane przez kolejne, osobno
  odbierane podetapy z własnym wynikiem i bramką jakości, a każdy milestone ma
  osobny execution plan. Zakres rezerwuje `TASK-0015–TASK-0089`, ale plik
  zadania powstaje dopiero bezpośrednio przed rozpoczęciem danego zakresu.
- **Reason:** M2–M8 łączą migracje, API, panel, długie jobs, publikację,
  benchmarki, obraz, ML, manual review, urządzenia i operacje. Pozostawienie ich
  jako pojedynczych bloków roadmapy przeniosłoby zbyt wiele decyzji do
  przyszłego kontekstu i zachęcałoby do dużych, trudnych do zweryfikowania
  zadań.
- **Consequences:** każdy milestone M2–M8 ma osobny plan od
  `delivery/MILESTONE_02_EXECUTION_PLAN.md` do
  `delivery/MILESTONE_08_EXECUTION_PLAN.md`. Milestone rozpoczyna się po bramce
  poprzedniego i poleceniu właściciela. M5 pozostaje zablokowany przez
  Q-015–Q-017, finalne zabezpieczenie panelu w M8 przez Q-019, a analiza
  aplikacji referencyjnej poza obserwacją przez Q-020. Rezerwacja identyfikatora
  nie oznacza utworzenia ani rozpoczęcia zadania.

## D-015 — Fixed-width signature codec v1

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** codec v1 zapisuje każdą komórkę jako dodatni dziesiętny
  `mobile_code` dopełniony zerami z lewej do `signature_cell_width`. Szerokość
  1–5 jest konfiguracją całego datasetu, trafia do snapshotu i nie jest
  wyprowadzana z pojedynczego layoutu. Kody symboli należą do zakresu
  `1..32767`, zgodnego z dodatnią częścią typu `smallint`.
- **Reason:** reprezentacja rozróżnia m.in. `[1, 23]` od `[12, 3]`, zachowuje
  zgodność prefiksu wprowadzania z prefiksem sygnatury oraz daje identyczny
  wynik w Pythonie i TypeScript. Jawna szerokość zapobiega zmianie kodowania
  zależnie od danych pojedynczego rekordu.
- **Alternatives:** kodowanie zmiennoszerokie z separatorem, globalna szerokość
  zaszyta w kodzie, BLOB od pierwszej wersji.
- **Consequences:** `dataset_versions` i mobilne `games` przechowują
  `signature_cell_width`; build odrzuca kody niemieszczące się w niej.
  Repozytoria traktują sygnaturę jako nieprzezroczystą, więc po benchmarku
  można zmienić fizyczną reprezentację na BLOB bez zmiany logiki domenowej.

## D-016 — Payout v1 boundary and structured audit

- **Status:** superseded
- **Date:** 2026-07-24
- **Decision:** payout engine v1 obsługuje konfiguracje do 5 kolumn i odrzuca
  szersze plansze stabilnym błędem do czasu zdefiniowania wielu rozłącznych
  ciągów. Audit używa indeksów 0-based `row-major`, a interpretacja każdego
  jokera jest strukturą `(cell_index, as_symbol_mobile_code)`.
- **Reason:** M1 ma planszę 3 × 5 i jednoznaczną semantykę jednego ciągu.
  Ciche uogólnienie na szersze plansze rozstrzygnęłoby otwarte pytanie
  produktowe. Strukturalny audit jest jednoznaczny i nie wymaga parsowania
  tekstu w raportach ani przyszłym API.
- **Consequences:** publikacja gry szerszej niż 5 kolumn wymaga wcześniejszej
  decyzji i nowej wersji algorytmu. Python i TypeScript utrzymują zgodny
  kontrakt `JokerInterpretation`; payout nadal jest liczony tylko build-time.
- **Superseded by:** D-019. Strukturalny audit pozostaje obowiązujący, lecz
  semantyka ciągu i granica pięciu kolumn zostały zastąpione.

## D-017 — Target engine stream boundary

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** czysty Target engine otrzymuje metadane wydania oraz dokładnie
  `N - 1` uporządkowanych par `(sequence_number, payout)`. Adapter danych
  odpowiada za cykliczny odczyt, a engine niezależnie weryfikuje długość,
  następstwo i zawinięcie. Szczyty są wykrywane w jednym przebiegu bez
  materializacji pełnej tablicy `net`.
- **Reason:** logika matematyczna pozostaje testowalna bez SQLite, a uszkodzony
  lub nieciągły strumień nie daje częściowego wyniku. Jeden przebieg ogranicza
  pamięć roboczą przed benchmarkiem 500 000 layoutów.
- **Consequences:** repozytorium M1.3 musi zwracać kolejność zaczynającą się od
  następcy spinu 0 i kończącą na jego poprzedniku. Integracja M1.5 przekazuje
  dane do engine’u bez ponownego implementowania kumulacji ani lokalnych
  maksimów.

## D-018 — Final M1 SQLite snapshot contract

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** finalny snapshot M1 używa schema version `2`, tabel
  `metadata`, `games`, `symbols`, `layouts`, indeksu
  `(game_id, signature)`, `PRAGMA application_id = 0x47505244` oraz
  `PRAGMA user_version = 2`. Zewnętrzny manifest zawiera wersje, liczniki,
  fixture fingerprint, logiczną checksumę treści i SHA-256 pliku.
- **Reason:** schema spike’u M1.1 zawierała wyłącznie rekordy diagnostyczne i
  nie jest zgodna z finalnym modelem danych. Zachowanie numeru `1` pozwoliłoby
  aplikacji zaakceptować bazę o niewłaściwych tabelach. Oddzielna checksum
  logiczna wykrywa zmianę rekordów nawet po ponownym policzeniu SHA-256 pliku.
- **Consequences:** mobile akceptuje wyłącznie schema version `2` i asset
  `m1-snapshot.db`; stary `m1-spike.db` zostaje usunięty. `created_at` jest
  jawnym wejściem wydania, więc fixture M1 zachowuje deterministyczność bajtową.
  Snapshot nie przechowuje `cells`, paylines ani pełnych payout rules, ponieważ
  runtime potrzebuje konfiguracji gry, symboli, sygnatur i precomputed payoutu.

## D-019 — Left-anchored payout and per-symbol minimum

- **Status:** accepted
- **Date:** 2026-07-24
- **Decision:** `payout-v2` ocenia wyłącznie ciągły prefiks payline zaczynający
  się w pierwszej kolumnie. Każdy zwykły symbol w wersji reguł ma
  `minimum_match_length`, domyślnie 3 i konfigurowalne w zakresie
  `2..columns`. Dla każdej długości od minimum do liczby kolumn administrator
  definiuje osobny, ściśle rosnący payout; naliczana jest tylko najdłuższa
  pasująca długość.
- **Context:** wcześniejsza odpowiedź dopuszczała start w dowolnej kolumnie i
  stałe minimum 3. Właściciel sprostował, że wygrana musi obejmować pierwszą
  kolumnę, a wybrane symbole mogą wygrywać już od dwóch pierwszych kolumn.
- **Reason:** model odpowiada rzeczywistym zasadom gry, pozwala różnicować próg
  według symbolu i usuwa niejednoznaczność rozłącznych ciągów na szerszej
  planszy.
- **Alternatives:** start w dowolnej kolumnie, globalne minimum 3, wyprowadzanie
  minimum wyłącznie z najkrótszej istniejącej payout rule.
- **Consequences:** `rules_version_symbols` przechowuje wersjonowany próg,
  macierz payoutów jest kompletna od progu symbolu, a algorytm nie potrzebuje
  granicy pięciu kolumn z D-016. Istniejący payout-v1, fixture M1, golden
  payout/Target i zbudowane APK wymagają przeliczenia oraz ponownej walidacji
  przed zamknięciem G2–G6.
- **Supersedes:** część D-016 dotyczącą semantyki payout-v1 i granicy pięciu
  kolumn; strukturalny audit z D-016 pozostaje obowiązujący.

## D-020 — M1 acceptance and deferred release revalidation

- **Status:** accepted
- **Date:** 2026-07-26
- **Decision:** M1 i bramka G6 zostają zaakceptowane na podstawie statycznie
  zweryfikowanego APK, instalacji/aktualizacji in-place oraz zakończonych
  scenariuszy manualnych offline na Pixel 10 Pro XL i Galaxy S21 Ultra. Test
  aktywacji celowo zmienionego snapshotu oraz dokładne pomiary matching, Target
  i przewijania zostają przeniesione do M3.4–M3.5.
- **Context:** właściciel potwierdził, że aplikacja działa zgodnie z planem i nie
  widzi błędów. Dokładniejsze testy mają większą wartość po M2, gdy panel tworzy
  rzeczywiste wersjonowane dane, a M3 buduje z nich snapshot i APK.
- **Reason:** nie blokować M2 testem na kolejnym tymczasowym fixture, zachowując
  jednocześnie jawny obowiązek weryfikacji mechanizmu D-012 na właściwym
  pipeline’ie wydania.
- **Consequences:** niewykonane punkty nie mogą być raportowane jako zaliczone w
  M1. G3.4 wymaga fizycznej aktualizacji do zmienionego snapshotu, a G3 wymaga
  pełnych pomiarów urządzeniowych. Dowodem offline Samsunga w M1 pozostają
  wyłączone Wi-Fi, brak karty SIM i zaliczone scenariusze zaakceptowane przez
  właściciela.

## D-021 — M2 local platform baseline and loopback boundary

- **Status:** accepted
- **Date:** 2026-07-26
- **Decision:** fundament M2 używa Next.js `16.2.11`, React `19.2.3` i
  TypeScript `6.0.3` dla `apps/admin` oraz FastAPI `0.139.2`, Uvicorn `0.51.0`
  i Python 3.12 dla `services/api`. Panel i API domyślnie wiążą się z
  `127.0.0.1`; konfiguracja odrzuca hosty i originy inne niż loopback.
- **Context:** D-003 i D-004 wybrały Next.js oraz FastAPI, ale przed M2 nie
  istniał uruchamialny baseline ani egzekwowana granica sieciowa lokalnego
  narzędzia.
- **Reason:** przypięte, wzajemnie zgodne wersje dają odtwarzalny fundament na
  Windows, a walidacja loopback zapobiega przypadkowemu wystawieniu
  niechronionego panelu administracyjnego w LAN lub Internecie.
- **Consequences:** major upgrade fundamentu wymaga osobnego zadania
  kompatybilności. Publiczny albo sieciowy dostęp nie może zostać włączony samą
  zmianą `.env`; wymaga decyzji bezpieczeństwa. PostgreSQL, Alembic, CRUD i
  klient OpenAPI pozostają zakresem TASK-0016–TASK-0017.

## D-022 — Local PostgreSQL and migration lifecycle

- **Status:** accepted
- **Date:** 2026-07-26
- **Decision:** kanoniczna baza M2 używa lokalnego PostgreSQL `18.4` z obrazu
  `postgres:18.4-alpine3.24`, SQLAlchemy `2.0.51`, Psycopg `3.3.4` i Alembic
  `1.18.5`. Port Compose jest wiązany wyłącznie z loopback, dane są trwałe w
  nazwanym volume, a pierwsza migracja `0001_empty_baseline` nie zawiera tabel
  domenowych.
- **Context:** TASK-0015 przygotował API i panel, lecz brakowało kanonicznej bazy
  i kontrolowanego punktu początkowego dla kolejnych pionów M2.
- **Reason:** przypięte wersje i pusty baseline dają odtwarzalny punkt startowy,
  nie utrwalając przedwcześnie szczegółów tabel przed implementacją ich reguł
  integralności.
- **Alternatives:** PostgreSQL instalowany globalnie, SQLite jako baza panelu,
  automatyczne `create_all`, baseline tworzący cały docelowy model.
- **Consequences:** każda zmiana schematu wymaga odwracalnej migracji Alembic.
  Test migracji zarządza wyłącznie bazą `game_predictor_baseline_test`; baza
  deweloperska i nazwany volume nie są automatycznie usuwane. Docker Desktop z
  kontenerami Linux jest lokalnym wymaganiem uruchomieniowym panelu od M2.

## D-023 — Generated Admin API client and drift gate

- **Status:** accepted
- **Date:** 2026-07-26
- **Decision:** FastAPI OpenAPI 3.1 jest jedynym źródłem typów HTTP panelu.
  Deterministyczny JSON oraz klient Fetch są generowane w prywatnym workspace
  `@game-predictor/admin-api-client` przez przypięty
  `@hey-api/openapi-ts 0.99.0`. Root quality gate odrzuca drift backendu,
  artefaktu OpenAPI i wygenerowanego klienta.
- **Context:** przed CRUD M2 panel potrzebuje typowanego kontraktu, który nie
  może rozchodzić się z modelami FastAPI.
- **Reason:** generowanie z działającej aplikacji nie wymaga serwera HTTP ani
  kopiowania modeli, a osobny workspace uniemożliwia przypadkowe dołączenie
  klienta administracyjnego do mobile.
- **Alternatives:** ręczne interfejsy TypeScript, generowanie z działającego
  localhost, `openapi-typescript 7.13.0` z wymuszeniem niezgodnego peer
  dependency TypeScript 5.x.
- **Consequences:** każda operacja API ma stabilny `operationId`; zmiana
  response/error schema wymaga `npm run openapi:generate`. Wygenerowany katalog
  nie jest edytowany ręcznie. Generator pozostaje przypięty, ponieważ seria
  `0.x` może zawierać breaking changes.

## D-024 — Stable catalog identity and archive-only API deletion

- **Status:** accepted
- **Date:** 2026-07-26
- **Decision:** `games.code`, a także para `symbols.code` i
  `symbols.mobile_code` w obrębie gry, są stabilną tożsamością domenową i nie są
  edytowalne po utworzeniu. Publiczne operacje `DELETE` gier i symboli mają
  semantykę idempotentnej archiwizacji, bez fizycznego usuwania rekordu.
- **Context:** pierwszy pion CRUD M2 musi zachować identyfikatory, które później
  znajdą się w wersjonowanych regułach, datasetach i snapshotach mobile.
- **Reason:** zmiana lub ponowne użycie kodu po publikacji uniemożliwiałoby
  jednoznaczne odtworzenie historycznego wydania. Archiwizacja zapewnia jeden
  kontrakt przed i po dodaniu zależności wersjonowanych.
- **Alternatives:** edytowalne kody, fizyczne kasowanie rekordów nieużytych,
  osobne endpointy kasowania i archiwizacji.
- **Consequences:** korekta błędnego stabilnego kodu wymaga utworzenia nowego
  rekordu i archiwizacji poprzedniego. Przyszłe klucze obce chronią historię,
  ale publiczne API nie zmieni semantyki usuwania.

## D-025 — Server-assigned rules version and draft-only mutation

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** Admin API przydziela kolejny numer wersji reguł jako
  `max(version) + 1` w obrębie gry po zablokowaniu jej rekordu w tej samej
  transakcji. Utworzenie zawsze daje status `draft`; publiczna aktualizacja
  TASK-0021 przyjmuje wyłącznie `rows`, `columns` i `spinCost` oraz działa tylko
  dla draftu. Lista jest deterministycznie uporządkowana od najnowszej wersji.
- **Context:** numer wersji jest częścią historycznej tożsamości wydania, ale nie
  jest decyzją administratora. Równoległe żądania nie mogą utworzyć dwóch
  rekordów o tym samym numerze ani pozostawić luk przez ręczne wartości.
- **Reason:** serwerowa numeracja i blokada rekordu gry zapewniają prostą,
  deterministyczną sekwencję, a ograniczenie mutacji do draftu przygotowuje
  niezmienność danych bez przedwczesnego implementowania publikacji.
- **Alternatives:** numer podawany przez UI, retry wyłącznie po konflikcie
  constraintu, edycja pól niezależnie od statusu.
- **Consequences:** UI nie wysyła `version` ani `status`. Constraint
  `(game_id, version)` pozostaje ostatnią linią obrony. Przejścia
  `draft → published → archived`, kompletność reguł i ustawienie
  `published_at` należą do TASK-0024.

## D-026 — Stable payline identity and dimension-safe draft lifecycle

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** `paylines.code` jest stabilny i unikalny w wersji reguł.
  Publiczne `DELETE` ustawia `is_active = false`, bez fizycznego usuwania;
  PATCH może ponownie aktywować wzorzec. `row_path` pozostaje unikalny także dla
  nieaktywnego rekordu. Zmiana liczby kolumn draftu jest zabroniona, gdy
  istnieje jakakolwiek payline, a zmniejszenie liczby rzędów jest możliwe tylko,
  gdy każdy istniejący indeks nadal mieści się w nowym zakresie.
- **Context:** kod i ścieżka linii będą częścią odtwarzalnej wersji reguł.
  Fizyczne usunięcie lub ponowne użycie tożsamości utrudniałoby audyt, a zmiana
  wymiarów mogłaby pozostawić wzorce sprzeczne z własnym rodzicem.
- **Reason:** jeden lifecycle draftu zachowuje historię i upraszcza przyszłą
  publikację, natomiast walidacja wymiarów gwarantuje integralność bez kaskadowej
  modyfikacji wzorców.
- **Alternatives:** fizyczne usuwanie nieopublikowanych linii, ponowne używanie
  zarchiwizowanego `row_path`, automatyczne przycinanie ścieżki po zmianie
  wymiarów.
- **Consequences:** korekta stabilnego kodu wymaga nowej payline i archiwizacji
  poprzedniej. Zarchiwizowany wzorzec można odzyskać przez edycję, a próba
  utworzenia jego kopii nadal zwraca `DUPLICATE_PAYLINE`.

## D-027 — Draft payout configuration lifecycle

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** pierwszy PATCH symbolu w wersji reguł wykonuje upsert jego
  konfiguracji. Panel prezentuje brakującą konfigurację zwykłego symbolu z
  domyślnym minimum 3, ale rekord staje się wersjonowaną prawdą dopiero po
  zapisie. Podniesienie minimum automatycznie archiwizuje payout rules poniżej
  nowego progu. Publiczne DELETE payoutu jest archiwizacją; unikalna para
  symbol/długość pozostaje zarezerwowana i może zostać reaktywowana przez PATCH.
- **Context:** draft musi pozwalać stopniowo uzupełniać macierz wypłat, ale nie
  może zachowywać aktywnych reguł sprzecznych z aktualnym minimum ani tracić
  historycznej tożsamości rekordu.
- **Reason:** upsert upraszcza konfigurację symboli istniejących przed wersją
  reguł, automatyczna archiwizacja usuwa lokalną sprzeczność po zmianie progu,
  a wspólny lifecycle zachowuje audyt zgodny z games, symbols i paylines.
- **Alternatives:** materializacja konfiguracji wszystkich symboli przy
  tworzeniu wersji, fizyczne kasowanie payoutów, blokowanie podniesienia progu
  do czasu ręcznej archiwizacji, atomowy dodatkowy endpoint całego formularza.
- **Consequences:** CRUD draftu może być przejściowo niekompletny. UI waliduje
  kompletny i ściśle rosnący zestaw jednego symbolu przed zapisem; walidacja
  kompletności całej wersji i publikacja pozostają w TASK-0024.

## D-028 — Atomic rules publication and active version membership

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** aktywne `rules_version_symbols` definiują skład symboli wersji.
  Gotowa wersja ma co najmniej jedną aktywną payline i jeden aktywny zwykły
  symbol, a każdy zwykły symbol ma pełną, ściśle rosnącą macierz payoutów.
  Read-only raport gotowości i publikacja używają tej samej czystej walidacji.
  Publikacja blokuje rekord `rules_versions`, ponownie waliduje i atomowo ustawia
  `published` oraz serwerowy `published_at`. Wiele historycznych wersji tej samej
  gry może pozostać opublikowanych. Osobna archiwizacja jest idempotentnym
  przejściem `published → archived` i zachowuje timestamp publikacji.
- **Context:** preflight panelu poprawia UX, ale nie może być jedyną ochroną
  przed zmianą danych pomiędzy sprawdzeniem i zapisem statusu.
- **Reason:** jedna deterministyczna walidacja usuwa drift między UI i
  publikacją, a blokada i transakcja zapewniają niezmienność bez kolejki,
  rozproszonego locka ani nowej infrastruktury.
- **Alternatives:** walidacja wyłącznie w UI, publikacja bez preflightu,
  automatyczna archiwizacja poprzedniej wersji, tylko jedna opublikowana wersja
  gry, osobna tabela zdarzeń publikacji.
- **Consequences:** nieaktywne konfiguracje pozostają historyczne, ale nie mogą
  mieć aktywnych payoutów. Nieudana walidacja nie zmienia statusu ani
  `published_at`. Dataset i release jawnie wskazują wersję, więc poprzednia
  opublikowana wersja nie musi być automatycznie wycofywana.

## D-029 — Bounded deterministic mock generation into staging

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** administracyjny generator mocka tworzy synchronicznie dokładnie
  1000 layoutów na podstawie opublikowanej wersji reguł. Jej aktywne
  konfiguracje symboli definiują alfabet, a wymiary definiują rozmiar planszy.
  Seed, wersja generatora i szerokość codeca są zapisane w `dataset_versions`.
  Cała stagingowa wersja wraz z layoutami powstaje w jednej transakcji.
- **Context:** demonstracja M2 potrzebuje szybkiego, powtarzalnego datasetu, ale
  docelowa skala 500 000 rekordów nie może ustanawiać długiego requestu HTTP.
- **Reason:** stały limit zachowuje prosty pion panel–API dla M2, a zapisane
  parametry pozwalają odtworzyć logiczne dane i nie mieszają technicznego UUID z
  kolejnością domenową.
- **Alternatives:** generator 500 000 rekordów w requestcie, tworzenie joba bez
  działającego workera, losowanie bez zapisanego seedu, kopiowanie fixture M1
  bez powiązania z aktualnym katalogiem.
- **Consequences:** powtórzenie tych samych wejść tworzy nowy numer wersji i
  inne identyfikatory techniczne, ale identyczny uporządkowany zestaw
  `sequence_number/cells/signature`. Raporty i publikacja pozostają w
  TASK-0026–TASK-0027; większe datasety wykonuje worker.

## D-030 — Synchronous validation report for the bounded mock

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** raport integralności datasetu używa jednego czystego,
  deterministycznego walidatora, który zostanie ponownie użyty przez publikację.
  Admin API może wykonać go synchronicznie wyłącznie dla bounded datasetu
  `mock-v1`. Raport zawiera dokładne liczniki i ograniczone, deterministyczne
  próbki diagnostyczne. Duplikat sygnatury ma poziom `warning`; luka, duplikat
  numeru, zła liczba komórek, obcy symbol i niespójna sygnatura mają poziom
  `blocking`.
- **Context:** obowiązujący kontrakt opisywał validation job, ale M2 nie ma
  jeszcze infrastruktury trwałych jobów ani workera administracyjnego. Obecny
  dataset ma zawsze tylko 1000 rekordów.
- **Reason:** bezpośredni raport zamyka pion M2 bez tworzenia pozornego joba,
  zachowuje jedną definicję gotowości do publikacji i nie ustanawia długiego
  requestu dla skali docelowej.
- **Alternatives:** synchroniczna walidacja dowolnego rozmiaru, atrapowy job
  kończący się w requestcie, przedwczesne wdrożenie kolejki lub trwałych jobów,
  osobny walidator w panelu.
- **Consequences:** endpoint raportu odrzuca inne wersje generatora stabilnym
  błędem `DATASET_VALIDATION_REQUIRES_JOB`. Importy i datasety docelowej skali
  zachowują kontrakt validation job realizowany przez workera w późniejszym
  milestone. Panel nie wylicza integralności samodzielnie.

## D-031 — Keyset preview and atomic dataset publication

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** podgląd layoutów używa bounded keyset pagination po domenowym
  `sequence_number`, a nie offsetu ani technicznego UUID. Publikacja blokuje
  rekord `dataset_versions`, ponownie uruchamia wspólny walidator i atomowo
  wykonuje `staging → published` z serwerowym `published_at`. Ostrzeżenia o
  duplikatach sygnatur nie blokują publikacji. Wiele opublikowanych datasetów
  jednej gry może współistnieć. Archiwizacja jest idempotentnym przejściem
  `published → archived` i zachowuje timestamp oraz layouty.
- **Context:** preflight z TASK-0026 poprawia obsługę panelu, ale dane mogłyby
  zmienić się pomiędzy raportem a publikacją. Podgląd musi zachować porządek
  istotny dla algorytmu także po wzroście liczby rekordów.
- **Reason:** wspólna walidacja pod blokadą usuwa drift i wyścig publikacji, a
  kursor domenowy daje stabilny oraz indeksowalny odczyt bez kosztu rosnącego
  offsetu. Archiwizacja bez usuwania zachowuje audyt i przyszłe odtwarzanie
  snapshotu.
- **Alternatives:** walidacja wyłącznie przed publikacją, offset pagination,
  automatyczne wycofanie poprzedniej wersji, fizyczne usuwanie wersji lub
  layoutów.
- **Consequences:** ponowna publikacja wersji innej niż staging jest odrzucana.
  Nie istnieje publiczny endpoint mutacji layoutów; każda przyszła mutacja musi
  blokować ten sam rekord rodzica. Duże importy nadal wymagają validation job,
  lecz zachowają ten sam warunek gotowości.

## D-032 — Universal job lifecycle separated from workflow stage

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** wszystkie długie operacje używają wspólnego cyklu życia
  `created → processing → completed/failed` z opcjonalnym
  `processing → waiting_for_review → created` oraz anulowaniem. Szczegół
  pipeline'u jest przechowywany osobno jako `stage`. Żądanie anulowania joba
  `processing` tylko ustawia `cancel_requested_at`; dopiero worker w bezpiecznym
  punkcie przełącza go na `cancelled`. Payload wejściowy ma jawny
  `schemaVersion`, a kanoniczny hash typu, gry i payloadu jest unikalnym kluczem
  enqueue.
- **Context:** wymagania używały nazw `scanning` i `validating` obok stanów
  terminalnych, choć dotyczą one wyłącznie importu. Te same jobs mają obsłużyć
  import, walidację, payout, snapshot i Android build.
- **Reason:** jeden mały automat pozwala jednakowo egzekwować przejścia,
  anulowanie i retry, a osobny etap zachowuje dokładny postęp każdego workflow.
  Unikalny klucz wejścia blokuje przypadkowe duplikaty jeszcze przed
  implementacją workera.
- **Alternatives:** osobny enum statusów dla każdego typu, etap jako status,
  anulowanie działającego joba bez potwierdzenia workera, brak ochrony przed
  powtórnym enqueue.
- **Consequences:** `created` pełni rolę trwałej kolejki bez Redis/Celery.
  Wiele jobs może oczekiwać, ale ograniczenie jednego ciężkiego wykonania będzie
  egzekwowane atomowym lease w TASK-0030. `waiting_for_review` nie trzyma workera
  i może wrócić do `created` po rozwiązaniu review.

## D-033 — PostgreSQL singleton lease with fenced worker updates

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** lokalny worker przejmuje najstarszy job `created` w transakcji
  `FOR UPDATE SKIP LOCKED`. Rekord `processing` otrzymuje singletonowy
  `execution_slot = 1`, owner, losowy token lease, expiry i heartbeat.
  Unikalność slotu w PostgreSQL gwarantuje najwyżej jedno ciężkie wykonanie.
  Każda aktualizacja workera wymaga zgodnego, niewygasłego tokenu. Progress i
  wersjonowany checkpoint JSONB zapisują się w jednej transakcji. Wygasły lease
  wraca na tym samym rekordzie do `created` z zachowanym checkpointem; jeśli
  istniało żądanie anulowania, przechodzi do `cancelled`.
- **Context:** proces działa lokalnie bez Redis/Celery, może zostać zamknięty w
  dowolnej chwili, a dwóch przypadkowo uruchomionych workerów nie może
  wykonywać ciężkich jobs jednocześnie ani nadpisywać nowszej próby.
- **Reason:** constraint bazy zamyka wyścig niezależnie od liczby procesów,
  token stanowi fencing dla starego workera, a checkpoint tego samego rekordu
  zachowuje idempotencję wynikającą z `input_key`.
- **Alternatives:** blokada wyłącznie w pamięci procesu, advisory lock bez
  trwałego lease, osobna kolejka Redis/Celery, tworzenie nowego joba przy retry,
  automatyczne oznaczanie każdego osieroconego joba jako failed.
- **Consequences:** handler wykonuje się poza transakcją i musi raportować
  heartbeat/checkpoint przed expiry. Domyślny lease trwa 60 sekund. Konkretne
  workflow odpowiada za idempotentny zapis własnych wyników; brak handlera jest
  stabilnym błędem, a ekran statusu pozostaje zakresem TASK-0031.

## D-034 — Idempotent payout batches with external JSONL audit

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** `payout-v2` odczytuje layouty keysetowo w partiach po 1000.
  Każda partia najpierw tworzy atomowo podmieniany, deterministyczny JSONL,
  następnie wykonuje upsert `layout_payouts`, a na końcu zapisuje checkpoint.
  Wszystkie wyniki partii wskazują wspólny względny `audit_path`; rekord audytu
  identyfikuje `sequenceNumber`. Klucz wyniku obejmuje dataset, rules,
  sequence i algorithm.
- **Context:** docelowy dataset ma około 500 000 layoutów, pełny audyt nie
  powinien rozdymać głównych tabel ani wymagać załadowania całości do pamięci.
  Worker może zostać zamknięty między dowolnymi krótkimi transakcjami.
- **Reason:** JSONL jest strumieniowy i zachowuje strukturalne matches, komórki,
  jokery oraz interpretacje. Deterministyczna nazwa i upsert sprawiają, że
  powtórzenie ostatniej partii po awarii jest bezpieczne, zaś checkpoint nigdy
  nie wyprzedza trwałego wyniku.
- **Alternatives:** JSONB audytu w każdym rekordzie PostgreSQL, jeden plik na
  layout, jeden ogromny plik całego joba, checkpoint przed zapisem wyników,
  kasowanie wszystkich payoutów przy retry.
- **Consequences:** lokalny katalog artefaktów musi być zachowany razem z
  administracyjną bazą, jeżeli wymagany jest historyczny audyt. Osierocony plik
  po awarii przed upsertem jest bezpieczny i zostanie deterministycznie
  zastąpiony przy retry. Rozmiar partii i audytów podlega pomiarowi M3.5.

## D-035 — Exact-version payout readiness gate

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** gotowość payoutów jest liczona wyłącznie dla dokładnej kombinacji
  dataset/rules/algorithm. Wymaga opublikowanych i zgodnych źródeł, jednego
  wyniku dla każdej sekwencji oraz niepustego `audit_path`. Repozytorium zwraca
  dokładne agregaty i najwyżej 100 rosnących brakujących numerów. Zawartość
  JSONL potwierdza osobny strumieniowy weryfikator.
- **Context:** historyczne wyniki są celowo zachowywane, więc sama liczba
  rekordów lub payout innej wersji mogłyby fałszywie domknąć wejście snapshotu.
  Docelowy dataset ma około 500 000 layoutów i nie może być materializowany w
  pamięci tylko dla diagnostyki.
- **Reason:** dokładny klucz wersji zapewnia odtwarzalność wydania, agregaty SQL
  zachowują bounded memory, a jawny raport z kodami problemów może być używany
  przez generator snapshotu i późniejszą orkiestrację release.
- **Alternatives:** uznanie najnowszego wyniku sekwencji niezależnie od wersji,
  pełne pobranie 500 000 rekordów do workera, brak audytu jako ostrzeżenie,
  weryfikacja tylko liczby payoutów bez lewego złączenia z layoutami.
- **Consequences:** archiwalny dataset lub rules nie jest nowym gotowym wejściem
  snapshotu. Brak ścieżki audytu blokuje gotowość, a koszt sprawdzenia zawartości
  wszystkich plików audytu zostanie zmierzony w M3.5.

## D-036 — Deterministic streaming production snapshot

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** produkcyjny generator zachowuje SQLite schema version 2 i
  przyjmuje jawny zestaw wyborów dataset/rules/algorithm. Każdy wybór przechodzi
  D-035. Gry są porządkowane po stabilnym kodzie, symbole po `mobile_code`, a
  layouty są czytane keysetowo i zapisywane partiami po 1000. Logiczny SHA-256
  powstaje w tym samym przebiegu. Kompletny plik jest publikowany bez możliwości
  nadpisania istniejącego celu.
- **Context:** fixture-only generator M1 materializuje wszystkie rekordy w
  pamięci i zawiera metadata testowe. Docelowy snapshot ma obsługiwać wiele gier
  i około 500 000 layoutów na grę, ale `mobile_releases` oraz manifest powstają
  dopiero w następnych zadaniach.
- **Reason:** jawne wersje i stabilne sortowanie odcinają wynik od UUID oraz
  kolejności requestu. Bounded batch ogranicza pamięć, a publikacja dopiero po
  pełnym zapisie nie pozostawia częściowego artefaktu.
- **Alternatives:** ponowne użycie fixture generatora M1, ładowanie wszystkich
  layoutów do pamięci, użycie technicznych UUID jako mobilnych identyfikatorów,
  nadpisywanie wspólnego pliku, rejestracja joba przed powstaniem release.
- **Consequences:** wszystkie gry schema v2 używają jednego globalnego
  `algorithm_version`; wersje dataset/rules pozostają per gra. Generator nie
  zapisuje pól fixture. Manifest, niezależna walidacja i katalog artefaktu są
  zakresem TASK-0035, a integracja job/release zakresem M3.4.

## D-037 — Content-addressed validated snapshot artifact

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** manifest schema v1 jest kanonicznym JSON zawierającym globalne
  metadata, oba SHA-256, dokładne liczniki oraz kanoniczne UUID i numery
  dataset/rules per gra. Zweryfikowany artefakt jest publikowany pod
  `snapshots/<releaseVersion>/<logicalContentSha256>/` i zawiera wyłącznie
  `snapshot.db` oraz `manifest.json`. Identyczny retry może użyć istniejącego
  katalogu dopiero po pełnej walidacji; nigdy go nie nadpisuje.
- **Context:** generator TASK-0034 tworzy poprawny plik, lecz Android build
  potrzebuje samodzielnego, wersjonowanego kontraktu i dowodu, że artefakt nie
  został uszkodzony po zapisie. Poprzednie wydania muszą pozostać dostępne.
- **Reason:** content-addressed ścieżka łączy D-012 z niezmiennością, a osobny
  read-only przebieg nie ufa generatorowi, metadata ani manifestowi. Odtworzenie
  logicznego checksumu wykrywa poprawnie opakowaną zmianę rekordów.
- **Alternatives:** jeden nadpisywany `snapshot.db`, manifest tylko z checksumą
  pliku, walidacja wyłącznie `quick_check`, publikacja pliku przed manifestem,
  akceptacja istniejącego katalogu bez porównania.
- **Consequences:** pełna walidacja czyta każdy layout i jej koszt podlega
  benchmarkowi M3.5. Pusty `.staging` może pozostać technicznym katalogiem
  roboczym, ale nie jest artefaktem wydania. Podłączenie do `mobile_release`,
  snapshot joba i Android build pozostaje zakresem M3.4.

## D-038 — Immutable server-versioned mobile release selection

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** nowy `mobile_release` jest globalnie unikalnym, niezmiennym
  draftem zawierającym 1–15 dokładnych wyborów dataset/rules. Backend zapisuje
  jedyny obsługiwany `payout-v2` i SQLite schema `2`; klient nie przekazuje tych
  wartości. Wszystkie opublikowane źródła są blokowane i zapisywane z rodzicem
  w jednej transakcji, a gry są kanonicznie porządkowane po stabilnym kodzie.
- **Context:** publiczne payloady snapshot/android jobs wskazują
  `mobileReleaseId`, ale przed M3.4 nie istniał rekord ustalający odtwarzalne
  wejście wielu gier. Dopuszczenie dowolnego algorytmu z panelu tworzyłoby
  konfigurację, której worker nie potrafi wykonać.
- **Reason:** oddzielenie utworzenia niezmiennego draftu od uruchomienia builda
  umożliwia przejrzenie wejścia, bezpieczny retry i późniejszy audyt. Serwerowe
  wersje techniczne ograniczają kontrakt do faktycznie wspieranej ścieżki.
- **Alternatives:** mutowalny draft, algorytm podawany przez UI, jeden release
  per gra, utworzenie release dopiero wewnątrz joba.
- **Consequences:** korekta wersji albo wyboru wymaga nowego release. TASK-0037
  może utworzyć dokładnie jeden workflow dla utrwalonego wejścia i ponownie
  sprawdzić pełną kompletność payoutów przed snapshotem.

## D-039 — One resumable job owns the complete release workflow

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** dokładnie jeden job `android_build` jest właścicielem pełnego
  workflow release: rewalidacji, brakujących payoutów, snapshotu, obu
  weryfikacji i kontrolowanego builda APK. Nie tworzy child-jobów. Checkpoint
  schema v1 przechowuje etap, ukończone gry oraz aktywny cursor payoutu. Retry
  wznawia ten sam job i może użyć istniejącego artefaktu tylko po pełnej
  walidacji.
- **Context:** lokalny worker celowo ma jeden slot wykonawczy. Nadrzędny job
  oczekujący na payout albo snapshot child-job zablokowałby jedyny slot lub
  wymagał osobnego scheduler'a. Release ma już niezmienne wejście i jedno pole
  `build_job_id`.
- **Reason:** jeden owner upraszcza atomowy start, anulowanie, diagnostykę i
  odtwarzalność. Zagnieżdżony checkpoint zachowuje bounded-memory payout oraz
  pozwala kontynuować po wygaśnięciu lease bez duplikowania release i
  nadpisywania artefaktów.
- **Alternatives:** osobne zależne joby payout/snapshot/build, synchroniczny
  request HTTP, drugi worker lub kolejka Celery, uruchamianie Gradle bez
  trwałego joba.
- **Consequences:** `android_build` jest typem workflow, nie nazwą wyłącznie
  ostatniego procesu Gradle. Release przechodzi do `ready` dopiero po końcowym
  checkpointcie i zapisie obu zweryfikowanych artefaktów; błąd lub anulowanie
  daje `failed`, a retry nie tworzy nowego joba.

## D-040 — Controlled APK download by immutable release identity

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** panel pobiera gotowy APK przez typowany endpoint przyjmujący
  wyłącznie `mobileReleaseId`. Admin API rozwiązuje utrwaloną ścieżkę względem
  skonfigurowanego katalogu artefaktów, wymaga statusu `ready`, zwykłego pliku
  `.apk` i zgodnego SHA-256. Panel może skopiować ścieżkę względną, ale nie
  przekazuje ścieżki wejściowej ani komendy systemowej.
- **Context:** przeglądarka nie może niezawodnie otworzyć lokalnego katalogu
  Windows ze strony HTTP, a endpoint przyjmujący dowolną ścieżkę lub polecenie
  przekroczyłby granicę bezpieczeństwa lokalnego panelu.
- **Reason:** identyfikator niezmiennego release wiąże pobierany plik z audytem
  TASK-0037 i pozwala sprawdzić integralność bez zaufania do klienta. Ręczne
  otwarcie skopiowanej ścieżki zachowuje prosty workflow bez desktop bridge.
- **Alternatives:** `file://` z panelu, dowolny path w query, uruchamianie
  Explorera przez API, automatyczna instalacja na telefonie.
- **Consequences:** Admin API i worker muszą wskazywać ten sam
  `artifact_root`. Pobranie czyta i hashuje APK przed odpowiedzią; koszt jest
  akceptowalny dla ręcznej, prywatnej dystrybucji i nie dotyczy mobile runtime.

## D-041 — Conditional M4 start before physical G3 evidence

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** implementacja M4 może rozpocząć się przed formalnym zaliczeniem
  G3. Brakujące benchmarki 500 000 layoutów na Pixelu i Samsungu oraz końcowy
  raport akceptacyjny M3 pozostają obowiązkowe i zostaną wykonane po M4, przed
  rozpoczęciem M5. Rozpoczęcie M4 nie zmienia statusu `blocked` TASK-0039,
  TASK-0041, TASK-0042 ani raportu G3.
- **Context:** właściciel wykonał bieżące testy funkcjonalne layoutów normalnych,
  duplikatów i pozostałych funkcji, a dokładne testy wydajnościowe świadomie
  odłożył do odbioru po M4.
- **Reason:** M4 korzysta ze stabilnych kontraktów `cells`, sygnatury,
  wersjonowania datasetu i istniejącego resumowalnego lifecycle jobs. Brakujące
  dowody G3 dotyczą wydajności urządzeń i formalnego odbioru release, a nie
  modelu ręcznego importu.
- **Alternatives:** zatrzymanie całego developmentu do czasu pełnych pomiarów
  obu telefonów albo fałszywe oznaczenie G3 jako zaliczone.
- **Consequences:** M4 jest realizowane warunkowo. Nie wolno używać rozpoczęcia
  M4 jako dowodu akceptacji adaptera Android ani zamykać M3 bez raportu
  `m35-acceptance-report.json` o statusie `passed`.

## D-042 — Streaming layout import formats v1

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** `layout-import-v1` obsługuje ścisłe UTF-8 bez BOM, dokładny CSV
  z kolumnami `schema_version,sequence_number,cells` oraz JSON Lines z polami
  `schemaVersion`, `sequenceNumber`, `cells`. Wersja `1` jest zapisana w każdym
  rekordzie, a `cells` jest tablicą JSON dodatnich kodów `smallint` w kolejności
  row-major.
- **Context:** ręczny import ma obsługiwać około 500 000 layoutów bez
  materializacji całego pliku. Zwykły wielki dokument JSON wymagałby dodatkowego
  parsera strumieniowego i utrudniał checkpoint na granicy rekordu.
- **Reason:** CSV i JSONL są czytelne, łatwe do wygenerowania z zewnętrznych
  narzędzi oraz pozwalają wznawiać pracę na stabilnej granicy linii. Powtarzana
  wersja wykrywa sklejone lub częściowo niezgodne pliki.
- **Alternatives:** monolityczny JSON array, binarny format własny, sidecar z
  metadanymi albo wersja wyłącznie w nazwie pliku.
- **Consequences:** CSV zapisuje `cells` jako cytowaną tablicę JSON. UTF-8 BOM,
  nieznane pola i dodatkowe kolumny są błędami kontraktu. Wymiary i alfabet gry
  pozostają poza formatem i są walidowane podczas stagingu.

## D-043 — Server-attested local import source

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** ręczny layout import przyjmuje od klienta wyłącznie względny
  POSIX `sourcePath` pod skonfigurowanym `import_root` oraz
  `contractVersion = 1`. Admin API samo ustala format z `.csv/.jsonl`, sprawdza
  zwykły plik, limit, preview, liczy SHA-256 bounded partiami i zapisuje
  poświadczone metadata w istniejącym jobie `import`. Klient nie podaje
  checksumy, rozmiaru ani formatu.
- **Context:** generyczny wcześniejszy payload `sourcePath/pipelineVersion`
  pozwalał wskazać dowolną lokalną ścieżkę i nie wiązał joba z konkretnymi
  bajtami. M4 wymaga bezpiecznej ścieżki oraz idempotencji dla dużych plików.
- **Reason:** osobny root ogranicza dostęp systemu plików, serwerowy checksum
  daje odtwarzalne wejście, a użycie istniejącego lifecycle jobs zachowuje lease,
  retry i unikalny `input_key` bez nowej tabeli.
- **Alternatives:** upload wielkiego pliku przez FastAPI, zaufanie checksumie
  klienta, ścieżka absolutna, kopiowanie pliku w requestcie albo nowy model
  kolejki importów.
- **Consequences:** domyślny limit wynosi 1 GiB i jest konfigurowalny.
  `input_key` layout importu ignoruje nazwę pliku, a obejmuje grę, SHA-256,
  format i wersję kontraktu. Worker musi ponownie potwierdzić checksum przed
  stagingiem, ponieważ użytkownik może zmienić plik po utworzeniu joba.

## D-044 — Raw import rows with prefix-fenced resumable checkpoints

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** TASK-0045 zapisuje każdy niepusty fizyczny rekord
  `layout-import-v1` do osobnej tabeli `layout_import_rows` przypisanej do joba.
  Rekord zawiera pozycję pliku oraz dokładnie jeden wariant:
  `sequence_number/cells` albo stabilny błąd. Checkpoint powstaje po
  idempotentnym upsercie partii i zawiera offset, numer linii oraz łańcuch
  checksumy fizycznego prefiksu. Wznowienie weryfikuje ten łańcuch i usuwa
  wszystkie wiersze znajdujące się za trwałym numerem linii.
- **Context:** zapis bezpośrednio do `layouts` wymagałby przedwcześnie wymiarów,
  alfabetu gry i finalnej sygnatury należących do TASK-0046. Sam offset nie
  wykrywałby sytuacji, w której plik zmienił się po zapisie partii, a proces
  zakończył przed checkpointem; w bazie mógłby pozostać nietrwały ogon.
- **Reason:** surowa tabela zachowuje błędy bez blokowania poprawnych rekordów i
  nie jest widoczna dla release. Klucz `(job_id, line_number)` pozwala
  powtarzać partię, natomiast łańcuch prefiksu i odcięcie ogona wiążą staging z
  dokładnymi bajtami poprzedniego przebiegu bez serializacji stanu `hashlib`.
- **Alternatives:** bezpośredni zapis do `layouts`, jeden JSONB z całym
  stagingiem, checkpoint wyłącznie po `sequence_number`, ufanie samemu
  offsetowi, kopiowanie całego źródła do osobnego artefaktu przed parsowaniem.
- **Consequences:** migracja `0011_layout_import_staging` dodaje jedną tabelę i
  indeks. Worker `worker-v3` ponownie hashuje źródło przed i po przebiegu oraz
  odtwarza bounded prefiks przy wznowieniu. Surowe rekordy zajmują dodatkowe
  miejsce do czasu jawnego odrzucenia lub normalizacji; utworzenie datasetu i
  sygnatur pozostaje zakresem TASK-0046.

## D-045 — Separate rules-bound layout import validation job

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** normalizacja surowego importu jest osobnym jobem `validate` z
  `validation_kind = layout_import`, `import_job_id` i `rules_version_id`.
  Wymaga zakończonego importu oraz opublikowanej wersji reguł tej samej gry.
  Wynik trafia do `layout_import_normalized_rows` keyed przez
  `(validation_job_id, line_number)` i nadal nie jest datasetem.
- **Context:** surowy job TASK-0045 ma postęp liczony w bajtach i kończy się po
  reatestacji pliku. Wymiary, aktywny alfabet i szerokość sygnatury pojawiają
  się dopiero w TASK-0046. Łączenie obu etapów w jednym jobie zmieniałoby
  znaczenie postępu i uniemożliwiałoby bezpieczną ponowną walidację tych samych
  bajtów względem innej wersji reguł.
- **Reason:** osobny lifecycle zachowuje jednoznaczne liczniki, prosty retry,
  niezmienny surowy staging i jawne powiązanie z regułami. Osobna tabela
  dopuszcza tymczasowe duplikaty `sequence_number`, których nie przyjmie finalne
  `layouts`, oraz przygotowuje raport TASK-0047.
- **Alternatives:** dopisać normalizację po końcu joba importu, nadpisywać
  surowe wiersze, wybrać automatycznie najnowsze reguły albo zapisywać od razu
  do `layouts`.
- **Consequences:** generyczny payload datasetowego `validate` pozostaje
  obsługiwany, a nowy wariant ma jawne `validationKind`. Worker `worker-v4`
  checkpointuje liczbę rekordów i fizyczną linię po idempotentnym upsercie.
  TASK-0047 raportuje luki i duplikaty, a TASK-0049 dopiero tworzy
  `dataset_version`.

## D-046 — Exact SQL import report with bounded diagnostics

- **Status:** accepted
- **Date:** 2026-07-27
- **Decision:** raport znormalizowanego importu jest liczony read-only z
  zakończonego stagingu. Dokładne agregaty SQL obejmują zgodność liczby wierszy,
  poprawne i błędne warianty, ciąg dodatnich numerów od `1`, duplikaty numerów,
  duplikaty sygnatur i kody błędów. Próbki są ograniczone do 100 elementów.
  Podgląd używa keyset po fizycznym `line_number`.
- **Context:** staging celowo dopuszcza błędy, luki i duplikaty, których nie
  przyjmie finalna tabela `layouts`. Docelowe 500 000 rekordów nie może zostać
  pobrane do procesu API tylko po to, aby zbudować raport lub listę.
- **Reason:** dokładne liczniki z bounded próbkami zachowują pełną informację
  decyzyjną i przewidywalną pamięć. `line_number` jest jednoznacznym kursorem
  także wtedy, gdy `sequence_number` ma duplikaty. Wyznaczenie przedziałów luk
  przez `lag` unika nieograniczonego `generate_series` dla wadliwego, bardzo
  wysokiego numeru.
- **Alternatives:** utrwalony cache raportu, pełna materializacja stagingu w
  Pythonie, offset pagination, generowanie każdego numeru od `1` do maksimum.
- **Consequences:** błędny wiersz blokuje gotowość i nie wypełnia luki w zbiorze
  poprawnych layoutów. Brak poprawnych wierszy, różnica względem
  `progress.total`, luka i duplikat numeru są blokadami. Duplikat sygnatury jest
  dozwolonym ostrzeżeniem. Raport nie zmienia danych i nie tworzy datasetu;
  publikacja TASK-0049 musi ponownie użyć tej samej definicji gotowości.

## D-047 — Confirmed rejection of an entire unpublished import staging

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** odrzucenie wskazuje zakończony job walidacji
  `layout_import`, z którego backend wyprowadza dokładny `import_job_id`.
  W jednej transakcji usuwa wszystkie znormalizowane wiersze wszystkich
  walidacji tego importu, a następnie surowe wiersze. Joby pozostają trwałym
  audytem. Panel wymaga przepisania pełnego `importJobId` przed potwierdzeniem.
- **Context:** jeden surowy import może zostać zwalidowany względem kilku wersji
  reguł, a FK znormalizowanych wierszy nie pozwala bezpiecznie usunąć wyłącznie
  surowej części. Usuwanie tylko wyniku jednej walidacji pozostawiłoby
  niejednoznaczny, częściowo istniejący import.
- **Reason:** granicą destrukcyjnej operacji jest cały nieopublikowany import,
  natomiast identyfikator walidacji daje panelowi jednoznaczny kontekst raportu.
  Zachowanie jobów utrzymuje historię wejścia i wykonania bez dodawania osobnej
  tabeli odrzuceń.
- **Alternatives:** usunięcie tylko jednego znormalizowanego stagingu, usunięcie
  jobów, fizyczne usuwanie przez dowolny `importJobId` podany przez klienta albo
  nowa encja lifecycle stagingu.
- **Consequences:** aktywna walidacja tego samego importu oraz dataset wskazujący
  import lub którąkolwiek jego walidację blokują odrzucenie. Powtórzenie po
  udanym usunięciu zwraca zerowe liczniki. Nie jest potrzebna migracja; TASK-0049
  musi zapisać `source_job_id` tak, aby ochrona użycia pozostała skuteczna.

## D-048 — Atomic and idempotent publication from normalized import staging

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** zakończona walidacja `layout_import` bez blokad tworzy
  `dataset_versions` i `layouts` w jednej transakcji PostgreSQL. Dane są
  kopiowane setowym `INSERT ... SELECT`; wersja otrzymuje od razu status
  `published`, serwerowy timestamp i
  `source_job_id = validation_job_id`. Niepusty `source_job_id` chroni
  częściowy indeks unikalny. Import używa
  `generator_version = layout-import-v1` oraz neutralnego
  `generation_seed = 0`.
- **Context:** znormalizowany staging może zawierać około 500 000 rekordów i
  nie może zostać pobrany do procesu API. Publikacja musi użyć tej samej
  definicji gotowości co raport TASK-0047, wykluczyć wyścig z odrzuceniem i
  bezpiecznie przeżyć utratę odpowiedzi HTTP.
- **Reason:** blokada wspólnego joba importu i jego walidacji daje jedną granicę
  synchronizacji dla publikacji oraz usuwania. Blokada gry serializuje
  serwerowe `max(version) + 1`, a unikalne provenance zapewnia idempotencję.
  Atomowe utworzenie stagingowego rekordu, kopiowanie i przejście do
  `published` nie wystawia częściowego datasetu.
- **Alternatives:** materializacja layoutów w Pythonie, osobny długotrwały job
  kopiujący, tworzenie widocznego datasetu staging przed kopiowaniem,
  idempotencja wyłącznie w kodzie albo wskazanie surowego import joba jako
  provenance.
- **Consequences:** publikacja pozostawia staging jako audyt i blokuje jego
  późniejsze odrzucenie. Retry zwraca istniejący dataset. Payouty, snapshot i
  APK pozostają jawnymi kolejnymi operacjami; reprezentatywny test skali i
  pełny release należą do TASK-0050.

## D-049 — Conditional start of M5.1 before physical G3 evidence

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** po warunkowym ukończeniu M4 właściciel trzykrotnie polecił
  przejście do kolejnego zadania mimo jawnego przypomnienia o brakujących
  raportach urządzeniowych. Dopuszczone jest rozpoczęcie wyłącznie TASK-0051,
  ponieważ inwentaryzacja korpusu i golden annotations nie zmieniają adaptera
  mobile ani nie fałszują pomiarów G3. TASK-0041, TASK-0042 i G3 zachowują
  status `blocked`.
- **Context:** D-041 wymagała domknięcia fizycznych benchmarków po M4 i przed
  M5. Zweryfikowane APK benchmarkowe istnieje, ale ADB nie widzi telefonu, więc
  dowodów Pixel/Samsung nie można obecnie zebrać. M5.1 wymaga równolegle
  odpowiedzi Q-015–Q-017 oraz przygotowania materiału przez właściciela.
- **Reason:** korpus, prawa użycia, ground truth i progi są niezależnym,
  odwracalnym zakresem przygotowawczym. Ich wcześniejsze ustalenie nie wymaga
  wdrożenia OCR, geometrii ani zmiany runtime mobile.
- **Alternatives:** całkowite zatrzymanie prac do fizycznego G3 albo rozpoczęcie
  całego pipeline'u M5 bez spełnionych warunków wejścia.
- **Consequences:** TASK-0051 może rozpocząć dialog i przygotowanie kontraktów.
  Nie wolno uznać G3 za zaliczoną, rozpocząć M5.2 ani implementować automatycznej
  geometrii/OCR, dopóki odpowiednie bramki i wejścia nie zostaną jawnie
  spełnione albo właściciel nie podejmie kolejnej udokumentowanej decyzji.
- **Supersedes:** D-041 wyłącznie w zakresie dopuszczenia TASK-0051; wszystkie
  wymagania fizycznego G3 pozostają obowiązujące.

## D-050 — Provisional local corpus for M5.1

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** 12 zdjęć JPEG przekazanych przez właściciela w
  `examples/imgs/` tworzy korpus `m5-prototype-corpus-v1` do lokalnej pracy
  kontraktowej i prototypowej. Oryginały są ignorowane przez Git, nie wolno ich
  redystrybuować, a repozytorium przechowuje wyłącznie ścieżki względne,
  metadane i SHA-256. Korpus pozostaje `provisional` i nie zalicza G5.1.
- **Context:** właściciel potwierdził, że obecnie nie ma więcej zdjęć i polecił
  pracować na dostępnych plikach. Materiał obejmuje jedną grę, jedną sesję,
  jedną rozdzielczość 960 × 1280 i ciągłe numery 1–108.
- **Reason:** 12 unikalnych obrazów wystarcza do ustalenia wersjonowanych
  kontraktów manifestu, golden annotations, walidatora i pierwszego prototypu.
  Nie daje jednak podstaw do twierdzenia o jakości między grami, urządzeniami,
  rozdzielczościami i skrajnymi warunkami optycznymi.
- **Alternatives:** zatrzymanie całego M5.1 do zebrania 20–100 zdjęć albo
  obniżenie bramki reprezentatywności bez pomiarów.
- **Consequences:** Q-015 jest zamknięte odpowiedzią „12 obecnie dostępnych”.
  Q-016 i Q-017 pozostają otwarte. Adnotacje sekwencji mogą powstać od razu,
  natomiast pełna geometria, akceptacja progów i status
  `readyForGeometryBenchmark` wymagają dalszych ustaleń. Oryginalny cel
  20–100 reprezentatywnych zdjęć pozostaje warunkiem pełnego benchmarku G5,
  chyba że właściciel podejmie osobną decyzję na podstawie wyników prototypu.

## D-051 — Conditional image discovery before complete M5 entry gate

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** po zapowiedzi dostarczenia dalszych zdjęć właściciel polecił
  przejść do następnego zadania. Dopuszczone jest rozpoczęcie TASK-0052 na
  prototypowym korpusie D-050, ograniczone do read-only discovery, checksum,
  metadanych i manifestu źródłowego. TASK-0053 oraz geometria/OCR pozostają
  niedopuszczone do czasu kolejnego jawnego kroku i właściwych wejść.
- **Context:** TASK-0052 nie zależy od znajomości stałej siatki strony ani
  etykiet symboli. Jego kontrakt jest potrzebny także do bezpiecznego dołączania
  kolejnych zdjęć, które właściciel dostarczy później.
- **Reason:** deterministyczne wykrywanie plików, stabilna tożsamość po SHA-256
  i brak modyfikacji oryginałów są odwracalnym fundamentem niezależnym od
  jakości korpusu i wyboru algorytmu obrazu.
- **Alternatives:** zatrzymanie M5.2 do pełnego G5.1 albo rozpoczęcie całego
  pipeline'u mimo otwartych Q-016/Q-017.
- **Consequences:** TASK-0051 pozostaje `in_progress`, G3/G5.1 nie są zaliczone,
  a TASK-0052 nie może tworzyć wpisów PostgreSQL, obracać obrazów, generować
  kopii roboczych ani uruchamiać geometrii/OCR.
- **Supersedes:** D-049 wyłącznie w zakresie dopuszczenia read-only TASK-0052.

## D-052 — Conditional EXIF normalization on the provisional corpus

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** po ukończeniu TASK-0052 właściciel jawnie polecił rozpocząć
  następne zadanie. Dopuszczone jest TASK-0053 ograniczone do weryfikacji
  źródła, orientacji EXIF, lokalnych kopii roboczych i diagnostyki.
- **Context:** normalizacja nie wymaga odpowiedzi Q-016 o stałości geometrii
  strony ani Q-017 o zbiorze treningowym. Jest potrzebna przed każdym wariantem
  detektora, a jej poprawność dla Orientation 1–8 można wykazać syntetycznymi
  golden fixtures mimo braku tagu w obecnym korpusie.
- **Reason:** odseparowany adapter `image-normalization-v1` nie podejmuje decyzji
  o geometrii/OCR i nie zapisuje danych domenowych. Content-addressed artefakty
  oraz ponowna kontrola SHA-256 chronią oryginały i odtwarzalność.
- **Alternatives:** czekanie na pełny korpus albo łączenie normalizacji z
  detektorem strony.
- **Consequences:** można przypiąć Pillow i tworzyć lokalne RGB PNG poza
  katalogiem źródłowym. TASK-0054+ nadal wymaga kolejnego jawnego polecenia;
  G3, TASK-0051 i G5.1 pozostają otwarte.
- **Supersedes:** D-051 wyłącznie w zakresie dopuszczenia TASK-0053.

## D-053 — Supported 3 × 3 geometry variant before Q-016

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** po commicie M5.2 właściciel polecił przejść do następnego
  zadania bez odpowiedzi na Q-016. TASK-0054 może implementować wyłącznie
  wariant widoczny na obecnym korpusie: dokładnie dziewięć plansz w siatce
  3 × 3 z czerwonymi ramkami. Inna liczba lub nieregularny układ daje
  `needs_review/unsupported`, nigdy sztucznie dopełniony wynik.
- **Context:** detekcja bieżącego wariantu pozwala zmierzyć przydatność
  klasycznej geometrii, lecz brak odpowiedzi o innych grach nie pozwala uznać
  tego kontraktu za uniwersalny.
- **Reason:** jawne ograniczenie wariantu chroni indeksy i sequence order przed
  cichym przesunięciem, a port detektora pozwala później dodać konfigurację albo
  wymienić implementację bez zmiany dalszego pipeline'u.
- **Alternatives:** zatrzymanie do Q-016 albo ukryte założenie, że wszystkie gry
  mają identyczny ekran.
- **Consequences:** można użyć OpenCV/NumPy i tworzyć raporty/overlaye dla
  3 × 3. Nie wolno zaliczyć progu accuracy bez niezależnej pełnej geometrii
  golden ani rozpocząć TASK-0055 bez kolejnego polecenia. Q-016 pozostaje
  otwarte.
- **Supersedes:** D-052 wyłącznie w zakresie dopuszczenia TASK-0054.

## D-054 — Canonical board and cell crop contract for the supported variant

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** na kolejne jawne polecenie właściciela TASK-0055 może
  indywidualnie prostować dziewięć plansz wariantu D-053. Kontrakt
  `board-cell-crops-v1` mapuje każdy quad do RGB 500 × 300, odcina po 5%
  szerokości/wysokości z każdej strony i dzieli wnętrze na 3 × 5 komórek
  RGB 90 × 90. Indeksy planszy, wiersza i kolumny są 0-based oraz row-major.
- **Context:** jeden globalny warp nie kompensuje krzywizny ekranu. Stały
  kanoniczny wymiar i jawny margines dają deterministyczny kontrakt wejścia dla
  przyszłego klasyfikatora bez uzależnienia go od rozdzielczości źródła.
- **Reason:** 500 × 300 zachowuje proporcję siatki 5:3, a margines 5% daje bez
  resamplingu dokładne komórki 90 × 90. Każda transformacja oraz checksum
  pozostają audytowalne.
- **Alternatives:** zmienny rozmiar wynikowy, jeden warp strony albo wycinanie
  osiowych bounding boxów bez korekty perspektywy.
- **Consequences:** można tworzyć wycinki tylko dla kompletnego, wykrytego
  wyniku TASK-0054. Inny wariant lub niepoprawny quad daje `needs_review`;
  nie wolno rozpoczynać OCR ani deklarować accuracy/G5.3 bez osobnego zadania
  i niezależnych golden annotations. Q-016 pozostaje otwarte.
- **Supersedes:** D-053 wyłącznie w zakresie dopuszczenia TASK-0055.

## D-055 — Local PP-OCRv5 recognition runtime without PaddleX

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** pierwszy adapter `SequenceNumberRecognizer` używa oficjalnego
  modelu recognition-only `en_PP-OCRv5_mobile_rec` przez CPU runtime
  PaddlePaddle `3.3.1`, bez instalowania pakietów orkiestracyjnych PaddleOCR
  i PaddleX. Model jest przygotowywany wcześniej w jawnym lokalnym katalogu,
  identyfikowany checksumami, a worker nigdy nie pobiera wag podczas przebiegu.
  Wersjonowany preprocessing wycina jasny komponent numeru, a dekoder CTC
  dopuszcza wyłącznie blank i cyfry `0–9`.
- **Context:** instalacja `paddleocr==3.7.0` wprowadzała
  `opencv-contrib-python==4.10.0.84` oraz ograniczenie NumPy do `<=2.3.5`, co
  kolidowało z przypiętym stosem geometrii OpenCV `4.13.0.92` / NumPy `2.4.6`.
  Warstwa PaddleOCR może też pobierać model, jeżeli nie wskaże się lokalnych
  katalogów. Bezpośredni runtime Paddle Inference poprawnie otwiera oficjalne
  pliki `inference.json`, `inference.pdiparams` i `inference.yml`.
- **Reason:** osobny port zachowuje granicę D-010, usuwa konflikt przestrzeni
  `cv2`, gwarantuje offline runtime i pozwala zmienić model po benchmarku bez
  zmiany raportu, stagingu ani manual review.
- **Alternatives:** instalacja całego PaddleOCR/PaddleX kosztem cofnięcia
  OpenCV/NumPy, Tesseract z dodatkowym systemowym runtime albo własny model
  przed zebraniem reprezentatywnego korpusu.
- **Consequences:** repo przypina `paddlepaddle==3.3.1` i `PyYAML==6.0.3`.
  Lokalny model nie jest commitowany. Raport zapisuje wersję runtime, nazwę
  modelu, checksumy plików, fingerprint i politykę dekodera. Baseline
  `68/108 = 62.9630%` nie spełnia proponowanego progu 98%, dlatego nie zalicza
  G5.4 i musi być jawnie oceniony w TASK-0057/TASK-0058.
- **Supersedes:** D-010 wyłącznie w zakresie mechanizmu pierwszej implementacji
  OCR; wymienny port, praca offline i obowiązek benchmarku pozostają bez zmian.

## D-056 — Retain image contracts, rework OCR, and hold M6

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** prototyp M5 kończy się wynikiem `completed_with_rework`, bez
  zaliczenia G5. Zachowujemy lokalny model workera, łańcuch checksum,
  content-addressed artefakty i wersjonowane kontrakty discovery, normalizacji,
  geometrii, cropów, OCR oraz benchmarku. `page-board-detector-v1` i
  `board-cell-crops-v1` pozostają eksperymentalne poza wspieranym wariantem
  dziewięciu plansz 3 × 3. Port `SequenceNumberRecognizer` oraz raport
  `sequence-number-ocr-v1` zostają, ale implementacja
  `en_PP-OCRv5_mobile_rec` z `bright-component-tight-v1` ma status `rework`
  i nie może automatycznie akceptować numerów.
- **Context:** TASK-0057 zmierzył 100% detekcji strony i kompletu plansz na 12
  zdjęciach jednej gry/sesji, lecz bez niezależnych golden pozycji i narożników.
  OCR osiągnął `68/108 = 62.9630%`, konflikt ciągłości `51/108 = 47.2222%`,
  a pięć błędnych wyników miało confidence `>= 0.8`. Kontrola surowego cropu
  była gorsza: `46/108 = 42.5926%`. Korpus nie osiąga minimum 20 zdjęć, progi
  są `proposed`, a Q-016/Q-017 pozostają otwarte.
- **Reason:** poprawne granice i audytowalność pipeline'u nie zależą od jakości
  konkretnego modelu. Jednocześnie wysoki confidence nie odróżnia bezpiecznie
  błędów, więc automatyczna publikacja obecnego OCR naruszałaby integralność
  `sequence_number`. Wynik jednego wariantu nie uzasadnia ciężkiego detektora
  ani deklaracji generalizacji.
- **Alternatives:** zaakceptowanie 62.9630% wraz z ręcznym czyszczeniem,
  ciche poprawianie numerów przez continuity, rozpoczęcie M6 mimo niezaliczonego
  G5, natychmiastowe dodanie większego OCR/detektora albo odrzucenie wszystkich
  kontraktów M5.
- **Consequences:** do czasu reworku każdy numer OCR jest wyłącznie sugestią do
  manual review; nie istnieje próg auto-accept. M4 pozostaje bezpiecznym
  sposobem wprowadzania danych. TASK-0051 ma status `blocked` na dodatkowym
  materiale i odpowiedziach Q-016/Q-017. M6 nie rozpoczyna się, dopóki:
  1. korpus nie ma co najmniej 20 reprezentatywnych zdjęć z opisanymi wariantami,
  2. niezależne goldeny pozycji/narożników nie pozwalają zmierzyć geometrii,
  3. progi nie zostaną zaakceptowane przed kolejną optymalizacją,
  4. OCR nie przejdzie zaakceptowanego progu na held-out source images,
  5. Q-017 nie potwierdzi wystarczającego materiału symboli.
     Rework porównuje wyspecjalizowane alternatywy cyfr na podziale według zdjęcia,
     bez strojenia i raportowania na tych samych 12 goldenach. Czas cropów jest
     obserwowany, ale nie optymalizowany bez zaakceptowanego budżetu.
- **Supersedes:** D-053–D-055 wyłącznie w zakresie statusu po benchmarku;
  kontrakty, ograniczenie wariantu, lokalność i checksumy pozostają w mocy.

## D-057 — Variable final page and manual-review-only OCR open M6

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** strona zawiera od 1 do 9 layoutów w kolejności row-major.
  Wszystkie strony poza ostatnią wymagają dziewięciu pozycji; tylko jawnie
  wskazana ostatnia strona znanego ciągu może mieć 1–8 pozycji bez luk.
  `page-board-detector-v2` może odzyskać geometrię siatki wyłącznie przy
  znanym `expectedBoardCount` i wystarczającym dowodzie czerwonej ramki.
  Korpus 43 zdjęć / 387 layoutów, zweryfikowana geometria i automatyczne cropy
  zaliczają G5 dla wejścia do M6. OCR pozostaje w trybie
  `manual_review_only`; próg 98% nadal obowiązuje przed włączeniem auto-accept.
- **Context:** właściciel zamknął Q-016/Q-017, dodał 31 zdjęć w różnej jakości
  i potwierdził możliwość uzyskania około 100 przykładów na symbol. Pipeline
  utworzył 387 board crops i 5805 cell crops. Detektor osiągnął 43/43 stron,
  komplet oczekiwanych pozycji i zero nierozwiązanych elementów geometrii.
  OCR osiągnął `247/387 = 63.8243%`, a na 31 held-out source images
  `179/279 = 64.1577%`; nie spełnia progu auto-accept.
- **Reason:** eksport datasetu symboli M6 może korzystać z wizualnie
  przejrzanych numerów golden i zweryfikowanych cropów, dlatego nie zależy od
  automatycznej akceptacji OCR. Blokowanie klasyfikatora symboli do czasu
  osiągnięcia 98% OCR mieszałoby dwie wymienne części pipeline'u. Jednocześnie
  obniżenie progu lub użycie continuity do cichego poprawiania numerów byłoby
  niebezpieczne.
- **Consequences:** TASK-0051 i TASK-0092 mogą zostać zamknięte, G5 otrzymuje
  status `passed_manual_review_only_ocr`, a TASK-0059 może się rozpocząć.
  Właściciel nie wycina ręcznie obrazów: worker generuje board/cell crops.
  Ręczna praca w M6 dotyczy zatwierdzania lub poprawiania etykiet symboli.
  Każdy numer z OCR nadal wymaga zatwierdzenia i nie może samodzielnie trafić
  do publikowanego datasetu.
- **Supersedes:** D-056 w zakresie blokady wejścia do M6 i dokładnie
  dziewięciu plansz na każdej stronie. D-056 nadal obowiązuje dla braku
  auto-accept, audytowalności i wymiennego adaptera OCR.

## D-058 — Reviewed cell decisions bootstrap the symbol dataset

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** M6 używa dwóch oddzielnych kontraktów:
  `symbol-crop-inventory-v1` opisuje wszystkie zweryfikowane cropy bez
  przypisywania klasy, a `reviewed-cell-labels-v1` zawiera wyłącznie jawne
  decyzje `accepted/rejected` administratora. `labeled-symbol-dataset-v1`
  eksportuje tylko decyzje `accepted`. OCR, continuity, dane fixture i
  niezatwierdzona sugestia klasyfikatora nie mogą tworzyć etykiety.
- **Context:** pipeline M5 utworzył 5805 cropów i przejrzane numery 1–387, ale
  repozytorium nie zawiera prawdziwych rekordów layoutów odpowiadających tym
  zdjęciom. Snapshoty M1/M4 zawierają dane testowe lub benchmarkowe i ich
  symbole nie opisują fotografowanego ekranu.
- **Reason:** przypisanie danych fixture do rzeczywistych cropów zatrułoby
  dataset treningowy. Rozdzielenie inwentarza od decyzji człowieka pozwala
  automatycznie przygotować pliki, zachować audyt i później użyć interfejsu
  wspomagającego etykietowanie bez zmiany kontraktu eksportu.
- **Consequences:** każdy sample ma stabilne ID wyprowadzone z korpusu,
  źródłowego obrazu, zatwierdzonego numeru, pozycji i checksumy cropu.
  Identyczne bajty są materializowane raz, ale wszystkie wystąpienia pozostają
  w manifeście. Brak decyzji pozostaje `pending`; duplikat, nieznany symbol,
  drift lub dwie etykiety dla identycznych bajtów blokują eksport. TASK-0059
  nie jest ukończone, dopóki nie powstanie pierwsza przejrzana wersja etykiet.

## D-059 — Cell-grid v2 gates symbol labeling and batch active learning

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** `board-cell-crops-v1` nie może zasilać etykietowania ani
  treningu. Po wyprostowaniu planszy 500 × 300 cropper v2 najpierw tworzy
  piętnaście slotów 100 × 100, a następnie stosuje wersjonowany inset wewnątrz
  każdego slotu. Poprawność mierzy niezależny `cell-grid-golden-v1`. Gdy równy
  profil nie przechodzi goldenu, administrator koryguje cztery linie pionowe i
  dwie poziome dla wersjonowanego zakresu kalibracji, nie dla każdego layoutu.
  Etykietowanie odbywa się na pełnej planszy 5 × 3. Model uczy się wyłącznie
  batchowo z jawnej wersji datasetu; active learning priorytetyzuje niepewne
  przypadki, a auto-accept wymaga kalibracji held-out.
- **Context:** podczas pierwszej rzeczywistej sesji bootstrap review właściciel
  stwierdził, że 5805 cropów jest przeciętych względem symboli. Inspekcja kodu
  i overlayów potwierdziła, że v1 usuwa globalnie 25/15 px, a potem stosuje
  krok 90 px zamiast zachować logiczny krok 100 px. Golden quadów planszy
  weryfikował położenie plansz, ale nie granice piętnastu komórek.
- **Reason:** etykietowanie wadliwych cropów zatrułoby dataset, a uczenie modelu
  nie naprawi systematycznego błędu geometrii. Niezależny golden zapobiega
  ponownemu zatwierdzeniu algorytmu jego własnym wynikiem. Pełnolayoutowy review
  i active learning ograniczają pracę właściciela bez utraty audytu.
- **Alternatives:** oznaczenie wszystkich 5805 cropów mimo błędu, ręczne
  wycinanie każdej komórki, ręczne linie dla każdego layoutu, model uczący się
  online po każdym kliknięciu albo jeden model rozpoznający całe zdjęcie.
- **Consequences:** G5 zostaje ponownie otwarte wyłącznie dla granic komórek,
  M6.1 jest wstrzymane, a v1 pozostaje historycznym artefaktem bez prawa do
  treningu. Prace dzielą się na TASK-0094–0097; TASK-0061–0063 przejmują
  batch training, ONNX, kalibrację i wybór active-learning. Stabilne
  `observationId` jest oddzielone od zależnego od croppera `cropSampleId`.
- **Supersedes:** D-057 w zakresie akceptacji cell crops i wejścia M6 do
  etykietowania oraz D-058 w zakresie tożsamości sample zależnej wyłącznie od
  checksumy. D-057 nadal obowiązuje dla geometrii plansz i
  `manual_review_only` OCR; D-058 nadal obowiązuje dla jawnych decyzji,
  deduplikacji i zakazu użycia fixture/OCR jako etykiet.

## D-060 — Source-quad golden precedes canonical cell-grid cuts

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** niezależny golden TASK-0094 zapisuje ręcznie zaakceptowany
  czworokąt rzeczywistej ramy planszy w układzie współrzędnych oryginalnego
  zdjęcia. Edytor pokazuje na zdjęciu ukośną siatkę perspektywiczną 5 × 3
  wyprowadzoną z czterech narożników oraz generowany na żywo kanoniczny podgląd
  500 × 300 i 15 komórek. Wewnętrzne granice kanonicznej planszy pozostają
  równe 100 × 100. Nie zapisujemy sześciu dowolnych ukośnych linii na
  historycznym `board.png`.
- **Context:** pierwsza plansza rzeczywistego review ujawniła, że linie są
  osiowe, ale symbole pozostają skośne. Detektor wskazał lewy górny narożnik
  około `(122, 408)`, podczas gdy widoczna rama zaczyna się bliżej
  `(117, 399)`. Historyczny warp przyciął część planszy i pozostawił
  resztkową perspektywę. Dotychczasowy pending golden miał `0/27` akceptacji,
  `reviewRevision = 0` i żadnych szkiców.
- **Reason:** korygowanie linii dopiero na przyciętym boardzie utrwalałoby błąd
  wcześniejszego quadu i nie odzyskałoby utraconych pikseli. Cztery narożniki
  są najmniejszą wystarczającą adnotacją dla planarnej, regularnej siatki;
  homografia jednocześnie koryguje obrót, skalę i perspektywę, a reviewer nadal
  ocenia wszystkie 15 wynikowych komórek.
- **Alternatives:** sześć niezależnych odcinków na historycznym boardzie,
  ręczne ustawianie 24 skrzyżowań siatki albo akceptacja prostych linii mimo
  widocznego skosu.
- **Consequences:** `cell-grid-golden-v1` przechodzi przed pierwszą decyzją
  człowieka z osiowych współrzędnych boardu na `sourceQuad` w pikselach zdjęcia.
  Historyczny baseline mierzy zarówno błąd narożników detektora, jak i pozycję
  jego linii v1 po odwzorowaniu do kanonicznego układu goldenu. TASK-0095
  zastosuje zaakceptowany sposób rectyfikacji przed insetem per komórka.
- **Supersedes:** D-059 w zakresie założenia, że zaakceptowany quad planszy jest
  wystarczający i że fallback polega na sześciu liniach w historycznym
  `board.png`. Kwarantanna v1, niezależny golden, cropy 100 × 100 plus inset i
  batchowe uczenie pozostają bez zmian.

## D-061 — Sequence-anchored source-quad calibration profiles

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** `grid-calibration-profiles-v1` ma dokładnie jeden niezmienny
  profil dla pary `source_group + board_position`. Każdy z 27 zaakceptowanych
  quadów TASK-0094 jest kotwicą zawierającą korektę czterech narożników w
  lokalnej bazie aktualnego quadu detektora. Dla planszy pomiędzy dwiema
  kotwicami korekta jest interpolowana liniowo po domenowym `sequence_number`;
  poza zakresem stosuje się najbliższą kotwicę bez ekstrapolacji. Profil z jedną
  kotwicą stosuje stałą korektę. Regeneracja konsumuje opublikowany profil,
  zapisuje jego tożsamość w osobnym artefakcie i nie odczytuje goldenu jako
  bezpośredniego override'u.
- **Context:** detector-only cropper v2 zachował prawidłowy krok 100 px, ale na
  27 ręcznie poprawionych planszach uzyskał P95 linii `42.1563 px`. Korpus ma
  dwie spójne sesje źródłowe i dziewięć pozycji; 27 zaakceptowanych korekt daje
  18 zakresów kalibracji i od jednej do dwóch kotwic na zakres.
- **Reason:** lokalne współrzędne korekty są niezależne od skali obrazu,
  zachowują perspektywę quadu i dają się zastosować do wszystkich 387 plansz.
  Interpolacja po kolejności modeluje stopniowy dryf sesji, a clamp zapobiega
  niekontrolowanej ekstrapolacji. Profil pozostaje audytowalny i nie wymaga
  ręcznej korekty każdej planszy.
- **Alternatives:** średnia korekta na zakres nie spełnia budżetu jakości
  (wstępny P95 narożników `13.0096 px`), profile per layout odtwarzają ręczną
  pracę 387 razy, a dowolne linie na historycznym boardzie nie odzyskują
  pikseli utraconych przez błędny quad.
- **Consequences:** profil obowiązuje wyłącznie dla jawnej grupy źródłowej i
  pozycji. Nowa sesja wymaga nowych kotwic i wersji profilu. Przejście goldenu
  obecnych dwóch sesji nie jest deklaracją uogólnienia na inne urządzenie,
  automat lub sposób fotografowania.

## D-062 — Per-source local-frame calibration and disjoint geometry gate

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** korekta geometrii planszy jest liczona na lokalnej bazie
  `boundingBox` tej samej planszy i kalibrowana wyłącznie kotwicą z dokładnie
  tego samego obrazu źródłowego. Brak kotwicy dla obrazu daje `needs_review`;
  nie wolno użyć korekty innego zdjęcia, pozycji ani odległego
  `sequence_number`. Metryki plansz użytych jako kotwice są raportowane jako
  `anchor fit`, ale bramka generalizacji korzysta wyłącznie z rozłącznych
  plansz held-out oraz przeglądu kompletnej strony. Zmiana geometrii tworzy
  nowy `cropSampleId`; istniejąca etykieta nie przechodzi automatycznie na nowy
  crop.
- **Context:** podczas rzeczywistego etykietowania plansza 1 była czytelna,
  natomiast kolejne plansze tego samego zdjęcia zostały przycięte. Sekwencja 2
  użyła jedynej kotwicy pozycji 1 z sekwencji 74, a sekwencja 3 kotwicy z
  sekwencji 66. Raport P95 `1.8337 px` sprawdzał te same 27 plansz, które były
  wejściem profili, więc nie mierzył pozostałych 360 plansz. Diagnostyka na
  pierwszym zdjęciu potwierdziła, że lokalna baza ramki plus jedna korekta tego
  zdjęcia zachowuje symbole plansz 1–3.
- **Reason:** położenie ramki jest obserwacją lokalną dla zdjęcia, podczas gdy
  numer sekwencji nie opisuje perspektywy aparatu. Rozłączny held-out zapobiega
  ponownemu zaliczeniu algorytmu na jego danych kalibracyjnych. Jedna kotwica
  na zdjęcie ogranicza ręczną pracę do maksymalnie 43 korekt zamiast 387.
- **Alternatives:** dalsze klamrowanie po sekwencji, ręczna korekta wszystkich
  plansz, trening klasyfikatora na błędnych cropach albo automatyczna migracja
  56 istniejących etykiet na nowe obrazy.
- **Consequences:** D-061 i `board-cell-crops-v2-calibrated-v1` pozostają
  historyczne, ale tracą prawo do zasilania treningu. TASK-0098 przygotowuje
  profile obrazu, nową wersję cropów i uczciwą bramkę; TASK-0099 dodaje
  sugestie dopiero po zaakceptowaniu geometrii. Dwadzieścia siedem obrazów ma
  już po jednej kotwicy, a szesnaście wymaga jej dodania. Istniejące decyzje
  pozostają audytowalne dla starych `cropSampleId`.
- **Supersedes:** D-061 w zakresie produkcyjnego użycia profili
  `source_group + board_position`, interpolacji/clamp po sekwencji oraz
  zaliczenia G5.3 na anchorach. Niezmienność artefaktów, lokalne współrzędne
  korekty i zakaz nadpisywania pozostają w mocy.

## D-063 — Symbol-aware per-board grid refinement

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** produkcyjna geometria komórek rozpoczyna od quadu detektora
  wyznaczonego osobno dla każdej planszy, a następnie lokalizuje środek symbolu
  w każdym z 15 przybliżonych slotów. Z wiarygodnych środków dopasowuje
  odporną korektę afiniczną do logicznej siatki 5 × 3. Transform musi spełnić jawne
  progi pokrycia, liczby inlierów, residualu, wypukłości, granic obrazu i
  maksymalnego przesunięcia. Niepowodzenie nie publikuje cropów: cała strona
  otrzymuje `needs_review`, a odrzucona plansza trafia do małej kolejki ręcznej
  korekty exact-observation. Progów globalnych nie obniżamy. Quad detektora
  pozostaje ograniczeniem obszaru wyszukiwania, lecz nie jest samodzielnym
  źródłem finalnych granic komórek.
- **Context:** ręczna kolejka TASK-0098 zakończyła się `25/25`, jednak
  właściciel nadal obserwował przecięcia symboli. Wszystkie 9 plansz held-out
  miało zgłoszony problem. Spike TASK-0100 używający wszystkich 15 środków
  obniżył medianę odchylenia na held-out z `6.6964 px` do `2.0441 px`, znalazł
  komplet środków na 25 planszach i został zaakceptowany wizualnie przez
  właściciela.
- **Reason:** sama rama opisuje perspektywę planszy, ale nie gwarantuje
  położenia wizualnych symboli wewnątrz slotów. Użycie 15 punktów jest
  odporniejsze od samych czterech narożników na zasłonięcia, nietypowy kształt
  pojedynczego symbolu i lokalny szum.
- **Alternatives:** dalsze użycie wyłącznie ramy, dopasowanie tylko czterech
  symboli narożnych, ręczna korekta 387 plansz albo trening na cropach z
  przeciętymi symbolami.
- **Consequences:** powstaje nowy namespace profili i cropów. Każdy rekord
  planszy zachowuje wersję refinera, coverage, inliery i residual. Wynik nie
  migruje starych etykiet i nadal wymaga bramki wizualnej stron przed
  `trainingAllowed = true`. Pełny benchmark wyznaczył automatycznie `381/387`
  plansz, a 6 plansz (`11`, `33`, `123`, `172`, `266`, `337`) skierował do
  ręcznej korekty. Próba użycia jednej korekty ramy exact-image jako geometrii
  startowej została odrzucona po kontroli wizualnej, ponieważ przesuwała dolne
  rzędy plansz w innych pozycjach tej samej strony.
- **Supersedes:** D-062 w zakresie założenia, że jedna korekta ramy zdjęcia
  wystarcza do wyznaczenia finalnych granic komórek. Exact-source scope,
  rozłączny held-out, fail-closed i niezmienność artefaktów pozostają w mocy.

## D-064 — Guarded projective transform from the complete symbol lattice

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** nowy kandydat geometrii najpierw rozszerza quad detektora w jego
  własnym układzie projektowym, a następnie traktuje środki symboli z całej
  planszy jako jeden przypisany zbiór siatki 5 × 3. Homografia
  ideal-to-observed jest dopasowywana przez RANSAC i ponownie liczona na
  inlierach. Cztery wirtualne narożniki siatki wynikają z tego transformu, a
  nie z czterech potencjalnie zasłoniętych symboli skrajnych. Wynik wymaga co
  najmniej 10 wiarygodnych kandydatów, 9 inlierów, pokrycia wszystkich 3 rzędów
  i 5 kolumn, P95 residualu inlierów najwyżej `10 px` oraz jawnych guardów
  wypukłości, pola, marginesu ramki i odstępów. Niespełnienie dowolnego warunku
  daje kontrolowany fallback.
- **Context:** właściciel odrzucił v9 na sekwencji 29, ponieważ osiowy szeroki
  bounding box usunął widoczne nachylenie planszy. Projektowe rozszerzenie v11
  zachowało perspektywę. Na jego wyniku estymator
  `symbol-lattice-homography-ransac-v1` znalazł `14/15` wiarygodnych kandydatów,
  13 inlierów obejmujących 3 × 5 i P95 `7.6869 px`; błędny środek górnego rzędu
  nie steruje narożnikami.
- **Reason:** homografia modeluje perspektywę, której transform afiniczny ani
  osiowy mesh nie mogą odtworzyć. Użycie wszystkich inlierów ogranicza wpływ
  zasłoniętej kontrolką komórki, nietypowego symbolu lub lokalnego szumu.
- **Alternatives:** dalsze strojenie odrzuconego osiowego v9, homografia z
  samych czterech symboli narożnych, zewnętrzne ręczne linie per plansza albo
  natychmiastowa zmiana biblioteki. OpenCV 4.13 zapewnia już wymagany,
  zweryfikowany prymityw.
- **Consequences:** affine v7–v9 i ich artefakty pozostają niezmienną historią,
  ale nie mogą zasilać treningu. Krok 2 publikuje tylko estymator i diagnostykę;
  nie publikuje cropów. Rectyfikacja, stały padding i mała bramka regresji na
  `29`, `4`, `6`, `7`, `26`, `30` oraz kontrolach są obowiązkowym krokiem 3
  przed jakimkolwiek pełnym przebiegiem 387 plansz. `trainingAllowed` pozostaje
  `false`.
- **Supersedes:** D-063 w zakresie transformu afinicznego jako docelowego
  kandydata granic komórek. Per-board scope, wykorzystanie wielu środków,
  fail-closed, rozłączny held-out i niezmienność artefaktów pozostają w mocy.

## D-065 — Globalne przypisanie symboli i source-aware fixed padding

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** kandydat produkcyjnej geometrii nie może proponować niezależnego
  środka w każdym przybliżonym slocie. Najpierw tworzy globalny zbiór
  komponentów symboli, wspólnie wyznacza pięć kolumn i trzy rzędy, a następnie
  przypisuje najwyżej jeden komponent do slotu 5 × 3. Dopiero przypisany slot
  może być wiarygodną obserwacją homografii. Rozszerzona plansza 500 × 300 jest
  płaszczyzną analizy, nie granicą dostępnych pikseli. Finalny transform składa
  `ideal -> analysis -> normalized source`, a stały padding jest pobierany
  bezpośrednio z realnego źródła. Każdy padded crop nadal wymaga wszystkich
  narożników w granicach źródła i support fraction `1.0`.
- **Context:** v12 technicznie przepuściło `4` i `26`, ale ich pierwsze kolumny
  były przecięte, ponieważ slot-local locator wybrał czerwoną ramę około
  `x = 55` zamiast globalnej kolumny symboli około `x = 99`. Na sekwencji 29
  poprawny dolny lewy narożnik siatki wypada około `(42.84, 329.41)` w
  płaszczyźnie analizy, mimo że wymagane piksele istnieją w oryginalnym
  zdjęciu. Ograniczanie go do `y <= 300` odtwarzało przycięcie.
- **Reason:** globalne przypisanie usuwa systematyczny błąd całej kolumny,
  którego RANSAC nie może odróżnić od poprawnego modelu. Kompozycja do źródła
  oddziela obszar użyty do detekcji od fizycznego dowodu dostępności pikseli.
  Zachowuje to fail-closed bez wymuszania błędnych środków i bez syntetycznego
  uzupełniania obrazu.
- **Alternatives:** dalsze strojenie slot-local saliency, obniżenie progów
  RANSAC, zwiększenie statycznego quadu wszystkich plansz, border replication
  albo zmiana biblioteki. Statyczne poszerzenie nie odzyskało bezpiecznie
  kontroli `3` i `11`, a OpenCV zapewnia wystarczające prymitywy.
- **Consequences:** powstają wersje
  `global-bright-component-lattice-assignment-v1`,
  `symbol-lattice-homography-ransac-v2-global-assignment-v1` i
  `board-cell-crops-v13-global-lattice-source-aware-fixed-padding-preflight-v1`.
  Progi liczby punktów, inlierów, coverage i residualu pozostają bez zmian.
  Guard pola i marginesu dotyczy teraz bounded ekstrapolacji w sztucznej
  płaszczyźnie analizy; ostateczną granicą jest ścisły preflight realnego
  źródła. Regresja poprawia wynik z `13/20` do `18/20` i odzyskuje wszystkie
  zgłoszone sekwencje, lecz `3` i `11` pozostają fail-closed. Pełny korpus,
  publikacja datasetu i trening nadal są zabronione.
- **Supersedes:** D-064 w zakresie slot-local źródła kandydatów i traktowania
  expanded 500 × 300 jako finalnej granicy pikseli. Guarded RANSAC, pełne
  coverage, stały padding, niezmienność artefaktów i fail-closed pozostają w
  mocy.

## D-066 — Bounding box wyłącznie jako awaryjna płaszczyzna analizy

- **Status:** accepted
- **Date:** 2026-07-28
- **Decision:** po błędzie
  `GLOBAL_SYMBOL_LATTICE_INSUFFICIENT_COMPONENTS`,
  `GLOBAL_SYMBOL_LATTICE_AXIS_ASSIGNMENT_FAILED` albo
  `GLOBAL_SYMBOL_LATTICE_INSUFFICIENT_ASSIGNMENTS` kandydat v14 może wykonać
  dokładnie jeden retry na płaszczyźnie analizy wyprowadzonej z `boundingBox`
  detektora z paddingiem `6%` w poziomie i `4%` w pionie. Bounding box nie jest
  finalną geometrią komórek. Retry musi ponownie wykonać globalne przypisanie
  5 × 3, guarded RANSAC, kompozycję do znormalizowanego źródła i preflight
  support fraction `1.0`. Każdy inny błąd pozostaje fail-closed.
- **Context:** v13 odzyskało wszystkie sekwencje zgłoszone przez właściciela,
  ale kontrola `3` miała zniekształcony projektowy quad detektora, który
  odcinał część siatki, a kontrola `11` dostarczała tylko osiem przypisań.
  Dalsze rozszerzanie tego samego quadu nie odzyskało kompletnej siatki.
  Szersza prostokątna płaszczyzna analizy odzyskała odpowiednio 13 i 12
  przypisań, po czym finalna homografia zachowała po 12 inlierów oraz P95
  `4.3133 px` i `4.3328 px`.
- **Reason:** lokalizator potrzebuje zobaczyć całą siatkę, ale rama detektora
  nie powinna sterować granicami cropów. Rozdzielenie awaryjnego obszaru
  wyszukiwania od finalnej homografii zachowuje perspektywę, pełne coverage
  i dowód realnych pikseli bez obniżania progów.
- **Alternatives:** obniżenie progów RANSAC, bezwarunkowe używanie bounding boxu,
  ręczny override dwóch kontroli, syntetyczne piksele albo natychmiastowa
  zmiana biblioteki. Żadna z tych opcji nie daje równie małego i audytowalnego
  rozszerzenia istniejącego kontraktu OpenCV.
- **Consequences:** powstaje
  `board-cell-crops-v14-global-lattice-source-aware-bbox-analysis-fallback-v1`.
  Ograniczona regresja przechodzi technicznie `20/20`; tylko `3` i `11`
  korzystają z retry, a pozostałe 18 kart ma te same checksumy co v13. Status
  pozostaje `waiting_for_owner_review`, a pełny korpus i trening są zabronione
  do jawnej akceptacji galerii.
- **Supersedes:** D-065 wyłącznie w zakresie braku ścieżki dla kontroli `3`
  i `11`. Globalne przypisanie, source-aware fixed padding, niezmienione guardy,
  niezmienność artefaktów i fail-closed pozostają w mocy.

## D-067 — Exact-observation override dla fallbacków pełnego preflightu v14

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** dokładnie 14 plansz odrzuconych przez pełny preflight v14 trafia
  do osobnej kolejki ręcznej geometrii. Dla każdej obserwacji właściciel ustawia
  cztery narożniki kompletnej siatki symboli 5 × 3 na oryginalnym zdjęciu i
  zatwierdza podgląd wszystkich 15 komórek. Override jest wiązany przez checksum
  obrazu źródłowego i `position_index`; nie może być przeniesiony na inną
  planszę ani zmienić `sequence_number`.
- **Context:** v14 automatycznie utworzyło poprawne cropy dla 373/387 plansz,
  natomiast 14 plansz pozostało fail-closed w pięciu rodzinach błędów. Właściciel
  zaakceptował rozmieszczenie grafik w diagnostyce i wybrał szybką ręczną
  korektę pozostałych 14 zamiast kolejnego globalnego strojenia progów.
- **Reason:** 14 jawnych korekt jest małym, audytowalnym wyjątkiem. Pozwala
  zachować niezmienione guardy automatyczne i nie naraża 373 poprawnych plansz
  na regresję.
- **Alternatives:** dalsze strojenie globalnego lokalizatora, obniżenie progów
  RANSAC albo ręczna korekta całego korpusu. Pierwsze dwie opcje zwiększają
  ryzyko false accept, a trzecia niepotrzebnie powtarza 373 poprawne wyniki.
- **Consequences:** powstaje niezależny dokument
  `v14-projective-fallback-review-v1` obejmujący wyłącznie sekwencje `33`, `38`,
  `123`, `163`, `203`, `237`, `254`, `255`, `325`, `333`, `334`, `335`, `346`
  i `379`. Dopiero `14/14` zaakceptowanych korekt może zasilić nową wersję
  croppera oraz ponowny pełny preflight `387/387`. Sam dokument review nie
  zezwala na trening. Po akceptacji korekt v16 zachowuje bajtowo 373 poprawne
  wyniki v14 i generuje tylko 14 ręcznych obserwacji. Dwa przebiegi v16 dały
  identyczny raport SHA-256
  `c336a872388d35a4bb28a15626565906cd105345577919f0c6a3b251841ac5b9`,
  `387/387` plansz, `5805/5805` komórek i zero fallbacków. Końcowy page-level
  review nadal blokuje trening.
- **Supersedes:** D-066 wyłącznie dla 14 plansz odrzuconych przez pełny preflight.
  Automatyczna ścieżka v14, niezmienne artefakty i fail-closed pozostają w mocy.

## D-068 — Zaakceptowany v16 jako jedyne źródło dalszego etykietowania

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** właściciel zaakceptował kompletny wynik v16 i zezwolił na
  przejście dalej. Dalsze review oraz eksport używają
  `symbol-crop-inventory-v3`, który wiąże dokładny raport v16, dokument
  akceptacji właściciela i checksumy wszystkich 387 plansz oraz 5805 komórek.
  Historyczne 56 decyzji z v2 nie jest migrowane automatycznie, ponieważ
  `cropSampleId` identyfikuje również wersję geometrii i bajty cropu.
- **Context:** v16 przeszedł dwa identyczne przebiegi techniczne, a właściciel
  zakończył kontrolę 14 ręcznych korekt i zaakceptował dalszą pracę.
- **Reason:** jawne rozdzielenie inwentarzy zapobiega przypisaniu starej etykiety
  do zmienionego obrazu, a jednocześnie zachowuje stabilne `observationId` do
  porównań i audytu.
- **Alternatives:** dalsze użycie wycofanego v2 albo automatyczna migracja po
  pozycji komórki. Obie opcje omijają kontrolę dokładnej wersji obrazu.
- **Consequences:** v2 i jego 56 decyzji pozostają historycznym dowodem.
  Nowy plik decyzji v16 startuje z tą samą konfiguracją ośmiu symboli, lecz z
  zerem decyzji. TASK-0097 jest ponownie aktywny; trening nadal czeka na jawne
  etykiety.
- **Supersedes:** D-061 w zakresie produkcyjnego źródła cropów do review.
  Kontrakty stabilnej obserwacji, jawnej decyzji i braku auto-accept pozostają
  w mocy.

## D-069 — Deterministyczny source-aware split rzeczywistego datasetu

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** `labeled-symbol-dataset-v1` jest dzielony w całości po checksumie
  zdjęcia źródłowego, ze stałym seedem i proporcjami docelowymi `70/15/15`.
  Każdy z train, validation i test wymaga co najmniej dwóch zdjęć oraz wszystkich
  symboli. Identyczne bajty cropu nie mogą wystąpić w różnych źródłach ani
  splitach. Manifest zachowuje przydział źródeł i uporządkowane identyfikatory
  próbek.
- **Context:** pierwszy rzeczywisty eksport zawiera 416 zaakceptowanych próbek
  z 18 zdjęć i wszystkich ośmiu symboli. Losowanie po pojedynczych cropach
  umieściłoby niemal identyczne warunki tego samego zdjęcia w treningu i
  ewaluacji.
- **Reason:** granica zdjęcia źródłowego zapobiega przeciekowi tła, perspektywy,
  oświetlenia i artefaktów ekranu. Stały seed i raport checksum pozwalają
  odtworzyć dokładnie ten sam logiczny dataset.
- **Alternatives:** losowanie per crop albo ręcznie utrzymana lista. Pierwsze
  przecieka między zbiorami, drugie jest podatne na drift i trudniejsze do
  odtworzenia.
- **Consequences:** split ma `269/74/73` próbek i `10/4/4` zdjęć dla
  train/validation/test. Wszystkie symbole występują w każdym zbiorze, a bramka
  strukturalna przechodzi. Żaden symbol nie osiąga jeszcze orientacyjnego celu
  100 zaakceptowanych próbek, co pozostaje jawnym advisory i ogranicza pierwszy
  model do statusu bootstrapowego.
- **Supersedes:** brak.

## D-070 — Mały deterministyczny CNN jako bootstrap klasyfikatora symboli

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** pierwszy klasyfikator używa lokalnego PyTorch `2.12.1` CPU i
  torchvision `0.27.1`, własnego CNN bez pretrained weights, wejścia RGB
  `64 × 64` oraz stałej normalizacji do `[-1, 1]`. Trening ma stały seed,
  ważony cross-entropy, Adam, 40 epok i jeden wątek CPU. Checkpoint wybiera
  wyłącznie validation macro-recall, następnie accuracy, loss i wcześniejsza
  epoka. Test jest oceniany raz po zamrożeniu checkpointu.
- **Context:** source-aware split TASK-0060 udostępnia 269 próbek train, 74
  validation i 73 test. Wszystkie klasy są obecne, ale żadna nie osiąga jeszcze
  orientacyjnego celu 100 próbek.
- **Reason:** mały model 24 104 parametrów daje tani, wymienny i odtwarzalny
  baseline CPU. Brak pretrained weights usuwa pobieranie sieciowe oraz ukrytą
  zależność od zewnętrznego datasetu.
- **Alternatives:** transfer learning z ciężkiego modelu, template matching albo
  model aktualizowany online po każdym review. Pierwsza opcja nie jest potrzebna
  przed pomiarem baseline, druga słabo generalizuje, a trzecia łamie wersjonowany
  batch i audyt.
- **Consequences:** najlepszy checkpoint pochodzi z epoki 22. Validation ma
  accuracy `59.4595%` i macro-recall `61.4469%`; test ma accuracy `63.0137%`
  i macro-recall `62.7128%`. `star`, `watermelon` i `plum` są słabymi klasami,
  więc model pozostaje `bootstrap`, nie definiuje confidence policy i nie może
  uruchamiać auto-accept. Logiczny checksum stanu to
  `0edab6bbb738d908c4e902a347c982407549c159829c80fc3010c314a6c1aea2`.
- **Supersedes:** brak.

## D-071 — Zamrożone, leakage-safe sugestie tylko do ręcznego review

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** TASK-0099 tworzy indeks podobieństwa wyłącznie z 269
  zaakceptowanych próbek partycji train i embeddingu zamrożonego checkpointu
  TASK-0061. Każde zapytanie wyklucza własną próbkę oraz wszystkie referencje
  z tego samego obrazu źródłowego. UI pokazuje najwyżej jedną referencję na
  symbol i trzy klasy, jeżeli najlepsze podobieństwo cosinusowe osiąga
  `0,9975`. W przeciwnym razie pokazuje `no_suggestion`. Historyczna etykieta
  po `observationId` jest wyświetlana osobno i nie uczestniczy w rankingu.
- **Context:** baseline ma charakter bootstrapowy, a jego validation accuracy
  wynosi tylko `59,4595%`. Naiwny próg `0,80` dawał sugestię dla całej
  walidacji, ponieważ embeddingi małego CNN są skupione bardzo blisko siebie.
  Nie można traktować samego softmax confidence ani podobieństwa jako zgody na
  automatyczną etykietę.
- **Reason:** zamrożony train-only indeks zachowuje uczciwą granicę
  source-aware validation, jest odtwarzalny i nie zmienia się po kliknięciach.
  Konserwatywny próg jawnie rezygnuje z części pokrycia zamiast zawsze zgadywać.
- **Alternatives:** użycie wszystkich 416 próbek jako referencji, aktualizacja
  indeksu po każdym kliknięciu albo auto-accept top-1. Pierwsza opcja
  zanieczyszcza ocenę validation, druga łamie wersjonowany batch, a trzecia nie
  jest uzasadniona jakością modelu.
- **Consequences:** source-disjoint validation ma coverage `75,6757%`, top-1
  accuracy przy coverage `76,7857%`, top-3 `94,6429%` i zero source leakage.
  Sugestia nigdy nie mutuje `reviewed-cell-labels-v1`; dopiero kliknięcie albo
  Q/W/E tworzy zwykłą decyzję właściciela. Kalibracja confidence i jakakolwiek
  polityka auto-accept pozostają zakresem TASK-0063.
- **Supersedes:** brak.

## D-072 — ONNX opset 18 jako lokalna granica inferencji symboli

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** dokładny checkpoint TASK-0061 jest eksportowany aktualnym
  mechanizmem `torch.export` do ONNX opset 18. Graf ma dynamiczny wyłącznie
  batch i stały kontrakt `N × 3 × 64 × 64 -> N × 8 logits`. Produkcyjny port
  inferencji używa przypiętych ONNX `1.22.0`, ONNX Script `0.7.1` oraz ONNX
  Runtime CPU `1.28.0`; adapter dopuszcza wyłącznie `CPUExecutionProvider`,
  sekwencyjne wykonanie i jeden wątek.
- **Context:** klasyfikator został wytrenowany w PyTorch, ale wymagania M6
  wskazują wymienny, lokalny runtime produkcyjny. Pierwsza próba z legacy
  exporterem przeszła technicznie, lecz PyTorch 2.12 oznaczył ją jako
  wycofywaną, dlatego nie została przyjęta.
- **Reason:** aktualny eksporter usuwa zależność od ścieżki przeznaczonej do
  usunięcia. Jawny kształt, class order, checksum i ONNX checker tworzą wąską,
  testowalną granicę bez pobierania wag z sieci.
- **Alternatives:** pozostawienie PyTorch jako runtime produkcyjnego, legacy
  TorchScript exporter albo dynamiczne wymiary obrazu. Pierwsza opcja nie
  realizuje zaakceptowanego stosu, druga tworzy dług techniczny, a trzecia
  rozszerza kontrakt bez potrzeby.
- **Consequences:** artefakt ma 115133 bajtów i SHA-256
  `e03f66f2ab092b6049920fee6fb2839900a95eb94af42fbd5ef7e35c473b5fb8`.
  Na wszystkich 416 próbkach nie zmienił żadnej klasy top-1; maksymalny błąd
  logits wynosi `2.861e-6`, prawdopodobieństw `4.172e-7`, a tolerancja obu to
  `1e-5`. Drift checksumy, klasy, kształtu, typu albo wartości niefinitywnej
  blokuje inferencję stabilnym kodem. Confidence policy pozostaje zakresem
  TASK-0063.
- **Supersedes:** brak.

## D-073 — Validation-only kalibracja i fail-closed active learning

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** confidence klasyfikatora symboli jest skalowane jedną dodatnią
  temperaturą dopasowaną deterministycznie na source-disjoint validation przez
  minimalizację NLL. Test jest mierzony dopiero po zamrożeniu temperatury.
  Auto-accept wymaga statusu `production_candidate`, osiągniętego celu próbek,
  co najmniej 95% precision na 20 próbkach validation i co najmniej 90%
  precision na 3 próbkach każdej klasy. Automatyczny reject pozostaje
  wyłączony. Następny batch review wybiera 30 kompletnych pending plansz,
  łącząc niepewność, różnorodność predykcji, nowe źródło i rzadkie klasy; do
  pokrycia źródeł wybiera najwyżej jedną planszę z jednego zdjęcia.
- **Context:** temperatura `1.0338382913` nie zmienia top-1 i nieznacznie
  poprawia NLL, ale validation ECE rośnie z `0.06960527` do `0.08450210`.
  Najlepszy próg `0.89329293` ma precision `1.0` tylko na 9 próbkach, a klasy
  `star`, `watermelon` i `plum` pozostają słabe na teście. Model oraz dataset
  nadal mają status bootstrapowy.
- **Reason:** confidence nie może zastąpić dowodu jakości per klasa.
  Fail-closed policy zapobiega automatycznej mutacji etykiet, a wybór całych
  plansz zachowuje szybszy workflow użytkownika i różnorodność źródeł.
- **Alternatives:** niekalibrowany softmax, próg dobrany na teście, auto-accept
  na podstawie 9 łatwych próbek albo ranking pojedynczych cropów. Pierwsze trzy
  przeceniają wiarygodność, a ostatnie niszczy whole-layout review.
- **Consequences:** wszystkie 5389 pending cropów są nadal decyzją człowieka.
  Z 359 kompletnych pending plansz wybrano odtwarzalny batch 30 plansz z 30
  źródeł; cztery częściowe plansze nie weszły do batcha. Raport kalibracji ma
  SHA-256
  `a2359efed1e2dc2d73fc383d9e260c88f4a19838a74af3dd165362692601bff7`,
  a raport selekcji
  `2ab9a79a6d1c81b8d08abe0defc447510f0cfe4df1909c9aa8da77d79e6115d2`.
  Następna wersja modelu powstaje dopiero z nowego, jawnie zatwierdzonego
  datasetu.
- **Supersedes:** brak.

## D-074 — Niezmienny batch review i oddzielona granica zapisu decyzji

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** wynik `whole-layout-active-learning-v1` jest importowany
  atomowo jako `review_batch` identyfikowany canonical SHA-256 całego raportu.
  Każda pozycja zachowuje niezmienny snapshot pełnej planszy 5 × 3,
  provenance, confidence i alternatives. TASK-0064 udostępnia tylko
  idempotentny import oraz read-only list/detail; przejścia
  approve/correct/reject, audyt i eksport feedbacku należą do TASK-0066.
- **Context:** TASK-0063 utworzył odtwarzalny batch 30 kompletnych plansz.
  Interfejs TASK-0065 potrzebuje stabilnego źródła danych, ale samo
  wyświetlenie predykcji nie może tworzyć decyzji ani zmieniać etykiet.
- **Reason:** checksum-bound batch wiąże review z dokładnym modelem, kalibracją,
  splitem i inventory, a oddzielenie od resolution zmniejsza ryzyko ukrytej
  mutacji podczas implementacji UI. Deterministyczny `selection_rank` jest
  bezpiecznym kursorem i zachowuje kolejność rankingu.
- **Alternatives:** przechowywanie wyłącznie ścieżki do JSON, tworzenie jednego
  rekordu na komórkę albo jednoczesne dodanie resolution w TASK-0064. Pierwsza
  opcja nie zapewnia trwałego, transakcyjnego źródła dla panelu, druga niszczy
  whole-layout workflow, a trzecia łączy odczyt UI z audytowalną mutacją bez
  gotowego kontraktu korekt.
- **Consequences:** PostgreSQL przechowuje raport i snapshoty JSONB, lecz nie
  obrazy. Identyczny retry zwraca ten sam batch; inna gra lub payload pod tym
  samym checksumem są konfliktem. TASK-0065 może budować UI na generowanym
  kliencie, a TASK-0066 musi dodać atomowe resolution i historię bez
  nadpisywania źródłowego snapshotu.
- **Supersedes:** brak.

## D-075 — Item-scoped streaming lokalnych obrazów review

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** panel manual review pobiera obrazy wyłącznie przez trzy
  read-only endpointy związane z istniejącym `review_item`: source, board i
  cell o indeksie 0–14. Klient nie przekazuje ścieżki. Source jest wybierany
  pod `GAME_PREDICTOR_REVIEW_SOURCE_ROOT` po zapisanym SHA-256; board i cell są
  rozwiązywane pod `GAME_PREDICTOR_REVIEW_CROP_ROOT` z niezmiennego snapshotu.
- **Context:** strona HTTP nie może bezpiecznie renderować lokalnego `file://`,
  a TASK-0064 celowo przechowuje tylko metadane i nie zapisuje obrazów w
  PostgreSQL. TASK-0065 musi jednocześnie pokazać oryginał, planszę i crop.
- **Reason:** item-scoped route nie tworzy ogólnego serwera plików, zachowuje
  granicę loopback i pozwala backendowi ponownie sprawdzić root, typ pliku oraz
  checksumę oryginału. JSON pozostaje mały i typowany.
- **Alternatives:** osadzenie obrazów jako base64/JSONB, linki `file://`,
  publiczny static root albo endpoint przyjmujący ścieżkę. Pierwsza opcja
  powiększa bazę i odpowiedzi, druga jest blokowana przez przeglądarkę, a dwie
  ostatnie niepotrzebnie udostępniają szerszy fragment systemu plików.
- **Consequences:** dwa lokalne rooty są konfigurowalne i domyślnie wskazują
  zaakceptowany namespace v16 oraz `examples/imgs`. Brak, niejednoznaczność,
  unsafe path, nieobsługiwany typ lub błędny indeks kończą się stabilnym
  błędem; UI pokazuje placeholder bez ukrywania predykcji. Endpoint nie zapisuje
  decyzji i nie zmienia batcha.
- **Supersedes:** brak.

## D-076 — Revisioned whole-board review and immutable feedback versions

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** manual review zapisuje decyzję dla całej planszy jako atomową
  parę: bieżąca projekcja `review_items` oraz append-only
  `review_resolutions`. Każda komenda ma UUID idempotencji i oczekiwaną
  rewizję. Accepted/corrected wymaga potwierdzonej geometrii i dokładnie 15
  etykiet związanych z `sampleId`; rejected nie niesie etykiet. Eksport
  feedbacku jest niezmienny, game-local versioned i identyfikowany checksumą
  kompletnego bieżącego stanu batcha.
- **Context:** TASK-0064/0065 zapewniły niezmienny snapshot i bezpieczny odczyt,
  ale zapis pojedynczych komórek lub nadpisanie jednej decyzji utraciłoby
  kontekst planszy, umożliwiło częściowy dataset i usunęło historię korekt.
- **Reason:** optimistic revision chroni przed zapisem na nieaktualnym widoku,
  idempotency key przed podwójnym kliknięciem, a pełne 15 etykiet pozwala
  jednoznacznie odtworzyć dane treningowe. Checksum stanu oddziela retry od
  rzeczywistej nowej wersji feedbacku.
- **Alternatives:** mutable single-row resolution bez audytu, osobne decyzje
  per cell, eksport nadpisujący jeden plik albo automatyczny trening po zapisie.
  Pierwsza opcja usuwa historię, druga dopuszcza częściowe plansze, trzecia
  łamie wersjonowanie, a ostatnia narusza manual-review-only i rollback modelu.
- **Consequences:** zmiana decyzji dopisuje rewizję; exact retry nie tworzy
  zdarzenia, a stale revision lub reuse klucza z innym payloadem kończy się
  konfliktem. Pending blokuje eksport, rejected jest wykluczony z próbek, a
  nowy stan tworzy kolejną wersję bez mutacji starego payloadu. Obrazy
  pozostają poza PostgreSQL, a retraining wymaga osobnego jawnego zadania.
- **Supersedes:** brak.

## D-077 — Techniczny odbiór pionu oddzielony od promocji modelu

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** G6 używa checksumowanego raportu
  `classifier-review-vertical-slice-v1`, który ponownie weryfikuje zaakceptowaną
  geometrię v16, inventory, dataset i split, uruchamia lokalny ONNX na całym
  oznaczonym korpusie oraz odtwarza atomowe accept/correct dla kompletnych
  plansz. Przejście technicznego pionu nie promuje automatycznie modelu.
  Aktualny bootstrap pozostaje `manual-review-only`, wymaga retrainingu przed
  auto-accept i nie zezwala na masowy import. Retraining i rollback zawsze
  wybierają nowy albo wcześniejszy kompletny manifest; nie nadpisują wag,
  raportów ani historycznych batchy.
- **Context:** istniejące 416 etykiet pozwala uczciwie zmierzyć ONNX, ale model
  ma tylko `68.509615%` accuracy i `70.14904%` macro recall na całym oznaczonym
  korpusie. Spośród 24 kompletnych plansz tylko jedna nie wymaga korekty;
  polityka confidence poprawnie kieruje 100% predykcji do człowieka.
- **Reason:** bramka integracyjna ma potwierdzić działanie granic technicznych,
  a nie ukrywać słabość modelu przez wynik po ręcznej korekcie. Oddzielny
  manifest promocji daje jednoznaczny rollback bez mutacji danych audytowych.
- **Alternatives:** uznać poprawność po review za jakość automatyczną, obniżyć
  progi albo podmieniać jeden aktywny plik ONNX. Pierwsze dwie opcje fałszują
  gotowość, a ostatnia usuwa odtwarzalność i bezpieczny rollback.
- **Consequences:** TASK-0067 może zaliczyć pion M6 przy decyzji
  `retraining_required_before_auto_accept`. Kolejna iteracja modelu wymaga
  nowego feedback exportu, datasetu, source-aware splitu, checkpointu, ONNX,
  kalibracji i ponownego raportu pionu. Masowy import pozostaje niedozwolony.
- **Supersedes:** brak.

## D-078 — Fingerprint całego pipeline'u i tożsamość wyniku per plik

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** pełny import obrazów używa kanonicznego
  `image-pipeline-manifest-v1`, który zawiera stałą kolejność etapów, wersje
  adapterów, modeli, preprocessingu, kalibracji i polityk oraz względne ścieżki
  POSIX i SHA-256 artefaktów. `pipelineFingerprint` jest SHA-256 kanonicznych
  bajtów manifestu bez envelope. Wynik per plik identyfikuje
  `fileExecutionKey = SHA-256(image-file-execution-v1, source SHA-256,
pipelineFingerprint)`. Checkpoint przechowuje tylko uporządkowany prefiks
  etapów i nie może ominąć wymaganej granicy manual review.
- **Context:** M5–M6 wersjonowały komponenty osobno. Sam ogólny
  `pipeline_version`, nazwa pliku albo nazwa modelu nie chroniły przed
  nadpisaniem wyniku po zmianie checksumy wag, kalibracji lub confidence
  policy.
- **Reason:** fingerprint pełnego wejścia wykonawczego daje deterministyczną
  idempotencję i audytowalne współistnienie wyników wielu wersji bez zależności
  od hosta, czasu i lokalnej ścieżki.
- **Alternatives:** mutable alias `latest`, klucz tylko z nazwy/mtime pliku albo
  osobne, niepowiązane kolumny wersji. Alias i mtime nie są odtwarzalne, a
  luźne kolumny pozwalają pominąć istotny składnik przy deduplikacji.
- **Consequences:** zmiana dowolnego składnika manifestu tworzy nowy
  fingerprint oraz wynik. Identyczny plik i manifest mają ten sam klucz.
  Aktualne OCR i klasyfikator `manual_review_only` wymuszają
  `waiting_for_review`, wyłączone auto-accept/auto-reject i etap
  `manual_review` przed walidacją. TASK-0069 utrwali kontrakt bez zmiany jego
  semantyki.
- **Supersedes:** brak.

## D-079 — Globalne wykonanie pliku oddzielone od członkostwa w batchu

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** trwały wynik pipeline'u obrazu jest przechowywany raz w
  `image_file_executions` pod globalnym `fileExecutionKey`. Członkostwo,
  kolejność i względna ścieżka konkretnego importu należą do osobnej tabeli
  `image_import_job_files`. File checkpoint jest zapisywany przed checkpointem
  joba, w transakcji sprawdzającej aktywny lease/fencing token oraz oczekiwaną
  poprzednią wersję checkpointu.
- **Context:** umieszczenie pełnego wyniku bezpośrednio pod jobem duplikowałoby
  pracę przy bezpiecznym retry lub imporcie tych samych bajtów pod inną nazwą.
  Sam globalny rekord nie przechowuje natomiast kolejności ani kontekstu batcha.
- **Reason:** rozdzielenie content-addressed execution od asocjacji joba
  zapewnia deduplikację, historię model drift i deterministyczny batch bez
  mutowania wcześniejszego wyniku. Kolejność zapisu file→job daje bezpieczny
  replay po awarii pomiędzy transakcjami.
- **Alternatives:** jeden rekord per `(job, source)`, cały stan plików w JSONB
  joba albo jedna wielka transakcja batcha. Pierwsze duplikuje wyniki, drugie
  nie skaluje się do dużych katalogów, a trzecie blokuje bazę i utrudnia
  anulowanie.
- **Consequences:** wiele jobów może wskazać ten sam wykonany plik, natomiast
  inny `pipelineFingerprint` zawsze tworzy nowy rekord. File write wymaga
  aktywnego job lease i zgodnego expected checkpoint. Review jest kumulacyjne,
  a job przechodzi do `waiting_for_review` dopiero po diagnostycznym przebiegu
  pozostałych plików. Rzeczywiste etapy i tabele rozpoznania pozostają w M7.2.
- **Supersedes:** brak.

## D-080 — Operacyjne review M7 oddzielone od batchy active learning M6

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** globalne, niezmienne wyniki sześciu etapów automatycznych są
  zapisane per `fileExecutionKey`, ale source/board/cell, operacyjne review i
  staging layoutu należą do konkretnego image import joba. M7 używa
  `image_review_items`, a nie bounded `review_batches/review_items` M6.
  Staging powstaje wyłącznie z atomowej decyzji accepted/corrected całej
  planszy.
- **Context:** review M6 zamraża najwyżej 100 wybranych plansz do active
  learning i wymaga znanego numeru. Masowy import M7 może zawierać niepewny
  OCR, odrzucone plansze oraz znacznie większą kolejkę, więc istniejące
  constraints nie opisują tego lifecycle.
- **Reason:** oddzielenie zachowuje audyt treningu i pozwala współdzielić
  kosztowny wynik modeli bez współdzielenia decyzji administratora między
  niezależnymi importami.
- **Alternatives:** rozszerzyć historyczne `review_items` o nullable batch i
  dwa lifecycle albo trzymać całe review w JSONB joba. Pierwsze miesza dwa
  źródła prawdy, drugie nie skaluje się i utrudnia idempotencję.
- **Consequences:** binaria pozostają w storage, PostgreSQL przechowuje
  checksumy i ścieżki. Duplikat lub luka numeru pozostaje jawną blokadą
  walidacji; system nigdy nie poprawia OCR ani nie przesuwa sekwencji po cichu.
  TASK-0071 rozszerzy ten model o trwałe błędy i retry per plik.
- **Supersedes:** brak.

## D-081 — Globalny cache automatyczny, job-local workflow review

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** immutable wyniki sześciu automatycznych etapów nadal należą do
  globalnego `image_file_execution`, ale checkpoint, status, błąd i retry
  manual review/walidacji należą do `image_import_job_files`. Każda decyzja
  operacyjnego review jest append-only eventem z kluczem idempotencji.
- **Context:** completed execution może zostać użyte w nowym imporcie bez
  ponownej inferencji, lecz nowy import musi utworzyć własne source/board/cell
  i własną decyzję administratora. Wspólny checkpoint po manual review
  mutowałby historię pierwszego joba albo pozwalał pominąć review w drugim.
- **Reason:** granica odpowiada rzeczywistej własności danych: kosztowny,
  deterministyczny wynik modelu jest content-addressed, a decyzja i ciągłość
  datasetu zależą od konkretnego importu. Oddzielny workflow umożliwia retry
  bez duplikacji i bez zmiany zakończonego joba.
- **Alternatives:** pełny execution per job, współdzielony status przez cały
  pipeline albo kopiowanie stage results. Pierwsze i trzecie duplikują dane i
  obliczenia, a drugie miesza niezależne decyzje review.
- **Consequences:** rehydratacja odtwarza job-local projekcje z globalnych stage
  results bez wywołania adapterów. Błąd jednego pliku nie zatrzymuje batcha,
  retry może wskazać wyłącznie `nextStage`, a konflikty numeracji wracają do
  review bez przesuwania wartości. Publiczne operacje UI pozostają w
  TASK-0072.
- **Supersedes:** doprecyzowuje D-079 i D-080, nie unieważnia ich.

## D-082 — Zarządzany storage bez automatycznej destrukcji

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** artefakty M7 mają jeden zarządzany root
  `<artifact-root>/data` z przestrzeniami `originals`, `working`, `crops`,
  `training`, `models` i `exports`. TASK-0073 udostępnia wyłącznie read-only
  inwentarz i polityki z `automaticDeletion = false`; nie implementuje
  fizycznego usuwania. Diagnostyka joba jest niezmiennym, content-addressed
  JSON pod `exports/image-jobs/<jobId>/<sha256>/diagnostics.json`.
- **Context:** obecne prototypy tworzą wiele historycznych katalogów, a baza
  przechowuje tylko ścieżki względne i checksumy. Automatyczne czyszczenie bez
  kompletnego grafu referencji mogłoby usunąć oryginał, zaakceptowany crop,
  model albo dowód wymagany do odtworzenia wyniku.
- **Reason:** jawny inwentarz daje pomiar storage przed M7.4, natomiast brak
  destrukcji zachowuje bezpieczną granicę. Content-addressed eksport jest
  idempotentny, możliwy do niezależnej weryfikacji i nie wymaga zapisywania
  binariów w PostgreSQL.
- **Alternatives:** automatyczny TTL, ręczne kasowanie namespace albo ZIP z
  obrazami. TTL i kasowanie są niebezpieczne bez pełnego lineage; ZIP zwiększa
  rozmiar i ryzyko ujawnienia danych, choć do diagnozy błędu wystarcza manifest.
- **Consequences:** M7.3 nie odzyskuje jeszcze miejsca. Każda przyszła akcja
  delete/garbage collection wymaga osobnego zadania, jawnego potwierdzenia,
  dry-run oraz dowodu, że plik nie jest oryginałem ani referencją zaakceptowanej
  lub opublikowanej wersji. M7.4 może mierzyć sześć stabilnych przestrzeni.
- **Supersedes:** brak.

## D-083 — Ograniczona rejestracja wsadowa bez dodatkowej kolejki

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** odkryte pliki image importu są rejestrowane przez produkcyjne
  repozytorium w deterministycznych partiach po najwyżej 500 rekordów.
  Operacje retry, checkpoint i wykonanie pojedynczego pliku pozostają niezależne.
  Na podstawie pomiaru storage/database nie dodajemy Redis, Celery ani osobnego
  workera.
- **Context:** pierwszy smoke dla 1 000 plików osiągnął tylko
  `41.13 plików/s`, ponieważ każdy plik otwierał osobną transakcję. Rejestracja
  wsadowa osiągnęła `184.32 plików/s` dla 55 556 plików i zakończyła pełny
  pomiar w limicie 900 sekund.
- **Reason:** bounded batch usuwa koszt transakcji per plik bez ładowania całego
  katalogu do pamięci, zachowuje kolejność `orderIndex`, content-addressed
  idempotencję i istniejącą granicę pojedynczego procesu.
- **Alternatives:** transakcja per plik przekraczała budżet czasu; jeden
  nieograniczony insert zwiększa ryzyko pamięci i rollbacku; zewnętrzna kolejka
  nie rozwiązuje kosztu rejestracji i nie ma jeszcze uzasadnienia pomiarowego.
- **Consequences:** importer może utrzymywać najwyżej 500 lekkich rekordów
  rejestracji w pamięci. Konflikt kolejności, ścieżki lub provenance odrzuca
  całą bieżącą partię. TASK-0075 nadal musi zmierzyć właściwy pipeline,
  recovery i review throughput przed końcową decyzją o kolejce.
- **Supersedes:** brak.

## D-084 — G7.4 przechodzi wyłącznie w trybie manual-review-only

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** odporność i persistence image importu zaliczają G7.4, ale nie
  zmieniają decyzji jakości M6. OCR i classifier auto-accept pozostają
  wyłączone, `manualReviewShare = 1.0`, a duży masowy import i publikacja są
  zablokowane do zebrania review feedbacku, retrainingu i nowej kalibracji.
- **Context:** fizyczny benchmark odtworzył restart po checkpointcie, po jednej
  awarii każdego etapu, exact retry, 387 zapisów review oraz ciągły staging.
  Jednocześnie checksum-bound raport M6 nadal podaje accuracy `0.68509615` i
  `massImportAllowed = false`.
- **Reason:** jakość predykcji i niezawodność orkiestracji są niezależnymi
  bramkami. Dobry wynik PostgreSQL/recovery nie może zastąpić dowodu held-out
  ani automatycznie zaakceptować błędnych symboli lub numerów.
- **Alternatives:** odblokowanie importu na podstawie poprawnego recovery
  mieszałoby dwie bramki; obniżenie progów jakości łamałoby zaakceptowany
  kontrakt; ręczne review całych 500 000 layoutów nie jest akceptowalnym
  pipeline'em publikacyjnym.
- **Consequences:** TASK-0075 jest zakończony, ale TASK-0076 nie może opublikować
  dużego datasetu. Następny krok produktowy to zebranie dodatkowego feedbacku i
  retraining; TASK-0077 może osobno zamknąć decyzję o kolejce na podstawie obu
  benchmarków.
- **Supersedes:** brak.

## D-085 — Jeden lokalny worker i PostgreSQL pozostają docelową kolejką M7

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** zachowujemy jeden lokalny Python worker, globalny
  `execution_slot = 1` oraz rekordy `jobs` w PostgreSQL jako trwały mechanizm
  kolejkowania z fenced lease. Nie dodajemy Redis, Celery, brokera,
  mikroserwisów ani zdalnych workerów.
- **Context:** pełny profil 55 556 plików osiągnął `184.32 plików/s` rejestracji
  i `431.19 plików/s` materializacji storage. Restart, izolacja sześciu awarii
  i exact retry przeszły, a zapis review osiągnął `26.16 decyzji/s`. Aktualną
  blokadą pozostaje `massImportAllowed = false` i 100% manual review.
- **Reason:** obecna architektura spełnia lokalny, prywatny model wdrożenia i
  zapewnia trwałość, idempotencję oraz recovery. Zewnętrzny broker zwiększyłby
  złożoność instalacji i failure surface, ale nie poprawiłby jakości OCR/ML.
- **Alternatives:** Redis/Celery, wiele lokalnych workerów, mikroserwisy albo
  kolejka in-memory. Pierwsze trzy nie mają uzasadnienia pomiarowego; ostatnia
  traci trwałość i fencing dostępne już w PostgreSQL.
- **Consequences:** ciężkie joby nadal wykonują się sekwencyjnie i
  `waiting_for_review` zwalnia slot. Decyzję wolno ponownie otworzyć po
  zmierzonym trwałym backlogu co najmniej 3 jobów przez 30 minut, dwukrotnym
  przekroczeniu zaakceptowanego SLA TASK-0076, wymaganiu co najmniej dwóch
  równoczesnych operatorów, regresji recovery/fencingu albo zmianie topologii
  poza jeden komputer. Ponowna ocena wymaga nowego zadania i ADR; nie uruchamia
  migracji automatycznie.
- **Supersedes:** domyka pomiarowo D-006, D-029, D-033 i D-083 bez zmiany ich
  kontraktów.

## D-086 — Decyzja człowieka jest nadrzędna, a ręcznie zweryfikowany zakres ma osobną ścieżkę publikacji

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** M6.5 dodaje lokalne, wysokoprzepustowe stanowisko operacyjnego
  review oparte na `image_review_items`. Accepted/corrected zamraża numer,
  rewizję geometrii, 15 `cropSampleId` i 15 symboli jako append-only decyzję
  człowieka. Retraining może zmienić sugestie tylko dla unresolved items.
  Całkowicie ręcznie rozwiązany, ciągły zakres może przejść do standardowej
  walidacji i publikacji stagingu przy `massImportAllowed = false`; flaga nadal
  blokuje automatyczną publikację bez pełnego nadzoru.
- **Context:** model spatial ma znacznie lepszy wynik niż baseline, ale
  productionization i kalibracja nie są jeszcze zakończone. Czekanie na
  perfekcyjny auto-accept blokowałoby zbieranie kanonicznych layoutów, podczas
  gdy istniejące M7 persistence, idempotencja i audyt obsługują decyzje całych
  plansz.
- **Reason:** człowiek może bezpiecznie zatwierdzić 1000/3000+ plansz, zebrać
  lepszy dataset i kontynuować produkt, o ile UI minimalizuje koszt decyzji, a
  pipeline nie udaje automatycznej jakości. Rozdzielenie supervised
  publication od auto-accept zachowuje uczciwość obu bramek.
- **Alternatives:** dalsze ręczne narzędzia ad hoc, czekanie na idealny model
  albo obniżenie progów auto-accept. Pierwsze nie skaluje się i rozprasza
  audyt, drugie zatrzymuje roadmapę, a trzecie zwiększa ryzyko błędnych danych.
- **Consequences:** powstaje M6.5 i TASK-0105–0111. Geometria i cropy są
  wersjonowane, wcześniejsze decyzje pozostają edytowalne przez nową rewizję,
  a zamrożenie kohorty i trening są jawnymi osobnymi operacjami. D-084 nadal
  blokuje automatyczny masowy import i ręczne review całych 500 000 layoutów
  nie staje się celem.
- **Supersedes:** doprecyzowuje D-076, D-080, D-081 i D-084; nie unieważnia ich.

## D-087 — Zdalne review jest odłożoną, ograniczoną granicą bezpieczeństwa

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** lokalny M6.5 pozostaje na loopback. Zdalne review jest
  opcjonalnym M8.7 i udostępnia wyłącznie game-scoped powierzchnię recenzenta
  po odwoływalnej, wygasającej sesji, osobno przekazywanym kodzie i HTTPS.
  Pełny Admin API, PostgreSQL, worker, konfiguracja oraz wydania nie są
  dostępne zdalnie. Surowe przekierowanie portu routera jest wykluczone.
- **Context:** właściciel chce później przekazać link osobie pracującej poza
  domową siecią, a komputer w domu ma pozostać serwerem bez kosztu chmurowego.
  Obecny stos celowo odrzuca binding inny niż loopback i nie posiada
  produkcyjnej autoryzacji.
- **Reason:** oddzielna faza pozwala szybko dostarczyć lokalny panel i nie
  zamieniać zmiany UX w niekontrolowane wystawienie prywatnych obrazów oraz
  operacji administracyjnych do Internetu.
- **Alternatives:** bezpośredni port forwarding, wspólne hasło do całego
  panelu, publiczny hosting albo brak zdalnego dostępu. Dwie pierwsze mają zbyt
  szeroki zakres i słabą izolację, hosting rozszerza koszty i operacje, a brak
  zdalnego dostępu nie realizuje przyszłego sposobu współpracy.
- **Consequences:** Q-019 jest zamknięte jako model wielu jawnych aktorów.
  Q-021 i TASK-0112 wybiorą transport po aktualnym porównaniu. M8.7 wymaga
  hashy kodów, TTL, limitu prób, unieważnienia, audytu sesji, optimistic
  revision i zewnętrznego testu zakresu. Mobile nadal nie otrzymuje
  `INTERNET`.
- **Supersedes:** rozszerza przyszły zakres D-021 i M8.1 bez zmiany domyślnego
  loopback.

## D-088 — Spatial CNN jest produkcyjnym modelem sugestii symboli

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** wydanie `production-spatial-symbol-cnn-v1` z architekturą
  `spatial-symbol-cnn-v1`, preprocessingiem
  `rgb-resize64-normalize-half-v1` i ONNX
  `spatial-symbol-cnn-onnx-v1` staje się wersjonowanym modelem sugestii
  symboli. Scalar temperature `1.1515684402` i próg auto-accept
  `0.88850097` pochodzą wyłącznie z zamrożonego validation. Test służy tylko
  jako końcowy pomiar. Globalne `massImportAllowed` pozostaje `false`, ponieważ
  OCR numerów nadal działa jako `manual_review_only`.
- **Context:** TASK-0104 wybrał spatial CNN bez augmentacji na validation.
  TASK-0105 wyeksportował model do ONNX, uzyskał zero top-one mismatch,
  maksymalny błąd `0.000002861` oraz odtworzył cały manifest na 1316 próbkach.
  Validation confidence gate odblokował auto-accept symboli, a zamrożony test
  przy wybranym progu osiągnął precision `0.97674419` i coverage `0.82428115`.
- **Reason:** checksum-bound manifest łączy checkpoint, kolejność ośmiu klas,
  preprocessing, ONNX, kalibrację, vertical slice i decyzję jakościową. Dzięki
  temu panel może pokazywać stabilne sugestie i maksymalnie cztery alternatywy,
  nie mieszając jakości symboli z niezależną jakością OCR.
- **Alternatives:** pozostawienie słabszego bootstrapu, dalszy trening mimo
  przejścia bramki albo odblokowanie globalnego importu samym wynikiem symboli.
  Pierwsze pogarsza UX review, drugie nie ma uzasadnienia w bieżących danych,
  a trzecie łamie niezależną bramkę OCR.
- **Consequences:** TASK-0106 może budować operacyjny API review na nowym
  kontrakcie sugestii. Symbol auto-accept jest dozwolony tylko dla predykcji
  spełniających zamrożony próg; pozostałe wymagają człowieka. D-086 nadal
  pozwala publikować w pełni ręcznie zweryfikowane ciągłe zakresy, a TASK-0076
  pozostaje zablokowany do nowej decyzji obejmującej także OCR.
- **Supersedes:** finalizuje wybór modelu symboli z D-080 i D-084; nie zmienia
  wymogu ręcznego OCR ani nadrzędności decyzji człowieka z D-086.

## D-089 — Ręczna korekta geometrii tworzy nową projekcję cropów bez migracji etykiet

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** geometria pipeline'u pozostaje rewizją `0`. Każdy zapis
  czterech narożników tworzy append-only `image_board_geometry_revisions`,
  niezmienną planszę 500 × 300 i dokładnie 15 content-addressed cropów.
  `recognized_boards.geometry_revision` wskazuje bieżącą projekcję, natomiast
  bazowe `cell_observations` zachowują stabilne `observationId`. Nowe bajty,
  ścieżka i wersja croppera tworzą nowe `cropSampleId`.
- **Context:** operator musi móc naprawić pojedynczą źle wyciętą planszę przed
  zatwierdzeniem symboli. Kopiowanie wcześniejszego symbolu człowieka po zmianie
  pikseli ukrywałoby błąd i zanieczyszczało zweryfikowaną kohortę.
- **Reason:** rozdzielenie stabilnej obserwacji od wersji próbki zachowuje audyt
  i umożliwia późniejszą analizę korekt, a jednocześnie atomowe ponowne otwarcie
  itemu usuwa tylko jego staging i wymusza świadomą decyzję dla nowych cropów.
  Preview używa tego samego adaptera `manual-review-geometry-v1`, ale nie
  zapisuje plików.
- **Alternatives:** nadpisanie istniejących plików, kopiowanie labeli,
  tworzenie nowej domenowej obserwacji dla każdego cropu albo przechowywanie
  binariów w PostgreSQL. Pierwsze dwie łamią audyt, trzecia traci stabilną
  tożsamość komórki, a ostatnia narusza przyjętą granicę storage.
- **Consequences:** zapis wymaga expected geometry i resolution revision oraz
  UUID idempotencji, tworzy event `reopened`, czyści bieżące resolved fields i
  staging, ale nie usuwa poprzedniej geometrii, decyzji ani plików. Korekta
  jednego itemu nigdy nie propaguje się automatycznie na inne plansze.
- **Supersedes:** doprecyzowuje technicznie D-086; nie zmienia D-084 ani bramki
  automatycznego importu.

## D-090 — Zamrożenie kohorty jest niezmiennym eksportem, a nie komendą treningową

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** jawne zamrożenie tworzy wersjonowany
  `image_verified_cohort_exports` i content-addressed JSON pod zarządzanym
  storage. Checksum stanu obejmuje wszystkie bieżące statusy oraz rewizje
  review, natomiast próbki payloadu pochodzą wyłącznie z kompletnych
  accepted/corrected i wiążą dokładne `cropSampleId`. Identical retry zwraca
  istniejącą wersję. Operacja nie wywołuje treningu, inferencji ani publikacji.
- **Context:** właściciel chce zamrażać dane etapami po jawnym poleceniu,
  przykładowo po 1000 albo 3000 planszach. Próg liczbowy nie może niejawnie
  uruchomić kosztownej operacji ani zmienić wcześniej zatwierdzonych etykiet.
- **Reason:** oddzielenie niezmiennego wejścia od ciężkich konsumentów pozwala
  odtworzyć dokładny dataset, porównać wersje i uruchomić retraining osobno.
  Uwzględnienie statusów pending/rejected w checksumie sprawia, że każda nowa
  decyzja tworzy nową wersję dowodu, mimo że rejected nie tworzy próbek.
- **Alternatives:** trening bezpośrednio z żywych tabel, automatyczny próg,
  eksport samych symboli albo nadpisywanie jednego pliku. Pierwsze trzy tracą
  dokładne pochodzenie i granicę decyzji człowieka, a ostatnie łamie audyt.
- **Consequences:** panel wymaga osobnego potwierdzenia, pokazuje licznik i
  historię wersji. Późniejszy retraining musi przyjąć checksum-bound eksport i
  może zmieniać sugestie tylko unresolved. Istniejący staging accepted/corrected
  pozostaje oddzielny; standardowa walidacja nadal blokuje luki, duplikaty i
  niekompletny zakres.
- **Supersedes:** implementuje granicę D-086 i korzysta z tożsamości cropu
  D-089; nie zmienia D-084 ani `massImportAllowed`.

## D-091 — Osobna lokalna aplikacja recenzenta poprzedza bezpieczny dostęp zdalny

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** stanowisko operacyjnego review nie jest częścią nawigacji
  panelu admina. Działa jako osobne `apps/reviewer` na osobnym porcie.
  Administrator wybiera grę i image import job, tworzy wygasającą lokalną sesję
  i otrzymuje link oraz osobny jednorazowo ujawniony kod. Kod nie znajduje się
  w linku i jest przechowywany wyłącznie jako hash. W lokalnym pionie wszystkie
  procesy nadal bindują wyłącznie loopback.
- **Context:** odbiór TASK-0111 wykazał, że użyteczny widok został błędnie
  osadzony w rozbudowanym panelu admina. Docelowy operator powinien otwierać
  minimalistyczną aplikację przez przekazany link i kod, zanim wdrożony zostanie
  transport internetowy.
- **Reason:** osobny frontend od razu ustanawia właściwą granicę produktu i
  pozwala iterować UX bez udostępniania CRUD konfiguracji. Lokalny kod umożliwia
  test przepływu, ale nie jest przedstawiany jako zamiennik HTTPS, limitu prób,
  odwołania i audytu wymaganych przed dostępem spoza komputera.
- **Alternatives:** dalsze osadzenie w panelu admina utrwala błędną granicę;
  natychmiastowe wystawienie portu do Internetu jest niebezpieczne; wspólny kod
  dla wszystkich gier nie ogranicza kontekstu.
- **Consequences:** TASK-0112 dostarcza lokalny frontend i sesję scope
  `(gameId, importJobId)`. M8.7 nadal odpowiada za bezpieczny ingress,
  persistent/revocable access, rate limiting i audyt aktora. D-087 pozostaje
  obowiązująca dla transportu zdalnego, ale lokalne wydzielenie UI i code gate
  nie są już odłożone.
- **Supersedes:** doprecyzowuje D-087 i zastępuje część D-086/D-087 mówiącą o
  osadzeniu lokalnego stanowiska w panelu admina.

## D-092 — Zatwierdzenie planszy jest pojedynczą, idempotentną akcją

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision:** pojedyncze `Enter` albo kliknięcie przycisku zatwierdzenia od
  razu wysyła pełną decyzję planszy. Nie jest wyświetlany modal potwierdzenia.
  Trwający zapis, `KeyboardEvent.repeat`, idempotency key i optimistic revision
  pozostają obowiązkowymi zabezpieczeniami.
- **Context:** właściciel po pierwszym kontakcie z ekranem odrzucił
  dwustopniowe potwierdzenie jako zbędne tarcie w seryjnej pracy.
- **Reason:** plansze kompletne pozostają edytowalne przez kolejną rewizję, a
  niezmienny audyt pozwala odtworzyć poprzedni stan. Dodatkowy modal nie daje
  proporcjonalnej ochrony, a obniża przepustowość operatora.
- **Alternatives:** podwójny Enter/modal, opóźniony zapis lub batch save.
- **Consequences:** testy klawiatury i instrukcje odbioru muszą zostać
  zaktualizowane. Akcje destrukcyjne, takie jak odrzucenie albo zamrożenie
  kohorty, mogą nadal wymagać osobnego potwierdzenia.
- **Supersedes:** zastępuje dwustopniowy Enter z TASK-0108 i D-086.

## D-093 — Sesja Reviewera nawiguje po pełnej kolejności plansz

- **Status:** accepted
- **Date:** 2026-07-30
- **Decision:** aktywna sesja Reviewera używa jednej deterministycznej
  kolejności wszystkich plansz wybranego importu. Zapis accepted/corrected nie
  usuwa bieżącego itemu z tej kolejki. Pojedyncze `Enter` zapisuje i przechodzi
  do następnego elementu, a nawigacja w lewo może wrócić do właśnie
  zatwierdzonej planszy. Pierwsze wejście i reload wybierają pierwszą pending;
  jeśli pending nie istnieje, wybierają pierwszą planszę importu.
- **Context:** odbiór operatorski wykazał, że filtrowanie aktywnej kolejki do
  pending usuwało item natychmiast po zapisie i uniemożliwiało naturalny powrót
  strzałką w lewo.
- **Reason:** status decyzji nie może zmieniać topologii bieżącej sesji.
  Stabilna pełna kolejność daje przewidywalną nawigację i nadal pozwala szybko
  wznowić pracę od pierwszego nierozwiązanego itemu po ponownym wejściu.
- **Alternatives:** osobne kolejki pending/completed, klientowa tablica całego
  importu albo ręczny powrót przez zmianę filtra. Pierwsza powoduje skok po
  zapisie, druga łamie bounded memory, a trzecia utrudnia seryjny review.
- **Consequences:** API udostępnia projekcję `all`, ale Reviewer zachowuje
  `limit = 1` i nie ładuje pełnej kolejki. Widoki pending/completed pozostają
  licznikami lub projekcjami statusu. Testy obejmują save-and-next, powrót do
  accepted oraz oba przypadki pozycji startowej.
- **Supersedes:** doprecyzowuje nawigację D-086 i zachowuje pojedynczą,
  idempotentną akcję zapisu D-092.

## D-094 — Grupa duplikatów może podpowiedzieć layout, ale nie pozycję sekwencji

- **Status:** accepted
- **Date:** 2026-07-30
- **Decision:** jeżeli po dopasowaniu niepełnego wejścia pozostało kilka
  rekordów, ale wszystkie mają dokładnie tę samą pełną sygnaturę layoutu,
  aplikacja mobilna może zaproponować uzupełnienie brakujących symboli tym
  layoutem. Po akceptacji exact match nadal zwraca `duplicate`; aplikacja nie
  wybiera żadnego `sequence_number` i nie uruchamia Target.
- **Context:** duplikaty tej samej planszy są dozwolone w danych. Obecny modal
  podpowiada tylko wtedy, gdy pozostał jeden rekord, mimo że kilka rekordów o
  jednej sygnaturze daje równie jednoznaczną podpowiedź symboli.
- **Reason:** jednoznaczność treści layoutu i jednoznaczność pozycji sekwencji są
  różnymi własnościami. Pierwsza wystarcza do bezpiecznego uzupełnienia planszy,
  druga jest nadal konieczna do uruchomienia Target.
- **Alternatives:** brak podpowiedzi dla każdej grupy duplikatów albo wybór
  pierwszego rekordu. Pierwsza opcja niepotrzebnie zwiększa pracę ręczną, a druga
  łamie zasadę braku arbitralnego wyboru duplikatu.
- **Consequences:** TASK-0116 doda distinct-signature matching, jawny wariant
  modala dla duplikatu oraz testy potwierdzające brak Target i brak wybranego
  numeru sekwencji.
- **Supersedes:** rozszerza automatyczną propozycję M1 bez zmiany D-008.

## D-095 — Zdalny Reviewer używa outbound-only Quick Tunnel i same-origin proxy

- **Status:** accepted
- **Date:** 2026-07-30
- **Decision:** czasowy dostęp v0.1 publikuje wyłącznie aplikację
  `apps/reviewer` przez Cloudflare Quick Tunnel. Reviewer pozostaje zbindowany
  do `127.0.0.1:3001`, a tunel tworzy wychodzące połączenie HTTPS. Same-origin
  proxy Reviewera przekazuje do FastAPI wyłącznie allowlistę scoped review;
  Admin, PostgreSQL, worker, eksporty i wydania nie mają publicznej trasy.
  Sesje są trwałe, odwoływalne, blokowane po pięciu błędnych kodach i wydają
  niejawny token przechowywany przez przeglądarkę wyłącznie jako HttpOnly cookie.
- **Context:** odbiorca ma wejść zwykłym linkiem z innego miasta bez instalacji
  VPN, domeny ani płatnego hostingu. Lokalny procesowy code gate z D-091 nie
  stanowił zabezpieczenia internetowego.
- **Reason:** outbound tunnel nie wymaga otwierania portu routera, a publiczny
  proxy pozwala technicznie odciąć całą powierzchnię Admin API. Quick Tunnel
  spełnia czasowy charakter prywatnych testów i może zostać uruchomiony oraz
  zatrzymany jedną komendą.
- **Alternatives:** Tailscale Funnel wymaga konfiguracji tailnetu i pozostaje
  usługą beta; VPN wymaga klienta po stronie odbiorcy; named Cloudflare Tunnel
  wymaga konta i domeny; surowy port forwarding jest niedopuszczalny.
- **Consequences:** link `trycloudflare.com` zmienia się po ponownym
  uruchomieniu i nie ma SLA. Test z sieci zewnętrznej pozostaje obowiązkową
  bramką TASK-0115. Stały adres albo tryb always-on wymagają named tunnel oraz
  osobnej decyzji operacyjnej.
- **Supersedes:** rozstrzyga Q-021 i materializuje zdalną część D-087/D-091.

## D-096 — Google Pixel 10 Pro XL jest jedyną bramką urządzeniową wersji 0.1

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** lokalna wersja `0.1` wymaga kompletnego odbioru wyłącznie na
  Google Pixel 10 Pro XL. Samsung Galaxy S21 Ultra pozostaje urządzeniem
  późniejszego testu kompatybilności, ale jego brak nie blokuje TASK-0041,
  TASK-0042, G3 ani wydania `0.1`.
- **Context:** właściciel zakończył automatyczny i ręczny odbiór Pixela oraz
  świadomie ograniczył pierwszą wersję produktu do jednego urządzenia.
- **Reason:** aplikacja jest prywatnym projektem zaliczeniowym instalowanym na
  maksymalnie kilku urządzeniach. Dla pierwszej kompletnej wersji ważniejszy
  jest zamknięty przepływ produktu niż powtarzanie tej samej bramki na drugim
  telefonie.
- **Alternatives:** utrzymanie obowiązkowego Pixela i Samsunga dla `0.1` albo
  całkowite usunięcie Samsunga z planu kompatybilności.
- **Consequences:** ocena M3.5 podejmuje decyzję adaptera na podstawie Pixela.
  Raport Samsunga może zostać dodany później bez zmiany artefaktu `0.1`.
- **Supersedes:** dla wersji `0.1` zastępuje dwuurządzeniowe wymaganie D-020,
  kryterium M1 w `MOBILE_APP.md` i dotychczasową bramkę TASK-0041/TASK-0042.

## D-097 — Lokalny Admin ufa właścicielowi Windows, ale mutacje chroni API

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** Admin wersji `0.1` pozostaje narzędziem jednego właściciela bez
  osobnego ekranu logowania i binduje wyłącznie loopback. Konto Windows,
  uprawnienia plików i loopback stanowią lokalną granicę dostępu. Zdalny
  Reviewer pozostaje osobną, ograniczoną powierzchnią i nigdy nie publikuje
  Admina. Operacje wysokiego wpływu wymagają serwerowego sygnału intencji,
  jednoznacznego celu i append-only audytu z aktorem `local-owner`; potwierdzenie
  obecne tylko w UI nie jest wystarczającym zabezpieczeniem.
- **Context:** audyt M8.1 potwierdził poprawne bindingi loopback oraz
  potwierdzenia w UI, ale bezpośrednie wywołania endpointów archiwizacji,
  odrzucenia stagingu i anulowania jobu mogą ominąć warstwę prezentacji.
  Administracyjne mutacje nie mają również jednego wspólnego audytu aktora.
- **Reason:** lokalne hasło na tym samym przejętym komputerze tworzyłoby
  pozorną ochronę. Egzekwowanie intencji, celu, konfliktu i audytu w API chroni
  natomiast przed realnym obejściem UI, przypadkową mutacją i utratą śladu.
- **Alternatives:** pełny system kont lokalnych, zaufanie wyłącznie do
  potwierdzeń React albo wystawienie Admina przez mechanizm Reviewera.
- **Consequences:** TASK-0079 dodaje guard mutacji, audyt, regresję loopback,
  ochronę cross-origin oraz redakcję sekretów. Wiele lokalnych kont lub
  publiczny Admin wymaga nowej decyzji. M8 core może być realizowany dla
  lokalnej wersji `0.1` niezależnie od zablokowanej automatycznej publikacji
  masowego importu w TASK-0076.
- **Supersedes:** doprecyzowuje lokalną część D-021 i D-087; nie zmienia
  zdalnego modelu D-095.

## D-098 — Admin steruje tylko przypiętym lifecycle’em publicznego Reviewera

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** `Utwórz link i wystaw online` wykonuje kolejno kontrolowany
  start produkcyjnego Reviewera, start outbound-only Quick Tunnel i utworzenie
  game/import-scoped sesji. `Zatrzymaj udostępnianie` próbuje unieważnić
  bieżącą sesję i zatrzymuje tunel. FastAPI może wywołać wyłącznie trzy stałe
  skrypty `start/status/stop` z timeoutem; request nie może podać komendy,
  procesu, portu ani URL. Serwer developerski jest blokowany.
- **Context:** wcześniejszy TASK-0115 wymagał ręcznego uruchomienia Reviewera i
  tunelu w PowerShellu przed utworzeniem sesji, czego właściciel nie uznał za
  docelowy przepływ operatorski.
- **Reason:** jeden jawny przycisk ogranicza błędy kolejności, a przypięty
  kontroler zachowuje granicę bezpieczeństwa i nie tworzy ogólnego zdalnego
  wykonania poleceń. Blokada trybu developerskiego zapobiega publikacji
  słabszej konfiguracji CSP.
- **Alternatives:** pozostawienie czterech ręcznych komend, ogólny runner
  poleceń z panelu albo publiczny binding Admina/API.
- **Consequences:** produkcyjny build Reviewera musi istnieć przed kliknięciem.
  API może oczekiwać maksymalnie 25 sekund na tę małą operację lifecycle, ale
  nie wykonuje builda. CLI pozostaje ścieżką awaryjną. Zewnętrzny odbiór
  TASK-0115 nadal jest wymagany do zamknięcia G8.7.
- **Supersedes:** rozszerza operatorską część D-095 bez zmiany transportu,
  scope ani modelu sesji.

## D-099 — Lokalne mutacje używają stałej intencji i niezależnego audytu JSONL

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** wszystkie niebezpieczne metody lokalnego Admin API wymagają
  loopback, dozwolonego originu i stałej intencji `local-owner`. Jawna mapa
  operacji wysokiego wpływu wymaga dodatkowo potwierdzenia i dokładnego celu.
  Odrzucenia, autoryzacje i wyniki są zapisywane append-only do kontrolowanego,
  redagowanego artefaktu JSONL, niezależnie od transakcji domenowej.
- **Context:** D-097 odrzuciła pozorne lokalne logowanie, ale istniejące modale
  React nie chroniły bezpośredniego requestu ani nie zapewniały wspólnego audytu
  serwerowego aktora.
- **Reason:** własny nagłówek intencji wymusza preflight dla obcej strony,
  dokładny target blokuje omyłkę celu, a audit przed i po wywołaniu zachowuje
  ślad również wtedy, gdy domenowa transakcja zostanie odrzucona. JSONL nie
  wymaga osobnej transakcji PostgreSQL i można objąć go backupem artefaktów.
- **Alternatives:** lokalne hasło jednego właściciela, same potwierdzenia UI,
  audyt wyłącznie w tabelach domenowych albo publiczny system kont i ról.
- **Consequences:** oficjalny klient Admina zawsze wysyła intencję, operacje
  wysokiego wpływu mają kontrakt OpenAPI z confirmation/target, a ręczne
  narzędzia operatorskie muszą podać te same nagłówki. Plik audytu należy objąć
  backupem i nie może zawierać body ani sekretów. Reviewer zachowuje osobną
  allowlistę Bearer i nie dziedziczy uprawnień `local-owner`.
- **Supersedes:** realizuje D-097; nie zmienia D-095 ani D-098.

## D-100 — Wersja 0.1 zamyka reprezentatywny dataset 500k, a hardening i Admin przechodzą do 0.2

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** wersja `0.1` zostanie zamknięta przez TASK-0118 i TASK-0119 jako
  całkowicie offline APK dla Google Pixel 10 Pro XL z jedną grą i dokładnie
  500 000 layoutów. Ponad 100 ręcznie zatwierdzonych layoutów stanowi
  chroniony podzbiór, a brakujące rekordy powstają deterministycznie z
  zapisanym seedem, wersją generatora i checksumem. Wydanie używa grafik
  symboli z zatwierdzonych cropów, znanych nazw, 10 jawnych paylines oraz
  deterministycznych testowych minimów i payoutów. Przebudowa Admina,
  TASK-0076 i niezakończone M8.2–M8.6 (TASK-0080–0089) przechodzą do wersji
  `0.2`.
- **Context:** podstawowy przepływ mobile, Admin, pipeline wydania, Reviewer,
  ochrona lokalnego API i benchmark 500 000 rekordów już działają. Pełny
  rzeczywisty dataset zdjęciowy pozostaje zablokowany jakością klasyfikacji, a
  dotychczasowy Admin jest funkcjonalny, lecz zbyt długi i techniczny. Dalsze
  oczekiwanie na perfekcyjną automatyzację opóźniałoby sprawdzenie kompletnego
  produktu na telefonie.
- **Reason:** reprezentatywne dane pozwalają zweryfikować od początku do końca
  ergonomię, matching, duplikaty, Target, rozmiar i wydajność bez fałszywego
  przedstawiania danych syntetycznych jako wyniku rozpoznawania. Osobna wersja
  `0.2` daje bezpieczny zakres na przebudowę Admina i operacyjny hardening.
- **Alternatives:** blokowanie `0.1` do czasu TASK-0076 i całego G8 albo wydanie
  mniejszego snapshotu, który nie sprawdza docelowej skali.
- **Consequences:** `0.1` jest funkcjonalnym wydaniem demonstracyjnym, a nie
  finalnie zahardeningowanym systemem odzyskiwania po awarii. TASK-0118 nie
  zalicza TASK-0076 ani G7, a dane dopełniające muszą być jawnie oznaczone jako
  deterministyczne dane testowe. Ukończone G8.1 i G8.7 pozostają obowiązujące.
  Na początku `0.2` właściciel odpowie na zebrane Q-022–Q-032 przed
  implementacją TASK-0120–0133.
- **Supersedes:** zmienia alokację wydaniową pozostałych zadań M7/M8 bez zmiany
  ich wymagań i bramek; nie zmienia D-096 dla odbioru Pixela ani zasad domeny.

## D-101 — Wersja 0.2 używa czystej bazy i małego datasetu, a pełne dane przechodzą do 0.3

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** po zbudowaniu statycznej paczki `0.1` można rozpocząć prace nad
  `0.2` przed zakończeniem odbioru urządzeniowego TASK-0119. Pierwszym zadaniem
  `0.2` jest kontrolowany reset lokalnego PostgreSQL do pustego, zmigrowanego
  baseline’u. Reset nie obejmuje paczki `0.1`, klucza podpisującego, kodu,
  dokumentacji ani źródłowych plików poza bazą. Wersja `0.2` waliduje Admina i
  pełny workflow na jednej grze oraz małym, jawnie ograniczonym datasecie.
  Pełny rzeczywisty dataset, około 500 000 layoutów, nowe gry, wielogrowe
  wydanie, TASK-0076 i TASK-0080–0089 należą do `0.3`.
- **Context:** paczka `0.1.5 (6)` jest gotowa, ale jej odbiór na Pixelu będzie
  wykonany później. Dotychczasowa baza zawiera dane kolejnych eksperymentów,
  importów, jobów i review, które utrudniają sprawdzenie nowego UX od czystego
  stanu. Jednoczesne wymaganie przebudowy Admina i pełnego datasetu w `0.2`
  tworzyłoby zbyt szeroką bramkę oraz utrudniało diagnozę błędów funkcjonalnych.
- **Reason:** mały, kontrolowany zbiór wystarcza do walidacji nawigacji,
  importu, symboli, reguł, review, payoutów i orkiestracji wydania. Pełna skala
  powinna zostać uruchomiona dopiero po zaakceptowaniu ergonomii obu wersji i
  naprawieniu znalezionych błędów.
- **Alternatives:** blokowanie `0.2` do zamknięcia wszystkich testów `0.1`,
  zachowanie historycznej bazy jako startowego stanu albo jednoczesna realizacja
  nowego UX, pełnych danych, nowych gier i hardeningu.
- **Consequences:** TASK-0120 zostaje nowym pierwszym zadaniem `0.2`, a
  dotychczasowe rezerwacje TASK-0120–0133 przesuwają się na TASK-0121–0134.
  Testy `0.2` nie zaliczają bramki pełnej skali. Start `0.3` wymaga akceptacji
  testów `0.1` i `0.2` oraz zamknięcia wymaganych poprawek. Szczegóły historyczne
  pozostają w ukończonych zadaniach i Decision Log, dlatego `CURRENT_STATE` jest
  utrzymywany jako krótki handoff zamiast dziennika wszystkich wyników.
- **Supersedes:** zastępuje część D-100 przypisującą TASK-0076 i TASK-0080–0089
  do `0.2`; nie zmienia zakresu ani artefaktów wydania `0.1`.

## D-102 — Usuwanie gry jest odłożone, a 0.2 używa archiwizacji i filtrów

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** docelowa operacja `Usuń grę` ma kaskadowo usunąć grę oraz
  należące do niej rekordy. Nie będzie jednak implementowana w wersji `0.2`.
  Katalog gier `0.2` udostępni filtry `Aktywne`, `Szkice`, `Zarchiwizowane` i
  odwracalną archiwizację.
- **Context:** właściciel będzie usuwał gry rzadko i w bieżącej wersji bardziej
  potrzebuje czytelnej organizacji katalogu niż destrukcyjnego workflow.
- **Reason:** odłożenie operacji pozwala uniknąć niepełnej kaskady obejmującej
  importy, reguły, review, wydania i audyt. Archiwizacja realizuje bieżącą
  potrzebę bez utraty danych.
- **Alternatives:** usuwanie wyłącznie pustego szkicu albo natychmiastowa
  implementacja pełnej kaskady w `0.2`.
- **Consequences:** TASK-0122 obejmuje filtry i archiwizację, ale nie przycisk
  `Usuń`. Późniejsze zadanie usuwania musi jawnie zdefiniować wszystkie
  zależności, audyt, potwierdzenie dokładnego celu i zachowanie artefaktów
  wydań, zanim otrzyma zgodę na operację destrukcyjną.
- **Supersedes:** rozstrzyga Q-022 i zawęża zakres TASK-0122 bez zmiany
  pozostałych zadań 0.2.

## D-103 — Usunięcie wydania Android jest pełne i nie zapewnia powrotu

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** jawna operacja `Usuń wydanie` ma usunąć rekord wybranego
  wydania Android oraz jego APK, snapshot, manifest, checksumy i dedykowane
  artefakty. Nie zachowujemy dostępnej historii starej wersji ani możliwości
  przywrócenia jej z panelu. Pozostaje tylko minimalny append-only wpis audytowy
  potwierdzający wykonanie operacji.
- **Context:** właściciel nie planuje wracać do wersji uznanych za zbędne i
  chce usuwać je całkowicie zamiast utrzymywać katalog historyczny.
- **Reason:** pełne usunięcie odpowiada prostemu prywatnemu modelowi eksploatacji
  i odzyskuje zarówno miejsce, jak i usuwa niepotrzebne rekordy z UI.
- **Alternatives:** usuwanie wyłącznie APK/snapshotu przy zachowaniu rekordu,
  manifestu i checksum albo bezterminowa retencja wszystkich wydań.
- **Consequences:** operacja jest nieodwracalna, musi wymagać dokładnego celu i
  mocnego potwierdzenia oraz usuwać pliki dopiero w kontrolowanym workflow.
  Nie może usunąć innego wydania przez wspólną ścieżkę artefaktu. Zwykły audyt
  operacji pozostaje zgodny z D-099, ale nie służy odtworzeniu wersji.
- **Supersedes:** rozstrzyga Q-023 i zmienia rekomendowaną politykę cleanupu
  wydania w Adminie 0.2.

## D-104 — Joby mają własny prosty workspace bez automatycznej retencji

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** główna nawigacja Admina `0.2` ma trzy zakładki: `Zarządzanie
grami`, `Wersje Android` i `Joby`. Trzecia zakładka pokazuje listę, postęp i
  proste filtrowanie po statusie. `0.2` nie dodaje automatycznej retencji ani
  osobnej logiki cleanupu jobów.
- **Context:** joby są potrzebne do obserwacji importu, przeliczania i buildów,
  ale mieszanie ich z formularzami gry i wydania zaśmiecało długi panel.
- **Reason:** osobny, prosty workspace zachowuje widoczność postępu bez
  rozbudowy polityk operacyjnych, których mała lokalna instalacja jeszcze nie
  potrzebuje.
- **Alternatives:** pokazywanie jobów wyłącznie kontekstowo przy każdej operacji
  albo dodanie rozbudowanej retencji, wyszukiwania i cleanupu już w `0.2`.
- **Consequences:** TASK-0121 buduje trzy tryby nawigacji, a TASK-0132 realizuje
  prostą zakładkę `Joby` i filtr statusu zamiast usuwać globalny widok. Ekrany
  źródłowe mogą pokazać identyfikator utworzonego joba i link do jego widoku,
  ale nie duplikują pełnej listy.
- **Supersedes:** rozstrzyga Q-024 i zastępuje wcześniejszy kierunek
  kontekstowych jobów w planie Admina 0.2.

## D-105 — Folder zdjęć wybiera natywny dialog Windows uruchamiany lokalnie

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** Admin `0.2` udostępnia przycisk `Wybierz folder`, który przez
  kontrolowany lokalny backend otwiera standardowe okno wyboru folderu Windows.
  Backend po wyborze waliduje istnienie, dostępność i obsługiwane pliki. Ręczne
  wpisanie ścieżki nie jest wymagane w podstawowym workflow.
- **Context:** zwykła aplikacja webowa nie może dowolnie przeglądać lokalnego
  systemu plików, natomiast Admin i backend działają lokalnie na komputerze
  właściciela.
- **Reason:** natywny dialog jest prostszy i mniej podatny na błędy ścieżki niż
  ręczne kopiowanie pełnej nazwy katalogu.
- **Alternatives:** wyłącznie tekstowe pole ścieżki albo upload wszystkich
  obrazów przez przeglądarkę.
- **Consequences:** endpoint otwierający dialog musi pozostać wyłącznie na
  loopback, nie może przyjmować zdalnego wywołania Reviewera i zwraca tylko
  zatwierdzoną ścieżkę. TASK-0123 obejmuje dialog oraz walidację folderu.
- **Supersedes:** rozstrzyga Q-025.

## D-106 — Admin pokazuje jeden workspace reguł, a backend zachowuje wersje

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** użytkownik widzi jeden bieżący workspace reguł. Zapis zmian
  tworzy draft, a publikacja nową niezmienną wersję backendową; opublikowanej
  wersji nie nadpisuje się w miejscu.
- **Context:** pełna historia wersji zaśmiecała panel, ale wydania Android muszą
  pozostać związane z dokładnymi regułami.
- **Reason:** prosty UI nie wymaga rezygnacji z odtwarzalności danych.
- **Alternatives:** widoczna pełna historia albo nadpisywanie publikacji.
- **Consequences:** TASK-0127 ukrywa historię z głównego widoku, zachowując
  obecny niezmienny model domenowy.
- **Supersedes:** rozstrzyga Q-026.

## D-107 — Oczekiwana liczba layoutów jest konfigurowalna z domyślnym 500 000

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** gra ma prostą konfigurację `expected_layout_count`, domyślnie
  `500 000`; dataset zamraża użyte oczekiwanie. `0.2` może ustawić małą wartość
  testową. Pole nie generuje syntetycznie brakujących rekordów.
- **Context:** obecnie każda docelowa gra prawdopodobnie będzie miała 500 000
  layoutów, ale niewielki koszt konfiguracji chroni model przed sztywną stałą i
  umożliwia kontrolowane testy 0.2.
- **Reason:** konfiguracja jest prostsza niż późniejsza migracja twardego limitu.
- **Alternatives:** stałe 500 000 w kodzie albo dowolna liczba bez domyślnej.
- **Consequences:** TASK-0124 i migracja danych dodają dodatnie oczekiwanie;
  publikacja porównuje je z faktycznym `layout_count`.
- **Supersedes:** rozstrzyga Q-027.

## D-108 — Ręczny sequence number jest opcjonalną decyzją review

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** administrator może ręcznie zaakceptować lub poprawić numer
  sekwencji, ale nie musi. Może pozostawić brak i doładować lepsze lub nowe
  zdjęcia. Surowa odpowiedź OCR pozostaje niezmieniona.
- **Context:** niska jakość obrazu może uniemożliwić pewny OCR, a kolejne źródło
  może rozwiązać problem bez ręcznego numerowania.
- **Reason:** oba sposoby uzupełnienia braków są potrzebne i audytowalne.
- **Alternatives:** wyłącznie OCR albo obowiązkowa ręczna korekta każdego braku.
- **Consequences:** TASK-0124 waliduje ręczny zakres i konflikty, ale pozwala
  kontynuować doładowanie zdjęć bez wymuszania wartości.
- **Supersedes:** rozstrzyga Q-028.

## D-109 — Wybór źródła sekwencji jest automatyczny z ręcznym override

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** pipeline szereguje zdjęcia tej samej sekwencji według jawnych
  metryk i domyślnie wybiera najlepsze. Reviewer pokazuje kandydatów i pozwala
  człowiekowi zmienić wybór z zachowaniem pochodzenia.
- **Context:** automatyczny ranking przyspiesza import, ale nie zawsze rozpozna
  częściowe przycięcie lub lokalną nieczytelność symbolu.
- **Reason:** człowiek zachowuje finalną kontrolę bez ręcznego wybierania każdego
  poprawnego przypadku.
- **Alternatives:** wyłącznie ranking albo obowiązkowy ręczny wybór.
- **Consequences:** TASK-0124 zapisuje metryki, kolejność i jawny override.
- **Supersedes:** rozstrzyga Q-029.

## D-110 — Konflikt liczby klastrów symboli wymaga decyzji użytkownika

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** inna liczba klastrów niż oczekiwana blokuje automatyczne
  utworzenie katalogu symboli. Użytkownik scala warianty jakości tego samego
  symbolu, rozdziela błędne scalenie albo przypisuje kandydatów.
- **Context:** dodatkowy klaster często reprezentuje ten sam symbol w gorszej
  jakości, a brak klastra może oznaczać połączenie dwóch różnych symboli.
- **Reason:** ciche dopasowanie liczby zanieczyściłoby etykiety i kolejne dane.
- **Alternatives:** automatyczne obcinanie/dodawanie albo przyjęcie liczby modelu.
- **Consequences:** TASK-0125 potrzebuje prostego stanu konfliktu i ręcznego
  rozstrzygnięcia przed nadaniem stabilnych `mobile_code`.
- **Supersedes:** rozstrzyga Q-030.

## D-111 — Import kopiuje oryginały do kontrolowanego storage

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** obrazy wybrane w folderze są kopiowane content-addressed do
  zarządzanego `data/originals`, z checksumą i pochodzeniem. Dalszy pipeline nie
  zależy od pierwotnego folderu.
- **Context:** użytkownik może przenieść albo usunąć folder po imporcie, a
  wznowienie i Reviewer nadal muszą działać.
- **Reason:** zarządzana kopia upraszcza odtwarzalność i późniejszy backup.
- **Alternatives:** przetwarzanie wyłącznie in-place albo upload przez browser.
- **Consequences:** TASK-0123 kopiuje i deduplikuje bajty; późniejsze testy mogą
  ponownie ocenić politykę, jeśli rozmiar okaże się problemem.
- **Supersedes:** rozstrzyga Q-031.

## D-112 — Reset layoutów przywraca grę do stanu sprzed importu

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** `Wyczyść layouty i dane powiązane` zachowuje rekord gry, ale
  usuwa wszystkie game-scoped dane i pliki utworzone w workflow importu,
  symboli, reguł, review, datasetów, payoutów i wydań. Współdzielone bloby
  pozostają do zaniku ostatniej referencji; minimalny audyt resetu zostaje.
- **Context:** właściciel oczekuje efektu odpowiadającego stanowi bezpośrednio
  przed pierwszym wczytaniem layoutów dla danej gry.
- **Reason:** częściowe usunięcie pozostawiałoby osierocone lub mylące dane.
- **Alternatives:** usuwanie jednego stagingu albo blokada danych użytych przez
  wydanie.
- **Consequences:** TASK-0133 wymaga read-only preview pełnej kaskady, mocnego
  potwierdzenia, ochrony danych innej gry i raportu częściowych błędów. Operacja
  nie usuwa plików z pierwotnego folderu użytkownika.
- **Supersedes:** rozstrzyga Q-032 i rozszerza cleanup 0.2.

## D-113 — Wybór folderu używa krótkotrwałego capability tokenu

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** natywny dialog jest wywoływany przez stały, loopback-only
  endpoint. Backend zapisuje zatwierdzoną ścieżkę w pamięci procesu na 15 minut
  i zwraca losowy, jednorazowy token. Utworzenie importu przyjmuje token i
  `game_id`, a nie dowolną ścieżkę z przeglądarki. Sam dialog ma limit 120
  sekund; skanowanie, checksumy i kopiowanie wykonuje później worker.
- **Context:** blokujący request nie może wykonywać długiego importu, a pole
  tekstowe pozwalałoby frontendowi wskazać dowolny katalog lokalny.
- **Reason:** krótki token zachowuje wygodę natywnego wyboru i jednocześnie
  oddziela niezaufany kontrakt HTTP od uprawnień systemu plików.
- **Alternatives:** pełna ścieżka w body, upload przez browser albo trwała sesja
  wyboru w PostgreSQL.
- **Consequences:** restart API unieważnia niezrealizowany wybór i wymaga
  ponownego kliknięcia `Wybierz folder`. Po utworzeniu joba dalszy stan jest
  trwały. TASK-0123 wprowadza ten kontrakt bez migracji bazy.
- **Supersedes:** uszczegóławia D-105 bez zmiany decyzji użytkownika.

## D-114 — Reguły mają jeden bieżący workspace nad niezmiennymi wersjami

- **Status:** accepted
- **Date:** 2026-07-31
- **Decision:** Admin wybiera najnowszy draft, a gdy go nie ma — najnowszą
  opublikowaną wersję. Rozpoczęcie edycji wersji opublikowanej tworzy pełny
  draft-kopię wraz z paylines, konfiguracją symboli i payoutami. Ponowienie
  zwraca istniejący draft. Historia pozostaje wewnętrzna i nie zajmuje głównego
  ekranu.
- **Context:** dotychczasowy ekran wymagał ręcznego zarządzania listą wersji, a
  nowy draft był pusty, przez co prosta korekta reguł wymagała odtwarzania całej
  konfiguracji.
- **Reason:** użytkownik pracuje nad jedną konfiguracją, a backend nadal
  zachowuje dokładne, niezmienne źródła snapshotów i wydań Android.
- **Alternatives:** edycja opublikowanej wersji w miejscu albo pusty draft
  tworzony ręcznie dla każdej korekty.
- **Consequences:** TASK-0127 dodaje jawną operację kopiowania wersji; nie
  usuwa historii ani nie zmienia kontraktu istniejących mutacji draftu.

## D-115 — Wersja 0.3 dostosowuje Mobile, a pełna skala pierwotnie przechodzi do 0.4

- **Status:** superseded by D-123 for the full-scale release assignment
- **Date:** 2026-08-01
- **Decision:** wersja 0.3 obejmuje kompaktowy interfejs i usprawnienia
  przepływu aplikacji mobilnej. Pełny rzeczywisty dataset, nowe gry, końcowe
  testy dużych zbiorów, TASK-0076 i TASK-0080–0089 należą do wersji 0.4.
- **Context:** przed kosztowną bramką danych użytkownik chce poprawić ergonomię
  działającej aplikacji i wykonywać Target na wybieranym oknie.
- **Reason:** rozdzielenie zmian UX od masowego importu ogranicza zakres regresji
  i pozwala ocenić zachowanie interfejsu na istniejącym artefakcie.
- **Alternatives:** zachowanie pełnej skali w 0.3 albo wdrożenie UX i danych w
  jednym wydaniu.
- **Consequences:** plan 0.3 otrzymuje TASK-0135–0141, a dotychczasowy zakres
  0.3 został pierwotnie zachowany w planie 0.4; D-123 przesuwa pełną skalę do
  0.5, nie zmieniając zakresu mobilnego 0.3.
- **Supersedes:** zmienia wyłącznie przypisanie wersji w D-101; nie zmienia
  zasad danych ani bramek jakości M7/M8.

## D-116 — Mobile używa dokładnego limitu Targetu i anchora dla Next

- **Status:** accepted
- **Date:** 2026-08-01
- **Decision:** użytkownik podaje `target_scan_limit` w polu liczbowym: domyślnie
  10 000, minimum 1 000, maksimum 500 000. Engine ocenia
  `min(target_scan_limit, N - 1)` przyszłych spinów. `Next` działa wyłącznie z
  jednoznacznego anchora `sequence_number`, przechodzi cyklicznie do następnej
  pozycji, przelicza Target i jest jednym krokiem Undo.
- **Context:** liniowy suwak dla zakresu 500:1 byłby nieprecyzyjny, a duplikat
  layoutu nadal nie może arbitralnie wybrać pozycji sekwencji.
- **Reason:** input pozwala podać dokładny zasięg przy małej wysokości UI, a
  anchor zachowuje deterministyczność nawigacji i obliczeń.
- **Alternatives:** suwak, zawsze pełny cykl albo Next wybierający pierwsze
  wystąpienie duplikatu.
- **Consequences:** adapter SQLite dostarcza ograniczone okno payoutów, wynik
  jawnie opisuje ocenioną liczbę spinów, a zmiana limitu unieważnia poprzedni
  skan. Pełny cykl pozostaje dostępny przez limit co najmniej `N - 1`.
- **Supersedes:** rozszerza D-003 i D-004 bez zmiany definicji pełnego cyklu.

## D-117 — Mobilny symbol ma opcjonalne etykiety polską i angielską

- **Status:** accepted
- **Date:** 2026-08-01
- **Decision:** kanoniczny symbol i snapshot schema v3 otrzymują opcjonalne
  `name_pl` oraz `name_en`. Selection pokazuje krótszą niepustą etykietę, przy
  remisie polską, a wymagane dotychczas `name` pozostaje fallbackiem.
- **Context:** obecny kontrakt przenosi tylko jedną nazwę, więc UI nie może
  deterministycznie wybrać krótszej wersji językowej.
- **Reason:** jawne dane są odtwarzalne i skalują się na nowe symbole; UI nie
  powinien zgadywać tłumaczeń ani utrzymywać słownika zależnego od gry.
- **Alternatives:** wbudowany słownik w aplikacji, automatyczne tłumaczenie albo
  używanie zawsze jednej dotychczasowej nazwy.
- **Consequences:** TASK-0136 obejmuje migrację Alembic, pola w istniejącym
  kontrakcie i formularzu symbolu, generator i walidator schema v3 oraz fallback
  dla danych bez lokalizacji. Istniejące APK i snapshot v2 pozostają niezmienne.
- **Supersedes:** brak.

## D-118 — Folder zdjęć wybiera przeglądarka, a API przyjmuje kontrolowany upload

- **Status:** accepted
- **Date:** 2026-08-01
- **Decision:** Admin `0.2` otwiera selektor folderu synchronicznie przez ukryty
  `input type=file` z wyborem katalogu. JPEG-i są przesyłane pojedynczo do
  kontrolowanego stagingu API, walidowane i finalizowane do jednorazowego
  capability tokenu. Główny UI nie uruchamia PowerShella ani systemowego
  dialogu przez blokujący request backendu.
- **Context:** dialog Windows uruchamiany przez ukryty proces API nie pojawiał
  się użytkownikowi, pozostawiał request w stanie `Otwieranie…` i globalną
  blokadę `IMAGE_FOLDER_PICKER_ALREADY_OPEN` także po zmianie gry.
- **Reason:** standardowy selektor przeglądarki jest bezpośrednio związany z
  gestem użytkownika, nie dziedziczy widoczności procesu backendu i nie może
  pozostawić osieroconego procesu wyboru.
- **Alternatives:** dalsze dostrajanie właściciela okna PowerShell, ręczne pole
  ścieżki albo aplikacja desktopowa Electron/Tauri.
- **Consequences:** wybór wymaga lokalnej kopii plików do stagingu i jawnego
  postępu. API ogranicza liczbę oraz rozmiar, waliduje każdy JPEG, sprząta
  anulowane i wygasłe wybory, a CORS dopuszcza kontrolowany `PUT` oraz nagłówek
  `X-Image-Relative-Path`. Legacy endpoint Windows pozostaje chwilowo zgodny,
  lecz nie jest używany przez Admin UI.
- **Supersedes:** zastępuje D-105 oraz część D-113 dotyczącą sposobu otwierania
  dialogu; zachowuje jednorazowy token i lokalną granicę bezpieczeństwa.

## D-119 — Iteracyjne uczenie jest skumulowane, per gra i nie zmienia decyzji człowieka

- **Status:** accepted
- **Date:** 2026-08-01
- **Decision:** Ulepszanie klasyfikatora symboli działa jako jawny batchowy
  trening od początku na całej zamrożonej, skumulowanej kohorcie jednej gry.
  `accepted` i `corrected` są kanonicznymi przykładami treningowymi,
  `rejected` pozostaje chronioną decyzją bez udziału w treningu, a tylko
  aktualne `pending` może otrzymać nową rewizję predykcji. Kandydat wymaga
  osobnej bramki i jawnej aktywacji; import przypina model przy tworzeniu joba.
- **Context:** właściciel chce poprawiać dokładność po około 100, następnie 1000
  i kolejnych ręcznie zweryfikowanych planszach oraz używać lepszego modelu dla
  nowych zdjęć, bez ryzyka utraty pewnych danych człowieka.
- **Reason:** skumulowany trening od początku ogranicza zapominanie klas i jest
  łatwiejszy do odtworzenia niż online fine-tuning. Oddzielenie treningu,
  bramki i aktywacji zapobiega wdrożeniu regresji, a warunkowy zapis tylko dla
  `pending` chroni równoległą pracę Reviewera.
- **Alternatives:** uczenie online po każdej decyzji, fine-tuning tylko na
  ostatniej delcie, automatyczna aktywacja albo przeliczenie wszystkich plansz.
- **Consequences:** potrzebne są TASK-0143–0150, rejestr modeli, niezmienne
  manifesty, source-aware split i trwałe joby. Progi 100/1000 są doradcze.
  Geometria i OCR pozostają osobnymi pętlami. M6.6 jest bramką przed pełnym
  automatycznym importem 0.5.
- **Supersedes:** rozszerza D-086 i zachowuje jej ochronę decyzji człowieka.

## D-120 — Kontroler Reviewera normalizuje środowisko Windows i ma 60 sekund na zimny start

- **Status:** accepted
- **Date:** 2026-08-01
- **Decision:** API rekonstruuje środowisko kontrolera bez nazw zmiennych
  kolidujących wielkością liter, a skrypt startowy scala odziedziczone `Path` i
  `PATH` do jednego kanonicznego `Path` przed każdym `Start-Process`. Zimny start
  produkcyjnego Reviewera i Quick Tunnel pozostaje synchroniczny, ale ma
  twardy timeout 60 sekund: do 20 sekund na Reviewer i do 30 sekund na URL
  Cloudflare oraz ograniczony narzut kontrolera.
- **Context:** Windows odziedziczył jednocześnie `Path` i `PATH`. PowerShell
  przy przekierowaniu logów próbował dodać oba do case-insensitive dictionary i
  przerywał start kodem `REVIEWER_INGRESS_COMMAND_FAILED`. Pomiar zimnego Next.js
  wyniósł 8,1 sekundy, a Quick Tunnel może przekroczyć dotychczasowe 10 sekund.
- **Reason:** Windows ma jedną semantyczną zmienną ścieżki; normalizacja usuwa
  przyczynę niezależnie od terminala i restartu. Nadal ograniczony timeout
  uwzględnia rzeczywisty zimny start bez wprowadzania joba ani dowolnego runnera.
- **Alternatives:** wymaganie restartu komputera, jednorazowe usunięcie `PATH` w
  terminalu, pozostawienie 25 sekund albo asynchroniczny job dla małej operacji.
- **Consequences:** ręczny CLI i kliknięcie w Adminie używają wspólnego helpera.
  Dodano regresję uruchamiającą proces z przekierowaniem logów. Błąd sieci nadal
  kończy się najpóźniej po 60 sekundach i nie tworzy aktywnego publicznego stanu.
  Kontroler wykonuje przed startem bounded 5-sekundowy test TCP do
  `api.trycloudflare.com:443`, dzięki czemu proces bez wychodzącego HTTPS zwraca
  przyczynę od razu zamiast mylącego timeoutu publikacji URL.
- **Supersedes:** zmienia wyłącznie limit 25 sekund z D-098; zachowuje wszystkie
  jej granice bezpieczeństwa i stałe komendy start/status/stop.

## D-121 — Reprezentatywne zdjęcia wybiera osobny, niedestrukcyjny preselektor

- **Status:** accepted
- **Date:** 2026-08-02
- **Decision:** Panel Admin otrzymuje czwarty workspace `Selekcja zdjęć`.
  Osobny job `image_selection` wykonuje tani strumieniowy skan miniatur,
  geometrii, jakości, fingerprintu i punktowego OCR, wybierając jedno zdjęcie na
  dowolny rozpoznany zakres. Nie uruchamia cropów komórek ani klasyfikacji
  symboli. Folder użytkownika pozostaje read-only; wynik jest kontrolowaną
  kopią z checksumowanym manifestem i jawnym handoffem do `Importu layoutów`.
- **Context:** katalog 10 000–30 000 zdjęć może zawierać 50–100 różnych ujęć
  tego samego ekranu. Pełny pipeline na każdym pliku tworzyłby tysiące
  zbędnych cropów i review oraz trwałby wiele godzin lub dni. Zakresy są zwykle
  ułożone grupami, ale mogą skakać, na przykład z `19–27` do `400–408`.
- **Reason:** osobny lifecycle umożliwia niezależny retry, benchmark i manualne
  wyjątki. Strumieniowe grupowanie ogranicza kosztowne OCR/weryfikacje do
  liczby grup × top-k, a kopia zamiast move/delete zachowuje odtwarzalność i
  chroni przed utratą danych przy błędnej decyzji algorytmu.
- **Alternatives:** usuwanie lub przenoszenie plików źródłowych, checkbox przed
  pełnym pipeline'em w `Imporcie layoutów`, pełne rozpoznanie każdego zdjęcia,
  model chmurowy albo nowy mikroserwis.
- **Consequences:** TASK-0151–0157 tworzą M7.0 wersji 0.4. Historyczna wersja
  0.2 zachowuje swoją bramkę trzech workspace'ów. Pełny import TASK-0076 należy
  do 0.5, wymaga przejścia bramki selektora oraz nadal podlega M6.6. Niepewność
  zwiększa manual review, ale nie może tworzyć błędnego automatycznego zakresu.
- **Supersedes:** nie zastępuje D-118; reużywa jego browser-native upload i
  dodaje poświadczony purpose dla preselektora.

## D-123 — Wersja 0.4 dostarcza selektor, a duże datasety zaczynają się w 0.5

- **Status:** accepted
- **Date:** 2026-08-02
- **Decision:** wersja 0.4 obejmuje wyłącznie M7.0 i TASK-0151–0157: osobny
  moduł selekcji reprezentatywnych zdjęć, manualny fallback, bezpieczny output,
  handoff oraz benchmark selektora 10k/30k. Wersja 0.5 rozpoczyna pracę na
  większych rzeczywistych datasetach i obejmuje M6.6, TASK-0076, nowe gry,
  wielogrowe wydanie, benchmarki pełnego pipeline'u i TASK-0080–0089.
- **Context:** właściciel chce najpierw zamknąć i odebrać szybki preselektor,
  zanim pełny pipeline otrzyma duże zbiory danych. Pozwala to ograniczyć liczbę
  wejściowych zdjęć bez łączenia tej zmiany z treningiem, publikacją i
  hardeningiem urządzeń.
- **Reason:** selektor ma odrębny model kosztu, lifecycle i kryteria jakości.
  Samodzielna bramka zmniejsza zakres regresji i tworzy kontrolowane wejście do
  kosztowniejszych prac 0.5.
- **Alternatives:** utrzymanie całej skali w 0.4 albo przesunięcie także testu
  10k/30k do 0.5. Drugą opcję odrzucono, ponieważ 10k/30k mierzy wyłącznie
  selektor surowych zdjęć, a nie pełny dataset layoutów.
- **Consequences:** TASK-0151–0157 są kompletnym zakresem 0.4. TASK-0143–0150,
  TASK-0076 oraz TASK-0080–0089 zachowują numery i przechodzą do 0.5. Pełny
  import około 500 000 rzeczywistych layoutów na grę oraz nowe gry nie mogą
  rozpocząć się w bramce 0.4.
- **Supersedes:** zastępuje wyłącznie przypisanie pełnej skali do 0.4 w D-115;
  zachowuje zakres mobilny 0.3 oraz architekturę selektora z D-121.

## D-124 — Output selektora skraca ścieżkę Windows bez utraty tożsamości runu

- **Status:** accepted
- **Date:** 2026-08-03
- **Decision:** niezmienny output selektora jest publikowany pod
  `data/exports/image-selections/<manifestSha256>/`, a wybrane JPEG-i pod
  `images/`. Kanoniczny manifest zawiera `runId`, wejściową checksumę i
  fingerprint selektora, dlatego jego SHA-256 nadal jednoznacznie wiąże content
  z runem. Nazwy JPEG używają dodatniego zakresu i 12 znaków checksumy źródła.
- **Context:** zagnieżdżenie `<runId>/<manifestSha256>/selected/` wraz z długą
  nazwą operatorską JPEG niepotrzebnie zbliżało lokalne ścieżki testowe i
  operatorskie do klasycznego limitu Windows. `runId` już należy do
  kanonicznych bajtów manifestu.
- **Reason:** pojedynczy content address zachowuje niezmienność i idempotencję,
  skraca ścieżkę o segment UUID i nadal pozwala zweryfikować właściciela runu
  bez polegania na nazwie katalogu.
- **Alternatives:** pozostawienie obu segmentów, skrócenie samej checksumy
  katalogu albo globalne wymaganie włączenia long paths w Windows.
- **Consequences:** lookup zawsze zaczyna się od ścieżki manifestu zapisanej w
  `image_selection_runs`; handoff sprawdza zarówno SHA-256, jak i `runId`
  wewnątrz manifestu. Folder nie może być interpretowany bez manifestu.
- **Supersedes:** doprecyzowuje wyłącznie planowaną ścieżkę storage w D-121.

## D-125 — Ręczne korekty są append-only, a finalny output pozostaje niezmienny

- **Status:** accepted
- **Date:** 2026-08-03
- **Decision:** każde zatwierdzenie albo poprawka grupy selektora zapisuje nową
  rewizję `image_selection_manual_decisions` z UUID idempotencji. Aktualny wybór
  grupy jest projekcją ostatniej rewizji, a atomowy `manual-decisions.json`
  przechowuje kanoniczny stan roboczy. Pliki ręczne używają krótkiej ścieżki
  `data/working/is-manual/<runPrefix>/<groupPrefix>/<checksumPrefix>.jpg`, ale
  pełne UUID, checksumy i proweniencja pozostają w bazie. Po opublikowaniu
  content-addressed outputu nie można go mutować; następna korekta wymaga nowego
  runu.
- **Context:** modal musi pozwalać poprawić wcześniejszy wybór, a handoff może
  być ponawiany i konsumowany niezależnie. Nadpisanie finalnego manifestu
  złamałoby checksumę, audyt oraz odtwarzalność istniejącego importu.
- **Reason:** append-only historia łączy bezpieczny retry, audyt i edycję przed
  publikacją, zachowując niezmienność kontraktu TASK-0154.
- **Alternatives:** nadpisywanie jednej decyzji bez historii, mutowanie
  opublikowanego manifestu albo tworzenie nowego runu przy każdej korekcie.
- **Consequences:** UI może ponownie otworzyć grupę i dodać korektę do momentu
  publikacji. Po publikacji API zwraca `IMAGE_SELECTION_ALREADY_PUBLISHED`, a
  operator uruchamia nowy run. Krótkiej ścieżki pliku nie wolno używać jako
  identyfikatora domenowego.
- **Supersedes:** doprecyzowuje D-121 i zachowuje niezmienność z D-124.

## D-126 — Checkpoint selektora potwierdza bounded kursor, a fencing chroni projekcje

- **Status:** accepted
- **Date:** 2026-08-03
- **Decision:** produkcyjny `image_selection` używa wspólnego lease i
  `execution_slot = 1`. JSON checkpointu przechowuje wyłącznie kursor, bounded
  stan otwartej grupy, pending guard, top-k oraz liczniki; grupy i kandydaci są
  trwałą projekcją PostgreSQL. Projekcja jest zapisywana przed checkpointem, a
  retry przycina odczyt do `finalizedGroupCount` ostatniego potwierdzonego
  checkpointu i idempotentnie odtwarza najwyżej jego niedomknięty ogon. Każdy
  zapis grupy i finalnego outputu wymaga aktualnego tokenu fencing.
- **Context:** zapis projekcji i checkpointu korzysta z istniejących, odrębnych
  granic transakcji. Awaria pomiędzy nimi może pozostawić projekcję o bounded
  partię przed kursorem, a zapis checkpointu jako pierwszy mógłby pozostawić
  kursor przed brakującą projekcją.
- **Reason:** kolejność projection-first nie pomija danych. Uzgodnienie do
  potwierdzonego prefiksu pozwala bezpiecznie powtórzyć małą partię, zachowując
  prosty lokalny worker bez nowego brokera ani rozproszonej transakcji.
- **Alternatives:** jedna rozproszona transakcja obejmująca runtime i projekcję,
  checkpoint przed projekcją, ponowne skanowanie całego katalogu albo nowa
  kolejka Redis/Celery.
- **Consequences:** crash po checkpointcie wznawia następny plik, a crash przed
  nim powtarza najwyżej 32 pliki. `waiting_for_review` zwalnia slot; cancel jest
  sprawdzany przy checkpointach skanu i publikacji. Diagnostyka pozostaje
  bounded i content-addressed, a czas aktywnych prób nie obejmuje ręcznego
  oczekiwania.
- **Supersedes:** doprecyzowuje wykonanie D-121 i korzysta z globalnego modelu
  lease/fencing opisanego przez D-028–D-030.

## D-127 — Selekcja 10k/30k przechodzi techniczną bramkę skali

- **Status:** accepted
- **Date:** 2026-08-03
- **Decision:** `fast-image-selector-v1` otrzymuje techniczną decyzję `ready` po
  profilach 10 000 i 30 000 na komputerze właściciela. Bramka wymaga nadal
  krótkiego odbioru workspace'u, manualnego fallbacku, outputu i handoffu przez
  właściciela; do tego czasu TASK-0157 i wersja 0.4 pozostają otwarte.
- **Context:** profil 10k zakończył selekcję w 252,51 s przy +76,2 MiB peak RSS,
  a 30k w 792,43 s przy +194,0 MiB. Oba uzyskały zero fałszywych scaleń,
  grouping i auto-selection precision równe 1 oraz nie zmieniły źródłowego
  inventory. Sparse verification wyniosło odpowiednio 375 i 1200, czyli
  dokładnie `grupy × top-k`, a nie N.
- **Reason:** pomiar udowadnia liniowy, bounded tani skan z dużym zapasem wobec
  limitów 15/45 minut i redukcję wejść pełnego pipeline'u odpowiednio
  10 000 → 122 oraz 30 000 → 389.
- **Alternatives:** rozpoczęcie dużych danych bez pomiaru, przeniesienie bramki
  10k/30k do 0.5 albo dodanie Redis/Celery. Odrzucono je, ponieważ lokalny
  pojedynczy worker spełnia obecny budżet.
- **Consequences:** nie ma przesłanki do zmiany kolejki ani architektury.
  TASK-0076 pozostaje zablokowany przez odbiór właściciela oraz osobne bramki
  `massImportAllowed` i rzeczywistych danych wersji 0.5. Benchmark range
  verification używa niezależnych adnotacji bez prywatnego modelu OCR; raport
  nie jest pomiarem jakości OCR ani klasyfikatora symboli.
- **Supersedes:** doprecyzowuje bramkę D-123 bez zmiany zakresu 0.4/0.5.

## D-128 — Pełna siatka numerów potwierdza zakres niezależnie od czerwonych ramek

- **Status:** accepted
- **Date:** 2026-08-03
- **Decision:** `fast-image-selector-v2` grupuje zdjęcia fingerprintem HSV
  stałego obszaru ekranu, a dla top-k potwierdza pełny zakres także z
  przestrzennej siatki jasnych numerów. Fallback wymaga co najmniej sześciu
  zgodnych punktów, pierwszego i ostatniego numeru, wszystkich wierszy i kolumn
  oraz jednoznacznej homografii RANSAC. Udana pełna weryfikacja zastępuje tanią
  ocenę liczby ramek, marginesu i ekspozycji całej obudowy, ale nie zastępuje
  bramek blur, clippingu, glare ani confidence zakresu.
- **Context:** pierwszy rzeczywisty run 180 zdjęć skierował `32/32` grup do
  manual review. Detektor czerwonych ramek zwracał dla tego samego ekranu od 5
  do 9 plansz, przez co zmieniał fingerprint i blokował OCR. Całe zdjęcie
  obejmuje ciemną obudowę automatu, więc jego ekspozycja nie opisuje
  czytelności ekranu.
- **Reason:** numery są bezpośrednim dowodem domenowym zakresu i tworzą stabilną
  siatkę mimo perspektywy. Kontrolny przebieg tych samych danych rozpoznał 7
  zakresów automatycznie, 4 grupy jako powtórzenia i pozostawił 0 wyjątków w
  44,2 s.
- **Alternatives:** obniżenie wszystkich progów jakości, zwiększenie top-k,
  uruchomienie pełnego pipeline'u na każdym zdjęciu albo ręczne zatwierdzenie 32
  grup. Odrzucono je jako mniej bezpieczne albo niewystarczająco skalowalne.
- **Consequences:** zmiana ma nowy fingerprint selektora. To samo niezmienne
  źródło może mieć wiele runów wersjonowanych fingerprintem; migracja 0028
  zachowuje idempotencję gra + manifest wejścia + selector fingerprint i nie
  usuwa historycznego runu v1.
- **Supersedes:** doprecyzowuje D-123 i D-127 dla rzeczywistych zdjęć bez
  odwoływania technicznej bramki skali v1.

## D-129 — Brak ręcznego JPEG-a jest terminalną decyzją zakresu

- **Status:** accepted
- **Date:** 2026-08-03
- **Decision:** ręczne rozwiązanie grupy wymaga dodatniego zakresu, ale nie
  wymaga pliku. Bez JPEG-a system zapisuje append-only decyzję
  `missing_image`, pokazuje `Brak zdjęcia dla layoutów X–Y` i wznawia ten sam
  job po rozwiązaniu ostatniej grupy. JPEG pozostaje opcjonalnym uzupełnieniem.
- **Context:** użytkownik chce kontynuować selekcję mimo braku dobrego zdjęcia;
  ręczne szukanie pliku dla każdego wyjątku nie może blokować przekazania
  poprawnie wybranych reprezentantów.
- **Reason:** jawny stan odróżnia brak pliku od duplikatu, błędu i zatwierdzonego
  obrazu, zachowując audyt i możliwość raportowania luk.
- **Alternatives:** tworzenie pustego kandydata, użycie
  `skipped_existing_range` albo wymuszenie JPEG-a. Odrzucono je jako
  semantycznie błędne lub blokujące workflow.
- **Consequences:** migracja 0029 rozszerza status grupy i ręczne decyzje;
  publisher pomija plik dla `missing_image`, a handoff obejmuje pozostałe
  obrazy. Zakresu nie wolno inferować z sąsiednich grup, ponieważ numeracja może
  skakać.
- **Supersedes:** doprecyzowuje manualny fallback D-123.

## D-130 — Nierozpoznany wyjątek nie blokuje pewnego wyniku selekcji

- **Status:** accepted
- **Date:** 2026-08-03
- **Decision:** główna akcja selekcji pomija wszystkie nierozpoznane grupy jako
  `missing_image`, również bez zakresu, i publikuje pewne reprezentanty.
  Ręczne dodanie JPEG-a oraz zakresu jest opcjonalnym uzupełnieniem. Wynik można
  skopiować browser-native pickerem do folderu użytkownika pod nazwami
  `seq_<start>-<end>.jpg` albo jawnie przekazać do Importu layoutów.
- **Context:** techniczny numer grupy `#13` nie mówi użytkownikowi, których
  layoutów brakuje, a wymuszanie ręcznie wpisanego zakresu blokowało poprawne
  zdjęcia mimo istnienia osobnego procesu uzupełniania danych w Import layouts.
- **Reason:** system nie może wymyślać numerów przy dozwolonych skokach
  sekwencji. Pusty zakres zachowuje prawdę domenową i audyt, a jednocześnie nie
  zatrzymuje wartościowego, częściowego wyniku.
- **Consequences:** migracja 0030 dopuszcza `null` w zakresie decyzji
  `missing_image`; publisher pomija taki zestaw. Eksport jest checksumowany,
  backend nie otrzymuje dowolnej ścieżki z komputera, a folder docelowy wybiera
  bezpośrednio użytkownik w przeglądarce.
- **Supersedes:** zmienia obowiązek zakresu z D-129; pozostała semantyka
  terminalnego `missing_image` pozostaje aktualna.

## D-131 — Pojedynczy run selekcji przyjmuje do 100 000 JPEG-ów

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** limit liczby zdjęć `photo_selection` wynosi 100 000 na run po
  stronie Admina i API. Panel pokazuje jawny loader przed przygotowaniem listy i
  zwykły postęp po rozpoczęciu uploadu. Limit bajtów, rezerwa wolnego miejsca,
  bounded concurrency równe 4 i streaming workera pozostają bez zmian.
- **Context:** rzeczywisty katalog 32 000 zdjęć został odrzucony przez dawny
  limit 30 000 po lokalnym odczycie całej listy, co wyglądało jak brak reakcji.
- **Reason:** 32 000 jest poprawnym wejściem biznesowym, a domena i storage nie
  wymagają podziału sekwencyjnego katalogu. Loader usuwa niejednoznaczność między
  przygotowaniem listy a brakiem działania.
- **Alternatives:** dzielenie folderu na wiele runów albo pełny automatyczny
  benchmark 100k przed zmianą. Pierwsze komplikuje ciągłość i output, a drugie
  właściciel jawnie odłożył na rzecz rzeczywistego testu.
- **Consequences:** zaliczona bramka jakości i wydajności 0.4 nadal dotyczy
  profili 10k/30k. Limit 100k jest dozwolonym wejściem, ale pierwszy taki run ma
  być obserwowany operacyjnie; nie wolno przedstawiać go jako wcześniej
  zaliczonego benchmarku.
- **Supersedes:** rozszerza limit wejścia D-123 bez zmiany algorytmu selektora.

## D-132 — Rzeczywiste dane 500 000 layoutów są zasilane etapami

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** przed pierwszym rzeczywistym zasileniem lokalny PostgreSQL jest
  resetowany do pustego aktualnego schematu. Pierwsza partia około 32 000 zdjęć,
  odpowiadająca w przybliżeniu pierwszym 5 000 layoutów, przechodzi przez
  Selekcję zdjęć. Kolejne z 28 katalogów są dodawane etapami, a docelowy wynik
  wynosi 500 000 layoutów.
- **Context:** dane demonstracyjne i wcześniejsze runy utrudniałyby odróżnienie
  nowych wyników, jobów, wyjątków i pomiarów czasu od historii rozwojowej.
- **Reason:** pusty stan zapewnia audytowalną numerację, jednoznaczne statystyki
  i możliwość zatrzymania procesu po każdej partii bez mieszania źródeł.
- **Consequences:** chronione APK i snapshot 0.1, klucz podpisu oraz zdjęcia
  źródłowe nie są usuwane. Pełna publikacja datasetu nadal wymaga kontroli
  pierwszych partii i jawnego otwarcia bramki `massImportAllowed`; rozpoczęcie
  selekcji zdjęć nie omija tej bramki.
- **Alternatives:** dopisywanie nowych zdjęć do istniejących danych odrzucono,
  ponieważ zafałszowałoby statystyki oraz mogłoby połączyć nowe joby ze starymi
  grami i runami.

## D-133 — Browser staging używa liniowego dziennika zamiast pełnego checkpointu per plik

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** stałe metadane uploadu są przechowywane w compact state schema
  v2, a metadane każdego ukończonego JPEG-a są dopisywane raz do kanonicznego
  JSONL. Odpowiedź pojedynczego PUT nie zawiera pełnej listy wcześniejszych
  indeksów; pełne inventory służy wyłącznie wznowieniu przez begin/get.
- **Context:** rzeczywisty upload 32 079 plików ukończył się w 2346,44 s i
  zwalniał wraz z postępem. Przyczyną było wielokrotne sortowanie, zapisywanie i
  przesyłanie rosnącego inventory, czyli koszt zbliżony do `O(n²)`.
- **Reason:** append-only daje koszt `O(n)` oraz zachowuje możliwość wznowienia.
  Awaria może co najwyżej pozostawić niepełny ostatni rekord, który jest
  pomijany i ponownie wysyłany; właściwy selektor zachowuje częste checkpointy,
  lease i fencing bez zmian.
- **Alternatives:** zwiększenie concurrency, rzadkie pełne checkpointy albo brak
  trwałości uploadu. Pierwsze nie usuwało przyczyny, drugie nadal kopiowałoby
  całe inventory, a trzecie niepotrzebnie usuwałoby istniejące wznowienie.
- **Consequences:** historyczny schema v1 jest jednokrotnie migrowany do
  dziennika. Kolejny rzeczywisty duży folder stanowi pomiar poprawy; nie jest
  wymagany osobny długi benchmark 100 000 przed kontynuacją pracy.

## D-134 — Temporalna ciągłość grup jest wersjonowana jako selector v3

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** nowe runy używają `fast-image-selector-v3`, który porównuje
  fingerprint zarówno z bounded reprezentantami jakościowymi, jak i ostatnią
  kolejną obserwacją bieżącej grupy. Pusta lub nieporównywalna sygnatura lattice
  oznacza brak dowodu geometrycznego, a nie maksymalną zmianę. Manifest v2
  pozostaje dostępny w rejestrze po niezmiennym fingerprintcie.
- **Context:** rzeczywisty run 32 079 zdjęć przy 13 408 wejściach miał 1166 grup
  i 3461 weryfikacji. Średnia 11,5 zdjęcia na grupę była wielokrotnie niższa od
  typowych 50–100, mimo zera błędów i stabilnej pamięci. Zmiana kąta lub światła
  oddalała klatkę od najlepszego historycznego reprezentanta i tworzyła
  fałszywe granice.
- **Reason:** sąsiednie zdjęcia tego samego ekranu zwykle zmieniają się stopniowo.
  Bounded kotwica czasowa zachowuje tę ciągłość bez stałej długości grupy i bez
  zwiększania kosztu OCR per plik. Wersjonowanie jest konieczne, ponieważ zmiana
  state machine pod istniejącym fingerprintem złamałaby deterministyczny retry.
- **Alternatives:** podniesienie globalnego progu fingerprintu grozi fałszywym
  scaleniem różnych stron, a restart i przeliczenie działającego runu utraciłyby
  wartościowy checkpoint. Równoległy pełny rerun odrzucono na czas bieżącego
  joba, aby nie konkurować o CPU i dysk.
- **Consequences:** checkpoint v3 przechowuje jedną dodatkową bounded obserwację.
  Worker rozwiązuje manifest po fingerprintcie runu, więc po restarcie może
  wznowić v2 dokładnie jego algorytmem. Rzeczywisty pomiar poprawy v3 wymaga
  nowego runu na tym samym niezmiennym stagingu po zakończeniu v2.

## D-135 — Niepełna geometria obrazu jest izolowanym wynikiem per plik

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** odzyskiwanie siatki nie liczy statystyk dla pustego przypisania
  wiersza lub kolumny. Niepełna geometria zwraca brak wyniku, a granice adapterów
  selekcji mapują `StatisticsError` na błąd konkretnego pliku zamiast zatrzymywać
  cały job.
- **Context:** rzeczywisty run v2 32 079 zdjęć zakończył się przy checkpointcie
  14 144 po próbie policzenia mediany pustej grupy. Wszystkie wcześniejsze
  checkpointy, staging i fingerprint runu pozostały poprawne.
- **Reason:** pojedyncze zasłonięte lub nietypowe zdjęcie jest oczekiwanym
  wejściem domenowym. Nie może unieważniać wielu godzin poprawnej pracy nad
  pozostałymi plikami.
- **Consequences:** ten sam job można deterministycznie wznowić od checkpointu;
  wadliwe zdjęcie zwiększa licznik błędów lub przechodzi ścieżką braku geometrii,
  ale nie kończy całej sesji.

## D-136 — Statystyki image importu są przyrostowe pomiędzy pełnymi snapshotami

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** `ImageBatchHandler` pobiera pełne statystyki joba raz na wejściu
  i raz na końcowej granicy wykonania. Pomiędzy nimi aktualizuje liczniki z
  poprzedniego oraz zapisanego statusu pliku. Świeży `waiting_for_review`
  przechodzi pierwszą kontrolę bez rehydratacji; tylko stan istniejący przed
  bieżącym wykonaniem odbudowuje projekcję.
- **Context:** wcześniejszy handler wykonywał agregację wszystkich asocjacji po
  każdym z ośmiu etapów każdego pliku. Dla `n` zarejestrowanych zdjęć dawało to
  koszt zbliżony do `O(n²)` oraz ponowną projekcję świeżych wyników review.
- **Reason:** file checkpoint jest już trwałym i fenced źródłem przejścia.
  Liczniki można wyprowadzić z różnicy dwóch statusów bez odczytu całej tabeli,
  nie zmieniając wyników adapterów ani odporności na restart.
- **Alternatives:** rzadsza pełna agregacja nadal rośnie wraz z liczbą plików;
  utrzymywanie osobnej tabeli liczników zwiększa model danych bez potrzeby.
- **Consequences:** liczba pełnych agregacji na wykonanie jest stała. Końcowy
  snapshot wykrywa ewentualny drift, checkpoint per etap, retry, fencing i
  anulowanie pozostają bez zmian. Fingerprint pipeline'u nie zmienia się,
  ponieważ bajty wyników adapterów są identyczne.

## D-137 — Zbiorcze pominięcie nie utrwala sugerowanych zakresów selekcji

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** `Kontynuuj z wybranymi zdjęciami` zapisuje każdą nierozpoznaną
  grupę jako `missing_image` bez zakresu. Frontend może zasugerować zakres tylko
  jednej nierozwiązanej grupie pomiędzy dwoma znanymi zakresami. Modal pokazuje
  numer zestawu i bounded listę nazw kandydatów, ale wyraźnie oddziela je od
  numerów layoutów.
- **Context:** w rzeczywistym runie 32 079 źródeł kilka sąsiednich grup dostało
  ten sam zakres wyprowadzony ze starego snapshotu. Pierwszy zapis przeszedł,
  kolejny poprawnie zatrzymała unikalność domenowa. Użytkownik nie potrafił też
  odróżnić 2288 nierozpoznanych zestawów od liczby brakujących zdjęć.
- **Reason:** brak rozpoznanego zakresu jest prawdziwą informacją domenową.
  Zgadywana numeracja nie może blokować publikacji pewnych reprezentantów ani
  udawać, że numer zestawu jest numerem layoutu.
- **Consequences:** walidacja unikalności zakresów pozostaje bez zmian. Bieżący
  run można bezpiecznie kontynuować, a ręczne wyszukanie źródła korzysta z
  małego endpointu kandydatów zamiast z pełnej kolejki.

## D-138 — Selector v4 wybiera najlepszy dostępny obraz i odzyskuje jedną bounded lukę

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** nowe runy używają `fast-image-selector-v4`. Błędy dekodowania,
  skanu, jawne `IMAGE_OCCLUDED` i minimalna ostrość pozostają twardymi blokadami,
  natomiast progi
  ekspozycji, refleksów, perspektywy, marginesu i ogólnego quality score są
  sygnałami rankingowymi. Gdy rozpoznana grupa ma wyłącznie słabe kandydaty, v4
  wybiera najlepszy dostatecznie ostry obraz i dodaje
  `QUALITY_BEST_AVAILABLE`. Po finalizacji grup może też przypisać zakres tylko
  jednej nierozpoznanej grupie pomiędzy dwoma wybranymi zakresami, jeżeli luka
  jest dodatnia i obejmuje najwyżej dziewięć layoutów; wynik otrzymuje
  `RANGE_INFERRED_FROM_BOUNDED_GAP`.
- **Context:** rzeczywisty run odrzucił między innymi czytelne zdjęcia zakresu
  `73–81`. Sąsiednie zakresy `64–72` i `82–90` były pewne, lecz kandydaci luki
  mieli słabe metryki ekspozycji/marginesu i brak wyniku OCR. Zmuszało to
  użytkownika do ręcznego uzupełniania mimo wystarczającego dowodu wizualnego i
  domenowego.
- **Reason:** celem modułu jest szybki wybór jednego najlepszego dostępnego
  zdjęcia, a nie odrzucenie całej serii dlatego, że wszystkie ujęcia są słabsze
  od idealnego progu. Dwie kotwice ograniczają pojedynczą lukę jednoznacznie,
  bez wprowadzania ogólnego założenia ciągłości numeracji.
- **Alternatives:** globalne obniżenie progów usunęłoby informację o jakości;
  zwiększenie `topK` lub liczby wywołań OCR podniosłoby koszt dużego runu;
  przypisywanie zakresu wielu grupom w jednej luce byłoby niejednoznaczne.
- **Consequences:** v4 wykonuje ten sam bounded skan i najwyżej `topK = 3`
  weryfikacje na grupę, a dodatkowy post-pass ma koszt O(g) i nie uruchamia OCR.
  Ręczne decyzje i `missing_image` nie są nadpisywane. Manifesty v2/v3 pozostają
  rozwiązywalne po swoich fingerprintach, więc trwające runy wznawiają dokładnie
  wcześniejszy algorytm. Realny rerun v4 pozostaje bramką TASK-0157.
- **Supersedes:** doprecyzowuje quality gate z D-123 oraz zachowuje temporalne
  grupowanie D-134.

## D-139 — Tani skan selekcji używa bounded ordered parallel prefetch

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** `worker-v7` zleca odczyt JPEG, miniaturę, lattice/fingerprint i
  metryki jakości maksymalnie czterem wątkom, utrzymując najwyżej osiem futures.
  Wyniki są konsumowane wyłącznie w naturalnym `order_index`. Grupowanie,
  top-k verification, OCR, checkpointy i publikacja pozostają sekwencyjne.
- **Context:** rzeczywisty run 32 079 zdjęć przetwarzał około 5,1 zdjęcia/s,
  używał praktycznie jednego z ośmiu logicznych procesorów i miał stabilne
  430–450 MiB working set. Upload oraz liczba checkpointów nie były bieżącym
  wąskim gardłem.
- **Reason:** tani analyzer produkcyjny jest bezstanowy, a drogie operacje
  Pillow/OpenCV wykonują większość pracy poza Pythonem. Ordered consumption
  zachowuje identyczny strumień domenowy przy wykorzystaniu wolnych rdzeni.
- **Alternatives:** uruchomienie kilku jobów odrzucono przez globalny
  `execution_slot = 1`; równoległy PaddleOCR jest ryzykowny dla modelu i pamięci;
  samo rzadsze checkpointowanie ma mały potencjał według pomiaru.
- **Consequences:** strategia wykonania nie zmienia manifestu ani fingerprintów
  v2/v3/v4. Po crashu najwyżej osiem niezapisanych obserwacji może zostać
  policzonych ponownie, ale checkpoint nie pomija plików. Tryb jednowątkowy
  pozostaje dostępny w konstruktorze. Realne przyspieszenie wymaga pomiaru
  następnego runu po restarcie workera.
- **Supersedes:** nie zmienia D-134 ani D-138; doprecyzowuje lokalny model
  wykonania z D-123.

## D-140 — Selector v5 rozdziela ciągłość kamery od zmiany strony

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** nowe runy będą używać `fast-image-selector-v5`. Granica strony
  jest oceniana względem bezpośrednio poprzedniej obserwacji i nadal wymaga
  bounded potwierdzenia kolejnej zgodnej klatki. Historyczne top-k służy do
  wyboru reprezentanta, ale nie może zablokować granicy dlatego, że nowa strona
  przypomina jeden ze starszych layoutów. Pełna weryfikacja v5 używa guarded
  grid recovery oraz digit-aware fallbacku widocznych numerów; tani skan i
  kolejność źródeł pozostają bez zmian.
- **Context:** rzeczywisty run v4 32 079 zdjęć utworzył 743 grupy, z których 703
  wymagały review. 700 miało niepełną geometrię, 692 brak siatki numerów, 71
  grup przekroczyło 100 źródeł, a największa miała 462. Czytelny zakres
  `271–279` był odrzucony przez stałe ROI, limit szerokości etykiety i wyłączone
  odzyskanie siatki. Pierwsza grupa zawierała jednocześnie rozpoznane zakresy
  `10–18` i `19–27`, co potwierdza fałszywe scalenie.
- **Reason:** zdjęcia w katalogu są uporządkowane, a kolejne klatki tego samego
  widoku zmieniają perspektywę płynnie. Bezpośrednia kotwica czasowa rozróżnia
  taki dryf od skoku do następnej strony. OCR zakresu musi obsługiwać rosnącą
  liczbę cyfr i położenie dolnego rzędu, zamiast zakładać geometrię pierwszego
  małego corpus.
- **Alternatives:** samo obniżenie progów jakości odrzucono, ponieważ 700 grup
  nie miało zakresu, a jakość nie była blokadą. Zwiększenie top-k bez naprawy
  granic podniosłoby koszt OCR i nadal weryfikowałoby połączone strony.
- **Consequences:** v5 zmienia selector fingerprint. Manifesty v2–v4 pozostają
  w rejestrze i wznawiają się ze swoim zachowaniem. Przed pełnym rerunem 32 079
  plików obowiązuje regresja na rzeczywistych przypadkach odrzuconych przez v4.
- **Supersedes:** koryguje regułę granicy z D-134; zachowuje ranking i bounded
  inference z D-138 oraz model wykonania z D-139.

## D-141 — Nowy selektor ponownie wykorzystuje niezmienny staging

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** historyczny run może utworzyć run aktualnego selektora bez
  ponownego uploadu. Backend wyprowadza `sourceSelectionId`, grę i checksum
  wyłącznie z trwałego runu, sprawdza kontrolowany manifest na dysku i tworzy
  idempotentny run dla aktualnego fingerprintu. UI nie przesyła ścieżki ani
  deklarowanego checksumu.
- **Context:** staging 32 079 zdjęć zajmuje około 7,55 GB, jest niezmieniony i ma
  poprawny manifest. Ponowny upload nie wnosi informacji, trwa długo i zwiększa
  ryzyko przerwania pracy tylko dlatego, że wdrożono selektor v5.
- **Reason:** obrazy wejściowe są niezmiennym, checksumowanym źródłem, natomiast
  wersja selektora jest osobną osią tożsamości runu.
- **Alternatives:** ponowny upload odrzucono jako kosztowny i zbędny. Mutowanie
  historycznego runu odrzucono, ponieważ zniszczyłoby audyt i porównanie v4/v5.
- **Consequences:** Admin pokazuje akcję `Przelicz ponownie załadowane zdjęcia`.
  Zmieniony lub usunięty staging jest blokowany przed utworzeniem joba, a
  powtórne kliknięcie dla tego samego fingerprintu przywraca istniejący run.
- **Supersedes:** doprecyzowuje idempotencję selektora opisaną w D-123 i nie
  zmienia wersjonowania z D-140.

## D-142 — Selector v6 odzyskuje dokładne wielogrupowe luki

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** nowe runy używają `fast-image-selector-v6`. Kilka kolejnych
  grup bez numerów pomiędzy pewnymi zakresami jest odzyskiwane automatycznie,
  jeśli całą lukę można podzielić dokładnie na pełne strony po dziewięć
  layoutów. Odzyskanie jest utrwalane po pojawieniu się prawej kotwicy.
- **Context:** przy 519 grupach realnego runu v5 istniały 54 grupy bez zakresu.
  Aż 50 z nich należało do dokładnych luk; poprzedni fallback obsługiwał tylko
  pojedynczą grupę i pozostawiał wieloelementowe bloki do review.
- **Reason:** dwie pewne kotwice i dokładny rozmiar całej luki dają jednoznaczny
  podział bez zgadywania kolejnego zakresu. Rozwiązanie usuwa większość
  fałszywie manualnych przypadków bez dodatkowego OCR i bez wpływu na koszt
  skanu.
- **Alternatives:** przypisywanie numerów wyłącznie na podstawie kolejności
  odrzucono, ponieważ źródła mogą zawierać skok, np. `19–27 → 400–408`.
  Ukrycie licznika odrzucono, ponieważ nie naprawia danych.
- **Consequences:** v6 ma nowy fingerprint. V5 pozostaje w rejestrze i zachowuje
  niezmienne zachowanie przy wznowieniu. Niepasujące luki nadal są jawne; 100%
  nie jest deklarowane kosztem fałszywych numerów.
- **Supersedes:** rozszerza bounded inference z D-138 i zachowuje reguły granic
  oraz OCR z D-140.

## D-143 — Selector v7 wybiera obraz na podstawie czytelnego zakresu

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** nowe runy używają `fast-image-selector-v7`. Jednoznaczna siatka
  numerów albo dokładna bounded luka wystarcza do wybrania najlepszego
  dekodowalnego zdjęcia. Zasłonięcie, rozmycie i słaba jakość plansz wpływają na
  ranking i audyt, lecz nie blokują reprezentanta. Twardą blokadą pozostaje
  niedekodowalny plik, błąd skanu lub konflikt zakresu.
- **Context:** rzeczywiste zdjęcie z layoutami `73–81` miało czytelne wszystkie
  numery i użyteczne plansze, lecz starsza maska odrzucała ciepło zabarwione
  etykiety, a polityka jakości blokowała częściowe zasłonięcie. Ręczne dodanie
  tego samego JPEG-a nie docierało do API przez brak `X-Image-File-Name` w CORS.
- **Reason:** celem modułu jest redukcja wielkiego folderu do najlepszego
  dostępnego materiału. Niedoskonały obraz nadal pozwala wyciąć widoczne
  layouty, a resztę uzupełnić później ręcznie; utrata całej strony jest gorsza
  niż jawne ostrzeżenie jakości.
- **Alternatives:** dalsze podnoszenie progów jakości oraz obowiązkowy manualny
  wybór odrzucono, bo powtarzały ten sam problem i zwiększały pracę użytkownika.
- **Consequences:** adapter `visible-sequence-label-range-v3` rozszerza maskę
  etykiet i pozostawia walidację przestrzenną RANSAC. V2–v6 zachowują historyczne
  fingerprinty. Ręczny upload ma trwały test preflight CORS.
- **Supersedes:** D-138 w zakresie twardej blokady zasłonięcia i minimalnej
  ostrości; zachowuje reguły jednoznaczności D-140 oraz D-142.

## D-144 — Selector v8 kończy OCR na pierwszym użytecznym zdjęciu grupy

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** nowe runy używają `fast-image-selector-v8`. Dla każdej grupy
  selektor zachowuje pierwszą dostatecznie czytelną obserwację i bounded
  fallbacki, weryfikuje je w kolejności źródłowej oraz kończy pełny OCR po
  pierwszym jednoznacznym zakresie. Kolejny kandydat jest sprawdzany wyłącznie,
  gdy poprzedni nie daje zakresu lub kończy się twardym błędem.
- **Context:** v7 wykonywał do trzech pełnych weryfikacji dla każdej grupy, aby
  wybrać najwyżej oceniony obraz. Przy dużym katalogu użytkownik zaobserwował
  wyraźne spowolnienie, mimo że pierwsze zdjęcie serii często było wystarczająco
  czytelne.
- **Reason:** celem Selekcji zdjęć jest szybkie ograniczenie duplikatów przed
  właściwym pipeline'em, nie poszukiwanie marginalnie najlepszego kadru kosztem
  wielokrotnego OCR. Typowy koszt pełnej weryfikacji spada z `g × topK` do
  `g × 1`, przy zachowaniu bounded fallbacku.
- **Alternatives:** pełny ranking wszystkich top-k odrzucono jako zbyt wolny.
  Pomijanie zdjęć skokami odrzucono, ponieważ mogłoby przeoczyć krótką serię.
- **Consequences:** v8 ma nowy fingerprint i wersjonowaną politykę minimalnej
  czytelności. V7 pozostaje niezmienny dla wznowień. Tani skan nadal przechodzi
  po wszystkich źródłach w naturalnej kolejności, więc granice grup pozostają
  deterministyczne.
- **Supersedes:** D-143 wyłącznie w zakresie wyboru najwyżej ocenionego zdjęcia;
  zachowuje jego reguły jednoznaczności i twardych błędów.

## D-145 — Selector v9 wybiera wizualne grupy bez OCR i geometrii

- **Status:** accepted
- **Date:** 2026-08-04
- **Decision:** nowe runy po przejściu TASK-0165–0171 będą używać
  `fast-image-selector-v9`. Selekcja dekoduje zmniejszony JPEG, buduje lekki
  deskryptor wyglądu, wykrywa potwierdzone zmiany kolejnych ekranów i wybiera
  pierwszego dostatecznie czytelnego albo najlepszego dekodowalnego kandydata.
  Nie uruchamia OCR, `PageBoardDetector`, homografii ani cropów i nie ustala
  `sequence_number`. Zakres, dokładna geometria i deduplikacja po numerach należą
  do `Importu layoutów`.
- **Context:** v8 ograniczył typowy OCR z trzech do jednego kandydata na grupę,
  ale realny scan nadal dekodował każdy JPEG w pełnej rozdzielczości, wykonywał
  geometrię dla każdego obrazu i uruchamiał kosztowny fallback na fałszywych
  granicach. Użytkownik zaobserwował proces przekraczający godzinę, podczas gdy
  upload 32 079 zdjęć po wcześniejszej korekcie pozostaje stabilny około 20
  minut i nie jest bieżącym problemem.
- **Reason:** celem bounded contextu jest szybka redukcja kolejnych podobnych
  ujęć, nie rozpoznawanie danych domenowych. Przeniesienie dokładności do
  istniejącego ciężkiego pipeline'u usuwa koszt ze wszystkich duplikatów oraz
  pozwala Importowi stosować OCR i geometrię tylko na wybranych zdjęciach.
- **Alternatives:** dalsze rozszerzanie masek OCR lub zmiana PaddleOCR została
  odrzucona jako optymalizacja niewłaściwego etapu. Nowa biblioteka CV, YOLO,
  GPU i mikroserwis zostały odłożone, ponieważ obecne Pillow/libjpeg-turbo i
  OpenCV wystarczą do reduced decode oraz lekkich deskryptorów. Pomijanie plików
  stałym skokiem pozostaje odłożone do czasu zaliczenia bezpiecznej wersji
  liniowej.
- **Consequences:** output v9 jest range-free i używa nazw
  `selection_<groupOrder>.jpg`; `groupOrder` nie jest numerem layoutu.
  Historyczne runy v2–v8 oraz `seq_<start>-<end>.jpg` pozostają odtwarzalne.
  Niepewny późniejszy duplikat może wejść do Importu, ponieważ dodatkowa praca
  jest bezpieczniejsza niż utrata unikalnego ekranu. Upload schema v2 nie jest
  zmieniany. Aktywacja v9 wymaga co najmniej 20 zdjęć/s w krótkim realnym
  profilu, zero false merge i pełnego runu 32 079 zdjęć w najwyżej 45 minut.
- **Supersedes:** D-144 dla nowych runów po aktywacji v9. D-139 pozostaje
  historycznym modelem wykonania v2–v8, a D-141 nadal pozwala ponownie używać
  niezmiennego stagingu.

## D-146 — Właściciel ocenia czas selekcji na próbie 40 000 zdjęć

- **Status:** accepted
- **Date:** 2026-08-05
- **Decision:** końcowa bramka wydajności v9 użyje dokładnie 40 000 naturalnie
  uporządkowanych zdjęć. Nie ma z góry ustalonego maksymalnego czasu. Raport
  zapisze całkowity czas, throughput, peak RSS i jakość grupowania, a właściciel
  jawnie wybierze `accepted` albo `optimize`.
- **Context:** historyczny proces po około 50 minutach pozostawał mniej więcej w
  połowie i łącznie zbliżył się do dwóch godzin. Sztywny limit 45 minut nie
  wynika z biznesowej potrzeby; ważne jest przedstawienie rzeczywistego wyniku
  po architektonicznym usunięciu OCR i geometrii z selekcji.
- **Reason:** akceptowalność czasu zależy od faktycznej redukcji danych oraz
  sposobu pracy właściciela. Pomiar musi być wiarygodny, lecz automatyczny próg
  nie powinien zastępować decyzji użytkownika.
- **Alternatives:** pozostawienie limitu 45 minut odrzucono jako arbitralne.
  Rezygnację z pomiaru odrzucono, ponieważ bez pełnego czasu nie da się ocenić
  regresji ani kosztu 40 000 zdjęć.
- **Consequences:** krótkie profile 500–1000 i 3000 nadal chronią przed
  uruchomieniem oczywiście wadliwego pełnego joba. TASK-0171 nie oznacza `ready`
  bez jawnej oceny właściciela. Działający upload pozostaje poza zakresem.
- **Supersedes:** zastępuje wyłącznie sztywny limit czasu z D-145; pozostałe
  bramki jakości i rozdzielenie odpowiedzialności v9 pozostają bez zmian.

## D-147 — Reduced JPEG decode zachowuje roboczy bok 960 px

- **Status:** accepted
- **Date:** 2026-08-05
- **Decision:** nowe runy używają wersjonowanego adaptera
  `pillow-jpeg-draft-thumbnail-v2`. Adapter wywołuje decoder-side `draft()` przed
  `load()`, zachowuje wymiary źródła oraz EXIF i dopiero potem tworzy
  deterministyczne RGB. Roboczy dłuższy bok pozostaje równy 960 px. OpenCV ma
  jeden wątek wewnętrzny, a ostateczna liczba zewnętrznych scan workers zostanie
  wybrana z pomiaru 1/2/4 w TASK-0171.
- **Context:** warianty 384 i 480 px zmniejszały koszt, lecz oba naruszyły
  przypięty realny golden granic: 384 utracił wykrytą planszę, a 480 zmienił
  oczekiwaną liczbę plansz 8 na 9. Pełny decode do rozdzielczości telefonu przed
  skalowaniem do 960 px nadal był zbędnym kosztem.
- **Reason:** decoder-side redukcja usuwa największą nadmiarową pracę bez
  pogarszania istniejącej geometrii. Jeden wewnętrzny wątek OpenCV zapobiega
  zagnieżdżonej nadsubskrypcji przy bounded zewnętrznym poolu.
- **Alternatives:** aktywację 384 albo 480 odrzucono z powodu regresji goldena.
  Zmianę biblioteki odłożono, ponieważ Pillow/libjpeg udostępnia wymagany reduced
  decode. Pełne porównanie 1/2/4 podczas aktywnego historycznego joba odłożono
  zgodnie z decyzją właściciela do wspólnej bramki TASK-0171.
- **Consequences:** nowy fingerprint manifestu wynosi `284eb7f842b6…`.
  Historyczny v8 o fingerprintcie `9dc754cca7e…` jawnie zachowuje adapter
  `pillow-exif-thumbnail-v1`, więc checkpoint i retry są nadal odtwarzalne.
  Zmiana nie dotyka uploadu ani staging schema v2.

## D-148 — V9 grupuje wyłącznie po bounded deskryptorze wyglądu

- **Status:** accepted
- **Date:** 2026-08-05
- **Decision:** `fast-image-selector-v9` używa stałego wektora 97 wartości:
  niskoczęstotliwościowego pHash 8×8, osobnych histogramów H/S/V oraz siatki
  gęstości i orientacji krawędzi. Granica wymaga zmiany względem bezpośredniego
  poprzednika i rolling centroidu grupy oraz dwóch zgodnych kolejnych
  obserwacji. Centroid, licznik, top-k i pending guard są częścią bounded
  checkpointu. V9 nie konstruuje `PageBoardDetector` ani modelu OCR.
- **Context:** historyczne v2–v8 używały geometrii plansz i fingerprintu obszaru
  ekranu. Zmiana kąta powodowała fragmentację, a dokładne adaptery wykonywały
  koszt niewspółmierny do celu preselektora.
- **Reason:** połączenie pHash, koloru i szerokich regionów krawędzi zachowuje
  zmianę zawartości ekranu, ale rolling centroid oraz bezpośredni poprzednik
  tolerują płynny ruch kamery. Dwuklatkowy guard izoluje refleks, zasłonięcie i
  pojedynczą klatkę przejściową.
- **Alternatives:** sam hash kolorów odrzucono jako zbyt ubogi, pełną geometrię
  i OCR jako zbyt kosztowne, a nieograniczoną historię deskryptorów jako
  sprzeczną z bounded pamięcią. Przewidywanie zakresu lub długości serii nadal
  należy do późniejszego Importu layoutów.
- **Consequences:** pierwszy przedaktywacyjny manifest v9 miał fingerprint
  `711ce8cddc86…`; D-149 zastępuje go po dodaniu polityki reprezentanta.
  Domyślny manifest pozostaje v8 do końcowej aktywacji w TASK-0171. Prywatny golden
  kolejnych ekranów `1–9`, `10–18`, `19–27` nie ma false merge; mała zmiana
  perspektywy tego samego realnego zdjęcia pozostaje poniżej progu granicy.
  TASK-0168 przejmie wybór reprezentanta bez pełnej weryfikacji.

## D-149 — V9 wybiera pierwszego użytecznego reprezentanta bez OCR

- **Status:** accepted
- **Date:** 2026-08-05
- **Decision:** otwarta grupa v9 zachowuje pierwszą dekodowalną obserwację
  spełniającą wersjonowane progi jakości oraz najwyżej jeden najlepszy
  dekodowalny fallback. Po zamknięciu grupy pierwszy użyteczny obraz zostaje
  `auto_selected` bez wywołania verifiera. Jeżeli żaden obraz nie przechodzi
  progów, najlepszy fallback zostaje wybrany z `QUALITY_BEST_AVAILABLE`.
- **Context:** celem selekcji jest redukcja liczby wejść do ciężkiego Importu,
  a nie ostateczna ocena plansz. Odrzucanie całej strony z powodu miękkich
  metryk powodowało niepotrzebne manual review i ryzyko utraty unikalnego
  ekranu.
- **Reason:** pierwsze wystarczające zdjęcie minimalizuje pracę i zachowuje
  kolejność, natomiast pojedynczy fallback chroni słabe serie bez wzrostu
  checkpointu. Dokładne OCR, geometria i deduplikacja należą do Importu.
- **Alternatives:** poszukiwanie absolutnie najlepszego kadru odrzucono jako
  zbędne, a obowiązkowy manual review słabych grup jako sprzeczny z szybkim
  preselektorem. Pominięcie całej grupy jest dozwolone tylko wtedy, gdy nie ma
  żadnego dekodowalnego pliku.
- **Consequences:** polityka progów jest częścią kanonicznego manifestu, top-k v9
  wynosi dwa, a nowy przedaktywacyjny fingerprint to `65c19a84a959…`.
  Historyczne v2–v8 pozostają niezmienne; v9 nadal nie jest domyślny przed
  TASK-0171.
- **Supersedes:** zastępuje wyłącznie przedaktywacyjny fingerprint v9 zapisany
  w D-148; decyzja o appearance-only grouping pozostaje bez zmian.

## D-150 — Cache lekkiego skanu jest odtwarzalnym artefaktem plikowym

- **Status:** accepted
- **Date:** 2026-08-05
- **Decision:** lekka obserwacja JPEG-a jest cache'owana jako bounded kanoniczny
  JSON pod kontrolowanym `data/cache/image-selection-scan/`. Klucz logiczny
  łączy checksumę źródła z osobnym fingerprintem adapterów i parametrów skanu.
  Checkpoint i projekcja grup pozostają jedynym źródłem prawdy postępu, a
  publikator zawsze ponownie sprawdza pełną checksumę wybranego pliku.
- **Context:** crash przed bounded checkpointem i zgodny rerun stagingu mogły
  powtarzać koszt reduced decode oraz deskryptora dla niezmienionych JPEG-ów.
- **Reason:** cache usuwa powtarzaną pracę bez utrwalania obrazów, bez zmiany
  kolejności i bez wiązania lifecycle selektora z bazą danych. Osobny fingerprint
  pozwala ponownie użyć obserwacji po zmianie wyłącznie progów grupowania.
- **Alternatives:** PostgreSQL BLOB, Redis i cache sieciowy odrzucono jako
  niepotrzebną złożoność. Włączenie pełnego selector fingerprintu odrzucono,
  ponieważ unieważniałoby poprawne obserwacje po samej zmianie decyzji domenowej.
- **Consequences:** wpis uszkodzony daje miss i jest atomowo odbudowywany; błąd
  zapisu nie kończy joba. Bezpieczny cleanup usuwa tylko osobny katalog cache
  przy zatrzymanym workerze. Rozmiar rośnie liniowo względem unikalnych par
  checksumy i adaptera, a diagnostyka mierzy hity, missy oraz baseline czasu.

## D-151 — V9 używa ciągłej sygnatury DCT i pozostaje nieaktywny do pełnej bramki

- **Status:** accepted
- **Date:** 2026-08-05
- **Decision:** przedaktywacyjny `fast-image-selector-v9` zastępuje binarny
  pHash ciągłą, znormalizowaną sygnaturą DCT 12×12 obliczaną z centralnego
  obszaru plansz. Składnik DCT jest porównywany wycentrowaną odległością
  cosinusową. Jego waga wynosi 0,80, a histogramu HSV i edge signature po 0,10.
  Progi i crop pozostają częścią kanonicznego manifestu. V9 nie staje się
  domyślny po samych krótkich profilach; aktywacja wymaga pełnej bramki D-146 i
  jawnej decyzji właściciela.
- **Context:** realny golden 500 zdjęć wykazał, że medianowe progowanie pHash
  potrafi odwrócić bity między niemal identycznymi klatkami. Stare progi
  `.12/.10/.22` były jednocześnie wielokrotnie większe od realnych odległości,
  więc 500 zdjęć zostało fałszywie scalonych w jedną grupę. Ciągła sygnatura
  rozróżniła 20 kolejnych ekranów bez fałszywego scalenia i bez fragmentacji.
- **Reason:** preselektor potrzebuje stabilnej miary podobieństwa obrazu, a nie
  binarnej decyzji wrażliwej na położenie współczynnika względem mediany.
  Centralny crop ogranicza wpływ stałego nagłówka automatu i dolnej obudowy,
  zachowując obszar, w którym zmieniają się plansze.
- **Alternatives:** dalsze podnoszenie progów binarnego pHash odrzucono, ponieważ
  nie naprawia niestabilności deskryptora. Powrót do OCR lub geometrii odrzucono
  jako sprzeczny z odpowiedzialnością v9 i wynikiem wydajnościowym.
- **Consequences:** selector fingerprint wynosi
  `eaca91fd6f6c169f25436a81b1059810152899953d3eecdef980391df7124afb`, a
  scan-adapter fingerprint
  `408bd8574526e07d055958734ce6136288beff5a54cf1dcd9f76f6291edea396`.
  Profile 500 i 3000 przekroczyły 20 zdjęć/s, zachowały bounded pamięć i zerowe
  liczniki ciężkich adapterów. Domyślny v8 oraz wszystkie historyczne
  fingerprinty pozostają dostępne do wznowień.
- **Supersedes:** zastępuje część D-148 opisującą binarny pHash 8×8 i
  przedaktywacyjne fingerprinty v9 z D-148/D-149; nie zmienia range-free
  odpowiedzialności ani polityki reprezentanta.

## D-152 — Selekcja zdjęć ma osobny lokalny execution lane

- **Status:** accepted
- **Date:** 2026-08-05
- **Decision:** wspólny pakiet workera jest uruchamiany jako dwa lokalne
  procesy. General worker konsumuje import, walidację, payout i build Android w
  `execution_slot = 1`; image-selection worker konsumuje wyłącznie
  `image_selection` w `execution_slot = 2`. Atomowy claim filtruje dozwolone
  typy przed założeniem lease. Oba lane używają jednej tabeli `jobs`, jednego
  PostgreSQL, tego samego fencing tokenu i wspólnego panelu Admin.
- **Context:** globalny slot powodował, że wielogodzinna selekcja blokowała
  właściwy Import layoutów, mimo że są to niezależne workflow. Właściciel chce
  przygotowywać kolejną partię zdjęć równolegle z importowaniem wcześniejszego
  wyniku.
- **Reason:** dwa filtrowane procesy usuwają blokowanie kolejki przy minimalnej
  zmianie architektury. Nie wymagają kopiowania danych, drugiego API ani nowego
  mechanizmu retry.
- **Alternatives:** osobny mikroserwis, kontener, URL, baza oraz Redis/Celery
  zostały odrzucone jako niepotrzebna złożoność. Jeden proces z priorytetami
  nadal nie pozwala wykonywać selekcji i importu równolegle.
- **Consequences:** operator uruchamia najwyżej jeden proces każdego lane.
  Równoległe joby konkurują o lokalny CPU, RAM i dysk, więc izolacja kolejki nie
  oznacza gwarancji pełnej wydajności obu procesów. Migracje należy wykonywać
  przy zatrzymanych workerach. API i UI nie wybierają slotu.
- **Supersedes:** zastępuje część D-077/D-139 zakładającą jeden globalny slot;
  zachowuje decyzję o PostgreSQL jobs, fenced lease i braku brokera.

## D-153 — Lokalne worker lanes mają jeden kontrolowany supervisor procesów

- **Status:** accepted
- **Date:** 2026-08-05
- **Decision:** oba procesy workera są domyślnie uruchamiane w tle przez jeden
  skrypt operatorski z akcjami start/status/stop. Ignorowany stan runtime
  przechowuje lane, PID, nazwę procesu, czas startu i ścieżki logów. Operacje
  start/stop są serializowane krótką blokadą pliku; proces jest uznawany za
  zarządzany wyłącznie po zgodności PID, nazwy oraz czasu startu.
- **Context:** D-152 wymaga dwóch długotrwałych procesów. Ręczne utrzymywanie
  dwóch dodatkowych terminali utrudnia obsługę, a sam PID nie chroni przed jego
  ponownym użyciem po restarcie lub zakończeniu workera.
- **Reason:** mały supervisor PowerShell upraszcza lokalną obsługę i trwale
  zapobiega duplikatom bez zmiany runtime jobów, API lub infrastruktury.
- **Alternatives:** autostart Windows, usługa systemowa, Docker Compose dla
  workerów i zewnętrzny process manager zostały odłożone jako niepotrzebne dla
  lokalnego produktu. Ręczne terminale pozostają trybem diagnostycznym.
- **Consequences:** workerów trzeba jawnie uruchomić po restarcie komputera;
  jedno polecenie odtwarza oba lane i usuwa logicznie stare wpisy. Supervisor
  nie zatrzymuje procesów uruchomionych poza nim. Logi i stan są lokalne w
  `.runtime` i nie trafiają do repozytorium.
- **Supersedes:** uzupełnia operatorską część D-152; nie zmienia execution
  slots, lease, fencing ani dozwolonych typów jobów.

## D-154 — Status lane używa fenced heartbeat, a zasoby bounded thread budget

- **Status:** accepted
- **Date:** 2026-08-05
- **Decision:** każdy lokalny worker lane zapisuje w PostgreSQL aktualną
  instancję, losowy token, okresowy heartbeat i budżet wątków. Heartbeat działa
  w osobnym lekkim wątku także przy pustej kolejce i podczas handlera. Panel
  odczytuje wyłącznie stan, wersję, budżet i czasy. Supervisor ustawia domyślnie
  dwa wątki dla general oraz cztery zewnętrzne scan workers dla image selection;
  natywne biblioteki selekcji pozostają jednowątkowe.
- **Context:** sam heartbeat aktywnego joba nie pokazuje zatrzymanego lub
  bezczynnego procesu. Dwa równoległe procesy mogły też tworzyć zagnieżdżoną
  nadsubskrypcję wątków mimo rozdzielonych execution slots.
- **Reason:** mała projekcja daje wiarygodną obserwowalność po restarcie, a
  przenośny budżet wątków ogranicza konkurencję bez Windows-only limitów,
  mikroserwisu albo brokera.
- **Alternatives:** odczyt `.runtime/worker-lanes.json` przez API odrzucono,
  ponieważ nie potwierdza żywotności procesu. Windows Job Objects i twardy
  procent CPU odłożono jako nieprzenośne i niewymagane przed pomiarem TASK-0177.
- **Consequences:** nowa rejestracja odcina stary token. Po 15 sekundach bez
  sygnału status jest `degraded`, po 60 `stopped`; jawne zakończenie działa
  natychmiast. Limity opisują współbieżność, nie gwarantowany procent CPU.
- **Supersedes:** uzupełnia D-152 i D-153 bez zmiany kolejki `jobs`, lease ani
  fencing konkretnego joba.

## D-155 — V9 jest aktywnym manifestem nowych runów przed pełnym pomiarem 40 000

- **Status:** accepted
- **Date:** 2026-08-05
- **Decision:** na jawne polecenie właściciela
  `APPEARANCE_ONLY_SELECTOR_MANIFEST_V9` staje się produkcyjnym
  `DEFAULT_SELECTOR_MANIFEST` przed utworzeniem runu na dostępnych 40 000
  naturalnych zdjęć. API zapisuje dla nowych runów fingerprint
  `eaca91fd6f6c169f25436a81b1059810152899953d3eecdef980391df7124afb`, a worker
  wykonuje range-free ścieżkę bez OCR, geometrii plansz i cropów.
- **Context:** krótkie profile 500 i 3000 zdjęć oraz bramka dwóch worker lane
  przeszły. Właściciel dostarczył pełny korpus i chce, aby właściwy produkcyjny
  run był jednocześnie końcowym pomiarem v9, zamiast tworzyć najpierw kolejny
  run v8.
- **Reason:** aktywacja jest potrzebna, aby panel utworzył job z badanym
  fingerprintem. Nie zmienia istniejącego stagingu ani historycznych runów.
- **Alternatives:** osobny benchmark v9 przed przełączeniem defaultu został
  odrzucony przez właściciela jako zbędny dodatkowy przebieg pełnego korpusu.
- **Consequences:** wszystkie procesy API i workera uruchomione przed zmianą
  trzeba zatrzymać i uruchomić ponownie. V2–v8 pozostają w rejestrze manifestów,
  dlatego ich retry zachowuje poprzedni algorytm. TASK-0171 pozostaje otwarty do
  zapisania metryk 40 000 zdjęć i decyzji właściciela `accepted | optimize`;
  sama aktywacja nie jest odbiorem wydajności.
- **Supersedes:** zmienia wyłącznie kolejność ostatniego punktu D-151: aktywacja
  następuje przed pełnym runem na polecenie właściciela, ale nie usuwa końcowej
  bramki jakości i wydajności.

## D-156 — V10 wybiera najlepsze zdjęcie z całej grupy i zapisuje progresywnie

- **Status:** accepted
- **Date:** 2026-08-08
- **Decision:** nowe runy używają `fast-image-selector-v10`. Każdy obraz jest
  lekko oceniany, pełna weryfikacja obejmuje top-12 całej grupy, a wybór nie ma
  early exit. Run utrwala kierunek i opcjonalny pierwszy numer. Admin wymaga
  katalogu wynikowego przed katalogiem wejściowym i zapisuje każdą zakończoną
  grupę jako `seq_<od>-<do>.jpg`.
- **Context:** v9 skrócił realny run do około 40 minut, ale `first usable`, top-2
  i brak pełnej weryfikacji obniżyły jakość wybieranych zdjęć.
- **Reason:** poprawność wyboru jest ważniejsza od throughputu; użytkownik
  dopuszcza orientacyjnie 3–5 razy dłuższy proces.
- **Alternatives:** utrzymanie v9 i strojenie samych progów odrzucono, ponieważ
  nie porównywał on najlepszych klatek całej grupy. Pełny pipeline każdego
  zdjęcia również odrzucono; symbole i cropy pozostają w `Imporcie layoutów`.
- **Consequences:** v2–v9 pozostają odtwarzalne przez zapisany fingerprint.
  V10 może uruchomić do 12 pełnych weryfikacji na grupę. Odbiór czasu i jakości
  jest ręczny na około 5000 i 32 000 zdjęć.
- **Supersedes:** D-155 jako aktywny manifest nowych runów; D-155 pozostaje
  historycznym opisem aktywacji i wyniku v9.

## D-157 — Skumulowana kohorta gry jest osobnym, niezmiennym manifestem treningowym

- **Status:** accepted
- **Date:** 2026-08-08
- **Decision:** TASK-0143 agreguje aktualny stan review wszystkich importów jednej
  gry do content-addressed manifestu. Pozycje powstają wyłącznie dla kompletnych
  `accepted` i `corrected`; `pending`, `rejected` i niekompletne decyzje są
  uwzględnione w stanie oraz licznikach, ale nie tworzą próbek. Każda pozycja
  wiąże review, import, źródło, geometrię, pipeline i dokładnie 15 cropów.
- **Context:** dotychczasowy `image_verified_cohort_exports` poprawnie zamrażał
  jeden import, lecz trening kolejnych iteracji wymaga pełnego, skumulowanego
  stanu gry bez ręcznego łączenia eksportów i bez czytania zmiennych tabel live.
- **Reason:** wspólny kanoniczny adapter planszy zachowuje jedną definicję
  kompletnej decyzji, a osobny rejestr iteracji daje stabilną tożsamość całemu
  wejściu treningowemu. SHA-256 obejmuje zawartość i proweniencję.
- **Alternatives:** trening bezpośrednio z tabel review, kopiowanie binariów do
  PostgreSQL oraz traktowanie eksportu pojedynczego importu jako skumulowanej
  kohorty odrzucono z powodu braku odtwarzalności albo dublowania danych.
- **Consequences:** identyczny manifest zwraca istniejącą kohortę, zmieniony stan
  tworzy kolejną iterację, a operacje modelu muszą przed zapisem zablokować item
  i potwierdzić `pending` oraz oczekiwane rewizje. TASK-0143 nie uruchamia
  treningu, inferencji ani UI.
- **Supersedes:** rozszerza D-090 z poziomu jednego importu do skumulowanego
  wejścia treningowego gry; nie zmienia historycznych eksportów review.

## D-158 — Dataset symboli ma stabilny hash splitu rodziny źródłowej

- **Status:** accepted
- **Date:** 2026-08-08
- **Decision:** `verified-symbol-training-dataset-v1` grupuje wszystkie cropy
  według checksumy zdjęcia źródłowego i przypisuje całą rodzinę stabilnym
  hashem do 65% train, 15% validation, 10% test albo 10% regression. Seed,
  polityka splitu i wersja transformacji są częścią manifestu.
- **Context:** losowy split po cropach zawyżałby jakość, a ponowne
  balansowanie całej kohorty przy każdej iteracji przenosiłoby stare przykłady
  między zbiorem treningowym i kontrolnym.
- **Reason:** stabilny hash zachowuje rozłączność pochodnych jednego źródła
  oraz stały regression set w kolejnych skumulowanych iteracjach.
- **Alternatives:** losowanie po cropach i globalne ponowne balansowanie przy
  każdym buildzie odrzucono z powodu przecieku albo niestabilnej bramki.
- **Consequences:** przy małej liczbie źródeł niektóre klasy lub splity mogą
  mieć niskie pokrycie; manifest raportuje to jako advisory. Trening i promocja
  modelu muszą respektować przypisanie manifestu i nigdy nie włączać
  regression do train.
- **Supersedes:** doprecyzowuje ogólną politykę source-aware splitu M6.6.

## D-159 — Kandydat modelu kończy wspólną bramkę bez automatycznej aktywacji

- **Status:** accepted
- **Date:** 2026-08-08
- **Decision:** trwały job `symbol_training` po checkpointcie `trained` wykonuje
  eksport ONNX, parity, kalibrację, ocenę test/regression i zapis wspólnego
  manifestu SHA-256. Kończy jako `candidate_ready`, kontrolowane `rejected` albo
  techniczne `failed`. Żaden z tych stanów nie zmienia aktywnego modelu.
- **Context:** checkpoint PyTorch nie gwarantuje zgodności produkcyjnego ONNX ani
  braku regresji pojedynczego symbolu. Pierwsza iteracja może nie mieć aktywnej
  bazy odniesienia.
- **Reason:** jedna checkpointowana operacja zachowuje idempotencję i pełną
  proweniencję, a jawny brak bazy jest bezpieczniejszy niż fałszywe porównanie.
- **Alternatives:** automatyczną aktywację po treningu oraz osobny nietrwały
  proces eksportu odrzucono jako nieaudytowalne i niebezpieczne dla importów.
- **Consequences:** pierwszy kandydat raportuje `baseline_unavailable`; kolejne
  muszą porównywać kandydata i aktywną bazę na identycznych próbkach. Regresja
  recall pojedynczej klasy blokuje promocję nawet przy lepszym accuracy globalnym.
- **Supersedes:** doprecyzowuje D-158; rejestr i aktywacja pozostają zakresem
  TASK-0148.

## D-160 — Aktywny model jest projekcją monotonicznego rejestru zdarzeń

- **Status:** accepted
- **Date:** 2026-08-08
- **Decision:** aktywacja i rollback modelu symboli dopisują per gra niezmienne
  zdarzenie z monotonicznym `activation_number`, nadawanym pod blokadą rekordu
  gry. Aktywny model to zdarzenie z najwyższym numerem. Nowy image import
  przypina pełny checksum-bound snapshot modelu i łączy jego fingerprint z
  fingerprintem pipeline'u.
- **Context:** kolejność po `created_at + UUID` nie gwarantuje kolejności
  uzyskania blokady przez równoległe transakcje. Sam identyfikator aktywnej
  iteracji nie wystarcza też do bezpiecznego użycia cache i odtworzenia
  trwającego importu po późniejszej aktywacji.
- **Reason:** monotoniczny numer daje jednoznaczną projekcję bez mutowalnego
  wskaźnika, a snapshot w jobie izoluje trwający import od kolejnych komend.
- **Alternatives:** osobna mutowalna kolumna aktywnego modelu w `games`, wybór po
  czasie/UUID oraz odczyt aktywnego modelu dopiero przez workera zostały
  odrzucone jako podatne na rozjazd albo zmianę modelu w połowie joba.
- **Consequences:** rollback jest nowym zdarzeniem do wcześniej aktywnej,
  kompletnej wersji. Brak zdarzeń używa jawnego bootstrap snapshotu. Drift
  manifestu, ONNX, klas lub kalibracji blokuje nowy import bez fallbacku.
- **Supersedes:** doprecyzowuje planowaną aktywację TASK-0148 i D-159.

## D-161 — Lease joba jest odnawiany niezależnie od checkpointu handlera

- **Status:** accepted
- **Date:** 2026-08-08
- **Decision:** wspólny runtime workera uruchamia dla każdego claimed joba lekki
  keepalive odnawiający ten sam fenced lease co najwyżej co 15 sekund. Keepalive
  działa niezależnie od heartbeat lane i częstotliwości checkpointów domenowych.
- **Context:** realny run selektora v10 zatrzymał postęp na 96/32079. Analiza
  jednej partii trwała dłużej niż 60-sekundowy lease, więc checkpoint był
  odrzucany, a worker przeliczał tę samą partię w kolejnych attemptach.
- **Reason:** koszt pojedynczego batcha zależy od danych i bibliotek natywnych;
  checkpoint nie może być jedynym mechanizmem podtrzymania własności joba.
- **Alternatives:** wydłużenie lease, zmniejszenie batcha tylko w selektorze i
  heartbeat osadzony w każdym adapterze zostały odrzucone jako kruche albo
  duplikujące mechanizm w treningu, OCR i kolejnych handlerach.
- **Consequences:** checkpoint nadal określa trwały postęp i bounded retry.
  Keepalive nie zapisuje postępu; błąd lub fencing zatrzymuje terminalny zapis.
- **Supersedes:** uzupełnia D-033 i D-154; nie zmienia execution slots ani
  polityki checkpointów domenowych.

## D-162 — V10.1 rozdziela wybór reprezentanta od adaptacyjnego OCR zakresu

- **Status:** accepted
- **Date:** 2026-08-08
- **Decision:** wszystkie zdjęcia grupy zachowują lekki scoring i top-12, ale
  geometria oraz ranking reprezentanta są niezależne od dowodu numeru. OCR
  używa kotwic, adaptacyjnych poziomów klatek `2 -> 4 -> 8 -> 12` i fallbacku
  cropów `18 -> 36 -> 72`. Pełna ścieżka pozostaje dostępna dla konfliktów.
  Rozpoznanego skoku zakresów nie wolno zastąpić przewidywaną ciągłością.
- **Context:** profil 200 realnych zdjęć trwał 377,530649 s. 99 kandydatów
  uruchomiło 792 batche i 7128 cropów OCR; OCR zużył 291,673863 s. Tani scoring
  całej grupy nie był wąskim gardłem.
- **Reason:** redukcja powtarzanego OCR może skrócić typową grupę bez powrotu do
  niedokładnego `first usable` i bez pomijania zdjęć.
- **Alternatives:** stałe obniżenie top-k odrzucono jako ryzyko utraty
  najlepszego kadru. Całkowite usunięcie OCR odrzucono, ponieważ bieżący output
  wymaga `seq_<start>-<end>.jpg`. Wymuszanie kolejnego zakresu odrzucono,
  ponieważ poprawne dane mogą skakać, np. `19–27 -> 400–408`.
- **Consequences:** powstaje wersjonowany manifest selektora. Bramka na tych
  samych 200 zdjęciach oczekuje 60–70% krótszego czasu bez regresji jakości;
  dopiero potem właściciel uruchomi 5000/32 000. Historyczne runy pozostają
  odtwarzalne po swoich fingerprintach.
- **Supersedes:** koryguje D-156 w zakresie wymuszonej ciągłości i pełnego OCR
  całej shortlisty; nie zmienia pełnego scoringu grupy ani progresywnego zapisu.

## D-163 — Iteracyjny import używa trwałego kursora manifestu

- **Status:** accepted
- **Date:** 2026-08-09
- **Decision:** ukończony manifest Selekcji Zdjęć jest rejestrowany jako trwałe
  źródło v0.5. Każdy import atomowo rezerwuje kolejne N wpisów według
  groupOrder. Model symboli i profil siatki są przypinane przy tworzeniu joba i
  działają wyłącznie dla nowych partii.
- **Context:** pojedynczy wynik może zawierać ponad 2100 zdjęć i około 19000
  layoutów. Import całości uniemożliwia krótką pętlę review–ulepszenie–import.
- **Reason:** monotoniczny kursor usuwa ręczne liczenie plików, luki i duplikaty,
  a małe partie pozwalają poprawiać jakość bez zmiany decyzji człowieka.
- **Alternatives:** ręczne wskazywanie zakresów i automatyczne przeliczanie
  wcześniejszych pending odrzucono jako podatne na błędy i rozszerzające zakres.
- **Consequences:** retry wznawia ten sam zakres; nowa partia nie powstaje w
  trakcie aktywnej. Selekcja Zdjęć pozostaje niezmieniona.

## D-164 — Geometria v0.5 używa wersjonowanej kalibracji

- **Status:** accepted
- **Date:** 2026-08-09
- **Decision:** zaakceptowane quady z Reviewera budują osobny profil korekt
  istniejącego detektora. Kandydat ma własną bramkę, aktywację i rollback.
- **Context:** pierwsze iteracje obejmują dziesiątki lub setki zdjęć, czyli za
  mało zróżnicowanych danych na bezpieczny nowy model neuronowy.
- **Reason:** odporna mediana znormalizowanych przesunięć narożników dla
  dokładnego scope `image_selection_run_id + position_index` jest
  deterministyczna i daje szybki efekt w tej samej serii zdjęć. Profil nie
  interpoluje po numerze sekwencji, ponieważ numer powstaje dopiero w OCR po
  cropowaniu; brak scope oznacza użycie detektora bazowego.
- **Alternatives:** trening detektora neuronowego od pierwszej partii odrzucono
  z powodu ryzyka przeuczenia i większej złożoności.
- **Consequences:** po dwóch nieskutecznych iteracjach lub ponad 10% ręcznych
  korekt na reprezentatywnej partii należy zaproponować model neuronowy i użyć
  zachowanej kohorty obraz–cztery narożniki.

## D-165 — Automatyczna nazwa wymaga zgodności zakresu z reprezentantem

- **Status:** accepted
- **Date:** 2026-08-09
- **Decision:** selektor może używać kilku klatek do ustalenia zakresu, ale
  przed automatycznym eksportem finalny JPEG musi potwierdzić ten sam zakres.
  Konflikt dzieli grupę albo kieruje ją do manualnego review. Dopuszczalna jest
  niewielka utrata automatycznego recall na rzecz czasu, lecz nie błędna nazwa.
- **Context:** realna grupa 2109 połączyła klatki `18406-18414` oraz
  `18415-18423`. OCR pierwszych klatek ustalił starszy zakres, a ranking jakości
  wybrał późniejszy obraz i utworzył niespójny `seq_18406-18414.jpg`.
- **Reason:** poprawność pliku wynikowego jest ważniejsza niż pełna automatyzacja;
  jeden bounded check reprezentanta kosztuje mniej niż ponowny import i ręczna
  naprawa błędnie nazwanych danych.
- **Alternatives:** bezwarunkowe przenoszenie zakresu całej grupy na dowolny
  reprezentant odrzucono. Pełny OCR wszystkich zdjęć pozostaje niepotrzebny.
- **Consequences:** powstaje v10.2 i nowy fingerprint przy każdej zmianie decyzji
  domenowej. Historyczne runy zachowują swoje wyniki. Manualny workspace musi
  umożliwić wybór istniejącego kandydata i powrót do konkretnego joba.
- **Supersedes:** ogranicza D-162 w zakresie niezależności reprezentanta od OCR.

## D-166 — Ręczna galeria zachowuje członkostwo grupy bez kopiowania obrazów

- **Status:** accepted
- **Date:** 2026-08-09
- **Decision:** dla nowych runów worker utrwala po jednym lekkim rekordzie
  kandydata dla każdej obserwacji zakończonej grupy. Rekord wskazuje istniejący
  JPEG stagingu i ma znacznik `manualGalleryOnly`; nie zawiera BLOB-a i jest
  pomijany przy odtwarzaniu decyzji selektora. Admin pokazuje te rekordy jako
  lazy-load miniatury, a pełny obraz pobiera dopiero po wyborze. Historyczne runy
  mogą pokazać wyłącznie zachowane top-12 i muszą ujawnić to licznikiem.
- **Context:** duży run pozostawił wiele grup wymagających ręcznej decyzji.
  Użytkownik nie może szukać właściwego JPEG-a ręcznie w folderze 32 000 źródeł
  ani tracić możliwości powrotu do zakończonego joba.
- **Reason:** rekordy metadanych są małe, wykorzystują ten sam bezpieczny staging
  i pozwalają wybrać najlepszy obraz całej grupy bez ponownego OCR lub kopiowania
  wszystkich JPEG-ów.
- **Alternatives:** zapisywanie tylko top-12 nie realizuje pełnego wyboru
  manualnego; kopiowanie obrazów do bazy lub osobnego katalogu dubluje dane;
  rekonstrukcja historycznych granic grup na podstawie domysłów jest
  niedeterministyczna.
- **Consequences:** limit galerii wynosi 500 źródeł na grupę, co przekracza
  oczekiwane 50–100. Ręczna decyzja może unieważnić opublikowany manifest i
  uruchomić jego kontrolowaną rewizję, ale nie zmienia wcześniejszych wpisów
  audytu ani wyniku innych grup.

## D-167 — Zgodny własny OCR może zmiękczyć bramkę geometrii reprezentanta

- **Status:** accepted
- **Date:** 2026-08-10
- **Decision:** po potwierdzeniu zakresu przez konsensus selektor może wybrać
  kandydata z miękkim błędem geometrii lub jakości, jeżeli ten sam JPEG
  samodzielnie odczytuje dokładnie ten zakres z confidence co najmniej `0.90`.
  Inny albo nieznany zakres nadal wymaga ręcznej decyzji.
- **Context:** v10.2 zmniejszył ryzyko błędnych nazw, ale produkcyjny run kierował
  około 37% grup do review. Zapisane dane pokazały dokładnie zgodne odczyty na
  JPEG-ach odrzuconych głównie przez niepełną geometrię i różnicę liczby plansz.
- **Reason:** poprawność nazwy pochodzi z własnego OCR pliku, natomiast pełna
  geometria jest miarą jakości i kompletności późniejszego cięcia. Nie powinna
  sama odrzucać poprawnie nazwanego najlepszego dostępnego źródła.
- **Alternatives:** powrót do bezwarunkowego pożyczania zakresu z v10.1 odrzucono
  przez realny false merge. Pozostawienie wszystkich przypadków w review
  odrzucono z powodu nieakceptowalnego kosztu ręcznego.
- **Consequences:** powstaje `fast-image-selector-v10.3` i nowy fingerprint.
  Wyniki v10.2 pozostają niezmienne; worker musi zostać przeładowany przed nowym
  runem.
- **Supersedes:** doprecyzowuje D-165, nie znosi wymagania zgodności nazwy.

## D-168 — V10.4 używa siatki etykiet i obowiązkowej kotwicy pierwszej grupy

- **Status:** accepted
- **Date:** 2026-08-11
- **Decision:** nowe runy `fast-image-selector-v10.4` wymagają dodatniego
  `first_sequence_number`, rozpoznają zakres z maksymalnie dwóch batchów siatki
  `3×3` i wybierają reprezentanta po lekkiej ocenie całej grupy. Historyczne
  runy i kolumna bazy pozostają nullable oraz odtwarzalne po fingerprintach.
- **Context:** v10.2–v10.3 ograniczyły błędne nazwy, ale pełna geometria i
  progresywny OCR `18/36/72` dominowały czas, a ręczne galerie ujawniły dobre
  JPEG-i odrzucane przez zbyt kosztowną i zbyt ostrą ścieżkę. Pierwsza klatka
  następnego ekranu mogła też wejść do galerii poprzedniej grupy.
- **Reason:** dziewięć etykiet ma znaną topologię i pozwala korygować pojedynczy
  błąd OCR bez hardcode. Jawna pierwsza kotwica usuwa koszt i ryzyko startowego
  zgadywania, ale nie fałszuje późniejszych skoków numeracji.
- **Alternatives:** powrót do `first usable`, pożyczanie dowodu z dowolnego JPEG-a
  i ciągły cursor odrzucono ze względu na jakość oraz realny false merge. Pełny
  OCR top-12 odrzucono jako zbyt kosztowny.
- **Consequences:** zwykła grupa ma najwyżej 18 cropów OCR, wszystkie zdjęcia są
  nadal porównane tanim scoringiem, a niejednoznaczny przypadek pozostaje
  dostępny w trwałej galerii ręcznej. Odbiór na danych następuje osobno.
- **Supersedes:** zastępuje domyślną ścieżkę OCR v10.1–v10.3 dla nowych runów;
  nie zmienia historycznych manifestów.

## D-169 — Duplikat zakresu wymaga jawnej i zweryfikowanej decyzji

- **Status:** accepted
- **Date:** 2026-08-11
- **Decision:** grupa manualna może zostać odrzucona jako duplikat tylko jawną
  akcją administratora i tylko wtedy, gdy backend znajdzie inną rozwiązaną
  grupę tego runu z identycznym zakresem. Decyzja `duplicate_range` projektuje
  grupę do `skipped_existing_range` bez wybranego kandydata.
- **Context:** poprawna ochrona unikalności zwracała
  `IMAGE_SELECTION_RANGE_CONFLICT`, ale modal nie pozwalał zakończyć faktycznej
  kopii. Taka grupa wracała do kolejki po ponownym otwarciu.
- **Reason:** jawna akcja usuwa blokadę pracy, zachowując ochronę przed
  przypadkowym odrzuceniem grupy z błędnie wpisanym numerem.
- **Alternatives:** automatyczne ukrycie po każdym konflikcie odrzucono, ponieważ
  konflikt może oznaczać pomyłkę w zakresie, a nie duplikat obrazu.
- **Consequences:** kontrakt i migracja audytu otrzymują nową rezolucję; plik
  istniejącego zakresu nie jest kopiowany ani nadpisywany.
- **Supersedes:** doprecyzowuje D-129 i D-167.

## D-170 — V10.4 nie przechodzi odbioru; v10.5 odzyskuje OCR v10.3

- **Status:** accepted
- **Date:** 2026-08-11
- **Decision:** v10.4 nie może pozostać domyślnym selektorem. V10.5 używa
  szerokiego grupowania v10.3, bounded bufora granicy v10.4 i lekkiego
  niezależnego OCR na poziomach kandydatów `1/2/4`, bez pełnej geometrii.
- **Context:** realny run 42 403 zdjęć utworzył 3 840 grup, z których 3 388
  (88,23%) trafiło do manualnego wyboru. Tyle samo grup nie miało zakresu, a
  7 401 z 7 680 prób zakończyło się `RANGE_LABEL_GRID_NO_HYPOTHESIS` mimo
  czytelnych etykiet. Podejście v10.4 okazało się zdecydowanie nieskuteczne.
- **Reason:** syntetyczne testy topologii siatki nie reprezentowały rzeczywistego
  rozkładu cropów i OCR. Optymalizacja czasu usunęła recall dojrzałego
  recognizera, przez co przeniosła koszt na użytkownika.
- **Alternatives:** dalsze obniżanie progów grid-only odrzucono jako ryzyko
  błędnych nazw. Pełny powrót do geometrii v10.3 odrzucono z powodu czasu.
- **Consequences:** kolejna wersja nie może zostać domyślna wyłącznie po testach
  syntetycznych. Wymagane jest porównanie na tym samym rzeczywistym wycinku,
  minimum 95% znanych zakresów, maksimum 35% manualnych i zero błędnych nazw w
  zatwierdzonym regression secie.
- **Supersedes:** D-168 w zakresie domyślnego OCR i descriptoru grupowania;
  zachowuje obowiązkową kotwicę oraz bezpieczny bufor granicy.

## D-171 — Ręczna decyzja nie kończy się przed trwałym eksportem JPEG-a

- **Status:** accepted
- **Date:** 2026-08-11
- **Decision:** Admin przechowuje uchwyt katalogu wynikowego w IndexedDB per
  `gameId + runId`, uzgadnia zakończone grupy przed review i przechodzi dalej
  dopiero po poprawnym zapisie ręcznie zatwierdzonego JPEG-a.
- **Context:** decyzje runu `252cb5cb…` były zapisane w bazie, lecz po wybraniu
  historycznego runu uchwyt katalogu istniał wyłącznie w pamięci. Modal pozwalał
  zatwierdzać i przechodzić dalej bez jakiegokolwiek zapisu na dysk.
- **Reason:** baza i folder wynikowy muszą być uzgadnialne po odświeżeniu,
  przełączeniu runu i restarcie przeglądarki. Fire-and-forget ukrywał utratę
  części wyniku przed użytkownikiem.
- **Alternatives:** przechowywanie ścieżki Windows w backendzie odrzucono,
  ponieważ przeglądarka nie może odzyskać dostępu na podstawie samego tekstu.
- **Consequences:** przeglądarka może ponownie poprosić o zgodę; pełne
  uzgodnienie jest idempotentne i nigdy nie nadpisuje kolizji.
- **Supersedes:** doprecyzowuje progresywny eksport D-165.

## D-172 — Fizyczne usunięcie ogranicza się do anulowanego runu selekcji

- **Status:** accepted
- **Date:** 2026-08-11
- **Decision:** właściciel może trwale usunąć wyłącznie anulowany job
  `image_selection`, jeżeli run nie ma handoffu ani opublikowanego manifestu.
  Zarządzane pliki są najpierw przenoszone do kwarantanny i usuwane dopiero po
  commicie bazy. Współdzielony staging i zewnętrzny folder wynikowy pozostają.
- **Context:** anulowane i słabe eksperymentalne runy zaśmiecały listę jobów, a
  samo ukrycie dropdownu selekcji nie zwalniało zarządzanych danych.
- **Reason:** wąski kontrakt daje kontrolę właścicielowi bez wprowadzania
  ogólnego, ryzykownego mechanizmu kasowania historii wszystkich jobów.
- **Alternatives:** ogólny cleanup jobów oraz usuwanie całego stagingu odrzucono,
  ponieważ mogłyby naruszyć audyt, inny run albo dane już przekazane dalej.
- **Consequences:** usunięcie jest nieodwracalne po commicie i wymaga dokładnego
  celu wysokiego ryzyka; awaria transakcji przywraca katalogi z kwarantanny.
- **Supersedes:** doprecyzowuje politykę braku automatycznego cleanupu z
  TASK-0132 i wymagania retencji selekcji zdjęć.

## D-173 — Niepewność reprezentanta i zakresu ma osobne kolejki

- **Status:** accepted
- **Date:** 2026-08-11
- **Decision:** znany zakres bez bezpiecznego JPEG-a otrzymuje
  `manual_required`, a bezpieczny automatyczny JPEG bez zakresu
  `range_required`. Grupa całkowicie nieczytelna kończy się jako
  `skipped_unreadable`. Użytkownik może odrzucić element obu kolejek i
  przywrócić go do stanu zapisanego w `rejection_origin_status`.
- **Context:** v10.5 kierowała do jednego modala zarówno problem wyboru obrazu,
  jak i sam brak numerów. Użytkownik potrafił szybko ustalić zakres czytelnego
  automatycznego zdjęcia, ale interfejs wymuszał ponowną decyzję o JPEG-ie.
- **Reason:** rozdzielenie przyczyn ogranicza pracę manualną, nie osłabiając
  unikalności zakresu ani trwałości wynikowego pliku.
- **Alternatives:** jeden wspólny status i modal odrzucono jako nieprecyzyjny;
  automatyczne zapisywanie całkowicie rozmazanych grup odrzucono jako
  nieużyteczne dla późniejszego importu.
- **Consequences:** statusy, migracja, API i audyt rozróżniają oba workflow.
  Odrzucenie/przywrócenie nie dotyka folderu wynikowego; zatwierdzony obraz nadal
  musi zostać zapisany przed przejściem dalej.
- **Supersedes:** doprecyzowuje wspólną kolejkę manualną z D-129 oraz trwałość
  eksportu z D-171.

## D-174 — Reprezentanta szukamy najpierw w środku grupy

- **Status:** accepted
- **Date:** 2026-08-11
- **Decision:** v10.6 pełniej sprawdza najpierw pięć centralnych klatek grupy.
  Dopiero gdy wszystkie są nieczytelne, sprawdza trzy pierwsze i trzy ostatnie;
  czytelny globalny rekord top-12 pozostaje ostatnim bounded bezpiecznikiem.
  Brak jakiejkolwiek czytelnej klatki daje `skipped_unreadable` bez OCR.
- **Context:** v10.5 zużyła 3634 s z 3810 s selekcji na OCR, a mimo tego 92,62%
  grup trafiło do wspólnego review. Ręczna kontrola pokazała, że środkowe klatki
  często mają stabilny ekran i wystarczająco widoczne symbole.
- **Reason:** centralne klatki ograniczają zdjęcia przejściowe przy zachowaniu
  taniego skanu całej grupy. Łagodna bramka nie odrzuca lekkiego rozmycia.
- **Alternatives:** pełna weryfikacja top-12 pozostaje zbyt kosztowna; pierwsza
  klatka często pokazuje przejście; losowa próbka nie jest deterministyczna.
- **Consequences:** checkpoint utrwala ostatni indeks źródła, a brak zakresu
  przenosi wybrany JPEG do osobnej kolejki `range_required`.
- **Supersedes:** zmienia kolejność kandydatów v10.5, zachowując D-170 w zakresie
  grupowania i historycznej odtwarzalności.

## D-175 — Cztery kolejne pozycje są lokalnym dowodem zakresu dziewięciu

- **Status:** accepted
- **Date:** 2026-08-11
- **Decision:** v10.7 może wyprowadzić pełny zakres `start..start+8` z czterech
  kolejnych etykiet, jeżeli ich liczby i pozycje row-major są kolejne, każda ma
  confidence co najmniej `0.72`, a lokalna geometria siatki jest spójna.
- **Context:** v10.5 zakończyła 968 z 997 prób jako
  `RANGE_LABEL_LATTICE_INCOMPLETE`, mimo że właściciel bez problemu widział
  częściowe ciągi liczb. Próby do 72 cropów odpowiadały za większość czasu.
- **Reason:** cztery kolejne wartości wystarczają matematycznie do ustalenia
  początku po znanej pozycji, a użycie trzech osi lokalnej siatki chroni przed
  przesunięciem wyniku o cały wiersz.
- **Alternatives:** sam ciąg czterech liczb bez pozycji odrzucono jako
  niejednoznaczny; OCR wszystkich dziewięciu pozostaje zbyt kosztowny i kruchy;
  ciągłość z poprzednią grupą narusza poprawne skoki numerów.
- **Consequences:** OCR ma poziomy `9/18/36`, pełny dowód siedmiu etykiet nadal
  ma pierwszeństwo, a każdy remis kończy się fail-closed w `range_required`.
- **Supersedes:** rozszerza lokalny dowód D-170 bez przywracania pełnej
  geometrii ani przewidywanego cursora.

## D-176 — Pełny run v10.7 może rozpocząć się przed bramkami po jawnej decyzji właściciela

- **Status:** accepted
- **Date:** 2026-08-11
- **Decision:** na jawną prośbę właściciela uruchamiamy v10.7 od razu na pełnym
  zbiorze 42 403 JPEG-ów. Run może zostać anulowany po obserwacji tempa i
  jakości pierwszych grup; jego start nie jest automatyczną akceptacją
  algorytmu.
- **Context:** kontrakt v10.7 rekomenduje kolejno małą próbkę, około 5000 zdjęć
  i dopiero pełny corpus. Właściciel preferuje rozpoczęcie pełnego przebiegu i
  ewentualne przerwanie go w trakcie.
- **Reason:** kompletny immutable staging v10.5 jest dostępny do bezkosztowego
  rerunu bez ponownego uploadu 11,2 GB, a progresywny raport pozwala wcześnie
  ocenić tempo, review rate i błędy.
- **Alternatives:** ponowny upload odrzucono jako zbędny; obowiązkowe zatrzymanie
  na 200/5000 odrzucono wyłącznie na podstawie jawnej decyzji właściciela.
- **Consequences:** operator monitoruje ten sam run i nie uruchamia drugiego.
  Pełna decyzja `ready | optimize | reject` nadal wymaga wyniku i ręcznej oceny;
  anulowanie zachowuje już utrwalone dane diagnostyczne.
- **Supersedes:** jednorazowo zmienia kolejność etapów kontraktu v10.7, nie jego
  bramki jakościowe ani wymóg fail-closed.

## D-177 — Cztery etykiety wymagają kotwicy layoutów, nie globalnej bezbłędności OCR

- **Status:** accepted
- **Date:** 2026-08-11
- **Decision:** v10.8 akceptuje jeden spójny ciąg czterech etykiet przypisanych
  do pozycji odtworzonej siatki `3×3`, nawet gdy OCR myli inne etykiety poza tym
  oknem. Kotwica wymaga większości pięciu widocznych ramek i pokrycia wszystkich
  osi. Fragmenty pomiędzy kolejnymi potwierdzonymi zakresami są odrzucane, a
  wiele fragmentów jednej dokładnej luki może utworzyć tylko jeden wynik.
- **Context:** v10.7 skierował 603 z 648 grup do ustalenia zakresu. Na realnym
  zdjęciu OCR poprawnie widział `20003–20006`, lecz globalny konflikt z trzema
  niepotrzebnymi, błędnymi odczytami unieważniał cały JPEG. Grupowanie wyglądu
  tworzyło też dziesiątki małych podgrup jednego przejścia.
- **Reason:** lokalne okno jest wystarczającym dowodem matematycznym po znanej
  pozycji. Błędy poza oknem nie niosą informacji o jego początku. Dokładnie
  ograniczone sąsiednie zakresy pozwalają usunąć duplikaty bez zgadywania skoku.
- **Alternatives:** globalne wymaganie zgodności wszystkich dziewięciu etykiet
  odrzucono jako kruche; cztery liczby bez pozycyjnej kotwicy pozostają
  niebezpieczne; automatyczne wypełnianie dowolnego skoku jest zabronione.
- **Consequences:** detektor selekcyjny ma własne progi, OCR kończy się na
  `9/18`, większościowy silny blur blokuje wybór, a kontrakt 5000/pełny corpus
  nadal wymaga ręcznej oceny z zerem błędnych zakresów.
- **Supersedes:** koryguje niezakotwiczone mapowanie D-175 i zachowuje zasadę
  lokalnego dowodu oraz poprawnych skoków z D-170.

## D-178 — Krótszy dowód zakresu wymaga częściowej kotwicy i jawnego poziomu zaufania

- **Status:** accepted
- **Date:** 2026-08-11
- **Decision:** v10.9 odtwarza lokalną siatkę z co najmniej trzech ramek na dwóch
  wierszach i dwóch kolumnach. Cztery etykiety od `0.72` albo trzy od `0.82`
  wystarczają na jednym JPEG-u. Dwie etykiety od `0.90` wymagają zgodnego zakresu
  na drugim JPEG-u o innym checksumie.
- **Context:** w anulowanym runie v10.8 wszystkie 39 skontrolowanych grup
  `range_required` miało czytelny środkowy JPEG. Detektor widział zwykle 3–6
  poprawnych ramek, ale zerował całą geometrię bez większości 5/9 i kierował OCR
  do kosztownego, zaszumionego fallbacku.
- **Reason:** numer etykiety wraz z pozycją wyznacza początek zakresu bez
  rozpoznawania wszystkich dziewięciu liczb. Rozdzielenie dowodu silnego i
  słabego zwiększa skuteczność bez akceptowania pojedynczego dwupunktowego błędu.
- **Alternatives:** samo obniżenie czterech etykiet do dwóch bez kotwicy
  odrzucono jako podatne na przesunięcie wiersza; wymóg kompletnej siatki 3×3
  odrzucono jako główną przyczynę regresji; cursor poprzedniej grupy nadal nie
  może rozstrzygać poprawnych skoków.
- **Consequences:** v10.9 ma osobny fingerprint; tani cache skanu v10.8 pozostaje
  zgodny. Warianty surowego i przetworzonego cropa są oceniane w kontekście
  całej siatki, a konflikt geometrii lub OCR kończy się fail-closed. Fragment
  ograniczony tym samym dokładnym zakresem jest oznaczany jako duplikat bez
  outputu. Pełny run 42 403 może ruszyć dopiero po bramce pierwszych 1440 zdjęć.
- **Supersedes:** rozszerza D-177 dla częściowo widocznej siatki i zachowuje
  lokalny dowód oraz brak zgadywanej ciągłości z D-170.

## D-179 — Wersja 0.5 kończy się na zaakceptowanym selektorze v10.9

- **Status:** accepted
- **Date:** 2026-08-12
- **Decision:** właściciel zamyka tor 0.5 na `v0.5.16` i akceptuje
  `fast-image-selector-v10.9` jako wystarczająco dobrą podstawę dalszej pracy.
  Następny tor zaczyna się od `v0.6.0` oraz ulepszeń workspace’ów `Gry` i
  `Import layoutów`.
- **Context:** v10.9 przeszedł bramkę 1440 zdjęć, pełny run po korekcie
  trwałości zakończył 42 422 / 42 422, a eksport uzgodnił 2 567 automatycznych
  plików. Nadal istnieją przypadki ręcznego review oraz niewykonane pierwotne
  bramki pełnego importu, skali i hardeningu 0.5.
- **Reason:** obecna jakość selekcji i bezpieczny manualny fallback wystarczają,
  aby przenieść uwagę produktu na dalszy przepływ importu bez kolejnych iteracji
  selektora w tym wydaniu.
- **Alternatives:** dalsze blokowanie 0.5 do ukończenia wszystkich pierwotnych
  bramek odrzucono decyzją właściciela; oznaczanie niewykonanych bramek jako
  zaliczonych również odrzucono.
- **Consequences:** TASK-0208, TASK-0150, TASK-0076, TASK-0080–0089, pełna
  publikacja około 500 000 layoutów, kolejne gry i końcowy hardening pozostają
  jawnie odroczone. `massImportAllowed` pozostaje zamknięte. Trwające runy
  selekcji są operacjami na dostarczonym kodzie i mogą zakończyć się po
  zamknięciu wydania.
- **Supersedes:** zmienia zakres zamknięcia planu 0.5, nie znosi bramek
  bezpieczeństwa ani trwałości danych.

## D-180 — Produkcyjny import v0.6 zachowuje natywny kontekst i skaluje komórkę tylko raz

- **Status:** accepted
- **Date:** 2026-08-13
- **Decision:** produkcyjna ścieżka importu zapisuje osiowy kontekst planszy
  bezpośrednio z obrazu po korekcie EXIF, bez obrotu, prostowania i zmiany
  rozmiaru. Każdy quad komórki jest projektowany z oryginalnych pikseli od razu
  do przypiętego rozmiaru wejścia modelu w jednym resamplingu. Płaszczyzna
  `500 × 300` pozostaje wyłącznie logicznym układem geometrii i historycznym
  artefaktem.
- **Context:** rzeczywisty import siedmiu zdjęć raportował zakończenie `14/14`,
  ale utworzył tylko 9 z oczekiwanych 63 plansz. Historyczna ścieżka prostowała
  mały obraz planszy do `500 × 300`, wycinała komórkę, a następnie ponownie ją
  skalowała do modelu, co zwiększało rozmycie. Na sześciu odrzuconych zdjęciach
  detektor znajdował dokładnie jedną bezpieczną hipotezę siatki dziewięciu
  pozycji.
- **Reason:** pojedyncza interpolacja zachowuje więcej informacji symbolu, a
  natywny podgląd pozwala człowiekowi oceniać rzeczywiste piksele źródłowe.
  Jednoznaczna hipoteza odzyskuje kompletność bez arbitralnego wyboru geometrii.
- **Alternatives:** stałe powiększanie każdej planszy do `500 × 300` odrzucono
  jako stratne; pokazywanie wyprostowanej kopii jako głównego podglądu odrzucono
  jako mylące; akceptowanie pierwszej z wielu hipotez odrzucono jako
  niedeterministyczne i niebezpieczne.
- **Consequences:** powstają wersjonowane adaptery croppera v17, detektora v3 i
  OCR ciągłości strony v2. Reviewer rozpoznaje nowe metadane geometrii, a stare
  importy nadal używają historycznego viewportu i fallbacku skalowania. Rerun
  korzysta z managed originals i tworzy nowy job; nie usuwa poprzednich danych.
- **Supersedes:** zastępuje D-059 i produkcyjne użycie rastra `500 × 300` w
  zakresie finalnych cropów oraz podglądu, ale zachowuje jego logiczną geometrię
  i historyczne artefakty.

## D-181 — V10.10 ufa pełnej siatce etykiet przed częściową geometrią bez górnego rzędu

- **Status:** accepted
- **Date:** 2026-08-13
- **Decision:** v10.10 odrzuca częściową kotwicę, jeżeli żadna obserwowana ramka
  nie leży w górnym rzędzie, i przechodzi do niezależnego czteroelementowego
  okna etykiet z wszystkich trzech rzędów. Zakres musi być zgodny modulo 9 z
  podanym początkiem zbioru. Dwie etykiety nie wystarczają samodzielnie.
- **Context:** run v10.9 miał około 95% nierozstrzygnięć z powodu
  `RANGE_LABEL_LATTICE_INCOMPLETE`, mimo czytelnych numerów. Dwa realne JPEG-i
  zostały jednocześnie błędnie zapisane jako zakresy o trzy mniejsze, ponieważ
  syntetyczny górny rząd siatki trafił na tabelę wypłat. Profil wykazał też
  ekrany kolejnych zakresów ukryte wewnątrz jednej szerokiej grupy wyglądu.
- **Reason:** lokalne liczby i ich przestrzenne pozycje są w tym korpusie
  stabilniejszym dowodem niż niepełne czerwone ramki. Zgodność modulo 9 usuwa
  klatki przejściowe bez przewidywania brakującego numeru, a rozdzielenie grupy
  zachowuje dwa JPEG-i tylko przy dwóch rzeczywistych, kolejnych dowodach.
- **Alternatives:** obniżenie progu do dwóch niezakotwiczonych liczb odrzucono
  jako źródło przesunięć; automatyczne wypełnianie każdej luki odrzucono, bo nie
  gwarantuje istnienia zdjęcia; modyfikację v10.9 odrzucono z powodu trwałych
  fingerprintów runów.
- **Consequences:** v10.10 ma osobny fingerprint i poziomy OCR `12/18`.
  Historyczne v10.9 pozostaje odtwarzalne. Brak dowodu nadal trafia do review
  albo pozostaje luką, natomiast grupa z dwoma bezpośrednio kolejnymi,
  wyrównanymi zakresami może deterministycznie utworzyć dwa wyniki.
- **Supersedes:** zaostrza słaby poziom D-178 dla nowego manifestu, zachowując
  historyczne zachowanie v10.9 oraz zakaz rozstrzygania z kursora.

## D-182 — Naprawa zakresów tworzy run pochodny i przebudowuje lokalne grupy

- **Status:** accepted
- **Date:** 2026-08-13
- **Decision:** naprawa historycznych grup `range_required` tworzy nowy,
  idempotentny run pochodny. Run źródłowy i jego audyt pozostają niezmienne.
  Dla każdego ciągłego bloku problemów system ponownie waliduje sąsiednie
  kotwice, spłaszcza kandydatów do pierwotnej kolejności i wyznacza granice grup
  od nowa; dotychczasowa grupa ani wybrany reprezentant nie są źródłem prawdy.
- **Context:** 748 grup historycznego runu może zawierać nie tylko czytelny
  JPEG bez wyniku OCR, ale też błędnego reprezentanta, false split, false merge
  albo zdjęcie przypisane do sąsiedniego zakresu. Zmiana samego pola zakresu
  utrwaliłaby wadliwe granice i utrudniła rollback.
- **Reason:** osobny wynik umożliwia porównanie, powtórzenie i kontrolę rewizji
  bez ryzyka utraty decyzji użytkownika. Lokalne spłaszczenie zachowuje bounded
  koszt, a jednocześnie nie ufa strukturze, której poprawność jest właśnie
  przedmiotem naprawy.
- **Alternatives:** mutowanie starego runu odrzucono z powodu utraty audytu;
  ponowne OCR tylko reprezentanta odrzucono jako niewystarczające; pełny rerun
  32 079 zdjęć odrzucono jako zbędny przed pomiarem lokalnego recovery.
- **Consequences:** schema wiąże run pochodny ze źródłem, rewizją i trybem
  wykonania. Recovery korzysta z istniejącego lane i stagingu. Zakres może
  zostać przypisany tylko JPEG-owi, którego własny dowód go potwierdza;
  ciągłość może walidować dokładną lukę, ale nie tworzy zakresu samodzielnie.
- **Supersedes:** rozszerza D-181 o bezpieczną naprawę historycznych wyników bez
  zmiany zachowania istniejących fingerprintów.

## D-183 — Dwie etykiety wymagają konsensusu dwóch JPEG-ów i globalnego właściciela zakresu

- **Status:** accepted
- **Date:** 2026-08-14
- **Decision:** v10.12 może użyć dwóch zgodnych etykiet jako słabego dowodu
  wyłącznie przy pewności co najmniej `0.90`, różnych pozycjach siatki i jednej
  hipotezie zakresu. Automatyczny wynik wymaga niezależnego potwierdzenia tego
  zakresu przez dwa JPEG-i o różnych checksumach. Projekcja recovery uzgadnia
  duplikaty zakresów globalnie, również pomiędzy osobno przebudowanymi blokami.
- **Context:** pełny dry-run v10.11 pozostawił 283 grupy `range_required`; 252 z
  nich nie miały alternatywnego rozpoznanego zakresu, a 282 kończyły powodem
  `RANGE_LABEL_LATTICE_INCOMPLETE`. Dwa bloki niezależnie utworzyły też zakres
  `14608–14616`, przez co bramka strukturalna poprawnie zablokowała recovery.
- **Reason:** dwie bardzo pewne i przestrzennie zgodne liczby wystarczają do
  zaproponowania zakresu, lecz bezpieczeństwo zapewnia dopiero zgodność dwóch
  fizycznie różnych zdjęć. Globalny właściciel jest konieczny, bo lokalne bloki
  nie widzą wzajemnie swoich wyników.
- **Alternatives:** zaakceptowanie pojedynczego dwucyfrowego odczytu odrzucono
  jako zbyt ryzykowne; inferowanie z samej luki odrzucono, bo nie dowodzi
  istnienia zdjęcia; modyfikację v10.11 odrzucono z powodu niezmiennych
  fingerprintów historycznych runów.
- **Consequences:** v10.12 ma osobny fingerprint i cache weryfikacji. Jedyna
  chroniona decyzja użytkownika wygrywa z wynikiem automatycznym; konflikt co
  najmniej dwóch chronionych decyzji pozostaje fail-closed. V10.11 nadal można
  odtworzyć bez zmiany zachowania.
- **Supersedes:** rozszerza D-181 i D-182 dla v10.12 bez osłabienia zakazu
  rozstrzygania z kursora lub pojedynczego JPEG-a.

## D-184 — Pełne granice sekwencji wyznaczają dokładną liczbę grup

- **Status:** accepted
- **Date:** 2026-08-14
- **Decision:** v10.13 zapisuje inkluzywne `first_sequence_number` i
  `last_sequence_number`, a następnie wymaga dokładnie
  `ceil((abs(last-first)+1)/9)` logicznych właścicieli w ciągłej siatce.
  Nadmiarowe fizyczne fragmenty są jawnymi duplikatami właściciela. Chronione
  decyzje użytkownika są twardymi ograniczeniami, a potencjalny false merge nie
  może zostać pominięty bez ponownej segmentacji.
- **Context:** źródłowy run `1–19809` ma 2295 fizycznych fragmentów. V10.12
  oznaczył 128 jako `skipped_existing_range`, pozostawiając 2167 właścicieli,
  chociaż inkluzywny zakres wymaga 2201. Odrzucono więc o 34 fragmenty za dużo;
  występowały też duże pominięte grupy i automatyczne zakresy przesunięte
  względem globalnej siatki modulo 9.
- **Reason:** sam OCR potwierdza treść widocznego JPEG-a, ale nie dowodzi
  kompletności całej projekcji. Znane granice folderu dostarczają niezależnego,
  deterministycznego inwariantu liczności i pozwalają wykryć false split,
  false merge oraz nadmiarowe odrzucenie.
- **Alternatives:** samo policzenie statusów po zakończeniu odrzucono, bo nie
  naprawia wyniku; sekwencyjne przepisanie numerów bez ponownej segmentacji
  odrzucono, bo utrwala błędne granice i reprezentantów; wymaganie wielokrotności
  dziewięciu odrzucono, ponieważ ostatnia grupa legalnie może być krótsza.
- **Consequences:** migracja 0043 dodaje koniec sekwencji i rozszerza klucze
  idempotencji. Folder o ścisłej nazwie `pierwszy - ostatni` ustawia granice
  automatycznie. Pełny run oraz recovery wykonują końcowe uzgodnienie przed
  publikacją. V10.12 pozostaje odtwarzalne, a cache jego identycznej weryfikacji
  obrazu może zostać użyty przez v10.13.
- **Supersedes:** rozszerza D-182 i D-183 o globalny inwariant kompletności;
  nie osłabia ochrony decyzji użytkownika ani bramek jakości reprezentanta.

## D-185 — Końcowa projekcja i eksport są osobnymi atomowymi bramkami

- **Status:** accepted
- **Date:** 2026-08-14
- **Decision:** pełny run z kompletnymi granicami sekwencji zapisuje wynik
  reconciliacji dedykowaną fenced transakcją dwufazową: najpierw zwalnia zakresy
  modyfikowalnych właścicieli automatycznych i sloty wybranych kandydatów grup
  niechronionych, następnie zapisuje całą projekcję i przed commitem sprawdza jej
  dokładną liczność, siatkę i reprezentantów. `selected_candidate` jest
  autorytatywny wobec historycznych decyzji pozostałych `top_candidates`.
  Dokładne liczniki statusów projekcji są zapisywane w payloadzie checkpointu,
  natomiast ogólne liczniki domeny joba stanowią monotoniczną kopertę historii
  wykonania i nie cofają się po retry ani zmianie klasyfikacji.
  Terminalny runner
  ponownie czyta wszystkie grupy od początku i oddzielnie bramkuje logiczne
  pokrycie projekcji oraz pokrycie gotowych grup plikami.
- **Context:** pierwszy pełny run v10.13 zeskanował 32 079 JPEG-ów, ale
  sekwencyjny upsert końcowych zakresów trafił w częściowy unikalny indeks, gdy
  docelowy zakres nadal należał do jeszcze niezmienionego rekordu. Transakcja
  cofnęła całą reconciliację. Po zwolnieniu zakresów ujawnił się analogiczny
  konflikt reprezentanta: nowy JPEG był autorytatywny, ale stary element listy
  kandydatów nadal niósł historyczne `selected_automatic` lub `selected_manual`.
  Po naprawie obu indeksów rzeczywisty zapis 2201 właścicieli przeszedł, lecz
  checkpoint próbował zmniejszyć historyczne `success_count` z 1888 do 1406 i
  został odrzucony jako `JOB_PROGRESS_REGRESSION`.
  Niezależnie progresywny kursor eksportu nie wracał do wcześniejszych grup
  wypromowanych dopiero w końcowej projekcji.
- **Reason:** inwariant 2201 właścicieli musi obowiązywać również w trwałym
  stanie bazy, a nie tylko w wyniku czystej funkcji. Eksport jest projekcją
  wtórną i wymaga własnego pełnego uzgodnienia, ponieważ monotoniczny polling nie
  obserwuje zmian za kursorem.
- **Alternatives:** odroczone ograniczenie unikalności i sekwencyjne retry
  odrzucono jako zależne od kolejności oraz trudniejsze do audytu; usunięcie
  indeksu odrzucono, bo osłabiłoby globalnego właściciela zakresu; pełny ponowny
  OCR odrzucono, ponieważ checkpoint 32 079 źródeł jest kompletny.
- **Consequences:** decyzje użytkownika i kandydaci ich chronionych grup nigdy
  nie są zwalniani w pierwszej fazie. Każdy błąd powoduje rollback i stabilny
  kod domenowy. Raport schema v3
  jest wymagany przed przejściem kolejki, a `failed`/`cancelled` nie naprawia
  katalogu. Manifest selektora v10.13 nie zmienia się, bo poprawka dotyczy
  trwałości i projekcji wynikowej, nie algorytmu analizy obrazu. Konsumenci
  aktualnego stanu selekcji czytają dokładne liczniki payloadu; ogólne liczniki
  joba mogą być wyższe po rekonsyliacji, bo opisują historię wykonania.
- **Supersedes:** rozszerza D-184 o trwałość końcowego inwariantu i kanoniczny
  eksport bez zmiany reguł selektora.

## D-186 — Produkcyjna selekcja używa czterech skanerów i jednego verifiera

- **Status:** accepted
- **Date:** 2026-08-15
- **Decision:** domyślny łączny budżet CPU lane `image-selection` wynosi pięć:
  cztery `scan_workers` i jeden `verification_worker`. Natywne biblioteki
  pozostają jednowątkowe, a drugi verifier nie jest aktywowany. Zmiana dotyczy
  wyłącznie wykonania i nie zmienia manifestu ani fingerprintu v10.13.
- **Context:** dotychczasowy budżet cztery dawał efektywnie trzy skanery i jeden
  verifier. Profil ABBA na tym samym wycinku 1000 JPEG-ów porównał czasy
  `3+1`: `225,290 s` i `195,385 s` z czasami `4+1`: `195,612 s` i
  `193,237 s`. Średnie wyniosły odpowiednio `210,338 s` i `194,425 s`.
- **Reason:** wariant `4+1` skrócił średni wall time o `7,566%`. Kanoniczne
  projekcje grup, zakresy, reprezentanci, checksumy i decyzje kandydatów były
  identyczne we wszystkich czterech wykonaniach.
- **Alternatives:** pozostawienie `3+1` odrzucono po powtarzalnym pomiarze.
  Aktywację dwóch verifierów oraz równoległe joby produkcyjne odłożono, ponieważ
  stanowią osobne zmiany modelu zasobów i wymagają własnej bramki operacyjnej.
  GPU nie jest używane przez bieżący pipeline i wymagałoby osobnego prototypu.
- **Consequences:** supervisor i bezpośrednie uruchomienie CLI stosują domyślnie
  budżet pięć. Jawne `--cpu-thread-budget 4` nadal odtwarza konfigurację `3+1`.
  Po wdrożeniu lane selekcji musi zostać kontrolowanie przeładowany, aby nowy
  proces zarejestrował budżet pięć w heartbeat.
- **Supersedes:** aktualizuje zasobową część D-154 i pomiarową konsekwencję
  TASK-0194; nie zmienia execution slotów, lease, fencing ani reguł selektora.

## D-187 — Pełny run ogranicza rozmiar fragmentu przed bramką liczności

- **Status:** accepted
- **Date:** 2026-08-15
- **Decision:** selektor v10.14 dla runu z pełnymi granicami dzieli wejście tak,
  aby jeden fizyczny fragment zawierał najwyżej
  `max(1, floor(source_count / expected_group_count))` źródeł. Granica obrazu
  może zakończyć fragment wcześniej. Reconciler nadal wybiera dokładnie jednego
  rzeczywistego właściciela każdej logicznej grupy i oznacza nadmiar jako
  duplikaty.
- **Context:** run `124129–149634` utworzył na v10.13 tylko 2678 fizycznych grup
  wobec 2834 wymaganych. Jedna błędnie scalona grupa zawierała 110 kolejnych
  JPEG-ów z wieloma czytelnymi, różnymi zakresami; ograniczone próbkowanie środka
  i brzegów nie mogło jej bezpiecznie rozdzielić po skanowaniu.
- **Reason:** reconciler może odrzucić nadmiarowe fragmenty, ale nie może stworzyć
  brakującego właściciela bez rzeczywistego zdjęcia. Limit wejściowy gwarantuje
  wystarczającą liczbę kandydatów i zachowuje pochodzenie każdego wyboru.
- **Alternatives:** zwiększenie liczby próbek OCR we wszystkich dużych grupach
  odrzucono jako wolniejsze i nadal zależne od rozpoznania etykiet. Tworzenie
  pustych lub syntetycznych grup odrzucono jako naruszenie inwariantu źródła.
- **Consequences:** pełny run z liczbą źródeł mniejszą niż oczekiwana liczba grup
  kończy się `IMAGE_SELECTION_SOURCE_CARDINALITY_UNDERFLOW`. V10.14 ma osobny
  manifest i fingerprint; może czytać zgodny cache weryfikacji v10.13/v10.12.
  Historyczne fingerprinty nie zmieniają się.
- **Supersedes:** rozszerza D-183 i D-184 o gwarancję wystarczającej liczby
  fizycznych fragmentów przed końcową reconciliacją.

## D-188 — Lokalny Reviewer nie wymaga zdalnej sesji ani kodu

- **Status:** accepted
- **Date:** 2026-08-15
- **Decision:** Admin udostępnia osobny przycisk `Otwórz lokalnie`, który przez
  stały endpoint i skrypt uruchamia Reviewer na `http://127.0.0.1:3001` bez
  Cloudflare. Lokalny URL otwiera wskazany scope `gameId + importJobId` bez
  sesji i kodu wyłącznie przy wejściu strony przez loopback.
- **Context:** kod i rozdzielony link są potrzebne dla dostępu zdalnego, ale
  podczas pracy na tym samym komputerze dodawały niepotrzebne kroki i zależność
  od dostępności Internetu.
- **Reason:** loopback jest już zaufaną granicą lokalnego właściciela Admin API.
  Rozdzielenie trybów upraszcza lokalną pracę bez osłabiania publicznej bramki.
- **Alternatives:** uruchamianie tunelu także dla pracy lokalnej odrzucono jako
  zależność sieciową. Umieszczenie trwałego tokenu albo kodu w URL odrzucono ze
  względu na historię przeglądarki i logi.
- **Consequences:** produkcyjny build Reviewera musi istnieć, jeśli port 3001
  nie jest już obsługiwany przez lokalny proces. Publiczny host ignoruje
  parametry trybu lokalnego i nadal wymaga ograniczonej sesji z kodem.
- **Supersedes:** uściśla lokalną część D-43, D-44 i D-122; nie zmienia modelu
  zagrożeń ani lifecycle zdalnej sesji.

## D-189 — Limit liczności jest adaptowany do pozostałego wejścia

- **Status:** accepted
- **Date:** 2026-08-16
- **Decision:** v10.15 wyznacza maksymalny rozmiar otwartego fragmentu jako
  `ceil(remaining_sources / remaining_groups)`. Po naturalnej granicy limit jest
  przeliczany. V10.14 i jego stała reguła pozostają niezmienne.
- **Context:** statyczne `floor(total / expected)` naprawiło brakujące granice,
  ale dla runu `149626–177288` utworzyło 4273 fragmenty wobec 3074 wymaganych
  właścicieli. 1199 nadmiarowych fragmentów uruchomiło dodatkowe weryfikacje;
  pełna selekcja trwała 24 377,456 s i była wyraźnie wolniejsza od v10.13.
- **Reason:** adaptacyjny iloraz nadal gwarantuje wystarczającą liczbę
  rzeczywistych fragmentów, lecz bez sztucznego minimum wynikającego z
  zaokrąglenia w dół. Naturalna segmentacja zachowuje pierwszeństwo.
- **Alternatives:** usunięcie bramki liczności odrzucono, bo przywróciłoby false
  merge v10.13. Sztywny limit czasu odrzucono; porównanie wydajności musi używać
  tego samego stagingu i zimnego cache'u.
- **Consequences:** manifest v10.15 ma osobny fingerprint, może czytać zgodny
  cache v10.14/v10.13/v10.12 i raportuje wymuszone granice w telemetrii.
  Wznowienie nie wymaga nowego pola checkpointu.
- **Supersedes:** koryguje strategię limitu D-187 bez osłabienia jej gwarancji
  liczności.

## D-190 — OCR ma bezpieczną ścieżkę szybką i niezmieniony pełny fallback

- **Status:** accepted
- **Date:** 2026-08-16
- **Decision:** v10.16 sprawdza center-first kandydatów na poziomach `1,2,4`
  przy szerokim limicie 12. Kończy szybko tylko po dwóch mocnych, zgodnych
  odczytach z różnych checksumów. W pozostałych przypadkach wykonuje pełną
  ścieżkę v10.15 z poziomem 18.
- **Context:** telemetria runu v10.14 pokazała, że około 90% czasu selekcji
  przypadało na OCR, a zimny cache uruchamiał znacznie więcej poziomów 18.
  Jednocześnie samo zwiększanie równoległości verifiera wcześniej pogarszało
  czas wykonania.
- **Reason:** większość czytelnych grup ma zgodne środkowe kadry. Dwa niezależne
  mocne odczyty pozwalają zatrzymać OCR przed drogim rozszerzeniem, zachowując
  pełny algorytm jako fail-closed fallback dla trudnych zdjęć.
- **Alternatives:** akceptację jednego mocnego albo jednego słabego odczytu
  odrzucono jako regresję bezpieczeństwa. Usunięcie poziomu 18 odrzucono, bo
  zmniejszyłoby odzysk trudnych, ale czytelnych grup. Drugi verifier pozostaje
  nieaktywny zgodnie z D-186.
- **Consequences:** v10.16 ma osobny adapter range i fingerprint. Szybkie wyniki
  nie trafiają do pełnego cache, a fallback może promować zgodne wpisy
  v10.15/v10.14/v10.13/v10.12. Telemetria rozdziela oba etapy.
- **Supersedes:** rozszerza D-189 o optymalizację OCR; nie zmienia reguł
  liczności ani końcowej reconciliacji.

## D-191 — Reprezentant jest próbkowany w pięciu wewnętrznych kwantylach

- **Status:** accepted
- **Date:** 2026-08-16
- **Decision:** v10.17 sprawdza pozycje `50%, 35%, 65%, 15%, 85%` etapami
  `1,3,5`. Nie sprawdza pierwszego ani ostatniego zdjęcia. Każdy kandydat
  przechodzi najwyżej raz przez jeden progresywny verifier `12 → 18`.
- **Context:** v10.16 nadal używał historycznego próbkowania pięciu kolejnych
  zdjęć środka oraz po trzech z obu krawędzi. Benchmark 100 rzeczywistych
  źródeł wykazał 177,692 s i 144 weryfikacje wobec 137,677 s i 101 weryfikacji
  v10.15. Brak konsensusu powodował powtórzenie poziomu 12 w pełnym fallbacku.
- **Reason:** kwantyle obejmują wnętrze całej grupy bez podatnych na zmianę
  ekranu i rozmazanie skrajnych klatek. Pięć próbek ogranicza koszt, a dwa różne
  mocne odczyty zachowują bramkę poprawności zakresu.
- **Alternatives:** pierwszą i ostatnią klatkę odrzucono jako ryzykowne źródło
  sąsiedniej grupy. Siedem próbek odłożono do osobnej wersji po pomiarze
  skuteczności pięciu. Akceptację samego środka odrzucono, ponieważ jeden błąd
  OCR nie jest bezpiecznym dowodem zakresu.
- **Consequences:** v10.17 ma osobny manifest i fingerprint. Historyczne
  fingerprinty pozostają niezmienne. Ponieważ pełny verifier pojedynczego
  JPEG-a jest zgodny, cache v10.15–v10.12 może być bezpiecznie promowany.
  Benchmark 100 JPEG-ów zmierzył 79,856 s i 75 weryfikacji wobec 131,387 s i
  101 weryfikacji v10.15, czyli poprawę wall time o 39,221%.
- **Supersedes:** koryguje koszt i strategię próbkowania D-190 bez cofania
  adaptacyjnego partycjonowania D-189.

## D-192 — Mocny czytelny kwantyl może sam zakończyć grupę

- **Status:** accepted
- **Date:** 2026-08-16
- **Decision:** v10.18 zachowuje poziomy `50% → 35%/65% → 15%/85%`, ale jeden
  mocny, niefuzzy zakres z JPEG-a przechodzącego pełną bramkę czytelności może
  zakończyć grupę. Po takim sukcesie pozostałe kwantyle nie są weryfikowane.
- **Context:** rzeczywisty run v10.17 `177220–179082` wykonywał średnio `4,53`
  weryfikacji na grupę, około 91% czasu zużywał w OCR i osiągał około 314
  JPEG-ów na 15 minut. Benchmark v10.17 mierzył czas, ale jego 15 grup nie
  zawierało żadnego automatu, więc nie potwierdził oczekiwanej reguły
  center-first ani recall automatu.
- **Reason:** właściciel akceptuje pojedynczy czytelny środek, jeżeli layout i
  zakres są jednoznaczne. Dodatkowe próbki mają być fallbackiem dla słabego lub
  nierozpoznanego środka, a nie obowiązkowym drugim dowodem.
- **Safety:** fuzzy, konflikt fuzji, dwa różne mocne zakresy, zakres poza siatką,
  blur layoutu, okluzja, niewidoczna plansza i błąd techniczny nadal blokują
  automat. Konflikt wykryty w parze jest lepki dla całej grupy.
- **Consequences:** v10.18 otrzymuje osobny manifest i fingerprint. V10.17
  pozostaje odtwarzalne z wymogiem dwóch checksumów. Cache pojedynczych
  weryfikacji v10.17–v10.12 jest zgodny, ponieważ OCR i adaptery nie zmieniają
  semantyki.
- **Supersedes:** zmienia odrzuconą w D-191 alternatywę jednego mocnego środka
  zgodnie z późniejszą jawną decyzją właściciela; zachowuje kwantyle i
  partycjonowanie D-189/D-191.

## D-193 — Sekwencja waliduje częściowy OCR i rozdziela sklejone zakresy

- **Status:** accepted
- **Date:** 2026-08-18
- **Decision:** v10.20 zachowuje niezależny trzyetykietowy dowód v10.19. Może
  dodatkowo potwierdzić dokładnie następny slot po dwóch dokładnych etykietach
  pełnej geometrii albo po trzech pozycjach częściowego viewportu, jeśli co
  najmniej jedna jest dokładna, pozostałe mają dystans OCR najwyżej jeden, a
  pozycje obejmują dwa wiersze i dwie kolumny. Mocny inny zakres blokuje tę
  ścieżkę.
- **Context:** tani deskryptor potrafił skleić sąsiednie strony, a OCR pojedynczej
  czytelnej klatki mylił jeden znak. Skutkiem były przesunięte zakresy albo
  utrata właściciela mimo deterministycznej kolejności grup po dziewięć.
- **Reason:** pełne granice określają jedyny dopuszczalny następny slot, ale nie
  zastępują dowodu z JPEG-a. Trzy przestrzennie rozłożone obserwacje ograniczają
  ryzyko pojedynczej pomyłki, a rozszerzenie do pięciu kwantyli występuje tylko
  przy niezgodności z oczekiwanym slotem.
- **Consequences:** adapter v18 ma fingerprint
  `5b979eb826bbf943047bff41a98e293ecf9f3cb46ba95044b606edd32a33bd86`.
  Sklejone sąsiednie zakresy z osobnym mocnym dowodem są rozdzielane, a
  nadmiarowe fragmenty po przypisaniu wszystkich slotów są duplikatami, nie
  logicznymi właścicielami ani pozycjami review. Korpus regresyjny 283 JPEG-ów
  i 20 ręcznych adnotacji jest obowiązkową bramką zmian tej ścieżki.
- **Supersedes:** precyzuje D-192 dla niezgodności zakresu i rozszerza proof-first
  v10.19 bez zmiany historycznych fingerprintów.

## D-194 — Lokalny fallback ręcznej selekcji zdjęć

- **Status:** accepted
- **Date:** 2026-08-18
- **Decision:** Admin otrzymuje osobną zakładkę `Ręczna selekcja`, która działa
  lokalnie na dwóch folderach wybranych przez operatora. Zakresy są wyliczane
  jako `start–start+8`; Enter zapisuje bieżący JPEG i zwiększa start o 9, Tab
  pomija zakres przy tym samym zdjęciu, a strzałki zmieniają tylko zdjęcie.
- **Context:** automatyczne selektory wielokrotnie wymagały ręcznej korekty, a
  ponowne uruchamianie OCR dla czytelnych zdjęć zużywało czas bez gwarancji
  poprawnego zakresu. Potrzebny jest prosty, przewidywalny tor awaryjny.
- **Reason:** bezpośredni odczyt i zapis przez File System Access API zachowuje
  jakość oryginału i nie zależy od dostępności API, workera, stagingu ani sieci.
  IndexedDB pozwala wznowić pracę po zamknięciu okna.
- **Safety:** zapis i undo są związane z checksumem źródła; obcy plik o tej samej
  nazwie blokuje operację. Zakładka nie mutuje automatycznych jobów ani bazy.
- **Consequences:** pliki `seq_*.jpg` są gotowym lokalnym wynikiem do późniejszego
  jawnego importu layoutów. Automatyczny kontrakt selekcji pozostaje bez zmian.

## D-195 — Ręczna selekcja zapisuje trwały ślad do kohorty rankera

- **Status:** accepted
- **Date:** 2026-08-18
- **Decision:** IndexedDB v2 utrzymuje append-only zdarzenia widoczności i
  decyzji. Kandydat treningowy wymaga udanego dekodowania oraz co najmniej
  300 ms rzeczywistego wyświetlenia. Wynik zaakceptowanych plików jest
  synchronizowany jako `manual-image-selection-output-v1.json`, a pełny ślad
  jest eksportowany jawnie jako `manual-image-selection-trace-v1.json`.
- **Reason:** dane do późniejszego uczenia nie mogą zależeć od pamięci sesji ani
  spowalniać każdego Entera. Tab nie jest negatywną etykietą, a historyczne
  sesje bez pomiaru widoczności pozostają `anchor_only`.
- **Safety:** manifest obcej sesji lub zmieniony checksum blokuje zapis;
  istniejące decyzje i uchwyty folderów są zachowane podczas migracji.
- **Consequences:** kohorta rankera może być zbudowana deterministycznie z
  jawnie zamrożonego śladu bez kopiowania JPEG-ów do bazy.

## D-196 — Zakres z nazwy `seq_*` jest poświadczonym źródłem numerów

- **Status:** accepted
- **Date:** 2026-08-18
- **Decision:** Folder zawierający nazwy `seq_<start>-<end>.jpg|jpeg` jest
  walidowany jako tryb importu poświadczonych zakresów. Worker sortuje zakresy
  numerycznie, blokuje duplikaty i nakładanie, zachowuje luki jako ostrzeżenia,
  a adapter `sequence-number-from-attested-range-v1` pomija OCR numerów.
- **Safety:** deklaracja jest używana tylko przy dokładnej, uporządkowanej
  geometrii i oczekiwanej liczbie plansz. Częściowy detektor pozostawia brak
  numeru i kieruje obraz do korekty; nie wolno przesuwać numerów po cichu.
- **Consequences:** managed manifest oraz wynik stage niosą początek, koniec i
  źródło zakresu. Historyczne importy bez `seq_*` nadal używają OCR i pozostają
  odtwarzalne.

## D-197 — Ranker jakości działa najpierw wyłącznie w cieniu

- **Status:** accepted
- **Date:** 2026-08-18
- **Decision:** `representative-quality-mlp-v1` uczy się na jawnie zamrożonych,
  checksumowanych śladach ręcznej selekcji. Ocenia siedem surowych metryk jakości
  i względną pozycję zdjęcia, ale w pierwszym wdrożeniu tylko raportuje ranking
  pięciu kandydatów w już istniejącej grupie.
- **Reason:** ręczne etykiety są wartościowe dla preferencji reprezentanta, ale
  nie są dowodem granic grup. Oddzielenie rankera od segmentacji ogranicza
  ryzyko powtórzenia regresji zakresów.
- **Safety:** Tab i niejednoznaczne pary nie tworzą negatywów; wymagane są
  checksumy, dwa foldery, 300 grup i 1000 par przed promocją. Snapshot z innym
  statusem niż `shadow` nie wpływa na v10.21.
- **Consequences:** kohorty, iteracje i aktywacje mają osobne append-only tabele;
  aktywny v10.22 wymaga osobnej decyzji właściciela.

## D-198 — Poświadczony numer jest widoczny i jawnie odblokowywany w Reviewerze

- **Status:** accepted
- **Date:** 2026-08-18
- **Decision:** plansza przypisana z `seq_<start>-<end>` przenosi źródło zakresu do
  geometrii review. Reviewer pokazuje operatorowi, że numer pochodzi z nazwy
  pliku, a pole numeru pozostaje zablokowane do kliknięcia jawnej akcji korekty.
- **Reason:** deklarowany zakres ma być źródłem prawdy, ale człowiek musi móc
  poprawić go w przypadku błędnej nazwy lub geometrii bez niejawnej zmiany.
- **Safety:** korekta wymaga istniejącego mechanizmu rewizji i nie przesuwa
  numerów pozostałych plansz; metadane źródła są zachowywane przy zapisie geometrii.
- **Consequences:** zwykłe importy OCR pozostają bez blokady, a poświadczone
  importy są jednoznaczne dla operatora i audytu.

## D-199 — Kanoniczne sekwencje są idempotentne między importami

- **Status:** accepted
- **Date:** 2026-08-18
- **Decision:** dla gry para `game_id + sequence_number` ma jednego właściciela
  po decyzji `accepted/corrected`. Kolejny import pomija ten numer; inne źródło
  jest alternatywą audytową i nie otwiera review bez jawnej decyzji operatora.
- **Reason:** ponowne przetwarzanie tych samych pierwszych zdjęć powodowało
  duplikaty review i wymuszało wielokrotne zatwierdzanie tych samych plansz.
- **Consequences:** import otrzymuje niezmienny snapshot kanonicznych numerów,
  a kolejka review jest sortowana po sekwencji i wznawia się od pierwszej luki.

## D-200 — Odświeżenie siatki jest pending-only i rewizyjne

- **Status:** accepted
- **Date:** 2026-08-19
- **Decision:** po aktywacji profilu siatki przycisk `Przelicz oczekujące`
  uruchamia osobny job wyłącznie dla plansz `pending`. Nowe cropy są zapisywane
  jako rewizja geometrii, a równoległa decyzja człowieka wygrywa przez blokadę.
- **Reason:** uczenie i poprawa detekcji nie mogą ponownie otwierać ani zmieniać
  zatwierdzonych plansz ani wymuszać pełnego importu/OCR.
- **Consequences:** rozwiązane źródła są pomijane, częściowo rozwiązane mogą
  zostać odświeżone, a późniejsze przeliczenie symboli korzysta z najnowszej
  rewizji cropów.

## D-201 — Browser staging `seq_*` ma trwały manifest i jawny, idempotentny start

- **Status:** accepted
- **Date:** 2026-08-19
- **Decision:** finalized browser staging dla `layout_import` pozostaje na dysku
  po restarcie API, a `_browser_manifest.json` jest źródłem logicznych nazw
  `seq_<start>-<end>`. Admin najpierw pobiera checksumowany preflight, pokazuje
  liczniki nowych, użytych ponownie i pominiętych sekwencji, a dopiero jawny
  start tworzy job. Start jest idempotentny dla `game + upload + manifest` i
  zwraca istniejący job zamiast tworzyć drugi.
- **Context:** wcześniejszy przepływ kończył upload, ale przycisk startu był
  oddzielony od wyniku, token żył wyłącznie w pamięci API, a worker widział
  fizyczne nazwy `00000001.jpg` zamiast poświadczonych zakresów. Restart lub
  odświeżenie mogły więc pozostawić 517 MB stagingu bez możliwości wznowienia,
  a uruchomienie groziło utratą zakresów i powrotem do OCR.
- **Safety:** manifest jest walidowany pod kątem wersji, purpose, kolejności,
  bezpiecznych ścieżek, rozmiarów, checksum i overlapów. Preflight oraz start
  ponownie sprawdzają staging i projekcję kanoniczną; zmiana któregokolwiek
  checksumu daje stabilny konflikt, a obcy `gameId` jest blokowany.
- **Consequences:** legacy token pozostaje dla innych przepływów, lecz Admin
  importu layoutów korzysta z trwałego uploadId, listy gotowych stagingów,
  preflightu i wygenerowanego klienta OpenAPI. Worker zachowuje jednocześnie
  logiczną nazwę `seq_*` i fizyczną ścieżkę pliku stagingowego.
- **Supersedes:** rozszerza D-118 i D-196 bez zmiany ich zasad bezpieczeństwa.

## D-202 — Import `seq_*` wymaga zweryfikowanej geometrii całej strony

- **Status:** accepted
- **Date:** 2026-08-19
- **Decision:** import poświadczonych zakresów uruchamia przed pipeline'em
  niezmienny preflight rejestracji do ręcznie zweryfikowanych stron-wzorców.
  Do croppera i inferencji dociera wyłącznie kompletna, target-specific siatka
  dziewięciu quadów z niezależnym dowodem czerwonych ramek.
- **Reason:** klasyczny detektor łączył ramki z ręką, strzałką i UI, po czym
  syntetyzował brakujące plansze. Prawidłowy OCR z nazwy pliku nie chronił przed
  cropem przesuniętym o cały rząd, a confidence symboli nie był dowodem geometrii.
- **Safety:** brak dowodu staje się kolejką korekty całej strony; nie jest
  technicznym failure ani wejściem do symboli. Snapshot manifestu, profilu i
  override'ów jest częścią fingerprintu joba. Ręczna korekta jest append-only,
  scoped do `game + source checksum` i nie zmienia zatwierdzonych plansz.
- **Consequences:** historyczny detektor v3 pozostaje odtwarzalny dla legacy
  importów, lecz browserowe `seq_*` nie może do niego wrócić jako fallback.

## D-203 — Rejestracja strony ma deterministyczny fallback budżetu ORB

- **Status:** accepted
- **Date:** 2026-08-19
- **Decision:** profil `verified-page-registration-v1` stosuje kolejno 1000,
  1500 i 3000 cech ORB. Wyższy budżet jest uruchamiany tylko dla tej samej
  strony, która nie przeszła mniejszego budżetu; wszystkie progi RANSAC,
  kompletności 3 × 3 i pokrycia czerwonych ramek pozostają bez zmian.
- **Context:** osiem bardzo czytelnych stron z rzeczywistego stagingu nie
  miało dostatecznej liczby dopasowań przy 1000 cechach. Siedem przeszło przy
  1500, a ostatnia przy 3000, ze spełnionymi rygorystycznymi bramkami.
- **Reason:** jednorodne podniesienie budżetu dla całego stagingu byłoby
  niepotrzebnym kosztem; poluzowanie progów naruszałoby fail-closed geometrii.
- **Safety:** wersja polityki i faktycznie użyty budżet są przypięte do profilu
  i manifestu. Nieudana próba nadal trafia do korekty strony, a nie do croppera
  ani klasyfikatora symboli.
- **Consequences:** nowy preflight jest wymagany przed importem. Zmiana nie
  zmienia kolejności `seq_*`, zatwierdzonych plansz ani historycznych manifestów.

## D-204 — Geometria komórek v19 wynika z wielopunktowej siatki symboli

- **Status:** accepted
- **Date:** 2026-08-20
- **Decision:** lokalizacja dziewięciu plansz na stronie pozostaje pierwszym
  etapem, ale nie jest geometrią finalnych komórek. Kandydat
  `board-cell-geometry-v19-multi-point-source-direct-v1` ma dla każdej planszy
  wyznaczać globalne środki siatki symboli 5 × 3, dopasowywać kanoniczną
  płaszczyznę przez guarded RANSAC i projektować komórki bezpośrednio ze źródła
  w jednym resamplingu. Zachowane zostają co najmniej 10 wiarygodnych punktów,
  9 inlierów, pokrycie wszystkich 3 rzędów i 5 kolumn oraz wersjonowany próg
  residualu. Cztery punkty ręcznej korekty oznaczają zewnętrzne narożniki
  siatki symboli 5 × 3, a nie narożniki czerwonej ramki ani całej planszy.
- **Context:** geometria strony może poprawnie wskazywać dziewięć plansz, lecz
  obecny crop komórek nadal potrafi przesunąć symbole poza wycinek. Wymuszanie
  prostopadłych albo równoległych boków w obrazie źródłowym byłoby błędem:
  perspektywa kamery może dawać trapez lub romb, mimo że płaszczyzna kanoniczna
  jest prostokątna.
- **Safety:** kompletna geometria i jej pochodzenie są warunkiem inferencji;
  confidence symboli nie może ratować geometrii. Historyczny
  `board-cell-crops-v18-source-direct-validated-v1` i jego manifesty pozostają
  odtwarzalne. TASK-0249 nie zmienia na tym etapie modelu ani katalogu symboli.
- **Consequences:** geometria komórek otrzyma osobny, content-addressed manifest,
  niezależny od `PageGeometryManifestV1`. Ręczny edytor i automatyczny estymator
  muszą używać tej samej semantyki punktów i tej samej walidacji przed
  pending-only recropem.
- **Supersedes:** rozszerza D-064–D-067 i D-202; nie zmienia ich zasad
  fail-closed ani source-direct.

## D-205 — Kolejka Reviewera zachowuje kolejność źródłową i first-save-wins

- **Status:** accepted
- **Date:** 2026-08-20
- **Decision:** niezmienna topologia kolejki jednego importu jest wyznaczana
  kluczem `(source_order_index, position_index, review_item_id)`. Sortowanie,
  keyset cursor, wznowienie i nawigacja używają dokładnie tego samego klucza;
  status i `sequence_number` nie mogą zmieniać położenia elementu. Przy
  równoległym zatwierdzaniu pierwsza poprawnie zapisana kanoniczna decyzja dla
  `game_id + sequence_number` wygrywa. Pozostałe oczekujące wystąpienia tego
  numeru stają się `superseded` i nie powodują błędu kursora.
- **Context:** kolejka oparta na numerze sekwencji zmienia się w czasie i przy
  dużym imporcie może odrzucić poprawną decyzję kodem
  `IMAGE_REVIEW_CURSOR_STALE`. Dwie osoby mogą też niezależnie dojść do tego
  samego numeru z różnych źródeł.
- **Safety:** first-save-wins nie nadpisuje ani nie otwiera ponownie decyzji
  `accepted/corrected/rejected`. Kanoniczna projekcja z D-199 zachowuje jednego
  właściciela, a przegrane wystąpienia pozostają audytowalne. Liczniki i
  `queueVersion` muszą pochodzić z trwałej projekcji, nie z klientowej tablicy.
- **Consequences:** migracje 0049–0050 utrwalają topologię, liczniki i
  first-save-wins. Cursor v2 zależy wyłącznie od klucza źródłowego oraz
  `queueVersion`, a resolution zwraca autorytatywny snapshot liczników po
  transakcji. `expectedRevision` dotyczy wyłącznie bieżącego itemu; zmiana
  sąsiada nie jest konfliktem komendy. Reviewer zachowuje UUID przy ponowieniu
  niezmienionej komendy po błędzie transportu.
- **Supersedes:** rozszerza D-093 i D-199, zastępując kolejność sekwencyjną
  niezmienną kolejnością źródłową dla operacyjnego Reviewera.

## D-206 — Wiele importów dzieli jeden proces Reviewera i jeden tunel

- **Status:** accepted
- **Date:** 2026-08-20
- **Decision:** każdy import może mieć najwyżej jedno aktywne przypisanie pracy,
  ale równolegle mogą działać przypisania dla różnych importów, w tym maksymalnie
  trzy udostępnienia online. Wszystkie korzystają z jednego produkcyjnego procesu
  Reviewera i jednego outbound-only Quick Tunnel. Zatrzymanie udostępnienia
  unieważnia wyłącznie wskazaną sesję/przypisanie; wspólny tunel kończy się
  dopiero po wygaśnięciu ostatniego przypisania online.
- **Context:** osobny start tunelu dla każdego linku koliduje o PID, port i
  wspólny plik `remote-reviewer-cloudflared.log`. Zatrzymanie całego ingressu
  wraz z jedną sesją uniemożliwia niezależną pracę dwóch lub trzech osób.
- **Safety:** scope `game_id + import_job_id`, HttpOnly cookie, code gate,
  allowlista same-origin proxy i loopback-only tryb lokalny pozostają bez zmian.
  Lifecycle musi być serializowany między procesami Windows, używać atomowego
  stanu PID/start-time/executable/instance i unikalnych logów startu. Ponowne
  `ensure-running` jest idempotentne.
- **Consequences:** Admin wybiera gotowy import przed utworzeniem lokalnego lub
  online przypisania. Lista sesji nie ujawnia sekretów. Klient Reviewera używa
  ograniczonego bufora `previous/current/next two`, a ograniczenia Quick Tunnel
  pozostają jawne; nie powstaje drugi proces Reviewera ani drugi tunel per link.
- **Supersedes:** rozszerza D-095, D-120 i D-188 oraz zastępuje w D-098 zasadę
  zatrzymywania całego tunelu przy zakończeniu pojedynczej sesji.

## D-207 — Edytor payline nie eksponuje nazwy ani kolejności technicznej

- **Status:** accepted
- **Date:** 2026-08-21
- **Decision:** administrator wskazuje stabilny `code`, aktywność i `row_path`.
  Przy POST Admin zapisuje `name = code` oraz automatyczną kolejność o jeden
  większą od najwyższej istniejącej wartości w tej wersji reguł. PATCH nie
  zmienia ani nazwy, ani kolejności. Tabela identyfikuje wzorzec przez kod i
  nie pokazuje pomocniczych pól.
- **Context:** ręczne pola `name` i `displayOrder` nie przekazują semantyki
  potrzebnej do definicji ani obliczenia payline, a zwiększają liczbę czynności
  podczas konfiguracji reguł.
- **Safety:** `code` pozostaje stabilny i unikalny zgodnie z D-026; `row_path`
  zachowuje wszystkie walidacje wymiarów i unikalności. `displayOrder` nie jest
  unikalny, lecz sort po nim, kodzie i UUID pozostaje deterministyczny. Kolejność
  nie wpływa na wynik payoutu.
- **Consequences:** kontrakt API i schemat bazy pozostają kompatybilne, bez
  migracji. Historyczne wartości nazwy i kolejności są zachowane podczas edycji;
  nowe rekordy otrzymują wartości automatyczne.

## D-208 — Panel używa „planszy”, a staging nie jest jobem Reviewera

- **Status:** accepted
- **Date:** 2026-08-21
- **Decision:** widoczny UI Admina i Reviewera nazywa sekwencyjny układ symboli
  „planszą”. Wewnętrzne nazwy oraz stabilne pola API `layout` pozostają bez
  zmiany. Finalized staging jest tylko poświadczonym źródłem JPEG-ów; nie jest
  import jobem ani elementem dropdownu Reviewera. Dropdown może wskazać
  wyłącznie job tej samej gry w stanie `waiting_for_review` lub `completed`,
  dla którego istnieje kolejka plansz.
- **Context:** gotowy staging `19810 - 45162` był widoczny w Importach, ale nie
  w Zatwierdzaniu plansz. Brak wyjaśnienia sugerował błąd, mimo że uruchomienie
  joba po preflightach było jeszcze świadomie pominięte.
- **Safety:** UI pokazuje gotowy staging i prowadzi do jawnego kroku importu,
  lecz nie uruchamia mutacji ani nie tworzy sesji Reviewera. Zakres gry,
  istniejące uprawnienia, staging manifest i fail-closed geometria pozostają
  niezmienione.
- **Consequences:** brak migracji, zmian OpenAPI lub ponownego uploadu. Termin
  `layout` nadal obowiązuje w kodzie technicznym i danych historycznych.

## D-209 — Nierozpoznana geometria strony jest odroczona, a nie blokująca

- **Status:** accepted
- **Date:** 2026-08-21
- **Decision:** preflight geometrii wykonuje najwyżej dwa automatyczne
  ponowienia z maksymalnie 21 zaostrzonymi auto-kotwicami na przebieg. Ukończony
  manifest może zawierać wpisy `review_required`; import przetwarza wyłącznie
  `registered`, a ręczna korekta wyjątków jest dostępna na końcu.
- **Context:** stagingi `19810–45162` i `70363–93861` miały odpowiednio 54 i
  152 nierozpoznane strony, mimo kompletnej geometrii większości źródeł.
  Wymaganie ręcznej korekty wszystkich wyjątków przed rozpoczęciem importu
  zatrzymywało tysiące poprawnych plansz.
- **Safety:** końcowe progi ORB/RANSAC, dowód czerwonej ramki, kompletność 3 × 3,
  zakaz syntetycznych quadów i ochrona kanonicznych numerów pozostają bez zmian.
  Auto-kotwice mają ostrzejsze progi niż wynik produkcyjny, limit liczby i
  audyt w manifeście. `review_required` nie jest kopiowane, cięte ani
  klasyfikowane.
- **Consequences:** Admin automatycznie odzyskuje lub tworzy preflight po
  pokazaniu raportu i pozwala uruchomić import częściowy. Staging pozostaje
  trwały, więc odroczone strony można ponowić albo poprawić ręcznie później.
- **Supersedes:** zmienia część D-195 wymagającą zera stron review przed startem,
  zachowując jej fail-closed zasady geometrii.

## D-210 — Lokalna ręczna selekcja nie należy do gry

- **Status:** accepted
- **Date:** 2026-08-22
- **Decision:** zakładka `Ręczna selekcja` jest dostępna bez aktywnej gry i
  utrzymuje jedną lokalną sesję pod stabilnym namespace'em narzędzia. Pole
  `gameId` historycznego schematu IndexedDB i manifestu v1 pozostaje technicznie
  obecne dla kompatybilności, ale zawiera identyfikator lokalnego workspace'u,
  a nie UUID gry.
- **Context:** wybór pojedynczych zdjęć oraz zapis `seq_*` korzystają wyłącznie
  z File System Access API. Wymaganie aktywnej gry blokowało niezależny proces,
  mimo że narzędzie nie wywołuje backendu, OCR ani workera.
- **Safety:** przy pierwszym wejściu najnowsza historyczna sesja per gra jest
  niedestrukcyjnie kopiowana razem z własnym trace. Jej `sessionKey`, checksumy,
  uchwyty i własność manifestu pozostają bez zmian, a stary rekord nie jest
  usuwany. Automatyczna selekcja i późniejszy jawny import pozostają odrębne.
- **Consequences:** zmiana nie wymaga migracji PostgreSQL ani OpenAPI. Format
  manifestu v1 pozostaje czytelny dla istniejącego rankera, który grupuje po
  `sessionKey` i zakresie, a przypisanie kohorty do gry następuje osobno.

## D-211 — Niewiarygodna geometria komórek ma trwały stan bez predykcji

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** brak zweryfikowanej geometrii 3 × 5 zapisuje się jako osobny
  rekord `image_board_geometry_pending`, związany z jobem, źródłem i pozycją
  planszy. Rekord może powstać przed `recognized_board` i nie wymaga utworzenia
  15 cropów ani `cells_prediction`. Jego niezmienny
  `BoardCellProcessingManifestV1` przypina poświadczoną sekwencję, rewizje oraz
  wszystkie wersje i fingerprinty przetwarzania.
- **Context:** bez osobnego stanu pełny pipeline musiałby albo zgubić planszę,
  albo utworzyć pozornie kompletną planszę z niewiarygodnymi/pustymi 15
  predykcjami. Oba zachowania łamią fail-closed i utrudniają trwałe wznowienie.
- **Safety:** zamknięte statusy to `pending`, `resolved`, `superseded`, a powody
  v1 to `insufficient_centers`, `incomplete_lattice`, `residual_too_high` i
  `source_unavailable`. Exact retry jest idempotentny. Rozwiązanie ponownie
  sprawdza planszę oraz review pod blokadą; późniejsza decyzja człowieka zawsze
  wygrywa i kończy automat jako `superseded`.
- **Consequences:** API TASK-0264 jest tylko do odczytu. Produkcyjne tworzenie
  rekordów należy do osobnego adaptera, nie przełącza v19 i nie zmienia
  historycznego v18. Tabela przechowuje ścieżki i checksumy, nigdy obrazy BLOB.
- **Supersedes:** rozszerza D-204 i D-209 o trwały fallback na poziomie
  pojedynczej planszy; nie osłabia ich bramek geometrii.

## D-212 — Pełny adapter v20 jest jawny i nie zmienia domyślnego v18

- **Status:** accepted
- **Date:** 2026-08-23
- **Decision:** `board-cell-processing-v20-verified-v19-v1` może działać w
  pełnym imporcie wyłącznie po jawnym przypięciu
  `boardCellProcessingMode=verified_v19`. Brak pola oznacza historyczny v18.
  W obrębie v20 plansza daje dokładnie 15 zweryfikowanych cropów v19 albo
  trwały deferred bez cropów i inferencji; fallback do v18 jest zabroniony.
- **Context:** cross-staging benchmark potwierdził jakość trafień, lecz osiągnął
  `93,78%` pokrycia przy bramce `98%`. Właściciel jawnie zlecił TASK 4 mimo tej
  bramki, aby zintegrować bezpieczny opt-in bez aktywacji domyślnej.
- **Safety:** snapshot i fingerprint rozdzielają execution v18/v20. Trwały
  pre-crop stage oraz replay po restarcie zapisują job-local deferrals
  idempotentnie. Równoległa decyzja człowieka nadal wygrywa. Historyczne
  checkpointy i manifest v18 nie są modyfikowane.
- **Consequences:** API pozwala jawnie uruchomić v20 i jawnie wrócić do v18.
  Zmiana domyślnego trybu pozostaje zablokowana do osobnego checkpointu z
  pokryciem co najmniej `98%`. TASK 5 dostarczył później wyłącznie ręczne
  rozwiązanie trwałych wyjątków.

## D-213 — Ręczny deferred materializuje istniejącą kolejkę review

- **Status:** accepted
- **Date:** 2026-08-23
- **Decision:** ręczna korekta jednego `image_board_geometry_pending` nie
  tworzy osobnej domeny review. Po uzyskaniu dokładnie 15 source-direct cropów
  v19 i predykcji modelu przypiętego do importu atomowo materializuje zwykły
  `recognized_board`, obserwacje, rewizję geometrii i `image_review_item`.
- **Context:** deferred powstaje przed planszą, więc istniejący edytor rewizji
  nie miał obiektu docelowego. Kopiowanie logiki kolejki albo inferencja przez
  bieżący model gry naruszałyby kolejność sekwencji i odtwarzalność importu.
- **Safety:** komenda jest związana z manifestem, źródłem, modelem i obiema
  rewizjami. Exact retry jest sprawdzany przed kosztowną pracą i pod blokadą;
  istniejąca plansza zawsze wygrywa jako `superseded`. Preview niczego nie
  zapisuje, a błędna geometria/model nie tworzą częściowej projekcji w bazie.
- **Consequences:** nowy item trafia przez istniejący trigger do tej samej
  uporządkowanej kolejki. API jest scope-bound dla Reviewera i lokalnego
  administratora. UI fallbacku, rollout v20, trening i backfill pozostają
  osobnymi zadaniami.

## D-214 — Rollout geometrii v19 kończy się kontrolowanym opt-in v20

- **Status:** accepted
- **Date:** 2026-08-23
- **Decision:** `historical_v18` pozostaje domyślnym trybem importu.
  `board-cell-processing-v20-verified-v19-v1` może zostać wybrany wyłącznie
  jawnie dla konkretnego stagingu i każdą pozycję kończy dokładnie 15 cropami
  v19 albo trwałym deferred bez inferencji. Nie ma fallbacku v19 → v18.
- **Context:** benchmark 300 stron i 2700 plansz potwierdził jakość trafień, ale
  osiągnął `93,78%` pokrycia przy wymaganym minimum `98%`. Właściciel jawnie
  dopuścił integrację i użycie bezpiecznego opt-in mimo odrzuconej aktywacji
  domyślnej.
- **Safety:** bramka `98%` nie zostaje obniżona. Snapshoty i fingerprinty
  rozdzielają v18/v20; istniejącego joba nie wolno przełączać w locie. Deferred
  jest rozwiązywany przez ten sam source-direct cropper v19 i model przypięty
  do źródłowego joba, a decyzja człowieka zawsze wygrywa.
- **Consequences:** rollback polega na utworzeniu kolejnego joba z
  `historical_v18`, bez mutowania historycznych wyników. Domyślny rollout v20
  wymaga nowego benchmarku osiągającego co najmniej `98%` i osobnej decyzji.
- **Supersedes:** domyka D-211–D-213; nie zmienia ich invariantów ani
  historycznego v18.

## D-215 — Kandydat modelu symboli v19 pozostaje odrzucony

- **Status:** accepted
- **Date:** 2026-08-23
- **Decision:** kandydat `spatial-symbol-cnn-v1` wytrenowany na zamrożonej
  kohorcie v19 otrzymuje końcowy status `rejected` i nie może zostać aktywowany.
  Aktywny fingerprint pozostaje równy
  `19e15e92591a3e1692a329e7c2fc9f4f3fe0f102bf623bebc20184615e48db64`.
- **Context:** kandydat poprawił whole-board accuracy o `5,8824 pp`, przeszedł
  ONNX parity i nie miał regresji recall powyżej `1 pp`, ale audyt 100 plansz
  wykrył jeden błąd `lemon → orange` z confidence `0,99999698`. Bramka wymaga
  zera błędów o confidence co najmniej `0,99`.
- **Safety:** próg nie jest osłabiany po zobaczeniu wyniku. Odrzucone artefakty
  i raport pozostają content-addressed oraz audytowalne; nie powstaje zdarzenie
  aktywacji i żaden trwający ani nowy import nie użyje kandydata.
- **Consequences:** kolejna iteracja wymaga osobnego jawnego zadania, nowej
  niezmiennej kohorty i ponownego przejścia pełnej bramki. Odrzucenie jakościowe
  nie jest klasyfikowane jako techniczny `failed`.
- **Supersedes:** domyka wynik D-159 bez zmiany D-160 i monotonicznego rejestru
  aktywacji.

## D-216 — Zdalna selekcja rozdziela rewizję partii od generacji pliku

- **Status:** accepted
- **Date:** 2026-08-23
- **Decision:** zdalna ręczna selekcja używa monotonicznego `serverRevision`
  dla kolejności operacji partii oraz niezależnego `selectionGeneration` dla
  żądanego stanu konkretnego pliku. Exact retry identyfikuje niezmienną
  operację przez `operationId + canonical command checksum`; starsza generacja
  kończy się `superseded` bez zmiany desired state ani rewizji.
- **Context:** zdalny klient może ponawiać, buforować i wysyłać operacje po
  zmianie połączenia. Jedna rewizja nie rozstrzyga jednocześnie kolejności
  dziennika i aktualności transferu lub usunięcia konkretnego pliku.
- **Safety:** obcy scope, luka/regresja `clientSequence`, konflikt rewizji,
  nieznany typ operacji i ponowne użycie `operationId` z inną treścią są
  odrzucane fail-closed. Każda maszyna stanów ma zamkniętą macierz przejść.
- **Consequences:** ORM i endpointy w kolejnych zadaniach muszą zachować te
  kontrakty. Istniejące output/trace v1 pozostają bez zmian; nie dodano jeszcze
  tabel, route, filesystemu ani transportu.
- **Alternatives:** jeden wspólny licznik dla partii i plików odrzucono, bo
  powodowałby fałszywe konflikty przy równoległym uploadzie i deselect.

## D-217 — Trwałość zdalnej selekcji jest scope-bound i append-only

- **Status:** accepted
- **Date:** 2026-08-23
- **Decision:** stan zdalnej ręcznej selekcji jest utrwalany w ośmiu
  addytywnych tabelach. Composite FK wiążą rekordy z jednym
  `session + batch + file` scope, globalne mapowanie
  `base binding + collection + batch` jest unikalne, a operacje i audyt są
  append-only także dla bezpośrednich poleceń SQL.
- **Context:** retry, dwóch klientów i dwie sesje mogą równolegle dotknąć tej
  samej logicznej partii. Spójność nie może zależeć wyłącznie od późniejszej
  warstwy HTTP ani od pojedynczego procesu API.
- **Safety:** aplikacja blokuje wiersz partii i pliku przed zastosowaniem
  operacji, tworzenie mapowania serializuje advisory lockiem, a constrainty
  pozostają ostateczną ochroną. Publiczne mappery nie zwracają ścieżek hosta,
  ścieżek tymczasowych, salt/hash ani lease tokenów. Obrazy pozostają poza
  bazą.
- **Consequences:** filesystem picker i path containment powstaną dopiero w
  TASK 5, a auth/writer lease service w TASK 6. Migracji nie należy cofać na
  produkcyjnych danych bez eksportu, audytu i jawnej decyzji.
- **Alternatives:** walidację tylko w repozytorium odrzucono, ponieważ nie
  zabezpiecza innych procesów ani bezpośrednich zapisów do bazy.

## D-218 — Host filesystem wymaga final-handle containment i własności

- **Status:** accepted
- **Date:** 2026-08-23
- **Decision:** zdalnie inicjowane mapowanie katalogu nie przyjmuje ścieżki.
  Host wybiera bazę stałym pickerem i przekazuje tylko jednorazową opaque
  capability. Collection i batch są dwoma walidowanymi komponentami, a zapis
  wymaga final-handle containment, braku reparse w łańcuchu oraz zgodnego,
  checksumowanego ownership markera.
- **Context:** tekstowe `resolve()` nie chroni przed junctionem podstawionym po
  walidacji, case/Unicode collision ani wznowieniem w obcym folderze.
- **Safety:** adapter trzyma uchwyty bazy, collection i batch bez
  `FILE_SHARE_DELETE`, ponownie sprawdza final path, nie wykonuje suffix ani
  overwrite i tworzy marker atomowym rename bez zastępowania celu. Marker bez
  zgodnego scope/DB blokuje operację; crash po markerze, ale przed commitem DB,
  można odzyskać tylko z tymi samymi identyfikatorami.
- **Consequences:** TASK 6 może zużyć capability przy lokalnym tworzeniu sesji,
  ale publiczny klient nigdy nie otrzyma ścieżki. Materializacja i usuwanie w
  późniejszych zadaniach muszą zachować ten sam guard oraz własność plików.
- **Rollback:** ustawienie
  `GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED=false` usuwa lokalny
  endpoint z runtime OpenAPI bez mutowania istniejących danych.
- **Alternatives:** `Path.resolve()` i walidację samych stringów odrzucono jako
  podatne na TOCTOU; automatyczny suffix i nadpisywanie odrzucono jako
  nieaudytowalne.

## D-219 — Zdalna selekcja ma osobne credentials i host-only writer fencing

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** sesja zdalnej ręcznej selekcji nie korzysta z
  `reviewer_access_sessions` ani scope `game/import`. Używa wspólnych primitives
  PBKDF2/token hash, ale własnej tabeli, kodu, rotowanego tokenu i
  45-sekundowego writer lease. Bearer trafia wyłącznie do ciasteczka
  `HttpOnly/Secure/SameSite=Strict` o ścieżce `/selection-api`, a fencing token
  lease pozostaje host-only.
- **Context:** reuse istniejącej sesji Reviewera rozszerzyłby dostęp do danych
  gry/importu. Przekazywanie bearer lub fencing tokenu w JSON/URL zwiększałoby
  ryzyko wycieku i pozwalało klientowi fałszować własność lease.
- **Safety:** kod jest ujawniany tylko przy create, pięć błędnych prób trwale
  blokuje sesję, unlock rotuje token, revoke usuwa token i lease. Aktywny lease
  innego `clientInstanceId` pozostaje read-only; takeover jest dozwolony dopiero
  po expiry i dostaje nowy host-only fencing token. Audyt nie zawiera sekretów
  ani ścieżki.
- **Consequences:** TASK 7 może wystawić cookie wyłącznie przez osobną
  allowlistę `/selection-api`. Operacje TASK 9 muszą sprawdzać zarówno session
  token, jak i aktualne writer ownership bez przyjmowania fencing tokenu od
  przeglądarki.
- **Rollback:** wyłączyć
  `GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED`; route znikają, a
  hash-only dane i audyt pozostają do kontrolowanego revoke/retencji.
- **Alternatives:** reuse bearer Reviewera, token w JSON/localStorage oraz
  client-provided lease token odrzucono jako rozszerzające lub osłabiające
  granicę bezpieczeństwa.

## D-220 — Zdalna selekcja współdzieli ingress, ale nie powierzchnię uprawnień

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** jeden produkcyjny Reviewer i jeden Quick Tunnel obsługują legacy
  review oraz zdalną ręczną selekcję. Selekcja ma osobny shell
  `/manual-selection`, proxy `/selection-api`, cookie i zamkniętą allowlistę.
  Publiczny URL sesji jest dynamiczną projekcją bieżącego originu tunelu.
- **Context:** drugi proces lub tunel zwiększałby ryzyko konfliktów portu, plików
  runtime i lifecycle. Reuse legacy cookie/allowlisty rozszerzyłby z kolei scope
  na grę, import i operacje zatwierdzania plansz.
- **Safety:** proxy tłumaczy purpose-scoped HttpOnly cookie, wymaga stałej
  intencji backendu i same-origin mutacji, filtruje nagłówki, ogranicza request
  i response do 128 KiB oraz łączy się tylko z loopback API. Revoke nie zależy
  od dostępności ani zatrzymania wspólnego ingressu.
- **Consequences:** restart Quick Tunnel zmienia URL, ale nie session ID. TASK 8
  rozszerzy tylko allowlistę nowego scope o read-only źródło i workspace;
  nie może użyć `/review-api` ani publicznego CORS FastAPI.
- **Rollback:** flaga
  `GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED=false` usuwa shell,
  proxy i backend route po restarcie, bez kasowania sesji i audytu. Legacy
  Reviewer pozostaje aktywny.
- **Alternatives:** drugi Reviewer/tunnel oraz wspólne credentials lub route
  proxy odrzucono jako bardziej awaryjne albo zbyt szerokie.

## D-221 — Zdalna mutacja wymaga trwałego lokalnego outboxu

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** każda zdalna operacja wpływająca na finalny JPEG musi zostać
  zapisana w osobnym, wersjonowanym IndexedDB outboxie przed próbą wysłania.
  Lokalna operacja jest `pending`, dopóki host jawnie nie potwierdzi jej
  dokładnego `operationId`; `beforeunload` nie jest mechanizmem poprawności.
- **Context:** refresh, crash, utrata sieci lub permission mogą nastąpić między
  decyzją operatora a odpowiedzią hosta. Stan wyłącznie w React albo pamięci
  procesu zgubiłby pracę lub zacierał różnicę między intencją i skutkiem.
- **Safety:** exact retry wymaga tego samego `operationId + checksum`,
  `clientSequence` jest monotoniczny, ack usuwa wyłącznie jawnie wymienione ID,
  a utrata uchwytu nie usuwa kursora ani outboxu. IndexedDB nie przechowuje
  Blobów JPEG ani ścieżek absolutnych.
- **Consequences:** TASK 9 może wysyłać i uzgadniać wyłącznie operacje wcześniej
  zapisane w outboxie. TASK 8 nie implementuje jeszcze transportu ani nie
  deklaruje synchronizacji bez host ack.
- **Alternatives:** request przed zapisem, pamięć React, localStorage i
  `beforeunload` odrzucono jako nietrwałe lub niewystarczające dla crash replay.

## D-222 — Idempotencja control plane jest związana z encją i trwałym outcome

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** UUID kolekcji, partii, pliku i operacji są kluczami
  idempotencji odpowiednich mutacji. Dokładny retry `operationId + checksum`
  zwraca wcześniej zapisany outcome bez zwiększenia rewizji, również po utracie
  writer lease. Każda nowa mutacja nadal wymaga aktywnego lease sprawdzonego w
  tej samej transakcji co zapis domenowy.
- **Context:** odpowiedź hosta może zginąć po trwałym commicie. Wymaganie nowego
  lease do samego odczytu outcome zablokowałoby bezpieczny replay, natomiast
  ponowne zastosowanie komendy mogłoby zdublować decyzję albo cofnąć generację.
- **Safety:** zgodność pełnego checksumy komendy, session/batch/client scope,
  `clientSequence`, `expectedServerRevision` i `selectionGeneration` jest
  egzekwowana fail-closed. Konflikt nie jest automatycznie rebase'owany ani
  rozstrzygany last-write-wins; pozostaje w outboxie do jawnego uzgodnienia.
- **Consequences:** source manifest aktywuje się dopiero po kompletnej walidacji
  i staje się immutable. State delta jest stronicowane i monotoniczne. TASK 10
  musi użyć tej samej tożsamości/generacji, ale nie może rozszerzyć control route
  o binarny body.
- **Alternatives:** losowy `Idempotency-Key` niezwiązany z encją, retry jako nowa
  operacja i automatyczne last-write-wins odrzucono jako tworzące drugi porządek
  lub ryzyko utraty decyzji.

## D-223 — Transfer i materializacja mają osobne kolejki oraz fault-injection gate

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** browser control outbox, kolejka transferów i host action queue są
  odrębnymi mechanizmami ze wspólną tożsamością pliku i generacji. Każdy workflow
  łączący bazę z filesystemem musi przejść fault injection wszystkich trwałych
  granic oraz idempotentne reconciliation przed uznaniem go za ukończony.
- **Context:** jedna kolejka blokowałaby nawigację transferem i mieszała intencję,
  przesłanie bajtów oraz lokalny skutek. PostgreSQL i NTFS nie tworzą jednej
  transakcji ACID, więc happy path nie dowodzi braku false success, overwrite ani
  podwójnej materializacji po crashu.
- **Safety:** host action używa lease i fencing tokenu, `SKIP LOCKED`, bounded
  retry/backoff, generation recheck, own marker, same-volume temp, fsync,
  checksumowany journal i wyłączną publikację finalnej nazwy. Reconciliation
  może adoptować wyłącznie zgodny własny półstan; obcy lub zmieniony target jest
  konfliktem.
- **Retry clarification (v0.7.43):** nowa próba ma osobny transfer ID i nie
  zmienia historii poprzedniej próby. Dopiero gdy nowa próba tego samego pliku i
  generacji osiągnie `verified`, starsze próby `failed` przechodzą do
  `cancelled`. Nieodzyskany bieżący `failed` nadal blokuje finalizację.
- **Consequences:** zasady R-003 i R-005 z planu zdalnej selekcji są przyjęte.
  TASK 12 i TASK 15 muszą używać tej samej kolejki/fault gate dla usuwania oraz
  finalizacji. Mały synchroniczny zapis lokalnego narzędzia może pozostać, jeśli
  nie przekracza tej granicy browser-to-host.
- **Rollback:** zatrzymać general executor; verified temp, akcje DB, journal i
  opublikowane own pliki pozostają do bezpiecznego wznowienia. Rollback nie
  usuwa ani nie nadpisuje finalnych plików.
- **Alternatives:** wspólna kolejka, bezpośredni zapis w requestcie oraz uznanie
  DB za synced przed weryfikacją finalnego pliku odrzucono jako blokujące lub
  podatne na crash windows.

## D-224 — Zdalne odznaczenie używa generacyjnego tombstone'u i odwracalnej kwarantanny

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** `deselect` i `undo` wskazują wcześniejszy zastosowany `select` i
  tworzą nową generację desired state. W tej samej transakcji starsze transfery
  są anulowane, akcje materializacji supersedowane, a dla istniejącego własnego
  wyniku powstaje priorytetowa akcja `remove`. Plik nie jest kasowany: po
  zgodności materialization journalu i checksummy zostaje przeniesiony
  przypiętym uchwytem do host-internal, checksumowanej kwarantanny.
- **Context:** upload, control outbox i host action są asynchroniczne. Bez
  generacyjnego fence spóźniona materializacja mogłaby wskrzesić odznaczony plik,
  a bez journalu crash między NTFS i PostgreSQL mógłby dać false success lub
  próbę usunięcia obcego celu.
- **Safety:** akcja `remove` ma pierwszeństwo przed nową materializacją, używa
  lease/fencing, bounded retry oraz ponownego sprawdzenia generacji. Rename jest
  dozwolony wyłącznie dla własnego, regularnego i nadal checksumowo zgodnego
  pliku. Foreign/changed/reparse target pozostaje nietknięty. Exact retry nie
  zwiększa rewizji ani generacji.
- **Consequences:** kwarantanna pozostaje odwracalna i nie ma finalnego GC do
  czasu rozstrzygnięcia `OPEN-5`. Osobna flaga rollbacku może zablokować nowe
  `deselect`/`undo`, zachowując trwałe operacje, journale i artefakty do
  bezpiecznego wznowienia. TASK 13 może budować UI na tym stanie, ale nie zmienia
  protokołu usuwania.
- **Alternatives:** bezpośrednie `unlink`, usuwanie po samej nazwie, traktowanie
  cancel uploadu jako wystarczające oraz last-write-wins bez generacji odrzucono
  jako nieodwracalne albo podatne na TOCTOU i stale resurrection.

## D-225 — Zdalny workspace zapisuje decyzję i outbox atomowo, a podgląd pozostaje lokalny

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** stan zakresu, decyzja operatora i odpowiadająca jej operacja
  outboxu są jednym zapisem IndexedDB przed zmianą widoku. Podgląd ma ograniczone
  okno lokalnych Object URL-i; sync control plane i transfer JPEG-a są osobnymi
  procesami w tle. UI rozróżnia local, pending, confirmed, synced i error.
- **Context:** zapis decyzji i outboxu w dwóch transakcjach tworzyłby crash window,
  w którym widok przeszedł dalej bez operacji możliwej do odtworzenia. Trzymanie
  JPEG-ów albo wszystkich podglądów w React/IndexedDB łamałoby local-first i
  bounded-memory przy 8–15 tysiącach zdjęć.
- **Safety:** Blob i absolutna ścieżka są zakazane w stanie trwałym i kontrakcie.
  Operacja nie czeka na sieć lub upload; potwierdzenie control plane nie jest
  nazywane synchronizacją pliku. Konflikt blokuje kolejne mutacje zamiast
  automatycznego rebase, a relink wymaga identycznego manifestu.
- **Consequences:** lokalny i zdalny ekran współdzielą semantykę skrótów, ale
  zachowują osobne adaptery trwałości. Refresh może wznowić kursor, outbox i
  transfer checkpoint bez przechowywania bajtów obrazu. TASK 14 może budować
  monitor hosta na tych stanach, lecz nie może scalać ich w jeden status.
- **Alternatives:** optymistyczna zmiana widoku przed zapisem, Blob cache w IDB,
  blokowanie interakcji do końca uploadu i etykieta „zapisano” po samym SELECT
  zostały odrzucone jako podatne na utratę, nieograniczoną pamięć lub false
  success.

## D-226 — Finalizacja zdalnej partii jest rewizyjną barierą hosta

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** zdalna partia przechodzi do `completed` dopiero po
  serwerowym preview i transakcyjnym potwierdzeniu braku aktywnych operacji,
  transferów i host actions oraz zgodności wszystkich wybranych plików.
  Manifesty output/trace zachowują lokalny schemat v1; stan operacyjny jest
  osobnym host-internal manifestem. Reopen jest wyłącznie lokalną operacją
  właściciela z exact targetem, rewizją i checksumą.
- **Context:** sam pusty outbox przeglądarki nie dowodzi, że JPEG został
  materializowany, a crash między zapisem JSON i commitem bazy mógłby stworzyć
  fałszywy sukces albo drugi wynik przy retry.
- **Safety:** rewizyjny journal i ownership pointer pozwalają adoptować tylko
  identyczny półstan. Obcy lub zmieniony manifest nigdy nie jest nadpisywany.
  Publiczna allowlista nie zawiera reopen ani endpointu zapisu manifestu.
- **Consequences:** zakończony Reviewer jest tylko do odczytu; import lokalny
  konsumuje wynik bez nowej gałęzi kontraktu. Ponowne otwarcie zwiększa rewizję
  i wymaga kolejnej jawnej finalizacji po zmianach.
- **Alternatives:** finalizacja na podstawie stanu React/IndexedDB, bezpośredni
  upload manifestów przez operatora i automatyczny reopen odrzucono jako
  podatne na rozjazd DB–filesystem, podmianę artefaktu lub stale mutation.

## D-227 — Wynik zdalnej ręcznej selekcji pozostaje na urządzeniu operatora

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** link, kod, cookie i writer lease służą wyłącznie do odblokowania
  strony Reviewera. Operator wybiera lokalne źródło i katalog nadrzędny, a
  Reviewer tworzy `<źródło> wybrane` i zapisuje w nim oryginalne JPEG-i `seq_*`
  oraz manifest. Decyzje, kursor i uchwyty pozostają w IndexedDB operatora;
  zoom i obie osie scrolla w jego localStorage. Nowy workspace nie rejestruje
  partii na hoście, nie wysyła operacji i nie uruchamia transferu ani host
  finalization.
- **Context:** rzeczywiste próby v0.7.47–v0.7.50 wielokrotnie wykazały rozjazd
  szybkich decyzji, zegara klienta i transferu. Właściciel jawnie wybrał zapis u
  użytkownika końcowego jako prostszy i bezpośrednio weryfikowalny model.
  Osobno wykryto, że Reviewer używał klas lokalnego selektora bez odpowiadających
  im bazowych stylów, więc zoom zmieniał etykietę bez prawidłowego viewportu.
- **Safety:** plik powstaje przed lokalnym commitem decyzji i jest weryfikowany
  SHA-256. Idempotentny zapis przyjmuje identyczną zawartość, a konflikt nie
  nadpisuje ani nie usuwa obcego pliku. Cofnięcie usuwa wyłącznie plik o zgodnej
  nazwie i checksumie. Interakcje są szeregowane, a brak trwałego File System
  Access API blokuje zapis jawnie.
- **Consequences:** host zachowuje tylko access session i audyt; techniczny
  binding pod artifact root nie jest wynikiem operatora. Operator musi wskazać
  katalog nadrzędny osobnym pickerem, ponieważ przeglądarka nie ujawnia rodzica
  źródłowego uchwytu. Historyczne tabele, endpointy, outbox, transfer i
  materializacja pozostają odtwarzalne, ale nie są wywoływane przez nowy ekran.
- **Supersedes:** D-221 i D-225 dla obowiązującego workspace'u; D-223, D-224 i
  D-226 pozostają historycznymi zasadami nieaktywnego wariantu host-transfer.
- **Alternatives:** dalsze naprawianie synchronizacji do hosta, upload całego
  stagingu i zapis Blobów w IndexedDB odrzucono jako bardziej złożone, wolniejsze
  albo niebezpieczne dla pamięci i trwałości.

## D-228 — Manifest operatora jest źródłem wznowienia folderu wynikowego

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** folder `<źródło> wybrane` może rozpocząć pracę tylko jako pusty
  albo jako kompletny wynik operator-local. W drugim przypadku
  `manual-image-selection-output-v1.json` przechowuje tożsamość źródła, liczbę
  zdjęć, kierunek, kursor, następny zakres i decyzje. Czasowa access session nie
  jest właścicielem wyniku; po nowym linku decyzje są wiązane ze świeżymi
  identyfikatorami IndexedDB według ordinalu i względnej ścieżki.
- **Context:** wcześniejszy Reviewer bezwarunkowo otwierał lub tworzył folder
  wynikowy. Nie potrafił odróżnić pustego katalogu od obcych danych ani użyć
  manifestu do wznowienia po utracie originu poprzedniego Quick Tunnel.
- **Safety:** niepusty folder bez poprawnego manifestu, dodatkowy plik,
  brakujący `seq_*`, niezgodna nazwa, liczba zdjęć lub checksum źródła blokują
  start. Zapis i cofnięcie nadal weryfikują checksumę konkretnego JPEG-a.
- **Consequences:** ponowne wskazanie zgodnego źródła i katalogu nadrzędnego
  wystarcza do odtworzenia zdjęcia oraz następnego zakresu, także pod nowym
  linkiem. Rozszerzenie manifestu v1 jest kompatybilne z istniejącą nazwą pliku.
- **Alternatives:** wyłączne poleganie na IndexedDB originu, bezwarunkowe
  czyszczenie folderu i zezwolenie na mieszanie obcych plików odrzucono jako
  podatne na utratę postępu albo nadpisanie danych.

## D-229 — Niedostępny katalog wymaga ponownego podpięcia obu stron workspace'u

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** brak źródłowego JPEG-a albo usunięty folder wynikowy zeruje
  lokalne decyzje, kursor i następny zakres, odłącza wszystkie uchwyty katalogów
  oraz wymaga ponownego wskazania źródła i katalogu nadrzędnego wyniku. Indeks i
  checksum manifestu źródła pozostają wyłącznie do fail-closed walidacji
  ponownie wybranego folderu. Nowy pusty manifest jest zapisywany dopiero przy
  jawnym rozpoczęciu selekcji.
- **Context:** starsze sesje nie zawsze miały utrwalony uchwyt katalogu
  nadrzędnego. Po zewnętrznym usunięciu folderu wynikowego przeglądarka zwracała
  `NotFoundError`, a aplikacja pozostawała przy martwym uchwycie i nie mogła
  wykonać restartu.
- **Safety:** recovery reaguje wyłącznie na niedostępny uchwyt albo stabilny
  błąd brakującego pliku źródłowego. Konflikt checksumy, obcy plik i niezgodny
  manifest nadal blokują operację bez resetowania dowodów.
- **Consequences:** operator rozpoczyna od pierwszego zdjęcia i ponownie nadaje
  oba uprawnienia; aplikacja nie próbuje niejawnie odtworzyć usuniętego folderu
  na podstawie nieaktualnego uchwytu.
- **Supersedes:** automatyczne odtwarzanie brakującego potomnego folderu opisane
  pierwotnie przy D-228; pozostałe invarianty D-227 i D-228 obowiązują.
- **Alternatives:** automatyczna rekonstrukcja wyłącznie z opcjonalnego uchwytu
  rodzica została odrzucona, ponieważ nie działa dla starszych sesji i nie
  naprawia równoczesnej utraty dostępu do źródła.

## D-230 — Aktywna iteracja symboli pozostaje najnowszym kandydatem gotowym do użycia

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision:** aktywna dla gry `777` pozostaje iteracja symboli `#3`
  `47b6aa0d-2cea-4765-97f0-ee1f86cfc056`, aktywowana 2026-08-19 po statusie
  `candidate_ready`. Nowe importy i przeliczenia przypinają jej snapshot; nie
  tworzymy ponownego zdarzenia aktywacji dla identycznego modelu.
- **Context:** opis historycznego kandydata v19 odrzuconego po błędzie
  `lemon → orange` był mylony z późniejszą iteracją #3. Odczyt rejestru modelu
  potwierdził, że #3 jest już aktywna, a API zwraca
  `SYMBOL_MODEL_ALREADY_ACTIVE` dla drugiej próby.
- **Safety:** odrzucony kandydat pozostaje audytowalny i nie może wrócić do
  produkcji. Aktywacja kolejnej iteracji nadal wymaga `candidate_ready`,
  aktualnego manifestu, oczekiwanego aktywnego modelu i jawnej komendy
  idempotentnej.
- **Consequences:** nie uruchamiamy treningu ani migracji tylko po to, aby
  ponownie aktywować model już aktywny. Dokumentacja rozróżnia historyczny
  wynik od bieżącego snapshotu.
- **Supersedes:** doprecyzowuje zakres historycznej D-215; nie zmienia jej
  decyzji o odrzuceniu konkretnego wcześniejszego kandydata.
- **Alternatives:** wymuszenie nowej aktywacji lub ręczna zmiana wskaźnika w
  bazie zostały odrzucone jako zbędne i mniej audytowalne.

## D-231 — v20 z geometrią i cropami v19 jest domyślnym silnikiem nowych importów

- **Status:** accepted
- **Date:** 2026-08-25
- **Decision:** do czasu jawnego odwołania właściciela każdy nowy staging oraz
  ponowne przetworzenie importu przypina
  `board-cell-processing-v20-verified-v19-v1`. API przy braku
  `boardCellProcessingMode` także wybiera `verified_v19`; Admin nie pokazuje
  wyboru ani potwierdzenia v18.
- **Context:** właściciel potwierdził, że kolejne runy mają zawsze używać v19,
  a aktywny v18 ma być anulowany i odtworzony jako nowy job. Poprzednia polityka
  opt-in pozostawiała v18 jako niezamierzoną wartość domyślną.
- **Safety:** istniejącego joba nie przełączamy w locie. Snapshot i fingerprint
  nadal rozdzielają v18 oraz v20/v19; brak kompletnej geometrii pozostaje
  `deferred`, bez fallbacku v19 → v18 i bez inferencji symboli. Decyzja
  człowieka nadal wygrywa.
- **Consequences:** v18 pozostaje czytelny i odtwarzalny wyłącznie dla historii;
  rollback wymaga świadomego utworzenia historycznego joba poza codziennym
  workflow. Nowe i odtworzone joby pokazują `rolloutMode=default_v19`.
- **Supersedes:** zastępuje w D-212 i D-214 wyłącznie zasadę opt-in oraz
  domyślny v18; pozostałe invarianty bezpieczeństwa pozostają bez zmian.

## D-232 — Kod zdalnej ręcznej selekcji jest trwały tylko lokalnie u właściciela

- **Status:** accepted
- **Date:** 2026-08-25
- **Decision:** panel `Zdalna ręczna selekcja` utrzymuje surowy kod zwrócony
  przez create wyłącznie w `localStorage` profilu lokalnego Admina. Wyświetla
  go przy wybranej aktywnej sesji wraz z linkiem i przyciskami kopiowania do
  `expiresAt` albo revoke.
- **Context:** jednorazowa karta kodu znikała po odświeżeniu, choć właściciel
  potrzebuje ponownie skopiować oba dane w krótkim czasie życia sesji.
- **Safety:** API, PostgreSQL, odpowiedzi listujące i logi nadal zachowują
  wyłącznie hash kodu; link nie zawiera kodu. Cache jest usuwany przy revoke,
  odrzuca wartości wygasłe lub uszkodzone i nie jest dostępny na innym
  komputerze/profilu Admina.
- **Consequences:** istniejącej sesji utworzonej przed tą zmianą nie można
  odzyskać kodu z serwera. Użytkownik widzi wtedy jasny stan niedostępności
  zamiast tworzenia równoległego mechanizmu odzyskania sekretu.
- **Alternatives:** zapis surowego kodu w bazie lub dodanie endpointu jego
  odczytu odrzucono, ponieważ poszerzałoby powierzchnię sekretów serwera bez
  potrzeby dla tego krótkotrwałego workflow.

## D-233 — Wyszukiwanie plansz korzysta z jednej projekcji logicznej na sekwencję

- **Status:** accepted
- **Date:** 2026-08-25
- **Decision:** częściowy wzór 3 × 5 jest oceniany na trwałej projekcji
  `game_id + sequence_number`, a nie przez pełny join `recognized_boards`,
  `cell_observations` i rewizji dla każdego requestu. Właściciel dokumentu jest
  kanoniczną planszą `accepted/corrected`; gdy jej nie ma, jest nim
  deterministycznie wybrana pozycja `pending`. Projekcja przechowuje wyłącznie
  kody, statusy, identyfikatory, checksumy i metadane assetu, bez obrazów BLOB.
- **Context:** obecny zbiór ma setki tysięcy plansz i miliony obserwacji.
  Bez materializacji read path nie ma przewidywalnego czasu odpowiedzi, a
  ponowione importy mogłyby wyświetlać wiele kart dla jednego numeru.
- **Safety:** accepted/corrected wykorzystuje wyłącznie ręcznie rozwiązany
  symbol. Dla `pending` wynik dokładny ma wagę 1, a alternatywy mają słabsze,
  wersjonowane wagi. Przyszły `?` oznacza brak dowodu: nie daje punktu i nie
  jest karą. Wynik jest ograniczony do 100 rekordów i po brakującym assetcie
  pokazuje kontrolowany fallback.
- **Consequences:** synchronizacja projekcji należy do ścieżek importu,
  inferencji i decyzji review. Trwałe blokowanie kolejnych pozycji `pending`
  dla tego samego numeru jest nadal osobnym TASK-0291, a nie ukrytą zmianą
  semantyki rankingu.
- **Alternatives:** wyszukiwanie identycznego łańcucha ignoruje niepewność;
  runtime join i skan całej tabeli na żądanie nie daje akceptowalnej wydajności;
  przechowywanie binarnych cropów w projekcji narusza model danych.

## D-234 — Katalog i grafika symbolu wymagają jawnej decyzji człowieka

- **Status:** accepted
- **Date:** 2026-08-26
- **Decision:** katalog symboli nowej gry jest definiowany ręcznie przez nazwę
  i oznaczenie Jokera. API nadaje niezmienny `code`, `mobileCode` i kolejność.
  Aktywna grafika symbolu nie jest predykcją ani wynikiem bootstrapu: powstaje
  wyłącznie po świadomym wskazaniu cropa z kanonicznej planszy
  `accepted/corrected`, którego końcowa etykieta człowieka odpowiada kodowi
  symbolu. Referencja przechowuje pełną proweniencję, rewizje i SHA-256, a jej
  bajty są kopiowane do content-addressed storage.
- **Context:** istniejące grafiki symboli pochodziły z niekanonicznych
  predykcji i mogły wskazywać przestarzały crop po korekcie geometrii. To
  wprowadzało błędne obrazki do katalogu i palety wyszukiwania mimo wielu
  zatwierdzonych plansz.
- **Safety:** pending, rejected, superseded, alternatywne źródła i confidence
  klasyfikatora nie mogą stworzyć katalogu ani grafiki referencyjnej. Symbol
  bez referencji pokazuje placeholder. Używany symbol nie jest fizycznie
  usuwalny; odpowiedź blokady zawiera liczniki reguł, plansz, predykcji,
  kohort, iteracji oraz aktywacji. Usunięcie nie wykonuje kaskady tych danych.
- **Consequences:** stary bootstrap, jego UI, API, klient i tabela zostały
  usunięte. Historyczne `image_path` bez wpisu proweniencji nie jest aktywną
  grafiką. Operator najpierw zatwierdza plansze, a potem ręcznie wybiera
  reprezentatywny crop w stronicowanym pickerze.
- **Supersedes:** dla bieżącego produktu zastępuje zachowanie TASK-0125 i
  TASK-0126: automatyczną budowę katalogu oraz ranking cropów po confidence.
  Ich migracje pozostają historycznie audytowalne.
- **Alternatives:** automatyczne przypisanie najwyższej pewności, pozostawienie
  starej grafiki bez proweniencji i archiwizowanie używanego symbolu odrzucono,
  ponieważ nie gwarantują zgodności z decyzją człowieka ani bezpiecznej
  integralności katalogu.

## D-235 — Weryfikacja symboli ma trwały stan per aktualny crop

- **Status:** accepted
- **Date:** 2026-08-26
- **Decision:** masowa weryfikacja symboli użyje jednej logicznej komórki dla
  `review_item_id + cell_index`, zawsze związanej z dokładną checksummą i
  rewizją geometrii bieżącego cropa. Komórka ma stan `pending` albo `approved`;
  niezależny `has_grid_issue` wymaga `pending`. Brak symbolu jest technicznym
  `?` (`NULL`) i nigdy nie może być zatwierdzony.
- **Context:** pełna decyzja 15 symboli jest zbyt gruba dla szybkiej kontroli
  wielu cropów, ale drugi, niesynchronizowany model planszy tworzyłby ryzyko
  konfliktu z istniejącym Reviewerem, canonical stagingiem i wyszukiwaniem.
- **Safety:** nowa geometria unieważnia wszystkie 15 decyzji komórek. Plansza
  zostaje automatycznie domknięta tylko przy 15 aktualnych zatwierdzeniach bez
  błędu siatki; zgodność z predykcją daje `accepted`, a każda zmiana symbolu
  `corrected`. Zła siatka pozostaje wyłącznie flagą komórki, z której Reviewer
  później obliczy filtr plansz.
- **Consequences:** repozytorium zapisuje historię append-only, a write-through
  istniejących decyzji pełnej planszy, geometrii, reinferencji i zmiany
  właściciela sekwencji jest transakcyjny. Cropy pozostają assetami filesystemu
  — baza zapisuje tylko bezpieczne ścieżki, checksumy i metadane. Wersja
  katalogu komórek rośnie najwyżej raz per transakcję gry, aby kolejne operacje
  masowe mogły bezpiecznie zamrażać filtr.
- **Alternatives:** flaga błędnej siatki na planszy oraz automatyczne
  zatwierdzanie nieznanego symbolu odrzucono jako niespójne z granularnym
  audytem i bezpieczeństwem geometrii.

## D-236 — Skala weryfikacji symboli jest obecnie potwierdzana statycznie

- **Status:** accepted
- **Date:** 2026-08-26
- **Decision:** zakończenie pionu masowej weryfikacji symboli nie uruchamia
  automatycznie fizycznego benchmarku około dwóch milionów komórek na
  komputerze operatora. Odbiór w tym momencie opiera się na analizie
  algorytmicznej, testach integralności i ograniczeniach pamięci; pomiar czasu
  zostaje odroczony do osobno zleconego testu na odizolowanej scratchowej bazie.
- **Context:** komputer operatora wykonuje aktywne importy i review. Tworzenie
  milionów rekordów oraz wymuszony crash obciążałoby bieżącą pracę, bez
  dostarczenia wiarygodnego, przenośnego wyniku p95 dla innej konfiguracji
  PostgreSQL i sprzętu.
- **Safety:** odroczenie nie osłabia invariantów: keyset, checksum-bound
  tożsamość, atomiczność per plansza, idempotency i recovery pozostają objęte
  istniejącymi testami. Bramka `p95 <= 250 ms` jest jawnie niezmierzona i nie
  może być raportowana jako zaliczona. Pełny test wymaga wyraźnej zgody,
  osobnej bazy i cleanupu tylko własnych danych testowych.
- **Consequences:** model referencyjny używa `2 000 010`, a nie dokładnie
  `2 000 000` komórek, aby zachować invariant 15 cropów na planszę. Analiza
  wskazuje również, że liczniki listy są obecnie agregowane po całym filtrze;
  ewentualna optymalizacja nastąpi wyłącznie po rzeczywistym pomiarze.
- **Alternatives:** uruchomienie benchmarku w tle, zaniżenie fixture’u przez
  niepełne plansze lub deklarowanie p95 bez danych odrzucono.

## D-237 — Ręczna korekta zakresu nie normalizuje historii wyborów

- **Status:** accepted
- **Date:** 2026-08-27
- **Decision:** lokalna oraz operator-local zdalna ręczna selekcja pozwalają
  operatorowi kliknąć bieżący zakres i podać wyłącznie dodatni przedział
  `start–start+8`. Zapis zmienia tylko `nextRangeStart`; istniejące decyzje i
  zapisane pliki pozostają dokładnie takie, jak zostały zatwierdzone. Domyślny
  kolejny zakres jest wyliczany o dziewięć pozycji zgodnie z kierunkiem sesji,
  z dolną granicą `1` dla kolejności malejącej.
- **Context:** operator musi móc poprawić pomyłkę numeracji w trakcie selekcji
  bez ponownego kopiowania już wybranych JPEG-ów. Wymuszanie ciągłości między
  decyzjami usuwało tę możliwość oraz błędnie traktowało świadomą lukę jako
  uszkodzenie manifestu.
- **Safety:** każda decyzja niezależnie waliduje dodatni zakres dokładnie
  dziewięciu plansz. Zgodność źródła, checksum, tożsamości manifestu i ochrona
  obcych plików pozostają fail-closed. Aplikacja nie uzupełnia luk, nie zmienia
  poprzednich zakresów i nie renumeruje historii bez jawnej operacji całego
  manifestu.
- **Consequences:** wznowienie odtwarza ręcznie poprawione, nieciągłe zakresy
  dokładnie z manifestu. Legacy batch bez trwałego `nextRangeStart` wyznacza
  kolejny zakres z ostatniej rzeczywistej decyzji, nie z liczby decyzji.
- **Alternatives:** wymuszenie pełnej ciągłości albo automatyczne
  przenumerowywanie poprzednich decyzji odrzucono, ponieważ groziły utratą
  świadomych korekt operatora.

## D-238 — Najnowszy import zastępuje wyłącznie nierozwiązaną planszę

- **Status:** accepted
- **Date:** 2026-08-27
- **Decision:** dla jednej gry i znanego `sequence_number` może istnieć najwyżej
  jedna aktywna pozycja `pending`. Plansza kanoniczna `accepted/corrected` jest
  chroniona i kolejny import nie otwiera jej ponownie. Gdy canonical nie
  istnieje, właścicielem zostaje najnowszy import według deterministycznego
  porządku `(job.created_at, job.id)`, a starsze pending przechodzą do
  audytowalnego `superseded`.
- **Context:** nakładające się stagingi tworzyły wiele pozycji do zatwierdzenia
  tego samego numeru oraz powtarzały ich cropy w widokach operacyjnych. Sam
  read model wybierający jedną kartę nie usuwał przyczyny ani nie chronił
  pozostałych ścieżek zapisu.
- **Safety:** częściowy indeks unikalny w PostgreSQL blokuje dwa pending dla
  `game_id + sequence_number`; wszystkie ścieżki materializacji używają jednej
  blokady sekwencji i tej samej polityki. Historyczne źródła i eventy nie są
  usuwane. Sekwencje bez jednoznacznego numeru pozostają poza tym invariantem i
  nadal muszą zakończyć się kontrolowanym review integralności.
- **Consequences:** zakończone importy nie występują w dropdownie operacyjnego
  Reviewera, ale pozostają w Jobach. Weryfikacja symboli i wyszukiwanie plansz
  dziedziczą tego samego właściciela z fast-document, więc starsze nakładające
  się stagingi nie dostarczają równoległych cropów.
- **Alternatives:** usuwanie historycznych importów, first-write-wins oraz
  wybieranie właściciela wyłącznie w UI odrzucono jako nieaudytowalne albo
  nieskuteczne dla ponownych importów.

## D-239 — Reconciliacja kompletnej projekcji nie blokuje istniejących cropów

- **Status:** accepted
- **Date:** 2026-08-27
- **Decision:** job `image_symbol_review_backfill` utworzony jawnie z projekcji
  `ready` otrzymuje trwały znacznik `preserve_ready_projection`. Gdy taki job
  jest aktywny, przejściowy stan `rebuilding` nie blokuje odczytu ani mutacji
  istniejących checksum-bound cropów. Początkowy backfill oraz rebuilding bez
  tego znacznika nadal są niedostępne.
- **Context:** operator może uruchomić `Uzupełnij brakujące symbole` podczas
  ręcznej weryfikacji. Dotychczas worker po przejęciu joba poprawnie zachowywał
  dane, ale globalna bramka `status == ready` blokowała nawet zmianę istniejącej
  zatwierdzonej komórki.
- **Safety:** każda lista i mutacja nadal sprawdza aktualnego właściciela,
  rewizję geometrii, rewizję komórki i checksumę cropa. Znacznik nie jest
  nadawany pierwszemu lub niekompletnemu backfillowi i obowiązuje tylko przy
  aktywnym jobie tej samej gry.
- **Consequences:** bounded reconciliacja może uzupełniać nowe rekordy bez
  przerywania pracy na już gotowych danych. Błąd lub zakończenie joba usuwa
  podstawę wyjątku; projekcja musi wtedy ponownie osiągnąć `ready` albo pozostaje
  kontrolowanie zablokowana.
- **Alternatives:** blokowanie całego workspace'u na czas maintenance oraz
  dopuszczenie każdego stanu `rebuilding` odrzucono odpowiednio jako zbędną
  przerwę operatorską i osłabienie integralności pierwszego backfillu.

## D-240 — Pojedyncza decyzja symbolu nie wymaga trwałego joba masowego

- **Status:** accepted
- **Date:** 2026-08-27
- **Decision:** jedna jawna, checksum-bound decyzja komórki jest wykonywana
  synchronicznie przez istniejący atomowy command path planszy. Trwała operacja
  i job `image_symbol_review_bulk` pozostają wymagane dla co najmniej dwóch
  jawnych targetów oraz snapshotu całego filtra.
- **Context:** ręczna korekta symbol po symbolu tworzyła dużą liczbę małych
  jobów oczekujących na general worker, mimo że klient zna dokładny
  `cellReviewId`, rewizję, geometrię i checksumę. Opóźniało to feedback oraz
  zaśmiecało operacyjną historię Jobów.
- **Safety:** szybka ścieżka używa tego samego repozytorium mutacji, blokady
  właściciela, kontroli rewizji i cropa, append-only eventu oraz agregacji
  planszy. Nie omija transakcji domenowej; pomija wyłącznie orkiestrację joba,
  która nie daje korzyści dla jednego targetu.
- **Consequences:** pojedyncza zmiana kończy się w jednym requestcie i daje
  natychmiastowy feedback. Operacje wielotysięczne nadal mają checkpoint,
  recovery, idempotencję i częściowy raport. Istniejące historyczne joby nie są
  usuwane automatycznie.
- **Alternatives:** utrzymanie joba dla każdej komórki oraz wykonywanie całych
  filtrów synchronicznie odrzucono odpowiednio z powodu narzutu operatorskiego
  i ryzyka długich transakcji HTTP.

## D-241 — Weryfikacja symboli utrzymuje jedną keysetową stronę 500 cropów

- **Status:** superseded by D-259
- **Date:** 2026-08-27
- **Decision:** Admin pokazuje jedną stronę maksymalnie 500 cropów, domyślnie w
  stanie `pending`. Nie prefetchuje i nie przechowuje stron sąsiednich. Operator
  może zaznaczyć wyłącznie jawne elementy bieżącej strony; snapshot całego
  niewidocznego filtra nie jest dostępny w UI.
- **Context:** infinite scroll i read-ahead zwiększały liczbę requestów oraz
  utrudniały przewidywanie, które elementy należą do jednej masowej decyzji.
  Operator preferuje większą, stabilną stronę i jawny zakres zaznaczenia.
- **Safety:** po decyzji Admin nie scala lokalnie pozostałości z odpowiedzią
  uzupełniającą po ID. Powtarza świeże zapytanie od zapamiętanego kursora
  wejściowego strony, dzięki czemu jeden backendowy keyset odpowiada za
  kolejność, brak duplikatów i dopełnienie do 500. W czasie operacji akcje oraz
  nawigacja są zablokowane.
- **Consequences:** w pamięci aplikacji znajduje się najwyżej 500 metadanych.
  Cache HTTP checksum-bound miniaturek pozostaje niezależny od danych strony i
  ogranicza ponowny transfer. Backend nadal wspiera filtr snapshotowy jako
  kontrakt kompatybilności, ale Admin go nie tworzy.
- **Alternatives:** osobny endpoint `changedIds -> replacements`, lokalne
  scalanie cache oraz utrzymanie infinite scrolla odrzucono z powodu ryzyka
  rozjazdu rewizji, duplikatów i niepotrzebnej złożoności.

## D-242 — Domyślny profil workera przeznacza siedem wątków na general

- **Status:** accepted
- **Date:** 2026-08-27
- **Decision:** `npm run workers:start` uruchamia wyłącznie general lane z
  kooperacyjnym budżetem siedmiu wątków. Rejestracja geometrii wiąże liczbę
  równoległych stron z tym budżetem, natomiast biblioteki natywne używają po
  jednym wątku. Image-selection lane nie startuje domyślnie, ale pozostaje
  dostępny przez jawny profil `workers:start:all` z podziałem 2+5.
- **Context:** automatyczna selekcja zdjęć została zastąpiona ręcznym wyborem,
  podczas gdy kolejka general zawiera kosztowne preflighty geometrii. Komputer
  ma osiem logicznych procesorów. Dotychczasowy ekran pokazywał budżety 2 i 5,
  lecz nie były to wymienne procesy jobów: general nadal ma jeden trwały slot.
- **Safety:** nie zwiększono liczby równocześnie mutujących general jobów i nie
  zmieniono lease, checkpointów ani execution slotów. Jednowątkowe OpenCV/BLAS
  zapobiega zagnieżdżonemu fan-outowi do 49 wątków.
- **Consequences:** preflight może obrabiać do siedmiu stron równolegle, a
  proces selekcji nie zużywa RAM ani CPU w bezczynności. Joby bez adaptera
  równoległego nie przyspieszą tylko od większej liczby w budżecie. Wznowienie
  automatycznej selekcji wymaga świadomego użycia profilu obu lane.
- **Alternatives:** ustawienie siedmiu natywnych wątków na każdy z czterech
  dotychczasowych tasków oraz równoległe wykonywanie wielu general jobów
  odrzucono odpowiednio z powodu nadsubskrypcji i ryzyka konfliktów projekcji.

## D-243 — Model symboli uczy się z zatwierdzonych cropów, nie pełnych plansz

- **Status:** accepted
- **Date:** 2026-08-28
- **Decision:** nowa kohorta symboli v2 kwalifikuje indywidualne, aktualne
  komórki `approved` bez błędu siatki. Korekty mają pierwszeństwo, podobne
  przykłady są redukowane, a liczność jest ograniczona do celu 1000 i maksimum
  2000 per aktywny symbol. Kalibracja siatki pozostaje osobnym workflowem.
- **Context:** kompletność całej planszy nie jest potrzebna do nauczenia
  klasyfikatora jednego cropa, a tysiące niemal identycznych przykładów
  zwiększałyby czas bez proporcjonalnej wartości.
- **Safety:** tożsamość próbki wiąże aktualnego właściciela sekwencji, rewizję
  komórki i geometrii, crop, checksumę oraz źródło. Splity nadal są rozłączne
  po rodzinie źródła. Historyczne kohorty v1 pozostają odtwarzalne.
- **Consequences:** można ulepszyć model po częściowej weryfikacji plansz;
  koszt selekcji jest liniowy i ograniczony, a koszt treningu nie rośnie po
  osiągnięciu limitu kohorty.
- **Alternatives:** uczenie z pełnych plansz i porównywanie każdego cropa z
  każdym odrzucono odpowiednio z powodu sztucznego blokowania feedbacku oraz
  kwadratowego kosztu.

## D-244 — Etykieta, jakość cropa i przydatność treningowa są niezależne

- **Status:** accepted
- **Date:** 2026-08-28
- **Decision:** logiczna etykieta komórki, problem jakościowy bieżącego cropa
  oraz zgodność cropa z ostatnim zatwierdzeniem są niezależnymi osiami. Recrop
  zachowuje zatwierdzoną etykietę, lecz nowy crop nie jest treningowy do czasu
  osobnej weryfikacji. `grid_issue` ponownie otwiera pole po recropie, a
  `unreadable` może zostać rozwiązane realnym symbolem albo domenowym `?` bez
  uczynienia słabego cropa próbką treningową.
- **Context:** dotychczas zatwierdzenie etykiety było utożsamiane z
  zatwierdzeniem pikseli. Po korekcie geometrii nowy, nieobejrzany crop mógł
  odziedziczyć status nadający go do treningu.
- **Safety:** przydatność treningowa wymaga aktywnego realnego symbolu,
  aktualnego właściciela planszy, braku problemu jakości, identycznej tożsamości
  i SHA-256 bieżącego oraz zatwierdzonego cropa i zweryfikowanego pliku.
  Topologia pochodzi z przypiętej wersji reguł; po pierwszym imporcie jej
  wymiary są niezmienne. `?` nie jest rekordem katalogu symboli.
- **Consequences:** geometria, review symboli i trening mogą być rozwijane
  niezależnie bez utraty decyzji człowieka. Aktualne rekordy bez proweniencji
  pozostają nietreningowe do czasu kontrolowanego backfillu 0073.
- **Alternatives:** reset wszystkich etykiet po recropie oraz automatyczne
  uznanie nowych cropów za zatwierdzone odrzucono odpowiednio z powodu utraty
  pracy człowieka i ryzyka zanieczyszczenia kohorty.

## D-245 — Topologia jest częścią artefaktu geometrii i fingerprintu

- **Status:** accepted
- **Date:** 2026-08-28
- **Decision:** każdy nowy import przypina `rows`, `columns` i wersję reguł w
  snapshotcie przetwarzania, fingerprintcie croppera oraz manifeście
  odroczenia. Wspólny source-direct cropper i ręczna geometria są generyczne,
  natomiast automatyczny adapter v20 jawnie obsługuje wyłącznie 3 × 5.
- **Context:** stałe 15 komórek były rozproszone między manifestem, cropperem i
  preview. Sama zmiana reguł mogła przez to nie wejść do tożsamości joba.
- **Safety:** stare artefakty bez pól topologii zachowują dokładną serializację,
  fingerprint i interpretację 3 × 5. Inna topologia nie uruchamia automatycznego
  v20 i kończy się `IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED`; ręczna geometria
  nadal może wygenerować dokładnie `rows × columns` cropów jednym
  source-to-output resamplingiem na komórkę.
- **Consequences:** nowe wyniki zapisują snapshot wymiarów na rozpoznanej
  planszy, a replay nie może przypadkiem użyć croppera o innej topologii.
- **Alternatives:** globalną zamianę stałych historycznych adapterów odrzucono,
  ponieważ złamałaby odtwarzalność istniejących jobów i manifestów.

## D-246 — Game-wide walidacja geometrii pozostaje lokalnym workflowem

- **Status:** accepted
- **Date:** 2026-08-28
- **Decision:** nowa kolejka `Zatwierdzanie cięcia siatki` działa domyślnie
  wyłącznie w lokalnym Reviewerze. Zdalna sesja zachowuje istniejący,
  scope-bound workflow i nie otrzymuje dostępu do game-wide endpointów Admin
  API. Po odbiorze 0.9 lokalny fallback zostaje usunięty.
- **Context:** API TASK 5 świadomie korzysta z lokalnego aktora Admina i może
  listować kolejkę całej gry. Rozszerzenie allowlisty publicznego proxy
  zwiększyłoby uprawnienia tokenu udostępnianego osobie trzeciej.
- **Safety:** proxy zdalnego Reviewera pozostaje bez zmian. Nowy ekran jest
  wybierany dopiero po jednoczesnym potwierdzeniu trybu lokalnego, loopbacku i
  poprawnego scope gry/importu.
- **Consequences:** lokalny operator zawsze otrzymuje docelowy workflow, a
  udostępniane linki zachowują dotychczasowe możliwości do czasu osobnego
  projektu bezpiecznego kontraktu zdalnej walidacji geometrii. Rollback 0.9
  wyłącza nowe mutacje bez niszczenia danych zamiast przywracać stary lokalny
  ekran.
- **Alternatives:** mapowanie game-wide endpointów przez publiczny proxy
  odrzucono z powodu zbyt szerokiego scope i ryzyka ujawnienia innych importów.

## D-247 — Unknown jest sentinelowym kodem layoutu, nie symbolem katalogu

- **Status:** accepted
- **Date:** 2026-08-28
- **Decision:** snapshot schema v4 i trwałe layouty używają `mobileCode = 0`
  wyłącznie jako logicznego unknown. Kodek layoutu dopuszcza zero, natomiast
  katalog symboli, plansza użytkownika i prefix wejściowy nadal wymagają
  realnych kodów `1..32767`. `payout-v3-unknown-prefix-stop` kończy linię na
  pierwszym zero i ignoruje dalszy sufiks.
- **Context:** nieczytelna komórka może być poprawną, zatwierdzoną decyzją
  logiczną, ale nie wolno tworzyć dla niej fałszywego symbolu ani traktować jej
  jak jokera.
- **Safety:** schema v4 deklaruje sentinel w metadata; aktualny mobile wspiera
  v3 i v4, a stare klienty v3 nie otrzymują release'u v4. Historyczny payout
  v2 oraz jego artefakty pozostają odtwarzalne.
- **Consequences:** unknown może przejść przez staging, dataset, snapshot i UI,
  nie stając się klasą modelu ani symbolem możliwym do ręcznego wpisania.

## D-248 — Crop treningowy wymaga zatwierdzonej tożsamości pikseli

- **Status:** accepted
- **Date:** 2026-08-28
- **Decision:** bieżąca kohorta symboli v3 dopuszcza próbkę tylko wtedy, gdy
  aktualny sample ID, SHA-256 i rewizja geometrii są identyczne z proweniencją
  cropa zatwierdzonego przez człowieka oraz plik przechodzi ponowną kontrolę
  ścieżki i checksummy. Kohorta geometrii jest wybierana według zatwierdzonej
  rewizji geometrii, niezależnie od logicznej etykiety symbolu.
- **Context:** recrop zachowuje zatwierdzoną etykietę, lecz tworzy nowe piksele.
  Sam status `approved` nie dowodzi więc, że aktualny crop został obejrzany i
  może bezpiecznie wejść do treningu klasyfikatora.
- **Safety:** unknown, unreadable, grid issue, changed crop i missing asset są
  jawnie raportowanymi wykluczeniami. Manifesty v1/v2 pozostają tylko do
  reprodukcji istniejących iteracji.
- **Consequences:** nowy crop wymaga ponownego zatwierdzenia przed treningiem;
  korekta etykiety nie blokuje uczenia geometrii z zatwierdzonego quada.

## D-249 — Fast documents jest jedyną bieżącą projekcją wyszukiwania

- **Status:** accepted
- **Date:** 2026-08-28
- **Decision:** runtime utrzymuje `image_board_search_candidates` oraz jedną
  wąską projekcję `image_board_search_fast_documents`. Stara tabela
  `image_board_search_documents`, tekstowe tokeny dopasowań i legacy
  `has_grid_issue` są usuwane przez migrację 0075. `quality_issue` jest jedynym
  trwałym źródłem jakości komórki.
- **Context:** właściciele starej i szybkiej projekcji są zgodni, a produkcyjne
  odczyty korzystają z fast documents. Dalszy dual-write zwiększa koszt zapisu
  i zajęte miejsce bez dostarczania odrębnej funkcji.
- **Safety:** downgrade deterministycznie odbudowuje starą strukturę z
  kandydatów i fast documents. Migracja nie usuwa obrazów, obserwacji ani
  audytu i nie wykonuje `VACUUM FULL`. Przed uruchomieniem na danych użytkownika
  wymagany jest raport rozmiaru i osobny checkpoint.
- **Consequences:** publiczne `hasGridIssue` pozostaje czasowo wyliczane dla
  zgodności API, ale ORM i zapisy nie zależą od usuniętej kolumny.

## D-250 — Retencja storage jest manifestowana i fail-closed

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** odtwarzalne artefakty image pipeline'u mają domyślną retencję
  24 h. Kwalifikacja jest deterministyczna i zapisywana w niezmiennym
  manifeście. Aktywna zależność, niepełny handoff stagingu, chroniona
  przestrzeń nazw, symlink albo niebezpieczna ścieżka zawsze blokują usunięcie.
- **Context:** trwałe pełnowymiarowe bitmapy normalizacji, browserowe stagingi i
  payloady etapów powodują liniowy wzrost dysku przy kolejnych rerunach.
- **Safety:** pierwszy cleanup jest tylko preview i wymaga jawnego
  potwierdzenia. GC nie usuwa originals, referencjonowanych cropów, modeli,
  kohort, release'ów, audytu ani ręcznej selekcji. Nie uruchamia `VACUUM FULL`
  ani kompaktowania VHDX.
- **Consequences:** przyszłe usuwanie musi ponownie sprawdzić manifest, mtime,
  rozmiar, zależności i granice zarządzanego rootu przed każdą partią.

## D-251 — Pełny inwentarz storage jest trwałym jobem, nie requestem UI

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** pełne liczenie plików i bajtów wykonuje idempotentny job
  `storage_inventory` w general lane. GET panelu korzysta z ostatniego
  `storage_usage_snapshots` i bieżących stałoczasowych metadanych woluminów.
- **Context:** zarządzany storage zawiera miliony plików. Synchroniczny skan po
  otwarciu widoku blokowałby request, zwiększał obciążenie dysku i mógłby
  powodować nakładające się pomiary.
- **Safety:** job niczego nie usuwa, nie podąża za symlinkami i zapisuje tylko
  agregaty. Równoległe starty są serializowane, a GC nadal wymaga osobnego
  niezmiennego preview i jawnego potwierdzenia.
- **Consequences:** wartości rozmiarów mogą być starsze do czasu jawnego
  odświeżenia, dlatego panel zawsze pokazuje czas pomiaru.

## D-252 — Późne payloady pipeline'u są odtwarzalne z manifestu terminalnego

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** po 24 godzinach terminalne execution może usunąć payloady
  `board_cell_geometry`, `board_crops`, `sequence_ocr` i `symbol_inference`,
  jeżeli nie ma aktywnej, błędnej ani nierozwiązanej zależności. Przed
  usunięciem utrwalany jest checksumowany manifest adapterów, etapów i finalnych
  wyników. `board_detection` pozostaje operacyjne dla korekty geometrii.
- **Context:** JSONB późnych etapów zajmuje większość tabeli
  `image_pipeline_stage_results`, mimo że finalne plansze, komórki, cropy i
  decyzje są już osobnymi źródłami prawdy.
- **Safety:** pierwszy run wymaga niezmiennego preview i jawnego potwierdzenia.
  Każda partia rewaliduje execution i checksumy. Kompakcja nie usuwa obrazów,
  audytu ani projekcji domenowych i nie wykonuje `VACUUM FULL`.
- **Consequences:** kolejny rerun rekonstruuje brakujące późne etapy z managed
  original; wcześniejsze manifesty pozostają audytowalne jako osobne wersje.

## D-253 — Automatyczny GC jest aktywny po kontrolowanym odbiorze

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** po udanym, jawnie zatwierdzonym pierwszym cleanupie
  `storage_gc_observe_only` ma domyślną wartość `false`. Tryb obserwacyjny
  pozostaje dostępny przez zmienną środowiskową do diagnostyki i kolejnych
  kontrolowanych rolloutów.
- **Context:** pierwszy run usunął 39 514 bitmap i odzyskał 62 191 682 889 B,
  pozostawiając jeden zmieniony kandydat jako konflikt. Inwentarz potwierdził
  brak zmian w originals, cropach, modelach, training i stagingu. Kompakcja
  PostgreSQL zakończyła 25 899 wykonań bez konfliktów.
- **Safety:** progi 60/30/80 GiB, rewalidacja manifestu, zależności, mtime,
  rozmiaru i ścieżki pozostają obowiązkowe. Automatyczny GC nie rozszerza
  zakresu na chronione przestrzenie i nadal nie uruchamia `VACUUM FULL` ani
  kompaktowania VHDX.
- **Consequences:** po restarcie API system może automatycznie odzyskać tylko
  dane spełniające zatwierdzoną politykę. Brak bezpiecznych kandydatów blokuje
  nowe zapisy zamiast usuwać dane chronione.

## D-254 — `seq_*` przypina aktywne sloty, a komórka 0.10 jest wirtualna

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** `seq_<start>-<end>.jpg|jpeg` deklaruje dokładnie od jednej do
  dziewięciu kolejnych plansz. Aktywne pozycje są wyłącznie row-major prefiksem
  `0..N-1` strony 3 × 3. Geometria 0.10 używa współrzędnych RGB po jednym EXIF
  transpose i wypukłych source quadów; nie wymaga prostokątów, rombów,
  równoległości ani kątów prostych na zdjęciu. Komórka otrzymuje trwałą
  logiczną tożsamość niezależną od geometrii oraz odrębną tożsamość renderowania
  zależną od źródła, quada, topologii, rewizji i konfiguracji.
- **Context:** obecne parsery i v20 znają zakresy `seq_*`, ale ich semantyka
  aktywnych slotów nie była jednym wspólnym kontraktem, a trwały crop mieszał
  dane logiczne z aktualnymi pikselami. Częściowa ostatnia strona i recrop
  wymagają jawnych, deterministycznych reguł przed migracją oraz OpenCV.
- **Safety:** TASK-0307 nie uruchamia nowego silnika, nie zmienia danych ani
  HTTP i nie tworzy bitmap. Stare artefakty pozostają odtwarzalne. Kolejne
  taski mogą podpiąć nową geometrię tylko za feature flagą i z kontrolą
  proweniencji pikseli.
- **Consequences:** parser API i worker używają jednej walidacji. Wirtualny
  renderer może wyprowadzać każdą komórkę bezpośrednio ze źródła jednym
  resamplingiem, zachowując oddzielnie wcześniejsze verified labels.
- **Alternatives:** wykrywanie liczby plansz z obrazu, dopuszczanie dziur w
  częściowej stronie oraz prostokątne ograniczenie quada odrzucono, ponieważ
  stoją w sprzeczności z poświadczoną nazwą, kolejnością i perspektywą zdjęć.

## D-255 — Wirtualny asset jest dual-schema i wdrażany per gra

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** geometria źródła jest append-only, a trwałe rekordy planszy,
  komórki, review i kohorty deklarują `legacy_file` albo `virtual_source`.
  Virtual nie przechowuje ścieżki cropa; wymaga source geometry, logical cell
  key, render spec, wersji extractora i checksumy wynikowych pikseli. Osobny
  rekord rolloutu per gra pozostaje domyślnie `legacy` / `legacy_files`.
- **Context:** kolejne silniki mają renderować komórkę bezpośrednio z managed
  original bez milionów trwałych plików, ale historyczne joby i review muszą
  pozostać odtwarzalne podczas długiego rolloutu.
- **Safety:** migracja 0082 jest addytywna. Constraints dużych tabel są
  dodawane jako `NOT VALID`, więc unikają nieograniczonego skanu historycznych
  rekordów, a nowe zapisy są sprawdzane od razu. Backfill rolloutów jest
  idempotentny i bounded. Dotychczasowe read paths odrzucają virtual fail-closed
  do czasu jawnego przełączenia.
- **Consequences:** fizyczny downgrade jest bezpieczny przed pojawieniem się
  source geometry lub aktywnego virtual mode. Później rollback oznacza zmianę
  rolloutu gry na legacy i zachowanie proweniencji, nie destrukcyjne usunięcie
  kolumn lub tabel.

## D-256 — Wirtualna komórka używa jednego source-direct warpa bez trwałego pliku

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** `CanonicalSourceLoader` dekoduje zweryfikowany managed original
  raz na bieżące wykonanie i stosuje EXIF dokładnie raz. Produkcyjny
  `virtual-cell-renderer-source-direct-v1` wykonuje jeden warp źródło→komórka,
  zwraca RGB w pamięci, render spec checksum oraz pixel checksum i nie zapisuje
  PNG. Warianty bounding-box i rectified-board są wyłącznie diagnostyczne.
- **Context:** trwałe cropy i pośrednie rastry zwiększają zajętość dysku, a
  geometry-bound kontrakty TASK-0307/0308 pozwalają odtworzyć piksele z managed
  original. Rollout wymaga jednak dowodu, że nowa ścieżka nie zmienia wejścia
  obecnego modelu.
- **Safety:** renderer waliduje kompletną partię, źródło, checksumy, wersję
  konfiguracji i pokrycie przed pierwszym warpem. Historyczny v19 pozostaje
  niezmieniony, a test wymaga dokładnej zgodności pikseli dla tej samej
  geometrii. TASK-0309 nie aktywuje pipeline'u ani nie zapisuje virtual records.
- **Consequences:** późniejszy task może podłączyć wariant B za rollout state,
  nie kopiując binariów. Każda zmiana interpolacji, paddingu lub preprocessingu
  musi otrzymać nową wersję render specu i osobną bramkę.

## D-257 — Globalna homografia Structured OpenCV jest wyłącznie inicjalizacją

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** `structured-opencv-global-initialization-v1` wyznacza wyłącznie
  początkowe ROI attested prefiksu slotów. Z profilem używa ORB/RANSAC na
  zatwierdzonych anchorach; bez profilu wymaga zgodnego dowodu czerwonych ramek,
  gradientów i LSD. Globalna homografia nie jest finalnym quadem planszy i nie
  pozwala rozpocząć cropowania ani inferencji.
- **Context:** historyczna rejestracja strony potrafiła dobrze przenosić układ
  między kątami, ale wspólny wynik mieszał inicjalizację z ostatecznym dowodem
  dziewięciu plansz. Częściowe strony potrzebują jawnego prefiksu bez
  syntetyzowania pozostałych pozycji.
- **Safety:** brak kompletnego dowodu zwraca `needs_manual_review` bez quadów.
  Numer sekwencji nadal wynika wyłącznie z nazwy `seq_*`. TASK-0310 nie zmienia
  aktywnego pipeline'u v20, bazy, UI ani danych użytkownika.
- **Consequences:** TASK-0311 może wykonać niezależne lokalne dopasowanie każdej
  aktywnej planszy w ograniczonym ROI. Profil i ścieżka cold-start mają wspólny,
  checksum-bound kontrakt, ale żadna z nich nie może ominąć finalnych bramek.
- **Alternatives:** uznanie przeniesionych quadów za finalne oraz syntetyzowanie
  brakujących slotów odrzucono z powodu wcześniejszych false-successów i ryzyka
  przesunięcia symboli.

## D-258 — Finalna geometria wymaga niezależnego dowodu linii każdej planszy

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** każdy aktywny slot otrzymuje własne lokalne dopasowanie sześciu
  pionowych i czterech poziomych linii. Tymczasowa rektyfikacja służy wyłącznie
  analizie, a finalna homografia oraz quad są wyrażone w źródle bez wymagania
  prostokąta. Automatyczny wynik wymaga wszystkich wersjonowanych hard gates;
  confidence klasyfikatora symboli nie jest wejściem geometrii.
- **Context:** globalna rejestracja dobrze inicjalizuje stronę, lecz wcześniejsze
  false-successy przenosiły lub syntetyzowały błędne quady mimo czytelnego
  obrazu. Krzywizna i perspektywa ekranu wymagają lokalnego dowodu osobno dla
  każdej planszy.
- **Safety:** jedna brakująca linia wewnętrzna może zostać wyprowadzona tylko z
  kompletnych granic zewnętrznych, a minimum linii, przecięć, reprojekcja,
  source support, row-major i overlap pozostają twardymi bramkami. Slot bez
  dowodu trafia do review albo korekty, nigdy do automatycznego cropowania.
- **Consequences:** wynik zawiera per-slot evidence, składowe confidence i
  stabilne reason codes. TASK-0311 pozostaje bez integracji produkcyjnej, bazy,
  API i UI; późniejszy rollout musi skonsumować dokładnie ten wersjonowany
  kontrakt.
- **Alternatives:** wspólna końcowa homografia strony, wymuszanie kątów prostych
  w zdjęciu, ML/keypoint fallback i segmentacja zostały odrzucone w tym etapie.

## D-259 — Weryfikacja symboli wirtualizuje strony i zamraża pełny filtr

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** lokalny Admin zachowuje jawne keysetowe strony po 500
  metadanych, lecz renderuje wyłącznie viewport z małym overscanem przez
  `@tanstack/react-virtual`. Trzyma najwyżej trzy najbliższe strony metadanych
  oraz prefetchuje wyłącznie jedną następną stronę. Wirtualne assety są
  pobierane atlasem dla najwyżej 100 aktualnie renderowanych komórek; klient nie
  pobiera 10 000 obrazów ani pełnej listy ID.
- **Context:** jednoczesne wyrenderowanie i pobranie miniaturek dla strony 500
  cropów obciążało przeglądarkę mimo bounded keysetu. Poprzednia decyzja D-241
  eliminowała każdy prefetch i snapshot filtra, co chroniło prostotę, ale
  ograniczało płynność oraz bezpieczną operację na większym zbiorze.
- **Safety:** cursor oraz snapshot wiążą grę, symbol, stan, przedział
  confidence i rewizję katalogu. Zaznaczenie jawne pozostaje ograniczone do
  10 000 targetów; `Zaznacz wyniki filtra` przekazuje wyłącznie ten snapshot i
  maksymalnie 10 000 wykluczeń. Zmiana filtra po zaznaczeniu wymaga
  potwierdzenia i czyści selection. Jedna jawna komórka nadal używa
  synchronicznej, checksum-bound mutacji, większe zbiory zachowują trwały job.
- **Consequences:** interfejs nie wraca do infinite scrolla ani offsetów;
  nawigacja stron pozostaje widoczna i deterministyczna. Backend ogranicza
  pojedynczy odczyt do 500, a confidence jest częścią scope cursorów i filtra
  operacji masowej. Zdalny Reviewer nie dostaje nowych endpointów Admina.
- **Alternatives:** renderowanie całych stron, pobieranie obrazów dla 10 000
  targetów i lokalne materializowanie całego filtra odrzucono z powodu pamięci,
  transferu oraz ryzyka starej rewizji katalogu.

## D-260 — Rollout wirtualnej geometrii wymaga bounded walidacji przed zapisem

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** każda gra przechodzi trwały, wznawialny job walidacji
  proweniencji źródeł `virtual_source`. Stan `ready` odblokowuje lokalny ręczny
  zapis, który tworzy wyłącznie append-only source/board geometry i checksumy
  renderowanych pikseli. Nie materializuje board ani cell PNG i nie promuje
  automatycznie trybu rolloutu.
- **Context:** pipeline potrafi już zapisać wirtualne wyniki i wyrenderować ich
  bounded podglądy, ale ręczna korekta była fail-closed. Bez osobnej bramki
  niepełna source geometry lub stara projekcja właściciela mogłaby doprowadzić
  do zapisu przeciwko niewłaściwej planszy.
- **Safety:** cursor jest ograniczony do gry, każda partia ma najwyżej 100
  źródeł, a niekompletna proweniencja kończy się kontrolowanym `failed` z ID
  źródła. Manualna transakcja ponownie blokuje sekwencję i sprawdza source,
  topologię, rewizję oraz checksumy. Etykieta człowieka pozostaje, lecz nowy
  crop nie jest treningowy do czasu ponownego zatwierdzenia pikseli.
- **Consequences:** identyczny retry nie tworzy duplikatów, obecne rekordy
  legacy pozostają niezmienione, a Reviewer może używać jednego workflow dla
  obu asset modes po przejściu bramki gry.
- **Alternatives:** automatyczna konwersja legacy, materializacja nowych PNG i
  promocja gry po samym backfillu zostały odrzucone jako zbyt ryzykowne.

## D-261 — Brak kompletnego raportu nie promuje rolloutu geometrii

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** `structured_default` / `virtual_default` jest dozwolone wyłącznie
  po zaakceptowanym holdoucie obejmującym minimum 100 źródeł, 500 aktywnych
  plansz, pięć bucketów oraz wszystkie historyczne failures i false-successy,
  z board-level automatic correctness co najmniej 98%. Wynik 95–98% pozostaje
  w `structured_review` / `virtual_shadow`, a wynik poniżej 95% utrzymuje
  `legacy` / `legacy_files`. Brak raportu albo niegotowa walidacja proweniencji
  nie zmienia bieżącego trybu i nie uruchamia TASK-0319.
- **Context:** TASK-0317 wdrożył bounded walidację i ręczny zapis virtual, ale
  jego Outcome jawnie potwierdza brak operacyjnego backfillu. Repozytorium nie
  zawiera kompletnego raportu 0.10, więc wynik board-level nie może zostać
  wyliczony bez zgadywania lub użycia danych niespełniających kontraktu.
- **Safety:** polityka progów jest czysta i deterministyczna. Niepełny dowód
  zwraca `insufficient_evidence` bez rekomendacji trybu. TASK-0318 nie mutuje
  stanów gry, nie usuwa aliasów, legacy cropów, source geometry, canonical
  ownership ani zweryfikowanych etykiet.
- **Consequences:** kod 0.10 pozostaje dostępny per gra w trybach kontrolowanych,
  lecz domyślny cutover jest wstrzymany do prawidłowego odbioru. Pełny rollback
  tworzy nową rewizję `legacy/legacy_files` dla przyszłych jobów; nie przepisuje
  snapshotów istniejących jobów i nie wykonuje downgrade'u 0082 po zapisaniu
  danych virtual.
- **Alternatives:** promocja po samym stanie `ready`, traktowanie braku raportu
  jak `<95%` oraz usunięcie legacy po przejściu testów jednostkowych odrzucono,
  ponieważ nie mierzą rzeczywistej poprawności plansz i osłabiają rollback.

## D-262 — Wczesny fallback keypoint pozostaje eksperymentem shadow-only

- **Status:** accepted
- **Date:** 2026-08-29
- **Decision:** bezpośrednie polecenie właściciela pozwala zaimplementować
  bounded eksperyment `KeypointGeometryEngine` mimo braku raportu `<95%`, ale
  nie pozwala aktywować go w produkcji. Model przewiduje `9 × 4` heatmaps i
  obecność slotów, używa wyłącznie ręcznie zatwierdzonych quadów, splitu według
  source family i ONNX Runtime CPU. Wynik zawsze przechodzi przez wspólny
  refiner oraz istniejące hard gates.
- **Context:** D-261 poprawnie zatrzymała automatyczny trigger TASK-0319 przy
  `insufficient_evidence`. Jawne polecenie implementacji rozszerza zakres
  bezpiecznego eksperymentu, nie stanowi jednak dowodu jakości ani decyzji o
  zmianie rolloutu.
- **Safety:** artefakt jest checksum-bound, manifest wydania ma
  `shadowOnly=true` i `activationAllowed=false`, nieaktywne sloty nie są
  syntetyzowane, a brak aktywnego slota kończy się fail-closed. Nie ma migracji,
  endpointu, operacyjnego treningu ani połączenia z primary workflow.
- **Consequences:** eksperyment można mierzyć na późniejszym, zaakceptowanym
  holdoucie bez naruszania istniejących wyników. Aktywacja wymaga osobnego
  zadania, rzeczywistego raportu, migracji stanu rolloutu i jawnej akceptacji.
- **Alternatives:** uznanie polecenia za zgodę na produkcyjną aktywację,
  automatyczny trening na danych użytkownika oraz osobny zestaw słabszych bramek
  dla modelu odrzucono jako naruszające D-261 i granice bezpieczeństwa.

## D-263 — Końcowa strona ręcznej selekcji jest ograniczona granicą gry

- **Status:** accepted
- **Date:** 2026-08-30
- **Decision:** nowa lokalna i operator-local sesja ręcznej selekcji może
  przypiąć `sequenceUpperBound`. Zakres pozostaje ciągły i ma najwyżej dziewięć
  plansz, lecz końcowa strona kończy się na tej granicy. Bieżący writer zapisuje
  schema v2 z liczbą aktywnych plansz i stanem terminalnym; fizyczna nazwa
  `manual-image-selection-output-v1.json` pozostaje dla jednego źródła
  wznowienia. Reader nadal obsługuje schema v1 jako pełne strony dziewięciu
  plansz.
- **Context:** rzeczywisty katalog kończył się na planszy `500000`, podczas gdy
  historyczna arytmetyka bez granicy zapisała w manifeście `499996–500004` dla
  fizycznego pliku `seq_499996-500000.jpg`.
- **Safety:** niezgodny istniejący katalog jest tylko diagnozowany przez
  read-only dry-run; system nie zmienia automatycznie manifestu ani JPEG-ów.
  Preflight importu dodatkowo blokuje każdy zakres przekraczający
  `games.expected_layout_count`.
- **Consequences:** cofnięcie ostatniej decyzji ponownie otwiera zakończoną
  sesję. Nie ma migracji bazy ani IndexedDB, a historyczny host-transfer nie
  zmienia kontraktu.
- **Alternatives:** sztuczne dopełnianie do dziewięciu, tworzenie drugiego pliku
  manifestu oraz automatyczna naprawa starego katalogu odrzucono jako źródła
  nieistniejących numerów, rozjazdu wznowienia lub ryzyka utraty danych.

## D-264 — Tożsamość logicznej komórki jest związana z wystąpieniem źródła

- **Status:** accepted
- **Date:** 2026-08-30
- **Decision:** `logical-cell-v2` jest wyliczany z niezmiennego wystąpienia
  `importJobId + fileExecutionKey`, fingerprintu przypiętej topologii, slotu
  planszy oraz pozycji komórki. Historyczny `logical-cell-v1` i `render-id-v1`
  pozostają bitowo niezmienione i są emitowane równolegle w render specie.
- **Context:** v1 używa checksummy JPEG-a, dlatego identyczne bajty w dwóch
  niezależnych importach otrzymywały tę samą logiczną tożsamość mimo różnych
  właścicieli i cykli życia. Checksum treści nie rozróżnia wystąpień domenowych.
- **Safety:** fingerprint topologii obejmuje wersję reguł, `rows`, `columns` i
  wersję semantyki slotów. Automatyczny i ręczny source-direct workflow
  korzystają z tej samej pary occurrence. TASK-0321 nie wykonuje migracji,
  backfillu ani przełączenia istniejącej kolumny `logical_cell_key`.
- **Consequences:** recrop zachowuje logical v2, ale zmienia render identity v2;
  identyczny JPEG w nowym jobie ma nowy logical v2. Addytywna trwałość klucza v2
  w osobnej kolumnie i cutover odczytów wymagają osobnego zadania.
- **Alternatives:** użycie samego SHA-256, losowego UUID renderu albo
  przepisywanie kluczy v1 odrzucono odpowiednio z powodu kolizji wystąpień,
  braku deterministycznego replayu i złamania kompatybilności historycznej.

## Szablon nowej decyzji

```text
## D-122 — Reviewer obsługuje szkic oraz aktywną grę przypisaną do sesji

- **Status:** accepted
- **Date:** 2026-08-02
- **Decision:** sesja Reviewera może wskazywać grę w statusie `draft` albo
  `active`; `archived` jest wykluczone. Scope `game_id + import_job_id`
  egzekwowany przez backend pozostaje granicą autoryzacji, a frontend nie
  filtruje poprawnego szkicu do pustego stanu.
- **Context:** ręczne zatwierdzanie plansz i budowa katalogu symboli odbywają się
  przed aktywacją gry. Wymaganie statusu `active` tworzyło błędne koło: szkicu
  nie dało się zweryfikować, mimo prawidłowo utworzonej sesji i gotowego joba
  `waiting_for_review`.
- **Consequences:** Admin launcher i osobny Reviewer pokazują gry draft/active,
  ale nie zarchiwizowane. Wydanie mobilne nadal ma osobną, bez zmian wymaganą
  bramkę aktywnej gry.
- **Alternatives:** aktywowanie gry przed review odrzucono, ponieważ miesza
  przygotowanie danych z gotowością do wydania.

## D-XXX — Tytuł

- Status:
- Date:
- Decision:
- Context:
- Reason:
- Alternatives:
- Consequences:
- Supersedes:
```
