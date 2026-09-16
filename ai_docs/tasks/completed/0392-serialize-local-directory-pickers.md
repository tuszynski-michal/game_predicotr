---
title: TASK-0392 — Wspólna blokada lokalnego pickera katalogów
status: done
last_updated: 2026-09-02
---

# TASK-0392 — Wspólna blokada lokalnego pickera katalogów

## Goal

Zapewnić, że działająca w tle `Weryfikacja zakresów` nie blokuje lokalnych
workflowów `Uzupełnij luki` i `Usuń sekwencje`, a równoległe kliknięcia nie
wywołują drugiego systemowego `showDirectoryPicker`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Scope

- jeden współdzielony koordynator File System Access dla lokalnych pickerów
  Admina;
- lock wyłącznie na czas otwartego natywnego dialogu;
- stabilny komunikat po drugim wywołaniu lub konflikcie dialogu spoza
  koordynatora;
- użycie koordynatora przez lokalną ręczną selekcję, korektę, weryfikację
  zakresów oraz pozostałe lokalne akcje wyboru katalogu.

## Out of scope

- zatrzymywanie joba weryfikacji zakresów;
- kolejka opóźnionych pickerów (straciłaby wymagany browserowy user gesture);
- zmiana manifestów, API, bazy albo workera.

## Acceptance criteria

- aktywny job OCR nie utrzymuje locka pickera;
- drugi picker podczas otwartego dialogu nie wywołuje natywnego API;
- po anulowaniu, sukcesie albo zewnętrznym `InvalidStateError` lock jest
  zwalniany;
- metoda jest wywoływana z `window` jako receiver, aby nie wywołać
  `Illegal invocation`.

## Outcome

- Dodano `local-directory-picker.ts` z procesowo współdzielonym lockiem i
  normalizacją natywnego konfliktu do czytelnego błędu.
- Lokalna selekcja, `Popraw selekcję`, `Weryfikacja zakresów`, półautomat oraz
  export selekcji używają wspólnego, krótkotrwałego pickera.
- Weryfikacja: `npm run test --workspace @game-predictor/admin` (`364`
  zaliczone), `npm run lint --workspace @game-predictor/admin`, `npm run
  typecheck --workspace @game-predictor/admin`, kontrola Prettier zmienionych
  plików oraz `npm run admin:build`.
