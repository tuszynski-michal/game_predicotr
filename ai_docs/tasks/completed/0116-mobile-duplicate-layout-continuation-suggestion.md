---
title: Mobile duplicate layout continuation suggestion
status: done
last_updated: 2026-07-30
---

# TASK-0116 — Mobile duplicate layout continuation suggestion

## Status

`done`

## Goal

Podpowiadać pełny layout, gdy wszystkie pozostałe dopasowania prefiksu są
duplikatami jednej sygnatury, bez wybierania pozycji sekwencji ani uruchamiania
Target.

## Context

Obecny modal otwiera się wyłącznie dla jednego rekordu. Kilka rekordów może
jednak przedstawiać identyczny layout; wtedy treść brakujących symboli jest
jednoznaczna, choć pozycja sekwencji nadal nie jest.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/DATA_MODEL.md`
- D-008 i D-094 w `ai_docs/process/DECISION_LOG.md`

## Scope

- rozszerzyć bounded prefix lookup o liczbę rekordów i distinct pełnych
  sygnatur,
- zwrócić jedną pełną planszę tylko wtedy, gdy distinct signature count wynosi
  dokładnie `1`,
- pokazać modal wariantu `duplicate suggestion`,
- zaakceptować uzupełnienie jako jeden krok Undo,
- po exact match zachować wynik `duplicate`, numery wystąpień i brak Target.

## Out of scope

- arbitralny wybór pierwszego `sequence_number`,
- confirmation chain między kolejnymi layoutami,
- zmiana danych snapshotu albo reguł Target.

## Acceptance criteria

- [x] dwa lub więcej rekordów jednej sygnatury podpowiada wspólny layout,
- [x] kilka różnych sygnatur nie otwiera modala,
- [x] modal duplikatu nie przedstawia jednej pozycji jako rozstrzygniętej,
- [x] akceptacja jest jednym krokiem Undo,
- [x] exact pozostaje `duplicate` i nie uruchamia Target,
- [x] Reset i odrzucenie propozycji czyszczą kontekst zgodnie z istniejącą
  procedurą,
- [x] testy obejmują duplikat jednej sygnatury, wiele sygnatur, unique i stale
  async result.

## Expected files

- `apps/mobile/src/data/local-layout-repository.ts`
- `apps/mobile/src/features/board/use-prefix-matching.ts`
- `apps/mobile/src/features/board/candidate-layout-modal.tsx`
- `apps/mobile/__tests__/`

## Verification

```powershell
npm run typecheck --workspace @game-predictor/mobile
npm run test --workspace @game-predictor/mobile
```

## Risks / open questions

- Odpowiedź repozytorium musi pozostać bounded dla 500 000 layoutów.

## Outcome

- Repozytorium zwraca jawny wariant podpowiedzi `unique` albo `duplicate`.
  Wariant duplikatu zawiera wspólne komórki i liczbę wystąpień, ale ma
  `sequenceNumber = null`.
- Wyszukiwanie wykonuje dokładny indeksowany count, a dla kilku rekordów
  pobiera najwyżej dwie różne sygnatury. `EXPLAIN QUERY PLAN` na dołączonym
  snapshotcie potwierdził covering index
  `idx_layouts_game_signature`.
- Modal rozróżnia pojedynczą pozycję od grupy duplikatów i jawnie informuje,
  że pozycja pozostaje nierozstrzygnięta oraz Target nie zostanie uruchomiony.
- Akceptacja nadal używa jednej operacji `complete_board`; test przepływu
  potwierdza jeden Undo, wynik exact `duplicate` i brak odczytu payoutów.
- Weryfikacja: 67/67 testów mobile, TypeScript strict, ESLint zmienionych
  plików i Prettier przeszły. Ręczny smoke na Pixelu został świadomie odłożony
  przez właściciela do późniejszej sesji testowej.
