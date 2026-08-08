---
title: TASK-0197 v10.1 first 5000 real-image owner gate
status: in_progress
release: "0.4"
last_updated: 2026-08-08
---

# TASK-0197 — V10.1 first-5000 real-image owner gate

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/tasks/completed/0196-image-selection-v101-bounded-full-geometry.md`

## Goal

Wykonać kontrolowany profil pierwszych 5000 rzeczywistych zdjęć po korektach
v10.1, zmierzyć czas i stabilność oraz przygotować wynik do ręcznej oceny
jakości przez właściciela przed decyzją o runie 32 000.

## Scope

- ten sam niezmienny staging 32 079 zdjęć,
- naturalne indeksy 0–4999,
- cold analysis bez cache lekkiego skanu,
- brak publikacji, zapisu domenowego i przekazania do Importu layoutów,
- trzy scan workers i jeden verifier,
- kontrolowany proces z PID-em, osobnymi logami i limitem 90 minut.

## Likely files

- `scripts/profile_image_selection_slice.py`
- `scripts/start_image_selection_profile.ps1`
- `artifacts/image-selection-v101-exact-geometry-first-5000-task0197.json`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

- proces kończy się w limicie i nie pozostawia osieroconego procesu,
- raport zawiera dokładnie 5000 źródeł, grupy, zakresy, statusy, checksumy
  reprezentantów, błędy skanu, telemetry, czas i peak RSS,
- znany prefiks 0–199 pozostaje zgodny z TASK-0196,
- anomalie zakresów, konflikty oraz `manual_required` są zestawione do oględzin,
- właściciel otrzymuje ścieżki wybranych JPEG-ów do ręcznej oceny,
- wynik nie uruchamia automatycznie profilu 32 000.

## Dependencies

- TASK-0194–0196 ukończone.

## Open questions

Końcowa decyzja `accepted | optimize | rejected` należy do właściciela po
obejrzeniu reprezentantów. Brak niezależnego goldena poza przypiętymi
przypadkami oznacza, że sam procent automatycznych wyników nie jest dowodem
poprawności.

## Outcome

Profil uruchomiono 2026-08-08 jako kontrolowany proces PID `12388`. Dedykowany
worker selekcji został wcześniej zatrzymany, a worker ogólny pozostał aktywny.
Proces używa limitu 5100 s, nie publikuje wyniku i nie zapisuje stanu domenowego.

Stan procesu oraz ścieżki są zapisane w
`.runtime/image-selection-profile.pid.json`. Log postępu zapisuje się do
`.runtime/image-selection-profile-20260808T214647311Z.out.log`, diagnostyka do
odpowiadającego pliku `.error.log`, a atomowy raport końcowy powstanie jako
`artifacts/image-selection-v101-exact-geometry-first-5000-task0197.json`.

Wynik i decyzja właściciela pozostają do uzupełnienia po zakończeniu profilu.
