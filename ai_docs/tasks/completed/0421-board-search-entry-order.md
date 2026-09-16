---
title: Board search entry order
status: done
task_id: TASK-0421
last_updated: 2026-09-03
---

# TASK-0421 — Kolejność wprowadzania wzoru planszy

## Goal

Pozwolić operatorowi wprowadzać częściowy wzór planszy kolumnami albo
wierszami, z kolejnością kolumnową jako ustawieniem domyślnym.

## Scope

- dodać deterministyczną kolejność `columns | rows` do czystego stanu edytora;
- domyślnie przechodzić pierwszą kolumnę z góry na dół, następnie kolejne;
- dodać wybór kolejności w UI `Wyszukaj plansze`;
- przy zmianie kolejności zachować wpisane komórki i wybrać pierwsze wolne pole
  w nowej kolejności;
- zachować kanoniczne indeksy komórek wysyłane do API;
- dodać testy obu porządków i zmiany porządku w trakcie edycji.

## Out of scope

- zmiana kontraktu API lub rankingu wyszukiwania;
- zmiana wizualnego układu planszy 3 × 5;
- trwałe zapisywanie preferencji operatora.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- pierwsze trzy wpisane symbole domyślnie trafiają do indeksów `0, 5, 10`;
- tryb wierszowy wpisuje kolejno do `0, 1, 2`;
- zmiana trybu nie zmienia zawartości wzoru;
- payload wyszukiwania nadal używa kanonicznych indeksów;
- testy, lint, typecheck i build Admina są zielone.

## Outcome

- Dodano wybór `Kolumnami / Wierszami`, z trybem kolumnowym jako domyślnym.
- Czysty edytor przechodzi deterministycznie po indeksach `0,5,10,1,...` albo
  `0,1,2,...`, a zmiana trybu zachowuje wszystkie wpisane komórki.
- Payload wyszukiwania nadal zawiera kanoniczne indeksy row-major.
- Weryfikacja:
  - `npm run test --workspace @game-predictor/admin` — 378 passed;
  - `npm run lint --workspace @game-predictor/admin` — passed;
  - `npm run typecheck --workspace @game-predictor/admin` — passed;
  - skoncentrowany `prettier --check` — passed;
  - `npm run admin:build` — passed.
