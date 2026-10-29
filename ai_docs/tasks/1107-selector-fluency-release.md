---
title: Dowody płynności, diagnostyka i sprawdzona paczka
status: in_progress
last_updated: 2026-10-29
---

# TASK-1107 — Dowody płynności, diagnostyka i sprawdzona paczka

## Status

`in_progress`

## Goal

Udokumentować płynność i brak zgubionych wyborów w rzeczywistym Electronie oraz dostarczyć sprawdzony ZIP Windows 1.0.4.

## Dependencies / entry conditions

TASK-1104–1106 done; HEAD b17e0e2e, v1.7.501. Operator zatwierdził cały plan, koszt 3–5 h, testy i ZIP, bez merge/push. Audyty Claude pominięte decyzją operatora. Historia wydań i package.json kończą się na 1.0.3.

## Recommended execution

`gpt-6.1-sol`, `medium`; odbiór, diagnostyka i istniejący proces wydania. Przekroczenie celu p95 wymaga analizy śladu i decyzji operatora.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/delivery/SELECTOR_FLUENCY_RELIABILITY_PLAN_20261029.md`
- `ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md`
- `ai_docs/quality/SELECTOR_OUTPUT_FOLDER_1_0_3_20261023.md`
- `ai_docs/tasks/completed/1105-selector-workspace-updates.md` — znany baseline native-checks.
- `ai_docs/tasks/completed/1106-selector-preview-cache.md` — metody smoke/race.

## Scope

Ograniczone agregaty diagnostyczne bez danych zdjęć; minimum 30 nawigacji i 10 wyborów na małej partii kopii istniejących JPEG. Czasy wejście–paint/decode/IPC/native/confirmation, żądania i payload. Flaga release smoke --fluency, aktualizacja operatora, komplet testów selektora w grupach i wydanie Windows z SHA/metadata/asar.

## Out of scope

Usługi, zmiany oryginałów, formatów trwałych i ochrony Windows, naprawa workerów native, merge/push. Dwa wcześniejsze usunięcia artefaktów i obcy worktree pozostają poza commitem.

## Acceptance criteria

- [ ] Bounded agregaty; brak logu na każdy klawisz, ścieżek i wpływu diagnostyki na operację.
- [ ] Minimum 30 nawigacji i 10 wyborów, pełne próbki i kontekst maszyny; lokalny warm p95 ≤50 ms.
- [ ] Cache hit przed odpowiedzią IPC opóźnioną o 500 ms; zero zgubionych F i błędnych imageId/range.
- [ ] Nowy proces potwierdza JPEG/SHA/manifest/liczniki; crash, recovery, obie numeracje, skoki i granica 500000.
- [ ] Pełny zestaw selektora w grupach ≤120 s concurrency=1, lint/typecheck/build i finalny rozpakowany ZIP ze smoke.
- [ ] ZIP, SHA i release metadata zachowane w artifacts/selector-releases/1.0.4; stare wydania zachowane.
- [ ] Dokumentacja i DoD rozliczone; fizyczny reboot i odbiór na komputerze odbiorcy pending.

## Technical notes

Bezpieczne założenie: lokalne kopie niewielkiej partii istniejących JPEG są wyłącznie fixture odbiorczym, nie pomiarem sprzętu odbiorcy. Zimny cache aplikacji nie oznacza zimnego cache systemu operacyjnego. Agregacja ma stałe limity; zapis po serii/na żądanie lub close, bez fsync na klawisz. Brak pytań blokujących przed pomiarem. Trzy timeouty native-checks były potwierdzone na poprzednim HEAD; nie zmieniamy kryteriów testów.

## Expected files

Istniejące: native/diagnostic-log.ts, src/main.ts, scripts/smoke-fluency.mjs, scripts/smoke-release.mjs, package.json i package-lock.json, instrukcja operatora, mapa i stan. Proponowane: ograniczony moduł agregatów/test, skrypt odbiorczego pomiaru i raport jakości.

## Test cases

Plan TASK-1107: warm/cold, opóźnienie500 ms, 30/10, finalny ZIP, strzałki/F/Enter, kierunki i skoki1/20, granica500000, zły JPEG, konflikt, utrata odpowiedzi, nowy proces i upgrade1.0.3.

## Verification

Każde polecenie przez scripts/run-bounded.mjs; testy concurrency=1, grupy ≤120 s. Lint/typecheck/build ≤120 s, make ≤300 s po uprzedzeniu, każdy smoke ZIP ≤120 s. Wyniki dopisywane po wykonaniu.

## Risks / open questions

Brak fizycznego reboot Windows i dostępu do komputera odbiorcy. Nie ma gwarancji wydajności innego dysku/ochrony/CPU.

## Outcome

Wypełnia agent po pracy.
