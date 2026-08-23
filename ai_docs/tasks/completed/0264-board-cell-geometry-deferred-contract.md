---
title: TASK-0264 board-cell geometry deferred contract
status: done
release: "0.7"
last_updated: 2026-08-23
completed_at: 2026-08-23
---

# TASK-0264 — Trwały kontrakt odroczonej geometrii komórek

## Goal

Dodać jawny, wersjonowany stan geometrii komórek i trwały fallback per plansza
bez aktywowania estymatora v19 w produkcyjnym workerze.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- `BoardCellProcessingManifestV1` i content-addressed artifact bez JPEG-ów,
- tabela `image_board_geometry_pending`, migracja Alembic i repozytorium,
- statusy `pending`, `resolved`, `superseded` i zamknięty katalog powodów,
- idempotentne odroczenie, bezpieczne przejścia i zasada human-wins,
- liczniki joba oraz list/get API z OpenAPI i generowanym klientem.

## Out of scope

- uruchamianie estymatora/croppera v19 w pełnym pipeline,
- zmiana domyślnego v18,
- mutacyjne API oraz UI ręcznej korekty,
- masowy backfill i trening.

## Acceptance criteria

- [x] Niewiarygodna geometria ma trwały stan bez tworzenia 15 predykcji.
- [x] Manifest przypina źródło, sekwencję, rewizje i wszystkie fingerprinty.
- [x] Exact retry jest idempotentny, a nowy manifest superseduje stary pending.
- [x] Równoległa decyzja człowieka wygrywa z automatycznym rozwiązaniem.
- [x] API list/get zwraca stabilną kolejność, reason code, status i liczniki joba.
- [x] Migracja ma odwracalny downgrade i nie zawiera obrazu BLOB.
- [x] OpenAPI i wygenerowany klient zawierają nowe operacje.

## Outcome

- Migracja `0054_image_board_geometry_pending` utrwala fallback na poziomie
  `import_job + source_image + position_index`; `recognized_board_id` i
  `review_item_id` są opcjonalne, więc fail-closed nie wymaga stworzenia
  fałszywej planszy ani predykcji.
- Content-addressed manifest przypina poświadczoną sekwencję, źródło, rewizje,
  wersje i fingerprinty pipeline'u, estymatora oraz croppera.
- Repozytorium serializuje konkurencyjne defery przez blokadę źródła i ponownie
  sprawdza bieżącą planszę/review przy rozwiązaniu. Zmiana człowieka ustawia
  `superseded`, nigdy nie jest nadpisywana.
- Kontrakt API pozostaje read-only w tym zadaniu; produkcyjne tworzenie stanów
  deferred należy do osobnego TASK 4 i nadal jest zablokowane wynikiem
  benchmarku pokrycia TASK 2.
- Walidacja: `410 passed, 2 skipped` w pełnym zestawie API bez testów
  PostgreSQL, `65/65` w celowanym zestawie kontraktu/jobów/migracji, aktualny
  OpenAPI i klient, typecheck klienta oraz Ruff zmienionych plików. Lokalna baza
  działa na `0054_image_board_geometry_pending (head)`.
- Pełny Ruff nadal zgłasza osiem wcześniejszych błędów formatowania w migracjach
  0045/0046 i teście workera. Pełny mypy nadal zgłasza 15 wcześniejszych błędów
  w sześciu plikach worker/API; żaden nie znajduje się w nowym pionie TASK-0264.
