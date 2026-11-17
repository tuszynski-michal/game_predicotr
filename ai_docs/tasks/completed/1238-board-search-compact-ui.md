# TASK-1238 — Uproszczenie wyszukiwarki plansz

## Status

`done`

## Goal

Uprościć panel wyszukiwania plansz, ograniczyć zajmowane miejsce i poprawić
wprowadzanie kolejnych wzorów, szczególnie na telefonach otwierających link.

## Context

Operator zgłosił 13 zmian 2026-11-17 i zatwierdził ich realizację po
ostrzeżeniu o koszcie (45–90 min). Punkty 1 i 2 zostały dodatkowo
potwierdzone: opisują oczekiwane zachowanie, nie błędy, które należy odwrócić.

## Dependencies / entry conditions

Operator polecił wykonanie całego zadania. Usuwamy wyłącznie przyciski
przeglądania sąsiednich zdjęć; zostają przyciski kolejnych dopasowań rankingu.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`, bez dodatkowego audytu, zgodnie z planem
implementacji. Wspólny UI i stany asynchroniczne wymagają testów regresji.
Zmiana API lub modelu domenowego wymaga ponownej oceny zakresu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/BOARD_SEARCH_COMPACT_UI_PLAN_20261117.md`
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/requirements/ADMIN_APP.md` — Wyszukiwanie plansz z niepełnym
  wzorem; Przybliżona wygrana.
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — wspólny UI Admina i linków,
  podgląd planszy z wykresu.

## Scope

Zmiany panelu wyszukiwania plansz według poniższej checklisty,
z uwzględnieniem mobilnego widoku linku. Numeracja odpowiada zgłoszeniu.

## Acceptance criteria

1. [x] **Potwierdzone:** po wyszukaniu pierwszy kolejny wpisany symbol czyści
   poprzedni wzór i staje się pierwszym symbolem nowego układu.
2. [x] **Potwierdzone:** kliknięcie „Szukaj plansz” ukrywa poprzednio znalezioną
   planszę pod formularzem; po odpowiedzi pokazuje nowy wynik.
3. [x] Usunięte są „Poprzedni układ” i „Następny układ” przy zdjęciu;
   pozostają „Poprzednia” i „Następna” między dopasowaniami rankingu.
4. [x] Przycisk symbolu `?` jest na razie ukryty w palecie.
5. [x] Na telefonach symbole do klikania są mniejsze, z zachowaniem wygodnej
   obsługi dotykiem.
6. [x] Usunięte są tytuł „Twój wzór” i jego podtytuł; odstęp między paletą
   symboli a wprowadzonym układem jest mniejszy.
7. [x] W wyborze kolejności wpisywania pozostają radio buttony „Kolumnami”
   i „Wierszami”; nie ma tytułu ani tekstu informacyjnego, a sekcja z tłem
   zajmuje mniej miejsca.
8. [x] Usunięty jest przycisk „Nowe szukanie”; „Resetuj” zapewnia rozpoczęcie
   od nowa.
9. [x] „Szukaj plansz” stoi obok „Cofnij” i „Resetuj”, jest największym
   przyciskiem i wypełnia pozostałe wolne miejsce.
10. [x] Na górze pozostają wybór gry oraz mniejszy tytuł „Wyszukaj plansze”,
    bez pozostałych tekstów. Pole „Liczba wyników” jest pod przyciskiem
    „Szukaj plansz”.
11. [x] Wynik ma jeden zwarty wiersz, np. „Układ #123 · dopasowanie 95% ·
    1 z 40”. Usunięty jest podtytuł powtarzający te informacje.
12. [x] Pod „Pokaż planszę” nie ma czterech pól: „Dokładne”, „Alternatywy”,
    „Sprzeczne” i „Brak danych”.
13. [x] W sekcji wygranej usunięte są zbędne nagłówki i podpowiedzi.
    Bezpośrednio pod zakresem wygranej i stawką znajduje się wykres
    z planszą; dalsza zawartość pozostaje zachowana.

## Technical notes

- Użyć istniejącego wspólnego UI Admina i widoków udostępnionych.
- „Resetuj” i „Nowe szukanie” mają obecnie osobne handlery. Przed usunięciem
  przycisku sprawdzić reset edytora, wyników i kontekstu wyszukiwania,
  zamiast zakładać, że oba przyciski już robią to samo.
- Ukrycie przycisku `?` nie oznacza usuwania danych ani zmiany znaczenia
  nieznanych symboli zapisanych w planszach i historii.
- Zachować komunikaty błędów, ładowania i braku wyników oraz dostępne nazwy
  kontrolek. Aktualizację wymagań wykonać przy implementacji.

## Expected files

Punkty wejścia wdrożonych zmian:

- `packages/board-search-ui/src/board-search-workspace.tsx` —
  `BoardSearchWorkspace`, edytor, nagłówek i akcje.
- `packages/board-search-ui/src/board-search-results.tsx` — prezentacja
  wyników, cztery pola dopasowania i nawigacja.
- `packages/board-search-ui/src/board-search-approximate-win.tsx` — zakres,
  stawka i zawartość sekcji wygranej.
- `packages/board-search-ui/src/board-search.css`, `use-board-search.ts`
  i `board-search-local-state.ts` — zwarty układ i trwały stan wprowadzania.
- Nagłówki linków i test panelu w Reviewerze; testy logiki, interakcji
  i nowy `test-browser/board-search-compact.mjs` w pakiecie UI.

## Test cases

Wykonane scenariusze; wyniki i ograniczenia w Outcome:

- Wyszukanie wzoru A → wpisanie B rozpoczyna nowy wzór od B; dalsze symbole
  uzupełniają nowy wzór. Ponowne szukanie ukrywa stary podgląd. Punkty 1–2.
- Odbiór obecności kontrolek, resetu i zwartego nagłówka wyniku. Punkty
  3–4 i 6–12.
- Odbiór linku na telefonie: rozmiar symboli, wygodny dotyk, brak poziomego
  przewijania i wykres z planszą bezpośrednio pod kontrolkami. Punkty 5 i 13.
- Regresja cofania, kolejności wpisywania, limitu wyników i dalszej
  zawartości sekcji wygranej; obsługa błędu i braku wyników.

## Verification

Z katalogu głównego worktree: testy pakietu `@game-predictor/board-search-ui`,
jego lint i typecheck, typecheck Admina i Reviewera oraz test panelu linku.
Każda skończona komenda uruchomiona przez `subprocess.run(timeout=120)`
(lub krótszy limit dla formatowania/odczytu).

Test interakcji używa w tym worktree `artifacts/task-1238-verification/tsconfig.json`,
który kieruje import pakietu UI do tego checkoutu i rozwiązuje React do jednej
kopii. Standardowe uruchomienie pożyczające zależności checkoutu głównego
ujawniło dwie kopie React; nie zmieniano zależności produktu.

Browser: `node packages/board-search-ui/test-browser/board-search-compact.mjs`,
limit 120 s, bezgłowy Edge z emulacją dotyku, trasy fixture w pamięci, bez
serwera aplikacji i danych operatora. Kontrola 320/375/768 px oraz podglądu
planszy z wykresu. Artefakty: `artifacts/task-1238-verification/`.

Kontrole końcowe: format zmienionego kodu, `npm run docs:check`,
`npm run code-map:check` i `git diff --check`.

## Out of scope

Zmiany API, rankingu, kalkulatora wygranej i danych. Panel zarządzania
i aplikacja mobilna offline. Restart usług, migracje, wdrożenie, merge i push.

## Risks / open questions

- Punkt 3 rozstrzygnięty przez operatora: usunięcie sąsiednich zdjęć,
  zachowanie przechodzenia po rankingu dopasowań.
- Paleta mobilna ma kafelki 44–48 px. Test dotykowy jest emulacją przeglądarki;
  fizyczny Android i działający link operatora wymagają osobnego odbioru.

## Outcome

Commit: v1.7.659 (hash dopisuje kolejny commit).

### Changed

- Wszystkie 13 punktów: nowy wzór po szukaniu, pełny reset, ukrywanie starego
  wyniku podczas zapytania i po błędzie, zwarty formularz i wynik,
  mniejsze symbole mobilne oraz wykres bezpośrednio pod zakresem i stawką.
- Usunięto wyłącznie nawigację sąsiednich zdjęć; ranking i jego kotwica
  wygranej pozostają. Podgląd/korekta dotyczą wybranego trafienia.
- Opcjonalny stan `nextSymbolStartsPattern` zachowuje moment rozpoczęcia
  wzoru po odświeżeniu, także przy identycznych symbolach. Stare zapisy
  pozostają czytelne. Reset odporny na spóźnioną odpowiedź.
- Opcje `simplified` są domyślnie wyłączone; regresje edytora zarządzania
  i pozostałych konsumentów przeszły.

### Verification results

- Testy interakcji pakietu: **131/131 PASS**; testy logiki: **115/115 PASS**.
  Dodatkowo panel Reviewera **2/2 PASS**. Końcowy test zmienionego pionu
  po uzupełnieniu dostępnej nazwy nagłówka: **23/23 PASS**.
- Lint pakietu i zmienionych plików Reviewera, typecheck pakietu oraz
  bezpośrednie `tsc --noEmit` Admina i Reviewera: PASS.
- Test Edge 320/375/768 px z dotykiem: PASS; brak przewijania poziomego,
  cele 44 px, trzy akcje i zakres/stawka w jednym rzędzie, zachowany ranking
  i podgląd planszy z wykresu. Zrzuty sprawdzono wizualnie.
- Format zmienionego kodu: PASS. Mapa kodu zregenerowana,
  `code-map:check` PASS. Zamknięcie `close_task.py` i `docs:check` PASS
  (okno stanu, linki decyzji, budżety i kopie skilli).

### Not completed

- Bez pełnych buildów aplikacji, fizycznego Androida, odbioru na danych/linku
  operatora, restartów, migracji, scalenia i pushu.
- Audyt krzyżowy nie był wymagany przez plan. Brak otwartych P0/P1.

### Documentation updates

- Wymagania Admina, architektura wspólnego UI, plan wdrożenia, katalog,
  mapa kodu i stan taska.

### Recommended next task

- Akceptacja wyniku i osobna zgoda na scalenie do main; potem odbiór
  rzeczywistego linku na telefonie.
