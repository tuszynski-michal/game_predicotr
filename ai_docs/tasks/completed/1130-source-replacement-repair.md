---
title: Przygotowanie nowych zdjęć dla otwartych luk
status: done
---

# TASK-1130 — Przygotowanie nowych zdjęć dla otwartych luk

## Status

`done`

## Goal

Istniejące Uzupełnij luki przygotowuje nowe JPEG-i dla dokładnych zakresów request-v1 w osobnym, trwale journalowanym output v3.

## Context

C1 zaakceptowanego planu 777A2. B2b 6ba198b9 / record 24f5d740 dostarcza typed request eksportowany wyłącznie dla wybranych gap_open.

## Dependencies / entry conditions

B1/B2a/B2b zakończone i audytowane. Implementacja narzędzia, bez danych operatora, usług, migracji, merge/push i zamykania backendowych luk.

## Recommended execution

gpt-6.1-sol / high; niezależny claude-opus-5-5 / medium przed commitem. Eskalacja przy sprzeczności kontraktu lub otwartym P0/P1 po jednej rundzie poprawek.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md` — C1/C2
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-580--wycofanie-całego-źródła-i-autoryzacja-otwartej-luki`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md` — lokalna korekta
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md` — lokalna korekta
- `ai_docs/architecture/CODE_MAP.md` i `CODE_MAP_SYMBOLS.md`

## Scope

Minimalny czysty core v3, typed request parser, exact ranges, osobny FSA adapter, istniejący ekran z trybem source_replacement, ponowna autoryzacja bieżącego entry przez obecne API, journal/recovery i niezmieniony handoff filled-gaps-v1.

## Out of scope

Admission/staging backend/import/restored (C2), nowy endpoint, Electron, operatorowe operacje i zmiana semantyki v1/v2.

## Acceptance criteria

- [x] Request używa wygenerowanego typu API i kanonicznego digestu; dokładne zakresy bez min–max i zaokrągleń.
- [x] Nowe seq JPEG są read-only, duplikat wymaga jawnego wyboru; output pusty albo własny v3, nigdy źródłowy.
- [x] Nowy zapis sprawdza target entry/revision/scopeDigest/gap_open/seq w skonfigurowanym API; inny entry nie unieważnia postępu.
- [x] Intent/write/hash/commit i recovery nową instancją są idempotentne; obcy/zmieniony/niepełny plik blokuje mutację.
- [x] Filled-gaps-v1 zawiera wyłącznie rzeczywiste zweryfikowane committed JPEG z proweniencją journalu; binding tylko v3.
- [x] V1/v2 bez zmiany kontraktu, odrzucają v3; UI rozróżnia lokalny wynik i backendową lukę.
- [x] Testy pionu, format/lint/typecheck, dokumentacja, audyt, task-close i commit.

## Technical notes

Założenia bez zmiany domeny: nowy moduł i adapter v3 nie używają v2 auto-adoption/min–max. Plik requestu nie wybiera serwera; authority to skonfigurowany uwierzytelniony klient. Global batch revision nie jest CAS. Jedna operacja i jeden JPEG naraz; recovery może ponownie wskazać read-only source po utracie uprawnień. Zapisany lokalny output nie zamyka backendowego gap_open. Existing v1/v2 reader odmawia katalogu v3, a wspólny handoff reader rozpoznaje oba niezależnie.

## Expected files

Nowe: core `replacement-repair.ts`, Admin `replacement-repair-storage.ts`, `replacement-repair-workspace.tsx`, testy core/adapter/UI. Istniejące: repair workspace mounting, repair reader/handoff, package exports/dependency, wymagania/architektura, mapa kodu i bieżący stan.

## Test cases

Exact zakres <9, rozłączne luki, zły/overlap/duplicate range, stare SHA, brak/current API/stale target/unrelated entry, obcy katalog, intent przed write, JPEG przed hash/commit, commit przed handoff, utracona odpowiedź i ponowne otwarcie, zmieniony/partial JPEG, v1/v2 regresje.

## Verification

Z katalogu worktree, każde polecenie timeout 120 s: Node strip-types testy core/repair i Admin repair/crop/picker, workspace/scoped TypeScript, ESLint zmienionych plików, Prettier zmienionych plików; Python root venv generate_code_map i cztery docs checkers. Szerszy build po scoped checks, bez uruchamiania usług. Audyt timeout 480 s.

## Risks / open questions

FSA nie zapewnia locka między procesami; sprawdzanie własności i journalu odmawia obcym celom. Backend C2 ponownie waliduje admission. Ręczny odbiór natywnego pickera i danych operatora pozostaje D1/operatorowi.

## Outcome

Commit: v1.7.529 (hash dopisuje kolejny commit).

### Changed

- Osobny, czysty core replacement-repair, typed generated API import przez types-only subpath; runtime parser i digest zgodny z rzeczywistym fixture PG request-v1.
- V3 FSA adapter z exact ranges, read-only source, odrębnym owned output, journalem intent/committed, Web Locks na zapis/recovery i fail-closed drift/foreign/partial.
- Istniejący ekran Popraw selekcję ma opcję request-v1, nazwę gry z obecnego API, podgląd całego zdjęcia i ręczny wybór duplicate range. Nowy zapis wymaga fresh GET target entry. UI wyraźnie mówi o lokalnym wyniku i otwartej backendowej luce.
- Filled-gaps-v1 niezmieniony; proweniencja journalu i rzeczywiste verification evidence. Uzgodniony z C2 helper deriveReplacementStagingSelection zachowuje request A+B, ale selectedEntryIds/files zawierają wyłącznie jawnie wybrane verified committed A. Brak C2 API.

### Verification results

- `node --experimental-strip-types --test packages/manual-image-selection-core/test/replacement-repair.test.mjs packages/manual-image-selection-core/test/manual-selection-repair.test.mjs` — 14 PASS, timeout120 s.
- `node node_modules/tsx/dist/cli.mjs --tsconfig artifacts/c1130/tsconfig.json --test apps/admin/test/replacement-repair.test.mjs apps/admin/test/manual-selection-repair.test.mjs apps/admin/test/selected-image-crop-storage-contract.test.mjs apps/admin/test/local-directory-picker.test.mjs apps/admin/test-interactions/replacement-repair-workspace.test.mjs` — 60 PASS, timeout120 s. Realny dysk, fresh child process (timeout30 s) po JPEG, crash/lost-response przed/po intencji, przed/po JPEG, commit/handoff, pending source drift, foreign output i concurrent foreign requests; UI nazwa gry/zakres/duplikat/nieobecne API; stale public inspector kontra writer, foreign handoff i source A+unselected B; delayed duplicate >400ms, temp .crswap i readonly handoff bez writes/zmiany bytes/mtime/promowania intent. Po dodaniu jawnego licznika createWritable testy filesystem17/17 PASS.
- `node node_modules/typescript/bin/tsc --noEmit -p artifacts/c1130/tsconfig.json` oraz `core-tsconfig.json` — scoped Admin i core PASS, każdy timeout120 s. Tymczasowe konfiguracje dziedziczą repo tsconfig i kierują TS paths na LOCAL client/index, client/types generated, core/index, core/*, board-search-ui/index oraz @/*; bez zmiany junction/main.
- ESLint pięciu zmienionych modułów Admina i trzech nowych testów — PASS, timeout120 s. Prettier zmienionych TS/TSX/MJS/package.json — PASS.
- Root venv `scripts/generate_code_map.py`, `check_decision_links.py`, `check_current_state_window.py`, `check_startup_read_budget.py`, `check_skill_mirrors.py` — PASS, każdy timeout120 s.
- Audyt Opus 5.5/medium R1 PASS, actual modelUsage `claude-opus-5-5`, 22 bounded reads. Raport R1 zachowany w `ai_docs/quality/TASK-1130_AUDIT_claude-opus-5-5_R1.md`. Jedna runda poprawek: cacheScope dla nowego preview, dedykowany temp-file failclosed i polskie błędy. Koordynator rozpoznał dodatkowy P1-COMPAT: readonly crop consumer nie może wywoływać mutującego readera (dawne P3-1); naprawiono readonly verify+derive persisted committed, recovery wyłącznie readwrite. Celowany R2 Opus 5.5/medium PASS, actual modelUsage `claude-opus-5-5`, zamknął P1-COMPAT/P2-1/P2-2; raport `ai_docs/quality/TASK-1130_AUDIT_claude-opus-5-5.md`. Brak P0/P1/P2. Po R2 dodano bezpośredni assert disabled przed 300ms (UI3/3 PASS); bez R3.

### Not completed

- Ograniczenia operacyjne: pending dla A blokuje ogon B w tym output; równoczesna inicjalizacja jednego pustego outputu przez legacy v1/v2 i v3 nie jest wspólnym workflow. Nieznany .crswap bez własnego manifestu pozostaje foreign/failclosed; bez automatycznego usuwania/adopcji. Journal wymaga stabilnego nonempty operationId (nowe IDs z crypto.randomUUID), bez migracji historycznych formatów.
- Bez usług, danych operatora, migracji, importu/admission/restored, aktywacji, merge/push. Pełny build i odbiór fizycznego Windows/FSA pozostają D1/operatorowi. Brak testu Android FSA: funkcja wymaga przeglądarki wspierającej natywny picker katalogów.

### Documentation updates

- Wymagania i architektura lokalnego manual selection opisują osobny v3, autoryzację aktualnego API, recovery i częściowy descriptor dla C2. CURRENT_STATE i wygenerowana mapa kodu zaktualizowane. D-580 już rozstrzyga authority, bez nowej decyzji/migracji.

### Recommended next task

- TASK-1131 / C2: mapowanie lokalnego descriptoru na pełny pion staging/admission/import/review z ponowną autoryzacją backendu. B2b schema0175/manifestv21 i mainpin40581449 bez zmian.
