---
title: Minimalistyczne stawki, zapisany układ i wspólny edytor
status: todo
last_updated: 2026-10-08
---

# TASK-0942 — Minimalistyczne stawki, zapisany układ i wspólny edytor

## Status

`todo`

## Goal

Zmniejszyć stawki i edytor panelu, wykorzystując wspólne wyszukiwanie, wyliczenia i zapisany stan bez regresji innych konsumentów.

## Context

Operator chce minimalnego UI i szybkiego przechodzenia między punktami, maszynami
i stawkami. Cały plan jest zaakceptowany i uruchomiony; koszt oraz manualne audyty
zostały uzgodnione. Nie trzeba rekonstruować historii rozmowy.

## Dependencies / entry conditions

TASK-0940 zakończony z audytem/commitem, kod i testy TASK-0941 gotowe.
Operator 2026-10-09 jawnie pozwolił wykonać kod/testy0942–0943 przed audytem0941.
Audyty i osobne commity pozostają wymagane przed zamknięciem planu/merge.
Bezpośrednio przed startem sprawdzić main pod TASK-0935/0936 i zastosować regułę
integracji planu; nie czekać na nie, jeśli jeszcze nie weszły.

## Recommended execution

gpt-6.1-sol / high. Przed startem odnotować wynik sprawdzenia wspólnych plików i main. Modyfikacja zwykłych konsumentów byłaby regresją. Przy konflikcie semantyki kosztu/snapshot version wstrzymać zależny fragment i skorygować kontrakt wspólnego helpera.
Wymagany niezależny ręczny review claude-fable-5-1 / high przed commitem. Konfiguracja musi
odpowiadać końcowej tabeli planu; niedostępność albo zmiana ryzyka wymagają jawnej
aktualizacji, bez ukrytej zamiany modelu.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md — sekcje TASK-0942 i reguły wspólne.
- ai_docs/requirements/MANAGEMENT_PANEL.md
- ai_docs/architecture/MANAGEMENT_PANEL.md
- ai_docs/process/DECISION_LOG.md — D-536 i D-533.
- ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md
- ai_docs/quality/AUDIT_REPORT_TEMPLATE.md

## Scope

- Sześć małych klikalnych kafelków stawki, zapis-status i symbole20–24px, bez miniChart/przycisków Open.
- Otwieranie zapisanej query/start/range/pins, bez wyboru pierwszego trafienia; stan Save/changes/new/replace/clear według planu.
- Wariant compact jako opcjonalny prop BoardSearchWorkspace, reuse ApproximateWinBalanceChart/approximateWin*.
- Szybkie wiersze z pin metadata, wykres dopiero po rozwinięciu do wyboru0–6pinów, axesPLN/spins/zero.
- Tabela i journal collapsed, pełny wynik on demand; stale replies/CAS/recovery/sessionloss zachowują szkic.

## Out of scope

- Push, merge, deployment, dane/baza operatora i lifecycle API/Admin.
- Nowa kopia wyszukiwarki/kalkulatora, konta/chmura/Redis/Celery i benchmarki.
- Usuwanie katalogu gier, symboli, plansz, globalnych korekt i innych dzienników.
- Taski innych torów oraz niezwiązane wcześniejsze błędy.

## Acceptance criteria

- [ ] Karta ma tylko stawkę, zapis-status i potrzebny symbol-preview; cała klikalna, selected wyraźny.
- [ ] Stored start z managementSavedSelection odtworzony deterministycznie; brak top-hit autochoose.
- [ ] Nowy układ/reset nie czyści slotu; Save changes vs Replace wymaga właściwego CAS i confirm, Clear jawny.
- [ ] Spin/Wkład/Netto/Na maszynie zgodne ze wspólnymi helperami; zero i losing dozwolone, unavailable jawne.
- [ ] 0–6 pinów i osie widoczne w rozwiniętym wykresie; nie ma nieczytelnych black dot miniCharts.
- [ ] Quick preview nie pobiera full result; full tabela/history tylko po rozwinięciu; queue≤2.
- [ ] Default ordinary search/share zachowane, optional props i regression testy.
- [ ] Zmiana globalnych symboli nadal zapisuje natychmiast, reset szkicu tego nie cofa.

## Technical notes

Obowiązuje produktowa tabela stanów planu i sekcja reużycia/integracji. Nie kopiować wykresu/search/modali ani obliczać wkładu przez sumę spinów. Przy zmiennym koszcie Mumii użyć wspólnej infrastruktury z golden fixtures, nie reinterpretować zamrożonych historycznych payloadów. Stable machine/game/stake scopeKey chroni dirty editor przed zmianą background identity. Wszystkie kafelki compact są button; default poprzednich konsumentów nie zmienia się.

## Expected files

- Istniejące: packages/board-search-ui/src/management/management-cards.tsx, management-game-workspace.tsx, management-result-view.tsx, management-slot-state.ts, management.css.
- Istniejące: packages/board-search-ui/src/board-search-workspace.tsx oraz board-search-approximate-win.tsx i board-search-approximate-win-state.ts — opcjonalny compact i helpery.
- Istniejące: management-data-source.ts / management-journal.tsx — on demand, collapse, recovery.
- Testy interakcji board-search-ui, Admin geometry i Reviewer geometry; fixtures wspólnych wyliczeń.

## Test cases

- Stored start niepierwszego trafienia po reload → ten sam sequence/query/range/pins.
- Reset/new + wyjście/cancel/Save failed → stary zapis pozostaje do Replace success.
- Pin0/przegrany/6/7/unavailable → dokładna granica i wartości; zmienny koszt jeśli zintegrowany.
- History wartości/rules bez zmian po aktualizacji globalnych reguł.
- Default search/share flow → poprzednie controls i zachowanie; tylko compact uproszczony.
- Late responses, revisionconflict, pendinglostresponse i sesjaodmowa → draft zachowany, brak cichego overwrite.

## Verification

Katalog: root oddzielnego worktree. Każdą poniższą skończoną komendę wykonaj
z wymuszonym timeoutem 120s w runnerze; provisioning check:30s. PG wyłącznie
disposable DB, GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 tylko w procesie testowym.
Brak venv/node_modules worktree wymaga izolowanego środowiska; nie buduj dist
ani aplikacji w głównym checkout operatora. Testy poniżej są planowane,
nie zostały jeszcze uruchomione. Najpierw pion, potem lint/typecheck/scoped
format, dopiero regresje/build. Znany build >120s poprzedź komunikatem.

```powershell
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run test:geometry --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/board-search-ui
npm run reviewer:management:browser
```

Nowe moduły muszą dostać własne testy razem z kodem. Po zmianach Python uruchom
Ruff i mypy odpowiednich plików z istniejącej konfiguracji; TS: lint/typecheck
zmienionych workspace. PG ownership/provisioning uruchamiaj tylko na bazie
izolowanej. Każde pominięcie/skip i istniejący niezwiązany błąd podaj w Outcome.
Warunek zakończenia: kryteria potwierdzone, wymagany audyt bez otwartych P0/P1,
osobny commit i dokumentacja stanu. Według zgody operatora z2026-10-09
brak audytu nie blokuje kodu/testów0943, ale blokuje done i merge.

## Risks / open questions

Przed startem odnotować wynik sprawdzenia wspólnych plików i main. Modyfikacja zwykłych konsumentów byłaby regresją. Przy konflikcie semantyki kosztu/snapshot version wstrzymać zależny fragment i skorygować kontrakt wspólnego helpera.

## Outcome

### Changed

- Nie rozpoczęto implementacji. Plan i task utrwalone; następny krok: warunki wejścia i kod.

### Verification results

- Brak wyników testów implementacji; komendy powyżej są planem.

### Not completed

- Implementacja, testy, ręczny audyt Claude i commit taska.

### Documentation updates

- Task utworzony według zaakceptowanego planu, D-536.

### Recommended next task

- Kod/testy TASK-0943 po przygotowaniu tego taska, według zgody operatora z2026-10-09; formalne zamknięcie po odroczonych audytach/commitach.
