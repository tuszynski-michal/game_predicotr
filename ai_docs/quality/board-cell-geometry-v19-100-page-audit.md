---
title: Board cell geometry v19 — 100-page manual audit
status: accepted
last_updated: 2026-08-20
---

# Board cell geometry v19 — audyt 100 stron

## Zakres i proweniencja

- manifest geometrii stron:
  `61e8c5b2ec489aa8c18f4d7ec57008d90b9305a50092feb78c5a9a23932e6cf4`,
- liczba dostępnych zarejestrowanych stron: `2194`,
- polityka próbki: `sha256-ranked-registered-pages-v1`,
- seed: `task-0249-v19-pre-editor-audit-v1`,
- próbka: `100` stron i `900` plansz,
- estymator: `board-cell-geometry-v19-multi-point-source-direct-v1`,
- wynikowy raport:
  `320c9b1089b1481e8e4eea71c955eaf796c61554391783d2ac34020aa2421691`,
- lokalny raport i nakładki:
  `artifacts/task-0249-board-cell-geometry-audit-v1/`.

Raport nie zawiera bezwzględnej ścieżki folderu źródłowego. Każdy JPEG został
odczytany po bezpiecznej ścieżce względnej i zweryfikowany względem checksumy z
manifestu przed estymacją.

## Odtworzenie

```powershell
.\.venv\Scripts\python.exe scripts\audit_board_cell_geometry_v19.py `
  --page-geometry-manifest artifacts\data\page-geometry-manifests\61e8c5b2ec489aa8c18f4d7ec57008d90b9305a50092feb78c5a9a23932e6cf4.json `
  --source-root "C:\Users\user\Documents\777" `
  --output-root artifacts\task-0249-board-cell-geometry-audit-v1 `
  --sample-size 100
```

Dwa pełne przebiegi zwróciły tę samą checksumę raportu. Drugi przebieg trwał
`31,81 s` i utworzył 100 pełnowymiarowych nakładek oraz 25 arkuszy audytowych.

## Wynik automatyczny

| Wynik | Liczba |
|---|---:|
| geometria wyestymowana | 888 |
| kontrolowany `needs_review` | 12 |
| fałszywy sukces wykryty ręcznie | 0 |
| przesunięcie o wiersz lub kolumnę | 0 |
| symbol poza wyestymowaną komórką | 0 |

Fallbacki nie zawierają `latticeBoundsQuad`, komórek ani evidence produkcyjnego:

| Sekwencja | Powód |
|---:|---|
| 1021 | `BOARD_CELL_GEOMETRY_AXIS_ASSIGNMENT_FAILED` |
| 1030 | `SYMBOL_LATTICE_INLIER_COVERAGE_INSUFFICIENT` |
| 1534 | `SYMBOL_LATTICE_INLIER_COVERAGE_INSUFFICIENT` |
| 3478 | `BOARD_CELL_GEOMETRY_AXIS_ASSIGNMENT_FAILED` |
| 5925 | `BOARD_CELL_GEOMETRY_AXIS_ASSIGNMENT_FAILED` |
| 5928 | `BOARD_CELL_GEOMETRY_AXIS_ASSIGNMENT_FAILED` |
| 6277 | `SYMBOL_LATTICE_INLIER_COVERAGE_INSUFFICIENT` |
| 9532 | `SYMBOL_LATTICE_INLIER_COVERAGE_INSUFFICIENT` |
| 11137 | `BOARD_CELL_GEOMETRY_INSUFFICIENT_GLOBAL_ASSIGNMENTS` |
| 15637 | `BOARD_CELL_GEOMETRY_INSUFFICIENT_GLOBAL_ASSIGNMENTS` |
| 16521 | `SYMBOL_LATTICE_INLIER_COVERAGE_INSUFFICIENT` |
| 18625 | `SYMBOL_LATTICE_INLIER_COVERAGE_INSUFFICIENT` |

## Audyt ręczny

Sprawdzono wszystkie 25 arkuszy, po cztery strony na arkusz. Zielone granice
każdej z 15 komórek porównano z widocznymi symbolami. Czerwone plansze
sprawdzono jako kontrolowane odrzucenia bez wyemitowanych komórek.

Checkpoint bezpieczeństwa jest zaliczony: estymator nie wygenerował błędnej
geometrii w próbce 100 stron. Pokrycie automatyczne wynosi `98,67%`; 12 plansz
pozostaje prawidłowo skierowanych do przyszłej ręcznej korekty. Audyt dotyczy
source-space quadów przed implementacją rasteryzacji. Nie aktywuje estymatora,
nie tworzy cropów i nie zmienia produkcyjnego croppera v18.
