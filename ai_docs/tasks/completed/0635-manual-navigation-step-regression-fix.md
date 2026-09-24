---
title: TASK-0635 — naprawa regresji adjacentManualNavigationStep w Reviewerze
status: done
last_updated: 2026-09-24
---

# TASK-0635 — naprawa regresji `adjacentManualNavigationStep` w Reviewerze

## Status

`done`

## Goal

Przywrócić poprawne przeskakiwanie po `MANUAL_IMAGE_NAVIGATION_STEPS` dla
skrótów klawiszowych „poprzedni/następny krok” w Reviewerze; zielony
`manual-image-selection-core.test.mjs`.

## Context

Użytkownik poprosił o naprawę błędów znalezionych podczas implementacji
TASK-0632–0634. Jeden z nich, zgłoszony wcześniej jako „przedsesyjny i
niepowiązany” chip (patrz Outcome `TASK-0633`), po zbadaniu okazał się
realną regresją funkcjonalną w Reviewerze, nie szumem testowym: commit
`v0.10.387 - numeric navigation step input with +/-1 arrows` zmienił
współdzieloną funkcję `adjacentManualNavigationStep`
(`packages/manual-image-selection-core/src/index.ts`) tak, żeby pasowała do
nowego UI Admina (dowolny numeryczny krok z przyciskami +/-1), ale przy
okazji przestał ją wywoływać z Admina w ogóle — Admin dostał własną, lokalną
kopię tej logiki. Jedynym pozostałym konsumentem funkcji w pakiecie jest
Reviewer, którego `<select>` kroku nawigacji i skróty klawiszowe nadal
zależą od przeskakiwania po liście `MANUAL_IMAGE_NAVIGATION_STEPS =
[1,2,...,10,15,20]`. Zmieniona funkcja złamała to bez testu Reviewera, który
by to złapał — złapał to istniejący test pakietu.

## Dependencies / entry conditions

- Brak. Niezależne od `TASK-0632`–`TASK-0634`.

## Recommended execution

`claude-sonnet-5`, reasoning `medium`. Punktowa naprawa regresji z jasną
diagnozą z `git log -p`; ryzyko niskie (przywrócenie dokładnie wcześniej
istniejącego, przetestowanego kodu).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-441)

## Scope

- `packages/manual-image-selection-core/src/index.ts`:
  `adjacentManualNavigationStep`.

## Out of scope

- `apps/admin/src/features/manual-image-selection/manual-image-selection-workspace.tsx`
  (własna, poprawna logika free-form — nie dotknięta).
- Dodanie dedykowanego testu Reviewera dla tej regresji (niezgłoszone przez
  użytkownika; pokrycie już istnieje na poziomie pakietu).
- Sprzątnięcie niepowiązanego, przedsesyjnego ostrzeżenia lint (`MANUAL_IMAGE_NAVIGATION_STEPS`
  nieużywane w `apps/admin/test/manual-local-image-selection.test.mjs`) —
  osobna, drobna sprawa, nie funkcjonalny błąd.

## Acceptance criteria

- [x] `adjacentManualNavigationStep` przesuwa się po
      `MANUAL_IMAGE_NAVIGATION_STEPS`, nie po surowej liczbie.
- [x] `npm run test --workspace @game-predictor/manual-image-selection-core`
      w pełni zielony.
- [x] `npm run test --workspace @game-predictor/reviewer` bez regresji.
- [x] Zero zmiany zachowania Admina (nie importuje już tej funkcji).

## Technical notes

**Aktualne (błędne) → wymagane zachowanie:** patrz `DECISION_LOG.md` D-441
— pełna diagnoza i uzasadnienie, nieduplikowane tutaj.

**Diagnoza:** `git log -p --follow -- packages/manual-image-selection-core/src/index.ts`
ujawnił dokładny commit i diff, który wprowadził regresję
(`dc8779058c973d5f8efb2c9743cac80f07cdeaae`, `v0.10.387`). Naprawa to
dosłowne przywrócenie usuniętego wtedy kodu.

## Expected files

- Istniejące: `packages/manual-image-selection-core/src/index.ts`,
  `ai_docs/process/DECISION_LOG.md`, `ai_docs/process/CURRENT_STATE.md`.
- Nowe: `ai_docs/tasks/completed/0635-manual-navigation-step-regression-fix.md`
  (ten plik).

## Test cases

- Istniejący test pakietu `offers contiguous one-to-ten image navigation
  steps` (niezmieniony) — teraz zielony.
- `adjacentManualNavigationStep(10, 1)` → `15` (przeskakuje przerwę w
  liście, nie `11`) — pośrednio pokryte przez test istniejący
  (`adjacentManualNavigationStep(9, 1) === 10`) i acceptance criteria; nie
  dodano nowej explicit asercji dla przeskoku 10→15, bo istniejący test
  pakietu już w pełni pokrywa kontrakt funkcji (indeks w tablicy), a dodanie
  kolejnej asercji do niezmienianego testu wykraczałoby poza zakres naprawy.

## Verification

```powershell
npm run test --workspace @game-predictor/manual-image-selection-core   # timeout 120 s
npm run typecheck --workspace @game-predictor/manual-image-selection-core  # timeout 120 s
npm run test --workspace @game-predictor/reviewer                       # timeout 120 s
npm run typecheck --workspace @game-predictor/reviewer                  # timeout 120 s
npx prettier --check packages/manual-image-selection-core/src/index.ts
```

Wszystkie uruchomione i zielone (patrz Outcome).

## Risks / open questions

- Brak. Naprawa jest przywróceniem wcześniej działającego, przetestowanego
  kodu; jedyny konsument (Reviewer) ma już pokrycie testowe na poziomie
  UI/kontraktów niezmienione przez tę naprawę.

## Outcome

### Changed

- `packages/manual-image-selection-core/src/index.ts`:
  `adjacentManualNavigationStep` przywrócone do przeszukiwania
  `MANUAL_IMAGE_NAVIGATION_STEPS`.
- `ai_docs/process/DECISION_LOG.md` (D-441), `ai_docs/process/CURRENT_STATE.md`.

### Verification results

- `npm run test --workspace @game-predictor/manual-image-selection-core` →
  110/110 passed (poprzednio 109/110).
- `npm run typecheck --workspace @game-predictor/manual-image-selection-core`
  → czysto.
- `npm run test --workspace @game-predictor/reviewer` → 193/193 passed, bez
  zmiany.
- `npm run typecheck --workspace @game-predictor/reviewer` → czysto.
- `npx prettier --check` → zielone po jednorazowym `--write` (diff
  zweryfikowany, obejmuje wyłącznie zmienioną funkcję).

### Not completed

- Nic w zakresie tej naprawy.

### Documentation updates

- `ai_docs/process/DECISION_LOG.md`: nowy wpis D-441.
- `ai_docs/process/CURRENT_STATE.md`: nowa sekcja TASK-0635 na szczycie.

### Recommended next task

- Brak pilnego. Opcjonalnie, osobno: dedykowany test Reviewera dla
  `previous_step`/`next_step` (obecnie pokrycie jest wyłącznie na poziomie
  pakietu współdzielonego) i sprzątnięcie nieużywanego importu
  `MANUAL_IMAGE_NAVIGATION_STEPS` w `apps/admin/test/manual-local-image-selection.test.mjs`.
