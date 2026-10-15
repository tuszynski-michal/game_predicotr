---
title: TASK-1000 — Pełna sekcja „Geometria V3”
status: todo
last_updated: 2026-10-14
---

# TASK-1000 — Pełna sekcja „Geometria V3”

## Status

`todo`

## Goal

Udostępnić cały proces z poziomu gry.

## Context

Task jest częścią zaakceptowanej rewizji 6. Integracja gotowych funkcji panelu. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0995, TASK-0997, TASK-0998, TASK-1003, TASK-1011; bez zależności od pozytywnego wyniku TASK-1006.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `medium`. integracja gotowych kontraktów.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- [Audyt TASK-1011](../quality/TASK-1011_AUDIT_claude-fable-5-1.md), P2-4: przed odbiorem całego planu zastąpić techniczne reasonCode/eligibilityReasonCode zrozumiałymi etykietami i fallbackiem w pełnym panelu/shared summary. Zachować odrębność dostępności i aktualności dowodu; kod nie jest samodzielną oceną jakości.

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [ADMIN_APP](../requirements/ADMIN_APP.md).
- Zakres odczytu uzupełniający z planu: ADMIN_APP, APP_V3_FUNCTIONAL_INVENTORY, D-527/D-541.

- [D-527](../process/decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-541](../process/decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Diagnostyka, próbka, korekty, dane, run, porównanie, wersje i ponowne rozpoznanie.
- Backend określa dostępność działań.
- Brak danych pokazuje konkretne wymagania.

## Out of scope

- Bez połączenia treningu symboli z geometrią i bez przebudowy archiwalnej 777.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Proces działa bez skryptów operatora.
- [ ] Wejście na ekran nie uruchamia joba.
- [ ] Zmiana gry/reload zachowuje właściwy stan.
- [ ] Panel działa z dwiema bazami i odrzuconym wspólnym kandydatem.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Diagnostyka, próbka, korekty, dane, run, porównanie, wersje i ponowne rozpoznanie. Backend określa dostępność działań. Brak danych pokazuje konkretne wymagania.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [model-quality-workspace.tsx](../../apps/admin/src/features/model-quality/model-quality-workspace.tsx) — `ModelQualityWorkspace`, montowanie klasycznego panelu.
- Pozostały zakres wskazany w zaakceptowanym planie: istniejąca nawigacja; nowe proponowane `grid-model-workspace.tsx`, `grid-model-state.ts`, `grid-model-client.ts`; wcześniejsze panele.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `apps/admin/src/features/model-quality/v3_grid_model_workspace.test.ts`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Proces działa bez skryptów operatora.
- Wejście na ekran nie uruchamia joba.
- Zmiana gry/reload zachowuje właściwy stan.
- Panel działa z dwiema bazami i odrzuconym wspólnym kandydatem.

## Verification

Zakres: ADMIN, testy transportu i interakcji, DOC.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez połączenia treningu symboli z geometrią i bez przebudowy archiwalnej 777.

## Outcome

### Execution phase

- Nie rozpoczęto.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit: wymagany `claude-fable-5-1`, reasoning `medium`; raport jeszcze nie istnieje, otwarte uwagi jeszcze nie ustalone.
- Następny krok: sprawdzić warunki wejściowe i ponownie odczytać task oraz odpowiadający fragment planu.

### Changed

- Nie rozpoczęto. Docelowy zapis wyniku: ścieżki operatora i jawne stany blokujące.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1001
