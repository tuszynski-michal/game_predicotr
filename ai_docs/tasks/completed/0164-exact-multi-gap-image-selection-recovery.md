---
title: TASK-0164 exact multi-gap image-selection recovery
status: done
release: "0.4"
last_updated: 2026-08-04
---

# TASK-0164 — Jednoznaczne odzyskiwanie wielu kolejnych zakresów

## Status

`done`

## Goal

Zmniejszyć końcową i widoczną podczas skanowania liczbę grup bez numerów przez
odzyskanie dowolnego ciągu pełnych stron pomiędzy dwiema pewnymi kotwicami.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0160-fast-image-selector-v5-real-corpus-correction.md`

## Evidence and assumptions

- przy `6912/32079` run v5 miał 496 grup: 444 automatyczne, 2 duplikaty i 50
  grup bez zakresu,
- późniejszy snapshot 519 grup miał 54 grupy bez zakresu; 50 z nich można było
  jednoznacznie podzielić na pełne zakresy po 9 layoutów pomiędzy dwiema
  kotwicami,
- kolejność wejścia jest deterministyczna, ale skok numeracji pozostaje
  dozwolony; odzyskanie jest zatem dozwolone tylko przy dokładnej zgodności
  całej luki,
- bieżący run v5 nie jest przerywany przez implementację v6.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/manifest.py`
- `services/worker/src/game_predictor_worker/images/selection/engine.py`
- adapter factory i testy selektora,
- UI licznika Selekcji zdjęć,
- dokumentacja wymagań, architektury i bieżącego stanu.

## Acceptance criteria

- [x] v4 i v5 zachowują niezmienne fingerprinty oraz dotychczasowe zachowanie,
- [x] v6 odzyskuje jedną grupę o rozmiarze 1–9 jak wcześniej,
- [x] v6 odzyskuje dwie lub więcej kolejnych grup tylko wtedy, gdy luka ma
      dokładnie `liczba grup × 9` layoutów,
- [x] skok albo niejednoznaczna luka pozostaje bez przypisanego zakresu,
- [x] odzyskane grupy dostają najlepsze bezpieczne zdjęcie i są utrwalane po
      pojawieniu się prawej kotwicy,
- [x] UI wyjaśnia, że aktywny licznik dotyczy grup oczekujących na dalszą
      kotwicę,
- [x] testy i kontrole jakości zmienionych części przechodzą.

## Outcome

Dodano `fast-image-selector-v6` o fingerprintcie
`22b0d13545c087b53e197dd20edaf214fbebd99b51036cd84dc624c76577bf1e`.
Historyczny v5 zachowuje fingerprint
`ff75216bcd71f7f2484fef2c2868eda639152ba7efd98e00f23e08a89585e3fb`
i może być bezpiecznie wznowiony.

V6 odzyskuje all-or-nothing dowolny blok pełnych stron po 9, wybiera dla każdej
grupy najlepszy bezpieczny kandydat i emituje zmienione projekcje natychmiast po
prawej kotwicy. Skok `19–27 → 400–408` pozostaje manualny. Admin nazywa aktywny
licznik `Roboczo bez numerów` i wyjaśnia jego tymczasowy charakter.

Weryfikacja: 52 testy selektora/adapterów, 11 testów trwałego joba i publikacji
oraz 165 testów Admina przeszło. Ruff, Mypy dla zmienionej domeny selektora,
TypeScript i ESLint przeszły. Izolowany Mypy pliku `job.py` nadal widzi
istniejący problem konfiguracji ścieżki importów pakietu API; nie jest skutkiem
tej zmiany. Aktywny run v5 nie został przerwany ani przełączony podczas pracy.
