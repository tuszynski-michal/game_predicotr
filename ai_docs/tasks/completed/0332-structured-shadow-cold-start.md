---
title: TASK-0332 Structured-shadow cold start without reviewed anchors
status: done
version: 0.10
last_updated: 2026-08-30
---

# TASK-0332 — Structured-shadow cold start

## Goal

Usunąć cykliczną zależność pierwszego importu nowej gry od profilu geometrii
z plansz, których nie można jeszcze zaimportować.

## Scope

- browserowy preflight jawnie zwraca, czy historyczny preflight geometrii jest
  wymagany;
- `verified_v19` nadal wymaga checksum-bound manifestu geometrii;
- `structured_shadow` nie uruchamia historycznego preflightu i tworzy job bez
  tego manifestu;
- polityka i rewizja gry nadal chronią start przed zmianą po preflighcie;
- Admin pokazuje jasny stan cold-start i nie wywołuje zbędnego endpointu.

## Out of scope

- promocja structured geometry do default/review;
- osłabienie fail-closed legacy primary;
- automatyczne tworzenie profilu z niezatwierdzonych plansz;
- zmiana plikowego licznika uploadu na licznik bajtowy.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`

## Definition of Done

- pierwsza paczka nowej gry w `structured_shadow` nie zwraca
  `IMAGE_PAGE_GEOMETRY_PROFILE_EMPTY`;
- stabilny tryb nadal nie może wystartować bez manifestu geometrii;
- start shadow nie przyjmuje manifestu z innej/starej ścieżki;
- API, klient i Admin mają zgodne testy.

## Outcome

- Browser preflight zwraca `geometryPreflightRequired` wynikające z przypiętej
  polityki gry.
- `verified_v19` nadal wymaga zakończonego, checksum-bound manifestu geometrii.
- `structured_shadow` tworzy pierwszy import bez historycznego profilu i
  odrzuca próbę dołączenia legacy manifestu.
- Admin nie uruchamia zbędnego preflightu dla cold-startu i pokazuje jego jawny
  stan.
- Testy API, Admina, OpenAPI, lint, typecheck i produkcyjny build przechodzą.
