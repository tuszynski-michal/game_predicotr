---
title: TASK-0435 — Kotwica cold-startu z bieżącego stagingu v0.10
status: done
last_updated: 2026-09-04
---

# TASK-0435 — Kotwica cold-startu z bieżącego stagingu v0.10

## Goal

Naprawić preflight nowej gry, aby ręcznie zatwierdzona geometria źródła z
bieżącego browser stagingu mogła zostać użyta jako kotwica przed skopiowaniem
JPEG-a do managed originals.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- rozwiązywanie kotwicy najpierw z bieżącego checksum-bound stagingu,
- zachowanie managed originals jako źródła kotwic historycznych,
- jawne ponowienie failed preflightu w panelu importu,
- test regresyjny rzeczywistego rejestratora i testy błędów źródła.

## Out of scope

- zmiana algorytmu rejestracji lub progów geometrii,
- kopiowanie całego stagingu podczas preflightu,
- ponowienie produkcyjnego joba bez osobnej zgody operatora,
- zmiany danych gier `77` i `777`.

## Definition of Done

- override bieżącego stagingu nie wymaga istniejącego managed original,
- brak bieżącego JPEG-a i brak historycznej kotwicy zachowują odrębne błędy,
- failed preflight można ponowić z panelu bez tworzenia drugiego joba,
- testy workera i Admina oraz właściwy lint, typecheck i build przechodzą,
- dokumentacja opisuje kolejność rozwiązywania kotwicy.

## Outcome

- Pierwszy rejestrator preflightu rozwiązuje kotwice z bieżącego stagingu przed
  historycznym managed original; nie kopiuje zdjęć przed importem.
- Brak bieżącego źródła ma stabilny kod
  `IMAGE_PAGE_GEOMETRY_SOURCE_UNAVAILABLE`, a brak kotwicy historycznej nadal
  kończy się `IMAGE_PAGE_GEOMETRY_ANCHOR_UNAVAILABLE`.
- Panel importu ponawia istniejący failed preflight przez `retryJob` zamiast
  odzyskiwać ten sam terminalny stan.
- Weryfikacja: 10 testów preflightu, 56 testów powiązanego API/workera i 386
  testów Admina przeszło; Ruff, ESLint, TypeScript, OpenAPI i build Admina są
  zielone.
- Pełny mypy został przerwany po 60 sekundach bez wyniku. Ograniczony przebieg
  `--follow-imports=skip` wskazał wyłącznie dwa wcześniejsze `no-any-return` na
  istniejących wywołaniach `np.asarray`; zmieniona logika nie dodała błędu.
- Nie ponowiono joba `ef3ac243-a8a0-4268-87a8-e2c8ecd17b9e` i nie zmieniono
  danych gry ani stagingu.
