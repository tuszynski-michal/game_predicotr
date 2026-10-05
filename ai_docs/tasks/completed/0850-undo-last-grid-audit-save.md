# TASK-0850 — Cofnięcie ostatniego zapisu planszy 388128

## Status

`done`

## Goal

Przywrócić jedną ostatnio zapisaną planszę 388128 / p00683 do przeglądu.

## Context

Operator ponownie polecił cofnięcie jednej zapisanej planszy. Odczyt bazy
wskazał receipt 0f3009c7-2923-4574-b130-e1cac7103f2a z 2026-10-05 15:57:10 UTC.

## Dependencies / entry conditions

- Board 15555a31-81fd-4473-8496-8243725d994e ma geometry revision 2;
  review acf3f254-89e6-4df8-9e45-404f8e8b58ab, poprzednia geometria revision 1.
- Wszystkie 15 pól przed zapisem miało pending / requires_review.
- Aktywny audyt: silent-grid-777-20261004-undo-p00545-20261005t130216.
- Założenie: cofnięcie obejmuje geometrię i 15 zatwierdzeń z tego samego
  atomowego zapisu, tak jak poprzednie cofnięcie TASK-0849.

## Recommended execution

gpt-6.1-sol / high; istniejąca operacja kompensująca, kontrola rewizji,
niezmienności pozostałych danych i trwałości. Bez delegowania.

## Relevant docs

- AGENTS.md; ai_docs/README.md; ai_docs/process/CURRENT_STATE.md.
- ai_docs/process/PLAN_STANDARD.md; ai_docs/process/TASK_TEMPLATE.md.
- ai_docs/requirements/ADMIN_APP.md — audyt i zapis geometrii.
- ai_docs/architecture/API_CONTRACT.md — geometry-revisions i CAS.

## Scope

Istniejące API zapisze poprzednie narożniki jako revision 3, zachowując historię.
Nowa niezmienna wersja aktualnego audytu zmieni baseline tylko p00683.
Wszystkie istniejące propozycje symboli zostaną zachowane, a ich piksele
sprawdzone dla przywracanej pozycji. Dowody operacji zostaną zarchiwizowane.

## Out of scope

Nowe UI, endpointy, schemat, trening algorytmu i usuwanie danych.

## Acceptance criteria

- [x] Poprzednie narożniki przywrócone; 15 pól ponownie do przeglądu.
- [x] Pozostałe geometrie, decyzje i propozycje niezmienione.
- [x] Poprzednie cofnięcie p00545 pozostaje zachowane w nowym audycie.
- [x] Świeży proces i UI pokazują p00683 jako otwartą pozycję.
- [x] Trwały receipt, Outcome, CURRENT_STATE i osobny wersjonowany commit.

## Technical notes

Idempotency key zapisany przed żądaniem; CAS i ponowne sprawdzenie ostatniego
receipt przed zmianą. Manifest publikowany po weryfikacji kompletu propozycji.
Historyczna aprobata revision 2 pozostaje jako pochodzenie starej decyzji;
aktualne pola mają pending / requires_review i brak verified_symbol_id_v2.

## Expected files

- Nowe: .runtime/task0850/undo_geometry.py i receipts.
- Nowe: artifacts/grid-audit-undo-20261005/p00683/ oraz niezmienny audyt.
- Dokumentacja: ten task i własna sekcja CURRENT_STATE.md.

## Test cases

CAS chroni przed cofnięciem nowszego zapisu; ponowienie używa tego samego
idempotency key. Porównanie 974 pozostałych plansz oraz pól tego samego źródła.
Świeży proces porównuje wszystkie pozycje i payloady propozycji.

## Verification

Z katalogu repo: ograniczony runner .runtime/task0847/run-check.ps1 uruchamia
prepare (40 s), apply (55 s), verify (45 s). PASS wymaga zgodności historii,
SHA podglądu, propozycji i otwartej pozycji w API oraz UI.

## Risks / open questions

Brak blokujących pytań; zakres wyraźnie autoryzowany przez operatora.

## Outcome

### Changed

- API utworzyło kompensującą geometry revision 3, receipt
  efc87ae4-6eae-4803-9fd3-0a4980707c84. Poprzednie narożniki przywrócone;
  wszystkie 15 pól pending / requires_review, bez aktualnego verified symbol.
- Niezmienny audyt silent-grid-777-20261004-undo-p00683-20261005t160416
  zmienia baseline wyłącznie p00683. Zachowano 975 pozycji, ich kolejność,
  poprzedni rebase p00545 oraz wszystkie 917 propozycji symboli.
- Dowody, wcześniejszy odczyt, receipts, weryfikacja i zrzut UI:
  artifacts/grid-audit-undo-20261005/p00683/.

### Verification results

- prepare / apply / verify PASS, każdy w osobnym ograniczonym procesie.
- 974 pozostałe geometrie i pola pozostałych plansz tego źródła niezmienione.
- 975 pozycji i 917 propozycji porównane; payloady bez zmian poza metadanymi
  nowego audytu i rewizjami kontekstu przywróconej pozycji. SHA PNG zgodny.
- Świeży proces API: p00683 open i pierwsza w kolejce; 402 open / 573 corrected.
- UI: plansza 388128, pozycja 3/9, 15/15 nowych propozycji symboli.
- Ruff format i końcowy check pomocnika PASS; pierwszy check wskazał długi
  wiersz poprawiony formatterem. Bez zmian logiki po weryfikacji.
- Kryteria akceptacji sprawdzone punkt po punkcie; zakres operacji zachowany.
- Commit dokumentujący operację: v1.7.196; pełny hash zostanie dopisany po commicie.

### Not completed

Nie uruchamiano ponownie testów aplikacji, lint/typecheck frontendu ani builda:
kod aplikacji i kontrakt API nie zostały zmienione. Bez push lub wdrożenia.

### Documentation updates

Task przeniesiony do completed; własna sekcja CURRENT_STATE z wynikiem.

### Recommended next task

Operator ponownie przegląda i zapisuje przywróconą planszę. Brak kolejnego
automatycznie uruchomionego zadania.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
| TASK-0850 | gpt-6.1-sol | high | Kontrola CAS, historii i niezmienności danych. | Samodzielna kontrola w nowym procesie; bez delegowania. |
