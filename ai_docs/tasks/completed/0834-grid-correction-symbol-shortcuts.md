---
title: Skróty klawiszowe symboli w korekcie cięcia siatki
status: done
last_updated: 2026-10-04
---

# TASK-0834 — Skróty klawiszowe symboli w korekcie cięcia siatki

## Status

`done`

## Goal

W ekranie „Korekta cięcia siatki” symbol zaznaczonego pola można wybrać tym
samym klawiszem, który wybiera ten symbol w pozostałych ekranach Reviewera.

## Context

TASK-0822 dał paletę symboli pod podglądem cropów, ale tylko do klikania.
Weryfikacja symboli przypisuje klawisze 1–9, 0, a potem litery, według
kolejności katalogu gry (`buildOperationalReviewSymbolShortcuts`). Zgłoszenie
operatora z 2026-10-04: te same skróty mają działać w korekcie siatki.

## Scope

- Paleta dostaje klawisze z istniejącej mapy `buildOperationalReviewSymbolShortcuts`
  (żadnej nowej tabeli skrótów); przycisk pokazuje klawisz (`<kbd>`) i ma
  `aria-keyshortcuts`.
- Klawisz ustawia symbol zaznaczonego pola, gdy podgląd jest aktualny, pole
  zaznaczone i nie trwa zapis. Bez zaznaczonego pola klawisz nic nie robi.
- Ignorowane są powtórzenia, kombinacje z Ctrl/Alt/Meta oraz pola tekstowe,
  listy wyboru i textarea; pola wyboru (checkbox) nie blokują skrótów.

## Out of scope

- Skrót dla „? Nie wiem” i „Usuń wybór”; automatyczne przejście do następnego pola.

## Acceptance criteria

- [x] Siódemka, arbuz, śliwka i wiśnia dostają klawisze wg kolejności katalogu
  (jak w Weryfikacji symboli); klawisz jest widoczny na przycisku palety.
- [x] Klawisz zmienia symbol zaznaczonego pola; zapis wysyła ten wybór w `cellSymbols`.
- [x] Klawisz z Ctrl lub nieprzypisany nie zmienia wyboru.

## Verification

```powershell
cd apps/reviewer
npx tsx --test test-interactions/board-geometry-correction.test.mjs   # 9/9
npx tsc --noEmit
npx eslint src/features/operational-reviews test-interactions
```

## Outcome

### Changed

- `board-geometry-correction-workspace.tsx` (klucz skrótu z
  `buildOperationalReviewSymbolShortcuts`), `deferred-board-cell-geometry-editor.tsx`
  (`CorrectionSymbol.shortcut`, obsługa klawiszy, `<kbd>` na palecie),
  `apps/admin/src/app/globals.css` (styl `kbd` palety), test interakcji
  (nowy test klawiszy; pozostałe dostosowane do `<kbd>`).

### Verification results

- Interakcje geometrii 9/9, typecheck i lint Reviewera czyste.
- Reviewer przebudowany (`reviewer:build`) i zrestartowany na 3001.

### Not completed

- Brak odbioru na żywo przez operatora.
