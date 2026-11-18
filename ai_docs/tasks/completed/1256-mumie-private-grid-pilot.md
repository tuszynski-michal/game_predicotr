# TASK-1256 — Ślepy pilot cięcia siatek Mumii A2

## Status

`done`

## Goal

Przygotować pomiar stu plansz i rozliczyć dostępne historyczne korekty.

## Relevant docs

- `delivery/PRIVATE_GAME_GRID_MODELS_PLAN_20261118.md`, sekcja 4.
- `requirements/VISION_LAB.md`, `architecture/VISION_LAB.md`, D-595, D-602.
- `quality/TASK-1246_STAGING_DEPLOYMENT_20261118.md`.

## Dependencies / entry conditions

Operator przygotuje osobny świeży folder. Trening, kandydat, ocena człowieka i zmiana przypisania wymagają osobnych działań.

## Recommended execution

gpt-6.2-astra / high. Operator wykonuje ślepą ocenę.

## Scope and acceptance criteria

Manifest stu pozycji na stu zdjęciach przed strojeniem, ochrona nagrania i kopii, osobna diagnoza oryginału, wejścia, geometrii i piętnastu pól, bilans korekt historycznych, ocena w ciemno oraz raport z bramką 5/100 i zerem nowych ucięć.

## Expected files

CLI i testy w `scripts/`, raport w `ai_docs/quality/`. Bez nowej migracji.

## Outcome

Commit: v1.7.684 / `fda9ecc021de747989fc1ab9e15e2768fce21e38`.

Narzędzie i kontrolowany przebieg są gotowe. Rzeczywisty pilot czeka na świeży folder oraz późniejszą decyzję operatora.

### Changed

- CLI `scripts/mumie_grid_pilot.py` zamraża 100 unikalnych zdjęć i pozycji przed strojeniem, sprawdza powiązania nagrań i kopii oraz wykrywa późniejszą ekspozycję. Przyjmuje świeży folder lub importy z potwierdzoną ochroną. Stały lokalny rejestr wiąże próbę z jednym kandydatem.
- Osobna galeria diagnostyczna pokazuje oryginał, wejścia detektora i planszy, siatkę modelu, ręczną korektę i rzeczywiste wycinki. Ślepy HTML pozwala ocenić A/B i pobrać głosy z przeglądarki. Raport oblicza bilans 5/100 i nowe ucięcia, sprawdza produkcyjne dowody dopuszczenia oraz ich aktualność.

### Verification results

- Pięć testów Pythona zaliczonych, w tym brak wykrycia, częściowa detekcja strony, 15 produkcyjnych wycinków oraz zapis i ponowienie pełnego procesu testowego na 100 parach. Test interakcji HTML w jsdom potwierdził wybór ocen, zmianę planszy, zaliczenie brakującej planszy do mianownika i pobranie pliku głosów.
- Pojedynczy rzeczywisty przebieg modelu `6cc10344` na jednolitym obrazie kontrolnym na CPU zwrócił brak detekcji. Filtr ekspozycji sprawdzony na zmigrowanym odrębnym PostgreSQL na porcie 55493. Odczyt katalogu operatora odrzucił znane zdjęcie i dopuścił nowy obraz kontrolny.
- 5567/5567 historycznych źródeł ma ustalony zakres i brak dowodu pełnego nagrania. Odtworzony przekrój 708/521 daje 589 dokładnych rewizji TRAIN, 57 VALIDATION i 21 REGRESSION. Pozostałych 41 nie użyto w tej postaci. Bieżący przekrój ma jedną dodatkową parę. Przyczyny i górna granica czasu są w raporcie.
- Ruff i mypy trzech zmienionych modułów z pominięciem grafu importów przeszły. Próba z pełnym grafem importów osiągnęła limit 100 s.

### Documentation updates

- Instrukcja dla operatora, liczności, bramki i ograniczenia znajdują się w `quality/MUMIE_PRIVATE_GRID_PILOT_20261118.md`.

### Not completed

- Operator dostarczy nowy folder później. Odroczone pozostają rzeczywiste zamrożenie 100 plansz, diagnoza na odrębnej próbie, osobno zatwierdzony trening, pomiar nowego kandydata i jego ślepa ocena. Rekomendacja aktywacji pozostaje niewyznaczona. Dane domenowe, usługi i aktywne modele zachowały stan.
