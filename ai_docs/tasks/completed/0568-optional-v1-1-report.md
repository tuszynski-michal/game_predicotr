---
title: TASK-0568 — testowy raport v1.1 przy gotowym stagingu
status: done
last_updated: 2026-09-16
---

# TASK-0568 — testowy raport v1.1 przy gotowym stagingu

## Goal

Operator otwiera raport gotowego stagingu domyślnie w v1.0 albo jawnie w v1.1.

## Context

Lista stagingów powielała domyślny wariant w przycisku „Przetwórz w v1.0”,
choć v1.1 wymaga osobnego wyboru do testowania.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- Zmiana przycisku w raporcie gotowego stagingu i ochrona kontekstu guarda przy
  zmianie wariantu.
- Test regresyjny wyboru wariantu i zachowania otwarcia raportu bez joba.

## Out of scope

- Zmiana algorytmu, API, danych i historycznych jobów.

## Acceptance criteria

- [x] Nowy staging otwiera raport v1.0 zwykłym przyciskiem.
- [x] Dodatkowy przycisk otwiera raport v1.1 tylko gdy wariant jest dostępny.
- [x] Odświeżenie aktywnego raportu zachowuje wariant, a przełączenie czyści
  lokalny kontekst guarda.
- [x] Otwarcie raportu nie uruchamia preflightu ani importu.

## Outcome

Zmieniono akcje listy stagingów i test kontraktu panelu. Raport v1.1 wymaga
dalej jawnego przygotowania geometrii i startu importu. Testy Admina 492/492,
lint i typecheck przeszły. Świeżo pobrany pakiet działającego Admina zawiera
nową etykietę przycisku. Nie uruchomiono jobów ani builda produkcyjnego w
trakcie działania lokalnego serwera developerskiego.
