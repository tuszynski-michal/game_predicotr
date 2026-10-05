---
title: TASK-0858 — decyzja RGB v2 i indeks pasm w podglądzie
status: todo
last_updated: 2026-10-05
---

# TASK-0858 — decyzja RGB v2 i indeks pasm w podglądzie

## Status

`todo`

## Goal

Podgląd przebiegu wybiera symbol metodą RGB v2 (argmax `SpatialSymbolCnn` na oryginalnym cropie, potwierdzenie jednomyślną biblioteką 7/7 z zamrożonego `artifacts/grid-audit-symbols-20261005/library.npz`) i buduje manifest tylko komórek, w których symbol albo status pewna/do przeglądu się zmienia; zakres wybierany z indeksu pasm według pierwotnej pewności modelu.

## Context

Etap A planu `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
(zaakceptowany przez operatora 2026-10-05). Metoda i ograniczenia:
`ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md`.

## Dependencies / entry conditions

- Plan zaakceptowany; poprzednie taski etapu A wykonane w kolejności planu.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (zgodnie z tabelą planu; audyt wstrzymany
przez operatora 2026-10-01).

## Relevant docs

- `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
- `ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md`
- `ai_docs/process/DECISION_LOG.md` (D-466)

## Scope

- Odczytowy eksport indeksu pasm per symbol (obecny symbol, obecna pewność i źródło, pierwotna pewność modelu, pasmo), porcjami, wznawialnie.
- Podgląd RGB v2 dla (symbol, pasmo, część): render z kontrolą SHA (istniejący cache), kandydat CNN, potwierdzenie biblioteką, reguła zapisu z tabeli planu, manifest, raport, HTML z próbką ≤ 40 na parę (obecny → nowy, status).

## Out of scope

- Zapis w bazie operatora (etap B), trening i zmiana checkpointu CNN,
  zatwierdzanie komórek, geometria.

## Acceptance criteria

- [ ] Kandydaci CNN identyczni z logitami zamrożonego snapshotu `approved-v2` (5688/5788 zgodnych z etykietami).
- [ ] Testy reguły zapisu dla każdego wiersza tabeli przykładów planu.
- [ ] Indeks pasm zmierzony dla ośmiu symboli; liczby w Outcome.

## Test cases

- `services/worker/tests/test_symbol_rgb_v2.py` (proponowany), `test_audit_rgb_classifier.py`, `test_evaluate_symbol_reference_library_script.py`.

## Outcome

Brak.
