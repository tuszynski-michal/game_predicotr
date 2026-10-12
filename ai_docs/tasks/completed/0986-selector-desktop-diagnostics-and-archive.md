---
title: Diagnozowalny start i automatyczna kontrola paczki
status: done
last_updated: 2026-10-12
---

# TASK-0986 — Diagnozowalny start i automatyczna kontrola paczki

## Status

`done`

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

- [x] Cold/timeout identity ma ograniczone próby, log czasu i zachowuje failclosed; timeout nie dowodzi martwego procesu.
- [x] Nieudany smoke zachowuje selector.log w osobnym katalogu diagnostycznym, sprząta własne procesy, nie usuwa danych operatora.
- [x] Automatyczna kontrola odrzuca asar ze src/node_modules oraz niezgodne build-info/sourceCommit/dirty/wersję; zgodny ZIP przechodzi.
- [x] Lint/typecheck i testy native/release przechodzą; logi nie zawierają zdjęć ani nieograniczonego dumpu.

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

ProcessIdentity wykonuje najwyżej dwie świeże próby i ponawia wyłącznie
NATIVE_CHECK_TIMEOUT. Nieznana tożsamość nadal blokuje przejęcie. Telemetria
zawiera attempt/elapsedMs/code, bez identity/ścieżek/PID. Awaria sinka jest
obojętna dla kontroli. Test z dwoma timeoutami pozostawia obcy lock bajtowo
bez zmian.

Wszystkie smoke mają wspólny finalizer z ograniczonym zamykaniem wyłącznie
zarejestrowanych własnych procesów. Ponowne close jest idempotentne. Błąd
zachowuje selector.log i rotacje poza fixture; błąd capture zachowuje cały
katalog. Failure.json zawiera ograniczony opis/kod; dane obrazu/base64/buffer
są redagowane, stos nie jest zapisywany. Nested child ma asynchroniczny
start i własny deadline, aby wykonać finally. Update obsługuje rzeczywiste
stare ZIP0.1.0 i0.1.2 oraz cursor legacy1/head2.

Verifier sprawdza świeżo rozpakowany ZIP, SHA, siedem plików app.asar,
manifest i dokładne provenance. Odrzuca src/node_modules/extra/link/unpacked.
Release używa archiwum z ZIP, nie luźnego dist. Historyczne dirty=true jest
akceptowane tylko przy identycznym build-info, bez fałszywego clean.

### Verification results

Komendy z worktree, run-bounded.mjs z jawnym limitem:

- 60 s: node --experimental-strip-types --test testy native-checks/foundation/archive/release/smoke-diagnostics — finalnie 53/53 PASS, 5,728 s. Testy realASAR14, native/foundation29, release2 i diagnostics8.
- 60 s: npm run lint --workspace @game-predictor/selector-desktop — PASS po ostatnich poprawkach.
- 60 s: npm run typecheck --workspace @game-predictor/selector-desktop — PASS.
- 30 s: Prettier --check zmienione src/scripts/test — PASS; ostatni helper/test ponownie sformatowany, lint PASS.
- 120 s: npm run package --workspace @game-predictor/selector-desktop — PASS, 8,154 s. To testowy build0.1.2 z nowym kodem, nie końcowy ZIP.
- 120 s z apps/selector-desktop: node scripts/smoke-start.mjs out/Selektor zdjec-win32-x64/Selektor-zdjec.exe — PASS: oba kierunki, historia, source reselect i moved-source relink po nowych procesach.
- 60 s: smoke-start.mjs z --diagnostic-fault-after-start — oczekiwany exit1. Finalny dowód artifacts/selector-smoke-diagnostics/smoke-start-fiYX0L zawiera prawdziwy selector.log64B i failure.json z przyczyną. Fixture usunięta po capture, zero procesów Selektor-zdjec. Kontrolowany błąd nastąpił przed pełną gotowością okna; graceful close przekroczył limit, więc zakończono wyłącznie zarejestrowany własny proces i odnotowano to w dowodzie.
- 120 s: verifier na świeżo rozpakowanym zachowanym ZIP0.1.2-c4181f7d — PASS, 7 plików i dokładny commit; ZIP/metadata bez zmian.
- 30 s: regeneracja mapy kodu. docs:check/code-map:check/diff PASS; okno44 active/10 done, 543 powiązania decyzji.

Pierwszy test archive wymagał path.normalize na Windows; poprawiony.
Pierwsza kontrola root wykryła względną ścieżkę child fixture, poprawioną na
import.meta.url; test przechodzi z repo i app cwd. Pierwszy actualstart
zaliczył wszystkie scenariusze, lecz FAIL w finalizerze już zamkniętych
obiektów Playwright. Regresja idempotentnego close i ponowny actualstart
PASS; dowód pierwotnego błędu smoke-start-9MWhz2 zachowano. Brak przyczyny
w pierwszym failure.json naprawiono przez bezpieczny ograniczony message.
Nie przedstawiamy tych pierwszych prób jako PASS. Sandbox blokował
realpath/Expand-Archive, te same własne fixture poza sandboxem przeszły.

### Not completed

Końcowy ZIP0.1.3, pełne smoke/update i pomiar15000 są w TASK-0987.
Nie ustalono historycznej przyczyny P2-E z audytu Claude; dodano ograniczone
recovery i dowody przyszłych błędów. Formalny audyt i fizyczny0979 operatora
pozostają odroczone zgodnie z D-545. Bez usług operatora lub jego danych.

### Documentation updates

Architektura i instrukcja opisują retry/failclosed oraz zachowanie logów.
Plan i CURRENT_STATE otrzymały wynik. Commit wykonania: v1.7.336 /
`c43434c28d49597407072f9636c7c07d1c3622b8`. Zapis hash w kolejnym
commicie/tasku zgodnie z procesem.

### Recommended next task

TASK-0987.
