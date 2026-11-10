---
title: TASK-1177 — Wydajny zapis symboli i zamrażanie manifestu
status: done
last_updated: 2026-11-10
---

# TASK-1177 — Wydajny zapis symboli i zamrażanie manifestu

## Status

`done`

## Goal

Skrócić zbiorcze zatwierdzanie i czas blokowania gry oraz bezpiecznie obsłużyć
zmianę manifestu między podglądem a zamrożeniem.

## Context / zgody

T1 planu REVIEW_LEARNING_RELIABILITY_PLAN_20261110.md. Operator zatwierdził
cały zakres, testy i Opus, budżet6–10h. Main f4d16729. Dane operatora tylko
odczytowo; brak zgody na merge/push/restart/migrację/trening w tym zadaniu.

## Recommended execution

gpt-6.1-sol/high; audyt Claude Code claude-opus-5-5/high. Blokada przy otwartych
P0/P1 po rundzie poprawek; żadnego zastępczego PASS.

## Relevant docs

- ai_docs/delivery/REVIEW_LEARNING_RELIABILITY_PLAN_20261110.md, T1.
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md.
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md.
- ai_docs/architecture/API_CONTRACT.md, verified-training-cohorts.
- ai_docs/requirements/IMAGE_INGESTION.md.
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md.
- ai_docs/process/CROSS_AUDIT.md; ai_docs/process/DEFINITION_OF_DONE.md.
- ai_docs/process/decisions/DECISION_LOG_2026.md#d-599--propozycje-siatek-do-ludzkiej-weryfikacji-symboli.

## Scope / expected files

Istniejące: storage/image_symbol_review_bulk_operation_repository.py,
storage/image_symbol_review_repository.py, storage/symbol_cell_training_source_repository.py,
application/verified_training_cohorts.py, API/schemas verified_training_cohorts,
Admin model-quality-actions/workspace, OpenAPI/SDK i odpowiadające testy.
Zmiany wyłącznie po potwierdzeniu przyczyny. Nowe helpery/testy raportować
jawnie. Ewentualna zmiana schematu wyłącznie przez Alembic, bez wykonania
migracji operatora. Bez nowej infrastruktury lub rozluźniania uprawnień.

## Acceptance criteria

- [x] Zmierzona przyczyna i ograniczone porównanie przed/po.
- [x] Mniej zbędnych SQL, krótsze sekcje blokad, zgodny wynik zapisów.
- [x] Aktualne potwierdzenie manifestu, realne stale nadal blokuje.
- [x] Czytelny konflikt/oczekiwanie i bezpieczny retry w Adminie.
- [x] Restart/utrata odpowiedzi/własność/holdouty/human approvals chronione.
- [x] API/OpenAPI/SDK zgodne, właściwe testy PG/UI i kontrole zaliczone.
- [x] Opus i task-close przed commitem, P2 jawnie zapisane.

## Verification

Istniejące testy: test_symbol_review_bulk_start_locking.py,
integration/test_symbol_review_bulk_start_locking_postgres.py,
test_verified_training_cohorts.py, test_symbol_cell_training_cohorts_domain.py
oraz właściwe zestawy mutacji/replay. Ograniczone nowe testy zapisów i
konkurencji; fixtures nie mogą ukrywać pełnego produkcyjnego zapisu.
Każda komenda ma timeout<=120s; audyt1800s. Wyniki w raporcie jakości taska.

## Outcome

Commit: v1.7.594 / `0e1a02ec916629508570ee6570ded38d4df92817`.

Implementacja gotowa do końcowej kontroli. Zachowano transakcję planszy,
własność i zgodę na aktualny manifest. Szczegóły, pomiary i ograniczenia:
ai_docs/quality/TASK-1177_VERIFICATION.md. PASS:56 Python,14 PostgreSQL,
12 interakcji Admina; Ruff, scoped mypy7 modułów, ESLint/typecheck/build,
OpenAPI i docs. Ograniczony pomiar45 komórek:413→376 SQL,1.229→1.180s.
Nie jest to dowód szybkości dużej partii operatora. Opus R1/R2 REVISE:
wcześniejsze P1 zamknięte; R2 P1-3 dotyczył formatu dwóch plików.
Operator zatwierdził dodatkową poprawkę i focused review; Prettier PASS,
końcowy audyt Opus PASS,0 P0/0 P1. Raport i receipt:
ai_docs/quality/TASK-1177_AUDIT_claude-opus-5-5.md.
P2-1 (pokrycie wszystkich pisarzy),P2-2 (identyfikacja wiszącego jobu) i
wcześniejszy P2-6 (kodowanie komunikatu) jawnie zachowane w raporcie.
Cały DoD sprawdzony: trwałe zapisy/replay, kontrakt i dokumentacja, kontrole
zmienionego pionu, mapa i audyt. Pełny projektowy mypy/quality nie był
uruchamiany; scoped nie jest deklarowany jako pełny. Bez wdrożenia i zapisu
na danych operatora; T2 kontynuowane w zatwierdzonym zakresie.
