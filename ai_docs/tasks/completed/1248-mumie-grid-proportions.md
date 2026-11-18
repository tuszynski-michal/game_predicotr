---
title: Ocena proporcji siatek Mumii A2
status: done
last_updated: 2026-11-18
---

# TASK-1248 — Ocena proporcji siatek Mumii A2

## Status

`done`

## Goal

Policzyć powtarzalny wynik podejrzenia przycięcia na podstawie 24 zapisanych węzłów.

## Recommended execution

`gpt-6.2-sol`, `medium`. Reguła została zmierzona na ręcznych poprawkach. Niezależny audyt niewymagany.

## Relevant docs

- `../process/CURRENT_STATE.md`
- `../requirements/ADMIN_APP.md`
- `../architecture/ITERATIVE_IMAGE_IMPORT.md`

## Acceptance criteria

- [x] Ocena wykorzystuje proporcje boków, całej planszy i lokalnych odstępów zgodnie z pomiarem.
- [x] Wynik wskazuje przyczynę i pola sąsiadujące z największym odchyleniem, jeśli można je ustalić.
- [x] Nieprawidłowa geometria otrzymuje brak oceny.

## Technical notes

Reguła wykorzystuje współrzędne oryginalnego zdjęcia. Próg 1,142 pochodzi z podziału po sumie pikseli znormalizowanego zdjęcia. Sam wynik służy do rankingu do ręcznej oceny. Patrz `grid_cut_suspicion.py`.

## Outcome

Commit: v1.7.674 / `54568609f281fc8297f2380a073e40ef6d77b432`.

Funkcja ocenia trzy cechy geometrii, wskazuje dominującą przyczynę i odcinek
oraz odrzuca niekompletne i zdegenerowane siatki. Dziesięć testów domenowych
przeszło. Powtórzenie odczytu 708 par dało 49/73 wykrytych dużych zmian i
9/110 wskazań po korekcie na 110 odłożonych planszach. Przesunięcie całej
siatki z zachowaniem proporcji może pozostać niewykryte.
