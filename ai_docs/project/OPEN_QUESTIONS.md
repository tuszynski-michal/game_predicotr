---
title: Open product and architecture questions
status: active
last_updated: 2026-07-24
---

# Otwarte pytania

Ten dokument zawiera wyłącznie pytania, które nadal wymagają odpowiedzi.

Q-001–Q-014 oraz Q-018 zostały rozstrzygnięte. Obowiązujące decyzje znajdują
się w [Decision Log](../process/DECISION_LOG.md), a dokładny zapis odpowiedzi
właściciela w
[ukończonym Task 0001](../tasks/completed/0001-architecture-clarification.md).

## Obraz i import

### Q-015 — Reprezentatywny zbiór zdjęć

Otrzymano trzy zdjęcia 960 × 1280 pokazujące po 9 layoutów 3 × 5 i numery sekwencji 1–27. Wystarczają do prototypu geometrii, ale nie do walidacji klasyfikatora.

Do ustalenia:

- czy można dostarczyć 20–100 reprezentatywnych zdjęć,
- jakie rozdzielczości i orientacje występują,
- czy zbiór obejmuje skrajne odbicia, rozmycie, zasłonięcia i różne urządzenia.

### Q-016 — Stabilność układu strony

Na trzech próbkach widoczny jest układ 3 × 3 mini-layoutów. Trzeba potwierdzić, czy:

- wszystkie gry i ekrany używają tego samego układu,
- ramki i numery znajdują się w przewidywalnych obszarach,
- występują inne warianty stron lub liczby layoutów na zdjęciu.

### Q-017 — Zestaw treningowy

Trzeba potwierdzić możliwość przygotowania docelowo około 100 poprawnie oznaczonych wycinków na każdy symbol, pochodzących z wielu różnych zdjęć. Podział trening/walidacja musi być wykonany według zdjęcia źródłowego, nie losowo według kafelka.

## Administracja i wdrożenie

### Q-019 — Wielu administratorów

Czy lokalny panel administracyjny będzie używany wyłącznie przez właściciela, czy przez kilka osób? Odpowiedź wpłynie na autoryzację, blokady edycji i audyt zmian, ale nie blokuje M1.

### Q-020 — Aplikacja referencyjna

Czy istnieje zgoda właściciela aplikacji Windows na analizę jej zachowania, plików i ruchu sieciowego? Bez zgody prace należy ograniczyć do obserwacji funkcji, dostarczonych zdjęć i ręcznego tworzenia specyfikacji.

## Warunek rozpoczęcia etapów

- M1 nie ma otwartych pytań blokujących.
- Techniczne decyzje toolchain/build podejmowane w M1.1 nie wymagają odpowiedzi
  produktowej, ale muszą zostać zapisane w Decision Log.
- Prace nad automatycznym importem zdjęć wymagają odpowiedzi na Q-015–Q-017.
- Produkcyjna autoryzacja panelu wymaga odpowiedzi na Q-019.
- Analiza aplikacji referencyjnej poza obserwacją wymaga odpowiedzi na Q-020.
