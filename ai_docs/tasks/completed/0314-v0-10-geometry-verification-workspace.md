---
title: TASK-0314 — Weryfikacja geometrii całego źródła 0.10
status: done
last_updated: 2026-08-29
---

# TASK-0314 — Weryfikacja geometrii całego źródła 0.10

## Goal

Rozszerzyć lokalny `grid-review-workspace` Reviewera tak, aby operator
weryfikował komplet aktywnych plansz jednego zdjęcia źródłowego, a nie tylko
pojedynczą planszę.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-254–D-258)
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- pełny, EXIF-oriented obraz źródłowy z overlayem wszystkich aktywnych quadów,
  linii topologii, slotów, confidence i reason codes;
- wybór planszy, edycja jej quada, drag narożników i całego quada,
  cofnięcie oraz reset do automatu;
- podgląd A/B bez trwałego overlay JPEG;
- zatwierdzenie, odrzucenie oraz zapis poprawionej geometrii z przejściem do
  następnego źródła;
- klawiatura `Enter`/`F`, ochrona przed podwójnym submit oraz liczniki
  board/image-level oparte na trwałych statusach.

## Out of scope

- nowy system stylów;
- wirtualizacja list Weryfikacji Symboli (TASK-0315);
- rollout/backfill virtual geometry (TASK-0317);
- tworzenie trwałych JPEG-ów z overlayem.

## Invariants

- zdalny Reviewer nie otrzymuje endpointów ani mutacji walidacji geometrii;
- lokalna akcja jest bound do bieżącej geometrii, topologii i checksummy źródła;
- nie można utworzyć trwałego obrazka overlay;
- aktywne sloty są pokazywane row-major i nie dopuszczają syntetycznych plansz;
- niezmienione zachowanie legacy pozostaje dostępne dla historycznych danych.

## Outcome

Zrealizowano w `v0.10.7`:

- lokalny workspace grupuje kolejkę po `sourceImageId` i pobiera najwyżej
  dziewięć aktualnych slotów źródła;
- API/klient przekazują source identity, slot, asset mode, silnik, confidence
  oraz reason codes, a cursor wiąże scope źródła;
- canvas ma overlay wszystkich slotów, wybór planszy, zoom/pan, ukrywanie
  overlayu, drag, undo/reset do automatu i A/B preview bez trwałego JPEG;
- `Enter`/`F`, zatwierdzenie i odrzucenie całego źródła używają submit guard;
  liczniki pokazują stan globalny i board/image-level;
- zapis legacy zachowuje dotychczasowy manualny workflow i przechodzi do
  następnego źródła.

Ręczny zapis `virtual_source` pozostaje fail-closed: obecny legacy writer
utrwalałby fizyczne cropy zamiast zachować virtual provenance. Workspace nadal
pozwala takie źródło obejrzeć, porównać A/B, zatwierdzić albo odrzucić; pełny
manualny write-through wirtualnej geometrii wymaga transactional recropu i jest
świadomie odłożony do TASK-0317.

Weryfikacja: focused API `7 passed`; focused Reviewer `10 passed`; OpenAPI i
generated client są zgodne; typecheck i lint Reviewera przechodzą. Pełny suite
Reviewera ma istniejącą, niezwiązaną awarię statycznego testu zdalnej selekcji
(`remote source navigation stays in natural folder order for descending ranges`).
