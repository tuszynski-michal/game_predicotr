---
title: Architecture decision log
status: active
last_updated: 2026-07-24
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
