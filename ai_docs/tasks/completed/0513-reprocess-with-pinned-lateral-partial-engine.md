---
title: Reprocess with pinned lateral partial engine
status: in_progress
last_updated: 2026-09-07
---

# TASK-0513 — Nowy run na istniejącym stagingu

## Status

`done`

## Goal

Włączyć wewnętrzny, trwały pion v0.10.4 w istniejącym preflighcie i imporcie,
z osobną idempotentną tożsamością i ochroną decyzji użytkownika.

## Context

TASK-0510–0512 dostarczyły snapshot, boczną kandydaturę rejestracji i lokalny
estimator. Nie są jeszcze połączone z manifestem i wykonaniem importu.

## Dependencies / entry conditions

- TASK-0512: commit c6a13a65, niezależny audyt bez P0–P3.
- Istniejące artefakty muszą być zgodne z grą, źródłem i topologią.
- Automatyczna propozycja partial nie ma prawa renderowania przed potwierdzeniem.
- Publiczna dostępność pozostaje pod końcową bramką jakości TASK-0515.

## Recommended execution

`gpt-6-astra high`, zgodnie z końcową tabelą zaakceptowanego planu.
Niezależny review `gpt-6-astra high` wymagany dla idempotencji i ochrony decyzji.
Konflikt z istniejącymi zasadami własności wymaga jawnego rozstrzygnięcia.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Wersjonowany manifest wiążący kandydatury ze źródłem i polityką.
- Jawne przygotowanie kompatybilnego preflightu bez nowego uploadu.
- Dispatch pełnej geometrii przez niezmienione v3, partial jako propozycja review.
- Osobny idempotentny run; ochrona ręcznych rewizji, masek i decyzji symboli.
- Poprawne sloty kontynuują pracę; nierozwiązane pozostają waiting_for_review.

## Out of scope

- UI TASK-0514, aktywacja jakościowa TASK-0515.
- Nowe job types, migracje, restart usług i reimport danych operatora.
- Dirty cleanup, 0102, next-env i istniejące zmiany virtual repository.

## Acceptance criteria

- [x] Snapshot i artefakty są przypięte i sprawdzane po restarcie.
- [x] Retry i podwójne żądanie nie tworzą duplikatów.
- [x] Niezgodny/stary artefakt wymaga jawnego preflightu, nie uploadu.
- [x] Ręczne decyzje i geometrie nie są nadpisywane automatycznie.
- [x] Kandydat partial trafia do review bez renderu brakujących pikseli.
- [x] Testy i niezależny audyt przechodzą.

## Technical notes

Nie zmieniamy starych manifestów. Geometria propozycji jest oddzielona od
ręcznej rewizji. Brak kandydata zachowuje pełny zestaw slotów z nazwy.
Nowy run wykorzystuje istniejący start browser import i mechanizm snapshotu;
integracja nie może robić nowego joba przy odczycie raportu.

## Expected files

- Istniejące: `application/jobs.py`, `api/image_imports.py`, schemas i klient.
- Istniejące: `page_geometry_preflight.py`, `production_workflow.py`.
- Nowe: ograniczony moduł walidacji artefaktu v4 i testy integracyjne.

## Test cases

- Restart i replay identycznego snapshotu.
- Brak artefaktu, drift checksumy, nieznana wersja i topologia.
- Retry, utrata odpowiedzi, podwójne kliknięcie.
- Chroniona ręczna korekta i decyzja symbolu, obok slotu automatycznego.
- Full/partial/manual na jednym źródle bez utraty slotu.

## Verification

Skupione testy pytest API/workera z limitem 120 s dla każdej grupy,
następnie Ruff i mypy zmienionych źródeł. Zmiana HTTP wymaga OpenAPI,
wygenerowanego klienta, wrappera i testu żądania. Audyt przed commitem.

## Risks / open questions

- Dotychczasowy writer może nie obsługiwać automatycznej propozycji jako
  odroczonego, lecz edytowalnego slotu; nie wolno nadawać jej ręcznej proweniencji.
- Odbiór na danych rzeczywistych i końcowa dostępność pozostają TASK-0515.

## Outcome

### Changed

- Połączono przypięty manifest v4 z istniejącym preflightem i importem.
- Dodano checksum-bound przygotowanie preflightu z managed originals po
  zwolnieniu browser stagingu oraz idempotentny managed/browser reprocess.
- Automatyczny partial pozostaje propozycją bez prawa renderu do ręcznego
  potwierdzenia; pełne sloty nadal przechodzą niezmienioną ścieżką v3.
- Ochrona ręcznych geometrii, symboli i odrzuceń działa pod blokadą sekwencji.
  Ujednolicono kolejność sequence → source/rows → state i ograniczono blokadę
  wyboru incumbent ownera do mutowanych review/board, bez blokowania JobModel.

### Verification results

- 82 skupione testy API/workera passed; dodatkowa regresja lock scope wraz z
  powiązanymi testami: 27 passed.
- 57 testów klienta oraz jego build i typecheck passed.
- `npm run openapi:check`, Ruff i scoped mypy 13 źródeł passed.
- Niezależny review `gpt-6-astra high` zaakceptował bramkę po usunięciu trzech
  cykli blokad, dodaniu managed preflightu i ochronie guard lineage. Końcowy
  re-review regresji PostgreSQL SQL: 13 passed, brak findings P0–P2.

### Not completed

- Nie wykonano realnego testu współbieżności PostgreSQL; testy potwierdzają
  kolejność i zakres generowanych blokad na poziomie wejść transakcyjnych.
- Publiczny wybór oraz odbiór jakości pozostają TASK-0514 i TASK-0515.
- Guard związany ze starszym preflightem wymaga jawnego przepięcia; v4 kończy
  się fail-closed zamiast utracić jego decyzje.

### Documentation updates

- Uzupełniono wymagania ingestion, własność geometrii, kontrakt API,
  Decision Log i CURRENT_STATE.

### Recommended next task

- TASK-0514 — wybór v0.10.4 i trwałe odtwarzanie raportu w Adminie.
