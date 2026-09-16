---
title: TASK-0461 Optional board area registration
status: done
---

# TASK-0461 — Opcjonalny wybór wariantu i trwałe przypięcie

## Goal

Udostępnić przy preflighcie jawny wybór standardowej rejestracji v0.10 albo
testowej rejestracji z maską obszaru plansz, bez zmiany ustawienia domyślnego.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Dependencies

- TASK-0460 — wariant maskowanych cech kotwicy.

## Scope

- addytywny wybór `standard_v0_10 | board_area_test` w istniejącym starcie
  preflightu;
- osobna wersja polityki preflightu i profil rejestracji w utrwalonym payloadzie;
- odrębna tożsamość joba dla innego wariantu oraz idempotencja identycznego
  żądania;
- zgodny pion backend → OpenAPI → klient → Admin;
- standardowy wariant pozostaje domyślny.

## Definition of Done

- retry odtwarza dokładnie przypięty wariant;
- nieznana wersja jest odrzucana fail-closed;
- wybór testowy nie zmienia historycznych manifestów ani ręcznych decyzji;
- API, klient i UI mają jeden spójny kontrakt;
- testy API, workera i Admina przechodzą.

## Outcome

- Istniejący endpoint przyjmuje domyślny `standard_v0_10` albo jawny
  `board_area_test`; Admin udostępnia oba wybory przed uruchomieniem joba.
- Wariant testowy przypina osobną politykę preflightu, profil maski i padding.
  Inny wariant zmienia input key, identyczne żądanie pozostaje idempotentne,
  a worker sprawdza zgodność wersji fail-closed.
- OpenAPI i klient zostały wygenerowane. Przeszły 72 testy API/workera, 22
  testy Admina, Ruff oraz typecheck Admina i klienta.
