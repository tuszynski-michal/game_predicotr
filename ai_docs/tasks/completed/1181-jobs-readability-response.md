---
title: Odczyt zadań jakości symboli w Jobs
status: done
last_updated: 2026-11-10
---

# TASK-1181 — Odczyt zadań jakości symboli w Jobs

## Status

`done`

## Goal

Lista i szczegóły Jobs odczytują istniejące symbol_readability bez HTTP500,
z prawdziwym postępem i błędami, także w mieszanej historii innych zadań.

## Context

Main a9af0032: _payload_from_domain nie rozpoznaje SYMBOL_READABILITY i wpada
w AndroidBuildJobPayload. GET /api/v1/admin/jobs?limit=10 daje500.
Producer storage/symbol_readability.py zapisuje schema_version1,
workflow=symbol_readability, action=prepare|fit|scan, identifier UUID.
Równoległy TASK-1180 zmienia wydajność tego producenta, nie jego kontrakt.

## Recommended execution

gpt-6.1-sol/high. Mała naprawa odczytu istniejącego kontraktu, bez delegowania.
Niezależny audyt Claude Code claude-opus-5-5/high przez terminal przed commitem.

## Relevant docs

- AGENTS.md; ai_docs/process/DEFINITION_OF_DONE.md; PLAN_STANDARD.md; TASK_TEMPLATE.md.
- ai_docs/requirements/ADMIN_APP.md, sekcja Jobs.
- ai_docs/architecture/API_CONTRACT.md, Job status.
- ai_docs/process/CROSS_AUDIT.md; ai_docs/architecture/CODE_MAP.md.

## Scope / plan

1. Dodać ścisły SymbolReadabilityJobPayload i odpowiednią gałąź odczytu.
   Zachować AndroidBuild, brak ogólnego tworzenia readability przez POST /jobs.
2. Test listy mieszanej, szczegółów, trzech akcji, postępu, błędu i odrzucenia
   wadliwego payloadu. Bez pomijania niewygodnych rekordów.
3. Backend→OpenAPI→generowany klient→wrapper/request test. Wrapper zachowuje
   listJobs i getJob; nie tworzymy równoległego endpointu ani ręcznych typów.
4. Sprawdzić odczyt rzeczywistych rekordów wyłącznie w nowym procesie READ ONLY.
   Testy, lint, typy, generacja i mapa, docs, audit, Outcome i task-close.

## Out of scope

Nowy trening, zmiany jobów operatora, migracje, naprawa pilota TASK-1180,
restarty usług, merge/push. Wdrożenie wymaga osobnej zgody; bez ukrytych usług.

## Acceptance criteria

- [x] prepare/fit/scan i AndroidBuild mają właściwe odpowiedzi; błąd historyczny
  oraz liczniki nie znikają z Jobs, lista mieszana zwraca200.
- [x] Wadliwe akcje/identyfikatory/pola pozostają odrzucane, API tworzenia bez zmian.
- [x] Kontrakt klienta i request test zgodne; rzeczywisty odczyt bez zapisów.
- [x] Kontrole, audyt i zamknięcie rozliczone; wynik gotowy do decyzji o wdrożeniu.

## Expected files

schemas/jobs.py, tests/test_jobs_api.py, OpenAPI i generowane pliki klienta,
packages/admin-api-client/test/jobs-readability-request.test.mjs (nowy),
API_CONTRACT.md, ADMIN_APP.md, CURRENT_STATE.md, mapy i raport weryfikacji.

## Risks / open questions

Nie ukrywać niepoprawnych jobów przez catch-all. Sprawdzić fallback Androida
i istniejące etykiety UI. Nie zmieniać plików równoległego taska1180.

## Outcome

Commit: v1.7.599 / `4e5585905caf6e369bc12c656c24a88fa03575d7`.

### Changed

- Ścisły odczyt readability i pełny kontrakt klienta. Nowy test
  tests/test_jobs_readability_response.py; stary test tworzenia sprawdza
  jawne pięć typów zamiast przestarzałej listy wyłączeń (baseline FAIL potwierdzony).

### Verification results

- 9 nowych Python PASS,36 istniejących PASS i poprawiona asercja1 PASS;
  165 SDK PASS, scoped mypy/ruff/Admin typecheck/build/docs/map/drift PASS.50 rzeczywistych jobów
  odczytanych bez błędu w nowym interpreterze READ ONLY.
- Szczegóły i granice: ai_docs/quality/TASK-1181_VERIFICATION.md.
- Terminal Opus5.5 R1 PASS,0 P0/0 P1, High requested. P2-1: uzupełniono
  testy niezerowych succeeded/failed/review bez zmiany kodu produkcyjnego.
  P2-2/P2-3 przyjęte: fixture SDK bada transport, a dane operatora pozostają
  w lokalnych dowodach. Raport i receipt w ai_docs/quality/.

### Not completed

- Scalenie, push i wdrożenie. Działające API nie zostało zrestartowane;
  nadal wymaga zastosowania poprawki. Brak nowych usług i zapisów operatora.

### Documentation updates

- API_CONTRACT, wymagania Jobs, mapa i wskaźnik taska. Usunięto nieaktualny
  wiersz już wdrożonego planu TASK-1177–1178 z listy planów oczekujących.

### Recommended next task

- Po kontrolach i audycie: decyzja operatora o scaleniu oraz uruchomieniu
  poprawionego API w widocznym terminalu operatora.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1181 — Jobs | gpt-6.1-sol | high | Uzupełnienie znanego kontraktu i regresja HTTP | Claude Code claude-opus-5-5/high |
