---
title: Accepted technology stack
status: accepted
last_updated: 2026-07-31
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
Migracja `0007_jobs` dodaje trwałe, typowane jobs, wspólny enum cyklu życia,
JSONB payload, unikalny hash wejścia, postęp, liczniki wyników i timestamp
żądania anulowania.
Migracja `0008_job_leases` dodaje wersjonowany checkpoint, licznik prób,
singletonowy slot wykonawczy oraz pola owner/token/expiry/heartbeat. Constraint
bazy wymaga pełnego kompletu lease wyłącznie dla statusu `processing`.
Migracja `0010_mobile_releases` dodaje niezmienną tożsamość wydania, globalnie
unikalną wersję, lifecycle, przyszłe pola artefaktów i dokładny zestaw
dataset/rules wybrany dla każdej gry.
Migracja `0011_layout_import_staging` dodaje surowe wiersze importu izolowane
przez job, fizyczny numer linii i offset oraz rozłączny wariant poprawnego
rekordu albo bezpiecznego błędu.
Migracja `0012_layout_import_normalization` dodaje osobny, resumowalny staging
walidacji związany z surową linią, jobem `validate` i opublikowaną wersją reguł
oraz indeksy numeru sekwencji i nieunikalnej sygnatury.
Migracja `0016_image_orchestration` dodaje globalne wykonania plików i
członkostwo w batchu. Migracja `0017_image_processing` dodaje niezmienne wyniki
etapów, domenowe źródła/plansze/komórki, operacyjne review oraz staging
zaakceptowanych layoutów bez binariów obrazów w PostgreSQL.
Migracja `0018_image_failure_retry` dodaje trwałe błędy i liczniki retry,
job-local workflow checkpoint oraz append-only eventy decyzji review.
Migracja `0019_review_geometry` dodaje bieżący wskaźnik rewizji planszy oraz
append-only ręczne rewizje geometrii z czterema narożnikami, planszą i
15 checksum-bound cropami. Binarne PNG pozostają pod zarządzanym
`<artifact-root>/data`.

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

- strumieniowy staging ręcznych CSV/JSONL,
- import zdjęć,
- walidację datasetu,
- precomputing payoutów,
- generowanie SQLite,
- przygotowanie artefaktów wydania,
- wywołanie kontrolowanego skryptu Android build.

M7 używa `ImagePipelineStageExecutor` jako composera portów M5–M6. Adaptery są
wiązane jawnie przez nazwę etapu i wersję z manifestu; composer nie zależy od
OpenCV, Paddle ani ONNX bezpośrednio. Dzięki temu istniejące implementacje i
ich testy pozostają wymienne, a persistence nie kopiuje runnerów
benchmarkowych.

Administracyjny mock M2 o stałym limicie 1000 layoutów może powstać
synchronicznie w FastAPI. Wszystkie większe datasety pozostają operacją
worker/CLI; nie wolno rozszerzać tego wyjątku przez samo zwiększenie limitu
requestu.

Postęp jest zapisywany w PostgreSQL. Początkowo działa najwyżej jedno ciężkie zadanie naraz. Nie używamy Redis ani Celery.

`created` jest trwałym stanem gotowym do przejęcia. `processing` oznacza
wykonanie, `waiting_for_review` zwalnia worker, a `completed`, `failed` i
`cancelled` są stanami końcowymi. Nazwy etapów, takie jak `scanning` lub
`writing_layouts`, są przechowywane osobno.

Lokalny runtime używa krótkich transakcji SQLAlchemy do claim, heartbeat,
checkpoint i zakończenia. Handler wykonuje pracę poza transakcją, a fencing
token jest weryfikowany przy każdej mutacji. Domyślny lease trwa 60 sekund.
Worker można uruchomić jednorazowo albo w pętli:

```powershell
npm run worker:once
npm run worker:poll
```

Worker `worker-v4` rejestruje handlery `import`, `validate`, `payout-v2` oraz nadrzędny
`android_build`. Import odczytuje plik w bounded partiach, zapisuje surowy
staging przed checkpointem i weryfikuje pełny checksum przed oraz po
przebiegu. Wariant `validate/layout_import` normalizuje zakończony staging
partiami po 1000 względem opublikowanych reguł i zapisuje wynik przed
checkpointem. Handler build wykonuje rewalidację, payouty, snapshot i kontrolowany
Android build w jednym jobie, z zagnieżdżonym checkpointem payoutu per gra.

M7.1 dodaje generyczny `ImageBatchHandler` i trwałe file executions. TASK-0070
dodaje prawdziwy seeder discovery, composer sześciu portów oraz projekcję do
review/staging. TASK-0071 domyka izolację błędów, selektywny retry, rehydratację
globalnych wyników i job-local review. TASK-0072 dodaje typowane endpointy
statystyk i retry pliku, wygenerowany klient OpenAPI oraz szczegóły image joba
w istniejącym ekranie Jobs. Orkiestracja korzysta z istniejącego globalnego
`execution_slot = 1`; nie dodaje kolejki, procesu ani zależności.

TASK-0073 używa wyłącznie standardowych `pathlib`, `os`, `hashlib`, `json` i
`tempfile`. Nie dodaje object storage ani zależności. Admin API skanuje tylko
`<artifact-root>/data/{originals,working,crops,training,models,exports}`, nie
podąża za symlinkami, a eksporty diagnostyczne publikuje atomowo przez
tymczasowy plik i hard link bez nadpisania istniejącego celu.

TASK-0074 nie dodaje technologii runtime. Benchmark wykorzystuje istniejące
SQLAlchemy/Alembic/PostgreSQL oraz lokalny filesystem, tworzy wyłącznie
unikalną tymczasową bazę i ma wewnętrzny deadline oraz zewnętrzny timeout
PowerShell. Rejestracja wsadowa po 500 jest optymalizacją istniejącego
repozytorium, a nie nowym systemem kolejkowym.

TASK-0075 również nie dodaje zależności ani procesu. Kontrolowane awarie,
restart i review throughput są mierzone na istniejących
`ImageBatchHandler`, repozytoriach SQLAlchemy i PostgreSQL. Raport jakości
odczytuje checksum-bound artefakty M5/M6; synthetic fixture służy wyłącznie do
pomiaru persistence i nie zastępuje ONNX/held-out quality gate.

TASK-0077 utrwala istniejący stos jako decyzję finalną M7: PostgreSQL jest
trwałą kolejką lokalnych jobów, a Python worker pozostaje pojedynczym
wykonawcą. Redis, Celery, broker i mikroserwisy nadal znajdują się w sekcji
świadomie odłożonych technologii. Zmiana wymaga spełnienia mierzalnego warunku
D-085, nowego benchmarku i osobnego ADR.

Domyślnie zapisuje audyty i niezmienne artefakty w `artifacts/`; alternatywny
katalog można wskazać:

```powershell
.venv\Scripts\python.exe -m game_predictor_worker --artifact-root D:\game-predictor-artifacts
```

Admin API musi rozwiązywać pobierane APK względem tego samego katalogu. Dla
niestandardowej lokalizacji należy uruchomić je z:

```powershell
$env:GAME_PREDICTOR_ARTIFACT_ROOT = 'D:\game-predictor-artifacts'
npm run api:dev
```

API nie przyjmuje ścieżki artefaktu od panelu; identyfikator release prowadzi do
niezmiennej ścieżki zapisanej po weryfikacji workera.

Ręczne pliki layoutów są umieszczane w oddzielnym lokalnym katalogu wejściowym.
Domyślna konfiguracja oraz przykład PowerShell:

```powershell
$env:GAME_PREDICTOR_IMPORT_ROOT = 'D:\game-predictor-imports'
$env:GAME_PREDICTOR_IMPORT_MAX_BYTES = '1073741824'
npm run api:dev
```

Klient podaje ścieżkę względną pod tym rootem. API używa standardowych
`pathlib`, `hashlib` i parserów CSV/JSON z biblioteki standardowej; TASK-0044
nie dodaje zależności ani uploadu HTTP. Worker używa tego samego
`GAME_PREDICTOR_IMPORT_ROOT` i limitu, a trwały staging zapisuje w PostgreSQL.

Brak handlera kończy przejęty job kodem
`JOB_HANDLER_NOT_REGISTERED`; nie pozostawia zajętego slotu.

Panel nie wykonuje dowolnych komend podanych przez użytkownika. Zleca typowane
zadanie, a worker uruchamia jeden wersjonowany workflow build. Obowiązuje lokalny
Gradle/Expo Android build bez zależności od chmurowej usługi buildowej.
Adapter zawsze uruchamia wariant Release dla `arm64-v8a`, przypięte skrypty
PowerShell oraz istniejący audyt podpisu, uprawnień i zawartości APK. Gotowy APK
jest publikowany jako
`android-releases/<releaseVersion>/app-release-<apkSha256>.apk`, bez
nadpisywania historycznej zawartości.

Bootstrap M1 potwierdził lokalny workflow Windows:

- Microsoft OpenJDK 17,
- Android SDK Platform i Build Tools 36,
- przyrostowy `expo prebuild --no-clean`; pełne czyszczenie wyłącznie na jawne
  żądanie operatorskie,
- przypięty Gradle wrapper,
- domyślny prywatny build urządzeniowy `arm64-v8a`.

Kanoniczny skrypt builda ma własne limity: 5 minut dla Expo prebuild i 30 minut
dla Gradle. Po przekroczeniu limitu kończy całe drzewo procesu, aby kolejna próba
nie konkurowała z osieroconym Gradle, Kotlin albo Ninja. Gradle działa bez
równoległości, z jednym workerem i kompilatorem Kotlin w tym samym procesie;
natywny CMake ma domyślnie najwyżej dwa równoległe zadania. Ustawienia Gradle są
również generowane przez plugin Expo `with-bounded-android-build`, więc pozostają
aktywne po odtworzeniu katalogu `android`. Skrypt wywołuje wyłącznie
`:app:assembleRelease`, bez zbędnego składania publikowalnych AAR-ów bibliotek.

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
- Pillow `12.3.0`,
- `opencv-python-headless` `4.13.0.92`,
- NumPy `2.4.6`,
- PaddlePaddle CPU `3.3.1` z oficjalnym modelem recognition-only
  `en_PP-OCRv5_mobile_rec`,
- PyYAML `6.0.3` do odczytu kontraktu lokalnego modelu,
- PyTorch `2.12.1` i torchvision `0.27.1` CPU do treningu,
- ONNX `1.22.0` i ONNX Script `0.7.1` do aktualnego eksportera
  `torch.export` z opset 18 oraz ONNX Runtime CPU `1.28.0` do lokalnej
  inferencji.

Geometria, OCR i klasyfikator implementują osobne porty. Dla prototypu
geometrii przypięto dojrzałą linię OpenCV 4.13 zamiast świeżego major 5, aby
nie łączyć zmiany kontraktu biblioteki z eksperymentem algorytmicznym. Zgodnie
z D-055 adapter OCR używa bezpośrednio lokalnych plików Paddle Inference,
ponieważ pakiet PaddleOCR/PaddleX wymuszał konfliktujące wersje OpenCV i NumPy.
Dekoder dopuszcza wyłącznie cyfry, lecz model pozostaje wymienny. Finalny model
OCR nie został zatwierdzony: wynik 63.8243% na 387 pozycjach utrzymuje go w
trybie `manual_review_only`, ale nie blokuje eksportu przejrzanych cropów
symboli w M6.

### Status po benchmarku M5

| Element | Status | Obowiązująca granica |
|---|---|---|
| Python/Pillow/OpenCV/NumPy | `retain` | lokalny worker i deterministyczne artefakty |
| `image-discovery-v1` | `retain` | wejście JPEG, ścieżki względne i SHA-256 |
| `image-normalization-v1` | `retain` | EXIF Orientation 1–8 i RGB PNG |
| `page-board-detector-v2` | `retain` | jawne 1–9 pozycji, recovery tylko z expected count i dowodem ramki |
| `board-cell-crops-v1` | `retain` | oczekiwane 1–9 layoutów, plansze 3 × 5 |
| `SequenceNumberRecognizer` / raport OCR | `retain` | wymienny port, raw/normalized/confidence bez korekty |
| `en_PP-OCRv5_mobile_rec` + obecny preprocessing | `manual_review_only` | sugestia do review, brak auto-accept |
| `m5-image-benchmark-v2` | `retain` | 43 zdjęcia, 387 pozycji, geometria i held-out OCR |

D-057 nie dodaje kolejnej biblioteki ani finalnego modelu. OCR nie osiągnął
progu 98%, dlatego auto-accept pozostaje wyłączony. M6 korzysta z
automatycznych cropów i przejrzanych etykiet, a nie z niepewnego OCR.

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

### Trwałe środowisko Windows

Referencyjny lokalny toolchain nie zależy od cache procesu Codex. Node i npm
znajdują się w `.tooling/node`, a JDK oraz Android SDK w istniejących katalogach
`.tooling/jdk` i `.tooling/android-sdk`. Konfigurację użytkownikowego `PATH`,
`JAVA_HOME`, `ANDROID_HOME`, `ANDROID_SDK_ROOT`,
`GAME_PREDICTOR_NODE_HOME` i krótkiego cache Gradle wykonuje:

```powershell
npm run windows:environment:setup
```

Skrypt jest idempotentny, deduplikuje wpisy `PATH`, waliduje zakresy wersji
z `package.json` i nie zmienia zmiennych na poziomie całego komputera.
`npm run windows:environment:check` odczytuje zapisany profil użytkownika, a nie
tylko zmienne odziedziczone przez bieżący terminal. Zmiana polityki wykonywania
PowerShell pozostaje oddzielną, opcjonalną decyzją operatorską.
Instrukcje operacyjne znajdują się w
`ai_docs/guides/LOCAL_OPERATION_GUIDE.md`.

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
