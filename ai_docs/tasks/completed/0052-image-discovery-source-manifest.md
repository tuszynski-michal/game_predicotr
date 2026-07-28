---
title: TASK-0052 Image discovery and source manifest
status: done
last_updated: 2026-07-28
---

# TASK-0052 — Image discovery and source manifest

## Status

`done`

## Goal

Zaimplementować deterministyczne, lokalne skanowanie katalogu źródłowego oraz
wersjonowany manifest obrazów bez modyfikowania oryginałów i bez uruchamiania
geometrii, OCR albo zapisu domenowego do PostgreSQL.

## Context

TASK-0051 przygotował prototypowy korpus 12 lokalnych zdjęć, checksumy i
kontrakty golden annotations. Q-016/Q-017, pełna reprezentatywność oraz G3
pozostają otwarte. Właściciel zapowiedział dostarczenie dalszych zdjęć i
polecił przejść do następnego zadania. D-051 dopuszcza wyłącznie discovery
TASK-0052 na obecnym korpusie; nie zalicza G5.1 ani nie otwiera TASK-0053+.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- D-006, D-010, D-014, D-049, D-050 i D-051 w
  `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- rekurencyjne, deterministyczne skanowanie lokalnego katalogu,
- jawny kontrakt `image-discovery-v1`,
- bezpieczne ścieżki względne POSIX bez ścieżki absolutnej w manifeście,
- JPEG jako pierwszy jawnie obsługiwany format wejścia,
- SHA-256 liczone strumieniowo, rozmiar, mtime, wymiary i podstawowe metadata,
- stabilna tożsamość treści niezależna od nazwy pliku,
- wykrywanie identycznej treści pod kilkoma ścieżkami,
- możliwość wybrania wyłącznie checksum nieobecnych w znanym manifeście,
- stabilne kody dla uszkodzonego JPEG, niewspieranego formatu obrazu,
  nieczytelnego pliku i niebezpiecznej ścieżki,
- deterministyczny JSON i CLI działające w Windows PowerShell,
- testy bez zależności od sieci i zewnętrznych modeli.

## Out of scope

- obrót i normalizacja EXIF — TASK-0053,
- kopie robocze i diagnostyczne obrazy — TASK-0053,
- OpenCV, detekcja strony/layoutów/komórek — TASK-0054/TASK-0055,
- OCR — TASK-0056,
- migracja `source_images` i produkcyjny handler importu zdjęć,
- panel administracyjny i manual review,
- zaliczenie G3, G5.1 albo G5.2.

## Assumptions

- W TASK-0052 obsługiwane są pliki `.jpg` i `.jpeg` z prawidłową sygnaturą
  JPEG. Inne rozszerzenia obrazów są raportowane, a pliki niebędące obrazami
  są ignorowane.
- Manifest nie zawiera czasu wygenerowania, aby identyczny katalog dawał
  identyczne bajty JSON. Mtime źródła pozostaje częścią rekordu pliku.
- Powtórna treść jest jednym obrazem źródłowym z listą wszystkich ścieżek.
  Nie jest błędem domenowym i nie uruchamia ponownego przetwarzania.

## Acceptance criteria

- [x] Ten sam niezmieniony katalog daje bajtowo identyczny manifest.
- [x] Manifest 12 zdjęć ma 12 unikalnych checksum i zakres ścieżek względnych.
- [x] Oryginały mają identyczne SHA-256 przed i po skanowaniu.
- [x] Dwie nazwy z identyczną treścią tworzą jeden rekord i alias ścieżki.
- [x] Znany manifest pozwala wybrać wyłącznie nowe checksumy.
- [x] Uszkodzony JPEG i niewspierany format obrazu mają stabilne kody błędów.
- [x] Manifest nie zawiera ścieżki absolutnej ani zawartości binarnej.
- [x] Skanowanie nie wykonuje zapisu w katalogu źródłowym.
- [x] Testy, formatowanie, Ruff i mypy przechodzą.

## Expected files

- `services/worker/src/game_predictor_worker/images/discovery.py`
- `services/worker/tests/test_image_discovery.py`
- `scripts/discover_m5_images.py`
- `ai_docs/quality/m5-source-discovery.json`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe scripts/discover_m5_images.py examples\imgs `
  --output ai_docs\quality\m5-source-discovery.json
.venv\Scripts\python.exe -m pytest services/worker/tests/test_image_discovery.py -q
.venv\Scripts\python.exe -m ruff check `
  services/worker/src/game_predictor_worker/images `
  services/worker/tests/test_image_discovery.py scripts/discover_m5_images.py
.venv\Scripts\python.exe -m mypy `
  services/worker/src/game_predictor_worker/images scripts/discover_m5_images.py
```

## Risks

- Obecny korpus nie pokrywa HEIC, PNG ani zdjęć z innych urządzeń.
- Ręczna implementacja odczytu wymiarów JPEG zostaje ograniczona do discovery;
  Pillow wchodzi w TASK-0053 do pełnej obsługi EXIF i normalizacji.
- Mtime może się zmienić przy kopiowaniu plików mimo identycznej treści; stabilna
  tożsamość i pomijanie znanego wejścia zależą dlatego od SHA-256.

## Outcome

Zaimplementowano dependency-free scanner `image-discovery-v1`, deterministyczny
manifest JSON, CLI z trybem zapisu/check oraz filtrem znanych checksum.
Identyczna zawartość pod wieloma ścieżkami jest grupowana bez ponownego
przetwarzania. Uszkodzone i niewspierane obrazy trafiają do raportu ze stabilnym
kodem zamiast przerywać cały skan.

Rzeczywisty korpus:

- `12` plików źródłowych i `12` unikalnych SHA-256,
- `0` duplikatów treści, `0` problemów discovery,
- manifest SHA-256
  `45ac57f91fefa7c75bb8d281bf5936e59ff94c13345279dbc48ef9ae436801d8`,
- ponowny `--check` przeszedł bez driftu,
- porównanie z manifestem M5 zwróciło `knownImageCount = 12` oraz
  `unseenImageCount = 0`,
- ponowny walidator korpusu potwierdził niezmienione checksumy oryginałów.

Weryfikacja: `11 passed`, Ruff bez błędów i mypy bez błędów dla 6 plików
źródłowych. TASK-0053, Pillow/EXIF i kopie diagnostyczne pozostały poza
zakresem.
