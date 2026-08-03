---
title: TASK-0155 image selection manual fallback workspace
status: todo
release: "0.4"
last_updated: 2026-08-02
---

# TASK-0155 — Image selection manual fallback workspace

## Status

`todo`

## Goal

Dostarczyć minimalistyczny modal do uzupełnienia grup bez bezpiecznego
automatycznego reprezentanta za pomocą jednego pliku JPEG i obsługi klawiatury.

## Context

Nie każda grupa ma zdjęcie spełniające quality gate, a nieustalony zakres nie
może zostać po cichu pominięty. Człowiek rozstrzyga tylko wyjątki po zakończeniu
automatycznego skanu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/tasks/completed/0154-curated-image-output-and-layout-import-handoff.md`

## Scope

- dodać modal kolejki `manual_required`,
- pokazać licznik decyzji, zakres/unknown, poprzedni, następny i zatwierdź,
- dodać single-file JPEG picker i preview wybranego zdjęcia,
- dla unknown wymagać dodatnich `range_start` i `range_end`,
- zaimplementować ArrowLeft/ArrowRight wyłącznie jako nawigację i Enter jako
  idempotentne zatwierdzenie,
- umożliwić ponowne otwarcie i korektę wcześniejszej decyzji,
- skopiować plik dopiero przez kontrolowane API i zaktualizować manifest,
- zachować focus, etykiety dostępności oraz style Admina.

## Out of scope

- zdalne udostępnianie tego modala,
- automatyczne uczenie z manualnych decyzji,
- wielokrotny wybór plików dla jednej grupy,
- zatwierdzanie strzałką w prawo.

## Acceptance criteria

- [ ] Header pokazuje `zatwierdzone / total` i właściwy zakres albo unknown.
- [ ] Strzałki ekranowe i klawisze kierunkowe tylko nawigują.
- [ ] Enter i przycisk zatwierdzają dokładnie raz poprawnie wybrany plik.
- [ ] Zablokowane zatwierdzenie nie pokazuje loadera, jeśli nie trwa request.
- [ ] Unknown wymaga poprawnego dodatniego zakresu; konflikt istniejącego zakresu
      jest jawny.
- [ ] Anulowanie file pickera nie blokuje następnego wyboru.
- [ ] Zapisana decyzja może zostać zmieniona z zachowaniem audytu/provenance.
- [ ] Modal jest używalny bez przewijania przy 1366×768 i ma widoczny focus.

## Technical notes

Nie kopiować aplikacji Reviewer. To bounded modal Admina dla całych zdjęć
źródłowych, nie dla 15 symboli planszy.

## Expected files

- `apps/admin/src/features/image-selection/`
- `apps/admin/test/`
- `services/api/src/game_predictor_api/api/`
- `services/api/src/game_predictor_api/application/`
- `services/api/tests/`
- `packages/admin-api-client/`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm.cmd test --workspace @game-predictor/admin
npm.cmd run typecheck --workspace @game-predictor/admin
npm.cmd run lint --workspace @game-predictor/admin
.venv\Scripts\python.exe -m pytest services/api/tests -q
npm.cmd run openapi:check
```

## Risks / open questions

- Przeglądarka nie może ujawniać pełnej lokalnej ścieżki wybranego pliku; UI
  pokazuje tylko bezpieczną nazwę prezentacyjną.

## Outcome

Do uzupełnienia po realizacji.
