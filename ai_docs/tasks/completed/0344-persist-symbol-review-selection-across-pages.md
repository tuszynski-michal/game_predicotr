---
title: TASK-0344 — Trwałe zaznaczenie cropów między stronami
status: done
version: 0.10
---

# TASK-0344 — Trwałe zaznaczenie cropów między stronami

## Cel

Pozwolić operatorowi połączyć jawnie zaznaczone cropy z wielu keysetowych stron
Weryfikacji symboli w jedną operację masową, bez podnoszenia limitu strony ponad
500 metadanych.

## Zakres

- zachować `selection` oraz ukryte po skutecznej decyzji targety przy
  przejściu na poprzednią i następną stronę;
- przekazać do śledzenia zakończonej operacji wszystkie jawne ID z wyboru, nie
  wyłącznie elementy bieżącej strony;
- potwierdzić testem akumulację wyboru z kolejnych stron.

## Invarianty

- pojedyncza strona API nadal ma maksymalnie 500 metadanych;
- jawny wybór pozostaje ograniczony do 10 000 checksum-bound targetów;
- zmiana filtra, wyczyszczenie wyboru albo przekazanie joba nadal kończy
  bieżące zaznaczenie;
- nie są pobierane dodatkowe cropy ani obrazy poza istniejącym keysetem.

## Outcome

- Wybór ze stron 1, 2, 3 i kolejnych pozostaje aktywny; toolbar pokazuje
  łączną liczbę i wysyła jeden job masowy.
- Po pełnym sukcesie ukrywane są wszystkie jawnie wysłane targety, także gdy
  operator wróci do strony, z której pochodziły.
