---
title: TASK-0253 board import staging visibility and terminology
status: done
release: "0.7"
last_updated: 2026-08-21
---

# TASK-0253 — Widoczność stagingu importu plansz i nazewnictwo panelu

## Status

`done`

## Goal

Administrator widzi, dlaczego gotowy staging zdjęć nie jest jeszcze dostępny do
zatwierdzania, oraz cały widoczny przepływ Admina nazywa jednostkę gry
„planszą”, nie „layoutem”.

## Context

Staging `19810 - 45162` (`e8c83cf9`, 2817 JPEG) zawiera wyłącznie gotowe pliki
źródłowe. Dropdown Reviewera przyjmuje tylko image-import joby w stanie
`waiting_for_review` albo `completed`, ponieważ jedynie one mają kolejkę
`image_review_items` i zasoby plansz. Obecny ekran nie pokazuje gotowego
stagingu, więc komunikat wygląda jak brak importu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/project/GLOSSARY.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- pokazać w sekcji zatwierdzania gotowe stagingi bieżącej gry, gdy nie istnieje
  jeszcze job dostępny do review,
- wyjaśnić, że staging nie trafia do dropdownu, bo wymaga raportu, preflightu
  geometrii i jawnego startu joba importu plansz,
- zachować dropdown wyłącznie dla jobów `waiting_for_review`/`completed`,
- zmienić widoczne etykiety, komunikaty, przyciski i opisy Admina z
  „layout/layouty/layoutów” na poprawne formy „plansza/plansze/plansz”,
- utrwalić regułę słownika: UI używa „plansza”, techniczne identyfikatory i
  istniejące kontrakty `layout` zostają bez breaking change.

## Out of scope

- automatyczne uruchamianie importu po uploadzie,
- dodawanie stagingu do dropdownu Reviewera albo tworzenie review bez joba,
- zmiana endpointów, OpenAPI, nazw tabel, pól `layoutCount` lub migracja bazy,
- zmiana algorytmu geometrii, symboli, kolejki lub uprawnień Reviewera,
- zmiana historycznych danych oraz URI API.

## Acceptance criteria

- [x] Gotowy staging przypisany do gry jest widoczny w sekcji zatwierdzania,
      gdy nie ma jeszcze gotowego joba review.
- [x] Komunikat wskazuje, że staging jest źródłem plików, a do dropdownu trafi
      dopiero job po jawnym starcie i utworzeniu kolejki plansz.
- [x] Przycisk prowadzi do sekcji `Import plansz`; nie uruchamia żadnej mutacji.
- [x] Dropdown nadal zawiera wyłącznie joby importu obrazów w statusie
      `waiting_for_review` lub `completed` tej samej gry.
- [x] Widoczny Admin używa słowa „plansza” w przepływach gier, selekcji zdjęć,
      importu, zatwierdzania, datasetów i payoutów.
- [x] Techniczne nazwy API/TypeScript i dane `layout` pozostają bez zmian.
- [x] Testy Admina, typecheck, celowany lint i formatowanie przechodzą.

## Technical notes

Lista stagingów używa istniejącego read-only endpointu
`listReadyBrowserImageSelections`. Jej awaria nie może ukryć gotowych jobów
Reviewera ani umożliwić pracy na stagingu. Widoczny staging jest filtrowany do
`gameId` bieżącej gry albo historycznego stagingu bez `gameId`, analogicznie do
ekranu importu plansz. Nie wymaga tokenu, joba ani zmiany uprawnień.

## Expected files

- `apps/admin/src/features/reviewer-access/reviewer-access-actions.ts`
- `apps/admin/src/features/reviewer-access/reviewer-access-state.ts`
- `apps/admin/src/features/reviewer-access/reviewer-access-launcher.tsx`
- `apps/admin/src/features/imports/image-folder-import-actions.ts`
- `apps/admin/src/features/imports/image-folder-import-panel.tsx`
- widoczne komponenty Admina używające etykiet plansz
- `apps/admin/test/reviewer-access-state.test.mjs`
- `apps/admin/test/reviewer-access-launcher-contract.test.mjs`
- `apps/admin/test/image-folder-import-panel-contract.test.mjs`
- `ai_docs/project/GLOSSARY.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm.cmd test --workspace @game-predictor/admin
npm.cmd run typecheck --workspace @game-predictor/admin
npx.cmd eslint src/features/reviewer-access/reviewer-access-actions.ts src/features/reviewer-access/reviewer-access-state.ts src/features/reviewer-access/reviewer-access-launcher.tsx src/features/imports/image-folder-import-actions.ts src/features/imports/image-folder-import-panel.tsx test/reviewer-access-state.test.mjs test/reviewer-access-launcher-contract.test.mjs test/image-folder-import-panel-contract.test.mjs
npx.cmd prettier --check ai_docs/project/GLOSSARY.md ai_docs/requirements/ADMIN_APP.md ai_docs/process/DECISION_LOG.md ai_docs/process/CURRENT_STATE.md apps/admin/src/features/reviewer-access/reviewer-access-actions.ts apps/admin/src/features/reviewer-access/reviewer-access-state.ts apps/admin/src/features/reviewer-access/reviewer-access-launcher.tsx apps/admin/src/features/imports/image-folder-import-actions.ts apps/admin/src/features/imports/image-folder-import-panel.tsx
```

## Risks / open questions

- Staging nie może być uruchamiany automatycznie: pełny import i preflight
  geometrii pozostają jawną decyzją właściciela.
- Termin `layout` pozostaje w stabilnym API i kodzie; globalne techniczne
  przemianowanie byłoby niepotrzebnym breaking change.

## Outcome

- Reviewer ładuje istniejące gotowe stagingi wyłącznie do komunikatu
  pomocniczego. Gdy dla wybranej gry nie ma joba gotowego do review, pokazuje
  nazwę stagingu, liczbę plików oraz wymagane kolejne kroki. Nie tworzy joba
  ani nie dodaje stagingu do dropdownu.
- UI Admina używa „plansza/plansze/plansz” w widocznych tekstach przepływów
  gier, selekcji zdjęć, importu, zatwierdzania, datasetów i payoutów.
  Kontrakty API i techniczne identyfikatory `layout` nie zostały zmienione.
- Weryfikacja: `npm.cmd test --workspace @game-predictor/admin` — 220/220;
  `npm.cmd run typecheck --workspace @game-predictor/admin` — OK; celowany
  ESLint — 0 błędów (2 istniejące ostrzeżenia `no-img-element`); Prettier
  `--check` — OK; `git diff --check` — OK.
