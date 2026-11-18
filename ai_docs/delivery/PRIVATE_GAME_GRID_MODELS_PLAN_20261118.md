---
title: Osobny model cięcia siatek dla każdej nowej gry
status: accepted
last_updated: 2026-11-18
---

# Osobny model cięcia siatek dla każdej nowej gry

Nowa gra V3 rozpoczyna od dopuszczonej bazy i uczy się z własnych korekt.
Przypisanie gry wyznacza wersję do porównania. Po realizacji tego planu operator zmienił sposób inicjalizacji pierwszego prywatnego treningu. TASK-1257 i [D-619](../process/decisions/DECISION_LOG_2026.md#d-619--niezależny-pierwszy-trening-geometrii-gry) wprowadzają start obu sieci od zera. Późniejsza kontynuacja korzysta z potwierdzonych własnych wag gry.
Pierwszą istniejącą grą objętą zmianą na jawne polecenie będzie Mumie A2.
Ostatni potwierdzony odbiór zapisał wersję gry `6cc10344` i domyślną
`01767a49`. Przy wykonaniu należy odczytać bieżące przypisanie.

## 1. Własność modelu i utworzenie gry

- Jedna addytywna migracja Alembic utrwala regułę prywatności oraz relację
  jednej gry z jedną rodziną. Pochodzenie od wersji bazowej i własność rodziny
  są odrębne. Migracja nie przełącza istniejących gier.
- Zwykłe tworzenie V3, ponowienie z tym samym kluczem i pierwsze przypisanie
  korzystają z obecnej rezerwacji. Bez dopuszczonej bazy zapamiętać zamiar,
  pokazać warunek importu i utworzyć rodzinę z jawnie wybranej dopuszczonej
  bazy przy pierwszym przypisaniu.
- Polecenie włączenia Mumii opiera nową rodzinę na aktualnej wersji gry.
  Sprawdzić rewizję pod blokadą, uwzględnić aktywne operacje obejmujące grę,
  zachować potwierdzenie i historię. Nie przejmować rodziny bazowego modelu.
- Nowe wspólne treningi nie mogą pobierać próbek z gry prywatnej, również
  przez wcześniejsze kohorty. Zachować odtwarzalność ukończonych operacji.
  Sprawdzić tworzenie dwóch gier z jednej bazy i zachowanie starszych rekordów.

## 2. Uczenie z aktualnej wersji gry

- Dla prywatnej gry powiązać podgląd, gotowość, przygotowanie w tle,
  start, wznowienie, trening i ocenę z identyczną polityką. Przypiąć grę,
  rewizję przypisania, rodzinę docelową, bazę i sumę jej manifestu. Baza
  pierwszej iteracji może należeć do innej rodziny niż wynik.
- W zestawie zachować tożsamość zdjęć, rewizje etykiet, podział i wykluczenia
  przodków, tryb treningu, wersję wycinania oraz dowód gotowości detektora.
  Trudne poprawione przypadki i poprawne zatwierdzenia tylko z tej gry.
  Kontrolować zapis i odczyt dowodów również w SQL i w zadaniach potomnych.
- W Adminie pokazać nazwę gry, przypisaną wersję, liczność i braki danych.
  Starsze polecenie wspólne dla prywatnej gry odrzucić z czytelną przyczyną.
  Zmiana przypisania w trakcie skutkuje wynikiem nieaktualnym, bez publikacji.
  Zachować istniejące bramki i historię operacji. Rozszerzyć backend, OpenAPI,
  generowany klient, wrapper i test żądania w jednym pionie.

## 3. Zastosowanie i cofnięcie

- Po jawnej decyzji operatora publikować kandydata i przypisywać wyłącznie do
  tej gry. Kontrolować prywatność również przy bezpośrednim użyciu rejestru,
  globalnym ustawieniu modelu, wyborze bazy i przypisaniu innej grze.
- Cofnięcie wymaga dopuszczonej wersji z historii przypisań tej gry oraz
  zgodnej rewizji. Rozpoczęty import zachowuje model z preflightu. Nowy
  import bierze aktualne przypisanie.
- Test na odrębnym PostgreSQL oraz przez HTTP i Admin obejmuje dwie gry, dwa
  kolejne treningi, zmianę niezwiązanego defaultu, zmianę przypisania gry,
  restart, utratę odpowiedzi, idempotencję i konkurujące polecenia. Sprawdzić
  migrację i zachowanie starszego klienta. Audyt kodu Opus 5.5 przed integracją.

## 4. Pilot Mumii A2

- Przed diagnozą zamrozić manifest 100 plansz ze 100 świeżych zdjęć. Dobór
  ma być niezależny od wykrycia i filtra podejrzeń. Chronić zdjęcia, ich kopie
  i powiązane nagrania przed treningiem i doborem przypadków diagnostycznych.
  Brak detekcji pozostaje w mianowniku.
- Na odrębnej próbce zestawić oryginał, wejście modelu, geometrię i końcowe
  15 obrazów pól. Rozróżnić błędy obrysu planszy, siatki, zapisu wycinków,
  przypadki mieszane i ucięcie na samym oryginale. Podsumować kwalifikację
  i powody wykluczeń w 708 historycznych parach z 521 zdjęć.
- Dobrać właściwy etap poprawy. Częściowe korekty służą do uczenia węzłów.
  Detektor wymaga odpowiednio oznaczonych pełnych zdjęć i istniejącej bramki
  gotowości. Poprawkę zapisu wycinków najpierw zmierzyć na tej samej wersji
  modelu. Modele porównywać przy identycznym zapisie wycinków.
- Operator ocenia te same plansze bez ujawnienia wersji. Raport podaje liczbę
  wymagających poprawy, naprawionych, pogorszonych oraz liczbę nowych ucięć.
  Brak planszy lub choć jedno pole do korekty oznacza planszę do poprawy.
  Zaproponować aktywację przy zysku netto co najmniej 5/100, zerze nowo
  obciętych wcześniej pełnych symboli i pozytywnym wyniku dotychczasowych
  kontroli jakości. Kolejna dostrojona próba wymaga świeżego sprawdzianu.

## Odbiór i uprawnienia

Kod i test migracji na osobnej gałęzi oraz izolowanej bazie. Migracja bazy
operatora, trening na jego danych, publikacja, aktywacja, operacje na main i
restart usług wymagają odrębnych poleceń. Ocena pilota wymaga decyzji człowieka.
Audyt projektu planu w Claude Code Opus 5.5 zakończył się REVISE. Powyższa
wersja uwzględnia uwagi. Fable 5.2 zgłosił wyczerpanie limitu.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| 1. Własność modelu i utworzenie gry | gpt-6.2-sol | high | Trwałe przypisanie, migracja i idempotencja. | Kontrola integracyjna w zadaniu 3. |
| 2. Uczenie z aktualnej wersji gry | gpt-6.2-astra | high | Spójność danych i wznawiania treningu. | Kontrola integracyjna w zadaniu 3. |
| 3. Zastosowanie i cofnięcie wersji | gpt-6.2-sol | high | Izolacja dwóch gier od utworzenia do importu. | claude-opus-5-5 / high przed integracją. |
| 4. Pilot i pomiar Mumii A2 | gpt-6.2-astra | high | Rozpoznanie źródła cięcia i niezależny pomiar. | Ślepa ocena operatora. |
