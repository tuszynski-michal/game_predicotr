# TASK-1259 — Przejście do następnego zdjęcia w serii

## Status

`done`

## Goal

Jeden lokalny link otwiera drugie z 30 zdjęć. Po zapisaniu ostatniej planszy operator przechodzi w Reviewerze do następnego zdjęcia tej samej serii.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/TECH_STACK.md`

## Scope

Lokalna strona serii, bramka Reviewera, ekran końca zakresu i jego test interakcji. Kolejność pochodzi z utrwalonej listy operatora. API geometrii i samodzielne linki do zdjęć zachowują dotychczasowe działanie.

## Acceptance criteria

- Kliknięcie lub Enter zapisuje bieżącą planszę z gotowym podglądem. Dziewiąta odrębna zaakceptowana pozycja automatycznie otwiera kolejne zdjęcie, również po powrocie do pominiętej planszy.
- Ostatnie zdjęcie kończy serię. Zły indeks lub nazwa nie otwierają importu.

## Outcome

Commit: v1.7.691 / `644d2416d70a546c756e8b138f27884ee0235b42`.

Adres pozycji serii odczytuje zakres jednego zdjęcia. Potwierdzone pozycje są liczone po odpowiedzi zapisu, z zachowaniem postępu po odświeżeniu karty. Utrzymany Enter nie powtarza zapisu. Interakcje 43/43, kontrakty 9/9, lint, typy i mapa PASS.
