---
title: TASK-0770 — Bramka bezpieczeństwa i odbiór udostępniania wyszukiwarki
status: todo
last_updated: 2026-09-30
---

# TASK-0770 — Bramka bezpieczeństwa i odbiór udostępniania wyszukiwarki

## Status

`todo`

## Goal

Nowa powierzchnia jest opisana w modelu zagrożeń, dokumentacji i odebrana na lokalnym buildzie produkcyjnym.

## Context

Punkt 5 zgłoszenia operatora z 2026-09-30, decyzja D-471. Pełna specyfikacja: plan §3 R4, §4.3–4.5 i §5 T12.

## Dependencies / entry conditions

- TASK-0765–0769 i TASK-0771 done.
- Etap B wymaga osobnego polecenia operatora.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz taska w tabeli planu). Bramka bezpieczeństwa i spójność dokumentacji z kodem. Audyt: niezależny agent `claude-fable-5-1` (`high` warunkowo). Dwa nieudane cykle poprawek P0–P2 zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

Zakres, pliki, przypadki testowe i kryteria według planu §5 T12. Przed startem ponownie sprawdzić kod po etapie A i doprecyzować ten plik.

## Out of scope

Według planu §8.

## Acceptance criteria

- [ ] Kryteria akceptacji planu §5 T12 spełnione.
- [ ] Brak otwartych uwag P0–P2 audytu.

## Technical notes

Patrz plan §5 T12.

## Expected files

Patrz plan §5 T12.

## Test cases

Patrz plan §5 T12.

## Verification

```powershell
# komendy według planu §5 (wspólne polecenia weryfikacji)
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

Według planu §7.

## Outcome

Wypełnia agent po pracy.
