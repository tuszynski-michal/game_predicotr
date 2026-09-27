---
title: TASK-0715 — Słownik laboratorium z samą nazwą symbolu
status: done
last_updated: 2026-09-27
---

# TASK-0715 — Słownik laboratorium z samą nazwą symbolu

## Status

`done`

## Goal

Operator wpisuje wyłącznie nazwę symbolu; techniczne ID i kod powstają automatycznie.

## Context

Użytkownik nie chce nadawać ID ani kodu w sekcji „Słownik gry”. Obecne
DictionaryEntry wymaga obu pól, ale nie wymaga ręcznego nadawania przez człowieka.
To wąska poprawka narzędzi T06a, nie wykonanie T06b ani treningu.

## Dependencies / entry conditions

T06a odebrane w v1.7.31. Bieżący HEAD v1.7.32 / 7bb63a793ddfa589fecfe994b1e86c1ca2f3d000.
Zastane zmiany dokumentacji i next-env należą do innych prac i nie wchodzą do commita.
Brak pytań blokujących; API, schemat i istniejące dane pozostają bez zmian.

## Recommended execution

Wykonawca `gpt-5.6-terra`, reasoning `high`; niezależny audyt `gpt-5.6-terra`,
reasoning `high`. Mała zmiana formularza i testów przy ustalonym kontrakcie.
Jeżeli nie wystarczy zachowanie istniejącego kontraktu, zatrzymać zależny zakres.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`, `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/tasks/0671-vision-lab-symbol-labels.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T06)
- `ai_docs/delivery/VISION_LAB_SYMBOL_LABELS_CONTRACT.md` (słownik, UI)

## Scope

Formularz słownika, automatyczna techniczna tożsamość nowych wpisów, regresje i dokumentacja.

## Out of scope

Zmiany API/backendu, import starych etykiet DB, zmiana danych operatora, trening,
holdouty, migracje, push i aktywacja modelu.

## Acceptance criteria

- [x] Nowa pozycja wymaga wyłącznie nazwy; ID i kod nie są polami formularza.
- [x] Nowy wpis dostaje raz UUID i kod `symbol_<UUID>` przy dodaniu, nie przy zapisie/retry.
- [x] Zmiana nazwy i odczyt istniejącej wersji zachowują oryginalne ID i kod.
- [x] Usunięcie i dodanie pozycji tworzy nową tożsamość, nie odzyskuje starej po nazwie.
- [x] Pusta nazwa po trim blokuje zapis z toastem; nazwa jest przy zapisie przycinana.
- [x] Jawny zapis i approval, CAS i identyczny retry pozostają bez zmian.
- [x] Testy, lint, typecheck i niezależny audyt nie pozostawiają P0–P2.

## Technical notes

Zachować DictionaryEntry i payload istniejącego API. Losowanie tylko w obsłudze
„Dodaj klasę”; wpis pozostaje w stanie UI, key=entry.id. Nie wyprowadzać tożsamości
z nazwy, indeksu ani liczby klas. Istniejące ID i kody mogą mieć dowolną zgodną
historyczną postać i nigdy nie są regenerowane. Nazwa może korygować opis tej samej
klasy; tekst UI wyjaśnia, że inny symbol należy dodać jako nową pozycję. Zapis
nowej wersji i jej zatwierdzenie zachowują dotychczasowe skutki dla aktualności
etykiet. API nadal ostatecznie waliduje ograniczenia i unikalność ID/kodów.

## Expected files

- `apps/vision-lab/src/components/symbol-label-editor.tsx` — SymbolLabelEditor.
- `apps/vision-lab/src/lib/symbol-workflow.ts` — helper nowego wpisu/normalizacji.
- `apps/vision-lab/test/symbol-workflow.test.mjs` i istniejący harness React.
- Wymagania VISION_LAB, kontrakt T06a, CURRENT_STATE oraz ten task.

## Test cases

Tworzenie dwóch wpisów; edycja nazwy bez zmiany ID/kodu; stara wersja z własnymi
kodami; usunięcie i ponowne dodanie; pusta nazwa; trim; brak pól ID/Kod w renderze;
utrata odpowiedzi i identyczny retry; dotychczasowe testy laboratorium.

## Verification

Z repo: `npm.cmd run test --workspace @game-predictor/vision-lab`, potem osobno
`npm.cmd run lint --workspace @game-predictor/vision-lab` oraz
`npm.cmd run typecheck --workspace @game-predictor/vision-lab`.
Każda skończona komenda z limitem 120 sekund i kontrolą procesu po timeout.
Build wyłącznie jako kontrolowana komenda. UI nie zatwierdza prawdziwych danych
podczas odbioru. Wyniki poniżej dopiero po wykonaniu.

## Risks / open questions

Otwarta strona może mieć niezapisane wpisy operatora; nie odświeżać jej ani nie
restartować usług bez sprawdzenia stanu. Nie zmieniać semantyki istniejącej klasy.

## Outcome

### Changed

Formularz wymaga wyłącznie nazwy. Generowany typ DictionaryEntry pozostaje
źródłem kontraktu; helper nadaje UUID i kod tylko przy dodaniu. Istniejące
tożsamości, jawne wersje i retry pozostają bez zmian. Pusta nazwa daje toast.
Commit: do zapisania po kontroli indeksu; ostatni potwierdzony HEAD v1.7.32.

### Verification results

- Wykonawca i niezależny audytor `gpt-5.6-terra/high`: końcowe 42/42 testy
  laboratorium, lint, typecheck, format i diff check PASS. Audyt bez P0–P2.
  Jeden cykl naprawił nieprawidłową długość UUID w teście; wcześniejsze 41/42
  nie było odbiorem, końcowy niezależny re-test jest zielony.
- Root: build Next PASS w nowym procesie; uruchomiony nowy lokalny UI PID22592,
  HTTP200 pod /symbols. Zweryfikowano tożsamość starego PID37032 przed zatrzymaniem.
  API8102 bez restartu. Logi `artifacts/vision-lab/t0715-build.*` i `t0715-ui.*`.
- Browser QA w osobnej karcie: wybrano Blazing, dodano wyłącznie niezapisany
  wpis; widoczne jedno pole Nazwa, bez ID/Kod. Bez zatwierdzania rzeczywistych
  słowników, etykiet, zmian geometrii ani odświeżania karty operatora.
- DoD: zakres/kontrakt/ochrona danych zgodne, testy towarzyszą kodowi,
  mały pion UI bez API/ORM/migracji. Trwałość potwierdzona buildem i nowym
  procesem; nie deklaruje się wykonanego restartu systemu.

### Not completed

Bez fizycznego Androida, restartu OS, pełnych testów repo, treningu,
importu starych zatwierdzeń DB, push/merge i aktywacji modelu.

### Documentation updates

Wymagania VISION_LAB, kontrakt T06a, przewodnik operatora, CURRENT_STATE i task.
Architektura/API/model danych nie zmieniły się, dlatego bez nowej decyzji domenowej.

### Recommended next task

Operator może po odświeżeniu sam dodać nazwy i jawnie zapisać/zatwierdzić słownik.
T06b nadal wymaga danych i kwalifikacji; poprawka nie odblokowuje treningu.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0715 — słownik z samą nazwą | `gpt-5.6-terra` | `high` | Mała poprawka formularza przy niezmienionym API. | `gpt-5.6-terra`, `high` |
