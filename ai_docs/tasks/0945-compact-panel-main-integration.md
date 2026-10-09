---
title: Integracja kompaktowego panelu z main
status: in_progress
last_updated: 2026-10-09
---

# TASK-0945 — Integracja kompaktowego panelu z main

## Status

`in_progress`

## Goal

Scalić audytowany panel do v1.1-vision-lab-hybrid-geometry bez utraty zmian Mumii ani niezapisanej pracy operatora.

## Context

Jawne polecenie operatora2026-10-09; kod0940–0943 zamknięty, main zmienił się równolegle.

## Dependencies / entry conditions

Main fc3d188/v1.7.287, panel433d8bfe/v1.7.278; czysty worktree panelu przed merge.
Niezapisane pliki main należą do operatora. Snapshot patch/status/hash istnieje.

## Recommended execution

gpt-6.1-sol / high; Claude opus5-5/high przed merge commitem. Zmiana granic danych
lub otwarty P0/P1 po ograniczonej poprawce zatrzymuje zależną operację.

## Relevant docs

- AGENTS.md, ai_docs/README.md, process/CURRENT_STATE.md i DECISION_LOG.md.
- ai_docs/process/PLAN_STANDARD.md, TASK_TEMPLATE.md i DEFINITION_OF_DONE.md.
- ai_docs/delivery/ADMIN_COMPACT_PANEL_INTEGRATION_PLAN.md.
- ai_docs/delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md, sekcja integracji i końcowe modele.
- ai_docs/requirements/MANAGEMENT_PANEL.md, architecture/MANAGEMENT_PANEL.md.
- ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md.
- ai_docs/process/decisions/DECISION_LOG_2026.md — D-533/D-536/D-537 i import panelu jakoD-538.
- ai_docs/quality/TASK-0941_AUDIT_claude-opus-5-5_ROUND_2.md, TASK-0942_AUDIT_claude-fable-5-1.md,
  TASK-0943_AUDIT_claude-opus-5-5.md — wcześniejsze dowody, bez powtarzania audytów.

## Scope

Konflikty wspólnych komponentów/snapshotów, pusty merge Alembic, guard, jeden OpenAPI,
pin metrics per pozycja, dokumentacja nowego procesu, audyt i bezpieczny fast-forward main.

## Out of scope

Push, rollout/migracja bazy operatora, API/Admin lifecycle, benchmarki, nowe funkcje.

## Acceptance criteria

- [ ] Obie funkcje zachowane: compact UI i supergame/provisional/free-spin koszty.
- [ ] Jedna głowa0153; oba rodzice0152 osiągalne, izolowany upgrade bez utraty triggerów/manifestuv6.
- [ ] Wkład/netto/na maszynie dla darmowych pinów zgodne backend/frontend;777 regresja bez zmiany digestu.
- [ ] OpenAPI/klient, scoped testy/lint/types i buildy przechodzą; docs/maps aktualne.
- [ ] D-538 i oba historyczne0940 nie nadpisują istniejącej dokumentacji; okno10done zachowane.
- [ ] Claude review bez P0/P1, osobny merge commit, pełny hash i finalny main zawiera panel.
- [ ] Hash niezapisanych plików operatora i untracked v7-output zachowane; brak zmian usług/danych.

## Expected files

- Istniejące konfliktowe board-search-results.tsx, management-result-view.tsx i saved-selection test.
- Istniejące domain/management_pin_metrics.py, storage/management_result_snapshots.py,
  board-search-approximate-win.tsx i ich testy — kompozycja kosztów.
- Nowa proponowana migracja0153_merge_compact_super_games.py i test ancestry.
- Istniejące schema_readiness.py, test_schema_readiness.py, _application_role_database.py.
- Generowane OpenAPI/klient/CODE_MAP; owner docs wymagania/architektura/operations/decyzje/state.

## Test cases

Darmowe spiny3..6: pin6 ma koszt40, wkład40, netto-40, na maszynie0;
start w serii: pierwszy darmowy spin nie wymaga wkładu; prowizoryczna wypłata
nie wchodzi do salda/wkładu. Compact zachowuje marker i lazy chart/table.
Merge ancestry zawiera oba0152; rola aplikacyjna ma oba zestawy zabezpieczeń.

## Verification

Planowane: focused pytest pin metrics/schema, shared TS tests/interactions,
Admin/Reviewer geometry; typecheck/lint; OpenAPI generate/check; Alembic heads,
izolowane management/supergame PG; docs:check/code-map:check; browser10cases;
Admin/Reviewer build. Każda komenda w ograniczonym runnerze120s, audyt480s.
Wyniki zapisujemy niżej, nie traktujemy tej listy jako wykonanej.

## Outcome

### Changed

Połączono konfliktowe komponenty i snapshoty; koszty pinów używają zamrożonych darmowych zakresów, provisional nie zwiększa wkładu. Dodano pusty merge0153, aktualny guard, preview dla0151/0152series i historyczną fixture v5. D-538 importuje decyzję panelu, nie zmieniając D-536 Mumii. OpenAPI/klient wygenerowano z backendu.

### Verification results

- Focused Python:31/31 PASS (metrics, frozen pins, ancestry/guard).
- TS helpery/golden cases:34/34 PASS; shared saved-selection/navigation:17/17 PASS.
- Admin management/cards:39/39 PASS; Reviewer proxy/geometry:31/31 PASS.
- Izolowane PG migration/receipt tests:3/3 PASS z0151,0152series i0152compact. Pierwszy przebieg2/3 fail wykazał manifestv6 użyty w starej fixture; naprawiono fixture do v5, nie zmieniono migracji/kontraktu.
- Shared lint/types, Admin/Reviewer typecheck, scoped Ruff:PASS.
- OpenAPI generate/check:PASS, obaj klienci aktualni.
- Admin build:PASS37,17s; Reviewer build:PASS27,88s.
- Chromium fixture:10/10 PASS,390/1440/1920px, grid/modal/touch/no overflow; transport mock.
- npm docs:check:PASS,535 wpisów/wierszy decyzji,37 aktywnych tasków,10done, state79KB.
- Standardowe komendy .venv działają w worktree przez lokalny ignorowany junction do istniejącego środowiska, bez instalacji. Dwa udane testy TS miały błąd kodowania tylko przy drukowaniu runnera po zakończeniu; surowe logi potwierdzają34/34 i17/17, runner drukuje jużUTF-8.
- Dodatkowy szeroki moduł PG osiągnął limit120s po7 testach bez raportu końcowego; nie deklarujemy PASS całego modułu. Sprzątnięto dokładnie jedną utworzoną przez ten przebieg bazę testową (0 aktywnych połączeń); siedem wcześniejszych, wygasłych baz testowych operatora pozostawiono. Zawężone dwa krytyczne scenariusze purge/role/rollback i zachowania tożsamości serii:2/2 PASS.
- Regresje API supergry:35 testów PASS; test777 wykrył wyłącznie celowe dodatkowe pola pinów. Zachowano oryginalny hash całego dawnego kontraktu przez projekcję tylko dwóch nowych pól i dodano osobny hash nowego kontraktu. Zamrożony digest jest identyczny;2/2 testy777 PASS.
- code-map:check:PASS; scoped strict mypy:PASS (3 pliki).
- Claude opus5.5/high:PASS,0 P0/P1, raport TASK-0945_AUDIT_claude-opus-5-5.md. Jedna runda przeglądu i jedna runda poprawek P2, bez ponownego pełnego audytu.
- P2-1: zagnieżdżona tabela nie powiela nagłówka ani obsługi replay; nowa regresja komunikatów PASS. P2-2: fixture dobiera manifest według ancestry, także0143/0145. P2-3: test sprawdza manifestv6 i aktywne triggery, po normalnym provisioningu roli dla wcześniejszych poprzednikówV7. P2-4: martwy helper usunięty. P2-5: odczytowy wykres ma etykietę „Wykres bilansu”.
- Po poprawkach TS helpery34/34, saved-selection15/15, backend pin/snapshot/77720/20, shared lint/types:PASS. Golden TS sprawdza także saldo z realnego approximateWinPointAtSpin.
- Końcowe buildy po poprawkach:Admin PASS27,50s, Reviewer PASS24,02s. Wzmocniona macierz PostgreSQL:3/3 PASS dla0143/0145/0152compact, sprawdza manifestv6 i aktywne triggery. Starsze rewizje wymagają normalnego post-migration provisioningu V7; test odwzorowuje tę procedurę. Wszystkie pięć P2 zamknięto w jednej rundzie. Testy klienta API:107/107 PASS.

### Audit resolution

Raport Claude pozostaje oryginalny. P2-1–P2-5 zamknięto zmianami i kontrolami opisanymi wyżej; brak otwartych uwag. Bez kolejnego audytu, zgodnie z ograniczeniem jednej rundy dla P2.

### Not completed

Commit i fast-forward main czekają na końcową kontrolę. Nie wykonano push, migracji bazy operatora, uruchomienia/restartu usług ani odbioru na żywym urządzeniu/ingress. Pełny szeroki moduł PG nie ukończył się w limicie; zastąpiono go wymaganymi testami migracji i dwoma krytycznymi scenariuszami.

### Documentation updates

Plan i aktualny task zapisano, żadna historia panelu/main nie jest zastępowana całą kopią.

### Recommended next task

Odbiór operatora i jawnie autoryzowany rollout danych, poza tym scaleniem.

### Integration checkpoint

Kod i audyt są gotowe do merge commita v1.7.288. Finalny fast-forward oraz pełny hash zapisujemy po wykonaniu operacji.
