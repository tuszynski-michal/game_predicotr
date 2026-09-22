---
title: TASK-0616 — pojedyncza siatka i odstępy ramki V1.2
status: done
---

# TASK-0616 — pojedyncza siatka i odstępy ramki V1.2

## Status

`done`

## Goal

Operator oznacza jedną siatkę symboli na planszę, a ramka V1.2 powstaje z czterech procentowych odstępów bez ponownego klikania narożników.

## Context

Dotychczasowy edytor wymagał dwóch warstw po dziewięć czworokątów. Kwalifikacje niepełnych plansz były ukryte, gdy operator edytował ramkę.

## Dependencies / entry conditions

- Istniejąca para `boardFrameQuads` i `symbolGridQuads` oraz kwalifikacje slotów pozostają źródłem zapisu.
- Niepowiązane zmiany V2 w worktree nie należą do tego zadania.

## Recommended execution

`gpt-5.6-terra`, reasoning `high`; własny audyt wystarcza, bez dodatkowego review Astra. Ponowna analiza jest wymagana, jeżeli istniejące pary V1.2 nie mogą pozostać bezstratnie czytelne.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`

## Scope

- Jeden przebieg klikania czworokątów siatki; cztery odstępy w procentach wyprostowanej siatki.
- Widoczna kwalifikacja wybranej planszy i osobne oznaczenie 15 pól niepełnej planszy.
- Bezstratny odczyt istniejącej pary i szkicu, bez nadpisania jej samą propozycją.
- Walidacja ramki częściowej poza zdjęciem tylko przy jawnej kwalifikacji niepełnej planszy.

## Out of scope

- Zmiana zwykłego profilu V1.2 i odblokowanie importu (następne zadania).
- V1.0, V1.1, V2.0/V2.1 oraz symbole.

## Acceptance criteria

- [x] Pełna strona wymaga 36 kliknięć zamiast dwóch kompletów.
- [x] Ostatnia strona używa zadeklarowanej liczby plansz.
- [x] Odstępy są niezależne i zachowują perspektywę; ujemny odstęp jest widoczny, ale nie zapisuje ramki bez zawierania siatki.
- [x] Trzy opcje kwalifikacji i 15 pól są dostępne pod wybraną planszą.
- [x] Starsza para może pozostać bez zmian; niepełny nowy szkic nie może zostać zapisany jako potwierdzona ramka.

## Technical notes

`symbolGridQuads` i `finalQuads` pozostają identyczne. Wyprowadzony `boardFrameQuads` nie używa koloru obrazu. Szkic zapisuje częściowo wpisane odstępy; istniejąca para, której nie da się odtworzyć jako czterech odstępów, pozostaje dokładna do czasu świadomego ponownego oznaczenia.

## Expected files

- `apps/admin/src/features/imports/page-geometry-correction-panel.tsx`
- `apps/admin/src/features/imports/page-geometry-draft-storage.ts`
- nowy `apps/admin/src/features/imports/page-geometry-v12-offsets.ts`
- `services/api/src/game_predictor_api/application/page_geometry_overrides.py`
- testy tych kontraktów.

## Test cases

- Perspektywiczna siatka + cztery różne odstępy → poprawna ramka i odtworzenie wartości.
- Ujemny odstęp → podgląd bez zgody na zapis.
- Ramka częściowej planszy poza zdjęciem → zapis kwalifikowany; pełna pozostaje ograniczona do zdjęcia.
- Szkic oraz starsza para → zachowanie danych po odczycie.

## Verification

Skoncentrowane testy Admina i API oraz typecheck, lint i format; wynik w Outcome.

## Risks / open questions

- Rzeczywistą dokładność nakładek Mumii oceni operator po integracji importu.

## Outcome

### Changed

- Edytor V1.2 używa jednej ręcznej siatki oraz procentowych odstępów ramki.
- Kwalifikacje niepełnej planszy są przy wybranej planszy; backend dopuszcza kwalifikowaną ramkę poza źródłem.

### Verification results

- Testy czystych przeliczeń i kontraktu panelu: zaliczone.
- Testy API, w tym pełny test HTTP: 10 zaliczonych.
- Testy interakcji geometrii Admina: 12 zaliczonych.
- Typecheck Admina: zaliczony.
- ESLint zmienionych modułów Admina, Ruff i kontrola formatu: zaliczone.

### Not completed

- Import V1.2 i rzeczywista ocena Mumii należą do kolejnych zadań.

### Documentation updates

- `CURRENT_STATE.md`.

### Recommended next task

- T02: filtrowanie zwykłego profilu i preflightu V1.2 według kwalifikacji.
