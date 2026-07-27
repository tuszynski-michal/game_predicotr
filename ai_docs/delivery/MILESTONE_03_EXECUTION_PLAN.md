---
title: Milestone 03 execution plan
status: accepted
last_updated: 2026-07-27
---

# Plan wykonania Milestone 03 — Versioned mobile release pipeline

## Cel

Połączyć opublikowane dane panelu z wznawialnym workerem, precomputingiem
payoutów, deterministycznym snapshotem SQLite i wersjonowanym APK. Zmierzyć
docelowy rząd wielkości 500 000 layoutów na grę przed utrwaleniem adapterów.

`ROADMAP.md` jest właścicielem granic milestone’u, a ten dokument jest
właścicielem kolejności podetapów, rezerwacji zadań i bramek jakości M3.

## Relevant docs

- `requirements/ADMIN_APP.md`
- `requirements/ALGORITHMS.md`
- `requirements/MOBILE_APP.md`
- `architecture/SYSTEM_ARCHITECTURE.md`
- `architecture/DATA_MODEL.md`
- `architecture/API_CONTRACT.md`
- `quality/TEST_STRATEGY.md`
- D-005–D-007, D-012–D-014 w `process/DECISION_LOG.md`

## Warunki wejścia

- M2 przechodzi G2.
- Dataset i rules version są niezmienne i mają zgodne wymiary.
- Algorytm payout z M1 ma wspólne golden fixtures dostępne dla workera.

## Zasady realizacji

- długie operacje nie działają wewnątrz requestu FastAPI,
- początkowo wykonywany jest najwyżej jeden ciężki job naraz,
- nie dodajemy Redis/Celery ani natywnego adaptera bez wyniku benchmarku,
- artefakty i opublikowane wersje są niezmienne,
- mobile nadal nie łączy się z API,
- plik zadania powstaje dopiero bezpośrednio przed rozpoczęciem zakresu.

## M3.1 — Trwałe jobs i worker

### Zakres

- stan i typowane payloady jobs,
- bezpieczne przejścia stanów, progress i error codes,
- lokalny worker/CLI poza procesem HTTP,
- polling lub jawne uruchomienie bez Redis/Celery,
- anulowanie, checkpoint i wznowienie,
- jeden ciężki job jednocześnie,
- ekran jobs w panelu.

### Zadania

- `TASK-0029 — Job state machine and Admin API` — done 2026-07-27
- `TASK-0030 — Local worker execution, lease and resume` — done 2026-07-27
- `TASK-0031 — Jobs progress and error UI` — done 2026-07-27

### Bramka G3.1

- długi job nie blokuje requestu FastAPI,
- błędne przejście statusu jest odrzucane,
- worker po restarcie wznawia lub bezpiecznie oznacza zadanie zgodnie z
  kontraktem,
- anulowanie zatrzymuje się w bezpiecznym punkcie,
- ponowienie nie dubluje wyników,
- panel pokazuje etap, postęp, błąd i czasy.

G3.1 zaliczona 2026-07-27.

## M3.2 — Precomputing payoutów i audyt

### Zakres

- batch evaluation dla `(dataset, rules, algorithm)`,
- trwały `layout_payout`,
- ślad interpretacji dla audytu poza mobile,
- invalidacja logiczna po zmianie wersji,
- kontrola kompletności przed snapshotem.

### Zadania

- `TASK-0032 — Batch payout precomputation and audit`
- `TASK-0033 — Payout completeness, restart and version safety`

### Bramka G3.2

- każdy layout ma dokładnie jeden aktualny payout dla wskazanych wersji,
- golden cases są identyczne z wynikiem M1,
- przerwanie i wznowienie nie zmienia wyniku ani nie tworzy duplikatów,
- brak reguły, zły symbol lub niezgodne wymiary zatrzymują publikację,
- audyt pozwala odtworzyć paylines, symbole, jokery i sumę.

## M3.3 — Produkcyjny snapshot SQLite

### Zakres

- finalny dla tego etapu schemat mobilny,
- deterministyczna serializacja gier, symboli i layoutów,
- indeks exact oraz kandydat prefix zatwierdzany benchmarkiem,
- manifest wersji, liczników i checksum,
- walidator integralności,
- niezmienny katalog artefaktu.

### Zadania

- `TASK-0034 — Production SQLite snapshot generator`
- `TASK-0035 — Snapshot validator, manifest and artifact layout`

### Bramka G3.3

- identyczne wejścia tworzą identyczną treść logiczną i manifest,
- wszystkie wersje oraz liczby rekordów są zapisane,
- snapshot nie zawiera stagingu, zdjęć ani tabel administracyjnych,
- dokładna/prefiksowa semantyka odpowiada kontraktom M1,
- uszkodzenie, luka lub brak payoutu są wykrywane przed buildem,
- artefakt poprzedniej wersji nie jest nadpisywany.

## M3.4 — Orkiestracja wydania i panel Android

### Zakres

- `mobile_release` i wybór wersji dla każdej gry,
- walidacja kompletności,
- workflow payout → snapshot → verify → Android build → verify,
- status `ready` dopiero po pełnym sukcesie,
- checksum SQLite i APK,
- panel tworzenia wydania oraz otwarcia katalogu artefaktów,
- fizyczny test aktualizacji bez odinstalowania do APK z celowo zmienioną
  `releaseVersion` i checksumą snapshotu,
- potwierdzenie w aplikacji, że aktywowano nowy snapshot zamiast lokalnej kopii
  poprzedniego wydania.

### Zadania

- `TASK-0036 — Mobile release domain and API`
- `TASK-0037 — Release workflow orchestration`
- `TASK-0038 — Android release panel and artifact UI`
- `TASK-0039 — Release failure and immutability integration tests`

### Bramka G3.4

- panel nie uruchamia dowolnej komendy użytkownika,
- niezgodny dataset/rules nie rozpoczyna builda,
- nieudany etap nie daje statusu `ready`,
- gotowe APK zawiera dokładnie snapshot z manifestu release,
- poprzednie wydanie i jego checksumy pozostają dostępne,
- API zwraca lokalne ścieżki, ale nie instaluje APK na urządzeniu,
- ręczny sideload na urządzeniu aktualizuje istniejącą aplikację, a ekran
  potwierdza wersję celowo zmienionego snapshotu zgodnie z D-012 i D-020.

## M3.5 — Benchmark 500 000 layoutów

### Zakres

- deterministyczny benchmark datasetu jednej gry,
- estymacja 12–15 gier,
- rozmiar PostgreSQL, SQLite i APK,
- exact match, prefix match, otwarcie bazy i skan `N - 1`,
- pamięć workera i mobile,
- zapis modelu urządzenia, Androida i konfiguracji builda,
- dokładne czasy matching, pełnego Target i przewijania tabeli na urządzeniach,
- decyzja o reprezentacji sygnatury i adapterze.

### Zadania

- `TASK-0040 — Representative 500k benchmark dataset`
- `TASK-0041 — SQLite, mobile and worker performance benchmark`
- `TASK-0042 — Benchmark decision and release pipeline acceptance`

### Bramka G3

- pełny workflow z panelu tworzy zweryfikowany snapshot i APK,
- wynik jest odtwarzalny dla tych samych wersji,
- wszystkie pomiary z `TEST_STRATEGY.md` są zapisane,
- osiągnięto robocze budżety albo zaakceptowano udokumentowaną zmianę adaptera
  i powtórzono pomiar,
- nie dodano Redis/Celery ani natywnego modułu bez dowodu pomiarowego,
- administrator potrafi wskazać gotowy APK do ręcznego sideloadu.

## Mapa zadań M3

| Podetap | Zadania | Liczba |
|---|---:|---:|
| M3.1 Jobs i worker | TASK-0029–0031 | 3 |
| M3.2 Precomputing payoutów | TASK-0032–0033 | 2 |
| M3.3 Snapshot SQLite | TASK-0034–0035 | 2 |
| M3.4 Release workflow | TASK-0036–0039 | 4 |
| M3.5 Benchmark 500k | TASK-0040–0042 | 3 |
| **Razem M3** | **TASK-0029–0042** | **14** |

## Następny milestone

Po przejściu G3 i poleceniu właściciela obowiązuje
`MILESTONE_04_EXECUTION_PLAN.md`.
