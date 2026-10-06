---
title: TASK-0875 — B8 — zapis RGB v2 dla pasma 60–80% (osiem symboli)
status: done
last_updated: 2026-10-06
---

# TASK-0875 — B8 — zapis RGB v2 dla pasma 60–80% (osiem symboli)

## Status

`done`

## Goal

Oczekujące komórki ośmiu symboli z pierwotną pewnością modelu 60–80% dostają
predykcję RGB v2 tam, gdzie zmienia się symbol albo status pewna/do przeglądu
(D-520 z poprawką z TASK-0874).

## Context

Etap B planu `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`. Bramkę
pasma przegląda wykonawca (polecenie operatora 2026-10-06).

## Dependencies / entry conditions

- Poprzednie pasmo zapisane i zweryfikowane.

## Recommended execution

`claude-opus-5-5`, reasoning `medium` (tabela planu).

## Relevant docs

- `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
- `ai_docs/guides/SYMBOL_RGB_V2_BAND_RUNBOOK.md`
- `ai_docs/process/DECISION_LOG.md` (D-520)

## Scope

- Podgląd części (≤ 60 000 komórek), przegląd próbek kategorii, zapis, weryfikacja.

## Out of scope

- Pozostałe pasma, zatwierdzanie komórek.

## Acceptance criteria

- [x] Przegląd próbek każdej kategorii przed zapisem, wynik w Outcome.
- [x] Zapis bez błędów (plansze `stale` dopuszczalne i opisane).
- [x] `verify` każdej części zgodny z manifestem.

## Test cases

- `verify` po każdej części.

## Outcome

- Podgląd 2026-10-05 23:45 – 10-06 00:06 UTC: 54 356 komórek, 600 zapisów
  (pewne zmiany 164, pewne bez zmiany symbolu 85, obniżenia do przeglądu 183,
  niepewne zmiany bez wsparcia biblioteki 168); 13 564 komórek chronionych
  regułą `library_keeps_current`.
- Przegląd próbek: pewne zmiany poprawne (wiśnie, śliwki, winogrona, gwiazdy,
  siódemki, pomarańcze); komórki chronione to błędy CNN (siódemki i gwiazdy
  jako winogrono / pomarańcz); obniżenia zgodne z regułą (często poprawny
  symbol bez jednomyślnej biblioteki).
- Zapis 00:07–00:13 UTC: 599 z 600 komórek `rgb_prediction` na 553 planszach,
  0 błędów; 1 plansza `stale:SYMBOL_REFERENCE_TARGET_QUALITY_CHANGED`
  (Pomarańcz, komórka dostała flagę jakości przy odświeżeniu; bez zmian).
