---
title: TASK-0490 — Pełna liczba slotów wynikająca z nazwy
status: done
owner: Codex
created: 2026-09-06
---

# TASK-0490 — Pełna liczba slotów wynikająca z nazwy

## Relevant docs

- ai_docs/requirements/IMAGE_INGESTION.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/process/DECISION_LOG.md
- ai_docs/process/DEFINITION_OF_DONE.md

## Zależności

TASK-0489

## Zakres i zaakceptowany plan

Zakres seq_start-end wyznacza sloty i numery. Dziewięć poza końcem gry. Edytor zawiera także odroczone sloty i szablony, pełny atomowy zapis zachowuje szkic i częściowe geometrie.
Zlecenie użytkownika obejmuje pełną serię 0489–0491. Nie zmieniamy algorytmu
v0.10 v3, kotwic, progów pojedynczej siatki ani istniejących jobów.

## Testy i Definition of Done

- Niska lub zerowa skuteczność nie gubi slotów i nie zatrzymuje katalogu.
- Zakres, integralność oraz ręczne decyzje pozostają chronione.
- Retry i utrata odpowiedzi nie tworzą duplikatów.
- Testy zmienionego pionu, Ruff/mypy, lint/typecheck, OpenAPI i build.
- Dokumentacja, Outcome i osobny commit z kolejnym numerem wersji.

## Outcome

Walidacja preflightu i planu uploadu odrzuca krótkie zakresy wewnętrzne.
Istniejąca kolejka i atomowy zapis obejmują aktualne oraz odroczone sloty;
rozszerzono regresję zapisu na wszystkie 9 odroczonych, bez fikcyjnych cropów.
Worker zachowuje także końcowy zakres pięciu plansz. Dodano trwałe szkice
lokalnego edytora z kontrolą checksum, rewizji i granic współrzędnych.
27 testów API, 28 testów Reviewera, lint i typecheck Reviewera, Ruff oraz
mypy domeny przeszły. Kontrole produkcyjnego builda po pionie 0491.
