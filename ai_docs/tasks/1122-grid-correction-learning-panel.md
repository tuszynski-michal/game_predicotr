---
title: Uproszczony panel i zastosowanie modelu
status: in_progress
last_updated: 2026-11-02
---

# TASK-1122 — Uproszczony panel i zastosowanie modelu

## Status

`in_progress`

## Goal

Wykonać T3 zaakceptowanego planu uczenia wspólnego modelu siatek z zapisanych korekt.

## Context

Operator ma ponad 100 poprawionych plansz Mumie A2 i potrzebuje uczenia bez ręcznej rejestracji nagrań. Liczba jest deklaracją, nie pomiarem kwalifikujących się danych.

## Dependencies / entry conditions

TASK-1121 ukończony z audytem; istniejące API i raporty pozostają zgodne.

Wyjątek jawnie zlecony przez operatora po limicie Anthropic: „Kontynuuj a potem
audyt”. Implementację T3 rozpocząć na odizolowanej kopii stabilnego T2; audyt
i commit T2 nadal muszą poprzedzić integrację, audyt i commit T3. Nie pomijać
żadnego audytu ani zastępować Opus innym modelem.

## Recommended execution

gpt-6.1-sol/high, według tabeli planu. Obowiązkowy niezależny audyt Claude Code claude-opus-5-5/high przed commitem; P0/P1 blokują commit. Niedostępność przypisanego modelu wymaga jawnej aktualizacji, bez niejawnej zamiany.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- [Plan i pełny zakres T3](../delivery/GRID_CORRECTIONS_LEARNING_PLAN_20261102.md)
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`, `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/VISION_LAB.md`, `ai_docs/architecture/CODE_MAP.md`
- [D-554](../process/decisions/DECISION_LOG_2026.md#d-554--nagrania-i-ochrona-danych-kontrolnych-geometrii-v3)
- [D-556](../process/decisions/DECISION_LOG_2026.md#d-556--niezmienne-kohorty-geometrii-v3-i-aktualność-dowodów)
- [D-559](../process/decisions/DECISION_LOG_2026.md#d-559--ocena-kandydata-geometrii-v3-per-gra-i-most-aktualności-dowodów)

## Scope

Pełna sekcja T3 planu; zasady i minima z planu są obowiązujące.

## Out of scope

Trening na danych operatora, zmiana defaultu lub przypisań, migracja bazy operatora, restart usług, merge/push; klasyfikator symboli i uczenie detektora całego ekranu.

## Acceptance criteria

- [ ] GET-only otwarcie; prowadzony workflow; full API vertical; lost response/restart bez duplicates; apply osobne i jawne, actual-assigned baseline, partial success.
- [ ] Właściwe testy, lint/typecheck i dokumentacja.
- [ ] Audyt Opus 5.5/high bez otwartych P0/P1.
- [ ] Outcome, task-close, osobny wersjonowany commit i record-hash.

## Technical notes

Przed kodowaniem ponownie odczytać ten task i sekcję T3 planu. Chronić istniejące polityki/snapshoty/raporty; nowe reguły wersjonowane. API zmieniać jednym pionem. Mutacje operatora wyłącznie z osobną zgodą. Podgląd nie tworzy dowodu faktycznego użycia danych.

## Expected files

Istniejące moduły wejściowe (ścieżki usług względem ich katalogów src): apps/admin/src/features/model-quality/grid-model-workspace.tsx; packages/admin-api-client. Nowe pliki wskazać w Outcome przed audytem.

## Test cases

Scenariusze T3 i T4 w planie: minima, brak danych, nowe/stare polityki, aliasy, restart, utracona odpowiedź, konflikty rewizji; zakres testów odpowiedni do zmienionego pionu.

## Verification

Polecenia ustalić z package.json/pyproject i istniejących testów. Każda skończona komenda z timeout <=120 s; build po uprzedzeniu, audyt <=600 s zgodnie ze skillem. Nie uruchamiać szerokich benchmarków.

## Risks / open questions

Preflight i rzeczywista kwalifikacja danych mogą zatrzymać implementację przed błędną obietnicą użycia korekt. Wynik pomiaru należy zapisać w Outcome.

## Outcome

W trakcie / oczekuje.
