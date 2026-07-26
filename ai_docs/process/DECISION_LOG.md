---
title: Architecture decision log
status: active
last_updated: 2026-07-26
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
