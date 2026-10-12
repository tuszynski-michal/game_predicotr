---
title: Natywne kontrole i zgodność trwałych projektów
status: done
last_updated: 2026-10-12
---

# TASK-0980 — Natywne kontrole i zgodność trwałych projektów

## Status

`done`

## Goal

Usunąć koszt startu procesów przy interakcjach bez osłabienia kontroli plików i trwałości.

## Context

Audyt operatora2026-10-12 ma REVISE. Operator zaakceptował dodatkową rundę
2–4 h z testami i nowym ZIP-em. Projekt/result pozostają lokalne, bez sieci.

## Dependencies / entry conditions

Plan OFFLINE_PHOTO_SELECTOR_AUDIT_REMEDIATION_PLAN_20261012.md zaakceptowany
poleceniem pełnej rundy.0980/0981: baza v1.7.323; ownership rozłączny,
commity w kolejności0980→0981.0982: po obu commitach, nie w trakcie ich zmian.
Oryginalny raport jest inputem operatora i nie jest edytowany.

## Recommended execution

`gpt-6.1-sol / high`, zgodnie z końcową tabelą planu. Model/effort dostępne.
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

- Jeden kontrolowany hidden Windows checks worker z typed JSONL, ID, limitami, timeout i shutdown.
- Świeże DriveInfo/reparse/processIdentity, bez stale cache i pomijania kontroli preview.
- Jeden zweryfikowany indeks źródła przekazany controllerowi; bez drugiego skanu.
- Close po LOCK_LOST bez unlink cudzej blokady; controller zwalnia zamknięty store.
- Powrót do skipped zakresu zgodnie z Reviewerem; accepted pozostają chronione.
- Jawne ograniczenia rosnącego stanu/receiptów i pełnych SHA, bez nowego protokołu kursora.

## Out of scope

Admin/Reviewer/API/OpenAPI/baza, usługi operatora, upload/linki/Proton,
benchmarki/duże korpusy, podpis, push/merge i fizyczny odbiór0979. Bez
resetowania błędnego projektu, usuwania obcych danych lub ślepego cache proof.

## Acceptance criteria

- [x] Ciepłe kontrole nie uruchamiają nowego PowerShell dla każdego JPEG/klawisza; mierzone na małym fixture.
- [x] Podmiana reparse/plików po indeksowaniu nadal blokuje preview i zapis.
- [x] Awaria, błędna odpowiedź, timeout i shutdown workera nie dają pozornego sukcesu ani osieroconego procesu.
- [x] Open wykonuje pojedynczy scan source, a SHA zaakceptowanego output pozostaje obowiązkowe.
- [x] Utrata locka pozwala close po zakończeniu szeregu; cudza blokada i dziennik pozostają nietknięte.
- [x] Skipped→korekta zakresu→accepted działa; accepted konflikt i powtórny source nadal blokowane.
- [x] Stare ProjectState1 oraz journal1/2, retry i przerwania procesu przechodzą regresję.

## Technical notes

Reguły kontraktu, walidacji i błędów opisuje zaakceptowany plan. Nie
zmieniamy ProjectState1/journal1/2 tylko dla samej optymalizacji. Dziennik,
backup, idempotencja oraz SHA przed zmianą JPEG pozostają. Kontrole nie mogą
być pozornie zielone wskutek pominięcia atrybutów lub skrócenia testów.
Worker wykonuje wyłącznie inspekcje, nie zapis danych. Każde polecenie ma
ograniczony czas, rozmiar oraz kontrolowany lifecycle. Dokładny źródłowy
raport audytu zostaje zachowany; nowe wyniki są osobnym dowodem poprawek.

## Expected files

Istniejące: native/path-security.ts (assertWindowsReparse), filesystem/local-storage.ts
(assertLocalStorage/powershellJson), native/source-registry.ts (register/openImage),
project/project-lock.ts (nativeProcesses/ProjectLock), project/project-store.ts
(ProjectStore/inventoryFor), project/state-codec.ts (walidacja), cały
native/project-controller.ts (refreshSource/closeInternal), test/project*.mjs i legacy*.
Nowe proponowane: native/windows-check-worker.ts i test natywnych kontroli.
Backend jest właścicielem powyższych plików. Nie edytuje main.ts/App/preferences/IPC.
Package scripts nowego testu tylko po uzgodnieniu z leadem.

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
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:native --workspace @game-predictor/selector-desktop
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

Jeden kontrolowany WindowsCheckWorker obsługuje świeże DriveInfo, reparse i
process identity. Typed JSONL, FIFO64, limity wejścia256KiB/wyjścia16KiB,
deadline obejmujący kolejkę, fail-closed błędnego protokołu i kontrolowany
shutdown. Żądania nie interpolują ścieżek do kodu PowerShell.

ProjectStore przekazuje faktyczny zweryfikowany scan z ułamkowym mtime do
SourceRegistry; open nie skanuje ponownie. SHA wszystkich zatwierdzonych
JPEG-ów nadal obowiązkowe. Close po LOCK_LOST nie usuwa cudzej blokady.
Skipped zakres można później wybrać; konflikt accepted i ponowny source
pozostają blokowane. Brak potwierdzonego JPEG-a blokuje nowe decyzje,
a przywrócenie zgodnego backupu umożliwia resume. REMOVABLE_STORAGE zastępuje
mylący NETWORK_STORAGE dla lokalnego nośnika wymiennego.

### Verification results

124 unikalne testy backendu PASS: native15, projekt48, legacy25,
legacy recovery26, przerwania prawdziwego procesu3, foundation7.
Każda grupa miała rzeczywisty timeout120s. Projekt48/48 trwał24,1s.
Mały funkcjonalny fixture3JPEG: ciepły NAV88ms, preview15ms, accept133ms;
liczba startów PowerShell nie rosła przy kolejnych operacjach. Jest to
ograniczony dowód usunięcia narzutu startu, nie benchmark dużych partii.
Testy obejmują crash/błędnyID/JSON/timeout/kolejkę/shutdown, reparse po scan,
pojedynczy scan, niezmienione obce lock bytes, skipped konflikt, missing
JPEG→odmowa skip/accept→nowy proces→zła kopia→poprawna kopia→resume.
Lint/typecheck i format zmienionych modułów PASS. docs:check oraz
code-map:check i git diff --check PASS przy zamykaniu taska.

Komendy: test:native, test:foundation, test:project, test:legacy,
test:legacy-recovery, test:legacy-process przez run-bounded120;
lint/typecheck przez run-bounded45. Mapy zregenerowane po dodaniu worker API.

### Not completed

Końcowy audyt wykonuje operator po rundzie, zgodnie z jego instrukcją;
nie uruchomiono CLI audytu i nie zastąpiono Claude modelem Codex.
Oryginalny raport REVISE pozostaje niezmieniony. Pełna historia receiptów,
NAV journal i O(inventory+historia) koszt pozostają świadomym ograniczeniem.
Pełne SHA przy open mogą długo trwać dla dużego wyniku. Pusty recovery guard
bez owner proof pozostaje fail-closed z diagnostyką; USB nie jest obsługiwany.
Nie wykonano benchmarku, danych operatora, usług, push ani merge.
Fizyczny odbiór0979 pozostaje blocked. Realne okno i ZIP należą do0981/0982.

### Documentation updates

Zaakceptowany plan/taski0980–0982, D-545, wymagania i architektura,
mapy, TRACEABILITY, rejestr oraz dowody poprawek. Instrukcja odtwarzania
JPEG-a zostanie ukończona w0981. Wejściowy audyt zachowany bajtowo.
Commit implementacji: v1.7.324 / a5ae96049de1fb48a216d7ebaaf895a24cc1e6e1.

### Recommended next task

TASK-0981, następnie0982; końcowy audyt i fizyczny odbiór operatora.
