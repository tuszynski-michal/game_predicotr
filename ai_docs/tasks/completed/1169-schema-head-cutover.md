---
title: Spójność rewizji schematu przy wdrożeniu pełnych symboli
status: done
last_updated: 2026-11-09
---

# TASK-1169 — Spójność rewizji schematu przy cutover

## Status

`done`

## Goal

Wspólny strażnik API/workera akceptuje dokładnie zatwierdzoną migrację0183,
a preflight wykrywa przyszłe rozbieżności przed zatrzymaniem usług.

## Context

Operator zaakceptował wdrożenie T0–T5, merge/push,0182/0183 i restarty.
Main/origin=c0bf0368, baza ma0183/manifestv22. Start API odmówił, bo
schema_readiness.EXPECTED_ALEMBIC_HEAD pozostał0181. Dane/default/przypisania
sprawdzone bez zmian. To pominięcie wdrażanego zakresu, nie błąd bazy.
Nie omijać strażnika i nie cofać bazy.

## Recommended execution

gpt-6.1-sol/high — mała poprawka istniejącej granicy startowej i preflight.
Niezależny terminalowy Claude Code claude-opus-5-5/high przed commitem.
Jeden audyt i jedna runda poprawek; brak PASS przy niedostępnym audytorze.

## Relevant docs

- AGENTS.md
- ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md (ograniczenia wdrożenia)
- ai_docs/quality/FULL_SYMBOL_CROPS_ACCEPTANCE_20261109.md
- ai_docs/guides/LOCAL_OPERATION_GUIDE.md (cutover,475–509)
- ai_docs/architecture/VISION_LAB.md
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/CODE_MAP.md
- .agents/skills/merge-to-main/SKILL.md

## Scope

- EXPECTED_ALEMBIC_HEAD0183 i opis manifestv22, bez rozluźnienia exactmatch.
- Aktualny dynamiczny test ScriptDirectory/currenthead i chain0183→0182→0181;
  odrzucenie poprzednich rewizji, także0181/0182. Zachować historyczne testy.
- Preflight ma raportować brak zgodności startuphead z rzeczywistą jedyną
  głową grafu migracji. Użyć bezpiecznego odczytu/statycznego AST, bez DB,
  importowania aplikacji lub uruchamiania migracji. Błąd/niejednoznaczność
  daje jawną blokadę, nie pozorną zgodność. Zachować exit/report konwencję.
- Test preflight odtwarza konkretny mismatch: dodana migracja bez zmiany
  strażnika nie przechodzi kontroli gotowości; zgodny graf przechodzi.
- Root ponawia zatwierdzony cutover i odczyty live po audycie/commicie.

## Out of scope

Nowy trening, import691, zmiana defaultu, zmiana reguł danych, ponowna
migracja/downgrade, usuwanie danych, szeroki refactor lub globalne testy.

## Acceptance criteria

- [x] Strażnik nadal exact, zgodny z jedyną głową0183 i manifestv22.
- [x] Testy guard/preflight odtwarzają problem i chronią kolejną migrację.
- [x] API i worker używają tej samej funkcji, bez bypassu startupu.
- [x] Scoped testy/lint/types, docs/map i Opus PASS przed commitem.
- [x] Outcome, osobny commit/task-close; stan restartów w raporcie, pełny cutover po integracji.

## Expected files

- services/api/src/game_predictor_api/storage/schema_readiness.py
- services/api/tests/test_schema_readiness.py
- scripts/integration_preflight.py
- services/worker/tests/test_integration_preflight_script.py
- Właścicielskie docs, task/status i quality report — root.

## Verification

Kontrakt CLI doprecyzowany przed implementacją: schema_readiness ma ref,
state matched/mismatch/unknown/not_applicable, blocks_merge,
expected_alembic_head, migration_heads, reason. Odczyt z pinned branch_tip,
nie losowego worktree. Mismatch/unknown blokują merge i dają warning; exit0
nadal oznacza poprawne utworzenie raportu. not_applicable wyłącznie dla
repo bez aplikacyjnego kontekstu API. Root aktualizuje procedurę merge.

Bezpośredni pytest zmienionych testów z timeout120s, scoped Ruff/mypy i
preflight tylko do odczytu. Brak usług/DB w wykonawcy. Root zweryfikuje
rzeczywisty start po integracji, z zachowaniem operatorowych danych.

## Outcome

Commit: v1.7.579 / `a5e78251f4fb0b6dec67256ceef9f43184150f94`.

### Changed

- Exacthead0183/manifestv22, dynamiczny test grafu i odrzucenie181/182.
- Preflight z pinnedref/AST, jawne mismatch/unknown i blocks_merge; brak DB/importów.
- Canonical procedura merge, mirror i guide egzekwują stan mimo exit0.

### Verification results

- 29guard/worker,12preflight i1nextmigration PASS; Ruff4/mypy2 oraz docs/map PASS.
- Root: rzeczywisty odczyt0183 rolą aplikacji w nowym procesie i wspólna funkcja workera PASS.
- Opus5.5/high R1 PASS0P0/0P1; raport i receipt w quality/TASK-1169_AUDIT_claude-opus-5-5.*.
- P2-2 instrukcji doprecyzowane. P2-1 dodatkowych trzech przypadków grafu zaakceptowane;
  brak fałszywej deklaracji pełnego pokrycia. Szczegóły quality/TASK-1169_VERIFICATION.md.

### Not completed

- Pełny restart jest następną zatwierdzoną operacją cutover po integracji;
  nie jest tu przedstawiany jako sukces. Nie zmieniano defaultu, danych ani importów.

### Documentation updates

- Guide, merge-to-main i mirror, mapa, bieżący stan oraz raport weryfikacji.

### Recommended next task

- Zgodny preflight nowego commita, merge/push i dokończenie zatwierdzonych restartów.
  Operator wybrał następnie przygotowanie danych do pełnego nowego modelu, bez treningu legacy.
