---
title: Przykłady korekt i niezależne kontrole
status: done
last_updated: 2026-11-11
---

# TASK-1183 — Przykłady korekt i niezależne kontrole

## Status

`done`

## Goal

Zrealizować mierzalny wynik T2 zaakceptowanego planu skutecznego uczenia.

## Context

Operator zatwierdził całe T1–T4, koszt6–10h i audyty terminalowe; na końcu pytać o scalenie.

## Dependencies / entry conditions

Plan EFFECTIVE_GRID_LEARNING_PLAN_20261111.md, część T2. Root potwierdził diagnozę T1
(CUDA TF32) i uruchomił niezależny pion danych T2; kolejność audytów i commitów
pozostaje T1→T2. Commit T2 dopiero po zamknięciu TASK-1182.

## Recommended execution

claude-opus-5-5/high (dokończenie na polecenie operatora2026-11-11). Ryzyko i warunki według tabeli planu. Audyt zmian Claude: gpt-6.1-sol/high; wcześniejsze części Codex weryfikuje niezależnie Claude przed modyfikacją.

## Relevant docs

- `AGENTS.md`
- `ai_docs/delivery/EFFECTIVE_GRID_LEARNING_PLAN_20261111.md`
- `ai_docs/requirements/VISION_LAB.md`
- `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CROSS_AUDIT.md`
- `ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md`

## Scope

Wszystkie wymagania części T2 planu; wykorzystać istniejący pion bez równoległego trenera/rejestru.

## Out of scope

Operator GPU/trening, migracje operatora, wdrożenie, merge/push/default i nadpisywanie ręcznych korekt.

## Acceptance criteria

- [x] Wszystkie kryteria T2 planu udowodnione testami i raportem.
- [x] Ochrona historycznych wersji, danych i niezależnych kontroli zachowana.
- [ ] Opus terminal PASS, brak otwartych P0/P1, docs/map i właściwe testy.
  (R1 REVISE poprawione; audyt poprawek niewykonany — warunkowa rezygnacja operatora.)

## Technical notes

Przeczytać część T2 planu przed kodowaniem. Hipoteza nie jest diagnozą. Wyniki kodu, danych i jakości modelu oddzielne.

## Expected files

Istniejące: domain/grid_correction_split.py, grid_correction_incremental_split.py,
grid_content_sampling.py; storage/grid_correction_split.py, grid_content_sampling.py,
grid_training_cohort_evidence.py; materializacja snapshotu i capability repo.
Nowe: domain/grid_learning_material.py, grid_learning_reference.py,
source_recording_sql_v10.py, source_recording_permissions_v10.py,
Alembic0184_effective_grid_material.py, testy domenowe i PostgreSQL.
Migracja nie zmienia tabel ani historycznych funkcji. Wdrożenie operatora poza zakresem.
Publiczne DTO/OpenAPI/SDK/wrapper/requesttest raportu dostarcza T4.

## Test cases

Scenariusze i kryteria T2 oraz tabela odbioru planu. Restart i utrata odpowiedzi dla trwałych workflowów.

## Verification

Właściwy scoped pytest przez główną .venv, lint/typecheck, npm run docs:check i npm run code-map:check; dokładne komendy i wyniki w raporcie taska. Komendy mają jawny timeout.

## Risks / open questions

Brak danych operatora może blokować trening lub pomiar, nigdy zastępczy PASS jakości.

Zwykła próbka REG losowana po całych grupach niezależnie od dobro/zło i dostępności
content labels; braki wskazują wyłącznie wybrane źródła. Trudna próbka wymaga
oryginalnej predykcji ze zweryfikowanego original_target, przypiętej wersji bazowej
i aktualnego human GT. Różnica punktów nie dowodzi konkretnej kategorii błędu:
bez osobnego pomiaru kategoria pozostaje unknown. Kategorie i braki reprezentacji
są raportowane, bez dopisywania diagnozy heurystycznej.

## Outcome

Commit: v1.7.603 / `e4bba0bdc173a36aaeaf06947a9d20c3d4d3c421`.

### Changed

- Wewnętrzny manifest learningMaterial, deduplikowane wagi4:1 i jawne BUFFER.
- Wykluczenie całego konfliktującego closure z nowego v4; pełna populacja i
  registryProof zachowane w freeze/currentness. Brak zmian historycznych ról.
- R1: wykluczenia zostają w kolejności importu; closure i po10 sąsiadów bez nowej
  roli; historyczne role i cele A/B (także wykluczonych kotwic) nadal buforują.
  Zwykłe bufory historyczne nie są wykluczeniami; fresh REG bez poszerzenia do20.
- R1: content recapture obejmuje wykluczone piny; bind v5 przez v4 dla
  częściowego TRAIN; roleShortfalls przy niewykonalnym podziale;
  NEURAL_GRID_PROOF_INVALID jako unknown; stary selectionState v1 bez zmian.
- Zwykły i trudny REG przed kandydatem; sprawdzony rodowód bazy i human GT,
  unknown zamiast odgadywania kategorii. Zachowane minima i caps.
- Partial TRAIN wyłącznie content opt-in do geometrii, nadal10fullTRAIN/5fullA.
- Migracja0184 dodaje capability (v4, bind v5, wrapper v7) bez zmian tabel i
  historycznych funkcji.

### Verification results

- Wykonawca R1: claude-opus-5-5/high na polecenie operatora (limit Codex).
- 141 PASS (17.04s) na czystym delivery; PG material 1 PASS (23.35s) i realny
  pion v4 PG 1 PASS (102.95s); Ruff PASS; mypy strict 0 błędów w18 plikach T2,
  14 zastanych błędów w8 nietkniętych modułach identycznych z HEAD.
- Zastane: adapter6FAIL i core6FAIL identyczne na czystym eksporcie HEAD.
- Odczyt operatora po P0 READ ONLY68.188s: konflikt1121/34 i sąsiedztwo20/17
  (3 historyczne A); TRAIN159/271, VALIDATION4/4 (brak1zdjęcia/11plansz), REG13/21;
  podział v4 niewykonalny bez dodatkowego materiału A.
- Audyt R1 Opus: REVISE (`ai_docs/quality/TASK-1183_AUDIT_claude-opus-5-5.md`).
  Poprawki R1: audyt Codex niewykonany — kontynuacja na polecenie operatora po
  wyczerpaniu limitu. To nie jest PASS.
- Raport: `ai_docs/quality/TASK-1183_VERIFICATION.md`.

### Not completed

- Operator migracja, trening i pełna ocena danych nie były wykonywane.
- Dane operatora nie spełniają minimum A po ochronie sąsiedztwa ani pełnej
  gotowości REG/content; nie deklarowano poprawy jakości modelu.
- Pion publiczny panelu/kontraktu należy doT4.

### Documentation updates

Sekcje TASK-1183 w wymaganiach i architekturze VISION_LAB, D-602, raport jakości,
mapa kodu.

### Recommended next task

T3 (TASK-1184); wdrożenie0184 wyłącznie razem z T3 za osobną zgodą.
