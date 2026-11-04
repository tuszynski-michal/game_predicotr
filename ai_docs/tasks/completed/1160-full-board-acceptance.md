---
title: Odbiór pełnego przepływu wykrywania plansz
status: done
last_updated: 2026-11-04
---

# TASK-1160 — Odbiór pełnego przepływu i przygotowanie wdrożenia

## Status

`done`

## Goal

Potwierdzić brakujące styki rzeczywistego handlera oceny i ratunku, rozliczyć wymagania
T0–T6 oraz przygotować bezpieczną instrukcję wdrożenia bez operacji na operatorze.

## Context

T6 zaakceptowanego FULL_BOARD_DETECTION_PLAN_20261103. Baza v1.7.564
`bc00e2a736a6f5a51a9d2bd590d96d280a95d23a`, T0–T5 z audytami Opus PASS.
Użytkownik zatwierdził pozostałe3–5h pełnego wpięcia/T6/audytów04.11 około10:41
Europe/Warsaw=09:41UTC. Root koordynuje koszt i audyty. Trzy zastane zmiany
record-hash T5 w CURRENT_STATE, archiwum Q4 i ukończonym tasku1159 należą do commita T6.

## Dependencies / entry conditions

T5 zakończony i przekazał kod oraz dokumentację. Przyjmujemy jego finalne scoped
PASS, build bindings i root receipt319 plików historycznego HTML; nie powtarzamy
zielonych zestawów bez zmiany źródeł. Ostatni readiness T1 nie jest aktualnym skanem.
Brak niezależnej kalibracji blokuje automat, nie raw-quality lub dopuszczalne propozycje.

## Recommended execution

`gpt-6.1-sol` / `high`; wymagany `claude-opus-5-5` / `high`, uruchamia wyłącznie root.
Zmiana kontraktu domeny lub nowa regresja wymaga zgłoszenia rootowi przed rozszerzeniem.

## Relevant docs

- AGENTS, README, CURRENT_STATE, DECISION_LOG, PLAN_STANDARD, TASK_TEMPLATE, DoD.
- delivery/FULL_BOARD_DETECTION_PLAN_20261103.md — T6 i mapa wymagań.
- requirements/VISION_LAB.md, requirements/ADMIN_APP.md; architecture/VISION_LAB.md,
  API_CONTRACT.md, CODE_MAP.md i CODE_MAP_SYMBOLS.md.
- quality/TASK-1157_VERIFICATION.md, TASK-1158_VERIFICATION.md, TASK-1159_VERIFICATION.md.
- guides/V3_GRID_FINE_TUNING_OPERATOR.md.
- process/decisions/DECISION_LOG_2026.md — D-588 (wyłącznie korekta10:41), D-587/D-586.
- tasks/completed/1159-full-board-panel-diagnostics.md i archive/CURRENT_STATE_2026Q4.md
  — wyłącznie zastany record-hash T5 i zamknięcie tego taska skillem.
- ignored artifacts/task1160-preflight/TASK1160_DRAFT.md i ACCEPTANCE_NOTES.md.

## Scope

- Dwa kontrolowane composed testy: real handler v4/grid-only/partial A do exact
  frozen targets i raw PASS przy auto-unqualified; actual rescue observation_sink
  do runtime evidence zgodnego z A-selected routing/profile.
- Brakujący downgrade0181 guard w disposable PG, tylko jeżeli brak wcześniejszego dowodu.
- Raport wymaganie→test/DoD, liczniki wszystkich propozycji i automatu, jawne ograniczenia.
- Istniejący operator guide:0179→0180→0181, capability/role provisioning, zgodne
  API/worker/UI, diagnostic registration przed nowym B/REG, NTFS i model rollback.
- Jedna korekta potwierdzonego timestampu D-588, bez zmiany decyzji i literalnych audytów.

## Out of scope

Operator DB, rejestracja diagnostyk, migracje/usługi, rzeczywista inferencja/trening/GPU,
publish/apply/default/rollback, benchmarki, nowy model/GT store/API i merge/push.
Browser visual/Android review jest niewykonany; zakazu obejścia local-file policy
nie omijamy serwerem, inną przeglądarką, CDP lub screenshot harness.

## Acceptance criteria

- [x] Rzeczywisty handler zapisuje wszystkie frozen A targets częściowego grid-only;
  require_targets(A) przechodzi, B nie trafia do A, raw PASS nie staje się auto PASS.
- [x] Actual run_with_rescue sink daje zgodne result-bound evidence; routing/preset
  drift nie przechodzi. Walidatory/proof/store i phase sealing nie są mockowane.
- [x] Restart zachowuje detail/report/frozen identities i budżet; partial dane nie
  dostają whole-photo/FP/duplicate claims. Brak nowej kwalifikacji rzeczywistego NN.
- [x] Deployment/readiness/downgrade/registration/rollback i liczniki mają właścicielski
  opis oraz konkretną kolejność, granice zgody i komendy PowerShell z timeoutem.
- [x] Plan/DoD pokryte dowodami aktualnych źródeł; reuse T0–T5 i niewykonane czynności jawne.
- [x] Scoped testy, lint/format/types adekwatne do delty, docs/map, root Opus PASS,
  task-close, wersjonowany commit i oddzielny końcowy record-hash.

## Technical notes

Autorytet celu to GridBoardDataset/strict frozen snapshot, nie sidecar. Test przechodzi
przez GridModelEvaluationJobHandler._run, CalibrationObserver i FullBoardCalibrationRun;
NN jest kontrolowane. Sink przechodzi real run_with_rescue i runtime_evidence, nie
ręczne składanie z assessment attrs. Dokładny zbiór porównujemy przed copy dedup.
Brak kwalifikacji B nie usuwa prawidłowego raw-quality wyniku. Małe fixtures nie są
rzeczywistym B/REG, dowodem niezależności lub poprawy modelu. Nie ma nowej decyzji produktu.

## Expected files

- Proponowane testy: services/worker/tests/test_full_board_acceptance.py;
  ewentualne rozszerzenie istniejącego test_validation_purpose_migration_postgres.py.
- Istniejące: guides/V3_GRID_FINE_TUNING_OPERATOR.md, delivery/FULL_BOARD_DETECTION_PLAN_20261103.md,
  process/decisions/DECISION_LOG_2026.md (D-588), process/CURRENT_STATE.md i close-out.
- Proponowany raport: quality/TASK-1160_VERIFICATION.md. Product source tylko przy
  odtworzeniu regresji; mapa kodu regenerowana zgodnie z rzeczywistą deltą.

## Test cases / Verification

Dwa przypadki Acceptance criteria i negatywne target/routing drifts; cold handler/store
odczytuje ten sam zapis bez nowego wywołania NN. Każda komenda ma timeout120s,
cwd D:/game_predicotr/worktrees/full-board-detection. Celowany pytest nowego pliku,
Ruff tego pliku; scoped mypy tylko przy zmianie produkcji; docs:check, code-map:check
i git diff --check. Dokładne wykonane komendy i wyniki trafią do raportu/Outcome.

## Risks / open questions

Nie ma blokującej decyzji produktowej. Zachować accepted T2/T3/T4 P2; brak realnego
NN wyniku i browser review nie jest ukrywany przez testy mechanizmu. T5 scoped types/
mirror builds nie oznaczają standard-workspace ani global mypy PASS.

## Outcome

Commit: v1.7.565 / `f42a31bd0c7c325b8d9bdea52731925c87ec8c39`.

### Changed

- Dodano rzeczywisty odbiór handlera v4/grid-only/partial A, z exact frozen targets,
  raw PASS/auto-unqualified i kontrolowanym przerwaniem po VALIDATION oraz REGRESSION.
  Resume zachowuje detail/seal bytes, final/report SHA i liczniki wywołań względem
  nieprzerwanego przebiegu; końcowy lost-response replay nie oblicza ponownie.
- Actual run_with_rescue observation_sink przechodzi runtime_evidence i proof guards;
  routing/preset drift oraz alias nie przejmują dowodów. Slot0 bez rescue zachowuje
  baseline support i stabilne evidence. Cold reader wymusza API i worker tego worktree.
- Rozszerzono istniejący disposable PG0181 test o empty downgrade/reupgrade oraz
  każdy z trzech osobno dowiedzionych warunków ochrony historii, bez zmiany migracji.
  Poprawiono deterministyczny prefix syntetycznej rodziny zgodnie z istniejącym CHECK.
- Kod produkcji, API/SDK i schemat pozostały bez zmian. Trzy znane record-hash T5
  należą do tego commita; D-588 koryguje wyłącznie10:41 zamiast11:41.

### Verification results

- Końcowy composed:3 PASS31.77s; PGguard1 PASS25.57s. Każda komenda miała timeout120s,
  cold subprocess30s. Świadkowie NN/parity/profilu są syntetyczni, bez jakości operatora.
- Osobny READ ONLY cleanup potwierdził4 własne journals: bazy0, role0, sesje0.
- Ruff/format obu testów, docs:check, code-map:check i whitespace PASS. Przed close
  startup44553/45000B,11/11 budżetów; close/record-hash wykonują dalsze kontrole okna.
- Actual Opus5.5/high R1 **PASS**, brak P0/P1; literalny raport i snapshot zachowane.
  Wykonawca uzupełnił5 P2 tylko w testach/dokumentacji, po czym root przeczytał całą
  deltę, potwierdził4 current SHA i zaakceptował wynik. Nie wykonano drugiego Opus.
- Pełny punktowy odbiór planu/DoD oraz faktyczne scoped receipts i reuse T0–T5:
  `quality/TASK-1160_VERIFICATION.md`. Finalne T5 pełne isolated builds obu aplikacji
  po R1 są użyte ponownie; nie są standard-workspace lub global mypy PASS.

### Not completed

- Rzeczywisty trening/inferencja/GPU, aktualny skan GT i niezależne rzeczywiste B/REG
  nie były zlecone.197GT/134foto/full0 to ostatni historyczny odczyt T1, nie nowy pomiar.
- Operator DB/migracje/diagnostic registration, usługi, apply/default/rollback i merge/push
  nie były wykonywane. Instrukcja jest przygotowana do osobno zatwierdzonego wdrożenia.
- Browser visual i fizyczny Android review niewykonane. Local-file policy nie była
  obchodzona serwerem, inną przeglądarką, CDP lub render harness.
- Zachowano przyjęte T2/T3/T4 P2 dotyczące synchronicznej inspekcji, źródeł/zależności,
  alias scope, NTFS i braku power-loss/GC gwarancji. Brak nowej poprawy jakości NN.

### Documentation updates

- Istniejący operator guide opisuje0179→0180→0181, capabilities/skew, NTFS, staged
  registration przed nowym B/REG, downgrade history i model rollback bez zmiany importów
  lub ręcznych korekt. Raport rozdziela wszystkie propozycje, automat i human approval.
- Plan T0–T6 rozliczony, mapa zregenerowana i sprawdzona. task-close aktualizuje okno,
  archiwum i lokalizację taska; pełny hash zapisuje oddzielny następny metadata commit.

### Recommended next task

Odczytowy preflight integracji roota, potem osobna akceptacja wyniku i zgoda na merge.
Operatorowe wdrożenie/migracja0181 i diagnostic registration pozostają osobną bramką;
rzeczywiste doszkalanie wymaga spełnienia gotowości danych i odrębnego polecenia.
