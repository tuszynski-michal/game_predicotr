---
title: Odbiór i dokumentacja uczenia z korekt
status: done
last_updated: 2026-11-02
---

# TASK-1123 — Odbiór i dokumentacja uczenia z korekt

## Status

`done`

## Goal

Wykonać T4 zaakceptowanego planu uczenia wspólnego modelu siatek z zapisanych korekt.

## Context

Operator ma ponad 100 poprawionych plansz Mumie A2 i potrzebuje uczenia bez ręcznej rejestracji nagrań. Liczba jest deklaracją, nie pomiarem kwalifikujących się danych.

## Dependencies / entry conditions

TASK-1120–1122 ukończone z audytami; bez zgód na rzeczywisty trening/restart/migrację operatora.

## Recommended execution

gpt-6.1-sol/high, według tabeli planu. Obowiązkowy niezależny audyt Claude Code claude-opus-5-5/high przed commitem; P0/P1 blokują commit. Niedostępność przypisanego modelu wymaga jawnej aktualizacji, bez niejawnej zamiany.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- [Plan i pełny zakres T4](../../delivery/GRID_CORRECTIONS_LEARNING_PLAN_20261102.md)
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`, `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/VISION_LAB.md`, `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/quality/TASK-1120_AUDIT_claude-opus-5-5.md`
- `ai_docs/quality/TASK-1121_VERIFICATION.md`
- `ai_docs/quality/TASK-1122_AUDIT_claude-opus-5-5.md`
- `ai_docs/quality/TASK-1122_VERIFICATION.md`
- [Raport odbioru](../../quality/GRID_CORRECTIONS_LEARNING_ACCEPTANCE_20261102.md)
- [D-554](../../process/decisions/DECISION_LOG_2026.md#d-554--nagrania-i-ochrona-danych-kontrolnych-geometrii-v3)
- [D-556](../../process/decisions/DECISION_LOG_2026.md#d-556--niezmienne-kohorty-geometrii-v3-i-aktualność-dowodów)
- [D-559](../../process/decisions/DECISION_LOG_2026.md#d-559--ocena-kandydata-geometrii-v3-per-gra-i-most-aktualności-dowodów)

## Scope

Odbiór obejmuje także P2-3/P2-5/P2-6 R2 TASK-1122: konkurencyjne resume oraz
odczyt historii przy konflikcie publikacji i nieukończonych porównaniach.
Poprawki z regresjami w T4, bez kolejnej rundy zmian T3.

Pełna sekcja T4 planu; zasady i minima z planu są obowiązujące.

## Out of scope

Trening na danych operatora, zmiana defaultu lub przypisań, migracja bazy operatora, restart usług, merge/push; klasyfikator symboli i uczenie detektora całego ekranu.

## Acceptance criteria

- [x] Pokrycie całego DoD planu, stare kontrakty i historia; jawne wyniki testów i niewykonanych operacji; audyt Opus 5.5/high.
- [x] Właściwe testy, lint/typecheck i dokumentacja.
- [x] Audyt Opus 5.5/high bez otwartych P0/P1.
- [x] Outcome, task-close, osobny wersjonowany commit i record-hash.

## Technical notes

Przed kodowaniem ponownie odczytać ten task i sekcję T4 planu. Chronić istniejące polityki/snapshoty/raporty; nowe reguły wersjonowane. API zmieniać jednym pionem. Mutacje operatora wyłącznie z osobną zgodą. Podgląd nie tworzy dowodu faktycznego użycia danych.

## Expected files

Istniejące: application/grid_correction_apply.py, test_grid_correction_apply.py,
integration/test_grid_correction_apply_postgres.py, test_grid_model_evaluation_bridge_postgres.py,
test_grid_model_evaluation_e2e_postgres.py, test_grid_training_cohort_e2e_postgres.py;
wymagania ADMIN_APP, architektura VISION_LAB i mapa kodu. Proponowany nowy raport:
ai_docs/quality/GRID_CORRECTIONS_LEARNING_ACCEPTANCE_20261102.md.

## Test cases

Scenariusze T1–T4 w planie: minima, brak danych, nowe/stare polityki, aliasy, restart, utracona odpowiedź, konflikty rewizji; zakres testów odpowiedni do zmienionego pionu.

## Verification

Polecenia ustalić z package.json/pyproject i istniejących testów. Każda skończona komenda z timeout <=120 s; build po uprzedzeniu, audyt <=600 s zgodnie ze skillem. Nie uruchamiać szerokich benchmarków.

## Risks / open questions

Preflight i rzeczywista kwalifikacja danych mogą zatrzymać implementację przed błędną obietnicą użycia korekt. Wynik pomiaru należy zapisać w Outcome.

## Outcome

Commit: v1.7.520 / `4672c0896f767efd17234328a9cc219975acd067`.

### Changed

Zamknięto P2-3/P2-5/P2-6 R2 T3: guard konkurencyjnego resume, odczyt historii
mimo obcego dowodu i adopcja GET dopiero po wcześniejszych porównaniach.
Zaktualizowano Windows fixture paths oraz ścisłe oczekiwanie aktualnej głowy Alembic, bez
osłabienia starych asercji lub zmniejszenia danych. Raport odbioru ma mapę
wymaganie–test oraz jawne granice dowodu i operacje operatora poza zakresem.

### Verification results

33 unit/worker PASS (3.19 s), 2 APPLY PG PASS (42.28 s), trzy legacy PG PASS
(po P2: bridge 30.26 s, evaluation 72.69 s, cohort 84.13 s), z nowym procesem datasetu i
stale-ready rollback. Ruff zmienionych części i scoped mypy jednego produkcyjnego
modułu PASS. OpenAPI i SDK drift PASS; frontend niezmieniony od aktualnego
buildu T3 PASS 17.52 s. Dokładne komendy i ograniczenia w raporcie odbioru.
Pełny projektowy mypy oraz szersza próba z wyjątkiem Torch przekroczyły 110 s;
nie deklarujemy ich PASS i nie zmieniamy globalnego config. P2-8 T1 zamknięte
pełnymi legacy przebiegami; pozostałe ryzyko P2-9 akceptowane po ograniczonej
obserwacji czasów, bez deklaracji porównawczego benchmarku.

Audyt [Claude Code Opus 5.5/high](../../quality/TASK-1123_AUDIT_claude-opus-5-5.md):
PASS, runda 1, bez P0/P1. P2-3: świadomie zaakceptowany brak pełnego mypy PASS;
wyniki scoped oraz granice dowodu są jawne. P2-1 i P2-2: jedna runda poprawek
fixture po audycie zakończona PASS trzech pełnych testów, bez zmiany produkcyjnego
kodu. Wspólny env parent ma dwa odrębne podkatalogi UUID i niezmienione journale
poprzedniego testu; expected head pochodzi z ScriptDirectory. Bez nowej rundy audytu
dla samych P2. Dalszy pełny baseline mypy zapisano w CURRENT_STATE.

### Not completed

Nie wykonano migracji operatora, restartu usług, rzeczywistego treningu/aktywacji
ani merge/push. Pełny baseline mypy pozostaje otwarty poza tym taskiem; wymaga
uzgodnionego dłuższego limitu. Migracja operatora i wdrożenie pozostają osobnymi operacjami po akceptacji wyniku.

### Assumptions recorded before coding

Rozpoczęto po commitach T1–T3 i ich audytach PASS. Lead realizuje P2 z R2 T3
oraz odbiór. Bezpieczne założenie: konflikt obcej publikacji blokuje nowe komendy,
ale nie może ukrywać wcześniejszej historii; adopcja GET wymaga zakończonych
wcześniejszych porównań. Inne uszkodzenia własnych receipts nadal fail-closed.
Kontrole legacy P2-8/P2-9 z audytu T1: tylko wymienione fixture paths/head, jeden
ograniczony przebieg z limitem 110 s i jawnym wynikiem; bez rozszerzania benchmarków.
