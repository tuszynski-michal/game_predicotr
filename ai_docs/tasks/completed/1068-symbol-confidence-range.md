# TASK-1068 — Zakres pewności rozpoznania symboli

## Status

`done`

## Goal

Zastąpić gotowe zakresy radio dwoma polami całkowitymi 0–100%.

## Context

Operator potrzebuje dowolnego zakresu pewności w Weryfikacji symboli. Polecenie użytkownika obejmuje implementację dwóch inputów albo suwaka.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md` — Weryfikacja symboli.
- `ai_docs/architecture/API_CONTRACT.md` — domknięte minConfidence/maxConfidence.
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

Dwa inputy Od (%) / Do (%), walidacja liczb całkowitych 0–100 i kolejności, zastosowanie oraz reset Wszystkie. Domknięte granice dzielone przez 100 trafiają do istniejącego API. Domyślnie brak filtra, także dla komórek bez pewności; jawne 0–100 filtruje tylko znaną pewność.

## Acceptance criteria

- [x] Dowolny domknięty zakres całkowity 0–100, także 0–0 i 100–100.
- [x] Puste, ułamkowe, odwrócone i wychodzące poza 0–100 wartości nie zmieniają filtra.
- [x] Zastosowanie korzysta z istniejącej ochrony zaznaczenia i resetu paginacji; reset usuwa oba parametry.
- [x] Testy, lint, typy i docs:check zaliczone; wynik oraz ograniczenia zapisane w Outcome.

## Expected files

- `apps/admin/src/features/symbol-reviews/symbol-review-state.ts` — typ i mapowanie zakresu.
- `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx` — kontrolki.
- Nowy `apps/admin/src/features/symbol-reviews/symbol-review-confidence-inputs.tsx` — lokalny draft i walidacja.
- Testy stanu, kontraktu i interakcji; wymagania ADMIN_APP, mapa kodu, CURRENT_STATE.

## Test cases

Zakres 37–92 mapuje się na 0.37–0.92; końce 0 i 100 są domknięte. Walidacja odrzuca pusty input, 1.5, -1, 101 i min > max. Zastosowanie i reset sprawdzane interakcyjnie.

## Risks / open questions

Brak blokujących pytań. Założenie UX: dwa inputy z jawnym zastosowaniem zapobiegają przeładowaniu podczas wpisywania. Bez zmiany API, migracji i usług. Audyt nie jest wymagany przez plan (zadanie bez osobnego planu).

## Outcome

Commit: v1.7.441 (hash dopisuje kolejny commit).

### Changed

- Dwa inputy całkowite Od (%) / Do (%), walidacja 0–100 i min <= max, zastosowanie przyciskiem lub Enter oraz reset Wszystkie.
- Domknięte granice przeliczane na istniejące parametry API; draft nie wywołuje requestów. Aktywny zakres widoczny przy polach.
- Zachowana ochrona zaznaczenia: anulowanie pozostawia filtr i zaznaczenie, potwierdzenie stosuje zakres i czyści zaznaczenie/paginację.
- Przyciski mają odrębne nazwy dla pewności i daty; kontrolki zawijają się na wąskim ekranie i mają wysokość minimum 44 px.

### Verification results

- 36/36 testów stanu, żądań i kontraktu workspace: node --experimental-strip-types --test (symbol-review-state, symbol-review-actions, symbol-review-workspace-contract).
- 17/17 testów interakcji: node --import tsx --test test-interactions/symbol-review-partial.test.mjs (cwd apps/admin), w tym zakresy 37–92 i 100–100, błędne wartości, ochrona zaznaczenia i reset.
- ESLint trzech zmienionych modułów TypeScript i tsc --noEmit: PASS. Prettier zmienionych plików aplikacji/testów: PASS.
- Build produkcyjny Admina: PASS (npm run build --workspace @game-predictor/admin).
- Regeneracja mapy kodu: PASS. docs:check: PASS przed zamknięciem; kontrola powtórzona po zamknięciu.

### Not completed

- Brak ręcznego odbioru w przeglądarce i na fizycznym Androidzie. Bez restartowania usług, zmiany API, migracji, operacji danych, push i scalania do main.
- Audyt krzyżowy nie jest wymagany (zadanie bez planu wymagającego dodatkowego review).

### Documentation updates

- ADMIN_APP: dowolny domknięty zakres całkowity, walidacja, zastosowanie i reset; mapa kodu i CURRENT_STATE aktualizowane zgodnie z task-close.

### Recommended next task

- Odbiór operatora i decyzja o scaleniu gałęzi codex/symbol-confidence-range do main.
