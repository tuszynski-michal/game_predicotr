---
title: TASK-0771 — Dziennik zapytań udostępnionego linku i odtworzenie w Adminie
status: todo
last_updated: 2026-09-30
---

# TASK-0771 — Dziennik zapytań udostępnionego linku i odtworzenie w Adminie

## Status

`todo`

## Goal

Operator widzi w Adminie, kiedy i jakie zapytania wykonano przez dany link, i
jednym przyciskiem odtwarza każde z nich w swojej sekcji „Wyszukaj plansze”.

## Context

Dopisek operatora z 2026-09-30 do punktu 5 (punkt 6), decyzja D-472.
Specyfikacja: plan §3 R5, §4.3–4.4 i §5 T11.

## Dependencies / entry conditions

- TASK-0766, TASK-0767 i TASK-0769 done. Wykonywany po TASK-0769, przed
  TASK-0770.
- Etap B wymaga osobnego polecenia operatora.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz T11 w tabeli planu). Migracja,
dane o odbiorcy i odtworzenie stanu wyszukiwarki. Audyt: niezależny agent
`claude-fable-5-1` (`high` warunkowo). Dwa nieudane cykle poprawek P0–P2
zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

Zakres, pliki, przypadki testowe i kryteria według planu §5 T11. Przed
startem ponownie sprawdzić kod po TASK-0765–0769 i doprecyzować ten plik.

## Out of scope

- Zapis adresu IP i nagłówków przeglądarki.
- Automatyczna retencja i usuwanie wpisów.
- Odtwarzanie stawki i jednostki odbiorcy.

## Acceptance criteria

- [ ] Kryteria akceptacji planu §5 T11 spełnione.
- [ ] Brak otwartych uwag P0–P2 audytu.

## Technical notes

Patrz plan §3 R5 i §5 T11.

## Expected files

Patrz plan §5 T11.

## Test cases

Patrz plan §5 T11.

## Verification

```powershell
# komendy według planu §5 (wspólne polecenia weryfikacji)
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

- Dziennik zawiera dane o zachowaniu odbiorcy; zakres zapisu ograniczony
  przez D-472.

## Outcome

Wypełnia agent po pracy.
