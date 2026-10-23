---
title: Persistent selector games and update labels
status: done
last_updated: 2026-10-23
---

# TASK-1088 — Lista gier i aktualizacja w selektorze Windows

## Status

`done`

## Goal

Trwały wybór gry z dodawaniem Enterem i walidowana aktualizacja w historii, dostarczone w paczce Windows 1.0.2.

## Context

Operator zatwierdził zakres i czas 30–45 minut. Aktualizacja ma być widoczna przy nazwie gry w historii, bez zmiany nazw folderów i zdjęć.

## Dependencies / entry conditions

Selektor 1.0.1 na main. Brak pytań blokujących. Zgoda na implementację i paczkę; scalenie wymaga osobnej akceptacji.

## Recommended execution

gpt-6.1-sol / high. Jeden wąski pion Electron i trwałych metadanych; bez delegacji i dodatkowego audytu. Eskalacja przy niezgodności istniejących formatów.

## Relevant docs

- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-571--trwały-katalog-gier-i-aktualizacja-partii-selektora`
- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Niezależny od limitu historii trwały katalog gier; wyszukiwanie, wybór i dodawanie Enterem.
- Wymagana aktualizacja nowych partii: `a` + cyfry lub `z_a` + cyfry, widoczna w historii.
- Odczyt starszych projektów bez aktualizacji; zachowanie nazw eksportu i katalogów.
- Paczka Windows 1.0.2 i kontrole regresji.

## Out of scope

Zmiany API/Admin, importu i nazw plików, scalanie oraz publikacja w zewnętrznym serwisie.

## Acceptance criteria

- [x] Enter dodaje nową grę bez utworzenia projektu; nazwa zostaje po restarcie.
- [x] Lista jest filtrowana, nie dubluje nazw i nie podlega limitowi 10 projektów.
- [x] Nowa partia wymaga poprawnej aktualizacji; native IPC również odrzuca błędne wartości.
- [x] Historia pokazuje grę i aktualizację; metadane przeżywają zapis, wznowienie i nowy proces.
- [x] Starszy projekt działa bez aktualizacji; nazwy plików i folderów są niezmienione.
- [x] Paczka 1.0.2 przechodzi test uruchomienia i nowego workflow.

## Technical notes

Założenia: cyfry aktualizacji są ciągiem ASCII, bez ograniczenia wartości liczbowej (także zero i zera wiodące); brak spacji i sufiksów. Nowy katalog zachowuje pierwszą pisownię nazwy, porównuje bez wielkości liter. Zasila się nazwami dostępnymi w starej historii. Kolejny folder zachowuje grę i aktualizację. Nowa opcjonalna właściwość stanu nie zmienia schematu istniejącego eksportu.

## Expected files

- Istniejące: `apps/selector-desktop/src/contracts.ts`, `main.ts`, `preload.ts`, `native/project-controller.ts`, `project/{types,state-codec,project-storage,project-store,recent-projects}.ts`, `renderer/App.tsx`, style, testy i skrypty smoke.
- Nowe: `apps/selector-desktop/src/native/game-catalog.ts`, `renderer/game-select.tsx`, testy katalogu i skrypt smoke gier.
- Dokumentacja obszaru, mapa kodu, wersja paczki i raport jakości.

## Test cases

Restart po dodaniu gry; ponad 10 nazw; duplikaty i uszkodzony katalog; poprawne i błędne aktualizacje; zapis i ponowny odczyt projektu; stary projekt; obsługa Entera, dropdownu i historii w paczce.

## Verification

Komendy uruchamiane z timeoutem przez `node apps/selector-desktop/scripts/run-bounded.mjs 120 ...`: testy zmienionego pionu, lint, typecheck, build, smoke wydania oraz `npm run docs:check` i `npm run code-map:check`. Build wydania ma własny limit 110 s. Zakończenie po zielonych kontrolach i gotowej paczce.

## Risks / open questions

Brak otwartych pytań. Starsza historia udostępnia najwyżej 10 dotychczasowych nazw; pozostałych nie odtwarzamy przez skanowanie dysku.

## Outcome

Commit: v1.7.467 / `6909ef00c73d29cdb176db7a4cd2ddcfc4d7083d`.

### Changed

- Niezależny trwały GameCatalog, typowane IPC i combobox z filtrem oraz dodawaniem Enterem. Deduplikacja i import dostępnych nazw z historii.
- Wymagana walidowana aktualizacja nowej partii, opcjonalne metadane starszych projektów w journal/ledger/backup oraz etykiety historii i aktywnej partii. Kolejny folder zachowuje obie wartości.
- Wersja 1.0.2, skrypt smoke gier i aktualizacja formularzy dotychczasowych testów. Nazwy eksportu i folderów bez zmian.

### Verification results

- 27/27: start-resume, game-catalog, renderer-contracts; 2/2: release.
- Lint, typecheck, build wydania, SHA-256 i zawartość rozpakowanego ZIP-a: PASS.
- Smoke workflow i games: PASS, w tym katalog zapisany przed utworzeniem projektu i historia po nowym procesie.
- Końcowa paczka 1.0.2 z commita v1.7.467, applicationSourceDirty=false: ponowny smoke games PASS. Kopia ZIP w `artifacts/selector-releases/1.0.2/`, SHA-256 i parametry w raporcie jakości.
- docs:check i code-map:check: PASS przed zamknięciem, ponowna kontrola dokumentacji po zamknięciu.
- Kryteria akceptacji porównane punkt po punkcie: wszystkie spełnione. DoD: trwałość sprawdzona w nowym procesie; brak zmiany backendu i bazy, dlatego OpenAPI/Alembic nie dotyczą. UI przeznaczone wyłącznie dla Windows.

### Not completed

- Fizyczny restart systemu i drugi komputer nie były objęte weryfikacją. Jedna próba smoke przy równoległym obciążeniu zwróciła ATTRIBUTE_SCAN_FAILED; samodzielne ponowienie przeszło, zabezpieczenia bez zmian.
- Brak scalenia i push — wymagają osobnej akceptacji wyniku. Audyt krzyżowy nie był wymagany; brak delegacji.

### Documentation updates

- D-571, wymagania, architektura, mapa kodu i raport `ai_docs/quality/SELECTOR_GAMES_UPDATES_1_0_2_20261023.md`.

### Recommended next task

Odbiór paczki 1.0.2 przez operatora; po akceptacji scalenie do main.
