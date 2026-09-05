---
title: Fix selected crop directory discovery
status: done
last_updated: 2026-09-06
---

# TASK-0477 — Naprawa wykrywania katalogów przycinania

## Goal

Runner katalogowy ma deterministycznie odnajdywać źródła zaczynające się od
numeru, pomijać katalogi `cut`, pliki i symlinki oraz uruchamiać wskazany zakres
indeksów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Cause

Wyrażenie regularne w literałach JavaScript zawierało podwójnie zapisane
backslashe. Dopasowywało dosłowne `\s` i `\d`, dlatego rzeczywiste katalogi
numeryczne dawały pustą listę i `CROP_RUN_RANGE_INCOMPLETE`.

## Definition of Done

- [x] Nazwy rozpoczynające się od numeru są rozpoznawane.
- [x] Wyniki `cut`, pliki, symlinki i nazwy nienumeryczne są pomijane.
- [x] Kolejność jest numeryczna i deterministyczna.
- [x] Regresja ma test jednostkowy.

## Outcome

Wydzielono czystą funkcję porządkującą katalogi, podłączono ją do runnera i
dodano test zgłoszonego przypadku. Kolejka 5–14 została uruchomiona dopiero po
ukończeniu katalogu nr 4.
