---
title: TASK-0305 — Zastępcze zdjęcie pojedynczej planszy 0.10
status: todo
last_updated: 2026-08-28
---

# TASK-0305 — Zastępcze zdjęcie pojedynczej planszy 0.10

## Goal

Pozwolić operatorowi dodać nowe zdjęcie dla jednego numeru planszy, utworzyć
z niego niezależne źródło i wynik rozpoznania oraz świadomie przełączyć
kanonicznego właściciela sekwencji bez utraty historii poprzedniego źródła.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- upload jednego nowego źródła przypisanego do gry i `sequence_number`,
- checksumowana, content-addressed kopia źródła poza głównymi tabelami,
- osobny `recognized_board` oraz komplet geometrii/cropów zależny od topologii,
- review etykiet i jakości według modelu 0.9,
- jawny preview porównania z bieżącym właścicielem,
- atomowe przełączenie `image_sequence_canonical`, stagingu, kolejki,
  fast documents i projekcji komórek,
- pełny append-only audyt oraz human-wins przy konflikcie rewizji.

## Out of scope

- automatyczne zastępowanie zatwierdzonej planszy na podstawie confidence,
- nadpisywanie lub usuwanie poprzednich źródeł i cropów,
- upload całego nowego stagingu,
- zmiana topologii przypiętej do gry,
- użycie `?` jako symbolu katalogowego.

## Invarianty

- nowy obraz nigdy nie nadpisuje istniejącego pliku ani rekordu,
- numer sekwencji pochodzi z jawnej decyzji operatora,
- bieżący canonical pozostaje aktywny do atomowego zatwierdzenia zamiany,
- konflikt rewizji lub checksummy nie może częściowo zmienić właściciela,
- poprzedni właściciel pozostaje audytowalny jako źródło zastąpione,
- nowy crop nie jest treningowy bez zatwierdzonej proweniencji 0.9.

## Acceptance criteria

- identyczny retry uploadu i decyzji jest idempotentny,
- inne bajty z tym samym kluczem idempotencji są blokowane,
- niezatwierdzony kandydat nie zmienia canonical,
- zatwierdzona zamiana aktualizuje wszystkie projekcje w jednej transakcji,
- restart procesu zachowuje źródło, postęp i decyzję,
- stary właściciel i jego audyt pozostają dostępne,
- zdalny Reviewer nie otrzymuje szerszych uprawnień bez osobnej decyzji.

## Status

Zadanie jest celowo odroczone poza wersję 0.9. Przed implementacją wymaga
osobnego breakdownu API, transakcji i UX.
