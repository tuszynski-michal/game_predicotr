---
title: Telemetria tempa przy wznowieniu przycinania zdjęć
status: done
last_updated: 2026-09-15
---

# TASK-0556 — Telemetria tempa przy wznowieniu przycinania zdjęć

## Status

`done`

## Goal

Po wznowieniu katalogu `cut` UI od razu pokazuje ostatni znany pomiar
równoległości, tempa oraz czasów etapów i jednoznacznie oznacza go jako pomiar
z poprzedniej karty, aż nowa paczka dostarczy bieżące dane.

## Context

`prepareAllSelectedImageCrops` poprawnie odtwarza trwały postęp z manifestu,
ale metryki `averageCommittedMs`, analizy i zapisu są wyłącznie stanem React.
Po restarcie `prepareForReview` ustawia progres bez `performance`, a pierwszy
emit nowego runnera również nie ma jeszcze ukończonego zapisu. Przez ten okres
operator widzi liczbę przygotowanych plików, ale nie tempo ani czasy.

## Dependencies / entry conditions

- TASK-0547 wprowadził bieżącą telemetrię równoległych workerów.
- Lokalny store przycinania przechowuje już wyłącznie stan pomocniczy UI:
  uchwyty katalogu, kursor oraz viewport. Nowe pole będzie opcjonalne i nie
  wymaga migracji IndexedDB.
- Źródłem prawdy dla wyniku cropów pozostają manifest, shardy i session journal;
  telemetria nie może wpływać na recovery, policy, worker ani dane katalogu.

## Recommended execution

`gpt-6-astra` z reasoning `high`: trzeba oddzielić pomocniczy snapshot UI od
trwałego recovery cropów, zachować zgodność historycznych rekordów IndexedDB
i nie prezentować starego tempa jako bieżącego. Ponowna analiza jest wymagana,
jeśli okaże się potrzebna zmiana manifestu cropów albo session journalu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-workspace.tsx`
- `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-local-store.ts`

## Scope

- Przechowanie ostatniej poprawnej próbki telemetrii w lokalnym rekordzie UI.
- Natychmiastowe pokazanie tej próbki po wznowieniu zgodnego katalogu.
- Oznaczenie pomiaru jako poprzedniego do pierwszej bieżącej publikacji i jego
  zastąpienie świeżą telemetrią.
- Test regresji oraz aktualizacja dokumentacji.

## Out of scope

- Zmiana manifestu, session journalu, polityki v12, liczby workerów i algorytmu
  przycinania.
- Dopisywanie telemetrii do katalogu użytkownika, danych importu albo API.
- Szacowanie tempa bez choćby jednej ukończonej próbki.

## Acceptance criteria

- [x] Wznowiony katalog z zapisaną próbką natychmiast pokazuje równoległość,
      tempo i czasy etapów z oznaczeniem „ostatni pomiar”.
- [x] Pierwsza bieżąca publikacja zastępuje snapshot bieżącym pomiarem bez
      oznaczenia historycznego.
- [x] Historyczny rekord IndexedDB bez telemetrii pozostaje czytelny; UI
      pokazuje wtedy czytelny stan oczekiwania na pierwszy bieżący pomiar.
- [x] Snapshot jest powiązany z nazwą i wybraną odmianą katalogu, więc nie
      wyświetla metryk innego źródła.
- [x] Telemetria nie zmienia recovery, plików, manifestu, policy ani kolejności
      publikacji.
- [x] Testy chronią kontrakt lokalnego snapshotu, oznaczenie stanu oraz przejście
      na bieżący pomiar.

## Technical notes

Lokalny session record dostanie opcjonalną próbkę z identyfikatorem katalogu
źródłowego, `sourceSelection`, timestampem i wartościami już zwracanymi przez
`SelectedImageCropPreparationPerformance`. Workspace zapisuje ją wyłącznie po
niepustym `progress.performance`; rejestruje ją z dotychczasowym debounced
zapisem local state. Przy reloadzie stosuje próbkę tylko gdy wybrany katalog i
tryb źródła nadal są zgodne. W wyniku `startOrResume` przygotowanie otrzymuje
ją jako `last measurement`; callback z `performance: null` nie może jej usunąć.
Pierwszy callback z bieżącą próbką ustawia stan `live` i nadpisuje lokalny
snapshot.

Nie wprowadzamy zerowych liczb ani nieskończonego `/min`. Rekord bez próbki
pozostawia aktualny progress i wyświetla tekst, że tempo pojawi się po pierwszej
opublikowanej paczce. Widok jasno odróżnia dawny pomiar od bieżącego, ponieważ
nie można uczciwie wyliczyć aktualnego tempa przed pierwszym commitem nowej
karty.

## Expected files

- Istniejące: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-local-store.ts` — opcjonalny snapshot UI.
- Istniejące: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-workspace.tsx` — dobór, zapis i prezentacja próbki.
- Istniejące: `apps/admin/test/selected-image-crop-workspace-contract.test.mjs` — regresja kontraktu resume telemetry.
- Istniejące: `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md` — zachowanie operatora.
- Istniejące: `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md` — granica trwałego recovery i UI.
- Istniejące: `ai_docs/process/CURRENT_STATE.md` — stan po wykonaniu.
- Istniejące: `ai_docs/process/DECISION_LOG.md` — decyzja o nieautorytatywnym snapshotcie telemetry.

## Test cases

- Rekord lokalny z próbką tego samego katalogu i `sourceSelection` → wznowienie
  pokazuje „ostatni pomiar” i wszystkie wartości.
- Pierwszy callback bez `performance` → nie usuwa odtworzonego snapshotu.
- Callback z bieżącym `performance` → pokazuje bieżące tempo i aktualizuje
  snapshot pomocniczy.
- Rekord bez próbki albo z innym katalogiem/trybem → nie pokazuje obcych liczb,
  tylko oczekiwanie na pierwszy pomiar.
- Przygotowanie i recovery działają identycznie, gdy telemetry nie jest dostępna.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, timeout pojedynczego kroku <= 120 s
node --experimental-strip-types --test apps/admin/test/selected-image-crop-workspace-contract.test.mjs
node_modules\.bin\tsc --project apps/admin/tsconfig.json --noEmit
node_modules\.bin\eslint.cmd src/features/semi-automatic-image-selection/selected-image-crop-workspace.tsx src/features/semi-automatic-image-selection/selected-image-crop-local-store.ts test/selected-image-crop-workspace-contract.test.mjs
node_modules\.bin\prettier --check apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-workspace.tsx apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-local-store.ts apps/admin/test/selected-image-crop-workspace-contract.test.mjs
```

Zaliczenie wymaga zielonych testów, typechecka, lint i formatowania oraz
potwierdzenia, że żaden plik cropa, manifest ani session journal nie został
zmieniony przez telemetry.

## Risks / open questions

- Próbka sprzed restartu nie jest miarą bieżącej przepustowości; dlatego musi
  mieć jawne oznaczenie i zostać zastąpiona po pierwszym nowym commicie.
- Błędy IndexedDB nie mogą blokować przygotowania cropów, ponieważ telemetry jest
  wyłącznie stanem pomocniczym UI.

## Implementation plan

1. Dodać opcjonalny, katalogowo związany snapshot telemetry do local session.
2. Odtwarzać go wyłącznie dla zgodnego resume i utrzymać przez pusty pierwszy
   callback runnera.
3. Zastępować go świeżą próbką, zapisywać z istniejącym debounce i prezentować
   rozróżnienie „ostatni” / „bieżący”.
4. Dodać regresję i zaktualizować dokumentację.

### Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0556 — Telemetria tempa przy wznowieniu przycinania zdjęć | gpt-6-astra | high | Zmiana wymaga rozdzielenia obserwowalności UI od trwałego workflowu danych oraz zachowania zgodności rekordów IndexedDB. | Nie; ponowna analiza gpt-6-astra/high tylko przy potrzebie zmiany manifestu lub journalu. |

## Outcome

### Changed

- `SelectedImageCropLocalSession` ma opcjonalną, powiązaną z katalogiem próbkę
  telemetry przygotowania. Historyczne rekordy bez pola pozostają czytelne.
- Workspace zapisuje ostatnią poprawną próbkę z istniejącym debounce, odtwarza
  ją wyłącznie dla zgodnego katalogu i zakresu oraz oznacza jako „ostatni
  pomiar z poprzedniej karty”. Pierwszy callback z bieżącą próbką automatycznie
  zastępuje oznaczenie historyczne.
- Brak lub niepoprawność próbki daje stan oczekiwania na pierwszą gotową paczkę.
  Snapshot nie zmienia manifestu, session journalu, cropów, policy ani workerów.

### Verification results

- `node --experimental-strip-types --test apps/admin/test/selected-image-crop-workspace-contract.test.mjs` — 12/12.
- `npm.cmd test` w `apps/admin` — zielony.
- `tsc --project apps/admin/tsconfig.json --noEmit`, skoncentrowany ESLint i
  Prettier — zielone.
- `npm.cmd run build` w `apps/admin` — zielony produkcyjny build Next.js.

### Not completed

- Nie uruchamiano rzeczywistego katalogu ani nie zmieniano danych użytkownika;
  odbiór wizualny nastąpi przy kolejnym wznowieniu cięcia.

### Documentation updates

- Zaktualizowano wymagania i architekturę selekcji ręcznej, `CURRENT_STATE.md`
  oraz D-390 w `DECISION_LOG.md`.

### Recommended next task

- Przy następnym wznowieniu katalogu potwierdzić, czy tekst „ostatni pomiar z
  poprzedniej karty” jest wystarczająco czytelny dla operatora.
