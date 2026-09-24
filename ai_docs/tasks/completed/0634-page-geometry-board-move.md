---
title: TASK-0634 — przesuwanie całej wybranej planszy w edytorze korekty geometrii
status: done
last_updated: 2026-09-24
---

# TASK-0634 — przesuwanie całej wybranej planszy w edytorze korekty geometrii

## Status

`done`

## Goal

Operator może przesunąć całą wybraną planszę (4 narożniki naraz), nie tylko
pojedyncze narożniki, w edytorze korekty geometrii strony.

## Context

T3 z 3-taskowego planu „wstępna geometria z automatycznej propozycji dla
przyciętych stron” (T1: `TASK-0632`/D-439 → T2: `TASK-0633` → T3:
`TASK-0634`). Niezależny od T1/T2 logicznie, ale wykonany po nich zgodnie z
kolejnością planu. Edytor nie miał wcześniej sposobu na przesunięcie całej
planszy — operator poprawiający propozycję z T2 musiał przesuwać 4 narożniki
osobno, nawet gdy cała plansza była tylko przesunięta względem rzeczywistej
pozycji na zdjęciu.

## Dependencies / entry conditions

- Brak twardej zależności od `TASK-0632`/`TASK-0633` — gest działa
  niezależnie od źródła geometrii startowej (propozycja, override, szablon).

## Recommended execution

`claude-sonnet-5`, reasoning `high`. Nowy gest współdzielący obsługę
wskaźnika z istniejącym wyborem planszy i przeciąganiem narożnika w dużym,
stanowym komponencie — wymaga starannych testów regresji konfliktu zdarzeń.
Dodatkowy review nie był wymagany do wykonania.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` (sekcja „Pochodzenie geometrii w
  korekcie strony”)
- `ai_docs/process/DECISION_LOG.md` (D-439)

## Scope

- `apps/admin/src/features/imports/page-geometry-correction-panel.tsx`:
  nowy rodzaj `dragging.kind === 'boardMove'`, czysta funkcja
  `translateBoardQuad`, refaktor `relativePoint` → `relativePointFromRect` +
  wrapper, zawężenie typu `beginDrag`, zmiana `onPointerDown` polygonu
  planszy (select-then-move, DA-4).
- `apps/admin/src/app/globals.css`: `cursor: move` na
  `.pageGeometryBoardSelected`.
- `apps/admin/test-interactions/page-geometry-qualification.test.mjs`: nowe
  testy interakcji.
- Dokumentacja: `ADMIN_APP.md`, `DECISION_LOG.md` (D-439), `CURRENT_STATE.md`.

## Out of scope

- Worker, manifest, logika preflightu.
- Zmiana kolejności źródeł startowej geometrii (T1/T2) i walidacji zapisu.
- V1.2, szkice `localStorage`, Reviewer.
- Naprawa niepowiązanego, przedsesyjnego dryfu formatowania w `globals.css`
  poza dodaną regułą (`.v7LabelGeometryControls` — zgłoszone w
  `CURRENT_STATE.md`, nie naprawiane tutaj).

## Acceptance criteria

- [x] Wybrana plansza, przeciągnięta za wnętrze, przesuwa się o stały
      wektor — 4 narożniki naraz, kształt bez zmian.
- [x] Pierwsze kliknięcie niewybranej planszy tylko ją wybiera, nie startuje
      ruchu (DA-4).
- [x] Przeciąganie pojedynczego narożnika wybranej planszy nadal zmienia
      tylko ten narożnik (regresja).
- [x] Ruch planszy bez flagi `partial` zatrzymuje się na krawędzi zdjęcia;
      z `partial` (na dowolnej planszy strony) pozwala wyjść w ten sam
      rozszerzony zakres, co przeciąganie narożnika.
- [x] Kursor wskazuje `move` nad wybraną planszą.

## Technical notes

Pełny opis mechanizmu (typ `dragging`, `translateBoardQuad`, wybór granic,
refaktor `relativePoint`, świadoma korekta względem planu co do `bounds`)
jest w `DECISION_LOG.md` D-439 (akapit T3) i `CURRENT_STATE.md` (sekcja
TASK-0634) — nie duplikowany tutaj.

**Odkryta podczas pracy pułapka formatowania:** `npx prettier --write` na
całym `globals.css` przeformatował przy okazji niepowiązaną regułę
`.v7LabelGeometryControls` — plik ma przedsesyjny dryf formatowania poza
zakresem tego taska. Cofnięte ręcznie, żeby diff obejmował tylko dodaną
regułę. Wniosek na przyszłość: dla dużych, współdzielonych plików CSS/TS
uruchamiać Prettier punktowo i sprawdzać `git diff --stat`/`git diff` przed
stage'owaniem, nie ufać ślepo `--write` na całym pliku.

## Expected files

- Istniejące: `apps/admin/src/features/imports/page-geometry-correction-panel.tsx`,
  `apps/admin/src/app/globals.css`,
  `apps/admin/test-interactions/page-geometry-qualification.test.mjs`,
  `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/process/DECISION_LOG.md`,
  `ai_docs/process/CURRENT_STATE.md`.
- Nowe: `ai_docs/tasks/completed/0634-page-geometry-board-move.md` (ten
  plik).

## Test cases

- Wybrana plansza (drugi `pointerdown` na już wybranej), przeciągnięcie o
  (+30, +10) → 4 punkty przesunięte o ten sam wektor, inne plansze bez
  zmian.
- Pierwszy `pointerdown` na niewybranej planszy → tylko wybór (klasa
  `pageGeometryBoardSelected`), zero zmiany punktów.
- Przeciągnięcie uchwytu narożnika wybranej planszy → zmienia tylko ten
  narożnik, reszta bez zmian.
- Ruch planszy bez `partial` daleko poza zdjęcie → zatrzymuje się dokładnie
  na krawędzi (`minX=0`), kształt zachowany.

## Verification

```powershell
npm run test:geometry --workspace @game-predictor/admin   # timeout 120 s
npm run test --workspace @game-predictor/admin             # timeout 120 s
npm run typecheck --workspace @game-predictor/admin        # timeout 120 s
npm run lint --workspace @game-predictor/admin              # timeout 120 s
```

## Risks / open questions

- `bounds` dla ruchu planszy używa globalnego `allowOutsideSource`
  (którakolwiek plansza na stronie jest `partial`), nie flagi tylko
  przesuwanej planszy — świadoma korekta dla spójności z istniejącym
  przeciąganiem narożnika na tej samej stronie (patrz D-439). Jeśli w
  przyszłości pojawi się wymaganie ściśle per-planszowego ograniczenia,
  wymaga to osobnej decyzji, bo zmieniłoby też zachowanie pojedynczego
  narożnika.

## Outcome

### Changed

- `apps/admin/src/features/imports/page-geometry-correction-panel.tsx`:
  `dragging` rozszerzony o `boardMove`, `translateBoardQuad`,
  `relativePointFromRect`/`relativePoint`, `beginDrag` zawężony typ,
  `onPointerDown` polygonu planszy.
- `apps/admin/src/app/globals.css`: `cursor: move` na
  `.pageGeometryBoardSelected`.
- `apps/admin/test-interactions/page-geometry-qualification.test.mjs`: 4
  nowe testy.
- `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/process/DECISION_LOG.md`
  (D-439), `ai_docs/process/CURRENT_STATE.md`.

### Verification results

- `npm run test:geometry --workspace @game-predictor/admin` → 22/22 passed
  (18 istniejących/T2 bez zmiany asercji + 4 nowe).
- `npm run test --workspace @game-predictor/admin` → 564/564 passed.
- `npm run typecheck --workspace @game-predictor/admin` → czysto.
- `npm run lint --workspace @game-predictor/admin` → 0 błędów, te same 4
  przedsesyjne warningi.
- Mutation test: tymczasowe wyłączenie warunku startu ruchu (`false && ...`)
  → 2 testy czerwone („a second pointerdown...”, „moving a non-partial
  board...”), potwierdzając że chronią rzeczywiste zachowanie.
- `git diff` po każdym `prettier --write` sprawdzony ręcznie — cofnięta
  jedna niepowiązana reformatowana reguła CSS (patrz Technical notes).

### Not completed

- Nic w zakresie tego taska. Plan „wstępna geometria z automatycznej
  propozycji” (T1→T2→T3) jest w całości ukończony.
- Zgłoszony, nie naprawiony: przedsesyjny dryf formatowania Prettiera w
  `globals.css` poza dodaną regułą.

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md`: nowy akapit o przesuwaniu planszy.
- `ai_docs/process/DECISION_LOG.md`: D-439 rozszerzone o akapit T3, status
  „plan w całości zrealizowany”.
- `ai_docs/process/CURRENT_STATE.md`: nowa sekcja TASK-0634 na szczycie.

### Recommended next task

- Brak zaplanowanego kolejnego taska w tym planie — wszystkie trzy (T1–T3)
  ukończone. Osobno, poza tym planem: rozważyć uruchomienie
  `npm run format:check` na `globals.css` i naprawę przedsesyjnego dryfu
  formatowania w osobnym, punktowym tasku.
