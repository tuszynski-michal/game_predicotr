---
title: TASK-1178 — Gotowość korekt i zalecany cel uczenia
status: done
last_updated: 2026-11-10
---

# TASK-1178 — Gotowość korekt i zalecany cel uczenia

## Status

`done`

## Goal

Pokazać aktualne ręczne korekty, zrozumiałe blokady startu i dobierać zalecany
cel uczenia zgodnie z gotowością danych.

## Context

T2 zaakceptowanego planu REVIEW_LEARNING_RELIABILITY_PLAN_20261110.md.
Zakres i koszt6–10h zatwierdzone dla całej pracy; zależy od zamknięcia T1.
Operator zgłasza disabled po kilkudziesięciu korektach oraz niejasny wybór.

## Recommended execution

gpt-6.1-sol/high; audyt Claude Code claude-opus-5-5/high.

## Relevant docs

- ai_docs/delivery/REVIEW_LEARNING_RELIABILITY_PLAN_20261110.md, T2 i odbiór.
- ai_docs/requirements/IMAGE_INGESTION.md.
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md.
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md.
- ai_docs/architecture/API_CONTRACT.md, grid-correction-learning.
- ai_docs/process/CROSS_AUDIT.md; ai_docs/process/DEFINITION_OF_DONE.md.
- ai_docs/process/decisions/DECISION_LOG_2026.md#d-582--przyrostowe-wyspy-treningu-i-zwalnianie-nieużytych-rezerwacji.

## Scope / expected files

Istniejące: application/grid_correction_learning.py i grid_model_evaluation.py
(ten sam historyczny guard przy tworzeniu nowej oceny), storage/grid_correction_split.py,
domain/grid_correction_progress.py, schemas/grid_correction_learning.py,
Admin grid-correction-learning-panel/state i testy API/PG/interakcji.
W razie zmiany kontraktu: backend/OpenAPI/SDK/wrapper/test żądania.
Nie zmniejszać minimów, nie zmieniać ról danych dla odblokowania przycisku.
Nie uruchamiać GPU w tle ani nie stosować nowego modelu bez decyzji operatora.

## Acceptance criteria

- [x] Bieżąca przyczyna disabled rozpoznana i przedstawiona liczbowo.
- [x] Ręczne korekty poprawnie kwalifikowane; podgląd aktualizuje liczniki.
- [x] Zalecany tryb wynika z danych; ręczny wybór zaawansowany zachowany.
- [x] Każdy istotny disabled ma zrozumiały powód i dalsze działanie.
- [x] Kontrakty, historyczne polecenia i ochrona TRAIN/A/B/REG zachowane.
- [x] Regresje, lint/typecheck/build/docs/map i Opus zakończone.
- [x] Outcome i task-close; finalnie pytanie o scalenie całego zakresu.

## Verification

Testy zmienionych modułów, istniejące test_grid_correction_learning_api.py,
test_grid_correction_workflow.py, test_grid_correction_split_adapter.py,
integration/test_grid_correction_learning_postgres.py oraz interakcje Admina.
Wyniki dopiero po wykonaniu; nie przedstawiać brakujących danych jako PASS.

## Outcome

Commit: v1.7.595 (hash dopisuje kolejny commit).

T1 zamknięty v1.7.594/0e1a02ec, Opus PASS. Przed kodowaniem: rzeczywisty
GET ready blokuje GRID_LEARNING_HISTORY_STALE przed zliczeniem nowych etykiet.
Odczyt diagnostyczny po oddzieleniu wyłącznie tego warunku:362 plansze/195
zdjęć; TRAIN276(201 wcześniej użytych,75 nowych),VALIDATION53,REGRESSION21,
12 oznaczonych plansz w buforach. To diagnoza, nie zastosowanie modelu.
Założenie: historycznie zweryfikowany zakres publikacji nie jest bieżącym
dowodem użycia dawnych etykiet. Aktualność wybranej ponownie kohorty oraz
publikacja/zastosowanie raportów nadal wymagają oddzielnych kontroli.
Nowy dobór celu jest jawnym opt-in GET ready; stare polecenia zachowują tryb.
Naprawiono także ten sam guard przy tworzeniu nowej oceny. Wyniki:
64 Python,2 PG,56 UI i164 SDK PASS; lint/format/scoped mypy5,
Admin/SDK typecheck/build, OpenAPI/drift/docs/map PASS.
Odczyt nowego serwisu bez monkeypatchy:canStart=true,75 nowych TRAIN,
276 wszystkich TRAIN, osobne kontrole zachowane;56.938s, nie obietnica
błyskawicznego skanu.6 wcześniejszych FAIL fixture'ów adaptera potwierdzone
na HEAD, nie naprawiane w tym zakresie. Szczegóły i ograniczenia:
ai_docs/quality/TASK-1178_VERIFICATION.md. Audyt Opus R1 REVISE:brak
asercji wyliczania liczników(P1-1). Uzupełniono rzeczywisty _preview o warianty
pełny/częściowy TRAIN, częściowe kontrole i niereprezentatywną kopię oraz
stale wybranego historycznego pinu. P2-1/3/4/5/6 poprawione; P2-2 ryzyko
latencji dwóch podglądów jawnie zachowane i wyjaśnione w panelu.
R2 Opus5.5/high PASS,0 P0/0 P1; raport i receipt:
ai_docs/quality/TASK-1178_AUDIT_claude-opus-5-5.md. P2-2(mały zapas do60s,
możliwe dwa podglądy) oraz P2-7(brak osobnej liczby częściowego TRAIN przy
uzasadnieniu) zapisane w weryfikacji. DoD i plan sprawdzone: trwałość,
kontrakt, kwalifikacja/ochrona, loading/error/empty, aktualny podgląd,
kontrole i dokumentacja. Panel lokalnego Admina; fizyczny Android i live
wdrożenie nie były odbiorem tego zadania. Brak migracji, restartów, treningu,
aplikacji modelu i zmian danych operatora. Końcowy odbiór całego planu:
ai_docs/quality/REVIEW_LEARNING_RELIABILITY_ACCEPTANCE_20261110.md.
