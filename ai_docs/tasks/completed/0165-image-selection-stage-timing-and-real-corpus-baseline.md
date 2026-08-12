---
title: TASK-0165 image selection stage timing and real corpus baseline
status: done
release: "0.4"
last_updated: 2026-08-05
---

# TASK-0165 — Image selection stage timing and real-corpus baseline

## Status

`done`

## Goal

Zmierzyć osobno koszt dekodowania, integralności pliku, deskryptora obrazu,
metryk jakości, geometrii, OCR, persistence i publikacji na reprezentatywnych
500–1000 rzeczywistych zdjęciach, bez zmiany wyniku selektora.

## Context

Obecne statystyki pokazują tylko łączny throughput. Nie pozwalają rozstrzygnąć,
czy kolejne usprawnienie faktycznie usuwa wąskie gardło, czy jedynie przenosi
koszt. Upload 32 079 plików działa stabilnie i nie należy do zakresu korekty.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/tasks/0157-image-selection-scale-quality-and-owner-acceptance.md`

## Scope

- dodać monotoniczne pomiary czasu per etap i bounded agregaty p50/p95/max,
- policzyć wywołania dekodera, `PageBoardDetector`, OCR, cropy OCR oraz odczyty
  checksum,
- odróżnić lekki skan wszystkich plików od pracy wykonywanej na granicy grupy,
- zapisać fingerprint wersji kodu i konfigurację CPU/threadingu w raporcie,
- przygotować ograniczony profil 500–1000 plików z twardym timeoutem pięciu
  minut oraz bez kopiowania lub kasowania istniejącego stagingu,
- wskazać trzy największe składniki czasu przed implementacją TASK-0166.

## Out of scope

- zmiana uploadu lub jego storage,
- zmiana progów, grupowania, OCR albo wyboru reprezentanta,
- pełny rerun 32 079 plików,
- optymalizacja na podstawie pojedynczego pomiaru bez porównywalnego baseline'u.

## Acceptance criteria

- [x] Raport rozdziela co najmniej decode, checksum, appearance, quality,
      geometry, OCR, persistence i output.
- [x] Liczniki wywołań kosztownych adapterów są mierzone, a nie estymowane.
- [x] Profil 500–1000 używa rzeczywistych zdjęć w naturalnej kolejności i ma
      timeout nie większy niż 300 s.
- [x] Pomiar nie mutuje runu, stagingu ani uploadu użytkownika.
- [x] Baseline zawiera throughput, peak RSS i liczbę logicznych oraz faktycznie
      używanych wątków.
- [x] Raport wskazuje mierzalny budżet dla kolejnych zadań.

## Technical notes

Metryki nie mogą zawierać obrazów ani ścieżek absolutnych. Instrumentacja ma
być wyłączalna i nie może zmienić selector fingerprintu, jeśli nie zmienia
zachowania domenowego.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/benchmark.py`
- `services/worker/src/game_predictor_worker/images/selection/adapters.py`
- `services/worker/src/game_predictor_worker/images/selection/telemetry.py`
- `services/worker/src/game_predictor_worker/images/selection/job.py`
- `scripts/run_image_selection_benchmark.py`
- `scripts/run_image_selection_benchmark.ps1`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_image_selection_adapters.py services/worker/tests/test_image_selection_job.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile smoke -TimeoutSeconds 300
```

## Risks / open questions

- Profil musi zawierać rzeczywiste duże JPEG-i; syntetyczne kopie małych plików
  nie pokażą kosztu dekodowania.

## Outcome

Wdrożono wyłączalny na poziomie adapterów, współbieżny i bounded kolektor
`image-selection-stage-timing-v1`. Raportuje on osobno checksum, decode,
appearance, quality, geometry, OCR, persistence i output, operacyjne liczniki,
p50/p95/max, wykorzystane wątki oraz fingerprint kodu. Worker zapisuje snapshot
w checkpointach i diagnostyce bez zmiany selector fingerprintu.

Dodano read-only tryb `--real-source-root` dla 500–1000 plików w naturalnej
kolejności, z limitem do 300 s, kontrolą integralności stagingu przed i po
pomiarze, peak RSS, throughputem i trzema dominującymi etapami. Tryb nie kopiuje,
nie usuwa ani nie aktualizuje wejściowego stagingu.

Testy jednostkowe kolektora, adaptera, benchmarku i job handlera przechodzą.
Właściciel zdecydował, że rzeczywiste profile oraz odbiór czasu 40 000 zdjęć
zostaną wykonane wspólnie po ostatnim zadaniu optymalizacyjnym w TASK-0171.
TASK-0165 zamyka więc kontrakt pomiarowy i narzędzia, bez konkurencyjnego
benchmarku obciążającego historyczny job.
