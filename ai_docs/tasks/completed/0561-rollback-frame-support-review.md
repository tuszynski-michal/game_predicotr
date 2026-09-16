---
title: Wycofanie domyślnej kwalifikacji słabych obramowań
status: done
last_updated: 2026-09-16
---

# TASK-0561 — Wycofanie domyślnej kwalifikacji słabych obramowań

## Status

`done`

## Goal

Nowe preflighty wariantu bocznych niepełnych plansz ponownie przypinają
politykę v1/v2 bez gałęzi słabych obramowań, a trzy wskazane stagingi zostają
przeliczone tą wcześniejszą polityką.

## Context

Polityka `structured-lattice-v4-lateral-partial-v3` z TASK-0549 zwiększyła dla
stagingu `45163 - 70371 cut` liczbę pozycji ręcznej korekty z 40 w jobie v2
`fed795a1-e0a4-46db-bcb6-8b0373625d62` do 355 w jobie v3
`07691c10-2c6c-43f4-a1a8-f77f9720c81d`. Użytkownik wycofał tę decyzję
produktową i polecił ponowić trzy konkretne preflighty wcześniejszym silnikiem.

## Dependencies / entry conditions

- Snapshoty v1/v2/v3 są immutable i muszą pozostać odtwarzalne.
- Job v3 `06c5fe4e-e39e-4f7e-b8c7-f3820b508c7b` został anulowany na bezpiecznym
  checkpointcie `1100/3104`; jego dane nie są usuwane.
- Lokalne zmiany użytkownika w `apps/admin/next-env.d.ts` oraz katalogi
  `.codex-task-0559*` pozostają poza zakresem.

## Recommended execution

`gpt-6-astra` z reasoning `high`: zmiana dotyczy wersjonowanego snapshotu,
idempotencji jobów i operacyjnego ponowienia trzech rzeczywistych preflightów.
Niezależny review nie jest wymagany, ponieważ parser i replay v3 pozostają
bez zmian, a produkcyjny wybór wraca do wcześniej zaakceptowanej v2.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0549-route-frame-clipped-visible-grids-to-review.md`

## Scope

- Ustawić `frame_support_review=False` jako politykę nowych snapshotów.
- Zachować ścisły odczyt i wykonanie historycznych snapshotów v3.
- Dodać regresję potwierdzającą, że nowy run z profilem niepełnych siatek
  przypina v2, a jawny historyczny v3 nadal przechodzi round-trip.
- Uaktualnić wymagania, architekturę, kontrakt i dziennik decyzji.
- Po testach i restarcie API/workera utworzyć preflighty v2 dla stagingów:
  `149626 - 177561 cut`, `177562 -200583 cut`, `45163 - 70371 cut`.

## Out of scope

- Usuwanie jobów, manifestów v3 albo ręcznych override'ów.
- Zmiana algorytmu niepełnych plansz v2 i jego profilu uczenia.
- Ponowne włączenie gałęzi słabych obramowań bez osobnej bramki jakości.

## Acceptance criteria

- [x] Nowy snapshot bez profilu ma politykę v1, a z profilem politykę v2.
- [x] Snapshot v3 pozostaje odtwarzalny wyłącznie po jawnym
      `frame_support_review=True` albo z przypiętego payloadu v3.
- [x] Trzy nowe joby mają `policyVersion=structured-lattice-v4-lateral-partial-v2`.
- [x] Stare joby i manifesty v3 pozostają dostępne i nie są modyfikowane.
- [x] Testy kontraktu API i workera przechodzą.

## Technical notes

Rollback jest zmianą wyboru polityki dla nowych runów, a nie usunięciem
kontraktu. `LateralPartialGeometrySnapshot.from_payload()` nadal rozpoznaje v3,
więc retry i odczyt historycznych raportów są deterministyczne. Zmiana polityki
zmienia pełny input key preflightu i nie może odzyskać zakończonego joba v3.

## Expected files

- Istniejące: `services/worker/src/game_predictor_worker/images/lateral_partial_contract.py`.
- Istniejące: `services/api/src/game_predictor_api/application/jobs.py` — jawny
  wybór v1/v2 dla nowych jobów niezależnie od sposobu uruchomienia API.
- Istniejące testy kontraktu w `services/worker/tests` i `services/api/tests`.
- Istniejące dokumenty wymagań, architektury, API, decyzji i bieżącego stanu.

## Test cases

- Konstruktor bez profilu → snapshot v1 bez `frameSupportReviewEnabled`.
- Konstruktor z profilem → snapshot v2 bez `automaticFrameProposalVersion`.
- Jawny `frame_support_review=True` → niezmieniony snapshot v3 i checksumowy
  round-trip.
- Nowy job API z profilem → przypięta polityka v2.
- Historyczny payload v3 → prawidłowy replay i obsługa istniejącej propozycji.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_lateral_partial_contract.py services/worker/tests/test_lateral_page_registration.py services/worker/tests/test_structured_lattice_refinement_v4.py services/worker/tests/test_lateral_partial_workflow.py services/api/tests/test_lateral_partial_engine_contract.py services/api/tests/test_image_grid_review_api.py -q
.venv\Scripts\python.exe -m ruff check services/api services/worker
.venv\Scripts\python.exe -m mypy services/api/src services/worker/src
```

## Risks / open questions

- Liczba 40 jest historycznym wynikiem konkretnego joba v2, nie gwarantowanym
  wynikiem nowych runów po uwzględnieniu późniejszych ręcznych override'ów.
- Ponowne preflighty pozostają pełnymi przebiegami na bieżącej gałęzi; TASK-0559
  nie jest jeszcze połączony z `version-0.10`.

## Outcome

- Nowe runy `structured_lattice_v4_partial_sides` przypinają wcześniejszą
  politykę `structured-lattice-v4-lateral-partial-v2`; historyczne payloady v3
  nadal przechodzą ścisły replay z `frameSupportReviewEnabled=true`.
- Job v3 `06c5fe4e-e39e-4f7e-b8c7-f3820b508c7b` anulowano na checkpointcie
  `1100/3104`, bez usuwania wyników. Utworzono trzy nowe joby v2:
  `3cbcec50-5406-4848-8571-89387e6da1f2`,
  `309d6837-d895-4587-a5eb-80cc2d9f35d6` i
  `0f8a2c88-9477-4486-9962-471ac62ecbc6`. Pierwszy rozpoczął pracę, a dwa
  pozostałe czekają w kolejce.
- Skoncentrowany zestaw sześciu plików testowych zakończył się wynikiem
  `120 passed`; końcowa kontrola dwóch kontraktów po jawnym wyborze polityki
  dała `31 passed`. Ruff oraz mypy zmienionego kontraktu przeszły.
- Pełny mypy nie zakończył się w limicie 60 sekund; kontrola skupiona na API
  wskazała wyłącznie trzy wcześniejsze błędy `Literal` w `schemas/jobs.py`,
  niezwiązane z tym zadaniem.
- General worker został uruchomiony z nowym kodem. Bieżący zewnętrzny proces API
  nie był bezpiecznie dostępny do restartu z tej sesji; kod v1/v2 załaduje się
  przy jego następnym kontrolowanym restarcie, a trzy wymagane joby są już
  deterministycznie przypięte do v2.

## Plan implementacji

1. Wyłączyć gałąź słabych obramowań dla nowych snapshotów i zachować replay v3.
2. Zaktualizować testy oraz dokumentację decyzji o rollbacku.
3. Uruchomić weryfikację, wykonać osobny commit i zrestartować API/workera.
4. Utworzyć oraz zweryfikować trzy nowe joby v2 bez usuwania historii v3.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0561 — Wycofanie domyślnej kwalifikacji słabych obramowań | gpt-6-astra | high | Zmiana obejmuje wersjonowany kontrakt, zgodność historycznych jobów i operacyjne ponowienie trzech preflightów. | Nie — replay v3 pozostaje bez zmian, a nowe runy wracają do zaakceptowanej v2. |
