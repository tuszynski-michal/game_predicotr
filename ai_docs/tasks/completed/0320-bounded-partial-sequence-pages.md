---
title: TASK-0320 bounded partial sequence pages
status: done
last_updated: 2026-08-30
---

# TASK-0320 — Ograniczone końcowe strony `seq_*`

## Status

`done`

## Goal

Ręczna selekcja ma zapisywać ostatnią stronę jako ciągły zakres 1–9 plansz
ograniczony jawnym maksymalnym numerem, a import gry ma blokować zakresy
wychodzące poza `expectedLayoutCount`.

## Context

Kontrakt TASK-0307 poprawnie dopuszcza częściową stronę jako aktywny prefiks
row-major. Generator ręcznej selekcji nadal jednak zawsze dopisywał osiem do
numeru początkowego. Dla katalogu kończącego się na planszy `500000` utworzył
przez to niespójny manifest `seq_499996-500004`, mimo że prawidłowym plikiem
jest `seq_499996-500000.jpg`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Dodać do lokalnej i operator-local ręcznej selekcji opcjonalny
  `sequenceUpperBound`.
- Wyliczać końcowy zakres jako `start..min(start+8, sequenceUpperBound)`.
- Zatrzymać decyzje po osiągnięciu górnej granicy albo dolnej granicy w trybie
  malejącym, z zachowaniem możliwości cofnięcia.
- Zapisywać manifest schema v2 z granicą i liczbą aktywnych plansz; czytać
  istniejący schema v1 bez zmiany jego semantyki.
- Walidować zgodność decyzji, nazw plików, granicy i checksum fail-closed.
- Dodać read-only dry-run diagnostyczny dla starego manifestu i fizycznych nazw
  `seq_*`; nie modyfikować katalogu użytkownika.
- Blokować preflight importu, jeżeli poświadczony zakres przekracza
  `games.expected_layout_count`.

## Out of scope

- Bez migracji bazy lub IndexedDB.
- Bez automatycznej naprawy istniejących plików i manifestów użytkownika.
- Bez zmiany logical/render identity, silnika geometrii i rolloutu 0.10.
- Bez zmian historycznego host-transfer wariantu zdalnej selekcji.

## Acceptance criteria

- [x] `rangeForStart(499996, 500000)` daje `499996–500000` i pięć aktywnych plansz.
- [x] Lokalny oraz operator-local workspace nie zapisują kolejnej decyzji po granicy.
- [x] Nowy manifest v2 odtwarza granicę, terminalny stan i częściowy zakres.
- [x] Manifest v1 nadal wznawia wyłącznie pełne zakresy dziewięcioplanszowe.
- [x] Niespójność `seq_499996-500000.jpg` kontra wpis `499996–500004` jest raportowana bez zapisu.
- [x] Preflight gry odrzuca zakres z numerem powyżej `expectedLayoutCount`.
- [x] Testy Admina, Reviewera, wspólnego core i API przechodzą.

## Expected files

- `packages/manual-image-selection-core/src/index.ts`
- `apps/admin/src/features/manual-image-selection/*`
- `apps/reviewer/src/features/manual-selection/*`
- `services/api/src/game_predictor_api/domain/image_sequence_canonical.py`
- `services/api/src/game_predictor_api/storage/image_sequence_canonical_repository.py`
- testy odpowiadających modułów
- dokumentacja ręcznej selekcji i importu

## Verification

```powershell
npm test --workspace @game-predictor/manual-image-selection-core
npm test --workspace @game-predictor/admin
npm test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/manual-image-selection-core
npm run typecheck --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/reviewer
.venv\Scripts\python.exe -m pytest services/api/tests/test_image_sequence_canonical.py -q
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/domain/image_sequence_canonical.py services/api/src/game_predictor_api/storage/image_sequence_canonical_repository.py services/api/tests/test_image_sequence_canonical.py
```

## Risks / open questions

- Plik manifestu zachowuje historyczną nazwę
  `manual-image-selection-output-v1.json`, aby nie tworzyć dwóch konkurencyjnych
  źródeł wznowienia. Wersję kontraktu rozstrzyga `schemaVersion`.
- Istniejący niezgodny katalog wymaga osobnej, jawnej naprawy po ocenie dry-run.

## Outcome

Wspólny core, lokalny Admin i operator-local Reviewer obsługują opcjonalny
`sequenceUpperBound`, częściową końcową stronę oraz trwały stan terminalny.
Writer zachowuje nazwę pliku manifestu, ale zapisuje schema v2 z
`activeBoardCount`; reader nadal obsługuje schema v1. Cofnięcie otwiera sesję,
a kolejna decyzja po granicy jest blokowana również wewnątrz serializowanej
kolejki.

Dodano read-only narzędzie
`scripts/preview_manual_selection_manifest_v2.mjs`, które weryfikuje checksumy
i pokazuje proponowany manifest v2 bez zapisu. Preflight `seq_*` odrzuca zakres
wychodzący poza `games.expected_layout_count`; prawidłowa końcówka
`499996–500000` przechodzi jako pięć plansz.

Weryfikacja:

- core: 18 testów;
- Admin: 305 testów, typecheck, lint i build;
- Reviewer: 163 testy, typecheck, lint i build;
- API: 9 testów preflightu, Ruff i mypy zmienionych modułów;
- `git diff --check` bez błędów.

Nie wykonano migracji ani automatycznej naprawy istniejącego katalogu
użytkownika.
