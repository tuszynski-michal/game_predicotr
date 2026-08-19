---
title: TASK-0149 pending-only re-inference and import pinning
status: in_progress
last_updated: 2026-08-19
---

# TASK-0149 — Pending-only re-inference and import pinning

## Status

`in_progress`

## Goal

Dodać jawną operację `Przelicz oczekujące`, która zapisuje nowe rewizje
predykcji tylko dla nadal nierozwiązanych elementów i nigdy nie zmienia decyzji
użytkownika.

## Context

Po aktywacji lepszego modelu właściciel chce poprawić sugestie dla pozostałej
pracy oraz używać go w nowych importach. Element może jednak zostać
zatwierdzony podczas trwającego joba, dlatego kwalifikacja przy starcie nie
wystarcza.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_06_6_EXECUTION_PLAN.md`
- `ai_docs/tasks/0148-model-registry-and-controlled-activation.md`

## Scope

- dodać preview liczby `pending`, chronionych i niekwalifikujących elementów,
- utworzyć wznawialny job inferencji przypięty do wskazanej aktywnej wersji,
- zapisywać append-only rewizje predykcji z rankingiem i confidence,
- przed każdym zapisem warunkowo sprawdzać status, rewizję review, crop checksum
  i geometrię,
- pomijać element rozwiązany albo zmieniony w czasie joba,
- raportować przeliczone, pominięte przez decyzję człowieka, zmienione cropy i
  błędy,
- pokazać postęp, możliwość retry i podsumowanie w Adminie,
- potwierdzić, że nowe importy automatycznie przypinają bieżący model.

## Out of scope

- ponowne otwieranie rozstrzygniętych elementów bez decyzji użytkownika,
- nadpisywanie starszych rewizji predykcji,
- recrop, korekta geometrii i OCR,
- automatyczne zatwierdzanie na podstawie confidence.

## Acceptance criteria

- [ ] Preview i job obejmują wyłącznie `pending` z pasującym cropem oraz grą.
- [ ] `accepted`, `corrected` i `rejected` są zawsze pomijane, również gdy
      znalazły się w początkowej partii przed zmianą statusu.
- [ ] Nowy wynik jest osobną rewizją i zachowuje wersję modelu oraz checksumę.
- [ ] Warunkowy zapis przegrywa bezpiecznie z równoległą decyzją użytkownika.
- [ ] Retry jest idempotentny i nie tworzy podwójnej identycznej rewizji.
- [ ] Po operacji checksumy zdarzeń review, ręcznych etykiet, geometrii i
      stagingu są identyczne jak przed operacją.
- [ ] Reviewer pokazuje najnowszą zgodną sugestię, ale zachowuje historię.
- [ ] Trwający oraz nowy import przechodzą test przypięcia wersji modelu.

## Technical notes

Ochrona ma działać w warstwie repozytorium/SQL, a nie tylko przez filtr w UI lub
wcześniejsze pobranie listy. To zabezpiecza równoległe zatwierdzanie w Reviewerze.

## Expected files

- `services/api/src/game_predictor_api/`
- `services/api/tests/`
- `services/worker/src/game_predictor_worker/`
- `services/worker/tests/`
- `apps/admin/src/features/model-quality/`
- `apps/reviewer/src/features/`
- `packages/admin-api-client/`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
python -m pytest services/api/tests -q
python -m pytest services/worker/tests -q
npm.cmd test --workspace @game-predictor/admin
npm.cmd test --workspace @game-predictor/reviewer
npm.cmd run openapi:check
```

## Risks / open questions

- Duża liczba `pending` wymaga keyset pagination i małych checkpointów, ale bez
  dodawania zewnętrznej kolejki przed pomiarem.

## Outcome

Zaimplementowano migrację append-only rewizji predykcji, jawny typ joba
`image_symbol_reinference`, snapshot aktywnego modelu oraz warunkowy zapis
pending-only w workerze. Reviewer nakłada najnowszą rewizję na sugestię bez
zmiany bazowych obserwacji. Dodano także `image_grid_reinference`, diagnostykę
kohorty, podgląd i przyciski `Przelicz oczekujące` w Adminie. Pozostaje pełny
odbiór E2E na rzeczywistych danych.
W v0.6.41 dodano wspólną diagnostykę kwalifikacji geometrii, a import v0.6.42
przypina aktywne snapshoty siatki i symboli podczas rerunu browserowego stagingu.
W v0.6.48 preflight zwraca fingerprinty obu snapshotów, a Admin przekazuje je
przy starcie; zmiana aktywnego modelu pomiędzy preflightem i startem jest
odrzucana. Naprawiono również wstrzykiwanie JobService do endpointu preflight.
