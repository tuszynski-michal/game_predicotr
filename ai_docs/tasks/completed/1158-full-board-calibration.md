---
title: Completeness and independent automatic calibration
status: done
last_updated: 2026-11-04
---

# TASK-1158 — Kompletność i rozdzielona kalibracja

## Status

`done`

## Goal

Mierzalne kontrole kompletności i wersjonowana kwalifikacja automatu per gra, z trwałymi A/B w istniejącym ledger oraz zachowaniem historii i częściowych kontrolnych zdjęć.

## Dependencies / entry conditions

T0–T3 done; HEAD f78c5b5a1a6dcbc1c0d280a0f4d2204417e5d9a3. Trzy znane wpisy record-hash T3 zachować i dołączyć do commita T4. D-587 i migracja0181 sprawdzone na wszystkich lokalnych/remotes refs, wolne. Dodatkowy zakres4–6h T3–T6 z audytami zatwierdzony.

## Recommended execution

GPT gpt-6-astra/high. Niezależny Claude Code claude-opus-5-5/high uruchamia root na scoped pakiecie. Bez zmiany modelu; otwarte P0/P1 blokują commit.

## Relevant docs

- AGENTS.md; ai_docs/process/{PLAN_STANDARD,TASK_TEMPLATE,DEFINITION_OF_DONE,CURRENT_STATE,DECISION_LOG}.md.
- ai_docs/delivery/FULL_BOARD_DETECTION_PLAN_20261103.md, T4 i styki T1–T3/T5/T6.
- ai_docs/requirements/VISION_LAB.md; ai_docs/architecture/VISION_LAB.md; CODE_MAP.md.
- ai_docs/quality/TASK-1157_VERIFICATION.md; FULL_BOARD_INPUT_DIAGNOSIS_20261103.md.
- D-585 i D-586: ai_docs/process/decisions/DECISION_LOG_2026.md (wpisy przypięcia operacji i ratunku).
- Zaakceptowany host draft: artifacts/task1158-preflight/TASK1158_DRAFT.md; decyzje roota utrwalone poniżej.

## Scope / Technical notes

1. Czyste mierzalne features: punkty/pewność/piksele, detector-grid, game/reference oraz perspective-neighbor, primary/rescue. Brak odniesienia nie daje PASS. Routing recognition/rescue z TRAIN/A i nowym path proof; progi B tylko auto-accept.
2. validationPurpose A/B w istniejącym registry; całe copy/session/ancestry components i bufory. Stare whole-row JSON/proof/receipts byte-for-byte. Legacy selection exposure tylko A; fresh freeze/start/resume blokuje B. Preview nie utrwala ról.
3. Assessment scope labelled_targets: 30 distinct dedup źródeł baseline-bad i30 baseline-good per opisany target osobno B/REG. Mieszane zdjęcie może zasilać obie klasy; overlap jawny. Candidate truth osobno, naprawione błędy nie usuwają minimum. Partial zachowane, whole-photo/FP/duplicates tylko full. Screen TRAIN/A full, REG5photos/15GT/full0.
4. Coverage missingArea/GTCellArea w x/W,y/H, epsilon1e-6 tylko numeryczne. Definicja i deterministic menu<=256 z tie-break zamrożone przed B; sealed profile przed REG. Zero przyjętych przycięć i wzrost correctAutomatic względem bazy po T0, raport także preT0. Bez statystycznych deklaracji.
5. Osobne raw quality/publication PASS i automatic qualification. Brak B/minimów nie blokuje dozwolonego treningu/propozycji/manual apply. Reuse report storage/currentness, bez nowego job frameworku.
6. Nowe acceptance-v4/pin-v3 obejmują centralne guards, SQL IMPORT/VALIDATE identity lookup i workflow/API. Cold retry zachowuje historyczny pin+policy, bez nonce/nowego budżetu.
7. Generic strict diagnostic record registration do istniejącego ledger; konkretny metadata staging manifest/polecenie dla T1 przed nowymi B/REG. Bez wykonania na operatorze i hardcode UUID w produkcie. Readiness134 nie exposure; 462205 i closure wykluczone B/REG po rejestracji.

## Expected files

Istniejące: domain/{grid_correction_policy,neural_grid_operation_pin,v3_engine_acceptance}; storage/{source_recording_sql*,grid_correction_split,job_repository,neural_grid_operation_qualification}; cohort commands/freeze/currentness; worker GridAssessmentDataset, evaluation/training/rescue pipeline; API schemas/OpenAPI/generated SDK/wrapper. Nowe: pure completeness/calibration modules, SQLv8/migration0181, focused tests i verification. Mapa regenerowana na końcu.

## Out of scope

Operator DB writes/migracja, usługi, realny trening/inferencja/GPU, model apply, merge/push. Nie powtarzać testów T0–T3 bez zmiany zależnego zachowania. Audyt wykonuje wyłącznie root; commit dopiero po PASS.

## Acceptance criteria / Test cases

- [x] Definicja bad/good i overlap, candidate naprawia wszystkie błędy, 29/30, partial scope i missing evidence.
- [x] Deterministyczne features, pixel coverage, brak reference, perspective i primary/rescue; A routing proof i stare trigger semantics.
- [x] Trwałe A/B, closure/buffers/diagnostics, legacy fences; migration zachowuje stare JSON/hash/receipts; atomic rollback/retry.
- [x] B menu preregistered, REG sealed/no tuning; oddzielne publication i automation; currentness i restart.
- [x] Cold IMPORT/VALIDATE retry pin+policy, brak autolabel/early accepted i bez odnowienia budżetu. Po R1 dodatni PG obejmuje oba typy i drift; VALIDATE wywodzi politykę ze swojego pinu.
- [x] Diagnostic manifest i polecenie przygotowane, bez operator mutation.
- [x] Pełny wymagany API/SDK pion, scoped tests/lint/mypy/docs/map, root Opus R1 i focused R2 PASS, Outcome i task-close v1.7.563.

## Verification

Wyniki i granice: [TASK-1158_VERIFICATION.md](../../quality/TASK-1158_VERIFICATION.md). Scoped API/worker i disposable PG wykonane; Ruff71plików PASS, mypy57modułów bez nowych błędów (1 potwierdzony baseline), OpenAPI/SDK/Admin types, frontend lint/format, docs/map PASS. Audyt roota R1 i focused R2 PASS; zamknięcie v1.7.563.

## Risks / open questions

Brak rzeczywistych niezależnych B/REG poprawnie pozostawia automat unqualified. T3 P2 ograniczenia synchronicznej inspekcji i archiwalnych reasonów pozostają. Liczniki preT0/T0 są porównaniem polityk na tych samych wynikach bazy, nie wykonaniem historycznego modelu. Nie uruchomiono benchmarku sweepu/inspekcji ani modelu na danych operatora.

## Outcome

Commit: v1.7.563 / `c7ed8afe1913292d3fe5f7f23cb133f077ac84e2`.

### Changed

SQLv8/Alembic0181, existing-ledger purpose A/B i snapshot/split/correctionsv4; ścisłe kontrolki kompletności i mierzone wsparcie rastra; zamrożone menu per gra i kolejne fazy A/B/REG; reportv5 z oddzielną kwalifikacją automatu; pinv3/acceptancev4 i zachowane historyczne retry. Nowy routing przechodzi rzeczywisty istniejący evaluator A. Actual raster identity wiąże cache i RescueAttemptStore. Generic diagnostic stage/execute oraz trwały manifest2rekordy/1źródło, bez execute. Backend/OpenAPI/SDK/wrapper/request i zgodność odczytu Admin.

### Verification results

Scoped wyniki w raporcie jakości. Rzeczywisty PG reader/profile/publication/workflow/API kwalifikuje dodatni v4 i blokuje drift. PG potwierdza stare proof JSON, nowe purpose fences, atomic freeze/rollback/odczyt z nowego połączenia oraz idempotentne diagnostyki. Dwa stare FAIL preview potwierdzone na HEAD, jeden mypy baseline przez shadow-file; testy nieosłabione. Syntetyki dowodzą kontraktu, nie kwalifikacji realnego modelu.

Opus R1 PASS zachowany jako [AUDIT_ROUND1](../../quality/TASK-1158_AUDIT_ROUND1.md). Koordynator zakwalifikował P2-1 jako P1: samo zadeklarowanie target hash było niewystarczające. Jedna runda poprawek wiąże plan i faktyczne cele z DB-bound frozen snapshot w workerze/resume/API; wymagane sourceId w niewydanym formacie, bez domyślania starego rekordu. R2: 14 unit + 1 composed routing + 1 PG PASS, Ruff12plików i mypy9modułów PASS. PG sprawdza6 rehashed removed/replaced/duplicate B/REG oraz zimne IMPORT/VALIDATE. [Focused R2 Opus](../../quality/TASK-1158_AUDIT_claude-opus-5-5.md) PASS, brak P0/P1; P1 koordynatora i P2-1/2/5 zamknięte.

Zaakceptowane ograniczenia P2-3/4: synchroniczny koszt sidecara/sweepu pod admission lock bez nowego cache/benchmarku; minima dotyczą dedup źródeł, nie niezależnych komponentów sesji/ancestry. Nie deklarujemy niezależności ani gwarancji statystycznej. Poprzednie ograniczenia T3 pozostają.

Nowe nieblokujące P2-6 zaakceptowane: composed test ręcznie składa observation z rzeczywistego RescueAssessmentEngine; nie przechodzi przez observation_sink run_with_rescue. Audyt sprawdził zgodne wyrażenia statycznie. T6 otrzymuje celowany scenariusz partial A/grid-only w produkcyjnym handlerze; nie wykonano go w T4 i nie deklarujemy PASS. Bez trzeciej rundy ani kolejnej zmiany zachowania.

DoD/plan T4: mierzalne features i brak reference→manual; trwałe role/closure/history; osobne A/B/REG i zamrożone menu; dokładny frozen target set; dodatni automat i drift; odrębna raw publication; pełny API/SDK pion oraz dowody i audyt — spełnione w opisanych granicach testów. Kontrola82 source SHA przed zamknięciem potwierdza zgodność kodu z zamrożonym R2. Brak empirycznej kwalifikacji danych operatora nie blokuje implementacji mechanizmu ani propozycji.

### Not completed

Operator migration/rejestracja diagnostyk/trening/ewaluacja/apply/usługi/merge/push celowo niewykonane; wymagają osobnej zgody wdrożeniowej. Realne minima B/REG nie są potwierdzone. Celowany partial A/grid-only należy do odbioru T6; ograniczenia P2-3/4/6 zapisane powyżej.

### Documentation updates

D-587, wymagania/architektura VISION_LAB, aktywny task i wskaźnik, raport jakości z trwałym staging path/SHA i poleceniem wdrożeniowym. Pełny prywatny payload operatora wyłączony z Git i audytu.

### Recommended next task

TASK-1159 / T5 po zakończeniu T4.
