---
title: TASK-0746 — T5 — Admin: filtr źródła predykcji i zakresu dat zmiany w weryfikacji symboli
status: done
last_updated: 2026-09-30
---

# TASK-0746 — T5 — Admin: filtr źródła predykcji i zakresu dat zmiany w weryfikacji symboli

## Status

`done`

## Goal

Operator w `Weryfikacja symboli` wybiera źródło predykcji (wszystkie / nowy
algorytm / stary model) i zakres daty zmiany komórki (od–do); filtry działają
z paginacją, przeskokiem stron, licznikami i operacjami masowymi.

## Context

D-466, pytanie 1: „oba — ten po dacie jako range picker”. API z TASK-0745.

## Dependencies / entry conditions

- TASK-0745 done (parametry `predictionSource`, `changedFrom`, `changedTo`).

## Recommended execution

`claude-opus-5-5`, reasoning `medium` (warunkowo). Audyt: `claude-fable-5-1`,
reasoning `medium` na polecenie operatora (poziomu nie da się ustawić z
sesji; rekomendacja warunkowa), osobny agent.

## Relevant docs

- `ai_docs/delivery/SYMBOL_REFERENCE_LIBRARY_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-466)

## Scope

- `symbol-review-state.ts`: pola filtra `predictionSource`, `changedFrom`,
  `changedTo`; konwersja `datetime-local` ↔ ISO, walidacja zakresu.
- `symbol-review-actions.ts`, `symbol-review-selection-state.ts`,
  `symbol-review-bulk-actions.ts`: przekazanie filtrów do listy, przeskoku,
  liczników i wyboru filtra operacji masowej.
- `symbol-review-workspace.tsx` i CSS: dwie nowe grupy filtrów.

## Out of scope

- Zmiany API (TASK-0745), reviewer.

## Acceptance criteria

- [x] Grupa „Źródło predykcji”: Wszystkie / Nowy algorytm (biblioteka
  wzorców) / Stary model.
- [x] Grupa „Data zmiany komórki”: pola Od i Do (`datetime-local`, czas
  lokalny), przyciski „Od dziś 00:00”, „Zastosuj zakres”, „Wyczyść”;
  koniec zakresu obejmuje całą wybraną minutę; błędny zakres pokazuje
  komunikat i nie zmienia filtra; aktywny zakres widać w legendzie.
- [x] Zmiana filtra działa jak pozostałe filtry (czyści zaznaczenie, pyta o
  potwierdzenie przy aktywnym zaznaczeniu, resetuje stronę i liczniki).
- [x] Bez nowych filtrów żądania są identyczne jak wcześniej.
- [x] Testy stanu i akcji masowych, typecheck, ESLint, Prettier.

## Technical notes

- Zakres zapisany w filtrze jako instant ISO w UTC (`toISOString()`), API
  przyjmuje `AwareDatetime`.
- Zakres filtra jest częścią `symbolReviewFilterScope`, więc liczniki
  nieaktualnego zakresu są odrzucane.

## Test cases

- `apps/admin/test/symbol-review-state.test.mjs`: filtry wysyłane tylko gdy
  ustawione, konwersja minut na zakres włącznie, walidacja.
- `apps/admin/test/symbol-review-bulk-actions.test.mjs`: wybór filtra
  przekazuje źródło i zakres tylko gdy ustawione.

## Outcome

- Zmiany jak w zakresie. 620 testów Admina, `tsc --noEmit`, ESLint, Prettier
  (`--end-of-line auto`) PASS.
- Koniec zakresu wysyłany jako `…59.999999Z` (API porównuje mikrosekundy
  włącznie); wartości z sekundami są obcinane do minuty.
- Audyt `claude-fable-5-1`: PASS bez P1/P2. Wdrożone P3: przywrócenie pól
  zakresu po anulowaniu zmiany filtra, czyszczenie komunikatu błędu przy
  edycji, akceptacja sekund. Pozostałe P3 (osobne zadanie): liczniki z
  filtrami rozszerzonymi liczone dokładnie przy każdej zmianie strony i
  decyzji (0,8–3 s; tak samo jak dla filtrów pewności), brak producenta
  zaznaczenia „wszystkie pasujące” w UI (stan sprzed T5), nieistniejąca
  godzina przy zmianie czasu przesuwana przez przeglądarkę.
- Worktree dostał własny `node_modules` (katalog z junction do zależności
  głównego checkoutu, a pakiety `@game-predictor/*` wskazują na worktree),
  bo junction całego katalogu kierował Admina do klienta API z głównego
  checkoutu. Katalog jest ignorowany przez Git; to ustawienie lokalne worktree.
