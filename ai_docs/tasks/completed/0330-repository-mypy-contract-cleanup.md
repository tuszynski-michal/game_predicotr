---
title: TASK-0330 Repository mypy contract cleanup
status: done
version: 0.10
last_updated: 2026-08-30
---

# TASK-0330 — Repository mypy contract cleanup

## Goal

Przywrócić zielony pełny typecheck repozytorium po wykryciu dwóch błędów przy
odbiorze TASK-0329, bez zmiany zachowania produktu.

## Scope

- zastąpić ogólny `object` jawnym portem capacity guarda browserowego uploadu;
- bezpiecznie dekodować nieujemny licznik symlinków z JSONB inwentarza;
- dodać skoncentrowany test dekodera;
- uruchomić pełny `python:typecheck` oraz testy zmienionego obszaru.

## Out of scope

- zmiana polityki storage, progów pojemności i lifecycle stagingu;
- zmiana API, OpenAPI, schematu bazy lub UI;
- refaktory niezwiązanych, istniejących zmian w worktree.

## Relevant docs

- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`

## Definition of Done

- capacity guard ma statycznie sprawdzalny minimalny kontrakt;
- nieprawidłowy JSON licznika nie jest niejawnie konwertowany;
- pełny repozytoryjny mypy przechodzi;
- Ruff i skoncentrowane testy przechodzą;
- niezwiązane zmiany użytkownika pozostają poza commitem.

## Outcome

Pełny repozytoryjny typecheck został przywrócony bez zmiany kontraktów HTTP,
schematu bazy ani zachowania produktu. Capacity guard browserowego uploadu ma
teraz minimalny port typowany przez `Protocol`, a liczniki pochodzące z JSONB i
manifestów są walidowane jako nieujemne liczby całkowite zamiast niejawnego
rzutowania z `object`.

W trakcie pełnej kontroli ujawniły się dalsze istniejące rozbieżności typów,
które zostały naprawione w tych samych granicach: jawne typy iteratorów
manifestów, bezpieczne dekodowanie checkpointów GC i kompakcji, granica typu
wyniku OpenCV, usunięcie zbędnych `type: ignore` oraz sprawdzenie opcjonalnych
crop artifacts. Dwa lokalne, nieśledzone skrypty operatorskie poprawiono tylko
w bieżącym worktree; nie zostały dołączone do commita.

Weryfikacja:

- `npm run python:typecheck` — sukces, 470 plików źródłowych;
- Ruff dla `services/api`, `services/worker` i `scripts` — sukces;
- 70 skoncentrowanych testów API/worker/storage/geometrii — sukces;
- niezwiązane zmiany użytkownika pozostały poza zakresem i commitem.
