---
title: TASK-0145 source-aware cumulative training dataset
status: done
last_updated: 2026-08-01
---

# TASK-0145 — Source-aware cumulative training dataset

## Status

`done`

## Goal

Zbudować odtwarzalny dataset treningowy ze skumulowanej kohorty, z
deterministycznym podziałem według źródła i bez przecieku danych.

## Context

Wiele cropów z jednego zdjęcia jest silnie skorelowanych. Losowy podział po
cropach zawyżałby wynik i mógłby promować gorszy model.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/delivery/MILESTONE_06_6_EXECUTION_PLAN.md`
- `ai_docs/tasks/completed/0143-cumulative-verified-training-cohort-contract.md`

## Scope

- materializować dataset z niezmiennego manifestu kohorty,
- walidować checksumy cropów, kompletność etykiet i katalog symboli gry,
- grupować po zdjęciu źródłowym i pochodnych tego samego materiału,
- tworzyć deterministyczne train/validation/test oraz stabilny regression set,
- generować manifest, statystyki per symbol/źródło/split i listę wykluczeń,
- zapisywać artefakt content-addressed,
- zapewnić identyczny wynik dla identycznego wejścia.

## Out of scope

- trening modelu,
- zmiana geometrii lub ponowne wycinanie cropów,
- ręczne uzupełnianie etykiet,
- aktywacja modelu.

## Acceptance criteria

- [x] Identyczna kohorta i konfiguracja dają identyczny manifest i SHA-256.
- [x] Żadne zdjęcie źródłowe ani jego pochodne nie występują w więcej niż
      jednym split.
- [x] Dataset zawiera wyłącznie etykiety zapisane przez człowieka dla pełnych
      `accepted` i `corrected` plansz.
- [x] Brak pliku, niezgodna checksum lub nieznany symbol zatrzymuje build przed
      treningiem ze stabilnym kodem błędu.
- [x] Raport pokazuje niedoreprezentowane klasy oraz rozmiary wszystkich części.
- [x] Stały regression set nie jest dołączany do train.
- [x] Artefakty są zapisane pod `data/training`, a baza przechowuje ścieżki i
      metadata zamiast obrazów.

## Technical notes

Trening kolejnej wersji używa całej skumulowanej kohorty, nie tylko nowych
przykładów. Seed, polityka splitu i wersja transformacji są częścią fingerprintu.

## Expected files

- `services/worker/src/game_predictor_worker/symbols/`
- `services/worker/tests/`
- `services/api/src/game_predictor_api/application/`
- `services/api/tests/`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
python -m pytest services/worker/tests -q
python -m pytest services/api/tests -q
```

## Risks / open questions

- Mała liczba niezależnych zdjęć może uniemożliwić reprezentatywny test mimo
  dużej liczby cropów; raport musi to ujawnić.

## Outcome

Dodano builder `verified-symbol-training-dataset-v1`, który czyta wyłącznie
niezmienny manifest kohorty, sprawdza jego SHA-256, deklarowane liczności,
komplet 15 komórek, aktywny katalog symboli oraz obecność i checksumę każdego
cropu. Brak, drift, nieznany symbol, konflikt etykiet albo niepełna plansza
kończą build stabilnym kodem przed uruchomieniem treningu.

Rodziną splitu jest checksum zdjęcia źródłowego, więc wszystkie jego
pochodne i identyczny materiał zapisany pod innym identyfikatorem pozostają w
jednym z rozłącznych splitów. Stabilny hash 65/15/10/10 zachowuje przypisanie
starych źródeł po rozszerzeniu skumulowanej kohorty. Regression nie trafia do
train. Manifest zawiera konfigurację, próbki, statystyki splitów, źródeł i
symboli, wykluczenia oraz advisory dla klas niedoreprezentowanych.

Artefakty są idempotentne i content-addressed pod
`data/training/<game-code>/<cohort-sha256>/`; PostgreSQL nadal przechowuje
wyłącznie metadane zamrożonej kohorty. Ścieżkę manifestu datasetu przejmie
trwała iteracja treningowa w TASK-0146, bez dodawania BLOB-ów ani tworzenia
przedwcześnie osobnej encji pośredniej.

Weryfikacja: 37 skupionych testów buildera, dotychczasowego eksportu/splitu i
kohorty API przeszło; dodatkowe testy serwisu API, Ruff i skupiony mypy również
przeszły. Pełny zestaw 572 testów workera przekroczył limit 120 sekund;
diagnostyczny przebieg `-x` doszedł do 97% bez odtworzenia porażki i zatrzymał
się na istniejącym, ciężkim teście rzeczywistego korpusu. Nie pozostał
uruchomiony benchmark ani trening.
