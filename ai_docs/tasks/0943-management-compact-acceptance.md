---
title: Odbiór kompaktowego panelu i instrukcja operatorska
status: todo
last_updated: 2026-10-08
---

# TASK-0943 — Odbiór kompaktowego panelu i instrukcja operatorska

## Status

`todo`

## Goal

Potwierdzić cały przepływ na ograniczonych fixture'ach i pozostawić kompletną dokumentację wdrożenia/odtworzenia.

## Context

Operator chce minimalnego UI i szybkiego przechodzenia między punktami, maszynami
i stawkami. Cały plan jest zaakceptowany i uruchomiony; koszt oraz manualne audyty
zostały uzgodnione. Nie trzeba rekonstruować historii rozmowy.

## Dependencies / entry conditions

TASK-0940–0942 zakończone z audytami/commitami; D-536 i aktualne API/UI udokumentowane. Bez zgody na rollout danych/usług operatora.

## Recommended execution

gpt-6-sol / medium. Wzrokowy odbiór operatora i migracja jego danych wymagają odrębnego czasu/zgody. Żadnych benchmarków ani testów na jego bazie. Niezwiązany wcześniejszy błąd opisać poza taskiem, nie rozszerzać zakresu.
Wymagany niezależny ręczny review claude-opus-5-5 / medium przed commitem. Konfiguracja musi
odpowiadać końcowej tabeli planu; niedostępność albo zmiana ryzyka wymagają jawnej
aktualizacji, bez ukrytej zamiany modelu.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md — sekcje TASK-0943 i reguły wspólne.
- ai_docs/requirements/MANAGEMENT_PANEL.md
- ai_docs/architecture/MANAGEMENT_PANEL.md
- ai_docs/process/DECISION_LOG.md — D-536 i D-533.
- ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md
- ai_docs/quality/AUDIT_REPORT_TEMPLATE.md

## Scope

- Finite browser fixture:40points, do40machinespoint, cases1/4tiles, gameIds200; desktop1440/1920 i390px.
- Zintegrowane Home→point→machine→stake→search→save→reset→replace→delete z dirty/recovery/conflict/session guards.
- Restart read w nowym procesie i application-role disposable PG; backup/restore tylko osobna testDB.
- Spójna dokumentacja requirements/architecture/operations/traceability/D-533/D-536/README/CURRENT_STATE.
- Ograniczony końcowy build/regression i konkretne pozostałe rollout gates operatora.

## Out of scope

- Push, merge, deployment, dane/baza operatora i lifecycle API/Admin.
- Nowa kopia wyszukiwarki/kalkulatora, konta/chmura/Redis/Celery i benchmarki.
- Usuwanie katalogu gier, symboli, plansz, globalnych korekt i innych dzienników.
- Taski innych torów oraz niezwiązane wcześniejsze błędy.

## Acceptance criteria

- [ ] Wszystkie kryteria planu mają dowód testu albo jawny niewykonany odbiór operatora; brak fikcyjnego PASS.
- [ ] Desktop i telefon bez horizontaloverflow, max320 i touch44; niezależne UI Admin/Reviewer zgodne.
- [ ] Fresh process trwałe receipty/saves/history i denied revoked session; rollback całej transakcji.
- [ ] Read-only migration preview z count legacy fallback oraz provisioning check i jedna głowa w torze panelu.
- [ ] Guide opisuje backup binarny i restore do osobnej DB, preview/confirm/migrację/manualrestart; nie obiecuje dataprollback przez downgrade.
- [ ] Requirements/architecture nie zawierają sprzecznego zakazu hard delete tego modułu ani archive-only workflow.
- [ ] Audyt Claude, Outcome i osobny commit kończą zlecony plan; brak push/merge/deployment.

## Technical notes

Regresje wcześniejszych tasków nie są ponawiane bez potrzeby: końcowy test obejmuje realny zintegrowany przepływ i nowe rozmiary. Istniejący browser runner uruchamia kontrolowaną headless przeglądarkę i statyczną fixture, nie usługi operatora. Fizyczne urządzenie, live tunnel/ingress i reboot operatora pozostają gates. Nie uznawać mock za wynik realnej produkcji. Dokładny nextversion z gitlog, nie z nazwy branch.

## Expected files

- Istniejące: scripts/prepare_management_browser_fixture.py i scripts/verify_management_panel_browser.mjs — finite acceptance.
- Istniejące: ai_docs/requirements/MANAGEMENT_PANEL.md, architecture/MANAGEMENT_PANEL.md, process/MANAGEMENT_PANEL_OPERATIONS.md, project/TRACEABILITY.md.
- Istniejące: ai_docs/process/DECISION_LOG.md (adnotacja D-533 i D-536), CURRENT_STATE.md, README.md i bieżący plan/task.
- Nowy, proponowany: ai_docs/quality/ADMIN_COMPACT_PANEL_ACCEPTANCE.md — dowody/pomiary i niewykonane rollout gates.

## Test cases

- End-to-end compact fixture w1440/1920/390 i1/4/40tiles → czytelny minimalny układ.
- Lost response + świeży proces/session identity → receipt/recovery bez duplikacji.
- Purge + rollback/fault injection i wspólny wynik innych maszyn → integralność.
- Backup restore osobna testDB → liczby obiektów/frozen results/receipts zgodne.
- Stare ordinary share i management online gates → zakres uprawnień nieposzerzony.

## Verification

Katalog: root oddzielnego worktree. Każdą poniższą skończoną komendę wykonaj
z wymuszonym timeoutem 120s w runnerze; provisioning check:30s. PG wyłącznie
disposable DB, GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 tylko w procesie testowym.
Brak venv/node_modules worktree wymaga izolowanego środowiska; nie buduj dist
ani aplikacji w głównym checkout operatora. Testy poniżej są planowane,
nie zostały jeszcze uruchomione. Najpierw pion, potem lint/typecheck/scoped
format, dopiero regresje/build. Znany build >120s poprzedź komunikatem.

```powershell
npm run reviewer:management:browser
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run test --workspace @game-predictor/reviewer
npm run openapi:check
npm run typecheck --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/reviewer
```

Nowe moduły muszą dostać własne testy razem z kodem. Po zmianach Python uruchom
Ruff i mypy odpowiednich plików z istniejącej konfiguracji; TS: lint/typecheck
zmienionych workspace. PG ownership/provisioning uruchamiaj tylko na bazie
izolowanej. Każde pominięcie/skip i istniejący niezwiązany błąd podaj w Outcome.
Warunek zakończenia: kryteria potwierdzone, wymagany audyt bez otwartych P0/P1,
osobny commit i dokumentacja stanu. Brak audytu zatrzymuje następny task.

## Risks / open questions

Wzrokowy odbiór operatora i migracja jego danych wymagają odrębnego czasu/zgody. Żadnych benchmarków ani testów na jego bazie. Niezwiązany wcześniejszy błąd opisać poza taskiem, nie rozszerzać zakresu.

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

- Odbiór operatorski po zakończeniu planu, bez automatycznego wdrożenia.
