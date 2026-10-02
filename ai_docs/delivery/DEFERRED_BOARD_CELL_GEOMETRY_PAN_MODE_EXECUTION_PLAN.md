---
title: Plan wykonania — jawny tryb przesuwania kadru odroczonej siatki
status: accepted
last_updated: 2026-09-26
---

# Jawny tryb przesuwania kadru odroczonej siatki

## Stan obecny i cel

`DeferredBoardCellGeometryEditor` po TASK-0699 pozwala przesuwać lokalny viewport
źródła poza czterema uchwytami. To koliduje z ręcznym ustawianiem siatki: zwykłe
przeciągnięcie wewnątrz canvasu przesuwa zdjęcie. Celem jest domyślnie statyczny
widok oraz jawne, chwilowe włączenie panoramowania bez zmiany geometrii,
kwalifikacji, preview, API albo danych trwałych.

## Decyzja

Dodaj lokalny checkbox `Aktywne przesuwanie`, domyślnie odznaczony dla każdego
wczytanego elementu. Cztery numerowane uchwyty zawsze edytują narożniki. Tylko
gdy checkbox jest zaznaczony, przeciągnięcie poza uchwytem przesuwa viewport.
Wyłączenie checkboxa nie centruje ani nie resetuje kadru — po prostu blokuje
następny gest panoramowania.

## TASK-0700 — jawna aktywacja panoramowania viewportu

Zmienić `DeferredBoardCellGeometryEditor`, jego opis operatorski i kontraktowy
test UI. Zachować istniejące granice pełnego/częściowego zdjęcia oraz przycisk
centrowania. Test ma chronić domyślnie wyłączony tryb i warunek rozpoczęcia
panoramowania. Nie zmieniać kontraktu backendu, geometrii source-direct ani
trwałego stanu.

Odbiór: na canvasie bez zaznaczonego checkboxa tylko chwyt uchwytu zmienia
narożnik, a tło pozostaje statyczne; po zaznaczeniu tło przesuwa wyłącznie
lokalny viewport; preview i zapis nadal używają niezmienionych współrzędnych
źródła.

## Przypisanie modeli do zadań

| Zadanie                                             | Model     | Reasoning | Uzasadnienie                                                                              | Dodatkowy review                                  |
| --------------------------------------------------- | --------- | --------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------- |
| TASK-0700 — jawna aktywacja panoramowania viewportu | gpt-6-sol | high      | Mała zmiana interakcji canvasu z wymaganym testem regresji i ochroną semantyki geometrii. | Zalecany niezależny review: gpt-6-astra / medium. |
