---
title: TASK-0131 Android release workspace for the controlled test game
status: done
last_updated: 2026-08-01
---

# TASK-0131 — Android release workspace for the controlled test game

## Status

`done`

## Goal

Uprościć przygotowanie testowego wydania Android 0.2 do jednej aktywnej gry i
jednego obserwowalnego workflow, bez eksponowania wielogrowej konfiguracji
odłożonej do wersji 0.3.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- wybrać dokładnie jedną aktywną grę testową,
- automatycznie wskazać jej najnowszy zgodny opublikowany dataset i reguły,
- jednym submittem utworzyć niezmienny draft i uruchomić kontrolowany build,
- zachować bezpieczne wznowienie draftu lub joba po częściowej awarii,
- pokazać przy wydaniu zwarty status i przejście do pełnego workspace'u `Joby`,
- zachować zwijaną historię, checksumy i pobieranie zweryfikowanego APK,
- nie usuwać wielogrowego kontraktu backendu potrzebnego w późniejszej wersji.

## Expected files

- `apps/admin/src/features/releases/`
- `apps/admin/src/features/catalog/catalog-workspace.tsx`
- `apps/admin/src/app/globals.css`
- testy stanu, akcji i kontraktu UI wydania,
- dokumentacja bieżącego stanu.

## Acceptance criteria

- [x] formularz nie pozwala wybrać więcej niż jednej gry,
- [x] źródła dataset/reguły są dobierane deterministycznie i pokazane read-only,
- [x] jedna akcja tworzy draft i od razu uruchamia build,
- [x] częściowa awaria zachowuje draft i pozwala ponowić właściwy etap,
- [x] historia jest zwijana, a gotowy APK nadal można pobrać,
- [x] ekran wydania prowadzi do pełnych szczegółów w `Joby`,
- [x] testy, lint, typecheck i build Admina przechodzą.

## Outcome

Workspace `Wersje Android` wybiera teraz dokładnie jedną aktywną grę. Pierwsza
gotowa gra jest wybierana deterministycznie, zmiana selecta zawsze wyłącza
pozostałe gry, a najnowsza zgodna opublikowana para dataset/reguły jest pokazana
read-only. Walidator warstwy Admina odrzuca zero albo więcej niż jeden wybór;
wielogrowy kontrakt backendu pozostaje zachowany dla 0.3.

Przycisk `Utwórz i uruchom wydanie` wykonuje sekwencję create → build. Jeżeli
utworzenie draftu się uda, a start builda nie, niezmienny draft zostaje w
historii i może być uruchomiony ponownie. Historia jest zwijana, download APK,
checksumy, ręczny refresh i retry pozostają dostępne. Karta joba pokazuje zwarty
status oraz prowadzi do osobnego workspace'u `Joby` po pełny postęp i
diagnostykę.

Weryfikacja: 117 testów Admina przeszło, w tym testy pojedynczego wyboru,
automatycznego źródła, kolejności create → build i zachowania draftu po awarii.
ESLint, TypeScript oraz produkcyjny build Next.js również przeszły.
