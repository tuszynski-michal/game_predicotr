---
title: TASK-0501 — Jednoznaczne przypisywanie modeli do zadań
status: done
last_updated: 2026-09-07
---

# TASK-0501 — Jednoznaczne przypisywanie modeli do zadań

## Status

`done`

## Goal

Każdy plan kończy się kompletną i jednoznaczną mapą tasków na model, poziom
rozumowania oraz wymagany dodatkowy review.

## Context

Dotychczasowy standard wymaga rekomendowanego wykonania, ale dopuszcza jedną
ogólną rekomendację dla wielu tasków. Utrudnia to przekazanie planu do wykonania
bez ponownego dobierania modelu.

## Dependencies / entry conditions

- Zaakceptowany plan TASK-0501.
- Aktualny standard planowania i szablon taska.
- Brak zależności od kodu aplikacji, API, bazy danych i uruchomionych usług.

## Recommended execution

`gpt-5.6-sol` z poziomem `low`: zmiana jest ograniczona do jednoznacznej
dokumentacji procesowej. Dodatkowy review nie jest wymagany.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Obowiązkowa końcowa sekcja planu `Przypisanie modeli do zadań`.
- Jeden jawny wpis dla każdego taska.
- Zgodność końcowej mapy z sekcją `Recommended execution` taska.
- Zasady niedostępności modelu i rozbieżności konfiguracji.

## Out of scope

- Automatyczna zmiana modelu, uruchamianie agentów lub delegowanie pracy.
- Zmiany aplikacji, API, bazy danych i konfiguracji usług.
- Stały ranking modeli lub cennik.

## Acceptance criteria

- [ ] `AGENTS.md` wymaga końcowej mapy dla każdego planu.
- [ ] `PLAN_STANDARD.md` definiuje wszystkie kolumny oraz przypadek planu bez
      numerowanych tasków.
- [ ] Nie można pominąć taska ani zastąpić modelu odwołaniem „ten sam model”.
- [ ] `TASK_TEMPLATE.md` wymaga zgodności z końcową mapą planu.
- [ ] Niedostępność modelu albo rozbieżność blokuje rozpoczęcie taska.
- [ ] `CURRENT_STATE.md` opisuje obowiązującą regułę.

## Technical notes

Końcowa tabela planu jest źródłem prawdy dla przypisania wykonawczego. Sekcja
`Recommended execution` w tasku zachowuje uzasadnienie i warunek eskalacji, ale
nie może zmieniać modelu ani poziomu rozumowania wskazanych w zaakceptowanym
planie. Aktualizacja przypisania wymaga kompletnej aktualizacji planu oraz taska.

## Expected files

- Istniejące: `AGENTS.md`.
- Istniejące: `ai_docs/process/PLAN_STANDARD.md`.
- Istniejące: `ai_docs/process/TASK_TEMPLATE.md`.
- Istniejące: `ai_docs/process/CURRENT_STATE.md`.
- Nowe: `ai_docs/tasks/0501-plan-task-model-assignment.md`.

## Test cases

- Plan z wieloma taskami zawiera dokładnie jeden wiersz na każdy task.
- Plan z jednym zadaniem bez numeru zawiera jeden wiersz opisujący całe
  wykonanie.
- Ogólne odwołanie „jak wyżej” albo „ten sam model” nie spełnia standardu.
- Rozbieżność modelu lub reasoning między planem i taskiem blokuje wykonanie.

## Verification

```powershell
rg -n "Przypisanie modeli do zadań|Dodatkowy review|ten sam model" AGENTS.md ai_docs/process/PLAN_STANDARD.md ai_docs/process/TASK_TEMPLATE.md
npm run format:check
```

Kontrola tekstowa musi wykazać regułę w każdym dokumencie procesowym, a format
check zakończyć się kodem zero. Testy aplikacji nie są wymagane.

## Risks / open questions

- Nazwa wskazanego modelu może przestać być dostępna; standard wymaga wtedy
  zatrzymania taska i aktualizacji planu zamiast niejawnego zamiennika.

## Outcome

TASK-0501 ukończony.

### Changed

- `AGENTS.md` wymaga kompletnej końcowej mapy modeli dla każdego planu.
- `PLAN_STANDARD.md` definiuje kolumny, liczność wierszy, źródło prawdy,
  obsługę planu bez numerowanych tasków oraz blokadę przy rozbieżności lub
  niedostępności modelu.
- `TASK_TEMPLATE.md` wymaga jawnego modelu i reasoning zgodnego z planem.
- `CURRENT_STATE.md` opisuje nową obowiązującą regułę.

### Verification results

- Celowany `rg` potwierdził obecność reguły i zakaz skrótów w trzech źródłach
  procesu oraz `CURRENT_STATE.md`.
- Celowany Prettier check pięciu zmienianych dokumentów zakończył się kodem 0.
- `git diff --check` zakończył się kodem 0.
- Pełny `npm run format:check` pozostaje czerwony z powodu 35 wcześniejszych,
  niezwiązanych plików; jedyny wykryty plik bieżącego taska (`AGENTS.md`) został
  poprawiony i przechodzi kontrolę celowaną.

### Not completed

- Nie zmieniano ani nie formatowano wcześniejszych plików spoza zakresu.

### Documentation updates

- Zaktualizowano nadrzędne instrukcje, standard planów, szablon taska i bieżący
  stan projektu.

### Recommended next task

- Brak; następny task wynika z osobnej decyzji użytkownika.
