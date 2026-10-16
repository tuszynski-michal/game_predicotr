# TASK-1032 — `AGENTS.md` ≤ 14 000 B: procedury do skilli

## Status

`todo`

## Goal

`AGENTS.md` ma najwyżej 14 000 B, zawiera wszystkie reguły wiążące w krótkiej
formie, a procedury zamykania taska, scalania i audytu są w skillach; budżet
jest wymuszany.

## Context

Plan `delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md`, etap B,
decyzja E3. `AGENTS.md` ma ok. 26 800 B i jest czytany przez każdą sesję,
wykonawcę i audytora; ok. 13 500 B to procedury potrzebne tylko w jednym
momencie pracy (tabela sekcji w planie).

## Dependencies / entry conditions

- TASK-1030 i TASK-1031 ukończone (skille `task-close`, `merge-to-main`).
- Gałąź zsynchronizowana z `main` tuż przed wykonaniem.

## Recommended execution

claude-opus-5-5 / high. Review: gpt-6.1-sol / medium przez
`scripts/audit_task.ps1` (operator może zrezygnować).

## Relevant docs

- `AGENTS.md`, `CLAUDE.md`
- `.claude/skills/audit-task/SKILL.md`, `.codex/skills/claude-audit/SKILL.md`
  (lub nowy katalog Codex z TASK-1030)
- `.claude/skills/task-close/SKILL.md`, `.claude/skills/merge-to-main/SKILL.md`
- `ai_docs/delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md`

## Scope

- Przenieść szczegóły do skilli, zostawiając w `AGENTS.md` 1–3 zdania
  wiążące i nazwę skilla:
  - „Audyt krzyżowy” → skille audytu (wykrywanie CLI, parametry skryptu,
    format raportu, limity czasu); w `AGENTS.md`: audytor z innej rodziny,
    tylko gdy wskazuje go plan, P0/P1 blokują commit, jedna runda;
  - „Scalanie do gałęzi integracyjnej” → `merge-to-main`; w `AGENTS.md`:
    `main`, scalenie i push tylko po akceptacji wyniku całego zleconego
    zakresu, migracje przed scaleniem;
  - „Wersjonowanie commitów”, „Brudny worktree”, „Po kodowaniu” →
    `task-close`; w `AGENTS.md`: osobny commit `vX.Y.N` na task, tylko hunki
    taska, zamknięcie przez skill;
  - „Oszczędzanie kontekstu” i akapit mapy kodu: skrócić do jednego akapitu.
- Pozostałe sekcje (zasady nadrzędne, budżet tokenów i zgody, usługi,
  trwałość, limity czasu, testy, operacje danych, hierarchia źródeł) zostają;
  dozwolone tylko skróty bez zmiany sensu.
- `scripts/check_startup_read_budget.py`: budżet `AGENTS.md` 14 000 B
  wymuszony; test negatywny.
- Odwołania do przeniesionych sekcji w innych dokumentach (`rg` po nazwach
  sekcji w `ai_docs/`, `CLAUDE.md`, skillach) przepiąć na skill.

## Out of scope

- Zmiana treści reguł lub polityk (np. modelu audytora).

## Acceptance criteria

- [ ] `AGENTS.md` ≤ 14 000 B; budżet wymuszony; `docs:check` PASS.
- [ ] Tabela w `Outcome`: każda reguła (zdanie z „musi”, „nie”, „wymaga”, „tylko”) z poprzedniej wersji → miejsce po zmianie (`AGENTS.md` sekcja albo skill); brak reguł bez miejsca.
- [ ] Brak martwych odwołań do usuniętych nagłówków.
- [ ] Review Codex PASS albo jawna rezygnacja operatora.

## Expected files

- Istniejące: `AGENTS.md`, `CLAUDE.md` (odwołania), skille z TASK-1030/1031,
  skille audytu, `scripts/check_startup_read_budget.py`, test budżetu.

## Verification

```powershell
# katalog worktree z dowiązaniem .venv, timeout 120 s
.\.venv\Scripts\python.exe scripts/check_startup_read_budget.py --report
npx prettier --check AGENTS.md
npm run docs:check
```

## Risks / open questions

- Agent bez załadowanego skilla może pominąć procedurę; zdanie wiążące w
  `AGENTS.md` musi nazywać skill i moment użycia.

## Outcome

Wypełnia agent po pracy.
