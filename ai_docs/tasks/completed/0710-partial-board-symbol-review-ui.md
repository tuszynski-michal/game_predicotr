# TASK-0710 — Interfejs i statusy importu

## Status
`done`

## Goal
Nowy filtr/badge/kafelek bez obrazu, przeniesienie po przypisaniu, source context, brak renderowania poza zdjęciem, czytelne statusy i zachowane interakcje.

## Context
Użytkownik 2026-09-27 zlecił cały zaakceptowany plan T1–T4.
Właściciel reguł: ai_docs/delivery/PARTIAL_BOARD_SYMBOL_REVIEW_EXECUTION_PLAN.md,
sekcja T3. Obce zmiany z wejściowego git status zachować.

## Dependencies / entry conditions
TASK-0709 odebrany. Wymagana ponowna kontrola kodu i stanu przed implementacją.
Apply danych pozostaje osobno zleconą operacją.

## Recommended execution
gpt-6-sol / medium; niezależny audyt gpt-6-astra / medium.
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
Wykonać kompletną sekcję T3 zaakceptowanego planu.
Outside po przypisaniu należy tylko do rzeczywistego symbolu, zachowując badge.
Widoczność jest niezależna od wyniku rozpoznania. Nie wymyślać obrazu/checksum.
Nie nadpisywać operatora, nie obchodzić routingu V2 i CAS.

## Out of scope
Trening, push/merge, destrukcyjne migracje, produkcyjne apply bez osobnego kroku.

## Expected files
apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx oraz virtual-grid/previews/state; features/imports/missing-boards-section.tsx i image-folder-import-state.ts.

## Acceptance criteria
- [x] Nowy filtr/badge/kafelek bez obrazu, przeniesienie po przypisaniu, source context, brak renderowania poza zdjęciem, czytelne statusy i zachowane interakcje.
- [x] Testy powiązanych regresji i przypadków brzegowych.
- [x] Niezależny audyt bez P0–P2.
- [x] Dokumentacja i Outcome, osobny wersjonowany commit.

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
### Changed
- Nowy filtr Poza zdjęciem, kafelek bez obrazu, trwałe badge widoczności i jakości.
- Podgląd źródła z zapisaną siatką, kontrolą właściciela/rewizji/SHA; brak atlasu i akcji graficznych dla outside.
- Decyzje pojedyncze i zbiorcze odświeżają ograniczoną stronę z unieważnieniem poprzednich żądań; Nieczytelny nie znika błędnie ze swojej grupy.
- Statusy stagingu i Brakujących plansz oddzielają niepełne zdjęcie, geometrię i przetwarzanie od decyzji symboli.

### Verification results
- 105 skoncentrowanych testów Node PASS: symbol-review*.test.mjs i image-folder-import-state.test.mjs.
- 5 testów interakcji React PASS: symbol-review-partial.test.mjs (tsx z tsconfig Admina).
- Admin tsc --noEmit, ESLint, Prettier 12 plików i git diff --check PASS.
- Izolowany Next build --webpack PASS (kopię źródeł zbudowano w work/partial-board-t3-build; działającego .next nie zmieniono).
- Niezależny audyt gpt-6-astra/medium: 17 testów logiki PASS oraz końcowe 5 interakcji PASS; brak nierozwiązanych P0–P2.
- Przeglądarka, prawdziwy komponent z izolowanym klientem testowym: outside, source+siatka poza kadrem, blokady obrazu, klawiatura 1+Enter, przeniesienie do Wiśni z badge, Nieczytelny pozostaje outside bez przełączania filtrów PASS. Tymczasowy serwer zatrzymano.
- Komendy testowe miały timeout 120 s; build w izolowanej kopii. Nie wykonywano mutacji danych użytkownika.

### Not completed
- Produkcyjne wdrożenie, migracje, apply 70 plansz i odbiór 1050 pozycji pozostają osobnym krokiem danych T4; test przeglądarkowy używał fixture.
- Nie potwierdzono fizycznego Androida ani restartu komputera.

### Documentation updates
- ADMIN_APP.md: nowy workflow, kontekst źródła i zgodne odświeżanie po decyzjach. CURRENT_STATE.md i Outcome.

### Recommended next task
- TASK-0711 / T4: narzędzie preview/apply, trwałe pokwitowania i odczytowy podgląd dokładnie 70 plansz.

### Commit
- Wersja/hash zostaną dopisane po utworzeniu osobnego commita T3.
