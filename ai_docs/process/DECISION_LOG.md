---
title: Architecture decision log
status: active
last_updated: 2026-07-29
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
  1) korpus nie ma co najmniej 20 reprezentatywnych zdjęć z opisanymi wariantami,
  2) niezależne goldeny pozycji/narożników nie pozwalają zmierzyć geometrii,
  3) progi nie zostaną zaakceptowane przed kolejną optymalizacją,
  4) OCR nie przejdzie zaakceptowanego progu na held-out source images,
  5) Q-017 nie potwierdzi wystarczającego materiału symboli.
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

## Szablon nowej decyzji

```text
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
