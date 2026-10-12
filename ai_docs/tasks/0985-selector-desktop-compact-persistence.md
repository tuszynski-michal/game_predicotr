---
title: Trwały zapis bez przepisywania inwentarza i historii
status: todo
last_updated: 2026-10-12
---

# TASK-0985 — Trwały zapis bez przepisywania inwentarza i historii

## Status

`todo`

## Goal

Zachować pełną trwałość i retry przy15000 zdjęć bez pełnego zapisu inventory/receiptów na każdą operację.

## Context

Pełny audyt Claude rundy2 ma PASS i otwarte P2/P3. Operator polecił wykonać
całą finalizację, zatwierdził3–5 h oraz pomiar15000. Odbiór fizyczny na końcu.

## Dependencies / entry conditions

TASK-0984 done; D-546 i kontrakt formatu w planie.

## Recommended execution

`gpt-6.1-sol / high`. Konfiguracja zgodna z tabelą planu finalizacji.
Eskaluj przy naruszeniu własności danych, idempotencji lub zgodności migracji.
Końcowy audyt operatora warunkowo `claude-sonnet-5-5 / high`;
D-545 odracza audyt do końca, bez gate CLI/per-task. Nie zastępuj Claude
niejawnie. Wewnętrzny review gpt-6-astra / high dla zapisu dowodów; nie jest audytem krzyżowym.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md — D-545, D-546
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_FINALIZATION_PLAN_20261012.md — TASK-0985
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md — sekcja desktop
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md — sekcja desktop
- ai_docs/architecture/CODE_MAP.md — selector
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_REAUDIT_CLAUDE_20261012.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md

## Scope

Disk head2, mirrored immutable inventory/baseline, append-only mirrored ledger i journal3. Cała kolejność, migracja i suffix recovery według planu/D-546. Logical state1 i outputv2 bez zmian.

## Out of scope

API/Admin/Reviewer/baza, upload/linki/Proton, usługi operatora, podpis,
instalator, push/merge oraz fizyczny odbiór0979. Bez danych użytkownika.

## Acceptance criteria

- [ ] Każda faza commit/upgrade ma test przerwania i recovery; nie gubi potwierdzonych decyzji ani nie dubluje receiptów.
- [ ] Legacy state1/journal1/2 migratują po recovery; starszy reader blokuje head2/journal3 także przy uszkodzonym primary.
- [ ] Retry bardzo starego operationId po undo/restart/open daje pierwotny receipt; inny fingerprint daje konflikt; retencja nie jest ograniczona.
- [ ] Zdrowe mirrory odtwarzają uszkodzony head/inventory/baseline/ledger; obie uszkodzone kopie blokują. Partial zgodny suffix jest kończony; inny/nadmiar jest odrzucany.
- [ ] Relink pending nie przepisuje recordu ledgeru; roots/source/project sprawdzane pod lockiem przed recovery.
- [ ] Zwykła operacja nie zapisuje inventory ani pełnego zbioru receiptów; UI nie klonuje historii receiptów na każdy krok.

## Technical notes

Disk head2, mirrored immutable inventory/baseline, append-only mirrored ledger i journal3. Cała kolejność, migracja i suffix recovery według planu/D-546. Logical state1 i outputv2 bez zmian. Zdjęcia źródłowe tylko do odczytu. Nie resetuj projektu po braku
folderu. Obce dane/niezgodne checksumy blokują zapis. Numeracja i porządek
zdjęć zachowują reguły core; wyniki są operator-local v2.

## Expected files

Ścieżki runtime względem `apps/selector-desktop/src`, skrypty/testy względem
workspace'u, o ile podano inaczej. project-store.ts execute/applyJournal/open/resumeInternal/relinkPending; state-codec.ts validators; types.ts; SecureFiles; project-controller.ts snapshot. Nowe proponowane project/project-storage.ts i test/compact-persistence.test.mjs.

## Test cases

Fault ENOSPC/rename/append, prawdziwy exit procesu, legacy adoption, upgrade, poisoned old reader, mirrors, suffix, foreign data, expected identity i relink w każdej fazie.

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

Do uzupełnienia po wykonaniu.

### Verification results

Do uzupełnienia po wykonaniu; planowane komendy nie są wynikiem PASS.

### Not completed

Do uzupełnienia po wykonaniu.

### Documentation updates

Do uzupełnienia po wykonaniu.

### Recommended next task

TASK-0986
