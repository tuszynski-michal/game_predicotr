---
title: TASK-0170 versioned image scan cache and resume
status: todo
release: "0.4"
last_updated: 2026-08-04
---

# TASK-0170 — Versioned image scan cache and resume

## Status

`todo`

## Goal

Ponownie wykorzystywać lekkie obserwacje niezmienionych JPEG-ów po retry,
restarcie i uruchomieniu zgodnej wersji selektora bez ponownego dekodowania.

## Context

Cache nie zastępuje przyspieszenia pierwszego przebiegu, ale usuwa koszt
powtarzania tej samej pracy podczas iteracji na stagingu 32 079 zdjęć.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0169-range-agnostic-selection-output-and-import-handoff.md`

## Scope

- kluczować obserwację przez checksum pliku i fingerprint lekkiego scan adaptera,
- przechowywać wyłącznie bounded metadane, deskryptor i metryki bez obrazu,
- atomowo zapisywać cache w kontrolowanym storage,
- unieważniać wpis po zmianie adaptera, parametrów lub checksumy,
- weryfikować pełną checksumę wybranego reprezentanta przed publikacją,
- raportować cache hit/miss oraz czas zaoszczędzony na podstawie baseline'u,
- zachować checkpoint jako źródło prawdy postępu runu; cache jest tylko
  odtwarzalną optymalizacją.

## Out of scope

- współdzielony cache sieciowy, Redis albo baza BLOB,
- cache wyników OCR lub geometrii należących do Importu layoutów,
- pominięcie końcowej weryfikacji pliku publikowanego do outputu,
- automatyczne kasowanie stagingu użytkownika.

## Acceptance criteria

- [ ] Powtórny zgodny scan ma mierzalne cache hits i nie dekoduje trafionych
      JPEG-ów.
- [ ] Zmiana fingerprintu lub pliku daje cache miss.
- [ ] Uszkodzony lub częściowo zapisany cache jest ignorowany i odbudowywany.
- [ ] Cache nie zmienia deterministycznych grup ani reprezentantów.
- [ ] Manifest wynikowy nadal weryfikuje checksumy wybranych JPEG-ów.
- [ ] Rozmiar cache rośnie liniowo i ma opisaną politykę bezpiecznego cleanupu.

## Technical notes

Nie należy osłabiać integralności. Checksum powstała podczas uploadu identyfikuje
immutable staged source, natomiast przed publikacją wybrany plik jest ponownie
sprawdzany end-to-end.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/io.py`
- `services/worker/src/game_predictor_worker/images/selection/job.py`
- `services/worker/src/game_predictor_worker/images/selection/manifest.py`
- `services/worker/tests/test_image_selection_job.py`
- `services/worker/tests/test_image_selection_adapters.py`

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_image_selection_job.py services/worker/tests/test_image_selection_adapters.py
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/selection services/worker/tests/test_image_selection_job.py
```

## Risks / open questions

- Cache bez limitu może niepotrzebnie zajmować dysk. Cleanup musi usuwać tylko
  odtwarzalne obserwacje i nie może dotknąć stagingu ani finalnego outputu.

## Outcome

Do uzupełnienia po realizacji.
