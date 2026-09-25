---
title: TASK-0665 — P00, zapis planu laboratorium wizji
status: done
last_updated: 2026-09-25
---

# TASK-0665 — P00, zapis planu laboratorium wizji

## Status

`done`

## Goal

Zapisać zatwierdzony plan P00/T01–T13, samodzielne taski i spójne reguły
źródeł danych oraz wykonania etapów.

## Context

Zaakceptowany po drugim review plan istniał tylko w rozmowie, a starszy plan
sieci siatek zawierał kolizje numerów i błędne D-446.

## Dependencies / entry conditions

- Wyraźne polecenie użytkownika zapisania i implementacji P00; czysta gałąź
  `v1.1-vision-lab-hybrid-geometry` na `v0.10.438`.

## Recommended execution

`gpt-6-sol`, reasoning `high`; niezależny audyt `gpt-6-astra`, reasoning
`medium`. Konfiguracje odpowiadają tabeli planu.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/delivery/GRID_ENGINE_V3_NEURAL_EXECUTION_PLAN.md`

## Scope

- Zapis nowego planu i TASK-0666–0678.
- D-447, wymagania i architektura `lab_human_approved`.
- Reguła etapowa AGENTS.md z odesłaniem z CLAUDE.md i PLAN_STANDARD.md.
- Zastąpienie starego planu, zablokowanie jego niewykonanych tasków,
  poprawienie mylącego D-446, rozdzielenie historycznego 777.
- Indeks, traceability i CURRENT_STATE.

## Out of scope

T01–T13, instalacja, eksport danych, trening, zapisy do DB, push i wdrożenie.
TASK-0611 pozostaje bez zmian.

## Acceptance criteria

- [x] Zaakceptowany plan w repo; końcowa tabela ma dokładnie P00/T01–T13.
- [x] T01–T13 mają model/reasoning/review, pliki/symbole, testy,
  komendy PowerShell z limitem i kryteria.
- [x] D-447 i dokumenty odróżniają lab approval od DB review.
- [x] Stary plan i jego niewykonane taski są oznaczone jako zastąpione/
  zablokowane, bez przypisywania D-446 do nowej wizji.
- [x] TASK-0645–0647 nie mają w tym projekcie neural slot fill;
  TASK-0611 niezmienione.

## Technical notes

Identyfikatorami starych, kolidujących tasków są pełne ścieżki plików, nie
sam numer. Numer następnej decyzji jest D-447, a następne wolne taski
zaczynają się od TASK-0665. Zaakceptowany plan chroni aktywację przez D-261
i zachowuje D-262 jako odniesienie do wcześniejszego eksperymentu.

## Expected files

- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` — nowy plan.
- `ai_docs/tasks/0666-*.md` … `0678-*.md` — nowe zadania.
- `AGENTS.md`, `CLAUDE.md`, `ai_docs/process/PLAN_STANDARD.md` — reguła.
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`,
  `ai_docs/process/DECISION_LOG.md` — pochodzenie etykiet.
- Stary plan/taski, indeks, traceability i CURRENT_STATE — status i odsyłacze.

## Test cases

- Każdy numer 0665–0678 jest unikalnym nowym plikiem; tabela planu ma 14
  wierszy przypisań i zgodne modele/reasoning.
- D-446 pozostaje decyzją „Przybliżona wygrana”; stare pliki siatek są
  zablokowane i kierują do D-447 oraz nowego planu.
- Wszystkie linki względne planu i indeksu prowadzą do istniejących plików.

## Verification

Z katalogu repo; cały job ma limit 120 s.

```powershell
$job = Start-Job -ScriptBlock {
  Set-Location 'C:\Users\tuszy\Documents\game_predicotr'
  git diff --check
  if ($LASTEXITCODE -ne 0) { throw 'git diff --check failed' }
  rg -n 'D-446|D-447|status: (accepted|superseded|blocked)' ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md ai_docs/delivery/GRID_ENGINE_V3_NEURAL_EXECUTION_PLAN.md ai_docs/process/DECISION_LOG.md
  if ($LASTEXITCODE -ne 0) { throw 'rg failed' }
  git status --short
}
if (-not (Wait-Job $job -Timeout 120)) { Stop-Job $job; throw 'documentation check timeout' }
Receive-Job $job
if ($job.State -ne 'Completed') { throw "documentation check $($job.State)" }
```

Warunek zaliczenia: brak błędów formatowania, kompletne numery, spójne linki
i niezależny audyt bez otwartych P0–P2. Testy dokumentacji są wykonywane w
P00; implementacyjne testy T01–T13 są planowane, niezaliczone.

## Risks / open questions

- Liczności danych, wybór gry niewidzianej i rzeczywisty koszt anotacji
  wymagają manifestu oraz STOP A/T03.
- Pakiety CUDA, GPU i porty będą zweryfikowane w odpowiednich etapach.

## Outcome

### Changed

- Zapisano plan, 13 kolejnych tasków, decyzję D-447, wymagania,
  architekturę i spójne instrukcje pracy etapowej. Stary plan/taski oznaczono
  jako zastąpione lub zablokowane.

### Verification results

- `git diff --check` bez błędów; 14 linków planu do tasków istnieje;
  TASK-0666–0678 mają komplet sekcji i limit 120 s w komendach testowych.
- Niezależny audyt `gpt-6-astra`, reasoning `medium`: re-review PASS,
  wszystkie zgłoszone P2/P3 poprawione, brak otwartych P0–P2.

### Not completed

- T01–T13, instalacja, trening i praca na danych użytkownika.

### Documentation updates

- README, traceability, CURRENT_STATE, DECISION_LOG, AGENTS/CLAUDE/
  PLAN_STANDARD oraz dokumenty wizji.

### Recommended next task

- Po jawnym poleceniu etapu A: TASK-0666, następnie TASK-0667.
