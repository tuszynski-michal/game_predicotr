---
title: TASK-0216 image-selection run history and candidate preview API
status: in_progress
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
storage. Testy API obejmują izolację i odczyt pliku; odbiór UI pozostaje w
TASK-0218.
