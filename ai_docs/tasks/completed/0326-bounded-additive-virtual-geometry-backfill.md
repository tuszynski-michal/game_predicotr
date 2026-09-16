---
title: TASK-0326 bounded additive virtual geometry backfill
status: done
last_updated: 2026-08-30
---

# TASK-0326 — Bounded backfill addytywnych kontraktów geometrii wirtualnej

## Status

`done`

## Goal

Rozszerzyć istniejący, trwały job walidacji rolloutu o idempotentny i
wznawialny backfill jednoznacznych pól dodanych przez migrację 0084. Backfill
ma przygotować raport zgodności wymagany przed późniejszym cutoverem odczytów,
bez zmiany etykiet człowieka, canonical ownership i historycznych eventów.

## Relevant docs

- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/tasks/completed/0325-additive-virtual-geometry-schema-corrections.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Wyprowadzać logical-cell-v2 i render-identity-v2 z historycznego,
  checksummed render specu oraz niezmiennego occurrence/topology context.
- Uzupełniać fingerprint topologii i checksumę attestation na source geometry
  revisions jednej gry.
- Uzupełniać v2 identity na virtual observations, bieżących review cells i
  zamrożonych verified training cells.
- Uzupełniać jawny outcome v2 tylko dla jednoznacznych bieżących review cells;
  nie reinterpretować modelowej sugestii jako decyzji człowieka.
- Wykorzystać istniejący `image_geometry_rollout_backfill` w general lane,
  partie maksymalnie 100 źródeł i trwały kursor po source image.
- Zapisywać liczniki backfillu w checkpointach joba i wymagać pełnej zgodności
  przed stanem `ready`.
- Zachować retry jako idempotentny: wartości istniejące muszą dokładnie zgadzać
  się z wyliczonym kontraktem, a konflikt kończy się fail-closed.

## Out of scope

- Bez przełączania publicznych read pathów i indeksów z v1 na v2.
- Bez przepisywania append-only `image_symbol_review_events`.
- Bez renderowania obrazów, zmiany verified labels i tworzenia assetów.
- Bez uruchamiania migracji 0084, backfillu lub cutoveru na bazie użytkownika.
- Bez zmiany algorytmu geometrii, progów, API publicznego i UI.
- Bez dołączania niezwiązanych zmian importu v20 i stagingu z worktree.

## Acceptance criteria

- [x] Historyczny render spec daje dokładnie te same v2 identity co nowy writer.
- [x] Istniejące, zgodne wartości są idempotentne; rozbieżność jest błędem.
- [x] Source revisions, observations, current reviews i verified cohorts są
      przetwarzane bez odczytu pikseli.
- [x] Niejednoznaczny outcome pozostaje nullable i blokuje `ready`.
- [x] Job wznawia się od trwałego kursora oraz raportuje liczniki kategorii.
- [x] Nowy virtual write powstały po minięciu kursora jest objęty finalną
      kontrolą stabilności.
- [x] Legacy rows i historyczne eventy pozostają niezmienione.
- [x] Testy repozytorium/workera, Ruff i scoped mypy przechodzą.
- [x] Nie wykonano operacji na danych użytkownika ani cutoveru odczytów.

## Planned commit

`v0.10.19 - backfill additive virtual geometry contracts`

## Outcome

Istniejący `image_geometry_rollout_backfill` otrzymał wersjonowany input v3 i
metadata-only etap backfillu addytywnych kontraktów 0084. Jedna transakcja
obejmuje maksymalnie 100 source images. Trwały checkpoint raportuje osobno
source revisions, observations, current review cells i frozen verified
training cells.

Historyczne checksummed render specs są deterministycznie wiązane z occurrence
i przypiętą topologią. Istniejące wartości muszą dokładnie odpowiadać
wyliczeniu. Bieżący jawny outcome nie promuje sugestii modelu, a niejasny stan
pozostaje nullable i kończy przebieg fail-closed. Finalizacja kontroluje nowe
źródła i pozostałe braki przed `ready`.

Skorygowano też istniejącą niespójność serializacji joba: OpenAPI i generowany
klient zachowują replay schema 1/2 i obsługują schema 3 z wymaganą wersją
backfillu. Nie zmieniono endpointów ani UI.

Weryfikacja objęła 142 testy API/workera, Ruff, scoped mypy oraz kontrolę
OpenAPI/generowanego klienta. Nie uruchomiono migracji, joba, backfillu ani
cutoveru na danych użytkownika.
