---
title: TASK-0252 simplify payline editor
status: done
release: "0.7"
last_updated: 2026-08-21
---

# TASK-0252 — Uproszczenie edytora wzorców

## Status

`in_progress`

## Goal

Administrator tworzy wzorzec przez stabilny kod i ścieżkę na siatce, bez ręcznego
wprowadzania opisowej nazwy ani technicznej kolejności.

## Context

`name` jest wyłącznie etykietą w panelu, a `display_order` determinuje tylko
kolejność prezentacji; żadne z tych pól nie zmienia obliczenia wypłat. Ręczne
wypełnianie ich w edytorze zwiększa liczbę czynności bez wartości domenowej.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- zachować jedyne edytowalne metadane wzorca: stabilny `code` i `is_active`,
- usunąć z formularza i tabeli pola `name` oraz `displayOrder`,
- przy tworzeniu ustawić `name` równe znormalizowanemu `code`,
- przy tworzeniu nadać `displayOrder` jako następną dostępną pozycję po
  istniejących wzorcach tej wersji,
- przy edycji nie wysyłać zmiany `name` ani `displayOrder`,
- dodać regresje automatycznej nazwy, kolejności i niezmienności tych pól przy
  edycji.

## Out of scope

- zmiana tabeli domenowej, migracja Alembic lub kontraktu OpenAPI,
- zmiana stabilności albo formatu `code`,
- ręczne przestawianie istniejącej kolejności,
- zmiana kolejności obliczania lub wartości payoutów,
- zmiana symboli, payoutów, publikacji albo importu layoutów.

## Acceptance criteria

- [ ] Formularz utworzenia pokazuje tylko kod, status oraz siatkę ścieżki.
- [ ] Nowy wzorzec zapisuje `name` dokładnie równą jego znormalizowanemu kodowi.
- [ ] Nowy wzorzec otrzymuje kolejność o jeden większą od największej istniejącej
      kolejności; pusty katalog zaczyna od `0`.
- [ ] Edycja ścieżki lub aktywności nie nadpisuje istniejącej nazwy ani
      kolejności.
- [ ] Tabela identyfikuje wzorzec przez kod, nie pokazuje nazwy ani kolumny
      kolejności.
- [ ] Wszystkie istniejące walidacje `code`, `rowPath`, wymiarów, duplikatu i
      lifecycle'u draftu pozostają aktywne.
- [ ] Testy Admina, typecheck, celowany lint i formatowanie przechodzą.

## Technical notes

`name` i `displayOrder` pozostają wymaganymi polami historycznego API oraz bazy.
Admin wypełnia je wyłącznie przy POST: `name = code`, a kolejność jest wyliczana
z aktualnej listy, obejmującej również zarchiwizowane rekordy. Ewentualny
równoległy POST może otrzymać ten sam `displayOrder`; kontrakt zachowuje
deterministyczny tie-break przez `code` i UUID, a payouty nie zależą od kolejności.

## Expected files

- `apps/admin/src/features/rules/payline-editor-state.ts`
- `apps/admin/src/features/rules/payline-actions.ts`
- `apps/admin/src/features/rules/payline-manager-modal.tsx`
- `apps/admin/src/app/globals.css`
- `apps/admin/test/payline-editor-state.test.mjs`
- `apps/admin/test/payline-actions.test.mjs`
- `apps/admin/test/payline-manager-modal-contract.test.mjs`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm.cmd test --workspace @game-predictor/admin
npm.cmd run typecheck --workspace @game-predictor/admin
npx.cmd eslint apps/admin/src/features/rules/payline-editor-state.ts apps/admin/src/features/rules/payline-actions.ts apps/admin/src/features/rules/payline-manager-modal.tsx apps/admin/test/payline-editor-state.test.mjs apps/admin/test/payline-actions.test.mjs apps/admin/test/payline-manager-modal-contract.test.mjs
npx.cmd prettier --check ai_docs/tasks/0252-simplify-payline-editor.md ai_docs/requirements/ADMIN_APP.md ai_docs/architecture/DATA_MODEL.md ai_docs/process/DECISION_LOG.md ai_docs/process/CURRENT_STATE.md apps/admin/src/app/globals.css apps/admin/src/features/rules/payline-editor-state.ts apps/admin/src/features/rules/payline-actions.ts apps/admin/src/features/rules/payline-manager-modal.tsx apps/admin/test/payline-editor-state.test.mjs apps/admin/test/payline-actions.test.mjs apps/admin/test/payline-manager-modal-contract.test.mjs
```

## Risks / open questions

- `displayOrder` nie jest unikalny. Równoległe utworzenia mogą otrzymać tę samą
  wartość, ale istniejący sort po `code` i UUID zapewnia stabilny wynik bez
  wpływu na payouty.

## Outcome

### Changed

- Formularz i tabela wzorców pokazują stabilny kod, aktywność i ścieżkę, bez
  ręcznej nazwy oraz kolejności.
- POST automatycznie wysyła `name = code` oraz kolejną wartość `displayOrder`;
  PATCH zmienia wyłącznie aktywność i ścieżkę.
- Układ tabeli i formularza został zwężony do faktycznej liczby pól.

### Verification results

- Admin tests: `219 passed`.
- Admin typecheck: passed.
- Celowany ESLint zmienionych modułów i testów: passed.
- Prettier dla kodu i dokumentacji zadania: passed.
- `git diff --check`: passed.

### Not completed

- Nie zmieniono API, OpenAPI, bazy ani historycznych rekordów — pozostają
  kompatybilne zgodnie z zakresem zadania.

### Documentation updates

- Zaktualizowano wymagania Admina, model danych i Decision Log (D-207).
- Zaktualizowano `CURRENT_STATE.md` i zarchiwizowano TASK-0252.

### Recommended next task

- Właściciel może utworzyć i edytować wzorzec w panelu, aby potwierdzić
  docelową prostotę interakcji na bieżącym draftcie.
