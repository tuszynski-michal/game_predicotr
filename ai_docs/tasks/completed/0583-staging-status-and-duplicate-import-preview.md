---
title: TASK-0583 — status stagingu i preview usunięcia podwójnego importu
status: done
---

# TASK-0583 — status stagingu i preview usunięcia podwójnego importu

## Goal

Oddzielić trwały status przebiegu importu plansz od historii jobów oraz przygotować
bezpieczny, szczegółowy preview usunięcia drugiego importu tego samego stagingu.

## Context

TASK-0582 wykrył 10 191 dodatkowych plansz z ponownego importu stagingu
`9c7de0ca-6eda-4b43-977d-d4684cb6b58b`. Status karty zależy dziś od przeszukiwania
historii jobów i łączy etap importu plansz z późniejszą oceną symboli.

## Dependencies / entry conditions

- TASK-0582 ukończony; audyt danych jest read-only.
- Użytkownik zlecił przygotowanie propozycji usunięcia, nie zatwierdził usunięcia.

## Recommended execution

gpt-5.6-sol / high. Zmiana obejmuje trwały model statusu, migrację, API, panel
i analizę zależności danych. Eskalować do osobnego review przed skryptem
destrukcyjnym lub zmianą zapisanej historii jobów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Zdefiniować status importu plansz niezależny od weryfikacji symboli.
- Wprowadzić trwałą projekcję statusu stagingu do użycia przez listę/panel;
  joby pozostają historią i źródłem audytu, lecz nie sterują kartą.
- Sporządzić read-only preview obu importów i ich zależności oraz wskazać
  kandydata do usunięcia wraz z kryteriami blokady.

## Out of scope

- Usunięcie rzeczywistych importów, plansz, cropów, symboli lub jobów.
- Tworzenie nowej gry, ponowny import, cięcie albo automatyczna korekta geometrii.
- Usuwanie historii jobów.

## Acceptance criteria

- [ ] Status „plansze utworzone” nie zależy od wyniku weryfikacji symboli.
- [ ] Lista stagingów używa trwałego statusu, a nie przeszukiwania jobów.
- [ ] Joby pozostają dostępne jako historia/audyt i nie są kasowane przez zmianę statusu.
- [ ] Preview zawiera zakres drugiego importu, różnice względem pierwszego i wszystkie blokujące zależności.
- [ ] Nie ma modyfikacji rzeczywistych danych ani planu usunięcia bez jawnej zgody.

## Technical notes

Status pracy plansz jest projekcją workflowu, nie skrótem do usunięcia jobów:
job pozostaje wymaganym provenance materializowanych danych. Po udanym
materializowaniu plansz status przechodzi do `boards_imported`; oczekująca lub
niepoprawna weryfikacja symboli nie cofa go. Błąd importu nie może zostać
oznaczony jako ukończony tylko dlatego, że istnieją pojedyncze symbole.

Preview porównuje identyczne źródło (checksum), pozycję, sekwencję i checksumy
wyników. Usunięcie może być zaproponowane tylko dla importu będącego ścisłym
podzbiorem innego importu i bez unikalnych zależności domenowych.

## Expected files

- istniejące: model/migracje retencji stagingu, `image_imports.py`, schemat
  OpenAPI, stan/panel importu Admina oraz ich testy;
- nowe: raport i skrypt preview usuwania duplikatu, jeśli istniejący audyt
  TASK-0582 nie obejmuje wszystkich zależności.

## Test cases

- Wykonany import plansz z oczekującymi symbolami → `boards_imported`.
- Job symboli nie zmienia statusu plansz.
- Brak historii jobów w zwróconym oknie → karta nadal używa trwałego statusu.
- Podzbiór z unikalnym wynikiem/dowolną domenową referencją → preview blokuje usunięcie.
- Podzbiór bez unikalnych zależności → preview wskazuje go, ale nie usuwa.

## Verification

Skoncentrowane pytest API/migracji i testy Admina, lint/typecheck/OpenAPI.
Audyt danych: transakcja read-only, limit zapytań i zapis raportu poza bazą.

## Risks / open questions

- Znaczenie „nie pamiętać jobów” jest interpretowane jako brak zależności UI
  od jobów, nie kasowanie trwałej historii/provenance. Kasowanie jobów wymaga
  osobnej jawnej decyzji i preview zależności.

## Outcome

- Dodano trwały `boardImportStatus` z migracjami 0112 i 0113. Wartość jest
  ustawiana przy starcie importu oraz przez worker po `waiting_for_review`,
  ukończeniu, błędzie lub anulowaniu. Backfill uwzględnia wszystkie importy
  stagingu, a nie tylko dawny wskaźnik retencji.
- API listy i Admin używają wyłącznie statusu stagingu; nie przekazują ani nie
  przeszukują `importJobId`/`importJobStatus` na potrzeby karty. Joby pozostają
  nienaruszoną historią/proweniencją.
- Audyt read-only gry 777 potwierdził `boards_imported` dla wszystkich 12
  importowanych stagingów i prawidłowe szkice oraz pliki dla 11 916 korekt.
  Szczegóły duplikatu zapisano w
  `ai_docs/quality/STAGING_DUPLICATE_PREVIEW_0583.md`.
- Nie usunięto danych. Nie można bezpiecznie usunąć całego starszego importu
  (44 unikalne plansze) ani nowszego (aktywna kolejka review). Przyszły cleanup
  może rozważyć tylko 10 191 zastąpionych starszych plansz po osobnym preview
  proweniencji i jawnej zgodzie.
- Weryfikacja: testy Admina, test API importu, izolowany PostgreSQL dla
  przejścia `waiting_for_review → boards_imported`, Ruff, mypy, typecheck,
  Prettier, eksport OpenAPI i kontrola wygenerowanego klienta przeszły.
  Pełny `test_openapi_contract.py` ujawnił wcześniejszy, niezwiązany błąd
  oczekiwania `minItems` dla `ImageGridReviewGeometryRevisionResponse.cells`;
  nie został zmieniony w tym tasku.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0583 | gpt-5.6-sol | high | Statusy, migracja i analiza referencji danych wymagają spójnego przeglądu backendu, UI oraz bazy. | Tak — gpt-6-astra / high przed wykonaniem operacji destrukcyjnej. |
