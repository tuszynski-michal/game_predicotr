---
title: TASK-0128 Test-dataset payout recomputation workflow
status: done
last_updated: 2026-08-01
---

# TASK-0128 — Test-dataset payout recomputation workflow

## Status

`done`

## Goal

Udostępnić w bieżącym workspace reguł jawną i bezpieczną akcję przeliczenia
payoutów całego małego datasetu testowego przez istniejący worker `payout-v2`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- przyjmować payout job wyłącznie dla opublikowanego, kompletnego i niepustego
  datasetu oraz opublikowanych reguł tej samej gry i o zgodnych wymiarach,
- utrwalić jawną wersję `payout-v2` w payloadzie joba,
- w workspace reguł wybrać deterministycznie najnowszy zgodny opublikowany
  dataset,
- pokazać gotowość albo dokładną blokadę przed uruchomieniem,
- pokazać status, etap, liczniki i procent postępu bieżącego joba,
- odświeżać aktywny job w ograniczonym pollingu i umożliwić wznowienie awarii na
  tym samym rekordzie,
- nie wykonywać obliczeń w requestcie HTTP i nie dodawać nowej kolejki.

## Expected files

- `services/api/src/game_predictor_api/application/jobs.py`
- `services/api/src/game_predictor_api/storage/job_repository.py`
- `services/api/src/game_predictor_api/api/jobs.py`
- `packages/admin-api-client/src/index.ts`
- `apps/admin/src/features/rules/`
- testy backendu, klienta i Admina,
- dokumentacja kontraktu i bieżącego stanu.

## Acceptance criteria

- [x] nieprawidłowa kombinacja dataset/reguły/algorytm nie trafia do kolejki,
- [x] braki, pusty dataset i niezgodne wymiary mają stabilne błędy,
- [x] UI pokazuje dataset, liczbę layoutów i `payout-v2`,
- [x] przycisk jest dostępny wyłącznie dla kompletnego opublikowanego źródła,
- [x] aktywny job pokazuje postęp i jest odświeżany bez podwójnego submitu,
- [x] zakończony job pozostaje widoczny, a nieudany można wznowić,
- [x] testy backendu, klienta i Admina przechodzą.

## Outcome

API rozpoznaje payout job jako osobny pion aplikacyjny i przed jego zapisaniem
sprawdza algorytm, statusy, grę, wymiary, niepustość oraz zgodność liczników
datasetu. Stabilne błędy zatrzymują nieprawidłowe wejście przed kolejką; same
obliczenia nadal wykonuje istniejący, resumowalny worker `payout-v2`.

Workspace reguł automatycznie wybiera najnowszy zgodny opublikowany dataset i
pokazuje jego wersję, wymiary oraz liczbę layoutów. Jawna akcja `Przelicz
layouty` utrwala dokładny tuple dataset/reguły/algorytm. Panel odświeża aktywny
job co 2 sekundy, pokazuje etap, liczniki i progress oraz wznawia nieudany job na
tym samym identyfikatorze i checkpointcie. Pełna diagnostyka pozostaje w
workspace `Joby`.

Weryfikacja: 32 testy API/kontraktu, 23 testy workera payout/runtime i 108 testów
Admina przeszło; lint, typecheck oraz produkcyjny build Admina także przeszły.
