# TASK-0930 — Klawisz `0` dla dziesiątego symbolu w weryfikacji symboli

## Status

`done`

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
plikach. Eskalacja niepotrzebna. Audyt: gpt-6.1-sol / high; do czasu CLI zamiennik claude-opus-5-5 / medium.

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

- [x] `0` w weryfikacji symboli wybiera dziesiąty aktywny symbol; przy mniej
      niż 10 symbolach `0` nic nie robi.
- [x] Modyfikatory (Ctrl/Alt/Meta) i pola tekstowe nadal ignorują skróty.
- [x] Etykiety w select i pasku skrótów zawierają `0` dla dziesiątego symbolu.
- [x] Istniejące testy klawiatury przechodzą bez zmian zachowania dla `1`–`9`.

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

### Changed

- Commit v1.7.266 / ad058e23a487a70f543636c6b024d779006c9bdb (zapis dodany po commicie przez leada).

- `apps/admin/src/lib/keyboard-shortcuts.ts`: dodano `EXTENDED_DIGIT_SHORTCUT_LIMIT = 10`, `extendedDigitShortcutIndex` (`1`-`9` na 0-8, `0` na 9) i `extendedDigitShortcutLabel` (0-8 na `1`-`9`, 9 na `0`). Istniejące eksporty bez zmian.
- `apps/admin/src/features/symbol-reviews/symbol-review-keyboard.ts`: użycie wersji rozszerzonych, `SYMBOL_REVIEW_SHORTCUT_SYMBOL_LIMIT` równe 10.
- `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`: tekst paska skrótów wspomina `0` (dziesiąty symbol). Etykiety w select i `shortcutSymbolsLabel` dostają `0` automatycznie przez `symbolReviewShortcutLabel`.
- `apps/admin/test/symbol-review-keyboard.test.mjs`: testy dla `0` (10 symboli, 9 symboli, Ctrl) oraz etykiet 9 i 10; usunięto stare założenie, że `0` jest ignorowane.
- `packages/board-search-ui` nie zmieniono (tam `0` oznacza „nieznany”).

### Verification results

- `npm run test --workspace @game-predictor/admin`: 668 pass, 0 fail.
- `npm run typecheck --workspace @game-predictor/admin`: bez błędów.
- `npm run lint --workspace @game-predictor/admin`: 0 błędów, 5 ostrzeżeń istniejących wcześniej w plikach spoza zakresu (board-search-share-corrections, image-folder-import-panel, page-geometry-correction-panel).

### Not completed

Brak. Nie uruchamiano testu wizualnego w przeglądarce.

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md` (sekcja weryfikacji symboli, akapit o skrótach): dodano `0` dla dziesiątego symbolu z odwołaniem do TASK-0930.
- Audyt niezależny (claude-opus-5-5 / medium, tylko odczyt): PASS, cztery znaleziska P2; raport `ai_docs/quality/TASK-0930_AUDIT_claude-opus-5-5.md`. Poprawione przed commitem: formatowanie Prettier dwóch plików, komentarz modułu, ten Outcome i status. Znalezisko o opisie w `apps/admin/src/features/symbols/symbol-catalog.tsx:684` („skróty 1–9 w weryfikacji symboli”) przekazane do TASK-0931, który edytuje ten plik.

### Recommended next task

TASK-0931 (etap S-A), w toku równolegle; uzupełnić tam opis skrótów w `symbol-catalog.tsx`.
