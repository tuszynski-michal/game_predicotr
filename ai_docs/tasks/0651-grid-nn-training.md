---
title: TASK-0651 — Sieć siatek v3: model, trening CPU i wydanie ONNX
status: blocked
---

# TASK-0651 — Model (etap A + B), trening i wydanie

## Status

`blocked` — plan zastąpiony przez `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (D-447); trening to TASK-0669/TASK-0670 i warunkowo TASK-0675. Numer koliduje z ukończoną serią „Przybliżona wygrana”; identyfikuj plik pełną ścieżką.

## Goal

Wytrenowane na zaakceptowanych danych modele etapu A (lokalizacja 9 plansz) i B (24 punkty siatki na wycinku) z eksportem ONNX, parytetem i manifestem wydania `shadowOnly=true`.

## Dependencies / entry conditions

- TASK-0650 `done`, zbiór złoty i ≥ 3 000 zaakceptowanych plansz treningowych.

## Recommended execution

`claude-opus-5-5`, reasoning `high`; review kontraktu ONNX i splitu: `claude-opus-5-5`, reasoning `high`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_ENGINE_V3_NEURAL_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-261, D-262)

## Scope

- Pakiet (proponowany) `images/grid_nn/` na wzór `images/keypoint_geometry` (dataset, model, onnx_adapter, release): etap A rozszerza kontrakt heatmap `9 × 4` o środki plansz; etap B — lekki enkoder-dekoder, wejście ~256 × 160, 24 heatmapy + 15 logitów widoczności komórek, dekodowanie sub-pikselowe.
- Augmentacje: rozmazanie ruchu, odblask, syntetyczne zasłonięcia (dłoń/strzałka), perspektywa, zakrzywienie, jasność/kontrast/kolor, przesunięcie wycinka (symulacja błędu etapu A).
- Trening CPU wznawialny (checkpointy w `artifacts/`), stały seed, walidacja per epokę, cache wycinków na dysku.
- Eksport ONNX (opset 18), test parytetu PyTorch↔ONNX, pomiar czasu CPU, manifest wydania (dataset checksum, split, konfiguracja, metryki walidacji).

## Out of scope

- Aktywacja w jakimkolwiek przepływie zapisu.

## Acceptance criteria

- [ ] Walidacja etapu B: mediana błędu punktu ≤ 0,05 komórki.
- [ ] Parytet ONNX; inferencja ≤ 300 ms/zdjęcie na CPU.
- [ ] Manifest `shadowOnly=true`, `activationAllowed=false`.

## Outcome

Wypełnia agent po pracy.
