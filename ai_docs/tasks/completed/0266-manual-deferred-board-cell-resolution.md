---
title: TASK-0266 manual deferred board-cell resolution
status: done
release: "0.7"
last_updated: 2026-08-23
---

# TASK-0266 — Ręczne rozwiązanie odroczonej geometrii komórek

## Goal

Pozwolić bezpiecznie zamienić jeden trwały `image_board_geometry_pending` na
zwykłą planszę oczekującą w istniejącej kolejce Reviewera, używając ręcznej
geometrii v19, dokładnie 15 cropów source-direct i modelu symboli przypiętego
do importu.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0264-board-cell-geometry-deferred-contract.md`
- `ai_docs/tasks/completed/0265-board-cell-processing-v20-worker-adapter.md`

## Scope

- checksum-bound kontekst oraz źródło jednego pendingu,
- preview czterech narożników przez istniejący cropper v19,
- dokładnie 15 cropów albo brak zapisu,
- inferencja przez snapshot modelu przypięty do źródłowego joba,
- atomowe utworzenie planszy, obserwacji i itemu istniejącej kolejki review,
- idempotencja, kontrola rewizji i zasada human-wins,
- mutacyjne API dostępne lokalnie oraz w poprawnie scoped sesji Reviewera.

## Out of scope

- komponenty UI i nawigacja kolejki fallbacku — osobny TASK 6,
- zmiana domyślnego pipeline'u v18 albo bramki rollout v20,
- trening, auto-akceptacja, backfill i masowe przeliczenie,
- zmiana poświadczonego numeru `seq_*`.

## Acceptance criteria

- [x] Preview nie zapisuje plików ani danych domenowych.
- [x] Zapis tworzy dokładnie 15 cropów row-major i jeden pending review item.
- [x] Niepełna geometria i błąd modelu nie tworzą częściowej projekcji.
- [x] Exact retry zwraca ten sam wynik, a zmieniona komenda daje stabilny konflikt.
- [x] Zmiana człowieka, manifestu lub źródła wygrywa z zapisem automatycznym.
- [x] Nowy item pojawia się w istniejącej kolejce we właściwej pozycji sekwencji.
- [x] Lokalny administrator i scoped Reviewer mają dostęp; obca sesja jest odrzucana.
- [x] OpenAPI, testy, lint i typecheck przechodzą dla zmienionego zakresu.

## Outcome

- Dodano scope-bound context/source, read-only preview i idempotentny zapis
  ręcznej geometrii jednego deferred.
- Model symboli jest odtwarzany z checksum-bound snapshotu źródłowego joba;
  temperatura ma bezpieczne minimum `0,50`, zgodne z pipeline'em.
- Repozytorium tworzy atomowo planszę, 15 obserwacji, rewizję i zwykły item
  review. PostgreSQL integration potwierdza projekcję do istniejącej kolejki,
  exact retry oraz human-wins.
- Celowane testy Python przeszły `46/46`, Reviewer `35/35`, klient OpenAPI
  `39/39`, a izolowany test PostgreSQL `1/1`. Ruff zmienionych plików,
  Reviewer lint/typecheck i OpenAPI check przeszły.
- Celowany mypy nie wykrywa błędów w TASK 5; raportuje wyłącznie dwa wcześniejsze
  błędy w `symbol_model_iteration_repository.py`. Pełny Ruff i Prettier repo
  nadal raportują wcześniejszy drift w plikach spoza TASK 5.
- UI listy i edytora deferred pozostaje wyłącznie w TASK 6. Domyślny v18,
  opt-in v20 i bramka rollout nie zostały zmienione.
