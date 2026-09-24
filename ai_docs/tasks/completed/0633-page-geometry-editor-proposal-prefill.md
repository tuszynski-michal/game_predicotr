---
title: TASK-0633 — edytor korekty geometrii startuje od automatycznej propozycji
status: done
last_updated: 2026-09-24
---

# TASK-0633 — edytor korekty geometrii startuje od automatycznej propozycji

## Status

`done`

## Goal

Otwarcie strony `review_required` bez istniejącej geometrii w edytorze
korekty pokazuje 9 plansz ułożonych według `automaticPageProposal` (T1,
`TASK-0632`) zamiast pustego, wyśrodkowanego szablonu; plansza wychodząca
poza kadr jest automatycznie oznaczona „Niepełna plansza”.

## Context

T2 z 3-taskowego planu „wstępna geometria z automatycznej propozycji dla
przyciętych stron” (T1: `TASK-0632`/D-439 → T2: `TASK-0633` → T3:
niezlecony, proponowany `TASK-0634`). T1 dostarczył pole
`automaticPageProposal` w `review-sources`, ale edytor Admin
(`page-geometry-correction-panel.tsx`) go nie czytał — operator nadal widział
`initialCorners()` (prostokąt 8% od krawędzi) przy każdej stronie
`manual_template`, mimo że dobra propozycja już jest w odpowiedzi API.

## Dependencies / entry conditions

- `TASK-0632` (D-439) ukończony: `BrowserPageGeometryReviewSourceResponse.automaticPageProposal`
  dostępne dla `geometryOrigin=manual_template`.
- Brak zależności od T3 (przesuwanie całej planszy) — niezależny task.

## Recommended execution

`claude-sonnet-5`, reasoning `high`. Punktowa zmiana w dużym komponencie ze
stanem, szkicami i kwalifikacjami (ryzyko regresji istniejącego workflow
szkiców/V1.2). Dodatkowy review nie był wymagany do wykonania (wykonano
solo); zalecany opcjonalnie `claude-opus-5-5`/`high` przed mergem do main,
zgodnie z pierwotnym planem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` (sekcja „Pochodzenie geometrii w
  korekcie strony”)
- `ai_docs/process/DECISION_LOG.md` (D-439)

## Scope

- `apps/admin/src/features/imports/page-geometry-correction-panel.tsx`:
  nowa czysta funkcja `proposalSourceGeometry`, użycie w `resetGeometry`
  (trzecie źródło startowej geometrii), nowy stan
  `initialQualificationFlags` reużywany w `resetCurrentGeometry`, nowy
  wariant komunikatu `geometryOriginNotice`.
- `apps/admin/test-interactions/page-geometry-qualification.test.mjs`: nowe
  testy interakcji.
- Dokumentacja: `ADMIN_APP.md`, `DECISION_LOG.md` (D-439), `CURRENT_STATE.md`.

## Out of scope

- Worker, manifest, `page_geometry_registration.py`, `page_geometry_preflight.py`.
- Przesuwanie całej planszy (T3, osobny task).
- Walidacja zapisu (`PageGeometryOverrideService`, `manualGridQualification`),
  `geometry_origin`, kontrakt `BrowserPageGeometryOverrideCreate`.
- V1.2 (`page-geometry-v12-offsets.ts`, `expandedFrameQuad`), szkice
  `page-geometry-draft-storage.ts`.
- Reviewer (`apps/reviewer`).

## Acceptance criteria

- [x] Strona `manual_template` z `automaticPageProposal` startuje z 9
      planszami ułożonymi wg propozycji, nie wg pustego szablonu.
- [x] Plansza, której surowy punkt propozycji wypada poza zdjęciem, ma
      automatycznie `partial: true` przy pierwszym wczytaniu.
- [x] Istniejąca geometria (szkic `localStorage`, override, wynik automatu)
      ma pierwszeństwo nad propozycją.
- [x] `geometryOrigin=automatic` z zapisanymi quadami ignoruje
      `automaticPageProposal`, nawet jeśli jest obecne (regresja).
- [x] V1.2 nie dostaje propozycji.
- [x] „Reset” przywraca dokładnie stan startowy, w tym flagę `partial`
      pochodzącą z propozycji (nie tylko geometrię).
- [x] Komunikat w panelu informuje o użyciu propozycji i listuje plansze
      poza kadrem; bez propozycji stary tekst pozostaje bez zmian.
- [x] Zapis bez korekt wysyła `finalQuads` propozycji i
      `slotQualifications[i].completenessStatus === 'pending_partial'` dla
      plansz poza kadrem.

## Technical notes

**Aktualne zachowanie → wymagane zachowanie:** patrz `DECISION_LOG.md` D-439
(akapit T2) i `CURRENT_STATE.md` (sekcja TASK-0633) — pełny opis kolejności
źródeł, przycinania i naprawionego błędu w `resetCurrentGeometry`, żeby nie
duplikować tu treści.

**Ważna pułapka odkryta w trakcie:** Prettier reformatuje tekst JSX między
liniami niezależnie od pierwotnego wcięcia — pierwsza wersja komunikatu
błędu złamała frazę „roboczym szablonem edytora” dokładnie w środku (między
„szablonem” i „edytora”), co zepsułoby istniejący kontrakt-test
sprawdzający dosłowny tekst źródła
(`page-geometry-correction-panel-contract.test.mjs`). Naprawione przez
przeniesienie zdania do stringu JS (`{'...'}`) zamiast surowego tekstu JSX —
Prettier nie łamie zawartości string-literału. Ta sama technika może być
potrzebna w przyszłych zmianach tego pliku dla innych fraz sprawdzanych
kontrakt-testem.

## Expected files

- Istniejące: `apps/admin/src/features/imports/page-geometry-correction-panel.tsx`,
  `apps/admin/test-interactions/page-geometry-qualification.test.mjs`,
  `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/process/DECISION_LOG.md`,
  `ai_docs/process/CURRENT_STATE.md`.
- Nowe: `ai_docs/tasks/completed/0633-page-geometry-editor-proposal-prefill.md`
  (ten plik).

## Test cases

- `manual_template` + propozycja z jedną planszą poza kadrem → po `onLoad`
  polygon planszy 0 ma punkty propozycji niezmienione, plansza 6 (x<0) ma
  zaznaczone „Niepełna plansza”, komunikat panelu wspomina „Poza kadrem: 7”
  i „Do sprawdzenia: 7”.
- Zapis bez zmian → `finalQuads` odpowiadają propozycji,
  `slotQualifications[6].completenessStatus === 'pending_partial'`,
  `unavailableCellIndices` niepuste, slot 0 `complete`.
- Istniejący szkic `localStorage` (inne quady, flagi bez `partial`) → wygrywa
  nad propozycją — polygon 0 pokazuje quady szkicu, plansza 6 nieoznaczona.
- `geometryOrigin: 'automatic'` z `existingFinalQuads` i (kontrowanym)
  `automaticPageProposal` → propozycja zignorowana, polygon 6 pokazuje
  zapisane quady, checkbox nieoznaczony.
- „Reset” po wczytaniu propozycji → polygon 6 nadal pokazuje quady
  propozycji, checkbox „Niepełna plansza” nadal zaznaczony (mutation-tested:
  cofnięcie poprawki `initialQualificationFlags` powoduje czerwony test —
  `false !== true`).

## Verification

```powershell
npm run test:geometry --workspace @game-predictor/admin   # timeout 120 s
npm run test --workspace @game-predictor/admin             # timeout 120 s
npm run typecheck --workspace @game-predictor/admin        # timeout 120 s
npm run lint --workspace @game-predictor/admin              # timeout 120 s
npx prettier --check apps/admin/src/features/imports/page-geometry-correction-panel.tsx apps/admin/test-interactions/page-geometry-qualification.test.mjs
```

Wszystkie polecenia uruchomione i zielone (patrz Outcome). Dodatkowo
uruchomiono (nie wymagane przez ten task, ale w zakresie deklarowanym przez
plan) `npm run test --workspace @game-predictor/manual-image-selection-core`
— 109/110 zielone, 1 czerwony przedsesyjny i niepowiązany (patrz Outcome).

## Risks / open questions

- Nazwa pola `origin` w `automaticPageProposal` (z T1) może być myląca —
  odziedziczone z zaakceptowanego planu, nie zmieniane w tym tasku.
- Jakość propozycji dla mocno przyciętych plansz zależy od homografii
  kandydata z T1 — operator nadal musi sprawdzić każdą planszę przed
  zapisem (niezmienione wymaganie).

## Outcome

### Changed

- `apps/admin/src/features/imports/page-geometry-correction-panel.tsx`:
  nowa `proposalSourceGeometry`, wpięcie w `resetGeometry` (trzecie źródło
  geometrii startowej, ustalanie `partialSlots`), nowy stan
  `initialQualificationFlags` (ustawiany w `resetGeometry`, reużyty w
  `resetCurrentGeometry` zamiast błędnego przeliczania od zera), nowy
  wariant komunikatu `geometryOriginNotice` z listą plansz poza kadrem i do
  sprawdzenia, `usedProposal` (`useMemo`) sterujący UI.
- `apps/admin/test-interactions/page-geometry-qualification.test.mjs`: 5
  nowych testów (prefill + oznaczenie; zapis; pierwszeństwo szkicu;
  regresja `automatic`; Reset).
- `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/process/DECISION_LOG.md`
  (D-439), `ai_docs/process/CURRENT_STATE.md`.

### Verification results

- `npm run test:geometry --workspace @game-predictor/admin` → 18/18 passed
  (13 istniejących bez zmiany asercji + 5 nowych).
- `npm run test --workspace @game-predictor/admin` → 564/564 passed.
- `npm run typecheck --workspace @game-predictor/admin` → czysto.
- `npm run lint --workspace @game-predictor/admin` → 0 błędów, 5 warningów
  (wszystkie przedsesyjne, niepowiązane z tym plikiem/taskiem poza trzema
  już istniejącymi w tym samym pliku przed zmianą).
- `npx prettier --check` → zielone po `--write` (jeden świadomy fix: string
  literał zamiast tekstu JSX, żeby przetrwać reformatowanie — patrz
  Technical notes).
- Mutation test: tymczasowe cofnięcie poprawki `resetCurrentGeometry` →
  test „Reset restores...” czerwony (`false !== true`), potwierdzając że
  test faktycznie chroni tę poprawkę.
- `npm run test --workspace @game-predictor/manual-image-selection-core` →
  109/110 passed. 1 czerwony (`offers contiguous one-to-ten image
  navigation steps`, `21 !== 20`) — **potwierdzony przedsesyjny i
  niepowiązany**: `git status --porcelain` dla tego pakietu pusty przez cały
  task, plik testu niezmieniony od `v0.10.13`. Nie naprawiony w tym tasku
  (poza zakresem — dotyczy nawigacji manualnej selekcji obrazów, nie
  geometrii strony).

### Not completed

- Nic w zakresie tego taska. T3 (przesuwanie całej planszy) pozostaje
  niezlecony.
- Przedsesyjny, niepowiązany czerwony test w
  `manual-image-selection-core.test.mjs` — zgłoszony, nie naprawiony (poza
  zakresem).

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md`: nowy akapit w „Pochodzenie geometrii
  w korekcie strony”.
- `ai_docs/process/DECISION_LOG.md`: D-439 rozszerzone o akapit T2, status
  zaktualizowany.
- `ai_docs/process/CURRENT_STATE.md`: nowa sekcja TASK-0633 na szczycie.

### Recommended next task

- T3 (przesuwanie całej wybranej planszy, `boardMove`) — wymaga osobnego
  polecenia użytkownika, proponowany numer `TASK-0634`.
- Osobno, poza tym planem: zbadać czerwony
  `manual-image-selection-core.test.mjs` (`offers contiguous one-to-ten
  image navigation steps`) — niepowiązany z geometrią strony.
