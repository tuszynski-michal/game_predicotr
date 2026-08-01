---
title: Current project state
status: active
last_updated: 2026-08-01
---

# Current State

## Phase

`Version 0.2 technically complete — owner acceptance pending`

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
- TASK-0119 — ręczne testy offline i końcowy odbiór Pixela — pozostaje otwarty,
- test wstępny 0.1 potwierdził start aplikacji i wykonywanie obliczeń; dokładna
  weryfikacja poprawności zostanie dokończona później przez właściciela,
- błędy znalezione w odbiorze 0.1 będą naprawiane równolegle z pracą nad 0.2.

### Wersja 0.2

- rozwój może rozpocząć się przed zakończeniem TASK-0119,
- TASK-0120 zakończył kontrolowany reset lokalnego PostgreSQL,
- TASK-0121 zakończył przebudowę Admina na trzy workspace’y, jeden kontekst gry
  i accordion zależnych sekcji ze stanem w URL,
- TASK-0122 dodał trzy filtry katalogu gier, spójny wybór kontekstu oraz
  odwracalne przywrócenie zarchiwizowanej gry jako szkicu,
- TASK-0123 dodał natywny wybór folderu Windows, jednorazowy token zatwierdzonej
  ścieżki, typowany image import oraz wznawialne kopiowanie JPEG-ów do
  content-addressed `data/originals` z niezmiennym manifestem,
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

- obejmuje pełne dane, nowe gry, wielogrowe wydanie, pełną skalę, końcowe testy
  dużych zbiorów i hardening,
- TASK-0076 oraz TASK-0080–0089 są przypisane do 0.4.

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
- nie istnieją aktywne joby, sesje Reviewera, gry, datasety ani wydania,
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
- masowy import, nowe gry i pełne benchmarki danych nie mogą wejść do bramki 0.2.

## Next recommended task

Wykonać krótki odbiór właściciela według
`ai_docs/quality/V0_2_ADMIN_ACCEPTANCE.md`. Po potwierdzeniu nawigacji, małego
workflow, jednego wydania i preview cleanup można zamknąć produktową bramkę 0.2;
następny zaplanowany pion to TASK-0135 z wersji 0.3. Regresje blokujące odbiór
0.1 lub 0.2 pozostają jawnie śledzone.

## Do not start yet

- pełnego importu około 500 000 rzeczywistych layoutów,
- dodawania i testowania kolejnych gier,
- wielogrowego wydania mobilnego,
- pełnej macierzy urządzeń i hardeningu przypisanego do 0.4,
- Celery/Redis, mikroserwisów, chmury, Google Play lub publicznego Admin API.
