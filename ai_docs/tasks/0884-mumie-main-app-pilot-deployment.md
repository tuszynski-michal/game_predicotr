---
title: TASK-0884 — wdrożenie pilota Mumii
status: todo
last_updated: 2026-10-06
---

# TASK-0884 — wdrożenie pilota Mumii

## Status

`todo`

## Goal

Uruchomić odebrany pilot w głównej aplikacji i przyjąć realną pierwszą partię bez wpływu na model 777.

## Context

Operator zlecił podłączenie Mumii do głównej aplikacji, uploady folderów,
korektę siatek i symboli oraz dalsze zbiorcze uczenie. Nie wymagać nowych
etykiet przed implementacją. Plan konkretyzuje przyjęty zakres.

## Dependencies / entry conditions

TASK-0880–0883 PASS; konkretna zgoda na 0144/operacje DB; bezpieczny checkpoint RGB0878.
Pracować w C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3.
Weryfikować rzeczywisty HEAD tej gałęzi przed numeracją commita.

## Recommended execution

gpt-6.1-sol / high; konfiguracja zgodna z tabelą planu.
Niezależny review: gpt-6.1-sol / high. Eskalować analizę przy sprzeczności
pochodzenia danych, kontraktu lub ochrony poprzednich konsumentów.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/delivery/MUMIE_MAIN_APP_PILOT_EXECUTION_PLAN_20261006.md
- ai_docs/process/DECISION_LOG.md — D-521
- ai_docs/delivery/GRID_V3_SHADOW_CONTRACT_20261005.md

## Scope

Wykonać dokładnie sekcję TASK-0884 planu, wraz z jej walidacją, stanami błędów,
idempotency, ochroną poprzednich workflowów i odtworzeniem w nowym procesie.
- Scalenie zachowuje aktualną pracę obu gałęzi.
- Backup, schema current/head i preview zapisane przed operacją.
- Główna aplikacja i worker gotowe; PID/readiness oraz modele zweryfikowane.
- Tylko Mumie aktywowane i 100 zdjęć pilota; większe partie po odbiorze.
- Recovery działa bez usuwania źródeł, decyzji i historii.
- Bez nieautoryzowanego push ani przerywania aktywnych zapisów.

## Out of scope

Nowy seed/refit V5, trening na predykcjach, targety Super, fikcyjne human
approvals, automatyczna aktywacja poza zatwierdzonym preview, usuwanie danych,
push oraz zmiany modelu 777.

## Acceptance criteria

- [ ] Scalenie zachowuje aktualną pracę obu gałęzi.
- [ ] Backup, schema current/head i preview zapisane przed operacją.
- [ ] Główna aplikacja i worker gotowe; PID/readiness oraz modele zweryfikowane.
- [ ] Tylko Mumie aktywowane i 100 zdjęć pilota; większe partie po odbiorze.
- [ ] Recovery działa bez usuwania źródeł, decyzji i historii.
- [ ] Bez nieautoryzowanego push ani przerywania aktywnych zapisów.

## Technical notes

Plan jest źródłem rozstrzygnięć technicznych tego taska, D-521 jego zakresu
produktowego. Nie zastępować całych źródeł pojedynczymi wycinkami w podziale
train/test. Zdjęcie z pięcioma pozycjami nie może mieć dziewięciu slotów.
R2 RGB i odrzucona para R2 to różne kwalifikacje. Runtime lab RGB potrzebuje
bilinear antialias na RGB96, nie istniejącego INTER_AREA.

Zmiana kontraktu wymaga pełnego pionu OpenAPI/klient/wrapper/request test.
Task nie nadaje zgody na operacje DB użytkownika; szczegółowy preview stanowi
wejście 0884. Własne zmiany CURRENT stagingować oddzielnie od dawnych metadanych.

## Expected files

- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\package.json
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\scripts\install_grid_engine_models.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\scripts\run_mumie_image_import.py
- Istniejące w MAIN: C:\Users\tuszy\Documents\game_predicotr\ai_docs\tasks\0878-symbol-rgb-v2-band-99-100.md
Nowe moduły, testy i migracje wskazano jawnie w odpowiadającej sekcji planu.

## Test cases

- Scalenie zachowuje aktualną pracę obu gałęzi. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Backup, schema current/head i preview zapisane przed operacją. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Główna aplikacja i worker gotowe; PID/readiness oraz modele zweryfikowane. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Tylko Mumie aktywowane i 100 zdjęć pilota; większe partie po odbiorze. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Recovery działa bez usuwania źródeł, decyzji i historii. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Bez nieautoryzowanego push ani przerywania aktywnych zapisów. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.

## Verification

Po gotowym preview i zgodzie: istniejące npm install, npm run admin:build,
npm run reviewer:build, npm run db:migrate w głównym checkoutcie.
Przed operacją sprawdzić Alembic current/heads, po operacji potwierdzić jedyny
oczekiwany head zawierający0144. Builds z zapowiedzianym dłuższym timeout;
readiness usług w10s; konkretne polecenia startu ustalić z aktualnego PID i
istniejących skryptów przy preview, bez uruchamiania drugiej kopii usług.
Odbiór100 rzeczywistych źródeł i zachowanych reguł rejestru/777, bez benchmarku.

## Risks / open questions

- Brak blokującej decyzji operatora dla przygotowania implementacji.
- Migracja/aktywacja na rzeczywistej bazie wymagają gotowego preview.
- Główna gałąź ma nowszą niezależną pracę RGB0878; zachować ją przy integracji.

## Outcome

### Changed

Jeszcze nie ukończono.

### Verification results

Jeszcze nie uruchomiono testów odbioru tego taska.

### Not completed

Pozostały kryteria odbioru wskazane powyżej.

### Documentation updates

Plan MUMIE_MAIN_APP_PILOT_EXECUTION_PLAN_20261006.md.

### Recommended next task

Odbiór pierwszej partii przez operatora.
