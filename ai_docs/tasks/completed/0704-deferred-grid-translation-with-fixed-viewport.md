---
title: TASK-0704 — Przesuwanie całej siatki bez ruchu kadru obrazu
status: done
---

# TASK-0704 — Przesuwanie całej siatki bez ruchu kadru obrazu

## Status

`in_progress`

## Goal

W edytorze odroczonej geometrii operator może przesunąć cały obrys siatki bez zmiany perspektywy i bez automatycznego ruchu obrazu.

## Context

Po TASK-0703 viewport nie jest już wyliczany ponownie po przeciągnięciu narożnika, ale przeciągnięcie wnętrza siatki nadal nie ma osobnego gestu. Operator potrzebuje przesunąć całą siatkę do właściwego miejsca bez deformowania jej i bez przesuwania zdjęcia.

## Dependencies / entry conditions

- TASK-0700 i TASK-0703 są zakończone; checkbox „Aktywne przesuwanie” domyślnie jest wyłączony.
- Dotyczy wyłącznie `DeferredBoardCellGeometryEditor` w kolejce „Niepełne siatki do ręcznej korekty”.

## Recommended execution

`gpt-6-sol`, reasoning `high`. Zmiana obejmuje izolowaną interakcję canvasu oraz czyste funkcje geometrii; wymaga regresji dla granic obrazu i zachowania perspektywy. Eskalacja do `gpt-6-astra` tylko przy wykryciu niejednoznaczności w geometrii projektowej.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`

## Scope

- Dodać czystą translację czterech narożników, która zachowuje ich wzajemne położenie i dla kompletnej planszy ogranicza całą siatkę do krawędzi obrazu.
- Przeciąganie wnętrza siatki przy wyłączonym „Aktywnym przesuwaniu” ma przesuwać cały obrys, nie viewport i nie pojedynczy narożnik.
- Gdy „Aktywne przesuwanie” jest włączone, drag poza numerowanym narożnikiem ma przesuwać wyłącznie viewport obrazu.
- Zachować osobną, precyzyjną korektę perspektywy przez numerowany narożnik oraz obsługę `Niepełna plansza` poza źródłem.

## Out of scope

- Zmiany API, backendu, zapisu geometrii, preview lub danych użytkownika.
- Zmiana zachowania pozostałych edytorów geometrii.

## Acceptance criteria

- [ ] Przy wyłączonym checkboxie przeciągnięcie wnętrza kompletnej siatki przesuwa wszystkie cztery rogi o identyczny dopuszczalny wektor.
- [ ] Siatka kompletna zatrzymuje się na granicach obrazu; viewport nie zmienia `x`, `y`, szerokości ani wysokości.
- [ ] Przy włączonym checkboxie drag poza narożnikiem zmienia tylko viewport, nie rogi siatki.
- [ ] Przeciągnięcie numerowanego narożnika nadal zmienia tylko ten narożnik.
- [ ] Testy zabezpieczają translację, granice i kontrakt edytora.

## Technical notes

Źródłem prawdy pozostają source-space rogi geometrii. Drag całej siatki zapamiętuje punkt i komplet rogów z chwili pointer-down, a każdy pointer-move wylicza jeden wektor od tego stanu początkowego. Dzięki temu ruch nie kumuluje błędów zaokrągleń ani nie zmienia perspektywy. Dla `partial=false` wektor jest wspólnie zawężany tak, aby minimum i maksimum wszystkich rogów pozostały w granicach źródła. Dla `partial=true` zachowane jest istniejące uprawnienie do obszaru poza zdjęciem.

Kolejność gestów: numerowany narożnik → (gdy checkbox włączony) viewport → (gdy checkbox wyłączony i punkt leży wewnątrz quada) translacja siatki → brak przechwycenia. Nie wolno odświeżać viewportu w `replaceCorners` dla któregokolwiek z dragów.

## Expected files

- Istniejące: `apps/reviewer/src/features/operational-reviews/operational-review-state.ts` — czyste funkcje zawierania i translacji quada.
- Istniejące: `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx` — rozróżnienie gestu narożnika, obrysu i viewportu.
- Istniejące: `apps/reviewer/test/operational-review-state.test.mjs` oraz `apps/reviewer/test/operational-review-workspace-contract.test.mjs` — regresje.

## Test cases

- Quad wewnątrz zdjęcia + duży dodatni/ujemny offset → wszystkie rogi przesuwają się jednakowo i zatrzymują na granicy.
- Quad perspektywiczny + offset → różnice między odpowiadającymi rogami są niezmienione.
- Quad niepełny + offset → zachowuje obsługę współrzędnych poza źródłem.
- Kontrakt edytora → osobne referencje dla translacji siatki i przesuwania viewportu.

## Verification

```powershell
pnpm --filter @game-predictor/reviewer test
pnpm exec prettier --check apps/reviewer/src/features/operational-reviews/operational-review-state.ts apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx apps/reviewer/test/operational-review-state.test.mjs apps/reviewer/test/operational-review-workspace-contract.test.mjs
git diff --check
```

## Risks / open questions

- Ręczny odbiór na wskazanym imporcie nie jest gwarantowany, gdy jego kolejka nie zawiera już pozycji; nie wolno tworzyć ani zmieniać danych tylko do testu UI.

## Outcome

### Changed

- Dodano czyste funkcje określające wnętrze quada i jego sztywną translację w
  source-space. Dla kompletnej planszy cały quad zatrzymuje się na granicy
  zdjęcia; dla jawnie niepełnej zachowuje dozwolony obszar poza źródłem.
- Edytor kolejki rozpoznaje trzy gesty: numerowany narożnik koryguje tylko
  perspektywę, wnętrze siatki przy wyłączonym checkboxie przesuwa cały obrys,
  a po włączeniu „Aktywnego przesuwania” drag poza narożnikiem przesuwa tylko
  viewport.
- Tekst ekranu opisuje nowe sterowanie; nie zmieniono API, preview ani zapisu.

### Verification results

- `pnpm --filter @game-predictor/reviewer test` — 203/203 zaliczone.
- `pnpm dlx prettier@3.5.3 --check ...` — zielone dla czterech zmienionych
  plików Reviewera.
- `git diff --check` — zielone.
- Regresje obejmują zachowanie perspektywy, wspólne ograniczenie do krawędzi,
  niepełny quad poza źródłem i kontrakt edytora.

### Not completed

- Lokalny `pnpm --filter @game-predictor/reviewer lint` i `typecheck` nie
  wystartowały: w checkoutcie brakuje binariów `eslint` i `tsc`; jednorazowy
  ESLint uruchomiony poza projektem także zakończył się błędem brakującej
  zależności `estraverse`. Nie zmieniano zależności projektu.
- Nie wykonano ręcznej próby na wskazanym imporcie, bo po odświeżeniu jego
  kolejka nie miała już pozycji; nie tworzono ani nie modyfikowano danych
  użytkownika tylko do odbioru UI.

### Documentation updates

- `ai_docs/process/CURRENT_STATE.md`

### Recommended next task

- Brak w tym zakresie; ręczny odbiór wykonać na rzeczywistej pozycji kolejki,
  gdy będzie dostępna.
