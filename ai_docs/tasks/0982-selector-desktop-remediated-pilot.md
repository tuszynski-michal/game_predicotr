---
title: Poprawiony pilotaż 0.1.1 i dowody odbioru
status: in_progress
last_updated: 2026-10-12
---

# TASK-0982 — Poprawiony pilotaż 0.1.1 i dowody odbioru

## Status

`in_progress`

## Goal

Zbudować i sprawdzić ZIP0.1.1 z obu commitów poprawek oraz przekazać dowody operatorowi.

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

- Bump0.1.1 wyłącznie wersji workspace i zgodnego wpisu lockfile; zależności pozostają przypięte.
- Świeży release/ZIP/SHA/app.asar/build-info; stabilna kopia w out/releases.
- Full/source-relink/legacy smoke EXE z tego samego ZIP-a.
- Aktualizacja własnej kopii projektu0.1.0→0.1.1, bez modyfikacji danych operatora.
- Raport poprawek odnosi się do każdego ustalenia oryginalnego audytu.
- Końcowy ponowny audyt i fizyczny odbiór0979 pozostają działaniami operatora.

## Out of scope

Admin/Reviewer/API/OpenAPI/baza, usługi operatora, upload/linki/Proton,
benchmarki/duże korpusy, podpis, push/merge i fizyczny odbiór0979. Bez
resetowania błędnego projektu, usuwania obcych danych lub ślepego cache proof.

## Acceptance criteria

- [ ] ZIP0.1.1 ma SHA, prawdziwy sourceCommit i applicationSourceDirty=false.
- [ ] Wszystkie smoke poprawionej paczki PASS, fixture/userData izolowane i procesy posprzątane.
- [ ] Projekt kopii utworzony0.1.0 otwiera się0.1.1 z decyzjami/kur­sorem/JPEG zachowanymi.
- [ ] Historyczny ZIP0.1.0 i jego sumy niezmienione.
- [ ] Lista zamkniętych i otwartych uwag nie udaje werdyktu niezależnego audytu.
- [ ] docs:check/code-map:check PASS; brak fizycznego odbioru nie jest raportowany jako PASS.

## Technical notes

Reguły kontraktu, walidacji i błędów opisuje zaakceptowany plan. Nie
zmieniamy ProjectState1/journal1/2 tylko dla samej optymalizacji. Dziennik,
backup, idempotencja oraz SHA przed zmianą JPEG pozostają. Kontrole nie mogą
być pozornie zielone wskutek pominięcia atrybutów lub skrócenia testów.
Worker wykonuje wyłącznie inspekcje, nie zapis danych. Każde polecenie ma
ograniczony czas, rozmiar oraz kontrolowany lifecycle. Dokładny źródłowy
raport audytu zostaje zachowany; nowe wyniki są osobnym dowodem poprawek.

## Expected files

Istniejące: apps/selector-desktop/package.json i root package-lock.json,
scripts/release*.mjs oraz smoke*.mjs. Nowy proponowany test aktualizacji kopii
może być ignorowanym bounded helperem korzystającym ze sprawdzonych smoke APIs.
Lead: rejestr odbioru, przekazanie, Outcome/CURRENT_STATE i osobne commity.

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

Wersja aplikacji0.1.1 i wyłącznie zgodny wpis workspace version w lockfile,
bez odświeżania zależności. smoke-release obsługuje warianty full/shortcuts/
legacy/ux z weryfikacją tego samego ZIP-a. Nowy smoke-update uruchamia
historyczne0.1.0, tworzy własny projekt, otwiera kopię w0.1.1, jawnie przepina
kopię wyniku i sprawdza decyzje/kursor/SHA w nowym procesie. Oryginalny
fixture source/project/output musi pozostać niezmieniony.

Kod wydania commitowany przed finalnym buildem w celu prawdziwego provenance:
v1.7.326; hash zostanie dopisany po commicie. Task pozostaje in_progress do
wykonania nowego release i odbioru lokalnego.

### Verification results

test:release2/2 PASS, globalny lint i typecheck desktopu PASS, format/diff
PASS. Bounded120s dla testów,45s lint/typecheck. Warianty końcowego ZIP-a
oraz rzeczywista aktualizacja zostaną wykonane po commicie źródeł.
Logi dotychczasowe: apps/selector-desktop/.tmp/0982-{test-release,lint,
typecheck,format}.log. Testy backendu124 i UI4 są aktualne z0980/0981;
nie powtarzamy ich bez zmiany modułów. docs:check/code-map:check PASS.

Komendy kolejnych kroków, każda bounded120s:

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run release --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:shortcuts --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:legacy --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:ux --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:update --workspace @game-predictor/selector-desktop
```

### Not completed

Świeży release, smoke nowegoZIP-a, faktyczna zmiana wersji na własnej kopii,
finalne SHA i przekazanie. Końcowy audyt oraz fizyczny odbiór0979 pozostają
operacjami operatora; nie zostaną oznaczone PASS na podstawie testów agenta.

### Documentation updates

Przygotowane statusy i komendy; końcowy rejestr paczki i wyniki po wykonaniu.
Bez usług operatora, danych użytkownika, push/merge i niezleconego audytu.

### Recommended next task

Dokończyć0982 po commicie źródeł; następnie audyt/odbiór operatora.
