---
title: TASK-0091 Documentation consistency before M2
status: done
last_updated: 2026-07-24
---

# TASK-0091 — Documentation consistency before M2

## Goal

Usunąć nieaktualne odwołania po TASK-0090 i zapewnić, że kolejność zadań M2
odpowiada zaakceptowanemu modelowi danych oraz warunkom wejścia.

## Context

Payout-v2, fixture i snapshot zostały ukończone, ale część aktywnej dokumentacji
nadal opisywała korektę jako przyszłą. Plan M2 przypisywał fundament Next.js
niejednoznacznie i wymagał wymiarów gry przed wdrożeniem `rules_versions`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/tasks/0014-release-apk-device-acceptance.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/project/OPEN_QUESTIONS.md`

## Scope

- aktualizacja statusów M1.2, M1.3 i M1.5 po TASK-0090,
- aktualizacja następnego kroku do nowego APK i odbioru urządzeń,
- aktualizacja aktywnego opisu fixture i przykładów wersji,
- jednoznaczne przypisanie fundamentu Next.js do TASK-0015,
- przeniesienie wymiarów i kosztu spinu do podetapu `rules_versions`,
- zachowanie G6 jako warunku wejścia do M2.

## Out of scope

- kod aplikacji,
- build APK i testy urządzeń,
- rozpoczęcie TASK-0015,
- zmiana zaakceptowanego zakresu produktu albo architektury.

## Acceptance criteria

- [x] Aktywne dokumenty nie kierują do ukończonego TASK-0090.
- [x] Aktualne fixture i algorytm są opisane jako v2.
- [x] Przykład API używa obsługiwanej wersji algorytmu i schematu snapshotu.
- [x] Każdy element zakresu M2.1 ma jednoznacznego właściciela zadania.
- [x] Wymiary i koszt spinu są wdrażane razem z `rules_versions`.
- [x] G6 pozostaje jawną blokadą startu M2.

## Verification

```powershell
rg -n "payout wymaga korekty|muszą zostać zregenerowane|muszą zostać przeliczone" ai_docs
git diff --check
```

## Outcome

- `CURRENT_STATE.md` i plan M1 kierują teraz do nowego APK oraz odbioru
  TASK-0014 zamiast do ukończonej korekty payout-v2.
- Statusy G2, G3 i G5 wskazują ponowną walidację przez TASK-0090.
- `DATA_MODEL.md`, `API_CONTRACT.md` i `TECH_STACK.md` opisują aktualne
  `m1-fixture-v2`, `payout-v2`, snapshot schema 2 i prywatny pipeline release.
- M2.1 przypisuje FastAPI i Next.js do TASK-0015, a PostgreSQL oraz odwracalny
  Alembic baseline bez tabel domenowych do TASK-0016.
- M2.2 obejmuje tożsamość gry i symbole. Wersjonowane wymiary oraz koszt spinu
  są tworzone z `rules_versions` w M2.3, zgodnie z modelem danych.
- Q-019 jest jawnie nieblokujące dla lokalnego panelu jednego właściciela w M2.
- Indeks ukończonych zadań obejmuje cały aktualny katalog `tasks/completed`.
- Metadane wszystkich ukończonych zadań używają zdefiniowanego statusu `done`.
- G6 i aktywne TASK-0014 pozostają warunkiem rozpoczęcia TASK-0015.
- Weryfikacja ograniczyła się do spójności dokumentacji i `git diff --check`;
  kod, snapshot i APK nie zostały zmienione w tym zadaniu.
