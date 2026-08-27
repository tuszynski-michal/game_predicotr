---
title: Symbol review projection rollout
status: in_progress
last_updated: 2026-08-27
---

# TASK-0295 — Uruchomienie projekcji Weryfikacji symboli

## Status

`in_progress`

## Goal

Udostępnić trwałe, wznawialne przygotowanie projekcji około 1,88 mln komórek
oraz bounded infinite scroll w Adminie bez ponownego uruchamiania pipeline'u
obrazów.

## Context

Kod odczytu i write-through istnieje od TASK-0294, ale dla gry `777` nie
uruchomiono jawnego backfillu. W efekcie tabela komórek jest pusta, a Admin
pokazuje wyłącznie stan przygotowania.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/quality/SYMBOL_CELL_REVIEW_SCALABILITY_ANALYSIS.md`

## Scope

- trwały job i API status/start backfillu,
- bounded reconciliacja zmian równoległych,
- progres i diagnostyka rozmiaru danych,
- dwukierunkowy infinite scroll zachowujący keyset i limit 180 rekordów,
- kontrolowane uruchomienie na istniejącej grze.

## Out of scope

- ponowny pełny pipeline obrazów,
- fizyczny benchmark 2 mln komórek,
- dodatkowy worker lane, Redis, Celery lub chmura.

## Acceptance criteria

- [x] Backfill jest trwałym, idempotentnym jobem general lane.
- [x] Restart wznawia pracę od checkpointu w partiach maksymalnie 200 plansz.
- [ ] Stan `ready` wymaga 15 aktualnych komórek dla każdego właściciela planszy.
- [ ] Nowe i zmienione plansze są objęte write-through i końcową reconciliacją.
- [ ] Admin pokazuje status, progres, diagnostykę i akcję wznowienia.
- [ ] Infinite scroll pobiera po 60 i przechowuje maksymalnie 180 rekordów.
- [ ] Nie uruchomiono benchmarku ani syntetycznego fixture'u wielomilionowego.

## Technical notes

Backfill używa istniejących cropów oraz `image_board_search_fast_documents`.
Aktualny preflight geometrii może zakończyć się przed claimem joba; oba zadania
korzystają z jednego general lane.

## Expected files

- `services/api/src/game_predictor_api/application/image_symbol_review_backfill.py`
- `services/api/src/game_predictor_api/storage/image_symbol_review_backfill_repository.py`
- `services/worker/src/game_predictor_worker/symbols/review_backfill.py`
- `apps/admin/src/features/symbol-reviews/`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_image_symbol_reviews_api.py -q
.venv\Scripts\python.exe -m pytest services/worker/tests -q
npm run admin:test
npm run openapi:check
npm run typecheck
```

## Risks / open questions

- Początkowy zapis około 1,88 mln rekordów powiększy PostgreSQL; raport ma
  pokazać rzeczywisty rozmiar bez uruchamiania benchmarku.

## Outcome

### Changed

- TASK 1: dodano trwały typ joba, lokalne API status/start, idempotentne
  kolejkowanie i general-lane handler pracujący w partiach 200 plansz.

### Verification results

- 61 testów API/migracji/workera; Ruff i mypy dla zmienionego pionu zaliczone.
- Istniejący test integracyjny PostgreSQL wznowienia został wskazany, ale w
  bieżącym środowisku pozostaje pominięty bez
  `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`.

### Not completed

- TASK 2 i TASK 3 oraz kontrolowane uruchomienie.

### Documentation updates

- `CURRENT_STATE.md`, kontrakt API i model danych opisują trwały backfill.

### Recommended next task

- TASK 2 — bounded reconciliacja zmian równoległych i metryki miejsca.
