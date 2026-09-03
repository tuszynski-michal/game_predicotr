---
title: TASK-0420 Persist virtual source board geometry revisions
status: done
last_updated: 2026-09-03
---

# TASK-0420 — Zapis rewizji geometrii `virtual_source`

## Problem

Wspólny zapis dziewięciu ręcznie wyznaczonych plansz poprawnie przechodził
walidację źródła i renderował 135 cropów, ale PostgreSQL odrzucał INSERT do
`image_board_geometry_revisions`. Pythonowe `None` było kodowane przez JSONB
jako JSON `null`, podczas gdy constraint dla `virtual_source` wymaga SQL NULL
w `crop_artifacts`. Po usunięciu tej blokady zapis ujawnił drugi błąd:
`grid_issue` był czyszczony bez przywrócenia modelowej sugestii oczekującego
cropa, co tworzyło niejednoznaczny stan v2. Oba nieobsłużone błędy powodowały
ogólny komunikat Reviewera.

## Scope

- Uzgodnić mapowanie nullable `crop_artifacts` z istniejącym constraintem.
- Po recropie `grid_issue` przywrócić oczekującą sugestię modelu zgodnie z
  istniejącym przejściem domenowym, bez zatwierdzania etykiety.
- Zamienić przyszłą niejednoznaczność outcome v2 na stabilny błąd API.
- Dodać test regresyjny semantyki bindowania PostgreSQL JSONB.
- Potwierdzić pełny prepare oraz zapis w transakcji wycofanej na rzeczywistym
  źródle dziewięciu plansz.

## Out of scope

- Bez zmiany punktów operatora, topologii, API i danych użytkownika.
- Bez migracji schematu: constraint już opisuje poprawny model.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_virtual_grid_geometry_repository.py -q
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/storage/models.py services/api/tests/test_virtual_grid_geometry_repository.py
npm run python:typecheck
```

## Outcome

### Changed

- `crop_artifacts=None` jest bindowane jako PostgreSQL SQL NULL, zgodnie z
  istniejącym constraintem rozłączającym assety legacy i virtual.
- Recrop komórki `grid_issue` przywraca oczekującą sugestię modelową oraz
  usuwa jakość siatki bez zatwierdzania symbolu.
- Niejednoznaczność outcome v2 jest mapowana na stabilny błąd domenowy zamiast
  nieobsłużonego wyjątku serwera.

### Verification results

- `pytest test_virtual_grid_geometry_repository.py test_virtual_grid_geometry.py -q`
  — 10 passed.
- Ruff dla zmienionego repozytorium, modelu i testów — passed.
- `npm run python:typecheck` — passed.
- Read-only prepare rzeczywistego źródła — 9 plansz i 135 cropów.
- Pełny zapis rzeczywistego źródła w transakcji zakończonej rollbackiem — 9
  rewizji, bez trwałej zmiany danych.

### Definition of Done

- Zgłoszony INSERT spełnia istniejący constraint PostgreSQL.
- Przejście `grid_issue -> pending` pozostaje zgodne z domeną i wyklucza crop
  z uczenia do jawnego zatwierdzenia.
- Nie zmieniono API, schematu ani danych operatora.
