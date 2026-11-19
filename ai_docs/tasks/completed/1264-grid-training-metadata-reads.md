# TASK-1264 — Odczyt stałych danych podczas prywatnego treningu siatek

## Status

`done`

## Goal

Usunąć wielokrotne kopiowanie manifestu przy dostępie do stałych parametrów bez zmiany próbek, przypisania gry, wag ani danych do oceny.

## Acceptance criteria

- Każda zamrożona kohorta udostępnia identyfikator gry dla historii ekspozycji raz na instancję dostawcy partii.
- Politykę częściowych zdjęć sprawdza się na poziomie przejścia po zbiorze.
- Trening po wznowieniu zachowuje zapisany krok; usługi pozostają uruchomione.

## Outcome

Commit: v1.7.696 / `c4b78912c0bada15d1ae0d6bfac2f74efc635992`.

42 testy przeszły, w tym wznowienie, dane częściowe, wybór punktu kontrolnego, eksport dwóch sieci i ograniczenie liczby odczytów. Ruff PASS. Mypy wskazuje istniejący błąd typu w liczniku pełnych zdjęć (linia 307), poza zmienionymi fragmentami. API obserwuje wyłącznie swój katalog src; zmiana dotyczy nowego procesu trenera.
