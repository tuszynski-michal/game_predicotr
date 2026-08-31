---
title: TASK-0362 Read-only symbol preview A/B
status: done
relevant_docs:
  - ai_docs/requirements/ADMIN_APP.md
  - ai_docs/architecture/API_CONTRACT.md
  - ai_docs/architecture/SYSTEM_ARCHITECTURE.md
---

# TASK-0362 — Podgląd A/B silnika v0.10

## Goal

Pozwolić operatorowi porównać bieżący crop z rendererem strukturalnym v0.10
bez tworzenia decyzji, cropów, jobów ani zmiany polityki silnika gry.

## Scope

- jawny wybór `current` / `structured_v0_10` w Weryfikacji symboli;
- osobna wersja i fingerprint renderera w API oraz kluczu atlasu;
- brak fallbacku do pliku legacy, gdy proweniencja v0.10 nie istnieje;
- blokada zaznaczania i wszystkich mutacji w trybie eksperymentalnym;
- testy cache identity, dostępności i kontraktu read-only.

## Outcome

- API rozdziela oba renderery content-addressed fingerprintem i raportuje
  niedostępne komórki bez tworzenia fałszywego obrazu v0.10.
- Admin pokazuje placeholder `Brak v0.10` dla komórek bez proweniencji oraz
  czytelny komunikat, że tryb eksperymentalny jest tylko do odczytu.
- Przełączenie podglądu nie zmienia listy logicznych komórek; czyści jedynie
  lokalne zaznaczenie i ładuje właściwe atlasy.
- Testy API, renderera i Admina potwierdzają brak kolizji cache oraz blokadę
  ścieżek mutujących.

