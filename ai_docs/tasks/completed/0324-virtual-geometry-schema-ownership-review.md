---
title: TASK-0324 virtual geometry schema ownership review
status: done
last_updated: 2026-08-30
---

# TASK-0324 — Virtual Geometry Schema Ownership Review

## Status

`done`

## Goal

Ustalić jednoznacznego kanonicznego właściciela source-level i board-level
geometrii po wdrożeniu addytywnego fundamentu 0082. Review ma wykryć
duplikowane odpowiedzialności i zaprojektować późniejszą addytywną korektę bez
zmiany zastosowanej migracji, danych użytkownika ani aktywnych write paths.

## Relevant docs

- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/quality/V0_10_VIRTUAL_GEOMETRY_CUTOVER.md`
- `ai_docs/quality/STRUCTURED_GEOMETRY_FEASIBILITY_SPIKE_V1.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Zinwentaryzować geometrię, topologię, active slots, provenance renderu i
  rollout w migracji 0082, ORM oraz wszystkich read/write paths.
- Odpowiedzieć, która tabela jest właścicielem finalnego quada source/board i
  jaką odpowiedzialność zachowują rewizje board-level.
- Określić, czy `recognized_boards` i `cell_observations` są właścicielami,
  projekcjami czy historycznymi rezultatami pipeline'u.
- Wskazać duplikaty aktywnych slotów i topologii oraz regułę ich walidacji.
- Ustalić odpowiedzialność `image_geometry_rollout_states` względem
  konfiguracji gry i snapshotu joba.
- Zidentyfikować legacy tabele, które po przyszłym cutoverze przestaną
  otrzymywać nowe rekordy, bez ich usuwania w tym zadaniu.
- Zaprojektować wyłącznie addytywną migrację korygującą oraz dual-read/write,
  jeśli są konieczne.
- Zapisać decyzję architektoniczną, mapę tabel, ryzyka i checkpoint przed
  implementacją schematu.

## Out of scope

- Bez zmian ORM, migracji, API, OpenAPI, workera i UI.
- Bez edycji historycznej migracji 0082/0083.
- Bez połączenia z produkcyjną bazą, backfillu i zmiany danych użytkownika.
- Bez aktywacji `structured_default`, usuwania legacy tabel/cropów albo zmiany
  canonical ownership sekwencji.
- Bez rozszerzania niewystarczającego korpusu TASK-0323 i bez zmiany progów
  geometrii.

## Acceptance criteria

- [x] Każdy trwały nośnik geometrii i proweniencji ma jedną opisaną rolę.
- [x] Wskazano dokładnie jednego właściciela source geometry revision i jedną
  regułę wyboru bieżącej board geometry revision.
- [x] Active slots, topologia i rollout mają jawne źródła prawdy oraz snapshoty.
- [x] Review odpowiada na wszystkie 12 pytań korekty schema ownership.
- [x] Projekt addytywnej korekty zachowuje 0082, legacy replay, verified labels
  i istniejące eventy.
- [x] Nie wykonano migracji, backfillu ani operacji na danych.
- [x] Dokumentacja architektury, modelu danych, Decision Log i CURRENT_STATE są
  spójne.

## Planned commit

`v0.10.17 - document virtual geometry schema ownership`

## Outcome

Przegląd ustalił, że finalne quady geometrii wirtualnej należą wyłącznie do
`image_source_geometry_revisions.board_geometries`, natomiast bieżąca plansza
wybiera source revision i slot przez `recognized_boards`. Pozostałe kopie mają
jawne role projekcji, audytu albo render provenance.

Zapisano D-267, pełną mapę odpowiedzialności, odpowiedzi na 12 pytań oraz
projekt następnej wyłącznie addytywnej korekty. Migracje 0082/0083, ORM, API,
worker, dane i progi geometrii nie zostały zmienione.
