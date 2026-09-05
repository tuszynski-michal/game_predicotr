---
title: Shadow structured lattice refinement
status: done
last_updated: 2026-09-04
---

# TASK-0447 — Integracja produkcyjna i tryb shadow

## Status

`done`

## Goal

Uruchamiać refiner v3 jako przypięty, checksummowany pomiar równoległy dla
nowych runów structured shadow, bez zmiany produkcyjnych cropów v2.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0445-separate-board-frame-and-symbol-lattice.md`
- `ai_docs/tasks/completed/0446-refine-structured-symbol-lattices.md`

## Scope

- nowy, niezmienny snapshot konfiguracji kandydata v3;
- wynik shadow z diagnostyką i fail-closed powodami odroczenia;
- zachowanie produkcyjnej geometrii i cropów bieżącego primary;
- pokazanie obszaru analizy i propozycji siatki w lokalnym Reviewerze;
- inicjalizacja edycji i reset z propozycji `symbolGridQuad`;
- niezmieniony replay już przypiętych kandydatów v2.

## Out of scope

- aktywacja v3 jako źródła cropów;
- automatyczne przeliczanie istniejących importów;
- migracja bazy;
- modyfikacja zatwierdzonych decyzji.

## Acceptance criteria

- [x] nowy run structured shadow przypina kandydat v3, a historyczny v2 nadal
      wybiera własny adapter;
- [x] checkpoint v3 jest checksummowany i powtarzany bez zmiany między etapami;
- [x] kandydat zapisuje oba quady, diagnostykę i dokładny powód odroczenia;
- [x] shadow nie zmienia produkcyjnych cropów, statusów ani decyzji;
- [x] Reviewer pokazuje `analysisQuad` i końcową propozycję osobno;
- [x] edycja i reset rozpoczynają się od bezpiecznego `symbolGridQuad`, jeśli
      kandydat go dostarczył;
- [x] operator widzi powód odroczenia refiner v3.

## Verification

Skoncentrowane testy workera, API i Reviewera, Ruff, mypy, lint oraz typecheck
zmienionych modułów.

## Outcome

### Changed

- Nowe runy structured shadow przypinają kandydat v3; zapisany snapshot v2
  nadal kieruje do historycznego adaptera.
- Wynik v3 jest checksummowany, walidowany i przenoszony bez zmian między
  detekcją oraz geometrią komórek. Primary nadal wykonuje dotychczasowy tor.
- Reviewer pokazuje diagnostyczny obszar analizy, propozycję siatki, status i
  powód odroczenia. Ręczna rewizja ma pierwszeństwo.

### Verification results

- Pytest: `92 passed` dla refiner v3, replay v2, workflow produkcyjnego, API
  jobów i API kolejki geometrii.
- Reviewer state tests: `12 passed`.
- Ruff: passed.
- Reviewer lint, typecheck i production build: passed.
- OpenAPI i wygenerowany klient: current.
- Prettier dla zmienionych plików: passed. Globalny `format:check` nadal
  raportuje pięć wcześniejszych, niezmienionych plików Admina.
- Skoncentrowany mypy nowego modułu v3: passed. Pełny mypy nie zwrócił wyniku
  przez 60 sekund i został bezpiecznie przerwany zgodnie z limitem repo.

### Not completed

- Nie aktywowano v3 i nie przeliczono żadnego importu. Odbiór na rzeczywistym,
  source-disjoint korpusie należy do TASK-0448.

### Documentation updates

- Requirements, architecture, API contract, Decision Log i Current State.

### Recommended next task

- TASK-0448 — odbiór i bezpieczna aktywacja.
