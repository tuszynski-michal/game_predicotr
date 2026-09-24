---
title: TASK-0647 — Gra 777: przebieg reweryfikacji siatek na żywych danych
status: todo
---

# TASK-0647 — Przebieg na żywych danych i odbiór

## Status

`todo`

## Goal

Za osobną, jawną zgodą użytkownika wykonać `execute` dla gry 777 i potwierdzić wynik licznikami Reviewera oraz próbką wizualną.

## Dependencies / entry conditions

- TASK-0646 `done` z review; świeży dry-run; **jawna zgoda użytkownika w czacie na zapis**.
- Zalecana kopia bazy (`pg_dump` schematu `game_data_v2`) przed startem — decyzja użytkownika.

## Recommended execution

`claude-sonnet-5`, reasoning `medium` — zgodnie z tabelą planu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`

## Scope

- Uruchomienie `execute` jako kontrolowany proces w tle, monitoring checkpointu, wznowienie po przerwaniu.
- Porównanie liczników Reviewera przed/po z raportem.
- Próbka 30 zatwierdzonych plansz + 30 rozwiązanych slotów do obejrzenia przez użytkownika.
- `CURRENT_STATE.md`, Outcome, przeniesienie tasków planu do `completed/`.

## Acceptance criteria

- [ ] Liczniki „Do walidacji”/„Do poprawy” spadły zgodnie z raportem (± `skipped_conflict`).
- [ ] Użytkownik zaakceptował próbkę.
- [ ] Dokumentacja zaktualizowana.

## Outcome

Wypełnia agent po pracy.
