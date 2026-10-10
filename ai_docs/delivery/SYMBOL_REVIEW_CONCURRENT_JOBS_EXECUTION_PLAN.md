# Równoległe joby weryfikacji symboli

## Stan obecny i cel

Użytkownik zgłasza nieudany start kolejnej operacji podczas pracy poprzedniej.
Log `.runtime/api-controlled-20261006T225835069Z.error.log` potwierdza
`DeadlockDetected` przy zapisie targetów, w kontroli FK do `recognized_boards`.
Start blokuje stan katalogu przed FK planszy. Mutacja workera blokuje planszę
przed stanem katalogu. Powstaje cykl oczekiwania. Limit jawnych targetów wynosi
10 000 na komendę; nie ma limitu liczby operacji.

Drugim potwierdzonym problemem jest `selectVisiblePage`: zaznacza także karty
już zablokowane przez aktywną lub zakończoną operację. To może wysłać nieaktualne
rewizje do kolejnego joba. Celem jest trwałe usunięcie obu przeszkód w kolejnych
niezależnych operacjach, bez zwiększania limitu ani zmiany kontraktu API.

## TASK-0897 — Start kolejnych jobów bez konfliktu blokad

- Backend: w `SqlAlchemySymbolCellReviewBulkOperationRepository.start` odczytaj
  gotowość bez blokady katalogu. Zachowaj idempotencję i dotychczasową walidację.
  Zamroź targety i wykonaj flush wszystkich FK przed blokadą katalogu. Następnie
  pobierz świeży stan z blokadą i ponownie sprawdź zakres/rewizje targetów lub
  rewizję filtra. Konflikt wycofuje całą transakcję HTTP, razem z jobem i targetami.
- Osobna transakcyjna blokada advisory dotyczy wyłącznie pary gra + UUID
  idempotencji. Zastępuje ochronę retry, którą zapewniała wcześniejsza blokada
  katalogu. Różne joby nie współdzielą tej blokady.
- Odczyt po blokadzie i ponowny odczyt targetów muszą odświeżać identity map
  SQLAlchemy. Nie wolno zaakceptować starych obiektów z pierwszego odczytu.
- UI: `Zaznacz stronę` wybiera wyłącznie karty niezablokowane przez wysłane
  operacje. Po wyczerpaniu strony przycisk jest nieaktywny. Kliki kart także
  sprawdzają blokadę. Limit pozostaje osobny dla nowego zaznaczenia każdego joba.
- Istniejące częściowe wyniki, CAS, target reset, zamrożony widok, polling,
  kolejność plansz i restart workera pozostają chronione.

## Odbiór i ryzyka

Zakres odbioru: test kolejności blokad i świeżości, izolowany test PostgreSQL startu
w trakcie mutacji tej samej planszy, jawny/filtr, idempotentny replay, konflikt
po oczekiwaniu i rollback. Interakcje UI uruchamiają dwa małe niezależne joby
bez odświeżenia, pomijają pending/settled i zachowują reset symbolu. Następnie
format/lint/typecheck i build Admina. Outcome TASK-0897 zapisuje wykonane wyniki:
PostgreSQL 4/4, backend/API 24/24, interakcje 16/16 i helpery 40/40 PASS;
format/lint/typy zmienionych modułów i build PASS. Pełniejsze testy pozostawiają
wcześniejszą rozbieżność timeoutu listy, a mypy z zależnościami przekroczył czas.
Uruchomienie poprawki w działających procesach API/Admin wymaga ich restartu.

Nie wykonujemy zapisów symboli użytkownika, migracji produkcyjnej, treningu,
cleanup, restartu usług, wdrożenia, push ani merge. Test PostgreSQL używa
wyłącznie własnej, losowo nazwanej bazy testowej i ograniczonych danych.
Nie rozszerzamy zakresu o inne workflowy blokad. Model API pozostaje bez zmian.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0897 | gpt-6.1-sol | high | Potwierdzony cykl blokad wymaga kontroli transakcji, identity map i regresji UI. | Własny audyt kolejności blokad i rollback; bez delegowania. Eskalacja przy nieusuniętym cyklu lub zmianie kontraktu. |
