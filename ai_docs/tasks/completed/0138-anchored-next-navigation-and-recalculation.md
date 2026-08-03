---
title: TASK-0138 — Anchored Next navigation and recalculation
status: done
last_updated: 2026-08-01
---

# TASK-0138 — Anchored Next navigation and recalculation

## Status

`done`

## Goal

Uruchomić deterministyczne `Next` od jednoznacznej pozycji sekwencji, z
zawijaniem, ponownym obliczeniem Targetu i atomowym cofnięciem przez `Undo`.

## Context

TASK-0135 dodał przycisk jako nieaktywny kontrakt UI. Wersja 0.3 wymaga, aby
aplikacja mogła przejść do dokładnego kolejnego rekordu bez wyprowadzania
pozycji z potencjalnie zduplikowanej sygnatury.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/VERSION_0_3_EXECUTION_PLAN.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- dodać odczyt layoutu po dokładnym `sequence_number` do portu lokalnego SQLite,
- przechowywać jawny anchor pozycji razem ze stanem planszy i historią `Undo`,
- aktywować `Next` wyłącznie dla jednoznacznej pozycji,
- przechodzić do kolejnego rekordu z zawinięciem ostatni → pierwszy,
- traktować layout jawnie załadowany przez `Next` jako znaną pozycję nawet przy
  zduplikowanej sygnaturze,
- ponownie uruchamiać Target dla aktualnego limitu,
- obsłużyć bounded loading, błąd i spóźnioną odpowiedź bez zmiany planszy.

## Out of scope

- zmiana prezentacji podsumowania wyniku z TASK-0139,
- przycisk przewijania do góry z TASK-0140,
- odbiór APK na urządzeniu z TASK-0141,
- dowolna nawigacja do niejednoznacznego duplikatu bez wcześniejszego anchora.

## Acceptance criteria

- [x] `Next` jest nieaktywny dla stanu pustego, częściowego, `duplicate`,
  `not_found` i `local_data_error` bez anchora.
- [x] Od jednoznacznego layoutu ładuje dokładnie `sequence_number + 1`, a po
  ostatnim rekordzie ładuje `1`.
- [x] Zduplikowana sygnatura jawnie załadowanego rekordu zachowuje anchor i
  uruchamia Target od tej pozycji.
- [x] `Undo` cofa całe przejście jako jedną operację i przywraca poprzednią
  planszę oraz jej kontekst pozycji.
- [x] Błąd albo spóźniona odpowiedź odczytu nie nadpisuje bieżącego stanu.
- [x] Testy Mobile, typecheck, lint i format przechodzą.

## Technical notes

- `sequence_number` pozostaje wartością domenową. Następny rekord jest czytany
  po kluczu `(game_id, sequence_number)`, a nie odnajdywany przez sygnaturę.
- Anchor jest częścią snapshotu historii planszy. Matching ręcznego wejścia
  nadal korzysta z dotychczasowego exact matchingu.
- Zmiana nie wymaga migracji: snapshot już gwarantuje gęstą sekwencję
  `1..layout_count`.

## Expected files

- `apps/mobile/src/data/local-layout-repository.ts`
- `apps/mobile/src/features/board/board-reducer.ts`
- `apps/mobile/src/features/board/game-header.tsx`
- `apps/mobile/src/features/board/game-workspace-screen.tsx`
- `apps/mobile/src/features/board/use-exact-matching.ts`
- `apps/mobile/src/features/board/use-next-layout-navigation.ts`
- `apps/mobile/__tests__/board-reducer-test.ts`
- `apps/mobile/__tests__/local-layout-repository-test.ts`
- `apps/mobile/__tests__/next-layout-navigation-test.tsx`
- `ai_docs/delivery/VERSION_0_3_EXECUTION_PLAN.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm.cmd test --workspace @game-predictor/mobile -- --runInBand
npm.cmd run typecheck --workspace @game-predictor/mobile
npm.cmd run lint --workspace @game-predictor/mobile
npm.cmd exec prettier -- --check "apps/mobile/**/*.{ts,tsx}" "ai_docs/tasks/completed/0138-anchored-next-navigation-and-recalculation.md"
```

## Risks / open questions

- Brak pytań blokujących. Przyjęto zaakceptowaną regułę, że jawny odczyt po
  pozycji jest silniejszym dowodem anchora niż wynik exact matchingu sygnatury.

## Outcome

TASK-0138 ukończono 2026-08-01.

### Changed

- Dodano dokładny, walidowany odczyt layoutu po `(game_id, sequence_number)`.
- Stan planszy przechowuje anchor w każdym snapshotcie historii, a
  `load_anchored_layout` jest jednym krokiem `Undo`.
- `Next` zawija po końcu sekwencji, pokazuje bounded loading/error i ignoruje
  odpowiedź dla nieaktualnego kontekstu gry lub planszy.
- Exact matching rozpoznaje jawnie załadowany rekord jako znaną pozycję bez
  arbitralnego rozstrzygania zduplikowanej sygnatury; Target przelicza się dla
  bieżącego limitu.

### Verification results

- `npm.cmd test --workspace @game-predictor/mobile -- --runInBand` — 11 suites,
  81/81 testów.
- `npm.cmd run typecheck --workspace @game-predictor/mobile` — passed.
- `npm.cmd run lint --workspace @game-predictor/mobile` — passed; odczyt profilu
  Windows wymagał uruchomienia poza ograniczeniem sandboxa.
- Prettier check dla `apps/mobile/**/*.{ts,tsx}` i dokumentu zadania — passed.

### Not completed

- Test APK na Google Pixel 10 Pro XL pozostaje celowo w TASK-0141.

### Documentation updates

- Zaktualizowano plan 0.3 i `CURRENT_STATE.md`; wymagania oraz architektura już
  opisywały wdrożony kontrakt i nie wymagały zmiany semantyki.

### Recommended next task

- TASK-0139 — Consolidated matching and Target result summary.
