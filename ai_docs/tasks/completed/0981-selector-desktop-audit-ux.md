---
title: Obsługa błędów i płynny zapis widoku
status: done
last_updated: 2026-10-12
---

# TASK-0981 — Obsługa błędów i płynny zapis widoku

## Status

`done`

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

- [x] Rzeczywiste okno zamyka się po LOCK_LOST, bez kasowania cudzych plików; bez błędnej instrukcji retryclose.
- [x] Scroll burst zapisuje ostatnią wartość; close/zmiana projektu zachowuje ją w nowym procesie.
- [x] Akceptacja nie oczekuje na każdy pośredni scroll; potwierdzone decyzje pozostają szeregowane.
- [x] Open pokazuje weryfikację; NAV nie udaje zapisu wyboru.
- [x] Picker nie unieważnia adresów otwartego źródła, anulowanie zachowuje projekt.
- [x] Instrukcja obejmuje brak seq JPEG, obce systemowe pliki oraz źródło dowodów idempotencji.

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

Main oczekuje na szereg controller.close(), zapisuje diagnostykę, kończy
własny worker i pozwala wyjść także po LOCK_LOST. Nie usuwa cudzych blokad.
Preferencje widoku mają debounce250ms i wspólny pending Promise; flush
obejmuje zmianę projektu i zamknięcie. Decyzje nie czekają na każdy scroll,
a odpowiedź mutacji nie nadpisuje nowszego widoku interfejsu.

Usunięty martwy pickSource z IPC/preload/main. NAV pokazuje zapis pozycji,
wybór pokazuje trwałe zatwierdzenie, open informuje o weryfikacji źródła
oraz SHA JPEG-ów. OUTPUT_MISSING_FILE ma instrukcję zgodnego backupu
bez resetu lub edycji manifestu. Instrukcja opisuje obce pliki systemowe,
unknown recovery guard, idempotencję tego samego operationId i ograniczenia.

### Verification results

UI4/4 PASS, globalny typecheck i lint/format zmienionych modułów PASS.
Package wspólnego runtime PASS. Rzeczywisty EXE smoke-ux PASS (~7,5s):
open verification, NAV, 50 zdarzeń scroll+accept, flush i wznowienie w nowym
procesie, utrata locka oraz końcowy pending scroll tuż przed zamknięciem.
Obca blokada pozostała bajtowo identyczna, log zawiera LOCK_LOST, cache
zawiera ostatnie współrzędne po wyjściu. Unit burst50 daje jeden atomowy
zapis ostatniego widoku. Anulowanie pickera zachowuje projekt; martwy kanał
nie istnieje.

Pierwszy przebieg smoke miał błąd założenia harnessu: scroll49 był48,8
przy skali Windows. Test porównuje teraz ostatnią rzeczywistą wartość DOM
z cache i wznowionym widokiem; runtime nie zmieniono dla tego błędu.
Każdy krok bounded120s lub45s dla lint/typecheck. Komendy: test:ui,
package i smoke:ux przez run-bounded oraz scoped ESLint/Prettier.
Logi w ignorowanym apps/selector-desktop/.tmp/0981-*.log, finalny wynik
w0981-smoke-ux-final.log. docs:check/code-map:check/diff --check PASS.
Mapa zregenerowana; zmiany metod istniejących klas nie dodały symboli eksportu.

### Not completed

Końcowy audyt operatora po rundzie oraz fizyczny odbiór0979. Nie wykonano
CLI audytu, push/merge, usług ani danych operatora. Brak automatycznego repair
JPEG, nowego protokołu receipts, USB i przejęcia nieznanego recovery-lock
pozostaje świadomym ograniczeniem zaakceptowanego planu.

### Documentation updates

Instrukcja odtworzenia brakującego JPEG-a i storage/lock/retry,
raport dowodów poprawek, Outcome/CURRENT_STATE. Commit implementacji:
v1.7.325; pełny hash zostanie dopisany po commicie.

### Recommended next task

TASK-0982 — świeży ZIP0.1.1, test aktualizacji0.1.0→0.1.1 oraz przekazanie
operatorowi do końcowego audytu i fizycznego odbioru.
