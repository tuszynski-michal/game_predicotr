---
title: TASK-0878 — B11 — zapis RGB v2 dla pasma 99–100% (osiem symboli)
status: blocked
last_updated: 2026-10-06
---

# TASK-0878 — B11 — zapis RGB v2 dla pasma 99–100% (osiem symboli)

## Status

`blocked` — bramka operatora: skala obniżeń do przeglądu (plan, ryzyko 1).

## Goal

Oczekujące komórki ośmiu symboli z pierwotną pewnością modelu ≥ 99% dostają
predykcję RGB v2 według reguł D-520 i decyzji operatora na bramce.

## Context

Etap B planu `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`; bramka tego
pasma należy do operatora. Pasmo: 7 008 583 komórek, 120 części po ≤ 60 000.

## Dependencies / entry conditions

- TASK-0874–0877 zakończone.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (tabela planu).

## Relevant docs

- `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
- `ai_docs/guides/SYMBOL_RGB_V2_BAND_RUNBOOK.md`
- `ai_docs/process/DECISION_LOG.md` (D-520)

## Scope

- Podgląd 120 części, zapis wg decyzji, weryfikacja.

## Out of scope

- Zatwierdzanie komórek.

## Acceptance criteria

- [ ] Decyzja operatora na bramce.
- [ ] Zapis bez błędów; `verify` każdej części zgodny z manifestem.

## Technical notes

- Próbka bramki 2026-10-06 02:31–04:44 UTC: część 1 każdego symbolu
  (468 365 komórek, ~17,5 min podglądu na część). Zapisy wg obecnych reguł:
  obniżenia do przeglądu (ten sam symbol, biblioteka niejednogłośna) 58 957
  (12,6%; Cytryna 39 646 z 58 621 = 68%), pewne zmiany symbolu 190, niepewne
  zmiany 23; chronione regułą biblioteki 889.
- Ekstrapolacja na całe pasmo: obniżenia ~0,99 mln (Cytryna ~713 tys.,
  Śliwka ~84 tys., Arbuz ~61 tys., Pomarańcz ~47 tys., Siedem ~38 tys.,
  Winogron ~33 tys., Wiśnia ~7 tys., Gwiazda ~5 tys.), pewne zmiany ~2,8 tys.,
  niepewne zmiany ~350.
- Próbki: obniżane komórki mają prawie zawsze poprawny symbol (cytryny,
  siódemki, winogrona, gwiazdy); pewne zmiany poprawiają rzeczywiste błędy
  modelu (np. Śliwka → Wiśnia, Siedem → Gwiazda).
- Czas: podgląd pozostałych 112 części ~33 h; zapis przy obniżeniach ~30 h,
  bez obniżeń minuty na część.

## Test cases

- `verify` po każdej części.

## Outcome

Brak.
