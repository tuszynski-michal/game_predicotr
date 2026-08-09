---
title: TASK-0215 verifier and OCR batching gate
status: done
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

Pełna zawężona regresja selekcji przechodzi 127/127. Kontrolowana bramka na
pierwszych 200 rzeczywistych zdjęciach zakończyła się kanonicznie identycznym
wynikiem obu wariantów. Jeden verifier trwał 123,427 s, dwa 118,363 s, czyli
zysk wyniósł tylko 4,10% i nie osiągnął progu 10%. Raport
`artifacts/image-selection-v102-verifier-gate-task0215.json` wymusza decyzję
`keep_one_verifier`; produkcja nadal używa jednego verifiera. Istniejące recognizery już
batchują kotwice oraz kolejne poziomy fallbacku; dodatkowe batchowanie między
kandydatami nie zostanie aktywowane bez pomiaru wykazującego potrzebę i parity.
