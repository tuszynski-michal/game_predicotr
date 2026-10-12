---
title: Obsługa błędów i płynny zapis widoku
status: in_progress
last_updated: 2026-10-12
---

# TASK-0981 — Obsługa błędów i płynny zapis widoku

## Status

`in_progress`

## Goal

Zamknąć program po utracie locka oraz zapisywać ostatni widok bez kolejki zdarzeń scroll.

## Context

Audyt operatora2026-10-12 ma REVISE. Operator zaakceptował dodatkową rundę
2–4 h z testami i nowym ZIP-em. Projekt/result pozostają lokalne, bez sieci.

## Dependencies / entry conditions

Plan OFFLINE_PHOTO_SELECTOR_AUDIT_REMEDIATION_PLAN_20261012.md zaakceptowany
poleceniem pełnej rundy.0980/0981: baza v1.7.323; ownership rozłączny,
commity w kolejności0980→0981.0982: po obu commitach, nie w trakcie ich zmian.
Oryginalny raport jest inputem operatora i nie jest edytowany.

## Recommended execution

`gpt-6.1-sol / medium`, zgodnie z końcową tabelą planu. Model/effort dostępne.
Przegląd po rundzie wykonuje operator; konfiguracja jego Claude jest warunkowa,
bez zamiany na Codex ani automatycznego CLI audytu. Eskalacja przy koniecznej
zmianie ochrony danych, protokołu trwałości lub przekroczeniu zatwierdzonego kosztu.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md — D-545
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_AUDIT_REMEDIATION_PLAN_20261012.md
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_IMPLEMENTATION_AUDIT_CLAUDE_20261012.md
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/CODE_MAP.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md
- ai_docs/tasks/0979-selector-desktop-release-acceptance.md

## Scope

- Handler close integruje bezpieczne zamknięcie backendu i shutdown workera; czeka na szereg.
- Debounce250 ms ostatnich preferencji, flush close/project change; decyzje/kursor bez debounce.
- Czytelny stan open: weryfikacja źródła i JPEG-ów; brak mylącego potwierdzenia wyboru po NAV.
- Usunięcie/blokada martwego pickSource dla aktywnego projektu.
- Korekta mylącego komunikatu storage wymiennego, bez rozszerzenia do USB.
- Instrukcja OUTPUT_MISSING_FILE: przywrócenie zgodnego backupu bez resetu/edycji manifestu.
- Doprecyzowanie retry backendu, desktop.ini/Thumbs.db i nieznanego recovery-lock.

## Out of scope

Admin/Reviewer/API/OpenAPI/baza, usługi operatora, upload/linki/Proton,
benchmarki/duże korpusy, podpis, push/merge i fizyczny odbiór0979. Bez
resetowania błędnego projektu, usuwania obcych danych lub ślepego cache proof.

## Acceptance criteria

- [ ] Rzeczywiste okno zamyka się po LOCK_LOST, bez kasowania cudzych plików; bez błędnej instrukcji retryclose.
- [ ] Scroll burst zapisuje ostatnią wartość; close/zmiana projektu zachowuje ją w nowym procesie.
- [ ] Akceptacja nie oczekuje na każdy pośredni scroll; potwierdzone decyzje pozostają szeregowane.
- [ ] Open pokazuje weryfikację; NAV nie udaje zapisu wyboru.
- [ ] Picker nie unieważnia adresów otwartego źródła, anulowanie zachowuje projekt.
- [ ] Instrukcja obejmuje brak seq JPEG, obce systemowe pliki oraz źródło dowodów idempotencji.

## Technical notes

Reguły kontraktu, walidacji i błędów opisuje zaakceptowany plan. Nie
zmieniamy ProjectState1/journal1/2 tylko dla samej optymalizacji. Dziennik,
backup, idempotencja oraz SHA przed zmianą JPEG pozostają. Kontrole nie mogą
być pozornie zielone wskutek pominięcia atrybutów lub skrócenia testów.
Worker wykonuje wyłącznie inspekcje, nie zapis danych. Każde polecenie ma
ograniczony czas, rozmiar oraz kontrolowany lifecycle. Dokładny źródłowy
raport audytu zostaje zachowany; nowe wyniki są osobnym dowodem poprawek.

## Expected files

Istniejące: main.ts (close/IPC/protocol), contracts.ts (CHANNELS/SelectorBridge),
preload.ts (bridge), renderer/App.tsx, renderer/image-viewer.tsx,
native/view-preferences.ts (ViewPreferencesStore), test/renderer-contracts.test.mjs,
scripts/smoke-packaged.mjs oraz smoke-shortcuts.mjs.
Nowe proponowane: wąski test close/view native UI. Lead edytuje dokumentację.
Nie edytuje ProjectStore/project-lock/state-codec/project-controller/source registry;
zmiany wspólnego interfejsu najpierw uzgadnia z wykonawcą0980.

## Test cases

Kryteria powyżej dostają testy regresji. Dla backendu: błędne ID/JSON,
crash/timeout worker, reparse po indeksie, martwy/nieznany lock, utrata
odpowiedzi i wznowienie journal. UI: scroll burst/flush/close, utrata locka,
picker aktywnego źródła, NAV kontra decyzja. Release: źródło/backup/import,
prawdziwa zmiana wersji programu na własnej kopii i zgodne sumy.

## Verification

Istniejące komendy z katalogu worktree; każda bounded do120 s. Najpierw
wąskie testy zmiany, następnie grupy regresji. Nowy test musi zostać dodany
z kodem; jego komendę dopisać po sprawdzeniu faktycznej ścieżki.

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:foundation --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:project --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:legacy --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:legacy-recovery --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:ui --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 45 npm run lint --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 45 npm run typecheck --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run docs:check
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run code-map:check
```

0982 używa istniejących release/smoke:release/smoke:release:shortcuts i
smoke:legacy z EXE rozpakowanego ZIP-a; każdy krok bounded120 s. Nie
wykonujemy wszystkich tych komend wielokrotnie bez zmian ani full suite202 s
w limicie120. Grupowanie nie pomija testów. Bez benchmarków i danych operatora.

## Risks / open questions

Otwarty P1 pozostaje blokadą pilotażu do wykazania poprawy; wykonawca nie
wydaje sam sobie PASS audytu. P2-4: pełny SHA jest świadomym kosztem otwarcia.
Retencja wszystkich receipts chroni stare operationId, ale powiększa stan.
P3 nieznanego pustego recovery-lock pozostaje fail-closed do dowodu właściciela.

## Outcome

### Changed

Do uzupełnienia po implementacji.

### Verification results

Testów tej rundy jeszcze nie wykonano.109/109 z audytu dotyczy poprzedniej paczki.

### Not completed

Kryteria powyżej, końcowy audyt i fizyczny odbiór0979.

### Documentation updates

Plan i task opisują zaakceptowany zamiar, nie wyniki implementacji.

### Recommended next task

Następny task według kolejności planu; po0982 audyt/odbiór operatora.
