# TASK-1238 — Uproszczenie wyszukiwarki plansz

## Status

`todo`

## Goal

Uprościć panel wyszukiwania plansz, ograniczyć zajmowane miejsce i poprawić
wprowadzanie kolejnych wzorów, szczególnie na telefonach otwierających link.

## Context

Operator zgłosił 13 zmian 2026-11-17. Bieżące zlecenie obejmuje wyłącznie
zapisanie ich do wykonania w przyszłości. Punkty 1 i 2 zostały dodatkowo
potwierdzone: opisują oczekiwane zachowanie, nie błędy, które należy odwrócić.

## Dependencies / entry conditions

Implementacja wymaga osobnego polecenia operatora oraz ponownego sprawdzenia
bieżącego kodu i wymagań. Przed wdrożeniem doprecyzować zakres usuwanej
nawigacji opisany w pytaniach poniżej.

## Recommended execution

Zaakceptowany plan zapisu wskazuje `gpt-6.1-sol`, reasoning `low`, bez
dodatkowego review. To przypisanie dotyczy wyłącznie zapisu dokumentacji.
Dobór wykonawcy, reasoning i ewentualnego audytu przyszłych zmian UI należy
do osobnego planu implementacji; nie wynika z obecnego zlecenia.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — Wyszukiwanie plansz z niepełnym
  wzorem; Przybliżona wygrana.
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — wspólny UI Admina i linków,
  podgląd planszy z wykresu.

## Scope

Przyszłe zmiany panelu wyszukiwania plansz według poniższej checklisty,
z uwzględnieniem mobilnego widoku linku. Numeracja odpowiada zgłoszeniu.

## Acceptance criteria

1. [ ] **Potwierdzone:** po wyszukaniu pierwszy kolejny wpisany symbol czyści
   poprzedni wzór i staje się pierwszym symbolem nowego układu.
2. [ ] **Potwierdzone:** kliknięcie „Szukaj plansz” ukrywa poprzednio znalezioną
   planszę pod formularzem; po odpowiedzi pokazuje nowy wynik.
3. [ ] Usunięte są przyciski przechodzenia do poprzedniej i następnej planszy.
4. [ ] Przycisk symbolu `?` jest na razie ukryty w palecie.
5. [ ] Na telefonach symbole do klikania są mniejsze, z zachowaniem wygodnej
   obsługi dotykiem.
6. [ ] Usunięte są tytuł „Twój wzór” i jego podtytuł; odstęp między paletą
   symboli a wprowadzonym układem jest mniejszy.
7. [ ] W wyborze kolejności wpisywania pozostają radio buttony „Kolumnami”
   i „Wierszami”; nie ma tytułu ani tekstu informacyjnego, a sekcja z tłem
   zajmuje mniej miejsca.
8. [ ] Usunięty jest przycisk „Nowe szukanie”; „Resetuj” zapewnia rozpoczęcie
   od nowa.
9. [ ] „Szukaj plansz” stoi obok „Cofnij” i „Resetuj”, jest największym
   przyciskiem i wypełnia pozostałe wolne miejsce.
10. [ ] Na górze pozostają wybór gry oraz mniejszy tytuł „Wyszukaj plansze”,
    bez pozostałych tekstów. Pole „Liczba wyników” jest pod przyciskiem
    „Szukaj plansz”.
11. [ ] Wynik ma jeden zwarty wiersz, np. „Układ #123 · dopasowanie 95% ·
    1 z 40”. Usunięty jest podtytuł powtarzający te informacje.
12. [ ] Pod „Pokaż planszę” nie ma czterech pól: „Dokładne”, „Alternatywy”,
    „Sprzeczne” i „Brak danych”.
13. [ ] W sekcji wygranej usunięte są zbędne nagłówki i podpowiedzi.
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

Sprawdzone punkty wejścia do przyszłych zmian:

- `packages/board-search-ui/src/board-search-workspace.tsx` —
  `BoardSearchWorkspace`, edytor, nagłówek i akcje.
- `packages/board-search-ui/src/board-search-results.tsx` — prezentacja
  wyników, cztery pola dopasowania i nawigacja.
- `packages/board-search-ui/src/board-search-approximate-win.tsx` — zakres,
  stawka i zawartość sekcji wygranej.
- Właściwe style, testy i osadzenie wyboru gry potwierdzić przed kodowaniem.

## Test cases

Planowane na etap implementacji, obecnie niewykonane:

- Wyszukanie wzoru A → wpisanie B rozpoczyna nowy wzór od B; dalsze symbole
  uzupełniają nowy wzór. Ponowne szukanie ukrywa stary podgląd. Punkty 1–2.
- Odbiór obecności kontrolek, resetu i zwartego nagłówka wyniku. Punkty
  3–4 i 6–12.
- Odbiór linku na telefonie: rozmiar symboli, wygodny dotyk, brak poziomego
  przewijania i wykres z planszą bezpośrednio pod kontrolkami. Punkty 5 i 13.
- Regresja cofania, kolejności wpisywania, limitu wyników i dalszej
  zawartości sekcji wygranej; obsługa błędu i braku wyników.

## Verification

Przy samym zapisie: komplet 13 punktów, potwierdzenia punktów 1–2, status
`todo`, wskaźnik w `CURRENT_STATE.md` oraz `npm run docs:check` z timeoutem
120 s, uruchomione z katalogu głównego checkoutu dokumentacji.

Testy aplikacji, lint/typecheck zmienionych modułów i odbiór telefonu
należą do późniejszej implementacji.

## Out of scope

Implementacja UI w ramach obecnego zlecenia zapisu, zmiany API, rankingu,
kalkulatora wygranej i danych. Panel zarządzania i aplikacja mobilna offline.
Restart usług, migracje, wdrożenie, merge i push.

## Risks / open questions

- Punkt 3 wymaga rozróżnienia przycisków „Poprzedni układ” / „Następny układ”
  przy zdjęciu od „Poprzednia” / „Następna” między dopasowaniami. Zgłoszenie
  nie rozstrzyga likwidacji możliwości wyboru pozostałych wyników.
- Rozmiary symboli i odstępy trzeba dobrać na widoku mobilnym; operator nie
  podał wartości w pikselach.

## Outcome

2026-11-17: zapisano zgłoszenie 13 zmian do późniejszej realizacji oraz
potwierdzone znaczenie punktów 1–2. Zadanie pozostaje `todo`; implementacja,
testy aplikacji i odbiór telefonu nie zostały wykonane.

Weryfikacja zapisu: komplet 13/13 punktów, dwa potwierdzenia, status `todo`
i wskaźnik w `CURRENT_STATE.md` sprawdzone. `npm run docs:check` PASS
(linki decyzji, okno stanu, 11/11 budżetów odczytu i kopie skilli).
