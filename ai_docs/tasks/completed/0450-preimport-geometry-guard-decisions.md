---
title: Append-only pre-import geometry guard decisions
status: done
version: v0.10.161
---

# Cel

Utrwalic checksum-bound decyzje operatora dla plansz odroczonych przez bramke
duzego importu oraz zamykac kompletny, content-addressed manifest rozliczenia.

# Zakres

- migracja `0096`, modele domenowe i SQLAlchemy,
- decyzje `corrected_full`, `partial`, `rejected` z rewizjami append-only,
- maska `unavailableCellIndices` i stan `pending_partial` planszy,
- atomowy zapis jednej lub wielu decyzji dla jednego zrodla,
- lista nierozliczonych plansz z raportu v2,
- zamkniecie manifestu dopiero po rozliczeniu calej kolejki,
- bezpieczny odczyt obrazu z checksum-bound stagingu,
- endpointy API, OpenAPI, wygenerowany klient i testy kontraktu.

# Poza zakresem

- wykonanie browser-import schema v7,
- materializacja cropow planszy czesciowej,
- UI kolejki,
- operacyjne wznowienie failed joba.

# Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

# Definition of Done

- decyzje sa append-only, game/staging/report/source/slot-bound,
- partial ma 1..14 unikalnych komorek, full ma 0, rejected nie ma geometrii,
- zapis zbiorczy jest atomowy i wymaga wspolnej checksumy zrodla,
- manifestu nie mozna zamknac przy nierozliczonej planszy ani drifcie,
- odczyt staged JPEG ponownie sprawdza rozmiar i SHA-256,
- schema bazy ma migracje i modele,
- API/OpenAPI/klient/testy oraz dokumentacja sa zgodne.

# Outcome

- Dodano migrację `0096`, modele domenowe/SQLAlchemy i append-only repozytorium.
- Dodano kolejkę raportu v2, atomowy zapis decyzji, bezpieczny staged asset i
  content-addressed zamknięcie kompletnego manifestu.
- OpenAPI oraz wygenerowany klient zawierają cztery nowe operacje.
- Weryfikacja: 6 testów domeny/API, test head migracji, Ruff, aktualność klienta
  i TypeScript typecheck zakończone powodzeniem.
- Skoncentrowany mypy dla domeny, aplikacji i repozytorium zakończył się bez
  błędów. Szeroki mypy z pełnym śledzeniem importów przekroczył kontrolowany
  limit 4 minut i został przerwany bez pozostawienia procesu.
