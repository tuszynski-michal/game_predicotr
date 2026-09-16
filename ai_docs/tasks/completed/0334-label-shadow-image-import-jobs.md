---
title: TASK-0334 Label structured-shadow image import jobs correctly
status: done
version: 0.10
last_updated: 2026-08-30
---

# TASK-0334 — poprawna etykieta jobów shadow

## Goal

Rozróżniać job `structured_shadow`, który celowo zawiera również stabilny
snapshot v20/v19, od czystego importu `verified_v19`.

## Scope

- rollout `structured_shadow` ma pierwszeństwo przy etykietowaniu joba;
- etykieta jawnie pokazuje nowy pomiar shadow i stabilny wynik primary;
- walidacja zgodności joba z polityką nie może uznać shadow za `verified_v19`;
- test obejmuje rzeczywisty payload z jednoczesnym rolloutem i snapshotem
  `boardCellProcessing`.

## Out of scope

- zmiana lub ponowne uruchomienie istniejących jobów;
- promocja Geometry v2 do primary;
- zmiana pipeline'u workera.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`

## Definition of Done

- istniejący job shadow jest opisany jako `0.10 shadow` z informacją o primary;
- czysty v20/v19 i historyczny v18 zachowują dotychczasowe etykiety;
- shadow pasuje wyłącznie do polityki `structured_shadow`;
- testy Admina, lint, typecheck i build przechodzą.

## Outcome

- Rollout shadow ma pierwszeństwo przed snapshotem stabilnego primary w
  etykiecie i walidacji polityki.
- Etykieta pokazuje jednocześnie nowy pomiar i rzeczywisty primary v20/v19.
- Dodano regresję dla payloadu zawierającego oba snapshoty.
- Testy Admina, lint, typecheck i build przechodzą.
