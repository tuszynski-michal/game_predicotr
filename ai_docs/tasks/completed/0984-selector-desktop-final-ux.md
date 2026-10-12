---
title: Bezpieczny start, klawiatura i zamykanie
status: done
last_updated: 2026-10-12
---

# TASK-0984 — Bezpieczny start, klawiatura i zamykanie

## Status

`done`

## Goal

Usunąć pułapki startu oraz przypadkowe decyzje przy obsłudze lokalnych projektów.

## Context

Pełny audyt Claude rundy2 ma PASS i otwarte P2/P3. Operator polecił wykonać
całą finalizację, zatwierdził3–5 h oraz pomiar15000. Odbiór fizyczny na końcu.

## Dependencies / entry conditions

Brak; baza v1.7.332, raport rundy2 PASS z P2-A/C/D i P3-A/B.

## Recommended execution

`gpt-6.1-sol / medium`. Konfiguracja zgodna z tabelą planu finalizacji.
Eskaluj przy naruszeniu własności danych, idempotencji lub zgodności migracji.
Końcowy audyt operatora warunkowo `claude-sonnet-5-5 / medium`;
D-545 odracza audyt do końca, bez gate CLI/per-task. Nie zastępuj Claude
niejawnie.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md — D-545, D-546
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_FINALIZATION_PLAN_20261012.md — TASK-0984
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md — sekcja desktop
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md — sekcja desktop
- ai_docs/architecture/CODE_MAP.md — selector
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_REAUDIT_CLAUDE_20261012.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md

## Scope

Jawna nowa partia po braku folderu; newest projectRoot; preflight obu folderów bez zapisu w obcych; ignore repeat decision keys; close unknown lock bez unlink; jedno odroczone relaunch.

## Out of scope

API/Admin/Reviewer/baza, upload/linki/Proton, usługi operatora, podpis,
instalator, push/merge oraz fizyczny odbiór0979. Bez danych użytkownika.

## Acceptance criteria

- [x] Martwy wpis historii daje czytelną ścieżkę odzyskania albo jawnie potwierdzoną nową partię; brak automatycznego resetu.
- [x] Obcy output nie zostawia nowego pustego projektu; open folderu bez markerów nie tworzy locka; ścieżki/kody są jednoznaczne.
- [x] Repeat Enter/Tab/Ctrl+Z nie wywołuje decyzji; nowe naciśnięcie działa; strzałki mogą się powtarzać.
- [x] Close przy nieznanym właścicielu nie usuwa obcej blokady; ponowne uruchomienie podczas close kończy się jednym otwartym oknem.

## Technical notes

Jawna nowa partia po braku folderu; newest projectRoot; preflight obu folderów bez zapisu w obcych; ignore repeat decision keys; close unknown lock bez unlink; jedno odroczone relaunch. Zdjęcia źródłowe tylko do odczytu. Nie resetuj projektu po braku
folderu. Obce dane/niezgodne checksumy blokują zapis. Numeracja i porządek
zdjęć zachowują reguły core; wyniki są operator-local v2.

## Expected files

Ścieżki runtime względem `apps/selector-desktop/src`, skrypty/testy względem
workspace'u, o ile podano inaczej. project-controller.ts begin/open/create; recent-projects.ts list/remember; project-store.ts createInitial/open/close; renderer/App.tsx keyboard; main.ts close/second-instance.

## Test cases

start-resume.test.mjs, project.test.mjs, renderer-contracts.test.mjs i smoke-start/smoke-ux/smoke-packaged: brak folderu, duplicate root, cancel, obce katalogi, event.repeat, obcy lock, drugi EXE.

## Verification

Z worktree D:\game_predicotr\worktrees\offline-photo-selector. Najpierw pion,
potem pełny desktop. Każdy krok ma timeout; brak wyniku60s wymaga kontroli
zgodnie z AGENTS, buildy kontrolowane mają znany limit120s.

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:project --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run lint --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run typecheck --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run docs:check
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run code-map:check
```

Powyższe skrypty są sprawdzone. Nowe testy używają istniejącego runnera Node
lub jawnie dodanego skryptu; ich komendy/wyniki dopisz w Outcome. Odbiór
zadania wymaga wszystkich właściwych kryteriów, nie tylko zielonego testu.

## Risks / open questions

Fizyczny odbiór0979 i końcowy review operatora następują po implementacji.
Nie certyfikuj zaniku zasilania ani dowolnego sprzętu. Format disk2 jest
jednokierunkową zgodną migracją do nowej aplikacji; stara musi odmówić zapisu.

## Outcome

### Changed

TASK-0984 zamknął P2-A/C/D i P3-A/B raportu rundy2. Brak projektu ma pełną ścieżkę i jawne potwierdzenie „Nowa partia”; anulowanie zachowuje aktywny projekt. Historia preferuje newest wpis i deduplikuje projectRoot. Preflight obu folderów chroni obce dane oraz nie pozostawia pustego projektu po konflikcie wyniku. Open obcego folderu nie tworzy locka. Repeat accept/skip/undo jest ignorowany wyłącznie w desktopie. Close toleruje LOCK_LOST/LOCK_OWNER_UNKNOWN bez usunięcia cudzej blokady. Dwa uruchomienia podczas close planują jeden relaunch.

Przygotowanie planu/D-546: v1.7.333 / 9434446b39e23044e9d7198e205dce8ff9a6aaeb. Hash commita wykonania zostanie dopisany w kolejnym commicie zgodnie z AGENTS.

### Verification results

Komendy używały run-bounded.mjs, z worktree. Natywne testy/pakowanie/smoke wymagają eskalacji z powodu kontroli Windows oraz uruchamiania własnych procesów.

| Kontrola | Timeout | Wynik |
|---|---|---|
| npm run test --workspace @game-predictor/selector-desktop |120 s|151/151 PASS, 26.0 s, bez skipped |
| npm run lint / typecheck --workspace @game-predictor/selector-desktop |60 s każdy|PASS |
| Prettier zmienionych źródeł, testów i skryptów |30 s|PASS po formatowaniu smoke-ux |
| npm run package --workspace @game-predictor/selector-desktop |120 s|PASS, 7.0 s; pakiet testowy z brudnego drzewa, nie wydanie |
| npm run smoke:ux --workspace @game-predictor/selector-desktop |120 s|PASS, nowe procesy/scroll/LOCK_LOST i dwa realne EXE podczas close; jeden relaunch i zachowane args userData |
| npm run smoke:packaged --workspace @game-predictor/selector-desktop |120 s|PASS, wszystkie decision repeats, arrow repeat, undo, pełny workflow, nowy proces i relink |
| Python generate_code_map.py / npm run code-map:check |60 s każdy|PASS, nowe helpery i publiczne symbole w mapie |
| npm run docs:check / git diff --check |60/30 s|PASS przed zamknięciem; ponowiona kontrola okna przy commicie |

Pierwszy pełny test:146 PASS/5 FAIL, wyłącznie stare oczekiwania FOREIGN_CONTENT/PROJECT_NOT_FOUND. Zmieniony kontrakt ma osobne OUTPUT_FOLDER_NOT_EMPTY/PROJECT_FOLDER_FOREIGN; testy własności i oryginalnych danych pozostają. Powtórka151/151 PASS. Pierwszy smoke packaged miał błędne założenie, że skok20 wróci do wcześniejszego indeksu1; nowa sonda repeat arrow używa skoku1 i przywraca zapisany krok. Powtórka PASS bez zmiany zachowania aplikacji. Kontrola procesów po pierwszym nieudanym smoke: brak Selektor-zdjec.

### Not completed

Finalny ZIP0.1.3 należy do0987. Fizyczny odbiór0979 i audyt krzyżowy pozostają dla operatora na końcu zgodnie z D-545; nie uruchomiono Claude i nie deklaruje się niezależnego PASS nowych zmian. Android nie dotyczy lokalnej aplikacji Windows.

Istniejąca granica: nieanulowane create/open mogą zamknąć poprzedni store przed późniejszym błędem walidacji. Trwały postęp pozostaje. Anulowanie pickera oraz dialogu nowej partii zachowuje store i możliwość undo, co sprawdza regresja. Bez zmian API/Admin/Reviewera/bazy, usług, danych użytkownika, uploadu, push i merge.

### Documentation updates

Wymagania/architektura, instrukcja, TRACEABILITY, mapy kodu i CURRENT_STATE. Cztery kryteria zadania spełnione; Definition of Done sprawdzona punkt po punkcie w odpowiednim zakresie Windows. Archive okna zachowuje tekst najstarszej sekcji done bez zmian.

### Recommended next task

TASK-0985 — kompaktowy zapis i zgodna migracja.
