---
title: TASK-1003 — Podgląd i raport ponownego rozpoznania
status: todo
last_updated: 2026-10-14
---

# TASK-1003 — Podgląd i raport ponownego rozpoznania

## Status

`todo`

## Goal

Operator rozumie zakres, koszt i wynik przebiegu.

## Context

Task jest częścią zaakceptowanej rewizji 6. Podgląd zakresu i raport operacji. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0999, TASK-1013.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `medium`. gotowy kontrakt backendu.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [ADMIN_APP](../requirements/ADMIN_APP.md).
- Zakres odczytu uzupełniający z planu: ADMIN_APP, D-541, zakresy z sekcji 2.

- [D-541](../process/decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Oddzielne liczby zdjęć, slotów, plansz i komórek; domyślny zakres, pilot do 100, jawny szeroki wybór, postęp i wznowienie.
- Raport rozróżnia propozycje, automatyczne zapisy, ochronę, brak zmiany i konflikty.

## Out of scope

- Frontend nie wylicza samodzielnie kwalifikacji ani zakresu na podstawie jednego licznika.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Stary preview daje konflikt; utrata odpowiedzi odtwarza tę samą operację; zmiana gry nie miesza stanu; wszystkie automatyczne nie są domyślnie zaznaczone.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Oddzielne liczby zdjęć, slotów, plansz i komórek; domyślny zakres, pilot do 100, jawny szeroki wybór, postęp i wznowienie. Raport rozróżnia propozycje, automatyczne zapisy, ochronę, brak zmiany i konflikty.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Pozostały zakres wskazany w zaakceptowanym planie: nowe proponowane `grid-reinference-preview.tsx`, `grid-reinference-report.tsx`, stan i akcje w Adminie; istniejące linki do jobów.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `apps/admin/src/features/model-quality/grid_reinference_preview_and_report.test.ts`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Stary preview daje konflikt; utrata odpowiedzi odtwarza tę samą operację; zmiana gry nie miesza stanu; wszystkie automatyczne nie są domyślnie zaznaczone.

## Verification

Zakres: ADMIN, test transportu, DOC.

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

- Frontend nie wylicza samodzielnie kwalifikacji ani zakresu na podstawie jednego licznika.

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

- Nie rozpoczęto. Docelowy zapis wyniku: podglądy i raport dla aktualnej bazy oraz przykłady błędów.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1002
