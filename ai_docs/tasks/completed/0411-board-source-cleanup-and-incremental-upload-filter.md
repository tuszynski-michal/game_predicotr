---
title: TASK-0411 — Usuwanie źródeł plansz i filtrowanie uploadu seq_*
status: done
last_updated: 2026-09-03
---

# TASK-0411 — Usuwanie źródeł plansz i filtrowanie uploadu `seq_*`

## Goal

Operator widzi numer planszy przy cropie, może bezpiecznie usuwać całe źródła
zakresów oraz lokalne pliki `seq_*`, a ponowne wskazanie dużego katalogu wysyła
wyłącznie JPEG-i zawierające nadal brakujące plansze.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Scope

- overlay numeru planszy w Weryfikacji symboli;
- lokalne, zbiorcze usuwanie wybranych plików `seq_*` bez restore;
- preview i kontrolowane usunięcie dokładnych zakresów źródłowych wraz z
  zależnymi danymi i ekskluzywnymi artefaktami;
- pre-upload plan browserowego importu, który pomija kompletne zakresy przed
  transferem JPEG-ów;
- OpenAPI, wygenerowany klient, migracja Alembic, testy i aktualizacja
  dokumentacji.

## Out of scope

- TASK-0305 i niedestrukcyjna wymiana pojedynczej planszy;
- automatyczne aktywowanie modelu symboli;
- usuwanie niezależnego modelu `candidate_ready`;
- wykonywanie cleanupu na danych użytkownika.

## Invariants

- usuwanie grupuje wszystkie źródła o identycznym `start/end`; częściowy
  overlap blokuje operację;
- aktywne operacje zapisujące i zależności między grami blokują cleanup;
- kandydat `candidate_ready` niezależny od usuwanych źródeł pozostaje. Preview
  informuje, że kolejny import wymaga jego ręcznej aktywacji;
- bootstrap jest dostępny wyłącznie, gdy po cleanupie nie ma ani aktywacji, ani
  `candidate_ready`;
- pre-upload plan nie wysyła bajtów kompletnego zakresu; zakres częściowy jest
  przesyłany jako cały JPEG;
- lokalna paczka delete kontynuuje po izolowanym błędzie, ale zatrzymuje się po
  błędzie krytycznym journalu lub uchwytu katalogu.

## Acceptance criteria

- [x] Numer planszy jest widoczny na każdym kafelku bez zmiany jego wymiaru.
- [x] Operator może wybrać wiele lokalnych `seq_*` według prefiksu `start` i
  otrzymać raport każdego usunięcia.
- [x] Cleanup usuwa dokładny graf wybranych źródeł, jest idempotentny i ma
  durable recovery kwarantanny.
- [x] Preview pokazuje model po cleanupie oraz blokadę `candidate_ready`.
- [x] Import z dużego katalogu przesyła wyłącznie brakujące albo częściowe
  zakresy; końcowy preflight nadal wykrywa zmianę canonical.
- [x] API, OpenAPI i wygenerowany klient są zgodne, a testy obejmują retry,
  stale plan i konflikt zależności.

## Outcome

Dodano overlay numeru planszy, lokalne paczkowe usuwanie `seq_*`, kontrolowany
cleanup pełnych źródeł oraz planowanie uploadu przed transferem JPEG-ów.
Serwer utrwala zakresy pominięte przez plan w stagingu i ponownie sprawdza je
przed importem, dlatego równoległe usunięcie kanonicznej planszy daje
`IMAGE_SEQUENCE_UPLOAD_PLAN_STALE` zamiast cichego niekompletnego importu.

Weryfikacja: Ruff, 49 ukierunkowanych testów Python, generator oraz kontrola
OpenAPI, typecheck Admina i 46 testów kontraktów Node. Nie uruchamiano
integracji PostgreSQL ani operacji cleanupu na danych użytkownika; wymagają
osobnego, jawnego środowiska testowego i potwierdzenia.
