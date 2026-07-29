---
title: Keyboard-first review and safe confirmation
status: done
last_updated: 2026-07-29
completed_at: 2026-07-29
---

# TASK-0108 — Keyboard-first review and safe confirmation

## Status

`done`

## Goal

Umożliwić operatorowi wybranie i poprawienie symboli oraz bezpieczne,
idempotentne zatwierdzenie całej planszy bez użycia myszy.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_06_5_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- wybierać komórkę kliknięciem oraz jawnie pokazywać jej bieżący symbol,
- mapować aktywny katalog symboli na `1`–`9`, `0`, następnie klawisze QWERTY,
- pokazać dostępną legendę rzeczywistego mapowania wybranej gry,
- pozwolić zmienić wybraną komórkę skrótem lub jedną z maksymalnie czterech
  uporządkowanych sugestii,
- nawigować strzałkami lewo/prawo między planszami,
- blokować skróty podczas pisania, innego dialogu oraz zapisu,
- pierwszym `Enter` otwierać potwierdzenie całej planszy, drugim wykonać
  dokładnie jeden zapis; `Escape` zamyka potwierdzenie,
- wysyłać pełne 15 komórek, zaakceptowany numer sekwencji, geometry revision,
  expected resolution revision i UUID idempotencji przez klienta TASK-0106,
- odróżniać accepted od corrected na podstawie faktycznej zmiany względem
  predykcji oraz obsłużyć konflikt rewizji kontrolowanym stanem,
- zachować możliwość ponownej edycji plansz completed,
- dodać testy czystych reguł, akcji zapisu i kontraktu klawiatury/UI.

## Out of scope

- odrzucanie planszy i podawanie powodu,
- edycja narożników, geometrii i ponowne cropy — TASK-0109,
- zamrożenie kohorty i retraining — TASK-0110,
- ręczne testy ekranu — odbiór po TASK-0111,
- hosting i dostęp zdalny — M8.7.

## Acceptance criteria

- [x] kliknięcie komórki oraz skrót symbolu zmieniają dokładnie jedną widoczną
  komórkę,
- [x] legenda używa stabilnej kolejności aktywnego katalogu gry,
- [x] tooltip pokazuje 3–4 sugestie wybranej komórki i pozwala je zastosować,
- [x] strzałki nie przechwytują pól formularza i przechodzą bounded cursorami,
- [x] pojedyncze lub przytrzymane `Enter` nie zapisuje decyzji,
- [x] drugi świadomy `Enter` tworzy najwyżej jedną rewizję z jednym
  idempotency key,
- [x] `Escape` anuluje potwierdzenie bez zapisu,
- [x] accepted/corrected zapisuje pełny kontrakt całej planszy, a completed
  pozostaje edytowalne,
- [x] stale revision ma kontrolowany komunikat i możliwość ponownego odczytu,
- [x] nowe zachowanie ma testy automatyczne oraz przechodzi lint, typecheck,
  formatowanie i build.

## Expected files

- `apps/admin/src/features/operational-reviews/operational-review-actions.ts`
- `apps/admin/src/features/operational-reviews/operational-review-state.ts`
- `apps/admin/src/features/operational-reviews/operational-review-workspace.tsx`
- `apps/admin/src/app/globals.css`
- `apps/admin/test/operational-review-*.test.mjs`
- dokumentacja procesu.

## Assumptions

- accepted oznacza brak zmiany numeru i wszystkich symboli względem predykcji;
  każda jawna zmiana używa corrected,
- ponowny zapis completed bez żadnej zmiany bieżącej rewizji jest blokowany, aby
  nie tworzyć pustej rewizji audytu,
- przy otwartym potwierdzeniu wszystkie skróty poza `Enter` i `Escape` są
  wyłączone,
- każde nowe otwarcie potwierdzenia otrzymuje nowy UUID, a retry tego samego
  zapisu zachowuje jego UUID,
- każda potencjalnie ciężka komenda ma timeout nie większy niż 120 sekund.

## Outcome

Panel pobiera aktywny katalog symboli i tworzy stabilne mapowanie `1`–`9`, `0`,
następnie QWERTY. Kliknięcie wybiera jedną komórkę, a skrót lub jedna z
maksymalnie czterech sugestii zmienia tylko jej draft. Bieżące korekty są
widoczne na siatce przed zapisem, a plansze completed wymagają realnej zmiany,
zanim powstanie kolejna rewizja.

Czysta maszyna stanów klawiatury rozróżnia nawigację, zmianę symbolu, otwarcie,
anulowanie i wysłanie potwierdzenia. Pomija input/select/textarea,
`contentEditable`, inny otwarty dialog, key repeat i trwający zapis. Pierwszy
`Enter` tylko otwiera dialog; drugi uruchamia atomowy zapis całych 15 komórek.
Synchroniczna blokada mutacji i UUID idempotencji chronią także przed dwoma
eventami albo aktywacją przycisku w tym samym czasie.

Zapis wysyła accepted dla niezmienionej predykcji albo corrected po zmianie
numeru/symbolu, wraz z current crop IDs, geometry revision i expected resolution
revision. Konflikt rewizji ma kontrolowany komunikat i akcję ponownego odczytu.

### Verification results

- pełne testy panelu: `89 passed`,
- TypeScript strict: passed,
- ESLint zmienionego obszaru: passed bez ostrzeżeń,
- Prettier check zmienionego obszaru: passed,
- produkcyjny build Next.js: passed.

### Not completed

- ręczne testy viewportu i pełnego przepływu operatorskiego są zgodnie z
  decyzją właściciela odroczone do odbioru po TASK-0111,
- odrzucanie oraz korekta geometrii nie należą do tego zadania.

### Documentation updates

- M6.5.4 i G6.5.4 oznaczono jako ukończone,
- `CURRENT_STATE.md` wskazuje TASK-0109 jako następny krok.

### Recommended next task

- TASK-0109 — Review geometry correction and immutable recrop.
