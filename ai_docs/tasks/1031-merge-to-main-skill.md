# TASK-1031 — Skill `merge-to-main` z preflightem scalania

## Status

`todo`

## Goal

Przed scaleniem gałęzi roboczej do `main` agent uruchamia
`scripts/integration_preflight.py`, który raportuje możliwość fast-forward i
kolizje numerów, a skill `merge-to-main` prowadzi scalenie, push i bezpieczne
usunięcie worktree z bramkami zgody operatora.

## Context

Plan `delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md`, etap A,
decyzje E1, E2, E6. 2026-10-16 `main` przesunął się w trakcie pracy, a
kolizje TASK-1024, D-548 i `v1.7.364–365` wyszły dopiero przy scaleniu.
Usunięcie worktree z junction `.venv`/`node_modules` wymaga najpierw
odpięcia dowiązań.

## Dependencies / entry conditions

- TASK-1030 (mechanizm luster skilli i katalog Codex).

## Recommended execution

claude-sonnet-5-5 / high. Bez dodatkowego review; samokontrola kryteriów w
`Outcome`.

## Relevant docs

- `AGENTS.md` („Scalanie do gałęzi integracyjnej”, „Brudny worktree”)
- `ai_docs/process/CURRENT_STATE.md` (ograniczenia: gałąź `main`,
  akceptacja przed scaleniem, kolizje numeracji, migracje)
- `ai_docs/delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md`

## Scope

- Nowy `scripts/integration_preflight.py` (proponowany), tylko odczyt:
  - gałąź robocza vs `main` i `origin/main`: liczba commitów w obie strony,
    czy fast-forward jest możliwy, czy lokalny `main` wyprzedza `origin`;
  - kolizje numerów między gałęzią a `main` oraz innymi lokalnymi gałęziami
    z niescalonymi commitami: pliki `ai_docs/tasks/**/NNNN-*.md`, nagłówki
    `D-NNN` w pliku wpisów decyzji, prefiksy `vX.Y.N` commitów, numery
    migracji `services/api/alembic/versions/NNNN_*.py`;
  - czy gałąź dodaje migrację (przypomnienie: scalenie dopiero po
    migracji operatora);
  - wynik tekstowy i `--json`; kod 0 zawsze, chyba że błąd git.
- Skill `.claude/skills/merge-to-main/SKILL.md` (+ kopia Codex): kroki
  preflight → zgoda operatora → aktualizacja gałęzi (`git merge main` w
  worktree, rozwiązywanie konfliktów okna w nowym formacie) →
  `docs:check` → `git merge --ff-only` na `main` w `D:\game_predicotr` →
  push (zgoda na scalenie obejmuje push) → odpięcie junction (`cmd /c rmdir`)
  → `git worktree remove` → `git branch -d`; zakazy: bez `--force` na
  worktree z dowiązaniami, bez push gałęzi pomocniczych, bez scalania kodu
  wymagającego niewykonanej migracji.
- Para lustrzana w `check_skill_mirrors.py`.

## Out of scope

- Automatyczne przenumerowanie kolizji (zgłasza preflight, decyduje agent).

## Acceptance criteria

- [ ] Testy preflight na tymczasowym repo git: fast-forward możliwy / niemożliwy, kolizja TASK, D, `vX.Y.N`, migracji, `main` przed `origin/main`.
- [ ] Skill w Claude Code i kopia wykryta przez Codex; lustro w `docs:check`.
- [ ] Skill nazywa wszystkie bramki zgody z `AGENTS.md` bez ich osłabienia.
- [ ] ruff, `mypy --strict`, `docs:check` PASS.

## Expected files

- Nowe (proponowane): `scripts/integration_preflight.py`,
  `.claude/skills/merge-to-main/SKILL.md`, kopia Codex, test w
  `services/worker/tests/`.
- Istniejące: `scripts/check_skill_mirrors.py` (lista par).

## Verification

```powershell
# katalog worktree z dowiązaniem .venv, timeout 120 s
.\.venv\Scripts\python.exe -m pytest services/worker/tests -k integration_preflight -q -p no:cacheprovider --basetemp D:/ptw
.\.venv\Scripts\python.exe scripts/integration_preflight.py
npm run docs:check
```

## Risks / open questions

- Testy na repo git w katalogu tymczasowym na Windows: krótka ścieżka
  `--basetemp` (długie ścieżki psują testy).

## Outcome

Wypełnia agent po pracy.
