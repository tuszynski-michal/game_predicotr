---
title: TASK-0053 EXIF normalization and diagnostics
status: done
last_updated: 2026-07-28
---

# TASK-0053 — EXIF normalization and diagnostics

## Status

`done`

## Goal

Zbudować deterministyczny, lokalny etap normalizacji JPEG, który stosuje
orientację EXIF do kopii roboczej, zachowuje oryginał bez zmian i zapisuje
wersjonowany manifest diagnostyczny potrzebny późniejszej geometrii.

## Context

TASK-0052 dostarczył `image-discovery-v1`, deterministyczny manifest 12 zdjęć
i stabilną tożsamość treści po SHA-256. Obecne pliki nie deklarują orientacji
EXIF, ale pipeline musi poprawnie obsłużyć wszystkie wartości 1–8 dla kolejnych
zdjęć. Właściciel jawnie polecił przejście do następnego zadania; D-052
dopuszcza TASK-0053 bez zaliczenia G3/G5.1 i bez uruchamiania geometrii/OCR.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- D-006, D-010, D-014 i D-049–D-052 w
  `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- przypięcie Pillow 12.3.0 dla Python 3.12,
- kontrakt `image-normalization-v1`,
- ponowna weryfikacja źródłowego manifestu i checksum przed odczytem obrazu,
- odczyt EXIF Orientation 1–8 i jawna nazwa zastosowanej transformacji,
- `ImageOps.exif_transpose` wykonywane wyłącznie na kopii w pamięci,
- deterministyczna kopia robocza RGB PNG bez przenoszenia EXIF,
- niezmienne, content-addressed ścieżki artefaktów,
- manifest diagnostyczny ze źródłowym i wynikowym SHA-256, wymiarami, trybem,
  orientacją, transformacją, ścieżką względną i wersjami pipeline/Pillow,
- idempotentny retry oraz blokada kolizji istniejącego artefaktu,
- stabilne błędy dla driftu manifestu, uszkodzonego obrazu, niedozwolonej
  orientacji, limitu pikseli i niebezpiecznych ścieżek,
- CLI Windows działające całkowicie offline po instalacji zależności,
- testy wszystkich ośmiu wartości Orientation oraz braku tagu.

## Out of scope

- korekta jasności, kontrastu, perspektywy albo zakrzywienia ekranu,
- detekcja strony, layoutów i komórek — TASK-0054/TASK-0055,
- OCR — TASK-0056,
- PostgreSQL, jobs i panel administracyjny,
- miniatury UI, manual review i klasyfikacja symboli,
- zaliczenie G3, G5.1 lub pełnego G5.

## Assumptions

- Kopia robocza jest zapisywana jako RGB PNG, aby uniknąć kolejnej stratnej
  kompresji przed geometrią.
- Brak tagu Orientation oznacza brak transformacji i jest zapisywany jako
  `null`; wartość `1` również nie zmienia pikseli, ale pozostaje jawna.
- Artefakty trafiają poza katalog źródłowy. Repozytorium śledzi mały raport,
  nie binarne kopie robocze.
- Limit jednego źródła wynosi 50 000 000 pikseli; przekroczenie jest stabilnym
  błędem zamiast niekontrolowanego użycia pamięci.

## Acceptance criteria

- [x] Osiem wartości EXIF Orientation daje oczekiwane wymiary i układ pikseli.
- [x] Brak EXIF daje kopię o niezmienionej orientacji i jawne `null`.
- [x] Oryginały mają identyczne SHA-256 przed i po normalizacji.
- [x] Kopie RGB PNG nie zawierają tagu EXIF Orientation.
- [x] Drugi przebieg zwraca te same ścieżki i checksumy bez nadpisywania.
- [x] Drift źródła i odmienny istniejący artefakt mają stabilne błędy.
- [x] Manifest oraz artefakty nie zawierają ścieżek absolutnych.
- [x] Rzeczywisty korpus 12 zdjęć przechodzi bez problemu.
- [x] Worker nie wykonuje połączeń sieciowych ani pobierania podczas przebiegu.
- [x] Testy, formatowanie, Ruff i mypy przechodzą.

## Expected files

- `services/worker/src/game_predictor_worker/images/normalization.py`
- `services/worker/tests/test_image_normalization.py`
- `scripts/normalize_m5_images.py`
- `ai_docs/quality/m5-normalization-report.json`
- `pyproject.toml`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe scripts/normalize_m5_images.py `
  examples\imgs ai_docs\quality\m5-source-discovery.json `
  --artifact-root artifacts\m5-normalization `
  --output ai_docs\quality\m5-normalization-report.json
.venv\Scripts\python.exe -m pytest `
  services/worker/tests/test_image_normalization.py -q
.venv\Scripts\python.exe -m ruff check `
  services/worker/src/game_predictor_worker/images `
  services/worker/tests/test_image_normalization.py scripts/normalize_m5_images.py
.venv\Scripts\python.exe -m mypy `
  services/worker/src/game_predictor_worker/images scripts/normalize_m5_images.py
```

## Risks

- Obecne 12 zdjęć nie zawiera tagu Orientation, dlatego poprawność wartości
  2–8 musi być udowodniona syntetycznymi golden fixtures.
- PNG będzie większy od JPEG, ale pozostaje lokalnym artefaktem roboczym i nie
  trafia do APK.
- Wynik kodowania jest przypięty do dokładnej wersji Pillow zapisanej w
  manifeście.

## Outcome

Zaimplementowano `image-normalization-v1` z Pillow 12.3.0. Adapter ponownie
weryfikuje discovery manifest i SHA-256 źródła, stosuje Orientation 1–8 przez
`ImageOps.exif_transpose`, tworzy czyste RGB PNG i zapisuje niezmienne artefakty
pod ścieżką zależną od checksumy. Każdy wynik ma osobną diagnostykę, a raport
nie zawiera ścieżek absolutnych.

Syntetyczne golden tests potwierdziły układ pikseli i wymiary dla wszystkich
ośmiu wartości Orientation, brak tagu, limit pikseli, drift źródła, blokadę
artefaktów wewnątrz katalogu źródłowego oraz kolizję bez nadpisania.

Rzeczywisty korpus:

- `12/12` obrazów znormalizowanych, `0` problemów,
- wszystkie źródła mają `exifOrientation = null`,
- wszystkie kopie mają `960 × 1280`, tryb RGB i brak Orientation,
- 12 PNG zajmuje `15 983 691` bajtów; wraz z diagnostyką powstały 24 lokalne
  pliki ignorowane przez Git,
- SHA-256 raportu:
  `7521e3dbee351918b0dca058905d640d518a2f0fee4ee9bed3a788c96f910352`,
- ponowny `--check` przeszedł bez driftu i bez nadpisywania,
- discovery oraz walidator korpusu ponownie potwierdziły oryginalne checksumy.

Weryfikacja: `25 passed`, Ruff bez błędów, mypy bez błędów dla 8 plików,
`pip check` bez konfliktów. Przebieg nie zawiera kodu sieciowego ani pobierania;
instalacja przypiętej zależności jest osobnym krokiem środowiskowym.
