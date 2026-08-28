---
title: TASK-0304 — Walidacja geometrii, jakość symboli i topologia planszy 0.9
status: in_progress
last_updated: 2026-08-28
---

# TASK-0304 — Walidacja geometrii, jakość symboli i topologia planszy 0.9

## Status

`in_progress`

TASK 1–3 zostały ukończone w kodzie. TASK 2 dodaje addytywny schemat 0073 i
kontrolowany backfill metadanych, a TASK 3 przenosi przypiętą topologię przez
snapshot, fingerprint, geometrię, cropper i ręczny preview. Migracja nie została
jeszcze zastosowana na roboczej bazie: wymaga osobnego checkpointu SQL i okna
operacyjnego. HTTP, worker oraz UI pozostają celowo bez zmian.

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

### v0.9.2 — addytywny schemat i backfill 0073

- Migracja `0073_topology_geometry_crop_provenance` dodaje przypięcie topologii
  gry, snapshot wymiarów i zatwierdzenie geometrii planszy, jakość cropa oraz
  dokładną tożsamość cropa zatwierdzonego z etykietą.
- `has_grid_issue` pozostaje tymczasowo dostępne. Odczyt preferuje
  `quality_issue`, ale rozumie legacy bool; bieżące mutacje zapisują oba pola.
- Dodano append-only `image_board_geometry_review_events` oraz rozszerzono
  istniejący audyt komórek o jakość i proweniencję zatwierdzonego cropa.
- Bounded backfill blokuje grę podczas przypinania najnowszej zgodnej wersji
  reguł, przetwarza maksymalnie 200 plansz w transakcji i nie zgaduje topologii
  przy niespójnych danych.
- Plansze `accepted/corrected` otrzymują zatwierdzenie bieżącej geometrii,
  jednoznacznie ręczne rewizje również mogą zostać uznane za zatwierdzone, a
  pipeline'owe pending pozostają `needs_validation`.
- Zatwierdzone komórki otrzymują bieżącą tożsamość zatwierdzonego cropa.
  Backfill nie kopiuje obrazów i nie tworzy sztucznych eventów.
- `scripts/backfill_v09_schema.py` zapisuje atomowy checkpoint po każdej
  zatwierdzonej partii. Powtórzenie jest idempotentne; raport końcowy wymienia
  braki topologii, geometrii, jakości i proweniencji.
- Cykl migracji 0072 → 0073 → 0072 → 0073 przeszedł na izolowanej bazie
  testowej. Migracja i backfill nie zostały uruchomione na danych użytkownika.

### v0.9.3 — topologiczna geometria i source-direct cropper

- Nowy snapshot importu przypina `gridRows`, `gridColumns`,
  `topologyRulesVersionId` i fingerprint topologii; wersja reguł zostaje
  atomowo przypięta pod blokadą rekordu gry.
- Generyczne wyprowadzenie quadów, source-direct cropper i ręczny preview
  obsługują dowolne poprawne `rows × columns`, zachowując row-major i dokładnie
  jeden finalny `warpPerspective` na komórkę.
- Automatyczny adapter `board-cell-processing-v20-verified-v19-v1` pozostaje
  jawnie 3 × 5. Inna topologia jest blokowana kodem
  `IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED`, bez uruchomienia częściowego pipeline'u.
- `recognized_boards` otrzymuje snapshot wymiarów użytych przez nowy pipeline,
  a manifest odroczenia wiąże wymiary i wersję reguł z checksumą.
- Historyczne snapshoty, manifesty i fingerprint croppera bez topologii nie
  zmieniły bajtów ani interpretacji 3 × 5.
- Celowane testy worker/API, Ruff, ograniczony mypy oraz OpenAPI z generowanym
  klientem przechodzą. Baza użytkownika nadal pozostaje na 0072.

## Następny etap

Checkpoint operacyjny TASK 2 pozostaje: migracja 0073 i bounded backfill na
danych użytkownika dopiero po zakończeniu aktywnych pipeline'ów. Następny etap
implementacyjny to TASK 4 — atomowa synchronizacja geometrii, komórek i planszy.
