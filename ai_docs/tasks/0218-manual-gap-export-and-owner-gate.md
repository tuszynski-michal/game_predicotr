---
title: TASK-0218 manual gap export and owner gate
status: in_progress
release: "0.4"
last_updated: 2026-08-09
---

# TASK-0218 — Uzupełnianie katalogu i odbiór

## Goal

Po powrocie do joba dopisywać ręcznie wybrane brakujące reprezentanty do jego
katalogu wynikowego, a następnie wykonać małą regresję przed ręcznym testem
większej partii.

## Verification

Idempotentny ledger, brak nadpisania kolizji, test 0–199 i trudny wycinek;
duży test 5000/32079 wykonuje właściciel.

## Outcome

Backend pozwala poprawić także opublikowaną wcześniej grupę: unieważnia stary
manifest, zapisuje audyt decyzji i wznawia zakończony job do ponownej publikacji.
Panel po ręcznym zatwierdzeniu dopisuje dokładnie brakującą grupę do ponownie
wskazanego folderu. Testy automatyczne przechodzą; test przeglądarkowy,
decyzja właściciela oraz większa próba pozostają otwarte.

Automatyczna część bramki jest ukończona. Pierwsze 200 rzeczywistych zdjęć
dało kanonicznie identyczne decyzje dla jednego i dwóch verifierów. Trudny
wycinek `29640–29739` nie wyeksportował niespójnego reprezentanta i skierował
mieszaną grupę do `manual_required`. Pozostają: manualny odbiór galerii,
rzeczywisty pomiar kursora eksportu i warm cache oraz test 5000/32079.
