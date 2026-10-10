# TASK-0969 — Sekcja „Ostatnie korekty” w Reviewerze

## Status

`done`

## Goal

Operator widzi ostatnie korekty bieżącego importu w „Korekta cięcia siatki” i cofa wybraną po podglądzie skutków i potwierdzeniu.

## Context

Plan `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, sekcja „UI Reviewera (TASK-0969)”.

## Dependencies / entry conditions

- TASK-0968 ukończony (klient z trzema operacjami).

## Recommended execution

`claude-sonnet-5-5`, reasoning `medium`: komponent UI z listą, modalem i testami w istniejącym ekranie. Eskalacja: potrzeba zmiany kontraktu API → zatrzymaj i zgłoś. Review: Codex `gpt-6-astra`, `medium`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` (sekcja Reviewera, jeśli istnieje; inaczej plan)

## Scope

- Komponent (proponowany) `apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx` w `BoardGeometryCorrectionWorkspace` (`board-geometry-correction-workspace.tsx`), pod kolejką.
- Wiersz listy: godzina lokalna, sekwencja, pozycja, rodzaj („slot” / „plansza”), autor; „Cofnij” tylko dla `revertable`, inaczej komunikat blokady.
- Modal potwierdzenia z podglądem (`previewGeometryCorrectionRevert`): co zostanie usunięte lub przywrócone; przycisk „Potwierdź cofnięcie” z nowym `idempotencyKey`; blokada podwójnego kliknięcia; obsługa 409 (komunikat i odświeżenie).
- Odświeżenie listy po zapisie korekty (`handleSaved`) i po cofnięciu; odświeżenie kolejki po cofnięciu.
- Wywołania przez klienta z `packages/admin-api-client` (bez ręcznych typów).

## Out of scope

- Panel Admin, zmiany API.

## Acceptance criteria

- [ ] Testy Reviewera: render listy, stan zablokowany, podgląd, potwierdzenie wysyła jedno żądanie z CAS, 409 pokazuje komunikat, sukces odświeża kolejkę i listę.
- [ ] `typecheck`, `lint`, `test` i `build` Reviewera zielone.

## Expected files

- Nowe (proponowane): `apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx`, test w `apps/reviewer/test/` lub `apps/reviewer/test-interactions/`.
- Zmieniane: `board-geometry-correction-workspace.tsx`, style Reviewera.

## Test cases

- Lista z dwiema korektami (jedna zablokowana) → jeden przycisk „Cofnij”.
- Potwierdzenie → `revertGeometryCorrection` z `expectedGeometryRevision`/`expectedResolutionRevision` z listy.
- Odpowiedź 409 `GEOMETRY_REVERT_CELLS_CHANGED` → komunikat, lista odświeżona.

## Verification

```powershell
npm run test --workspace @game-predictor/reviewer
npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run reviewer:build
```

## Risks / open questions

- Brak.

## Outcome

Wykonawca: claude-sonnet-5-5 (medium), 2026-10-09. Bez commita.

### Changed

- Nowy `geometry-correction-history.tsx` (`GeometryCorrectionHistory`): lista (godzina lokalna, sekwencja, pozycja, rodzaj slot/plansza, autor), `Cofnij` tylko dla `revertable`, inaczej komunikat blokady z API; modal potwierdzenia z podglądem (`previewGeometryCorrectionRevert`), `Potwierdź cofnięcie` wysyła jedno żądanie z nowym `crypto.randomUUID()` i tokenami CAS z podglądu; blokada podwójnego kliknięcia (ref); błąd (409) zamyka modal, pokazuje komunikat i odświeża listę; sukces odświeża listę i kolejkę (`onReverted`).
- `board-geometry-correction-workspace.tsx`: typ klienta rozszerzony o trzy operacje, sekcja pod kolejką, odświeżenie listy w `handleSaved` (`refreshToken`), przeładowanie kolejki po cofnięciu.
- `reviewer.css`: style listy i modala (style modala Admina nie są w CSS Reviewera).
- Testy: nowy `test-interactions/geometry-correction-history.test.mjs` (3 testy), `fakeApi` w `board-geometry-correction.test.mjs` rozszerzone o `listGeometryCorrections`.

### Verification results

- `npm run test --workspace @game-predictor/reviewer` -> 241 pass, 0 fail.
- `npm run test:geometry --workspace @game-predictor/reviewer` -> 43 pass, 0 fail.
- `npm run typecheck --workspace @game-predictor/reviewer` -> bez błędów.
- `npm run lint --workspace @game-predictor/reviewer` -> 0 błędów, 1 istniejące ostrzeżenie (`board-search-share-data-source.ts`, poza zakresem).
- `npm run reviewer:build` -> sukces.
- `npx prettier --check apps/reviewer/src apps/reviewer/test-interactions` -> czysto.

### Not completed

- Brak testu, że zapis korekty w pełnym ekranie ponownie wywołuje `listGeometryCorrections` (pokryte wyłącznie przez `refreshToken` komponentu i testy listy).
- Brak ręcznej weryfikacji w przeglądarce.

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md`: akapit o sekcji `Ostatnie korekty` w „Korekta cięcia siatki”. `CURRENT_STATE.md` i `DECISION_LOG.md` zostawione leadowi.

### Recommended next task

TASK-0970: odrzucanie przyciętej planszy i slotu w Reviewerze.

### Runda poprawek audytu

Raport rundy 1 zachowany w `ai_docs/quality/TASK-0969_AUDIT_gpt-6-astra_round1.md`.

- P0-1: klucz idempotencji tworzony raz przy otwarciu modala (`openRevert`) i używany przy każdej ponowie; treść żądania pochodzi z jednego podglądu. Błąd sieci lub nieznany wynik zostawia modal otwarty z tym samym kluczem i przyciskiem „Spróbuj ponownie”. Odpowiedź z błędem API (409 i inne) zamyka modal i odświeża listę oraz kolejkę; sukces, także powtórzony (`created=false`), odświeża listę i kolejkę tak samo. Poprawiony wprowadzający w błąd komentarz.
- P1-1: `fakeApi` w `board-geometry-correction.test.mjs` zapisuje wywołania listy korekt, podglądu i cofnięcia; dwa testy całego ekranu (zapis korekty odświeża listę; cofnięcie odświeża historię i kolejkę, a przywrócony slot pojawia się w kolejce).
- P2-1: fokus wchodzi do modala, Tab jest uwięziony, Escape zamyka (poza trwającym żądaniem), fokus wraca do przycisku „Cofnij”. Klawisze modala nie propagują się (`stopPropagation`), a skróty symboli edytora (`deferred-board-cell-geometry-editor.tsx`) są pomijane, gdy istnieje `[aria-modal="true"]`. Testy: ponowienie z tym samym kluczem, fokus/Tab/Escape/brak wycieku klawiszy.
- Weryfikacja: test Reviewera 241 pass; `test:geometry` 47 pass; typecheck czysty; lint 0 błędów (1 istniejące ostrzeżenie); `reviewer:build` OK; prettier czysty.

### Druga runda poprawek (decyzja leada)

- Wygenerowany klient nie rzuca przy błędach transportu: zwraca `{error, request, response}` z `response === undefined`. Kod traktował to jako jednoznaczną odmowę i tracił klucz.
- `geometry-correction-history.tsx`: jednoznaczną odmową jest wyłącznie wynik z zdefiniowanym `response` o statusie 4xx i ciałem błędu z `code` (modal zamyka się, odświeżają się lista i kolejka). Wszystko inne (wyjątek, brak `response`, nieparsowalne ciało, 5xx także z `code`) zostawia modal otwarty z tym samym kluczem i treścią oraz przyciskiem „Spróbuj ponownie”. 5xx jest nieznanym wynikiem, bo serwer mógł zatwierdzić zmianę przed błędem; ponowienie z tym samym kluczem jest idempotentne i rozstrzyga stan.
- Testy w `geometry-correction-history.test.mjs` używają prawdziwego klienta (`createAdminApiClient`) z podstawionym `fetch`: 409 z kodem, odrzucony fetch, 503, a następnie sukces powtórzony `created=false` z identyczną treścią i kluczem w trzech żądaniach.
- Weryfikacja: test Reviewera 241 pass; `test:geometry` 47 pass; typecheck czysty; lint 0 błędów (1 istniejące ostrzeżenie); prettier czysty.

### Trzecia runda poprawek (decyzja leada)

Raport rundy 3 zachowany w `ai_docs/quality/TASK-0969_AUDIT_gpt-6-astra_round3.md`.

- Odpowiedź podglądu była dopasowywana do modala tylko po `boardGeometryRevisionId`, więc spóźniona odpowiedź z zamkniętego otwarcia nadpisywała podgląd, tokeny CAS lub błąd ponownie otwartego modala.
- `geometry-correction-history.tsx`: każde otwarcie ma własny klucz (`idempotencyKey`) zapisany w `openingRef`; odpowiedź podglądu jest stosowana tylko, gdy jej klucz jest bieżącym otwarciem, a odświeżenie listy po błędzie podglądu dotyczy tylko bieżącego otwarcia. Otwarcie, które wysłało cofnięcie (`sentKeysRef`), nigdy nie dostaje nowego podglądu ani nowych tokenów czy treści.
- Test odwróconej kolejności odpowiedzi: otwórz, anuluj, otwórz ponownie, druga odpowiedź przychodzi przed pierwszą; ponowienie używa tokenów i treści drugiego otwarcia.

### Zamknięcie (lead)

- Audyt Codex `gpt-6-astra`/`medium`: runda 1 REVISE (P0 ponowienia, P1 testy, P2 fokus), runda 2 REVISE (P0 błąd transportu bez wyjątku), runda 3 REVISE (P0 wyścig podglądu), runda 4 PASS. Raporty rund w `ai_docs/quality/TASK-0969_AUDIT_gpt-6-astra_round{1,2,3}.md`. Rundy 2–3 poprawek to decyzja leada (operator polecił samodzielne rozwiązywanie problemów).
- Weryfikacja leada: `npm run reviewer:build` → sukces.
- Commit: v1.7.294 / f8fa2ae0ba9ed57e0e8777f7c20c0a205de56040.
