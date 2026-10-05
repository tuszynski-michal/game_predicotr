---
title: TASK-0841 — symbole i skróty dostępne po otwarciu planszy audytu
status: done
last_updated: 2026-10-04
---

# TASK-0841 — symbole i skróty dostępne po otwarciu planszy audytu

## Status

`done`

## Goal

Plansza w kolejce audytu pozwala od razu wybrać symbol klawiaturą lub paletą,
bez ręcznego ponawiania podglądu i bez przesuwania siatki.

## Context

Operator zgłosił brak skrótów znanych ze zwykłej korekty oraz konieczność
ponawiania podglądu. Kod kolejki audytu pomija `shortcut` przy mapowaniu
katalogu. Wspólny edytor czeka na wczytanie pełnego zdjęcia przed żądaniem
podglądu API i domyślnie nie zaznacza żadnego pola.

## Dependencies / entry conditions

- TASK-0840 jest wdrożony; baza deweloperska ma migrację `0140`.
- Polecenie operatora: skróty katalogu, `9 = Nie wiem`, edycja od otwarcia.
- Założenie UI: pierwsze pole mające piksele zostaje zaznaczone po gotowym
  podglądzie i katalogu. Samo zaznaczenie nie przypisuje ani nie zapisuje symbolu.
- Istniejące API podglądu korzysta z checksum-bound źródła po stronie serwera;
  wczytanie obrazu canvas nie jest potrzebne do tego odczytu.

## Recommended execution

`gpt-6.1-sol`, `medium`: ograniczona poprawka frontendu i regresji interakcji.
Bez delegowania. Rozszerzenie API, zmiana transakcji lub semantyki symboli
wymaga ponownej analizy zakresu przed implementacją.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — Korekta cięcia siatki, TASK-0840.
- `ai_docs/architecture/API_CONTRACT.md` — lokalna korekta, D-488.
- `ai_docs/delivery/GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md` — istniejący zapis D-488.
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` — Poprawki z audytu siatek.

## Scope

- Wspólne mapowanie katalogu na skróty z opcjonalną rezerwacją klawiszy.
- W kolejce audytu: `1–8` jak w katalogu, `9` dla „Nie wiem”; dalsze symbole
  dostają `0`, potem litery. Nie ma dwóch działań pod tym samym klawiszem.
- Opcjonalne ustawienia edytora dla audytu: podgląd niezależny od wczytywania
  canvas, pierwsze dostępne pole zaznaczone, skrót „Nie wiem”.
- Testy opóźnionego zdjęcia i katalogu, zapisu bez ruszania siatki, przejścia
  do kolejnej planszy oraz zachowania zwykłej korekty.
- Aktualizacja wymagań, instrukcji i bieżącego stanu.

## Out of scope

- Zmiany API, schematu, modeli siatek, trybu shadow i planu symboli Mumii.
- Zapis korekty na żywej bazie, migracje, usuwanie danych, push.
- Zmiana domyślnego zachowania zwykłej korekty i automatyczne etykietowanie.

## Acceptance criteria

- [x] Po otwarciu planszy podgląd powstaje bez ręcznych działań, także gdy
  pełne zdjęcie nadal się wczytuje lub katalog przychodzi później.
- [x] Pierwsze dostępne pole jest zaznaczone; paleta pokazuje klawisze.
- [x] `1`, `5`, `6` wybierają odpowiednio Wiśnię, Śliwkę, Arbuz według katalogu;
  `9` wybiera „Nie wiem” (`symbolId = null`).
- [x] Klawisze w polach tekstowych, modyfikatory i repeat nie przypisują symboli.
- [x] Zapis przez istniejący kontrakt przesyła wyłącznie jawne wybory, bez
  konieczności ruszania narożników. Kolejna plansza nie dziedziczy wyborów.
- [x] Opcjonalne ustawienia zachowują dotychczasową zwykłą korektę; testy,
  lint, typecheck i build Reviewera są poprawne.

## Technical notes

`buildOperationalReviewSymbolShortcuts` pozostaje źródłem kolejności skrótów.
Domyślnie zachowuje `1–9, 0, litery`; audyt rezerwuje `9`. W edytorze
podgląd musi nadal odpowiadać bieżącemu command key, nie powstaje podczas
przeciągania, a spóźnione odpowiedzi nie zastępują aktualnej geometrii.
Automatyczne zaznaczenie odbywa się raz na otwarcie celu i pomija pola bez
pikseli; nie przywraca pola po świadomym odznaczeniu. `null` nadal oznacza
nieczytelność, a brak wpisu oznacza brak decyzji operatora.

## Expected files

- `apps/reviewer/src/features/operational-reviews/operational-review-state.ts`
  — `buildOperationalReviewSymbolShortcuts`.
- `apps/reviewer/src/features/operational-reviews/grid-audit-correction-workspace.tsx`
  — katalog i ustawienia `BoardGeometryCorrectionEditor`.
- `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx`
  — opcjonalne ustawienia, preview i obsługa klawiatury.
- `apps/reviewer/test/operational-review-state.test.mjs` i
  `apps/reviewer/test-interactions/grid-audit-correction.test.mjs` — regresje.
- Dokumenty wymagań, instrukcji i stanu wymienione powyżej.

## Test cases

- Zdjęcie bez zdarzenia `load`, katalog opóźniony → podgląd i edycja są gotowe.
- Nieuporządkowany katalog, symbol zarchiwizowany → deterministyczne skróty.
- Bez kliknięcia cropa: `1`, `5`, `6`, `9` → etykieta pierwszego pola i `null`.
- Dziewiąty symbol katalogu → `0`; `9` pozostaje „Nie wiem”.
- Zapis mock API i następna plansza → niezmienione narożniki, tylko jawne
  etykiety, świeże zaznaczenie bez przeniesienia wyborów.
- Dotychczasowe interakcje zwykłej korekty → nadal wymaga kliknięcia pola,
  brak nowego skrótu „Nie wiem”, stare skróty działają.

## Verification

Katalog: `C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3`.
Komendy wykonywane przez istniejący bounded runner z limitem 120 s:

```powershell
& 'C:\Program Files\nodejs\node.exe' 'C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js' run test:geometry --workspace @game-predictor/reviewer
& 'C:\Program Files\nodejs\node.exe' 'C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js' run test --workspace @game-predictor/reviewer
& 'C:\Program Files\nodejs\node.exe' 'C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js' run lint --workspace @game-predictor/reviewer
& 'C:\Program Files\nodejs\node.exe' 'C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js' run typecheck --workspace @game-predictor/reviewer
```

Build: `run reviewer:build`, limit 300 s po uprzedzeniu operatora. Odbiór
w przeglądarce bez zapisu danych; kontrola świeżego otwarcia i skrótów.

## Risks / open questions

- Przy większym katalogu audyt przesuwa skróty od dziewiątego symbolu, aby
  zarezerwować `9`; paleta pokazuje rzeczywisty klawisz.
- Nie ma decyzji blokujących ten zakres.

## Outcome

Commit: `v1.7.186` / `65ce8f212cc5f2b3930251b6539f8787dcf8df13`
(wpis hash po commicie).

### Changed

- Kolejka audytu przekazuje skróty z istniejącego mapowania katalogu,
  rezerwuje `9` dla nieczytelności i pokazuje klawisze w palecie.
- Opcjonalne ustawienia wspólnego edytora uruchamiają preview niezależnie od
  canvas i zaznaczają pierwsze pole z pikselami po odpowiedzi podglądu.
  Późniejszy katalog nie wymaga odświeżenia. Świadome odznaczenie jest zachowane.
- `9` zapisuje lokalny wybór `null`; tylko jawne wybory trafiają do istniejącej
  komendy zapisu. Przejście do kolejnej planszy usuwa poprzednie wybory.
- Domyślne zachowanie zwykłej korekty zachowane, bez zmian API i bazy.

### Verification results

- Regresje przed zmianą: oba nowe testy kończyły się `0 !== 1` przy oczekiwaniu
  automatycznego preview podczas opóźnionego zdjęcia; stare testy audytu 3/3.
- Po zmianie: skoncentrowane interakcje 14/14; testy stanu 22/22.
- Pełne interakcje Reviewera 18/18, jednostkowe 208/208, lint i typecheck czyste.
- Formatowanie pięciu plików kodu/testów zgodne z Prettier.
- `reviewer:build` poprawny w worktree (20,36 s). Ostrzeżenie Next o dwóch
  lockfile przy wykrywaniu root; brak błędu builda.
- Zestaw interakcji obejmuje zwykłą korektę, spóźnione odpowiedzi, nawigację,
  utratę odpowiedzi zapisu i nowy mount; nie osłabiono dotychczasowych testów.
- Fast-forward do `v1.1-vision-lab-hybrid-geometry`; build w głównym checkoutu
  poprawny (17,27 s). Reviewer uruchomiony w nowym procesie (launcher PID 3432),
  HTTP 200. Pierwszy ograniczony polling z timeoutem 1 s na request nie
  potwierdził gotowości; logi i osobny odczyt HTTP potwierdziły działanie
  tej samej kopii. Nie uruchomiono drugiego procesu.
- Odbiór na żywo po restarcie: plansza 423759 otwarta z 15/15 cropów,
  zaznaczonym pierwszym polem i klawiszami palety. `1` Wiśnia, `5` Śliwka,
  `6` Arbuz i `9` „Nie wiem” wybierają symbol bez kliknięcia cropa,
  przesuwania siatki lub „Ponów podgląd”. Testowy wybór wyczyszczono lokalnie;
  nie naciśnięto zapisu. Screenshot:
  `artifacts/grid-v3-deployment-20261004/task0841-live.jpg`.
- Kryteria taska i właściwe punkty DoD sprawdzone. Zmiana lokalnej korekty
  desktopowej; dotykowa paleta nadal korzysta z istniejących przycisków.

### Not completed

- Zapis na żywej bazie poza zakresem.
- Bez push, zmian API, migracji i uruchamiania shadow.

### Documentation updates

- `ADMIN_APP.md`: zachowanie audytu i domyślnej korekty.
- `LOCAL_OPERATION_GUIDE.md`: edycja bez ruszania siatki, skróty i moment zapisu.
- `CURRENT_STATE.md`: rezultat oraz wyniki kontroli.

### Recommended next task

- Odbiór przez operatora podczas korekty listy audytu.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
| TASK-0841 | gpt-6.1-sol | medium | Poprawka stanu UI i skrótów, istniejący kontrakt API oraz testy interakcji. | Nie; regresje wszystkich konsumentów edytora i kontrola diffu. |
