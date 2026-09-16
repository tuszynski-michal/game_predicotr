---
title: Board-level large-import geometry guard report
status: done
version: v0.10.160
---

# Cel

Rozszerzyc deterministyczny raport ochronny duzego importu v0.10 o wynik kazdej
planszy, aby bledy `incomplete_lattice` mozna bylo rozliczac przed importem bez
mutowania zakonczonego joba.

# Zakres

- raport `image-geometry-systemic-guard-v2` z board-level diagnostyka,
- zachowanie nazwy zrodla, slotu i wynikajacego numeru sekwencji,
- zachowanie geometrii strony, `analysisQuad`, proponowanego `symbolGridQuad`,
  evidence i wszystkich reason codes,
- deterministyczny builder raportu v2 dla historycznego raportu v1 na podstawie
  przypietych snapshotow joba,
- brak zmian progu 98% i brak mutacji historycznych artefaktow.

# Poza zakresem

- zapis decyzji operatora,
- plansze czesciowe i odrzucone,
- schema browser-import v7,
- UI kolejki wyjatkow i operacyjne wznowienie importu.

# Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

# Definition of Done

- nowy raport zapisuje pozycje 0..N-1 i ich `sequenceNumber`,
- gotowa i odroczona plansza maja jawny status oraz reason codes,
- raport zapisuje nazwe zrodla i dostepna geometrie/evidence,
- ten sam input daje bajtowo identyczny raport,
- istniejacy raport v1 pozostaje odtwarzalny i nie jest nadpisywany,
- skoncentrowane testy workera, lint i typecheck przechodza,
- dokumentacja i `CURRENT_STATE.md` sa zaktualizowane.

# Outcome

- Dodano board-level kontrakt i raport systemowej bramki schema v2.
- Zachowano logiczne nazwy `seq_*`, deterministyczne numery oraz wszystkie
  geometrie, evidence i reason codes produkcyjnego toru.
- Dodano kontrolowaną rekonstrukcję v1→v2 bez mutowania historycznego raportu.
- Weryfikacja: `ruff format`, `ruff check` oraz 9 skoncentrowanych testów
  workera zakończone powodzeniem.
