---
title: Current project state
status: active
last_updated: 2026-08-02
---

# Current State

## Phase

`Version 0.4 in development — TASK-0151 complete; owner acceptance 0.2/0.3 deferred`

## Aktywne tory wydań

### Wersja 0.1

- TASK-0118 jest ukończony,
- lokalna paczka `0.1.5 (6)` zawiera jedną grę i 500 000 layoutów,
- APK ma SHA-256
  `d94061734d1e141ee9e68bf0e532eeb0ac1d485b68796f853c0dc3589326c522`,
- snapshot ma SHA-256
  `ddbfa90e673811efe2acad8e8049acc2435389bbbcaf256715573a744ef66de8`,
- APK `0.1.5 (6)` zainstalowano aktualizacyjnie na Google Pixel 10 Pro XL;
  Android potwierdził wersję, zachowany `firstInstallTime` i poprawny start,
- TASK-0119 został ukończony 2026-08-01: właściciel potwierdził podstawowe
  scenariusze offline, matching, duplikaty, Target, Undo/Reset, restart i
  płynność tabeli bez błędu blokującego,
- wersja 0.1 jest odebrana; ponowny test Mobile nastąpi po zmianach 0.3.

### Wersja 0.2

- rozwój może rozpocząć się przed zakończeniem TASK-0119,
- TASK-0120 zakończył kontrolowany reset lokalnego PostgreSQL,
- TASK-0121 zakończył przebudowę Admina na trzy workspace’y, jeden kontekst gry
  i accordion zależnych sekcji ze stanem w URL,
- TASK-0122 dodał trzy filtry katalogu gier, spójny wybór kontekstu oraz
  odwracalne przywrócenie zarchiwizowanej gry jako szkicu,
- TASK-0123 dodał źródło folderu, jednorazowy token, typowany image import oraz
  wznawialne kopiowanie JPEG-ów do content-addressed `data/originals` z
  niezmiennym manifestem; pierwotny dialog Windows został zastąpiony podczas
  odbioru przez przeglądarkowy wybór i kontrolowany upload,
- TASK-0124 dodał konfigurowalny cel liczby layoutów, raport kompletności i luk,
  walidację ręcznych numerów sekwencji oraz deterministyczny wybór najlepszego
  źródła z audytowalnym ręcznym override,
- TASK-0125 dodał checksum-bound bootstrap katalogu symboli z rzeczywistych
  cropów, automatyczne utworzenie przy zgodnej liczbie grup oraz jawne
  rozstrzygnięcie merge/split przy konflikcie,
- TASK-0126 dodał kafelki z rzeczywistą grafiką, modal z deterministycznymi
  stronami po 10 cropów oraz atomową zmianę nazwy i obrazu bez zmiany
  stabilnego `code` ani `mobileCode`,
- TASK-0127 uprościł reguły do jednego bieżącego workspace'u, zachowując
  wewnętrzną niezmienną historię oraz pełne, idempotentne kopiowanie
  opublikowanej konfiguracji do edytowalnego draftu,
- TASK-0128 dodał jawną akcję przeliczania layoutów, preflight kompletnego
  opublikowanego datasetu i reguł, widoczny `payout-v2`, postęp oraz wznowienie
  tego samego joba od checkpointu,
- TASK-0129 powiązał jedno wejście do osobnej aplikacji Reviewer z aktywną grą,
  najnowszym gotowym image importem i faktycznymi planszami oraz dodał jawne
  blokady i przejście z powrotem do importu,
- TASK-0130 usunął z widocznego workspace'u techniczny katalog Dataset i
  zabezpieczył brak powrotu dawnych wejść `datasets` oraz `manual-review` przez
  URL; encje, endpointy i audyt pozostały nienaruszone,
- TASK-0131 uprościł wydanie Android do jednej aktywnej gry, automatycznej
  najnowszej zgodnej pary dataset/reguły i pojedynczej akcji create → build;
  zwijana historia, bezpieczny draft po częściowej awarii, retry, checksumy i
  pobieranie APK pozostały dostępne,
- TASK-0132 uprościł osobny workspace `Joby` do jednego filtra statusu i
  zwartego podsumowania typu, kontekstu, postępu, czasu oraz błędu; techniczne
  metadane i dotychczasowe operacje pozostały dostępne po rozwinięciu joba,
- TASK-0133 dodał read-only preview i mocno potwierdzane usunięcie pojedynczego
  wydania oraz reset game-scoped danych layoutów bez usuwania gry; aktywne
  workflow i współdzielone wydania blokują operację, współdzielone artefakty i
  joby są zachowywane, a wykonanie ma idempotentne potwierdzenie,
- TASK-0134 dodał powtarzalną, ograniczoną czasowo bramkę końcową; cztery testy
  izolowanego PostgreSQL, 126 testów Admina, TypeScript, ESLint, OpenAPI i
  produkcyjny build przeszły, a przeglądarka przy 1366 × 768 potwierdziła trzy
  workspace'y, URL, puste stany, czystą konsolę i brak poziomego overflow,
- TASK-0142 jest aktywnym zadaniem stabilizacyjnym odbioru właściciela; pierwszy
  pion poprawił layout, style, pomoc i stany operacji sekcji `Import layoutów`;
  trzeci rozszerzył wybór gry na cały kafelek i dodał uzgadnianie skutecznego
  zapisu edycji; piąty uprościł wejście do sekcji symboli; szósty ostatecznie
  zastąpił zawodny dialog Windows standardowym selektorem przeglądarki,
  kontrolowanym uploadem JPEG-ów, postępem i sprzątanym stagingiem. Historyczne
  próby drugiego i czwartego pionu zostały supersedowane; siódmy uporządkował
  hierarchię kafelka gry i przeniósł czyszczenie na dół konfiguracji. Przechodzi
  138 testów Admina, 24 testy klienta i siedem skupionych testów API importu.
  Ósmy pion poprawił kontrakt checkpointu image importu i diagnostykę domenowych
  błędów workera. Dziewiąty podłączył pod tę samą akcję istniejący pełny
  pipeline obrazu i batchowy OCR strony; naprawczy job `777` jest wznawiany z
  checkpointu bez ponownego uploadu i tworzy cropy oraz pozycje review. Panel
  `Joby` mapuje techniczne dwie fazy na rzeczywiste `X / 739 zdjęć`. Dziesiąty
  pion usunął konflikt Windows `Path`/`PATH` przy generowaniu publicznego linku:
  API i skrypt używają wspólnej normalizacji, smoke test uruchamia proces z
  przekierowanymi logami, a nadal ograniczony cold-start ma do 60 sekund.
  Rzeczywisty start uzyskał HTTPS Quick Tunnel i został kontrolowanie
  zatrzymany; trwały profil użytkownika ma jeden `Path` oraz zweryfikowane
  zmienne Node/JDK/Android/Gradle. Jedenasty pion ograniczył edytor geometrii
  Reviewera do pojedynczego layoutu z marginesem, zachowując mapowanie narożników
  do współrzędnych oryginału oraz istniejący immutable recrop. Korekta poprawia
  bieżący layout, ale nie trenuje automatycznie globalnego profilu geometrii.
  Dwunasty pion rozdzielił koniec automatycznego image importu od terminalnego
  końca joba: `Wymaga review` pokazuje teraz datę, godzinę i czas zakończonego
  importu z pipeline'em, bez doliczania ręcznego zatwierdzania. Trzynasty pion
  usunął zależny od checkoutu Windows fałszywy drift klienta OpenAPI: LF/CRLF
  jest normalizowane przy porównaniu, ale zmiany semantyczne nadal blokują
  bramkę. Powtórna pełna bramka przeszła 2026-08-02: PostgreSQL 4/4, Admin
  140/140, klient API 26/26, typecheck, lint, OpenAPI i produkcyjny build.
- Czternasty pion TASK-0142 naprawił odbiór rzeczywistego szkicu `777 v0.2`:
  Reviewer i launcher dopuszczają `draft`/`active`, nadal wykluczając
  `archived`, a bootstrap symboli mapuje `None` do SQL `NULL`. Rzeczywisty
  bootstrap zakończył się `applied` i utworzył osiem symboli; produkcyjna sesja
  pokazała układ #8 oraz pełną kolejkę 4050 plansz.
- Admin i workflow powstają od czystej bazy,
- testy używają jednej gry i małego kontrolowanego datasetu,
- pełne 500 000 rzeczywistych layoutów i nowe gry nie należą do 0.2,
- zakres zadań 0.2 to TASK-0120–0134.

### Wersja 0.3

- obejmuje dostosowanie aplikacji mobilnej: kompaktowy header, planszę i
  Selection, `Next`, wybierany zasięg Targetu, skonsolidowany wynik i powrót na
  górę,
- zakres jest rozpisany jako TASK-0135–0141,
- odbiór kończy się testem offline na Google Pixel 10 Pro XL,
- nie obejmuje końcowych testów dużych rzeczywistych zbiorów.

### Wersja 0.4

- TASK-0151 ukończył fundament domenowy na branchu
  `codex/image-selection-domain-storage`: migracja `0025_image_selection`, job
  `image_selection`, trzy lekkie tabele bez BLOB, idempotentne create/get runu,
  stronicowana lista grup oraz wygenerowany klient OpenAPI,
- obejmuje wyłącznie M7.0 i TASK-0151–0157, czyli niedestrukcyjny preselektor:
  czwarty workspace
  `Selekcja zdjęć` redukuje katalog 10 000–30 000 kolejnych ujęć do jednego
  checksumowanego JPEG-a na dowolny rozpoznany zakres, a niepewne grupy kieruje
  do małego manualnego modala,
- TASK-0151–0157 obejmują model domenowy, skalowalny folder staging, szybki
  selector, output i handoff, manual fallback, operacje oraz bramkę 10k/30k,
- folder użytkownika pozostaje read-only; pełny pipeline dostaje jawnie
  przekazany manifest wybranych kopii i nie jest uruchamiany przez sam selector,
- testy 10k/30k mierzą sam selektor na surowych zdjęciach; nie są pełnym
  importem layoutów i nie odblokowują `massImportAllowed`.

### Wersja 0.5

- rozpoczyna pracę na większych rzeczywistych datasetach po zaakceptowaniu
  selektora 0.4,
- M6.6 został zaakceptowany jako obowiązkowy tor iteracyjnego ulepszania modelu
  symboli przed pełnym automatycznym importem,
- TASK-0143–0150 obejmują skumulowane kohorty per gra, panel jakości,
  source-aware dataset, trwały trening, bramkę ONNX, kontrolowaną aktywację,
  przeliczenie wyłącznie `pending` oraz odbiór dwóch iteracji,
- `accepted`, `corrected` i `rejected` są nienaruszalnymi decyzjami człowieka;
  żadna automatyczna operacja modelu nie może ich przeliczyć ani zmienić,
- TASK-0076 realizuje pełny import około 500 000 rzeczywistych layoutów na grę,
- nowe gry, wielogrowy snapshot/APK, benchmarki pełnego pipeline'u i
  TASK-0080–0089 domykają skalę oraz hardening 0.5.

## Dane i artefakty

### Chronione

- `artifacts/v01-representative-release/` — kompletna paczka odbiorowa 0.1,
- `artifacts/v01-ready-for-pixel/Game-Predictor-0.1.5-v6-Pixel.apk` — prosta
  kopia APK gotowa do instalacji na Pixelu,
- `artifacts/v02-clean-baseline/pre-reset/` — pełny dump i inwentarz danych
  istniejących bezpośrednio przed resetem 0.2,
- `.tooling/android-signing/` — prywatny klucz i konfiguracja podpisu,
- zdjęcia źródłowe i ręczne materiały wejściowe poza PostgreSQL,
- dokumentacja decyzji, migracje, kod i raporty jakości.

### Robocze

- PostgreSQL ma w repozytorium head `0025_image_selection`; przed rozpoczęciem pionu
  importu 0.2 baza nie zawierała rekordów domenowych,
- podczas odbioru utworzono roboczą grę `777` i image import; job naprawczy
  `65d6ca14-dacc-4341-b015-c187f2d7af36` zakończył automatykę w stanie
  `waiting_for_review`: 739 źródeł, 4050 plansz, 60 750 cropów i 4050 pozycji
  review; automatyczny bootstrap utworzył dla gry osiem symboli,
- dane poprzedniej iteracji są dostępne wyłącznie w kontrolowanym dumpie
  pre-reset; nie należy go automatycznie importować do workflow 0.2,
- `apps/mobile/assets/snapshot/m1-snapshot.db` jest małym fixture’em
  deweloperskim; pozostaje do świadomego zastąpienia fixture’em 0.2.

## Ukończony fundament

- aplikacja mobilna działa całkowicie offline i używa SQLite w APK,
- matching rozróżnia unique, duplicate i not found,
- payout-v2 ocenia prefiks od pierwszej kolumny i precomputed payout,
- Target przechodzi pełny cykl i pokazuje dodatnie lokalne maksima,
- lokalny Admin, FastAPI, PostgreSQL i wersjonowanie domenowe działają,
- import ręczny, snapshot/release pipeline i kontrolowane joby działają,
- pipeline zdjęć, geometria, OCR adapter, klasyfikacja i manual review mają
  działające piony oraz raporty jakości,
- osobny Reviewer działa lokalnie i przez ograniczony link z kodem,
- lokalny Admin API jest chroniony przez loopback/origin/intencję i audyt.

Szczegółowe wyniki historyczne znajdują się w `tasks/completed/`,
`process/DECISION_LOG.md` i raportach `quality/`; nie są powtarzane tutaj.

## Otwarte pytania

- Q-020 — dozwolony zakres analizy aplikacji referencyjnej,
- Q-022–Q-032 zostały rozstrzygnięte; Admin 0.2 nie ma otwartego pytania
  blokującego rozpoczęcie TASK-0122,
- finalny model OCR nie blokuje najbliższego pionu mobilnego; nazwa i sposób
  prezentacji wyniku zostały rozstrzygnięte dla 0.3.

Q-020 pozostaje niezależne od Admina 0.2 i nie blokuje TASK-0134.

## Blocked / deferred

- TASK-0076 pozostaje zablokowany przez `massImportAllowed = false` i należy do
  0.5,
- TASK-0080–0089 należą do pełnego hardeningu 0.5,
- TASK-0143–0150 są zaplanowane w M6.6 wersji 0.5; nie rozpoczynają się przed
  przejściem bramki selektora 0.4 i spełnieniem warunków wejścia M6.6,
- TASK-0151–0157 są zaplanowane jako M7.0 i nie zmieniają bieżącego zakresu
  TASK-0142; implementacja zaczyna się dopiero po osobnym poleceniu właściciela,
- masowy import, nowe gry i pełne benchmarki danych nie mogą wejść do bramki 0.2.

## Next recommended task

Kontynuować odbiór właściciela według
`ai_docs/quality/V0_2_ADMIN_ACCEPTANCE.md` i dopisywać regresje do aktywnego
TASK-0142. Import, pipeline, Symbole, Reviewer i Joby są potwierdzone; po
utworzeniu jednego wydania, kontroli klawiatury w Adminie i preview cleanup można
zamknąć produktową bramkę 0.2. Następny zaplanowany pion to
TASK-0135 z wersji 0.3. M7.0 wersji 0.4 rozpocznie TASK-0151 po osobnym
poleceniu; dopiero po TASK-0157 wersja 0.5 może rozpocząć M6.6 i duże dane.
Żaden z tych torów nie zastępuje odbioru 0.2.

## Do not start yet

- pełnego importu około 500 000 rzeczywistych layoutów,
- dodawania i testowania kolejnych gier,
- wielogrowego wydania mobilnego,
- pełnej macierzy urządzeń i hardeningu przypisanego do 0.5,
- Celery/Redis, mikroserwisów, chmury, Google Play lub publicznego Admin API.
