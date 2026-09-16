---
title: TASK-0345 — Osobne wyznaczanie dziewięciu plansz
status: done
version: 0.10
---

# TASK-0345 — Osobne wyznaczanie dziewięciu plansz

## Cel

Pozwolić operatorowi wyznaczyć dokładny obrys każdej planszy bez wcześniejszego
dopasowywania obrysu całej strony oraz 36 punktów krzywizny.

## Zakres

- zachować istniejący tryb `Wyznacz 4 narożniki`;
- dodać prowadzony tryb `Wyznacz 9 plansz osobno`;
- zebrać dla każdej planszy punkty LT → PT → PD → LD;
- prowadzić po planszach w kolejności row-major 1–3, 4–6, 7–9;
- blokować przejście po niewypukłym obrysie lub złej kolejności plansz;
- pokazywać już ukończone obrysy i pozwolić cofnąć ostatni punkt;
- zapisać wynik przez istniejący kontrakt dziewięciu finalnych quadów.

## Invarianty

- numeracja `seq_*` i cięcie plansz pozostają row-major;
- żaden niepełny zestaw 36 punktów nie może zostać zapisany;
- dotychczasowy obrys strony, korekta krzywizny oraz korekta pojedynczej planszy
  pozostają dostępne;
- API, baza danych i format finalnych quadów nie zmieniają się;
- `Reset` przywraca geometrię widoczną przy otwarciu źródła.

## Outcome

- Operator może kliknąć cztery narożniki każdej planszy od lewego górnego
  obrysu do prawego dolnego, bez ręcznej korekty 36 punktów.
- UI pokazuje numer planszy, rząd, kolumnę i oczekiwany narożnik, a ukończone
  quady wyróżnia na obrazie.
- Po dziewiątej planszy te same finalne quady można zapisać i wysłać zbiorczo
  do istniejącego preflightu.
