# TASK-0711 — Uzupełnienie istniejących danych i odbiór

## Status
`todo`

## Goal
Preview dokładnie 70 numerów, owner/revision-bound retry/checkpoint/human protection; apply tylko osobno zlecone; 1050 pozycji po operacji, audyt pozostałych gier read-only.

## Context
Użytkownik 2026-09-27 zlecił cały zaakceptowany plan T1–T4.
Właściciel reguł: ai_docs/delivery/PARTIAL_BOARD_SYMBOL_REVIEW_EXECUTION_PLAN.md,
sekcja T4. Obce zmiany z wejściowego git status zachować.

## Dependencies / entry conditions
TASK-0708–0710 odebrane. Wymagana ponowna kontrola kodu i stanu przed implementacją.
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
Wykonać kompletną sekcję T4 zaakceptowanego planu.
Outside po przypisaniu należy tylko do rzeczywistego symbolu, zachowując badge.
Widoczność jest niezależna od wyniku rozpoznania. Nie wymyślać obrazu/checksum.
Nie nadpisywać operatora, nie obchodzić routingu V2 i CAS.

## Out of scope
Trening, push/merge, destrukcyjne migracje, produkcyjne apply bez osobnego kroku.

## Expected files
Nowe narzędzie preview/apply i raport w scripts/ oraz artifacts/; wspólny coordinator T1; nowa instrukcja operatorska.

## Acceptance criteria
- [ ] Preview dokładnie 70 numerów, owner/revision-bound retry/checkpoint/human protection; apply tylko osobno zlecone; 1050 pozycji po operacji, audyt pozostałych gier read-only.
- [ ] Testy powiązanych regresji i przypadków brzegowych.
- [ ] Niezależny audyt bez P0–P2.
- [ ] Dokumentacja i Outcome, osobny wersjonowany commit.

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
Do uzupełnienia po implementacji i audycie.
