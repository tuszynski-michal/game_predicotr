---
title: TASK-0387 — Filtr stanu Weryfikacji symboli
status: done
last_updated: 2026-09-02
---

# TASK-0387 — Filtr stanu Weryfikacji symboli

## Goal

Pozwolić operatorowi przełączać listę cropów między wszystkimi,
oczekującymi i zatwierdzonymi bez zmiany kontraktu danych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- radio `Wszystkie / Oczekujące / Zatwierdzone` w Weryfikacji symboli;
- przekazanie istniejącego filtra `state` do strony i liczników;
- reset stron i zaznaczenia zgodny z pozostałymi filtrami.

## Out of scope

- nowy stan domenowy `odrzucone`;
- zmiana ścieżek `Zła siatka` i `Nieczytelny symbol`.

## Acceptance criteria

- [ ] Każda opcja radiowa ładuje wyłącznie właściwy stan review.
- [ ] Zmiana filtra z zaznaczeniem nadal wymaga potwierdzenia.
- [ ] Liczniki i paginacja pozostają związane z bieżącym filtrem.

## Expected files

- `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`
- `apps/admin/test/symbol-review-workspace-contract.test.mjs`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run test --workspace @game-predictor/admin -- symbol-review-workspace-contract.test.mjs
npm run typecheck --workspace @game-predictor/admin
```

## Outcome

### Changed

- Dodano radio `Wszystkie / Oczekujące / Zatwierdzone` pod wyborem gry i zakresu.
- Bounded list page oraz snapshot liczników otrzymują bieżące `filters.state`.
- Nie dodano fałszywego statusu `odrzucone`; problemy jakości pozostają odrębnymi
  ścieżkami korekty.

### Verification results

- `node --experimental-strip-types --test test/symbol-review-workspace-contract.test.mjs` — 8 passed.
- `npm run typecheck --workspace @game-predictor/admin` — passed.
- `npm run lint --workspace @game-predictor/admin` — passed.

### Not completed

- Nie dodano nowej kolejki ani filtra jakościowego dla `Zła siatka`/
  `Nieczytelny symbol`; nie były częścią tego taska.
