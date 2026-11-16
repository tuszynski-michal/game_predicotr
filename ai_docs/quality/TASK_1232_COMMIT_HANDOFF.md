# TASK-1232 — Informacja do Claude Code o zakresie commita

Data: 2026-11-16. Katalog: `D:\game_predicotr`. Użytkownik polecił przekazać
Claude Code przez terminal informację, co ma zacommitować po zakończeniu zmian.
Ta informacja nie jest zgodą na merge, push ani restart usług.

## Wynik

- Maksimum kliknięcia ±50 spinów wybiera wyłącznie dodatnią wygraną wliczoną
  do bilansu; pusty odcinek nie tworzy przypadkowego punktu.
- Wspólny wykres Admin/link/panel i dziennik zapytań pokazują miniaturę pod
  wykresem. Marker i akcja podglądu otwierają własną planszę, bez ponownego
  przyciągania do wyższego sąsiedniego punktu.
- Pozycja planszy pochodzi z wiersza API, zdjęcie jest związane checksumą i
  rewizją. Podgląd ma ograniczone wymiary, zamknięcie, loading/error i retry.

## Właścicielski zakres

Pełne zmiany poniższych plików należą do TASK-1232 (były czyste przed zadaniem):

- `packages/board-search-ui/src/board-search-approximate-win-state.ts`
- `packages/board-search-ui/src/board-search-approximate-win.tsx`
- nowy `packages/board-search-ui/src/board-search-chart-preview.tsx`
- `packages/board-search-ui/src/board-search.css`
- `packages/board-search-ui/test/board-search-approximate-win-state.test.mjs`
- `packages/board-search-ui/test-interactions/board-search-approximate-win.test.mjs`
- `apps/admin/src/features/board-search/board-search-share-query-log.tsx`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/archive/CURRENT_STATE_2026Q4.md` — tylko nowy blok TASK-1232.
- nowy `ai_docs/tasks/completed/1232-board-search-winning-chart-preview.md`
- ten nowy plik przekazania.

Pliki współdzielone miały cudze zmiany. Do indeksu wyłącznie:

- `ai_docs/process/CURRENT_STATE.md`: nowy wpis `done` TASK-1232 i usunięcie
  najstarszego wiersza TASK-1203 zgodnie z oknem 10. Bez zmian TASK-1230/1231.
- `ai_docs/architecture/CODE_MAP.md`: wyłącznie liczba plików
  `packages/board-search-ui/src/`: 42 → 43.
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`: wyłącznie nowy wiersz
  `board-search-chart-preview.tsx: BoardSearchChartPreview`.

Nie dołączać `AGENTS.md`, innych dokumentów procesu, klienta OpenAPI, uczenia
siatek, selektora, package-lock ani innych zmian zastanych. Nie używać
`git add .` ani `git add -A`. Materiały `artifacts/task-1232/` są ignorowane
i nie należą do commita.

## Przygotowane łatki

- `artifacts/task-1232/commit-scope.patch`: pełny zakres tego taska nałożony
  na indeks HEAD, z nowymi plikami i wyłącznie własnymi zmianami dokumentów
  współdzielonych. Przed użyciem sprawdzić aktualność i `git apply --cached --check`.
- `artifacts/task-1232/code-map-task-only.patch`: wyłącznie własne dwa hunki mapy.
- Materiały robocze i kontrolne w `artifacts/task-1232/`; nie commitować ich.

## Weryfikacja

- Unit całego pakietu PASS; zmieniona logika 32/32 PASS.
- Zmieniony plik interakcji 32/32 PASS oraz późniejsze cztery nowe przypadki
  braku/starego/obcego zdjęcia 4/4 PASS.
- Pełne interakcje: 120/121 PASS; jedyny FAIL `Admin opens the editable series
  modal in StrictMode...` to dwie kopie Reacta i `useMemo` w niezmienionym
  wrapperze Admina. Plik wrappera nie ma diff względem HEAD. Nie zmieniano
  tego testu ani zależności; nie deklarować pełnego PASS.
- Publiczny adapter i proxy Reviewera/panelu 38/38 PASS.
- Typecheck wspólnego pakietu, Admina i Reviewera PASS. ESLint i Prettier
  zmienionych plików PASS. Mapa zregenerowana, `code-map:check` PASS.
- Chrome 1100/390 px PASS: karta 380/344 px, zdjęcie 214,8/193,2 px,
  brak poziomego overflow i pełnoekranowego modala, marker wskazuje planszę 7.
- Zamknięcie przez `scripts/close_task.py` wykonane; kontrola okna i budżetu
  odczytu PASS. Wynik końcowego `docs:check` w Outcome.
- Bez pełnych buildów Next i uruchamiania/restartowania usług. Bez testu
  rzeczywistego udostępnionego linku na danych operatora; publiczny adapter
  jest objęty testem interakcji z kontrolowanymi odpowiedziami.

## Stan Git i wersja

Codex nie zapisał commita: próba zwykłego `git switch -c
codex/chart-win-preview` zakończyła się `Permission denied` dla `.git`.
Nie używano obejść ani delegowania zapisu Git w celu ominięcia blokady.
Przekazanie jest informacyjne; potwierdzenie odbioru przez CLI nie oznacza commita.

Próby wysłania informacji przez odkryte CLI nie uzyskały potwierdzenia odbioru
w limicie 60 s (stdin i argument pozycyjny; pośredni błąd parsowania argumentu
poprawiono). `claude auth status` potwierdziło aktywne logowanie. Nie deklarujemy
dostarczenia ani wykonania commita. Dokładny zakres i gotowa łatka pozostają
zapisane lokalnie do odebrania przez sesję Claude Code.

Sprawdzony HEAD: `34a03819`, wersja `v1.7.646`. Przewidziano `v1.7.647 -
Wygrane na wykresie i podglad planszy`; przed rzeczywistym commitem ponownie
ustalić numer z `git log`, pracować na gałęzi roboczej i zweryfikować hunki
oraz `git diff --cached --check/stat/name-only`. Po commicie zweryfikować
`git show`, zapisać rzeczywisty hash procedurą `record-hash`; jeśli wersja
się zmieniła, spójnie poprawić metadane zadania i stanu. Bez merge/push.
