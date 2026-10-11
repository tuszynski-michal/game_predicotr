---
title: Odroczone przejęcie starej sesji
status: todo
last_updated: 2026-10-11
---

# TASK-0978 — Odroczone przejęcie starej sesji

## Status

`todo`

## Goal

Utworzyć projekt desktopowy z dowodowo zgodnej sesji operator-local v1/v2 bez modyfikowania oryginału.

## Context

Obecny operator-local Reviewer zależy od dostępu do strony przez host i tunel.
Nowy selektor działa lokalnie; zdjęcia i wyniki pozostają u odbiorcy. Proton
Drive jest obsługiwany poza aplikacją. Task realizuje wyłącznie odpowiedni
fragment zaakceptowanego planu.

## Dependencies / entry conditions

ODROCZONE. TASK-0979 zakończony i osobne polecenie operatora. Dostępny claude-sonnet-5-5 / medium. Nie należy do zatwierdzonego pierwszego wydania.

## Recommended execution

`gpt-6.1-sol / high`. Niezależny statyczny audyt
`claude-sonnet-5-5 / medium`, warunkowo po potwierdzeniu CLI i modelu.
Konfiguracja odpowiada tabeli planu. Eskaluj, gdy zmiana wymaga innego modelu
własności danych, nowych reguł domeny lub niezgodnego formatu. Nie zmieniaj
modelu/reasoning niejawnie. Jeden audyt i jedna runda poprawek według AGENTS.md.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md — D-545
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_EXECUTION_PLAN.md — TASK-0978
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md — obowiązująca sekcja operator-local
- ai_docs/architecture/CODE_MAP.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md

## Scope

- Read-only odczyt manifestów operator_local v1/v2, preview i jawne utworzenie nowego projektu.
- Walidacja tożsamości źródła, powiązań ordinal/path, JPEG-ów i checksum.
- Zachowanie numeracji, decyzji, natural_v2/legacy cursor semantics i końcowej granicy.
- Brak automatycznego złagodzenia zgodności po różnej checksumie metadanych.

## Out of scope

Zmiana oryginalnej sesji, odczyt cudzego IndexedDB, core-items manifest, import zmienionego źródła na podstawie domysłu o mtime.

## Acceptance criteria

- [ ] Zgodny komplet source/output odtwarza ten sam postęp; oryginał jest nietknięty.
- [ ] Nieznany format, brak checksum/dowodów, zmieniona lista i różne JPEG checksums blokują.
- [ ] Manifest core-items nie jest traktowany jako operator_local.
- [ ] Nie można uznać dowolnej różnicy checksummy za zmianę wyłącznie dat plików.

## Technical notes

buildRemoteSourceManifestV1 zawiera sizeBytes i lastModifiedMs. Sam historyczny output przechowuje checksum, nie kompletny porównywalny source inventory. Jeśli nie można dowieść zgodności, nie rekonstruuj utraconych informacji z aktualnego folderu jako faktów historycznych. Rozszerzenie migracji skopiowanego źródła ze zmienionymi mtime wymaga oddzielnego planu dowodów.

## Expected files

- Nowe, proponowane: apps/selector-desktop/src/legacy-adoption/ i test/legacy*.test.mjs.
- Istniejące tylko do odczytu: OperatorLocalOutputManifestV1/V2, resumeOperatorLocalBatch, buildRemoteSourceManifestV1.
- Dokumentacja procesu migracji i task Outcome.

## Test cases

- v1/v2, rosnący/malejący, legacy bez natural_v2, końcowy zakres.
- Obcy core-items, brak source fingerprint, missingseq, changedJPEG, różne mtime.
- Anulowane preview i błędny import pozostawiają oryginalne pliki identyczne.

## Verification

Z katalogu worktree selektora. Każda skończona komenda ma timeout do 120 s;
znany dłuższy build tylko po uprzedniej informacji i osobnym limicie.

```powershell
npm run test --workspace @game-predictor/manual-image-selection-core
npm run typecheck --workspace @game-predictor/manual-image-selection-core
npm run test --workspace @game-predictor/reviewer
npm run docs:check
npm run code-map:check
```

Powyższe skrypty istnieją w repo. W nowym worktree wymagają dostępnych
zależności oraz interpreterów; przygotowanie środowiska nie uprawnia do
restartu usług ani migracji. TASK-0975 ma dodać test/lint/typecheck/build/
package/make aplikacji desktopowej, a następnie zapisać sprawdzone komendy
i wyniki w Outcome. Te skrypty są teraz proponowane, nie wykonane.
Testy Reviewera sprawdzają zgodność kontraktu; nie zastępują odbioru Electrona.
Po zmianie modułów/symboli zregenerować mapę, potem sprawdzić code-map:check.

## Risks / open questions

Nie ma zgody na wykonanie tego taska w bieżącym zleceniu. Historyczny manifest może nie zawierać wystarczających dowodów.

## Outcome

### Changed

Przygotowano specyfikację taska i zaakceptowany plan. Implementacja nie została rozpoczęta.

### Verification results

Kontrole przygotowanej dokumentacji: check_decision_links.py PASS (542 odnośniki/wpisy/wiersze indeksu), check_current_state_window.py PASS (47 aktywnych tasków, 10 done). Testów implementacji nie uruchamiano.

### Not completed

Wszystkie kryteria implementacyjne i wymagany audyt.

### Documentation updates

Task, plan, D-545 i wpisy źródeł prawdy opisują zaakceptowany zamiar.

### Recommended next task

Po osobnym odbiorze zatrzymać zakres.
