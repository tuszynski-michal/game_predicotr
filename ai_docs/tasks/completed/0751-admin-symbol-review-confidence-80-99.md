---
title: TASK-0751 — Admin: przedział pewności 80–<99% w weryfikacji symboli
status: done
last_updated: 2026-09-30
---

# TASK-0751 — Admin: przedział pewności 80–<99% w weryfikacji symboli

## Status

`done`

## Goal

Operator filtruje w `Weryfikacja symboli` komórki z pewnością rozpoznania od
80% do poniżej 99%, bez ok. 6 mln komórek z pewnością ≥ 99%.

## Context

TASK-0750 przepuszcza przez bibliotekę wzorców pasmo 80–99% (335 tys.
komórek). Komórki bez pewnej propozycji zostają przy predykcji modelu, a
istniejący przedział „80–<100%” miesza je z komórkami ≥ 99%. Polecenie
operatora 2026-09-30: dodać przedział 80–<99% (bez źródła „Do przeglądu”).

## Dependencies / entry conditions

- API przyjmuje dowolne `minConfidence` / `maxConfidence` (bez zmian).

## Recommended execution

`claude-opus-5-5`, reasoning `medium` (warunkowo). Audyt: `claude-opus-5-5`,
osobny agent.

## Relevant docs

- `ai_docs/process/DECISION_LOG.md` (D-466)
- `ai_docs/tasks/completed/0746-admin-symbol-review-source-and-change-filters.md`

## Scope

- `symbol-review-state.ts`: wartość `from_80_to_99` →
  `minConfidence 0.8`, `maxConfidence 0.99 − ε/2`.
- `symbol-review-workspace.tsx`: opcja „80–<99%” w grupie „Pewność
  rozpoznania”.
- Test mapowania zakresu.

## Out of scope

- Źródło „Do przeglądu”, zmiany API.

## Acceptance criteria

- [x] Opcja „80–<99%” obok „80–<100%”; zakres nie obejmuje 0,99, więc
  predykcje biblioteki (0,99) i komórki ≥ 99% są poza nim.
- [x] Pozostałe przedziały bez zmian.
- [x] Typecheck, testy, ESLint, Prettier; audyt bez P0–P2.

## Technical notes

- Przedział nakłada się z „80–<100%” celowo (opcja węższa).

## Test cases

- `apps/admin/test/symbol-review-state.test.mjs`: mapowanie `from_80_to_99`.

## Outcome

- Opcja „80–<99%” (`from_80_to_99`: `minConfidence 0.8`,
  `maxConfidence 0.9899999999999999`) obok „80–<100%”; 6 opcji w dwóch
  wierszach. API bez zmian (`>= min`, `<= max`, `double precision`).
- Weryfikacja: `tsc --noEmit`, 620 testów Admina, ESLint, Prettier.
- Audyt `claude-opus-5-5`: PASS. Odczyt bazy: 92 458 oczekujących komórek z
  pewnością dokładnie 0,99 i wszystkie komórki biblioteki są poza przedziałem.
  P3 wdrożone: literał granicy w teście. P3 informacyjne: ok. 200 komórek
  biblioteki ma pewność ≥ 0,99, ale ≠ 0,99 — do wyjaśnienia przy TASK-0750.
