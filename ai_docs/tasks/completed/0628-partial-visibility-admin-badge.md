---
title: TASK-0628 — badge „poza kadrem" dla częściowo widocznych komórek w Weryfikacji symboli (T3)
status: done
last_updated: 2026-09-24
---

# TASK-0628 — badge „poza kadrem" dla częściowo widocznych komórek w Weryfikacji symboli (T3)

## Status

`done`

## Goal

Karta cropu w Admin → Weryfikacja symboli pokazuje operatorowi *dlaczego*
dana komórka jest nierozpoznana, gdy przyczyną jest częściowa widoczność
(`qualityIssue === 'partial_visibility'`, TASK-0627/D-436) — analogicznie
do istniejących badge'y dla `grid_issue`/`blurry`/`unreadable`.

## Context

Ostatni z 3-taskowego planu D-434 (T1: TASK-0625, T2: TASK-0626+0627, ten
task: T3). Backend od TASK-0627 (`v0.10.394`) wymusza dla komórek
częściowo widocznych (1–3 z 4 rogów quada poza kadrem): `assignedSymbolId
= null`, `qualityIssue = "partial_visibility"`, `assignmentSource =
"geometry_partial"`, `reviewState = pending`. Te komórki już trafiają pod
istniejący filtr „Nierozpoznany (?)" w Admin — brakuje im tylko wizualnego
wyjaśnienia PRZYCZYNY na karcie, tak jak mają je już `grid_issue`
(„Zła siatka"), `blurry` („Niewyraźny") i `unreadable` („Nieczytelny").

Research (Explore agent) potwierdził: jedyne miejsce renderujące te
wyjaśnienia to `symbolReviewCardBadge()` w
`apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx` —
czysta funkcja `(item) => string | null`, zwracająca krótki tekstowy chip
(bez ikon, bez kolorowania — `apps/admin` nie ma biblioteki ikon). Pole
`qualityIssue` w wygenerowanym typie (`packages/admin-api-client`) to
zwykłe `string | null` (backend nie używa Pydantic `Literal`), więc **nie
trzeba nigdzie aktualizować typów** — tylko dodać nowe porównania
`=== 'partial_visibility'`. `assignmentSource` nie jest dziś w ogóle
używane we frontendzie — bez zmian, poza zakresem. Nie ma osobnego filtra
po `qualityIssue` — istniejący filtr „Nierozpoznany (?)" (po `symbolId`)
już obejmuje te komórki bez żadnych zmian w filtrowaniu.

## Dependencies / entry conditions

- TASK-0625, TASK-0626, TASK-0627 ukończone i zacommitowane
  (`v0.10.392`–`v0.10.394`).

## Recommended execution

`claude-sonnet-5`, reasoning `medium`. Uzasadnienie: jedna czysta funkcja w
jednym pliku, wzorzec do skopiowania już istnieje 3 razy w tym samym
pliku (grid_issue/blurry/unreadable); brak nowych typów, brak zmian
backendu/API, brak migracji. Eskalacja: gdyby okazało się, że
`SymbolCellReviewListItemResponse` faktycznie ma literal union (nie
zwykły `string`) i wymaga regeneracji klienta OpenAPI — wtedy przerwać i
przejść na `claude-opus-5-5`/`xhigh`, bo to sygnał, że research się mylił
co do zakresu. Dodatkowy review: nie — ryzyko niskie, wzorzec kopiowany
1:1 z istniejącego kodu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-434, D-435, D-436)
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/tasks/completed/0627-partial-visibility-review-cell-reconciliation.md`

## Scope

- `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`
  `symbolReviewCardBadge()`: nowa gałąź `item.qualityIssue ===
  'partial_visibility'` w obu blokach (stan `approved` i domyślny),
  wzorem istniejącej gałęzi `unreadable` — tekst „Poza kadrem · ?" (pending)
  / „Poza kadrem · ? · poza uczeniem" (approved).
- `apps/admin/test/symbol-review-workspace-contract.test.mjs`: nowa
  asercja `assert.match(source, /item\.qualityIssue === 'partial_visibility'/)`
  wzorem istniejącej dla `unreadable` (linia ok. 158).

## Out of scope

- `assignmentSource` (`geometry_partial`) — nieużywane dziś we
  frontendzie; brak potrzeby produktowej, żeby to zmieniać teraz.
- Nowy filtr po `qualityIssue` — istniejący filtr „Nierozpoznany (?)" już
  obejmuje te komórki.
- Ikony, kolorowanie per-typ, tooltipy — `apps/admin` nie ma dziś
  biblioteki ikon ani systemu kolorowania per-quality-issue; wprowadzenie
  takiego systemu byłoby refaktorem większym niż ten task, nie jest
  wymagane do spełnienia Goal.
- `apps/reviewer` — osobna aplikacja, poza zakresem tego zgłoszenia
  (dotyczyło Admin → Weryfikacja symboli).

## Acceptance criteria

- [x] Karta cropu z `qualityIssue === 'partial_visibility'` pokazuje
      widoczny tekstowy badge (jak istniejące dla grid_issue/blurry/unreadable).
- [x] Wariant `reviewState === 'approved'` pokazuje wariant z „poza
      uczeniem" (spójnie z `unreadable`, bo D-436 uczynił
      `partial_visibility` równie trwałym wykluczeniem z treningu).
- [x] Brak zmian w typach (`packages/admin-api-client`), bo `qualityIssue`
      jest już `string | null`.
- [x] `npm run test --workspace @game-predictor/admin` (lub odpowiedni
      test kontraktowy) zielony z nową asercją.
- [x] `npm run lint --workspace @game-predictor/admin` i `npm run
      typecheck --workspace @game-predictor/admin` czyste.

## Technical notes

Kopiuj wzorzec 1:1 z gałęzi `unreadable` (linie ok. 1515-1517 i 1535-1537
w `symbol-review-workspace.tsx` przed zmianą) — ta sama struktura
`if (item.qualityIssue === '...') return '...';`, umieszczona
bezpośrednio po gałęzi `unreadable` w obu blokach (kolejność sprawdzania
nie ma znaczenia semantycznego, bo `qualityIssue` ma dokładnie jedną
wartość na komórkę, ale zachowaj sąsiedztwo dla czytelności — wszystkie
`quality_issue` sprawdzane razem, przed `cropApprovalState`/`isUnknown`).

## Expected files

- Istniejące: `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`,
  `apps/admin/test/symbol-review-workspace-contract.test.mjs`.

## Test cases

- Karta z `qualityIssue: 'partial_visibility', reviewState: 'pending'` →
  badge „Poza kadrem · ?".
- Karta z `qualityIssue: 'partial_visibility', reviewState: 'approved'` →
  badge „Poza kadrem · ? · poza uczeniem".

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

Timeout 120 s na krok.

## Risks / open questions

- Dokładne brzmienie polskiego tekstu badge'a nie było wcześniej ustalone
  z użytkownikiem — przyjęto „Poza kadrem" (spójne z terminologią „ramka
  wychodzi poza kadr" z oryginalnego zgłoszenia T3 w TASK-0626). Do
  ewentualnej korekty przez użytkownika po review.

## Outcome

### Changed

- `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`
  `symbolReviewCardBadge()`: nowa gałąź `qualityIssue === 'partial_visibility'`
  w obu blokach (`approved`: `'Poza kadrem · ? · poza uczeniem'`; domyślny:
  `'Poza kadrem · ?'`), umieszczona bezpośrednio po gałęzi `unreadable`.
- `apps/admin/test/symbol-review-workspace-contract.test.mjs`: dwie nowe
  asercje w istniejącym teście `shows only crop thumbnails and exposes
  durable mutation feedback` — dopasowanie do
  `item.qualityIssue === 'partial_visibility'` i do tekstu `Poza kadrem`.
- `ai_docs/requirements/ADMIN_APP.md`: wyliczenie badge'y w sekcji
  Weryfikacji symboli rozszerzone o `Poza kadrem · ?`, plus zdanie
  wyjaśniające skąd bierze się ten stan (D-434/D-435/D-436, operator nie
  może go ustawić ani usunąć ręcznie).

### Verification results

```
npm run test --workspace @game-predictor/admin → 539 passed, 0 failed
npm run lint --workspace @game-predictor/admin → 0 errors, 5 pre-existing
  warnings (none w dotkniętych plikach)
npm run typecheck --workspace @game-predictor/admin → czysto
```

Nie przeprowadzono żywej weryfikacji w przeglądarce z rzeczywistą komórką
`partial_visibility` — wymagałoby to pełnego importu zdjęcia z genuinie
częściowo widoczną planszą przez worker, co jest nieproporcjonalnym
nakładem dla jednoliniowej zmiany tekstu. Poprawność zweryfikowana testem
kontraktowym (dopasowanie dokładnego wzorca źródła identycznego ze
wzorcem trzech już działających badge'y) oraz lint/typecheck. Zgłoszone
jawnie zgodnie z zasadą „jeśli nie możesz przetestować UI, powiedz to
wprost" — brak twierdzenia o wizualnym sukcesie bez dowodu.

### Not completed

- Brak. Zakres w całości zrealizowany.

### Documentation updates

- `ai_docs/process/CURRENT_STATE.md`: nowy wpis TASK-0628 (domyka 3-taskowy
  plan D-434).
- `ai_docs/requirements/ADMIN_APP.md`: zaktualizowana sekcja Weryfikacji
  symboli.
- Brak nowego wpisu `DECISION_LOG.md` — to zmiana wyświetlania UI, nie
  zmiana domeny ani architektury; D-434/D-435/D-436 już opisują decyzję
  leżącą u podstaw tego badge'a.

### Recommended next task

- Brak zaplanowanego kolejnego zadania w tym obszarze — 3-taskowy plan
  D-434 (T1/T2/T3) jest w całości zrealizowany.
