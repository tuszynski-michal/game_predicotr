---
title: TASK-0631 — Sekcja „Brakujące plansze” i zwinięty blok akcji w Adminie
status: todo
last_updated: 2026-09-24
---

# TASK-0631 — Sekcja „Brakujące plansze” i zwinięty blok akcji w Adminie

## Status

`todo`

## Goal

Sekcja „Brakujące plansze” zastępuje kartę kompletności i historię importów w
„Import plansz”. Wszystkie akcje ponownego przetwarzania pozostają dostępne w
zwiniętym bloku.

## Context

Ostatni z trzech tasków planu „sekcja Brakujące plansze”
(`ai_docs/tasks/completed/0629-board-import-coverage-definition.md`,
`ai_docs/tasks/0630-board-import-coverage-endpoint.md`). Użytkownik
(decyzje DU-1..DU-3, 2026-09-24) chce widzieć braki względem pełnego
oczekiwanego zakresu numerów zamiast tylko zatwierdzonych plansz, bez utraty
istniejących akcji reprocess.

## Dependencies / entry conditions

- `TASK-0630` musi być `done`: endpoint i wrapper klienta `getBoardImportCoverage`
  muszą istnieć.

## Recommended execution

claude-sonnet-5, reasoning high. Uzasadnienie: duży plik panelu, ochrona
istniejących akcji reprocess, polling z guardem wyścigu i 7 stanów UI.
Dodatkowy review: tak — claude-opus-5-5, medium (kontrola, że żadna akcja nie
zniknęła i polling się wyłącza).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/tasks/completed/0629-board-import-coverage-definition.md`
- `ai_docs/tasks/0630-board-import-coverage-endpoint.md`

## Scope

- Nowy `apps/admin/src/features/imports/missing-boards-section.tsx`: własny
  stan (widok Brakujące/Dodane, zakres/wyszukiwanie, kursor, dane, błąd).
- Nowy czysty moduł `apps/admin/src/features/imports/missing-boards-state.ts`:
  `parseSequenceRangeQuery`, `formatSegmentRange` (`toLocaleString('pl-PL')`),
  `missingReasonLabel`, `summaryState` (loading / error / unknown-target /
  empty / all-added / no-results / list).
- `apps/admin/src/features/imports/image-folder-import-panel.tsx`:
  - usunąć kartę „Kompletność zaakceptowanych plansz” (linie ok. 2176–2223)
    i stan/pobieranie `completeness` w `refreshJobs`;
  - w miejscu `importHistorySection` wstawić `<MissingBoardsSection>` oraz
    `<details>` „Ponowne przetwarzanie importów” (domyślnie zwinięte) z listą
    5 ostatnich jobów, `ImportGeometryReviewSummary` i trzema przyciskami
    („Przetwórz ponownie z oryginałów”, „Przetwórz w v1.0”, „Kontynuuj z
    ręczną korektą”) — warunki widoczności i handlery bez zmian; usunąć tylko
    linie diagnostyczne (silnik, manifest, guard, profil, model, outcome);
  - przekazać `refreshToken` (rośnie przy każdym `refreshJobs`) do sekcji.
- Odświeżanie: montowanie, `refreshToken`, zmiana filtra/zakresu; polling
  15 s tylko gdy `notices.activeImportJobCount > 0`, z `clearInterval` przy 0
  lub unmount; guard kolejności odpowiedzi (id żądania).
- Style: dopisać do istniejącego globalnego CSS obok `.importCompletenessCard`
  i `.importMetrics`, reużywając klas; jedna kolumna przy ~600 px.
- `image-folder-import-actions.ts`: dodać `getBoardImportCoverage` do
  `ImageFolderImportClient`; usunąć `getImageDatasetCompleteness` z typu
  panelu tylko jeśli grep potwierdzi brak innych konsumentów w admin.
- Aktualizacja `ai_docs/requirements/ADMIN_APP.md` (zachowanie sekcji,
  definicja, powody, stany).

## Out of scope

- Zmiana definicji lub endpointu (`TASK-0629`, `TASK-0630` zamknięte przed
  startem).
- Kopiowanie zakresów do schowka, linki z segmentu do joba/Reviewera, podział
  widoku „Dodane” na zatwierdzone/oczekujące, przeniesienie akcji reprocess do
  zakładki Joby — poza MVP.

## Chronione zachowanie

Warunki i handlery `reprocessImport`, `reprocessManagedV4`,
`reprocessImport(job, true)` oraz `ImportGeometryReviewSummary` — bez zmian
logiki, tylko przeniesienie do `<details>`.

## Acceptance criteria

- [ ] Karta „Kompletność zaakceptowanych plansz” i sekcja „Ostatnie importy
      tej gry” (stara treść) znikają z panelu.
- [ ] `<MissingBoardsSection>` pokazuje liczniki, powody, filtr
      Brakujące/Dodane (bez „Wszystkie”), wyszukiwanie zakresu, segmenty,
      stronicowanie i 7 stanów ekranu z treści planu.
- [ ] `<details>` „Ponowne przetwarzanie importów” zawiera 5 ostatnich jobów i
      trzy przyciski akcji, domyślnie zwinięte.
- [ ] Polling działa tylko przy aktywnym imporcie i wyłącza się poprawnie.
- [ ] Żadna istniejąca akcja reprocess nie zmienia zachowania (test
      regresyjny).

## Test cases

- `missing-boards-state.test.mjs`:
  - parser zakresu: `"12"`, `"10-20"`, `"10–20"`, `" 5 - 7 "`;
  - błędy: `0`, `b<a`, `>E`, tekst;
  - etykiety wszystkich 7 powodów;
  - `summaryState` dla 7 stanów ekranu.
- `image-folder-import-panel-contract.test.mjs` (aktualizacja):
  - brak „Ostatnie importy tej gry” i starej karty kompletności;
  - obecność `<MissingBoardsSection`;
  - `<details` z trzema etykietami przycisków;
  - polling warunkowy (`activeImportJobCount`).
- `image-folder-import-actions.test.mjs`: test regresyjny istniejących akcji
  reprocess (bez zmian asercji).

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
```

Ręcznie przez `admin:dev` i `api:dev` jako procesy w tle: filtr, zakres,
stronicowanie, pusty wynik, rozwijanie bloku akcji, „Odśwież status”. Jeśli
nie uda się sprawdzić na żywych danych, zaraportować to jawnie.

## Risks / open questions

- Duży plik `image-folder-import-panel.tsx` — wysokie ryzyko przypadkowego
  usunięcia nieużywanego, ale wciąż importowanego kodu; stąd wymagany
  dodatkowy review.

## Outcome

Wypełnia agent po pracy.
