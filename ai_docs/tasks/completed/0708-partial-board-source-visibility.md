# TASK-0708 — Wspólny zapis dostępności i kompletu pozycji

## Status
`done`

## Goal
Każda plansza 3 × 5 ma 15 logicznych pozycji, outside bez fikcyjnego zasobu; partial początkowo unknown; zapis atomowy, retry idempotentne, decyzje człowieka zachowane.

## Context
Użytkownik 2026-09-27 zlecił cały zaakceptowany plan T1–T4.
Właściciel reguł: ai_docs/delivery/PARTIAL_BOARD_SYMBOL_REVIEW_EXECUTION_PLAN.md,
sekcja T1. Obce zmiany z wejściowego git status zachować.

## Dependencies / entry conditions
Brak. Wymagana ponowna kontrola kodu i stanu przed implementacją.
Apply danych pozostaje osobno zleconą operacją.

## Recommended execution
gpt-6-sol / high; niezależny audyt gpt-6-astra / medium.
Przy nierozwiązanych P0–P2 po dwóch rundach zatrzymać zależne prace.

## Relevant docs
- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/PARTIAL_BOARD_SYMBOL_REVIEW_EXECUTION_PLAN.md
- ai_docs/requirements/IMAGE_INGESTION.md
- ai_docs/requirements/ADMIN_APP.md
- ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md
- ai_docs/architecture/DATA_MODEL.md
- ai_docs/process/DECISION_LOG.md

## Scope / technical notes
Wykonać kompletną sekcję T1 zaakceptowanego planu.
Outside po przypisaniu należy tylko do rzeczywistego symbolu, zachowując badge.
Widoczność jest niezależna od wyniku rozpoznania. Nie wymyślać obrazu/checksum.
Nie nadpisywać operatora, nie obchodzić routingu V2 i CAS.

## Out of scope
Trening, push/merge, destrukcyjne migracje, produkcyjne apply bez osobnego kroku.

## Expected files
services/api/src/game_predictor_api/domain/image_geometry_v2.py — SourceQuad i klasyfikacja przecięcia; services/api/src/game_predictor_api/storage/image_symbol_review_repository.py — SymbolCellReviewWriteThroughCoordinator; models.py i nowa migracja Alembic.

## Acceptance criteria
- [x] Każda plansza 3 × 5 ma 15 logicznych pozycji, outside bez fikcyjnego zasobu; partial początkowo unknown; zapis atomowy, retry idempotentne, decyzje człowieka zachowane.
- [x] Testy powiązanych regresji i przypadków brzegowych.
- [x] Niezależny audyt bez P0–P2.
- [x] Dokumentacja i Outcome, osobny wersjonowany commit v1.7.12 (hash po commicie).

## Test cases / verification
Testy według sekcji Testy zaakceptowanego planu; wykonawca dobiera istniejące
focused test modules i zapisuje dokładne komendy/wyniki w Outcome.
Komendy z cwd repo; timeout do 120 s, dłuższy build zapowiedziany.
Nie wykonywać mutujących testów na produkcyjnych rekordach.
T4 rozdziela odbiór narzędzi od niezleconego jeszcze apply.

## Risks / open questions
Zastane historyczne kwalifikacje wymagają odczytu geometrii.
Nowy kontrakt bez cropa wymaga spójnych odbiorców, nie fikcyjnego zasobu.
Nie raportować wdrożenia ani naprawy danych na podstawie samych testów.

## Outcome
Commit: `v1.7.12` — `9b4950911fd35cb7fa04e878f59c1db4bfdcc7d7`.

### Changed

- Klasyfikacja full/partial/outside z przecięcia aktualnych footprintów ze źródłem.
- Wspólny koordynator tworzy 15 logicznych pozycji; outside bez cropa/predykcji.
  Błąd projekcji propaguje do właściciela transakcji zamiast udawać sukces.
- Migracja 0126 rozszerza V2, eventy i cele bulk; historyczna widoczność pozostaje NULL.
- Legacy i virtual respektują te same reguły; historyczne 15 cropów z maską oraz
  sparse real-crop revisions są obsługiwane. Outside nie jest zapisywany jako plik.
- Decyzje człowieka i historia zatwierdzeń zachowane przez kolejne korekty;
  nowe piksele wymagają ponownej weryfikacji. Identyczne retry nie zmienia rewizji.

### Verification results

- Mypy --follow-imports=silent: 10 zmienionych modułów produkcyjnych PASS.
  Ruff check oraz format --check: 16 plików PASS. git diff --check PASS.

- 94/94 PASS: test_symbol_cell_source_visibility, test_qualified_cell_reconciliation,
  test_image_symbol_reviews_domain, test_image_geometry_v2, test_board_cell_geometry_pending,
  test_image_symbol_review_virtual_source, worker/test_manual_partial_geometry,
  worker/test_manual_board_cell_geometry_preview.
- test_geometry_qualification: 32/32 PASS; stare oczekiwanie wykluczania całej
  maski legacy świadomie zastąpione zaakceptowaną regułą D-451.
- PostgreSQL: 2/2 PASS, izolowana baza, upgrade 0125 → 0126, istniejące i nowe
  partycje, nullable identities oraz prawdziwe INSERT/odrzucenie sprzecznych pól.
- Niezależny gpt-6-astra / medium: PASS bez P0–P2; 27/27 testów PASS.
- Testy uruchomiono przez pytest z bundled Python i repo site-packages, w nowym
  procesie z timeout 120 s; krótki --basetemp w .venv omija limit ścieżek Windows.
  Launcher .venv/Scripts/python.exe nie działa w bieżącym sandboxie.

### Not completed

- Bez migracji/aplikowania danych produkcyjnych. Odbiór 1050 rekordów po apply
  pozostaje T4; próbki 62287/62404/62440 sprawdzono testami logiki zapisu.
- API/grupy/UI należą do T2/T3; ten commit nie jest samodzielnym wdrożeniem.

### Documentation updates

- D-451, IMAGE_INGESTION, DATA_MODEL, zaakceptowany plan i zadania T1–T4.

### Recommended next task

- TASK-0709 (T2), zgodnie ze zleceniem realizacji całego planu.
