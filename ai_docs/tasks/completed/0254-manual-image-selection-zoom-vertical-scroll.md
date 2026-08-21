---
title: TASK-0254 manual image selection zoom vertical scroll
status: done
release: "0.7"
last_updated: 2026-08-21
---

# TASK-0254 — Przewijanie pionowe powiększonego zdjęcia ręcznej selekcji

## Goal

Powiększony JPEG w lokalnej ręcznej selekcji pozostaje dostępny od góry do
dołu. Operator może przewijać go pionowo, a szeroki obraz pozostaje
wyśrodkowany i jest celowo przycinany wyłącznie po bokach.

## Context

Obecny zoom używa CSS `transform: scale(...)`. Transformacja zmienia wyłącznie
warstwę wizualną i nie powiększa wymiarów scrollowalnego układu, dlatego część
obrazu ponad viewportem jest odcinana bez możliwości przewinięcia.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- zastąpić prezentacyjny `transform` wymiarami layoutu odpowiadającymi zoomowi,
- utworzyć ograniczony viewport obrazu z pionowym scrollowaniem i bez
  poziomego scrolla,
- utrzymać poziome wyśrodkowanie zdjęcia przy obcięciu obu boków,
- zachować informację pełnoekranową, nawigację, skróty i zapis oryginalnych
  bajtów JPEG-a,
- uzupełnić test kontraktowy UI oraz dokumentację ręcznej selekcji.

## Out of scope

- zmiana poziomów zoomu 100–3000%, nawigacji, IndexedDB, folderów, manifestu
  albo zapisu plików,
- API, backend, staging, worker i import plansz,
- ręczne obracanie, kadrowanie lub zmiana obrazu źródłowego.

## Acceptance criteria

- [x] Po powiększeniu operator może przewinąć do górnej i dolnej części JPEG-a.
- [x] Widok nie oferuje poziomego przewijania; zbyt szerokie fragmenty są
      przycinane symetrycznie po bokach, z centrum obrazu w viewportcie.
- [x] Przy 100% obraz zachowuje dotychczasowe dopasowanie do podglądu.
- [x] Pełny ekran nadal pokazuje zakres, pozycję i nazwę pliku; informacja
      pozostaje widoczna podczas pionowego scrolla obrazu.
- [x] Zoom nie modyfikuje źródłowego Blobu, nazwy pliku ani działania Enter,
      F, Tab, A/Ctrl+Z i strzałek.
- [x] Testy Admina, typecheck, celowany lint i formatowanie przechodzą.

## Expected files

- `apps/admin/src/features/manual-image-selection/manual-image-selection-workspace.tsx`
- `apps/admin/src/app/globals.css`
- `apps/admin/test/manual-local-image-selection.test.mjs`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Outcome

- Zastąpiono `transform: scale(...)` wymiarami layoutu obliczanymi z naturalnego
  rozmiaru JPEG-a, dostępnego viewportu i aktualnego poziomu zoomu.
- Wewnętrzny viewport przewija wyłącznie pionowo; obraz jest centrowany w osi X,
  a szeroki nadmiar jest ukrywany po bokach. Zmiana zdjęcia wraca na jego górę.
- Pełny ekran ma osobny, nieprzewijalny kontener z informacją nad wewnętrznym
  viewportem, dlatego zakres, pozycja i nazwa nie znikają podczas przewijania.
- Uruchomiono: `npm.cmd test --workspace @game-predictor/admin` (221/221),
  `npm.cmd run typecheck --workspace @game-predictor/admin`, celowany ESLint,
  Prettier check, `git diff --check` oraz build Admina.
- Nie zmieniono API, backendu, stagingu, zapisu Blobów, skrótów, ani niezwiązanej
  zmiany `apps/admin/next-env.d.ts`.
