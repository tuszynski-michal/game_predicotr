---
title: TASK-0930 — audyt niezależny (claude-opus-5-5 / medium)
status: accepted
last_updated: 2026-10-08
---

# TASK-0930 — audyt: klawisz `0` w weryfikacji symboli

Audytor: niezależny subagent claude-opus-5-5 / medium, świeży kontekst, tylko
odczyt (zamiennik audytu Codex do czasu dostępności CLI, D-535). Zakres:
diff plików zadania względem v1.7.264 w worktree `mumie-super-game`.

## Werdykt

PASS. Brak P0 i P1. Cztery znaleziska P2, wszystkie obsłużone przed commitem
(poniżej).

## Znaleziska

1. [P2] Dwa zmienione pliki nie przechodziły Prettiera
   (`symbol-review-keyboard.ts:15`, `symbol-review-workspace.tsx:2398-2401`).
   Naprawione: `npx prettier --write` na czterech plikach zadania.
2. [P2] Opis w `apps/admin/src/features/symbols/symbol-catalog.tsx:684` nadal
   mówi o skrótach `1–9` w weryfikacji symboli. Przekazane do TASK-0931, który
   edytuje ten plik równolegle.
3. [P2] Outcome podawał „Brak” w aktualizacjach dokumentacji mimo zmiany w
   `ADMIN_APP.md`; status i kryteria niezaktualizowane. Naprawione.
4. [P2] Komentarz modułu z podwójnym „so” i za długą linią. Naprawione.

## Sprawdzone bez uwag

- `0` przy ≥10 symbolach wybiera `symbols[9]`, przy 9 zwraca `null`; testy
  obejmują oba przypadki oraz Ctrl/Alt/Meta i pola tekstowe.
- `1`–`9` bez zmian (delegacja do `digitShortcutIndex`); mapowanie
  indeks→etykieta bez przesunięcia (0→`1`, 8→`9`, 9→`0`, 10→`null`).
- Select i pasek skrótów używają tej samej funkcji etykiety; żaden test
  kontraktu renderu nie asertuje tekstu paska.
- `packages/board-search-ui` nietknięty: `0` nadal oznacza „nieznany”.
- `ADMIN_APP.md` (akapit skrótów weryfikacji) spójny z kodem.

## Testy uruchomione przez audytora

- `npm run test --workspace @game-predictor/admin`: 668 pass, 0 fail.
- `npm run typecheck --workspace @game-predictor/admin`: bez błędów.
- Prettier na zmienionych plikach (treść znormalizowana do LF): różnice w
  dwóch plikach, naprawione po audycie.

Przegląd statyczny, bez zmian plików przez audytora.
