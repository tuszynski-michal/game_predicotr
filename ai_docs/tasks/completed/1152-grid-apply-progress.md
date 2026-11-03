# TASK-1152 — Zachowanie postępu między etapami zastosowania modelu

## Status

`done`

## Goal

Wznowione zastosowanie modelu kończy publish/default/activate bez regresji zapisanych liczników.

## Context

Jawne polecenie operatora zastosowania PASS jako default i dla MumieA2 utworzyło apply a2eeba17-405a-42d1-952f-1a469a1fcfce. Publish zakończone, kolejny lease odrzuca success_count0 wobec1 z JOB_PROGRESS_REGRESSION. Default/przypisanie niezmienione. Nie ponawiać startu ani nie zmieniać SQL/statusu ręcznie.

## Recommended execution

gpt-6-astra/high, lokalna mechaniczna poprawka. Jeden claude-opus-5-5/high przed commitem.

## Relevant docs

- AGENTS.md; process/DEFINITION_OF_DONE.md.
- requirements/VISION_LAB.md: Correction learning and scoped evaluation.
- architecture/VISION_LAB.md: Explicit correction apply.
- domain/jobs.py: monotonic progress and lease checks.

## Scope

Istniejący handler zachowuje zapisane success/failure/review counters na wejściu nowego lease. Końcowy sukces nadal pochodzi z ukończonych steps, failure/review pozostają zachowane. Nie zmieniać guardów domenowych, receiptów, identyfikatorów, CAS ani publikacji. Test wykorzysta prawdziwy checkpoint_job i nowy handler/context między etapami, także waiting/comparison i failure/resume.

## Expected files

services/worker/src/game_predictor_worker/images/grid_correction_apply_handler.py; services/worker/tests/test_grid_correction_apply_handler.py; architecture/VISION_LAB.md; dokumentacja taska/planu/mapa.

## Acceptance criteria

- [x] Regresja odtworzona rzeczywistą walidacją domeny, test czerwony przed poprawką.
- [x] Trzy etapy i ponowne waiting zachowują monotoniczne liczniki po odtworzeniu kontekstu.
- [x] Lint/types, właściwe regresje, docs/map i Opus bezP0/P1.
- [x] Osobny commit task-close; wdrożenie i restart general worker dopiero po osobnej zgodzie.

## Risks / open questions

Brak zgody na restart usług w tym nowym zadaniu; po gotowej, audytowanej poprawce operator musi zatwierdzić merge/push i restart wyłącznie general worker. Trwające zastosowanie zachowuje częściowy sukces, nie uruchamiać nowego apply.

## Outcome

Commit: v1.7.553 (hash dopisuje kolejny commit).

### Changed

Handler zachowuje success/failure/review counts między lease. Finalny success nadal wynika wyłącznie z ukończonych etapów. Nie zmieniono guardów domeny, receiptów, API ani CAS.

### Verification results

Nowe testy na starym kodzie: 3FAIL/3PASS, wszystkie z prawdziwego checkpoint_job/JOB_PROGRESS_REGRESSION. Po poprawce worker apply/learning8PASS i domenowe progress4PASS. Test przechodzi przez3etapy na nowych handlerach/kontekstach, JSONrestored checkpoint, rzeczywiste requeue_job po failed, zachowuje ID/receipts. Osobno2waiting ze stałymi licznikami i niezerowe failure/review. Ruff format/check PASS. Logi w root artifacts/grid-applied-comparison-20261103/task1152-*.log. Scoped mypy produkcyjnego handlera PASS (1moduł; project config z tylko torch skip, follow-imports=silent), mapa odnowiona. Opus przed commitem; operacja operatora wciąż failed po publish, default/przypisanie stare.

### Not completed

Wdrożenie, restart i wznowienie tego samego apply wymagają końcowej zgody.


### Audit and final verification

Rzeczywisty Claude Code claude-opus-5-5/high R1: PASS bezP0/P1. Raport quality/TASK-1152_AUDIT_claude-opus-5-5.md. Jedna runda poprawekP2: P2-1 test używa teraz rzeczywistych defer_job_for_dependency/start_job/fail_job/requeue_job zamiast podmieniania stanu; P2-2 parametryzacja obejmuje comparison waiting i prawdziwyUUID waitingForJobId; P2-3 poprawiono link i pozycję planu w DOC_INDEX/Dostarczanie. Produkcyjny kod po audycie bez zmian, bez kolejnego audytu. Worker apply/learning po rozszerzeniu10PASS; domain progress4PASS; ruff i scoped mypy1moduł PASS. Mapa i docs przed i po domknięciu sprawdzane osobno.

Naprawa gotowa do zatwierdzenia jako konkretny diff/commit. API i Admin nie wymagają restartu; po zgodzie trzeba scalić/push i zrestartować tylko general worker, następnie oficjalne resume tego samego apply a2eeba17. Bez nowego treningu, bez resetu danych/stanów i bez ponawiania publish. Runtime potwierdzenie zależy od tej osobnej zgody; nie zgłaszamy zastosowania modelu jako wykonanego.
