---
title: TASK-0646 — Gra 777: ścieżka execute reweryfikacji siatek
status: todo
---

# TASK-0646 — Ścieżka `execute` (bez uruchomienia na żywych danych)

## Status

`todo`

## Goal

Zapisywać decyzje „pewne” z TASK-0645 wyłącznie przez istniejące serwisy Reviewera, idempotentnie i z izolacją błędów per zdjęcie, pokryte testami.

## Dependencies / entry conditions

- TASK-0645 `done`.

## Recommended execution

`claude-opus-5-5`, reasoning `high` — zgodnie z tabelą planu. Wymagany review diffu: `claude-opus-5-5`, reasoning `high`, przed TASK-0647.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-444, D-445)

## Scope

- Podkomenda `execute` wymagająca `--confirm-game-id` równego `--game-id`.
- Plansze pewne: `ImageGridReviewService.approve_source` z podzbiorem pewnych plansz zdjęcia; oczekiwane tożsamości (rewizje, checksum, wymiary, topologia) z odczytu w tej samej iteracji.
- Zdjęcia `resolvable`: `VirtualGridGeometryService.save_source` z komendami dla wszystkich slotów (odroczone → quad weryfikatora; rodzeństwo → bieżący `symbolGridQuad` zaokrąglony do int).
- Aktor `system:grid-reverify-777-v1`; idempotencja `uuid5(NAMESPACE_URL, "grid-reverify-777-v1:{source_image_id}:{source_geometry_revision_id}")`.
- Sesja i commit per zdjęcie jak w `services/api/src/game_predictor_api/main.py` (`default_image_grid_review_service_dependency`, `default_virtual_grid_geometry_service_dependency`), w `game_storage_scope(game_id)`.
- Obsługa błędów wg tabeli w planie; checkpoint i wznowienie.

## Out of scope

- Uruchomienie na bazie deweloperskiej `game_predictor` (TASK-0647, za zgodą).

## Acceptance criteria

- [ ] Bez `--confirm-game-id` → odmowa przed odczytem obrazów.
- [ ] Niepewne plansze/zdjęcia → brak jakiegokolwiek zapisu.
- [ ] Konflikt rewizji → rollback zdjęcia, `skipped_conflict`, kontynuacja.
- [ ] Ponowne uruchomienie → brak duplikatów (replay idempotencji).
- [ ] Po zatwierdzeniu istnieją bieżące komórki symboli dla nowych rewizji (sync coordinator).
- [ ] Testy jednostkowe (fałszywe serwisy) i integracyjny Postgres (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, baza `*_test`) przechodzą.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest <test file> -q   # timeout 120 s
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest <integration test> -q
npm run python:lint; npm run python:typecheck
```

## Risks / open questions

- `save_source` zapisuje rewizję jako `manual_v1` — akceptowane w planie; pochodzenie odróżnia aktor.

## Outcome

Wypełnia agent po pracy.
