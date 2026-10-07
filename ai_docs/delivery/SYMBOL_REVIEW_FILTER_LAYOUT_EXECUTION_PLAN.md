---
title: Zwijane filtry weryfikacji symboli
status: accepted
last_updated: 2026-10-07
---

# Zwijane filtry weryfikacji symboli

## Stan obecny, cel i reguły

Użytkownik zleca pojedynczy wiersz opcji dla stanu, pewności i źródła predykcji
oraz zwijanie tych filtrów i daty, aby powiększyć listę w pełnym ekranie.
Istniejący `symbol-review-workspace.module.css` narzuca trzy kolumny dla
fieldsetów, dlatego kolejne opcje przechodzą niżej. Workspace przechowuje
warunki i roboczy zakres dat niezależnie od renderowania filtrów.

Zalecenie: trzy grupy zajmują pełną szerokość; każda ma jeden pasek opcji bez
zawijania. Na małym ekranie pasek przewija się poziomo w swoim kontenerze,
bez poszerzania strony. Dwie niezależne sekcje, `Filtry szczegółowe` i
`Data zmiany komórki`, są początkowo rozwinięte. Zwijanie ukrywa zawartość,
zachowuje jej DOM i wartości oraz nie pobiera danych ani nie czyści zaznaczeń.
Nagłówki pokazują liczbę aktywnych filtrów/aktywny zakres dat. Stan zwinięcia
pozostaje podczas przełączania pełnego ekranu; po nowym wejściu sekcje są otwarte.

## TASK-0896 — układ i zwijanie filtrów

Zadanie: [0896-symbol-review-filter-layout.md](../tasks/completed/0896-symbol-review-filter-layout.md).
Istniejący `SymbolReviewWorkspace` otrzyma lokalny komponent sekcji z
`aria-expanded`, `aria-controls`, przyciskiem i ukrytą zawartością. Enter na
przycisku sekcji nie może wywołać globalnego zapisu symbolu. Zachować obecną
logikę radio, daty, zmiany filtra, wyboru celu i wszystkich mutacji.
Zmienić tylko workspace/CSS, testy interakcji i wymagania/guide/CURRENT_STATE.
Nie rozszerzać API, nie wykonywać decyzji na danych ani restartu usług.

## Odbiór i ryzyka

Regresja interakcji: niezależne zwijanie, zachowane zaznaczenia/radio/draft
dat, brak odczytów i mutacji po zwijaniu, pełny ekran i Enter na nagłówku.
Zwykłe testy zapisu pozostają. Sprawdzić scoped format/lint/types, następnie
build. Komendy przez istniejący absolutny runner z limitem 120 s.
Przeglądarka: normalny/pełny ekran i szerokość 390 px; opcje na jednym poziomie,
lokalny overflow, większa wysokość cropów po zwinięciu, dostępne nagłówki.
Nie uruchamiać prawdziwej decyzji; zapisać screenshot jako dowód.
Ryzyka: CSS nie może nadpisać atrybutu hidden; klawiatura nagłówka nie może
zapisać cropa. Brak blokującej decyzji, migracji, treningu, wdrożenia lub merge.

## Wynik

TASK-0896 wykonany. Interakcje 14/14 i kontrakty/helpery 40/40 zaliczone;
scoped format/lint/types i build Admina zaliczone. Przeglądarka potwierdza
jednoliniowe grupy, niezależne zwijanie, powiększenie listy i lokalny scroll
na 390 px bez poszerzenia strony. Szczegóły i ograniczenia zawiera Outcome.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
| TASK-0896 | gpt-6.1-sol | high | Układ responsywny i kontrola klawiatury w istniejącym workflow. | Audyt własny oraz odbiór UI; bez delegowania. |
