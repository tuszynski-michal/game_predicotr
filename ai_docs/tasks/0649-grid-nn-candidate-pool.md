---
title: TASK-0649 — Sieć siatek v3: pula kandydatów i kontrakt datasetu
status: blocked
---

# TASK-0649 — Pula kandydatów i kontrakt datasetu (tylko odczyt)

## Status

`blocked` — plan zastąpiony przez `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (D-447); odpowiednik zakresu danych to TASK-0666/TASK-0668. Numer TASK-0649 koliduje z ukończonym zadaniem „Przybliżona wygrana”; identyfikuj ten plik pełną ścieżką.

## Goal

Wersjonowany manifest kandydatów do kuracji (plansze 777 z quadem, źródłem i metrykami trudności) z warstwowym losowaniem i splitem według rodziny źródła, bez zapisu do bazy.

## Dependencies / entry conditions

- Zakończony dry-run i przegląd 777 (plan `GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`), aby decyzje użytkownika były dostępne.

## Recommended execution

`claude-sonnet-5`, reasoning `high` — zgodnie z tabelą planu `GRID_ENGINE_V3_NEURAL_EXECUTION_PLAN.md`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_ENGINE_V3_NEURAL_EXECUTION_PLAN.md`
- `ai_docs/architecture/GRID_ENGINE_V3_PROPOSAL.md`

## Scope

- Moduł (proponowany) `services/worker/src/game_predictor_worker/images/grid_nn/candidates.py` + podkomenda skryptu `scripts/grid_nn_dataset.py candidates`.
- Źródła kandydatów: `hybrid_confirmed` (plansza „pewna” w hybrydzie przy ≥ 8 potwierdzonych rodzeństwach), `dry_run_accepted` (decyzje użytkownika z `artifacts/grid-reverify-777/dry-run-*/decisions.json`), `accepted-by-user-2026-09-24.json`.
- Metryki trudności: strzałka (pl. 4/6), skrajna kolumna, ekstrapolacja, ECC dociągania, obecność ręki/odblasku (proxy: niski kontrast lokalny), odchylenie.
- Warstwy i kwoty losowania; split `source_family_id = import_job_id` (deterministyczny seed); zbiór złoty wyznaczony pierwszy i wyłączony z treningu.
- Etykieta: quad → 24 punkty (interpolacja biliniowa) + maska widocznych komórek.

## Out of scope

- Kopiowanie obrazów, zapis do bazy, trening.

## Acceptance criteria

- [ ] Manifest z checksumą, wersją, seedem, liczebnościami per warstwa i split.
- [ ] Żadna rodzina źródła nie występuje w dwóch splitach (test).
- [ ] Zbiór złoty: ≥ 150 zdjęć, ≥ 1 000 plansz, ≥ 5 kategorii trudności.

## Outcome

Wypełnia agent po pracy.
