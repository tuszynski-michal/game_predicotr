---
title: Jawny wybór cropów do ręcznej poprawki
status: done
last_updated: 2026-09-15
---

# TASK-0548 — jawny wybór cropów do ręcznej poprawki

## Status

`done`

## Goal

Nie zaznaczać automatycznie wszystkich zdjęć ostrzeżonych przez detektor jako
przeznaczonych do ręcznej poprawki. Operator ma wskazywać pojedyncze zdjęcia,
mieć stale dostępne osobne akcje `Zaznacz wszystkie` i `Odznacz wszystkie`, a
zakończenie przeglądu ma jawnie zaakceptować pozostałe, niewybrane ostrzeżenia.

## Context

Detektor v12 zachowuje konserwatywną kolejkę ostrzeżeń. Obecny adapter kopiuje
każde ostrzeżenie do `correctionFileNames`, a UI buduje zaznaczenie z sumy
wyborów operatora i nierozstrzygniętych ostrzeżeń. W efekcie dobrze przycięte
zdjęcia mają border wyboru i wszystkie trafiają do ręcznego edytora. Jeden
przycisk zmienia etykietę między zaznaczeniem i odznaczeniem całości, więc obie
akcje nie są stale dostępne.

## Dependencies / entry conditions

- TASK-0547 jest ukończony na gałęzi `codex/crop-performance`.
- Trwałe `correctionFileNames` pozostaje źródłem prawdy dla jawnego wyboru
  operatora; dowód detektora pozostaje w shardzie.
- Nie zmieniamy detektora v12, fingerprintu, plików JPEG ani danych w `D:\777`.

## Recommended execution

`gpt-6-astra` z reasoning `high`. Zmiana dotyka znaczenia utrwalonego review i
bramki zakończenia, więc wymaga testu regresyjnego nowych oraz istniejących
sesji. Dodatkowy review jest potrzebny tylko przy zmianie schematu pliku review
albo algorytmu detekcji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Scope

- Nie dodawać automatycznego ostrzeżenia do `correctionFileNames` podczas
  przygotowania ani przeliczenia.
- Rysować border wyboru i liczyć `Popraw zaznaczone` wyłącznie z trwałego,
  jawnego `correctionFileNames`.
- Pozostawić ostrzeżenia w filtrze `Niepewne` oraz pokazać ich oddzielny
  licznik bez nazywania ich obowiązkową poprawką.
- Rozdzielić akcję zbiorczą na dwa stale widoczne przyciski: `Zaznacz wszystkie`
  i `Odznacz wszystkie`, działające na przygotowanych zdjęciach bieżącego
  filtra i zachowujące wybory ukryte przez filtr.
- Jawne odznaczenie ostrzeżenia akceptuje automatyczną propozycję. Jawne
  `Zatwierdź i zakończ przegląd` akceptuje wszystkie pozostałe niewybrane
  ostrzeżenia, ale nadal blokuje się dla wybranych poprawek, failures, pending
  i nieprzygotowanych wyników.
- Zachować możliwość odznaczenia wpisów utrwalonych przez wcześniejszą wersję;
  nie wykonywać automatycznej migracji decyzji operatora.
- Dodać testy domenowe i kontraktowe oraz zaktualizować dokumentację.

## Out of scope

- Zmiana progów, klasyfikacji lub fingerprintu v12.
- Automatyczne czyszczenie istniejących `correctionFileNames`.
- Zmiana schematu review, migracja danych albo modyfikacja gotowych JPEG-ów.
- Przełączenie działających kart przed zakończeniem trwającego cięcia.

## Acceptance criteria

- [x] Nowe automatyczne ostrzeżenie nie otrzymuje borderu i nie trafia do
      `Popraw zaznaczone`, dopóki operator nie kliknie jego miniaturki.
- [x] Filtr `Niepewne` nadal pokazuje wszystkie nierozstrzygnięte ostrzeżenia.
- [x] Pojedyncze kliknięcie dodaje zdjęcie do poprawki, a kolejne je usuwa i
      akceptuje propozycję tylko wtedy, gdy zdjęcie miało ostrzeżenie.
- [x] `Zaznacz wszystkie` i `Odznacz wszystkie` są jednocześnie widoczne i
      obejmują wyłącznie przygotowane zdjęcia bieżącego filtra.
- [x] Zakończenie akceptuje niewybrane ostrzeżenia, ale nie omija jawnie
      wybranej poprawki, failure, pending ani brakującego wyniku.
- [x] Istniejące zapisane wybory pozostają zaznaczone do jawnego odznaczenia.
- [x] Testy skoncentrowane, pełny Admin, typecheck, lint i build przechodzą.

## Technical notes

W UI powstaną dwa zbiory. `selectedCorrectionFileNames` zawiera wyłącznie
`snapshot.review.correctionFileNames` i steruje borderem, licznikiem oraz
edytorem. `automaticWarningFileNames` wynika z
`requiredSelectedImageCropCorrections` i steruje filtrem oraz licznikiem
ostrzeżeń. Zbiory mogą się przecinać, ale nie są łączone dla prezentacji
wyboru.

Zbiorcze zaznaczenie dodaje widoczne nazwy do istniejącego wyboru w kolejności
inwentarza. Zbiorcze odznaczenie usuwa tylko widoczne nazwy; widoczne
ostrzeżenia przekazuje jako jawnie zaakceptowane sugestie. Zakończenie buduje
review z pustą kolejką korekt, sumą dotychczas zaakceptowanych i wszystkich
pozostałych wymaganych ostrzeżeń, kompletnym `reviewedFileNames` oraz
`completedAt`.

## Expected files

- `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-workspace.tsx`
- `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-storage.ts`
- `packages/manual-image-selection-core/src/crop-session.ts`
- testy workspace, storage i crop session
- wymagania, architektura, `CURRENT_STATE.md` i decision log

## Test cases

- Nowy wynik z automatycznym ostrzeżeniem → brak wpisu w
  `correctionFileNames`, ostrzeżenie pozostaje w required/filterze.
- Kliknięcie ostrzeżonego kafelka → jawny wybór; drugie kliknięcie → brak
  wyboru i wpis w `acceptedSuggestionFileNames`.
- Zaznaczenie całości w filtrze `Niepewne` → tylko widoczne ostrzeżenia trafiają
  do wyboru; ukryte wybory zostają.
- Odznaczenie całości w filtrze → tylko widoczne wybory są usunięte i widoczne
  ostrzeżenia zaakceptowane.
- Zakończenie z zerem jawnych wyborów i dwoma ostrzeżeniami → oba zaakceptowane,
  review zakończone.
- Zakończenie z jednym jawnym wyborem albo failure → stabilny
  `SELECTED_IMAGE_CROP_REVIEW_INCOMPLETE`.

## Verification

```powershell
node --experimental-strip-types --test --test-isolation=none apps/admin/test/selected-image-crop-storage-contract.test.mjs apps/admin/test/selected-image-crop-workspace-contract.test.mjs packages/manual-image-selection-core/test/selected-image-crop-session.test.mjs
npm run typecheck --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/manual-image-selection-core
npm run lint --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
```

## Risks / open questions

- `Odznacz wszystkie` jest świadomą akceptacją widocznych automatycznych
  ostrzeżeń. Przycisk działa tylko w bieżącym filtrze, aby nie ukrywać decyzji
  poza widokiem.
- Nie ma pytań blokujących; polecenie użytkownika rozstrzyga, że wybór do
  poprawki ma należeć do operatora.

## Outcome

Zadanie ukończone 2026-09-15 w osobnym worktree, bez przeładowania działających
kart i bez modyfikacji danych użytkownika.

### Changed

- Border i kolejka ręcznego edytora korzystają wyłącznie z jawnego
  `correctionFileNames`. Automatyczne ostrzeżenia pozostają osobnym filtrem i
  licznikiem.
- Przygotowanie i przeliczenie nie zaznaczają ostrzeżonych zdjęć. Pojedynczy
  kafelek nadal pozwala dodać lub usunąć wybór.
- Dodano jednocześnie widoczne akcje `Zaznacz wszystkie` i `Odznacz wszystkie`
  ograniczone do bieżącego filtra.
- Końcowa akcja akceptuje niewybrane ostrzeżenia, zachowując blokady dla
  jawnych poprawek, failures, pending i brakujących wyników.

### Verification results

- Skoncentrowane testy storage, workspace i crop session: 42/42.
- Pełny zestaw testów Admina: 485/485.
- Pełny zestaw testów `manual-image-selection-core`: 99/99.
- Typecheck Admina i core, lint Admina oraz Prettier: kod 0.
- Produkcyjny build Admina: kod 0; kompilacja, TypeScript i generowanie stron
  zakończone poprawnie.

### Not completed

- Nie przełączono kart korzystających z głównego worktree, aby nie przerwać
  aktywnego cięcia. Nie zmieniono istniejących wyborów w plikach review.

### Documentation updates

- Uzupełniono wymagania, architekturę, `CURRENT_STATE.md` i decyzję D-386.

### Recommended next task

- Po zakończeniu obecnego cięcia przełączyć aplikację na commity TASK-0547 i
  TASK-0548 oraz potwierdzić na jednym katalogu, że ostrzeżenia nie dostają
  borderu przed kliknięciem operatora.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0548 — jawny wybór cropów do ręcznej poprawki | gpt-6-astra | high | Zmiana rozdziela automatyczne ostrzeżenie od trwałej decyzji operatora i musi zachować recovery. | Nie; o ile schema review i detektor pozostają bez zmian. |
