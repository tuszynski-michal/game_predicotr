---
title: TASK-0331 Per-game image import engine policy
status: done
version: 0.10
last_updated: 2026-08-30
---

# TASK-0331 — Per-game image import engine policy

## Goal

Pozwolić bezpiecznie przypiąć silnik nowych importów plansz osobno dla każdej
gry, bez zmiany istniejących jobów i bez udostępniania niezatwierdzonych trybów
produkcyjnych.

## Scope

- dwa jawne presety: stabilny `verified_v19` oraz pomiarowy
  `structured_shadow`;
- trwałość ustawienia w istniejącym `image_geometry_rollout_states`;
- inicjalizacja brakujących stanów dla istniejących i nowych gier;
- revision-bound preview i zapis ustawienia;
- przypięcie polityki do checksumy preflightu i startu browserowego importu;
- ustawienia w Adminie oraz widoczna informacja o wpływie trybu;
- OpenAPI, generowany klient, testy i dokumentacja.

## Out of scope

- aktywacja `structured_default`, `virtual_default` lub Geometry v2 jako
  właściciela geometrii;
- zmiana istniejących jobów albo ponowne przetwarzanie danych;
- zmiana progów 95/98 i decyzji D-271/D-272;
- uruchomienie importu lub migracji na danych użytkownika.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DECISION_LOG.md`

## Definition of Done

- każda gra ma jedno trwałe ustawienie nowych importów;
- klient nie może nadpisać polityki gry w payloadzie startu;
- zmiana po preflighcie wymusza ponowny raport;
- `structured_shadow` pozostawia dotychczasowy wynik primary i nie aktywuje v2;
- istniejące joby zachowują niezmienne snapshoty;
- API, klient i UI są zgodne oraz mają testy;
- pełny typecheck i właściwe testy przechodzą.

## Outcome

Dodano bezpieczne presety per gra, inicjalizację istniejących i nowych gier,
revision-bound API, przypięcie do browserowego preflightu/startu oraz kontrolkę
w Adminie. `structured_shadow` nie zmienia primary, a istniejące joby zachowują
snapshot. Testy domenowe/API/importów/katalogu/jobów i typecheck Admina przeszły.
