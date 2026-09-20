---
title: TASK-0584 — V7 selection feasibility and isolation
status: in_progress
last_updated: 2026-09-20
---

# TASK-0584 — Wykonalność selekcji v7

## Status

`done`

## Goal

Udostępnić powtarzalny probe, który potwierdza lokalny model, Paddle, korpus i izolowane artefakty przez rzeczywiste wywołanie OCR na JPEG-u.

## Context

Pozostałe taski zależą od lokalnego OCR działającego na rzeczywistych danych. Wykonanie biegnie na `version-0.10`, bez worktree i bez dotykania istniejących zmian użytkownika.

## Dependencies / entry conditions

- Korpus jest przekazywany argumentem, nigdy zaszywany w kodzie.
- `en_PP-OCRv5_mobile_rec` pochodzi z oficjalnego archiwum PaddleOCR, a sumy jego trzech plików są wpisane do Outcome.
- `.venv` bieżącego checkoutu zawiera zależności projektu.

## Recommended execution

`gpt-5.6-terra xhigh`; niezależny review `gpt-6-astra medium` przed commitem. Zatrzymać kolejne taski przy braku modelu, nieudanej inferencji, pustym korpusie lub artefaktach poza checkoutem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`

## Scope

- Testowalny probe modelu, Paddle, korpusu i katalogu artefaktów.
- CLI z odwracalnym testem zapisu pod `.runtime` checkoutu.
- Rzeczywiste wywołanie istniejącego OCR na JPEG-u z raportem batcha.

## Out of scope

- Trening lub zmiana modelu, skan całego korpusu, katalog `cut`, API i migracje.
- Zmiana istniejącego v6 lub aktywowanie v7.

## Acceptance criteria

- [x] Probe blokuje brak/niekompletność modelu, runtime, pusty korpus, brak GPU gdy wymagany i zero batchów OCR.
- [x] Żaden katalog artefaktów poza checkoutem nie może zostać przygotowany.
- [x] Test zapisu nie nadpisuje ani nie usuwa istniejącego pliku.
- [x] CLI raportuje katalogi JPEG i diagnostykę OCR.
- [x] Rzeczywista próba jest wpisana do Outcome.

## Test cases

- Brak modelu, model niekompletny, pusty korpus, CUDA build bez urządzenia, zero batchów OCR.
- Mieszane rozszerzenia JPEG są zliczane deterministycznie.
- Błąd zapisu usuwa wyłącznie własny plik tymczasowy; wcześniejszy plik pozostaje.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_v7_selection_feasibility.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection/v7_feasibility.py services/worker/tests/test_v7_selection_feasibility.py scripts/probe_v7_selection_environment.py
.\.venv\Scripts\python.exe scripts/probe_v7_selection_environment.py --checkout-root . --artifact-root .runtime/v7-selection --corpus-root "<operator corpus>" --model-root artifacts/m5-models/sequence-number-ocr-v1 --prepare-artifact-root
```

## Risks / open questions

- Paddle 3.3.1 jest CPU-only mimo RTX 4050. To ostrzeżenie T00 i bramka pomiaru T11; GPU nie jest dziś aktywne.

## Outcome

### Changed

- Dodano testowalną bramkę środowiska v7 oraz CLI bez mutowania JPEG-ów.
  Raportuje kompletność modelu, runtime Paddle, urządzenia GPU, bezpośrednie
  katalogi korpusu, lokalne etykiety/pozycje, czas i liczbę batchy rzeczywistego
  OCR. Sam brak zakresu nie jest przedstawiany jako dowód numeracji.
- Dodano powtarzalny skrypt PowerShell pobierający wyłącznie oficjalne archiwum
  Paddle, weryfikujący SHA-256 archiwum i trzech plików oraz publikujący model
  dopiero po pełnej weryfikacji. Skrypt nie nadpisuje istniejącego katalogu.
- Audyt Astra doprecyzował, że T00 potwierdza runtime, lecz nie pozytywną
  skuteczność lokalizacji. T02 musi zbudować i zmierzyć lokalizator etykiet;
  nie wolno traktować wyniku T00 jako automatycznego dowodu zakresu.

### Verification results

- `pytest`: 11 passed; `ruff` i `mypy`: PASS.
- `provision_v7_sequence_ocr_model.ps1 -VerifyOnly`: PASS. Oficjalne archiwum
  ma SHA-256 `E595B4CF2FFAD19FBB5A61BA345D63939577A3AB8717B6E5995642590C9101B4`.
  Zweryfikowano też `inference.json`
  `FD1B6EC722EA841A72D3BA43E527DF1D1066D5D7808E0503EE3EEC7265188753`,
  `inference.pdiparams`
  `3EC8A97ED6CEFE8568D3E2EE90BB193299B566A7661AA4FD52D224B96B59F66B` oraz
  `inference.yml`
  `27E91D0582F40168AA218303C76E184BC78FA7A5D105AAD0CFBAD8458B441067`.
- Rzeczywisty probe: 3 241 JPEG-ów w 10 katalogach, Paddle 3.3.1 CPU,
  `ocrBatchCalls=5`, 1 322 ms dla `777/302200 777_000645.jpg`; model nie
  odczytał lokalnej etykiety (`RANGE_LABEL_LATTICE_INCOMPLETE`). Ograniczona,
  read-only próba 40 zdjęć (po cztery z każdego katalogu) potwierdziła ten sam
  brak etykiet i czas 0,03–1,51 s na zdjęcie.

### Not completed

- RTX 4050 nie jest dostępny dla zainstalowanego Paddle (`compiledWithCuda=false`);
  pozostaje warningiem i przedmiotem T11.
- Istniejący v3 nie jest skutecznym lokalizatorem etykiet na badanej próbce.
  T00 nie zmienia jego polityki i nie zamraża kontraktu dowodu v7.

### Documentation updates

- Dodano plan wykonawczy v7 oraz wpis o wyniku T00 w `CURRENT_STATE.md`.

### Recommended next task

- T01 — niezmienny manifest korpusu, splity i kontrakt zakresów; T02 otrzyma
  jawnie negatywny wynik bazowy lokalizacji.
