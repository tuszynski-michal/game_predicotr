# TASK-0657 — skróty klawiszowe w palecie „Wyszukaj plansze”

## Status

`done`

## Goal

Operator wprowadza wzór w „Wyszukaj plansze” (Zarządzanie grami) z
klawiatury, bez klikania palety symboli.

## Context

Zgłoszenie użytkownika (2026-09-25) po TASK-0656: te same skróty cyfrowe co
w „Weryfikacji symboli” mają działać przy wyborze symboli w wyszukiwarce.

## Dependencies / entry conditions

TASK-0656 (skróty w Weryfikacji symboli). Bez zmian API.

## Recommended execution

Zadanie zgłoszone bezpośrednio w rozmowie, poza planem; wykonane przez
Claude Opus 5.5 (reasoning domyślny sesji).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` — „Wyszukiwanie plansz z niepełnym wzorem”

## Scope

- `1`–`9` → wstaw aktywny symbol nr N (kolejność `displayOrder`, jak w
  palecie i w „Zarządzaniu grami → Symbole”); `0`/`?` → nieznany `?`;
  `Backspace` → `Cofnij`; `Enter` → `Szukaj plansz`.
- Numer skrótu jako znaczek na przycisku palety + legenda w nagłówku palety.
- Wspólne helpery `apps/admin/src/lib/keyboard-shortcuts.ts`;
  `symbol-review-keyboard.ts` korzysta z nich (API modułu bez zmian).

## Out of scope

- Nawigacja strzałkami po polach wzoru, zmiana API.

## Acceptance criteria

- [x] Cyfry wstawiają symbole w kolejności katalogu i przechodzą do kolejnego pola.
- [x] Pisanie w „Liczba wyników” nie wstawia symboli.
- [x] `Enter` na kontrolce poza edytorem (np. wyniki) zachowuje natywne działanie.
- [x] Istniejące testy interakcji bez zmian (`title` przycisku = nazwa symbolu).

## Expected files

- `apps/admin/src/lib/keyboard-shortcuts.ts` (nowy)
- `apps/admin/src/features/board-search/board-search-keyboard.ts` (nowy)
- `apps/admin/src/features/board-search/board-search-workspace.tsx`
- `apps/admin/src/features/symbol-reviews/symbol-review-keyboard.ts`
- `apps/admin/src/app/globals.css`
- `apps/admin/test/board-search-keyboard.test.mjs` (nowy)
- `apps/admin/test-interactions/board-search-keyboard.test.mjs` (nowy)

## Verification

```powershell
npm run test --workspace @game-predictor/admin          # 602/602
npm run test:geometry --workspace @game-predictor/admin # 42/42
npm run typecheck --workspace @game-predictor/admin     # czysto
npm run lint --workspace @game-predictor/admin          # 0 błędów, 4 istniejące ostrzeżenia
```

## Risks / open questions

- Brak odbioru na żywym Adminie.
- `Backspace` poza polem tekstowym cofa edycję wzoru w całej zakładce
  (także gdy fokus jest w wynikach) — celowo, bo przeglądarki nie używają już
  `Backspace` do nawigacji wstecz.

## Outcome

Zaimplementowano zgodnie z zakresem; testy, typecheck i lint Admina zielone.
