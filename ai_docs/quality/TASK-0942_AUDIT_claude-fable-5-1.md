# Audyt TASK-0942 — Minimalistyczne stawki, zapisany układ i wspólny edytor

Werdykt: PASS
Audytor: claude-fable-5-1, high
Wykonawca: gpt-6.1-sol, high
Zakres: 0625512d...0625512d4a37072f1d6d44f3f85ef225e7db1835 oraz zmiany niezacommitowane (snapshot `artifacts/audits/TASK-0942_STAGE/audit-source`), data 2026-10-09
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano trzynaście plików snapshotu TASK-0942: wariant `compact` wspólnych komponentów `BoardSearchWorkspace`, `BoardSearchResults` i `BoardSearchApproximateWin`, przebudowane kafelki stawek, szybkie wiersze pinów, zwijany dziennik i wynik, logikę Zapisz zmiany / Zastąp układ / Usuń zapisany układ w `management-game-workspace.tsx` oraz zmienione testy Admin, Reviewer i board-search-ui. Zmiana realizuje tabelę stanów planu, nie kopiuje wyszukiwarki ani wykresu, a wyliczenia Wkład / Wygrana netto / Na maszynie pochodzą z istniejących helperów `approximateWinStakeToPoint` i `approximateWinMachineCashAtPoint`. Domyślne ścieżki zwykłego search i share zachowują poprzednie gałęzie renderowania, bo każdy nowy prop ma wartość domyślną `false`. Nie znaleziono P0 ani P1. Główne ryzyko to mylący komunikat po anulowaniu zastąpienia układu oraz brak pełnego ponownego uruchomienia suite Reviewer po dostosowaniu pięciu testów; oba odnotowane jako P2.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `packages/board-search-ui/src/management/management-game-workspace.tsx:608-618` — anulowanie `window.confirm` przy zastąpieniu układu jest sygnalizowane przez `throw new Error('Zastąpienie anulowane…')`. `saveDraft` w `packages/board-search-ui/src/board-search-workspace.tsx:286-293` przepuszcza ten błąd przez `apiErrorMessage` (`packages/board-search-ui/src/api-error.ts:3-5`), który rozpoznaje tylko obiekty z polami `code` i `message`, więc operator po świadomym „Anuluj” widzi baner `role="alert"` „Nie udało się zapisać układu. Zachowano niezapisane zmiany. Spróbuj ponownie.” Zachowanie danych jest poprawne (brak żądania, szkic i zapis zostają; test `apps/admin/test-interactions/management-cards.test.mjs:1409-1412`), ale komunikat jest fałszywym błędem. Proponowana poprawka: dedykowany sygnał anulowania (np. klasa błędu rozpoznawana w `saveDraft` i pokazywana jako `role="status"` bez słowa „nie udało się”) albo rozszerzenie `apiErrorMessage` o `Error.message`.
- [P2-2] `packages/board-search-ui/src/management/management-game-workspace.tsx:875-885` — `<details>` „Pełny zapisany wynik” nie ma treści; wynik renderuje się osobno w `:964-977`, a stan `open` jest niekontrolowany. Otwarcie edytora kafelkiem odmontowuje `<details>`, lecz `view` zostaje, więc po „Zamknij szkic” summary pokazuje stan zwinięty przy widocznym wyniku; kolejne rozwinięcie ponownie wywołuje `open()`. Proponowana poprawka: `open={view !== null && !view.historical && view.stake === slot.stakeGrosze}` albo przeniesienie `ManagementResultView` do wnętrza `<details>`.
- [P2-3] `packages/board-search-ui/src/board-search-approximate-win.tsx:956-969` oraz `packages/board-search-ui/src/management/management-game-workspace.tsx:874` — szybkie wiersze z `slot.pinnedPoints` pokazują „niedostępny” także wtedy, gdy pin jest `available`, a tylko `requiredStakeCredits`/`machineCashCredits` są `null` (metadane sprzed fallbacku TASK-0940, fixture `apps/admin/test-interactions/management-cards.test.mjs:111-114`). Etykieta zlewa „pin poza zakresem” z „metryka niewyliczona”, a przy braku pinów renderuje się pusta tabela z nagłówkiem. Proponowana poprawka: odrębny znacznik („—”) dla brakującej metryki dostępnego pinu i krótki tekst „Brak przypiętych punktów” zamiast pustej tabeli; akceptowalne jako ryzyko, bo backend uzupełnia wartości dla maksymalnie 6 pinów × 6 slotów.
- [P2-4] `packages/board-search-ui/src/management/management-game-workspace.tsx:937-940` — podpowiedź „Wybór planszy, zakres i punkty zapisujesz przyciskiem „Zapisz układ”” jest nieaktualna po wprowadzeniu etykiet „Zapisz zmiany” i „Zastąp układ” (`:950-959`). Proponowana poprawka: tekst opisujący trzy etykiety albo użycie bieżącej etykiety w komunikacie.
- [P2-5] `ai_docs/tasks/0942-management-compact-stakes.md:155,161` — po dostosowaniu pięciu testów Reviewer ponowiono wyłącznie `management-panel.test.mjs`; pełna suite `npm run test:geometry --workspace @game-predictor/reviewer` nie została uruchomiona na końcowym stanie. Ryzyko regresji jest niskie (zmiany ograniczone do tego pliku), ale komenda z sekcji Verification taska nie ma zielonego wyniku dla finalnego snapshotu. Proponowana poprawka: jedno pełne uruchomienie przed commitem i odnotowanie wyniku w Outcome.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Karta ma tylko stawkę, zapis-status i symbol-preview; cała klikalna, selected wyraźny | spełnione | `packages/board-search-ui/src/management/management-cards.tsx:91-123` (jeden `button`, `aria-pressed`, brak miniwykresu); `management.css:42-45,82-92`; test `apps/admin/test-interactions/management-cards.test.mjs:358-364,1321-1323` |
| Stored start z managementSavedSelection odtworzony deterministycznie; brak top-hit autochoose | spełnione | `packages/board-search-ui/src/board-search-workspace.tsx:151-169,231-235`; `management-game-workspace.tsx:498-506`; test `packages/board-search-ui/test-interactions/board-search-saved-selection.test.mjs:790-792` (0 wyszukiwań, kalkulacja od 999) |
| Nowy układ/reset nie czyści slotu; Save changes vs Replace wymaga CAS i confirm, Clear jawny | spełnione (z P2-1) | `management-game-workspace.tsx:599-658,909-936,950-959`; `board-search-workspace.tsx:404-413`; test `management-cards.test.mjs:1336-1429` (brak clear, confirm false → 0 zapisów, 422 → OLD, sukces → NEW, `expectedRevision` 1) |
| Spin/Wkład/Netto/Na maszynie zgodne ze wspólnymi helperami; zero i losing dozwolone, unavailable jawne | spełnione (edytor), niezweryfikowane dla metadanych bez wartości (P2-3) | `board-search-approximate-win.tsx:977-1016` (helpery `approximateWinStakeToPoint`/`approximateWinMachineCashAtPoint`, spin 0 → 0); test `board-search-saved-selection.test.mjs:795-806` (`['3','60','-60','0']`, spin 12 niedostępny) |
| 0–6 pinów i osie widoczne w rozwiniętym wykresie; brak miniChart | spełnione | `board-search-approximate-win.tsx:637-651` (chart dopiero po `chartOpen`), `:1536-1543` (osie „spiny”, „zł”), limit `board-search-approximate-win-state.ts:234`; `management-cards.tsx` bez `ManagementMiniChart`; test `board-search-saved-selection.test.mjs:807-810` |
| Quick preview nie pobiera full result; full tabela/history tylko po rozwinięciu; queue≤2 | spełnione | `management-game-workspace.tsx:866-889`; `management-result-view.tsx:131-144,159-232`; `management-journal.tsx:187-203`; `management-slot-state.ts:99-112`; testy `management-cards.test.mjs:287-313,1296-1334` |
| Default ordinary search/share zachowane, optional props i regression testy | spełnione (statycznie) | domyślne `compact = false`: `board-search-workspace.tsx:144-145`, `board-search-results.tsx:62`, `board-search-approximate-win.tsx:125,520-521`; gałęzie non-compact bez zmian semantyki (`board-search-results.tsx:171-178,199-214`, `board-search-approximate-win.tsx:677-706`); Outcome: 55/55 interakcji, 175/175 Admin |
| Zmiana globalnych symboli nadal zapisuje natychmiast, reset szkicu tego nie cofa | spełnione | `management-data-source.ts:183-229` bez zmian; reset dotyka tylko stanu edytora `board-search-workspace.tsx:404-413`; test Reviewer `apps/reviewer/test-interactions/management-panel.test.mjs:941-981` |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy, runda 1.

Otwarte: P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- Test anulowanego zastąpienia sprawdzający treść komunikatu: po `confirm → false` brak elementu `role="alert"` z tekstem „Nie udało się zapisać układu”; plik `apps/admin/test-interactions/management-cards.test.mjs`, komenda `node node_modules/tsx/dist/cli.mjs --tsconfig apps/admin/tsconfig.json --test apps/admin/test-interactions/management-cards.test.mjs`.
- Test szybkich wierszy dla pinu `available: true` z `requiredStakeCredits`/`machineCashCredits` ustawionymi przez backend (np. spin 3 → 60/−60/0) oraz dla spinu 0, aby zakotwiczyć kontrakt metadanych TASK-0940 po stronie UI; ten sam plik i komenda.
- Pełne `npm run test:geometry --workspace @game-predictor/reviewer` na końcowym snapshocie (P2-5).
- Test, że po „Zamknij szkic” summary „Pełny zapisany wynik” odzwierciedla widoczny wynik (po poprawce P2-2); plik `apps/admin/test-interactions/management-cards.test.mjs`.

## Zakres przeglądu i ograniczenia

Przeczytano w całości wszystkie trzynaście plików snapshotu `TASK-0942_STAGE/audit-source` (kod, CSS, testy, task) oraz pomocniczo z worktree: `management-slot-state.ts`, `board-search-approximate-win-state.ts`, `board-search-saved-selection.ts`, `board-search-results-state.ts`, `api-error.ts`, `management-client.ts`, typy `ManagementPinnedPoint`/`ManagementStakeResponse` w `admin-api-client`, sekcje TASK-0942 planu wykonania i wymagań `MANAGEMENT_PANEL.md`. Nie uruchamiano testów, lintera, typecheck ani Prettier; wyniki z Outcome przyjęto jako dowód wykonawcy. Nie oceniano geometrii przeglądarkowej 1440/1920/390 px ani `reviewer:management:browser`, które plan przypisuje TASK-0943. Nie sprawdzano zgodności numeracji wersji commita, bo commit jeszcze nie powstał.
