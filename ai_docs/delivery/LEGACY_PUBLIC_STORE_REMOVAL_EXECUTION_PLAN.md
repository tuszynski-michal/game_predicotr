---
title: Usunięcie legacy magazynu gier ze schematu public
status: accepted
last_updated: 2026-09-25
---

# `game_data_v2` jako jedyny magazyn danych gier

## Stan obecny, cel i granice

PostgreSQL `game_predictor` jest na Alembic head `0124_game_data_v2_partial_visibility_constraints`. `game_data_v2` jest magazynem generacji 2, z 65 partycjonowanymi tabelami game-owned z zamrożonego manifestu v1 (D-377). Trzy aktywne gry — `777` (`bfc4f949-5c14-4850-b02a-db99610bcfa5`), `mumie` (`cf300bc1-…`) i `Mumie` (`2a46d3a6-…`) — mają aktywne rekordy `public.game_storage_locations` ze schematem `game_data_v2`, generacją `2` i manifestem `game-data-v2-manifest-v1`.

W `public` nadal znajdują się historyczne kopie tych 65 tabel. Według odczytu z 2026-09-25 wszystkie są puste (łącznie około 3,5 MB); `game_storage_migrations` ma zero wierszy, gdyż TASK-0525 wykonał greenfield cutover, a nie migrację `public → game_data_v2`. Ten odczyt jest faktem wejściowym planu, nie zgodą na DDL: T01 musi powtórzyć go bez zapisu tuż przed przygotowaniem migracji, a T09 ponownie bezpośrednio przed jej zastosowaniem.

**Cel:** po zakończeniu aktywna aplikacja PostgreSQL ma jeden fizyczny data plane danych należących do gry: `game_data_v2`. Schemat `public` pozostaje globalnym catalog/control/shared plane. Oznacza to, że pozostają w nim m.in. `games`, `symbols`, `rules_versions`, `rules_version_symbols`, `paylines`, `payout_rules`, globalne `jobs`, registry storage oraz tabele shared z manifestu — nie są one kopiami legacy danych gry i nie są usuwane tym planem.

**Poza zakresem:** przenoszenie danych między magazynami, dual-write, zmiana trzech aktywnych location, kasowanie partycji V2, GC plików, `VACUUM FULL`, zmiana danych użytkownika, przebudowa katalogu/shared plane, push, merge, wdrożenie oraz aktywacja modelu. Nie uruchamia się 0125 ani żadnego `DROP` wyłącznie wskutek zaakceptowania planu; T09 wymaga osobnej, dokładnej zgody użytkownika po pokazaniu aktualnego preflightu.

## Rekomendowana decyzja D-448

**D-448 (accepted):** dla PostgreSQL `game_data_v2` jest jedynym fizycznym magazynem relacji game-owned. `public` nie jest fallbackiem dla game-owned read/write; brak poprawnej aktywnej location V2 jest stanem fail-closed. Historyczne, puste kopie 65 relacji z manifestu v1 usuwa migracja `0125_remove_legacy_public_game_store` wyłącznie przez statyczną, manifest-bound listę `DROP TABLE ... RESTRICT` w kolejności od zależnych do rodziców. Nie używa `CASCADE`, dynamicznego DDL z katalogu, migracji danych ani rollbacku udającego odtworzenie utraconych danych.

Uzasadnienie: greenfield cutover już potwierdził V2 jako jedyną aktywną ścieżkę, a legacy kopie zwiększają ryzyko przypadkowego odczytu pustego `public` (por. regresję D-440). `RESTRICT`, dwa niezależne preflighty i połączenie routera z testami zarówno V2, jak i braku location chronią przed usunięciem relacji wspólnych albo niezauważonym fallbackiem. `downgrade()` 0125 ma jawnie odmówić działania; nie istnieje bezstratne odtworzenie nieznanej historycznej zawartości tabel.

## Inwarianty i kontrakty

| Obszar | Wymagane zachowanie | Zabronione skróty |
|---|---|---|
| Własność | Lista usuwanych relacji pochodzi z zamrożonego `game_data_v2_manifest_v1.GAME_TABLES`; katalog i shared/control plane pozostają w `public`. | Wnioskowanie po prefiksie nazwy, `DROP SCHEMA public`, `CASCADE`. |
| Routing | Każdy produkcyjny dostęp game-owned najpierw wiąże `GameStorageRouter` z aktywną location V2; brak/uszkodzona location zatrzymuje operację. | Cichy `search_path` do pustego `public`, domyślne `legacy-public-v1` na PostgreSQL. |
| DDL | 0125 przed każdym `DROP` sprawdza, że relacja istnieje, jest zwykłą tabelą `public`, należy do zamrożonej listy i ma zero wierszy; potem `DROP ... RESTRICT` w ustalonej kolejności FK. | `CASCADE`, dynamiczna lista z produkcyjnego katalogu, wyłączenie FK/trigerów. |
| Recovery | Błąd preflightu, niepusta tabela, zależność spoza listy, aktywny job maintenance albo timeout kończy operację bez dalszego DDL. Po częściowym błędzie operator używa raportu katalogu i ponownie uruchamia 0125; nie cofa schematu przez rekonstrukcję danych. | Kontynuowanie po błędzie, ręczne tworzenie pustych tabel jako „rollback”. |
| Dane i operacje | T01/T09 są read-only. Zastosowanie 0125 wymaga aktualnego raportu, okna maintenance i osobnej zgody. | Traktowanie odczytu z 2026-09-25 jako trwałego dowodu lub uruchamianie DDL podczas normalnej pracy. |

Kolejność DDL jest częścią migracji, wyprowadzoną w T05 z FK między **publicznymi** kopiami i zapisaną jako literalna lista wraz z testem. Jeżeli aktualne metadane wykryją zależność, której nie ma w tym porządku, migracja kończy się przed pierwszym dropem. `alembic_version`, registry `game_storage_*` i V2 parents nie są kandydatami do DDL.

## Zadania, etapy i punkty STOP

Każdy task ma własny audyt, commit, Outcome i aktualizację `CURRENT_STATE.md`. Polecenie uruchomienia etapu uruchamia wszystkie jego taski, ale nie zastępuje osobnej zgody na T09.

| Etap | Task | Wynik i bramka |
|---|---|---|
| P00 | [TASK-0679](../tasks/completed/0679-legacy-public-store-removal-plan.md) | Plan, D-448 i taski; nie uruchamia A. |
| A | [TASK-0680](../tasks/completed/0680-legacy-public-store-inventory.md) | Read-only inventory wykazał dokładny zakres, pustość, location V2 i brak aktywnej migracji. |
| A | [TASK-0681](../tasks/completed/0681-v2-only-storage-routing.md) | Router i kontrakt katalogu są V2-only na PostgreSQL, bez fallbacku legacy. |
| A | [TASK-0682](../tasks/completed/0682-game-owned-access-routing-audit.md) | Wszystkie produkcyjne repository, workery i raw SQL game-owned mają testowany bind. |
| A | [TASK-0683](../tasks/completed/0683-v2-only-test-and-bootstrap-contract.md) | Bootstrap/fixture provisionuje V2 bez zależności od kopii `public` przed ich usunięciem. |
| B | [TASK-0684](../tasks/completed/0684-legacy-public-store-migration-0125.md) | Manifest-bound migracja 0125, bez `CASCADE`, ma izolowany dowód PostgreSQL, w tym fresh-head po 0125. |
| B | [TASK-0685](../tasks/0685-legacy-public-store-migration-rehearsal.md) | Dry-run i odbiór release/migration wykazują warunki startu, timeouty i ścieżkę po błędzie. |
| B | [TASK-0686](../tasks/0686-legacy-public-store-operations-docs.md) | Instrukcja preflight/approval/postflight oraz obserwowalność nie mylą public z data plane. |
| STOP B | — | Pokaż operatorowi świeży raport T01/T05, review DDL, plan okna i dokładny zakres. Bez jawnego polecenia T09 plan zatrzymuje się tutaj. |
| C | [TASK-0687](../tasks/0687-v2-only-release-readiness.md) | Wersja aplikacji gotowa do działania bez kopii publicznych; tylko read-only smoke przed operacją. |
| C | [TASK-0688](../tasks/0688-apply-legacy-public-store-removal.md) | Po osobnej zgodzie: 0125 stosuje się raz, z utrwalonym raportem przed/po. |
| C | [TASK-0689](../tasks/0689-post-removal-operational-acceptance.md) | Aktywne gry, API i worker przechodzą postflight bez relacji legacy. |
| D | [TASK-0690](../tasks/0690-remove-legacy-public-code-paths.md) | Usunięte są już nieosiągalne oznaczenia/adaptery legacy, bez naruszenia testowego adaptera nie-PostgreSQL. |
| D | [TASK-0691](../tasks/0691-legacy-public-store-final-acceptance.md) | Końcowy audyt i dokumentacja potwierdzają granicę V2-only. |

**STOP A:** jeśli inventory wskazuje choć jedną niepustą relację legacy, location różną od active V2, aktywną migrację, nierozpoznaną zależność lub niezgodny manifest, nie tworzy się migracji usuwającej; potrzebny jest nowy plan migracji danych lub decyzja. **STOP B:** brak pełnego izolowanego testu, niezależnego review DDL lub instrukcji operatorskiej blokuje T08/T09. **STOP C:** błąd postflightu zatrzymuje D; nie rekonstruuje się pustych kopii bez nowej decyzji i dowodu danych.

**Korekta sekwencji 2026-09-25:** T04 testuje bootstrap V2 na aktualnym
headzie przed migracją usuwającą, ponieważ nie może uczciwie udowodnić stanu
po rewizji, która jeszcze nie istnieje. Dowód świeżej bazy podniesionej do
head `0125` bez 65 relacji legacy należy do T05, który tworzy `0125`.

## Mapa wymagań, dowody i ryzyka

| Wymaganie | Zadania | Dowód |
|---|---|---|
| Tylko V2 dla game-owned | T02–T04, T08–T11 | test braku fallbacku, testy V2 repository/raw SQL oraz smoke aktywnych gier. |
| Usunąć wyłącznie 65 pustych kopii | T01, T05, T06, T09 | manifest-bound inventory, `RESTRICT`, izolowany PostgreSQL i raport przed/po. |
| Zachować catalog/control/shared | T01, T05, T09, T12 | allowlista relacji, kontrakt katalogu i postflight relacji pozostających w `public`. |
| Bezpieczna operacja na 85 GB DB | T05–T10 | limity czasu/locków, explicit approval, brak `CASCADE`, raport transakcji i brak aktywnych maintenance jobs. |
| Trwałość po restarcie | T03, T07, T10, T12 | nowa sesja/worker wiąże V2; migracja head i smoke po nowym procesie. |

Skala 85 GB nie uzasadnia długiej transakcji ani skanowania pełnych danych: preflight liczy wyłącznie 65 tabel, każdą osobnym bounded `count`/statusem, a DDL dotyczy potwierdzenie pustych relacji (historycznie 3,5 MB). T05 ustali rzeczywiste `lock_timeout` i `statement_timeout` z istniejących konwencji; T09 nie wykonuje kroku bez jawnie zapisanych wartości. Pełna pustość tabel jest warunkiem bezpieczeństwa, nie optymalizacją.

Ryzyka: inny proces może stworzyć dane między preflightem a DDL; dlatego T09 wykonuje ostateczną kontrolę w tej samej kontrolowanej sesji przed migracją. Niezrutowany raw SQL może działać na pustym `public`; T02–T04 wymagają regresji na grze V2 z danymi, nie tylko fixture legacy. Nieodwracalność usunięcia pustego schematu jest świadoma: brak danych nie daje prawa do fabrykowania ich podczas downgrade.

Nie wykonano jeszcze testów ani operacji nowej implementacji; wszystkie komendy wskazane w taskach są planowane. Przed każdym taskiem wykonawca ponownie sprawdza wolność numeru, stan repozytorium, Alembic head, aktywny task oraz dostępność przypisanego modelu/reasoning.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| P00 / TASK-0679 | `gpt-6-sol` | `high` | Spójność architektury, D-448 i wieloetapowego planu. | `gpt-6-astra`, `medium` |
| T01 / TASK-0680 | `gpt-6-sol` | `high` | Inventory rozróżnia własność danych i stan aktywnej bazy. | `gpt-6-astra`, `high` |
| T02 / TASK-0681 | `gpt-6-astra` | `high` | Zmienia fail-closed routing na granicy wszystkich danych gry. | `gpt-6-sol`, `high` |
| T03 / TASK-0682 | `gpt-6-astra` | `high` | Audyt wielu repository, workerów i raw SQL ma wysokie ryzyko regresji. | `gpt-6-sol`, `high` |
| T04 / TASK-0683 | `gpt-6-sol` | `high` | Kontrakt bootstrapu i fixture wymaga zgodności testów z PostgreSQL. | `gpt-6-astra`, `high` |
| T05 / TASK-0684 | `gpt-6-astra` | `high` | Destrukcyjny DDL, zależności FK i nieodwracalna migracja wymagają rygorystycznego review. | `gpt-6-sol`, `high` |
| T06 / TASK-0685 | `gpt-6-astra` | `high` | Rehearsal ocenia locki, timeouty i scenariusze awarii. | `gpt-6-sol`, `high` |
| T07 / TASK-0686 | `gpt-6-sol` | `high` | Instrukcja operatorska musi zachować dokładne bramki bezpieczeństwa. | `gpt-6-astra`, `medium` |
| T08 / TASK-0687 | `gpt-6-sol` | `high` | Readiness łączy istniejące kontrakty bez zmiany danych. | `gpt-6-astra`, `high` |
| T09 / TASK-0688 | `gpt-6-astra` | `high` | Zastosowanie zatwierdzonego DDL na danych użytkownika wymaga najwyższej ostrożności. | `gpt-6-sol`, `high` |
| T10 / TASK-0689 | `gpt-6-astra` | `high` | Postflight musi niezależnie wykryć routing lub kontraktowy regres. | `gpt-6-sol`, `high` |
| T11 / TASK-0690 | `gpt-6-sol` | `high` | Usunięcie martwych ścieżek wymaga pełnego testu kompatybilności. | `gpt-6-astra`, `high` |
| T12 / TASK-0691 | `gpt-6-astra` | `high` | Końcowy odbiór ustala trwałą granicę danych i ryzyka resztkowe. | `gpt-6-sol`, `high` |
