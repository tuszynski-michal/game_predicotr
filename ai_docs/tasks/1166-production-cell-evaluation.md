---
title: Ocena produkcyjnych wycinków i monotoniczna bramka
status: todo
last_updated: 2026-11-08
---

# TASK-1166 — Ocena produkcyjnych wycinków i monotoniczna bramka

## Status

`todo`

## Goal

Porównywać zawartość tych samych komórek na rzeczywistych wycinkach,
bez ukrycia braków, pomylenia pól i kompensowania nowych błędów.

## Dependencies / entry conditions

T1–T2 implementacja gotowa, dopuszczalne przesunięcie audytu wyłącznie
przy limicie Opus; brak rzeczywistych etykiet daje not_evaluable.

## Recommended execution

gpt-6-astra/high; dodatkowy review Claude Code claude-opus-5-5/high.

## Relevant docs

- AGENTS.md
- ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md (T3)
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/decisions/DECISION_LOG_2026.md (D-578/587/588)
- ai_docs/architecture/CODE_MAP.md

## Scope

T3 w całości: VirtualCellRenderer/classifier/padding snapshot, float64,
u i ε tylko numeryczny, trzy stany zawartości/missing, macierz przypisania,
per-instance pogorszenie, nowe ruleVersion i readery/publikacja/default.
Stara bramka i raporty zachowują interpretację. Wymagana baza3ed60010,
kandydat9992a316 jedynie komparator informacyjny.

## Acceptance criteria

- [ ] Ten sam sourceSHA/board/cell i stały mianownik dla bazy/kandydata.
- [ ] preserved/borderline/clipped/missing i wrong-cell/remis/obcy pełny symbol.
- [ ] Brak kompensacji nowych błędów przez poprawę innych instancji.
- [ ] NME_k≤NME_b+δ i brak regresji metryk per gra A/REG, FP na pełnych zdjęciach.
- [ ] Bieżąca gra świeżyREG ≥1 dodatkowa użyteczna plansza; odrzuć-all nie daje sukcesu.
- [ ] Brak danych/etykiet/pełnych zdjęć blokuje odpowiedni dowód i zastosowanie.
- [ ] Historyczne reguły, raporty i ludzkie korekty pozostają bez zmian.
- [ ] Testy/kontrakt/scoped lint/types/docs/map i audyt.

## Expected files

API domain/grid_correction_evaluation.py i full_board_calibration*.py;
worker images/full_board_completeness.py, grid_model_evaluation*,
virtual_cell_extraction.py, readery/piny raportów. Rozwinąć po scoped inspekcji.

## Test cases

Przesunięta granica rzędu bez zmiany outerquad; wrong-row/column, brakdetekcji,
foreignsymbol, remisy, borderline→clipped, odrzucenie wszystkiego, nierówne
źródła, częściowe zdjęcia, epsilon i δ jednostki, stare wersje.

## Verification

Testy pionu/metriki/raporty/API/PG, lint/types/docs/map z timeoutami;
dokładne wyniki quality/TASK-1166_VERIFICATION.md.

## Outcome

Nie rozpoczęto.
