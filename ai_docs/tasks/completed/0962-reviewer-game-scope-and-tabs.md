---
title: TASK-0962 — Lokalny Reviewer w zakresie gry, zakładki i tanie liczniki
status: done
last_updated: 2026-10-10
---

# TASK-0962 — Lokalny Reviewer w zakresie gry, zakładki i tanie liczniki

## Status

`done`

## Goal

Lokalny Reviewer (`mode=local&gameId=…`, bez `importJobId`) pokazuje kolejkę
korekty całej gry z tanimi licznikami i ma zakładki „Do korekty” oraz „Braki
zdjęć”.

## Context

Plan: `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`, decyzje 2, 3 i 7.
Dziś `apps/reviewer/src/app/page.tsx` wchodzi w tryb lokalny tylko z
`importJobId` w UUID, a `BoardGeometryCorrectionWorkspace` filtruje kolejkę po
tym imporcie. Operator nie potrzebuje wyboru importu (Mumie ma 165 jobów
typu import). Zakładka „Braki zdjęć” powstaje w TASK-0963; ten task dodaje jej
miejsce (pusty stan) i przełącznik.

## Dependencies / entry conditions

- TASK-0961 zakończony (parametr `counts` w kliencie).
- Zdalny Reviewer (sesja, tunel) nie zmienia się (D-462 P3).

## Recommended execution

`claude-sonnet-5-5`, `medium` — zgodnie z tabelą planu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md` (tylko dla potwierdzenia,
  że zdalna ścieżka nie jest ruszana)

## Scope

1. `apps/reviewer/src/app/page.tsx`: tryb lokalny wymaga `mode=local`,
   loopbackowego hosta i `gameId` w UUID; `importJobId` jest opcjonalny —
   brak albo poprawny UUID. Obecny, nieprawidłowy `importJobId` nie włącza
   trybu lokalnego (jak dziś). Tryby `grid-audit` i `grid-shadow` bez zmian.
2. `ReviewerAccessGate` → `LocalReviewerWorkspace` →
   `BoardGeometryCorrectionWorkspace`: `importJobId` opcjonalny (`string |
   undefined`); gdy brak, `listImageGridReviews` nie dostaje filtra importu.
3. `BoardGeometryCorrectionWorkspace` woła `listImageGridReviews` z
   `counts: 'correction'` i czyta wyłącznie `counts.correction`.
4. `LocalReviewerWorkspace`: dwie zakładki „Do korekty” (domyślna) i „Braki
   zdjęć”; zakładka braków w tym tasku renderuje komponent-zaślepkę z jednym
   zdaniem („Lista braków pojawi się w kolejnym kroku”) i **nie** trafia do
   wydania bez TASK-0963 (zadania etapu A wykonywane razem).
5. Teksty: nagłówek i opis zakładki „Do korekty” bez wzmianki o imporcie.

## Out of scope

- Zawartość zakładki „Braki zdjęć” (TASK-0963).
- Admin (TASK-0964).
- Zmiany polityki proxy zdalnego Reviewera.

## Acceptance criteria

- [x] `/?mode=local&gameId=<uuid>` otwiera lokalny Reviewer bez `importJobId`.
- [x] `/?mode=local&gameId=<uuid>&importJobId=<uuid>` działa jak dotąd.
- [x] `/?mode=local&gameId=<uuid>&importJobId=zly` nie włącza trybu lokalnego.
- [x] Wywołanie `listImageGridReviews` z Reviewera zawiera `counts=correction`
      i nie zawiera `importJobId`, gdy go nie podano.
- [x] Przełączenie zakładek nie gubi stanu edytora zakładki „Do korekty”
      (komponent nie jest odmontowywany ani remontowany bez potrzeby —
      sprawdzić; jeśli remontuje, ukrywać CSS-em).
- [x] `npm run test --workspace @game-predictor/reviewer`,
      `test:geometry`, typecheck i lint zielone.

## Technical notes

`page.tsx` liczy `localMode` z `UUID.test(importJobId)`; zastąp warunkiem
`importJobId === '' || UUID.test(importJobId)`. Do gate'a przekaż
`importJobId` jako `undefined`, gdy puste. `gridValidationEnabled` pozostaje
`localMode`. W `loadPage` (workspace) dodaj `counts: 'correction'` do
wywołania i nie rozpoczynaj spreadu `importJobId`, gdy `undefined` (klient
generowany pomija `undefined`). Test interakcyjny w
`apps/reviewer/test-interactions/board-geometry-correction.test.mjs`
rozszerz o zakres bez importu i o zakładki.

## Expected files

- Istniejące: `apps/reviewer/src/app/page.tsx`,
  `apps/reviewer/src/features/access/reviewer-access-gate.tsx`,
  `apps/reviewer/src/features/access/local-reviewer-workspace.tsx`,
  `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx`,
  `apps/reviewer/test-interactions/board-geometry-correction.test.mjs`.
- Nowe (proponowane): brak (zaślepka zakładki w tym samym pliku
  `local-reviewer-workspace.tsx`).

## Test cases

- Strona: trzy warianty parametrów (powyżej) → odpowiednio lokalny / lokalny /
  bramka kodu dostępu.
- Workspace: żądanie listy bez `importJobId`, z `counts=correction`.
- Zakładki: przełączenie na „Braki zdjęć” i z powrotem zachowuje bieżącą
  planszę.

## Verification

```powershell
# katalog: korzeń worktree; timeout <= 120 s na komendę
npm run test --workspace @game-predictor/reviewer
npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
```

Zaliczenie: wszystkie zielone. Testy planowane nie są wynikami wykonania.

## Risks / open questions

- Zakładka-zaślepka nie może trafić do użytkownika — etap A odbieramy po
  TASK-0963.

## Outcome

### Changed

- `apps/reviewer/src/app/page.tsx`: tryb lokalny wymaga `importJobId === ''` albo UUID; do bramki trafia `importJobId: undefined`, gdy go brak. `grid-audit` i `grid-shadow` bez zmian.
- `reviewer-access-gate.tsx`: `localScope.importJobId` opcjonalny; bez importu zawsze `LocalReviewerWorkspace`. Ścieżka sesji z kodem dostępu bez zmian.
- `local-reviewer-workspace.tsx`: zakładki „Do korekty” (domyślna) i „Braki zdjęć” (zaślepka z jednym zdaniem, do TASK-0963). Oba panele są stale zamontowane, nieaktywny ma `hidden`; edytor nie jest odmontowywany ani przeładowywany.
- `board-geometry-correction-workspace.tsx`: `importJobId` opcjonalny i pomijany w żądaniu, gdy brak; `counts: 'correction'`; teksty bez wzmianki o imporcie; nowy prop `keyboardEnabled`.
- `deferred-board-cell-geometry-editor.tsx`: prop `keyboardEnabled` (domyślnie `true`) wyłącza klawisze symboli w ukrytej zakładce (odstępstwo od opisu taska: bez tego ukryty edytor reagowałby na klawisze z drugiej zakładki).
- `reviewer.css`: style zakładek i `[hidden]` panelu.
- Testy: 3 nowe w `board-geometry-correction.test.mjs` (zakres bez importu, zakładki zachowują ten sam węzeł edytora bez nowych żądań, klawisze nieaktywne w zakładce braków), asercja `counts: 'correction'` w istniejącym teście, dwa testy źródła (`reviewer-access-gate-contract`, `local-reviewer-workspace-contract`).

### Verification results

- `npm run test --workspace @game-predictor/reviewer` — 243/243 PASS.
- `npm run test:geometry --workspace @game-predictor/reviewer` — 53/53 PASS.
- `npm run typecheck --workspace @game-predictor/reviewer` — PASS.
- `npm run lint --workspace @game-predictor/reviewer` — 0 błędów, 1 istniejące ostrzeżenie (`board-search-share-data-source.ts`, poza zakresem).
- `npm run format:check` — PASS.

### Not completed

- Zawartość zakładki „Braki zdjęć” (TASK-0963). Zaślepka nie może trafić do użytkownika bez TASK-0963.
- Brak odbioru na żywo (TASK-0965); brak audytu (zawieszony przez operatora), commit wykonuje orkiestrator.

### Documentation updates

- `ai_docs/process/CURRENT_STATE.md` (okno kroczące; TASK-0944 przeniesiony do `ai_docs/archive/CURRENT_STATE_2026Q4.md`).

### Recommended next task

- TASK-0963

### Audit

Niezależny audyt tylko do odczytu: subagent Claude `haiku` (`medium`), niższy
model niż wykonawca (Codex niedostępny z powodu wyczerpanego limitu;
zastępstwo zgodne z poleceniem operatora z 2026-10-10). Werdykt: PASS z
uwagami P2, brak P0/P1. Uwagi P2 (bez zmian w kodzie, odnotowane):

- trzy warianty parametrów strony są sprawdzane asercjami na źródle, bez testu
  wykonawczego `HomePage` z mockowanymi `searchParams`/`headers`;
- warunek `gridValidationEnabled || localScope.importJobId === undefined` w
  bramce jest zbędny (gałąź `OperationalReviewWorkspace` dla lokalnego zakresu
  była martwa już przed zmianą).
