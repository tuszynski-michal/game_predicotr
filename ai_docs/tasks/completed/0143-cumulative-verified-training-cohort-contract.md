---
title: TASK-0143 cumulative verified training cohort contract
status: done
last_updated: 2026-08-01
---

# TASK-0143 — Cumulative verified training cohort contract

## Status

`done`

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

- [x] Kohorta jednej gry ma niezmienny manifest i SHA-256 zależne od pełnej
      zawartości oraz pochodzenia.
- [x] Do kohorty wchodzą tylko kompletne plansze `accepted` lub `corrected` z
      zaakceptowaną geometrią i wszystkimi etykietami komórek.
- [x] `rejected`, `pending`, niekompletne oraz obce grze elementy nie wchodzą do
      treningu.
- [x] Identyczne wejście zwraca istniejącą kohortę; zmienione wejście tworzy
      nową wersję i nie nadpisuje poprzedniej.
- [x] Kontrakt zapisuje crop checksum, source image, pipeline i geometry
      revision potrzebne do odtworzenia danych.
- [x] Test udowadnia, że żądanie zapisu automatycznej predykcji nie może zmienić
      `accepted`, `corrected` ani `rejected`.
- [x] Schema powstaje wyłącznie przez migrację Alembic, a OpenAPI używa typów
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

Dodano migrację `0034_verified_training_cohorts`, modele nagłówka i pozycji,
game-scoped preview oraz idempotentne freeze przez Admin API. Manifest jest
content-addressed, korzysta ze wspólnego adaptera kompletnej planszy istniejącego
eksportu review i nie zapisuje obrazów w PostgreSQL. Pozycje wiążą import,
source image, review, rewizję geometrii, pipeline i 15 checksum-bound cropów.

Polityka domenowa i blokada repozytorium dopuszczają automatyczną predykcję
wyłącznie dla bieżącego `pending` ze zgodnymi rewizjami. Testy dowodzą ochrony
`accepted`, `corrected` i `rejected`, wykluczanie danych niekompletnych,
idempotencję, nową iterację po zmianie etykiety, migrację i kontrakt OpenAPI.

Weryfikacja: 60 skupionych testów i izolowany cykl PostgreSQL
upgrade → downgrade → upgrade `passed`, Ruff `passed`, OpenAPI i generowany
klient `current`, a klient TypeScript przeszedł 32/32 testy. Pełny mypy nadal
raportuje istniejący problem klasyfikowania
pakietu `game_predictor_worker` jako zewnętrznego bez `py.typed`; nie wykazał
błędu specyficznego dla kohorty. UI, dataset, trening, ONNX i inferencja pozostają
poza zakresem zgodnie z zadaniem. Lokalny PostgreSQL został kontrolowanie
podniesiony z `0033` do `0034` przy zatrzymanych workerach; oba lane następnie
wróciły do `running`, a nowe logi błędów pozostały puste.
