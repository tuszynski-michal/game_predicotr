---
title: Katalogi cut w wyborze uzupełnionych luk
status: done
last_updated: 2026-09-15
---

# TASK-0546 — katalogi cut w wyborze uzupełnionych luk

## Status

`done`

## Goal

Po wybraniu `Tylko uzupełnione luki z manifestu` lista pokazuje każdy
bezpośredni katalog, także zakończony ` cut`, który zawiera manifest aktywnych
uzupełnień, i nie proponuje katalogu wynikowego `filled-gaps cut`.

## Context

Lista katalogów jest obecnie budowana raz po wyborze katalogu nadrzędnego i
bezwarunkowo odrzuca nazwy zakończone ` cut`. Zmiana zakresu nie odświeża listy.
W `D:\777` istnieją katalogi `* cut` z
`manual-image-selection-filled-gaps-v1.json`, więc operator nie może uruchomić
dla nich istniejącego trybu ograniczonego.

## Dependencies / entry conditions

- TASK-0519 dostarcza checksum-bound handoff aktywnych uzupełnień.
- TASK-0545 chroni zapis jednego katalogu przed równoległymi kartami.
- Katalogi i manifesty użytkownika pozostają tylko do odczytu podczas poprawki.

## Recommended execution

`gpt-6-astra` z poziomem `high`. Zmiana dotyka wyboru katalogu, tożsamości
źródła i wyprowadzenia katalogu wynikowego. Dodatkowy review jest potrzebny,
jeżeli zakres miałby objąć rekurencyjne katalogi albo scalić wynik z istniejącym
`cut`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Scope

- Uzależnić kwalifikację katalogu od trybu `all | filled_gaps`.
- W trybie pełnym zachować dotychczasowe ukrywanie katalogów `* cut`.
- W trybie luk pokazywać bezpośrednie katalogi z handoffem, w tym `* cut`, ale
  wykluczyć pochodne `* filled-gaps cut`.
- Odświeżyć opcje po zmianie trybu i zachować wybraną nazwę tylko, gdy nadal
  jest dostępna.
- Pokazywać wybór trybu również wtedy, gdy lista trybu pełnego jest pusta.

## Out of scope

- Przenoszenie, łączenie lub usuwanie JPEG-ów i katalogów.
- Zmiana formatu repair manifestu albo algorytmu cięcia.
- Rekurencyjne skanowanie katalogów.

## Acceptance criteria

- [x] `foo cut` z manifestem jest widoczny w trybie `filled_gaps`.
- [x] `foo cut` pozostaje niewidoczny w trybie `all`.
- [x] `foo filled-gaps cut` nie jest proponowany jako ponowne źródło.
- [x] Przełączenie trybu przebudowuje listę bez ponownego wyboru katalogu
      nadrzędnego.
- [x] Brak opcji nie blokuje dostępu do selektora trybu.

## Technical notes

Źródłem kwalifikacji jest nazwa bezpośredniego podkatalogu i obecność pliku
`FILLED_GAPS_MANIFEST_NAME`. Pełna walidacja zawartości, powiązania nazwy oraz
SHA-256 pozostaje w `prepareSelectedImageCropDirectory`; samo listowanie nie
uznaje manifestu za poprawny wynik. Dla źródła `foo cut` wynik ograniczony ma
nazwę `foo cut filled-gaps cut` i nie jest później ponownie kwalifikowany.

## Expected files

- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-storage.ts`.
- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-workspace.tsx`.
- Proponowany: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-directory-options.ts`.
- Testy w `apps/admin/test/`.
- Wymagania, architektura i `CURRENT_STATE.md`.

## Test cases

- `all`: zwykły katalog jest widoczny, `* cut` jest ukryty.
- `filled_gaps`: zwykły i `* cut` z handoffem są widoczne; brak handoffu i
  `* filled-gaps cut` są ukryte.
- Kontrakt UI wymaga odświeżenia listy po zmianie trybu i niezależnego
  renderowania selektora trybu.

## Verification

```powershell
node --experimental-strip-types --test --test-isolation=none apps/admin/test/selected-image-crop-directory-options.test.mjs apps/admin/test/selected-image-crop-storage-contract.test.mjs apps/admin/test/selected-image-crop-workspace-contract.test.mjs
npm --workspace @game-predictor/admin run typecheck
npm --workspace @game-predictor/admin run lint
npm --workspace @game-predictor/admin test
npm --workspace @game-predictor/admin run build
```

Kryterium zaliczenia: testy, typecheck, lint i build są zielone, a odczyt
rzeczywistych nazw w `D:\777` potwierdza widoczność katalogów `* cut` z
manifestem bez modyfikowania danych.

## Risks / open questions

- Uszkodzony manifest może być widoczny na liście; start zachowuje istniejący
  stabilny błąd walidacji zamiast ukrywać problem.

## Outcome

### Changed

- Dodano czystą kwalifikację nazw zależną od trybu i obecności handoffu.
- Lista katalogów jest odświeżana po zmianie zakresu, a bieżący wybór pozostaje
  tylko wtedy, gdy nadal należy do nowych opcji.
- Wybór zakresu przeniesiono przed listę katalogów i uniezależniono od jej
  niepustości.

### Verification results

- 29/29 skoncentrowanych testów przeszło.
- Pełny zestaw Admina przeszedł 478/478.
- Typecheck Admina przeszedł.
- Lint, formatowanie oraz produkcyjny build Admina przeszły.
- Odczyt rzeczywistych katalogów potwierdził cztery źródła `* cut` z handoffem;
  nie zapisano ani nie usunięto danych użytkownika.

### Not completed

- Brak.

### Documentation updates

- Zaktualizowano wymagania, architekturę i `CURRENT_STATE.md`.

### Recommended next task

- Brak; po odświeżeniu strony należy potwierdzić listę dla `D:\777`.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0546 | gpt-6-astra | high | Zmiana obejmuje kwalifikację katalogów, asynchroniczny stan UI i ochronę przed rekurencyjnym wyborem outputu. | Nie; `gpt-6-astra` z `xhigh` tylko przy zmianie formatu manifestu albo scalaniu katalogów. |
