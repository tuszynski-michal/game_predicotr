---
title: TASK-0444 — Bezpieczniejsze górne cięcie i większe miniatury
status: done
---

# TASK-0444 — Bezpieczniejsze górne cięcie i większe miniatury

## Status

`done`

## Goal

Automatyczny crop wybranych zdjęć zachowuje większy margines nad planszami,
nie zaczyna się od błędnego `topY = 0`, a przegląd pokazuje większe miniatury w
jednym poziomym rzędzie.

## Context

Dolna granica jest poprawna, lecz górna bywa zbyt niska. Fałszywy klaster przy
górnej krawędzi potrafi dodatkowo rozciągnąć crop od początku zdjęcia, co
utrudnia późniejszą detekcję plansz. Miniatury 120×80 px są zbyt małe do
szybkiej oceny.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Zwiększyć górny padding detektora z 4,5% do 7,5% wysokości, pozostawiając
  dolny padding 4,5%.
- Odrzucić klaster, którego padding doprowadziłby do `topY = 0`, i zwrócić
  bezpieczny pas domyślny.
- Powiększyć atlasowe miniatury do 144×96 px i zmienić wersję renderera cache.
- Pokazać miniatury w jednym poziomym, przewijanym rzędzie.

## Out of scope

- Zmiana już zapisanych JPEG-ów lub automatyczne przeliczanie istniejących
  manifestów.
- Zmiana dolnej granicy, jakości finalnego JPEG-a albo geometrii plansz.

## Acceptance criteria

- [x] Górna granica ma dodatkowy margines 3% wysokości źródła.
- [x] Kandydat prowadzący do początku obrazu wraca jako `safe_default` i nigdy
      nie emituje `topY = 0`.
- [x] Dolny padding pozostaje bez zmian.
- [x] Miniatury mają 144×96 px, nową tożsamość cache i nie zawijają się.
- [x] Testy, lint, typecheck i build właściwych workspace'ów przechodzą.

## Technical notes

Wartości są proporcjami, aby zachować spójne kadrowanie dla wysokości 1280 i
1920 px. Zmiana wymaga nowej wersji polityki detekcji oraz renderera atlasu.

## Expected files

- `packages/manual-image-selection-core/src/auto-crop.ts`
- `packages/manual-image-selection-core/test/selected-image-auto-crop.test.mjs`
- `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-atlases.ts`
- `apps/admin/src/app/globals.css`
- `apps/admin/test/selected-image-crop-atlas-contract.test.mjs`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run test --workspace @game-predictor/manual-image-selection-core
npm run typecheck --workspace @game-predictor/manual-image-selection-core
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
```

## Risks / open questions

- Istniejące zaakceptowane cropy pozostają niezmienne i wymagają jawnej
  korekty albo nowej sesji, jeżeli operator chce zastosować nową politykę.

## Outcome

Wypełnia agent po pracy.

### Changed

- Wprowadzono asymetryczny padding auto-cropa 7,5% u góry i 4,5% u dołu.
- Klaster prowadzący do `topY = 0` przechodzi na jawny `safe_default`.
- Powiększono miniatury do 144×96 px, zaktualizowano renderer atlasu do v2 i
  ułożono kafelki w jednym przewijanym poziomym pasku.
- Dodano testy regresyjne detekcji krawędziowej, wymiarów cache i układu CSS.

### Verification results

- `npm run test --workspace @game-predictor/manual-image-selection-core` — 39
  testów, 39 passed.
- `npm run typecheck --workspace @game-predictor/manual-image-selection-core` —
  passed.
- `npm run test --workspace @game-predictor/admin` — 396 testów, 396 passed.
- `npm run lint --workspace @game-predictor/admin` — passed.
- `npm run typecheck --workspace @game-predictor/admin` — passed.
- `npm run build --workspace @game-predictor/admin` — passed.

### Not completed

- Nie przeliczano ani nie nadpisywano istniejących cropów i manifestów.

### Documentation updates

- Zaktualizowano wymagania, architekturę, D-334 i `CURRENT_STATE.md`.

### Recommended next task

- Wykonać operatorski smoke test na kilku nowych, jeszcze nieprzygotowanych
  zdjęciach przed użyciem całego katalogu.
