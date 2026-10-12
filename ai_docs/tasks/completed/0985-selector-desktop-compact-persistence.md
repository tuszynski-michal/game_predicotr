---
title: Trwały zapis bez przepisywania inwentarza i historii
status: done
last_updated: 2026-10-12
---

# TASK-0985 — Trwały zapis bez przepisywania inwentarza i historii

## Status

`done`

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

- [x] Każda faza commit/upgrade ma test przerwania i recovery; nie gubi potwierdzonych decyzji ani nie dubluje receiptów.
- [x] Legacy state1/journal1/2 migratują po recovery; starszy reader blokuje head2/journal3 także przy uszkodzonym primary.
- [x] Retry bardzo starego operationId po undo/restart/open daje pierwotny receipt; inny fingerprint daje konflikt; retencja nie jest ograniczona.
- [x] Zdrowe mirrory odtwarzają uszkodzony head/inventory/baseline/ledger; obie uszkodzone kopie blokują. Partial zgodny suffix jest kończony; inny/nadmiar jest odrzucany.
- [x] Relink pending nie przepisuje recordu ledgeru; roots/source/project sprawdzane pod lockiem przed recovery.
- [x] Zwykła operacja nie zapisuje inventory ani pełnego zbioru receiptów; UI nie klonuje historii receiptów na każdy krok.

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

Disk head schema2, journal schema3, dwie niezmienne kopie inventory/baseline
oraz lustrzany append-only ledger zastępują pełny zapis stanu na każdy krok.
Logiczny ProjectState1 i manifest operator-local v2 pozostają zgodne. Cała
historia operationId i dokładne receipty są zachowane bez limitu retencji.
Recovery kończy wyłącznie zgodny pending suffix. Zdrowy mirror naprawia
uszkodzoną kopię; dwie uszkodzone kopie blokują zapis. Upgrade starych
projektów odbywa się po recovery, pod lockiem, z descriptor journal3 przed
sidecarami. Stary reader odmawia zapisu nowego projektu.

Gorąca ścieżka używa delty i pojedynczego receipt, współdzieli inventory
oraz indeks historii. Odpowiedź UI pomija inventory/receipty; publiczny
snapshot pozostaje izolowany. Relink pending zachowuje bajty recordu i
zmienia wyłącznie zweryfikowane bindings. Migracja po błędzie dysku i
przeniesieniu folderów zachowuje decyzje oraz dawny receipt.

Wewnętrzny statyczny review gpt-6-astra/high: początkowy REVISE z dwoma P1.
Jedna runda poprawek i ograniczony przegląd zmienionych P1: PASS, oba
zamknięte. Raport TASK-0985_ENGINEERING_REVIEW_CODEX.md zachowuje pierwotne
znaleziska. Nie jest audytem krzyżowym Claude.

### Verification results

Komendy z worktree, jawne limity w run-bounded.mjs:

- 120 s: npm run test --workspace @game-predictor/selector-desktop — 233/233 PASS, 110,605 s, bez skip. Zawiera 82 przypadki compact, fault każdej fazy upgrade/ledger/head, poison copy/removals, mirrory, legacy journal1/2, rzeczywiste exit/reopen, stare ID, retry, undo/restart oraz oba kierunki.
- 60 s: npm run lint --workspace @game-predictor/selector-desktop — PASS.
- 60 s: npm run typecheck --workspace @game-predictor/selector-desktop — PASS.
- 30 s: node node_modules/prettier/bin/prettier.cjs --check zmienione src/test — PASS.
- 30 s: python scripts/generate_code_map.py — aktualizacja nowych modułów/symboli.
- 60 s: npm run code-map:check — PASS.
- 60 s: npm run docs:check oraz 30 s git diff --check — PASS; okno 45 aktywnych tasków /10 done, 543 powiązania decyzji.

Wykonawca wcześniej: 165/165 skoncentrowanych testów PASS, dodatkowa macierz
14 błędów ledger/head i cztery rzeczywiste przerwania upgrade PASS. Finalna
grupa czterech regresji P1 PASS, 8,31 s. Pełna kontrola lead powyżej obejmuje
ostateczne poprawki. Analiza/review nie jest dowodem wykonania testów.

### Not completed

Pakowanie końcowego ZIP i kontrolowany pomiar15000 należą do TASK-0987.
Nie uruchomiono benchmarku ani usług operatora w tym tasku. Formalny audyt
Claude i fizyczny odbiór0979 pozostają operatorowi zgodnie z D-545.
Pozostałe jawne koszty: manifest O(D), pełne SHA przy open, pamięć
O(N+R+D), source IPC O(N) i izolowany snapshot publiczny. Nie certyfikujemy
zaniku zasilania lub awarii sprzętowej ponad dotychczasową obsługę fsync.

### Documentation updates

D-546, wymagania i architektura opisują format/migrację/recovery. Instrukcja
wymaga kopii całego folderu projektu i nowej wersji po upgrade. Plan, mapy
kodu oraz CURRENT_STATE odnotowują wynik. Commit wykonania: v1.7.335 /
`d82fbcb576ef138b8b6049102212b85f97d0a803`. Zapis pełnego hash w kolejnym
commicie/tasku zgodnie z procesem.

### Recommended next task

TASK-0986.
