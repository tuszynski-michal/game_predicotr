---
title: TASK-1192 — Naprawa dwóch pozostałych padających testów API
status: done
last_updated: 2026-11-12
---

# TASK-1192 — Naprawa dwóch pozostałych padających testów API

## Status

`done`

## Goal

Dwa testy wykryte jako zastane FAIL przy TASK-1191 przechodzą; przyczyną są
nieaktualne testy, a kod produkcyjny zostaje bez zmian.

## Context

Przy weryfikacji TASK-1191 dwa testy padały identycznie na `main` `20635d36`
(zapis w `Outcome` TASK-1191). Operator zlecił ich naprawę (2026-11-12). Test
migracji należy do grupy historycznych testów odłożonych w TASK-0940; polecenie
operatora jest decyzją o jego naprawie.

## Dependencies / entry conditions

TASK-1191 scalony (`main` `3c1d83db`). Bez migracji.

## Recommended execution

Claude Opus 5.5, reasoning standard — dwie małe poprawki testów; operator
zlecił je bezpośrednio. Bez audytu krzyżowego (brak planu z kolumną
`Dodatkowy review`).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

1. `test_geometry_qualification.py::test_override_repository_roundtrip_after_new_repository_instance`
   — `Mock` sesji zwracał z `scalar()` obiekt `Mock`, więc idempotentne
   sprawdzenie paragonu w `SqlAlchemyPageGeometryOverrideRepository.append`
   (od `a41f8d8d`) próbowało zamienić go na domenę (`TypeError`). Atrapa
   modeluje teraz „brak wcześniejszego wiersza”, a asercja sprawdza dokładną
   sekwencję intencji routera (`WRITE`, `READ`, `READ`) zamiast samej liczby.
2. `integration/test_neural_page_geometry_postgres.py::test_0145_preserves_old_partitions_validates_binding_and_recovers_in_new_process`
   — zasiew na schemacie `0144` wstawiał `source_images` bieżącym modelem ORM,
   który ma kolumnę `purged_at` z `0177`. Wiersz źródła jest teraz wstawiany
   wyłącznie kolumnami fizycznie obecnymi w bazie (`information_schema`), więc
   kolejne nowe kolumny nie zepsują testu historycznego.

## Out of scope

- Kod produkcyjny i migracje.
- Pozostałe historyczne testy z TASK-0940.

## Acceptance criteria

- [x] Oba testy przechodzą bez osłabiania asercji migracji i roundtripu.
- [x] Zasiew historyczny nie zależy od kolumn dodanych po przypiętej rewizji.

## Technical notes

Ponowny `bind` z `READ` po `WRITE` w tej samej sesji zwraca istniejące
powiązanie i nie zdejmuje blokady zapisu (`GameStorageRouter.bind`), więc
dodatkowy odczyt w `append` jest zamierzony. Obiekt `SourceImageModel` w
zasiewie jest przejściowy (nie trafia do sesji); `ensure_source_geometry` tylko
go czyta, a metadane normalizacji są wpisane jawnie z tymi samymi wartościami,
które ustawiłby fixture.

## Expected files

- `services/api/tests/test_geometry_qualification.py`
- `services/api/tests/integration/test_neural_page_geometry_postgres.py`

## Test cases

- Roundtrip repozytorium przez serializację JSON → równy obiekt domenowy.
- Migracja 0144 → 0145 zachowuje stare partycje, waliduje wiązanie, blokuje
  downgrade z historią i działa w nowym procesie.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_geometry_qualification.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_neural_page_geometry_postgres.py -q
```

## Outcome

Commit: v1.7.621 (hash dopisuje kolejny commit).

- Roundtrip repozytorium: atrapa sesji zwraca `None` z `scalar()` przy zapisie
  (brak wcześniejszego paragonu); asercja sprawdza sekwencję intencji
  `WRITE`, `READ`, `READ`. Kod produkcyjny bez zmian.
- Test migracji 0145: wiersz `source_images` zasiewany tylko kolumnami
  obecnymi w schemacie `0144` (`information_schema`), z jawnymi metadanymi
  normalizacji; reszta zasiewu bez zmian.
- Weryfikacja: oba testy padały na `main` `3c1d83db` (zapis TASK-1191) i
  przechodzą po poprawce; `test_neural_page_geometry_postgres.py`,
  `test_source_replacement_geometry_guards_postgres.py` (jednorazowe bazy),
  `test_geometry_qualification.py`, `test_page_geometry_overrides.py`,
  `test_neural_page_geometry_api.py`: 78 passed; ruff check/format PASS.
- Nie wykonano: audytu krzyżowego (niewymagany), scalenia do `main`.
