---
title: TASK-0774 — Jednostka w etykietach punktów wykresu bilansu
status: done
last_updated: 2026-09-30
---

# TASK-0774 — Jednostka w etykietach punktów wykresu bilansu

## Status

`done`

## Goal

Etykieta punktu na wykresie „Bilans według liczby spinów” (najechanie i
przypięcie) oraz lista przypiętych punktów podają jednostkę kwoty: „zł” dla
złotych, „kredytów” dla kredytów.

## Context

Zgłoszenie operatora z 2026-09-30: przypięta etykieta pokazywała
„Bilans: 450” bez informacji, czego dotyczy. TASK-0761 celowo usuwał „zł” z
etykiety (jednostkę nazywała oś), a kredyty były zawsze gołą liczbą.

## Dependencies / entry conditions

- TASK-0761, TASK-0762, TASK-0765 done.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Audyt: niezależny agent `claude-opus-5-5`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`

## Scope

- `packages/board-search-ui/src/board-search-approximate-win.tsx`: kwota w
  etykiecie, opisie dostępności i liście przypiętych punktów to ta sama
  kwota co w tabeli z jednostką (`45,00 zł` albo `450 kredytów`).
- Szerokość etykiety 124 → 172 jednostek SVG, aby zmieścić
  „Bilans: -123 456,5 kredytów”, i 4 zamiast 3 wierszy etykiet (pas nad
  wykresem wyższy o 34 jednostki), aby osiem przypięć i etykieta najechania
  się nie nakładały. Geometria etykiet jest eksportowana z
  `board-search-approximate-win-state.ts` i testowana w układzie.

## Out of scope

- Zmiana formatu kwot w tabeli, metrykach i osi.

## Acceptance criteria

- [x] Etykieta i lista przypiętych punktów kończą się „kredytów” w trybie
  kredytów i „zł” w trybie złotych.
- [x] Etykiety się nie nakładają (układ używa nowej szerokości).

## Outcome

### Changed

- Etykieta punktu, opis `aria-label` przycisku odpinania i lista przypiętych
  punktów używają jednej funkcji `labelAmount` z jednostką.
- `APPROXIMATE_WIN_CHART_LABEL` (szerokość 172, 4 wiersze) i
  `APPROXIMATE_WIN_CHART_LABEL_LAYOUT` w module stanu; testy układu używają
  prawdziwej geometrii (przypadek regresji i 3000 losowych zestawów ośmiu
  przypięć z etykietą najechania).

### Verification results

- Pakiet: testy 74/74, interakcje 33/33 (dokładne etykiety przy stawce
  6 zł: „Bilans: 2700 kredytów”, „Bilans: 270,00 zł”; lista przypiętych z
  „kredytów”), typecheck i lint czyste; typecheck Admina czysty.
- Audyt niezależnego agenta `claude-opus-5-5`: cykl 1 FAIL — P2 przy 3
  wierszach i szerokości 172 etykiety mogły się nakładać (68/100 000
  losowych zestawów ośmiu przypięć), testy układu używały starej szerokości;
  P3 brak dokładnych wartości w teście, limit siedmiocyfrowego salda.
  Poprawki naniesione. Cykl 2 PASS; P3 (rzadkie nałożenie etykiety
  najechania na przypięcie przy dwóch pełnych skupiskach, precyzja generatora
  w teście) — komentarz doprecyzowany, generator poprawiony.
- Ręcznie na `127.0.0.1:3010`: „Bilans: -50 075 kredytów” i
  „Bilans: -5007,50 zł” mieszczą się w etykiecie.
