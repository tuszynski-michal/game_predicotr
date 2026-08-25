---
title: TASK-0286 — Panel hosta zdalnej ręcznej selekcji
status: done
last_updated: 2026-08-24
---

# TASK-0286 — Panel hosta zdalnej ręcznej selekcji

## Status

`done`

## Goal

Udostępnić w niezależnej od gry zakładce Admina bezpieczny lifecycle sesji
zdalnej ręcznej selekcji: wybór bazy, utworzenie, jednorazowe przekazanie kodu,
monitorowanie i odwołanie dokładnej sesji.

## Context

Backend, Reviewer i trwały pipeline zdalnej selekcji powstały w TASK-0277–0285,
ale Admin nie ma jeszcze panelu właściciela. TASK 14 z zaakceptowanego breakdownu
wymaga odzyskiwalnego widoku aktywnych sesji bez utrwalania sekretów i ścieżek.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- typowany klient Admina dla select/create/list/detail/revoke,
- ograniczony monitoring partii, dysku hosta, błędów i wspólnego ingressu,
- picker bazy, etykieta i TTL sesji,
- jednorazowa karta linku i kodu bez trwałego storage,
- lista odzyskiwana po reloadzie, dynamiczny URL po restarcie tunelu,
- odwołanie wyłącznie konkretnej sesji z exact-target confirmation,
- integracja panelu z niezależną zakładką `Ręczna selekcja`.

## Out of scope

- zmiany zdalnego workspace Reviewera,
- globalne zatrzymywanie wspólnego tunelu,
- edycja lub finalizacja plików i partii,
- TASK 15 i późniejsze zadania.

## Acceptance criteria

- [x] Host wybiera bazę i tworzy sesję z etykietą oraz TTL.
- [x] Kod jest dostępny tylko w wyniku create i znika po reloadzie/odrzuceniu karty.
- [x] Lista/detail nie ujawniają kodu, tokenu ani ścieżki hosta.
- [x] Panel po reloadzie odtwarza sesje i pokazuje aktualny URL bieżącego ingressu.
- [x] Polling jest ograniczony i monitoruje wybraną sesję oraz maksymalnie 100 partii.
- [x] Host widzi writer/ingress, pojemność dysku, liczniki i stabilne kody błędów.
- [x] Revoke dotyczy dokładnego session ID i nie zatrzymuje innych assignments ani tunelu.
- [x] Loading, empty, error i ochrona przed podwójnym submit są obsłużone.
- [x] Testy Admina, klienta, API, OpenAPI, lint, typecheck i build przechodzą.

## Technical notes

- Lista sesji pozostaje path/secret-free. Szczegół monitoringu udostępnia wyłącznie
  zagregowane liczniki, bajty wolnego miejsca i stabilne kody błędów.
- Sekret create pozostaje wyłącznie w pamięci komponentu React.
- Wspólny ingress jest tylko odczytywany; revoke nie wykonuje globalnego stopu.

## Expected files

- `services/api/src/game_predictor_api/application/remote_manual_selection_access.py`
- `services/api/src/game_predictor_api/storage/remote_manual_selection_access_repository.py`
- `services/api/src/game_predictor_api/schemas/remote_manual_selections.py`
- `services/api/src/game_predictor_api/api/remote_manual_selections.py`
- `packages/admin-api-client/src/index.ts`
- `apps/admin/src/features/manual-image-selection/remote-manual-selection-*`
- `apps/admin/src/features/manual-image-selection/manual-image-selection-workspace.tsx`
- testy API, klienta i Admina

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_remote_manual_selection_access.py services/api/tests/test_remote_manual_selection_access_api.py services/api/tests/test_openapi_contract.py -q
npm run test --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/api/remote_manual_selections.py services/api/src/game_predictor_api/application/remote_manual_selection_access.py services/api/src/game_predictor_api/schemas/remote_manual_selections.py services/api/src/game_predictor_api/storage/remote_manual_selection_access_repository.py
.venv\Scripts\python.exe -m mypy --disable-error-code import-untyped --disable-error-code unused-ignore services/api/src/game_predictor_api/api/remote_manual_selections.py services/api/src/game_predictor_api/application/remote_manual_selection_access.py services/api/src/game_predictor_api/schemas/remote_manual_selections.py services/api/src/game_predictor_api/storage/remote_manual_selection_access_repository.py
npm run openapi:check
```

## Risks / open questions

- Quick Tunnel pozostaje transportem testowym bez SLA; panel raportuje jego stan,
  ale go nie przedstawia jako niezawodnego hostingu.

## Outcome

### Changed

- Dodano path/secret-free monitor sesji i maksymalnie 100 partii z agregatami
  bazy oraz statusem dysku.
- Rozszerzono typowany klient o pełny lifecycle hosta i exact-target create/revoke.
- Dodano responsywny panel hosta nad lokalnym workspace z pickerem, etykietą,
  TTL, jednorazowym sekretem, bounded pollingiem i dwustopniowym revoke.

### Verification results

- Admin: 248/248 testów, lint bez błędów, typecheck i production build zaliczone.
- Admin API client: 41/41 testów, lint, typecheck i build zaliczone.
- API/OpenAPI: celowane testy zaliczone, Ruff i focused mypy zaliczone, artefakt
  OpenAPI i klient bez driftu.
- PostgreSQL: izolowany test agregacji monitoringu 1/1 zaliczony.

### Not completed

- Nie uruchamiano rzeczywistego publicznego Quick Tunnel; pozostaje transportem
  testowym bez SLA. Nie rozpoczęto TASK 15.

### Documentation updates

- Zaktualizowano wymagania ręcznej selekcji, kontrakt API, plan architektury i
  `CURRENT_STATE.md`.

### Recommended next task

- Osobny checkpoint/review TASK 14, następnie TASK 15 — finalizacja i zgodność
  outputu/śladu.
