# TASK-1239 — Doprecyzowanie zwartej wyszukiwarki

## Status

`done`

## Goal

Wprowadzić pięć korekt wyglądu zgłoszonych po odbiorze TASK-1238.

## Scope / Acceptance criteria

- [x] Ukryć oba opisy pod tytułem palety symboli.
- [x] Powiększyć mobilne kafelki palety o 15%: 44–48 → 50,6–55,2 px.
- [x] Liczba wyników po prawej od Wierszami, w tym samym rzędzie; dostępna
  nazwa inputu zachowana, bez długiej widocznej etykiety.
- [x] Ukryć opis skrótów pod przyciskami rankingu.
- [x] Pod wykresem pokazać wyłącznie „N częściowych, M brakujących”.

## Technical notes / plan wykonania

Zmiany wyłącznie zwykłego widoku (`sequenceEnabled` / `simplified`),
z zachowaniem domyślnego edytora zarządzania. Przenieść istniejący input,
zachować walidację i automatyczne odświeżanie limitu. Skróty nadal działają.
Sprawdzić interakcje i render dotykowy 320/375/768 px. Bez API, danych,
restartów, scalenia i pushu. Zakres i powiększenie wynikają z polecenia
operatora; nie ma otwartych pytań produktowych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`

## Expected files

- `packages/board-search-ui/src/board-search-workspace.tsx` — formularz.
- `packages/board-search-ui/src/board-search-results.tsx` — opis nawigacji.
- `packages/board-search-ui/src/board-search-approximate-win.tsx` — liczby.
- `packages/board-search-ui/src/board-search.css` oraz istniejące testy.

## Recommended execution

`gpt-6.1-sol`, reasoning `medium`; niewielka zmiana prezentacji, bez API.
Powrót do oceny zakresu, jeśli ujawni się konieczność zmiany logiki szukania.

## Verification

Interakcje zmienionego pionu, typecheck i lint pakietu, format oraz istniejący
test przeglądarkowy 320/375/768 px. Komendy z timeoutem ≤120 s. Zamknięcie
przez task-close, kontrola dokumentacji i osobny commit oraz zapis hasha.

## Outcome

Commit: v1.7.661 (hash dopisuje kolejny commit).

- Wszystkie pięć kryteriów spełnione, domyślne zachowanie panelu zarządzania
  zachowane. API i semantyka szukania bez zmian.
- Interakcje formularza i wygranej 53/53 PASS; lint i typecheck pakietu PASS.
- Test Edge z dotykiem 320/375/768 px PASS: limit na prawo od Wierszami
  w jednej linii, brak przewijania poziomego, kafelki +15%, ranking i podgląd
  wykresu działają. Zrzut 320 px sprawdzony wizualnie.
- Format, kontrola mapy kodu, docs:check i zamknięcie task-close PASS.
- Bez pełnego builda, restartu usług, fizycznego Androida, audytu
  (niewymagany), merge i pushu. Zmiany czekają na akceptację do scalenia.
- Wymagania wyszukiwarki uaktualnione. Następny krok: odbiór i zgoda na merge.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1239 | gpt-6.1-sol | medium | Pięć lokalnych korekt prezentacji, istniejące testy i fixture mobilne. | Nie |
