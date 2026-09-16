---
title: TASK-0396 — Wskaźnik wykluczenia zatwierdzonego cropa z uczenia
status: done
last_updated: 2026-09-02
---

# Cel

W widoku `Zatwierdzone` Weryfikacji symboli operator ma od razu widzieć, że
zatwierdzony crop nie wejdzie do kolejnej kohorty treningowej, oraz dlaczego.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Zakres

- Dodać do istniejącego badge'a karty zatwierdzonego cropa czytelne wskazanie
  `Poza uczeniem`, gdy bieżące dane wykluczają go z kohorty.
- Pokazać przyczynę: problem jakości (`blurry`, `unreadable`, awaryjnie
  `grid_issue`) albo brak aktualnie zatwierdzonego checksum-bound cropa.
- Dodać regresyjny test kontraktowy komponentu oraz zaktualizować wymaganie i
  Current State.

## Poza zakresem

- Zmiana kryteriów budowy kohorty, modelu danych, endpointów lub migracji.
- Zmiana zatwierdzenia, przypisania symbolu lub bieżącego workflowu review.

## Definition of Done

- Zatwierdzony crop wykluczony z uczenia ma badge z przyczyną i tekstem
  `Poza uczeniem`.
- Crop zatwierdzony i kwalifikujący się zachowuje obecny, niezaśmiecony widok.
- Test kontraktowy potwierdza stany jakości i checksum-bound recrop.
- Zmienione testy, lint, typecheck i build Admina przechodzą.

## Outcome

Zaimplementowano oznaczenie `Poza uczeniem` wyłącznie na zatwierdzonych
cropach, które istniejąca polityka kohort wyklucza przez problem jakości,
nierozpoznane `?` albo nieaktualny / niezatwierdzony checksum-bound crop.
Karty kwalifikujące się do uczenia nie otrzymują dodatkowego badge'a.

Walidacja: `npm run test --workspace @game-predictor/admin` (367 testów),
`npm run lint --workspace @game-predictor/admin`,
`npm run typecheck --workspace @game-predictor/admin` oraz
`npm run build --workspace @game-predictor/admin`.
