---
title: TASK-0879 — plan pilota Mumii
status: done
last_updated: 2026-10-06
---

# TASK-0879 — plan pilota Mumii

## Status

`done`

## Goal

Utrwalić wykonywalny plan podłączenia zaakceptowanego R2 RGB i neural geometrii do folderów, korekty oraz dalszego uczenia.

## Context

Operator zlecił podłączenie Mumii do głównej aplikacji, uploady folderów,
korektę siatek i symboli oraz dalsze zbiorcze uczenie. Nie wymagać nowych
etykiet przed implementacją. Plan konkretyzuje przyjęty zakres.

## Dependencies / entry conditions

Brak; wybór wcześniejszego R2 RGB został przyjęty przez operatora.
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

Wykonać dokładnie sekcję TASK-0879 planu, wraz z jej walidacją, stanami błędów,
idempotency, ochroną poprzednich workflowów i odtworzeniem w nowym procesie.
- Plan odróżnia pilot od pełnej kwalifikacji modelu.
- Plan pokrywa folder, sloty, pełne 24 węzły, symbole, korekty, trening i wdrożenie.
- Uwzględnia istniejący rejestr, migrację, recovery i kolizje głównej gałęzi.
- Niezależny review bez otwartych P0–P2.

## Out of scope

Nowy seed/refit V5, trening na predykcjach, targety Super, fikcyjne human
approvals, automatyczna aktywacja poza zatwierdzonym preview, usuwanie danych,
push oraz zmiany modelu 777.

## Acceptance criteria

- [x] Plan odróżnia pilot od pełnej kwalifikacji modelu.
- [x] Plan pokrywa folder, sloty, pełne 24 węzły, symbole, korekty, trening i wdrożenie.
- [x] Uwzględnia istniejący rejestr, migrację, recovery i kolizje głównej gałęzi.
- [x] Niezależny review bez otwartych P0–P2.

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

- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\ai_docs\delivery\MUMIE_MAIN_APP_PILOT_EXECUTION_PLAN_20261006.md
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\ai_docs\process\DECISION_LOG.md
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\ai_docs\process\CURRENT_STATE.md
Nowe moduły, testy i migracje wskazano jawnie w odpowiadającej sekcji planu.

## Test cases

- Plan odróżnia pilot od pełnej kwalifikacji modelu. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Plan pokrywa folder, sloty, pełne 24 węzły, symbole, korekty, trening i wdrożenie. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Uwzględnia istniejący rejestr, migrację, recovery i kolizje głównej gałęzi. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Niezależny review bez otwartych P0–P2. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.

## Verification

Kontrola wg PLAN_STANDARD: każde wymaganie → task → przypadek odbioru;
sprawdzone API i schema, pochodzenie, idempotency, recovery, sloty, crop/input
oraz ochrona 777. Niezależny read-only review gpt-6.1-sol/high.
Przed commitem git diff --cached --check, staged paths/stat; po commicie
git show --stat i status. Dokument nie wymaga builda aplikacji ani benchmarku.

## Risks / open questions

- Brak blokującej decyzji operatora dla przygotowania implementacji.
- Migracja/aktywacja na rzeczywistej bazie wymagają gotowego preview.
- Główna gałąź ma nowszą niezależną pracę RGB0878; zachować ją przy integracji.

## Outcome

### Changed

Plan0879–0884, D-521, taski i supplementy requirements/architecture.
Wykryte opset17/Torch/crop96, źródłowa korekta przed sequence i ochrona
holdoutów mają konkretne rozwiązania. Większy eksperymentC zastąpiony jawnym
pilotem R2 RGB, bez zmiany odrzucenia V5 ani pary R2.

### Verification results

Niezależny review ai_experiment_audit: PASS po poprawkach,0 otwartychP0–P2.
PLAN_STANDARD/DoD i cztery kryteria odbioru spełnione. Read-only live API
potwierdziło grę/katalog/profil. Preflight405 real crops z3 zdjęć: input
max7.153e-7, logit max1.908e-6,0 class changes;40.17s, timeout120s, exit0.
Testy implementacji0880–0884 nie zostały jeszcze wykonane.
Oddzielny commit v1.7.221 / 2ac7a36bdf7894021de0d7c4118649efa025945e,
potwierdzony git show --stat; dawne dirty metadata zachowane poza stagingiem.

### Not completed

Nie wdrożono aplikacji, nie zmieniono bazy ani aktywacji. Te działania należą
do następnych tasków. Nie jest wymagane nowe oznaczanie przez operatora teraz.

### Documentation updates

Plan MUMIE_MAIN_APP_PILOT_EXECUTION_PLAN_20261006.md.

### Recommended next task

TASK-0880. Kontynuować zgodnie z planem po audycie i commicie.
