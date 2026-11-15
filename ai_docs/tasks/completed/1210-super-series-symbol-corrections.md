---
title: Korekta symboli bezpośrednio z modala supergry
status: done
last_updated: 2026-11-15
---

# TASK-1210 — Korekta symboli z modala supergry

## Status

`done`

## Goal

Odbiorca udostępnionej wyszukiwarki otwiera istniejący edytor symboli bezpośrednio z widoku wyboru super symbolu.

## Context

Obecnie korekta wymaga otwarcia planszy z liniami i osobnego włączenia trybu poprawiania. Użytkownik zlecił skrócenie tej ścieżki i build Reviewera; działający link zatrzymuje ręcznie w Adminie.

## Dependencies / entry conditions

Istniejący publiczny port korekty i wspólny modal planszy pozostają źródłem zapisu. Bez zmian API i schematu. Bezpieczne założenie: przycisk „Popraw symbole” otwiera ten sam edytor od razu w trybie edycji; podgląd linii nadal zaczyna w trybie odczytu.

## Recommended execution

Wykonanie w bieżącej sesji, bez delegowania. Rekomendacja warunkowa: gpt-6.1-sol / medium (konfiguracja dostępna w katalogu środowiska; tożsamość bieżącego wykonawcy nie jest ujawniona). Eskalacja przy potrzebie zmiany API lub trwałości korekt. Niezależny audyt nie jest wymagany dla dodania wejścia do istniejącego edytora.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — sekcja Supergry.
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — zapis przez udostępnioną wyszukiwarkę.
- `ai_docs/architecture/API_CONTRACT.md` — publiczna powierzchnia udostępniania.
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`

## Scope

- Bezpośredni przycisk poprawiania symboli bieżącej planszy w serii.
- Wykorzystanie `BoardSearchBoardLinesModal` z `startInEditMode`.
- Powrót fokusu, odświeżenie serii i wyników po korekcie; zachowanie dotychczasowego podglądu.
- Testy interakcji, lint, typecheck i izolowany build Reviewera.

## Out of scope

Zmiana API, migracje, zatrzymanie linku, restart usług, merge i push.

## Acceptance criteria

- [x] Z modala supergry można otworzyć korektę jednym przyciskiem i od razu wskazać pole.
- [x] Zapis używa istniejącego portu; zamknięcie edytora odświeża serię, zamknięcie serii odświeża wyniki.
- [x] Anulowanie wraca do przycisku korekty; skróty super symbolu są zablokowane podczas edycji.
- [x] Podgląd linii zachowuje poprzednie zachowanie; brak danych edycji nie udostępnia fałszywej akcji.
- [x] Kontrole zmienionych części i build mają zapisany wynik; usługi pozostają pod kontrolą operatora.

## Technical notes

Stan otwartego okna przechowuje numer planszy i tryb wejścia. Wspólna referencja wskazuje faktyczny przycisk otwierający. Edytor nadal sam pobiera aktualne rewizje pól i obsługuje konflikty oraz ponowienie utraconej odpowiedzi. Nie kopiujemy logiki korekt do panelu supergry.

## Expected files

- `packages/board-search-ui/src/super-game-series/super-game-series-panel.tsx` — `SuperGameSeriesPanel`, `SeriesBoardView`.
- `packages/board-search-ui/test-interactions/super-game-series-modal.test.mjs` — regresje bezpośredniego wejścia i podglądu.
- `ai_docs/requirements/ADMIN_APP.md` i dokumentacja stanu zadania.

## Test cases

Bezpośrednie wejście → aktywny edytor; zapis → świeże symbole i wyniki; Esc bez zapisu → powrót do przycisku; klient tylko do odczytu → brak przycisku; stary podgląd linii → tryb odczytu.

## Verification

Polecenia uruchamiane z katalogu repozytorium, timeout 120 s na test/lint/typecheck; build osobno z jawnym limitem po uprzedzeniu.

## Risks / open questions

Główny checkout jest na main, a zapis metadanych Git i utworzenie osobnego checkoutu są zablokowane uprawnieniami środowiska. Próba narzędzia zarządzanego worktree również nie powiodła się. Nie modyfikować działającego `.next`; build wymaga osobnego katalogu.

## Outcome

Commit: v1.7.636 (hash dopisuje kolejny commit).

### Changed

- Panel serii pokazuje „Popraw symbole” przy bieżącej planszy, jeżeli klient i dane pozwalają na korektę. Istniejący edytor otwiera się z `startInEditMode=true`.
- Stan okna wiąże numer planszy i tryb wejścia. Anulowanie wraca do faktycznie użytego przycisku; stara akcja podglądu nadal otwiera tryb odczytu.
- Istniejący zapis korekty, odświeżenie serii i wyników, blokowanie skrótów i ochrona rewizji pozostają używane bez nowej implementacji. Nie zmieniono kontraktu ani danych.

### Verification results

- PASS: 3 nowe testy interakcji (bezpośrednia korekta i odświeżenie, Esc i zachowanie roboczego wyboru, klient bez zapisu).
- PASS: 14/14 testów `super-game-series-panel.test.mjs`; 5/5 testów `board-search-board-cell-correction.test.mjs`.
- Pełny plik modala: 10/11 PASS. Istniejący test integracji Admina zgłasza `Invalid hook call` w nietkniętym `apps/admin/src/features/board-search/board-search-workspace.tsx:61` z powodu oddzielnych kopii Reacta w Adminie i pakiecie. Powtórzenie oryginalnego pliku testu pobranego z HEAD daje ten sam błąd przed renderowaniem panelu serii. Test nie został osłabiony ani usunięty.
- PASS: Prettier dla obu zmienionych plików, scoped ESLint oraz `tsc --noEmit` pakietu `board-search-ui`.
- Mapy kodu zregenerowano skryptem. PASS: `npm run docs:check` (4 walidatory) oraz `git diff --check`; mapa nie wymagała zmian zawartości indeksu symboli.
- Build izolowany (`next build --webpack`, timeout 300 s) bez dotykania aktywnego `.next`: początkową ścieżkę wspólnego CSS w kopii skorygowano przez zachowanie struktury katalogów. Build pozostaje BLOCKED przez `EPERM` przy tworzeniu katalogów `.next/types/app/management` oraz `.next/server/app/manual-selection`; wyłączenie `webpackBuildWorker` w konfiguracji wyłącznie kopii nie usunęło blokady. Nie ma gotowej paczki produkcyjnej.
- Build produkcyjny Reviewera w głównym checkoutcie (TASK-1211, `BUILD_ID` 2026-11-15 21:08:45) powstał po ostatniej zmianie panelu serii (20:21:17), więc obejmuje ten task: PASS.
- Zamknięcie (Claude Code, 2026-11-15, poza sandboxem Codexa): ponownie 10/11 PASS pliku `super-game-series-modal.test.mjs`; jedyny błąd to ten sam zastany `Invalid hook call` Admina (`board-search-workspace.tsx:61`).

### Not completed

- Odbiór na działającym linku/fizycznym Androidzie.
- Nie uruchamiano ani nie zatrzymywano usług, nie odwołano linków, nie wykonano merge ani push. Audyt nie jest wymagany (kolumna `Dodatkowy review`: Nie).
- Blokada zapisu `.git` w sandboxie Codexa: commit i zamknięcie wykonał Claude Code na gałęzi roboczej `codex/super-series-grid-symbols`.

### Documentation updates

- `ADMIN_APP.md`: bezpośrednie wejście do edytora, warunki dostępności i zachowanie odświeżenia.
- `CURRENT_STATE.md`: wskaźnik taska i blokery.

### Recommended next task

Operator zatrzymuje udostępnienie w Adminie, a w swoim terminalu w `D:\game_predicotr` uruchamia `npm run reviewer:build`. Następnie uruchamia udostępnianie ponownie w Adminie (kontroler wykrywa zmianę BUILD_ID i obsługuje nieaktualny proces). Jeśli build lokalny również zgłosi EPERM, należy usunąć przyczynę uprawnień przed uruchomieniem linku. Oddzielnie potrzebne są uprawnienia Git do przeniesienia zmian na roboczą gałąź, commita i formalnego zamknięcia; merge/push wymagają wyraźnej zgody. Izolowana kopia builda w `artifacts/reviewer-build-task1210/` jest nieudanym artefaktem diagnostycznym, nie paczką do wdrożenia.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1210 | gpt-6.1-sol (rekomendacja warunkowa; wykonanie w bieżącej sesji) | medium | Mała zmiana wejścia do istniejącego edytora; bez zmiany kontraktu lub domeny. | Nie |
