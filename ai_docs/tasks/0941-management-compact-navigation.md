---
title: Kompaktowe punkty i maszyny z nawigacją w głąb
status: todo
last_updated: 2026-10-08
---

# TASK-0941 — Kompaktowe punkty i maszyny z nawigacją w głąb

## Status

`todo`

## Goal

Umożliwić szybką nawigację punkt → maszyna z małymi kafelkami i atomowymi modalami bez utraty szkicu.

## Context

Operator chce minimalnego UI i szybkiego przechodzenia między punktami, maszynami
i stawkami. Cały plan jest zaakceptowany i uruchomiony; koszt oraz manualne audyty
zostały uzgodnione. Nie trzeba rekonstruować historii rozmowy.

## Dependencies / entry conditions

TASK-0940 zakończony, audyt i commit zapisane. Przed kodowaniem przeczytać ten task oraz sekcje produktu/nawigacji planu.

## Recommended execution

gpt-6-sol / medium. Nie rozszerzać zmian domyślnego search/share. Największe ryzyko: popstate/dirty guard i własny refresh unieważniający preview. Layout oceniany na fixture, produkcyjne przeglądarki i dane operatora poza testem.
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
- ai_docs/delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md — sekcje TASK-0941 i reguły wspólne.
- ai_docs/requirements/MANAGEMENT_PANEL.md
- ai_docs/architecture/MANAGEMENT_PANEL.md
- ai_docs/process/DECISION_LOG.md — D-536 i D-533.
- ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md
- ai_docs/quality/AUDIT_REPORT_TEMPLATE.md

## Scope

- Siatka punktów i maszyn max320px, cztery kolumny od pierwszego kafelka; Home/back i brak wszystkich poziomów naraz.
- Cały tile klikalny, sibling edit/delete icons, widoczne zaznaczenie i touch44.
- Modal punktu/maszyny; atomowa nazwa+gry, preview/confirm/delete i zachowanie formularza po błędzie.
- URL mpPoint/mpMachine/mpGame/mpStake, ostatnia gra pernamespace/machine, scrollpertab, refresh snapshot i pending recovery.
- Dirty guards wszystkich wyjść, pauza własnego autorefresh przy delete; lokalny panel linków collapsed; legacy archived collapsed.

## Out of scope

- Push, merge, deployment, dane/baza operatora i lifecycle API/Admin.
- Nowa kopia wyszukiwarki/kalkulatora, konta/chmura/Redis/Celery i benchmarki.
- Usuwanie katalogu gier, symboli, plansz, globalnych korekt i innych dzienników.
- Taski innych torów oraz niezwiązane wcześniejsze błędy.

## Acceptance criteria

- [ ] Jeden tile nie rozciąga się; kontener1000/750/500 używa4/3/2kolumn, mniejszy1; brak horizontal scroll przy390px.
- [ ] Home i Cofnij do punktów działają, wybrana maszyna/stawka oznaczone; ikony nie wybierają kafelka.
- [ ] Modal zapisuje name+games jednym request; error/CAS zachowuje draft i wymaga świeżego preview.
- [ ] Reload/URL/popstate odtwarzają najbliższy poprawny poziom, mpStake nie otwiera editor, parent params zachowane.
- [ ] Pending scope i stara sesja nie są przenoszone na innego aktora; recovery bez autoretry.
- [ ] Focus/back/writes/notfound/conflict odświeżają snapshot; usunięcie w innym oknie nie zostawia fałszywego aktywnego celu.
- [ ] Dirty draft chroniony na Home/back/popstate/game/modalclose; legacy archived usuwalne, archiwizacja niewidoczna.
- [ ] Admin i Reviewer używają tego samego UI; link controls tylko lokalnie.

## Technical notes

Obowiązuje sekcja „Nawigacja i ochrona szkicu” planu. Lokalny namespace i publiczny session UUID są odrębne. Wybrane mpStake oznacza tile, nie jest serializacją szkicu. Controls edit/delete to rodzeństwo pełnego button, nie nested HTML. Reload pending nie ponawia mutacji automatycznie. Restore zakresu służy odzyskiwaniu, nie zastępuje wyboru URL innymi danymi bez guardu. Nie kopiować wrapperów do nowych niezależnych implementacji.

## Expected files

- Istniejące: packages/board-search-ui/src/management/management-workspace.tsx, management.css — hierarchy/layout/modals.
- Istniejące: management-operation.ts, management-client.ts, management-game-workspace.tsx — pending commands, preview ports, refresh pause.
- Istniejące: apps/admin/src/features/management/management-workspace.tsx, management-share-panel.tsx; apps/reviewer/src/features/management/management-gate.tsx — cienkie integracje.
- Nowe, proponowane: packages/board-search-ui/src/management/management-navigation.ts i management-structure-modal.tsx — czysta URL/state logika i modal.
- Testy istniejących management interaction/geometry suites w board-search-ui/Admin/Reviewer.

## Test cases

- 1/4/40 kafelków oraz40punktów do40maszyn — geometria bez autoexpand pojedynczego tile.
- Enter/Space na tile, edit/delete click, touch44 → poprawna akcja bez double navigation.
- Niepoprawny/missing URL scope i delete w drugim oknie → valid ancestor replaceState.
- Błąd atomowego save/preview expired → modal zachowuje wpisany formularz.
- Dirty draft + każda droga wyjścia/popstate → guard; cancel pozostawia wybrany scope.
- Public session change/recovery UUID → stara operacja nie przechodzi do nowej sesji.

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
```

Nowe moduły muszą dostać własne testy razem z kodem. Po zmianach Python uruchom
Ruff i mypy odpowiednich plików z istniejącej konfiguracji; TS: lint/typecheck
zmienionych workspace. PG ownership/provisioning uruchamiaj tylko na bazie
izolowanej. Każde pominięcie/skip i istniejący niezwiązany błąd podaj w Outcome.
Warunek zakończenia: kryteria potwierdzone, wymagany audyt bez otwartych P0/P1,
osobny commit i dokumentacja stanu. Brak audytu zatrzymuje następny task.

## Risks / open questions

Nie rozszerzać zmian domyślnego search/share. Największe ryzyko: popstate/dirty guard i własny refresh unieważniający preview. Layout oceniany na fixture, produkcyjne przeglądarki i dane operatora poza testem.

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

- TASK-0942 dopiero po zamknięciu tego taska.
