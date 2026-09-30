---
title: TASK-0772 — Poprawianie symbolu pola z okna planszy „Przybliżonej wygranej”
status: todo
last_updated: 2026-09-30
---

# TASK-0772 — Poprawianie symbolu pola z okna planszy

## Status

`todo`

## Goal

Operator poprawia błędnie rozpoznany symbol pola bezpośrednio w oknie planszy
z liniami wypłat, a linie, tabela i bilans przeliczają się z poprawionych
danych.

## Context

Po odbiorze etapu A operator wskazał planszę #66321: linia Arbuz × 5 (2500)
przechodzi przez pole z „7” rozpoznane jako Arbuz; poprawnie Arbuz × 3
(250). Decyzja D-473, plan §3 R6 i §5 T5b.

## Dependencies / entry conditions

- TASK-0763 i TASK-0764 done (`v1.7.86`, `v1.7.87`).

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz T5b w tabeli planu). Zapis
decyzji człowieka do żywych danych istniejącym mechanizmem. Audyt:
niezależny agent `claude-opus-5-5` (`high` warunkowo). Dwa nieudane cykle
poprawek P0–P2 zatrzymują pracę.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- `cells[15] | null` w szczegółach planszy (dane do mutacji pola).
- Tryb „Popraw symbole” w oknie, paleta, zapis istniejącym
  `applySingleSymbolReviewDecision`, ponowne pobranie szczegółów,
  przeliczenie tabeli po zamknięciu okna ze zmianą.

## Out of scope

- Korekta plansz zatwierdzonych i archiwalnych.
- Nowy endpoint zapisu; zmiany w „Weryfikacji symboli”.

## Acceptance criteria

- [ ] Plansza oczekująca: 15 pól z identyfikatorem, rewizją, rewizją
  geometrii, próbką i sumą cropa; zatwierdzona i archiwum → `cells = null`.
- [ ] Wybór innego symbolu → `reassign`, ten sam → `approve`,
  „Nieczytelny” → `mark_unreadable`, „Zła siatka” → `mark_grid_issue`, z
  oczekiwaną rewizją i sumą.
- [ ] Po zapisie okno pobiera szczegóły ponownie i rysuje nowe linie.
- [ ] Konflikt rewizji → komunikat i odświeżenie szczegółów.
- [ ] Zamknięcie okna po zmianie przelicza tabelę.
- [ ] Brak edycji dla plansz zatwierdzonych.

## Technical notes

Plan §3 R6 i §5 T5b. Pola tylko bieżącej planszy i rewizji geometrii
(reguła `_current_cell_decisions`). Po zmianie w oknie bramka zgodności z
wierszem tabeli jest pomijana (tabela jest znana jako nieaktualna), ale suma
linii nadal musi równać się wypłacie.

## Expected files

Patrz plan §5 T5b.

## Test cases

Patrz plan §5 T5b.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_board_detail_api.py
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

- Poprawka zapisuje decyzję człowieka w żywej bazie; da się ją zmienić
  kolejną decyzją.

## Outcome

Wypełnia agent po pracy.
