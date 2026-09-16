---
title: TASK-0491 — Raport, ręczna korekta i wznowienie importu
status: done
owner: Codex
created: 2026-09-06
---

# TASK-0491 — Raport, ręczna korekta i wznowienie importu

## Relevant docs

- ai_docs/requirements/IMAGE_INGESTION.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/process/DECISION_LOG.md
- ai_docs/process/DEFINITION_OF_DONE.md

## Zależności

TASK-0490

## Zakres i zaakceptowany plan

Raport rozdziela liczby i ostrzeżenia. Kontynuuj z ręczną korektą tworzy nowy idempotentny run z managed originals i manifestem strony. Spójny pion API/OpenAPI/klient/Admin, bez migracji ani uruchamiania importu użytkownika.
Zlecenie użytkownika obejmuje pełną serię 0489–0491. Nie zmieniamy algorytmu
v0.10 v3, kotwic, progów pojedynczej siatki ani istniejących jobów.

## Testy i Definition of Done

- Niska lub zerowa skuteczność nie gubi slotów i nie zatrzymuje katalogu.
- Zakres, integralność oraz ręczne decyzje pozostają chronione.
- Retry i utrata odpowiedzi nie tworzą duplikatów.
- Testy zmienionego pionu, Ruff/mypy, lint/typecheck, OpenAPI i build.
- Dokumentacja, Outcome i osobny commit z kolejnym numerem wersji.

## Outcome

- Istniejący managed reprocess przyjmuje jawny wariant kontynuacji. Kopiuje
  snapshoty i manifest źródła; retry zwraca ten sam run również przy zmienionym
  bieżącym fingerprintcie aplikacji. Integralność pozostaje fail-closed.
- Raport rozdziela liczniki zdjęć od siatek i pokazuje ostrzeżenie próbki.
  Akcja Popraw siatki otwiera istniejący lokalny Reviewer w korekcie.
- Zachowano pełne sloty, rewizje, atomowy zapis i szkice z TASK-0490.
  Nie zmieniono algorytmu geometrii ani bieżących jobów.
- Weryfikacja: 131 testów API/workera, 25 testów akcji/kontraktu Admina,
  51 testów klienta, 28 testów Reviewera oraz 2 testy route kontynuacji.
  Ruff, mypy (5 zmienionych modułów, follow-imports=silent), lint/typecheck
  Admina i Reviewera, OpenAPI i oba produkcyjne buildy przeszły.
- Formatowanie ograniczone do zmienionych plików; wcześniejsze niezwiązane
  zmiany, w tym admin next-env, pozostają poza commitem. Doprecyzowano
  istniejącą adnotację Literal pochodzenia geometrii bez zmiany zachowania.
- Nie wykonywano pełnego importu danych użytkownika, migracji, benchmarku,
  restartu usług ani wizualnego odbioru uruchomionego systemu. Operator może
  teraz jawnie kontynuować zatrzymany import bez ponownego uploadu.
