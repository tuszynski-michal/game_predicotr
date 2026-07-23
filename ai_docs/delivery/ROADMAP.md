---
title: Delivery roadmap
status: proposed
last_updated: 2026-07-23
---

# Roadmap

Każdy milestone kończy się działającym pionem funkcjonalnym. Nie rozpoczynamy rozpoznawania zdjęć przed ustabilizowaniem modelu danych i ręcznego importu.

## M0 — Architecture clarification

### Cel

Zamknąć pytania blokujące i zaakceptować stos.

### Rezultat

- odpowiedzi na Q-001–Q-020,
- zaakceptowane decyzje D-001–D-006,
- ustalony model online/offline,
- próbki zdjęć zinwentaryzowane,
- definicja algorytmu wygranych wystarczająca do testów.

## M1 — Mocked mobile vertical slice

Szczegóły: [MILESTONE_01_MOCKED_MOBILE.md](MILESTONE_01_MOCKED_MOBILE.md)

### Rezultat

Mobile + API + PostgreSQL, 3 gry, 1000 układów na grę, prefix matching, modal, exact matching i duplikaty.

## M2 — Admin configuration

### Zakres

- CRUD gier,
- CRUD symboli,
- edytor paylines,
- payout rules,
- generator/import mock layouts,
- walidacja sekwencji.

### Rezultat

Dane dla M1 mogą być tworzone z UI admina zamiast seedów.

## M3 — Payout engine

### Zakres

- dokładnie uzgodnione typy wzorców,
- joker,
- sumowanie,
- audytowalne match details,
- testy golden cases.

### Rezultat

Backend oblicza payout jednego layoutu.

## M4 — Target forecast

### Zakres

- analiza do 100 000 kolejnych układów,
- high-water marks,
- obsługa końca sekwencji,
- wersjonowanie wyniku,
- pomiar wydajności.

### Rezultat

Mobile pokazuje tabelę targetu dla jednoznacznej pozycji.

## M5 — Manual data import

### Zakres

- import CSV/JSON przygotowanego zewnętrznie,
- staging,
- walidacja,
- raport luk i duplikatów,
- publikacja datasetu.

### Rezultat

System jest gotowy przyjąć dane z późniejszego pipeline'u obrazowego.

## M6 — Image ingestion prototype

### Zakres

- 20–100 reprezentatywnych zdjęć,
- korekta perspektywy,
- detekcja 9 layoutów,
- OCR numerów,
- ręczne wycinki symboli,
- raport jakości.

### Bramka

Nie przechodzimy do masowego importu, dopóki prototyp nie osiągnie zaakceptowanych metryk.

## M7 — Symbol classifier and review workflow

### Zakres

- oznaczone przykłady,
- klasyfikacja z confidence,
- manual review,
- zapisywanie korekt jako dataset.

## M8 — Large-scale resumable import

### Zakres

- pełny worker,
- batch processing,
- wznowienia,
- statystyki,
- obciążeniowe testy bazy,
- publikacja dużej wersji danych.

## M9 — Distribution and production hardening

Zależne od decyzji wdrożeniowej:

- backend dostępny zdalnie lub snapshot offline,
- autoryzacja,
- backup,
- monitoring,
- build Android,
- aktualizacje datasetu.

## Zasady przejścia

- milestone ma własne kryteria akceptacji,
- otwarte błędy krytyczne blokują przejście,
- każda zmiana modelu domenowego aktualizuje dokumentację,
- nowe technologie wymagają wpisu do Decision Log,
- wydajność mierzymy na reprezentatywnych danych, a nie na 100 rekordach.
