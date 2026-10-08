# TASK-0930 — Klawisz `0` dla dziesiątego symbolu w weryfikacji symboli

## Status

`todo`

## Goal

W weryfikacji symboli klawisz `0` wybiera dziesiąty symbol gry (dla Mumii:
Mumia) jako „Symbol do zatwierdzenia”, a etykiety pokazują skrót `0`.

## Context

`DIGIT_SHORTCUT_LIMIT = 9` mapuje `1`–`9` na symbole 0–8 w kolejności
`display_order`. Mumia ma `display_order 9` i jako jedyna nie ma skrótu.
Plan: `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`, etap S-0.

## Dependencies / entry conditions

Brak. W wyszukiwaniu plansz `0` i `?` oznaczają „nieznany”
(`BOARD_SEARCH_UNKNOWN_SHORTCUT`) i pozostają bez zmian.

## Recommended execution

claude-sonnet-5-5 / medium. Mała zmiana TS z testem jednostkowym w dwóch
plikach. Eskalacja niepotrzebna. Audyt: gpt-6.1-sol / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` (sekcja weryfikacji symboli)

## Scope

- `apps/admin/src/lib/keyboard-shortcuts.ts`: nowa funkcja
  `extendedDigitShortcutIndex(key)` (`'1'`–`'9'` → 0–8, `'0'` → 9) i
  `extendedDigitShortcutLabel(index)` (0–8 → `1`–`9`, 9 → `0`); stałe
  `EXTENDED_DIGIT_SHORTCUT_LIMIT = 10`. Istniejące funkcje bez zmian.
- `apps/admin/src/features/symbol-reviews/symbol-review-keyboard.ts`: użycie
  wersji rozszerzonej; `SYMBOL_REVIEW_SHORTCUT_SYMBOL_LIMIT = 10`.
- `symbol-review-workspace.tsx`: etykiety w select i pasku skrótów
  (`shortcutSymbolsLabel`) pokazują `0 · Mumia`.

## Out of scope

- Wyszukiwanie plansz i `packages/board-search-ui`.
- Zmiana kolejności symboli.

## Acceptance criteria

- [ ] `0` w weryfikacji symboli wybiera dziesiąty aktywny symbol; przy mniej
      niż 10 symbolach `0` nic nie robi.
- [ ] Modyfikatory (Ctrl/Alt/Meta) i pola tekstowe nadal ignorują skróty.
- [ ] Etykiety w select i pasku skrótów zawierają `0` dla dziesiątego symbolu.
- [ ] Istniejące testy klawiatury przechodzą bez zmian zachowania dla `1`–`9`.

## Technical notes

Aktualne: `digitShortcutIndex('0') === null`. Wymagane: w kontekście
weryfikacji symboli `'0'` → 9. Pozostałe konteksty używają starej funkcji.

## Expected files

- Istniejące: `apps/admin/src/lib/keyboard-shortcuts.ts`,
  `apps/admin/src/features/symbol-reviews/symbol-review-keyboard.ts`,
  `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`,
  `apps/admin/test/symbol-review-keyboard.test.mjs`.

## Test cases

- 10 symboli, `key: '0'` → `{ kind: 'select_target', symbolId: symbols[9].id }`.
- 9 symboli, `key: '0'` → `null`.
- `key: '0', ctrlKey: true` → `null`.
- Etykieta indeksu 9 → `'0'`, indeksu 10 → `null`.

## Verification

```powershell
# katalog worktree, timeout 120 s każda
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
```

## Risks / open questions

- Brak.

## Outcome

Wypełnia agent po pracy.

### Changed

### Verification results

### Not completed

### Documentation updates

### Recommended next task
