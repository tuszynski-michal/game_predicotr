---
title: TASK-0590 — V7 domain, API and activation gate
status: done
last_updated: 2026-09-21
---

# TASK-0590 — Domena, API i bramka aktywacji V7

## Goal

Przygotować addytywny kontrakt V7 w istniejącym półautomacie: wersję runu,
konfigurację pełnej strony, odpowiedź capabilities i migrację metadanych. Nowy
start V7 ma być twardo odrzucony przez backend do odbioru T12; historyczne
runy `selection` i `filename_verification` pozostają niezmienione.

## Dependencies / entry conditions

- TASK-0584–0589 są ukończone; T05 nie odblokował kalibracji ani aktywacji.
- Obowiązują D-403–D-407 oraz zaakceptowany plan V7.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`

## Scope

- Dodać wariant workflowu V7 i checksummowaną konfigurację: tryb, kierunek,
  pełne granice, styl obramowania, konfigurację lokalizatora oraz fingerprint
  kalibracji. Nie wolno pobierać tych danych z klienta jako niezweryfikowanych
  fingerprintów.
- Dodać wersjonowany, addytywny zapis metadanych V7 w runie oraz status
  aktywacji domyślnie `blocked` w migracji Alembic.
- Rozszerzyć backendowe capabilities, request/response i OpenAPI o jawną
  informację `v7` oraz odrzucić POST tworzący V7 przed T12 niezależnie od UI.
- Utrzymać zgodność serializacji i identity historycznych runów; nie zmieniać
  ich fingerprintów, writerów, output-acknowledgements ani workflowu viewera.

## Out of scope

- OCR, skan, checkpointy, output, recovery, ręczne podmiany, UI, aktywacja,
  migracja danych historycznych, trening i nowe usługi.

## Design

1. `v7_selection` jest nowym, jawnym workflowem, a nie zmianą znaczenia
   istniejącego `selection`.
2. Domain tworzy konfigurację V7 wyłącznie z istniejących typów parsera T01;
   serializuje ją kanonicznie do payloadu joba i identity. Brak konfiguracji
   dla wariantu V7 jest błędem.
3. API ma osobny `v7` blok capabilities z `activationStatus=blocked` oraz
   przyczyną. `POST` odrzuca V7 przed wyborem źródła/stagingu, więc nie tworzy
   joba ani nie konsumuje tokenu.
4. Alembic dodaje nullable `v7_configuration` i `v7_calibration_fingerprint`
   do runu oraz pojedynczy rekord polityki aktywacji. Nie zmienia istniejących
   rekordów i nie stosuje migracji na lokalnej bazie użytkownika.

## Acceptance criteria

- [ ] Historyczne runy mają identyczne odpowiedzi, identity i ścieżki startu.
- [ ] V7 configuration jest pełną stroną 3×3, ma domyślne `semi_automatic`,
  `ascending` i `top_and_sides`, jest kanoniczna oraz checksumowana.
- [ ] Backend pokazuje blokadę V7 i odrzuca próbę startu przed utworzeniem
  jakiegokolwiek joba, niezależnie od wartości przycisku w UI.
- [ ] Migracja jest addytywna, ma upgrade/downgrade i test kontraktu.
- [ ] OpenAPI i wygenerowany klient są zgodne z backendem.

## Expected files

- `services/api/alembic/versions/0114_v7_semi_automatic_activation_gate.py`
- `services/api/src/game_predictor_api/domain/semi_automatic_image_selections.py`
- `services/api/src/game_predictor_api/application/semi_automatic_image_selections.py`
- `services/api/src/game_predictor_api/schemas/semi_automatic_image_selections.py`
- `services/api/src/game_predictor_api/storage/models.py`
- testy API/domeny/migracji oraz wygenerowany klient/OpenAPI.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_semi_automatic_image_selections.py services/api/tests/test_semi_automatic_selection_migration.py -q
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/domain/semi_automatic_image_selections.py services/api/src/game_predictor_api/application/semi_automatic_image_selections.py services/api/src/game_predictor_api/schemas/semi_automatic_image_selections.py
npm run openapi:check
```

## Outcome

- Dodano `v7_selection`, server-owned konfigurację pełnej strony oraz payload
  joba schema v4; legacy identity/payloady pozostają bez zmian.
- Migracja 0114 dodaje nullable metadane V7 i singleton aktywacji `blocked`;
  downgrade blokuje się przy istniejącym V7, nie usuwa danych.
- Capabilities/OpenAPI pokazują blokadę; create odrzuca V7 przed source/token.
- Weryfikacja: 33 testy półautomatu/repozytorium/migracji, ruff, ograniczony
  mypy oraz `npm run openapi:check` przeszły. Pierwsza próba pełnych testów w
  sandboxie nie miała dostępu do katalogu tymczasowego pytesta; ten sam zestaw
  przeszedł poza sandboxem. Astra Medium odnalazła i po poprawce zatwierdziła
  SQL `NULL` dla legacy metadata oraz walidację wersji/fingerprintu V7.
- Ograniczenie: V7 jest świadomie nieaktywne. T07–T12 dostarczą scan, zapis, UI
  i odbiór; żaden nowy katalog ani JPEG użytkownika nie został zmieniony.
