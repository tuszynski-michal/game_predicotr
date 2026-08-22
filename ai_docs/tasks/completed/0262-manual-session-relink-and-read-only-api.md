---
title: TASK-0262 manual session relink and read-only API stability
status: done
release: "0.7"
last_updated: 2026-08-22
---

# TASK-0262 — Odzyskiwanie sesji lokalnej i stabilne odczyty API

## Goal

Usunąć regresję wznowienia ręcznej selekcji po utracie uchwytu folderu oraz
deadlocki wywoływane przez read-only ekrany jakości podczas pracy workerów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- ponowne wskazanie nieaktualnego folderu źródłowego lub wynikowego bez utraty
  decyzji, zakresu i kursora,
- trwałe zapisanie naprawionych uchwytów w IndexedDB,
- read-only preview jakości bez `FOR UPDATE`,
- zachowanie blokady pełnego snapshotu wyłącznie podczas zamrażania kohorty,
- montowanie tylko rozwiniętej sekcji gry, aby zamknięte ekrany nie uruchamiały
  równoległych requestów.

## Out of scope

- zmiana danych review, aktywnych modeli lub jobów,
- restart albo modyfikacja workerów,
- zmiana kontraktu odpowiedzi API/OpenAPI,
- automatyczne odzyskiwanie dostępu do folderu bez zgody przeglądarki.

## Acceptance criteria

- [x] błąd `NotFoundError` wskazuje, który folder trzeba wybrać ponownie,
- [x] ponowne wskazanie folderu wznawia istniejący stan zamiast tworzyć nowy,
- [x] naprawione uchwyty są zapisane na następny restart,
- [x] GET preview/model-quality nie blokuje rekordów plansz ani gry,
- [x] freeze nadal używa transakcyjnego, blokowanego snapshotu,
- [x] zamknięte sekcje gry nie uruchamiają własnych requestów,
- [x] właściwe testy Admina i API oraz lint/typecheck przechodzą.

## Outcome

Workspace pozwala ponownie wskazać brakujące źródło lub wynik bez resetowania
stanu i zapisuje naprawione uchwyty. Admin montuje wyłącznie rozwiniętą sekcję
Gry. Podgląd kohorty używa lekkiej projekcji około 67 tys. historycznych stanów
i pełnych danych tylko dla rozstrzygniętych pozycji; zachowanie manifestu
potwierdza test równoważności. Rzeczywiste endpointy zwracają HTTP 200 zamiast
timeoutu i błędu PostgreSQL 65 535 parametrów. Panel jakości nie wysyła już
drugiego równoległego requestu budującego identyczny snapshot, a ciężki panel
siatki montuje dopiero po odpowiedzi podstawowej jakości.

Walidacja: 233 testy Admina, 12 celowanych testów API, ESLint, TypeScript,
Prettier i Ruff przeszły. Mypy pozostaje z 27 istniejącymi błędami środowiska
`py.typed` workera oraz jednym istniejącym `unused-ignore` poza zmienionym
zakresem.
