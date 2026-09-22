---
title: Retry cancelled browser page-geometry preflight
status: done
---

# TASK-0614 — Ponowienie anulowanego preflightu geometrii

## Status

`done`

## Goal

Przycisk preflightu dla kompletnego browser stagingu ponawia anulowany job
geometrii, zamiast wyłącznie odświeżać jego terminalny status.

## Context

Backend retry dla `page_geometry_preflight` już bezpiecznie przywraca job
`cancelled` do `created` z wyczyszczonym postępem. Admin rozpoznawał dotąd
jako retry tylko `failed`, przez co anulowany job pozostawał widoczny i blokował
ponowne uruchomienie bez wpływu na staging.

## Recommended execution

gpt-5.6-terra / high; końcowy review gpt-6-astra / medium. Zakres jest
ograniczony do istniejącego kontraktu retry i nie wymaga zmiany API.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`

## Scope

- Ujednolicić w Adminie statusy retry preflightu: `failed` i `cancelled`.
- Zachować istniejące wywołanie `retryJob`, bez tworzenia nowego stagingu,
  uploadu ani joba importu.
- Dodać regresję dla anulowanego statusu.

## Out of scope

- Zmiany backendowego lifecycle jobów, stagingu, geometrii V1.1/V1.2 i V2.
- Zmiana danych lub ponowne przetwarzanie istniejących stagingów.

## Acceptance criteria

- [x] `cancelled` uruchamia tę samą bezpieczną ścieżkę retry co `failed`.
- [x] UI komunikuje „Ponów preflight” dla obu statusów.
- [x] Stan aktywny i ukończony nie jest ponawiany.
- [x] Test regresji obejmuje anulowany preflight.

## Expected files

- `apps/admin/src/features/imports/image-folder-import-actions.ts`
- `apps/admin/src/features/imports/image-folder-import-panel.tsx`
- `apps/admin/test/image-folder-import-actions.test.mjs`
- `apps/admin/test/image-folder-import-panel-contract.test.mjs`

## Outcome

### Zmiana

Wspólna funkcja `canRetryPageGeometryPreflight` uznaje wyłącznie terminalne
statusy `failed` i `cancelled` za ponawialne. Panel oraz ścieżka managed
reprocess wywołują dla nich istniejące `retryJob`, dlatego zachowują ten sam
job i zatwierdzony staging. Nie tworzą stagingu, nie usuwają plików i nie
uruchamiają importu.

### Weryfikacja

- `node --experimental-strip-types --test test/image-folder-import-actions.test.mjs test/image-folder-import-panel-contract.test.mjs` — 46 testów przeszło.
- `npm run typecheck` — przeszło.
- `npx eslint src/features/imports/image-folder-import-actions.ts src/features/imports/image-folder-import-panel.tsx` — bez błędów; pozostaje istniejące ostrzeżenie `next/no-img-element` w dużym panelu.
- Audyt Astra Medium nie znalazł problemów P0–P3. Po audycie dodano wyłącznie regresyjne asercje dla statusów `created` i `completed`, bez zmiany logiki.

### Ograniczenia

Nie wykonywano ręcznego ponowienia joba na danych stagingu. Weryfikacja
kontraktu obejmuje wywołanie istniejącego retry i wykluczenie statusów
aktywnych oraz ukończonych.

### Następny krok

W Adminie odświeżyć widok stagingu `a139379b` i użyć `Ponów preflight`.
Anulowany job zostanie ponowiony bez tworzenia nowego stagingu.
