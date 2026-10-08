# TASK-0932 — Ewaluator `payout-v4-wild-count`

## Status

`todo`

## Goal

Dla gry z symbolem uruchamiającym supergrę kalkulator liczy wygraną jako
linie (Wild podmienia per linia) plus wypłatę za liczbę sztuk symbolu
uruchamiającego na planszy; dla gier bez takiego symbolu wyniki są identyczne
z `payout-v3-unknown-prefix-stop`.

## Context

Po TASK-0931 Mumia może być Wild i symbolem uruchamiającym, ale ewaluator
nadal traktuje ją jak zwykły symbol liniowy. Plan: etap S-A. Po tym zadaniu
operator włącza Wild i testuje w modalu linii.

## Dependencies / entry conditions

- TASK-0931 zacommitowany i zaudytowany (role w domenie i API).
- Fakt: ewaluator w `services/worker/src/game_predictor_worker/domain/payout.py`
  jest współdzielony przez API (`PreparedPayoutEvaluator`); TS odpowiednik w
  `packages/shared-ts/src/validation.ts`; złote przypadki w
  `packages/domain-fixtures/payout-golden-cases.json` wykonują oba języki.

## Recommended execution

gpt-6.1-sol / high. Ewaluator w Pythonie i TS, złote przypadki, regresja 777.
Eskalacja do gpt-6-astra / high przy rozbieżności wyników Python/TS. Audyt:
claude-opus-5-5 / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/requirements/ALGORITHMS.md` (§B, §D)
- `ai_docs/architecture/DATA_MODEL.md` (wersjonowanie algorytmu)

## Scope

- `payout.py`: symbole z `super_game_trigger_count` wyłączone z
  `_ordinary_symbols_by_display_order`; Wild bez zmian; nowy rodzaj
  dopasowania `count` (symbol, liczba sztuk, komórki, kredyty) z reguł
  symbolu uruchamiającego; `total = linie + count`. Nieznane komórki (`0`)
  nie liczą się jako sztuki (dolne ograniczenie zachowane).
- Wersja algorytmu `payout-v4-wild-count` wybierana per gra: gra bez symbolu
  uruchamiającego używa `v3` bez zmian (identyczne wyniki i audyt).
- Kontrakty (`PayoutMatch`/`PayoutEvaluation`): pole `match_kind`
  (`line` | `count`) z domyślną wartością `line`, zgodność wstecz raportów.
- `packages/shared-ts/src/validation.ts` i kalkulator TS: ta sama reguła;
  złote przypadki w `payout-golden-cases.json`.
- Admin: modal linii pokazuje wiersz „Mumia ×3 (sztuki na planszy) → 20”;
  przybliżona wygrana używa nowej wersji dla gier ze symbolem uruchamiającym.
- `ALGORITHMS.md` §B: opis `payout-v4-wild-count`; „Joker” → „Wild”.

## Out of scope

- Rozwinięcie super symbolu i koszt per pozycja (TASK-0936).
- Serie (TASK-0933). Aplikacja mobilna.

## Acceptance criteria

- [ ] Złote przypadki: Wild jako dwa różne symbole na dwóch liniach; sztuki
      3/4/5; sztuki + linie na jednej planszy; same Wildy bez wygranej;
      nieznana komórka nie liczy się jako sztuka; plansza bez symbolu
      uruchamiającego identyczna z v3.
- [ ] Wszystkie istniejące złote przypadki 777 bez zmian wyników.
- [ ] Python i TS dają identyczne wyniki na wszystkich przypadkach.
- [ ] Modal linii i przybliżona wygrana pokazują wypłatę za sztuki.

## Technical notes

Wejście → wynik (Mumie, Mumia = Wild + trigger 3, reguły Mumii 3→20):
`[10, Mumia, 10, 10, J / K, K, Mumia, Q, Q / Mumia, A, A, A, 10]` →
linia A: `10 ×4` (Mumia jako 10); linia B: `K ×3` (Mumia jako K);
linia C: brak (prefiks A nie zaczyna się w kolumnie 1; Mumia sama nie liczy
się jako ciąg); sztuki Mumii = 3 → 20; suma = payout(10,4) + payout(K,3) + 20.

## Expected files

- Istniejące: `services/worker/src/game_predictor_worker/domain/payout.py`,
  `domain/contracts.py`, `domain/validation.py`,
  `services/worker/tests/test_payout.py`, `test_payout_batch.py`,
  `packages/shared-ts/src/validation.ts`, `packages/shared-ts/src/contracts.ts`,
  `packages/domain-fixtures/payout-golden-cases.json`,
  `services/api/src/game_predictor_api/domain/board_search_board_detail.py`,
  `packages/board-search-ui/src/board-search-board-lines-modal.tsx`,
  `ai_docs/requirements/ALGORITHMS.md`.

## Test cases

- Jak w kryteriach akceptacji; dodatkowo: symbol uruchamiający bez reguł
  → brak wypłaty za sztuki, brak błędu; sztuki = 2 przy regule od 3 → 0.

## Verification

```powershell
# katalog worktree, timeout 120 s każda
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_payout.py services/worker/tests/test_payout_batch.py -q
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_board_detail_api.py services/api/tests/test_board_search_approximate_win_domain.py -q
npm run test --workspace @game-predictor/shared-ts
npm run test --workspace @game-predictor/board-search-ui
npm run quality
```

## Risks / open questions

- Raporty wydania 777 muszą odtwarzać `v3`; nowa wersja nie może zmienić
  `algorithm_version` gier bez symbolu uruchamiającego.

## Outcome

Wypełnia agent po pracy.

### Changed

### Verification results

### Not completed

### Documentation updates

### Recommended next task
