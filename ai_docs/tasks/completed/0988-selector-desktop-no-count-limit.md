---
title: TASK-0988 — Selektor bez limitu liczby zdjęć
status: done
last_updated: 2026-10-13
---

# TASK-0988 — Selektor bez limitu liczby zdjęć

## Status

`done`

## Goal

Źródła i projekty z 20–30 tysiącami JPEG-ów nie są odrzucane z powodu liczby plików.

## Context

Operator2026-10-12 polecił natychmiast usunąć limit15 000. Jest to zmiana
wymagania pierwszego pilota, a nie zmiana reguł numeracji lub ochrony plików.

## Dependencies / entry conditions

Gotowe0.1.3, branch codex/offline-photo-selector, HEAD v1.7.339 /e596787f.
Brak zmian użytkownika w śledzonych plikach. Nie ma pytań blokujących.

## Recommended execution

gpt-6.1-sol / medium zgodnie z planem. Mała zmiana istniejących walidacji;
audyt operatora na końcu zgodnie z D-545/D-546.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_NO_COUNT_LIMIT_PLAN.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md

## Scope

- Usunięcie limitu JPEG-ów, limitu wpisów skanu i limitu inventory projektu.
- Regresje30 000 metadanych źródła i trwałego formatu projektu.
- ZIP0.1.4, a przy zamknięciu aktualne wydanie1.0.0 oraz instrukcja operatora. Instrukcja Word odroczona osobnym poleceniem użytkownika.

## Out of scope

Benchmarki, nowy format projektu, sieć, usługi głównej aplikacji i zmiany danych użytkownika.

## Acceptance criteria

- [x] Kod nie ma liczbowej blokady kolekcji ani skanowania źródła.
- [x] Indeks30 000 JPEG-ów zachowuje naturalną kolejność.
- [x] Stan30 000 pozycji po serializacji/odczycie nadal przechodzi walidację.
- [x] Testy dotychczasowej ochrony ścieżek i projektów pozostają zielone.
- [x] Nowy ZIP i aktualna instrukcja operatora nie deklarują limitu15 000. Word pozostaje osobnym zadaniem na polecenie użytkownika.

## Technical notes

Usunąć MAX_SOURCE_IMAGES i SOURCE_TOO_LARGE przy skanowaniu, a także
inventory.length >15000 w validateStateStructure. Nie dodawać Infinity ani
nowego większego limitu. Pamięć i czas skanu nadal zależą od rozmiaru kolekcji;
historyczne pomiary nie są dowodem czasu dla większego źródła.

## Expected files

- apps/selector-desktop/src/native/source-registry.ts — scanSource.
- apps/selector-desktop/src/project/state-codec.ts — validateStateStructure.
- apps/selector-desktop/test/foundation.test.mjs i compact-persistence.test.mjs.
- apps/selector-desktop/package.json, package-lock.json.
- Wymagania, architektura, decyzja i mapa kodu.
- Ignorowane artefakty ZIP i instrukcji Word.

## Test cases

- Kontrolowany katalog z30 000 metadanych JPEG, bez tworzenia masowego zbioru plików.
- State schema1 z30 000 pozycji i kursorem ostatniego zdjęcia przechodzi encode/decode/validate.
- Dotychczasowe symlinki, niezgodny plik, restart, recovery i oba kierunki pozostają zgodne.

## Verification

Z worktree, Windows PowerShell:

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:foundation --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 node --experimental-strip-types --test apps/selector-desktop/test/compact-persistence.test.mjs
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 45 npm run lint --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 45 npm run typecheck --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run release --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:start --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run docs:check
node apps/selector-desktop/scripts/run-bounded.mjs 45 npm run code-map:check
```

## Risks / open questions

Nie zmierzono większych rzeczywistych kolekcji. Nie jest to blokada funkcjonalna.
Fizyczny odbiór odbiorcy i audyt operatora pozostają osobne.

## Outcome

### Changed

Usunięto ograniczenia zdjęć i wpisów katalogowych bez zmiany kontroli plików. Commit v1.7.340 / ccb9526e4b29d5586eba1927d592d82149a5fb43. Dokumentację odłożono na polecenie operatora; uzupełniono przy wydaniu1.0.0.

### Verification results

Desktop264/264 PASS w bounded grupach, lint/typecheck/format PASS; indeks30 000 JPEG +100 001 pomijanych wpisów i stan30 000 obu kierunków PASS. Release0.1.4, full/start obu kierunków PASS; świeży1.0.0 również full/UX/start PASS.

### Not completed

Niezależny audyt ostatnich zmian nie jest wykonany. Odbiór zatwierdził operator D-547; brak fizycznych dowodów nie jest oznaczony jako PASS.

### Documentation updates

Plan i task przygotowane przed kodowaniem w ignorowanych artefaktach. Repozytoryjny zapis wykonany po odroczeniu dokumentacji przez operatora.

### Recommended next task

Osobna aktualizacja instrukcji Word.
