---
title: TASK-0564 — Typowane liczniki ręcznej weryfikacji nazw
status: done
last_updated: 2026-09-16
---

# TASK-0564 — Typowane liczniki ręcznej weryfikacji nazw

## Goal

Kontrola typów całego kodu API i workera przechodzi bez zmiany liczników końcowych selekcji zdjęć.

## Context

`complete_filename_verification_cleanup` buduje `dict(Result)` z zapytania SQLAlchemy. Mypy zgłasza dwa błędy; wartości `filenameManualKept` i `filenameManualRejected` muszą pozostać takie same.

## Recommended execution

`gpt-5.6-sol medium`; w razie rozbieżności runtime i typów wymagana ponowna analiza zapytania.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`

## Scope

- Jawna konwersja wierszy SQLAlchemy na `dict[str, int]`.
- Skoncentrowane testy i mypy źródeł API oraz workera.

## Out of scope

- Zmiany decyzji selekcji, danych, schematu bazy i kolejności jobów.

## Acceptance criteria

- [x] `filenameManualKept` i `filenameManualRejected` zachowują semantykę.
- [x] Mypy źródeł API/workera oraz testy odpowiedniego modułu przechodzą.

## Outcome

Jawnie przekształcono wiersze z `Result.tuples()` na `dict[str, int]`; zapytanie,
grupowanie i brakujące wartości domyślne pozostały bez zmian. Mypy API/workera:
429 plików bez błędów. Testy modułu selekcji: 16 zaliczonych. Próba mypy
obejmująca także cały katalog `scripts/` zgłasza 31 wcześniejszych błędów w
pięciu niezwiązanych skryptach; ich nie zmieniano. Nie zmieniono danych ani jobów.
