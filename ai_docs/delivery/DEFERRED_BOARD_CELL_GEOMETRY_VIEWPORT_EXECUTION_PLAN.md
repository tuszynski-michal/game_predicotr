---
title: Deferred board-cell geometry viewport execution plan
status: accepted
last_updated: 2026-09-26
---

# Plan wykonania — viewport odroczonej korekty siatki

## Stan i cel

TASK-0693 pozwala zapisać niepełną planszę, lecz `DeferredBoardCellGeometryEditor`
rysuje zdjęcie w viewportcie obliczonym tylko z początkowego `boardQuad`.
Operator nie może przesunąć obrazu ani szybko wycentrować siatki po jej korekcie.
TASK-0699 ma umożliwić przesunięcie wyłącznie widoku i dopasowanie go do bieżącej
siatki, bez zmiany współrzędnych źródła lub trwałych danych.

## Zakres i decyzje

- Tło canvasu poza uchwytem narożnika uruchamia przeciąganie viewportu; obraz
  podąża za kursorem, a cztery narożniki nie zmieniają się.
- Akcja „Wycentruj widok na siatce” wylicza viewport z aktualnych narożników
  oraz istniejącego marginesu 35%.
- Po przesunięciu narożnika viewport automatycznie wraca do dopasowania
  bieżącej siatki, więc uchwyty pozostają widoczne.
- Dla pełnej planszy viewport nie wychodzi poza źródło. Dla częściowej używa
  istniejącego `allowOutsideSource`, a brak obrazu pokazuje się na szaro.
- Stan viewportu jest lokalny dla otwartego wpisu: nie wchodzi do komendy
  preview/save, nie jest utrwalany i resetuje się przy zmianie wpisu.
- Nie zmieniamy API, OpenAPI, schematu, workera ani kontraktu kwalifikacji.

## TASK-0699 — przesuwanie widoku Reviewera

- Status: `done`
- Implementacja: stan viewportu w `DeferredBoardCellGeometryEditor`, czysta
  funkcja translacji viewportu w `operational-review-state.ts`, dostępna
  etykieta instruktażowa i przycisk centrowania.
- Testy: translacja zachowuje wymiary, nie modyfikuje punktów źródłowych;
  viewport częściowy może obejmować szare tło; test kontraktu UI potwierdza
  kontrolki i rozróżnienie przeciągania tła od uchwytu.
- Weryfikacja: 201/201 testów Reviewera, lint, typecheck i production build
  są zielone. `test:geometry` nie uruchamia się przed testem z powodu
  wcześniejszego błędu Node 24 `uv_os_get_passwd ENOMEM`; build zawiera nową
  kontrolkę. Ręczny odbiór realnego wpisu zablokował błąd pobrania z API.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0699 | gpt-6-sol | high | Lokalny gest canvasu wymaga zachowania transformacji współrzędnych oraz regresji częściowych plansz, bez zmiany domeny i API. | gpt-6-astra / medium — review finalnego diffu UI i testów. |
