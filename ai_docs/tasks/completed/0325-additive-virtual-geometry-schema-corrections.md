---
title: TASK-0325 additive virtual geometry schema corrections
status: done
last_updated: 2026-08-30
---

# TASK-0325 — Addytywne korekty schematu geometrii wirtualnej

## Status

`done`

## Goal

Utrwalić kontrakty zaakceptowane w TASK-0321, TASK-0322 i TASK-0324 obok pól
historycznych v1, bez przełączania odczytów, przepisywania istniejących etykiet
ani modyfikowania zastosowanych migracji 0082/0083.

## Relevant docs

- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/tasks/completed/0321-logical-cell-identity-v2.md`
- `ai_docs/tasks/completed/0322-symbol-verification-outcome-v2.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Dodać nową migrację 0084 po faktycznym headzie 0083, bez edycji historii.
- Utrwalić fingerprint topologii i wersjonowaną checksumę attestation na
  `image_source_geometry_revisions`.
- Utrwalić `logical-cell-v2` oraz `render-identity-v2` obok v1 w bieżących
  observation, review, eventach i zweryfikowanych komórkach kohort.
- Utrwalić jawny `symbol-verification-outcome-v2` w bieżącej projekcji i
  append-only eventach, pozostawiając legacy pola jako aktywny kontrakt HTTP.
- Związać gotowość rolloutu z dokładną rewizją polityki, checksumą wejścia i
  jobem walidującym.
- Dodać dual-write dla nowych rekordów virtual geometry i fail-closed
  walidację niespójnych kombinacji.
- Dodać bounded, read-only diagnostykę rekordów historycznych wymagających
  późniejszego backfillu; nie mapować automatycznie przypadków niejednoznacznych.
- Zachować istniejącą niezatwierdzoną migrację 0083 jako niezmienny warunek
  łańcucha, jeżeli kontrola diffu i testy potwierdzą jej deklarowany zakres.

## Out of scope

- Bez cutoveru odczytów lub indeksów na v2.
- Bez wykonania migracji na bazie użytkownika i bez mutującego backfillu.
- Bez zmiany verified labels, eventów historycznych i canonical ownership.
- Bez zmiany algorytmu geometrii, progów, renderera, API publicznego i UI.
- Bez usuwania pól v1, projekcji kompatybilnościowych i legacy assetów.
- Bez dołączania niezwiązanych zmian importu v20, stagingu i skryptów
  operatorskich znajdujących się w worktree.

## Acceptance criteria

- [x] Migracja jest addytywna, ma jeden head i nie skanuje dużych tabel.
- [x] ORM jest zgodny z migracją i wymusza checksumy/enum dla nowych zapisów.
- [x] Automatic i manual virtual write paths utrwalają tę samą tożsamość v2.
- [x] Review cells/events zapisują jawny outcome v2 bez symbolu `?`.
- [x] Existing legacy rows pozostają czytelne z nullable v2 i nie są
  heurystycznie przepisywane.
- [x] Rollout `ready` jest związany z dokładnym snapshotem walidacji.
- [x] Diagnostyka rozróżnia rekordy gotowe do backfillu i niejednoznaczne.
- [x] Testy migracji, storage, domeny, Ruff i scoped mypy przechodzą.
- [x] Nie wykonano migracji ani operacji na danych użytkownika.

## Planned commit

`v0.10.18 - persist additive virtual geometry contracts`

## Outcome

- Dodano migrację 0084 po niezmienionym prerequisite 0083. Wszystkie nowe
  kolumny są nullable, constraints są `NOT VALID`, a upgrade nie wykonuje
  skanu ani backfillu dużych tabel.
- Source geometry zapisuje fingerprint topologii i checksumę attestation.
  Automatic render i manual recrop zapisują logical/render identity v2 obok
  historycznego v1; zamrożone kohorty zachowują tę proweniencję, gdy manifest
  ją dostarcza.
- Current review i append-only eventy zapisują outcome v2 oraz osobny
  `verified_symbol_id_v2`. Legacy modelowa sugestia w `assigned_symbol_id` nie
  jest reinterpretowana jako zatwierdzony symbol.
- Rollout validation wiąże `ready` z bieżącą rewizją, SHA-256 pełnego inputu i
  dokładnym jobem. Historyczny niezwiązany `ready` wymaga nowej walidacji.
- Dodano limitowaną do 500 rekordów, read-only diagnostykę. Stany
  niejednoznaczne pozostają nullable i nie są mutowane.
- Weryfikacja: 168 testów domeny/storage/API/workera, dodatkowo 67 testów
  migracji i bindingu; Ruff przechodzi. Scoped mypy API (9 plików) oraz worker
  bez historycznie błędnego `pipeline_store.py` przechodzą. Pełny scoped mypy
  nadal raportuje dwa wcześniejsze błędy `pipeline_store.py:1209,1452`, poza
  zmienionymi liniami.
- Nie uruchomiono migracji 0084, backfillu, cutoveru ani operacji na danych
  użytkownika.
