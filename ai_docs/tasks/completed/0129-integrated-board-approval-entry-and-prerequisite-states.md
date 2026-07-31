---
title: TASK-0129 Integrated board approval entry and prerequisite states
status: done
last_updated: 2026-08-01
---

# TASK-0129 — Integrated board approval entry and prerequisite states

## Status

`done`

## Goal

Zapewnić w kontekście aktywnej gry jedno bezpieczne wejście do osobnej
aplikacji Reviewer, dostępne wyłącznie dla gotowego importu zawierającego
plansze do zatwierdzenia.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- używać aktywnej gry bez dodatkowego selecta gry,
- deterministycznie wybierać najnowszy image import w statusie
  `waiting_for_review` albo `completed`,
- pozwolić jawnie wybrać starszy gotowy import tej samej gry,
- sprawdzić bounded stroną Reviewera, czy import zawiera plansze i pokazać
  liczniki decyzji,
- zablokować utworzenie sesji dla importu pustego, niedokończonego lub z innej
  gry,
- przy braku danych udostępnić akcję prowadzącą do sekcji `Import layoutów`,
- zachować istniejący lifecycle lokalnego Reviewera, publicznego ingressu,
  kodu, revoke i audytu.

## Expected files

- `services/api/src/game_predictor_api/storage/reviewer_access_repository.py`
- `apps/admin/src/features/reviewer-access/`
- `apps/admin/src/features/catalog/catalog-workspace.tsx`
- testy API/serwisu i Admina,
- dokumentacja kontraktu i bieżącego stanu.

## Acceptance criteria

- [x] aktywna gra jest jedynym kontekstem sekcji,
- [x] najnowszy gotowy import jest wybierany deterministycznie,
- [x] starszy gotowy import można wybrać jawnie,
- [x] pusty lub niedokończony import nie pozwala utworzyć sesji,
- [x] UI rozróżnia loading, error, brak importu, import w toku i gotowość,
- [x] brak plansz prowadzi do `Import layoutów`,
- [x] sesja nadal otwiera osobną aplikację Reviewer i zachowuje zabezpieczenia,
- [x] testy backendu i Admina przechodzą.

## Outcome

Sekcja `Zatwierdzanie plansz` korzysta bezpośrednio z aktywnej gry. Z image
importów tej gry wybiera najnowszy status `waiting_for_review` albo `completed`,
zachowuje jawny wybór starszego gotowego importu i bounded requestem pobiera
liczniki plansz. UI pokazuje osobno brak importu, import jeszcze trwający, pusty
import, loading, błąd oraz gotowość. Brak danych udostępnia akcję przenoszącą do
accordionu `Import layoutów` bez utraty kontekstu gry.

Tworzenie sesji jest zablokowane do czasu potwierdzenia co najmniej jednej
planszy. Repozytorium backendowe ponownie wymaga właściwej gry, typu image
import, statusu review/completed i istnienia `image_review_items`, więc warunku
nie można ominąć przez ręczny request. Istniejący tunel, kod, TTL, revoke,
scope tokenu i audyt pozostają bez zmian.

Weryfikacja: 28 testów API/Reviewera oraz 110 testów Admina przeszło; Ruff,
ESLint, typecheck i produkcyjny build Admina również przeszły.
