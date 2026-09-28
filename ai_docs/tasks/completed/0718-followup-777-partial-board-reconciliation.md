# TASK-0718 — Uzupełnienie sześciu plansz 777

## Status

done

## Goal

Sześć wskazanych plansz gry 777 ma po 15 logicznych pozycji, bez utraty decyzji.

## Context

Operator zlecił osobne uzupełnienie 13 historycznie pominiętych pól na planszach
225930, 225933, 225939, 225942, 225948, 225957.

## Relevant docs

- ai_docs/requirements/ADMIN_APP.md
- ai_docs/architecture/DATA_MODEL.md
- ai_docs/delivery/PARTIAL_BOARD_SYMBOL_REVIEW_EXECUTION_PLAN.md
- ai_docs/quality/PARTIAL_BOARD_SYMBOL_REVIEW_ROLLOUT.md

## Scope

Dokładnie sześć plansz 777. Wspólny mechanizm projekcji, kontrola ownera, rewizji,
geometrii i ręcznych decyzji, trwałe pokwitowanie oraz ponowienie.

## Out of scope

Inne gry i plansze, zmiana modelu symboli, hurtowe rozpoznawanie, trening.

## Acceptance criteria

- [x] Podgląd przypisuje 13 brakujących indeksów do `outside`.
- [x] Sześć plansz ma po 15 pozycji; istniejące identyfikatory i decyzje zachowane.
- [x] Ponowienie nie tworzy duplikatów, tylko odczytuje receipt.

## Expected files

- services/api/src/game_predictor_api/domain/partial_board_reconciliation.py
- scripts/reconcile_followup_777_board_positions.py
- services/api/tests/test_partial_board_reconciliation.py
- ai_docs/process/CURRENT_STATE.md

## Outcome

Preview SHA `7753a0d911b0503cac957d1540e6a7e02d15ef70a1d7c12e7cd86ade333f9da9`
zapisany w `.runtime/followup-777-six-preview-20260928.json`. Zapis sześciu
transakcji zakończony; każdy receipt ma `cellCount=15`. Kontrolne ponowienie
zwróciło `replayed=True` dla wszystkich sześciu. Odczyt bazy: 90 pozycji,
w tym 13 `outside` (3, 2, 3, 1, 2, 2). Nie wykonano zmiany innych plansz ani
automatycznego ponowienia wcześniejszej operacji użytkownika.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0718 | gpt-6-sol | high | Wrażliwa operacja danych z kontrolą rewizji i trwałości. | Niewymagany w tym osobnym zleceniu danych. |
