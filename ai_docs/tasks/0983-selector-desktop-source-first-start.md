---
title: Source-first selector start and resume
status: in_progress
last_updated: 2026-10-12
---

# TASK-0983 — Start od zdjęć, etykieta gry i automatyczne wznowienie

## Status

`in_progress`

## Goal

Wybrać tylko folder zdjęć, zacząć nową partię lub wznowić istniejącą,
zachowując numerację i postęp w obu kierunkach.

## Context

Operator potwierdził foldery obok źródła, etykietę gry i dropdown historii.
Zgoda na dodatkowe1–2 h obejmuje kod, testy i nowy ZIP; brak wiarygodnego
szacunku tokenów. Obecny worktree czysty, HEADc32fa802 / v1.7.327.

## Dependencies / entry conditions

0980–0982 wykonane; fizyczny odbiór0979 nadal blocked. Numer0983 wolny
w worktree i głównym checkout. Pytania produktowe rozstrzygnięte.

## Recommended execution

`gpt-6.1-sol`, reasoning `medium`: typowany native flow i trwałe metadane.
Końcowy audyt operatora jak w D-545; nie tworzyć własnego niezależnego PASS.
Zmiana semantyki numeracji lub osłabienie granic wymaga zatrzymania.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-545)
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_START_PLAN_20261012.md`
- `ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md`

## Scope

- Source-first picker, etykieta gry, historia rozwijana, auto-resume.
- Zgodne opcjonalne metadane projektu, walidacja własności przed recovery.
- Regresje obu kierunków i realny UI po restarcie procesu; ZIP0.1.2.

## Out of scope

- Zmiana numeracji/kolejności zdjęć, formatów manifestu i granic plików.
- Chmura, API, podpis, odbiór odbiorcy, benchmarki i usługi głównej aplikacji.

## Acceptance criteria

- [x] Jedyny picker nowej partii wybiera zdjęcia; wynik/projekt powstają obok.
- [x] Gra jest etykietą historii, bez wpływu na nazwy folderów/seq_*.
- [x] Ponowny wybór źródła po nowym procesie wznawia kursora i konfigurację.
- [x] Dropdown wznawia zapisany projekt; stare projekty/cache są zgodne.
- [x] Oba kierunki, undo/skip/korekta zakresu i wznowienie zachowują semantykę.
- [x] Anulowanie, obce dane i niejednoznaczność nie resetują ani nadpisują.
- [ ] Kontrole jakości oraz realny smoke czystego ZIP zaliczone.

## Technical notes

Plan określa granice native, token, zgodność ProjectState1 i reakcje na
konflikt. Brak folderu nie jest zgodą na reset. Istniejący custom projekt
można dalej otworzyć; główny nowy przepływ nie pyta o dodatkowe foldery.

## Expected files

Istniejące: contracts.ts, preload.ts, main.ts, native/project-controller.ts,
project/types.ts, state-codec.ts, project-store.ts, recent-projects.ts,
renderer/App.tsx/style.css; scripts/smoke-* i manifest/lockfile wersji.
Nowe proponowane: test/start-resume.test.mjs, scripts/smoke-start.mjs.
Dokumentacja wymagań/architektury/guides/README/TRACEABILITY i mapa kodu.

## Test cases

Nowa partia Mumie/123 → sibling folders; etykieta pozostaje po restarcie.
Accept, skip, navigate, undo, range → ponowny wybór źródła w obu kierunkach
odtwarza ten sam stan i JPEG. Brak cache, stare metadata, zły token, obcy
folder, kilka projektów i obca tożsamość → bez ukrytych mutacji.

## Verification

Z root worktree, Windows PowerShell; jawne limity wrappera:

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 node --experimental-strip-types --test apps/selector-desktop/test/start-resume.test.mjs
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:project --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:ui --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:legacy --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run lint --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run typecheck --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run release --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:start --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run docs:check
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run code-map:check
```

Wyniki dopiero po wykonaniu; brak wide test loops/benchmarku.

## Risks / open questions

- Historia to pomocniczy cache10 pozycji; default sibling resume nie wymaga go.
- Więcej niż jeden projekt źródła wymaga jawnego wyboru.
- Pełne SHA open i niepodpisana paczka mają wcześniejsze ograniczenia.
- Audyt operatora i rzeczywisty odbiór0979 pozostają osobnymi bramkami.

## Outcome

### Changed

Source-first begin/create z opaque tokenem, gameName jako zgodne metadane
schema1, dropdown10 projektów oraz auto-resume z walidacją przed recovery.
Nie ma pickerów projektu/wyniku w głównym nowym przepływie. Stare custom
projekty/cache/manifesty są zgodne. Numeracja i naturalny porządek bez zmian.
Wersja programu0.1.2; źródła przygotowane do commita v1.7.328.


### Verification results

121 unikalnych testów PASS: start9, project48, UI4, legacy25,
legacy-recovery26, foundation7, release2. Typecheck PASS. Packaged start
PASS w obu kierunkach po nowym procesie; formularz/historia obejrzane na
screenshotach. Pierwszy smoke wymagał jednoznacznego aria-label kierunku;
uzupełniono UI. Test wstrzykniętej awarii poprawiono do rzeczywistego
kontraktu WRITE_FAILED, z asercją osiągnięcia fazy prepare:after.
Końcowy lint/typecheck, format i docs:check PASS; mapy zregenerowane.
Czysty ZIP i jego realne smoke testy pending.


### Not completed

Finalny ZIP z czystego commita w kolejnym kroku. Nie wykonano niezależnego
audytu zamiast operatora, odbioru na jego komputerze/rebootu ani podpisu.
Brak danych użytkownika, usług, push/merge i benchmarków.


### Documentation updates

Plan/start task, wymagania, architektura, D-545 (obie kopie), README,
TRACEABILITY, instrukcja operatora i CURRENT_STATE. Mapa do regeneracji.


### Recommended next task

Końcowy audyt operatora i odbiór0979.
