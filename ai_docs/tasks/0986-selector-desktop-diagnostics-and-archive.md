---
title: Diagnozowalny start i automatyczna kontrola paczki
status: todo
last_updated: 2026-10-12
---

# TASK-0986 — Diagnozowalny start i automatyczna kontrola paczki

## Status

`todo`

## Goal

Zachować dowody błędów startu/aktualizacji i automatycznie sprawdzać zawartość/provenance asar.

## Context

Pełny audyt Claude rundy2 ma PASS i otwarte P2/P3. Operator polecił wykonać
całą finalizację, zatwierdził3–5 h oraz pomiar15000. Odbiór fizyczny na końcu.

## Dependencies / entry conditions

TASK-0985 done; hipoteza WMI nadal wymaga weryfikacji, nie zakładamy przyczyny.

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
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_FINALIZATION_PLAN_20261012.md — TASK-0986
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md — sekcja desktop
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md — sekcja desktop
- ai_docs/architecture/CODE_MAP.md — selector
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_REAUDIT_CLAUDE_20261012.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md

## Scope

Ograniczona świeża próba identity i jeden retry timeoutu z diagnostyką czasu; unknown nadal failclosed. Zachowanie logów przy porażce smoke; kontrola asar/build-info na istniejącym ZIP.

## Out of scope

API/Admin/Reviewer/baza, upload/linki/Proton, usługi operatora, podpis,
instalator, push/merge oraz fizyczny odbiór0979. Bez danych użytkownika.

## Acceptance criteria

- [ ] Cold/timeout identity ma ograniczone próby, log czasu i zachowuje failclosed; timeout nie dowodzi martwego procesu.
- [ ] Nieudany smoke zachowuje selector.log w osobnym katalogu diagnostycznym, sprząta własne procesy, nie usuwa danych operatora.
- [ ] Automatyczna kontrola odrzuca asar ze src/node_modules oraz niezgodne build-info/sourceCommit/dirty/wersję; zgodny ZIP przechodzi.
- [ ] Lint/typecheck i testy native/release przechodzą; logi nie zawierają zdjęć ani nieograniczonego dumpu.

## Technical notes

Ograniczona świeża próba identity i jeden retry timeoutu z diagnostyką czasu; unknown nadal failclosed. Zachowanie logów przy porażce smoke; kontrola asar/build-info na istniejącym ZIP. Zdjęcia źródłowe tylko do odczytu. Nie resetuj projektu po braku
folderu. Obce dane/niezgodne checksumy blokują zapis. Numeracja i porządek
zdjęć zachowują reguły core; wyniki są operator-local v2.

## Expected files

Ścieżki runtime względem `apps/selector-desktop/src`, skrypty/testy względem
workspace'u, o ile podano inaczej. native/windows-check-worker.ts processIdentity; native/diagnostic-log.ts; project/project-lock.ts; scripts/smoke-*.mjs/release-support.mjs/smoke-release.mjs; test/native-checks.test.mjs/release.test.mjs.

## Test cases

Wstrzyknięty timeout pierwszej identity, trwały błąd i retry; fault smoke i log retention; prawdziwy archive oraz mała zła fixture.

## Verification

Z worktree D:\game_predicotr\worktrees\offline-photo-selector. Najpierw pion,
potem pełny desktop. Każdy krok ma timeout; brak wyniku60s wymaga kontroli
zgodnie z AGENTS, buildy kontrolowane mają znany limit120s.

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:native --workspace @game-predictor/selector-desktop
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

TASK-0987
