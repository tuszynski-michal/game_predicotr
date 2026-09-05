---
title: TASK-0318 — finalny cutover wirtualnej geometrii
status: done
version: 0.10.11
last_updated: 2026-08-29
---

# Cel

Zamknąć rollout 0.10 zgodnie z rzeczywistymi dowodami jakości, bez promocji
Structured OpenCV ponad poziom dozwolony przez bramkę board-level oraz bez
usuwania danych potrzebnych do rollbacku.

# Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md` — D-254–D-260
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0317-v0-10-virtual-geometry-rollout-backfill.md`

# Zakres

- jedna czysta, deterministyczna polityka bramki cutoveru;
- minimum 100 źródeł, 500 aktywnych plansz i pięć bucketów jakości/kąta;
- wymaganie niezależnego zbioru oraz kompletu historycznych false-successów i
  failures;
- `>=98%` jako jedyna ścieżka do `structured_default` / `virtual_default`;
- `95–98%` jako `structured_review` / `virtual_shadow`;
- `<95%` jako `legacy` / `legacy_files` i przesłanka do TASK-0319;
- brak raportu lub niepełna proweniencja jako brak zgody na zmianę trybu;
- pełna instrukcja rollbacku i jawny raport odbiorczy;
- aktualizacja wymagań, architektury, kontraktu i stanu projektu.

# Poza zakresem

- uruchamianie benchmarku lub operacyjnego backfillu na danych użytkownika;
- tworzenie brakującego raportu przez domysł albo z danych treningowych;
- automatyczna mutacja `image_geometry_rollout_states`;
- usuwanie starych cropów, source geometry, eventów lub aliasów potrzebnych do
  rollbacku;
- TASK-0319 i model keypoint;
- pominięty w bieżącej historii TASK-0316 dotyczący banku prototypów.

# Invarianty

- decyzja cutoveru wynika z board-level, nie cell-level ani confidence modelu;
- całkowicie odrzucone zdjęcie wnosi wszystkie aktywne plansze do mianownika;
- brak dowodu nigdy nie promuje istniejącego trybu;
- istniejący job zachowuje przypięty snapshot mimo późniejszej zmiany gry;
- rollback nie zmienia canonical owner ani zweryfikowanych etykiet;
- legacy cropy pozostają dostępne i odtwarzalne.

# Kryteria odbioru

- testy kodują wszystkie przedziały 95%/98% i minimalną próbkę;
- nie da się uzyskać rekomendacji default bez gotowej walidacji proweniencji;
- brak kompletnego raportu daje `insufficient_evidence` bez rekomendacji trybu;
- aktualny stan dowodów jest zapisany w raporcie jakości;
- pełny rollback jest opisany krok po kroku;
- pełne testy, lint, typecheck, OpenAPI oraz buildy Admina i Reviewera zostały
  uruchomione, a ograniczenia zapisane w Outcome.

# Outcome

- Dodano czystą domenową politykę `assess_geometry_cutover`, która najpierw
  waliduje komplet próbki i proweniencji, a dopiero potem stosuje dokładne
  progi board-level 95% i 98%. Niepełny dowód nie zwraca trybu docelowego ani
  nie uruchamia warunkowego fallbacku.
- Audyt nie znalazł zaakceptowanego raportu 0.10. Outcome TASK-0317 jawnie
  potwierdza, że operacyjnego backfillu nie uruchamiano. Finalna decyzja to
  `insufficient_evidence`: nie zmieniono stanu żadnej gry, nie promowano
  Structured OpenCV i nie uruchomiono TASK-0319.
- Dodano raport `V0_10_VIRTUAL_GEOMETRY_CUTOVER.md` z wymaganym kontraktem
  próbki, stanem dowodów, zachowaną kompatybilnością i pełnym rollbackiem
  operacyjnym. D-261 utrwala, że sam stan backfillu `ready` nie jest bramką
  jakości.
- Nie usunięto starych cropów, aliasów Reviewera, source geometry, eventów,
  canonical ownership ani snapshotów historycznych jobów. API i OpenAPI nie
  otrzymały nieaudytowalnej mutacji trybu.

## Weryfikacja

- test domenowy cutoveru: `11 passed`;
- regresja API/workera geometrii 0.10: `42 passed`;
- Ruff całego repozytorium: pass;
- celowany mypy nowej domeny z pominięciem importów zależnych: pass;
- TypeScript typecheck wszystkich workspace'ów: pass;
- OpenAPI i wygenerowany klient: pass;
- Admin build: pass;
- Reviewer build: pass;
- pełne testy workspace'ów: Admin `305 passed`, Mobile `84 passed`, klient API
  `47 passed`, manual-selection core `16 passed`, shared-ts `25 passed`;
- Reviewer: `160 passed`, `1 failed` w istniejącym, niezwiązanym teście
  `remote source navigation stays in natural folder order for descending ranges`;
- pełne Python testy uruchomiono, lecz przerwano po limicie 120 s. Nowy test
  przechodził; wcześniej wystąpiły trzy niezwiązane błędy
  `test_board_search_projection_repository.py`, potwierdzone osobnym runem
  `3 failed, 2 passed`;
- pełny mypy przekroczył limit 120 s bez wyniku i został przerwany; celowana
  kontrola nowego modułu przechodzi;
- `format:check` wskazuje pięć istniejących plików poza zakresem TASK-0318,
  m.in. oba `next-env.d.ts` i komponenty Reviewera. Nie formatowano ich w tym
  zadaniu.

TASK-0318 nie tworzy brakującego TASK-0316 ani raportu jakości przez domysł.
Ponowne rozpatrzenie promocji wymaga rzeczywistego, zaakceptowanego raportu.
