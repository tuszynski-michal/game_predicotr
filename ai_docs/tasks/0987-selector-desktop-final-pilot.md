---
title: Finalny pilot0.1.3 i dowody kompletnej rundy
status: in_progress
last_updated: 2026-10-12
---

# TASK-0987 — Finalny pilot0.1.3 i dowody kompletnej rundy

## Status

`in_progress`

## Goal

Dostarczyć sprawdzony ZIP0.1.3 z pełną instrukcją, pomiarem15k i gotowym przekazaniem do odbioru operatora.

## Context

Pełny audyt Claude rundy2 ma PASS i otwarte P2/P3. Operator polecił wykonać
całą finalizację, zatwierdził3–5 h oraz pomiar15000. Odbiór fizyczny na końcu.

## Dependencies / entry conditions

TASK-0986 done; wszystkie984–986 zweryfikowane; artefakty0.1.0/0.1.2 zachowane.

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
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_FINALIZATION_PLAN_20261012.md — TASK-0987
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md — sekcja desktop
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md — sekcja desktop
- ai_docs/architecture/CODE_MAP.md — selector
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_REAUDIT_CLAUDE_20261012.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md

## Scope

Wersja0.1.3; własne fixture15000, kontrolowany baseline/final pomiar; actual ZIP update0.1.0 i0.1.2 do0.1.3; wszystkie sześć scenariuszy obu kierunków, restart procesu i migrated history; SHA/provenance.

## Out of scope

API/Admin/Reviewer/baza, upload/linki/Proton, usługi operatora, podpis,
instalator, push/merge oraz fizyczny odbiór0979. Bez danych użytkownika.

## Acceptance criteria

- [ ] Pełny desktop test/lint/typecheck/format, core/zgodność gdy właściwe, docs/code-map/diff PASS z zapisanymi komendami i timeoutami.
- [ ] ZIP0.1.3 i asar mają zgodne SHA/build-info/sourceCommit; runtime bez źródeł/monorepo; historyczne ZIP-y bez zmian.
- [ ] Sześć finalnych smoke oraz rzeczywiste update0.1.0/0.1.2→0.1.3 na kopiach przechodzą; oba kierunki/source reselect/legacy/recovery/relaunch bez utraty pracy.
- [ ] Pomiar15000 podaje rzeczywiste p50/p95 i pozostałe koszty; brak zapisu inventory/receipt history na krok, brak dodatkowych warm worker spawns.
- [ ] Instrukcja wskazuje źródłową decisions[].imagePath przy manualnym odtworzeniu JPEG i kontrolę SHA; dokumentacja wskazuje aktualną paczkę i wszystkie rundy.
- [ ] Raport domyka uwagi implementacyjne albo jasno wykazuje blokujący przypadek; fizyczny0979 i końcowy audyt operatora nie są udawane.

## Technical notes

Wersja0.1.3; własne fixture15000, kontrolowany baseline/final pomiar; actual ZIP update0.1.0 i0.1.2 do0.1.3; wszystkie sześć scenariuszy obu kierunków, restart procesu i migrated history; SHA/provenance. Zdjęcia źródłowe tylko do odczytu. Nie resetuj projektu po braku
folderu. Obce dane/niezgodne checksumy blokują zapis. Numeracja i porządek
zdjęć zachowują reguły core; wyniki są operator-local v2.

## Expected files

Ścieżki runtime względem `apps/selector-desktop/src`, skrypty/testy względem
workspace'u, o ile podano inaczej. package.json/lockfile; scripts/release/smoke; instrukcja operatora, acceptance/handoff, plany, TRACEABILITY, CURRENT_STATE, task0979. Nowe proponowane scripts/measure-selector.mjs i quality/OFFLINE_PHOTO_SELECTOR_FINAL_VERIFICATION_20261012.md.

## Test cases

Własny bounded fixture15k; true processes/updates; ZIP contents; fault log retained; original fixture bytes/mtime; source and output relink; user receipt checklist.

## Verification

Z worktree D:\game_predicotr\worktrees\offline-photo-selector. Najpierw pion,
potem pełny desktop. Każdy krok ma timeout; brak wyniku60s wymaga kontroli
zgodnie z AGENTS, buildy kontrolowane mają znany limit120s.

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test --workspace @game-predictor/selector-desktop
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

Do uzupełnienia po wykonaniu.

### Verification results

Do uzupełnienia po wykonaniu; planowane komendy nie są wynikiem PASS.

### Not completed

Do uzupełnienia po wykonaniu.

### Documentation updates

Do uzupełnienia po wykonaniu.

### Recommended next task

Fizyczny odbiór TASK-0979 przez operatora i jego końcowy audyt.
