---
title: TASK-0620 — Drag-to-draw grid geometry for manual board placement
status: done
---

# TASK-0620 — Dwuklikowe wyznaczanie siatki zamiast czterech kliknięć

## Status

`done`

## Goal

W edytorze geometrii plansz operator wyznacza siatkę 3 × 5 dwoma kliknięciami:
kliknięcie lewego górnego narożnika (LT), przesunięcie kursora z odciśniętym
przyciskiem myszy — podczas ruchu widoczny jest żywy podgląd siatki 3 × 5 —
oraz drugie kliknięcie w prawym dolnym narożniku (PD). System zapisuje cztery
narożniki (LT, PT, PD, LD) w kolejności zgodnej z kontraktem. Kolejność plansz
pozostaje rzędami od lewej do prawej, wiersz po wierszu.

## Context

Obecny edytor (`grid-review-editor.tsx`) wymaga czterech kliknięć na planszę w sztywnej kolejności LT → PT → PD → LD. Dla dziewięciu plansz to 36 kliknięć. Operator zauważył, że szybciej i wygodniej jest zaznaczać każdą planszę jednym przeciągnięciem po skosie, a następnie — tylko gdy trzeba — poprawiać poszczególne rogi. Ta zmiana dotyczy wyłącznie ręcznego workflowu w edytorze geometrii; nie zmienia silników automatycznej detekcji, kontraktów zapisu ani modelu danych.

## Dependencies / entry conditions

- Istnieje działający edytor grid-review w `apps/reviewer` ze stanem `GridGeometryDraft` i czterema narożnikami.
- Kontrakt API/Worker akceptuje cztery narożniki w kolejności LT, PT, PD, LD.
- Backward compatibility z istniejącymi szkicami w `localStorage` i zapisanymi rewizjami.

## Recommended execution

`openrouter/moonshotai/kimi-k2.7-code`, reasoning `high`: zmiana łączy interakcję wskaźnika, perspektywiczną geometrię i wizualny podgląd siatki. Po implementacji wymagany jest skoncentrowany review testów interakcyjnych i typecheck/lint. Eskalacja jest wymagana, jeśli zmiana wymagałaby modyfikacji kontraktu API/Worker lub bazy danych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-421, D-428, D-429)
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`

## Scope

- Zmiana interakcji w `grid-review-editor.tsx` z 4 kliknięć na 2 kliknięcia LT → PD.
- Wyznaczenie czterech narożników z wektora LT→PD i pozycji kursora (kursor determinuje pochylenie).
- Wizualizacja siatki 3 × 5 podczas ruchu kursora między kliknięciami.
- Minimalny rozmiar prostokąta: 80 × 60 px; zbyt mały prostokąt jest odrzucany, plansza pozostaje niewyznaczona.
- Aktualizacja komunikatów UI i testów interakcyjnych.

## Out of scope

- Zmiana silników automatycznej detekcji geometrii (V1.0, V1.1, V1.2, V2.x).
- Zmiana kontraktu API, modelu danych lub migracji bazy.
- Dodanie trybu klasycznego (4 kliknięcia) jako fallback.
- Uczenie modeli, OCR, payouty, import.

## Acceptance criteria

- [x] Operator może wyznaczyć planszę przez kliknięcie LT, przesunięcie kursora i drugie kliknięcie PD (przycisk myszy jest zwolniony między kliknięciami).
- [x] W czasie ruchu kursora widoczna jest siatka 3 × 5 dopasowana do aktualnej pozycji kursora.
- [x] Po drugim kliknięciu system zapisuje cztery narożniki w kolejności LT, PT, PD, LD zgodnej z kontraktem.
- [x] Po zapisie można przeciągać każdy z czterech narożników lub całą siatkę (zachowanie obecne).
- [x] W trybie wsadowym przejście do następnej planszy odbywa się przez przycisk **Dalej**; brak automatycznego przeskakiwania po zatwierdzeniu siatki.
- [x] Prostokąt mniejszy niż 80 × 60 px nie jest zapisywany; plansza pozostaje niewyznaczona.
- [x] Istniejące szkice i zapisane geometrie pozostają czytelne (backward compatibility).
- [x] Testy interakcyjne, lint i typecheck przechodzą.

## Technical notes

### Aktualne zachowanie
- `pointerDown` w `grid-review-editor.tsx` dodaje punkty przez `addGridGeometryPoint` do `activeDraft.length === 4`.
- Po 4 punktach operator może przeciągać narożniki lub całą siatkę.
- `GRID_CORNER_LABELS = ['LT', 'PT', 'PD', 'LD']` w `grid-review-state.ts`.

### Wymagane zachowanie
- Pierwsze kliknięcie zapisuje LT i rozpoczyna podgląd.
- `pointerMove` z odciśniętym przyciskiem aktualizuje żywy podgląd siatki.
- Drugie kliknięcie (`pointerDown`) finalizuje PD, wylicza PT i LD z wektora LT→PD i pozycji kursora, zapisuje cztery narożniki.
- Jeśli prostokąt jest za mały, zaznaczenie jest odrzucane i plansza pozostaje niewyznaczona.
- Aby edytować istniejącą automatyczną siatkę, operator najpierw klika planszę na liście (tryb edycji), a potem przeciąga narożniki.

### Algorytm wyznaczania PT/LD (wersja 1)
Wejście:
- `LT = (x1, y1)`
- `PD = (x2, y2)`
- kursor w czasie dragu: `C = (cx, cy)`

Obliczenia:
- `v_main = PD − LT`
- `d = |v_main|`
- `angle_main = atan2(v_main.y, v_main.x)`
- `angle_cursor = atan2(C.y − LT.y, C.x − LT.x)`
- `skew = angle_cursor − angle_main`, clamped do zakresu ±45°
- `perp = (−v_main.y, v_main.x) / d`
- `skew_factor = tan(skew) * d * 0.5`
- `PT = LT + v_main + perp * skew_factor`
- `LD = LT + perp * skew_factor` (przybliżenie perspektywiczne)

Uwaga: powyższy algorytm jest heurystyką wizualną; finalne rogi są zawsze edytowalne. Dokładność perspektywy nie jest krytyczna, bo operator i tak dopasowuje siatkę.

### Źródła prawdy
- Kolejność narożników: `GRID_CORNER_LABELS` w `grid-review-state.ts`.
- Format zapisu: `ImageGridReviewGeometryCommand` (backendowy kontrakt pozostaje bez zmian).
- Stan dragu: lokalny `useRef` w `grid-review-editor.tsx`.

### Walidacja
- Min width 80 px, min height 60 px.
- Wszystkie współrzędne ograniczone do granic źródła (z uwzględnieniem `allowOutsideSource`).

## Expected files

- Istniejące: `apps/reviewer/src/features/grid-reviews/grid-review-editor.tsx` — interakcja i rysowanie.
- Istniejące: `apps/reviewer/src/features/grid-reviews/grid-review-state.ts` — algorytm wyznaczania narożników.
- Istniejące: `packages/manual-image-selection-core/src/manual-grid-qualification.ts` — walidacja minimalnego rozmiaru (opcjonalnie).
- Istniejące: `apps/reviewer/test-interactions/grid-geometry-qualification.test.mjs` — testy interakcyjne.
- Nowe: `apps/reviewer/src/features/grid-reviews/grid-review-state.test.ts` — jednostkowe testy algorytmu (proponowane).

## Test cases

- Przeciągnięcie LT→PD w dół i w prawo → cztery narożniki, kolejność LT, PT, PD, LD.
- Przeciągnięcie pod kątem 30° → siatka pochylona, PT i LD wyznaczone zgodnie z kierunkiem kursora.
- Prostokąt 40 × 40 px → odrzucony, draft pusty.
- Tryb wsadowy: po zakończeniu planszy 1 focus przechodzi na planszę 2.
- Regresja: istniejące zapisane geometrie wyświetlają się poprawnie.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr; timeout maksymalnie 120 s na krok
npm run typecheck --workspace=apps/reviewer
npm run lint --workspace=apps/reviewer
npm test --workspace=apps/reviewer -- --run test-interactions/grid-geometry-qualification.test.mjs
```

## Risks / open questions

- Heurystyka pochylenia może być niedokładna dla bardzo nachylonych plansz; operator zawsze może poprawić rogi ręcznie.
- Wydajność rysowania siatki 3 × 5 w czasie przeciągania na słabszych maszynach — wymaga testu wizualnego.
- Backward compatibility szkiców `localStorage`: istniejące szkice zawierają 4 narożniki per plansza i pozostają kompatybilne.

## Outcome

### Changed

- `apps/reviewer/src/features/grid-reviews/grid-review-state.ts`:
  - dodano `dragGeometryCorners`, `finalizeDragGeometry`, `GRID_DRAG_MIN_SIZE`,
    oraz wyeksportowano `boundedGridGeometryPoint`;
  - `finalizeDragGeometry` odrzuca prostokąty mniejsze niż 80 × 60 px i zwraca
    cztery narożniki w kolejności LT, PT, PD, LD.
- `apps/reviewer/src/features/grid-reviews/grid-review-editor.tsx`:
  - nowa interakcja dwuklikowa: pierwszy `pointerDown` zaczyna zaznaczenie,
    `pointerMove` rysuje żywy podgląd 3 × 5, drugi `pointerDown` finalizuje;
  - Escape anuluje rozpoczęte zaznaczenie;
  - edycja istniejącej siatki wymaga wejścia w tryb edycji przez kliknięcie
    planszy na liście;
  - zaktualizowano komunikaty pomocy pod canvasem.
- `apps/reviewer/test/grid-review-state.test.mjs`: jednostkowe testy algorytmu
  `dragGeometryCorners` i `finalizeDragGeometry`.
- `apps/reviewer/test/grid-review-workspace-contract.test.mjs`: aktualizacja
  kontraktu UI (nowe teksty pomocy).
- `apps/reviewer/test-interactions/grid-geometry-qualification.test.mjs`:
  dostosowanie testu legacy reset do nowej interakcji.
- `ai_docs/process/CURRENT_STATE.md`: nowa sekcja TASK-0620.
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`: instrukcja dwuklikowego
  wyznaczania siatki.

### Verification results

```powershell
npm run typecheck --workspace=apps/reviewer    # przeszło
npm run lint --workspace=apps/reviewer          # przeszło
npm test --workspace=apps/reviewer              # 193/193 przeszło
npm run test:geometry --workspace=apps/reviewer # 3/3 przeszło
```

### Not completed

- Brak. Zakres taska został wykonany w całości.

### Documentation updates

- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- niniejsza karta zadania

### Recommended next task

- Wdrożenie do stagingu i wizualny test z rzeczywistymi zdjęciami Mumii.
- Ewentualna regulacja heurystyki pochylenia na podstawie feedbacku operatora.
