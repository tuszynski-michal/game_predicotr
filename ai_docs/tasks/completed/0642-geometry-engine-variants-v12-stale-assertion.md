---
title: TASK-0642 — napraw nieaktualną asercję geometryEngineVariants (v1.2)
status: done
last_updated: 2026-09-24
---

# TASK-0642 — napraw nieaktualną asercję `geometryEngineVariants` (v1.2)

## Status

`done`

## Goal

`test_image_import_engine_policy_requires_preview_and_is_per_game`
przechodzi zielono, asercja odzwierciedla rzeczywisty, zamierzony kontrakt
API.

## Context

Napotkane jako czerwone przy realizacji TASK-0637 (D-442), niezwiązane z
tamtym planem — użytkownik poprosił o naprawę po jego zamknięciu.

## Dependencies / entry conditions

- Brak. Fakt potwierdzony przez `git show --stat 4afa8b30` (`v0.10.354 -
  add v1.2 contrast frame geometry`): ten commit dodał wariant
  `contrast_frame_grid_v1_2` do
  `services/api/src/game_predictor_api/schemas/image_geometry_rollout.py::to_image_import_engine_policy_response`
  (funkcja zawsze zwraca wszystkie 3 zarejestrowane warianty — v1.0, v1.1,
  v1.2 — niezależnie od aktywnej polityki gry), ale **nie zmienił**
  `services/api/tests/test_image_grid_review_api.py`, który wciąż
  oczekiwał dokładnie 2 wariantów. To nie jest zależne od środowiska —
  `LATERAL_PARTIAL_RELEASED = True` w
  `services/worker/src/game_predictor_worker/images/lateral_partial_contract.py:36`
  jest stałą modułu (nie flagą/env), więc `enabled=True` dla v1.2 jest
  deterministyczne wszędzie.
- Fakt: TASK-0613 (`ai_docs/tasks/completed/0613-v12-contrast-frame-grid-engine.md`)
  opisuje v1.2 jako jawny, **opt-in** wariant testowy (stąd etykieta „(test)”
  w nazwie) — `enabled=True` oznacza tylko, że jest wybieralny jako
  `targetPolicy`, nie że jest domyślny. Kontrakt produkcyjny (zawsze 3
  warianty w liście) jest zamierzony; test był po prostu nieaktualny.

## Recommended execution

claude-sonnet-5, reasoning: medium. Aktualizacja jednej asercji testowej
zgodnie z potwierdzonym, zamierzonym zachowaniem produkcyjnym; niskie
ryzyko. Dodatkowy review: nie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/tasks/completed/0613-v12-contrast-frame-grid-engine.md`

## Scope

- `services/api/tests/test_image_grid_review_api.py`: rozszerzona lista
  oczekiwana w `test_image_import_engine_policy_requires_preview_and_is_per_game`
  o trzeci wpis (`contrast_frame_grid_v1_2`, `enabled=True`, bez blokera),
  dokładnie zgodny z `to_image_import_engine_policy_response`.

## Out of scope

- Zmiana produkcyjnego kodu (`image_geometry_rollout.py`,
  `lateral_partial_contract.py`) — zachowanie jest zamierzone.
- Zmiana `LATERAL_PARTIAL_RELEASED` ani logiki dostępności wariantów.

## Acceptance criteria

- [x] Test zielony.
- [x] Pełny `test_image_grid_review_api.py` zielony (17/17).
- [x] Nowa asercja bajt-w-bajt zgodna z etykietą w kodzie produkcyjnym
      (zweryfikowane programowo, nie wzrokowo — porównanie stringów w
      Pythonie, nie w terminalu, ze względu na kodowanie konsoli).

## Technical notes

Przed: `geometryEngineVariants == [v1.0, v1.1]` (2 elementy).
Po: `geometryEngineVariants == [v1.0, v1.1, v1.2]` (3 elementy), trzeci
wpis: `{"variant": "contrast_frame_grid_v1_2", "label": "v1.2 —
kontrastowa ramka i siatka (test)", "enabled": True, "blockerCode": None,
"blockerMessage": None}`.

## Expected files

- Istniejące: `services/api/tests/test_image_grid_review_api.py`.

## Test cases

- `current.json()["geometryEngineVariants"]` zawiera dokładnie 3 wpisy w
  ustalonej kolejności v1.0 → v1.1 → v1.2, wszystkie `enabled=True`, bez
  blokerów.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_grid_review_api.py -q
npm run python:lint
```

Uruchomione i zielone: 17/17 testów w pliku, `ruff check`/`format --check`
czyste.

## Risks / open questions

- Brak. Zachowanie produkcyjne niezmienione, wyłącznie asercja testowa
  dogoniła istniejący kontrakt.

## Outcome

### Changed

- [services/api/tests/test_image_grid_review_api.py](../../services/api/tests/test_image_grid_review_api.py):
  `test_image_import_engine_policy_requires_preview_and_is_per_game` teraz
  oczekuje 3 wariantów geometrii zamiast 2.

### Verification results

- `pytest services/api/tests/test_image_grid_review_api.py`: 17/17
  zielone (wcześniej 16/17).
- Programowe porównanie stringów (Python `repr`/`==`) potwierdziło
  identyczność etykiety w teście i w
  `services/api/src/game_predictor_api/schemas/image_geometry_rollout.py`
  (unikając mylącego kodowania w terminalu Windows).
- `ruff check`/`ruff format --check`: czyste.
- `python:typecheck`: brak nowych błędów w zmienionym pliku.

### Not completed

- Nic — pełny zakres wykonany.

### Documentation updates

- Ten plik przeniesiony do `ai_docs/tasks/completed/`.
- `ai_docs/process/CURRENT_STATE.md` — nowa notatka.

### Recommended next task

- Brak.
