---
title: TASK-0259 manual selection keyboard step
status: done
release: "0.7"
last_updated: 2026-08-21
---

# TASK-0259 — Klawiaturowa zmiana skoku ręcznej selekcji

## Goal

Operator ma zmieniać wartość skoku bez odrywania rąk od klawiatury:
`ArrowDown` przechodzi do następnej wartości selectu, a `ArrowUp` do
poprzedniej.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- jedna kanoniczna lista wartości `1, 2, 3, 4, 5, 6, 7, 10, 15, 20`,
- czysta funkcja wyboru sąsiedniej wartości z ograniczeniem na krańcach,
- globalne skróty góra/dół poza kontrolkami formularza,
- trwały zapis przez istniejący mechanizm sesji,
- testy zachowania oraz aktualizacja dokumentacji.

## Out of scope

- zmiana znaczenia lewo/prawo, Enter, Tab, A, F albo Ctrl+Z,
- zmiana bieżącego obrazu lub zakresu przy regulacji skoku,
- nowa migracja IndexedDB, API, worker albo backend,
- przejęcie pionowych strzałek, gdy fokus pozostaje w formularzu.

## Acceptance criteria

- [x] `2 + ArrowDown` ustawia `3`.
- [x] `3 + ArrowUp` ustawia `2`.
- [x] `7 + ArrowDown` wybiera następną wartość listy, czyli `10`.
- [x] Granice `1` i `20` nie wychodzą poza listę.
- [x] Wybór jest zapisywany w istniejącym stanie sesji.
- [x] Testy, typecheck, lint i build Admina przechodzą.

## Outcome

- Lista skoków została przeniesiona do współdzielonej logiki domenowej, aby
  select, normalizacja i klawiatura nie mogły się rozjechać.
- Pionowe strzałki zmieniają tylko skok. Handler nadal ignoruje formularze i
  elementy edytowalne.
- Przeszło `225/225` testów Admina, typecheck, build oraz celowany ESLint z
  zerem błędów i jednym istniejącym ostrzeżeniem `<img>` dla lokalnego obrazu.
