---
title: Version 0.2 execution plan
status: accepted
last_updated: 2026-07-31
---

# Plan wykonania wersji 0.2

## Cel

Zbudować na czystej lokalnej bazie prosty, prowadzony workflow Admina:
gra → import małego zestawu testowego → symbole → reguły → zatwierdzanie →
testowe wydanie Android. Wersja `0.2` służy walidacji funkcji i ergonomii, a
nie skali docelowego datasetu.

## Relacja z wersją 0.1

- statyczna paczka `0.1.5 (6)` jest ukończona i chroniona,
- TASK-0119 oraz poprawki wykryte podczas odbioru Pixela mogą być wykonywane
  równolegle z rozwojem `0.2`,
- reset danych `0.2` nie może usunąć APK, snapshotu, manifestu, grafik ani
  raportu wydania `0.1`,
- przejście do `0.3` wymaga zaakceptowania przez właściciela testów `0.1` i
  `0.2` oraz zamknięcia znalezionych błędów o uzgodnionym priorytecie.

## Zasady danych testowych 0.2

- aktywny PostgreSQL zaczyna od pustego, zmigrowanego schematu,
- `0.2` używa jednej kontrolowanej gry i ograniczonego podzbioru layoutów,
- liczba layoutów wynika z testu danego pionu; nie obowiązuje bramka 500 000,
- kompletność jest liczona względem jawnego `expected_layout_count` testowego
  datasetu, a nie względem docelowej skali produktu,
- testy muszą nadal obejmować unique, duplicate, not found, payout i Target,
- mały dataset `0.2` nie jest dowodem gotowości wydajnościowej ani jakościowej
  dla pełnego importu.

## V0.2.0 — Czysty stan danych

- `TASK-0120 — Controlled PostgreSQL reset and v0.2 clean baseline`
  — **ukończone 2026-07-31**: zapisano pełny dump i inwentarz, zabezpieczono
  instalacyjne APK 0.1, wyczyszczono dane domenowe/joby, a schemat odtworzono
  migracjami Alembic do `0021_reviewer_access`.

### Dane chronione podczas TASK-0120

- `artifacts/v01-representative-release/` w całości,
- `.tooling/android-signing/` i konfiguracja toolchainu,
- zdjęcia źródłowe oraz ręczne materiały wejściowe poza PostgreSQL,
- kod, migracje, dokumentacja, test fixtures i raporty jakości,
- `apps/mobile/assets/snapshot/m1-snapshot.db` do czasu świadomego zastąpienia
  fixture’em `0.2`.

### Bramka V0.2.0

- destrukcyjny reset ma zatwierdzony dokładny cel i nie używa szerokiej ścieżki,
- schemat PostgreSQL jest na `alembic head`, a tabele domenowe nie zawierają
  danych poprzedniej iteracji,
- nie istnieje aktywny job, sesja Reviewera ani release wskazujący na usunięte
  rekordy,
- checksumy paczki `0.1` są niezmienione,
- powstał krótki raport z listą usuniętych klas danych i zachowanych artefaktów.

Bramka została spełniona. Raport znajduje się w
`artifacts/v02-clean-baseline/reset-report.json`, a przywracanie dumpu nie jest
częścią zwykłego startu wersji 0.2.

## V0.2.1 — Nawigacja i jeden kontekst gry

- `TASK-0121 — Admin workspace navigation and collapsible sections`
  — trzy kafelki trybu (`Zarządzanie grami`, `Wersje Android`, `Joby`),
  accordion zarządzania grą, zachowanie scrolla i stan w URL.
- `TASK-0122 — Active game catalog, filters and archiving`
  — sekcja `Gry`, podświetlenie, filtry statusu i odwracalna archiwizacja; bez
  fizycznego usuwania gry w `0.2`.

### Bramka V0.2.1

- bez aktywnej gry wejście pokazuje wyłącznie `Gry`,
- zawsze istnieje najwyżej jeden aktywny kontekst gry,
- zmiana sekcji nie resetuje wyboru ani pozycji użytkownika,
- zależne sekcje nie mają drugiego selecta gry.

## V0.2.2 — Mały import zdjęć i katalog symboli

- `TASK-0123 — Local image folder source and resumable test ingestion`
  — natywny dialog `Wybierz folder` na Windows, walidacja katalogu, discovery,
  manifest i wznowienie.
- `TASK-0124 — Test dataset completeness, gaps and source quality selection`
  — konfigurowalny oczekiwany zakres, brakujące numery, opcjonalna ręczna
  korekta numeru, doładowanie zdjęć oraz automatyczny/ręczny wybór źródła.
- `TASK-0125 — Automatic symbol catalog bootstrap from imported layouts`
  — oczekiwana liczba symboli, propozycje nazw, stabilne kody oraz ręczne
  rozwiązanie konfliktu liczby klastrów.
- `TASK-0126 — Representative symbol image picker and catalog refinement`
  — kandydatury grafik oraz edycja grafiki i nazwy.

### Bramka V0.2.2

- import nie zależy od `examples/imgs` ani Excela,
- ponowienie nie dubluje sekwencji,
- UI pokazuje kompletność względem testowego `expected_layout_count`,
- symbole powstają z rzeczywistych cropów testowego importu,
- oryginały są kopiowane do kontrolowanego content-addressed storage,
- każda automatyczna decyzja zachowuje pochodzenie i metrykę jakości.

## V0.2.3 — Reguły i zatwierdzanie bez technicznego szumu

- `TASK-0127 — Single rules workspace with internal immutable versioning`
  — jeden bieżący widok bez eksponowania pełnej historii.
- `TASK-0128 — Test-dataset payout recomputation workflow`
  — jawne przeliczenie, progress, wersja algorytmu i blokada przy brakach.
- `TASK-0129 — Integrated board approval entry and prerequisite states`
  — jedna sekcja zatwierdzania prowadząca do osobnego Reviewera.
- `TASK-0130 — Remove duplicate Dataset and Manual Review navigation`
  — przeniesienie funkcji bez usuwania encji i audytów backendu.

### Bramka V0.2.3

- zmiana reguł nie modyfikuje opublikowanej historii,
- payout całego małego datasetu można przeliczyć i wznowić,
- zatwierdzanie jest dostępne wyłącznie dla prawidłowego importu,
- nie ma dwóch ekranów wykonujących tę samą decyzję review.

## V0.2.4 — Testowe wydanie i odbiór workflow

- `TASK-0131 — Android release workspace for the controlled test game`
  — jedna orkiestracja dla aktywnej gry; test wielu gier należy do `0.3`.
- `TASK-0132 — Simple Jobs workspace and status filters`
  — osobna lista jobów, postęp, prosty filtr statusu i kompaktowa diagnostyka
  bez dodatkowej logiki retencji.
- `TASK-0133 — Safe cleanup controls for v0.2 working data`
  — pełne usuwanie wybranego wydania oraz kontrolowany reset wszystkich danych
  layoutów wskazanej gry do stanu sprzed importu, z preview zależności.
- `TASK-0134 — Admin 0.2 end-to-end usability and regression acceptance`
  — desktop 1366 × 768, klawiatura, loading/error/empty i pełny mały workflow.

### Bramka V0.2

- Admin realizuje prowadzony workflow bez duplikowania kontekstu gry,
- workflow działa od pustej bazy do testowego artefaktu,
- mały dataset pokrywa podstawowe warianty domenowe, ale nie udaje pełnej skali,
- użytkownik może sprawdzić postęp wszystkich jobów w oddzielnej trzeciej
  zakładce bez mieszania ich z formularzami gry i wydania,
- cleanup nie narusza innego aktywnego artefaktu ani minimalnego audytu
  wykonanej operacji,
- właściciel wykonał testy `0.2`, a zaakceptowane poprawki są zamknięte albo
  jawnie odłożone.

## Świadomie poza 0.2

- pełny dataset obejmujący wszystkie dostępne layouty,
- automatyczna publikacja około 500 000 rzeczywistych layoutów,
- dodawanie i testowanie kolejnych gier,
- wielogrowe wydanie mobilne,
- pełne benchmarki skali, rozszerzona macierz urządzeń i finalny hardening,
- TASK-0076 oraz TASK-0080–0089.

Powyższy zakres należy do [wersji 0.3](VERSION_0_3_EXECUTION_PLAN.md).

## Poza zakresem bez nowej decyzji

- Google Play i publiczna dystrybucja,
- publiczny Admin API lub PostgreSQL,
- synchronizacja mobile z backendem,
- automatyczne kasowanie decyzji człowieka, audytu lub aktywnego release.
