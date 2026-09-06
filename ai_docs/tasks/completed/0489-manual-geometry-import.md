---
title: TASK-0489 — Kontynuowanie importu przy słabym dopasowaniu
status: done
owner: Codex
created: 2026-09-06
---

# TASK-0489 — Kontynuowanie importu przy słabym dopasowaniu

## Relevant docs

- ai_docs/requirements/IMAGE_INGESTION.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/process/DECISION_LOG.md
- ai_docs/process/DEFINITION_OF_DONE.md

## Zależności

TASK-0488

## Zakres i zaakceptowany plan

Wersjonowana polityka nowych jobów: próg 98% ostrzega; błędy integralności blokują. Niepewne sloty trafiają do trwałej korekty, poprawne są przetwarzane. Historyczny retry pozostaje niezmienny.
Zlecenie użytkownika obejmuje pełną serię 0489–0491. Nie zmieniamy algorytmu
v0.10 v3, kotwic, progów pojedynczej siatki ani istniejących jobów.

## Testy i Definition of Done

- Niska lub zerowa skuteczność nie gubi slotów i nie zatrzymuje katalogu.
- Zakres, integralność oraz ręczne decyzje pozostają chronione.
- Retry i utrata odpowiedzi nie tworzą duplikatów.
- Testy zmienionego pionu, Ruff/mypy, lint/typecheck, OpenAPI i build.
- Dokumentacja, Outcome i osobny commit z kolejnym numerem wersji.

## Outcome

Nowa polityka v2 jest przypinana i fingerprintowana dla nowych importów.
218/225 kontynuuje rejestrację; v1 nadal blokuje. Zerowa skuteczność zachowuje
odroczone sloty, pełną rewizję źródła bez quadów i pusty output cropów.
Techniczne wyjątki nie są już zamieniane na odroczenia w nowej polityce.
Testy: 100 API/worker przed ostatnim dopięciem rewizji źródła, następnie
64 worker i 3 kontrakty API; Ruff, mypy (5 zmienionych modułów,
follow-imports=silent) oraz wygenerowany OpenAPI/klient. Build Admina i kontrole
UI zostają wykonane po pionie 0491. Bez restartu usług i zmian danych użytkownika.
