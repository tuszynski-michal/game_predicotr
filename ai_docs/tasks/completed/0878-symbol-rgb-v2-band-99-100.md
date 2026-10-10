---
title: TASK-0878 — B11 — zapis RGB v2 dla pasma 99–100% (osiem symboli)
status: done
last_updated: 2026-10-07
---

# TASK-0878 — B11 — zapis RGB v2 dla pasma 99–100% (osiem symboli)

## Status

`done`

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

- [x] Decyzja operatora na bramce: tylko zmiany symbolu (2026-10-06).
- [x] Zapis bez błędów; `verify` każdej części zgodny z manifestem.

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

- Decyzja operatora 2026-10-06: tylko zmiany symbolu (`SYMBOL_CHANGES_ONLY_BANDS`,
  poprawka D-520).
- Podgląd 120 części 2026-10-06 05:59 – 2026-10-07 04:53 UTC (dwa sterowniki
  równolegle, cache wycinków kasowany po części — na C: było 27 GB wolnego);
  przerwa 17:28 UTC przez chwilowy brak połączenia z bazą
  (`psycopg.errors.ConnectionTimeout`), wznowienie 17:30 UTC bez utraty części.
  7 008 583 komórek; zapisy 2 958 (pewne 2 585, niepewne 373). Największe
  grupy: Śliwka → Pomarańcz 260, → Wiśnia 213, → Gwiazda 144, → Arbuz 142,
  → Winogron 118, → Siedem 108; Cytryna → Wiśnia 102.
- Przegląd próbek (miniatury kontekstu): pewne zmiany poprawne (rzeczywiste
  błędy modelu), niepewne mieszane — część trafnych cytryn; zapisane 0,50 do
  przeglądu.
- Zapis 2026-10-07 04:54–05:36 UTC: 2 958 z 2 958 komórek `rgb_prediction` na
  2 809 planszach, 0 błędów, 0 `stale`; `verify` 120/120 części zgodny.
  Per symbol obecny: Śliwka 1 168, Cytryna 441, Arbuz 293, Pomarańcz 282,
  Wiśnia 248, Siedem 200, Winogron 196, Gwiazda 130.
