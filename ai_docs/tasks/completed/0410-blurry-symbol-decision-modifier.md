---
title: TASK-0410 — Niewyraźny jako modyfikator decyzji symbolu
status: done
last_updated: 2026-09-03
---

# TASK-0410 — Niewyraźny jako modyfikator decyzji symbolu

## Problem

Osobna akcja `Niewyraźny` wymaga dodatkowego kroku i nie pozwala w jednej
decyzji poprawić błędnej etykiety oraz wykluczyć słabego cropa z treningu.
Operator powinien móc zaznaczyć jakość przed zatwierdzeniem lub zmianą symbolu.

## Scope

- zastąpić przycisk `Niewyraźny` checkboxem w toolbarze Weryfikacji symboli,
- checkbox modyfikuje `Zatwierdź` oraz `Zastosuj zmianę`,
- wykonać zatwierdzenie/przypisanie i zapis `quality_issue = blurry` w jednej
  transakcji oraz jednym evencie,
- obsłużyć identyczną semantykę dla jednej komórki i operacji masowej,
- zachować zgodność istniejącej akcji `mark_blurry` bez symbolu docelowego,
- wykluczać wynik z kohort treningowych przez istniejący predykat jakości,
- resetować modyfikator po zmianie gry lub filtra symbolu, aby nie przenosić
  przypadkowej decyzji jakości między katalogami.

## Out of scope

- brak migracji bazy,
- brak nowej wartości jakości,
- brak zmian w klasyfikatorze i trwającej reinferencji,
- brak automatycznego wykrywania niewyraźnych cropów.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/CURRENT_STATE.md`

## Definition of Done

- zaznaczony checkbox i zatwierdzenie zachowują bieżący symbol jako approved,
  zapisują `blurry` i wykluczają crop z treningu,
- zaznaczony checkbox i zmiana symbolu atomowo zapisują symbol docelowy jako
  approved oraz `blurry`,
- niezaznaczony checkbox zachowuje dotychczasowe approve/reassign,
- osobny przycisk `Niewyraźny` nie występuje w toolbarze,
- testy domeny, API i Admina obejmują oba warianty pojedyncze i masowe.

## Outcome

- `mark_blurry` przyjmuje opcjonalny aktywny symbol docelowy i atomowo zapisuje
  jego przypisanie, approved bieżącego cropa oraz `quality_issue = blurry`.
- Ta sama komenda działa bez symbolu docelowego jako dotychczasowe oznaczenie
  rozpoznanego cropa; nie zmieniono historycznej wartości akcji ani schematu DB.
- Admin zastąpił osobny przycisk checkboxem modyfikującym `Zatwierdź` i
  `Zastosuj zmianę`; pojedyncze i masowe requesty używają jednego zapisu.
- Testy domeny/API/Admina, Ruff, lint, typecheck Admina, OpenAPI i produkcyjny
  build są zielone. Globalny `format:check` nadal zgłasza trzy wcześniejsze,
  niezwiązane pliki; zmienione pliki tego taska są sformatowane.
