---
title: TASK-0486 — Jawne uruchamianie preflightu geometrii
status: done
last_updated: 2026-09-06
---

# TASK-0486 — Jawne uruchamianie preflightu geometrii

## Goal

Otwarcie raportu lub zakończenie uploadu nie może samo utworzyć joba geometrii;
kosztowny preflight uruchamia wyłącznie jawna akcja operatora.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`

## Scope

- rozdzielić odczyt raportu od komendy tworzącej preflight geometrii;
- zastosować tę samą zasadę po nowym uploadzie i po wznowieniu stagingu;
- zachować idempotentny przycisk `Przygotuj geometrię stron`;
- wyjaśnić w UI, że lista stagingów zawiera tylko fizyczne kopie gotowe do
  wznowienia, a nie historię zakończonych importów;
- dodać test regresyjny kontraktu panelu.

## Out of scope

- zatrzymywanie aktywnych jobów;
- usuwanie użytego stagingu lub wyników importu;
- zmiana retencji 24 godzin, API, OpenAPI lub PostgreSQL.

## Acceptance criteria

- [x] `Pokaż raport` wykonuje tylko preview;
- [x] zakończenie uploadu wykonuje tylko preview;
- [x] preflight rozpoczyna się dopiero po jawnym kliknięciu;
- [x] istniejący identyczny preflight jest nadal przywracany idempotentnie;
- [x] aktywny lub użyty staging pozostaje chroniony przed akcją przeznaczoną
      dla nieużywanych danych.

## Expected files

- `apps/admin/src/features/imports/image-folder-import-panel.tsx`
- `apps/admin/test/image-folder-import-panel-contract.test.mjs`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
node --test apps/admin/test/image-folder-import-panel-contract.test.mjs apps/admin/test/image-folder-import-actions.test.mjs
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run admin:build
```

## Outcome

### Changed

- Upload i `Pokaż raport` kończą się na odczycie raportu oraz wyzerowaniu
  lokalnego uchwytu joba geometrii.
- `Przygotuj geometrię stron` pozostaje jedyną komendą startu i przywraca
  identyczny istniejący job przez dotychczasową idempotencję API.
- Panel wyjaśnia różnicę między fizycznym stagingiem gotowym do wznowienia a
  historią importów w zakładce Joby.

### Verification results

- 24 testy kontraktu panelu i akcji importu — zielone.
- ESLint, TypeScript, Prettier i produkcyjny build Admina — zielone.
- Odczytowa kontrola danych potwierdziła, że `6b9de344…` ma aktywny preflight
  `c4b9edf7…` oraz import `745b94c5…` z wynikami, więc nie jest nieużywany.

### Not completed

- Nie przerwano aktywnego joba i nie usunięto stagingu ani wyników importu.
  Zasób pozostaje chroniony do zakończenia zależności i kwalifikacji przez GC.

### Documentation updates

- Zaktualizowano wymagania Admina, ingestion oraz `CURRENT_STATE.md`.

### Recommended next task

- Jeśli potrzebne jest natychmiastowe usuwanie wyłącznie roboczej kopii
  stagingu po zakończonym imporcie, zaprojektować osobną, checksum-bound akcję
  weryfikującą komplet managed originals; nie rozszerzać semantyki przycisku
  `Usuń nieużywany staging`.
