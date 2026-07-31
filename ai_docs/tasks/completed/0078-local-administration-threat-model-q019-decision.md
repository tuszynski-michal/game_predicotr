---
title: Local administration threat model and Q-019 decision
status: done
last_updated: 2026-07-31
---

# TASK-0078 — Local administration threat model and Q-019 decision

## Status

`done`

## Goal

Zdefiniować adekwatny model bezpieczeństwa lokalnego panelu Admin dla prywatnej
wersji `0.1`, potwierdzić granicę jednego właściciela na loopback oraz zamienić
zamknięte Q-019 i istniejące decyzje Reviewera w testowalne wymagania dla
TASK-0079.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_08_EXECUTION_PLAN.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- aktywa, granice zaufania, aktorzy i założenia lokalnego Admina,
- zagrożenia dla konfiguracji, importów, wydań, plików i sekretów,
- model jednego lokalnego właściciela bez pozornej ochrony hasłem,
- wymaganie loopback dla Admina, API i PostgreSQL,
- rozdzielenie Admina od ograniczonego zdalnego Reviewera,
- wymagania potwierdzenia operacji destrukcyjnych i append-only audytu,
- przegląd logów, OpenAPI, ścieżek plików i sekretów,
- jawna lista działań implementacyjnych dla TASK-0079.

## Out of scope

- implementacja zabezpieczeń TASK-0079,
- zewnętrzny test Cloudflare Quick Tunnel z TASK-0115,
- publiczny Admin, chmura, Google Play i port forwarding,
- pełny system kont użytkowników dla lokalnego właściciela,
- backup/restore z M8.3.

## Acceptance criteria

- [x] Model wymienia aktywa, aktorów, granice zaufania i scenariusze nadużyć.
- [x] Lokalny Admin ma jawny model jednego właściciela na loopback.
- [x] Zdalny Reviewer nie rozszerza powierzchni Admin API.
- [x] Operacje destrukcyjne mają wymagania celu, potwierdzenia i audytu.
- [x] Sekrety, kody, tokeny i ścieżki absolutne mają jawne zasady logowania.
- [x] Luki implementacyjne są przypisane do TASK-0079 z priorytetem.
- [x] Dokumentacja źródeł prawdy i CURRENT_STATE są spójne.

## Expected files

- `ai_docs/security/LOCAL_ADMIN_THREAT_MODEL.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/delivery/MILESTONE_08_EXECUTION_PLAN.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
rg -n "loopback|destruk|audit|secret|Reviewer" ai_docs/security/LOCAL_ADMIN_THREAT_MODEL.md
git diff --check
```

## Outcome

Dodano `LOCAL_ADMIN_THREAT_MODEL.md` z aktywami, aktorami, granicami zaufania,
macierzą zagrożeń, operacjami wysokiego wpływu i priorytetami TASK-0079.

Audyt implementacji potwierdził:

- fail-closed konfigurację loopback API, Admina i PostgreSQL,
- osobną, allowlistowaną powierzchnię zdalnego Reviewera,
- potwierdzenia operacji wysokiego wpływu w bieżącym UI,
- brak wspólnego serwerowego guardu potwierdzenia i append-only audytu lokalnych
  mutacji administracyjnych.

D-097 utrzymuje model jednego właściciela Windows bez pozornego lokalnego
logowania. TASK-0079 otrzymał priorytety: regresja granicy sieciowej, serwerowa
intencja/potwierdzenie, aktor `local-owner`, append-only audyt, ochrona
cross-origin oraz redakcja sekretów. Nie zmieniono kodu produkcyjnego.
