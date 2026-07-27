---
title: Jobs progress and error UI
status: done
last_updated: 2026-07-27
---

# TASK-0031 — Jobs progress and error UI

## Status

`done`

## Goal

Dodać do lokalnego panelu responsywny ekran obserwacji trwałych jobs, który
pokazuje lifecycle, etap, postęp, liczniki, czasy, lease i błąd oraz pozwala
bezpiecznie anulować albo ponowić zadanie przez generowany klient Admin API.

## Context

TASK-0029 dostarczył lifecycle i API, a TASK-0030 lokalny worker, lease,
checkpoint i retry. TASK-0031 domyka M3.1 warstwą operatorską, bez dodawania
konkretnych workflow payout/snapshot/build.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- sekcja `Jobs` i dostępna nawigacja panelu,
- lista 50 najnowszych jobs z filtrami statusu i typu,
- jawne loading, empty, error i success,
- etap, progress, liczniki success/failure/review i attempt,
- czasy utworzenia, startu, końca, heartbeat i expiry,
- wersja workera i stabilny kod/komunikat błędu,
- ręczne odświeżenie oraz polling aktywnego `created/processing`,
- cancel dla `created/processing/waiting_for_review`,
- retry dla `failed/waiting_for_review`,
- ochrona przed podwójną mutacją i czytelny feedback tekstowy,
- testy czystego stanu, akcji i komponentu.

## Out of scope

- tworzenie jobów z panelu,
- implementacja handlerów payout/import/snapshot/android_build,
- manual review elementów,
- log strumieniowy albo osobna tabela zdarzeń,
- zmiany Admin API lub schematu PostgreSQL,
- WebSocket/SSE i biblioteka query/cache.

## Acceptance criteria

- [x] Panel pokazuje każdy publiczny status i osobny stage.
- [x] Postęp jest czytelny także bez znanego totalu.
- [x] Wynik nie jest przekazywany wyłącznie kolorem.
- [x] Błąd pokazuje stabilny code i bezpieczny message.
- [x] Cancel i retry używają generowanego klienta oraz blokują double submit.
- [x] Żądanie anulowania processing jest widoczne jako oczekujące na safe point.
- [x] Polling działa tylko, gdy lista zawiera aktywny job, i nie nakłada requestów.
- [x] Loading, empty i błąd API mają osobne stany z ręcznym retry.
- [x] Widok pozostaje użyteczny na wąskim ekranie.
- [x] Testy i produkcyjny build panelu przechodzą.

## Assumptions

- Widok pobiera maksymalnie 50 najnowszych rekordów.
- Polling co 2 sekundy jest wystarczający dla lokalnego operatora.
- `created` i `processing` są aktywne; `waiting_for_review` wymaga jawnej akcji,
  więc nie uruchamia ciągłego pollingu.
- Timestampy są prezentowane w lokalnej strefie przeglądarki.

## Expected files

- `apps/admin/src/components/admin-shell.tsx`
- `apps/admin/src/features/catalog/catalog-workspace.tsx`
- `apps/admin/src/features/jobs/job-actions.ts`
- `apps/admin/src/features/jobs/job-state.ts`
- `apps/admin/src/features/jobs/job-monitor.tsx`
- `apps/admin/src/app/globals.css`
- testy panelu i dokumentacja stanu

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run admin:build
npm run quality
```

## Risks / open questions

- Brak pytań blokujących. Strumieniowy log może wymagać przyszłego kontraktu
  zdarzeń, ale obecny `error.code/message` wystarcza dla TASK-0031.

## Outcome

Dodano ekran `Jobs` oparty wyłącznie na generowanym kliencie Admin API. Panel
pokazuje 50 najnowszych zadań, filtry statusu i typu, osobny stage, postęp
określony i nieokreślony, liczniki, attempt, lease, heartbeat, wersję workera,
czasy oraz stabilny kod i bezpieczny komunikat błędu.

Ręczne odświeżenie oraz polling co 2 sekundy nie nakładają requestów; polling
działa tylko dla `created/processing`. Cancel ma dwuetapowe potwierdzenie i
komunikat o oczekiwaniu na safe point, retry aktualizuje ten sam rekord, a obie
mutacje są chronione przed podwójnym submit.

Dodano czyste moduły stanu i akcji oraz 7 testów panelu. Test przeglądarkowy
objął aktywny job, błąd, review, nieznany total, cancel, retry i widok 390 px.
Wykryty poziomy overflow usunięto przez jawne `minmax(0, 1fr)` i `min-width: 0`.
Przy pełnej bramce poprawiono także dwa wcześniejsze fixture testów lease tak,
aby używały spójnego, jawnego czasu zamiast zależeć od pory uruchomienia.

Weryfikacja:

- produkcyjny build Next.js przeszedł,
- 51 testów panelu, 63 mobile, 23 wspólnej domeny i 8 klienta API przeszło,
- 150 testów Python przeszło, 4 fizyczne testy integracyjne pozostały pominięte
  zgodnie z konfiguracją standardowej bramki,
- lint, typecheck, format, OpenAPI i walidatory snapshotów/fixture przeszły,
- konsola przeglądarki pozostała czysta, a widok 390 px nie ma poziomego
  overflow.
