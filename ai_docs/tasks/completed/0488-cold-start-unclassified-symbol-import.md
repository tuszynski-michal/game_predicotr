---
title: TASK-0488 — Cold-start import bez modelu symboli
status: done
owner: Codex
created: 2026-09-06
---

# TASK-0488 — Cold-start import bez modelu symboli

## Cel

Odblokować pierwszy import nowej gry z niezgodnym katalogiem klas bez używania
globalnego modelu bootstrapowego. Plansze oraz cropy mają powstać z przypiętej
geometrii, a każda komórka ma trafić do weryfikacji jako `?` z confidence `0`.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Zakres

- Utrwalić wersjonowany tryb `cold_start_unclassified` bez artefaktu ONNX.
- Zezwolić na niego wyłącznie przy braku zatwierdzonych komórek, kohort,
  iteracji i aktywacji modelu gry.
- Nie zezwalać na fallback, gdy istnieje kandydat wymagający aktywacji.
- Utworzyć zwykłe plansze i cropy, ale zapisać `?`/`0` bez rewizji predykcji ML.
- Pokazać jawny stan i przycisk pierwszego importu w Adminie.
- Zachować późniejszą pending-only reinferencję na tych samych cropach.

## Testy

- Preflight nowej gry jawnie zwraca możliwość cold-startu.
- Start tworzy job tylko dla pustej historii uczenia i weryfikacji.
- Zatwierdzona komórka, kohorta, iteracja albo aktywacja blokują cold-start.
- Worker nie otwiera ONNX i tworzy piętnaście `?` na każdą kompletną planszę.
- Tryb cold-start nie tworzy rewizji predykcji modelu.
- Historyczne oraz aktywne modele zachowują dotychczasowe zachowanie.

## Definition of Done

- Staging nowej gry można uruchomić po zakończonym preflighcie geometrii.
- Cropy są widoczne w Weryfikacji symboli jako oczekujące `?`.
- Nie następuje inferencja niezgodnym bootstrapem ani dublowanie cropów.
- API, OpenAPI, klient, Admin, worker, testy i dokumentacja są spójne.

## Outcome

- Dodano deterministyczny snapshot `cold-start-unclassified-v1` oraz jawne pole
  `inferenceMode`. Bramka dopuszcza go tylko bez zatwierdzonych komórek, kohort,
  iteracji i aktywacji modelu.
- Preflight, start API, OpenAPI, wygenerowany klient i Admin pokazują osobną
  ścieżkę pierwszego importu. Stan jest sprawdzany ponownie przy starcie.
- Worker materializuje wszystkie dostępne komórki jako pending `?` z
  confidence `0`, nie otwiera ONNX i nie zapisuje ich jako rewizji predykcji.
- Po treningu istniejąca reinferencja pending działa na tej samej projekcji
  cropów; nie powstają duplikaty assetów.
- Skoncentrowany odbiór: 92 testy Python i 12 testów kontraktu Admina przeszły;
  Ruff, mypy, ESLint, TypeScript, OpenAPI i build Admina przeszły. Globalny
  `format:check` pozostaje czerwony na 50 wcześniejszych, niezwiązanych plikach;
  zmieniony plik Admina sformatowano osobno.
