---
title: Mała aktualizacja workspace przez IPC
status: done
last_updated: 2026-10-29
---

# TASK-1105 — Mała aktualizacja workspace przez IPC

## Status

`done`

## Goal

Zwykłe execute nie przesyła listy zdjęć i ponownie nie buduje indeksu controller/renderer.

## Context

Pełny bootstrap pozostaje O(N+D), acceptedImageIds pozostaje O(D). Inventory ProjectStore i manifest pozostają poza optymalizacją.

## Dependencies / entry conditions

TASK-1104: b280ae39, metadane f9cd8eb0. Plan rewizja 3 i koszt całego zakresu zaakceptowane. Audyty Claude pominięte przez operatora. Brak pytań blokujących.

## Recommended execution

`gpt-6.1-sol` / `medium`. Skończony pion kontraktu. Eskalacja do high przy zmianie recovery. Audyt pominięty decyzją operatora 2026-10-29.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`
- `ai_docs/delivery/SELECTOR_FLUENCY_RELIABILITY_PLAN_20261029.md`
- `ai_docs/tasks/completed/1104-selector-selection-intents.md` (zależność i smoke)

## Scope

DesktopWorkspaceUpdate, indeks SourceIndex native/renderer, adapter maszyny intencji, testy i rzeczywisty preload/IPC smoke.

## Out of scope

TASK-1106–1107, zapis trwały i SHA, HTTP/baza, usługi, dane operatora, merge/push.

## Acceptance criteria

- [x] Bootstrap jest pełny, execute nie zawiera source.images/inventory/receiptów ani absolutnych ścieżek źródłowych.
- [x] Zgodne projectId/sourceId i monotoniczna rewizja; niezgodna odpowiedź wymaga snapshotu przed kolejnym accept.
- [x] Indeks imageId/path/ordinal powstaje raz na SourceIndex; relink/open unieważnia poprzedni.
- [x] Kształt update nie zależy od N przy stałym D; intencje TASK-1104 zachowane.
- [x] Testy, prawdziwe IPC, lint/typecheck/build/smoke oraz mapa/docs przechodzą.

## Technical notes

Założenie: cache WeakMap jest związany z tożsamością obiektu zweryfikowanego SourceIndex, nie samym id. Każdy renderer ma własny bootstrap; po close/reopen/relink indeks powstaje ponownie. Pełna odpowiedź skalarów pozwala odtworzyć także pominięte rewizje; starsza odpowiedź jest odrzucana. Nie zmieniamy zasad recovery ani operationId.

## Expected files

Istniejące: apps/selector-desktop/src/contracts.ts, native/project-controller.ts, renderer/App.tsx, renderer/selection-intents.ts; test/start-resume.test.mjs, test/selection-intents.test.mjs, scripts/smoke-fluency.mjs. Main/preload przekazują typowany kontrakt bez własnej projekcji.
Nowe proponowane: src/source-index.ts, renderer/workspace-updates.ts, test/workspace-updates.test.mjs.

## Test cases

Navigate/accept/undo/range/retry; projectId/sourceId/stara rewizja; relink/puste źródło/close/reopen i niezależne bootstrapy; brak przebudowy indeksu i rozmiar delta przy małych fixture; rzeczywisty preload/IPC i regresje intencji1104.

## Verification

Każda komenda ma timeout120s: celowane node --test, lint/typecheck workspace, selector:build, smoke-fluency --local i smoke-shortcuts --local, docs:check/code-map:check. Pełny zestaw i ZIP w1107.

## Risks / open questions

AcceptedImageIds ma O(D), trwały zapis nadal ma dotychczasowy koszt. Brak otwartych pytań.

## Outcome

Commit: v1.7.498 (hash dopisuje kolejny commit).

### Changed

- Execute zwraca DesktopWorkspaceUpdate z sourceId i pełnymi skalarami, bez source.images, inventory, receiptów i absolutnych ścieżek źródłowych. Bootstrap create/open/resume/relink/snapshot nadal jest pełny. Main/preload przekazują typowany wynik.
- SourceLookup przez WeakMap buduje imageId/path/ordinal raz na SourceIndex. Controller, App, SelectionIntents i ImageViewer korzystają z indeksu zamiast find/map przez N zdjęć. Podgląd nie zmienia cache ani kolejności decode (to TASK-1106).
- ApplyWorkspaceUpdate sprawdza projekt, źródło, niemalejącą całkowitą rewizję oraz przynależność imageId. Zostawia źródło i lokalny view. Niezgodna odpowiedź przechodzi do istniejącego snapshot recovery, które blokuje F przed bootstrapem i jawnym retry. Zasady operationId i intencji1104 zachowane.
- Stare testy controller.execute przeniesione jawnie na nowy kontrakt. Testy używają małych fixture1/3 zdjęcia, sprawdzają identyczny rozmiar/kształt delta przy stałym D oraz brak ponownego dostępu do source.images po zbudowaniu indeksu. Relink/close/reopen dostają nowy indeks.

### Verification results

- Finalny celowany zestaw: `node --experimental-strip-types --test --test-concurrency=1 test/workspace-updates.test.mjs test/selection-intents.test.mjs test/renderer-contracts.test.mjs test/start-resume.test.mjs` z apps/selector-desktop: PASS47/47, 29s. Wszystkie polecenia mają subprocess timeout120s.
- Pierwszy szerszy kontrolowany zestaw z native-checks:65/68 PASS. Trzy dotychczasowe testy timeoutów150/200ms FAIL także osobno i na niezmienionej kopii HEAD f9cd8eb0 utworzonej przez `git archive HEAD apps/selector-desktop`. Potwierdzenie baseline: `node --experimental-strip-types --test --test-name-pattern "identity retries only timeout|two identity timeouts|identity timeout retry never" test/native-checks.test.mjs` (kopiowany HEAD):0/3, TIMEOUT oraz spawn1 zamiast2. Kod workera i tych testów nietknięty. Kopia baseline została usunięta po sprawdzeniu ścieżki pod własnym .tmp.
- Prettier zmienionych plików, lint/typecheck workspace i selector:build: PASS. Mapa zregenerowana; docs:check/code-map:check PASS przed zamknięciem i docs ponownie po zamknięciu.
- Smoke-fluency --local: PASS na Electron42.11.12/Windowsx64. Prawdziwe preload/IPC potwierdzają lekki payload; testowa podmiana sourceId/projectId/starej rewizji wymusza snapshot, trzymany barierą. F nie wysyła accept przed bootstrapem ani przed jawnym retry. Dalej PASS cały smoke1104: opóźnienie odpowiedzi, F/decode, identyczny retry, crash/reopen i SHA/JPEG/manifest, close timeout i lock. Dwie pierwsze próby miały błąd synchronizacji nowego scenariusza testu (Wybierz celowo jest dostępne podczas nawigacji); oczekiwanie na koniec mutacji oparto na Pomiń. Bez zmiany reguł aplikacji.
- Smoke-shortcuts --local: PASS (malejąca numeracja, F przesuwa o jeden przy step20, krótki zakres, uszkodzony JPEG, opaque IPC i relink po nowym procesie). Pierwszy przebieg zaliczył zachowanie, ale teardown własnego procesu przekroczył limit; kontrolowany cleanup zabił wyłącznie własne drzewo. Izolowane ponowienie zakończyło się normalnie.
- Testy natywnych kontroli i Electron wymagały eskalacji uprawnień procesu; bez zmiany konfiguracji systemowej. Audyt Claude pominięty jawną decyzją operatora dla całego planu; nie ma niezależnego PASS audytu.

### Not completed

- Trzy wcześniejsze niepowodzenia native-checks pozostają poza zakresem. TASK-1107 ma je rozliczyć względem powyższego baseline; bez osłabiania testów.
- Pełny suite, pomiar p95 i ZIP należą do1107; bitmap cache/decode do1106. AcceptedImageIds pozostaje O(D); odczyty inventory ProjectStore i projectManifest pozostają liniowe.
- Fizyczny restart Windows i komputer odbiorcy pending. Bez usług, migracji, oryginałów, zmian ochrony, merge/push. Cudze usunięcia artefaktów i worktree zachowane.

### Documentation updates

- Architektura opisuje kontrakt update, indeks i walidację/fallback. Plan i CURRENT_STATE wskazują zakończenie1105; mapy kodu uwzględniają nowe moduły.
- DoD oraz kryteria taska/plan1105 porównane punkt po punkcie: funkcjonalność, błędy i restart, kontrakt desktop, UX, kod i dokumentacja spełnione; testy zmienionego pionu zielone. Ograniczenia wcześniejszych testów jawnie zapisane. HTTP/baza/Android nie dotyczą tej zmiany desktopowej.

### Recommended next task

- TASK-1106 — Priorytet bieżącego zdjęcia i jeden obiekt podglądu. Cały plan ma zgodę operatora; niniejszy wykonawca kończy na1105.
