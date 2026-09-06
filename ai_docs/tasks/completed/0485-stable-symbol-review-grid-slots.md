---
title: TASK-0485 — Stabilne miejsca kafli Weryfikacji symboli
status: done
last_updated: 2026-09-06
---

# TASK-0485 — Stabilne miejsca kafli Weryfikacji symboli

## Goal

Zachować zamontowane podglądy wszystkich niezmienionych cropów podczas lokalnego
ukrywania zakończonej decyzji, bez ponownego układania wirtualizowanej siatki.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/tasks/completed/0484-retain-active-symbol-review-previews.md`

## Scope

- przekazywać do wirtualizatora niezmienny snapshot aktywnej strony;
- po sukcesie zastąpić wyłącznie dokładny target pustym miejscem o tym samym
  rozmiarze;
- zachować pozycje, klucze React i elementy atlasów pozostałych kart;
- pozostawić wybór oraz operacje ograniczone do nieukrytych kart;
- dodać test regresyjny kontraktu UI.

## Out of scope

- zmiana API, atlasów serwerowych, PostgreSQL lub semantyki decyzji;
- przechowywanie podglądów innych stron;
- uzupełnianie strony nowymi rekordami po decyzji.

## Acceptance criteria

- [x] sukces jednej lub wielu decyzji nie przesuwa pozostałych kart;
- [x] pozostałe podglądy zachowują ten sam element DOM i nie wracają do
      placeholdera ładowania;
- [x] ukryty target nie może zostać ponownie wybrany ani wysłany;
- [x] zmiana strony, filtra albo gry nadal czyści pamięciową mapę tile.

## Expected files

- `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`
- `apps/admin/src/features/symbol-reviews/symbol-review-workspace.module.css`
- `apps/admin/test/symbol-review-workspace-contract.test.mjs`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
node --test apps/admin/test/symbol-review-workspace-contract.test.mjs apps/admin/test/symbol-review-preview-atlases.test.mjs apps/admin/test/symbol-review-virtual-window.test.mjs
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run admin:build
```

## Outcome

### Changed

- Wirtualizator otrzymuje stały snapshot `currentPage.items`, niezależny od
  lokalnej listy targetów zakończonych decyzji.
- Zakończony target jest zastępowany niewidocznym slotem 100 × 100 px. Inne
  karty zachowują pozycje, klucze React i zamontowany element atlasu.
- Zaznaczanie strony i tworzenie operacji nadal używa listy pomniejszonej o
  ukryte targety.

### Verification results

- 18 testów workspace'u, atlasów i wirtualnego okna — zielone.
- ESLint i TypeScript Admina — zielone.
- Prettier dla zmienionych plików — zielony.
- Produkcyjny build Admina — zielony.

### Not completed

- Nie zmieniano API, serwerowego cache'u atlasów ani danych.

### Documentation updates

- Doprecyzowano kontrakt stabilnego slotu w `ADMIN_APP.md` i bieżący stan.

### Recommended next task

- Brak wymaganego kolejnego taska; zachowanie można odebrać na działającym
  ekranie przez serię pojedynczych i masowych decyzji.
