---
title: TASK-0414 Preserve multi-board geometry drafts
status: done
last_updated: 2026-09-03
---

# TASK-0414 — Zachowanie szkicu wielu plansz w edytorze geometrii

## Problem

Tryb `Wyznacz plansze osobno` trzyma szkice narożników w mapie jednego źródła,
ale kliknięcie `Zakończ plansze osobno` ponownie inicjalizuje tę mapę. Po
wybraniu drugiej planszy pierwszy quad wraca więc do automatycznej geometrii,
chociaż operator nie anulował swojej pracy.

## Scope

- zachować lokalne szkice wszystkich slotów po wyjściu i ponownym wejściu do
  trybu wielu plansz;
- poza aktywnym trybem nadal rysować niepusty szkic wcześniej wyznaczonej
  planszy, a dla niewyznaczonego slotu pokazać automat;
- przy wejściu wybrać następny niekompletny slot w kolejności row-major;
- nie zmieniać zapisu, topologii, API ani trwałych danych;
- dodać test regresji przejścia plansza 1 → wyjście → plansza 2.

## Out of scope

- brak trwałości niezatwierdzonego szkicu po odświeżeniu strony;
- brak zmiany pojedynczego edytora oraz workflow legacy.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Definition of Done

- wyznaczony quad nie znika po zmianie aktywnej planszy ani po chwilowym
  wyjściu z trybu wielu plansz;
- kolejne wejście prowadzi do pierwszego niekompletnego slotu row-major;
- zapis pozostaje dostępny tylko dla kompletnego źródła;
- test regresji i kontrola typu Reviewera przechodzą.

## Outcome

- Usunięto reset `sourceDrafts` podczas wstrzymania oraz wznowienia trybu
  wieloplanszowego. Główny edytor zachowuje teraz tę samą instancję dla całego
  `sourceImageId`, a zmiana aktywnego slotu nie odmontowuje mapy szkiców.
- Wstrzymany szkic pozostaje widoczny poza trybem edycji; wznowienie wskazuje
  pierwszy niekompletny slot w kolejności row-major.
- Przy zmianie wybranego slotu poza trybem wieloplanszowym szkic pojedynczej
  planszy nadal wraca do automatycznej geometrii, więc nie zmieniono workflowu
  pojedynczej korekty.
- Weryfikacja: skoncentrowane testy Reviewera, `npm run typecheck --workspace
  @game-predictor/reviewer` oraz `npm run lint --workspace
  @game-predictor/reviewer` przeszły pomyślnie.
