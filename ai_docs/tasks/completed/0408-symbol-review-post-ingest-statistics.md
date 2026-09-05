---
title: TASK-0408 Symbol review post-ingest statistics
status: done
last_updated: 2026-09-03
---

# TASK-0408 — Symbol review post-ingest statistics

## Problem

Po przygotowaniu projekcji nowej gry `777` PostgreSQL nie wykonał `ANALYZE`
dla tabel zasilających Weryfikację symboli. Dla około 298 710 bieżących komórek
planner estymował jeden rekord gry i wybierał kosztowny nested-loop z wieloma
odczytami I/O. Pierwsza bounded strona 500 metadanych nie kończyła się mimo
kompletnej projekcji i poprawnych cropów.

## Scope

- dodać jawne, PostgreSQL-only odświeżenie statystyk tabel read modelu po
  pomyślnej finalizacji trwałego backfillu/reconciliacji Weryfikacji symboli,
- objąć statystykami komórki, bieżących właścicieli, plansze, obserwacje oraz
  rewizje predykcji używane podczas hydracji strony,
- wykonać maintenance przed opublikowaniem terminalnego sukcesu joba,
- zwrócić stabilny błąd workera, jeśli odświeżenie statystyk nie powiedzie się,
- zachować no-op dla testowych baz innych niż PostgreSQL,
- odświeżyć statystyki bieżącej bazy i potwierdzić poprawny plan dla gry `777`,
- dodać test regresyjny wykonania maintenance wyłącznie po stanie `ready`.

## Out of scope

- brak ponownego importu 19 000 plansz,
- brak usuwania lub modyfikowania cropów, decyzji, eventów i kohort treningowych,
- brak migracji Alembic, zmiany OpenAPI albo UI,
- brak `VACUUM FULL`, benchmarku syntetycznego i przebudowy indeksów.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/quality/SYMBOL_REVIEW_FAST_PAGE_ACCEPTANCE.md`
- `ai_docs/process/CURRENT_STATE.md`

## Definition of Done

- nowy lub uzupełniany duży read model nie przechodzi do terminalnego sukcesu
  bez aktualnych statystyk tabel krytycznej ścieżki,
- statystyki są odświeżane raz po kompletnej finalizacji, nie po każdej partii,
- failure nie publikuje fałszywego terminalnego sukcesu joba,
- operacja nie zmienia żadnych danych domenowych ani treningowych,
- skoncentrowane testy API/workera, Ruff i mypy przechodzą,
- rzeczywisty plan gry `777` nie estymuje już jednego rekordu zamiast setek
  tysięcy komórek.

## Outcome

Dodano zamkniętą listę pięciu tabel krytycznej ścieżki Weryfikacji symboli i
PostgreSQL-only maintenance `ANALYZE`. Worker wykonuje ją dokładnie raz, w tej
samej transakcji co pomyślna finalizacja backfillu/reconciliacji i przed
terminalnym checkpointem. Błąd maintenance wycofuje finalizację i zwraca
`SYMBOL_CELL_REVIEW_STATISTICS_REFRESH_FAILED`; bazy testowe innych dialektów
pozostają no-op.

Na rzeczywistej bazie przed naprawą `last_analyze` i `last_autoanalyze` były
puste dla głównych tabel, a planner estymował jeden rekord gry mimo 298 710
bieżących komórek. Jednorazowy `ANALYZE` wyzerował `n_mod_since_analyze`, po
czym planner estymował 310 232 rekordy. Pierwsza bounded strona gry `777`
zwróciła 500 elementów w 1,475 s. Nie zmieniono ani nie usunięto cropów,
decyzji, eventów, modeli i kohort treningowych.

Weryfikacja objęła 34 skoncentrowane testy API i workera, Ruff oraz mypy dwóch
zmienionych modułów. Pełny `python:typecheck` doszedł do końca i zgłosił 29
wcześniejszych błędów wyłącznie w pięciu niezwiązanych plikach OCR/schema;
żaden zmieniony moduł nie wystąpił w raporcie.
