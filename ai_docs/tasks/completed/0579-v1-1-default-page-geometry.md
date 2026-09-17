---
title: TASK-0579 v1.1 as default page-geometry engine
status: done
last_updated: 2026-09-17
---

# TASK-0579 — v1.1 jako domyślny silnik geometrii stron

## Status

`in_progress`

## Goal

Nowy raport, preflight geometrii i import przeglądarkowego stagingu bez jawnie
wybranego wariantu przypinają `selective_board_review_v1_1` (v1.1).

## Context

Właściciel potwierdził, że v1.1 radzi sobie dobrze i ma zastąpić v1.0 jako
domyślny wybór nowych workflowów. Dotychczasowy default v1.0 był zapisany
zarówno w panelu Admina, jak i w schematach żądań API.

## Dependencies / entry conditions

- TASK-0562 i TASK-0563 dostarczyły oba stabilne warianty oraz odrębne,
  checksummowane snapshoty.
- Capability v1.1 jest nadal sprawdzana przed utworzeniem joba; brak capability
  ma zwrócić istniejącą blokadę, nigdy cicho uruchomić v1.0.
- Istniejące joby zawierają przypięty wariant i nie są migrowane.

## Recommended execution

`gpt-5.6-sol`, reasoning `high`: niewielka zmiana obejmuje panel, fallback
API, OpenAPI i regresje zachowania historycznego. Ponowna analiza mocniejszym
modelem jest potrzebna tylko, gdy testy ujawnią niejednoznaczność istniejących
tożsamości preflightu lub importu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Ustawić v1.1 jako wartość początkową nowych raportów w Adminie i fallback
  braku raportu dla nowego stagingu.
- Ustawić v1.1 jako backendowy default raportu, preflightu i startu importu;
  zregenerować oraz zweryfikować OpenAPI i klienta.
- Zachować jawny wybór v1.0 oraz przypięte warianty istniejących preflightów i
  importów.
- Uaktualnić wymagania, kontrakt, decyzję architektoniczną i bieżący stan.

## Out of scope

- Uruchamianie nowych preflightów, importów, cropów lub zmian w stagingach.
- Modyfikacja istniejących manifestów, jobów albo danych gry.
- Zmiana algorytmu v1.0 lub v1.1 oraz polityki per-game.

## Acceptance criteria

- [ ] Brak `geometryEngineVariant` w żądaniu raportu, preflightu i startu
  importu daje v1.1 w modelu API i w opublikowanym OpenAPI.
- [ ] Nowy staging w panelu zaczyna z v1.1; v1.0 może nadal zostać wybrany
  ręcznie.
- [ ] Otwarcie stagingu z ukończonym v1.0 lub v1.1 zachowuje jego przypięty
  wariant, bez tworzenia joba.
- [ ] Testy kontraktu, API, klienta i panelu potwierdzają nowe zachowanie oraz
  ochronę historii.

## Technical notes

1. `image-folder-import-actions.ts` przechowuje stały default początkowego
   stanu panelu, a czysty moduł stanu zachowuje równoważny fallback bez importu
   runtime, aby był wykonywalny w bezpośrednich testach Node.
2. `readyBoardImportGeometryVariant` rozróżnia brak pasującego preflightu
   (nowy default v1.1) od znalezionego historycznego preflightu (odczyt jego
   przypiętego wariantu, w tym kompatybilny fallback v1.0).
3. Trzy request models w `schemas/image_imports.py` muszą zwracać v1.1 także
   gdy klient pominie pole lub prześle wartość pustą. Dla niedostępnego v1.1
   bramka capability pozostaje fail-closed.
4. Zmiana domyślnej wartości jest zmianą kontraktu dokumentowaną w OpenAPI;
   wygenerowane pliki pochodzą wyłącznie z `npm run openapi:generate`.
5. D-400 zastępuje wyłącznie decyzję o defaultcie z D-396 oraz opt-in część
   D-397. Semantyka selektywnego ponownego użycia v1.1 pozostaje bez zmian.

## Expected files

- Istniejące: `apps/admin/src/features/imports/image-folder-import-actions.ts`
  — stały domyślnego wariantu.
- Istniejące: `apps/admin/src/features/imports/image-folder-import-state.ts`
  — fallback nowego stagingu i odczyt historii.
- Istniejące: `apps/admin/src/features/imports/image-folder-import-panel.tsx`
  — początkowy wybór i etykieta v1.1.
- Istniejące: `services/api/src/game_predictor_api/schemas/image_imports.py`
  — backendowe wartości domyślne.
- Istniejące: testy API/Admina oraz `packages/admin-api-client/openapi/` i
  `packages/admin-api-client/src/generated/` — regresje i wygenerowany kontrakt.
- Istniejące: `ai_docs/requirements/IMAGE_INGESTION.md`,
  `ai_docs/architecture/API_CONTRACT.md`, `ai_docs/process/DECISION_LOG.md`,
  `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Puste requesty trzech modeli API → v1.1 w `geometryEngineVariant`.
- Nowy staging bez pasującego preflightu → v1.1; ukończony v1.0 i v1.1 →
  odpowiednio przypięty wariant.
- Panel oferuje v1.1 jako wybór startowy oraz v1.0 jako opcję ręczną.
- Export OpenAPI → trzy deklaracje defaultu v1.1, wygenerowany klient bez
  dryfu.

## Verification

```powershell
# Katalog repozytorium; każdy krok ma limit 120 s.
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_lateral_partial_engine_contract.py -q
node --test apps/admin/test/image-folder-import-state.test.mjs apps/admin/test/image-folder-import-panel-contract.test.mjs
npm run openapi:generate
npm run openapi:check
npm test --workspace @game-predictor/admin-api-client
npx tsc --noEmit -p apps/admin/tsconfig.json
npx eslint apps/admin/src/features/imports/image-folder-import-actions.ts apps/admin/src/features/imports/image-folder-import-state.ts apps/admin/src/features/imports/image-folder-import-panel.tsx
```

## Risks / open questions

- Default v1.1 jest zależny od istniejącej capability release; jej brak celowo
  blokuje żądanie zamiast zmieniać wybrany silnik na v1.0.
- Wygenerowanie OpenAPI może wymagać lokalnych zależności JavaScript; nie wolno
  ręcznie poprawiać plików generated.

## Outcome

### Changed

- v1.1 (`selective_board_review_v1_1`) jest backendowym defaultem raportu,
  preflightu oraz startu importu browser stagingu; OpenAPI i wygenerowany klient
  pokazują tę samą wartość.
- Panel Admina zaczyna nowy workflow z v1.1 i nie opisuje go już jako testowego.
  v1.0 pozostaje ręcznie dostępny.
- Nowy staging bez pasującego preflightu wybiera v1.1, zaś istniejący preflight
  v1.0 albo v1.1 zachowuje przypięty wariant.
- D-400 dokumentuje decyzję właściciela; wymagania, kontrakt i bieżący stan są
  z nią zgodne.

### Verification results

- `python -m pytest services/api/tests/test_lateral_partial_engine_contract.py -q`
  — 12 passed (poza sandboxem, ponieważ Pytest potrzebuje Windows temp).
- Celowany kontrakt panelu — 1 passed; stan gotowych stagingów — 10 passed.
- `npm test --workspace @game-predictor/admin-api-client` — 57 passed.
- `npm run openapi:generate` oraz `npm run openapi:check` — passed.
- Typecheck Admina, Ruff zmienionych plików API, Prettier i `git diff --check`
  — passed. ESLint zmienionych modułów ma 0 błędów oraz istniejące ostrzeżenie
  `@next/next/no-img-element` dla niezmienionego obrazu podglądu.

### Not completed

- Nie uruchomiono preflightu, importu, cropa ani żadnej operacji na stagingach,
  manifestach lub zdjęciach użytkownika.
- Pełny plik `image-folder-import-panel-contract.test.mjs` kończy się 28/30:
  dwie wcześniejsze asercje podmiany JPEG-a oczekują fragmentów, których nie ma
  także w bazowym `HEAD`; są poza zakresem TASK-0579.

### Documentation updates

- Zaktualizowano wymagania importu, kontrakt API, D-400 i `CURRENT_STATE.md`.

### Recommended next task

- Brak koniecznego kolejnego taska. Ewentualnie osobno naprawić dwie nieaktualne
  asercje kontraktu panelu podmiany JPEG-a.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0579 — v1.1 jako domyślny silnik geometrii stron | gpt-5.6-sol | high | Spójna, niewielka zmiana defaultu obejmująca UI, API i kontrakt wygenerowany. | Nie jest wymagany; eskalacja do gpt-6-astra high tylko przy niejednoznacznej regresji tożsamości jobów. |
