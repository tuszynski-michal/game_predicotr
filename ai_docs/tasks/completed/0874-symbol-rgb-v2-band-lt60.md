---
title: TASK-0874 — B7 — zapis RGB v2 dla pasma < 60% (osiem symboli)
status: done
last_updated: 2026-10-06
---

# TASK-0874 — B7 — zapis RGB v2 dla pasma < 60% (osiem symboli)

## Status

`done`

## Goal

Oczekujące komórki ośmiu symboli z pierwotną pewnością modelu < 60% dostają
predykcję RGB v2 tam, gdzie zmienia się symbol albo status pewna/do przeglądu
(D-520).

## Context

Etap B planu `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`. Operator
2026-10-05/06: uruchomić etap B i kontynuować bez pytań do napotkania problemu
nierozwiązywalnego; bramki pasm 1–4 przegląda wykonawca, bramka 99–100% wraca
do operatora.

## Dependencies / entry conditions

- Etap A (TASK-0870–0873) zakończony; indeks pasm gotowy.

## Recommended execution

`claude-opus-5-5`, reasoning `medium` (tabela planu).

## Relevant docs

- `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
- `ai_docs/guides/SYMBOL_RGB_V2_BAND_RUNBOOK.md`
- `ai_docs/process/DECISION_LOG.md` (D-520)

## Scope

- Podgląd 8 części (po jednej na symbol), przegląd próbek, zapis, weryfikacja.

## Out of scope

- Pozostałe pasma, zatwierdzanie komórek.

## Acceptance criteria

- [x] Przegląd próbek każdej klasy przed zapisem, wynik w Outcome.
- [x] Zapis bez błędów (plansze `stale` dopuszczalne i opisane).
- [x] `verify` każdej części zgodny z manifestem.

## Test cases

- Kanarek 3 plansz z odczytem bazy; `verify` po każdej części.

## Outcome

- Podgląd 2026-10-05 23:29–23:37 UTC: 16 481 komórek, 3 563 planowane zapisy.
  Przegląd próbek (arkusze po klasach): 3 227 zapisów to niepewne propozycje
  CNN wbrew jednogłośnej bibliotece, która wskazywała obecny symbol; próbki to
  gwiazdy i plastry arbuza przy dominancie barwnej proponowane jako cytryna /
  pomarańcz — błąd CNN. Reguła bramki `library_keeps_current`
  (`WRITE_RULES_VERSION = 2`, poprawka D-520, tabela planu): takich komórek się
  nie zapisuje. Pozostałe grupy obejrzane: pewne zmiany (65) poprawne
  (np. Arbuz → Gwiazda/Siedem/Winogron, Wiśnia → Gwiazda), pewne bez zmiany
  symbolu (39) poprawne, obniżenia do przeglądu (61, głównie przycięte wiśnie)
  zasadne, niepewne zmiany bez wsparcia biblioteki (171) mieszane — zapisane
  jako 0,50 do przeglądu zgodnie z decyzją operatora.
- Podgląd ponowiony 23:41–23:43 UTC z nowymi regułami: 336 zapisów
  (Arbuz 46, Cytryna 23, Gwiazda 21, Pomarańcz 51, Siedem 25, Śliwka 55,
  Winogron 12, Wiśnia 103).
- Kanarek 23:44 UTC (3 plansze Arbuza): odczyt bazy — rewizja `symbol-rgb-v2`,
  2 × ARBUZ 0,99 `confirmed`, 1 × CYTRYNA 0,50 `tentative`, wpis
  `referenceLibrary` usunięty, przypisany symbol zgodny, komórki `pending`.
- Zapis 23:44–23:50 UTC: 336 komórek na 324 planszach, 0 błędów, 0 `stale`;
  `verify` każdej części: wszystkie cele `rgb_prediction`. Manifesty i
  pokwitowania w worktree `artifacts/symbol-rgb-v2/runs/lt60/` (poza Gitem).
