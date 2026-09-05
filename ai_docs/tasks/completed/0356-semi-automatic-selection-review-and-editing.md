# TASK-0356 — Review i ręczna edycja półautomatycznej selekcji

Status: `done`

## Cel

Udostępnić końcowy przegląd wszystkich oczekiwanych zakresów oraz bezpieczne,
checksum-bound ręczne dodanie albo zastąpienie źródłowego JPEG-a.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `.tmp/TASK-0350-0357-semi-automatic-selection-plan.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Zakres

- pobranie pełnego, keysetowego snapshotu oczekiwanych zakresów;
- lokalna synchronizacja automatycznych wyborów przed review;
- `REVIEW_MODE` i `EDIT_SOURCE_MODE` ze wspólnym viewerem;
- nawigacja zakresów i źródłowych JPEG-ów z focus guardem;
- ręczne dodanie luki i zastąpienie istniejącego wyboru;
- rozszerzenie istniejącego acknowledgement o opcjonalny, checksum-bound indeks
  ręcznego źródła;
- recovery lokalnego manifestu po przerwaniu ręcznego zapisu.

## Poza zakresem

- zmiana OCR, grupowania i selector policy;
- nowe tabele lub migracja;
- rollout flagi i rzeczywisty odbiór 10/100 zdjęć (TASK-0357);
- automatyczne nadpisywanie istniejącego pliku o niezgodnej checksumie.

## Invarianty

- zakres pozostaje zablokowany podczas edycji źródła;
- istniejący wybór otwiera dokładny `sourceIndex`;
- luka zaczyna od poprzedniego wybranego `sourceIndex + 1`, z fallbackiem 0;
- ręczna mutacja wiąże rewizję zakresu, indeks, ścieżkę, rozmiar i SHA-256;
- docelowy plik może zostać zastąpiony tylko wtedy, gdy jego bieżąca checksumma
  odpowiada wyborowi należącemu do tego samego manifestu;
- IndexedDB i backend nie przechowują bajtów JPEG;
- skróty nie przejmują zdarzeń z pól formularza ani elementów edytowalnych.

## Weryfikacja

- testy domeny API ręcznego acknowledgement;
- testy recovery i manual add/replace lokalnego manifestu;
- kontrakt UI dla review/edit, viewera i focus guarda;
- testy API, Admina i klienta, Ruff, mypy, lint, typecheck, build, OpenAPI i
  format check zmienionych plików.

## Outcome

- Dodano pełny, keysetowy snapshot zakresów oraz lokalną synchronizację przed
  wejściem do review.
- Dodano `REVIEW MODE` i `EDIT SOURCE MODE` ze wspólnym viewerem, focus guardem
  oraz deterministycznym startem źródła dla wyboru i luki.
- Ręczne dodanie i zastąpienie używają journalu, oryginalnych bajtów,
  read-backu SHA-256 i blokady obcego celu.
- Istniejący acknowledgement przyjmuje opcjonalny `sourceIndex`; backend
  ponownie weryfikuje źródło w gotowym stagingu i zapisuje wersjonowaną metodę
  ręcznego wyboru.
- Skoncentrowane testy API i Admina, Ruff, typecheck obu workspace'ów oraz lint
  zmienionych plików przechodzą. Pełny lint Admina pozostaje blokowany przez
  wcześniejszy, niezwiązany błąd hooka w `unreadable-board-review-workspace`.
