---
title: TASK-0442 — Manifest uzupełnionych luk dla lokalnego cropowania
status: done
last_updated: 2026-09-04
---

# TASK-0442 — Manifest uzupełnionych luk dla lokalnego cropowania

## Goal

Zapisać deterministyczną listę aktywnych plików `seq_*`, którymi operator
uzupełnił luki w `Popraw selekcję`, oraz pozwolić przekazać dokładnie tę listę
do `Semi-auto selekcja → Przytnij wybrane zdjęcia`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Scope

- pochodny manifest aktywnych uzupełnień, synchronizowany z repair manifestem,
- odtworzenie listy także dla historycznego repair manifestu,
- osobny tryb cropowania tylko aktywnych uzupełnień,
- osobny katalog wynikowy, aby nie kolidować z pełną sesją cropowania,
- walidacja nazwy, zakresu i checksummy przed rozpoczęciem pracy.

## Out of scope

- automatyczne przycinanie lub usuwanie istniejących zdjęć,
- zmiana importu plansz, API albo bazy danych,
- kopiowanie zdjęć pomiędzy katalogami użytkownika.

## Acceptance criteria

- fill pojawia się w handoffie, a undo/delete usuwa go z aktywnej listy,
- ponowne otwarcie starego repair manifestu odtwarza handoff,
- cropowanie może objąć wyłącznie wskazane, nadal zgodne pliki,
- pełne cropowanie zachowuje dotychczasowe zachowanie i katalog `<źródło> cut`,
- sesja uzupełnień używa osobnego katalogu i wznawia ten sam zakres.

## Outcome

- Dodano pochodny `manual-image-selection-filled-gaps-v1.json`, zawierający
  wyłącznie aktywne uzupełnienia związane z repair revision i checksumami.
- Tryb `Tylko uzupełnione luki z manifestu` weryfikuje każdy plik i używa
  osobnego katalogu `<źródło> filled-gaps cut`.
- Nie wykonano żadnej operacji na rzeczywistych katalogach ani zdjęciach
  operatora; nie zmieniono API, bazy danych ani importu plansz.

## Verification

- `npm run test --workspace @game-predictor/manual-image-selection-core` — 38
  testów zaliczonych.
- `npm run test --workspace @game-predictor/admin` — 395 testów zaliczonych.
- typecheck pakietu domenowego i Admina — zaliczony.
- lint Admina — zaliczony.
- build pakietu domenowego i produkcyjny build Admina — zaliczony.
- `git diff --check` — zaliczony.
