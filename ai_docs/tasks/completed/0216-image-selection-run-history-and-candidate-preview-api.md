---
title: TASK-0216 image-selection run history and candidate preview API
status: done
release: "0.4"
last_updated: 2026-08-09
---

# TASK-0216 — Historia runów i preview kandydatów

## Goal

Dodać stronicowaną historię runów gry oraz bezpieczny odczyt JPEG-a kandydata
należącego do wskazanej grupy.

## Verification

Izolacja po grze/runie/grupie, bounded strony, staging i manual storage bez
ujawnienia ścieżek absolutnych.

## Outcome

Dodano stronicowaną historię runów gry oraz endpoint JPEG-a kandydata z kontrolą
`run + group + candidate` i rozwiązywaniem tylko w zarządzanym stagingu/manual
storage. Skupiona regresja workera/API przeszła 149/149, w tym izolację,
bounded stronę, restart i odczyt pliku bez ujawnienia ścieżki absolutnej.
Odbiór UI pozostaje w TASK-0218 i nie blokuje ukończenia kontraktu API.
