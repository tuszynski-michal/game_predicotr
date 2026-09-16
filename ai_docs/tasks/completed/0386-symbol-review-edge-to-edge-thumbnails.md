---
title: TASK-0386 Symbol review edge-to-edge thumbnails
status: done
last_updated: 2026-09-02
---

# TASK-0386 — Miniatury symboli bez czarnej ramki

## Goal

Usunąć wizualny odstęp i czarne pasy wokół cropa w `Weryfikacji symboli`, bez
zmiany rozmiaru strony, wirtualizacji ani liczby requestów atlasów.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- renderer bieżących cropów legacy skaluje pełny crop do tile'a 100 × 100 bez
  dopisywania czarnego płótna;
- wersja renderera i klucz cache zmieniają się, aby nie serwować starych atlasów;
- karta nie rezerwuje przestrzeni na border, a obramowanie jest nakładką na
  krawędzi grafiki;
- placeholder i atlas nie dodają czarnego tła.

## Out of scope

- rozmiar strony 500 elementów;
- wirtualizacja, batching i cache atlasów;
- źródłowe cropy oraz decyzje review.

## Definition of Done

- crop wypełnia tile 100 × 100;
- narożniki legacy tile'a nie zawierają dopisanych czarnych pasów;
- border przylega do grafiki i nie zmniejsza jej powierzchni;
- zmiana nie zwiększa liczby atlasów ani requestów;
- skoncentrowane testy API i Admina przechodzą.

## Outcome

- Renderer `symbol-review-current-crop-renderer-v2-edge-to-edge` skaluje pełny
  crop legacy bez czarnego letterboxa; zmieniona wersja unieważnia stare atlasy.
- Karta 100 × 100 px ma transparentne tło, a border jest pseudo-elementem
  nakładanym na krawędź obrazu bez zajmowania jego powierzchni.
- Zachowano batching do 100 tile'i, maksymalnie pięć atlasów na stronę i
  istniejącą wirtualizację.
- Testy API: 30 passed; testy kontraktowe Admina: 12 passed; Ruff, ESLint,
  TypeScript i produkcyjny build Admina przeszły. Samodzielne `mypy` pozostaje
  zablokowane przez istniejący brak `py.typed` pakietu workera i wcześniejsze
  błędy poza zakresem zadania.
