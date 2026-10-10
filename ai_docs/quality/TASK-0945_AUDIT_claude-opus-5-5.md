# Audyt TASK-0945 — Integracja kompaktowego panelu z main

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...fc3d188862dbd85e6aa2fe247e47942c56a9fd67 (pusty diff commitów) oraz zmiany niezacommitowane w podanych ścieżkach, data 2026-10-09
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików i nie uruchamiał testów ani poleceń zmieniających stan.

## Streszczenie

Sprawdziłem cztery obszary scalenia. Pierwszy to łańcuch migracji: nowa pusta migracja 0153 łączy obie gałęzie 0152, a strażnik schematu wskazuje 0153. Drugi to fixture testowa, która dla starych rewizji zakłada grę w formacie manifestu v5 zamiast obecnego v6. Trzeci to kwoty przypiętych pinów (wkład, netto, „na maszynie”) dla darmowych spinów i wypłat prowizorycznych, osobno w zamrożonym wyniku na backendzie i w widoku kompaktowym. Czwarty to rozwiązanie konfliktów we wspólnych komponentach, w tym zachowanie markerów supergry.

Łańcuch migracji jest poprawny: oba rodzice 0152 schodzą do `0151_super_game_roles`, a strażnik pokazuje jedną głowę. Python i TS liczą metryki pinów identycznie i używają wspólnych przypadków golden. Digest zamrożonego wyniku się nie zmienia, więc regresja dla gry 777 nie występuje. Nie znalazłem błędów P0 ani P1. Główne ryzyko to dublowanie komunikatów w zagnieżdżonej tabeli widoku kompaktowego oraz niepełne asercje izolowanego testu scalenia.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `packages/board-search-ui/src/board-search-approximate-win.tsx:675` — w trybie kompaktowym pełna tabela otwiera się jako rekurencyjne wywołanie `ApproximateWinResultView` z `tableOnly`. To wywołanie renderuje ponownie cały nagłówek z linii 613–646: `SuperGameStateBanner`, licznik kompletności, `ApproximateWinProvisionalSummary` i baner o niepełnych danych. Po rozwinięciu tabeli te same komunikaty `role="status"` pojawiają się więc dwa razy. Dodatkowo efekt `boardRequest` z linii 574–587 działa wtedy w dwóch instancjach i może dwukrotnie wywołać `onBoardRequestHandled` oraz `onReplayNotice`. Panel zarządzania nie używa replay, więc w praktyce widać tylko podwójne komunikaty. Poprawka: objąć bloki nagłówka i efekt `boardRequest` warunkiem `!tableOnly` albo wydzielić samą tabelę z filtrem do osobnego komponentu.
- [P2-2] `services/api/tests/integration/_application_role_database.py:143` — manifest v5 jest wybierany na sztywno tylko dla `0151_super_game_roles` i `0152_management_compact_panel`. Wywołania z rewizjami 0143 i 0144 nadal provisionują grę w manifeście v6 na schemacie, który zna tylko v5 (wprowadzony w 0142, sprawdzany w 0144/0145). Chodzi o `services/api/tests/integration/test_lab_symbol_candidate_registry_postgres.py:47` i `services/api/tests/integration/test_neural_page_geometry_postgres.py:143`. Problem pochodzi z main (od wprowadzenia v6 w `0152_super_game_series`), a nie z tej integracji, ale poprawiony helper go nie obejmuje. Nie sprawdzałem tego uruchomieniem. Poprawka: wybierać v5 dla każdej rewizji, która nie jest potomkiem `0152_super_game_series`, albo jawnie odnotować to ograniczenie.
- [P2-3] `services/api/tests/integration/test_compact_super_game_merge_postgres.py:27` — test upgrade'u z gałęzi kompaktowej sprawdza tylko `alembic_version` i `describe_application_role(...).compliant`. Kryterium akceptacji wymaga „bez utraty triggerów/manifestu v6”. Test nie sprawdza, że gra założona w v5 przeszła na `game-data-v2-manifest-v6`, ani że triggery `management_history_immutable` są nadal podpięte do tabel. Raport roli sprawdza tylko istnienie i atrybuty funkcji (`services/api/src/game_predictor_api/storage/database_roles.py:384`). Udany upgrade pośrednio to sugeruje. Poprawka: dodać asercje na wersję manifestu gry i na obecność wpisów w `pg_trigger` dla tabel zarządzania.
- [P2-4] `services/api/src/game_predictor_api/storage/management_result_snapshots.py:138` — `_super_spins_up_to` nie jest już nigdzie używana, bo jej logikę zastąpiła `cost_at` w `domain/management_pin_metrics.py:51`. Martwy kod utrzymuje drugą kopię formuły kosztu, która może się rozjechać z pierwszą. Poprawka: usunąć funkcję.
- [P2-5] `packages/board-search-ui/src/management/management-result-view.tsx:140` — wykres historycznego wyniku jest tylko do odczytu (bez `onPinsChange`), a sekcja ma tytuł „Wybierz punkty na wykresie”. Operator może się spodziewać, że da się tu zmienić piny. Poprawka: dla widoku historycznego użyć tytułu w rodzaju „Wykres bilansu”. Zmiana etykiety w linii 198 na „Prowizoryczna (poza bilansem)” jest zgodna z D-537. Informację o supergrze nadal niesie `ApproximateWinProvisionalSummary` (linia 132).

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Obie funkcje zachowane: compact UI i supergame/provisional/free-spin koszty | spełnione | `board-search-results.tsx:157` (marker supergry z `seriesHref` zachowany), `board-search-results.tsx:161-201` (compact); `board-search-approximate-win.tsx:613-636` (banner/provisional), `:648-693` (lazy chart/table), `:759-779` (badge, prowizoryczny, darmowy spin); `management-result-view.tsx:132-149`. Zgodnie z `apps/admin/src/features/board-search/board-search-workspace.tsx:59-61` panel zarządzania celowo nie dostaje `superGameSeriesHref`, więc brak tego propsa w zagnieżdżonym wywołaniu niczego nie traci |
| Jedna głowa 0153; oba rodzice 0152 osiągalne; izolowany upgrade bez utraty triggerów/manifestu v6 | spełnione (statycznie); triggery i manifest niezweryfikowane wprost (P2-3) | `0153_merge_compact_super_games.py:3-4`; `0152_super_game_series.py:41` i `0152_management_compact_panel.py:7` mają rodzica 0151; `schema_readiness.py:17`; `test_schema_readiness.py:18,43-51`; `test_management_receipt_backfill_postgres.py:23` (0151 oraz 0152 series → head); `test_compact_super_game_merge_postgres.py:19-32` (0152 compact → head) |
| Wkład/netto/na maszynie dla darmowych pinów zgodne backend/frontend; brak regresji digestu 777 | spełnione | `management_pin_metrics.py:51-73` odpowiada `board-search-approximate-win-state.ts:181-197,640-678`; wspólne przypadki w `management-pin-metric-cases.json` (free-series-pin 6→40/−40/0, first-spin-free, provisional-excluded) są wykonywane przez `test_management_pin_metrics.py:18` i `test/management-pin-metrics.test.mjs:21`; `test_management_stakes.py` (`test_frozen_compact_pins_use_saved_free_spin_costs`); `freeze_result` (`management_result_snapshots.py:67-123`) i jego digest są bez zmian, a nowe klucze trafiają tylko do `pinned_points` (`:155-162`); legacy piny bez nowych pól są przeliczane z zamrożonego payloadu (`management_stake_repository.py:227-244`) |
| OpenAPI/klient, scoped testy/lint/types i buildy przechodzą; docs/maps aktualne | niezweryfikowane (deklaracja wykonawcy) | Pola `requiredStakeCredits`/`machineCashCredits` są w `openapi.json:17741,17752` i `schemas/management_stakes.py:50-51`. Wyników nie uruchamiałem. Wykonawca sam zaznacza, że `code-map:check` jest „w toku” |
| D-538 i oba historyczne 0940 nie nadpisują dokumentacji; okno 10 done zachowane | niezweryfikowane | Poza listą ścieżek tego audytu. `MANAGEMENT_PANEL_OPERATIONS.md:9` dodaje sekcję D-538, nie usuwając wcześniejszych procedur |
| Claude review bez P0/P1, osobny merge commit, pełny hash, finalny main zawiera panel | częściowo: ten raport nie zgłasza P0/P1; commit i fast-forward jeszcze nie wykonane | Task, sekcja „Not completed” |
| Hash niezapisanych plików operatora i untracked v7-output zachowane; brak zmian usług/danych | niezweryfikowane | Nie da się tego sprawdzić statycznie. Diff nie dotyka plików usług ani danych poza testami i skryptem tylko do odczytu (`scripts/preview_management_receipt_migration.py:22-23` ustawia `READ ONLY` i limit czasu zapytania) |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- `services/api/tests/integration/test_compact_super_game_merge_postgres.py`: po `upgrade head` sprawdzić, że gra ma manifest `game-data-v2-manifest-v6`, a triggery `management_history_immutable` istnieją w `pg_trigger`. Uruchomienie: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_compact_super_game_merge_postgres.py`.
- `packages/board-search-ui/test-interactions/board-search-saved-selection.test.mjs`: po `expandCompact('Pełna tabela wypłat')` sprawdzić, że podsumowanie prowizoryczne i baner stanu supergry występują dokładnie raz (dotyczy P2-1).
- `packages/board-search-ui/test/management-pin-metrics.test.mjs`: dla przypadków golden sprawdzać też `net` przez `approximateWinPointAtSpin`, zamiast podawać `fixture.net` jako wejście. Wtedy saldo po stronie TS też będzie objęte wspólnym kontraktem.

## Zakres przeglądu i ograniczenia

Przeczytane:

- **Migracje i strażnik:** pełny diff z briefu, migracja 0153, linie `revision`/`down_revision` migracji 0150–0153, `schema_readiness.py`.
- **Kwoty pinów:** `domain/management_pin_metrics.py`, `storage/management_result_snapshots.py`, fragment `management_stake_repository.py:210-247`, helpery TS w `board-search-approximate-win-state.ts` (koszt, punkt, wkład, kasa), `test/management-pin-metrics.test.mjs`.
- **Komponenty:** `board-search-approximate-win.tsx:125-153,440-480,520-780`, `management-result-view.tsx:1-160`, użycie `ApproximateWinPinRows` w `management-game-workspace.tsx`.
- **Fixture i role:** helper `_application_role_database.py:76-185`, importy manifestu w `game_partition_lifecycle.py`, `_management_function_errors` w `database_roles.py`.

Testów, buildów, Alembica, OpenAPI ani przeglądarki nie uruchamiałem. Wyniki z sekcji „Verification results” to deklaracje wykonawcy. Nie czytałem pełnych CURRENT_STATE i DECISION_LOG, wcześniejszych audytów 0940–0943 ani wygenerowanego klienta TS. Nie powtarzałem audytu funkcji compact poza zmianami integracyjnymi.
