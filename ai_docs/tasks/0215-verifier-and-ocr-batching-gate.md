---
title: TASK-0215 verifier and OCR batching gate
status: in_progress
release: "0.4"
last_updated: 2026-08-09
---

# TASK-0215 — Bramka verifierów i batchowania

## Goal

Porównać jeden/dwa verifiery bez konkurencji CPU i opcjonalnie batchować te
same cropy OCR. Wariant szybszy może zwiększyć manual review, ale nie może
tworzyć błędnych automatycznych zakresów.

## Verification

Canonical diff, pomiar czasu i jawna decyzja aktywacji albo odrzucenia.

## Outcome

Profil wycinka używa teraz aktywnego manifestu v10.2 zamiast przypiętego v10.1.
Dodano kontrolowany skrypt `scripts/run_image_selection_verifier_gate.py`, który
uruchamia sekwencyjnie jeden i dwa izolowane verifiery na identycznym wycinku,
ogranicza wątki bibliotek natywnych, stosuje osobny timeout każdego przebiegu i
porównuje kanonicznie granice, zakresy, statusy, reprezentantów oraz shortlisty.
Dwa verifiery mogą zostać zalecone wyłącznie przy identycznym wyniku i zysku co
najmniej 10%; w każdym innym przypadku raport wymusza `keep_one_verifier`.

Pełna zawężona regresja selekcji przechodzi 127/127. Realny pomiar 1 vs 2 na
tym samym stagingu pozostaje odroczony do kontrolowanego okna bez konkurujących
jobów. Produkcja nadal używa jednego verifiera. Istniejące recognizery już
batchują kotwice oraz kolejne poziomy fallbacku; dodatkowe batchowanie między
kandydatami nie zostanie aktywowane bez pomiaru wykazującego potrzebę i parity.
