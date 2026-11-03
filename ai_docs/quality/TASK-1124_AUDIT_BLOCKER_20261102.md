---
title: TASK-1124 — blokada wymaganego audytu
status: superseded
last_updated: 2026-11-02
---

# TASK-1124 — blokada limitu sesji audytora

To jest raport operacyjny blokera, **nie audyt i nie werdykt PASS/REVISE**.

## Aktualizacja po wznowieniu

Operator wznowił audyt po resecie limitu. Wymagany Opus5.5/high wykonał audyt (kod0, REVISE); P1 i P2 rozliczono jedną rundą poprawek oraz decyzją leada. Raport bieżący: [audyt i rozliczenie](TASK-1124_AUDIT_claude-opus-5-5.md). Poniższy stan i komenda opisują historyczną blokadę, nie stan końcowy taska.

## Stan historyczny

Implementacja A1 i weryfikacja pionu są gotowe do audytu. Task pozostaje
`blocked`, bez commita i bez `task-close`. Nie rozpoczęto A2, pilota,
treningu ani skanu danych operatora. Wymagany audytor nie został zmieniony.

## Próba audytu

Z katalogu `D:/game_predicotr/worktrees/777a2-readability-replacement` uruchomiono
`scripts/audit_task.ps1 -Task 1124 -Auditor claude -Model claude-opus-5-5
-Effort high -Plan ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md
-TimeoutSec 480`, z `-Paths` ograniczonym do trzech nowych modułów, testu,
taska, planu oraz wymagań i architektury symboli. Wywołanie miało zatwierdzony
dostęp poza ograniczeniami sieciowymi narzędzia (`require_escalated`).

Skrypt zapisał brief `artifacts/audits/TASK-1124_BRIEF_claude.md` (93 889 B),
wykrył fizyczną instalację Claude Code 2.1.309 i zakończył się błędem:

```text
audit_task: the claude CLI exited with code 1. stderr tail:
```

Stderr był pusty. Nie powstał raport audytu. Kod procesu wywołującego skrypt
w tej sesji wynosił 1; wewnętrzny proces Claude również zwrócił 1.

Jedna ograniczona diagnostyka tego samego dynamicznie wykrytego CLI,
z `-p --permission-mode plan --model claude-opus-5-5 --effort high`,
limitem 60 s i przechwyceniem stdout/stderr potwierdziła przyczynę:

```text
EXIT 1
STDOUT You've hit your session limit — resets 8:10pm (Europe/Warsaw)
STDERR
```

Diagnostyka nie była audytem. Nie wykonywano kolejnych prób ani zmian
poświadczeń. Reset wskazany przez CLI: **2026-11-02 20:10 Europe/Warsaw**.

## Weryfikacja przed blokadą

- `pytest -q --basetemp=artifacts/pytest-1124-run3 services/worker/tests/test_readability_detector.py`:
  **12 passed in 15.23s**, kod 0. W tym publiczny fit obu headów, odczyt
  artefaktu w nowym procesie, neutralność BN, split leakage, minima pilota,
  niepewne etykiety, natural audit200, ranking i nonconvergence.
- `ruff check` i `ruff format` czterech nowych plików: PASS, kod 0.
- `mypy --follow-imports=silent` trzech nowych modułów: PASS, kod 0.
- Pełne śledzenie importów mypy ujawniło wcześniejsze błędy
  `services/api/src/game_predictor_api/schemas/source_lattice_geometry.py:36,38`
  i osiągnęło 120 s; nie jest zaliczoną kontrolą całego repo. Próba `skip`
  pomijała również numpy i powodowała niemiarodajne błędy aliasów typów.
- `generate_code_map.py` oraz `generate_code_map.py --check`: PASS, kod 0.
- `npm run docs:check` nie znalazło `.venv` w izolowanym worktree.
  Wszystkie cztery identyczne skrypty wykonano bezpośrednio Pythonem
  `D:/game_predicotr/.venv/Scripts/python.exe`: linki decyzji, okno stanu,
  budżety startowe i mirror skilli **PASS**, każdy kod 0. Budżety: 11/11;
  odczyt startowy 43 610 B. Redundantny punkt ograniczeń usunięto, zachowując
  informację w planie i wskaźniku taska.
- Wyłącznie read-only sprawdzono pierwszy asset zamrożonego datasetu:
  RGB64x64. Nie wykonano pełnego preflightu ani inferencji na danych operatora.

Każda skończona komenda miała limit do 120 s; diagnostyka 60 s,
audyt 480 s. Wyniki testów odnoszą się do małych kontraktowych fixture,
nie do jakości empirycznej detektora na bibliotece operatora.

## Wznowienie

Po resecie limitu operator/lead może wznowić **ten sam wymagany audyt**:

```powershell
Set-Location D:/game_predicotr/worktrees/777a2-readability-replacement
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_task.ps1 `
  -Task 1124 -Auditor claude -Model claude-opus-5-5 -Effort high `
  -Paths services/worker/src/game_predictor_worker/symbols/readability_features.py,services/worker/src/game_predictor_worker/symbols/readability_cohort.py,services/worker/src/game_predictor_worker/symbols/readability_detector.py,services/worker/tests/test_readability_detector.py,ai_docs/tasks/1124-readability-detector-core.md,ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md,ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md,ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md `
  -Plan ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md `
  -TimeoutSec 480
```

Potrzebny jest ten sam dostęp sieciowy narzędzia. Po rzeczywistym audycie:
odczytać raport, rozliczyć najwyżej jedną rundę P0/P1, uzupełnić Outcome,
użyć `task-close`, ustalić wersję z bieżącego `git log`, wykonać commit
i `record-hash`. Nie ma obecnie hasha zamykającego task.

## Interfejsy dla A2 po odblokowaniu A1

- `readability_features.preflight_base(...) -> (FrozenBase, SpatialSymbolCnn)`:
  ścieżki/checksumy datasetu i checkpointu, data root i jawny preprocessing.
- `extract_features(model, native_rgb_crops) -> ndarray[N,1032]`, batch <=128.
- `readability_cohort.QualitySample`: identity, provenance, niezależne
  human `overlap`/`unreadable` bool/null i warstwy oceny.
- `assign_families(samples, base, assignments=...) -> CohortSplit` oraz
  `pilot_issues(cohort)`: kontrola rodzin/splitów i minimów bez modelu.
- `train_detector(cohort, features, base) -> QualityArtifact`:
  tylko po etykietach i jawnej zgodzie na eksperyment. `document()` daje
  serializowalny JSON z fingerprintem. `load_artifact(...)` odtwarza model.
- `rank_candidates(artifact, samples, features)` oraz
  `evaluate_pilot(artifact, cohort, features, natural_audit_receipt=...,
  operator_accepted=False)` dają ranking i bramkę. Sam artefakt nie
  upoważnia do pełnego skanu. A2 najpierw umożliwia zebranie etykiet bez
  gotowego detektora.
