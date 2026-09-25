# TASK-0656 — pełny ekran i skróty klawiszowe w „Weryfikacji symboli”

## Status

`done`

## Goal

Operator przegląda cropy w „Weryfikacji symboli” z jednym paskiem przewijania
(tryb pełnoekranowy) i zmienia symbol zaznaczonych cropów z klawiatury.

## Context

Zgłoszenie użytkownika (2026-09-25): podwójne scrolle (strona + wirtualna
siatka o stałej wysokości) utrudniają przegląd; filtry mają zostać stałe na
górze, a przewijać ma się wyłącznie lista cropów. Dodatkowo klawisze 1–8
mają wybierać symbol docelowy odpowiadający kolejności symboli z „Zarządzania
grami → Symbole”, a zatwierdzenie przenosi cropy do tej kategorii.

## Dependencies / entry conditions

Brak. Zmiana wyłącznie frontendowa Admina; bez zmiany API.

## Recommended execution

Zadanie zgłoszone bezpośrednio w rozmowie, poza planem; wykonane przez
Claude Opus 5.5 (reasoning domyślny sesji).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` — sekcja „Weryfikacja symboli”

## Scope

- Przycisk `Pełny ekran` / `Zamknij pełny ekran` w bloku filtrów. Tryb
  pełnoekranowy to nakładka `position: fixed` na cały viewport (bez nagłówka
  strony i nawigacji): filtry, toolbar i podsumowanie stałe u góry, siatka
  wypełnia resztę wysokości i jest jedynym przewijanym elementem, paginacja
  na dole. Scroll `body` jest zablokowany na czas trybu.
- Skróty (ignorowane przy fokusie w polu tekstowym/select oraz z Ctrl/Alt/Meta):
  - `1`–`9` — wybór symbolu docelowego `Zmień symbol` (aktywne symbole w
    kolejności `displayOrder`, tej samej co w „Zarządzaniu grami”);
  - `Enter` — `Zastosuj zmianę` dla zaznaczonych cropów (jedna karta:
    bezpośrednia decyzja; więcej: preview operacji masowej); przy otwartym
    preview — `Uruchom operację`;
  - `Esc` — zamknięcie preview operacji albo wyjście z pełnego ekranu.
- Numer skrótu przy nazwie symbolu w selekcie `Zmień symbol` i legenda
  skrótów w toolbarze.

## Out of scope

- Zmiana API, nowe akcje (`Zatwierdź`, `Nieczytelny`, `Zła siatka`) pod
  klawiszami, nawigacja kursorem po kartach, Fullscreen API przeglądarki.

## Acceptance criteria

- [x] W trybie pełnoekranowym przewija się wyłącznie siatka cropów.
- [x] `1`–`9` ustawia symbol docelowy; `Enter` wysyła zmianę zaznaczonych.
- [x] Checkbox `Niewyraźny` nadal modyfikuje zmianę wykonaną klawiszem.
- [x] Dotychczasowy widok (bez pełnego ekranu) działa bez zmian.

## Technical notes

- Czysta logika: `symbol-review-keyboard.ts`
  (`resolveSymbolReviewKeyboardCommand`, `isSymbolReviewTextEntryTarget`,
  `symbolReviewShortcutLabel`).
- Listener `keydown` na `window` rejestrowany raz; aktualny handler trzymany
  w refie. `Enter` przy obsłużonej akcji wywołuje `preventDefault`, żeby
  sfokusowana karta nie przełączyła ponownie zaznaczenia.
- `SymbolReviewVirtualGrid` dostał opcjonalny prop `fill` (domyślnie `false`
  — zachowanie istniejącego widoku bez zmian).

## Expected files

- `apps/admin/src/features/symbol-reviews/symbol-review-keyboard.ts` (nowy)
- `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`
- `apps/admin/src/features/symbol-reviews/symbol-review-workspace.module.css`
- `apps/admin/src/features/symbol-reviews/symbol-review-virtual-grid.tsx`
- `apps/admin/src/features/symbol-reviews/symbol-review-virtual-grid.module.css`
- `apps/admin/test/symbol-review-keyboard.test.mjs` (nowy)

## Test cases

- Cyfry → symbol wg kolejności; cyfra bez symbolu, `0`, litery → brak akcji.
- `Enter`/`Escape` → `apply`/`cancel`; modyfikatory → brak akcji.
- Etykiety tylko dla pierwszych 9 symboli.
- Kontrakt źródła: przycisk pełnego ekranu, `fill`, listener i przepływ
  `reassign`/`startPreviewedOperation`, CSS `position: fixed`.

## Verification

```powershell
npm run test --workspace @game-predictor/admin       # 596/596
npm run typecheck --workspace @game-predictor/admin  # czysto
npm run lint --workspace @game-predictor/admin       # 0 błędów, 4 istniejące ostrzeżenia
```

## Risks / open questions

- Brak odbioru na żywym Adminie (nie uruchamiano API/Admina).
- Założenie: numeracja obejmuje wyłącznie aktywne symbole (lista
  `Zmień symbol` pokazuje tylko aktywne); nieaktywny symbol w „Zarządzaniu
  grami” nie zajmuje numeru. Skróty obejmują 9 pierwszych symboli.

## Outcome

Zaimplementowano zgodnie z zakresem; testy, typecheck i lint Admina zielone.
