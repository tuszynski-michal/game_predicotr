---
title: TASK-1011 — Usunięcie zatwierdzonych pozostałości V1.1 z V3
status: todo
last_updated: 2026-10-14
---

# TASK-1011 — Usunięcie zatwierdzonych pozostałości V1.1 z V3

## Status

`todo`

## Goal

Ekrany V3 pokazują właściwy model i dostępne działania.

## Context

Task jest częścią zaakceptowanej rewizji 6. Ograniczone zmiany UI i regresja starej gry. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1004.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `medium`. ograniczona zmiana UI z regresją starej gry.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [ADMIN_APP](../requirements/ADMIN_APP.md).
- Zakres odczytu uzupełniający z planu: ADMIN_APP, APP_V3_FUNCTIONAL_INVENTORY, D-541/D-544.

- [D-541](../process/decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-544](../process/decisions/DECISION_LOG_2026.md#d-544--nowe-gry-777-importują-przez-v3-z-profilem-grid_profile_777_v2) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Usunąć klasyczny panel z F15, klasyczną gotowość z F16 i stare opcje tworzenia z F17.
- Dokładne stare wartości to `framed_full_page_v2` i `requires_clarification`.
- Zwykły formularz traci również wybór dwóch profili V3 na rzecz default.

## Out of scope

- Nie usuwać historycznych enumów z odczytu API ani backendu klasycznego.
- Inne pozostałości wpisać do listy decyzji operatora.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] V3 nie pokazuje klasycznych działań; pokazuje stan przypisanej wersji.
- [ ] Stara 777 nadal poprawnie odczytuje historyczne wartości i raporty.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Usunąć wyłącznie trzy zatwierdzone miejsca V3: montowanie klasycznego panelu w `ModelQualityWorkspace`, tekst klasycznej gotowości w `game-catalog.tsx` oraz stare opcje tworzenia w `game-catalog-state.ts`. Zwykły formularz nie przesyła `shapeGeometryConfiguration` ani wyboru dwóch profili V3; używa kontraktu TASK-1004 z neutralnym `neural_grid_v3`, ustawianym przez serwer. Przypięta wersja modelu ma odrębny assignment; zaawansowany wybór nie modyfikuje formatu.

Draft bez assignment pokazuje blokadę importu zamiast klasycznej gotowości. Istniejąca stara 777 nadal odczytuje i aktualizuje `framed_full_page_v2`, `requires_clarification` oraz pozostałe historyczne wartości; backend/enumy legacy nie są usuwane. Nowe klasyczne tworzenie jest zablokowane. Regresje kontraktu formularza i stanu UI obejmują oba typy gry, brak default, assignment oraz zmiany gry/reload. Przed startem zweryfikować symbole i konkretne komunikaty istniejących kontraktów; inne pozostałości zgłosić jako pytanie operatora, bez samodzielnego rozszerzania usuwania. Bootstrap nie zmienia komponentów.

## Expected files

- Istniejące: [model-quality-workspace.tsx](../../apps/admin/src/features/model-quality/model-quality-workspace.tsx) — `ModelQualityWorkspace`, montowanie klasycznego panelu.
- Istniejące: [game-catalog.tsx](../../apps/admin/src/features/games/game-catalog.tsx) — komunikat klasycznej gotowości i formularz.
- Istniejące: [game-catalog-state.ts](../../apps/admin/src/features/games/game-catalog-state.ts) — `SHAPE_GEOMETRY_CONFIGURATION_LABELS`.
- Pozostały zakres wskazany w zaakceptowanym planie: testy `model-quality-workspace-contract`, `game-catalog-state`, `game-catalog-contract`.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `apps/admin/src/features/model-quality/v3_classical_ui_removal.test.ts`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- V3 nie pokazuje klasycznych działań; pokazuje stan przypisanej wersji.
- Stara 777 nadal poprawnie odczytuje historyczne wartości i raporty.

## Verification

Zakres: ADMIN, DOC; odbiór obu rodzajów gry.

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

- Nie usuwać historycznych enumów z odczytu API ani backendu klasycznego.
- Inne pozostałości wpisać do listy decyzji operatora.

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

- Nie rozpoczęto. Docelowy zapis wyniku: trzy usunięte miejsca i lista pozostałych zależności poza zakresem.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- TASK-1015, rozliczenie P2-3 audytu: doprecyzowano projektowany neutralny format V3, oddzielny assignment oraz ochronę dawnych wartości; kontrakt nie jest jeszcze zaimplementowany.
- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-0999
