---
title: TASK-0389 — Trwałe grafiki z pojedynczo zatwierdzonych cropów
status: done
last_updated: 2026-09-02
---

# TASK-0389 — Trwałe grafiki z pojedynczo zatwierdzonych cropów

## Goal

Umożliwić wybranie grafiki katalogowej z każdego aktualnego, pojedynczo
zatwierdzonego cropa symbolu oraz po zatwierdzeniu zapisać trwałą,
checksumowaną kopię pliku. Aplikacja mobilna ma czytać wyłącznie tę kopię,
nigdy staging, atlas podglądu ani renderowany w locie crop v0.10.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- kandydaci picker'a pochodzą z bieżących komórek `approved`, aktywnego
  symbolu, bez problemu jakości i z pełną zgodnością zatwierdzonej tożsamości
  cropa z tożsamością bieżącą;
- obejmują cropy legacy oraz `virtual_source` v0.10;
- wybór legacy zachowuje dotychczasową kopię bajtów, a wybór v0.10 renderuje
  pełny, checksumowany crop źródłowy raz do trwałego PNG;
- rekord referencji przechowuje checksumę fizycznie zapisanych bajtów, a nie
  checksumę wirtualnej tożsamości renderera;
- endpoint podglądu renderuje bieżący wirtualny crop tylko przed wyborem;
  endpoint grafiki symbolu zawsze zwraca wyłącznie trwały plik;
- komunikat Admina opisuje pojedynczo zatwierdzone cropy.

## Out of scope

- zmiana kwalifikacji kohort treningowych — pojedyncze zatwierdzenia już do
  niej trafiają;
- generowanie referencji automatycznie bez decyzji operatora;
- usuwanie istniejących referencji, stagingu lub cache atlasów;
- zmiana formatu odpowiedzi listy kandydatów.

## Invariants

- kandydat stale lub zmieniony po zatwierdzeniu jest odrzucany fail-closed;
- referencja v0.10 nie używa atlasu WebP ani zmniejszonego podglądu;
- zapis jest content-addressed, atomowy i odporny na kolizję;
- referencja nie wymaga dalszego dostępu do źródła ani renderera po udanym
  zatwierdzeniu;
- historyczne referencje legacy pozostają czytelne.

## Acceptance criteria

- pojedynczo zatwierdzony crop z planszy `pending` jest widoczny w pickerze;
- crop z niezgodną tożsamością zatwierdzoną nie jest widoczny;
- v0.10 zapisuje trwały PNG o własnej sumie SHA-256 i endpoint referencji
  serwuje jego bajty po usunięciu cache podglądów;
- wybór legacy nadal zachowuje oryginalne bajty i checksumę;
- schema bazy dopuszcza `resolution_revision = 0` dla pojedynczego cropa bez
  rozstrzygnięcia całej planszy;
- testy obejmują eligibility, v0.10 materializację i konflikt stale.

## Outcome

- Picker korzysta z aktualnych, pojedynczo zatwierdzonych komórek, niezależnie
  od statusu całej planszy.
- Zatwierdzenie legacy zachowuje kopię oryginalnych bajtów, a `virtual_source`
  v0.10 materializuje jeden pełnowymiarowy PNG pod checksumowaną ścieżką
  referencji.
- Referencja zapisuje checksumę fizycznego artefaktu; po wyborze odczyt nie
  wymaga stagingu, atlasu ani renderera.
- Dodano migrację dopuszczającą rewizję rozstrzygnięcia `0` dla pojedynczo
  zatwierdzonych cropów oraz testy kwalifikacji, materializacji i trwałego
  odczytu.
