---
title: Uproszczenie wyszukiwarki plansz
status: accepted
last_updated: 2026-11-17
---

# Wykonanie TASK-1238

## Cel i ustalenia

Operator zatwierdził realizację wszystkich 13 punktów, koszt pracy 45–90 min
i usunięcie wyłącznie „Poprzedni układ” / „Następny układ” przy zdjęciu.
„Poprzednia” / „Następna” w rankingu dopasowań pozostają. Jedyny task:
`ai_docs/tasks/completed/1238-board-search-compact-ui.md`.

Zmiana obejmuje zwykłą wyszukiwarkę Admina i linków. Kompaktowy edytor panelu
zarządzania zachowuje dotychczasowe domyślne zachowanie. Bez zmian API,
rankingu, kalkulatora, danych, restartów, merge i pushu.

## Implementacja

- **Wprowadzanie:** pierwszy symbol po jawnym, poprawnym wysłaniu szukania
  rozpoczyna nowy wzór; następne uzupełniają go. W nowym wzorze Cofnij nie
  odtwarza poprzedniej planszy. Automatyczny refresh limitu lub korekty nie
  rozpoczyna nowego wzoru. Resetuj zastępuje pełne czyszczenie „Nowe szukanie”,
  w tym zapis przeglądarki i kontekst wyników. Zapisany rozpoczęty nowy wzór
  musi przetrwać ponowne zamontowanie widoku.
  Opcjonalne `nextSymbolStartsPattern` w zapisie v2 zachowuje ten stan także
  dla nowego wzoru identycznego z poprzednim; stare zapisy są odczytywane.
- **Wyniki:** podczas wyszukiwania ukryć stary podgląd i wygraną, zachowując
  wewnętrzny snapshot potrzebny do refreshu i wyboru trafienia. Po błędzie
  pokazać błąd bez starego podglądu; po sukcesie nowy wynik lub stan pusty.
  Zachować blokadę szukania podczas kalkulacji i ochronę przed spóźnioną
  odpowiedzią po resecie. Zdjęcie dotyczy znalezionego trafienia; następne
  trafienie nadal wybiera się według rankingu. Usunąć cztery pola dowodów.
- **Układ:** mniejszy tytuł, bez opisów nagłówka i „Twój wzór”; radio buttony
  bez dodatkowych tekstów. Schować przycisk `?`, zachowując zapisane dane
  i skróty klawiatury. Trzy akcje w jednym rzędzie, Szukaj wypełnia wolną
  przestrzeń, liczba wyników bezpośrednio pod nim. Na telefonie paleta
  mniejszych kafelków o celu dotykowym co najmniej 44 px, bez przewijania
  poziomego. Wynik w jednym wierszu: układ, procent i pozycja w rankingu.
- **Linki i wygrana:** u góry panelu linku zostawić select gry; dla linku
  jednej gry pozostawić zwięzłą nazwę tej gry. Zachować obsługę wygaśnięcia
  dostępu. Przy zakresie i stawce usunąć zbędne nagłówki oraz podpowiedź
  mnożnika; wykres z istniejącym podglądem planszy ma poprzedzać dodatkowe
  podsumowania. Zachować ostrzeżenia domenowe i dalszą tabelę/filtrowanie.
- **Wspólne elementy:** nowe opcje prezentacji Results/ApproximateWin są
  opcjonalne i domyślnie wyłączone; włącza je zwykła wyszukiwarka. Style
  ograniczyć do jej klasy. Uaktualnić wymagania, mapę kodu i task.

## Weryfikacja i zakończenie

- Pokrycie: testy interakcji resetu/nowego wzoru/loading/error/ponownego
  montowania (1–2,8), nawigacji rankingu i braku sąsiednich zdjęć (3),
  kontrolek i struktury strony (4,6–7,9–13); przegląd layoutu mobilnego (5).
- Najpierw zmienione testy interakcji; potem pełne testy i interakcje pakietu
  `@game-predictor/board-search-ui`, lint zmienionych plików, typecheck
  pakietu i obu aplikacji, test panelu Reviewera. Każda komenda ≤120 s.
- Sprawdzić dostępność etykiet bez widocznych opisów, render mobilny
  320/375/768 px oraz regresję domyślnego widoku panelu zarządzania.
  Bez startowania usług; fizyczny Android wymaga odbioru operatora.
- Format tylko zmienionego kodu, regeneracja mapy, `code-map:check`,
  `docs:check`. Testy planowane nie są wynikami. Zamknięcie przez task-close,
  osobny commit taska i następny commit hasha. Zatrzymanie przed merge.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1238 — wszystkie 13 zmian | gpt-6.1-sol | high | Zmiana współdzielonego UI i stanów asynchronicznych, z istniejącymi testami regresji. Zmiana API lub modelu domenowego wymaga ponownej oceny zakresu. | Nie; testy zmienionego pionu i regresja domyślnych konsumentów. |
