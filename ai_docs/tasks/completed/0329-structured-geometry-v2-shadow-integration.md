---
title: TASK-0329 Structured Geometry v2 shadow integration
status: done
version: 0.10
last_updated: 2026-08-30
---

# TASK-0329 — Structured Geometry v2 shadow integration

## Goal

Podłączyć eksperymentalny, wieloźródłowy config geometrii v2 do istniejącego
trybu `structured_shadow` jako odtwarzalny i wyłącznie diagnostyczny sidecar.
Legacy oraz Structured OpenCV v1 pozostają wynikami wykonawczymi pipeline'u.

## Scope

- przypięcie pełnego payloadu i checksummy configu v2 w niezmiennym snapshocie
  nowego joba `structured_shadow`;
- zachowanie odczytu historycznych snapshotów v1 i ich checksum;
- zebranie rzeczywistych sygnałów Hough, gradientów, regularności i centrów
  symboli na finalnym quadzie kandydata v1;
- przeliczenie znormalizowanego błędu reprojekcji względem przekątnej komórki;
- zapis checksummowanego `structuredGeometryCandidateV2` obok wyniku v1 w
  checkpointach `board_detection` oraz `board_cell_geometry`;
- jawne oznaczenie, że geometria pochodzi z engine'u v1, a config v2 służy
  tylko do pomiaru decyzji;
- testy deterministyczności, replayu snapshotu, braku wpływu na primary output
  oraz fail-closed przy drift configu.

## Out of scope

- aktywacja `structured_default` lub zmiana bieżącego trybu dowolnej gry;
- zmiana progów, engine'u lub fingerprintów v1;
- wykorzystanie decyzji v2 do cropów, inferencji, review, canonical ownership
  albo training provenance;
- rozszerzanie korpusu D-266, strojenie progów i decyzja rolloutowa;
- migracja, API publiczne, UI, backfill i operacje na danych użytkownika.

## Invariants

- `activationAllowed=false` oraz maturity `experimental_measurement_only` są
  weryfikowane przy tworzeniu i odtwarzaniu joba;
- candidate v2 może wystąpić wyłącznie w `structured_shadow`;
- legacy fingerprint pozostaje bitowo identyczny;
- `structuredGeometry` v1 pozostaje jedynym źródłem virtual shadow geometry;
- brak finalnego quada albo sygnału nie może tworzyć sztucznego automatic;
- wynik v2 jest deterministycznie związany ze źródłem, wynikiem v1 i configiem.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/DECISION_LOG.md` — D-266, D-271
- `ai_docs/tasks/completed/0328-structured-geometry-config-v2.md`

## Expected files

- `services/worker/src/game_predictor_worker/images/pipeline_contract.py`
- `services/worker/src/game_predictor_worker/images/production_workflow.py`
- `services/worker/src/game_predictor_worker/images/structured_geometry/configuration_v2.py`
- `services/worker/src/game_predictor_worker/images/structured_geometry/signal_probe.py`
- `services/worker/src/game_predictor_worker/images/structured_geometry/shadow_v2.py`
- `services/api/src/game_predictor_api/application/jobs.py`
- odpowiednie testy worker/API i dokumentacja źródeł prawdy.

## Verification

- focused pytest dla configu, snapshotu, shadow evaluatora, workflow i jobów;
- Ruff i mypy dla zmienionych modułów;
- przegląd diffu z wykluczeniem istniejących, niezwiązanych zmian użytkownika.

## Definition of Done

- nowy job `structured_shadow` przypina dokładny config v2 i zmienia swój
  effective fingerprint przy zmianie configu;
- retry odtwarza dokładny config lub kończy się fail-closed przy drift;
- checkpoint zawiera osobny checksummowany candidate v2;
- legacy, review i default nie emitują candidate v2 i nie zmieniają swoich
  dotychczasowych snapshotów;
- żadna decyzja v2 nie steruje pipeline'em ani nie modyfikuje danych domenowych;
- testy i kontrole jakości przechodzą, dokumentacja opisuje ograniczenie.

## Outcome

Zaimplementowano addytywny snapshot rolloutu v2, który wyłącznie dla
`structured_shadow` przypina pełny config Geometry v2 i jego checksumę.
Historyczny snapshot v1 zachowuje identyczny payload i fingerprint. Worker
zbiera rzeczywiste sygnały Hough/LSD, gradientów, regularności i centrów
symboli na finalnym quadzie v1, normalizuje reprojekcję względem komórki i
zapisuje osobny checksummowany sidecar związany ze źródłem, pikselami, configiem
oraz upstreamowym wynikiem.

Sidecar jest walidowany jako `measurement_only`, nie ma autorytetu geometrii i
nie jest konsumowany przez cropper, inferencję, review, canonical ani trening.
Brak mierzalnej geometrii daje jawne `not_evaluated`. Rozszerzono typowany
payload odpowiedzi joba oraz wygenerowany klient Admina bez dodawania nowego
endpointu. Nie wykonano migracji, zmiany trybu gry ani operacji na danych.
