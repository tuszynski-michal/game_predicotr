---
title: TASK-0349 — Częściowa geometria ostatniej strony
status: done
version: 0.10
---

# TASK-0349 — Częściowa geometria ostatniej strony

## Cel

Usunąć sztywne wymaganie dziewięciu plansz z ręcznej korekty geometrii, gdy
poświadczona nazwa ostatniego zdjęcia zawiera krótszy zakres, na przykład
`seq_499996-500000.jpg`.

## Zakres

- backend wylicza `expectedBoardCount` z zakresu `seq_*` i przekazuje go do UI;
- zapis override'u, constraint bazy, preflight oraz produkcyjny import przyjmują
  dokładnie aktywny prefiks 1–9 row-major quadów;
- Admin ogranicza tryb osobnego wskazywania, korektę pojedynczych plansz i zapis
  do liczby poświadczonej dla bieżącego źródła;
- pełna strona zachowuje dotychczasową siatkę 6 × 6 i 36 narożników.

## Outcome

- `seq_499996-500000.jpg` wymaga pięciu, a nie dziewięciu quadów;
- API nie ufa liczbie przesłanej przez klienta i porównuje ją z manifestem;
- częściowy override przechodzi preflight oraz produkcyjny adapter z pięcioma
  planszami, lecz nie jest używany jako globalna kotwica 3 × 3;
- klient TypeScript został ponownie wygenerowany z OpenAPI;
- testy: 29 API funkcjonalnych, 60 migracji, 42 workera i 328 Admina przeszły;
  typecheck Admina przeszedł.
