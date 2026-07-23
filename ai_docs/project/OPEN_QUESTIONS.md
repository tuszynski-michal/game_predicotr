---
title: Open product and architecture questions
status: active
last_updated: 2026-07-23
---

# Otwarte pytania

Pytania są uporządkowane według wpływu na architekturę. Odpowiedzi należy zapisać w `tasks/0001-architecture-clarification.md`, a decyzje przenieść do `process/DECISION_LOG.md`.

## Blokujące inicjalizację

### Q-001 — Tryb działania aplikacji mobilnej

Czy aplikacja Android ma działać:

- wyłącznie z backendem dostępnym w sieci,
- offline na lokalnej kopii danych,
- hybrydowo: lokalne dane plus okresowa synchronizacja?

**Rekomendacja:** MVP online w tej samej sieci co lokalny backend; projekt danych przygotowany pod przyszły eksport read-only do SQLite.

### Q-002 — Faktyczna skala danych

Co oznacza liczba 500 000:

- 500 000 układów na grę,
- 500 000 zdjęć na grę,
- 500 000 zdjęć łącznie?

Czy każde zdjęcie zawsze zawiera dokładnie 9 layoutów? Przy 500 000 zdjęć byłoby to do 4 500 000 layoutów.

### Q-003 — Źródło numeru sekwencji

Czy numer widoczny pod każdym layoutem na zdjęciu jest zawsze prawidłowym i unikalnym `sequence_number`? Czy mogą wystąpić luki, duplikaty numerów lub błędy OCR?

### Q-004 — Granica sekwencji

Co zrobić po dojściu do ostatniego layoutu:

- zatrzymać obliczenia,
- przejść do początku sekwencji,
- zgłosić brak dalszych danych?

## Blokujące algorytm wygranych

### Q-005 — Typy wzorców

Czy gra może jednocześnie używać:

1. konkretnych paylines, np. V,
2. reguły „dowolny rząd w kolejnych kolumnach”?

### Q-006 — Kierunek i początek dopasowania

Czy wygrana zawsze musi zaczynać się w pierwszej kolumnie, czy może zaczynać się w kolumnie 2 lub później?

### Q-007 — Długość dopasowania

Jeżeli występuje 5 kolejnych symboli, czy należy policzyć tylko wypłatę za 5, czy również wypłaty za 3 i 4?

**Rekomendacja:** liczyć wyłącznie najwyższą pasującą długość dla tego samego symbolu i wzorca, aby uniknąć przypadkowego wielokrotnego naliczenia.

### Q-008 — Wiele wystąpień tego samego symbolu w kolumnie

Dla reguły „dowolny rząd” może istnieć kilka pasujących kafelków w jednej kolumnie. Czy:

- wypłata jest liczona raz,
- każda kombinacja jest liczona osobno,
- liczba kombinacji mnoży wypłatę?

### Q-009 — Joker

Czy joker:

- zastępuje każdy zwykły symbol,
- może zastępować inny symbol specjalny,
- może sam tworzyć wygraną,
- ma własną tabelę wypłat,
- może zastępować kilka różnych symboli w jednym layoucie?

### Q-010 — Sumowanie wygranych

Czy sumujemy:

- wszystkie różne symbole,
- wszystkie paylines,
- powtarzające się kombinacje tego samego symbolu,
- tylko najwyższą wygraną na symbol?

## Blokujące target forecast

### Q-011 — Punkt startowy kosztu

Czy aktualnie rozpoznany layout jest „spin 0”, a koszt naliczamy dopiero dla layoutu `sequence_number + 1`?

**Rekomendacja:** tak.

### Q-012 — Warunek dodatniego wyniku

Czy rekord jest dodatni, gdy `cumulative_payout - cumulative_cost > 0`?

### Q-013 — Tabela wyników

Opis sugeruje pokazywanie tylko kolejnych rekordów ustanawiających nowy dodatni rekord netto (`high-water mark`). Czy dodatkowo ma być zawsze pokazany pierwszy moment wyjścia na plus?

### Q-014 — Duplikaty layoutu

Po wykryciu kilku identycznych pozycji użytkownik ma podać następny pełny layout. Czy aplikacja powinna zachowywać poprzedni layout jako kontekst i filtrować kandydatów według całego łańcucha?

**Rekomendacja:** tak, poprzez `confirmation chain`.

## Obraz i import

### Q-015 — Format zdjęć

Potrzebne są przykładowe oryginalne zdjęcia, ich rozdzielczość, orientacja, sposób rozmieszczenia 9 layoutów i numerów.

### Q-016 — Stabilność układu strony

Czy 9 layoutów i ich numery są zawsze w tych samych miejscach, czy zdjęcia mogą obejmować różne warianty ekranów/stron?

### Q-017 — Zestaw treningowy

Czy dla każdego symbolu można przygotować co najmniej 10–20 poprawnie oznaczonych wycinków z różnych zdjęć?

## Administracja i wdrożenie

### Q-018 — Publikacja danych

Czy administrator ma publikować wersjonowany zestaw danych, który aplikacja mobilna pobiera, czy mobile zawsze czyta bezpośrednio z tej samej bazy przez API?

### Q-019 — Wielu użytkowników

Czy system będzie używany tylko przez właściciela, czy przez kilka osób? To wpływa na autoryzację i konflikt edycji.

### Q-020 — Aplikacja referencyjna

Czy masz zgodę właściciela aplikacji Windows na analizę jej zachowania, plików i ruchu sieciowego? Bez zgody należy ograniczyć się do obserwacji funkcji i ręcznego tworzenia specyfikacji.
