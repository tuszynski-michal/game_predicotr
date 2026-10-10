# Audyt TASK-0930 — Klawisz `0` dla dziesiątego symbolu w weryfikacji symboli

Werdykt: REVISE
Audytor: gpt-6-astra, medium
Wykonawca: claude-sonnet-5-5, medium (według taska i planu)
Zakres: ad058e23~1...d39c5ab4e5883679190bf99b2cbe74aaff3385c6 oraz zmiany niezacommitowane w ścieżkach briefu, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Implementacja poprawnie rozszerza skróty weryfikacji symboli o `0`, zachowując dotychczasowe mapowanie `1`–`9` i obsługę pól tekstowych oraz modyfikatorów. Etykiety korzystają ze wspólnego helpera, a wyszukiwarka plansz zachowuje znaczenie `0` jako symbolu nieznanego. Wykryto brak wymaganego zapisu wersji i hasha commita w dokumentacji ukończenia taska.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `ai_docs/tasks/completed/0930-symbol-review-zero-shortcut.md:90` oraz `ai_docs/process/CURRENT_STATE.md:112` — sekcja `Outcome` i wpis stanu zadania nie zawierają wersji ani hasha commita, wymaganych przez przekazane zasady `AGENTS.md`. Task ma status `done`, a historia potwierdza osobny commit `v1.7.266`, `ad058e23a487a70f543636c6b024d779006c9bdb`. Brak zapisu uniemożliwia potwierdzenie punktu kontynuacji bez odtwarzania historii. Uzupełnić oba miejsca o tę wersję i pełny hash.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| `0` wybiera dziesiąty aktywny symbol; poniżej 10 symboli nic nie robi | spełnione | `apps/admin/src/lib/keyboard-shortcuts.ts:31`; `apps/admin/src/features/symbol-reviews/symbol-review-keyboard.ts:35`; filtrowanie i kolejność: `apps/admin/src/features/symbol-reviews/symbol-review-actions.ts:252` |
| Ctrl/Alt/Meta i pola tekstowe nadal ignorują skróty | spełnione | `apps/admin/src/features/symbol-reviews/symbol-review-keyboard.ts:32`; `apps/admin/src/lib/keyboard-shortcuts.ts:17`; `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx:1313` |
| Select i pasek skrótów pokazują `0` dla dziesiątego symbolu | spełnione | `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx:2138`, `:2333`, `:2398`; `apps/admin/src/lib/keyboard-shortcuts.ts:37` |
| Istniejące testy przechodzą bez zmiany zachowania `1`–`9` | niezweryfikowane | Delegowanie do starego helpera zachowuje mapowanie: `apps/admin/src/lib/keyboard-shortcuts.ts:33`. Testy pozostają w `apps/admin/test/symbol-review-keyboard.test.mjs:26`. Wynik 668 PASS pochodzi wyłącznie z deklaracji wykonawcy. |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1.

## Proponowane testy

- Dla większej pewności granicy rozszerzyć `apps/admin/test/symbol-review-keyboard.test.mjs:78` o dokładnie 10 symboli (`symbols.slice(0, 10)`); obecny przypadek dodatni używa 11. Komenda: `node --experimental-strip-types --test apps/admin/test/symbol-review-keyboard.test.mjs`.

## Zakres przeglądu i ograniczenia

Sprawdzono brief, task, właściwe fragmenty wymagań, architektury, planu S-0 i dokumentacji procesu. Porównano diff z aktualnymi plikami, prześledzono ładowanie aktywnych symboli, obsługę klawiatury, generowanie etykiet i zawartość testów.

HEAD odpowiada briefowi. W ścieżkach objętych audytem nie ma zmian niezacommitowanych; pozostałe zmiany worktree pozostawiono poza zakresem.

Nie uruchamiano testów, lintowania, kontroli typów ani przeglądarki. Wyniki zapisane w `Outcome` nie zostały niezależnie potwierdzone.