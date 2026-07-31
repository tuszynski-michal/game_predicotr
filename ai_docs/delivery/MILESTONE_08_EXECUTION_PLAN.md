---
title: Milestone 08 execution plan
status: accepted
last_updated: 2026-07-31
---

# Plan wykonania Milestone 08 — Private distribution and hardening

## Cel

Przygotować system do powtarzalnego, prywatnego użycia: stały podpis, backup i
restore, diagnostyka, zgodność Android, instrukcje aktualizacji oraz adekwatne
zabezpieczenie lokalnego panelu.
Opcjonalny zakres końcowy może udostępnić osobie zdalnej wyłącznie
game-scoped stanowisko review, bez wystawiania pełnej administracji.

## Alokacja do wydań

- M8.1 i M8.7 zostały ukończone przed wydaniem `0.1` i pozostają jego częścią.
- Minimalną bramkę urządzeniową `0.1` realizuje TASK-0119 na Google Pixel 10
  Pro XL zgodnie z `VERSION_0_1_RELEASE_PLAN.md`.
- M8.2–M8.6, czyli TASK-0080–0089, są odłożonym zakresem wersji `0.3`.
  Dopiero ich ukończenie zamyka pełną bramkę G8 obejmującą stały podpis,
  backup/restore, recovery, formalny rollback i rozszerzoną kompatybilność.

`ROADMAP.md` jest właścicielem granic milestone’u, a ten dokument jest
właścicielem kolejności podetapów, rezerwacji zadań i bramek jakości M8.

## Relevant docs

- `requirements/MOBILE_APP.md`
- `requirements/ADMIN_APP.md`
- `architecture/SYSTEM_ARCHITECTURE.md`
- `architecture/DATA_MODEL.md`
- `architecture/API_CONTRACT.md`
- `quality/TEST_STRATEGY.md`
- `delivery/VERSION_0_1_RELEASE_PLAN.md`
- `delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `delivery/VERSION_0_3_EXECUTION_PLAN.md`
- Q-019 i Q-021 w `project/OPEN_QUESTIONS.md`
- D-003–D-006, D-012–D-014, D-086, D-087, D-100 i D-101 w
  `process/DECISION_LOG.md`

## Warunki wejścia

- pipeline M7 ma ukończone lokalne fundamenty; automatyczna publikacja
  masowego importu w TASK-0076 pozostaje osobną bramką jakości wersji `0.3`,
- Q-019 jest zamknięte: docelowo decyzje review może zapisywać więcej niż jeden
  jawnie identyfikowany operator.
- zakres urządzeń wymaganych dla pełnej bramki `0.3` zostanie zatwierdzony na
  początku tej wersji; odbiór samego `0.1` pozostaje w TASK-0119,
- Wszystkie artefakty przeznaczone do zachowania mają ustaloną lokalizację.

## Zasady realizacji

- aplikacja mobilna pozostaje całkowicie offline,
- finalny APK nie deklaruje uprawnienia `INTERNET`,
- klucz podpisujący i sekrety nie trafiają do repozytorium ani logów,
- backup jest uznany za działający dopiero po teście restore,
- destrukcyjne operacje wymagają jawnego celu i potwierdzenia,
- publiczna dystrybucja, chmura i Google Play pozostają poza zakresem,
- zdalne review nie może zmienić domyślnego loopback ani udostępnić pełnego
  Admin API.

## M8.1 — Model bezpieczeństwa lokalnej administracji

### Zakres

- odpowiedź Q-019 i zakres administratorów,
- granica loopback/LAN,
- auth albo świadomie zaakceptowany brak auth dla jednego lokalnego operatora,
- ochrona operacji destrukcyjnych,
- audyt zmian zgodny z wybranym modelem,
- przegląd sekretów i danych w logach.

### Zadania

- `TASK-0078 — Local administration threat model and Q-019 decision` — done
- `TASK-0079 — Administration access control and audit hardening` — done

### Bramka G8.1

Stan 2026-07-31: G8.1 jest zamknięta. Centralny guard mutacji wymusza loopback,
origin, intencję i dokładny cel operacji wysokiego wpływu; append-only audyt
używa aktora `local-owner`, a OpenAPI, klient i CSP Admina mają regresję.

- model jednego lub wielu administratorów jest jawny,
- panel nie jest przypadkowo wystawiony publicznie,
- mechanizm auth/audytu odpowiada decyzji, bez pozornej ochrony,
- destrukcyjne operacje wymagają właściwego potwierdzenia i wskazania celu,
- logi, OpenAPI i artefakty nie ujawniają sekretów.

## M8.2 — Stabilny podpis i odtwarzalny build

### Zakres

- trwały klucz podpisujący poza repozytorium,
- bezpieczna lokalna konfiguracja sekretu,
- spójny `applicationId`, versionCode i versionName,
- aktualizacja istniejącej instalacji,
- weryfikacja snapshotu, APK, ABI i manifestu,
- kontrola braku `INTERNET`,
- odtwarzalny raport builda.

### Zadania

- `TASK-0080 — Stable Android signing and secret handling`
- `TASK-0081 — Reproducible private release verification`

### Bramka G8.2

- klucz nie znajduje się w Git, logach ani artefakcie diagnostycznym,
- nowe APK aktualizuje poprzednią instalację bez zmiany tożsamości aplikacji,
- release report zawiera wersje i checksumy,
- finalny manifest nie deklaruje `INTERNET`,
- APK nie wymaga Metro, API ani komputera deweloperskiego,
- nieudana weryfikacja blokuje status `ready`.

## M8.3 — Backup i restore

### Zakres

- backup PostgreSQL,
- backup zdjęć, modeli, eksportów, snapshotów i APK,
- manifest checksum oraz relacje wersji,
- restore do czystego środowiska,
- kontrola spójności po restore,
- instrukcja częstotliwości i miejsca przechowywania.

### Zadania

- `TASK-0082 — PostgreSQL backup and restore workflow`
- `TASK-0083 — File artifacts backup, restore and verification`

### Bramka G8.3

- backup można odtworzyć bez dostępu do starej instancji,
- wersje bazy i plików są zgodne po restore,
- checksumy wykrywają brak lub uszkodzenie artefaktu,
- procedura nie nadpisuje istniejących danych bez jawnej zgody,
- test restore jest wykonany, a nie tylko opisany.

## M8.4 — Diagnostyka uszkodzonego snapshotu

### Zakres

- scenariusze brakującego, starego i uszkodzonego SQLite,
- `local_data_error` bez częściowych obliczeń,
- informacje diagnostyczne bez danych wrażliwych,
- procedura ponownej instalacji/aktualizacji,
- zachowanie poprzedniego artefaktu do rollbacku administracyjnego.

### Zadanie

- `TASK-0084 — Corrupted snapshot diagnostics and recovery`

### Bramka G8.4

- mobile nigdy nie uruchamia matching ani Target na niezweryfikowanej bazie,
- komunikat pozwala wskazać release/schema bez ujawniania sekretów,
- uszkodzenie jest odtwarzalne w teście,
- instrukcja prowadzi do sprawdzonego odzyskania poprawnego działania.

## M8.5 — Macierz urządzeń i regresja offline

### Zakres

- macierz urządzeń wersji `0.3`, której obowiązkowy skład zostanie uzgodniony
  przed rozpoczęciem TASK-0085,
- Google Pixel 10 Pro XL jako urządzenie bazowe z odebranej wersji `0.1`,
- Galaxy S21 Ultra i ewentualne pozostałe urządzenia do łącznej liczby 3–5,
- wersje Android, rozdzielczość, pamięć i ABI,
- instalacja, aktualizacja i ponowne uruchomienie,
- tryb samolotowy i brak sieci,
- unique, duplicate, not_found i Target,
- rozmiar, czasy, płynność i dostępność UI.

### Zadania

- `TASK-0085 — Android device compatibility matrix`
- `TASK-0086 — Offline install and update regression`
- `TASK-0087 — Mobile performance and accessibility acceptance`

### Bramka G8.5

- wszystkie urządzenia wskazane dla wersji `0.3` przechodzą obowiązkowy
  scenariusz; wcześniejszy odbiór Pixela z TASK-0119 może być dowodem bazowym,
  ale nie zastępuje regresji zmienionego artefaktu 0.3,
- aktualizacja aktywuje nowy snapshot i nie używa starej kopii,
- brak sieci nie zmienia funkcjonalności,
- manifest nie ma `INTERNET`,
- krytyczne czasy i rozmiary są zapisane per urządzenie,
- nie ma błędu blokującego ani nieudokumentowanego wyjątku kompatybilności.

## M8.6 — Prywatna dystrybucja i odbiór końcowy

### Zakres

- instrukcja przygotowania release z panelu,
- instrukcja sideload, update i diagnostyki,
- katalogowanie wersji oraz checksum,
- rollback przez instalację świadomie wybranej kompatybilnej wersji,
- finalna lista kontrolna,
- pełny test od backupu danych do działającego APK.

### Zadania

- `TASK-0088 — Private distribution, update and rollback runbook`
- `TASK-0089 — Disaster recovery and final system acceptance`

### Bramka G8.6

- administrator odtwarza środowisko z backupu,
- przygotowuje nowe wydanie z panelu,
- weryfikuje i instaluje APK na urządzeniach,
- aktualizacja oraz scenariusze mobile przechodzą całkowicie offline,
- poprzednie wydania i ich checksumy pozostają audytowalne,
- dokumentacja umożliwia wykonanie procesu w nowej sesji bez historii czatu,
- wszystkie błędy krytyczne są zamknięte, a ograniczenia zaakceptowane.

## M8.7 — Opcjonalne zdalne review

### Zakres

- threat model dla domowego komputera wystawiającego ograniczony panel,
- game-scoped, odwoływalna i wygasająca sesja review,
- link z nieujawniającym sekretu identyfikatorem oraz osobno przekazywany kod,
- przechowywanie wyłącznie hasha kodu, limit prób i blokada brute force,
- reviewer role bez dostępu do konfiguracji, jobów, eksportów i wydań,
- HTTPS przez jawnie wybrany tunel albo VPN, bez surowego port forwarding,
- audyt aktora/sesji, optimistic revision i unieważnienie dostępu,
- instrukcja uruchomienia, zatrzymania i sprawdzenia ekspozycji.

### Zadania

- `TASK-0113 — Remote reviewer threat model and session hardening`,
- `TASK-0114 — Revocable game-scoped authorization and brute-force protection`,
- `TASK-0115 — Secure ingress runbook and remote end-to-end acceptance`.

Stan 2026-07-31: TASK-0113, TASK-0114 i TASK-0115 są ukończone. Odbiór HTTPS
z innego urządzenia i innej sieci potwierdził właściwy scope, trwałość decyzji
oraz natychmiastowe zatrzymanie publicznej ekspozycji. Bramka G8.7 jest
zamknięta.

### Bramka G8.7

- bez zdalnego trybu panel i API nadal odrzucają adresy inne niż loopback,
- link bez poprawnego kodu nie ujawnia obrazów ani metadanych gry,
- kod wygasa, ma limit prób, nie występuje w bazie, URL ani logach w postaci
  jawnej,
- unieważnienie natychmiast blokuje kolejne odczyty i zapisy,
- reviewer nie może wywołać żadnego endpointu poza zakresem wskazanej gry i
  review,
- wszystkie decyzje nadal używają idempotencji i expected revision,
- połączenie działa przez HTTPS, a test z sieci zewnętrznej nie wymaga
  otwierania surowego portu routera.

### Bramka G8

Pełna bramka G8 należy do wersji `0.3` i wymaga G8.1–G8.6. G8.7 zostało już
zamknięte i pozostaje dodatkowym, wąskim zakresem zdalnego review.

## Mapa zadań M8

| Podetap | Zadania | Liczba |
|---|---:|---:|
| M8.1 Bezpieczeństwo | TASK-0078–0079 | 2 |
| M8.2 Podpis i build | TASK-0080–0081 | 2 |
| M8.3 Backup i restore | TASK-0082–0083 | 2 |
| M8.4 Diagnostyka snapshotu | TASK-0084 | 1 |
| M8.5 Urządzenia | TASK-0085–0087 | 3 |
| M8.6 Dystrybucja i odbiór | TASK-0088–0089 | 2 |
| M8.7 Zdalne review (opcjonalne) | TASK-0113–0115 | 3 |
| **Razem M8 core** | **TASK-0078–0089** | **12** |
| **Razem z M8.7** | **TASK-0078–0089, TASK-0113–0115** | **15** |

## Zakończenie roadmapy

Po przejściu G8 w wersji `0.3` system spełnia zaakceptowany zakres prywatnej
dystrybucji i hardeningu.
Publiczny backend ogólnego przeznaczenia, synchronizacja, Google Play, chmura
i zdalny dostęp do pełnej administracji wymagają nowej decyzji właściciela.
M8.7 jest wąskim wyjątkiem wyłącznie dla review.
