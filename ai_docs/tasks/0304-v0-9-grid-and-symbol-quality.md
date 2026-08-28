---
title: TASK-0304 — Walidacja geometrii, jakość symboli i topologia planszy 0.9
status: in_progress
last_updated: 2026-08-28
---

# TASK-0304 — Walidacja geometrii, jakość symboli i topologia planszy 0.9

## Status

`in_progress`

TASK 1 został ukończony jako czysty fundament domenowy. Schemat, backfill,
HTTP, worker oraz UI pozostają celowo bez zmian do kolejnych, osobno
weryfikowanych etapów.

## Goal

Rozdzielić logiczną etykietę symbolu, jakość bieżącego cropa i możliwość użycia
cropa w treningu; przypiąć topologię planszy do wersji reguł oraz dostarczyć
osobne workflowy walidacji geometrii i rozwiązywania nieczytelnych symboli.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- topologia planszy przypinana z wersji reguł przed pierwszym importem,
- niezależne stany geometrii, etykiety, jakości i proweniencji cropa,
- `?` jako wartość domenowa, a nie symbol katalogowy,
- topologicznie poprawna geometria i source-direct cropy,
- osobna walidacja geometrii oraz rozwiązywanie nieczytelnych pól,
- unknown w wyszukiwaniu, datasecie, snapshotach i payoutach,
- bezpieczne kohorty treningowe po recropie,
- usunięcie legacy storage dopiero po pełnym cutoverze.

## Out of scope

- zastępcze zdjęcie jednej planszy — osobny task wersji 0.10,
- automatyczny detektor dla topologii innych niż jawnie wspierane,
- osobna tabela kolejki nieczytelnych plansz,
- zapis JPEG-a z narysowanym overlayem,
- migracje, API i UI w TASK 1.

## Acceptance criteria

- [x] Czysta domena definiuje topologię bez nowej stałej 15.
- [x] Geometria rozróżnia `needs_validation`, `needs_correction` i `approved`.
- [x] Komórka rozróżnia etykietę, jakość i proweniencję cropa.
- [x] Recrop zachowuje zatwierdzoną etykietę, ale wyłącza nowy crop z treningu.
- [x] `grid_issue` wraca jako pending, a `unreadable` można rozwiązać symbolem
  albo logicznym `?` bez kwalifikowania cropa do treningu.
- [x] Agregacja planszy uwzględnia zatwierdzenie geometrii i topologię.
- [ ] Migracje 0073–0075 i backfill są wdrożone i odebrane.
- [ ] Pipeline, API, Admin, Reviewer, dataset, mobile i payout przeszły cutover.

## Progress

### v0.9.1 — model domenowy i blokada topologii

- Dodano `BoardTopology`, przypięcie do wersji reguł oraz walidację niezmiennych
  wymiarów.
- Dodano wyliczany stan review geometrii z pierwszeństwem `grid_issue`.
- Rozszerzono czystą domenę komórek o `quality_issue`, tożsamość zatwierdzonego
  cropa, stan proweniencji i pełny predykat `trainingEligible`.
- Recrop zachowuje bezpieczną decyzję logiczną. Nowe piksele pozostają
  nietreningowe do jawnego zatwierdzenia; pole z błędem siatki wraca do pending.
- Zachowano kompatybilność aktualnych rekordów bez proweniencji. Do czasu
  migracji 0073 nie są one uznawane przez nową bramkę treningową.
- Nie zmieniono SQL, ORM, HTTP, workera ani UI.

## Następny etap

TASK 2: addytywna migracja 0073, modele ORM i bounded, idempotentny backfill.
Przed uruchomieniem na danych wymaga osobnego review SQL, locków i raportu
spójności.
