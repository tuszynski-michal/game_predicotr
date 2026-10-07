---
title: Plan przyspieszenia raportów importu i izolacji między grami
status: proposed
last_updated: 2026-10-07
---

# Plan przyspieszenia raportów importu i izolacji między grami

Plan dotyczy przycisku „Pokaż raport”, listy wgranych folderów i kosztu
odczytów przy rozwoju jednej oraz wielu gier. Celem jest szybkie otwarcie
raportu bez ponownego przetwarzania całej geometrii i zdjęć. Pełna kontrola
integralności pozostaje warunkiem uruchomienia importu.

**Status: propozycja do oceny użytkownika i Claude Code.** Audyt projektu:
`gpt-6-astra`, reasoning `high`. Zlecenie przygotowania tego dokumentu nie
uruchamia jego implementacji, migracji ani wdrożenia. TASK-09111–09118 poniżej
są proponowanymi zadaniami; przed uruchomieniem trzeba sprawdzić kolizje numerów.

## Stan obecny i dowody

Pomiary z 2026-10-07 wykonano na istniejących plikach Mumii, bez bazy danych.
API na 8000 i PostgreSQL na 5432 były niedostępne. Są to pomiary składników,
nie czasu całego żądania HTTP ani renderowania przeglądarki.

| Składnik                                           | Zmierzony wynik                                        |
| -------------------------------------------------- | ------------------------------------------------------ |
| Manifest geometrii                                 | 270 978 264 bajty, 2575 zdjęć, 23 175 wykrytych plansz |
| Odczyt i pełna walidacja manifestu                 | 19,870 s                                               |
| Sam odczyt pliku / parsowanie JSON                 | 0,176 s / 2,283 s                                      |
| Pierwsza walidacja propozycji                      | 8,660 s                                                |
| Walidacja powiązań z powtórną walidacją propozycji | 8,570 s                                                |
| Pozostałe sprawdzenia manifestu                    | około 0,180 s                                          |
| Ponowne hashowanie 2575 JPEG-ów                    | 3,606 s; 784 252 248 bajtów                            |

23 175 oznacza wykryte plansze w artefakcie, nie liczbę już zaimportowanych
rekordów. Wyizolowane koszty dają około 23,5 s przed pozostałą pracą API.
Nie dowodzą, że baza odpowiada za zgłaszane 30–60 s.

Pozostałe potwierdzone przyczyny:

- Lista folderów przegląda globalny katalog i odczytuje stan każdego folderu;
  Admin filtruje gry dopiero po odpowiedzi.
- Współdzielony singleton `BrowserImageSelectionService` trzyma globalny
  `Lock` podczas sprawdzania wszystkich zdjęć jednego folderu.
- Preflight kanoniczności pobiera wszystkie numery i checksumy jednej gry,
  zamiast zakresów badanego folderu.
- Replay importu/preflightu przegląda do 10 000 jobów gry i filtruje je w Pythonie.
  Ten limit może też pominąć starszy, właściwy job.
- Ten sam preflight geometrii jest wyszukiwany ponownie w jednym odczycie raportu.

Źródła pomiarów:

- [findings.json](C:/Users/tuszy/Documents/game_predicotr/artifacts/report-audit-20261007/findings.json)
- [manifest-measurement.json](C:/Users/tuszy/Documents/game_predicotr/artifacts/report-audit-20261007/manifest-measurement.json)
- [staging-measurement.json](C:/Users/tuszy/Documents/game_predicotr/artifacts/report-audit-20261007/staging-measurement.json)

Artefakty pomiarowe są lokalne i ignorowane przez Git. Wyniki potrzebne do
oceny planu zapisano również powyżej. Nie wykonano benchmarku 20 folderów.

## Zakres i warunki ochrony danych

W zakresie: trwałe metadane raportu, małe indeksy źródeł i zakresów, odczyt
szczegółów na żądanie, zapytania ograniczone do folderu/gry, izolacja blokad,
zgodny pion backend → OpenAPI → klient → Admin i testy restartu.

Poza zakresem: trening i aktywacja modeli, zmiana progów rozpoznawania,
supersymbol, usuwanie starych silników/danych, sprzątanie dysku, Redis/Celery,
nowe mikroserwisy, zmiana globalnej liczby równoległych importów.

Obowiązują następujące reguły:

1. `sequence_number` i pochodzenie zdjęcia pozostają częścią domeny. Indeksy
   raportu nie mogą zmieniać zakresów, numeracji ani właściciela kanonicznego.
2. Historyczny, ukończony preflight pozostaje przypięty do swojej gry,
   selekcji, manifestu, modelu i polityki. Korekta innego źródła i zmiana
   game-wide profilu nie unieważniają go automatycznie.
3. Metadane raportu nie autoryzują importu ani treningu. `/start` zachowuje
   dokładną walidację źródeł, geometrii, widoczności komórek, rewizji,
   wykluczeń, modeli, fingerprintów, guardów i idempotencji.
4. Utworzenie joba oraz przejście stagingu do `in_use` pozostają jedną
   transakcją. Nie dodawać pośredniego commita w sesji z RLS.
5. Game-owned dane korzystają z `GameStorageRouter`, istniejących partycji
   i RLS. Historyczne stagingi bez `game_id` pozostają w `public`;
   odczyt nie odgaduje ich właściciela i nie zapisuje przypisania.
6. Zdjęcia pozostają plikami. Nowe metadane zawierają ścieżki, SHA-256,
   małe liczniki i wersje, nie JPEG-y ani geometrię każdej komórki w tabeli katalogu.
7. Migracje wyłącznie Alembic. Wykonanie migracji na bazie użytkownika,
   odbudowa zapisująca artefakty i wdrożenie wymagają osobnego sygnału.
8. Nie przerabiać całego schematu bazy bez pomiarów. Partycjonowanie daje
   izolację logiczną; nie gwarantuje izolacji wspólnego CPU, dysku ani kolejki.

## Zalecany przepływ raportu

```text
finalize uploadu
  -> istniejący manifest źródeł + mały source/range index + metadane katalogu
preflight geometrii uruchomiony jawnie
  -> dotychczasowy dokładny manifest + geometry summary + szczegóły per źródło
Pokaż raport
  -> mały overview natychmiast
  -> osobno doładowane aktualne liczniki kanoniczności, bez zdjęć/geometrii
Otwórz konkretne źródło
  -> indeks + zweryfikowany fragment szczegółów tego źródła
Uruchom import
  -> istniejący exact preflight i pełne guards -> atomowy job + in_use
```

To jeden zalecany projekt. Trwałe podsumowanie przechowuje niezmienny wynik
geometrii. Dynamiczne liczniki kanoniczności są liczone z aktualnych danych
wybranego folderu, bez trwałego cache wymagającego globalnej invalidacji.

### Tożsamość i aktualność

Proponowany `reportDescriptor` wiąże:
`schemaVersion`, `gameId`, `sourceSelectionId`, `sourceManifestSha256`,
`selectionRevision`, a dla geometrii także `geometryJobId`, numer próby,
`geometryManifestSha256`, przypięty model/politykę i SHA małego indeksu.

Są dwie niezależne osie:

| Oś                        | Źródło prawdy                                                                    | Zachowanie                                              |
| ------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------- |
| Historyczna geometria     | Przypięty manifest/job i descriptor                                              | Używalna mimo późniejszej zmiany globalnego profilu gry |
| Bieżąca możliwość importu | Aktualne źródła, lifecycle, wykluczenia, właściciele canonical, model i polityka | Sprawdzana ponownie w exact preflight i `/start`        |

Dynamiczne liczniki mają `observedAt` i tożsamość analizowanej selekcji.
Są informacją o stanie w chwili odczytu. Jednakowe liczniki nie oznaczają
jednakowych właścicieli. Obecna checksuma exact preflightu opiera się na
scalarach; nie wykrywa każdej podmiany właściciela przy jednakowych licznikach.
Plan zachowuje tę semantykę oraz dotychczasową ochronę kanoniczności workera.
Nie wprowadza nowego digest/CAS całej mapy właścicieli w `/start`.

### Artefakty i atomowa publikacja

Nowe formaty i symbole w tej sekcji są **proponowane**:

- `browser-report-source-index-v1` powstaje przy finalize, bez inferencji.
  Zawiera zakresy z nazw/manifestu, first/last, liczby/bytes, identyfikatory
  źródeł oraz dotychczasowe `skippedCanonicalRanges`.
- `geometry-report-summary-v1` powstaje z już zwalidowanego wyniku workera.
  Zawiera liczniki stanów, descriptor i wskaźniki szczegółów. Nie zawiera
  wszystkich quadów, proposal payloadów ani kopii manifestu 271 MB.
- Szczegóły geometrii zapisuje się osobno per źródło. Lookup używa
  małego, checksumowanego indeksu; stronicowanie odpowiedzi nie może
  poprzedzać odczytu całego monolitu.
- Wersje, SHA-256 i ścieżki trafiają do istniejącego rekordu retention oraz
  checkpointu joba. Rozszerzenie metadanych nie tworzy równoległego katalogu.

Budżety proponowane do testów: root maks. 64 KiB; indeks 256 bucketów według
prefiksu SHA źródła; katalog bucketu maks. 2 MiB; strona indeksu maks. 128
źródeł i 256 KiB; fragment szczegółów maks. 2 MiB. Większe poprawne źródło
dzieli się na deterministyczne fragmenty, zamiast obcinać wynik. Odczyt strony
szczegółów obejmuje najwyżej 20 źródeł i ma limit odpowiedzi 4 MiB.
Zakresy przetwarza się strumieniowo w paczkach maks. 1000, do istniejącego
limitu `MAX_PREFLIGHT_FILES = 1_000_000`, bez materializacji miliona rekordów
w jednej kolekcji. Limit struktur/bytes sprawdza się przed parsowaniem.

Publikacja:

1. Zapis do plików tymczasowych w dozwolonym katalogu artefaktów.
2. Walidacja zawartości/rozmiaru i SHA każdego fragmentu; deterministyczna kolejność.
3. Atomic rename do niezmiennych ścieżek content-addressed. Istniejący plik
   o tej nazwie musi mieć oczekiwane bytes/SHA; nie nadpisywać innej zawartości.
4. Krótka transakcja publikuje pointer po sprawdzeniu gry, próby joba,
   input descriptor i rewizji selekcji. `ready` oznacza kompletny zestaw.
5. Crash przed pointerem pozostawia nieopublikowane pliki. Retry z tą samą
   tożsamością je weryfikuje i wykorzystuje. Nie uruchamia kolejnej inferencji.

Ukończenie dotychczasowego dokładnego preflightu nie może zależeć od sukcesu
pomocniczej projekcji. Jej błąd pozostawia exact artifact używalny i jawny
stan `unavailable` podsumowania. Nie publikować częściowego summary jako ready.
Stare manifesty pozostają bez zmian. Jawna, idempotentna akcja przygotowania
indeksu starego raportu korzysta z istniejącego mechanizmu jobów/checkpointów;
nie przelicza modelu. Zwykłe otwarcie raportu nie tworzy joba.

### Katalog folderów i izolacja

Rozszerzyć `BrowserSelectionRetentionModel` o nullable metadane starych
rekordów: purpose, liczby plików/bytes, source-index descriptor, revision,
replacement/current oraz opis operacji w toku. Stan geometrii odczytywać
zbiorczo przez bezpośredni lookup jobów. Katalog jest w istniejącym magazynie
gry; globalne, nieprzypisane stagingi zachowują dotychczasową własność.

Lista Admina korzysta z SQL z `game_id`, purpose i keyset cursor
`(finalized_at DESC, upload_id ASC)`, limit domyślny 50, maks. 200.
Przy dodaniu kolejnego folderu kursor nie duplikuje starych pozycji. Zmiana
gry zeruje kursor i odrzuca spóźnione odpowiedzi.

Page envelope zawiera osobny, również stronicowany `legacyUnknownMetadata`
bucket: wyłącznie rekordy danej gry z `purpose IS NULL` lub brakującym
source-index descriptor. Jego karty mają akcję odzyskania metadanych i nie
deklarują gotowości importu. Każdy bucket ma własny cursor; łączny limit
odpowiedzi nadal maks. 200. Nie przypisywać NULL purpose na podstawie nazwy.

Nie iterować po dyskowych folderach innych gier. Odczyt listy nie hashuje JPEG-ów.
Retained staging, którego browserowy katalog zniknął po poprawnym handoffie,
pozostaje dostępny przez descriptor managed originals. Legacy/unbound
odzyskiwanie jest osobną, jawną akcją; GET nie skanuje całego dysku i nie przypisuje gry.

### Zapytania i walidacja

- Nowe zapytanie kanoniczności przyjmuje wyłącznie zakresy wybranego folderu,
  także skipped/confirmed neural ranges i aktualne wykluczenia. SQL filtruje
  grę przed agregacją; zwraca liczniki lub potrzebnych właścicieli, nie całe
  ORM-y gry. Paczki nie przekraczają 1000 zakresów. Scalone zakresy zachowują
  semantykę alternatyw i pochodzenie. Pełny zestaw liczników powstaje po
  przetworzeniu wszystkich paczek w jednym spójnym snapshotcie read-only.
- Dla normalnego folderu zakresy przekazać do jednego statementu SQL;
  większe indeksy obsłużyć paczkami w krótkiej transakcji read-only
  repeatable-read. Przed transakcją zwalidować root i descriptor niezmiennego
  indeksu; strony wcześniej opublikowanego indeksu czytać przez bounded
  iterator. Nigdy nie materializować wszystkich zakresów w kolekcji.
  Transakcja nie odczytuje JPEG ani monolitu; tylko ograniczone strony
  niezależnie checksumowanego range indexu. Cała operacja
  ma deadline 10 s, pojedynczy statement 5 s; limity chronią zasoby, a nie
  zastępują optymalizacji. Nie dodawać durable canonical-report joba.
- Dynamiczny odczyt jest osobnym żądaniem doładowującym raport. Root nie czeka
  na jego ukończenie. Koszt rośnie z wybranym folderem, nie historią wszystkich gier.
  Nie zostawiać dużych folderów z permanentnym `null`: błąd jest widoczny,
  retry jest możliwy, a niespełniony budżet czasu blokuje odbiór skalowania.
- Dotychczasowe `canonical_numbers`/`canonical_source_checksums` zachowują
  zachowanie innych konsumentów, m.in. checksum planera uploadu. Dodać węższe
  metody raportu, zamiast globalnie zmieniać semantykę tych metod.
- Lookup joba filtruje SQL po game, type i właściwej tożsamości źródła oraz
  manifestu **przed** LIMIT. Zachowuje kolejność `created_at DESC, id ASC`.
  Odpowiedni fingerprint/wariant sprawdza domena na strumieniu kandydatów;
  nie pomija najnowszego `failed`/`running` na rzecz starszego `completed`.
- W jednym żądaniu ponownie wykorzystać znaleziony job i zwalidowany snapshot.
  Raw validators nadal sprawdzają wszystkie wejścia na granicy zaufania.
  Proponowany `ValidatedNeuralSource` jest głęboko niezmienny; sam `frozen`
  dataclass z mutable dict/list albo parametr `trusted=True` nie wystarczy.
- Indeksy SQL dobierać po bounded `EXPLAIN (ANALYZE, BUFFERS)` na istniejących
  danych. Nie deklarować partition pruning ani skuteczności nowego indeksu
  bez wyniku. Zmiany schematu/indeksów są additive i testowane na izolowanej bazie.

First/last w overview mają proponowane nazwy `sourceFirstSequenceNumber` /
`sourceLastSequenceNumber`. Canonical response oddzielnie podaje
`firstUnresolvedSequence` / `lastUnresolvedSequence` zgodnie
z dotychczasowym exact kontraktem. Nie podstawiać całego zakresu źródeł za
zakres faktycznie brakujących numerów.

### Blokady i restart operacji na plikach

Usunąć globalną blokadę z kosztownych operacji. Jedna **exclusive systemowa
blokada pliku na UUID selekcji** chroni source-IO i mutacje tego
folderu w API, workerze oraz GC. Overview i lista czytające tylko metadane
nie pobierają tej blokady. Inne foldery i gry nie czekają na ten sam lock.

Proponowany adapter `BrowserSelectionOperationLock` używa stabilnego pliku
`<wspólny browser-staging-root>/.browser-selection-locks/<uuid>.lock`, poza
drzewem selekcji podlegającym rename/delete. Na Windows blokuje bajt 0 przez
`msvcrt.locking(..., LK_NBLCK, 1)`, utrzymując otwarty uchwyt przez całą
operację, również jej transakcje DB i cleanup w finally. Lockfile nie wolno
unlinkować, zastępować ani usuwać przez GC. Ścieżka jest kanonizowana,
bez symlink/reparse traversal. Przykład istniejącego mechanizmu: S11.

Próby mają deadline 2 s i krótki polling; brak locka zwraca konflikt/busy.
Maks. 4 aktywne konteksty per proces; nasycenie zwraca retryable busy.
Przy wielu UUID kolejność rosnąca UUID. Nie oczekiwać na lock z otwartą
transakcją/row lock. Zagnieżdżone wywołania przekazują wewnętrzny kontekst
już posiadanego locka; nie próbują ponownego zdobycia tej samej blokady.

Zakres to aktualna lokalna instalacja Windows: wszystkie API/worker/GC na
jednym hoście i tej samej lokalnej przestrzeni plików. Startup/odbiór muszą
potwierdzić wspólny root i dwuprocesową wyłączność. Inny host, SMB lub mieszane
Windows/Linux na wspólnym mount wymagają odrębnego projektu; konfiguracja
niezweryfikowana odmawia operacji źródłowych, nie przechodzi do no-op locka.
Nie dodawać advisory lock jako drugiej, rozbieżnej ochrony.

Wszystkie czytania/hashowanie źródeł, rename/replace/cancel, finalize,
start/handoff oraz fizyczne GC uczestniczą w tym samym protokole. Start
utrzymuje lock do końca istniejącej atomowej transakcji job + `in_use`.
Po przejściu do `in_use` istniejące trwałe zależności blokują delete.
Nie rozszerzać locka na całą grę, nie zwiększać liczby workerów.

Utrata połączenia DB unieważnia wynik sprawdzeń, ale nie zwalnia systemowego
locka procesu. Drugi proces nie może wejść do filesystemu przed zakończeniem
cleanup/abort pierwszego. Przed publikacją wymagany CAS rewizji/lifecycle.
Retry rozpoczyna pełną walidację od nowa. `finally` wykonuje unlock i zamyka
uchwyt; śmierć procesu zwalnia lock w systemie. Nie zamykać uchwytu wcześniej
na ścieżce błędu DB. Uchwytu locka nie używa się do odczytu/zapisu JPEG-ów.

`pendingOperation` zawiera operationId, kind, expected/next revision,
obie zweryfikowane bezpieczne ścieżki, descriptor i phase. Zapis intencji
oraz CAS lifecycle poprzedzają efekt na filesystemie. Recovery pod tym samym
lockiem kończy albo odtwarza wyłącznie tę operację. W stanie niejednoznacznym
ustawia blocked; nie usuwa danych na podstawie samego braku katalogu.

Szczególnie `cancel()` musi sprawdzić zależności i prawo usunięcia **przed**
rename katalogu. To naprawa kolejności bezpieczeństwa, nie zgoda na wykonanie
kasowania istniejących stagingów. Legacy selekcje bez rekordu DB korzystają
z tego samego UUID locka; ich recovery wymaga jawnego ustalenia własności.

## Kontrakt API i zachowanie Admina

Rozszerzyć istniejące operacje, zachowując domyślny kontrakt legacy:

| Operacja                                     | Rozszerzenie proponowane                                                      | Kompatybilność                                                  |
| -------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------- |
| GET browser-selections                       | `view=page`, wymagane gameId, purpose, limit, cursor → osobny envelope        | Brak view nadal zwraca istniejącą tablicę                       |
| POST browser-selections/{id}/preflight       | `view=overview` → osobny discriminated response; `view=canonical` → scalars   | Brak view / `exact` zachowuje pełny istniejący response         |
| POST browser-selections/{id}/preflight       | Jawne przygotowanie brakującej projekcji: `view=prepare-report` → job receipt | Nie uruchamia geometrii ani importu; idempotentne po descriptor |
| Istniejący endpoint szczegółów source review | Opcjonalny tryb/cursor szczegółów z indeksu                                   | Domyślny workflow korekty bez zmiany                            |
| POST browser-selections/{id}/start           | Dotychczasowy exact + guards                                                  | Nie przyjmuje overview jako zgody/checksumy preflightu          |

Nowe typy są propozycją: `BrowserImportOverviewResponse`,
`BrowserImportCanonicalSummaryResponse`, `BrowserReadySelectionPageResponse`.
Overview ma discriminator `view=overview`, descriptor, stan projekcji,
źródła/bytes, zakres first/last, geometry job/status i historyczne liczniki.
Nie posiada `preflightChecksumSha256`, `artifactReady` ani `importReady`.
Niehashowana informacja o modelu z registry nie oznacza zweryfikowanej gotowości.

Pola niewiadome są nullable i mają jawny powód/status. Root przed pierwszym
preflightem pokazuje istniejące metadane źródeł i akcję „Uruchom preflight”.
Przed ukończeniem canonical request pokazuje „Sprawdzanie numerów”; po sukcesie
komplet nowych/użytych numerów, alternatyw, first/last. Brak danych nie jest zerem.

Kliknięcie „Uruchom import” wykonuje dokładny preflight, pokazuje rozbieżności
z odczytanym wcześniej raportem i dopiero korzysta z istniejącego `/start`.
Spóźniona odpowiedź nie nadpisuje nowszego folderu/gry. Anulowanie zamyka tylko
odczyt UI, nie job. Błąd szczegółów lub canonical nie blokuje przeglądania listy.
UI nie wprowadza timeoutu jako substytutu usunięcia kosztownych odczytów.

### Kontrakt przygotowania projekcji legacy

Reuse istniejącego `JobType.VALIDATE`, z nowym proponowanym
`validation_kind = browser_import_report_projection`. Nie dodawać wartości
do enum job_type ani osobnej kolejki. Istniejący dispatch S12 otrzymuje
opcjonalny handler; dotychczasowe typy walidacji pozostają bez zmian.

Input, zapisany przez serwer po sprawdzeniu własności:

```text
schema_version = 1
validation_kind = browser_import_report_projection
report_policy_version = browser-import-report-projection-v1
game_id, source_selection_id, selection_revision
source_manifest_checksum_sha256
source_kind = browser_staging | managed_originals
managed_manifest_descriptor = {relative_path, checksum_sha256} | null
geometry_descriptor = {job_id, attempt, manifest_relative_path,
                       manifest_checksum_sha256, pinned_input_checksum_sha256} | null
report_schema_versions = {source_index: 1, geometry_summary: 1, details: 1}
```

Gdy nie ma ukończonej geometrii, job przygotowuje tylko source index. Nie
udaje wyniku modelu. Pola `geometry_descriptor` wskazują wyłącznie faktycznie
ukończony zgodny job. Ścieżki rozwiązuje serwer z bezpiecznych descriptorów,
nie dowolny payload klienta. Tożsamość ma `game_id` także poza input,
zgodnie z istniejącym `job_input_key` i `_persist_job`. Fingerprint obejmuje
cały powyższy input w canonical JSON, bez actor/time/losowego nonce.
Powtórne prepare odtwarza ten sam job; terminalne failed/cancelled używa
istniejącego retry, bez zmiany wejścia. Rewizja/format zmienione = nowa tożsamość.

Checkpoint ma fazy `source_index`, `source_details`, `summary`, `publish`;
przechowuje pełny input digest, last_source_key, checksumowane strony/fragmenty
oraz descriptor gotowy do publikacji. Dużej geometrii nie trzyma w checkpoint
JSON; używa istniejącego durable storage. Retry odtwarza sprawdzone fragmenty
tej samej tożsamości i wznawia deterministycznie. CAS przed pointerem nadal
obowiązuje. Utworzenie joba i durable source dependency/pin są jedną
transakcją; GC nie usuwa wejść queued/running. Release pin po zakończeniu
zachowuje istniejące managed history/retention i nie usuwa danych.

## Błędy i ponowienia

Kody/statusy nieobecne w kodzie są poniżej **proponowane**. Istniejących
kodów exact walidacji nie mapować na ogólne „brak raportu”.

| Warunek                                    | Zasięg i zapis                                                                 | UI / następny krok                                                |
| ------------------------------------------ | ------------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| Brak projekcji legacy                      | Overview `missing`, liczniki geometrii null; bez zapisu GET                    | Podstawowy raport dostępny; jawne „Przygotuj szczegóły raportu”   |
| Nieobsługiwana wersja                      | `incompatible`, bez odczytu monolitu                                           | Odbudowa projekcji pod nową wersją; exact workflow pozostaje      |
| Zły SHA / niepełny zestaw plików           | `corrupt`, bez publikacji częściowej                                           | Widoczny błąd; przygotowanie ponownie, nie zerowe liczniki        |
| Zmieniona rewizja selekcji / CAS           | `IMAGE_BROWSER_REPORT_REVISION_CONFLICT`; bez commit/publikacji                | Odśwież konkretny folder; historyczny wynik pozostaje             |
| Folder zajęty / limit lock connections     | `IMAGE_BROWSER_SELECTION_BUSY`; nic nie zmieniać                               | Krótkie retry ręczne z Retry-After, inne foldery dostępne         |
| Utrata odpowiedzi prepare                  | Idempotency po pełnym descriptor                                               | Retry zwraca ten sam job/projection, bez duplikatu                |
| Utrata połączenia DB                       | Operacja nie może publikować; OS lock pozostaje do abort; intencja do recovery | Retry od pełnego wejścia, bez użycia starego validated result     |
| Brak filesystem staging po managed handoff | Nie oznaczać usunięcia                                                         | Odczyt przez zweryfikowaną managed identity                       |
| Legacy bez właściciela                     | Oddzielna lista odzyskiwania, GET read-only                                    | Jawne przypisanie, nigdy zgadywanie gameId                        |
| API/DB niedostępne                         | Nie zapisywać gotowości ani sukcesu                                            | Oddzielny błąd/ponów; bez automatycznego restartu usług           |
| Błąd zapytania/liczników                   | Canonical state `error`, historyczna geometria dostępna                        | Ponów odczyt; exact nadal chroniony, brak cichego partial success |

## Zadania według zależności

Każde zadanie otrzyma osobny plik według TASK_TEMPLATE, niezależny review,
commit i Outcome. Poniższe opisy definiują projekt; pole Outcome pozostaje
do wypełnienia podczas przyszłej implementacji. Wspólne Relevant docs:
[AGENTS.md](C:/Users/tuszy/Documents/game_predicotr/AGENTS.md),
[PLAN_STANDARD.md](C:/Users/tuszy/Documents/game_predicotr/ai_docs/process/PLAN_STANDARD.md),
[CURRENT_STATE.md](C:/Users/tuszy/Documents/game_predicotr/ai_docs/process/CURRENT_STATE.md),
[IMAGE_INGESTION.md](C:/Users/tuszy/Documents/game_predicotr/ai_docs/requirements/IMAGE_INGESTION.md),
[API_CONTRACT.md](C:/Users/tuszy/Documents/game_predicotr/ai_docs/architecture/API_CONTRACT.md),
[DATA_MODEL.md](C:/Users/tuszy/Documents/game_predicotr/ai_docs/architecture/DATA_MODEL.md),
[GAME_DATA_V2_OWNERSHIP.md](C:/Users/tuszy/Documents/game_predicotr/ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md),
[DEFINITION_OF_DONE.md](C:/Users/tuszy/Documents/game_predicotr/ai_docs/process/DEFINITION_OF_DONE.md).

### TASK-09111 — Pomiar zapytań i kontraktu kosztu odczytów

**Status:** proposed/todo. **Goal:** ustalić baseline oraz mierzalne granice
bez odczytywania zdjęć w docelowym raportowaniu.

**Context / Dependencies:** istniejące pomiary plików powyżej; zaakceptowany
plan. Live SQL wymaga dostępnej bazy i usług; brak usług nie upoważnia do restartu.

**Recommended execution:** `gpt-6.1-sol / medium`; analiza ograniczona do
istniejących odczytów. Eskalacja do `gpt-6-astra / high` przy zmianie ochrony danych.

**Scope / Technical notes:** max. trzy odczyty istniejącego folderu w nowym
procesie; policzyć odczytane bytes/pliki, parser calls, zwrócone SQL rows i
roundtrips. Rozdzielić root, canonical, details i exact. SQL READ ONLY,
statement timeout 5 s, cały krok 120 s; bounded EXPLAIN tylko SELECT na
istniejących danych. Brak miliona sztucznych rekordów. Wybrać indeksy dopiero
po planie wykonania. Niedostępny SQL = jawny brak dowodu, nie wynik pozytywny.

**Expected files:** zweryfikowane punkty S1–S6 w mapie poniżej; proponowany
`C:/Users/tuszy/Documents/game_predicotr/scripts/verify_import_report_reads.py`
do instrumentacji read-only, z jawnym timeoutem i trybem bez produkcyjnych zapisów.

**Acceptance / Test cases:** instrumentacja wykrywa odczyt JPEG/monolitu i
globalne query/list scans; raport rozdziela pomiary od celów. Wynik nie twierdzi
o użyciu indeksu bez EXPLAIN. **Verification:** V1 oraz bounded instrumentacja.
**Out of scope:** naprawa kodu i wykonywanie migracji. **Risks:** offline DB
blokuje dowód SQL i późniejszy odbiór SLA, nie projekt pozostałych modułów.
**Outcome:** do wypełnienia przy wykonaniu.

### TASK-09112 — Jednorazowa walidacja niezmiennego neural snapshotu

**Status:** proposed/todo. **Goal:** usunąć powtórną walidację tego samego
payloadu w jednym żądaniu bez osłabienia guards.

**Context / Dependencies:** TASK-09111, znajomość raw-boundary callers.
**Recommended execution:** `gpt-6.1-sol / high`; zmiana granicy zaufania,
obowiązkowy niezależny `gpt-6-astra / high` przed commitem.

**Scope / Technical notes:** dodać głęboko immutable `ValidatedNeuralSource`;
raw proposal → pełna walidacja → typed value → binding validation. Zachować
publiczne raw validators dla pozostałych callers. Request-scoped reuse joba
i descriptor, bez cache między procesami i bez flagi trusted.

**Expected files:** S1, S3; rozszerzyć istniejące
`C:/Users/tuszy/Documents/game_predicotr/services/api/tests/test_neural_grid_proposal.py`
i `C:/Users/tuszy/Documents/game_predicotr/services/api/tests/test_neural_page_geometry_api.py`.

**Acceptance / Test cases:** błędne współrzędne/checksum/powiązania/partial
visibility nadal odrzucane; próba mutacji nested value niemożliwa;
walidator wywoływany raz dla tego samego źródła; inny descriptor walidowany osobno.
Wynik exact identyczny z baseline. **Verification:** V1, V2, scoped mypy.
**Out of scope:** omijanie pełnej walidacji `/start`. **Risks:** wszystkie
raw callers muszą zachować kontrakt. **Outcome:** do wypełnienia.

### TASK-09113 — Trwałe source index i geometry summary

**Status:** proposed/todo. **Goal:** raport istnieje po restarcie bez czytania
271 MB geometrii; świeży folder ma metadane jeszcze przed inferencją.

**Dependencies:** TASK-09111–09112; projekt formatu/publikacji z tego planu.
**Recommended execution:** `gpt-6.1-sol / high`; immutable provenance i crash
recovery wymagają niezależnego `gpt-6-astra / high`.

**Scope / Technical notes:** source index przy finalize, geometry summary
i per-source details po walidacji workera; atomowe pliki i pointer. Dodać
proponowany read-only reader/builder w
`C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/domain/browser_import_report.py`
oraz adapter w
`C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/storage/browser_import_report_store.py`.
Tożsamość obejmuje source i skipped ranges; nie liczyć wszystkiego ze zdjęć
pozostałych do uploadu. Klasyczny V1.1 i neural worker publikują spójny format.
Stary exact manifest bez zmian. Brak sidecar nie uruchamia ciężkiego fallbacku GET.
Ten task jest właścicielem minimalnej additive migracji nullable descriptorów
source/geometry projection oraz `selection_revision` w retention model.
Nowy zapis ustawia rewizję; legacy NULL nie jest dowodem zgodności i wymaga
jawnej inicjalizacji w recovery. Numer Alembic ustalić z aktualnego head.
TASK-09115 dopiero później dodaje metadane/listowanie katalogu.

**Expected files:** S2, S7, S8; nowe wskazane wyżej; proponowane
`C:/Users/tuszy/Documents/game_predicotr/services/api/tests/test_browser_import_report.py`.
Istniejące testy workera `test_neural_page_geometry_preflight.py` oraz
`test_page_geometry_preflight.py` w
`C:/Users/tuszy/Documents/game_predicotr/services/worker/tests/`.

**Acceptance / Test cases:** root/lookup bounded bytes; zero geometry-monolith
parse w czytaniu szczegółów; deterministyczny descriptor; crash każdej fazy
publikacji; retry nie powiela inferencji; stale attempt/CAS nie publikuje;
corrupt/missing/unsupported ma jawny stan; exact completion może istnieć bez
projekcji. **Verification:** V1/V3 + nowe testy; budżety struktur w fixtures
strumieniowych, bez benchmarku miliona rekordów.
**Out of scope:** masowa odbudowa istniejących danych użytkownika.
**Risks:** koszty jednorazowej projekcji i dysku jawne; osierocone pliki bez
automatycznego cleanupu. **Outcome:** do wypełnienia.

### TASK-09114 — Zapytania kanoniczności i replay ograniczone do folderu

**Status:** proposed/todo. **Goal:** koszt raportu nie zależy od całej historii
plansz/jobów gry, a właściwy replay nie ginie za limitem 10 000.

**Dependencies:** TASK-09111, TASK-09113. EXPLAIN wymagany przed wyborem indeksu.
**Recommended execution:** `gpt-6.1-sol / high`; semantyka numeracji i replay,
niezależny `gpt-6-astra / high`.

**Scope / Technical notes:** wąskie range-bound API repository + read-only
agregacja w spójnym snapshotcie. Nowe/użyte numery, alternatywy i first/last
muszą zgadzać się z exact dla tych samych wejść. SQL filtry source/game/type/
manifest przed LIMIT; kolejne keyset candidates przy różnym fingerprint.
Reuse lookup w żądaniu. Przy wyczerpaniu budgetu nie wybierać innego joba;
zwrócić jawny błąd, nie „brak joba”. Additive indeks Alembic tylko jeśli pomiar
wykazuje potrzebę. Historyczne metody planera uploadu pozostają bez zmian.

**Expected files:** S4–S6, S1; nowe pliki Alembic w
`C:/Users/tuszy/Documents/game_predicotr/services/api/alembic/versions/`
otrzymają numer dopiero po sprawdzeniu head. Testy:
`C:/Users/tuszy/Documents/game_predicotr/services/api/tests/test_image_sequence_canonical.py`
i `C:/Users/tuszy/Documents/game_predicotr/services/api/tests/test_image_imports_api.py`.

**Acceptance / Test cases:** skipped ranges, luki, alternatywy, overlapping
ranges, wykluczenia, latest failed/running, różne warianty, canonical owner
zmieniony przy jednakowych licznikach nie tworzy nowej obietnicy start-CAS;
wynik zgadza się z dotychczasową domeną i zachowuje worker owner protections.
Inne gry niewidoczne; SQL przed LIMIT;
brak globalnego list_jobs10000 w ścieżce raportu. **Verification:** V1/V2 oraz
izolowany PostgreSQL z query-plan assertion, bez produkcyjnych zapisów.
**Out of scope:** globalna zmiana schematu canonical. **Risks:** legacy JSON
job input keys/fingerprint muszą zachować semantykę. **Outcome:** do wypełnienia.

### TASK-09115 — Game-scoped katalog i paginacja gotowych folderów

**Status:** proposed/todo. **Goal:** lista aktywnej gry nie skanuje dysku ani
folderów pozostałych gier; świeży i retained folder da się odnaleźć po restarcie.

**Dependencies:** TASK-09113; zaakceptowane rozszerzenie kontraktu. Implementacja
API wymaga poinformowania użytkownika, że to opt-in envelope, zanim zacznie się kodowanie.
**Recommended execution:** `gpt-6.1-sol / high`; własność i zgodność kontraktu,
niezależny `gpt-6-astra / high`.

**Scope / Technical notes:** reuse retention model, additive nullable columns
katalogu (purpose, file_count, total_bytes, replacement/current) poza
descriptor/revision dostarczonymi przez TASK-09113 oraz potwierdzony indeks katalogu;
keyset game query i zbiorczy job/status lookup;
brak per-folder session/N+1. Finalize zapisuje małe metadata razem z ready.
Migracja nie parsuje wszystkich plików w transakcji. Nullable legacy pokazuje
osobny game-scoped bucket `legacyUnknownMetadata` i recovery action.
GET nigdy nie przypisuje właściciela ani purpose.
Managed handoff dostępny nawet po zniknięciu browser folderu.

**Expected files:** S2, S8, S9; schemas/OpenAPI/client/wrapper z S10.
Istniejące testy
`C:/Users/tuszy/Documents/game_predicotr/services/api/tests/test_browser_staging_list_recovery.py`
oraz
`C:/Users/tuszy/Documents/game_predicotr/services/api/tests/integration/test_browser_staging_retention_repository.py`.

**Acceptance / Test cases:** default legacy array; page envelope/cursor; obca
gra/RLS; retained managed; null owner; crash finalize po rename przed DB;
retry ready bez duplikatu; limit 200; fixed query count bez N+1.
**Verification:** V1/V2/V4, izolowany PostgreSQL.
**Out of scope:** automatyczne backfill i usuwanie stagingu.
**Risks:** brak metadanych starego folderu ma jawny recovery, nie ukryte skanowanie.
**Outcome:** do wypełnienia.

### TASK-09116 — Izolacja operacji folderu i bezpieczny recovery

**Status:** proposed/todo. **Goal:** kosztowny odczyt folderu A nie blokuje
folderu B; rename/delete nie może wyprzedzić kontroli zależności.

**Dependencies:** TASK-09113–09115. **Recommended execution:**
`gpt-6-astra / high`; spójność DB/filesystem i lock failure; niezależny
`gpt-6.1-sol / high` przed commitem, eskalacja Astra przy nierozstrzygniętej race.

**Scope / Technical notes:** adapter systemowego exclusive lock + operation intent/CAS,
protokół opisany powyżej we wszystkich konsumentach źródeł i GC. Przejść
call graph `cancel`, replacement, source reads, finalize, start, worker
handoff i physical GC; nie wystarczy usunięcie `self._lock`. Nie przenosić
exact `/start` do innej transakcji w tym tasku. Lock obejmuje dotychczasową
atomową transakcję job/in_use. Retry recovery jest idempotentny. Ten task
dodaje additive migrację struktury pendingOperation, nie przerzuca jej do późniejszego taska.

**Expected files:** S1, S2, S7–S9 oraz znalezione przez call graph adaptery
GC (sprawdzić ich dokładne symbole przed taskiem); proponowany
`C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/storage/browser_selection_operation_lock.py`.
Testy repository + nowe proponowane
`C:/Users/tuszy/Documents/game_predicotr/services/api/tests/integration/test_browser_selection_operation_lock.py`.

**Acceptance / Test cases:** dwa procesy start/cancel, worker/GC,
replace original+new w obu kierunkach, DB connection utracone przed publish
nie zwalnia OS locka, unlock/close failure, nasycenie max4, crash każdego intent phase,
recover blocked ambiguous, unbound legacy. Na izolowanych plikach/DB;
żaden test nie kasuje danych użytkownika. **Verification:** V1 + dedykowany
PostgreSQL proces/race test z jawnymi deadline'ami.
**Out of scope:** wykonanie cleanupu; zwiększenie worker concurrency.
**Risks:** wspólny protokół musi objąć wszystkich mutatorów. Brak pokrycia
jednego z nich blokuje merge zadania. **Outcome:** do wypełnienia.

### TASK-09117 — Szybki raport w Adminie i jawne przygotowanie legacy

**Status:** proposed/todo. **Goal:** „Pokaż raport” renderuje overview bez
JPEG/monolitu; pełne liczniki i szczegóły doładowują się niezależnie.

**Dependencies:** TASK-09113–09116, zaakceptowany kontrakt rozszerzenia API.
**Recommended execution:** `gpt-6.1-sol / medium`; określony pion UI/API,
niezależny `gpt-6-astra / high` dla exact/overview boundary i zgodności.

**Scope / Technical notes:** osobne discriminated schemas, wygenerowany klient,
wrapper, root/canonical requests, lazy indexed details. Import intent nadal
korzysta z exact. Nowa jawna przygotowująca projekcję operacja używa istniejącego
job engine; reuse `JobType.VALIDATE` i validation_kind/input/checkpoint
opisane w kontrakcie powyżej, spójny handler/replay/dispatch S12.
Idempotency po descriptor, restart/checkpoints,
bez inferencji i bez GET tworzącego job. Legacy działa do końca wdrożenia;
feature gate nowego report view pozwala wrócić do starego czytnika UI.

**Expected files:** S1, S10; proponowany handler
`C:/Users/tuszy/Documents/game_predicotr/services/worker/src/game_predictor_worker/images/browser_import_report_projection.py`
oraz S5/S12 i istniejące source dependency/retention adaptery z S8.
Testy Admina z V4 + nowe testy rendered interaction; backend schemas/request
tests w S1, worker restart test nowego handlera.

**Acceptance / Test cases:** pierwszy raport przed geometry preflight;
prepared/unavailable/corrupt summary; root nie czeka canonical; zmiana gry/
folderu i late response; cancel; utrata prepare response ten sam job;
zmiana profilu nie unieważnia pinned geometry; overview nie ma exact checksum;
próba start ze stale descriptor odrzucona; V1.1 i V3 zachowują korektę/import.
**Verification:** V1–V4, request tests, scoped lint/typecheck, wygenerowany
klient drift check, izolowany Admin build dopiero po focused checks.
**Out of scope:** wdrożenie do działającej aplikacji.
**Risks:** globalny worker lane może opóźnić jednorazowe legacy prepare;
UI pokazuje prawdziwy queued/progress. **Outcome:** do wypełnienia.

### TASK-09118 — Odbiór całego przepływu i instrukcja wdrożenia

**Status:** proposed/todo. **Goal:** dowody potwierdzają trwałość, zgodność
i zakres kosztu; użytkownik dostaje gotowy pakiet do osobno zatwierdzanego wdrożenia.

**Dependencies:** TASK-09111–09117, brak otwartych P0–P2; działająca izolowana
baza/testy, dostępne istniejące read-only dane do pomiaru.
**Recommended execution:** `gpt-6.1-sol / medium`; odbiór według jawnych
kryteriów; niezależny finalny `gpt-6-astra / high`.

**Scope / Technical notes:** bounded real-data read checks, nowy proces,
restart test fixtures, lost-response, pinned old model/profile, V1.1 regression;
instrukcja operatorska kolejności additive DDL/backend/worker/Admin i feature gate.
Przed DDL sprawdzić aktualne Alembic head, stan migracji i istniejącą procedurę
odtwarzania; nie obiecywać rollbacku DB ani robić kopii całych 48 GB jako
automatycznego kroku tego taska. Wdrożenie i produkcyjna odbudowa oddzielnie
po zgodzie, z oszacowaniem miejsca i czasu konkretnej operacji.

**Expected files:** plan, wymagania/API/data architecture w Relevant docs,
proponowany
`C:/Users/tuszy/Documents/game_predicotr/ai_docs/guides/IMPORT_REPORT_DEPLOYMENT.md`,
completed task/Outcome/CURRENT_STATE. **Verification:** V1–V4 + wyniki
live read-only SQL/HTTP, jeśli usługi dostępne; niedostępność blokuje dowód,
nie może być zastąpiona deklaracją „PASS”.

**Acceptance / Test cases:** wszystkie bramki poniżej; mapowanie wymaganie
→ test; brak fake-zero i ukrytego globalnego kosztu; review bez P0–P2.
**Out of scope:** uruchomienie rollout/migracji/cleanup/treningu.
**Risks:** brak SQL/HTTP dowodu oznacza gotowy projekt/kod, ale nie ukończony
odbiór wydajności. **Outcome:** do wypełnienia.

## Mapa sprawdzonych plików i symboli

Poniższe istniejące ścieżki/symbole sprawdzono w repo na HEAD
`69e7ec937dacb4155c8f32978f45a2b26f090a3b` (`v1.7.243`). Nowa sesja ponownie
sprawdza branch, status, instrukcje i HEAD; plan nie dowodzi niezmienności repo.

| Kod | Istniejące pliki i symbole                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1  | [api/image_imports.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/api/image_imports.py): `_load_page_geometry_manifest`, `browser_preflight`, `ready_selection`, `list_ready_browser_selections`, `start_ready_browser_import`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| S2  | [application/image_imports.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/application/image_imports.py): `BrowserImageSelectionService.finalize`, `get_ready`, `list_ready`, `_ready_selection`, `cancel`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| S3  | [neural_grid_proposal.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/domain/neural_grid_proposal.py): `NeuralGridSnapshot`, `validate_neural_source_proposal`, `validate_neural_source_binding`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| S4  | [image_sequence_canonical.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/domain/image_sequence_canonical.py): `ImageSequenceCanonicalService.preflight`; [repository](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/storage/image_sequence_canonical_repository.py): `canonical_numbers`, `canonical_source_checksums`                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| S5  | [application/jobs.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/application/jobs.py): `preview_image_import_model_fingerprints`, `get_managed_neural_import_by_source_selection`, `get_image_import_run_by_source_selection`, `get_page_geometry_preflight_by_source_selection`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| S6  | [job_repository.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/storage/job_repository.py): `SqlAlchemyJobRepository.list_jobs`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| S7  | [neural worker](C:/Users/tuszy/Documents/game_predicotr/services/worker/src/game_predictor_worker/images/neural_page_geometry_preflight.py): `NeuralPageGeometryPreflightHandler`; [classic worker](C:/Users/tuszy/Documents/game_predicotr/services/worker/src/game_predictor_worker/images/page_geometry_preflight.py): `PageGeometryPreflightHandler._write_immutable`                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| S8  | [models.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/storage/models.py): `BrowserSelectionRetentionModel`, `JobModel`, `ImageSequenceCanonicalModel`; [retention repository](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/storage/browser_staging_retention_repository.py): `SqlAlchemyBrowserStagingRetentionRepository.board_import_status`, `record_ready`, `record_in_use`, `discard_unused`                                                                                                                                                                                                                                                                                                                                                                                |
| S9  | [game_storage_routing.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/storage/game_storage_routing.py): `GameStorageRouter`; [main.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/main.py): `default_browser_image_selection_service`; [managed_reprocess_evidence.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/application/managed_reprocess_evidence.py): `resolve_managed_browser_selection`; [page_geometry_overrides.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/application/page_geometry_overrides.py): `PageGeometryOverrideService.snapshot`, `exclusion_snapshot`                                                                                                                               |
| S10 | [schemas/image_imports.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/schemas/image_imports.py): `BrowserImageImportPreflightResponse`; [Admin panel](C:/Users/tuszy/Documents/game_predicotr/apps/admin/src/features/imports/image-folder-import-panel.tsx): `prepareReadyImport`, `refreshReadySelections`; [wrapper](C:/Users/tuszy/Documents/game_predicotr/apps/admin/src/features/imports/image-folder-import-actions.ts): `previewReadyBrowserImageImport`, `listReadyBrowserImageSelections`; [state](C:/Users/tuszy/Documents/game_predicotr/apps/admin/src/features/imports/image-folder-import-state.ts); [klient](C:/Users/tuszy/Documents/game_predicotr/packages/admin-api-client/src/index.ts); [OpenAPI](C:/Users/tuszy/Documents/game_predicotr/packages/admin-api-client/openapi/openapi.json) |
| S11 | [annotations.py](C:/Users/tuszy/Documents/game_predicotr/services/worker/src/game_predictor_worker/vision_lab/annotations.py): `exclusive`, `exclusive_bounded`, przykład OS byte lock; [compose.yaml](C:/Users/tuszy/Documents/game_predicotr/infra/docker/compose.yaml): aktualny Compose uruchamia PostgreSQL, nie kontener API/worker. Istniejącego locka laboratorium nie refaktorować w tym planie.                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| S12 | [validation_dispatch.py](C:/Users/tuszy/Documents/game_predicotr/services/worker/src/game_predictor_worker/imports/validation_dispatch.py): `ValidationJobDispatchHandler`; [cli.py](C:/Users/tuszy/Documents/game_predicotr/services/worker/src/game_predictor_worker/cli.py): konfiguracja dispatchu; [domain/jobs.py](C:/Users/tuszy/Documents/game_predicotr/services/api/src/game_predictor_api/domain/jobs.py): `JobType.VALIDATE`, `job_input_key`; S5: `JobService._persist_job`                                                                                                                                                                                                                                                                                                                                                          |

## Weryfikacja planowana

Poniższe komendy są do wykonania **podczas implementacji**. Nie uruchomiono
ich w zadaniu planowania. Nowe testy z tasków trzeba dopisać do odpowiedniej
komendy po utworzeniu plików. Integracje używają wyłącznie izolowanej bazy
zgodnie z fixture; żadnego testu kasowania na produkcyjnych plikach.

Przykładowy bounded runner PowerShell dla istniejących narzędzi, bez shell
interpolacji polecenia. Każdy pojedynczy krok: maks. 120 s. Po timeout sprawdzić
proces potomny; nie uruchamiać kolejnej kopii, jeśli poprzednia nadal działa.

```powershell
# Katalog i wszystkie argumenty ścieżek są absolutne.
function Invoke-ReportPlanCheck {
    param([string]$Exe, [string[]]$Arguments, [string]$WorkingDirectory)
    $stepJob = Start-Job -ScriptBlock {
        param($stepExe, $stepArgs, $stepCwd)
        Set-Location -LiteralPath $stepCwd
        & $stepExe @stepArgs
        if ($LASTEXITCODE -ne 0) { throw "Exit code: $LASTEXITCODE" }
    } -ArgumentList $Exe, $Arguments, $WorkingDirectory
    try {
        if (-not (Wait-Job -Job $stepJob -Timeout 120)) {
            Stop-Job -Job $stepJob
            throw 'Step timeout; inspect child processes before retry.'
        }
        Receive-Job -Job $stepJob -ErrorAction Stop
        if ($stepJob.State -ne 'Completed') { throw 'Step failed' }
    } finally { Remove-Job -Job $stepJob -Force }
}
$reportRepo = 'C:\Users\tuszy\Documents\game_predicotr'
$reportPython = 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe'
$reportNode = 'C:\Program Files\nodejs\node.exe'

# V1: czyste guards i canonical; nie cały test suite.
Invoke-ReportPlanCheck -Exe $reportPython -WorkingDirectory $reportRepo -Arguments @(
    '-m', 'pytest', '-q',
    'C:\Users\tuszy\Documents\game_predicotr\services\api\tests\test_neural_grid_proposal.py',
    'C:\Users\tuszy\Documents\game_predicotr\services\api\tests\test_image_sequence_canonical.py'
)
# V2: API i zachowanie korekty/importu.
Invoke-ReportPlanCheck -Exe $reportPython -WorkingDirectory $reportRepo -Arguments @(
    '-m', 'pytest', '-q',
    'C:\Users\tuszy\Documents\game_predicotr\services\api\tests\test_image_imports_api.py',
    'C:\Users\tuszy\Documents\game_predicotr\services\api\tests\test_neural_page_geometry_api.py',
    'C:\Users\tuszy\Documents\game_predicotr\services\api\tests\test_browser_staging_list_recovery.py',
    'C:\Users\tuszy\Documents\game_predicotr\services\api\tests\test_managed_reprocess_evidence.py'
)
# V3: oba istniejące workery geometrii.
Invoke-ReportPlanCheck -Exe $reportPython -WorkingDirectory $reportRepo -Arguments @(
    '-m', 'pytest', '-q',
    'C:\Users\tuszy\Documents\game_predicotr\services\worker\tests\test_neural_page_geometry_preflight.py',
    'C:\Users\tuszy\Documents\game_predicotr\services\worker\tests\test_page_geometry_preflight.py'
)
# V4: focused Admin contracts + helpers.
Invoke-ReportPlanCheck -Exe $reportNode -WorkingDirectory $reportRepo -Arguments @(
    '--experimental-strip-types', '--test',
    'C:\Users\tuszy\Documents\game_predicotr\apps\admin\test\image-folder-import-actions.test.mjs',
    'C:\Users\tuszy\Documents\game_predicotr\apps\admin\test\image-folder-import-state.test.mjs',
    'C:\Users\tuszy\Documents\game_predicotr\apps\admin\test\image-folder-import-panel-contract.test.mjs',
    'C:\Users\tuszy\Documents\game_predicotr\apps\admin\test\neural-import-preflight.test.mjs'
)
```

Po focused tests uruchomić scoped Ruff/mypy oraz Admin/client lint/typecheck,
eksport OpenAPI i generator zgodnie ze zweryfikowanymi skryptami w
[package.json](C:/Users/tuszy/Documents/game_predicotr/package.json).
Nie generować klienta ręcznie. Build używa izolowanego katalogu wyjściowego,
żeby nie nadpisać działającego Admina. Dokładne listy plików lint i komendy
nowych testów zostaną zapisane w tasku przed jego kodowaniem.

## Mapa wymagań i odbiór

| Wymaganie                    | Zadania          | Kryterium / test                                                                     |
| ---------------------------- | ---------------- | ------------------------------------------------------------------------------------ |
| Szybkie Pokaż raport         | 09113, 09117, 09118 | Zero JPEG i zero parse pełnego geometry manifestu; root niezależny od canonical      |
| Brak podwójnej walidacji     | 09112             | Licznik raw validator = 1 przy tej samej tożsamości; invalid input nadal fail        |
| Więcej folderów i gier       | 09114–09116        | Game predicate przed LIMIT, bounded rows/bytes; brak globalnego filesystem scan/lock |
| Pełna zawartość raportu      | 09113, 09114, 09117 | Canonical scalars zgodne z exact; first/last, alternatywy, skipped i exclusions      |
| Bez utraty jakości           | 09112–09114, 09117  | Stale/changed-source/current-owner guards; exact nigdy z overview                    |
| Restart i utracona odpowiedź | 09113, 09115–09118  | Ten sam descriptor/job; atomic pointer, brak częściowego ready                       |
| Race start/delete/GC         | 09116             | Dwa procesy, lock loss, CAS i pending-operation recovery                             |
| Kompatybilność V1.1          | 09115, 09117, 09118 | Default API bez zmian, pinned old preflight i stary workflow                         |
| Ocena schematu i zapytań     | 09111, 09114, 09115 | Live read-only EXPLAIN, zakres folderu; brak nieudowodnionej przebudowy              |

**Proponowane cele odbioru, jeszcze nie wyniki:** na istniejącym folderze
2575 zdjęć/23 175 wykrytych plansz, trzy odczyty w nowym procesie: root HTTP
do 2 s bez obciążenia, canonical do 5 s, strona szczegółów do 2 s. Gotowy
root do 5 s przy jednym istniejącym workerze, jeśli taki read-only odczyt
jest możliwy bez uruchamiania dodatkowego obciążenia. Nie obiecywać tych
czasów dla miliona źródeł ani wszystkich konfiguracji sprzętu.

Odbiór skali opiera się również na asercjach kosztu: limit listy200, zero
JPEG/monolitu w root/list/details, indeksowane lookup, bounded parser bytes,
zapytania po game/folder, brak globalnego locka i brak N+1. Istniejące dane
innej gry mogą służyć do izolowanego odczytu; nie tworzyć 20 katalogów ani
milionowych fixture'ów bez nowego zlecenia benchmarku.

Jeśli wynik odbioru przekroczy cel, zadanie pozostaje nieodebrane. Wskazać
składnik kosztu i poprawić go w zakresie taska; nie podnosić limitu i nie
maskować błędu timeoutem. Brak usług/live SQL pozostaje jawną luką dowodową.

## Kolejność wdrożenia po osobnej zgodzie

1. Zatwierdzić plan po review Claude Code. Uruchamiać taski kolejno według
   zależności, osobny review/commit/Outcome po każdym. Nie wykonywać merge/push.
2. Zbudować zgodny backend/worker/Admin z nowym view wyłączonym. Sprawdzić
   aktualny stan Alembic, miejsca i procedurę odtwarzania przed rollout.
3. Po osobnym sygnale użytkownika wykonać wyłącznie opisane additive migracje,
   wdrożyć backend/worker z obsługą starego i nowego formatu, następnie Admin.
4. Nowe finalizacje/preflighty tworzą indeksy automatycznie. Dla starych
   raportów wykonać preview przygotowania i oszacowanie bytes/czasu;
   nie uruchamiać pełnego backfill bez osobnej zgody.
5. Włączyć nowy view po bounded odbiorze jednego istniejącego folderu.
   Wyłączenie view przywraca kompatybilny stary UI; nie oznacza automatycznego
   downgrade bazy i nie usuwa artefaktów ani wyników użytkownika.

## Ryzyka i ocena projektu

Największe ryzyko dotyczy protokołu lock/recovery, nie uczenia modelu.
Muszą w nim uczestniczyć wszystkie mutacje filesystemu. Dlatego ma osobny
task i testy z dwoma procesami. Równoległość globalnej kolejki pozostaje
bez zmian; szybkie odczyty nie wymagają zwiększania concurrency importu.

Pomiary wykazują zbędny koszt odczytu/walidacji. Nie wykazują wadliwości
całego schematu ani potrzeby innej bazy. Live EXPLAIN i odbiór wielogrowej
izolacji są nadal konieczne. Brak tych dowodów nie może być ukryty przez audyt
projektu. Audyt kodu gotowej implementacji będzie oddzielną bramką.

## Instrukcja do skopiowania do Claude Code

```text
Wykonaj niezależny audyt projektu. Nie implementuj zmian.
Repo: C:\Users\tuszy\Documents\game_predicotr.
Pracuj na ścieżkach absolutnych. Przeczytaj AGENTS.md, ai_docs/README.md,
CURRENT_STATE.md, PLAN_STANDARD.md oraz cały plan:
C:\Users\tuszy\Documents\game_predicotr\ai_docs\delivery\IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md
Potem przeczytaj audyt Astra:
C:\Users\tuszy\Documents\game_predicotr\ai_docs\quality\IMPORT_REPORT_PERFORMANCE_ASTRA_REVIEW_20261007.md
Sprawdź wskazane pliki, symbole, wymagania i architekturę w bieżącym kodzie.
Szukaj P0–P2: ochrony importu, niezmienności/provenance, atomic publication,
restartu i lost-response, OS locków/race, własności/RLS, zgodności API,
zależności migracji, semantyki canonical/replay i rzeczywistego ograniczenia kosztu.
Dla każdej uwagi podaj priorytet, sekcję/pliki, scenariusz błędu i konkretną
poprawkę projektu. Oddziel fakty od hipotez. Nie traktuj celów 2s/5s jako wyników.
Nie uruchamiaj DB zapisów, migracji, cleanupu, treningu, restartów ani benchmarków.
Nie zmieniaj plików. Jeśli nie ma uwag P0–P2, powiedz to wprost.
Odpowiedz po polsku. Plan pozostaje propozycją do akceptacji użytkownika.
```

## Przypisanie modeli do zadań

Dostępność nazw i poziomów sprawdzono w metadanych narzędzia delegacji
w sesji 2026-10-07. Tabela nie stanowi zgody na implementację ani delegowanie.

| Zadanie   | Model       | Reasoning | Uzasadnienie                                                                   | Dodatkowy review                                           |
| --------- | ----------- | --------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| TASK-09111 | gpt-6.1-sol | medium    | Ograniczony pomiar istniejących odczytów i SQL; eskalacja przy zmianie guards. | gpt-6-astra / high przed wyborem zmian SQL                 |
| TASK-09112 | gpt-6.1-sol | high      | Granica zaufania i niezmienność zwalidowanego payloadu.                        | gpt-6-astra / high, obowiązkowy                            |
| TASK-09113 | gpt-6.1-sol | high      | Provenance, atomowa publikacja i trwałe wersjonowane artefakty.                | gpt-6-astra / high, obowiązkowy                            |
| TASK-09114 | gpt-6.1-sol | high      | Domain sequence/replay i semantyka aktualnych właścicieli.                     | gpt-6-astra / high, obowiązkowy                            |
| TASK-09115 | gpt-6.1-sol | high      | Własność stagingu, RLS, schema/API compatibility.                              | gpt-6-astra / high, obowiązkowy                            |
| TASK-09116 | gpt-6-astra | high      | Ryzyko crash/race oraz spójność DB i filesystemu.                              | gpt-6.1-sol / high, obowiązkowy niezależny; spór eskalować |
| TASK-09117 | gpt-6.1-sol | medium    | Jawnie zdefiniowany pion API/UI i generator; eskalacja przy zmianie kontraktu. | gpt-6-astra / high, obowiązkowy na exact/overview boundary |
| TASK-09118 | gpt-6.1-sol | medium    | Odbiór według jawnych kryteriów i procedura operatorska.                       | gpt-6-astra / high, obowiązkowy końcowy                    |
