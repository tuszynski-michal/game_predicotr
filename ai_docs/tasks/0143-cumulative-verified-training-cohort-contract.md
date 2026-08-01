---
title: TASK-0143 cumulative verified training cohort contract
status: todo
last_updated: 2026-08-01
---

# TASK-0143 — Cumulative verified training cohort contract

## Status

`todo`

## Goal

Utworzyć game-scoped, niezmienny i checksum-bound kontrakt kohorty treningowej,
który wykorzystuje wyłącznie kompletne decyzje człowieka i chroni wszystkie
rozstrzygnięte plansze przed automatyczną zmianą.

## Context

Kolejne wersje klasyfikatora muszą korzystać ze skumulowanych danych 100,
1000 i kolejnych plansz bez utraty pochodzenia. Istniejący eksport zweryfikowanej
kohorty nie stanowi jeszcze rejestru iteracji treningowych ani twardej granicy
dla późniejszej ponownej inferencji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_06_6_EXECUTION_PLAN.md`

## Scope

- dodać migrację Alembic dla rejestru zamrożonych kohort i ich pozycji,
- wiązać pozycję z grą, rozstrzygnięciem review, rewizją, geometrią, cropami,
  etykietami człowieka, źródłem i checksumami,
- kwalifikować do treningu tylko pełne `accepted` i `corrected`,
- zachować `rejected` jako chronione rozstrzygnięcie, ale wykluczyć z danych
  treningowych,
- zapewnić idempotentne utworzenie tej samej kohorty,
- dodać domenową politykę, że operacje modelu mogą pisać predykcje tylko dla
  aktualnego `pending`,
- pokryć regułę ochrony testami bazy i warstwy aplikacyjnej.

## Out of scope

- panel Admina,
- budowa plikowego datasetu,
- trening i eksport ONNX,
- aktywacja modelu,
- właściwa masowa ponowna inferencja.

## Acceptance criteria

- [ ] Kohorta jednej gry ma niezmienny manifest i SHA-256 zależne od pełnej
      zawartości oraz pochodzenia.
- [ ] Do kohorty wchodzą tylko kompletne plansze `accepted` lub `corrected` z
      zaakceptowaną geometrią i wszystkimi etykietami komórek.
- [ ] `rejected`, `pending`, niekompletne oraz obce grze elementy nie wchodzą do
      treningu.
- [ ] Identyczne wejście zwraca istniejącą kohortę; zmienione wejście tworzy
      nową wersję i nie nadpisuje poprzedniej.
- [ ] Kontrakt zapisuje crop checksum, source image, pipeline i geometry
      revision potrzebne do odtworzenia danych.
- [ ] Test udowadnia, że żądanie zapisu automatycznej predykcji nie może zmienić
      `accepted`, `corrected` ani `rejected`.
- [ ] Schema powstaje wyłącznie przez migrację Alembic, a OpenAPI używa typów
      backendu.

## Technical notes

Kohorta ma obejmować pełny skumulowany stan w chwili zamrożenia, nie tylko
delta od poprzedniej iteracji. Delta może być metryką UI. Nie wolno kopiować
obrazów do PostgreSQL.

## Expected files

- `services/api/alembic/versions/*_verified_training_cohorts.py`
- `services/api/src/game_predictor_api/domain/`
- `services/api/src/game_predictor_api/application/`
- `services/api/src/game_predictor_api/infrastructure/`
- `services/api/tests/`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
python -m pytest services/api/tests -q
npm.cmd run openapi:check
```

## Risks / open questions

- Istniejące eksporty zweryfikowanych kohort należy wykorzystać przez adapter
  lub migrację kontraktu, bez dublowania źródła prawdy.

## Outcome

Do uzupełnienia po realizacji.
