---
title: TASK-0217 manual image-selection gallery
status: in_progress
release: "0.4"
last_updated: 2026-08-09
---

# TASK-0217 — Galeria ręcznej selekcji

## Goal

Pozwolić wybrać historyczny job, obejrzeć miniatury całej zachowanej grupy,
otworzyć pełny podgląd i zatwierdzić istniejący JPEG bez szukania na dysku.

## Verification

Mysz i klawiatura, lazy thumbnails, pełny preview, statusy błędów oraz zachowany
fallback uploadu pojedynczego JPEG-a.

## Outcome

Workspace ma sekcję `Zapisane procesy`, a modal galerię lazy-load, pełny podgląd
i wybór istniejącego kandydata. Nowy worker utrwala lekkie rekordy wszystkich
źródeł grupy; nie są one używane przy wznowieniu algorytmu. Starszy run pokazuje
licznik zachowanej shortlisty względem `sourceCount`. Manualny test przeglądarki
pozostaje w TASK-0218.
