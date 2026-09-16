# TASK-0478 — Deferred source slots in manual geometry

Status: done

## Goal

Każdy slot wynikający z poświadczonego zakresu nazwy `seq_<start>-<end>` ma być
widoczny i obowiązkowy w lokalnym edytorze geometrii źródła. Dla zwykłego
zdjęcia oznacza to dziewięć pozycji row-major; krótszy komplet jest dozwolony
wyłącznie wtedy, gdy sam zakres nazwy zawiera mniej niż dziewięć plansz.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Dependencies

- trwały `image_board_geometry_pending`;
- kompletna rewizja geometrii źródła z zakresem i aktywnymi slotami;
- source-direct renderer komórek oraz atomowy zapis geometrii całego źródła.

## Scope

- Dołączyć nierozwiązane rekordy `image_board_geometry_pending` do kolejki
  lokalnego `Zatwierdzania cięcia siatki`.
- Dodać jawną tożsamość slotu rozróżniającą istniejący review od deferred.
- Pokazać bezpieczny roboczy quad dla slotu bez automatycznej geometrii, ale nie
  materializować planszy, cropów ani akceptacji podczas odczytu kolejki.
- Wymagać w atomowym poleceniu wszystkich pozycji wynikających z rewizji
  geometrii źródła.
- Po poprawnym renderze wszystkich pozycji w jednej transakcji zapisać nową
  rewizję źródła, zaktualizować istniejące plansze i dopiero wtedy
  zmaterializować brakujące plansze oraz ich 15 wirtualnych komórek.
- Zachować obsługę retry po utracie odpowiedzi przez idempotency key.
- Nie zmieniać ani nie naprawiać danych istniejącego stagingu.

## Tests

- kolejka mapuje deferred na `needs_correction` z właściwym slotem i numerem;
- źródło z jednym deferred nadal składa się z dziewięciu obowiązkowych pozycji;
- polecenie wymaga dokładnie jednej tożsamości current/deferred;
- zapis nie przyjmuje brakującej pozycji ani złej kolejności;
- odczyt kolejki nie tworzy planszy ani cropów;
- zapis źródła renderuje pełny komplet przed rozpoczęciem transakcyjnej
  materializacji;
- UI identyfikuje szkice przez stabilne `slotId`, wysyła `pendingGeometryId` i
  nie pozwala zwyczajnie zatwierdzić lub odrzucić brakującej planszy;
- retry tego samego zapisu jest idempotentny.

## Definition of Done

- `seq_1234-1242` pokazuje pozycje `#1..#9`, w tym obowiązkowe
  `#6 · 1239`, jeśli slot 6 był odroczony;
- operator może poprawić roboczy quad każdej pozycji;
- brak jednej z dziewięciu geometrii blokuje zapis;
- dopiero kompletny, poprawnie wyrenderowany zapis tworzy brakujące cropy;
- backend, OpenAPI, klient, Reviewer i testy pozostają spójne;
- brak operacji na danych użytkownika i brak migracji.

## Outcome

- Kolejka lokalnego review łączy istniejące `image_review_items` z nierozwiązanymi
  rekordami `image_board_geometry_pending` i nadaje każdej pozycji stabilne
  `slotId` oraz jawny rodzaj `current_review` albo `deferred_geometry`.
- Deferred jest prezentowany jako `needs_correction` z obowiązkowym, edytowalnym
  szablonem. Dla `seq_1234-1242` test regresyjny zachowuje dziewięć szkiców,
  w tym `#6 · 1239`.
- Polecenie źródłowe przyjmuje dokładnie jedną tożsamość current/deferred na
  slot, wymaga pełnej kolejności row-major i renderuje wszystkie komórki przed
  zapisem. Następnie jedna transakcja zapisuje rewizję źródła, aktualizuje
  istniejące plansze oraz materializuje deferred z 15 komórkami virtual-source.
- Odczyt kolejki nie tworzy plansz, cropów ani decyzji. Pojedyncze akcje
  zatwierdzenia/odrzucenia są zablokowane dla deferred; jego rozwiązanie jest
  możliwe tylko przez atomowy zapis całego zdjęcia.
- Rozszerzono backend, OpenAPI, wygenerowany klient i Reviewer bez migracji
  Alembic oraz bez modyfikacji stagingów i danych użytkownika.

### Verification

- `pytest` zmienionego pionu: `23 passed`.
- testy kontraktu i stanu Reviewera: `21 passed`.
- Ruff dla całego API/workera/skryptów: passed.
- ESLint i TypeScript Reviewera: passed.
- TypeScript klienta Admin API: passed.
- kontrola OpenAPI i wygenerowanego klienta: passed.
- produkcyjny build Reviewera: passed.
- globalny mypy nadal zgłasza wcześniejsze błędy w 15 niezwiązanych modułach;
  błędy w plikach TASK-0478 zostały usunięte.
- globalny format check pozostaje czerwony przez wcześniejsze pliki Admina;
  zmienione pliki Reviewera są sformatowane.
