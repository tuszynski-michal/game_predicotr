---
title: Current project state
status: active
last_updated: 2026-08-01
---

# Current State

## Phase

`Version 0.3 mobile implementation in progress — Admin 0.2 acceptance continues independently`

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
  importu z pipeline'em, bez doliczania ręcznego zatwierdzania.
- Admin i workflow powstają od czystej bazy,
- testy używają jednej gry i małego kontrolowanego datasetu,
- pełne 500 000 rzeczywistych layoutów i nowe gry nie należą do 0.2,
- zakres zadań 0.2 to TASK-0120–0134.

### Wersja 0.3

- właściciel dopuścił niezależne rozpoczęcie Mobile 0.3 na branchu
  `ft/change-mobile-app`; trwający odbiór Admina 0.2 nie blokuje tego toru,
- obejmuje dostosowanie aplikacji mobilnej: kompaktowy header, planszę i
  Selection, `Next`, wybierany zasięg Targetu, skonsolidowany wynik i powrót na
  górę,
- zakres jest rozpisany jako TASK-0135–0141,
- TASK-0135 został ukończony 2026-08-01: nagłówek pokazuje `ver {releaseVersion}`,
  wybór gry i rząd `Next`, `Undo`, `Reset`; usunięto tytuły i liczniki planszy,
  status gotowości danych oraz opis Selection. `Next` pozostaje nieaktywnym
  kontraktem UI do TASK-0138. Testy Mobile przeszły 67/67 wraz z typecheckiem i
  lintem,
- TASK-0136 został ukończony 2026-08-01: opcjonalne nazwy PL/EN przechodzą przez
  PostgreSQL, Admin API/OpenAPI, snapshot SQLite schema v3 i Mobile; Selection
  wybiera krótszą nazwę (remis: PL), używa fallbacku `name` i zawija pojedynczo
  opisane kafelki bez poziomego przewijania. Testy Mobile przeszły 68/68,
- TASK-0137 został ukończony 2026-08-01: kontrolowany input zaczyna od 10 000 i
  dopuszcza dowolną liczbę całkowitą 1 000–500 000; engine oraz pojedynczy
  cykliczny odczyt SQLite oceniają `min(limit, N - 1)` spinów. Zmiana limitu
  unieważnia stary wynik i ignoruje spóźnioną odpowiedź. Testy Mobile przeszły
  74/74, a shared engine 24/24,
- TASK-0138 został ukończony 2026-08-01: `Next` działa wyłącznie od
  jednoznacznego anchora, czyta dokładny kolejny rekord po `sequence_number`,
  zawija ostatni rekord do pierwszego i uruchamia Target dla bieżącego limitu.
  Anchor jest częścią atomowej historii `Undo`; jawnie załadowany duplikat nie
  traci znanej pozycji, a błąd lub spóźniona odpowiedź nie zmienia planszy.
  Pełna regresja Mobile przeszła 81/81 wraz z typecheckiem, lintem i formatem,
- TASK-0139 został ukończony 2026-08-01: osobne karty matchingu i Targetu
  zastąpiła jedna dostępna karta. Sukces pokazuje `Układ znaleziony i obliczony`
  oraz numer; rozwijane szczegóły zawierają tylko koszt spinu, koszt i sumę
  końcową. Duplikat jest ostrzeżeniem, brak layoutu i błędy mają czerwony stan z
  opisem, a retry Targetu pozostał dostępny. Usunięto powtarzane wartości i
  opisy bez zmiany algorytmu ani tabeli. Regresja Mobile przeszła 81/81 wraz z
  typecheckiem, lintem i formatem,
- TASK-0140 został ukończony 2026-08-01: pływający przycisk powrotu na górę
  pojawia się po osiągnięciu zmierzonej kotwicy wyników Targetu, przewija ten
  sam wirtualizowany `FlatList` do początku i nie zasłania końca tabeli dzięki
  powiększonemu footerowi. Przycisk pozostaje w safe area i ma dostępny obszar
  52 × 52. Regresja Mobile przeszła 82/82 wraz z typecheckiem i lintem,
- TASK-0141 jest aktywny: Mobile przechodzi 82/82, shared engine 24/24,
  typecheck, lint, format zmienionych plików i walidację snapshotu schema 3.
  Podpisane APK `0.3.0 (7)` ma 42 267 190 bajtów i SHA-256
  `80dfb99fa85c466689d69901f0aea57d3fdf03d425c46fd71bb0f883569e1332`.
  Statyczny audyt potwierdził `arm64-v8a`, bundle JS, zgodny snapshot i brak
  `INTERNET`; lokalne wydanie wraz z manifestem, checksumą i instrukcją jest
  zachowane w `artifacts/v03-ready-for-pixel/`. Instalacja i manualny odbiór
  czekają na podłączenie Pixela,
- odbiór kończy się testem offline na Google Pixel 10 Pro XL,
- nie obejmuje końcowych testów dużych rzeczywistych zbiorów.

### Wersja 0.4

- obejmuje pełne dane, nowe gry, wielogrowe wydanie, pełną skalę, końcowe testy
  dużych zbiorów i hardening,
- M6.6 został zaakceptowany jako obowiązkowy tor iteracyjnego ulepszania modelu
  symboli przed pełnym automatycznym importem,
- TASK-0143–0150 obejmują skumulowane kohorty per gra, panel jakości,
  source-aware dataset, trwały trening, bramkę ONNX, kontrolowaną aktywację,
  przeliczenie wyłącznie `pending` oraz odbiór dwóch iteracji,
- `accepted`, `corrected` i `rejected` są nienaruszalnymi decyzjami człowieka;
  żadna automatyczna operacja modelu nie może ich przeliczyć ani zmienić,
- TASK-0076, TASK-0080–0089 oraz TASK-0143–0150 są przypisane do 0.4.

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

- PostgreSQL jest na migracji `0024_cleanup_operations`; przed rozpoczęciem pionu
  importu 0.2 baza nie zawierała rekordów domenowych,
- podczas odbioru utworzono roboczą grę `777` i image import; job naprawczy
  `65d6ca14-dacc-4341-b015-c187f2d7af36` przetwarza 739 zdjęć przez pełny
  pipeline i pozostaje kontrolowanym procesem w tle,
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
  0.4,
- TASK-0080–0089 należą do pełnego hardeningu 0.4,
- TASK-0143–0150 są zaplanowane w M6.6; nie rozpoczynają się przed zakończeniem
  odbioru workflow importu i Reviewera 0.2,
- masowy import, nowe gry i pełne benchmarki danych nie mogą wejść do bramki 0.2.

## Next recommended task

Kontynuować odbiór właściciela według
`ai_docs/quality/V0_2_ADMIN_ACCEPTANCE.md` i dopisywać regresje do aktywnego
TASK-0142. Niezależny tor Mobile kończy odbiór TASK-0141 na branchu
`ft/change-mobile-app`; nie wymaga formalnego zamknięcia odbioru Admina.
Niezależny tor danych rozpocznie TASK-0143 z M6.6 po spełnieniu jego warunków
wejścia; nie zastępuje on odbioru 0.2.

## Do not start yet

- pełnego importu około 500 000 rzeczywistych layoutów,
- dodawania i testowania kolejnych gier,
- wielogrowego wydania mobilnego,
- pełnej macierzy urządzeń i hardeningu przypisanego do 0.4,
- Celery/Redis, mikroserwisów, chmury, Google Play lub publicznego Admin API.
