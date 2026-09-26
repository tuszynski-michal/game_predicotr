---
title: TASK-0698 — globalny routing V2 i granica transakcji release
status: blocked
last_updated: 2026-09-26
---

# TASK-0698 — globalny routing V2 i granica transakcji release

## Status

`blocked` — wymaga jawnego rozstrzygnięcia sprzecznych zaakceptowanych zasad.

## Goal

Przywrócić globalne odczyty i atomowe wydania 1–15 gier bez legacy public,
bez utraty fail-closed i bez niejawnego obejścia izolacji V2.

## Context

T08 ujawnił HTTP500 dla dataset layouts i review batches. Release workflow
odczytuje dataset bez bind; job ANDROID_BUILD celowo ma game_id=None.
Audit T03 nie wykrył tych globalnych wejść i nie jest kompletnym dowodem.

## Dependencies / entry conditions

Accepted D-038 nakazuje blokady wszystkich źródeł i zapis rodzica w jednej
transakcji (DECISION_LOG:2372–2380). DATA_MODEL:177–181 zakazuje zmiany gry
w transakcji. Te zasady trzeba jawnie uzgodnić przed implementacją release.
To krytyczna sprzeczność, na której użytkownik zezwolił poczekać na decyzję.

## Recommended execution

`gpt-6-astra`, reasoning `high`; review `gpt-6-sol`, reasoning `high`.
Najpierw zaakceptowana decyzja i szczegółowy plan, potem implementacja.
Poniższy zakres jest propozycją, nie zgodą na zmianę D-038 lub RLS.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/DECISION_LOG.md` (D-038)
- `ai_docs/architecture/DATA_MODEL.md`, `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/delivery/LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md`
- `ai_docs/quality/V2_GAME_OWNED_ACCESS_AUDIT.md`
- `ai_docs/quality/LEGACY_PUBLIC_STORE_RELEASE_READINESS.md`

## Scope / technical notes

- DatasetID: jawne rozwiązanie właściciela bez public fallbacku.
- Globalne review: odczyty per gra, deterministyczne globalne sortowanie i
  limit50; brak location fail-closed, nie ciche pomijanie.
- Rekomendowany kierunek do zatwierdzenia: zachować atomowość D-038,
  zaprojektować osobny, jawny koordynator wielogrowej transakcji z zamkniętą
  listą gier, deterministycznym lock ordering i pełnymi fencing/RLS checks.
  Zwykły router nadal ma jedną grę. Wymaga zmiany architektury i testów izolacji.
- Alternatywa: rozbicie workflow na trwałą koordynację per gra wymaga zmiany
  D-038 oraz określenia recovery/kompensacji; nie jest drobną poprawką.
- Nie ograniczać po cichu release do jednej gry; nie wyłączać RLS ani nie
  tworzyć public kopii. Nie przyjmować globalnego search_path bez scope.

## Out of scope

Apply0125, dane użytkownika, GC, wdrożenie, geometry job schema3 (TASK-0695).

## Acceptance criteria

- [ ] Decyzja i architektura nie zawierają sprzeczności granicy transakcji.
- [ ] Dataset/global review działają bez legacy, z właściwymi limitami/porządkiem.
- [ ] Create/start/restart release co najmniej dwóch gier zachowuje kontrakt.
- [ ] Brak scope, obca gra, zmiana generation/status i błąd drugiej gry nie
      ujawniają danych ani nie pozostawiają częściowego wydania.
- [ ] Testy, niezależny audit i ponowienie T08; poprawiony audyt dostępu T03.

## Expected files

Router/session, dataset/review/mobile_release repositories, worker releases/
snapshot store, adekwatne testy oraz DECISION_LOG/DATA_MODEL/audyt dostępu.
Dokładny podział po zatwierdzeniu decyzji, nie przed nią.

## Verification

Małe izolowane bazy0125, rzeczywiste HTTP i procesy API/worker, timeout120s
na scenariusz. Bez benchmarków i bez modyfikacji bazy użytkownika.

## Outcome

Niezależny read-only audit gpt-6-astra/medium potwierdził dwa P1: globalne
odczyty bez owner routing oraz konflikt wielogrowej transakcji. Nie wdrożono
żadnej zmiany zasad. T08 no-go; T09–T12 oczekują usunięcia blokera i osobnego
approval dokładnego świeżego preflightu dla T09.
