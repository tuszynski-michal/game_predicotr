---
title: Galeria podejrzanych siatek Mumii A2
status: done
last_updated: 2026-11-18
---

# TASK-1249 — Galeria podejrzanych siatek Mumii A2

## Status

`done`

## Goal

Obejrzeć i zaznaczyć całe plansze w Adminie, a następnie skierować je do obecnej kolejki korekty.

## Dependencies / entry conditions

TASK-1251. Scope galerii uzgodniony z operatorem: bieżące pełne siatki automatyczne gry `mumie-aktu2`.

## Recommended execution

`gpt-6.2-sol`, `high`. Przekazanie wymaga zachowania rewizji geometrii i wycinka. Niezależny audyt niewymagany.

## Relevant docs

- `../requirements/ADMIN_APP.md`
- `../architecture/API_CONTRACT.md`
- `../architecture/ITERATIVE_IMAGE_IMPORT.md`

## Acceptance criteria

- [x] Admin skanuje zakres gry lub katalogu i pokazuje całe plansze z bieżącą siatką, marginesem oraz powodem wskazania.
- [x] Galeria pozwala wybrać plansze i po jednym polu na każdej, wykorzystując akcję „Zła siatka”.
- [x] Wynik operacji pokazuje sukcesy i konflikty rewizji. Zapis korekty nadal domyka zgłoszenie standardowym mechanizmem.
- [x] GET jest ograniczony do gry, katalogu, bieżącego właściciela i jawnego budżetu strony. Kursor działa także przy pustej liście wskazań.

## Technical notes

Istniejący odczyt `grid-reviews` otrzymuje widok `suspicious`, a operacja `mark_grid_issue` jawne cele z bieżącą rewizją pola, siatki i tożsamością wycinka. Zmiana obejmuje Admina, API, OpenAPI, klienta i test żądania.

## Outcome

Commit: v1.7.675 / `43e14c4fe0cc07128cfed3d9c3084a79319170f5`.

Galeria działa w Weryfikacji symboli dla `mumie-aktu2`. Widok odczytu
skanuje strony według bieżącego właściciela numeru. Admin wysyła osobną
istniejącą decyzję dla jednego pola każdej wybranej planszy, w partiach
do czterech żądań. Pokazuje wynik i ewentualny konflikt przy planszy.

Test żądania i kursora, 19 interakcji Admina, 22 kontrole kontraktów i
skrótów oraz dwa scenariusze w osobnej bazie PostgreSQL przeszły. Scenariusz
trzech siatek potwierdził dokładnie dwa zgłoszenia, a po korekcie jednej
siatki pozostało drugie. Przeszły TypeScript Admina, ESLint, Ruff i kontrola
aktualności OpenAPI oraz klienta. Sprawdzono początkowe partie w obu importach
i w zakresie całej gry tylko do odczytu. Chrome w rozmiarze telefonu
390 × 844 px wyrenderował zdjęcie planszy #379218 i przełączalną nakładkę.
Mypy zaliczył sześć zmienionych modułów przy pominięciu grafu importów.
Próba z grafem importów przekroczyła limit czasu.
Odbiór na fizycznym telefonie i integracja z działającymi usługami pozostają
do sprawdzenia przy wdrożeniu.
