---
title: Architecture decision log
status: active
last_updated: 2026-07-28
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
- **Consequences:** TASK-0051 i TASK-0091 mogą zostać zamknięte, G5 otrzymuje
  status `passed_manual_review_only_ocr`, a TASK-0059 może się rozpocząć.
  Właściciel nie wycina ręcznie obrazów: worker generuje board/cell crops.
  Ręczna praca w M6 dotyczy zatwierdzania lub poprawiania etykiet symboli.
  Każdy numer z OCR nadal wymaga zatwierdzenia i nie może samodzielnie trafić
  do publikowanego datasetu.
- **Supersedes:** D-056 w zakresie blokady wejścia do M6 i dokładnie
  dziewięciu plansz na każdej stronie. D-056 nadal obowiązuje dla braku
  auto-accept, audytowalności i wymiennego adaptera OCR.

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
