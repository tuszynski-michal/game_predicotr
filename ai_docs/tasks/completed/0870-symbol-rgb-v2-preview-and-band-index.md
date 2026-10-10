---
title: TASK-0870 — decyzja RGB v2 i indeks pasm w podglądzie
status: done
last_updated: 2026-10-06
---

# TASK-0870 — decyzja RGB v2 i indeks pasm w podglądzie

## Status

`done`

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

- [x] Kandydaci CNN identyczni z logitami zamrożonego snapshotu `approved-v2` (5688/5788 zgodnych z etykietami).
- [x] Testy reguły zapisu dla każdego wiersza tabeli przykładów planu.
- [x] Indeks pasm zmierzony dla ośmiu symboli; liczby w Outcome.

## Test cases

- `services/worker/tests/test_symbol_rgb_v2.py` (proponowany), `test_audit_rgb_classifier.py`, `test_evaluate_symbol_reference_library_script.py`.

## Outcome

- Numer: plan nadał TASK-0858; równoległy tor Mumii zajął 0858–0863, więc
  zadania planu mają TASK-0870–0878 (decyzja D-520 zamiast D-496).
- `services/worker/src/game_predictor_worker/symbols/rgb_v2.py`: pasma,
  status pewna/do przeglądu, `decide_rgb`, `needs_write` (reguła z tabeli planu).
- `scripts/symbol_rgb_v2.py` (osobny skrypt zamiast podkomendy
  `evaluate_symbol_reference_library.py`, żeby nie rozbudowywać 2,5-tysięcznego
  pliku; wspólne funkcje importowane jak w `recognize_grid_audit_symbols.py`):
  `index` (odczyt, części po skrócie md5 id), `preview` (render z kontrolą SHA,
  decyzja RGB v2 z zamrożonym checkpointem `1731869d…` i biblioteką
  `artifacts/grid-audit-symbols-20261005/library.npz`, wiersze, raport, HTML
  próbek) i `manifest` (wiązanie zatwierdzonych wierszy z bieżącymi rewizjami
  plansz tuż przed zapisem — po zapisie jednego symbolu wspólne plansze mają
  nowe rewizje, więc manifesty nie powstają przy podglądzie).
- Zgodność z obecną metodą na zamrożonym `approved-v2` (SHA `572722c8…`):
  kandydaci CNN identyczni z zapisanymi logitami 5788/5788, zgodność z
  etykietami 5688/5788 (98,27%). Potwierdzone 3391 (100% zgodnych — zawyżone,
  biblioteka pochodzi z zatwierdzeń), do przeglądu 2397 (95,8% zgodnych).
- Indeks pasm 2026-10-05 21:14 – 23:23 UTC (trzy równoległe odczyty, 256
  części, 0 komórek bez pierwotnej pewności): 7 412 524 komórek; < 60%
  16 481, 60–80% 54 356, 80–90% 59 261, 90–99% 273 843, 99–100% 7 008 583;
  źródło obecne: model 5 592 813, stara biblioteka 1 819 711. Wyniki w
  worktree `artifacts/symbol-rgb-v2/index/` (poza Gitem).
- Testy: `test_symbol_rgb_v2.py` 23 PASS; Ruff, format i mypy `--strict` dla
  nowych plików bez uwag. Audyt wstrzymany przez operatora (2026-10-01).
