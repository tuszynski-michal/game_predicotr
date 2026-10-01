# TASK-0719 — Przybliżona wygrana: przewijalna tabela i wykres

## Status

done

## Goal

Sekcja „Przybliżona wygrana” domyślnie analizuje 2 500 spinów, pokazuje wszystkie
wiersze wypłat w przewijalnej tabeli z widocznym nagłówkiem oraz wykres
narastających wypłat względem liczby spinów.

## Context

Operator potrzebuje przeglądać większy, typowy zakres bez ręcznej zmiany inputu
i porównywać wypłaty z pozycją w sekwencji bez zmiany stron tabeli.

## Dependencies / entry conditions

- Istniejący pion D-446 / TASK-0653 dostarcza dane wyłącznie do odczytu i
  narastające wartości dla wierszy z dodatnią wypłatą.
- Zmiana nie zmienia endpointu, limitu API (`1..10 000`) ani obliczeń payoutu.

## Recommended execution

gpt-6-sol, reasoning `medium` — lokalna zmiana klienta Admina z testami stanu,
interakcji i stylu. Eskalacja do `high` jest potrzebna tylko, jeżeli istniejące
dane API nie wystarczą do jednoznacznego wykresu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0653-approximate-win-admin-ui.md`

## Scope

- Zmienić domyślny „Zakres wygranej” z 1 000 na 2 500 spinów.
- Zastąpić kliencką paginację tabeli pojedynczym przewijalnym obszarem o
  wysokości mieszczącej około 20 wierszy; nagłówek tabeli pozostaje sticky.
- Usunąć sterowanie stronami i nie ograniczać listy wierszy po stronie klienta.
- Dodać pod tabelą dostępny, responsywny wykres SVG narastających rozpoznanych
  wypłat według numeru spinu, z zerowym początkiem; bez nowej zależności.
- Uaktualnić wymaganie UI, task i CURRENT_STATE.

## Out of scope

- Zmiana API, danych, algorytmu payoutu, limitu 10 000 lub zapytań.
- Wykres prognozy/statystyki dla spinów bez wypłaty.
- Uruchamianie lokalnego API/Admina na danych użytkownika.

## Acceptance criteria

- [x] Pierwsze otwarcie sekcji wysyła `spinCount: 2500`.
- [x] Wszystkie otrzymane wiersze dodatnich wypłat są w jednej tabeli;
      jednorazowo widocznych jest około 20, pozostałe są dostępne przez pionowe
      przewijanie, a nagłówki kolumn nie znikają.
- [x] Nie ma stopki, przycisków ani tekstu paginacji.
- [x] Pod tabelą jest wykres narastających wypłat względem spinów, czytelny
      także bez koloru i bez danych wyświetlający właściwy pusty stan.
- [x] Testy jednostkowe/interakcji, lint i typecheck Admina przechodzą.

## Technical notes

Źródłem danych wykresu są `rows[]` istniejącej odpowiedzi: każdy punkt używa
`spinNumber` oraz `cumulativePayoutCredits`, a punkt startowy ma `(0, 0)`.
Brak rekordów wygranej oznacza pusty stan wykresu, nie sztuczne dane. Inline SVG
jest celowo wybrany zamiast biblioteki: nie dokłada paczki ani dodatkowego
formatu danych i dziedziczy tokeny kolorów Admina. Tabela renderuje wszystkie
wiersze odpowiedzi; wysokość i sticky header są wyłącznie prezentacją CSS.

## Expected files

- Istniejące: `apps/admin/src/features/board-search/board-search-approximate-win-state.ts`.
- Istniejące: `apps/admin/src/features/board-search/board-search-approximate-win.tsx`.
- Istniejące: `apps/admin/src/app/globals.css`.
- Istniejące: `apps/admin/test/board-search-approximate-win-state.test.mjs`.
- Istniejące: `apps/admin/test-interactions/board-search-approximate-win.test.mjs`.
- Istniejące: `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Domyślne otwarcie → jedno żądanie z `spinCount=2500`.
- Odpowiedź z ponad 20 wierszami → DOM zawiera wszystkie wiersze i brak
  nawigacji stron.
- Odpowiedź z wypłatami → wykres zawiera opis i punkty od zera do ostatniego
  narastającego payoutu.
- Pusta lista wypłat → tabela oraz wykres pokazują poprawne puste stany.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

Każda komenda ma limit 120 sekund; zmiana jest zakończona dopiero po zaliczeniu
testów i kontroli jakości zmienionego frontendu.

## Risks / open questions

- API zwraca tylko pozytywne wypłaty, więc wykres nie może pokazać każdego
  spinu; opis wykresu musi to jasno komunikować.

## Outcome

### Changed

- Domyślny zakres zmieniono na 2 500 spinów.
- Usunięto stronicowanie; wszystkie dodatnie wypłaty są w jednej, pionowo
  przewijalnej tabeli ze sticky nagłówkiem.
- Dodano responsywny wykres SVG narastających rozpoznanych wypłat według numeru
  spinu oraz jawny pusty stan. Nie dodano nowej zależności.
- Zaktualizowano wymagania Admina i testy stanu/interakcji.

### Verification results

- Admin unit: 611 PASS.
- Admin interactions: 49 PASS.
- Zmodyfikowany pion: 12 testów stanu i 10 interakcji PASS.
- ESLint, TypeScript i produkcyjny build Next PASS.

### Not completed

- Nie uruchomiono API ani ręcznego odbioru na danych użytkownika; zmiana nie
  wymagała API, a testy komponentu korzystają z deterministycznego klienta.

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md` i `CURRENT_STATE.md` opisują nowy zakres,
  przewijanie tabeli oraz wykres.

### Recommended next task

- Brak; ewentualny odbiór na żywych danych gry 777 pozostaje osobnym zakresem.

Commit `v1.7.38` / `e7efc6acef70eb0af89533063fdf4bc298d1f6f4`.

## Przypisanie modeli do zadań

| Zadanie   | Model     | Reasoning | Uzasadnienie                                                                | Dodatkowy review                                              |
| --------- | --------- | --------- | --------------------------------------------------------------------------- | ------------------------------------------------------------- |
| TASK-0719 | gpt-6-sol | medium    | Zmiana dotyczy jednego izolowanego pionu UI oraz deterministycznych testów. | Niewymagany; review przez lint, typecheck i testy interakcji. |
