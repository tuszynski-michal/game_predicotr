# TASK-0935 — Oznaczenie supergry w wyszukiwaniu plansz

## Status

`todo`

## Goal

Wyniki wyszukiwania plansz i wiersze przybliżonej wygranej pokazują złote
oznaczenie serii supergry (trigger, pozycja w serii, super symbol lub „do
zdefiniowania”) z linkiem do widoku serii w Adminie.

## Context

Operator chce widzieć wygrane supergry w wyszukiwaniu plansz i wchodzić z
nich w definicję super symbolu. Plan: etap S-B.

## Dependencies / entry conditions

- TASK-0933 (serie) i TASK-0934 (widok serii) zacommitowane.
- Fakt: `packages/board-search-ui` jest współdzielony przez Admin, Reviewer i
  publiczny panel zarządzania; projekcja wyników pochodzi z API wyszukiwania.

## Recommended execution

claude-sonnet-5-5 / high. Znacznik w projekcji API i współdzielonym UI,
trzech konsumentów. Eskalacja do claude-opus-5-5 / high przy zmianie
kontraktu publicznego panelu. Audyt: gpt-6.1-sol / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/requirements/ADMIN_APP.md` (wyszukiwanie plansz)
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- API: odpowiedź wyniku wyszukiwania i wiersza przybliżonej wygranej
  dostaje opcjonalne `superGame`: `{ kind: 'trigger' | 'in_series',
  seriesId, spinIndex, seriesLength, superSymbolCode | null,
  completeness, runVerification, stale }`; brak pola = tryb bazowy; `stale`
  pochodzi z `super_game_derivation_state.is_stale` i oznacza, że serie są
  w trakcie przeliczania (ostrzeżenie w UI, bez blokady). Publiczny panel: to samo pole,
  bez `seriesId`.
- UI (`board-search-ui`): złote wyróżnienie karty wyniku i wiersza; etykieta
  „Supergra: spin 3/10, symbol K” lub „Supergra: super symbol do
  zdefiniowania”; w Adminie link „Zdefiniuj super symbol” do TASK-0934;
  Reviewer i panel tylko etykieta.
- Testy: stan wyników, kontrakt renderu, request testy API.

## Out of scope

- Zmiana wypłat (TASK-0936); wartości nadal z aktualnego ewaluatora.

## Acceptance criteria

- [ ] Plansza wyzwalająca i plansze serii mają oznaczenie w wynikach i w
      wierszach przybliżonej wygranej.
- [ ] Link prowadzi do właściwej serii; w Reviewerze i panelu brak linku.
- [ ] Gra `none` nie ma pola i oznaczeń; testy istniejące bez zmian.

## Technical notes

- Źródło: tabela `super_game_series`; dołączenie po `sequence_number` w
  zakresie serii; indeks na `(game_id, start_sequence_number)`.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/domain/board_search.py`,
  `board_search_approximate_win.py`, schematy wyszukiwania,
  `packages/board-search-ui/src/board-search-results.tsx`,
  `board-search-approximate-win.tsx`, `board-search.css`, testy pakietu,
  `apps/reviewer` (proxy allowlist bez zmian, jeśli pole jest w istniejących
  odpowiedziach).

## Test cases

- Wynik na pozycji 105 w serii 101–120 → `in_series`, `spinIndex 5`.
- Pozycja 100 (trigger) → `trigger`.
- Seria bez symbolu → `superSymbolCode null`, etykieta „do zdefiniowania”.

## Verification

```powershell
# katalog worktree, timeout 120 s każda
.\.venv\Scripts\python.exe -m pytest services/api/tests -k "board_search" -q
npm run test --workspace @game-predictor/board-search-ui
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run test --workspace @game-predictor/reviewer
npm run openapi:check
```

## Risks / open questions

- Złoty kolor musi być czytelny obok istniejących wyróżnień jokera/wilda w
  modalu linii.

## Outcome

Wypełnia agent po pracy.

### Changed

### Verification results

### Not completed

### Documentation updates

### Recommended next task
