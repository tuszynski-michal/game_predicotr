---
title: TASK-1205 — Uczenie korekt siatek nie tworzy kandydata gorszego od modelu bazowego
status: done
last_updated: 2026-11-13
---

# TASK-1205 — Uczenie korekt siatek nie tworzy kandydata gorszego od modelu bazowego

## Status

`done`

## Goal

Trening `grid-corrections-v1` mierzy model bazowy na VALIDATION przed pierwszym krokiem i
kończy się kodem `GRID_TRAINING_NO_IMPROVEMENT` bez eksportu kandydata, gdy żaden
checkpoint nie jest od niego ściśle lepszy według reguły wyboru checkpointu.

## Context

Uczenie `12ffda06` (Mumie A2, 2026-11-13) startowało z `abe39bce`. Model bazowy miał na
VALIDATION `boardCorrectRate` 0,678; wszystkie checkpointy 600–3600 kroków miały 0,520–0,626.
Reguła `validation-board-correct-photo-macro-error-earliest-v1` wybiera najlepszy krok
treningu, ale nie porównuje go z krokiem 0, więc wyeksportowała kandydata `01767a49`,
gorszego od bazy we wszystkich miarach. Operator: „Tak, napraw”, „Etap A, potem B”.
Decyzja: D-611.

## Dependencies / entry conditions

- `main` na v1.7.635 (TASK-1204). Bez migracji.
- Fakty: etykiety 550 wspólnych plansz kohort `0630f2cc` i `7e239be4` są identyczne;
  nowa kohorta dodała 48 plansz. Spadek wynika z dalszego treningu gotowego modelu.

## Recommended execution

Claude Opus 5.5, reasoning medium; bez dodatkowego review (zakres jednego modułu
workera, operator zatwierdził etap bez audytu krzyżowego w tej sesji).

## Relevant docs

- `AGENTS.md`
- [D-578](../process/decisions/DECISION_LOG_2026.md) (uczenie korekt), D-611 (nowa)
- `ai_docs/architecture/ADMIN_APP.md`

## Scope

- `training_core.grid_training.train`: opcja `baseline_floor`; na świeżym starcie ocena
  sieci bazowej (`evaluate`) przed pętlą, zapis `baselineFloor` w `bestState` każdego
  checkpointu, odczyt przy wznowieniu; `TrainingResult.baseline_floor`.
- `images.grid_training_child._train`: włącza próg dla `grid-corrections-v1` (bez ekranu);
  gdy najlepszy checkpoint nie jest ściśle lepszy od bazy, zwraca
  `status="no_improvement"`, `code="GRID_TRAINING_NO_IMPROVEMENT"` bez eksportu.
  Wynik eksportu niesie `baselineFloor` tylko w `result-<attempt>.json`.
- Admin: polski opis kodu w `grid-model-state.ts`.

## Out of scope

- Zmiana reguły wczesnego zatrzymania, nazwy reguły checkpointu, manifestów i API.
- Preset ekranowy `screen-grid-corrections-v1` i eksperymenty treści.
- Bramka v6 (TASK-1206) i tempo nauki (TASK-1207).

## Acceptance criteria

- [x] Checkpoint ściśle lepszy od bazy (wyższy `boardCorrectRate` albo równy przy niższym
  `normalizedError`) jest eksportowany jak dotąd; manifest i `checkpointSelection` bez zmian.
- [x] Równy albo gorszy najlepszy checkpoint daje `no_improvement` bez katalogu eksportu.
- [x] Wznowienie z checkpointu używa zapisanego progu, nie ocenia ponownie wytrenowanej sieci.
- [x] Checkpoint sprzed zmiany (bez `baselineFloor`) wznawia się bez progu (zapis `null`).
- [x] Kod `GRID_TRAINING_NO_IMPROVEMENT` ma polski opis w panelu uczenia.

## Technical notes

Porównanie używa klucza reguły: `(boardCorrectRate, -normalizedError)` najlepszego kroku
kontra kroku 0; remis oznacza brak poprawy. Ocena bazy nie zmienia `EarlyStopping` ani
historii, więc dotychczasowy wybór checkpointu i moment zatrzymania pozostają takie same.
Supervisor (`grid_training_handler`) już kończy job kodem z wyniku bez eksportu.

## Expected files

- `services/worker/src/game_predictor_worker/training_core/grid_training.py`
- `services/worker/src/game_predictor_worker/images/grid_training_child.py`
- `services/worker/tests/test_grid_training_baseline_floor.py` (nowy)
- `apps/admin/src/features/model-quality/grid-model-state.ts`

## Test cases

- Pętla z syntetycznym ewaluatorem: baza 0,7, checkpointy 0,5/0,6 → floor nie pobity.
- Baza 0,6, checkpoint 0,7 → pobity; równy wynik i niższy błąd → pobity; remis → nie.
- Wznowienie: zapisany próg zostaje, ewaluator nie jest wołany dla kroku 0.
- Child: wynik `no_improvement` bez `_export`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_training_baseline_floor.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests -k "grid_training" -q
```

## Risks / open questions

- Ocena bazy wydłuża przebieg o jedną ewaluację VALIDATION (~1 min).

## Outcome

Commit: v1.7.636 (hash dopisuje kolejny commit).

### Changed

- `grid_training.train(baseline_floor=)`: pomiar bazy na VALIDATION przed krokiem 1,
  `baselineFloor` w `bestState` checkpointów, odczyt przy wznowieniu;
  `TrainingResult.baseline_floor`, `beats_baseline`, `require_baseline_floor`.
- `grid_training_child._train`: próg tylko dla `grid-corrections-v1`; wynik
  `no_improvement`/`GRID_TRAINING_NO_IMPROVEMENT` bez eksportu; `baselineFloor` w wyniku.
- Admin: polski opis `GRID_TRAINING_NO_IMPROVEMENT`.

### Verification results

- `test_grid_training_baseline_floor.py`: 11 passed (przypadek 12ffda06, ścisła poprawa,
  remis, wznowienie z zapisanym progiem, checkpoint sprzed D-611, child bez eksportu).
- Szersze testy treningu siatek (child, handler, durable, shared, content, rescue,
  visibility, admission): 137 passed, 1 failed —
  `test_presets_are_versioned_distinct_and_fingerprint_their_parameters`, identycznie na `main`.
- ruff check/format PASS; mypy zmienionych modułów bez nowych błędów (14 zastanych w
  innych plikach); admin `grid-model-state.test.mjs` 7/7.

### Not completed

- Wdrożenie na workerze GPU i restart (operator, po scaleniu).

### Documentation updates

- D-611 (wpis, indeks; D-581 do archiwum indeksu), `API_CONTRACT.md`.

### Recommended next task

- TASK-1206: bramka v6 wymaga realnej poprawy kandydata.
