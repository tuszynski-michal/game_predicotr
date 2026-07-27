---
title: Accepted technology stack
status: accepted
last_updated: 2026-07-27
---

# Stos technologiczny

## Kryteria wyboru

- wygodny dla React Developera i czytelny dla agentów AI,
- silne typowanie na granicach,
- całkowicie offline runtime aplikacji Android,
- możliwość dołączenia kilku milionów prostych rekordów,
- dobry ekosystem dla lokalnego przetwarzania obrazu,
- minimalna liczba procesów i usług,
- rozwój, administracja i build na Windows,
- wymienialne adaptery dla obszarów wymagających benchmarku.

## Mobile

### React Native + Expo + TypeScript strict

Zaakceptowany wybór:

- React Native 0.86,
- Expo SDK 57 i lokalny Android build,
- React 19.2,
- Expo Router,
- TypeScript 6 z `strict: true`.

Powody:

- wykorzystanie znajomości React i TypeScript,
- szybki rozwój UI Android,
- możliwość dodania natywnych bibliotek przez development build bez zmiany frameworka,
- wspólne typy i narzędzia w monorepo.

### Biblioteki i moduły startowe

- `expo-sqlite` — lokalny dostęp do dołączonego snapshotu,
- Expo Router — struktura ekranów,
- React `useReducer` lub mały jawny store — stan wprowadzania planszy,
- wbudowane komponenty React Native i własne design tokens — UI bez ciężkiego frameworka,
- wirtualizowana lista React Native; `@shopify/flash-list` może zostać użyty, jeżeli pomiar pokaże przewagę nad `FlatList`.

Główny ekran używa jednej pionowej listy wirtualizowanej. Header, Layout,
Selection i podsumowanie Target są jej nagłówkiem, dzięki czemu długa tabela na
dole nie jest zagnieżdżona w `ScrollView`.

Mobile nie używa:

- klienta OpenAPI do danych domenowych,
- TanStack Query jako warstwy komunikacji z backendem,
- połączeń HTTP do panelu,
- zdalnego pobierania datasetu albo modeli,
- uprawnienia `INTERNET` w finalnym APK.

Logika matching i forecast korzysta z interfejsu repozytorium SQLite. Reprezentacja sygnatury może zmienić się z tekstu na BLOB po benchmarku bez zmiany komponentów UI i algorytmu.

Adapter inicjalizacji SQLite identyfikuje lokalną kopię przez release
version/checksum. Aktualizacja APK nie może ponownie otworzyć starego pliku tylko
dlatego, że istnieje w katalogu danych aplikacji.

Baseline M1 jest przypięty w `package-lock.json`. Major upgrade Expo, React
Native albo TypeScript wymaga osobnego zadania sprawdzającego wzajemną
kompatybilność.

### Wydajność

M1 zaczyna od asynchronicznych zapytań SQLite oraz przetwarzania partiami. Przed skalą 500 000 rekordów na grę obowiązuje benchmark:

- exact match,
- prefix match,
- pełny skan `N - 1` payoutów,
- czas otwarcia bazy,
- użycie pamięci,
- płynność przewijania tabeli.

Natywny moduł lub inny adapter obliczeń jest dopuszczalny dopiero, gdy pomiary pokażą, że Expo SQLite i TypeScript nie spełniają budżetu.

## Admin web

### Next.js + TypeScript strict

- Next.js `16.2.11` z App Router,
- React i React DOM `19.2.3`,
- TypeScript `6.0.3` z `strict: true`,
- `@hey-api/openapi-ts 0.99.0` dla generowanego klienta Fetch zgodnego z
  OpenAPI backendu,
- lokalna aplikacja webowa na Windows,
- komunikacja wyłącznie z lokalnym Admin API,
- formularze gier, symboli, paylines i payoutów,
- podglądy layoutów, zadań i manual review,
- panel przygotowania wersji Android.

Edytor payline używa natywnego elementu `<dialog>`, CSS Grid oraz kontrolowanego
stanu React. Prototyp potwierdził, że ten pion nie wymaga osobnej biblioteki
komponentów ani formularzy; ewentualna biblioteka może zostać dodana później
wyłącznie dla zakresu, którego własne komponenty nie obsłużą czytelnie.

Wygenerowany klient znajduje się w osobnym workspace
`@game-predictor/admin-api-client`. Generator ma przypiętą wersję i jawne
wsparcie TypeScript 6; zapisany OpenAPI oraz wygenerowany kod są sprawdzane pod
kątem driftu w root quality gate. Importy wewnętrzne generowanego źródła nie
zawierają rozszerzenia pliku, ponieważ panel konsumuje TypeScript bezpośrednio
przez `moduleResolution: Bundler`; wymuszanie `.js` nie jest zgodne z buildem
Turbopack tego pakietu źródłowego.

## Backend administracyjny

### Python + FastAPI

- FastAPI `0.139.2`,
- Uvicorn `0.51.0`,
- HTTPX2 `2.7.0` wyłącznie jako transport TestClient,
- obsługa wyłącznie panelu i lokalnych procesów administracyjnych,
- OpenAPI jako źródło typów klienta admin,
- brak endpointów wymaganych przez mobile,
- logika domenowa oddzielona od HTTP, ORM i UI.

Fundament M2 domyślnie nasłuchuje wyłącznie na `127.0.0.1:8000`, a panel działa
na `127.0.0.1:3000`. Konfiguracja hosta API, origin panelu i publicznego adresu
API panelu odrzuca adresy inne niż loopback. Ekspozycja w LAN lub Internecie nie
jest zmianą konfiguracyjną i wymaga osobnej decyzji bezpieczeństwa.

Warstwy:

```text
api          - routing i modele transportowe
application  - use cases, transakcje i zlecanie jobs
domain       - matching, payouts, forecasting, publication
storage      - SQLAlchemy repositories
schemas      - jawne kontrakty i serializacja
```

Narzędzia:

- SQLAlchemy `2.0.51`,
- Alembic `1.18.5` — jedyny mechanizm zmian schematu PostgreSQL,
- Psycopg `3.3.4` z lokalnym pakietem binary,
- Pydantic,
- Python 3.12 i projektowe `.venv`,
- pytest 8,
- Ruff,
- mypy strict jako checker typów.

## Bazy danych

### PostgreSQL 18.4 — kanoniczne źródło prawdy

PostgreSQL przechowuje:

- robocze i opublikowane konfiguracje,
- wersje datasetów i reguł,
- miliony layoutów,
- staging, zadania i manual review,
- metadane wydań.

Jest uruchamiany lokalnie z przypiętego obrazu
`postgres:18.4-alpine3.24` przez Docker Compose. Port hosta jest wiązany tylko z
`127.0.0.1`, a trwały volume PostgreSQL 18 jest montowany w
`/var/lib/postgresql`. Admin API i worker mogą korzystać z niego równolegle.

Pierwsza migracja `0001_empty_baseline` celowo nie tworzy tabel domenowych.
Ustanawia wyłącznie historię Alembic, aby każda późniejsza tabela powstała razem
z odpowiadającym jej pionem funkcjonalnym i testem rollbacku.
Migracja `0002_games_symbols` tworzy pierwszy pion kanoniczny wraz z enumami,
constraints unikalności, zakresem `mobile_code` i relacją symbolu do gry.
Migracja `0003_rules_versions` dodaje wersjonowane wymiary, koszt spinu, status
reguł oraz serwerowo numerowaną relację do gry.
Migracja `0004_paylines` dodaje wzorce należące do wersji reguł, tablicowy
`row_path`, stabilny kod, archiwizację oraz constraints unikalności kodu i
ścieżki.
Migracja `0005_symbol_payouts` dodaje wersjonowaną konfigurację symboli i payout
rules z kluczem złożonym konfiguracji, złożonym FK payoutu oraz zarezerwowaną
unikalnością symbol/długość.

### SQLite — niezmienny snapshot mobile

SQLite jest generowany dla konkretnego wydania i zawiera tylko dane potrzebne mobile:

- konfigurację gier i symbole,
- ciągłe numery sekwencji,
- sygnatury,
- gotowy payout każdego layoutu,
- wersje i checksumy.

Nie zawiera zdjęć, wycinków, stagingu ani danych treningowych. Nie jest kanoniczną bazą edytowaną przez panel.

## Worker i build

Osobny lokalny Python worker/CLI wykonuje:

- import zdjęć,
- walidację datasetu,
- precomputing payoutów,
- generowanie SQLite,
- przygotowanie artefaktów wydania,
- wywołanie kontrolowanego skryptu Android build.

Postęp jest zapisywany w PostgreSQL. Początkowo działa najwyżej jedno ciężkie zadanie naraz. Nie używamy Redis ani Celery.

Panel nie wykonuje dowolnych komend podanych przez użytkownika. Zleca typowane
zadanie, a worker uruchamia jeden wersjonowany workflow build. Obowiązuje lokalny
Gradle/Expo Android build bez zależności od chmurowej usługi buildowej.

Bootstrap M1 potwierdził lokalny workflow Windows:

- Microsoft OpenJDK 17,
- Android SDK Platform i Build Tools 36,
- czysty `expo prebuild`,
- przypięty Gradle wrapper,
- domyślny prywatny build urządzeniowy `arm64-v8a`.

Komendy root:

```powershell
npm run android:toolchain:setup
npm run android:build:debug
npm run android:build:offline
npm run android:verify:offline
```

Build debug wymaga Metro. Build offline zawiera bundle JavaScript i snapshot
SQLite. Pipeline M1.6 obsługuje trwały prywatny klucz release poza Git,
wersjonowanie APK oraz statyczną blokadę uprawnienia `INTERNET`. APK z payout-v2
został odebrany na obu urządzeniach w TASK-0014; test celowo zmienionego
snapshotu i dokładne pomiary należą do M3 zgodnie z D-020.

## Image ingestion

Zaakceptowany stos prototypu:

- Python,
- Pillow,
- `opencv-python-headless`,
- NumPy,
- PaddleOCR ograniczony do cyfr,
- PyTorch i torchvision do treningu,
- ONNX Runtime do inferencji.

Geometria, OCR i klasyfikator implementują osobne porty. Finalne modele zostaną zatwierdzone dopiero po benchmarku na 20–100 reprezentatywnych zdjęciach.

## Monorepo

Zaakceptowana struktura:

```text
apps/
  mobile/
  admin/
services/
  api/
  worker/
packages/
  admin-api-client/
  shared-ts/
  config/
infra/
  docker/
scripts/
ai_docs/
```

Root udostępnia czytelne komendy dla formatowania, lint, testów, typecheck,
migracji, generowania klienta, snapshotu i Android build.

JavaScript workspace używa npm 11 i jednego `package-lock.json`. Python używa
`pyproject.toml` oraz lokalnego `.venv`. Uzasadnienie i ograniczenia opisuje
D-013.

## Świadomie odłożone technologie

Bez wyników pomiarów nie dodajemy:

- Redis,
- Celery,
- Kafka,
- Kubernetes,
- GraphQL,
- Electron,
- mikroserwisów,
- chmury i object storage,
- zdalnej synchronizacji mobile,
- osobnej tabeli dla każdej komórki layoutu,
- ciężkiego detektora obiektów dla zdjęć.

## Wersjonowanie zależności

Baseline M1 jest przypięty w lockfile. Dalsze zmiany muszą:

1. zachować wzajemną kompatybilność wersji,
2. aktualizować lockfile,
3. zapisywać istotne decyzje w `DECISION_LOG.md`,
4. nie wykonywać automatycznych major upgrade'ów w trakcie milestone'u,
5. zachować odtwarzalny build na Windows.
