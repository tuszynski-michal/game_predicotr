---
title: Poprawiony pilotaż 0.1.1 i dowody odbioru
status: done
last_updated: 2026-10-12
---

# TASK-0982 — Poprawiony pilotaż 0.1.1 i dowody odbioru

## Status

`done`

## Goal

Zbudować i sprawdzić ZIP 0.1.1 z obu commitów poprawek oraz przekazać dowody operatorowi.

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
- ai_docs/tasks/completed/0979-selector-desktop-release-acceptance.md

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

- [x] ZIP 0.1.1 ma SHA, prawdziwy sourceCommit i applicationSourceDirty=false.
- [x] Wszystkie smoke poprawionej paczki PASS, fixture/userData izolowane i procesy posprzątane.
- [x] Projekt kopii utworzony0.1.0 otwiera się0.1.1 z decyzjami/kur­sorem/JPEG zachowanymi.
- [x] Historyczny ZIP 0.1.0 i jego sumy niezmienione.
- [x] Lista zamkniętych i otwartych uwag nie udaje werdyktu niezależnego audytu.
- [x] docs:check/code-map:check PASS; brak fizycznego odbioru nie jest raportowany jako PASS.

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

Wersja aplikacji 0.1.1 i zgodny wpis workspace version w lockfile, bez zmian
zależności. Warianty smoke-release sprawdzają full/shortcuts/legacy/ux z tego
samego ZIP-a. smoke-update sprawdza rzeczywiste programy 0.1.0 i 0.1.1 na
izolowanej kopii projektu, z jawnym przepięciem kopii wyniku. Oryginalne
fixture source/project/output pozostają niezmienione.

Commit źródeł wydania: v1.7.326 /
ede94bdcb3ad1cac5838f524b604423bec81b69f. Finalny zapis dowodów i poprawki
harnessu w v1.7.327 nie zmienia runtime ani ZIP-a.

Paczka zachowana w apps/selector-desktop/out/releases/pilot-0.1.1-ede94bdc:
Selektor zdjec-win32-x64-0.1.1.zip, 149400221 bajtów. Sąsiadujące .sha256 i
.release.json zachowano bajtowo. ZIP SHA-256:
fa1891d20f0348de2e89e4a66d5b4e849744ba148ae961c29e5997072512b023.
app.asar SHA-256:
9c3d0c6bb46ac262106c1cf1e8c5181971045ee4ebafdf0d0bfcb957bd17adc8.
dirty=false, applicationSourceDirty=false. BuiltAt2026-10-12T09:43:02.413Z,
releasedAt2026-10-12T09:43:25.794Z. Historyczne oba ZIP-y 0.1.0 zachowały SHA.

### Verification results

test:release 2/2, globalny lint/typecheck, format i diff PASS. Release
około 24 s; full smoke 18 s, shortcuts/source-relink 12 s, legacy 12 s, UX 12 s i
rzeczywista aktualizacja 35 s PASS. Czasy przybliżone według logów; każdy
build/smoke ma rzeczywisty timeout 120 s. Unit/lint/typecheck bounded 30 s.
Aktualizacja zachowuje projectId, decyzje, kursor oraz SHA seq_1-9.jpg.
Po jawnym relink kopii wyniku nowa decyzja seq_19-27.jpg ma zgodne bajty
i przetrwała nowy proces. SHA/size/mtime oryginalnych fixture są identyczne.
Nie pozostały własne osierocone procesy. Kopia ZIP-a i metadane zweryfikowane.

Pierwszy smoke aktualizacji porównywał tymczasowy opaque UUID między
procesami. Poprawiony wyłącznie harness porównuje ordinal, relativePath
oraz zapisany currentRelativePath; nie osłabia dowodu kursora. Finalny test
PASS. Poprawka testu po commicie326 nie wymagała zmiany runtime lub ZIP-a.

Backend124 oraz UI 4 z0980/0981 pozostają aktualne; z release 2 łącznie130
unikalnych testów tej rundy PASS. Nie powtarzano rdzenia/Reviewera bez zmiany
ich modułów. docs:check/code-map:check i git diff --check PASS przy zamknięciu.
Logi: apps/selector-desktop/.tmp/0982-*.log, w tym0982-smoke-update-final.log.

Komendy z katalogu worktree, każda bounded 120 s:

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run release --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:shortcuts --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:legacy --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:ux --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:update --workspace @game-predictor/selector-desktop
```

### Not completed

Końcowy audyt i fizyczny odbiór0979: drugi komputer, rzeczywista dystrybucja,
restart Windows i uruchomienie bez narzędzi deweloperskich wymagają operatora.
Niepodpisany pilot; brak gwarancji identycznych bajtów przebudowy lub odporności
na awarię dysku/zasilania. Pełne SHA open, rosnący journal/receipts,
nieznany recovery guard, brak USB/automatycznego repair pozostają świadomymi
ograniczeniami planu. Bez benchmarku, usług, danych operatora, push i merge.

### Documentation updates

Rejestr paczki, przekazanie, instrukcja, raport dowodów poprawek, plan,
Outcome/CURRENT_STATE i mapy. Oryginalny audyt REVISE zachowano bez zmiany.
To dowody wykonawcy, nie PASS niezależnego audytu.

### Recommended next task

Operator: audyt poprawionego zakresu i fizyczny odbiór TASK-0979.
