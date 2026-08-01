---
title: TASK-0144 model quality workspace and cohort freeze
status: todo
last_updated: 2026-08-01
---

# TASK-0144 — Model quality workspace and cohort freeze

## Status

`todo`

## Goal

Dodać do Admina panel jakości rozpoznawania, w którym właściciel widzi gotowość
danych i jawnie zamraża kohortę przez akcję `Ulepsz rozpoznawanie`.

## Context

Liczby 100 i 1000 mają pomagać zaplanować iteracje, ale nie mogą uruchamiać
uczenia automatycznie. Przed kosztownym jobem użytkownik musi zobaczyć pokrycie
klas, źródeł i różnicę względem poprzedniej kohorty.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_06_6_EXECUTION_PLAN.md`
- `ai_docs/tasks/0143-cumulative-verified-training-cohort-contract.md`

## Scope

- dodać read-only podsumowanie aktywnego modelu dla wybranej gry,
- pokazać liczbę pełnych zweryfikowanych plansz, nowe elementy od ostatniej
  kohorty, źródła oraz liczności per symbol,
- pokazać ostrzeżenia o klasach i źródłach o zbyt małym pokryciu,
- pokazać doradcze progi 100 i 1000 bez automatycznego triggera,
- dodać preview elementów wchodzących, wykluczonych i chronionych,
- po potwierdzeniu utworzyć niezmienną kohortę oraz szkic iteracji modelu,
- nie uruchamiać drugiej operacji dla tej samej gry, jeżeli konfliktuje z
  aktywnym ciężkim jobem.

## Out of scope

- implementacja treningu,
- obliczanie metryk kandydata,
- aktywacja modelu,
- przeliczanie oczekujących elementów.

## Acceptance criteria

- [ ] Panel działa w kontekście jednej aktywnej gry i nie miesza danych gier.
- [ ] UI pokazuje aktywną wersję, checksumę, liczby ogółem i delta oraz pokrycie
      wszystkich symboli.
- [ ] Preview rozdziela dane treningowe, odrzucone, niekompletne, oczekujące i
      wszystkie chronione decyzje człowieka.
- [ ] `Ulepsz rozpoznawanie` wymaga jawnego potwierdzenia manifestu, ale nie
      wymaga osiągnięcia dokładnie 100 albo 1000 plansz.
- [ ] Powtórzenie requestu z tym samym kluczem idempotencji nie tworzy duplikatu.
- [ ] Stan operacji nie blokuje trwale UI po błędzie, odświeżeniu ani zmianie
      gry.
- [ ] Generowany klient OpenAPI jest jedynym źródłem typów frontendu.

## Technical notes

Funkcję istniejącego panelu kohort w Reviewerze należy wykorzystać albo
wydzielić, zamiast tworzyć drugi rozbieżny kontrakt. Sam Reviewer pozostaje
narzędziem rozstrzygania, a zarządzanie modelem należy do Admina.

## Expected files

- `apps/admin/src/features/model-quality/`
- `apps/admin/src/app/globals.css`
- `apps/admin/test/`
- `services/api/src/game_predictor_api/api/`
- `services/api/src/game_predictor_api/application/`
- `services/api/tests/`
- `packages/admin-api-client/`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm.cmd test --workspace @game-predictor/admin
npm.cmd run typecheck --workspace @game-predictor/admin
npm.cmd run lint --workspace @game-predictor/admin
python -m pytest services/api/tests -q
npm.cmd run openapi:check
```

## Risks / open questions

- Przy bardzo małej liczbie źródeł panel ma ostrzegać, nie ukrywać problemu
  przez samą wysoką liczbę cropów.

## Outcome

Do uzupełnienia po realizacji.
