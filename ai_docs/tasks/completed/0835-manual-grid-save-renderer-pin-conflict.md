---
title: Konflikt rewizji przy zapisie korekty siatki dla starszego renderera
status: done
last_updated: 2026-10-04
---

# TASK-0835 — Konflikt rewizji przy zapisie korekty siatki dla starszego renderera

## Status

`done`

## Goal

Zapis „Zapisz geometrię i dalej” działa dla plansz, których komórki przypięły
starszą wersję renderera, zamiast kończyć się
`IMAGE_GRID_REVIEW_REVISION_CONFLICT`.

## Context

Zgłoszenie operatora z 2026-10-04: zapis korekty w imporcie `e5cf4465-…` (gra
`bfc4f949-…`) zwraca „The virtual grid review changed while its correction was
rendered”. Wszystkie 240 030 komórek tego importu mają
`virtual-cell-renderer-source-direct-v1`, a bieżący renderer to `v4`.

TASK-0815 (v1.7.158) związał kontekst przygotowywany przez
`VirtualGridGeometryService._prepare` z bieżącym rendererem
(`_bind_current_renderer`), ale repozytorium nadal porównywało go pod blokadą
(`_require_same_context`) z kontekstem odczytanym z bazy, czyli z wersją
przypiętą w komórkach. Test TASK-0815 używał repozytorium w pamięci, które nie
porównuje kontekstów, więc luka nie wyszła.

## Scope

- `_require_same_context` pomija wersję extractora (jedyne pole, które zapis
  celowo zmienia); rewizje, źródło, geometria i reszta konfiguracji renderu
  nadal muszą się zgadzać.
- Test regresji: kontekst z `v1` zgadza się z kontekstem związanym z `v4`, a
  zmiana `resolution_revision` nadal daje `IMAGE_GRID_REVIEW_REVISION_CONFLICT`.

## Out of scope

- Zmiana ścieżki odczytu kontekstu i samego renderu; migracje.

## Acceptance criteria

- [x] Porównanie kontekstów nie zależy od wersji renderera przypiętej w komórkach.
- [x] Prawdziwy konflikt rewizji nadal jest zgłaszany.
- [x] Na żywych danych importu: kontekst z bazy (`v1`) vs związany (`v4`) przechodzi
  poprawioną kontrolę (odczyt, bez zapisu).

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_virtual_grid_geometry.py -q   # 27 passed
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py services/api/tests/test_virtual_grid_geometry.py
```

## Outcome

### Changed

- `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py`
  (`_require_same_context`), `services/api/tests/test_virtual_grid_geometry.py`
  (nowy test).

### Verification results

- `test_virtual_grid_geometry.py` 27/27, ruff i format czyste.
- Odczyt na żywych danych potwierdził przyczynę (`v1` vs `v4`) i poprawkę.
- API (`--reload`) przeładowało kod; `/api/v1/health` zwraca `ok`.

### Not completed

- Brak ponownego zapisu geometrii w żywej bazie (operator zapisuje ręcznie).
- PostgreSQL integration tests nie były uruchamiane.
