---
title: Crop eligibility and crop plan compared with the P1 selection
status: active
last_updated: 2026-10-17
---

# Kwalifikacja i plan kadru wobec próbki P1 (TASK-1044)

Porównanie reguł TASK-1043/1044 z zamrożoną próbką P1
([raport P1](PHOTO_CROP_PREVIEW_20261014.md)). Wejście wyłącznie z artefaktów
`D:/game_predicotr/artifacts/photo-crop-preview-20261014/`: `manifest.json`
(40 źródeł, 360 plansz, odczyt READ ONLY z 2026-10-14), `lossless/lossless_report.json`
(pomiar `jpegtran`) i kopie oryginałów z galerii. Bez dostępu do bazy operatora.
Skrypt: `compare_p1_eligibility.py`, wynik: `lossless/p1_eligibility_comparison.json`.

## Wynik

| Kontrola | Wynik |
|---|---:|
| Źródła | 40 |
| Ścieżka `data/originals/<sha[:2]>/<sha>.jpg` (`UNMANAGED_PATH`) | 40/40 zgodne |
| `coordinate_space = exif-normalized-rgb-pixels-v1` | 40/40 |
| Wszystkie plansze z zatwierdzoną bieżącą rewizją | 40/40 |
| Plansze bez quadów (`BOARD_GEOMETRY_MISSING`) | 0 źródeł |
| Plan kadru R6 (`plan_source_crop`, iMCU z pliku) równy zmierzonemu kadrowi bezstratnemu | 40/40 |
| Plan kadru zawiera ramkę P1 (`bbox` z marginesem) | 40/40 |

P1 pominęło grę „777 a2” (brak źródeł z zatwierdzoną geometrią wszystkich
siatek). Nowe reguły dają w takim przypadku `GEOMETRY_NOT_APPROVED`, więc
wynik dla tej gry jest zgodny.

## Warunki nieocenione z artefaktów

Manifest P1 nie zawiera tych faktów, więc źródła **nie** są dla nich uznane za
kwalifikujące się: `IMPORT_NOT_COMPLETED`, `GAME_STORAGE_NOT_ACTIVE`,
`ACTIVE_IMAGE_JOB`, `PENDING_GRID_PROPOSAL`, `PAGE_SOURCE_EXCLUDED`. Ocena tych
warunków wymaga odczytu bazy operatora i należy do pilotażu TASK-1050, za
osobną zgodą.

## Różnice reguł względem kolektora P1

- `SOURCE_REVISION_NOT_ACCEPTED` wymaga `accepted`. P1 odrzucało statusy
  `pending`, `needs_review`, `rejected` i `reverted`, czyli przy pięciu
  statusach CHECK warunek jest równoważny.
- Kontrola quadów działa per plansza (`BOARD_GEOMETRY_MISSING`). P1 odrzucało
  źródło, gdy którakolwiek plansza nie miała quadów, więc reguła jest równoważna.
- Zbiór kluczy quadów jest kluczami P1 plus `sequenceLabelQuad` i `corners`.
  Na danych P1 kadr wynikowy jest identyczny (40/40).
- Reguły nowe i surowsze: import zakończony, partycja gry aktywna, brak
  aktywnego joba obrazu w grze, brak oczekującej propozycji siatki, brak
  wykluczenia strony, zgodna tożsamość obrazu wszystkich źródeł bloba.
