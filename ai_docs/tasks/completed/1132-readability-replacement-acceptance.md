---
title: Odbiór detektora i wymiany źródeł
status: done
last_updated: 2026-11-03
---

# TASK-1132 — Odbiór detektora i wymiany źródeł

## Status

`done`

## Goal

Rozliczyć punktowo dowody A1–C2, rzeczywiste buildy zmienionych pakietów i nierozstrzygniętą grupę APK oraz przygotować instrukcję odbioru operatora.

## Dependencies / entry conditions

TASK-1124–1131 done. Czysty HEAD07956943, gałąź codex/777a2-readability-replacement, testowana baza main40581449. Cały plan, koszt, delegowanie i audyty zatwierdzone. Nowszy mainfa38a3cd pozostaje do preflight integracji, bez merge w D1.

## Recommended execution

gpt-6.1-sol / medium; review claude-opus-5-5 / medium. Jeden audyt końcowy, tylko do odczytu. P0/P1 blokują commit.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/CODE_MAP.md` i `CODE_MAP_SYMBOLS.md`
- `ai_docs/tasks/completed/1124-readability-detector-core.md`
- `ai_docs/tasks/completed/1125-readability-durable-review.md`
- `ai_docs/tasks/completed/1126-shift-range-selection.md`
- `ai_docs/tasks/completed/1127-source-replacement-manifest.md`
- `ai_docs/tasks/completed/1128-source-replacement-ownership.md`
- `ai_docs/tasks/completed/1129-source-replacement-retirement.md`
- `ai_docs/tasks/completed/1130-source-replacement-repair.md`
- `ai_docs/tasks/completed/1131-source-replacement-import.md`
- `ai_docs/quality/TASK-1131_AUDIT_claude-opus-5-5.md`

## Scope

Istniejące dowody i DoD, aktualność kontraktu/dokumentacji/mapy, build klienta/core/Admina/Selektora, dokładnie jedna powtórka grupy APK z Outcome1129 bez deselection. Raport, instrukcja, audyt i zamknięcie taska.

## Out of scope

Nowe harnessy, warianty zdjęć, eksperymenty, szerokie powtarzanie zielonych testów, dane operatora, usługi, produkcyjne migracje, pilot, fit, scan, aktywacja, merge/push.

## Acceptance criteria

- [x] Raport mapuje wszystkie punkty D1 i DoD na istniejące dowody lub jawne ograniczenie.
- [x] Rzeczywiste buildy używają kodu worktree; kontrola kontraktu/docs/mapy rozliczona.
- [x] Dokładna grupa APK wykonana bez deselection; wynik i ewentualna ograniczona diagnoza zapisane.
- [x] Instrukcja oddziela implementację od operacyjnego odbioru/pilota i zgód operatora.
- [x] Audyt Opus5.5/medium, task-close, commit oraz record-hash.

## Technical notes

Root node_modules jest junction do main. Tymczasowe wyłącznie lokalne linki pakietów muszą kierować do worktree; przed utworzeniem sprawdzamy brak, po użyciu exact target i usuwamy sam junction bez rekurencji. To przygotowanie builda, nie zmiana zależności produktu. Brak nowych decyzji produktowych. Baza40581449 pozostaje testowaną bazą; aktualizacja main należy do późniejszego merge preflight.

## Expected files

Nowe: ten task oraz `ai_docs/quality/777A2_READABILITY_REPLACEMENT_ACCEPTANCE_20261103.md`, raport audytu. Istniejące: plan, CURRENT_STATE, DOC_INDEX; archiwum stanu przez task-close. Bez zmian kodu aplikacji.

## Test cases

Ponowne wykorzystanie świeżych wyników A1–C2. D1 uruchamia tylko wskazaną grupę APK, checks kontraktu/docs/mapy i buildy.

## Verification

Cwd worktree, root Python D:/game_predicotr/.venv/Scripts/python.exe. Jawne limity120s dla kontroli/APK, znany build Admina300s, audyt480s/internal i600s/external. Bez API/Admin/worker start/stop/restart. Wyniki w Outcome i raporcie.

## Risks / open questions

Brak fizycznego Chrome/FSA i Androida oraz etykiet pilota. A1 końcowy mypy partial pozostaje jawny. C2 P2 rozliczone przez koordynatora; bez rozszerzenia tego taska.

## Outcome

Commit: v1.7.533 / `675f0135f3bb74d8eeebf7b7912e2913a1fab43c`.

### Changed

Raport `ai_docs/quality/777A2_READABILITY_REPLACEMENT_ACCEPTANCE_20261103.md` mapuje każdy punkt D1 i DoD na dowody A1–C2 oraz instrukcję operatora. D1 nie zmienia kodu produktu i nie dodaje scenariuszy.

### Verification results

- Rzeczywisty klient/core build PASS4,45s/1,77s; board-search-ui typecheck PASS3,44s; Selector build PASS0,55s; Admin domyślny Turbopack build PASS22,44s z pełnym TypeScript i statycznymi stronami. Fresh-process resolver wskazał pakiety worktree. Własne lokalne junctions usunięto w finally, resolver po sprzątaniu wrócił do main.
- Dokładna grupa APK wskazana w Outcome1129 bez deselection: 47 PASS23,81s (wall26,80s). Obecny przebieg nie odtworzył DID NOT RAISE; historyczna przyczyna nierozstrzygnięta. Pierwsza ograniczona próba TestClient bez postępu przerwana88,88s; własne dwa procesy pytest zakończone i sprawdzone przed jednym wznowieniem z dostępem sieciowym. Bez równoległej kopii.
- Aktualne OpenAPI/generated/map PASS; cztery identyczne checkery docs:check przez root Python PASS. Brak własnej .venv w worktree wymaga rozwinięcia wrappera, bez pominięcia kontroli. Logi D:/game_predicotr/artifacts/t1132/.
- Świeżych zielonych testów A1–C2 nie powtarzano. Ich lint/scoped typy i testy są punktowo przywołane w raporcie. Końcowy mypy A1 pozostaje partial, bez deklaracji PASS.
- Audyt końcowy Opus5.5/medium R1 PASS, actual modelUsage claude-opus-5-5, exit0. Raport ai_docs/quality/TASK-1132_AUDIT_claude-opus-5-5.md; bez otwartych P0/P1. Task zamknięty przez task-close; commit i record-hash według procedury.

### Not completed

Bez fizycznego Chrome/FSA/Androida, operatorowego odbioru, etykiet, pilota/fit/scan, aktywacji, usług, migracji operatora, operacji danych, merge/push. Skuteczność detektora niezmierzona. C2 P2 rozliczone i nieruszane. Nowszy mainfa38a3cd pozostaje do integracyjnego preflight; testowana baza40581449.

### Documentation updates

Raport odbioru, plan, DOC_INDEX, CURRENT_STATE; task-close prowadzi archiwum i zamknięcie. Punktowe porównanie planu/DoD w raporcie. Implementacja narzędzi ukończona z jawnymi ograniczeniami odbioru ręcznego i typowania A1.

### Recommended next task

Odbiór operatora i osobna decyzja o integracji; następnie osobno uzgadniane wdrożenie/migracja/restart oraz pilot. Bez automatycznej operacji.
