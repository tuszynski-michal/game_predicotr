---
title: Odbiór przepływu niepełnych plansz
status: done
last_updated: 2026-09-07
---

# TASK-0509 — Odbiór przepływu niepełnych plansz

## Status

`done` — odbiór inżynierski; wdrożenie i test na urządzeniu pozostają operatorskie.

## Goal

Odbiór przepływu niepełnych plansz, według zaakceptowanego planu „Niepełne plansze i wykluczanie niepewnej geometrii z uczenia”.

## Context

Operator zlecił całą serię 0505–0509 wraz z audytami; bez zatrzymywania po każdym tasku.

## Dependencies / entry conditions

TASK-0505–0508; jego implementacja oraz wymagany audyt muszą być odebrane. Obce zmiany i pozostałości TASK-0504 pozostają poza commitem. Bez restartów usług i operacji na danych operatora.

## Recommended execution

`gpt-5.6-sol high`, zgodnie z końcową tabelą zaakceptowanego planu. Wymagany niezależny audyt `gpt-6-astra high` przed zamknięciem: geometria, trwałość lub integracja właściwa dla zakresu. Eskalacja przy konflikcie kontraktu lub bezpieczeństwa danych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` — ręczna kompletność i kwalifikacja
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/DECISION_LOG.md` — D-371

## Scope

- Testy przyciętej góry/dołu/boków/pochylenia/dwóch rogów, samej ramki, masek automatycznych/ręcznych i 15/15.
- Zachować wszystkie sloty z nazwy i krótszy końcowy zakres. Spójność preflight/import/GridReview/render.
- Testy zachowania i wywołań API: nawigacja bez zapisu, szkic, refresh, konflikt, atomic save, utrata odpowiedzi/idempotencja.
- Sprawdzić wykluczenia kohort/kotwic, historyczne manifesty i brak duplikatów; izolowane fixture’y z kilku istniejących źródeł bez reimportu operatora.
- API/worker/Admin/Reviewer testy, Ruff/mypy/lint/typecheck/OpenAPI/format oraz oba buildy. Dokumentacja wymagań, architektury, Decision Log, Current State, wyniki i ograniczenia.

## Out of scope

Detektor produkcyjny v0.10, OCR, lokalny auto-crop, aktywne joby, dane operatora, cleanup. Warunkowa prośba o eksperymentalny v0.10.4 wymaga osobnej analizy po odbiorze tej serii.

## Acceptance criteria

- [x] Testy przyciętej góry/dołu/boków/pochylenia/dwóch rogów, samej ramki, masek automatycznych/ręcznych i 15/15.
- [x] Zachować wszystkie sloty z nazwy i krótszy końcowy zakres. Spójność preflight/import/GridReview/render.
- [x] Testy zachowania i wywołań API: nawigacja bez zapisu, szkic, refresh, konflikt, atomic save, utrata odpowiedzi/idempotencja.
- [x] Sprawdzić wykluczenia kohort/kotwic, historyczne manifesty i brak duplikatów; izolowane fixture’y z kilku istniejących źródeł bez reimportu operatora.
- [x] API/worker/Admin/Reviewer testy, Ruff/mypy/lint/typecheck/OpenAPI/format oraz oba buildy. Dokumentacja wymagań, architektury, Decision Log, Current State, wyniki i ograniczenia.
- [x] Testy i niezależny audyt zakresu oraz zgodność historyczna.

## Technical notes

TASK-0508 odebrany audytem w v0.10.224. Odbiór nie uruchamia migracji ani
starego importu. Kontrole DB operatora nie są testem izolowanym; nie używać
fixture'ów resetujących lokalną bazę. Testy renderowania użyją małych,
izolowanych danych i odczytu kilku istniejących źródeł.
Planowane pliki: raport `ai_docs/quality/PARTIAL_GEOMETRY_ACCEPTANCE.md`,
test odbiorczy ręcznej kwalifikacji oraz dokumentacja operatorska.

Kanoniczny właściciel kwalifikacji to snapshot rewizji źródła; nullable projekcje nie są alternatywną prawdą. Nowe oznaczenia nie mogą zniknąć przez historyczny zapis. Żaden szablon nie tworzy fikcyjnego cropa ani zatwierdzenia.

## Expected files

Testy istniejących modułów i dokumenty wymienione w Relevant docs.

## Test cases

Każde kryterium zakresu otrzymuje test zachowania, w tym przypadki negatywne i zgodność historyczna. Nie osłabiać testów dla zielonego wyniku.

## Verification

Kontrole wykonano ze skryptów repo: najpierw testy pionu, potem typy/lint i szersza kontrola. Kroki miały timeout do 120 s, znane buildy do 300 s po zapowiedzi. Wyniki i ograniczenia odbioru podano poniżej oraz w raporcie jakości.

## Risks / open questions

Samo zapisanie wykluczenia nie odtrenowuje aktywnego profilu. Bezpieczne read-only fixture’y nie dowodzą odbioru UI na urządzeniu operatora.

## Outcome

Odbiór inżynierski zakończony. Szczegóły, komendy i scenariusze operatora:
`ai_docs/quality/PARTIAL_GEOMETRY_ACCEPTANCE.md`. Zaliczone: 182 testy API,
120 workera, 431 Admina, 183 Reviewera, 6 interakcji, 54 klienta oraz dodatkowa
grupa 13 testów krawędzi/slotów (grupy pokrywają się). Oba buildy/lint/typecheck,
OpenAPI, Ruff i format zmienionych plików zaliczone; mypy 41 źródeł
z --follow-imports=silent zaliczone.
Globalny format wykazał wcześniejsze problemy poza zakresem; nie formatowano
obcych plików. Ponownie sprawdzono formatowanie plików TASK-0508.

Nowe regresje: dwa ucięte rogi z maską 0/5/9/14, pełne symbole przy brakującej
ramce, pięć końcowych slotów 499996–500000. Read-only skrypt sprawdził trzy
istniejące JPEG-i, nie zmieniając żadnych źródeł; jego quady są fixture'ami
protokołu, nie referencjami jakości detektora.

Audyt gpt-6-astra high przyjął kod po uzupełnieniu obu regresji krawędzi;
niezależnie 13 testów zaliczonych, brak dalszych blockerów odbioru inżynierskiego.
Nie wykonano migracji 0100/0101, restartów, reimportów ani odbioru Androida
i rzeczywistej współbieżności PostgreSQL. Te ograniczenia nie są oznaczone
jako zaliczone. Instrukcja uruchomienia została uzupełniona.

Oceniono warunkowe rozszerzenie v0.10.4: samodzielne wykrywanie bocznych
partial wymaga nowej hipotezy geometrii i testów jakości, nie jest lekką
zmianą. Nie osłabiono istniejących bramek i nie dodano pozornej wersji silnika.
Obsługa ręczna działa bez zmiany detektora; automaska dotyczy wskazanego quada.
