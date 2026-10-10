---
title: TASK-0706 — Domyślna zakładka niepełnych siatek
status: done
---

# TASK-0706 — Domyślna zakładka niepełnych siatek

## Status

`in_progress`

## Goal

Lokalny Reviewer po wejściu do importu otwiera „Niepełne siatki do ręcznej korekty”, gdy kolejka zawiera co najmniej jedną pozycję.

## Context

`LocalReviewerWorkspace` domyślnie wybierał „Walidację gotowych siatek”, gdy oba widoki miały pozycje. Użytkownik wskazał, że priorytetem wejścia jest ręczna korekta niepełnych siatek.

## Dependencies / entry conditions

- Zmiana dotyczy wyłącznie lokalnego przełącznika dwóch zakładek geometrii.

## Recommended execution

`gpt-6-sol`, reasoning `high`. Mała, deterministyczna zmiana priorytetu z testem wszystkich kombinacji liczników.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`

## Scope

- Gdy `deferredGeometryCount > 0`, otwierać tryb `deferred` niezależnie od liczby gotowych siatek.
- Gdy kolejka niepełnych siatek jest pusta, zachować wejście do `grid`.

## Out of scope

- Zmiany mechaniki korekty, API, danych i pozostałych filtrów.

## Acceptance criteria

- [ ] Import z gotowymi i niepełnymi siatkami otwiera drugą zakładkę.
- [ ] Import bez niepełnych siatek otwiera walidację gotowych siatek.
- [ ] Test jednostkowy obejmuje oba przypadki.

## Technical notes

Jedynym właścicielem decyzji startowej jest `initialLocalReviewerWorkspaceMode`; nie kodować wyjątku URL ani nie zmieniać ręcznego przełączania zakładek.

## Expected files

- `apps/reviewer/src/features/access/local-reviewer-workspace-state.ts`
- `apps/reviewer/test/local-reviewer-workspace-state.test.mjs`

## Test cases

- `(9, 158) → deferred`, `(0, 1) → deferred`, `(9, 0) → grid`, `(0, 0) → grid`.

## Verification

```powershell
pnpm --filter @game-predictor/reviewer test
pnpm dlx prettier@3.5.3 --check apps/reviewer/src/features/access/local-reviewer-workspace-state.ts apps/reviewer/test/local-reviewer-workspace-state.test.mjs
git diff --check
```

## Risks / open questions

- Brak: przełącznik pozostaje dostępny ręcznie po wejściu.

## Outcome

### Changed

- `initialLocalReviewerWorkspaceMode` wybiera teraz `deferred` zawsze, gdy
  lokalna kolejka niepełnych siatek ma co najmniej jedną pozycję.
- Ręczne przełączanie zakładek i fallback do walidacji gotowych siatek przy
  pustej kolejce niepełnej pozostały bez zmian.

### Verification results

- `pnpm --filter @game-predictor/reviewer test` — 203/203 zaliczone.
- `pnpm dlx prettier@3.5.3 --check ...` oraz `git diff --check` — zielone.

### Not completed

- Serwer pod `127.0.0.1:3001` podczas pierwszego odbioru nadal serwował
  poprzedni build; po commicie wymaga kontrolowanego przeładowania z bieżącego
  checkoutu przed końcowym odbiorem URL-u.

### Documentation updates

- `ai_docs/process/CURRENT_STATE.md`

### Recommended next task

- Brak.
