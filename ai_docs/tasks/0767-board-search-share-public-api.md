---
title: TASK-0767 — Publiczne endpointy odczytu udostępnionej wyszukiwarki
status: todo
last_updated: 2026-09-30
---

# TASK-0767 — Publiczne endpointy odczytu udostępnionej wyszukiwarki

## Status

`todo`

## Goal

Endpointy publiczne z §4.3 zwracają dane wyłącznie gry z sesji, bez identyfikatorów wewnętrznych, z limitami żądań.

## Context

Punkt 5 zgłoszenia operatora z 2026-09-30, decyzja D-471. Pełna specyfikacja: plan §3 R4, §4.3–4.5 i §5 T8.

## Dependencies / entry conditions

- TASK-0763 i TASK-0766 done.
- Etap B wymaga osobnego polecenia operatora.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz taska w tabeli planu). Publiczna powierzchnia danych: izolacja gry, redakcja, limity. Audyt: niezależny agent `claude-fable-5-1` (`high` warunkowo). Dwa nieudane cykle poprawek P0–P2 zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

Zakres, pliki, przypadki testowe i kryteria według planu §5 T8. Przed startem ponownie sprawdzić kod po etapie A i doprecyzować ten plik.

## Out of scope

Według planu §8.

## Acceptance criteria

- [ ] Kryteria akceptacji planu §5 T8 spełnione.
- [ ] Brak otwartych uwag P0–P2 audytu.

## Technical notes

Patrz plan §5 T8.

## Expected files

Patrz plan §5 T8.

## Test cases

Patrz plan §5 T8.

## Verification

```powershell
# komendy według planu §5 (wspólne polecenia weryfikacji)
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

Według planu §7.

## Outcome

Wypełnia agent po pracy.
