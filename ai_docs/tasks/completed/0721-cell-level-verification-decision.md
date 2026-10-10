# TASK-0721 — Decyzja D-462 i plan weryfikacji per komórka

## Status

done

## Goal

Zapisać zaakceptowany plan, decyzję D-462 i zadania etapu A tak, aby kolejne
taski wykonywały się bez odtwarzania rozmowy.

## Context

Operator zmienił założenie: weryfikowane są pojedyncze komórki, a
zatwierdzanie planszy, siatki lub zdjęcia nie może blokować użycia
zweryfikowanych symboli. Plan zaakceptowano 2026-09-29 z P1–P4; wykonanie
obejmuje etap A.

## Dependencies / entry conditions

Brak. Fakty i liczby z odczytu bazy 2026-09-29 są w planie.

## Recommended execution

claude-opus-5-5, high — dokument zmienia nadrzędne reguły 0.9. Audyt:
claude-opus-5-5, high (subagent, poziom warunkowy).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`

## Scope

- Plan w `ai_docs/delivery/` i link w `ai_docs/README.md`.
- D-462 w `DECISION_LOG.md`.
- Krótkie reguły D-462 w `ADMIN_APP.md` (Weryfikacja symboli, adnotacja przy
  Walidacji cięcia siatki 0.9).
- Pliki TASK-0722–0724.

## Out of scope

- Zmiany kodu i danych; szczegółowe przepisanie sekcji wymagań i modelu danych
  (każdy task etapu A aktualizuje opis swojego zachowania).

## Acceptance criteria

- [x] D-462 opisuje R1–R10 i P1–P4 bez sprzeczności z D-451.
- [x] Wymagania nie twierdzą, że niezaimplementowane zachowanie już działa.
- [x] TASK-0722–0724 zgodne z TASK_TEMPLATE i tabelą modeli planu.
- [x] Commit zawiera wyłącznie hunki tego taska.

## Expected files

- Nowe: `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`,
  `ai_docs/tasks/0722-…`, `0723-…`, `0724-…`.
- Istniejące: `ai_docs/README.md`, `ai_docs/process/DECISION_LOG.md`,
  `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/process/CURRENT_STATE.md`.

## Verification

```powershell
git diff --cached --check
```

## Risks / open questions

- `DECISION_LOG.md`, `ADMIN_APP.md` i `CURRENT_STATE.md` mają niezacommitowane
  zmiany użytkownika; indeks otrzymuje HEAD + hunki taska.

## Outcome

### Changed

- Plan `CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md` (R1–R10, A1–A4, mapa
  wymaganie → task → test, tabela modeli) i link w `ai_docs/README.md`.
- D-462 w `DECISION_LOG.md`; reguła docelowa ze statusem wdrożenia w
  `ADMIN_APP.md` (Weryfikacja symboli, Walidacja cięcia siatki 0.9).
- TASK-0722–0724 według TASK_TEMPLATE.
- Osobny commit przed taskiem: `v1.7.47` / `31cb54ca` — przywrócony quad
  siatki w fixture'ach opt-in suite PostgreSQL (od v1.7.12 suite padał przed
  asercjami).

### Verification results

- Audyt claude-opus-5-5 (subagent; poziom rozumowania dziedziczony, nie
  ustawiany jawnie): cykl 1 — 4× P1, 7× P2; cykl 2 — 1× P1 wprowadzone
  poprawką (R10 przez rewizję zamiast pikseli) i 1× P2; po poprawkach
  „Brak uwag P0–P2”. Nity P3 naniesione.
- Odczyt bazy: 456 zatwierdzonych komórek / 113 plansz ma inne piksele niż
  bieżące; definicja przez rewizję daje na obecnych danych ten sam zbiór.
- `git diff --cached --check` PASS.

### Not completed

- A4 (reset komórek przy walidacji ciągłości importu) poza etapem A.
- Pozostały dryf asercji opt-in suite `test_image_batch_store.py`
  (catalog revision, lista „Do poprawy siatki”) zgłoszony jako osobne zadanie.

### Documentation updates

- `DECISION_LOG.md`, `ADMIN_APP.md`, `README.md`, plan, zadania,
  `CURRENT_STATE.md`.

### Recommended next task

- TASK-0722.
