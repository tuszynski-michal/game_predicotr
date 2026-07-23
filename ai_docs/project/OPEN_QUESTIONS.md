---
title: Open product and architecture questions
status: active
last_updated: 2026-07-24
---

# Otwarte pytania

Pytania Q-001–Q-014 zostały rozstrzygnięte z właścicielem produktu w `tasks/0001-architecture-clarification.md`. Zaakceptowane decyzje architektoniczne i wykonawcze znajdują się w `process/DECISION_LOG.md`.

## Rozstrzygnięte 2026-07-24

| ID | Rozstrzygnięcie | Źródło |
|---|---|---|
| Q-001 | Mobile działa całkowicie offline już w M1; dane są dołączone do APK. | Task 0001, D-002, D-005 |
| Q-002 | Do około 500 000 layoutów na grę, około 12–15 gier; bez zdjęć w mobile. | Task 0001 |
| Q-003 | `sequence_number` jest ciągły i bez luk; duplikaty dotyczą treści layoutu, nie numeru. | Task 0001, D-007 |
| Q-004 | Sekwencja jest cykliczna. Pełny cykl ocenia `N - 1` przyszłych layoutów. | Task 0001, D-009 |
| Q-005 | Jedynym typem wzorca jest konkretna `PAYLINE`. | Task 0001 |
| Q-006 | Zwycięski ciąg może zacząć się w dowolnej kolumnie i ma co najmniej 3 kolejne kolumny bez luki. | Task 0001 |
| Q-007 | Dla jednego ciągu wypłacana jest tylko najdłuższa pasująca długość. | Task 0001 |
| Q-008 | Payline wybiera jedno pole na kolumnę; komórki mogą uczestniczyć w wielu paylines. | Task 0001 |
| Q-009 | Joker zastępuje zwykłe symbole niezależnie na każdej payline, bez własnej wypłaty i bez wygranej samych jokerów. | Task 0001 |
| Q-010 | Sumowane są wszystkie niezależnie prawidłowe paylines i symbole; wspólne komórki nie są „zużywane”. | Task 0001 |
| Q-011 | Rozpoznany layout to spin 0 bez kosztu i payoutu. | Task 0001 |
| Q-012 | Wynik netto to skumulowane payouty minus koszt wszystkich ocenionych spinów; dodatni oznacza `> 0`. | Task 0001 |
| Q-013 | Tabela zawiera każde dodatnie lokalne maksimum netto, a nie wyłącznie rekordy globalne. Plateau wybiera pierwszy spin. | Task 0001, D-009 |
| Q-014 | Duplikat blokuje prognozę; reset rozpoczyna zupełnie nowe wyszukiwanie, bez łańcucha potwierdzeń. | Task 0001, D-008 |
| Q-018 | Administrator przygotowuje wersjonowany snapshot i nowe APK; mobile nie pobiera danych przez API. | Task 0001, D-005 |

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
