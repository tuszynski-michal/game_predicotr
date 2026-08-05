---
title: TASK-0170 versioned image scan cache and resume
status: done
release: "0.4"
last_updated: 2026-08-04
---

# TASK-0170 — Versioned image scan cache and resume

## Status

`done`

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

- [x] Powtórny zgodny scan ma mierzalne cache hits i nie dekoduje trafionych
      JPEG-ów.
- [x] Zmiana fingerprintu lub pliku daje cache miss.
- [x] Uszkodzony lub częściowo zapisany cache jest ignorowany i odbudowywany.
- [x] Cache nie zmienia deterministycznych grup ani reprezentantów.
- [x] Manifest wynikowy nadal weryfikuje checksumy wybranych JPEG-ów.
- [x] Rozmiar cache rośnie liniowo i ma opisaną politykę bezpiecznego cleanupu.

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

Dodano osobny `scan_adapter_fingerprint`, który obejmuje wyłącznie reduced
decode, deskryptor/geometry adapter i metryki jakości. Cache zapisuje bounded
obserwację bez obrazu i ścieżki jako atomowy, kanoniczny JSON adresowany checksumą
JPEG-a i tym fingerprintem. Cache hit wiąże obserwację z aktualnym źródłem, ale
nie zmienia checkpointu ani kolejności domenowej.

Handler raportuje cache hit/miss, nieprawidłowe wpisy, błędy zapisu, liczbę i
rozmiar nowych wpisów oraz szacowany czas zaoszczędzony z baseline'u. Uszkodzony
wpis jest pomijany i odbudowywany, a niedostępny cache degraduje się do zwykłego
skanu zamiast kończyć job. Końcowy publisher nadal liczy checksumę wybranego
JPEG-a end-to-end.

Weryfikacja 2026-08-05:

- `pytest test_image_selection_job.py test_image_selection_adapters.py` —
  `32 passed`,
- `ruff check` oraz `ruff format --check` dla zmienionych modułów — zaliczone po
  formatowaniu,
- pełnego benchmarku 40 000 nie uruchamiano; należy do TASK-0171.

Cleanup: przy zatrzymanym workerze można usunąć wyłącznie
`data/cache/image-selection-scan/`. Jest to odtwarzalny cache; staging, manualne
źródła i finalny output pozostają poza tą operacją.
