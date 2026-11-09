---
title: TASK-1175 — Pełne pola symboli bez marginesu8%
status: todo
last_updated: 2026-11-09
---

# TASK-1175 — Pełne pola symboli bez marginesu8%

## Status

`todo`

## Goal

Pełne pola symboli bez marginesu8%.

## Context

Operator zaakceptował2–4h na margines0%, testy i Opus, połączył z najnowszym
zgłoszeniem powtarzającej się planszy i wolnego ładowania. Pełny zakres dwóch
tasków jest zlecony; zgoda nie obejmuje wdrożenia ani merge.

## Recommended execution

gpt-6.1-sol/high. Terminalowy niezależny Claude Code claude-opus-5-5/high,
przed commitem; otwarte P0/P1 po jednej rundzie poprawek zatrzymują task.
Bez automatycznej delegacji ani zmiany modelu.

## Relevant docs

- `ai_docs/delivery/FULL_FIELD_CORRECTION_FLOW_PLAN_20261109.md`.
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`, `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`.
- `ai_docs/requirements/IMAGE_INGESTION.md`, `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`.
- `ai_docs/process/CROSS_AUDIT.md`, `ai_docs/process/DEFINITION_OF_DONE.md`.
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — konkretne D-462/D-488/D-591/D-596/D-597 przez indeks; nie czytać całości.

## Out of scope

Trening, default geometrii, zapis do bazy operatora, masowe akceptacje, restarty,
merge/push i wdrożenie. Testy PG wyłącznie disposable. Operatorowe odczyty bounded/read-only.

## Scope

T2 planu. Jawny nowy pin0% w nowych snapshotach i dalszej manualnej korekcie obecnych6219; historyczny brak pola pozostaje8% i zachowuje fingerprint. Doprecyzować konkretną ścieżkę przed implementacją po sprawdzeniu manual resolvera.

## Acceptance criteria

- [ ] Spełnione kryteria przypisanej sekcji planu i regresje dotychczasowych konsumentów.
- [ ] Spójny kontrakt API/OpenAPI/SDK/wrapper/test, jeżeli zmieniany.
- [ ] Właściwe testy/lint/types/build/docs/map i niezależny Opus z receipt.
- [ ] Outcome, task-close, osobny commit i hash w kolejnym commicie.

## Expected files

domain/symbol_model_snapshots.py; storage/symbol_model_snapshot_resolver.py; worker production_workflow.py; storage/virtual_grid_geometry_repository.py i board_cell_geometry_pending_repository.py; transport snapshotów/kontekstu i testy; dokumenty/mapa.

## Test cases

Legacy bytes/fingerprint/crops unchanged; new policy0 serialized and hash-bound, invalid policies rejected; preview/symbol/save use identical0; changing crop invalidates old quality proof and changed symbol pixels; cold reload/idempotency/PG; real15rasters8/0.

## Verification

Python z D:/game_predicotr/.venv; PYTHONPATH własnego API/workera. Reviewer
`npm run test:geometry --workspace @game-predictor/reviewer` (najpierw właściwe pliki),
scoped Ruff/mypy/ESLint/TS, potem wymagany build. Skończone komendy timeout≤120s;
znany build/audyt według limitów repo. Nie uruchamiać usług.

## Risks / open questions

Dane operatora nie stanowią testowych fixture; same confidence/regularność nie
kwalifikują pełności. Brak GT nie jest pomiarem poprawy klasyfikacji. Nie tworzyć
fikcyjnego PASS. Wszelkie zmiany kolejności/source identity muszą zachować sequence.

## Outcome

Do uzupełnienia po pracy. Brak deklaracji testów lub audytu przed wykonaniem.
