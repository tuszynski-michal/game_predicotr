---
title: TASK-0403 — Stabilne wznowienie Popraw selekcję
status: done
created: 2026-09-02
---

# TASK-0403 — Stabilne wznowienie Popraw selekcję

## Goal

Usunąć pozorne zawieszenie lokalnego workflowu `Popraw selekcję` po reloadzie
oraz zagwarantować, że ręcznie wskazany katalog nie zostanie nadpisany przez
spóźnione automatyczne wznowienie.

## Context

Katalog z tysiącami plików `seq_*` jest przy wznowieniu czytany i hash­owany
dwukrotnie, bez stanu postępu. Dodatkowo automatyczne przywracanie z IndexedDB
może zakończyć się po ręcznym wyborze katalogu i zapisać starszy snapshot.
Operator widzi wówczas długą pustą kartę lub pozorne zawieszenie przy wyborze
katalogu bazowego do uzupełniania luk.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- Zachować pełną walidację nazw i checksumm przy pierwszym otwarciu/reloadzie,
  ale nie hash­ować ponownie pliku już sprawdzonego w tej samej inspekcji.
- Dodać jawne fazy UI dla przywracania, wyboru katalogu, inspekcji i listowania
  bazowego folderu; zablokować sprzeczne akcje w czasie tych faz.
- Unieważnić spóźnione przywracanie po ręcznym wyborze katalogu.
- Przy ręcznym rebindzie trwale zapisać właśnie wskazany uchwyt katalogu,
  zamiast zostawiać historyczny uchwyt z IndexedDB.
- Dodać testy regresji pojedynczego hash­owania oraz ochrony UI przed konfliktem
  recovery i ręcznego wyboru.

## Out of scope

- Zmiana formatu repair/output manifestu, zasad luk, lokalnych mutacji plików,
  OCR, API, jobów, stagingu lub uploadu.
- Osłabienie weryfikacji checksummy albo automatyczne usuwanie plików.

## Acceptance criteria

- [ ] Wznowienie hashuje każdy znany plik maksymalnie raz.
- [ ] UI pokazuje bieżący etap i nie pozwala rozpocząć sprzecznej akcji.
- [ ] Ręczny wybór katalogu wygrywa ze spóźnionym recovery.
- [ ] Nowy uchwyt katalogu jest zapisany w IndexedDB i działa po reloadzie.
- [ ] Nie ma regresji parsera zakresów, luk, mutacji checksummowanych ani
  współdzielonego pickera.

## Verification

```powershell
npm run test --workspace @game-predictor/manual-image-selection-core
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

## Outcome

Ukończono `v0.10.105 - stabilize manual selection repair recovery`.

- Pełna inspekcja katalogu nadal sprawdza wszystkie istniejące checksumy, lecz
  nie odczytuje drugi raz JPEG-a, którego checksumę potwierdził już reconciler
  w tej samej inspekcji.
- Workspace komunikuje recovery, wybór katalogu, inspekcję i listowanie
  katalogu bazowego. Manualny wybór unieważnia spóźnione recovery, a nowy
  uchwyt katalogu jest natychmiast zapisywany w IndexedDB.
- Dodano testy regresji pojedynczego odczytu checksummy i obecności ochrony
  recovery/UI.

Weryfikacja:

```powershell
npm run test --workspace @game-predictor/manual-image-selection-core
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npx prettier --check apps/admin/src/features/manual-image-selection/manual-selection-repair-storage.ts apps/admin/src/features/manual-image-selection/manual-selection-repair-workspace.tsx apps/admin/test/manual-selection-repair.test.mjs
```

Wszystkie komendy zakończyły się powodzeniem. Nie uruchamiano OCR, API,
workera, migracji ani mutacji lokalnych katalogów operatora.
