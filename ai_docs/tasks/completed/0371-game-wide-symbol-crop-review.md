---
title: TASK-0371 — Game-wide podgląd wszystkich cropów symboli
status: done
relevant_docs:
  - ai_docs/requirements/ADMIN_APP.md
  - ai_docs/architecture/API_CONTRACT.md
---

# TASK-0371 — Game-wide podgląd wszystkich cropów symboli

## Cel

Usunąć z `Weryfikacji symboli` ograniczenie podglądu do jednego symbolu, stanu
lub pasma confidence. Po wskazaniu gry operator ma zawsze widzieć wszystkie jej
bieżące cropy w deterministycznej, stronicowanej kolejności.

## Zakres

- kompatybilny zakres odczytu Admin API `symbolId=all`, odrębny od technicznego
  `unknown`,
- keyset cursor związany z game-wide scope,
- indeks kolejności `game_id → sequence_number → cell_index` dla stronicowania
  dużych katalogów bez pełnego sortowania,
- panel z wyborem wyłącznie gry; stan, symbol i confidence nie filtrują listy,
- zachowanie katalogu symboli jako celu ręcznej zmiany etykiety,
- jawne zaznaczanie pojedynczych cropów i bieżącej strony; bez mieszanego
  `Zaznacz wyniki filtra` dla całej gry.

## Definition of Done

- lista i liczniki dla `symbolId=all` obejmują przypisane i nierozpoznane cropy,
- cursor z zakresu `all` nie może zostać użyty w innym scope,
- UI nie renderuje filtrów symbolu, stanu ani confidence,
- po zatwierdzeniu gry pobierany jest zakres `all + state=all`,
- testy domeny, API, repozytorium i kontraktu Admina pokrywają nowy widok.

## Outcome

- Dodano odrębny, kompatybilny zakres `all` bez zmiany zachowania UUID i
  `unknown`.
- Admin pokazuje wszystkie aktualne cropy wybranej gry i nie ukrywa ich przez
  filtry symbolu, stanu ani confidence.
- Operacje pozostają ograniczone do jawnego zaznaczenia, dzięki czemu mieszany
  game-wide scope nie uruchamia niejednoznacznej masowej akcji.
- Dodano indeks seek dla pełnego katalogu gry, aby widok nie cofał się do
  kosztownego sortowania wszystkich cropów przy każdej stronie.
