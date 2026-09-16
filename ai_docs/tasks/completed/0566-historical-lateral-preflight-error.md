---
title: TASK-0566 — Poprawny błąd dla historycznego preflightu
status: done
last_updated: 2026-09-16
---

# TASK-0566 — Poprawny błąd dla historycznego preflightu

## Goal

Ponowne przetwarzanie z v1.0/v1.1 i historycznym preflightem bez przypiętej
polityki bocznych plansz zwraca `IMAGE_LATERAL_PARTIAL_PREFLIGHT_REQUIRED`.

## Context

`JobService._require_lateral_preflight` przekazuje brakujące pole
`lateral_partial_geometry` do parsera snapshotu. Parser słusznie odrzuca je
jako `IMAGE_LATERAL_PARTIAL_SNAPSHOT_INVALID`, lecz operator otrzymuje błędną
wskazówkę zamiast informacji o potrzebie nowego preflightu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Rozróżnić brak przypiętej polityki od niepoprawnej zapisanej polityki przed
  wywołaniem parsera snapshotu.
- Utrzymać walidację manifestu, checksummy, gry i selekcji oraz idempotencję.
- Dodać regresję dla domyślnego i jawnie wskazanego historycznego manifestu
  oraz odpowiedzi HTTP.

## Out of scope

- Zmiana manifestów, jobów i danych użytkownika.
- Automatyczne uruchomienie nowego preflightu albo zmiana wyboru silnika.

## Acceptance criteria

- [x] Brak polityki daje kod `IMAGE_LATERAL_PARTIAL_PREFLIGHT_REQUIRED`.
- [x] Niepoprawna istniejąca polityka nadal daje `IMAGE_LATERAL_PARTIAL_SNAPSHOT_INVALID`.
- [x] Ważny przypięty preflight nadal tworzy idempotentny job.
- [x] Testy API, lint, format i typy zmienionego pionu przechodzą.

## Outcome

`JobService._require_lateral_preflight` rozpoznaje brak przypiętej polityki
przed jej parsowaniem. Test obejmuje automatycznie odziedziczony i jawnie
wskazany stary manifest, niepoprawny snapshot, odpowiedź HTTP 409 oraz ochronę
przed utworzeniem joba po błędzie. Istniejący test ważnego manifestu nadal
potwierdza idempotencję.

Weryfikacja: 17/17 skoncentrowanych testów i 87/87 powtórzonych testów API,
Ruff check/format oraz mypy dla 429 plików źródłowych API/workera przeszły.
Pierwszy szeroki przebieg miał przejściowy błąd niezwiązanego testu migracji
starego uploadu; test przeszedł osobno i w powtórzonym pełnym zestawie.

Nie uruchamiano jobów ani nie zmieniano danych. Istniejący proces API wymaga
normalnego restartu, aby użyć nowego kodu.
