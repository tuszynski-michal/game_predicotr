---
title: Większy bufor cięcia wybranych zdjęć
status: done
last_updated: 2026-09-15
---

# TASK-0553 — Większy bufor cięcia wybranych zdjęć

## Status

`done`

## Goal

Automatyczne cięcie zachowuje wyraźnie większy zapas nad i pod panelem plansz, bez naruszenia zapisanych sesji ani granic obrazu.

## Context

Operator zgłosił, że automatycznie wycięty pas przebiega zbyt blisko plansz. Margines powstaje zarówno w bezpośrednim wykryciu układu v11, jak i w rejestracji v12 względem kotwicy.

## Dependencies / entry conditions

- Aktywna polityka to v12, a kompletna struktura v11 pozostaje jej szybką ścieżką.
- Istniejące wyniki v12 są przypięte fingerprintem i muszą pozostać czytelne po zmianie.

## Recommended execution

`gpt-5.6-sol`, reasoning `medium`. Zmiana jest ograniczona do deterministycznych granic i zgodności trwałego fingerprintu; eskalacja do niezależnego review jest potrzebna tylko, jeżeli testy ujawnią zmianę kontraktu zapisanych wyników.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Zwiększyć pionowy bufor bezpośredniego cropa v11: górny do 45% mediany wysokości planszy, dolny do 40%, a dolny bufor ścieżki bez etykiet do 80%.
- Zwiększyć bufor cropa rejestracji v12 do 45% wysokości planszy.
- Zachować odczyt fingerprintów v12 utworzonych przed zmianą.
- Dodać testy dokładnych granic i zgodności historycznego fingerprintu.

## Out of scope

- Zmiana szerokości cropa, detekcji układu, progów rejestracji, danych katalogów `cut` lub ponowne liczenie istniejących zdjęć.

## Acceptance criteria

- [x] Nowe automatyczne propozycje mają większy bufor w obu ścieżkach v11/v12.
- [x] Crop nigdy nie wykracza poza źródło i nadal przechodzi istniejące ograniczenia wysokości.
- [x] Zapisane wyniki z poprzednim fingerprintem v12 pozostają poprawne przy odczycie.
- [x] Testy core, typecheck i build core przechodzą.

## Technical notes

Źródłem granic pozostają `auto-crop-v11-boundaries.ts:boundStructuralCrop` i `auto-crop-v12-registration.ts:cropFromRegisteredBoardBand`. Zmiana jest wersjonowana przez bieżące fingerprinty. Wartości poprzedniej konfiguracji są zamrożone w legacy fingerprintach; kompatybilność dotyczy odczytu, natomiast browserowy worker nadal wymaga bieżącego fingerprintu. Gdy powiększony pas przekracza istniejący limit 78% wysokości źródła, v12 skraca wyłącznie nadmiar buforu symetrycznie wokół plansz; pas samych plansz większy od limitu nadal zostaje odrzucony.

Przykład: dla planszy o wysokości 60 px na poziomie analizy i skali źródła 2, górny zapas v11 rośnie z 40 px do 58 px, a dolny z 28 px do 52 px. Wynik nadal jest ograniczany do `0..source.height`.

## Expected files

- Istniejące: `packages/manual-image-selection-core/src/auto-crop-v11.ts` — konfiguracja i fingerprint v11.
- Istniejące: `packages/manual-image-selection-core/src/auto-crop-v12-registration.ts` — konfiguracja oraz zgodność fingerprintu v12.
- Istniejące: `packages/manual-image-selection-core/test/selected-crop-v11-boundaries.test.mjs` — granice v11.
- Istniejące: `packages/manual-image-selection-core/test/selected-crop-v12-registration.test.mjs` — bufor i zgodność v12.
- Istniejące: `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`, `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`, `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Pełny układ i komplet etykiet → większy górny oraz dolny zapas z ograniczeniem do źródła.
- Pełny układ bez kompletu etykiet → większy, wersjonowany dolny zapas.
- Zarejestrowany pas → crop otrzymuje 45% wysokości planszy z obu stron.
- Fingerprint v12 sprzed zmiany → jest przyjmowany przez odczyt trwałej propozycji.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, timeout 120 s
npm --workspace @game-predictor/manual-image-selection-core test
npm --workspace @game-predictor/manual-image-selection-core run typecheck
npm --workspace @game-predictor/manual-image-selection-core run build
```

## Risks / open questions

- Większy pas może objąć więcej tła ekranu, dlatego nie zmieniamy granic szerokości ani maksymalnej wysokości cropa.

## Outcome

### Changed

- v11 zachowuje większy zapas nad i pod panelem, także w ścieżce bez kompletnego pasa numerów.
- v12 zachowuje 45% wysokości planszy po obu stronach rejestrowanego pasa, a przy bardzo niskim źródle ogranicza wyłącznie nadmiar buforu do istniejącego limitu wysokości.
- Odczyt przyjmuje bieżący oraz dwa wcześniejsze fingerprinty v12; nowe wyniki zawsze zapisują bieżący fingerprint.

### Verification results

- `npm --workspace @game-predictor/manual-image-selection-core test`: 103 passed.
- `npm --workspace @game-predictor/manual-image-selection-core run typecheck`: passed.
- `npm --workspace @game-predictor/manual-image-selection-core run build`: passed.

### Not completed

- Nie uruchamiano ponownego cięcia istniejących katalogów `cut`.

### Documentation updates

- Zaktualizowano wymaganie, architekturę i `CURRENT_STATE.md`.

### Recommended next task

- Po odświeżeniu otwartej karty ocenić nowe propozycje na kolejnej paczce bez zmiany już zapisanych cropów.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0553 | gpt-5.6-sol | medium | Wystarcza do deterministycznej zmiany konfiguracji, kompatybilności fingerprintu i testów regresji. | Nie, chyba że ujawni się niezgodność danych zapisanych. |
