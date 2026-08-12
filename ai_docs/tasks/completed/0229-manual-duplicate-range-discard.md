---
title: TASK-0229 manual duplicate-range discard
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0229 — Odrzucenie zduplikowanego zakresu w selekcji ręcznej

## Goal

Pozwolić administratorowi jawnie zakończyć ręczną grupę, gdy wskazany zakres
`seq_<start>-<end>` został już rozwiązany przez inną grupę tego samego runu.
Taka grupa nie może wracać do kolejki ręcznej ani nadpisywać istniejącego pliku.

## Problem

Zwykłe zatwierdzenie poprawnie zwraca `IMAGE_SELECTION_RANGE_CONFLICT`, ale modal
nie oferuje sposobu zakończenia faktycznego duplikatu. Użytkownik pozostaje więc
z grupą, której nie da się poprawnie zatwierdzić ani usunąć z kolejki.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- dodać audytowalną decyzję `duplicate_range`,
- przed odrzuceniem potwierdzić po stronie backendu, że inna rozwiązana grupa
  ma dokładnie ten sam zakres,
- zakończyć grupę istniejącym statusem `skipped_existing_range`,
- dodać w modalu akcję `Odrzuć jako duplikat` i usunąć zakończoną grupę z
  bieżącej kolejki,
- zachować idempotencję oraz nie zmieniać istniejącego pliku `seq_<start>-<end>`.

## Verification

- test API sukcesu i idempotentnego replayu,
- test odrzucenia, gdy nie istnieje właściciel identycznego zakresu,
- test kontraktu Admina i kontrola typów wygenerowanego klienta,
- migracja dopuszcza nową wartość audytu bez zmiany statusów grup.

## Outcome

Dodano zweryfikowaną po stronie backendu, idempotentną decyzję
`duplicate_range`, endpoint i migrację audytu. Modal ma przycisk `Odrzuć jako
duplikat`; po sukcesie grupa otrzymuje `skipped_existing_range` i znika z
bieżącej kolejki bez zapisu JPEG-a. Przeszło 19 testów API, test migracji, 186
testów Admina, oba typechecki TypeScript, Ruff oraz kontrola OpenAPI. Pełny
Python mypy nie zakończył się w limicie 60 sekund i został przerwany zgodnie z
zasadami repozytorium; nie zwrócił przed przerwaniem diagnostyki dotyczącej tej
zmiany.
