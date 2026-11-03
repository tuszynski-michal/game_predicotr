---
title: Uproszczony panel i zastosowanie modelu
status: done
last_updated: 2026-11-02
---

# TASK-1122 — Uproszczony panel i zastosowanie modelu

## Status

`done`

## Goal

Wykonać T3 zaakceptowanego planu uczenia wspólnego modelu siatek z zapisanych korekt.

## Context

Operator ma ponad 100 poprawionych plansz Mumie A2 i potrzebuje uczenia bez ręcznej rejestracji nagrań. Liczba jest deklaracją, nie pomiarem kwalifikujących się danych.

## Dependencies / entry conditions

TASK-1121 ukończony z audytem; istniejące API i raporty pozostają zgodne.

Wyjątek jawnie zlecony przez operatora po limicie Anthropic: „Kontynuuj a potem
audyt”. Implementację T3 rozpocząć na odizolowanej kopii stabilnego T2; audyt
i commit T2 nadal muszą poprzedzić integrację, audyt i commit T3. Nie pomijać
żadnego audytu ani zastępować Opus innym modelem.

## Recommended execution

gpt-6.1-sol/high, według tabeli planu. Obowiązkowy niezależny audyt Claude Code claude-opus-5-5/high przed commitem; P0/P1 blokują commit. Niedostępność przypisanego modelu wymaga jawnej aktualizacji, bez niejawnej zamiany.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- [Plan i pełny zakres T3](../../delivery/GRID_CORRECTIONS_LEARNING_PLAN_20261102.md)
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`, `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/VISION_LAB.md`, `ai_docs/architecture/CODE_MAP.md`
- [D-554](../../process/decisions/DECISION_LOG_2026.md#d-554--nagrania-i-ochrona-danych-kontrolnych-geometrii-v3)
- [D-556](../../process/decisions/DECISION_LOG_2026.md#d-556--niezmienne-kohorty-geometrii-v3-i-aktualność-dowodów)
- [D-559](../../process/decisions/DECISION_LOG_2026.md#d-559--ocena-kandydata-geometrii-v3-per-gra-i-most-aktualności-dowodów)

## Scope

Pełna sekcja T3 planu; zasady i minima z planu są obowiązujące.

## Out of scope

Trening na danych operatora, zmiana defaultu lub przypisań, migracja bazy operatora, restart usług, merge/push; klasyfikator symboli i uczenie detektora całego ekranu.

## Acceptance criteria

- [x] GET-only otwarcie; prowadzony workflow; full API vertical; lost response/restart bez duplicates; apply osobne i jawne, actual-assigned baseline, partial success.
- [x] Właściwe testy, lint/typecheck i dokumentacja.
- [x] Audyt Opus 5.5/high bez otwartych P0/P1.
- [x] Outcome, task-close, osobny wersjonowany commit i record-hash.

## Technical notes

Przed kodowaniem ponownie odczytać ten task i sekcję T3 planu. Chronić istniejące polityki/snapshoty/raporty; nowe reguły wersjonowane. API zmieniać jednym pionem. Mutacje operatora wyłącznie z osobną zgodą. Podgląd nie tworzy dowodu faktycznego użycia danych.

Interpretacja concurrent default potwierdzona przez leada: świeży preview może
przypiąć nową rewizję tej samej wersji bazy. Inna wersja defaultu bez dowodu
porównania z nią blokuje zastosowanie starego kandydata; UI wskazuje nowy przebieg
bez automatycznego treningu. Własny receipt zmiany defaultu pozwala wznowić kroki
tego samego apply, o ile head nie został ponownie zmieniony.

R1: istniejąca publikacja kandydata może zostać przyjęta bez drugiej mutacji
wyłącznie przy identycznych evaluationId/evaluationSha256/manifestSha256,
kanonicznym evidence i checksum. Krok zapisuje deterministyczny receipt
`already-published`; inny dowód blokuje preview i wykonanie. Własny zakończony
default ma osobny komunikat i nie oferuje niemożliwego opt-in. Nowy start
blokują tylko aktywne apply; failed nie blokuje świeżego podglądu po obcym CAS.
Failed-but-resumable może więc konkurować z nowym przebiegiem po resume; CAS
chroni dane, ale jeden przebieg może zakończyć się jawnym konfliktem w historii.
To jawne ryzyko P2, bez osłabienia kontroli. Resume created/processing/completed
jest idempotentnym odczytem bieżącego wyniku, bez nowych etapów.

## Expected files

Istniejące moduły wejściowe (ścieżki usług względem ich katalogów src): apps/admin/src/features/model-quality/grid-model-workspace.tsx; packages/admin-api-client. Nowe pliki wskazać w Outcome przed audytem.

## Test cases

Scenariusze T3 i T4 w planie: minima, brak danych, nowe/stare polityki, aliasy, restart, utracona odpowiedź, konflikty rewizji; zakres testów odpowiedni do zmienionego pionu.

## Verification

Polecenia ustalić z package.json/pyproject i istniejących testów. Każda skończona komenda z timeout <=120 s; build po uprzedzeniu, audyt <=600 s zgodnie ze skillem. Nie uruchamiać szerokich benchmarków.

## Risks / open questions

Preflight i rzeczywista kwalifikacja danych mogą zatrzymać implementację przed błędną obietnicą użycia korekt. Wynik pomiaru należy zapisać w Outcome.

## Outcome

Commit: v1.7.519 / `470faf466dc1b0184169e3800ea82c8f6b1ca1d9`.

T3 rozpoczęto w odizolowanym `worktrees/grid-corrections-panel`; ta kopia jest
zamrożona. Po audycie T2 R2 PASS lead przeniósł T3 do
`worktrees/grid-corrections-learning` przez clean three-way merge, zachowując
poprawki R1/R2. Rzeczywista baza integracji i audytu T3 to ukończone T2:
`7801ea4711f92f04eeeb58bfed124f9f850e01e0` (`v1.7.518`). Stare trees7c/5394
były wyłącznie technicznymi bazami przygotowania i nie określają już diffu T3.
Przeniesione hunki T3 są w indeksie; wykonawca integracji nie resetował go ani
nie tworzył commita. Metadane record-hash T2 pozostają zachowane osobno do
commita T3. Audyt i zamknięcie T3 nadal należą do leada.

### Changed

- Cienki panel podstawowy, liczniki backendu, zakres oceny, start/postęp/raport,
  osobne potwierdzone zastosowanie, historia i przywrócenie wersji gry.
- Zaawansowany wcześniejszy workflow zachowany; kontrola jakości i reinference
  wydzielone jako osobne narzędzia. Obsługa małych ekranów i kontrole co najmniej 44 px.
- Trwały apply parent z osobnym discriminator, zamkniętymi schematami HTTP/job,
  GET-only preview/status, CAS, osobnymi comparison evidence oraz receipts kroków.
- Pełny pion OpenAPI/generated SDK/wrapper i test żądania.

### Verification results

Po połączeniu z T2 R1/R2: 27/27 interakcji panelu i legacy workspace,
29/29 testów stanu/kontraktów/jobs, 137/137 testów klienta po buildzie,
40/40 backend/API/worker i regresji scoped publication/composition PASS.
Parent LEARNING PostgreSQL replay/CAS/cancel/resume: 1/1 PASS na disposable DB,
27.94s; ten dowód nie dotyczy rodzica apply.
Admin TypeScript, klient TypeScript/build, scoped ESLint/Ruff/mypy, generated-client
check, docs:check i code-map:check PASS. Build po integracji przed R1: PASS
(exit0,20.52s). Aktualny build R1 i rzeczywisty test APPLY opisano poniżej;
wcześniejszy szkic artifacts nie zastępuje regresji w repozytorium.
Szczegóły i rzeczywiste ścieżki: [raport weryfikacji](../../quality/TASK-1122_VERIFICATION.md).
Po integracji scoped mypy siedmiu modułów PASS; szeroki mypy pozostaje jawnym
ograniczeniem T4, bez zmiany konfiguracji globalnej. Polskie etykiety P2-2
scope-stale oraz busy/cancellation-pending mają test. Lista audytu:
R1: `artifacts/task1122-audit-paths.txt`, 35 ścieżek bez metadanych T2 i CODE_MAP.
Pełna lista po R1: `artifacts/task1122-audit-paths-r2.txt`, 36 ścieżek wraz z nowym
testem PostgreSQL APPLY leada. Focused R2: `artifacts/task1122-audit-paths-r2-focused.txt`,
zmieniony serwis/UI/testy/docs i zachowany R1; bez metadanych T2 i CODE_MAP.

Po R1 REVISE wykonano jedną rundę poprawek P1-1/P2-2/P2-3/P2-4. Focused
regresje: 48/48 backend/API/worker i T2 scoped/composition PASS; 13/13 interakcji
nowego panelu PASS. Po dodaniu dodatkowego przypadku currentness: 25/25 unit
samego apply PASS. Mypy zmienionego serwisu, scoped Ruff/ESLint, Admin TypeScript,
OpenAPI/SDK i mapa PASS. Focused [R2](../../quality/TASK-1122_AUDIT_claude-opus-5-5.md) audytu: PASS, bez P0/P1.
Raport R1 pozostaje bez zmian. Uwagi P2-3/P2-5/P2-6 R2 przechodzą jawnie do T4:
blokada konkurencyjnego resume oraz bezpieczny i zgodny z kolejnością odczyt historii.

Lead: wszystkie trzy warianty realnego APPLY PostgreSQL PASS: `first_apply`
1/1,24.84s; manual/different_evidence 2/2,40.98s (dwa osobne wywołania). To nowa regresja
T3 po audycie w `integration/test_grid_correction_apply_postgres.py`, używana
dalej przez T4 zamiast szkicu artifacts. Preview/control.execute pozostają realne;
kontrolowana granica dotyczy `_evidence` i historycznego FixtureInspector.
Build R1 original PASS (exit0,17.52s).

### Not completed

- Audyt Opus5.5/high T3 zakończony PASS; task-close i osobny commit prowadzi lead.
  T2 po audycie i commicie zostało zintegrowane. Nie uruchamiano usług, treningu, migracji
  operatora ani zmian modeli.
- Odbiór nowych importów/starych korekt i szersza kontrola całości należą do T4.

### Documentation updates

`requirements/ADMIN_APP.md`, `architecture/VISION_LAB.md`, ten task i raport
weryfikacji. Mapy kodu zregenerowane po ustabilizowaniu backendu.

### Recommended next task

TASK-1123 po wymaganych audytach i osobnych commitach T2/T3.
