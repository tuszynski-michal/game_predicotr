# TASK-1254 — Uczenie z przypisanej wersji prywatnej gry

## Status

`done`

## Goal

Trening prywatny przypina aktualnie przypisaną bazę, rodzinę właściciela i dane jednej gry, a kolejne etapy weryfikują te same dowody.

## Context

Drugi krok zaakceptowanego planu prywatnych modeli. Dotychczasowe uczenie używa domyślnej wersji i kohort z historii publikacji.

## Dependencies / entry conditions

TASK-1253 i D-618. Zmiany w gałęzi roboczej, testy na izolowanej bazie. Weryfikacja integracyjna w zadaniu 3.

## Recommended execution

gpt-6.2-astra / high. Zmiany wymagają zgodności SQL, rejestru, parenta i dzieci. Sprzeczność własności zatrzymuje wdrożenie.

## Relevant docs

- `delivery/PRIVATE_GAME_GRID_MODELS_PLAN_20261118.md`, sekcja 2.
- `requirements/SUPERVISED_MODEL_IMPROVEMENT.md`, `architecture/SUPERVISED_MODEL_IMPROVEMENT.md`.

## Scope

Podgląd, gotowość, utrwalenie pinu, przygotowanie i wznowienie, trening, ocena, blokowanie prywatnych próbek w treningach wspólnych, Admin i klient API.

## Acceptance criteria

- Prywatna gra uczy się tylko z własnej kohorty, niezależnie od zmian defaultu. Starsze polecenie na tej grze dostaje zrozumiałą przyczynę blokady.
- Rozbieżność przypisania, właściciela lub manifestu zatrzymuje użycie. Kandydat należy do właściciela także przy pierwszej iteracji z obcej bazy.
- Przypięta tożsamość zdjęć, podział, gotowość i dotychczasowe bramki jakości pozostają sprawdzane.

## Expected files

Serwisy uczenia, treningu i oceny, ich adaptery i workery, migracja 0193, panel uczenia, kontrakt i testy.

## Test cases

Nowy i historyczny klient, przygotowanie i ponowienie, zmiana defaultu i przypisania, pierwsza iteracja cross-family, odrzucenie obcej kohorty.

## Outcome

Commit: v1.7.680 (hash dopisuje kolejny commit).

### Changed

- Gotowość, podgląd, synchroniczny start i przygotowanie w tle przypinają przypisaną wersję gry, jej rewizję, rodzinę docelową i SHA manifestu. Przygotowanie bez treningu zachowuje decyzję o wznowieniu. Dla trwałego przygotowania wykorzystano sprawdzoną implementację z 251fc5bd.
- Kohorta, worker i SQL 0193 sprawdzają pochodzenie danych, rodzinę i prywatny zakres. Pierwszy kandydat może pochodzić od wspólnej bazy. Raport jest związany z zadaniem oceny i kohortą. Dopasowanie starszej publikacji do prywatnej gry wymaga jawnego wykluczenia jej ze wspólnego treningu.
- Admin pokazuje grę i przypisaną wersję przy liczności i brakach. Komendy wysyłają potwierdzony zakres. OpenAPI, klient, wrapper oraz test żądania odpowiadają backendowi.

### Verification results

- Izolowany PostgreSQL 18 (tymczasowy kontener na 55493): test prywatnego pinu, utraty odpowiedzi i zmiany defaultu lub rewizji, test historycznego parenta z dziećmi i test trwałego przygotowania z wznowieniem przeszły. Obejmują migrację 0193 na pustej bazie.
- Python: 51 testów workerów treningu/oceny i wspólnych kandydatów, 32 testy przepływu i zależności eksperymentu, 15 testów kontraktu i prywatnego kandydata w węższym przebiegu. Dodatkowy zestaw HTTP miał 44 PASS; asercja zamkniętego schematu po uzupełnieniu pól przeszła osobno. Testy zachowują istniejące bramki; worker używa kontrolowanego zamiennika procesu trenera.
- Ruff dla zmienionych modułów PASS. Mypy obejmujący 15 modułów z pominięciem grafu importów PASS; pełnego wyniku nie uzyskano przed limitem 119 s. W szerszym przebiegu z pomijaniem importów ogólny schemat jobs.py zgłaszał 7 nierozpoznanych typów wyliczeń/aliasów. Odczyt odpowiedzi i schemat HTTP sprawdzono osobno.
- TypeScript Admina, cały zestaw interakcji panelu oraz 10 testów wrappera PASS. Zastany test etykiety dawnego limitu 20 000 zdjęć nie odpowiada już D-611 i zachowuje błąd również w bazowym HEAD.

### Documentation updates

Wymagania i architektura nadzorowanego uczenia, mapa kodu, stan projektu i kontrakt API.

### Not completed

Rzeczywiste dane operatora, GPU i wdrożenie wymagają odrębnego polecenia. Integracyjny odbiór dwóch kolejnych zastosowań i audyt kodu należą do TASK-1255.

### Recommended next task

TASK-1255 — zastosowanie i cofnięcie wersji.
