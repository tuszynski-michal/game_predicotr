# TASK-1069 — Kompaktowy styl zakresu pewności symboli

## Status

`done`

## Goal

Dopasować wygląd pól zakresu pewności do ciemnego panelu gry i zmniejszyć zajmowaną wysokość.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md` — Weryfikacja symboli.
- `ai_docs/architecture/MANAGEMENT_PANEL.md` — kompaktowy panel.
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

Wyłącznie styl i układ istniejącego filtra: pola z kolorami panelu, zaokrągleniami i wysokością 32 px na desktopie, etykiety obok pól, aktywny zakres w tym samym wierszu, przyciski zgodne z panelem. Urządzenia dotykowe zachowują minimum 44 px. Bez zmiany walidacji, zakresu i API.

## Expected files

- `apps/admin/src/features/symbol-reviews/symbol-review-confidence-inputs.tsx` — układ i klasy przycisków.
- `apps/admin/src/features/symbol-reviews/symbol-review-workspace.module.css` — lokalny styl.
- `ai_docs/requirements/ADMIN_APP.md`, task i CURRENT_STATE.

## Acceptance criteria

- [x] Pola mają tło i tekst z motywu panelu, zaokrąglenie oraz kompaktowy rozmiar.
- [x] Etykiety, pola, przyciski i aktywny zakres dzielą jeden wiersz przy dostępnej szerokości; na wąskim ekranie się zawijają.
- [x] Walidacja i istniejące interakcje działają; kontrolki dotykowe zachowują 44 px.

## Risks / open questions

Brak blokujących pytań. Korekta wizualna na polecenie operatora. Bez nowego planu i wymaganego audytu.

## Outcome

Commit: v1.7.443 (hash dopisuje kolejny commit).

### Changed

- Pola mają tło i tekst z motywu panelu, zaokrąglenia 8 px oraz wysokość 32 px na desktopie zamiast 44 px.
- Etykiety są obok pól; aktywny zakres dzieli wiersz z kontrolkami. Przyciski korzystają z primaryButton/secondaryButton i kompaktowych rozmiarów.
- Media query pointer: coarse przywraca minimum 44 px dla dotyku. Układ nadal zawija się przy braku miejsca.

### Verification results

- Odbiór wizualny w istniejącym Adminie przez przeglądarkę: PASS. Odczyt wyrenderowanego pola: height=32, borderRadius=8px, background=rgb(19, 34, 56). Pola, etykiety, oba przyciski i aktywny zakres są w jednym wierszu.
- Istniejący test interakcyjny integer confidence inputs: PASS (zakres, walidacja, ochrona zaznaczenia, reset).
- Prettier obu plików i ESLint komponentu: PASS. docs:check uruchomiony przy zamknięciu.
- Bez zmiany symboli publicznych, typów ani logiki; mapa kodu pozostaje aktualna. Nie powtarzano pełnego builda i testów aplikacji dla lokalnej korekty stylu.

### Not completed

- Brak testu na fizycznym urządzeniu dotykowym. Bez restartu usług, scalenia i push.
- Audyt nie jest wymagany przez plan.

### Documentation updates

- ADMIN_APP: kompaktowe kontrolki zakresu i minimum 44 px dla dotyku.

### Recommended next task

- Odbiór operatora i scalenie po jego zgodzie.
