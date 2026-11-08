---
title: Panel pełnych symboli, porównanie HTML i odbiór
status: todo
last_updated: 2026-11-08
---

# TASK-1168 — Panel pełnych symboli, porównanie HTML i odbiór

## Status

`todo`

## Goal

Operator widzi gotowość danych, propozycje i ocenę rzeczywistych15wycinków,
a odbiór potwierdza zgodność całego trwałego przepływu.

## Dependencies / entry conditions

T0–T4 zaimplementowane. Brak operator-labels lub audytu Opus jest widoczny,
nie udaje zaliczonego rzeczywistego treningu/oceny.

## Recommended execution

gpt-6.1-sol/high; dodatkowy review Claude Code claude-opus-5-5/high.

## Relevant docs

- AGENTS.md
- ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md (T5 i ograniczenia)
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/architecture/CODE_MAP.md

## Scope

Pełny pion kontraktu backend/OpenAPI/SDK/wrapper/requesttest; istniejący
panel uczenia i propozycji. Gotowość treningu vsautomatu, powodyzatrzymania,
wersjawejścia, zakresgier. HTML oryginał/realNNinput/baza/kandydat/15actualcrops.
Odróżnienie szerokiego podglądu od wejścia sieci. Testy odbioru planu i
instrukcje zgodności API/worker/migracji/rollback, bez wdrożenia operatora.

## Acceptance criteria

- [ ] Czytelne stany loading/empty/error i rozdział propozycja/człowiek/automat.
- [ ] Braki danych i zakres dowodu nie udają jakości nowych gier.
- [ ] HTML pokazuje rzeczywiste wycinki i to, co analizowała sieć.
- [ ] Żadna operacja propozycji nie zatwierdza geometrii/symboli człowieka.
- [ ] Testy realONNX/24vs15/rząd/wrongcell/neighbor/perspective/occlusion/bounds.
- [ ] Partial/unknown/stalereport/restart/lostresponse/budget są spójne.
- [ ] API/worker/PG/UI/lint/types/build/docs/map wykonane z uczciwym raportem.
- [ ] Wszystkie taski mają Outcome/audyt/commit/close albo jawny blocker,
  bez merge/push/migracji/operatortraining/importu.

## Expected files

apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx
i state/CSS; schemas/grid_correction_learning.py oraz istniejący endpoint,
packages wygenerowanego SDK/wrappera, generator HTML i testy interakcji.

Potwierdzone odczytem przed implementacją: scripts/render_grid_correction_comparison.py
(`render`, `main`), scripts/templates/grid-correction-comparison.html,
scripts/tests/test_grid_correction_comparison.py,
scripts/tests/test_grid_comparison_diagnostics.py,
scripts/tests/verify_grid_correction_comparison.mjs;
apps/admin/test-interactions/grid-correction-learning-panel.test.mjs,
apps/admin/test/grid-correction-learning-state.test.mjs;
packages/admin-api-client/src/index.ts i apps/admin/src/api/admin-api-client.ts.

## Technical notes

Istniejący generator sprawdza tożsamość run/game/version/sourceSHA i renderuje
zapisane wyniki, bez inferencji i domenowych zapisów. Reuse tych kontroli.
Obecna reguła `paired` opiera się na dziewięciu detekcjach i indeksie pozycji;
nowy raport nie może uznać samej liczby9 za dowód jednoznacznego przypisania.
Użyć wersjonowanego dopasowania T3; przy braku dowodu pokazać całość i brak
powiązania. Piętnaście rastrów pochodzi z produkcyjnego renderer/snapshotu,
nie z browserowego viewportu. Stopka może deklarować CPU/oryginalne piksele
tylko przy zapisanym dowodzie; brak metadanych pozostaje jawny.

## Test cases

Potwierdzony sukces vsunqualified, braki i nieaktualność, retry-refresh/loading,
geometryproposals preserving approval, rzeczywiste15rastrów i snapshotsettings,
wersje historyczne oraz cały flow po nowym procesie.

## Verification

Testy zmienionego pionu, PG, ONNX, Admin/Reviewer interakcje, lint/types/build,
OpenAPI/SDK/docs/map. Znane buildy kontrolowane, timeouty i brak osieroconych
procesów. Wyniki quality/TASK-1168_VERIFICATION.md.

## Outcome

Nie rozpoczęto.
