---
title: TASK-0127 Single rules workspace with internal immutable versioning
status: done
last_updated: 2026-07-31
---

# TASK-0127 — Single rules workspace with internal immutable versioning

## Status

`done`

## Goal

Pokazać administratorowi jeden bieżący workspace reguł bez eksponowania listy
technicznych wersji, zachowując pełną niezmienność opublikowanych konfiguracji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- wybrać jako bieżącą najnowszą wersję draft, a w razie jej braku najnowszą
  opublikowaną wersję gry,
- ukryć techniczną listę historii z głównego workspace'u,
- pierwszą konfigurację nadal tworzyć z jawnych wymiarów i kosztu spinu,
- rozpoczęcie edycji opublikowanej wersji tworzy lub zwraca jeden bieżący draft,
- nowy draft kopiuje wymiary, koszt, paylines, konfiguracje symboli i payouty,
- operacje edycji, publikacji, paylines i payoutów działają wyłącznie na draft,
- opublikowana wersja, stare wersje i źródła wydań nie są modyfikowane ani
  usuwane.

## Expected files

- `services/api/src/game_predictor_api/application/rules.py`
- `services/api/src/game_predictor_api/storage/rules_repository.py`
- `services/api/src/game_predictor_api/api/rules.py`
- `packages/admin-api-client/`
- `apps/admin/src/features/rules/`
- testy API, klienta i Admina,
- dokumentacja kontraktu, decyzji i bieżącego stanu.

## Acceptance criteria

- [x] główny ekran pokazuje najwyżej jeden bieżący workspace reguł,
- [x] najnowszy draft ma pierwszeństwo przed opublikowaną wersją,
- [x] edycja opublikowanej wersji tworzy pełną kopię w nowym drafcie,
- [x] ponowienie nie tworzy kolejnego draftu,
- [x] źródłowa opublikowana wersja i jej rekordy pozostają niezmienne,
- [x] pierwszy draft nadal można utworzyć bez wersji źródłowej,
- [x] loading, empty, error i status wersji są jawne,
- [x] OpenAPI, testy backendu, klienta i Admina przechodzą.

## Outcome

Admin pokazuje jeden bieżący workspace: najnowszy draft albo, gdy go nie ma,
najnowszą opublikowaną konfigurację. Pierwszy draft nadal powstaje z jawnych
wymiarów i kosztu. Przycisk rozpoczęcia edycji opublikowanej konfiguracji używa
nowego endpointu `POST /rules-versions/{id}/draft`, który atomowo kopiuje pełną
konfigurację i przy ponowieniu zwraca istniejący draft.

Backend zachowuje niezmienność źródła i nadaje nowe identyfikatory skopiowanym
paylines oraz payout rules. Typowany klient został odtworzony z OpenAPI, a testy
obejmują wybór workspace'u, akcję UI, idempotentne kopiowanie i zachowanie
rekordów źródłowych. Zmiana nie wymaga migracji schematu.
